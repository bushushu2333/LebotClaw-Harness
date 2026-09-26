"""Public tool extension API and built-in workspace tools."""
import asyncio
import hashlib
import importlib.util
import inspect
import json
import os
import signal
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from jsonschema import Draft202012Validator


@dataclass
class ToolContext:
    workspace: Path
    home: Path
    run_id: str
    execution: dict
    authorize: Callable = None
    media: object = None

    def path(self, value, directory=False):
        if not isinstance(value, str) or len(value) > 600 or '\x00' in value:
            raise ValueError("无效的项目路径。")
        raw = Path(value)
        if raw.is_absolute() or '..' in raw.parts:
            raise ValueError("只允许项目内的相对路径。")
        current = self.workspace.resolve()
        for part in raw.parts:
            if part in ('.git', '.ssh', '.venv', 'node_modules') or part == '.env' or (part.startswith('.env.') and part != '.env.example'):
                raise ValueError("默认不向模型开放凭据、依赖或版本管理内部目录。")
            current = current / part
            if current.is_symlink():
                raise ValueError("工具不跟随项目中的符号链接。")
        resolved = current.resolve()
        if not resolved.is_relative_to(self.workspace.resolve()):
            raise ValueError("路径超出项目。")
        if not directory and resolved == self.workspace.resolve():
            raise ValueError("请指定文件。")
        return resolved


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable
    effect: str = "read"

    def schema(self):
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": self.parameters}}


class ToolRegistry:
    def __init__(self):
        self.tools = {}

    def register(self, tool):
        if tool.name in self.tools:
            raise ValueError("工具名称重复：" + tool.name)
        if not tool.name.replace('_', '').isalnum() or len(tool.name) > 64:
            raise ValueError("工具名称仅支持字母、数字和下划线。")
        if tool.effect not in ("read", "write", "execute"):
            raise ValueError("不支持的工具副作用类型。")
        Draft202012Validator.check_schema(tool.parameters)
        self.tools[tool.name] = tool

    def schemas(self):
        return [t.schema() for t in self.tools.values()]

    async def execute(self, name, arguments, context):
        tool = self.tools.get(name)
        if not tool:
            return {"ok": False, "error": "未知工具：" + name}
        try:
            Draft202012Validator(tool.parameters).validate(arguments)
            if context.authorize:
                await context.authorize(tool, arguments)
            if tool.effect == 'execute' and context.execution['mode'] == 'off':
                return {"ok": False, "error": "程序执行未开启。可由操作者在 CLI 配置 Docker 或明确开启 host 模式。", "code": "EXECUTION_DISABLED"}
            result = tool.handler(arguments, context)
            if inspect.isawaitable(result):
                result = await result
            encoded = json.dumps(result, ensure_ascii=False)
            if len(encoded.encode()) > 180000:
                return {"ok": False, "error": "工具输出过大，请缩小读取范围。"}
            return {"ok": True, "data": result}
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            # Never surface arbitrary plugin exception text, which may embed credentials.
            from jsonschema.exceptions import ValidationError
            if isinstance(exc, ValidationError):
                return {"ok": False, "error": "参数未通过 JSON Schema 校验。", "path": list(exc.path)}
            if isinstance(exc, ModuleNotFoundError):
                return {"ok": False, "error": "该工具缺少可选依赖；文档工具请安装 lebotclaw-harness[documents]，浏览器验证请安装 lebotclaw-harness[browser] 并安装 Chromium。"}
            if isinstance(exc, (ValueError, FileNotFoundError, UnicodeError)):
                return {"ok": False, "error": str(exc)[:500]}
            return {"ok": False, "error": "工具执行失败：" + type(exc).__name__}

    def load_plugin(self, path):
        # This is trusted application code, NOT a sandboxed third-party extension.
        p = Path(path).expanduser().resolve()
        spec = importlib.util.spec_from_file_location('lebot_plugin_' + uuid.uuid4().hex, str(p))
        if not spec or not spec.loader:
            raise ValueError("无法载入扩展。")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.register(self)


def schema(properties=None, required=None):
    return {"type": "object", "properties": properties or {}, "required": required or [], "additionalProperties": False}


