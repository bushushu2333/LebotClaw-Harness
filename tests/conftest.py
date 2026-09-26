import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest


@contextmanager
def model_server(responder):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append(body)
            status, content_type, content = responder(body, len(requests))
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            encoded = content.encode()
            self.send_header('Content-Length', str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port) + '/v1', requests
    finally:
        server.shutdown(); server.server_close(); thread.join()


def sse(message, finish=None):
    deltas = []
    if message.get('reasoning_content'):
        deltas.append({'reasoning_content': message['reasoning_content']})
    if message.get('content'):
        deltas += [{'content': message['content'][:3]}, {'content': message['content'][3:]}]
    for index, call in enumerate(message.get('tool_calls', [])):
        args = call['function']['arguments']; split = max(1,len(args)//2)
        deltas.append({'tool_calls':[{'index':index,'id':call['id'],'type':'function','function':{'name':call['function']['name'],'arguments':args[:split]}}]})
        deltas.append({'tool_calls':[{'index':index,'function':{'arguments':args[split:]}}]})
    frames = [{'choices':[{'delta':d,'finish_reason':None}]} for d in deltas]
    frames.append({'choices':[{'delta':{},'finish_reason':finish or ('tool_calls' if message.get('tool_calls') else 'stop')}], 'usage':{'total_tokens':12}})
    return 200, 'text/event-stream', ''.join('data: '+json.dumps(f)+'\n\n' for f in frames)+'data: [DONE]\n\n'


def tool_reply(name, args, id='call_1'):
    return {'role':'assistant','content':'','reasoning_content':'测试协议字段保留', 'tool_calls':[{'id':id,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}


@pytest.fixture
def serve_model():
    return model_server
