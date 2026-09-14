import difflib
import shutil
from pathlib import Path
from .file_transactions import atomic_edit, workspace_lock
from .project_files import manifest, inventory, text_sources
from .template_registry import LEGACY_EDITABLE

TEMPLATE = Path(__file__).resolve().parents[1] / 'templates' / 'canvas'
MATCH3 = TEMPLATE.parent / 'match3'

def game_source(store,run):
    import json
    base=store.one('SELECT * FROM versions WHERE id=?',(run['base_version'],)) if run.get('base_version') else None
    plan=json.loads(run['plan']) if run.get('plan') else None
    if base:
        old=json.loads(base['evidence']).get('config',{}).get('mode')
        if plan and (plan['mode']=='match3')!=(old=='match3'):
            return MATCH3 if plan['mode']=='match3' else TEMPLATE
        return Path(base['path'])
    return TEMPLATE if plan and plan['mode']!='match3' else MATCH3

EDITABLE = LEGACY_EDITABLE


def copy_source(source: Path, dest: Path):
    source, dest = Path(source), Path(dest)
    if source.resolve() == dest.resolve() or dest.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(dest.resolve()):
        raise ValueError('源工程与目标工程目录必须独立')
    with workspace_lock(source):
        if manifest(source) is not None:
            entries = inventory(source)
            dest.mkdir(parents=True, exist_ok=True)
            def copy_project(staged):
                for child in staged.iterdir():
                    shutil.rmtree(child) if child.is_dir() else child.unlink()
                for entry in entries:
                    target = staged / entry['path']
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source / entry['path'], target)
            atomic_edit(dest, copy_project)
            return
        _copy_legacy(source, dest)


def _copy_legacy(source, dest):
    dest.mkdir(parents=True, exist_ok=True)
    for name in ('index.html', 'style.css', 'tsconfig.json', 'package.json', 'README.md'):
        shutil.copyfile(source / name, dest / name)
    shutil.copytree(source / 'src', dest / 'src', dirs_exist_ok=True)
    # Published snapshots are read-only. A new candidate must be writable without touching its base.
    for entry in dest.rglob('*'):
        if entry.is_file():
            entry.chmod(0o644)
        elif entry.is_dir():
            entry.chmod(0o755)


def source_files(path):
    path = Path(path)
    with workspace_lock(path):
        if manifest(path) is not None:
            return text_sources(path)
        for name in EDITABLE:
            target = path / name
            if target.is_symlink() or not target.resolve().is_relative_to(path.resolve()):
                raise ValueError('文件路径超出项目范围')
        return {name: (path / name).read_text() for name in sorted(EDITABLE)}


def apply_changes(path, changes):
    seen = set()
    for change in changes.files:
        if change.path not in EDITABLE or change.path in seen:
            raise ValueError('文件路径不允许或重复')
        seen.add(change.path)
    def edit(staged):
        for change in changes.files:
            (staged / change.path).write_text(change.content)
    atomic_edit(path, edit)


def diff_sources(old, new):
    return '\n'.join(''.join(difflib.unified_diff(old.get(n, '').splitlines(True), new.get(n, '').splitlines(True),
                     fromfile='before/' + n, tofile='after/' + n)) for n in sorted(set(old) | set(new)) if old.get(n) != new.get(n))
