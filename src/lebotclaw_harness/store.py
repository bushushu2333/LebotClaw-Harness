"""Transactional session log. External side effects cannot be atomically rolled back."""
import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path


def uid():
    return uuid.uuid4().hex[:20]


class Store:
    def __init__(self, home):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(self.home / "sessions.sqlite3"), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS metadata(version INTEGER NOT NULL);
        INSERT INTO metadata SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM metadata);
        CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,title TEXT NOT NULL,
            workspace TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,session_id TEXT REFERENCES sessions(id),
            status TEXT NOT NULL,model TEXT,goal TEXT,created REAL,updated REAL,steps INTEGER DEFAULT 0,
            tokens INTEGER DEFAULT 0);
        CREATE UNIQUE INDEX IF NOT EXISTS one_live_run ON runs(session_id)
            WHERE status IN ('queued','running');
        CREATE TABLE IF NOT EXISTS messages(seq INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT REFERENCES sessions(id),run_id TEXT REFERENCES runs(id),body TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT REFERENCES sessions(id),run_id TEXT REFERENCES runs(id),kind TEXT,
            data TEXT,created REAL);
        CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,run_id TEXT REFERENCES runs(id),
            call_id TEXT NOT NULL,name TEXT NOT NULL,args TEXT,status TEXT,result TEXT);
        ''')
        if self.db.execute("SELECT version FROM metadata").fetchone()[0] != 1:
            raise ValueError("数据库版本不受支持，请备份后升级。")
        self.db.commit()

    def _event(self, sid, rid, kind, data):
        self.db.execute("INSERT INTO events(session_id,run_id,kind,data,created) VALUES(?,?,?,?,?)",
                        (sid, rid, kind, json.dumps(data, ensure_ascii=False), time.time()))

    def event(self, sid, rid, kind, data):
        with self.lock, self.db:
            self._event(sid, rid, kind, data)

    def create(self, title="新任务", workspace=None):
        sid = uid()
        root = Path(workspace or self.home / "workspaces" / sid).expanduser().resolve()
        # Avoid granting a tool the entire machine or the harness's own state.
        if root == Path(root.anchor) or root == Path.home() or root == self.home or root in self.home.parents:
            raise ValueError("请指定具体项目目录，不能选择根目录、用户主目录或运行数据目录。")
        root.mkdir(parents=True, exist_ok=True)
        with self.lock, self.db:
            self.db.execute("INSERT INTO sessions VALUES(?,?,?,?,?)", (sid, title[:100], str(root), time.time(), time.time()))
            self._event(sid, None, "session.created", {"workspace": str(root)})
        return self.session(sid)

    def session(self, sid):
        with self.lock:
            row = self.db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
            if not row:
                raise ValueError("会话不存在。")
            result = dict(row)
            run = self.db.execute("SELECT * FROM runs WHERE session_id=? ORDER BY created DESC LIMIT 1", (sid,)).fetchone()
            result["last_run"] = dict(run) if run else None
            return result

    def last_profile(self, sid):
        with self.lock:
            row = self.db.execute("SELECT data FROM events WHERE session_id=? AND kind='model.selected' ORDER BY seq DESC LIMIT 1", (sid,)).fetchone()
            return json.loads(row[0])['profile'] if row else None

    def run(self, rid):
        with self.lock:
            row = self.db.execute("SELECT * FROM runs WHERE id=?", (rid,)).fetchone()
            return dict(row) if row else None

    def sessions(self):
        with self.lock:
            return [self.session(r[0]) for r in self.db.execute("SELECT id FROM sessions ORDER BY updated DESC")]

    def begin(self, sid, goal, model, content=None):
        self.session(sid)
        rid = uid()
        with self.lock, self.db:
            self.db.execute("INSERT INTO runs(id,session_id,status,model,goal,created,updated) VALUES(?,?,?,?,?,?,?)",
                            (rid, sid, "queued", model, goal, time.time(), time.time()))
            self.db.execute("UPDATE sessions SET updated=? WHERE id=?", (time.time(), sid))
            self.db.execute("INSERT INTO messages(session_id,run_id,body) VALUES(?,?,?)",
                            (sid, rid, json.dumps({"role": "user", "content": content or goal}, ensure_ascii=False)))
            self._event(sid, rid, "run.queued", {"goal": goal})
        return rid

    def status(self, sid, rid, status, detail=None):
        with self.lock, self.db:
            self.db.execute("UPDATE runs SET status=?,updated=? WHERE id=?", (status, time.time(), rid))
            self.db.execute("UPDATE sessions SET updated=? WHERE id=?", (time.time(), sid))
            self._event(sid, rid, "run." + status, detail or {})

    def step(self, sid, rid, n, tokens=0):
        with self.lock, self.db:
            self.db.execute("UPDATE runs SET steps=?,tokens=tokens+?,updated=? WHERE id=?", (n, tokens, time.time(), rid))

    def message(self, sid, rid, body):
        with self.lock, self.db:
            self.db.execute("INSERT INTO messages(session_id,run_id,body) VALUES(?,?,?)",
                            (sid, rid, json.dumps(body, ensure_ascii=False)))
            self._event(sid, rid, "message.committed", {"role": body["role"], "content": body.get("content")})

    def history(self, sid, public=False):
        with self.lock:
            items = [json.loads(r[0]) for r in self.db.execute("SELECT body FROM messages WHERE session_id=? ORDER BY seq", (sid,))]
        if public:
            return [{"role": m["role"], "content": m.get("content"), "tool_calls": m.get("tool_calls", [])}
                    for m in items if m["role"] != "tool"]
        return items

    def action_start(self, sid, rid, call_id, name, args):
        aid = uid()
        with self.lock, self.db:
            self.db.execute("INSERT INTO actions VALUES(?,?,?,?,?,?,?)", (aid, rid, call_id, name, json.dumps(args, ensure_ascii=False), "started", None))
            self._event(sid, rid, "tool.started", {"action_id": aid, "name": name, "arguments": args})
        return aid

    def action_end(self, sid, rid, aid, call_id, result, state="finished"):
        with self.lock, self.db:
            data = json.dumps(result, ensure_ascii=False)
            self.db.execute("UPDATE actions SET status=?,result=? WHERE id=?", (state, data, aid))
            self.db.execute("INSERT INTO messages(session_id,run_id,body) VALUES(?,?,?)", (sid, rid, json.dumps({"role": "tool", "tool_call_id": call_id, "content": data}, ensure_ascii=False)))
            self._event(sid, rid, "tool.finished", {"action_id": aid, "result": result})

    def close_pending(self, sid, rid, reason):
        pending = {}
        for m in self.history(sid):
            if m["role"] == "assistant":
                for call in m.get("tool_calls") or []:
                    pending[call["id"]] = call
            elif m["role"] == "tool":
                pending.pop(m["tool_call_id"], None)
        with self.lock, self.db:
            self.db.execute("UPDATE actions SET status='unknown' WHERE run_id=? AND status='started'", (rid,))
            for call_id in pending:
                body = {"role": "tool", "tool_call_id": call_id, "content": json.dumps({"ok": False, "error": reason, "outcome": "unknown_or_not_started", "instruction": "Inspect existing state before repeating side effects."})}
                self.db.execute("INSERT INTO messages(session_id,run_id,body) VALUES(?,?,?)", (sid, rid, json.dumps(body)))
            if pending:
                self._event(sid, rid, "recovery.required", {"reason": reason, "calls": list(pending)})

    def recover(self):
        # Caller must hold the process-level runtime lock.
        with self.lock:
            rows = self.db.execute("SELECT id,session_id FROM runs WHERE status IN ('queued','running')").fetchall()
        for r in rows:
            self.close_pending(r["session_id"], r["id"], "Previous runtime stopped; completion is not known.")
            self.status(r["session_id"], r["id"], "interrupted", {"message": "上次运行中断；已保存的文件保留，未自动重复操作。"})

    def events(self, sid, after=0):
        with self.lock:
            rows = self.db.execute("SELECT * FROM events WHERE session_id=? AND seq>? ORDER BY seq LIMIT 200", (sid, after)).fetchall()
            return [{**dict(r), "data": json.loads(r["data"])} for r in rows]

    def close(self):
        with self.lock:
            self.db.close()
