#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量生成剧情配音：豆包 TTS 炀炀2.0（ICL_uranus_zh_male_yangyang_tob）
流程：node 导出脚本文本 → 逐条合成 mp3 → assets/story/voice/<djb2hash>.mp3
引擎按 say/narr 节点原文算同样的 djb2 hash 找音频，找不到回退浏览器语音。
用法: python3 gen_voice.py            # 全部（已存在自动跳过）
"""
import os, sys, json, uuid, asyncio, re, subprocess
from pathlib import Path

os.environ["NO_PROXY"] = "openspeech.bytedance.com,bytedance.com,127.0.0.1,localhost"
os.environ["no_proxy"] = os.environ["NO_PROXY"]

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from _tts_ws.protocols import (MsgType, EventType, start_connection, finish_connection,
                               start_session, finish_session, task_request, receive_message)
import websockets

def _load_api_key() -> str:
    """优先环境变量 DOUBAO_TTS_API_KEY，其次本地 tools/.api_key（已 gitignore，不入库）"""
    key = os.environ.get('DOUBAO_TTS_API_KEY', '').strip()
    if not key and (HERE / '.api_key').exists():
        key = (HERE / '.api_key').read_text(encoding='utf-8').strip()
    return key

API_KEY = _load_api_key()
if not API_KEY:
    sys.exit('缺少豆包 TTS API key：export DOUBAO_TTS_API_KEY=... 或把 key 写入 tools/.api_key')
RESOURCE_ID = "seed-tts-2.0"
SPEAKER = "ICL_uranus_zh_male_yangyang_tob"   # 炀炀 2.0 少年男声
URL = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"

SITE = HERE.parent
VOICE_DIR = SITE / 'assets' / 'story' / 'voice'
VOICE_DIR.mkdir(parents=True, exist_ok=True)


def djb2(s: str) -> str:
    """与 JS charCodeAt 对齐：按 UTF-16 码元迭代"""
    h = 5381
    b = s.encode('utf-16-be')
    for i in range(0, len(b), 2):
        h = ((h << 5) + h + ((b[i] << 8) | b[i + 1])) & 0xffffffff
    return format(h, 'x')


def clean(text: str) -> str:
    """TTS 输入：去 markdown 强调、去 emoji"""
    t = text.replace('**', '')
    t = re.sub(r'[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍️]', '', t)
    return t.strip()


def dump_texts() -> list:
    """用 node 读 script-intro.js，导出全部需要配音的文本（say/narr/choice反馈）"""
    js = r'''
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
eval(src.replace('window.PROLOGUE_SCRIPT', 'globalThis.S'));
const out = [];
for (const n of globalThis.S) {
  if (n.t === 'say' || n.t === 'narr') out.push(n.text);
  if (n.t === 'choice') (n.options || []).forEach(o => { if (o.fb) out.push(o.fb); });
}
console.log(JSON.stringify([...new Set(out)], null, 0));
'''
    r = subprocess.run(['node', '-e', js, str(SITE / 'assets' / 'story' / 'script-intro.js')],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


async def tts(text: str, out_path: Path) -> bool:
    session_id = str(uuid.uuid4())
    headers = {"X-Api-Key": API_KEY, "X-Api-Resource-Id": RESOURCE_ID, "X-Api-Connect-Id": str(uuid.uuid4())}
    audio = bytearray()
    try:
        async with websockets.connect(URL, extra_headers=headers, max_size=8 * 1024 * 1024,
                                      open_timeout=30, close_timeout=10, ping_interval=20) as ws:
            await start_connection(ws)
            msg = await asyncio.wait_for(receive_message(ws), timeout=15)
            if msg.type == MsgType.Error or msg.event == EventType.ConnectionFailed:
                print("  ❌ 鉴权失败"); return False
            payload = json.dumps({
                "user": {"uid": session_id}, "namespace": "BidirectionalTTS",
                "req_params": {"speaker": SPEAKER, "audio_params": {"format": "mp3", "sample_rate": 24000}},
            }).encode()
            await start_session(ws, payload, session_id)
            while True:
                msg = await asyncio.wait_for(receive_message(ws), timeout=10)
                if msg.type == MsgType.Error or msg.event == EventType.SessionFailed:
                    print("  ❌ session失败", msg.payload[:200].decode('utf-8', 'ignore') if msg.payload else "")
                    return False
                if msg.type == MsgType.AudioOnlyServer and msg.payload:
                    audio += msg.payload
                if msg.event == EventType.SessionStarted:
                    break
            await task_request(ws, json.dumps({"req_params": {"text": text}}).encode(), session_id)
            await finish_session(ws, session_id)
            loop = asyncio.get_event_loop()
            deadline = loop.time() + 40
            while loop.time() < deadline:
                try:
                    msg = await asyncio.wait_for(receive_message(ws), timeout=15)
                except asyncio.TimeoutError:
                    break
                if msg.type == MsgType.Error:
                    print("  ❌ err", msg.error_code, msg.payload[:200].decode('utf-8', 'ignore') if msg.payload else "")
                    return False
                if msg.type == MsgType.AudioOnlyServer and msg.payload:
                    audio += msg.payload
                if msg.event in (EventType.SessionFinished, EventType.ConnectionFinished):
                    break
            try:
                await finish_connection(ws)
            except Exception:
                pass
    except Exception as e:
        print("  ❌ 异常:", repr(e)[:200]); return False
    if len(audio) > 1000:
        out_path.write_bytes(bytes(audio))
        return True
    print(f"  ❌ 无音频（{len(audio)}B）"); return False


async def main():
    texts = dump_texts()
    print(f"共 {len(texts)} 条待配音文本")
    ok = fail = skip = 0
    for i, raw in enumerate(texts):
        h = djb2(raw)
        out = VOICE_DIR / f'{h}.mp3'
        if out.exists():
            skip += 1; continue
        t = clean(raw)
        print(f"[{i+1}/{len(texts)}] {t[:30]}…")
        if await tts(t, out):
            ok += 1; print(f"  ✅ {out.name}")
        else:
            fail += 1
        await asyncio.sleep(0.5)
    print(f"\n完成：成功 {ok}，跳过 {skip}，失败 {fail}")

if __name__ == '__main__':
    asyncio.run(main())