def text_field(description=""):
    return {"type": "string", "description": description, "maxLength": 400000}


def list_files(args, ctx):
    root = ctx.path(args.get('path', '.'), directory=True)
    entries = []
    if not root.is_dir():
        raise ValueError("目录不存在。")
    # Prune excluded trees before traversal; don't scan dependency directories.
    pending = [root]
    while pending and len(entries) < 500:
        folder = pending.pop(0)
        for p in sorted(folder.iterdir()):
            relative = str(p.relative_to(ctx.workspace))
            try:
                ctx.path(relative)
            except ValueError:
                continue
            entries.append({"path": relative, "kind": "directory" if p.is_dir() else "file"})
            if args.get('recursive') and p.is_dir():
                pending.append(p)
            if len(entries) >= 500:
                break
    return {"entries": entries, "limit": 500}


def read_file(args, ctx):
    path = ctx.path(args['path'])
    if not path.is_file():
        raise ValueError('只支持常规文件。')
    if path.stat().st_size > 5_000_000:
        raise ValueError("文件大于 5 MB，请先拆分。")
    data = path.read_bytes()
    content = data.decode('utf-8')
    start = args.get('start_line', 1) - 1
    lines = content.splitlines()
    selected = '\n'.join(lines[start:start + args.get('line_count', 200)])
    if len(selected.encode()) > 120000:
        raise ValueError("这一段过大，请减少行数。")
    return {"path": args['path'], "content": selected, "start_line": start + 1, "total_lines": len(lines), "sha256": hashlib.sha256(data).hexdigest()}


def write_file(args, ctx):
    path = ctx.path(args['path'])
    encoded = args['content'].encode('utf-8')
    if len(encoded) > 500000:
        raise ValueError("单次写入最多 500 KB。")
    from .artifacts import save_artifact
    return save_artifact(ctx, args['path'], encoded, args.get('expected_sha256'))


def patch_file(args, ctx):
    path = ctx.path(args['path'])
    if not path.is_file() or path.stat().st_size > 500000:
        raise ValueError('补丁支持 500 KB 内的文本文件。')
    content = path.read_text(encoding='utf-8')
    if content.count(args['old']) != 1:
        raise ValueError('被替换文本必须唯一匹配；请先读取文件并补充上下文。')
    return write_file({'path':args['path'], 'content':content.replace(args['old'], args['new'], 1),
                       'expected_sha256':args['expected_sha256']}, ctx)


def file_info(args, ctx):
    path = ctx.path(args['path'])
    if not path.is_file() or path.stat().st_size > 20_000_000:
        raise ValueError('只支持 20 MB 内的常规文件。')
    return {'path':args['path'], 'bytes':path.stat().st_size, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def search_files(args, ctx):
    matches = []
    files = list_files({'path': args.get('path', '.'), 'recursive': True}, ctx)['entries']
    for item in files:
        if item['kind'] != 'file':
            continue
        path = ctx.path(item['path'])
        if not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
                if args['text'].casefold() in line.casefold():
                    matches.append({"path": item['path'], "line": n, "text": line[:500]})
                    if len(matches) >= 100:
                        return {"matches": matches, "truncated": True}
        except UnicodeError:
            continue
    return {"matches": matches, "truncated": False}


async def terminate(process):
    # A shell can exit while descendants still hold stdout or run in its group.
    if os.name == 'posix':
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            await process.wait()
            return
        except PermissionError:
            # Darwin can report EPERM for an already-exited, reaped process group.
            if process.returncode is None:
                raise
            return
        try:
            await asyncio.wait_for(process.wait(), 0.3)
        except asyncio.TimeoutError:
            pass
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                if process.returncode is None:
                    raise
        await process.wait()
    elif process.returncode is None:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 1.5)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()


