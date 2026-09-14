"""Trusted build inventory binding source, assets and served artifacts together."""
import hashlib
import json
import shutil
from pathlib import Path
from .project_files import manifest, safe_name, source_digest, MAX_SOURCE_BYTES, MAX_FILES

BUILD_MANIFEST = 'ludraft.artifacts.json'
MEDIA = {'.html':'text/html', '.js':'text/javascript', '.mjs':'text/javascript',
         '.css':'text/css', '.json':'application/json', '.png':'image/png',
         '.jpg':'image/jpeg', '.jpeg':'image/jpeg', '.webp':'image/webp'}


def digest_file(path):
    with path.open('rb') as file:
        return hashlib.file_digest(file, 'sha256').hexdigest()


def capture_artifacts(root):
    root=Path(root);project=manifest(root)
    if project is None:
        raise ValueError('新构建清单需要有效的项目身份')
    build=root/'dist'
    if build.is_symlink() or not build.is_dir():
        raise ValueError('构建目录不存在或无效')
    files={};total=0
    for path in sorted(build.rglob('*')):
        if path.is_symlink():
            raise ValueError('构建产物不能包含符号链接')
        if path.is_dir():continue
        if not path.is_file():raise ValueError('构建产物类型无效')
        name=safe_name(path.relative_to(build).as_posix())
        # Sourcemaps and unsupported media are never exposed through preview.
        if path.suffix not in MEDIA:continue
        if path.suffix=='.html' and name!='index.html':continue
        size=path.stat().st_size;total+=size
        if total>MAX_SOURCE_BYTES or len(files)>=MAX_FILES:
            raise ValueError('构建产物超过数量或体积限制')
        files[name]={'sha256':digest_file(path),'size':size,'media_type':MEDIA[path.suffix]}
    if 'index.html' not in files:raise ValueError('构建缺少入口 index.html')
    data={'schema_version':1,'template_id':project.template_id,'template_version':project.template_version,
          'source_digest':source_digest(root),'files':files}
    (root/BUILD_MANIFEST).write_text(json.dumps(data,sort_keys=True,ensure_ascii=False),encoding='utf-8')
    return {'source_digest':data['source_digest'],'artifact_digest':digest_file(root/BUILD_MANIFEST)}


def read_artifacts(root):
    root=Path(root);path=root/BUILD_MANIFEST
    if root.is_symlink() or path.is_symlink() or not path.is_file() or path.stat().st_size>256_000:
        raise ValueError('构建清单不存在或无效')
    data=json.loads(path.read_bytes());project=manifest(root)
    if not isinstance(data,dict) or type(data.get('schema_version')) is not int or data['schema_version']!=1 or project is None:
        raise ValueError('构建清单格式无效')
    if (data.get('template_id'),data.get('template_version'))!=(project.template_id,project.template_version):
        raise ValueError('构建清单与模板身份不一致')
    files=data.get('files')
    if not isinstance(files,dict) or not 1<=len(files)<=MAX_FILES:
        raise ValueError('构建文件清单无效')
    if 'index.html' not in files:
        raise ValueError('构建缺少入口 index.html')
    total = 0
    for name,entry in files.items():
        safe_name(name)
        expected_type=MEDIA.get(Path(name).suffix)
        if expected_type == 'text/html' and name != 'index.html':
            raise ValueError('构建只能提供根入口 HTML')
        if expected_type is None or not isinstance(entry,dict) or entry.get('media_type')!=expected_type:
            raise ValueError('构建资源媒体类型无效')
        if type(entry.get('size')) is not int or not 0<=entry['size']<=MAX_SOURCE_BYTES:
            raise ValueError('构建资源体积无效')
        total += entry['size']
        if total > MAX_SOURCE_BYTES:
            raise ValueError('构建资源总量超限')
        digest=entry.get('sha256')
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('构建资源摘要无效')
    return data


def artifact_file(root, name):
    root=Path(root);safe_name(name);data=read_artifacts(root)
    entry=data['files'].get(name)
    if entry is None:raise ValueError('资源不在可信构建清单中')
    target=root/'dist'/name
    chain=[target,*list(target.parents)[:len(target.relative_to(root).parts)]]
    if any(p.is_symlink() for p in chain):
        raise ValueError('资源路径包含符号链接')
    if not target.is_file() or not target.resolve().is_relative_to((root/'dist').resolve()):
        raise ValueError('资源路径无效')
    if target.stat().st_size!=entry['size'] or digest_file(target)!=entry['sha256']:
        raise ValueError('构建资源与验证版本不一致')
    return target,entry['media_type']


def binding_errors(root,evidence):
    try:
        root=Path(root);data=read_artifacts(root)
        if data['source_digest']!=source_digest(root) or evidence.get('source_digest')!=data['source_digest']:
            return ['源码或素材变化，必须重新验证']
        if evidence.get('artifact_digest')!=digest_file(root/BUILD_MANIFEST):
            return ['构建清单与测试证据不一致']
        for name in data['files']:artifact_file(root,name)
    except (ValueError,OSError,KeyError,TypeError):
        return ['构建产物缺失、变化或清单无效']
    return []


def copy_build_manifest(source,destination):
    if manifest(source) is not None:
        read_artifacts(source)
        shutil.copyfile(Path(source)/BUILD_MANIFEST,Path(destination)/BUILD_MANIFEST)
