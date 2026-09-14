"""Role connection contracts and credential-safe atomic persistence."""
import json
import os
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from pydantic import Field
from .models import Strict

PROVIDERS={'openai':'https://api.openai.com/v1','anthropic':'https://api.anthropic.com/v1','deepseek':'https://api.deepseek.com/v1','custom':''}

class RoleConnection(Strict):
    mode: Literal['shared','independent']='shared'
    provider: Literal['openai','anthropic','deepseek','custom']='openai'
    base_url: str=Field(default='',max_length=500)
    model: str=Field(default='',max_length=200)
    api_key: str=Field(default='',max_length=1000)
    clear_key: bool=False
    max_tokens: int=Field(default=12000,ge=256,le=64000,strict=True)

class ConnectionProbe(Strict):
    summary: str=Field(min_length=1,max_length=500)


def validate_url(url):
    url=url.strip().rstrip('/')
    parsed=urlparse(url)
    if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('模型地址必须是有效的 HTTP(S) API 基础地址')
    if parsed.scheme=='http' and parsed.hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('远程模型地址必须使用 HTTPS')
    if any(c.isspace() for c in url):raise ValueError('模型地址不能包含空白字符')
    return url


def atomic_private(path:Path,data):
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(data,f,ensure_ascii=False);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def key_for(old,settings,url,provider='openai'):
    changed=old.get('base_url')!=url or old.get('provider','openai')!=provider
    if changed and old.get('api_key') and not settings.api_key.strip() and not settings.clear_key:
        raise ValueError('服务商或 API 地址已改变，请重新填写该服务的密钥，或明确清除旧密钥')
    return '' if settings.clear_key else settings.api_key.strip() or old.get('api_key','')