async def command_run(args, ctx):
    argv = args['argv']
    mode = ctx.execution['mode']
    timeout = args.get('timeout_seconds', 30)
    cwd = ctx.path(args.get('cwd', '.'), directory=True)
    if not cwd.is_dir():
        raise ValueError("工作目录不存在。")
    docker_name = None
    if mode == 'docker':
        docker_name = 'lebot-' + uuid.uuid4().hex[:16]
        argv = ['docker', 'run', '--pull', 'never', '--rm', '--name', docker_name, '--init', '--network', 'bridge' if ctx.execution.get('network') else 'none',
                '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--pids-limit', '64',
                '--memory', '512m', '--cpus', '1',
                *(['--user', str(os.getuid()) + ':' + str(os.getgid())] if os.name == 'posix' else []), '--tmpfs', '/tmp:rw,nosuid,size=64m',
                '--mount', 'type=bind,source=' + str(ctx.workspace) + ',target=/workspace',
                '--workdir', '/workspace/' + str(cwd.relative_to(ctx.workspace)),
                '--env', 'HOME=/tmp', '--env', 'PYTHONDONTWRITEBYTECODE=1',
                ctx.execution['image'], *argv]
    elif mode != 'host':
        raise ValueError("执行未开启。")
    # Host mode is explicitly unconfined. Never inherit provider credentials.
    with tempfile.TemporaryDirectory(prefix='lebot-exec-') as temp_home:
        env = {'PATH': os.environ.get('PATH', os.defpath), 'HOME': temp_home,
               'TMPDIR': temp_home, 'LANG': 'en_US.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}
        if mode == 'docker':
            # Docker CLI may need its current context; it is NOT mounted in the container.
            env['HOME'] = str(Path.home())
        if os.name == 'nt':
            env['SYSTEMROOT'] = os.environ.get('SYSTEMROOT', r'C:\Windows')
        process = await asyncio.create_subprocess_exec(*argv, cwd=str(cwd), env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            start_new_session=(os.name == 'posix'))
        outputs = [bytearray(), bytearray()]
        truncated = [False, False]
        async def drain(stream, i):
            while True:
                chunk = await stream.read(8192)
                if not chunk:
                    return
                remaining = 50000 - len(outputs[i])
                outputs[i].extend(chunk[:max(0, remaining)])
                if len(chunk) > remaining:
                    truncated[i] = True
        readers = [asyncio.create_task(drain(process.stdout, 0)), asyncio.create_task(drain(process.stderr, 1))]
        timed_out = False
        try:
            try:
                await asyncio.wait_for(process.wait(), timeout)
            except asyncio.TimeoutError:
                timed_out = True
                await terminate(process)
            await terminate(process)
            await asyncio.wait_for(asyncio.gather(*readers), 3)
        finally:
            await terminate(process)
            for reader in readers:
                if not reader.done():
                    reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
            if docker_name:
                # Killing the docker client alone does not reliably stop its container.
                cleanup = await asyncio.create_subprocess_exec('docker', 'rm', '-f', docker_name,
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                try:
                    await asyncio.wait_for(cleanup.wait(), 10)
                except asyncio.TimeoutError:
                    cleanup.kill()
                    await cleanup.wait()
        return {"exit_code": process.returncode, "stdout": outputs[0].decode('utf-8', 'replace'),
                "stderr": outputs[1].decode('utf-8', 'replace'), "timed_out": timed_out,
                "truncated": any(truncated), "execution_mode": mode,
                "isolation": "docker_configured_boundary" if mode == 'docker' else "NONE_HOST_USER_AUTHORITY"}


def document_read(args, ctx):
    path = ctx.path(args['path'])
    if not path.is_file():
        raise ValueError('只支持常规文件。')
    if path.suffix.lower() in ('.docx', '.pptx'):
        from .documents import office_read
        return office_read(path)
    if path.suffix.lower() != '.pdf':
        return read_file({'path': args['path'], 'line_count': 300}, ctx)
    if path.stat().st_size > 15_000_000:
        raise ValueError("PDF 最多 15 MB。")
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError("PDF 需要安装 lebotclaw-harness[documents]；扫描件 OCR 尚未接入。")
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        raise ValueError("暂不支持加密 PDF。")
    page_no = args.get('page', 1)
    if not 1 <= page_no <= len(reader.pages):
        raise ValueError("页码超出范围。")
    content = reader.pages[page_no - 1].extract_text() or ''
    return {"page": page_no, "total_pages": len(reader.pages), "text": content[:30000],
            "truncated": len(content) > 30000, "note": "没有文本层的扫描件需要另接 OCR 或视觉模型。" if not content.strip() else ''}


def default_registry():
    r = ToolRegistry()
    r.register(Tool('files_list', '列出当前项目的文件，最多 500 项。', schema({'path': text_field(), 'recursive': {'type': 'boolean'}}), list_files))
    r.register(Tool('file_read', '按行读取 UTF-8 文件，返回内容哈希；覆盖前先读取。', schema({'path': text_field(), 'start_line': {'type':'integer','minimum':1}, 'line_count': {'type':'integer','minimum':1,'maximum':500}}, ['path']), read_file))
    r.register(Tool('file_write', '保存文件；覆盖现有文件必须提供读取时的 expected_sha256。', schema({'path': text_field(), 'content': text_field(), 'expected_sha256': {'type':'string','pattern':'^[a-f0-9]{64}$'}}, ['path','content']), write_file, 'write'))
    r.register(Tool('files_search', '在项目文本文件中查找文字，返回行号与来源。', schema({'path': text_field(), 'text': {'type':'string','minLength':1,'maxLength':300}}, ['text']), search_files))
    r.register(Tool('command_run', '执行参数数组形式的命令，读取退出码、stdout、stderr。仅在操作者配置执行模式后可用。', schema({'argv': {'type':'array','minItems':1,'maxItems':60,'items':{'type':'string','maxLength':12000}}, 'cwd': text_field(), 'timeout_seconds': {'type':'integer','minimum':1,'maximum':120}}, ['argv']), command_run, 'execute'))
    r.register(Tool('document_read', '提取文本文档或 PDF 指定页，保留页码。扫描件不进行猜测。', schema({'path': text_field(), 'page': {'type':'integer','minimum':1}}, ['path']), document_read))
    from .media import image_generate
    from .documents import document_create
    from .preview import browser_check
    r.register(Tool('file_info', '查看文件大小与 SHA256，支持二进制成果。', schema({'path':text_field()}, ['path']), file_info))
    r.register(Tool('file_patch', '唯一文本替换，避免重写整个文件；需传读取时的 SHA256。', schema({'path':text_field(), 'old':{'type':'string','minLength':1,'maxLength':200000}, 'new':text_field(), 'expected_sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'}}, ['path','old','new','expected_sha256']), patch_file, 'write'))
    r.register(Tool('image_generate', '调用用户配置的生图服务生成真实图片并保存到项目，可能计费；每次一张，使用新文件名。', schema({'prompt':{'type':'string','minLength':1,'maxLength':12000}, 'path':text_field()}, ['prompt','path']), image_generate, 'write'))
    section = schema({'title':{'type':'string','maxLength':150}, 'body':{'type':'string','maxLength':5000}, 'bullets':{'type':'array','maxItems':15,'items':{'type':'string','maxLength':1000}}, 'image':text_field()}, ['title'])
    r.register(Tool('document_create', '生成可编辑 PPTX 或 DOCX，可引用项目中的图片；每页/节由模型组织。排版需另行验证。', schema({'path':text_field(), 'title':{'type':'string','maxLength':150}, 'subtitle':{'type':'string','maxLength':500}, 'sections':{'type':'array','minItems':1,'maxItems':60,'items':section}}, ['path','title','sections']), document_create, 'write'))
    action = schema({'action':{'enum':['click','fill','press','text_contains','reload','download']}, 'selector':{'type':'string','maxLength':500}, 'value':{'type':'string','maxLength':5000,'description':'fill/press/assert 的值；download 是保存路径；reload 可传空 selector。'}}, ['action','selector'])
    r.register(Tool('browser_check', '在隔离的 Chromium 中运行项目网页，检查 JS 错误、资源和指定交互，保存截图。只允许本项目资源，不能访问外网。', schema({'path':text_field(), 'steps':{'type':'array','maxItems':20,'items':action}, 'screenshot':text_field()}, ['path','screenshot']), browser_check, 'write'))
    return r
