"""User grants and per-action approvals. Model output cannot create a grant."""
import asyncio
import copy
import json
import secrets

MODES = ('plan', 'ask', 'auto', 'full')


def plan():
    return {'mode': 'plan', 'read': False, 'write': False, 'execute': False,
            'images': False, 'network': False, 'execution': 'off',
            'remember': False, 'image_limit': 4, 'max_steps': 40,
            'max_seconds': 1200, 'max_tokens': 150000}


class Permissions:
    def __init__(self, store):
        self.store = store
        self.temporary = {}
        self.pending = {}
        with store.lock, store.db:
            store.db.execute('CREATE TABLE IF NOT EXISTS grants(workspace TEXT PRIMARY KEY, body TEXT NOT NULL)')

    def get(self, workspace):
        if workspace in self.temporary:
            return copy.deepcopy(self.temporary[workspace])
        with self.store.lock:
            row = self.store.db.execute('SELECT body FROM grants WHERE workspace=?', (workspace,)).fetchone()
        return {**plan(), **json.loads(row[0])} if row else plan()

    @staticmethod
    def validate(value):
        result = plan()
        if value.get('mode') not in MODES:
            raise ValueError('请选择有效的执行模式。')
        result['mode'] = value['mode']
        for field in ('read', 'write', 'execute', 'images', 'network', 'remember'):
            if field in value and type(value[field]) is not bool:
                raise ValueError('授权选项必须是布尔值。')
            result[field] = value.get(field, False)
        for field, minimum, maximum in (('image_limit', 0, 20), ('max_steps', 1, 100),
                                        ('max_seconds', 30, 3600), ('max_tokens', 1000, 1000000)):
            n = value.get(field, result[field])
            if type(n) is not int or not minimum <= n <= maximum:
                raise ValueError('任务预算超出允许范围：' + field)
            result[field] = n
        execution = value.get('execution', 'off')
        if execution not in ('off', 'docker', 'host'):
            raise ValueError('请选择有效的命令执行环境。')
        if result['mode'] == 'plan':
            result.update(write=False, execute=False, images=False, network=False)
        if result['execute'] and execution == 'off':
            raise ValueError('运行命令需要选择 Docker 或本机执行环境。')
        if result['execute'] and execution == 'host':
            if value.get('acknowledge_host') is not True or result['network'] is not True:
                raise ValueError('本机命令使用当前用户权限，可访问项目外文件和网络；需单独确认。限制在项目内执行请选择 Docker。')
        if result['write'] or result['execute'] or result['images']:
            result['read'] = True
        if result['execute'] or result['images']:
            result['write'] = True
        result['execution'] = execution if result['execute'] else 'off'
        return result

    def save(self, workspace, value):
        result = self.validate(value)
        with self.store.lock, self.store.db:
            self.store.db.execute('DELETE FROM grants WHERE workspace=?', (workspace,))
            if result['remember']:
                self.store.db.execute('INSERT INTO grants VALUES(?,?)', (workspace, json.dumps(result)))
        self.temporary.pop(workspace, None)
        if not result['remember']:
            self.temporary[workspace] = result
        return copy.deepcopy(result)

    def finish(self, workspace):
        current = self.temporary.get(workspace)
        if current:
            self.temporary[workspace] = {**plan(), 'read': current['read']}

    def allowed(self, workspace, tool):
        grant = self.get(workspace)
        if tool.effect == 'read':
            return grant['read']
        if grant['mode'] == 'plan':
            return False
        if tool.name == 'image_generate':
            return grant['write'] and grant['images']
        if tool.effect == 'execute':
            return grant['execute']
        return grant['write']

    async def check(self, sid, rid, workspace, tool, args):
        if not self.allowed(workspace, tool):
            raise ValueError('PERMISSION_REQUIRED：此操作未授权。请用户在“授权执行”中调整；模型不能自行授权。')
        grant = self.get(workspace)
        # Isolated routine commands may run in auto. Unconfined host commands
        # and chargeable image requests remain reviewable in auto mode.
        important = tool.name == 'image_generate' or (tool.effect == 'execute' and grant['execution'] == 'host')
        needs = tool.effect != 'read' and (grant['mode'] == 'ask' or (grant['mode'] == 'auto' and important))
        if not needs:
            return
        aid = secrets.token_urlsafe(18)
        future = asyncio.get_running_loop().create_future()
        data = {'id': aid, 'session': sid, 'run': rid, 'tool': tool.name,
                'arguments': copy.deepcopy(args), 'effect': tool.effect, 'workspace': workspace}
        self.pending[aid] = (data, future)
        self.store.event(sid, rid, 'approval.requested', data)
        if hasattr(self, 'notify'):
            self.notify(sid, rid, data)
        try:
            approved = await future
            if not approved:
                raise ValueError('USER_REJECTED：用户拒绝本项操作。不要换一种工具绕过拒绝。')
            if not self.allowed(workspace, tool):
                raise ValueError('授权已撤销，未执行。')
        finally:
            self.pending.pop(aid, None)

    def resolve(self, aid, approved):
        if type(approved) is not bool or aid not in self.pending:
            raise ValueError('批准请求已失效，请刷新任务。')
        data, future = self.pending[aid]
        if future.done():
            raise ValueError('此操作已经处理。')
        self.store.event(data['session'], data['run'], 'approval.decided', {'id': aid, 'approved': approved})
        future.set_result(approved)
        return {'accepted': True}

    def list(self, sid):
        return [copy.deepcopy(d) for d, f in self.pending.values() if d['session'] == sid and not f.done()]
