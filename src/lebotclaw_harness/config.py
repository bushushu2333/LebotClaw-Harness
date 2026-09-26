import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/v1",
    "glm": "https://open.bigmodel.cn/api/paas/v4",
}


def home_path(value=None):
    return Path(value or os.environ.get("LEBOTCLAW_HOME", "~/.lebotclaw-harness")).expanduser().resolve()


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temp = tempfile.mkstemp(prefix=".config-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


class Config:
    def __init__(self, home):
        self.home = home_path(home)
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.home / "config.json"
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {
            "version": 1, "active_model": None, "models": {}, "plugins": [],
            "execution": {"mode": "off", "image": "python:3.12-slim"},
        }
        if self.data.get("version") != 1:
            raise ValueError("配置版本不受支持，请先备份配置。")
        self.data.setdefault('capabilities', {})
        self.data.setdefault('media_options', {})

    def save(self):
        atomic_json(self.path, self.data)

    def add_model(self, name, provider, model, base_url=None, key_env=None, vision=False,
                  max_output_tokens=None, reasoning_effort=None, persist=True):
        if not re.fullmatch(r"[\w-]{1,64}", name):
            raise ValueError("配置名称仅支持字母、数字、下划线、短横线。")
        if provider not in (*DEFAULT_ENDPOINTS, "openai-compatible"):
            raise ValueError("未知提供商。")
        endpoint = (base_url or DEFAULT_ENDPOINTS.get(provider, "")).rstrip("/")
        parsed = urlparse(endpoint)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("接口地址不能包含凭据、查询参数或片段。")
        if not parsed.hostname or (parsed.scheme != "https" and not (
            parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1")
        )):
            raise ValueError("在线接口必须使用 HTTPS；HTTP 仅允许本地模型。")
        if not isinstance(model, str) or not model.strip() or len(model) > 150:
            raise ValueError("请填写准确的模型 ID。")
        if key_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key_env):
            raise ValueError("密钥环境变量名称不合法。")
        previous = self.data['models'].get(name, {})
        limit = max_output_tokens if max_output_tokens is not None else previous.get('max_output_tokens', 8192)
        effort = reasoning_effort if reasoning_effort is not None else previous.get('reasoning_effort', '')
        if type(limit) is not int or not 1024 <= limit <= 131072:
            raise ValueError('单次输出预算须为 1024–131072 的整数，并且不超过模型支持的上限。')
        if effort not in ('', 'low', 'medium', 'high', 'max'):
            raise ValueError('推理强度须为空、low、medium、high 或 max；实际支持以模型为准。')
        profile = {"provider": provider, "model": model.strip(), "base_url": endpoint,
                   "key_env": key_env, "vision": bool(vision)}
        profile['max_output_tokens'] = limit
        if effort:
            profile['reasoning_effort'] = effort
        if previous.get('base_url') == endpoint and previous.get('provider') == provider and previous.get('secure_key'):
            profile['secure_key'] = True
        self.data["models"][name] = profile
        if not self.data["active_model"]:
            self.data["active_model"] = name
        if persist: self.save()
        return profile

    def model(self, name=None):
        name = name or self.data["active_model"]
        if name not in self.data["models"]:
            raise ValueError("还没有配置模型。请运行 lebotclaw models add，或在图形界面中配置。")
        return name, dict(self.data["models"][name])

    def set_execution(self, mode, image=None):
        if mode not in ("off", "docker", "host"):
            raise ValueError("执行模式应为 off、docker 或 host。")
        if image and (not isinstance(image, str) or image.startswith("-") or len(image) > 200):
            raise ValueError("镜像名称无效。")
        self.data["execution"] = {"mode": mode, "image": image or self.data["execution"]["image"]}
        self.save()
