import json
import os
from pathlib import Path
import pytest

from studio.file_transactions import atomic_edit, journal_path, recover_edits
from studio.files import apply_changes, copy_source, diff_sources, source_files, TEMPLATE
from studio.models import Changes
from studio.project_files import MANIFEST, ProjectChanges, ProjectManifest, apply_project_changes, inventory, source_digest
from studio.template_registry import public_templates


def project(root):
    root.mkdir()
    (root/'src/scenes').mkdir(parents=True)
    (root/'src/config.ts').write_text('export const damage = 10;')
    (root/'src/scenes/GameScene.ts').write_text('export class GameScene {}')
    (root/'src/scenes/Preloader.ts').write_text('protected loader')
    (root/'package.json').write_text('{"scripts":{"build":"trusted"}}')
    (root/MANIFEST).write_text(ProjectManifest(template_id='phaser-tower_defense',template_version='1').model_dump_json())
    return root


def changes(root, files):
    return ProjectChanges(summary='change',base_digest=source_digest(root),files=files)


def test_multifile_create_update_delete_and_deleted_file_diff(tmp_path):
    root=project(tmp_path/'candidate');before=source_files(root)
    apply_project_changes(root, changes(root,[
        {'operation':'update','path':'src/config.ts','content':'export const damage=20;'},
        {'operation':'create','path':'src/entities/IceTower.ts','content':'export class IceTower {}'},
        {'operation':'delete','path':'src/scenes/GameScene.ts'},
    ]))
    after=source_files(root)
    assert after['src/entities/IceTower.ts']=='export class IceTower {}'
    assert 'src/scenes/GameScene.ts' not in after
    assert 'before/src/scenes/GameScene.ts' in diff_sources(before,after)
    assert after['src/scenes/Preloader.ts']==before['src/scenes/Preloader.ts']


def test_invalid_later_edit_never_changes_original(tmp_path):
    root=project(tmp_path/'candidate');before=source_digest(root)
    with pytest.raises(ValueError, match='业务范围'):
        apply_project_changes(root, changes(root,[
            {'operation':'update','path':'src/config.ts','content':'changed'},
            {'operation':'update','path':'src/scenes/Preloader.ts','content':'unsafe'},
        ]))
    assert source_digest(root)==before
    assert not list(tmp_path.glob('*.stage-*'))


def test_concurrent_stale_snapshot_is_rejected(tmp_path):
    root=project(tmp_path/'candidate')
    request=changes(root,[{'operation':'update','path':'src/config.ts','content':'new'}])
    (root/'src/config.ts').write_text('external change')
    with pytest.raises(ValueError, match='项目已变化'):
        apply_project_changes(root,request)
    assert (root/'src/config.ts').read_text()=='external change'


@pytest.mark.parametrize('path',['../escape.ts','/root.ts','src/../x.ts','src//x.ts','src/.env','src\\x.ts'])
def test_noncanonical_paths_rejected(path):
    with pytest.raises(ValueError):
        ProjectChanges(summary='unsafe',base_digest='0'*64,files=[{'operation':'create','path':path,'content':'x'}])


def test_symlinks_blocked_and_legacy_batch_validated_before_writes(tmp_path):
    root=tmp_path/'candidate';copy_source(TEMPLATE,root)
    old=(root/'style.css').read_text()
    with pytest.raises(ValueError):
        apply_changes(root,Changes(summary='duplicate',files=[{'path':'style.css','content':'new'},{'path':'style.css','content':'bad'}]))
    assert (root/'style.css').read_text()==old
    (root/'src/link').symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError,match='符号链接'):
        apply_changes(root,Changes(summary='link',files=[{'path':'style.css','content':'new'}]))
    assert (root/'style.css').read_text()==old


def test_directory_commit_failure_restores_original(tmp_path,monkeypatch):
    root=project(tmp_path/'candidate');before=source_digest(root)
    replace=os.replace
    def failing(src,dst):
        if '.stage-' in Path(src).name:
            raise OSError('simulated rename failure')
        return replace(src,dst)
    monkeypatch.setattr(os,'replace',failing)
    with pytest.raises(OSError):
        apply_project_changes(root,changes(root,[{'operation':'update','path':'src/config.ts','content':'new'}]))
    assert source_digest(root)==before
    assert not journal_path(root).exists()


@pytest.mark.parametrize('committed',[False,True])
def test_recovery_of_interrupted_directory_commit(tmp_path,committed):
    root=project(tmp_path/'candidate');backup=tmp_path/'.candidate.previous';stage=tmp_path/'.candidate.stage-test'
    stage.mkdir();(stage/'new.txt').write_text('complete new snapshot')
    journal_path(root).write_text(json.dumps({'stage':stage.name}))
    os.replace(root,backup)
    if committed:os.replace(stage,root)
    recover_edits(root)
    assert (root/'new.txt').exists() is committed
    assert (root/MANIFEST).exists() is (not committed)
    assert not backup.exists() and not stage.exists() and not journal_path(root).exists()


def test_source_copy_preserves_assets_and_excludes_build_outputs(tmp_path):
    import hashlib
    root=project(tmp_path/'source');assets=root/'public/assets';assets.mkdir(parents=True)
    image=b'fixture bytes';(assets/'tower.png').write_bytes(image)
    data=ProjectManifest(template_id='phaser-tower_defense',template_version='1',assets=[
        {'id':'tower','path':'public/assets/tower.png','source':'builtin','sha256':hashlib.sha256(image).hexdigest()}])
    (root/MANIFEST).write_text(data.model_dump_json())
    (root/'dist').mkdir();(root/'dist/index.html').write_text('stale build')
    copy_source(root,tmp_path/'copy')
    assert source_digest(root)==source_digest(tmp_path/'copy')
    assert not (tmp_path/'copy/dist').exists()
    (assets/'tower.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='素材文件'):
        inventory(root)


def test_registry_separates_future_support_from_available_modes():
    rows=public_templates()
    assert len([r for r in rows if r['status']=='available'])==4
    assert len([r for r in rows if r['status']=='planned'])==5
    with pytest.raises(ValueError,match='模板版本'):
        ProjectManifest(template_id='phaser-tower_defense',template_version='999')


@pytest.mark.parametrize('payload', ['[]', 'null', '"invalid"'])
def test_corrupt_recovery_record_does_not_crash_service_startup(tmp_path,payload):
    from studio.db import Store, uid
    store=Store(tmp_path);rid=uid();root=tmp_path/'candidates'/rid
    root.parent.mkdir(parents=True,exist_ok=True)
    journal_path(root).write_text(payload)
    store.recover()
    assert journal_path(root).read_text()==payload
    row=store.one("SELECT * FROM events WHERE run_id=? AND kind='file_recovery_failed'",(rid,))
    assert row is not None
    store.con.close()


def test_source_copy_rejects_overlapping_directories(tmp_path):
    root=project(tmp_path/'source')
    for dest in (root,root/'nested',tmp_path):
        with pytest.raises(ValueError,match='独立'):
            copy_source(root,dest)
    assert (root/MANIFEST).is_file()
