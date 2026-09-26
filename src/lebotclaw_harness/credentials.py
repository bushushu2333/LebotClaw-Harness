"""Opt-in OS credential storage. Never fall back to a plaintext key file."""
import hashlib


def identity(home, name, profile):
    value = '\n'.join((str(home), name, profile['provider'], profile['base_url']))
    return 'lebotclaw-harness:' + hashlib.sha256(value.encode()).hexdigest()


def backend():
    try:
        import keyring
        instance = keyring.get_keyring()
        if type(instance).__module__ not in ('keyring.backends.macOS', 'keyring.backends.Windows', 'keyring.backends.SecretService'):
            raise ValueError('当前系统没有可用的安全凭据库，请使用本次密钥或环境变量。')
        return keyring
    except ImportError:
        raise ValueError('安全保存需先安装 lebotclaw-harness[secure-keys]；也可只在本次使用密钥。')


def save(home, name, profile, key):
    try:
        backend().set_password(identity(home, name, profile), 'api-key', key)
    except ValueError:
        raise
    except Exception:
        raise ValueError('系统凭据库未完成保存；未写入明文文件。')


def read(home, name, profile):
    try:
        return backend().get_password(identity(home, name, profile), 'api-key') or ''
    except Exception:
        return ''
