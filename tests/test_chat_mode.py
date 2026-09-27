import asyncio
import json
import threading
from http.server import ThreadingHTTPServer
import httpx
import pytest
from lebotclaw_harness.config import Config
from lebotclaw_harness.runtime import Runtime
from lebotclaw_harness.store import Store
from lebotclaw_harness.web import Service, Handler
from conftest import sse


def test_store_chat_and_project_sessions(tmp_path):
    store = Store(tmp_path / 'state')
    chat = store.create('随便聊聊', kind='chat')
    project = store.create('做东西')
    assert chat['kind'] == 'chat' and chat['workspace'] == ''
    assert project['kind'] == 'project' and project['workspace']
    assert not (tmp_path / 'state' / 'workspaces' / chat['id']).exists()
    store.close()
    # 重新打开：kind 保留；旧库迁移列存在
    store = Store(tmp_path / 'state')
    assert store.session(chat['id'])['kind'] == 'chat'
    assert store.session(project['id'])['kind'] == 'project'
    store.close()


def test_chat_run_has_no_tools_and_chat_grant_rejected(tmp_path, serve_model):
    def respond(body, n):
        assert not body.get('tools'), '聊天会话不应提供任何工具'
        system = body['messages'][0]['content']
        assert '聊天会话' in system and '开始制作' in system
        return sse({'role': 'assistant', 'content': '你好呀，聊聊吧。'})
    with serve_model(respond) as (endpoint, requests):
        home = tmp_path / 'state'
        c = Config(home)
        c.add_model('test', 'openai-compatible', 'test-fixture', endpoint)
        async def run():
            rt = Runtime(home)
            try:
                sid = rt.store.create('聊天', kind='chat')['id']
                rid = await rt.start(sid, '你好')
                await rt.wait(rid)
                assert rt.store.run(rid)['status'] == 'completed'
                history = rt.store.history(sid, public=True)
                assert history[-1]['content'] == '你好呀，聊聊吧。'
                with pytest.raises(ValueError):
                    await rt.grant(sid, {'mode': 'plan', 'read': True})
            finally:
                await rt.shutdown(); rt.close()
        asyncio.run(run())


def test_concurrent_chat_sessions_do_not_collide(tmp_path, serve_model):
    def respond(body, n):
        return sse({'role': 'assistant', 'content': '回复 ' + str(n)})
    with serve_model(respond) as (endpoint, requests):
        home = tmp_path / 'state'
        c = Config(home)
        c.add_model('test', 'openai-compatible', 'test-fixture', endpoint)
        async def run():
            rt = Runtime(home)
            try:
                a = rt.store.create('聊天 A', kind='chat')['id']
                b = rt.store.create('聊天 B', kind='chat')['id']
                rid_a = await rt.start(a, '问题一')
                rid_b = await rt.start(b, '问题二')
                with pytest.raises(ValueError):
                    await rt.start(a, '重复开始')
                await asyncio.gather(rt.wait(rid_a), rt.wait(rid_b))
                assert rt.store.run(rid_a)['status'] == 'completed'
                assert rt.store.run(rid_b)['status'] == 'completed'
            finally:
                await rt.shutdown(); rt.close()
        asyncio.run(run())


def test_web_chat_session_and_promote(tmp_path):
    service = Service(tmp_path / 'state')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.service = service
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with httpx.Client(base_url='http://127.0.0.1:' + str(server.server_port), trust_env=False) as client:
            client.headers['X-Lebot-Token'] = client.get('/api/bootstrap').json()['token']
            chat = client.post('/api/session', json={'title': '聊聊', 'kind': 'chat'}).json()
            assert chat['kind'] == 'chat' and chat['workspace'] == ''
            detail = client.get('/api/session', params={'id': chat['id']}).json()
            assert detail['files'] == [] and detail['session']['kind'] == 'chat'
            denied = client.get('/api/file', params={'session': chat['id'], 'path': 'x.txt'})
            assert denied.status_code == 400 and '聊天会话' in denied.json()['error']
            rejected = client.post('/api/permission', json={'session': chat['id'], 'permission': {'mode': 'plan', 'read': True}})
            assert rejected.status_code == 400
            # 模拟聊过几轮，再转成项目：要点应作为背景材料带入
            store = service.runtime.store
            store.message(chat['id'], None, {'role': 'user', 'content': '我想做一个打砖块游戏'})
            store.message(chat['id'], None, {'role': 'assistant', 'content': '好主意，可以先规划关卡和素材。'})
            promoted = client.post('/api/session/promote', json={'session': chat['id'], 'title': '打砖块'}).json()
            assert promoted['kind'] == 'project' and promoted['workspace']
            history = store.history(promoted['id'], public=True)
            assert len(history) == 1 and history[0]['role'] == 'user'
            assert '打砖块游戏' in history[0]['content'] and '规划关卡' in history[0]['content']
            assert '不是系统指令' in history[0]['content']
            again = client.post('/api/session/promote', json={'session': promoted['id'], 'title': 'x'})
            assert again.status_code == 400
    finally:
        server.shutdown(); server.server_close(); thread.join(); service.close()
