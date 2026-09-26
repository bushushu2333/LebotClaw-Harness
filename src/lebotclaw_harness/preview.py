"""Generated pages run on a different origin, never on the privileged API origin."""
import mimetypes
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlparse


class PreviewHost:
    def __init__(self, port=0):
        self.entries = {}
        self.lock = threading.Lock()
        host = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def do_GET(self):
                if self.headers.get('Host') != '127.0.0.1:' + str(self.server.server_port):
                    self.send_error(403); return
                parts = unquote(urlparse(self.path).path).split('/', 2)
                with host.lock:
                    entry = host.entries.get(parts[1]) if len(parts) == 3 else None
                if not entry:
                    self.send_error(404); return
                ctx, allowed = entry
                try:
                    if not allowed():
                        self.send_error(403); return
                    file = ctx.path(parts[2])
                    if not file.is_file() or file.stat().st_size > 20_000_000:
                        self.send_error(404); return
                    body = file.read_bytes()
                    mime = mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
                    if file.suffix.lower() in ('.js', '.mjs'): mime = 'text/javascript'
                    if mime.startswith('text/') or mime == 'application/json': mime += '; charset=utf-8'
                    self.send_response(200)
                    self.send_header('Content-Type', mime)
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Referrer-Policy', 'no-referrer')
                    self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
                    self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-src 'none'; form-action 'none'; sandbox allow-scripts allow-same-origin allow-forms allow-downloads allow-modals")
                    self.end_headers()
                    self.wfile.write(body)
                except (OSError, ValueError):
                    self.send_error(404)
        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def origin(self):
        return 'http://127.0.0.1:' + str(self.server.server_port)

    def add(self, ctx, path, allowed=lambda: True):
        ctx.path(path)
        with self.lock:
            # Every project uses an unpredictable prefix; paths cannot escape it.
            token = next((k for k, (c, _) in self.entries.items() if c.workspace == ctx.workspace), None)
            token = token or secrets.token_urlsafe(24)
            self.entries[token] = (ctx, allowed)
        return self.origin + '/' + token + '/' + quote(path)

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)


async def browser_check(args, ctx):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise ValueError('浏览器验证需要安装 lebotclaw-harness[browser] 并运行 python -m playwright install chromium。')
    from .artifacts import save_artifact
    host = PreviewHost()
    errors, failed, actions = [], [], []
    try:
        url = host.add(ctx, args.get('path', 'index.html'))
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch()
            except Exception:
                raise ValueError('Chromium 未安装或无法启动。请运行 python -m playwright install chromium。')
            try:
                page = await browser.new_page(viewport={'width':1280,'height':800}, service_workers='block')
                async def route(request):
                    if request.request.url.startswith(host.origin + '/'):
                        await request.continue_()
                    else:
                        await request.abort()
                await page.route('**/*', route)
                page.on('pageerror', lambda e: errors.append(str(e)[:800]))
                page.on('console', lambda msg: errors.append(msg.text[:800]) if msg.type=='error' else None)
                page.on('dialog', lambda dialog: dialog.dismiss())
                page.on('response', lambda r: failed.append({'url':r.url.split('/')[-1], 'status':r.status}) if r.status >= 400 else None)
                page.set_default_timeout(5000)
                await page.goto(url, wait_until='networkidle', timeout=15000)
                for action in args.get('steps', []):
                    method = action['action']
                    if method == 'reload':
                        await page.reload(wait_until='networkidle')
                        actions.append({'action':'reload','passed':True})
                        continue
                    locator = page.locator(action['selector']).first
                    if method == 'click': await locator.click()
                    elif method == 'fill': await locator.fill(action.get('value', ''))
                    elif method == 'press': await locator.press(action.get('value', 'Enter'))
                    elif method == 'text_contains':
                        from playwright.async_api import expect
                        await expect(locator).to_contain_text(action.get('value', ''))
                    elif method == 'download':
                        async with page.expect_download() as download_info:
                            await locator.click()
                        download = await download_info.value
                        from pathlib import Path
                        downloaded = Path(await download.path())
                        if downloaded.stat().st_size > 20_000_000:
                            raise ValueError('下载文件超过 20 MB。')
                        saved = save_artifact(ctx, action['value'], downloaded.read_bytes())
                        actions.append({'action':'download','selector':action['selector'],'passed':True,'path':saved['path']})
                        continue
                    actions.append({'action':method, 'selector':action['selector'], 'passed':True})
                screenshot = args.get('screenshot', 'checks/browser.png')
                # Check before screenshot so existing evidence is not silently overwritten.
                if ctx.path(screenshot).exists():
                    raise ValueError('截图文件已存在，请选择新的截图路径。')
                result = save_artifact(ctx, screenshot, await page.screenshot(full_page=False))
                return {'title':await page.title(), 'text':(await page.locator('body').inner_text())[:5000],
                        'actions':actions, 'script_errors':errors[:20], 'failed_resources':failed[:20],
                        'screenshot':result['path'], 'verified':'browser_checks_passed' if not errors and not failed else 'browser_errors_found'}
            except ValueError:
                raise
            except Exception as e:
                evidence={'verified':'browser_checks_failed','error_type':type(e).__name__,
                    'actions':actions,'failed_step':args.get('steps',[])[len(actions)] if len(actions)<len(args.get('steps',[])) else None,
                    'script_errors':errors[:20],'failed_resources':failed[:20]}
                try:
                    evidence['page_text']=(await page.locator('body').inner_text(timeout=2000))[:6000]
                    screenshot=args.get('screenshot','checks/browser-error.png')
                    if not ctx.path(screenshot).exists():
                        evidence['screenshot']=save_artifact(ctx,screenshot,await page.screenshot(timeout=3000))['path']
                except Exception: pass
                return evidence
            finally:
                await browser.close()
    finally:
        host.close()
