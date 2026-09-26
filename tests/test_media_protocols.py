import asyncio
import base64
import io
import json
from pathlib import Path
import httpx
import pytest
from lebotclaw_harness.media import MediaServices,dashscope_images
from lebotclaw_harness.runtime import Runtime
from lebotclaw_harness.config import Config
from test_runtime import configured


def test_wan_sse_stops_on_usage_without_eof(monkeypatch):
    requests=[]
    class Events(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"code":200,"output":{"choices":[{"message":{"content":[{"type":"text","text":"working"}]}}]}}\n\n'
            yield b'data: {"output":{"choices":[{"message":{"content":[{"image":"https://example.com/1.png"},{"image":"https://example.com/2.png"}]},"finish_reason":"stop"}]},"usage":{"image_count":2}}\n\n'
            raise AssertionError('must not wait for EOF after complete image result')
    def respond(request):
        requests.append(request)
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Events())
    original=httpx.AsyncClient
    monkeypatch.setattr('lebotclaw_harness.media.httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
    result=asyncio.run(dashscope_images('https://provider.example/v1/images/generations',{'Authorization':'Bearer TEST'},'wan2.6-image','测试',{}))
    assert len(result['data'])==2 and result['usage']['image_count']==2
    assert requests[0].headers['x-dashscope-sse']=='enable'
    body=json.loads(requests[0].content);assert body['parameters']['enable_interleave'] is True
    assert body['input']['messages'][0]['content'][0]['text']=='测试'


def test_audio_protocols_and_secret_not_in_payload(tmp_path,monkeypatch):
    rt=Runtime(configured(tmp_path));c=Config(rt.home)
    c.add_model('voice','openai-compatible','voice-model','https://voice.example/v1')
    c.data['capabilities'].update(asr='voice',tts='voice');c.save();rt.set_key('voice','TEST-AUDIO-KEY')
    requests=[]
    def respond(request):
        requests.append(request)
        assert request.headers['authorization']=='Bearer TEST-AUDIO-KEY'
        assert b'TEST-AUDIO-KEY' not in request.content
        if request.url.path.endswith('transcriptions'):
            assert b'voice-model' in request.content and b'audio/webm' in request.content
            return httpx.Response(200,json={'text':'帮我做一个课程表'})
        body=json.loads(request.content);assert body['input']=='你好' and body['response_format']=='mp3'
        return httpx.Response(200,content=b'ID3test-protocol-audio')
    original=httpx.AsyncClient
    monkeypatch.setattr('lebotclaw_harness.media.httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(respond),**kwargs))
    async def scenario():
        assert (await rt.media.transcribe(b'test-audio','audio/webm'))['text']=='帮我做一个课程表'
        result=await rt.media.speech('你好');assert base64.b64decode(result['audio']).startswith(b'ID3')
        with pytest.raises(ValueError):await rt.media.speech('x'*4001)
    try:asyncio.run(scenario())
    finally:rt.close()
    assert len(requests)==2


def test_system_credential_identity_is_bound_to_destination(tmp_path,monkeypatch):
    from lebotclaw_harness import credentials
    values={}
    class Keys:
        def set_password(self,service,user,key):values[(service,user)]=key
        def get_password(self,service,user):return values.get((service,user))
    monkeypatch.setattr(credentials,'backend',lambda:Keys())
    p={'provider':'glm','base_url':'https://good.example/v1'}
    credentials.save(tmp_path,'my-model',p,'TEST-KEY')
    assert credentials.read(tmp_path,'my-model',p)=='TEST-KEY'
    assert credentials.read(tmp_path,'my-model',{**p,'base_url':'https://different.example/v1'})==''
    assert credentials.read(tmp_path/'different','my-model',p)==''
