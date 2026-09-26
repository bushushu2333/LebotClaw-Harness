import asyncio
import json
import os
import sys
from pathlib import Path
import pytest
from lebotclaw_harness.config import Config
from lebotclaw_harness.runtime import Runtime
from lebotclaw_harness.model import ModelReply
from lebotclaw_harness.store import Store
from lebotclaw_harness.tools import Tool, schema
from conftest import sse, tool_reply


def configured(tmp_path, endpoint='http://127.0.0.1:1/v1', execution='off'):
    home=tmp_path/'state'; c=Config(home)
    c.add_model('test','openai-compatible','test-fixture',endpoint)
    c.set_execution(execution)
    return home


def test_http_model_read_write_execute_repair_and_resume(tmp_path, serve_model, monkeypatch):
    """Scripted model decisions, real HTTP/SSE, filesystem, subprocess, SQLite and restart."""
    workspace=tmp_path/'project'; workspace.mkdir()
    (workspace/'input.csv').write_text('name,minutes\n阅读,25\n制作,35\n')
    bad="import csv\nrows=list(csv.DictReader(open('input.csv')))\nprint(sum(int(r['wrong']) for r in rows))\n"
    good="import csv,json,os\nrows=list(csv.DictReader(open('input.csv')))\nassert os.getenv('LEBOT_TEST_SECRET') is None\nvalue={'total':sum(int(r['minutes']) for r in rows),'count':len(rows)}\nopen('result.json','w').write(json.dumps(value))\nprint(json.dumps(value))\n"
    monkeypatch.setenv('LEBOT_TEST_SECRET','test-not-inherited')
    def respond(body, n):
        assert body['model']=='test-fixture' and body['tools']
        if n==1: assert 'input.csv' in body['messages'][-1]['content']; reply=tool_reply('file_read',{'path':'input.csv'},'read')
        elif n==2:
            assert '25' in body['messages'][-1]['content']
            assert body['messages'][-2]['reasoning_content']=='测试协议字段保留'
            reply=tool_reply('file_write',{'path':'analyze.py','content':bad},'write')
        elif n==3: reply=tool_reply('command_run',{'argv':[sys.executable,'analyze.py']},'execute_bad')
        elif n==4:
            result=json.loads(body['messages'][-1]['content'])['data']
            assert result['exit_code']!=0 and 'KeyError' in result['stderr']
            reply=tool_reply('file_read',{'path':'analyze.py'},'inspect')
        elif n==5:
            hashed=json.loads(body['messages'][-1]['content'])['data']['sha256']
            reply=tool_reply('file_write',{'path':'analyze.py','content':good,'expected_sha256':hashed},'repair')
        elif n==6: reply=tool_reply('command_run',{'argv':[sys.executable,'analyze.py']},'execute_good')
        elif n==7:
            result=json.loads(body['messages'][-1]['content'])['data']
            assert result['exit_code']==0 and json.loads(result['stdout'])=={'total':60,'count':2}
            reply={'role':'assistant','content':'完成了汇总，程序实际输出 60 分钟。'}
        else:
            assert body['messages'][-1]['content']=='检查刚才保存的成果'
            assert len(body['messages'])>10
            reply={'role':'assistant','content':'已保留会话和运行记录。'}
        return sse(reply)
    with serve_model(respond) as (endpoint,requests):
        home=configured(tmp_path,endpoint,'host')
        async def run():
            rt=Runtime(home)
            try:
                sid=rt.store.create('CSV 汇总',workspace)['id']
                await rt.grant(sid,{'mode':'full','read':True,'write':True,'execute':True,'execution':'host','network':True,'acknowledge_host':True,'remember':True})
                rid=await rt.start(sid,'分析 input.csv，计算总分钟数，保存分析脚本和 result.json。')
                await rt.wait(rid)
                assert rt.store.run(rid)['status']=='completed'
                assert rt.store.run(rid)['steps']==7
                assert json.loads((workspace/'result.json').read_text())=={'total':60,'count':2}
                assert list((home/'versions'/rid).iterdir())
                return sid
            finally: await rt.shutdown(); rt.close()
        sid=asyncio.run(run())
        async def resume():
            rt=Runtime(home)
            try:
                rid=await rt.start(sid,'检查刚才保存的成果');await rt.wait(rid)
                assert rt.store.run(rid)['status']=='completed'
                assert len(rt.store.history(sid))==16
            finally: await rt.shutdown();rt.close()
        asyncio.run(resume())
        assert len(requests)==8


class WaitingModel:
    async def complete(self,*args):
        await asyncio.Event().wait()


