import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from . import __version__
from .config import Config, home_path
from .runtime import Runtime
from .model import ModelError
from .store import Store
from .tools import default_registry


def parser():
    p = argparse.ArgumentParser(prog='lebotclaw', description='LebotClaw Harness · 超级小博的开源智能体运行环境')
    p.add_argument('--version', action='version', version=__version__)
    p.add_argument('--home', help='运行数据目录，默认 ~/.lebotclaw-harness')
    commands = p.add_subparsers(dest='command', required=True)
    commands.add_parser('init', help='初始化配置与数据目录')
    models = commands.add_parser('models', help='管理模型配置').add_subparsers(dest='action', required=True)
    models.add_parser('list')
    add = models.add_parser('add')
    add.add_argument('name'); add.add_argument('--provider', choices=['deepseek','glm','openai-compatible'], required=True)
    add.add_argument('--model', required=True); add.add_argument('--base-url'); add.add_argument('--key-env'); add.add_argument('--vision', action='store_true')
    add.add_argument('--max-output-tokens', type=int, help='每次模型回复的输出预算，默认 8192')
    add.add_argument('--reasoning-effort', choices=['', 'low', 'medium', 'high', 'max'], help='仅在模型支持时设置')
    use = models.add_parser('use'); use.add_argument('name')
    test = models.add_parser('test'); test.add_argument('name', nargs='?')
    for command in ('run', 'resume'):
        run = commands.add_parser(command, help='执行任务' if command == 'run' else '继续已保存的会话')
        if command == 'resume': run.add_argument('session')
        run.add_argument('prompt', nargs='?', default='继续之前的任务，先检查现有状态。' if command == 'resume' else None)
        run.add_argument('--workspace'); run.add_argument('--model'); run.add_argument('--json', action='store_true')
        run.add_argument('--max-steps', type=int, default=24); run.add_argument('--max-seconds', type=int, default=600)
        run.add_argument('--mode', choices=['plan','ask','auto','full'], default='plan')
        run.add_argument('--allow-read', action='store_true'); run.add_argument('--allow-write', action='store_true')
        run.add_argument('--allow-commands', action='store_true'); run.add_argument('--allow-images', action='store_true')
        run.add_argument('--allow-network', action='store_true')
        run.add_argument('--execution-mode', choices=['off','docker','host'], default='off')
        run.add_argument('--acknowledge-unrestricted-host-access', action='store_true')
    sessions = commands.add_parser('sessions').add_subparsers(dest='action', required=True)
    sessions.add_parser('list')
    show = sessions.add_parser('show'); show.add_argument('session')
    export = sessions.add_parser('export'); export.add_argument('session'); export.add_argument('--output', required=True)
    tools = commands.add_parser('tools'); tools.add_argument('action', choices=['list'])
    plugins = commands.add_parser('plugins').add_subparsers(dest='action', required=True)
    plugins.add_parser('list')
    plug = plugins.add_parser('add'); plug.add_argument('path'); plug.add_argument('--trust-code', action='store_true', required=True)
    execution = commands.add_parser('execution')
    execution.add_argument('mode', choices=['off','docker','host']); execution.add_argument('--image')
    execution.add_argument('--acknowledge-unrestricted-host-access', action='store_true')
    web = commands.add_parser('web', help='启动本地服务及浏览器界面')
    web.add_argument('--port', type=int, default=18866)
    web.add_argument('--open', action='store_true', help='启动后在默认浏览器打开')
    commands.add_parser('doctor', help='检查安装、配置和运行环境')
    return p


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


async def run_task(args, home):
    runtime = Runtime(home)
    try:
        session = runtime.store.session(args.session) if args.command == 'resume' else runtime.store.create((args.prompt or '新任务')[:60], args.workspace)
        if args.command == 'resume' and args.workspace and Path(args.workspace).resolve() != Path(session['workspace']):
            raise ValueError('继续任务时不能悄悄切换项目目录。')
        goal = args.prompt or (sys.stdin.read() if not sys.stdin.isatty() else '')
        await runtime.grant(session['id'], {'mode':args.mode,'read':args.allow_read,'write':args.allow_write,
            'execute':args.allow_commands,'images':args.allow_images,'network':args.allow_network,
            'execution':args.execution_mode,'acknowledge_host':args.acknowledge_unrestricted_host_access,
            'max_steps':args.max_steps,'max_seconds':args.max_seconds})
        async def handle_approval(data):
            approved = False
            if sys.stdin.isatty() and not args.json:
                print('\n待批准：' + data['tool'] + '\n' + json.dumps(data['arguments'],ensure_ascii=False))
                answer = await asyncio.to_thread(input, '批准此操作？[y/N] ')
                approved = answer.strip().lower() == 'y'
            try: await runtime.approve(data['id'],approved)
            except ValueError: pass
        if not args.json:
            print('会话：' + session['id']); print('项目：' + session['workspace'])
        def listener(event):
            if event['kind']=='approval.requested':
                asyncio.create_task(handle_approval(event['data']))
            if args.json:
                print(json.dumps(event, ensure_ascii=False), flush=True)
            elif event['kind'] == 'text.delta':
                print(event['data']['text'], end='', flush=True)
            elif event['kind'] == 'model.request':
                print('\n[处理第 %s 步]' % event['data']['step'], flush=True)
        runtime.listeners.append(listener)
        rid = await runtime.start(session['id'], goal, model=args.model, max_steps=args.max_steps, max_seconds=args.max_seconds)
        await runtime.wait(rid)
        result = runtime.store.session(session['id'])
        if args.json:
            print(json.dumps({'kind':'run.result','session':result}, ensure_ascii=False))
        else:
            print('\n状态：' + result['last_run']['status'])
            history = runtime.store.history(session['id'], public=True)
            if history and history[-1]['role'] == 'assistant':
                print('\n' + str(history[-1].get('content') or ''))
            events = []
            after = 0
            while True:
                batch = runtime.store.events(session['id'], after)
                if not batch: break
                events.extend(batch); after = batch[-1]['seq']
            if events and events[-1]['kind'] in ('run.failed','run.incomplete','run.cancelled'):
                print(events[-1]['data'].get('message', ''))
        return 0 if result['last_run']['status'] == 'completed' else 2
    finally:
        await runtime.shutdown()
        runtime.close()


