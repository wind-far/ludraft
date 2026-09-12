"""
文件操作工具模块 - 安全的文件读写辅助

核心职责:
- 安全的文件读写操作
- 路径验证与规范化
- JSON/YAML 辅助读写
- 目录遍历与文件发现
- Markdown frontmatter 解析
"""

import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Union
from datetime import datetime


def safe_read(file_path: Union[str, Path], encoding: str = 'utf-8') -> Optional[str]:
    """
    安全读取文件内容

    Args:
        file_path: 文件路径
        encoding: 编码格式

    Returns:
        文件内容，读取失败返回None
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return None
        if not path.is_file():
            return None
        return path.read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError):
        return None


def safe_write(file_path: Union[str, Path], content: str,
               encoding: str = 'utf-8', create_dirs: bool = True) -> bool:
    """
    安全写入文件

    Args:
        file_path: 文件路径
        content: 写入内容
        encoding: 编码格式
        create_dirs: 是否自动创建父目录

    Returns:
        是否成功
    """
    try:
        path = Path(file_path)
        if create_dirs:
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=encoding)
        return True
    except OSError:
        return False


def safe_json_read(file_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """
    安全读取JSON文件

    Args:
        file_path: JSON文件路径

    Returns:
        解析后的字典，失败返回None
    """
    content = safe_read(file_path)
    if content is None:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None


def safe_json_write(file_path: Union[str, Path], data: Any,
                    indent: int = 2, ensure_ascii: bool = False) -> bool:
    """
    安全写入JSON文件

    Args:
        file_path: 文件路径
        data: 要写入的数据
        indent: 缩进量
        ensure_ascii: 是否仅ASCII

    Returns:
        是否成功
    """
    try:
        content = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
        return safe_write(file_path, content)
    except (TypeError, ValueError):
        return False


def safe_yaml_read(file_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """
    安全读取YAML文件

    Args:
        file_path: YAML文件路径

    Returns:
        解析后的字典，失败返回None
    """
    try:
        import yaml
    except ImportError:
        return None

    content = safe_read(file_path)
    if content is None:
        return None
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError:
        return None


def resolve_path(path: Union[str, Path], base: Optional[Union[str, Path]] = None) -> Path:
    """
    规范化路径（解析相对路径、消除 .. 等）

    Args:
        path: 要规范化的路径
        base: 基准目录（用于解析相对路径）

    Returns:
        绝对路径
    """
    p = Path(path)
    if base and not p.is_absolute():
        p = Path(base) / p
    return p.resolve()


def is_path_within(child: Union[str, Path],
                   parent: Union[str, Path]) -> bool:
    """
    检查子路径是否在父路径内（防止路径穿越）

    Args:
        child: 子路径
        parent: 父路径

    Returns:
        是否在父路径范围内
    """
    try:
        child_resolved = Path(child).resolve()
        parent_resolved = Path(parent).resolve()
        child_resolved.relative_to(parent_resolved)
        return True
    except ValueError:
        return False


def parse_frontmatter(content: str) -> Tuple[Dict[str, Any], str]:
    """
    解析Markdown文件的YAML frontmatter

    Args:
        content: Markdown文件内容

    Returns:
        (frontmatter字典, 正文内容)
    """
    frontmatter = {}
    body = content

    # 匹配 --- 包围的frontmatter
    pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)'
    match = re.match(pattern, content, re.DOTALL)

    if match:
        fm_text = match.group(1)
        body = match.group(2)

        # 简单的YAML键值解析（不依赖yaml库）
        for line in fm_text.split('\n'):
            line = line.strip()
            if ':' in line and not line.startswith('#'):
                key, _, value = line.partition(':')
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                # 处理列表
                if value.startswith('[') and value.endswith(']'):
                    items = value[1:-1].split(',')
                    value = [item.strip().strip('"').strip("'") for item in items if item.strip()]
                # 处理布尔值
                elif value.lower() in ('true', 'yes'):
                    value = True
                elif value.lower() in ('false', 'no'):
                    value = False
                # 处理数字
                elif value.isdigit():
                    value = int(value)

                frontmatter[key] = value

    return frontmatter, body


def extract_title(content: str) -> str:
    """
    从Markdown内容中提取标题

    Args:
        content: Markdown文本

    Returns:
        标题文本，未找到返回空字符串
    """
    for line in content.split('\n'):
        line = line.strip()
        if line.startswith('#'):
            return line.lstrip('#').strip()
    return ""


def scan_directory(root: Union[str, Path],
                   pattern: str = "*.md",
                   recursive: bool = True) -> List[Path]:
    """
    扫描目录中符合模式的文件

    Args:
        root: 根目录
        pattern: 文件匹配模式
        recursive: 是否递归扫描

    Returns:
        匹配的文件路径列表
    """
    root_path = Path(root)
    if not root_path.exists():
        return []

    if recursive:
        return sorted(root_path.rglob(pattern))
    else:
        return sorted(root_path.glob(pattern))


def ensure_dir(dir_path: Union[str, Path]) -> Path:
    """
    确保目录存在

    Args:
        dir_path: 目录路径

    Returns:
        目录Path对象
    """
    path = Path(dir_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_tree_safe(src: Union[str, Path], dst: Union[str, Path],
                   overwrite: bool = False) -> bool:
    """
    安全的目录复制

    Args:
        src: 源目录
        dst: 目标目录
        overwrite: 是否覆盖已存在的目标

    Returns:
        是否成功
    """
    try:
        src_path = Path(src)
        dst_path = Path(dst)

        if not src_path.exists():
            return False

        if dst_path.exists() and not overwrite:
            return False

        if dst_path.exists():
            shutil.rmtree(dst_path)

        shutil.copytree(src_path, dst_path)
        return True
    except OSError:
        return False


def get_file_info(file_path: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """
    获取文件信息

    Args:
        file_path: 文件路径

    Returns:
        文件信息字典
    """
    try:
        path = Path(file_path)
        if not path.exists():
            return None

        stat = path.stat()
        return {
            "path": str(path),
            "name": path.name,
            "stem": path.stem,
            "suffix": path.suffix,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "is_file": path.is_file(),
            "is_dir": path.is_dir()
        }
    except OSError:
        return None


def count_files(directory: Union[str, Path],
                pattern: str = "*") -> Dict[str, int]:
    """
    统计目录下文件数量

    Args:
        directory: 目录路径
        pattern: 文件匹配模式

    Returns:
        按扩展名分类的文件计数
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return {}

    counts: Dict[str, int] = {}
    for f in dir_path.rglob(pattern):
        if f.is_file():
            ext = f.suffix or "(no ext)"
            counts[ext] = counts.get(ext, 0) + 1

    return counts
