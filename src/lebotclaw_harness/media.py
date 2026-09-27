"""Optional OpenAI-compatible image, speech and transcription services."""
import base64
import binascii
import io
import ipaddress
import json
import socket
from urllib.parse import urlparse
import httpx
from .artifacts import save_artifact
from .model import proxy_hint


async def bounded_request(method, url, headers=None, **kwargs):
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=15), follow_redirects=False, trust_env=False) as client:
            async with client.stream(method, url, headers=headers or {}, **kwargs) as response:
                if response.status_code >= 300:
                    raise ValueError('服务返回 HTTP %s，请检查模型、协议及额度%s；未自动重试。' % (response.status_code, proxy_hint()))
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 28_000_000:
                        raise ValueError('服务返回的内容超过 28 MB。')
                return bytes(raw)
    except httpx.HTTPError:
        raise ValueError('服务连接失败或超时%s。上游请求可能已产生用量；请核对后再生成，系统未自动重试。' % proxy_hint())


async def download_image(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('图片下载地址需要为公开 HTTPS 地址。')
    import asyncio
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise ValueError('不接受指向本机或内网的素材地址。')
    except OSError:
        raise ValueError('无法解析素材下载地址。')
    # No API credentials are forwarded to an asset host, and redirects are refused.
    return await bounded_request('GET', url)


async def dashscope_images(url, headers, model, prompt, options):
    """Wan's interleaved SSE protocol; stop when the server has finished images."""
    body = {'model':model, 'input':{'messages':[{'role':'user','content':[{'type':'text','text':prompt}]}]},
            'parameters':{'enable_interleave':True, 'stream':True}, 'size':options.get('size') or '1024x1024'}
    urls, usage, length = [], {}, 0
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(240,connect=15),follow_redirects=False,trust_env=False) as client:
            async with client.stream('POST',url,headers={**headers,'x-dashscope-sse':'enable'},json=body) as response:
                if response.status_code >= 300:
                    raise ValueError('生图服务返回 HTTP %s%s；未自动重试。' % (response.status_code, proxy_hint()))
                async for line in response.aiter_lines():
                    length += len(line)
                    if length > 2_000_000: raise ValueError('生图事件流过大。')
                    if not line.startswith('data:'): continue
                    raw = line[5:].strip()
                    if raw == '[DONE]': break
                    if not raw: continue
                    data = json.loads(raw)
                    if data.get('code') not in (None,0,'0',200,'200') or data.get('error'):
                        import re
                        code = re.sub(r'[^A-Za-z0-9_.-]','',str(data.get('code') or 'upstream_error'))[:100]
                        message = str(data.get('message') or data.get('error') or '')
                        key = headers.get('Authorization','').removeprefix('Bearer ')
                        if key: message=message.replace(key,'[redacted]')
                        message = re.sub(r'https?://\S+', '[url]', message)
                        raise ValueError('生图服务错误 %s：%s；未自动重试。' % (code,message[:240]))
                    usage = data.get('usage') or usage
                    finished = False
                    for choice in data.get('output',{}).get('choices',[]):
                        for content in choice.get('message',{}).get('content',[]):
                            if isinstance(content,dict) and content.get('image') and content['image'] not in urls:
                                urls.append(content['image'])
                        finished |= choice.get('finish_reason') == 'stop'
                    if len(urls) > 4: raise ValueError('服务生成超过 4 张图片，请核对上游用量。')
                    if urls and (finished or usage.get('image_count') == len(urls)):
                        return {'data':[{'url':u} for u in urls], 'usage':usage}
    except httpx.HTTPError:
        raise ValueError('生图连接中断或超时；上游可能已计费，请核对后再生成。')
    except (json.JSONDecodeError, TypeError):
        raise ValueError('无法解析生图事件流。')
    if urls: return {'data':[{'url':u} for u in urls], 'usage':usage}
    raise ValueError('生图服务没有返回图片。')