def main(argv=None):
    args = parser().parse_args(argv)
    home = home_path(args.home)
    try:
        config = Config(home)
        if args.command == 'init':
            config.save(); print('已初始化：' + str(home))
        elif args.command == 'models':
            if args.action == 'add':
                config.add_model(args.name,args.provider,args.model,args.base_url,args.key_env,args.vision,args.max_output_tokens,args.reasoning_effort)
                print('已保存模型配置，密钥值未写入文件。')
            elif args.action == 'use':
                config.model(args.name); config.data['active_model'] = args.name; config.save(); print('已切换。')
            elif args.action == 'list':
                print_json({'active':config.data['active_model'],'models':config.data['models']})
            elif args.action == 'test':
                runtime = Runtime(home, acquire=False)
                try:
                    _, _, model = runtime.resolve_model(args.name)
                    answer = asyncio.run(model.complete([{'role':'user','content':'请只回复连接成功。'}], []))
                    print(answer.message.get('content','')); print('文字接口已连通；这不等同于完整工具能力验证。')
                finally: runtime.close()
        elif args.command in ('run', 'resume'):
            return asyncio.run(run_task(args, home))
        elif args.command == 'sessions':
            store = Store(home)
            try:
                if args.action == 'list': print_json(store.sessions())
                else:
                    store.session(args.session)
                    value={'session':store.session(args.session),'messages':store.history(args.session, public=True),'events':[]}
                    after=0
                    while True:
                        rows=store.events(args.session,after)
                        if not rows: break
                        value['events'].extend(rows); after=rows[-1]['seq']
                    if args.action == 'show': print_json(value)
                    else:
                        output=Path(args.output)
                        with output.open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,indent=2)
                        print(str(output.resolve()))
            finally: store.close()
        elif args.command == 'tools':
            registry=default_registry()
            for plugin in config.data['plugins']: registry.load_plugin(plugin['path'])
            print_json([{'name':t.name,'effect':t.effect,'description':t.description} for t in registry.tools.values()])
        elif args.command == 'plugins':
            if args.action=='list': print_json(config.data['plugins'])
            else:
                path=Path(args.path).expanduser().resolve()
                if not path.is_file() or path.suffix!='.py': raise ValueError('扩展必须是明确的 .py 文件。')
                if not any(p['path']==str(path) for p in config.data['plugins']):
                    config.data['plugins'].append({'path':str(path),'trusted':True}); config.save()
                print('已登记受信任代码扩展。它拥有宿主 Python 进程权限；下次启动生效。')
        elif args.command == 'execution':
            if args.mode=='host' and not args.acknowledge_unrestricted_host_access:
                raise ValueError('host 不是沙箱，可能访问同一用户的文件和网络。确认使用时加 --acknowledge-unrestricted-host-access。')
            if args.mode=='host' and os.name!='posix':
                raise ValueError('本版本 host 进程树回收仅支持 POSIX；Windows 请使用已配置 Docker。')
            config.set_execution(args.mode,args.image);print('执行模式：'+args.mode)
        elif args.command == 'web':
            from .web import serve
            serve(home,args.port,open_browser=args.open)
        elif args.command == 'doctor':
            import shutil
            print_json({'version':__version__,'python':sys.version.split()[0],'home':str(home),'models':list(config.data['models']),
                        'execution':config.data['execution'],'docker_binary':bool(shutil.which('docker')),
                        'note':'找到 docker 命令不代表 daemon、镜像或隔离已经验证。'})
        return 0
    except KeyboardInterrupt:
        print('\n已停止。',file=sys.stderr);return 130
    except Exception as exc:
        # Controlled error messages only; provider SDK errors must be sanitized earlier.
        if isinstance(exc, (ValueError, ModelError)):
            print(str(exc),file=sys.stderr)
        else:
            print('操作失败：'+type(exc).__name__,file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
