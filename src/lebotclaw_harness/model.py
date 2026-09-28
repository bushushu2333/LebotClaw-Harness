"""Provider boundary; preserve tool-call and reasoning protocol fields."""
import asyncio
import json
import re
import urllib.request
import httpx
from dataclasses import dataclass
from typing import Callable, Optional


class ModelError(Exception):
    pass


def proxy_hint():
    """本应用默认直连（trust_env=False）；系统代理/VPN 的增强模式仍可能拦截流量，故障时给出提示。"""
    try:
        proxies = urllib.request.getproxies()
    except Exception:
        return ''
    if any(proxies.get(k) for k in ('http', 'https', 'all')):
        return '；检测到本机开启了系统代理，本应用默认直连不经过代理——若目标服务必须经代理访问，请在代理工具中为其配置规则；若连接的是本地服务（如 Ollama），代理的增强模式可能拦截请求，请尝试关闭'
    return ''


def validate_chat_endpoint(url):
    path = httpx.URL(url).path.rstrip('/')
    if '/anthropic' in path or path.endswith('/messages'):
        raise ModelError('这是 Claude / Anthropic 协议地址，当前配置使用 OpenAI 兼容协议。GLM 请使用 https://open.bigmodel.cn/api/paas/v4；中转站请填写其 OpenAI 兼容基础地址。')
    if path.endswith('/chat/completions'):
        raise ModelError('请填写 API 基础地址，去掉末尾的 /chat/completions。')


def provider_error(data):
    if not isinstance(data, dict):
        raise ModelError('接口未返回有效的 JSON 对象，请检查 API 基础地址。')
    error = data.get('error')
    if error or data.get('success') is False or ('code' in data and not data.get('choices') and data['code'] not in (0, 200, '0', '200')):
        details = error if isinstance(error, dict) else data
        code = re.sub(r'[^a-zA-Z0-9_.-]', '', str(details.get('code', 'unknown')))[:40]
        message = str(details.get('message', details.get('msg', ''))).lower()
        if '404' in message or 'not_found' in message:
            hint = '接口地址不存在，请检查基础地址及协议。'
        elif any(s in message for s in ('balance', 'credit', '余额', '额度')):
            hint = '额度不足，请在模型服务商检查余额或 Key 额度。'
        elif any(s in message for s in ('api key', 'api_key', 'token', 'unauthorized', 'authentication', '密钥')):
            hint = '密钥不可用，请检查 Key 及其对应的服务地址。'
        else:
            hint = '服务商拒绝请求，请检查模型、地址、Key 和额度。'
        raise ModelError('模型服务返回错误（代码 %s）。%s' % (code, hint))


@dataclass
class ModelReply:
    message: dict
    usage: dict
    finish_reason: str


class ChatModel:
    def __init__(self, profile, key=""):
        self.profile = dict(profile)
        self.key = key

    async def complete(self, messages, tools, on_text: Optional[Callable] = None):
        validate_chat_endpoint(self.profile['base_url'])
        body = {'model': self.profile['model'], 'messages': messages, 'stream': True,
                'max_tokens': self.profile.get('max_output_tokens', 8192)}
        if self.profile.get('reasoning_effort'):
            body['reasoning_effort'] = self.profile['reasoning_effort']
        if tools:
            body['tools'] = tools
        headers = {'Content-Type': 'application/json'}
        if self.key:
            headers['Authorization'] = 'Bearer ' + self.key
        message = {'role': 'assistant', 'content': ''}
        calls = {}
        usage = {}
        finish = None
        size = 0
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=15), follow_redirects=False, trust_env=False) as client:
                async with client.stream('POST', self.profile['base_url'] + '/chat/completions', headers=headers, json=body) as response:
                    if response.status_code >= 300:
                        raise ModelError('模型接口返回 HTTP %s；请检查配置、额度和能力支持%s。' % (response.status_code, proxy_hint()))
                    if 'text/event-stream' not in response.headers.get('content-type', ''):
                        raw = bytearray()
                        async for chunk in response.aiter_bytes():
                            raw.extend(chunk)
                            if len(raw) > 8_000_000:
                                raise ModelError('模型响应过大。')
                        data = json.loads(raw)
                        provider_error(data)
                        if not data.get('choices'):
                            raise ModelError('接口返回了 JSON，但没有模型回答。请确认地址支持 OpenAI Chat Completions 协议。')
                        choice = data['choices'][0]
                        return self.validate(choice['message'], data.get('usage') or {}, choice.get('finish_reason'))
                    async for line in response.aiter_lines():
                        size += len(line)
                        if size > 8_000_000:
                            raise ModelError('模型响应超出本次限制。')
                        if not line.startswith('data:'):
                            continue
                        raw = line[5:].strip()
                        if raw == '[DONE]':
                            break
                        if not raw:
                            continue
                        data = json.loads(raw)
                        provider_error(data)
                        if data.get('usage'):
                            usage = data['usage']
                        if not data.get('choices'):
                            continue
                        choice = data['choices'][0]
                        delta = choice.get('delta') or {}
                        for key in ('content', 'reasoning_content'):
                            if delta.get(key):
                                message[key] = message.get(key, '') + delta[key]
                                if key == 'content' and on_text:
                                    on_text(delta[key])
                        for part in delta.get('tool_calls') or []:
                            index = part.get('index', 0)
                            c = calls.setdefault(index, {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                            if part.get('id'):
                                c['id'] = part['id']
                            for key in ('name', 'arguments'):
                                value = (part.get('function') or {}).get(key)
                                if value:
                                    c['function'][key] += value
                        if choice.get('finish_reason'):
                            finish = choice['finish_reason']
            if calls:
                message['tool_calls'] = [calls[k] for k in sorted(calls)]
            return self.validate(message, usage, finish)
        except asyncio.CancelledError:
            raise
        except ModelError:
            raise
        except (httpx.TimeoutException, httpx.NetworkError):
            raise ModelError('模型网络连接失败或超时；本次没有执行不完整的工具请求%s。' % proxy_hint())
        except Exception:
            # Do not echo transport exceptions or raw provider responses (possible secrets).
            raise ModelError('无法解析模型响应；请检查接口协议和模型能力。')

    @staticmethod
    def validate(message, usage, finish):
        if finish == 'length':
            raise ModelError('模型输出达到单次最大 token 上限被截断，未执行其中的工具。请在模型设置的「图片理解与高级设置」中调大“单次最大输出 token”，或将任务拆小后重试。')
        if finish not in ('stop', 'tool_calls', 'function_call'):
            raise ModelError('模型输出未完整结束，未执行其中的工具。结束原因：' + str(finish))
        filtered = {k: v for k, v in message.items() if k in ('role', 'content', 'tool_calls', 'reasoning_content')}
        filtered['role'] = 'assistant'
        calls = filtered.get('tool_calls') or []
        if len(calls) > 16 or len({c.get('id') for c in calls}) != len(calls):
            raise ModelError('模型工具调用数量或 ID 无效。')
        for c in calls:
            if not c.get('id') or c.get('type') != 'function' or not isinstance(c.get('function', {}).get('arguments'), str) or not isinstance(c.get('function', {}).get('name'), str):
                raise ModelError('模型工具调用格式不完整。')
        if not calls and not filtered.get('content'):
            raise ModelError('模型没有返回正文或工具请求。')
        return ModelReply(filtered, usage, finish)