class MediaServices:
    def __init__(self, runtime):
        self.runtime = runtime

    def resolve(self, kind):
        from .config import Config
        config = Config(self.runtime.home)
        name = config.data.get('capabilities', {}).get(kind)
        if not name:
            raise ValueError('尚未配置%s服务，请在模型设置中单独配置。' % {'image':'生图','asr':'语音识别','tts':'语音播报'}[kind])
        name, profile, adapter = self.runtime.resolve_model(name)
        headers = {'Authorization': 'Bearer ' + adapter.key} if adapter.key else {}
        options = config.data.get('media_options', {}).get(kind, {})
        return name, profile, headers, options

    async def image(self, args, ctx):
        from PIL import Image
        path = ctx.path(args['path'])
        if path.exists():
            raise ValueError('生图请使用新文件名，以免付费后覆盖已有素材。')
        if path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp'):
            raise ValueError('图片路径请使用 .png、.jpg 或 .webp。')
        name, profile, headers, options = self.resolve('image')
        body = {'model': profile['model'], 'prompt': args['prompt'], 'n': 1}
        for field in ('size', 'quality', 'response_format'):
            if options.get(field): body[field] = options[field]
        if options.get('protocol') == 'dashscope':
            data = await dashscope_images(profile['base_url'] + '/images/generations',headers,profile['model'],args['prompt'],options)
        else:
            raw = await bounded_request('POST', profile['base_url'] + '/images/generations', headers, json=body)
            try: data = json.loads(raw)
            except json.JSONDecodeError: raise ValueError('生图接口返回的不是 JSON，请检查所选协议。')
        try:
            item = data['data'][0]
            image = base64.b64decode(item['b64_json'], validate=True) if item.get('b64_json') else await download_image(item['url'])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError, binascii.Error):
            raise ValueError('生图服务未返回兼容的 data[0].b64_json 或 url；异步任务协议需要对应适配器。')
        if len(image) > 20_000_000:
            raise ValueError('图片超过 20 MB。')
        try:
            with Image.open(io.BytesIO(image)) as im:
                if im.width * im.height > 24_000_000:
                    raise ValueError('图片像素过大。')
                im.load()
                output = io.BytesIO()
                fmt = {'.png':'PNG', '.jpg':'JPEG', '.jpeg':'JPEG', '.webp':'WEBP'}[path.suffix.lower()]
                if fmt == 'JPEG': im = im.convert('RGB')
                im.save(output, format=fmt)
                dimensions = [im.width, im.height]
        except (OSError, Image.DecompressionBombError):
            raise ValueError('服务返回的内容不是有效图片。')
        result = save_artifact(ctx, args['path'], output.getvalue())
        extra_assets = []
        for index, item in enumerate(data.get('data',[])[1:4], 2):
            extra = base64.b64decode(item['b64_json'],validate=True) if item.get('b64_json') else await download_image(item['url'])
            with Image.open(io.BytesIO(extra)) as im:
                if im.width * im.height > 24_000_000: raise ValueError('附加图片像素过大。')
                out = io.BytesIO(); im.convert('RGB').save(out,format='PNG')
            relative = str(__import__('pathlib').Path(args['path']).with_name(path.stem + '-' + str(index) + '.png'))
            extra_assets.append(save_artifact(ctx,relative,out.getvalue())['path'])
        return {**result, 'additional_assets':extra_assets, 'image_count':1+len(extra_assets), 'dimensions': dimensions, 'service': name, 'model': profile['model'],
                'generation': 'provider_api', 'usage': data.get('usage'), 'billing': 'provider_authoritative'}

    async def transcribe(self, audio, mime):
        if len(audio) > 4_000_000 or mime not in ('audio/webm', 'audio/mp4', 'audio/wav', 'audio/mpeg', 'audio/ogg'):
            raise ValueError('语音格式不支持或超过 4 MB。')
        _, profile, headers, _ = self.resolve('asr')
        extension = {'audio/webm':'webm', 'audio/mp4':'m4a', 'audio/wav':'wav', 'audio/mpeg':'mp3', 'audio/ogg':'ogg'}[mime]
        raw = await bounded_request('POST', profile['base_url'] + '/audio/transcriptions', headers,
                                    data={'model':profile['model']}, files={'file':('recording.' + extension, audio, mime)})
        try:
            text = json.loads(raw)['text']
            if not isinstance(text, str) or len(text) > 20000: raise ValueError()
            return {'text': text}
        except (KeyError, ValueError):
            raise ValueError('无法解析语音识别结果。')

    async def speech(self, text):
        if not isinstance(text, str) or not 1 <= len(text) <= 4000:
            raise ValueError('单次播报支持 1–4000 字。')
        _, profile, headers, options = self.resolve('tts')
        raw = await bounded_request('POST', profile['base_url'] + '/audio/speech', headers,
            json={'model':profile['model'], 'input':text, 'voice':options.get('voice') or 'alloy', 'response_format':'mp3'})
        if not (raw.startswith(b'ID3') or raw[:1] == b'\xff'):
            raise ValueError('语音服务未返回 MP3 音频。')
        return {'audio':base64.b64encode(raw).decode(), 'mime':'audio/mpeg'}


async def image_generate(args, ctx):
    if not ctx.media:
        raise ValueError('生图服务尚未接入当前运行环境。')
    return await ctx.media.image(args, ctx)
