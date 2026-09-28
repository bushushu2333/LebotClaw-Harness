"""多状态截图：首跑对话框、聊天模式、制作模式、工作台、授权对话框、窄窗口。"""
import json, subprocess, sys, time, urllib.request, os, shutil, sqlite3
sys.path.insert(0, 'src')
from playwright.sync_api import sync_playwright

import os.path
HOME = os.path.realpath('/tmp/lh-shots')
PORT = 18973
shutil.rmtree(HOME, ignore_errors=True)
OUT = '/tmp/lh-shots-out'; os.makedirs(OUT, exist_ok=True)

env = dict(os.environ, LEBOTCLAW_HOME=HOME, PYTHONPATH='src')
proc = subprocess.Popen(['.venv/bin/python', '-m', 'lebotclaw_harness', 'web', '--port', str(PORT)],
                        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
base = f'http://127.0.0.1:{PORT}'
for _ in range(40):
    try: urllib.request.urlopen(base + '/api/bootstrap', timeout=1); break
    except Exception: time.sleep(0.5)
else: raise SystemExit('server failed to boot')

def api(path, token, body=None):
    print('api ->', path)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + '/api/' + path, data=data, method='POST' if data else 'GET',
                                 headers={'X-Lebot-Token': token, 'Content-Type': 'application/json'})
    return json.load(urllib.request.urlopen(req))

try:
    boot = json.load(urllib.request.urlopen(base + '/api/bootstrap'))
    token = boot['token']
    # 种一个本地模型配置（不连通也能让 UI 走正常态）
    api('model', token, {'name': 'local', 'provider': 'openai-compatible', 'model': 'fixture-model',
                         'base_url': 'http://127.0.0.1:1/v1', 'key': 'X'})
    # 种一个聊天会话（带消息）和一个项目会话（带文件+事件）
    chat = api('session', token, {'title': '聊聊打砖块怎么做', 'kind': 'chat'})
    db = sqlite3.connect(os.path.join(HOME, 'sessions.sqlite3'))
    db.execute("INSERT INTO messages(session_id,run_id,body) VALUES(?,?,?)",
               (chat['id'], None, json.dumps({'role': 'user', 'content': '我想做一个打砖块游戏'})))
    db.execute("INSERT INTO messages(session_id,run_id,body) VALUES(?,?,?)",
               (chat['id'], None, json.dumps({'role': 'assistant', 'content': '好主意！我们可以用 HTML + JS 来做。**先聊聊规则**：球速要多快？要不要关卡？'})))
    db.commit()  # 先提交释放写锁，避免阻塞服务端建项目
    proj = api('session', token, {'title': '我的打砖块游戏'})
    sid = proj['id']
    api('permission', token, {'session': sid, 'permission': {'mode': 'plan', 'read': True, 'remember': True}})
    import pathlib
    root = pathlib.Path(proj['workspace'])
    (root / 'assets').mkdir()
    (root / 'index.html').write_text('<!doctype html><title>demo</title><h1>打砖块</h1>')
    (root / 'game.js').write_text('// 游戏主循环\nconst paddle = {x: 50};\nfunction loop() {\n  return "running";\n}\n')
    (root / 'assets' / 'starfield.md').write_text('# 素材说明\n\n星空背景图。\n')
    db.execute("INSERT INTO events(session_id,run_id,kind,data,created) VALUES(?,?,?,?,?)",
               (sid, None, 'tool.started', json.dumps({'action_id': 'p1', 'name': 'file_patch', 'arguments': {'path': 'game.js', 'old': 'const paddle = {x: 50};', 'new': 'const paddle = {x: 50, w: 120};', 'expected_sha256': 'x'}}), time.time()))
    db.execute("INSERT INTO events(session_id,run_id,kind,data,created) VALUES(?,?,?,?,?)",
               (sid, None, 'tool.finished', json.dumps({'action_id': 'p1', 'result': {'ok': True}}), time.time()))
    db.commit(); db.close()

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx0 = None
        def shot(name, page):
            page.screenshot(path=f'{OUT}/{name}.png')
            print('shot', name)
        # 1) 首跑（模型对话框自动弹出）1920x1080
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.set_default_timeout(6000)
        page.goto(base + '/'); page.wait_for_timeout(900); shot('01-first-run-dialog-1080p', page)
        # 2) 关掉对话框 → 聊天模式欢迎页
        if page.locator('#model-dialog').is_visible(): page.locator('#model-dialog .close').click()
        page.wait_for_timeout(400); shot('02-chat-welcome-1080p', page)
        # 3) 聊天会话（带消息 + 转化条）
        page.evaluate(f"localStorage.setItem('lebot-session','{chat['id']}')")
        page.goto(base + '/'); page.wait_for_timeout(900)
        if page.locator('#model-dialog').is_visible(): page.locator('#model-dialog .close').click(); page.wait_for_timeout(300)
        shot('03-chat-session-convertbar', page)
        # 4) 制作模式 + 右侧面板
        page.evaluate(f"localStorage.setItem('lebot-session','{sid}')")
        page.goto(base + '/'); page.wait_for_timeout(1000)
        if page.locator('#model-dialog').is_visible(): page.locator('#model-dialog .close').click(); page.wait_for_timeout(300)
        page.locator('#files-button').click(); page.wait_for_timeout(500)
        shot('04-work-panel-preview', page)
        # 5) 工作台页签
        page.locator('#tab-work').click(); page.wait_for_timeout(500)
        shot('05-workbench-tree', page)
        page.locator('#file-tree button', has_text='game.js').click(); page.wait_for_timeout(500)
        shot('06-workbench-code', page)
        page.locator('.work-tabs [data-wtab="diff"]').click(); page.wait_for_timeout(300)
        shot('07-workbench-diff', page)
        # 6) 授权对话框
        page.locator('#authorize').click(); page.wait_for_timeout(400)
        shot('08-grant-dialog', page)
        page.locator('#permission-dialog .close').click()
        # 7) 窄窗口 1280x800 聊天 + 工作台
        page.set_viewport_size({'width': 1280, 'height': 800}); page.wait_for_timeout(400)
        shot('09-work-1280x800', page)
        page.locator('#tab-work').click(); page.wait_for_timeout(400)
        shot('10-workbench-1280x800', page)
        # 8) 小窗 1024x700
        page.set_viewport_size({'width': 1024, 'height': 700}); page.wait_for_timeout(400)
        shot('11-1024x700', page)
        browser.close()
finally:
    proc.terminate(); proc.wait(timeout=5)
print('done ->', OUT)
