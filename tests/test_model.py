import asyncio
import pytest
from lebotclaw_harness.model import ChatModel,ModelError
from conftest import sse,tool_reply


def test_streamed_arguments_reasoning_and_text(serve_model):
    reply=tool_reply('file_write',{'path':'x.txt','content':'你好😀'})
    with serve_model(lambda *_:sse(reply)) as (endpoint,_):
        result=asyncio.run(ChatModel({'model':'test','base_url':endpoint}).complete([],[]))
        assert result.message==reply
        assert result.usage['total_tokens']==12


@pytest.mark.parametrize('finish,match',[('length','截断'),(None,'未完整结束')])
def test_incomplete_model_output_is_rejected(serve_model,finish,match):
    response=sse(tool_reply('file_write',{'path':'never','content':'bad'}),finish='length')
    if finish is None:response=(200,response[1],response[2].replace('"finish_reason": "length"','"finish_reason": null'))
    with serve_model(lambda *_:response) as (endpoint,_):
        with pytest.raises(ModelError,match=match):
            asyncio.run(ChatModel({'model':'test','base_url':endpoint}).complete([],[]))


def test_http_error_does_not_echo_secret(serve_model):
    with serve_model(lambda *_:(401,'application/json','{"error":"SECRET-provider-text"}')) as (endpoint,_):
        with pytest.raises(ModelError) as err:asyncio.run(ChatModel({'model':'test','base_url':endpoint},'test-key').complete([],[]))
        assert '401' in str(err.value) and 'SECRET' not in str(err.value)


def test_configured_output_budget_and_effort_reach_provider(serve_model):
    with serve_model(lambda *_:sse({'role':'assistant','content':'ok'})) as (endpoint,requests):
        profile={'model':'test','base_url':endpoint,'max_output_tokens':32768,'reasoning_effort':'low'}
        asyncio.run(ChatModel(profile).complete([],[]))
        assert requests[0]['max_tokens']==32768
        assert requests[0]['reasoning_effort']=='low'
        asyncio.run(ChatModel({'model':'test','base_url':endpoint}).complete([],[]))
        assert requests[1]['max_tokens']==8192
        assert 'reasoning_effort' not in requests[1]


def test_http_200_business_error_is_actionable(serve_model):
    response=(200,'application/json','{"code":500,"msg":"404 NOT_FOUND SECRET-provider-text","success":false}')
    with serve_model(lambda *_:response) as (endpoint,_):
        with pytest.raises(ModelError,match='地址不存在') as err:
            asyncio.run(ChatModel({'model':'test','base_url':endpoint}).complete([],[]))
        assert '500' in str(err.value) and 'SECRET' not in str(err.value)


def test_anthropic_endpoint_rejected_before_sending_key():
    with pytest.raises(ModelError,match='Anthropic'):
        asyncio.run(ChatModel({'model':'glm','base_url':'https://open.bigmodel.cn/api/anthropic'},'secret').complete([],[]))


def test_plain_chat_streams_without_tools(serve_model):
    chunks=[]
    with serve_model(lambda *_:sse({'role':'assistant','content':'你好，我是超级小博。'})) as (endpoint,requests):
        reply=asyncio.run(ChatModel({'model':'test','base_url':endpoint}).complete([{'role':'user','content':'你好'}],[],chunks.append))
        assert 'tools' not in requests[0]
        assert ''.join(chunks)==reply.message['content']