@pytest.mark.parametrize('started',[False,True])
def test_cancel_and_workspace_lease(tmp_path, started):
    async def run():
        rt=Runtime(configured(tmp_path),model_factory=lambda *_:WaitingModel())
        try:
            s=rt.store.create(); other=rt.store.create(workspace=s['workspace'])
            rid=await rt.start(s['id'],'等待')
            if started: await asyncio.sleep(.02)
            with pytest.raises(ValueError,match='运行中的任务'):
                await rt.start(other['id'],'冲突的写入')
            await rt.cancel(rid)
            assert rt.store.run(rid)['status']=='cancelled'
            assert not rt.workspaces
            again=await rt.start(other['id'],'新运行');await rt.cancel(again)
        finally:await rt.shutdown();rt.close()
    asyncio.run(run())


def test_recovery_marks_unknown_without_repeating(tmp_path):
    home=configured(tmp_path); st=Store(home); s=st.create();sid=s['id'];rid=st.begin(sid,'write','test')
    st.status(sid,rid,'running');st.message(sid,rid,tool_reply('file_write',{'path':'result.txt','content':'once'}))
    st.action_start(sid,rid,'call_1','file_write',{'path':'result.txt','content':'once'})
    (Path(s['workspace'])/'result.txt').write_text('once')
    st.close()
    rt=Runtime(home)
    try:
        assert rt.store.run(rid)['status']=='interrupted'
        history=rt.store.history(sid)
        assert history[-1]['role']=='tool'
        assert json.loads(history[-1]['content'])['outcome']=='unknown_or_not_started'
        assert (Path(s['workspace'])/'result.txt').read_text()=='once'
        assert rt.store.db.execute('SELECT status FROM actions').fetchone()[0]=='unknown'
        rt.store.recover()
        assert rt.store.history(sid)==history
    finally:rt.close()


def test_budget_and_provider_change(tmp_path):
    class Listing:
        async def complete(self,*args):return ModelReply(tool_reply('files_list',{}),{},'tool_calls')
    async def run():
        home=configured(tmp_path);rt=Runtime(home,model_factory=lambda *_:Listing())
        try:
            sid=rt.store.create()['id'];rid=await rt.start(sid,'一直列文件',max_steps=2);await rt.wait(rid)
            assert rt.store.run(rid)['status']=='incomplete'
            assert rt.store.run(rid)['steps']==2
            c=Config(home);c.add_model('other','openai-compatible','different','http://127.0.0.1:1/v1')
            with pytest.raises(ValueError,match='协议状态'):await rt.start(sid,'继续',model='other')
        finally:await rt.shutdown();rt.close()
    asyncio.run(run())


def test_process_lock(tmp_path):
    rt=Runtime(configured(tmp_path))
    try:
        with pytest.raises(ValueError,match='已有运行'):Runtime(rt.home)
    finally:rt.close()


def test_cancel_during_side_effect_repairs_protocol(tmp_path):
    entered=None
    async def handler(args,ctx):
        (ctx.workspace/'once').write_text('written');entered.set();await asyncio.Event().wait()
    class Model:
        async def complete(self,*_):return ModelReply(tool_reply('write_then_wait',{}),{},'tool_calls')
    async def run():
        nonlocal entered
        entered=asyncio.Event()
        rt=Runtime(configured(tmp_path),model_factory=lambda *_:Model());rt.registry.register(Tool('write_then_wait','test',schema(),handler,'write'))
        try:
            sid=rt.store.create()['id']
            await rt.grant(sid,{'mode':'full','write':True})
            rid=await rt.start(sid,'执行')
            await asyncio.wait_for(entered.wait(),2);await rt.cancel(rid)
            assert rt.store.run(rid)['status']=='cancelled'
            assert rt.store.history(sid)[-1]['role']=='tool'
            assert rt.store.db.execute('SELECT status FROM actions').fetchone()[0]=='unknown'
        finally:await rt.shutdown();rt.close()
    asyncio.run(run())


def test_failed_first_request_can_fix_endpoint_without_new_session(tmp_path):
    from lebotclaw_harness.model import ModelError
    class Broken:
        async def complete(self,*_):raise ModelError('错误地址')
    class Fixed:
        async def complete(self,*args):
            if len(args)>2:args[2]('你好')
            return ModelReply({'role':'assistant','content':'你好'}, {}, 'stop')
    async def run():
        home=configured(tmp_path);rt=Runtime(home,model_factory=lambda *_:Broken())
        try:
            sid=rt.store.create()['id'];rid=await rt.start(sid,'你好');await rt.wait(rid)
            assert rt.store.run(rid)['status']=='failed'
            assert not rt.progress
            Config(home).add_model('fixed','openai-compatible','fixed-model','http://127.0.0.1:2/v1')
            rt.model_factory=lambda *_:Fixed()
            rid=await rt.start(sid,'你好',model='fixed');await rt.wait(rid)
            assert rt.store.run(rid)['status']=='completed'
            assert rt.store.history(sid)[-1]['content']=='你好'
            assert not rt.progress
        finally:await rt.shutdown();rt.close()
    asyncio.run(run())
