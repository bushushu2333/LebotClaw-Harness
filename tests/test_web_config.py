import json
import threading
from http.server import ThreadingHTTPServer
import httpx
import pytest
from lebotclaw_harness.config import Config
from lebotclaw_harness.web import Service,Handler


def test_config_endpoints_and_no_stored_key(tmp_path):
    c=Config(tmp_path)
    for url in ['http://example.org','https://user:password@example.org','https://example.org/?key=x']:
        with pytest.raises(ValueError):c.add_model('a','deepseek','model',url)
    c.add_model('deepseek','deepseek','provider-model',key_env='DEEPSEEK_API_KEY')
    assert c.model()[1]['base_url']=='https://api.deepseek.com/v1'
    assert 'key' not in c.model()[1]
    assert (tmp_path/'config.json').stat().st_mode & 0o077==0


def test_model_budgets_validate_and_survive_basic_settings_save(tmp_path):
    c=Config(tmp_path)
    for value in (True, '32768', 0, 131073):
        with pytest.raises(ValueError):c.add_model('glm','glm','glm-5.3',max_output_tokens=value)
    with pytest.raises(ValueError):c.add_model('glm','glm','glm-5.3',reasoning_effort='invalid')
    c.add_model('glm','glm','glm-5.3',max_output_tokens=32768,reasoning_effort='low')
    c.add_model('glm','glm','glm-5.3')
    assert c.model()[1]['max_output_tokens']==32768
    assert c.model()[1]['reasoning_effort']=='low'


def test_web_api_auth_workspace_and_memory_key(tmp_path):
    service=Service(tmp_path/'state');server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.service=service
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with httpx.Client(base_url='http://127.0.0.1:'+str(server.server_port),trust_env=False) as client:
            assert client.get('/').status_code==200
            assert client.get('/api/state').status_code==403
            assert client.get('/api/bootstrap',headers={'Origin':'https://evil.example'}).status_code==403
            assert client.get('/api/bootstrap',headers={'Host':'evil.example'}).status_code==403
            boot=client.get('/api/bootstrap').json();client.headers['X-Lebot-Token']=boot['token']
            response=client.post('/api/model',json={'name':'local','provider':'openai-compatible','model':'fixture','base_url':'http://127.0.0.1:1/v1','key':'TEST-MEMORY-KEY'})
            assert response.status_code==200
            assert 'TEST-MEMORY-KEY' not in (tmp_path/'state'/'config.json').read_text()
            assert service.runtime.credentials['local']=='TEST-MEMORY-KEY'
            config=Config(service.runtime.home)
            config.add_model('local','openai-compatible','fixture','http://127.0.0.1:2/v1')
            assert service.runtime.resolve_model('local')[2].key==''
            s=client.post('/api/session',json={'title':'API project'}).json();sid=s['id']
            file=__import__('pathlib').Path(s['workspace'])/'result.txt';file.write_text('real-file')
            assert client.get('/api/file',params={'session':sid,'path':'result.txt'}).status_code==400
            assert client.get('/api/session',params={'id':sid}).json()['files']==[]
            assert client.post('/api/permission',json={'session':sid,'permission':{'mode':'plan','read':True}}).status_code==200
            assert client.get('/api/file',params={'session':sid,'path':'result.txt'}).json()['content']=='real-file'
            import io,zipfile
            packed=client.get('/api/project.zip',params={'session':sid})
            with zipfile.ZipFile(io.BytesIO(packed.content)) as archive:
                assert archive.namelist()==['result.txt']
                assert archive.read('result.txt')==b'real-file'
            assert client.get('/api/file',params={'session':sid,'path':'../config.json'}).status_code==400
            assert client.post('/api/appdata',json={'session':sid,'data':{'saved':1}}).status_code==200
            assert client.get('/api/appdata',params={'session':sid}).json()['data']=={'saved':1}
            assert client.get('/api/session',params={'id':sid}).json()['files']==['result.txt']
    finally:server.shutdown();server.server_close();thread.join();service.close()


def test_model_slot_update_is_atomic_and_does_not_replace_chat(tmp_path):
    service=Service(tmp_path/'state')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.service=service
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with httpx.Client(base_url='http://127.0.0.1:'+str(server.server_port),trust_env=False) as c:
            c.headers['X-Lebot-Token']=c.get('/api/bootstrap').json()['token']
            base={'name':'shared','provider':'openai-compatible','model':'chat-model','base_url':'http://127.0.0.1:1/v1'}
            assert c.post('/api/model',json=base).status_code==200
            before=(service.runtime.home/'config.json').read_bytes()
            assert c.post('/api/model',json={**base,'slot':'image','model':'image-model'}).status_code==400
            assert (service.runtime.home/'config.json').read_bytes()==before
            assert c.post('/api/model',json={**base,'name':'images','slot':'image','model':'image-model'}).status_code==200
            state=c.get('/api/state').json()
            assert state['active_model']=='shared' and state['capabilities']['image']=='images'
    finally:server.shutdown();server.server_close();thread.join();service.close()


def test_preview_origin_is_per_project_and_survives_service_restart(tmp_path):
    from pathlib import Path
    service=Service(tmp_path/'state');home=service.runtime.home
    try:
        a=service.runtime.store.create('a');b=service.runtime.store.create('b')
        for s in (a,b):
            (Path(s['workspace'])/'index.html').write_text('<h1>hello</h1>')
            service.call(service.runtime.grant(s['id'],{'mode':'plan','read':True,'remember':True}))
        url_a=service.preview_url(a['id'],'index.html');url_b=service.preview_url(b['id'],'index.html')
        assert httpx.URL(url_a).port!=httpx.URL(url_b).port
    finally:service.close()
    service=Service(home)
    try:
        restored=service.preview_url(a['id'],'index.html')
        assert httpx.URL(restored).port==httpx.URL(url_a).port
        assert restored!=url_a  # Capability rotates even though localStorage origin persists.
        with httpx.Client(trust_env=False) as client:
            assert client.get(restored).status_code==200
            assert client.get(url_a).status_code==404
        service.call(service.runtime.grant(a['id'],{'mode':'plan'}))
        with httpx.Client(trust_env=False) as client:assert client.get(restored).status_code==403
    finally:service.close()


def test_model_readiness_and_protocol_error_do_not_overwrite_config(tmp_path):
    service=Service(tmp_path/'state')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);server.service=service
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with httpx.Client(base_url='http://127.0.0.1:'+str(server.server_port),trust_env=False) as c:
            boot=c.get('/api/bootstrap').json();c.headers['X-Lebot-Token']=boot['token']
            assert boot['active_model'] is None and boot['model_health']=={}
            body={'name':'glm','provider':'glm','model':'glm-5.3'}
            assert c.post('/api/model',json={**body,'key':'test-key'}).status_code==200
            assert c.get('/api/state').json()['model_health']['glm']['ready']
            before=(service.runtime.home/'config.json').read_bytes()
            bad=c.post('/api/model',json={**body,'base_url':'https://open.bigmodel.cn/api/anthropic'})
            assert bad.status_code==400 and 'Anthropic' in bad.json()['error']
            assert (service.runtime.home/'config.json').read_bytes()==before
            service.runtime.credentials.clear()
            health=c.get('/api/state').json()['model_health']['glm']
            assert not health['ready'] and '密钥' in health['message']
            root=tmp_path/'browse';root.mkdir();(root/'child').mkdir();(root/'private.txt').write_text('private')
            listed=c.get('/api/folders',params={'path':str(root)}).json()
            assert [f['name'] for f in listed['folders']]==['child']
    finally:server.shutdown();server.server_close();thread.join();service.close()
