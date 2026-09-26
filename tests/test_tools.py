import asyncio
import os
import sys
import time
from pathlib import Path
import pytest
from lebotclaw_harness.tools import ToolContext,default_registry,command_run


@pytest.fixture
def context(tmp_path):
    workspace=tmp_path/'project';workspace.mkdir()
    home=tmp_path/'state';home.mkdir()
    return ToolContext(workspace,home,'run-test',{'mode':'off'})


def test_paths_schema_hash_and_symlink(context,tmp_path):
    async def run():
        r=default_registry()
        for path in ('../outside','/etc/passwd','.env','node_modules/secret'):
            assert not (await r.execute('file_write',{'path':path,'content':'bad'},context))['ok']
        (context.workspace/'link').symlink_to(tmp_path,target_is_directory=True)
        assert not (await r.execute('file_read',{'path':'link/anything'},context))['ok']
        assert not (await r.execute('file_write',{'path':'a.txt','content':4},context))['ok']
        assert (await r.execute('file_write',{'path':'a.txt','content':'one'},context))['ok']
        original=await r.execute('file_read',{'path':'a.txt'},context)
        assert not (await r.execute('file_write',{'path':'a.txt','content':'two'},context))['ok']
        (context.workspace/'a.txt').write_text('changed-by-user')
        assert not (await r.execute('file_write',{'path':'a.txt','content':'two','expected_sha256':original['data']['sha256']},context))['ok']
        assert (context.workspace/'a.txt').read_text()=='changed-by-user'
        assert (await r.execute('command_run',{'argv':['anything']},context))['code']=='EXECUTION_DISABLED'
        (context.workspace/'node_modules').mkdir();(context.workspace/'node_modules'/'hidden').write_text('secret')
        listing=await r.execute('files_list',{'recursive':True},context)
        assert listing['data']['entries']==[{'path':'a.txt','kind':'file'}]
    asyncio.run(run())


@pytest.mark.skipif(os.name!='posix',reason='POSIX host process cleanup')
def test_command_timeout_cleans_children_and_environment(context,monkeypatch):
    context.execution={'mode':'host'};monkeypatch.setenv('SECRET_TEST_TOKEN','DO-NOT-INHERIT')
    async def run():
        result=await command_run({'argv':[sys.executable,'-c',"import os; print(os.environ.get('SECRET_TEST_TOKEN','absent'))"]},context)
        assert result['stdout'].strip()=='absent' and result['exit_code']==0
        # The parent exits; the grandchild must not survive to write a delayed file.
        script="import subprocess,sys; subprocess.Popen([sys.executable,'-c',\"import time; time.sleep(2); open('leaked','w').write('bad')\"]);"
        result=await command_run({'argv':[sys.executable,'-c',script],'timeout_seconds':1},context)
        await asyncio.sleep(2.2)
        assert not (context.workspace/'leaked').exists()
        slow=asyncio.create_task(command_run({'argv':[sys.executable,'-c',"import time; time.sleep(2); open('cancelled-leak','w').write('bad')"]},context))
        await asyncio.sleep(.1);slow.cancel()
        with pytest.raises(asyncio.CancelledError):await slow
        await asyncio.sleep(2.2)
        assert not (context.workspace/'cancelled-leak').exists()
    asyncio.run(run())


def test_explicit_plugin(context,tmp_path):
    p=tmp_path/'extension.py';p.write_text('from lebotclaw_harness import Tool\ndef register(registry):\n registry.register(Tool("double", "Double a number", {"type":"object","properties":{"n":{"type":"integer"}},"required":["n"],"additionalProperties":False}, lambda a,c: {"value":a["n"]*2}))\n')
    r=default_registry();r.load_plugin(p)
    assert asyncio.run(r.execute('double',{'n':7},context))=={'ok':True,'data':{'value':14}}
    assert not asyncio.run(r.execute('double',{'n':'bad'},context))['ok']


@pytest.mark.skipif(os.name!='posix',reason='POSIX FIFO')
def test_file_tool_rejects_fifo_without_blocking(context):
    os.mkfifo(context.workspace/'pipe')
    r=default_registry()
    assert not asyncio.run(r.execute('file_read',{'path':'pipe'},context))['ok']
    assert not asyncio.run(r.execute('file_write',{'path':'pipe','content':'bad'},context))['ok']
