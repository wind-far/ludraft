"""Versioned source inventories and controlled multi-file changes.

Only backend-generated project manifests select trusted registry entries. The
manifest, build scripts, core files, asset bytes and dependencies are not writable
through the coding contract. Asset management will use a separate validated path.
"""
import hashlib
import json
import re
from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from .models import Strict
from .template_registry import get_template

MANIFEST = 'ludraft.project.json'
TEXT_SUFFIXES = {'.ts', '.js', '.mjs', '.css', '.json', '.html', '.md', '.txt'}
SOURCE_ROOTS = {'src', 'public', 'licenses'}
SOURCE_TOP = {MANIFEST, 'index.html', 'style.css', 'package.json', 'package-lock.json',
              'tsconfig.json', 'vite.config.js', 'vite.config.ts', 'README.md', 'LICENSE',
              'postcss.config.js', 'tailwind.config.js'}
MAX_FILES = 512
MAX_SOURCE_BYTES = 100 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024


def safe_name(name):
    if not isinstance(name, str) or len(name) > 240 or not re.fullmatch(r'[A-Za-z0-9_./-]+', name):
        raise ValueError('文件路径包含不允许的字符')
    if name.startswith('/') or any(p in ('', '.', '..') or p.startswith('.') for p in name.split('/')):
        raise ValueError('文件路径不允许或超出项目范围')
    return name


class AssetReference(Strict):
    id: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,79}$')
    path: str
    sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    source: Literal['builtin', 'upload', 'generated']

    @model_validator(mode='after')
    def valid_path(self):
        safe_name(self.path)
        if not self.path.startswith('public/assets/'):
            raise ValueError('素材必须位于 public/assets/')
        return self


class ProjectManifest(Strict):
    schema_version: Literal[1] = 1
    template_id: str
    template_version: str
    assets: list[AssetReference] = Field(default_factory=list, max_length=256)

    @model_validator(mode='after')
    def known_template(self):
        get_template(self.template_id, self.template_version)
        if len({a.id for a in self.assets}) != len(self.assets) or len({a.path for a in self.assets}) != len(self.assets):
            raise ValueError('素材标识和路径不能重复')
        return self


class ProjectFileChange(Strict):
    operation: Literal['create', 'update', 'delete']
    path: str
    content: str | None = Field(default=None, max_length=200_000)

    @model_validator(mode='after')
    def valid_operation(self):
        safe_name(self.path)
        if self.operation == 'delete' and self.content is not None:
            raise ValueError('删除文件不能同时写入内容')
        if self.operation != 'delete' and self.content is None:
            raise ValueError('新增或修改必须提供文件内容')
        return self


class ProjectChanges(Strict):
    summary: str = Field(min_length=1, max_length=2000)
    base_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    files: list[ProjectFileChange] = Field(min_length=1, max_length=50)

    @model_validator(mode='after')
    def unique_paths(self):
        if len({f.path for f in self.files}) != len(self.files):
            raise ValueError('同一批次的文件路径不能重复')
        return self


def manifest(root):
    path = Path(root) / MANIFEST
    if path.is_symlink():
        raise ValueError('项目清单不能是符号链接')
    if not path.exists():
        return None
    if path.stat().st_size > 128_000:
        raise ValueError('项目清单过大')
    return ProjectManifest.model_validate_json(path.read_bytes())


def inventory(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('项目根目录无效')
    items, total = [], 0
    for path in sorted(root.rglob('*')):
        name = path.relative_to(root).as_posix()
        if name.split('/')[0] not in SOURCE_ROOTS and name not in SOURCE_TOP:
            continue
        safe_name(name)
        if path.is_symlink():
            raise ValueError('项目源文件不能包含符号链接')
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError('项目源文件类型无效')
        size = path.stat().st_size
        total += size
        if size > MAX_SOURCE_BYTES or total > MAX_SOURCE_BYTES or len(items) >= MAX_FILES:
            raise ValueError('项目文件数量或体积超过限制')
        # Incremental hashing avoids loading an entire project into memory.
        with path.open('rb') as file:
            digest = hashlib.file_digest(file, 'sha256').hexdigest()
        items.append({'path': name, 'size': size, 'sha256': digest,
                      'text': path.suffix in TEXT_SUFFIXES or path.name == 'LICENSE'})
    project = manifest(root)
    if project:
        by_path = {f['path']: f for f in items}
        for asset in project.assets:
            if by_path.get(asset.path, {}).get('sha256') != asset.sha256:
                raise ValueError('素材文件缺失或与清单摘要不一致')
    return items


def source_digest(root):
    return hashlib.sha256(json.dumps(inventory(root), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def text_sources(root):
    result, total = {}, 0
    for entry in inventory(root):
        if not entry['text']:
            continue
        total += entry['size']
        if total > MAX_TEXT_BYTES:
            raise ValueError('源码超过整包读取限制，请使用文件清单按需读取')
        try:
            result[entry['path']] = (Path(root) / entry['path']).read_text(encoding='utf-8')
        except UnicodeError:
            raise ValueError('文本源文件不是有效 UTF-8') from None
    return result


def apply_project_changes(root, changes):
    from .file_transactions import atomic_edit
    root = Path(root)

    def edit(staged):
        project = manifest(staged)
        if project is None:
            raise ValueError('多文件变更需要有效的项目清单')
        if source_digest(staged) != changes.base_digest:
            raise ValueError('项目已变化，请重新读取后再修改')
        template = get_template(project.template_id, project.template_version)
        for change in changes.files:
            if not template.editable(change.path):
                raise ValueError('文件不属于模板允许修改的业务范围')
            target = staged / change.path
            if change.operation == 'create' and target.exists():
                raise ValueError('待新增文件已经存在')
            if change.operation != 'create' and not target.is_file():
                raise ValueError('待修改或删除文件不存在')
            if change.operation == 'delete':
                target.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(change.content, encoding='utf-8')
        inventory(staged)

    atomic_edit(root, edit)
