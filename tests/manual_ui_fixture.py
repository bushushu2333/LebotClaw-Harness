"""CUA-only UI fixture. Explicitly scripted model, never enabled by the product."""
import json
import tempfile
from pathlib import Path
from conftest import model_server, sse, tool_reply
from lebotclaw_harness.config import Config
from lebotclaw_harness.web import serve

HTML = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><style>body{font:16px system-ui;padding:24px;color:#292039;background:#faf8ff}button{background:#6657f4;color:white;border:0;border-radius:12px;padding:12px 20px;margin-top:20px}#count{font-size:48px;margin:20px 0}</style><h1>存储接口验证</h1><p>这是 UI 自动化测试材料。</p><div id="count">0</div><button id="add">增加一次</button><p id="result">正在读取</p><script>let n=0;Promise.resolve(JSON.parse(localStorage.getItem('ui-test-count')||'{}')).then(data=>{n=data.count||0;document.querySelector('#count').textContent=n;document.querySelector('#result').textContent='已读取本机数据'});document.querySelector('#add').onclick=async()=>{n++;localStorage.setItem('ui-test-count',JSON.stringify({count:n}));document.querySelector('#count').textContent=n;document.querySelector('#result').textContent='已保存到本机'};</script></html>'''

def respond(body,n):
    if not body.get('tools'):return sse({'role':'assistant','content':'【测试模型】当前为 Plan。请通过授权执行入口允许本次文件制作，再发送请求。'})
    last=body['messages'][-1]
    if last['role']=='tool':return sse({'role':'assistant','content':'【测试模型】文件工具已经保存 index.html，请在成果区打开并验证数据持久化。'})
    return sse(tool_reply('file_write',{'path':'index.html','content':HTML},'test-preview'))

if __name__=='__main__':
    home=Path(tempfile.mkdtemp(prefix='lebot-harness-ui-test-'))
    with model_server(respond) as (endpoint,_):
        print('TEST_MODEL_ENDPOINT='+endpoint,flush=True)
        print('TEST_HOME='+str(home),flush=True)
        serve(home,18867)
