"""Loopback UI adapter. No separate agent loop or template dispatch lives here."""
import asyncio
import base64
import concurrent.futures
import json
import mimetypes
import secrets
import threading
import subprocess
import sys
import io
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse, quote
from .config import Config, atomic_json
from .runtime import Runtime
from .model import ModelError, validate_chat_endpoint
from .tools import ToolContext, list_files
from .preview import PreviewHost

UI = Path(__file__).parent / 'ui'


class Service:
    def __init__(self, home):
        self.runtime = Runtime(home)
        self.previews = {}
        self.preview_lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)
        self.model_checks = {}
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()

    def future(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def call(self, coro, timeout=10):
        return self.future(coro).result(timeout)

    def context(self, sid, require_read=True):
        session = self.runtime.store.session(sid)
        if require_read and not self.runtime.permissions.get(session['workspace'])['read']:
            raise ValueError('尚未授权读取此项目，请打开“授权执行”选择只读或执行权限。')
        return ToolContext(Path(session['workspace']), self.runtime.home, 'ui', {'mode':'off'})

    def preview_url(self, sid, path):
        ctx=self.context(sid); root=str(ctx.workspace)
        with self.preview_lock:
            if root not in self.previews:
                if len(self.previews)>=20:
                    raise ValueError('同时预览的项目达到 20 个，请重启服务释放旧预览。')
                ports_path=self.runtime.home/'preview-ports.json'
                ports=json.loads(ports_path.read_text()) if ports_path.exists() else {}
                # Retain the origin across restarts so project localStorage survives.
                port=ports.get(root,0)
                if type(port) is not int or (port and not 1024<=port<=65535): port=0
                try: self.previews[root]=PreviewHost(port)
                except OSError:
                    raise ValueError('此项目的预览端口被占用。请释放端口 %s 后重试，以保留作品的本地存储。' % port)
                ports[root]=self.previews[root].server.server_port
                atomic_json(ports_path,ports)
            return self.previews[root].add(ctx,path,lambda:self.runtime.permissions.get(root)['read'])

    def state(self):
        config = Config(self.runtime.home)
        health = {}
        for name, profile in config.data['models'].items():
            try:
                if name == config.data['active_model']:
                    validate_chat_endpoint(profile['base_url'])
                self.runtime.resolve_model(name)
                check = self.model_checks.get(name, {})
                health[name] = {'ready': True, 'connected': check.get('profile') == profile and check.get('connected', False), 'tool_call': check.get('tool_call', False)}
            except (ValueError, ModelError) as exc:
                health[name] = {'ready': False, 'message': str(exc)}
        return {'sessions':self.runtime.store.sessions(), 'models':config.data['models'],
                'model_health': health,
                'active_model':config.data['active_model'], 'execution':config.data['execution'],
                'capabilities':config.data['capabilities'], 'media_options':config.data['media_options'],
                'tools':[{'name':t.name,'description':t.description,'effect':t.effect} for t in self.runtime.registry.tools.values()],
                'home':str(self.runtime.home), 'version':'0.2.1'}

    def close(self):
        self.call(self.runtime.shutdown(), timeout=20)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=3)
        self.loop.close()
        self.runtime.close()
        for preview in self.previews.values(): preview.close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    @property
    def service(self):
        return self.server.service

    def allowed(self):
        origin = 'http://127.0.0.1:' + str(self.server.server_port)
        return (self.headers.get('Host') == origin[7:] and
                self.headers.get('Origin', origin) == origin and
                self.headers.get('Sec-Fetch-Site', 'none') != 'cross-site')

    def reply(self, value, status=200, mime='application/json; charset=utf-8', filename=None):
        body=json.dumps(value,ensure_ascii=False).encode() if isinstance(value,(dict,list)) else value
        self.send_response(status)
        self.send_header('Content-Type',mime); self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        if filename: self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(filename))
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob: data:; connect-src 'self'; frame-src http://127.0.0.1:*; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass

    def do_GET(self):
        if not self.allowed(): return self.reply({'error':'来源无效'},403)
        u=urlparse(self.path); q=parse_qs(u.query)
        if u.path=='/api/bootstrap': return self.reply({'token':self.service.token,**self.service.state()})
        if u.path.startswith('/api/') and self.headers.get('X-Lebot-Token')!=self.service.token:
            return self.reply({'error':'请刷新页面'},403)
        try:
            if u.path=='/api/state': return self.reply(self.service.state())
            if u.path=='/api/folders':
                folder=Path(q.get('path',[''])[0] or Path.home()/'Documents').expanduser().resolve()
                if not folder.is_dir(): raise ValueError('文件夹不存在。')
                children=[]
                for child in sorted(folder.iterdir(), key=lambda p:p.name.lower()):
                    if not child.name.startswith('.') and not child.is_symlink() and child.is_dir():
                        children.append({'name':child.name,'path':str(child)})
                    if len(children)>=200: break
                return self.reply({'path':str(folder),'parent':str(folder.parent) if folder!=folder.parent else None,'folders':children})
            if u.path=='/api/session':
                sid=q['id'][0];store=self.service.runtime.store
                session=store.session(sid)
                grant=self.service.runtime.permissions.get(session['workspace'])
                files=list_files({'recursive':True},self.service.context(sid))['entries'] if grant['read'] else []
                approvals=self.service.call(self.service.runtime.approvals(sid))
                rid = (session.get('last_run') or {}).get('id')
                return self.reply({'session':session,'permission':grant,'approvals':approvals,'messages':store.history(sid,public=True),'events':store.events(sid,int(q.get('after',['0'])[0])), 'live':dict(self.service.runtime.progress.get(rid, {})), 'files':[f['path'] for f in files if f['kind']=='file']})
            if u.path=='/api/preview':
                url=self.service.preview_url(q['session'][0],q['path'][0])
                return self.reply({'url':url})
            if u.path=='/api/project.zip':
                ctx=self.service.context(q['session'][0]);output=io.BytesIO();total=0
                entries=list_files({'recursive':True},ctx)['entries']
                if len(entries)>=500: raise ValueError('项目文件过多，请在本机文件管理器中复制完整文件夹。')
                with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
                    for item in entries:
                        if item['kind']!='file': continue
                        source=ctx.path(item['path']);total+=source.stat().st_size
                        if total>50_000_000: raise ValueError('项目超过 50 MB，请在本机文件管理器中复制项目文件夹。')
                        archive.writestr(item['path'],source.read_bytes())
                title=self.service.runtime.store.session(q['session'][0])['title']
                return self.reply(output.getvalue(),mime='application/zip',filename=title+'.zip')
            if u.path=='/api/artifact':
                path=self.service.context(q['session'][0]).path(q['path'][0])
                if not path.is_file() or path.stat().st_size>20_000_000: raise ValueError('文件不存在或超过 20 MB。')
                return self.reply(path.read_bytes(),mime='application/octet-stream',filename=path.name)
            if u.path=='/api/file':
                path=self.service.context(q['session'][0]).path(q['path'][0])
                if not path.is_file(): raise ValueError('只支持常规文件。')
                if path.stat().st_size>500000: raise ValueError('预览文件过大。')
                return self.reply({'content':path.read_text(encoding='utf-8')})
            if u.path=='/api/appdata':
                sid=q['session'][0];self.service.runtime.store.session(sid)
                path=self.service.runtime.home/'appdata'/(sid+'.json')
                return self.reply({'data':json.loads(path.read_text()) if path.exists() else {}})
            if u.path.startswith('/api/'): return self.reply({'error':'接口不存在'},404)
            path=UI/('index.html' if u.path=='/' else u.path.lstrip('/'))
            if not path.resolve().is_relative_to(UI.resolve()) or not path.is_file():
                return self.reply(b'Not found',404,'text/plain')
            return self.reply(path.read_bytes(),mime=mimetypes.guess_type(str(path))[0] or 'application/octet-stream')
        except (ValueError,KeyError,FileNotFoundError,UnicodeError) as exc:
            return self.reply({'error':str(exc)[:300]},400)
        except Exception:
            return self.reply({'error':'请求未完成'},500)

    def do_POST(self):
        if not self.allowed() or self.headers.get('X-Lebot-Token')!=self.service.token:
            return self.reply({'error':'来源或会话凭据无效'},403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=8_000_000: raise ValueError('请求长度超出限制。')
            data=json.loads(self.rfile.read(size))
            if not isinstance(data,dict): raise ValueError('请求需要 JSON 对象。')
            result=self.post(urlparse(self.path).path,data)
            return self.reply(result)
        except (ValueError,KeyError,TypeError,ModelError) as exc:
            return self.reply({'error':str(exc)[:400]},400)
        except concurrent.futures.TimeoutError:
            return self.reply({'error':'请求仍在处理中，请刷新任务状态。'},504)
        except Exception:
            return self.reply({'error':'操作未完成'},500)

    def post(self, path, body):
        runtime=self.service.runtime
        if path=='/api/session':
            return runtime.store.create(str(body.get('title','新任务')),body.get('workspace') or None)
        if path=='/api/workspace/open':
            root=runtime.store.session(body['session'])['workspace']
            if sys.platform=='darwin': subprocess.Popen(['open',root])
            elif sys.platform=='win32':
                import os
                os.startfile(root)
            else: subprocess.Popen(['xdg-open',root])
            return {'opened':True}
        if path=='/api/run':
            root=runtime.store.session(body['session'])['workspace'];grant=runtime.permissions.get(root)
            rid=self.service.call(runtime.start(body['session'],body['text'],model=body.get('model'),attachments=body.get('attachments'),
                max_steps=grant['max_steps'],max_seconds=grant['max_seconds'],max_tokens=grant['max_tokens']))
            return {'run_id':rid}
        if path=='/api/permission':
            return self.service.call(runtime.grant(body['session'],body['permission']),timeout=20)
        if path=='/api/approval':
            return self.service.call(runtime.approve(body['id'],body['approved']))
        if path=='/api/model/test':
            async def check():
                name,profile,adapter=runtime.resolve_model(body.get('name'))
                # Plain chat and tools are separate provider paths; verify both.
                await adapter.complete([{'role':'user','content':'连接检查，请只回复：连接成功。'}],[])
                probe={'type':'function','function':{'name':'connection_probe','description':'确认工具协议可用，不操作文件。','parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}}}
                reply=await adapter.complete([{'role':'user','content':'这是接口能力检查。请调用 connection_probe，不需要其他操作。'}],[probe])
                result = {'connected':True,'tool_call':any(c['function']['name']=='connection_probe' for c in reply.message.get('tool_calls',[])), 'usage':reply.usage}
                self.service.model_checks[name] = {'profile':profile, **result}
                return result
            return self.service.call(check(),timeout=180)
        if path=='/api/audio/transcribe':
            raw=base64.b64decode(body['audio'],validate=True)
            return self.service.call(runtime.media.transcribe(raw,body['mime']),timeout=200)
        if path=='/api/audio/speech':
            return self.service.call(runtime.media.speech(body['text']),timeout=200)
        if path=='/api/cancel':
            # Return promptly; the durable status settles after process cleanup.
            row=runtime.store.run(body['run'])
            if not row: raise ValueError('运行不存在。')
            self.service.future(runtime.cancel(body['run']))
            return {'requested':True}
        if path=='/api/model':
            config=Config(runtime.home)
            slot=body.get('slot','chat')
            if slot not in ('chat','image','asr','tts'): raise ValueError('模型用途无效。')
            options=body.get('options',{})
            if not isinstance(options,dict) or any(k not in ('size','quality','voice','response_format','protocol') or not isinstance(v,str) or len(v)>100 for k,v in options.items()):
                raise ValueError('多模态选项无效。')
            if options.get('protocol','openai') not in ('openai','dashscope'): raise ValueError('未知生图协议。')
            key=body.get('key','')
            if key and (not isinstance(key,str) or len(key)>4096 or any(ord(c)<33 or ord(c)>126 for c in key)):
                raise ValueError('密钥格式错误。')
            previous=config.data['models'].get(body['name'])
            profile=config.add_model(body['name'],body['provider'],body['model'],body.get('base_url') or None,body.get('key_env') or None,body.get('vision',False),
                             body.get('max_output_tokens'),body.get('reasoning_effort'),persist=False)
            if slot == 'chat': validate_chat_endpoint(profile['base_url'])
            if slot!='chat' and config.data['active_model']==body['name'] and previous and any(profile[k]!=previous[k] for k in ('model','provider','base_url')):
                raise ValueError('这个名称正在用于主模型。为新的生图或语音模型换一个配置名称，以保留主模型连接。')
            if body.get('save_key'):
                if not key: raise ValueError('安全保存需要输入本次 API Key。')
                from .credentials import save
                save(runtime.home,body['name'],config.data['models'][body['name']],key)
                config.data['models'][body['name']]['secure_key']=True
            if slot=='chat': config.data['active_model']=body['name']
            else:
                config.data['capabilities'][slot]=body['name']
                config.data['media_options'][slot]=options
            config.save()
            if key: runtime.set_key(body['name'],key)
            self.service.model_checks.pop(body['name'], None)
            return {'saved':True,'key_storage':'system_keyring' if body.get('save_key') else 'memory_only'}
        if path=='/api/capability/disable':
            config=Config(runtime.home)
            if body['slot'] not in ('image','asr','tts'): raise ValueError('请选择可选能力。')
            config.data['capabilities'].pop(body['slot'],None);config.save()
            return {'saved':True}
        if path=='/api/appdata':
            sid=body['session'];runtime.store.session(sid)
            if len(json.dumps(body['data']))>100000: raise ValueError('应用数据过大。')
            atomic_json(runtime.home/'appdata'/(sid+'.json'),body['data'])
            return {'saved':True}
        raise ValueError('接口不存在。')


def serve(home, port=18866, open_browser=False):
    service=Service(home)
    server=None
    try:
        server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
        server.daemon_threads=True
        server.service=service
        print('LebotClaw Harness · http://127.0.0.1:%s' % server.server_port,flush=True)
        print('运行数据：'+str(service.runtime.home),flush=True)
        if open_browser:
            import webbrowser
            webbrowser.open('http://127.0.0.1:%s' % server.server_port)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if server: server.server_close()
        service.close()
