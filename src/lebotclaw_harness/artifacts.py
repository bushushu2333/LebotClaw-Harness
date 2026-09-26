"""Atomic binary artifacts with optimistic concurrency and recoverable versions."""
import hashlib
import json
import os
import tempfile
import uuid


def save_artifact(ctx, relative, data, expected=None):
    path = ctx.path(relative)
    if len(data) > 20_000_000:
        raise ValueError('单个成果不能超过 20 MB。')
    existed = path.exists()
    if existed and (not path.is_file() or path.stat().st_size > 20_000_000):
        raise ValueError('只能覆盖 20 MB 内的常规文件。')
    if existed and not expected:
        raise ValueError('文件已存在。请先读取哈希或使用新文件名，不能直接覆盖。')
    old = path.read_bytes() if existed else None
    if expected and (old is None or hashlib.sha256(old).hexdigest() != expected):
        raise ValueError('文件已变化，请重新读取。')
    path.parent.mkdir(parents=True, exist_ok=True)
    if old is not None:
        history = ctx.home / 'versions' / ctx.run_id
        history.mkdir(parents=True, exist_ok=True)
        version = uuid.uuid4().hex
        (history / (version + '.bin')).write_bytes(old)
        (history / (version + '.json')).write_text(json.dumps({
            'workspace': str(ctx.workspace), 'path': relative,
            'sha256': hashlib.sha256(old).hexdigest()}, ensure_ascii=False))
    fd, tmp = tempfile.mkstemp(prefix='.lebot-write-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        ctx.path(relative)
        if path.exists() != existed or (existed and path.read_bytes() != old):
            raise ValueError('写入前检测到其他程序修改文件，已保留其变更。')
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return {'path': relative, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'verified': 'file_saved_only'}
