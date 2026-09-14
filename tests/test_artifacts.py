import json
from fastapi.testclient import TestClient
import pytest
from studio.app import create_preview_app, create_app
from studio.artifacts import capture_artifacts, artifact_file, binding_errors, BUILD_MANIFEST, read_artifacts
from studio.db import Store, uid, now
from studio.project_files import MANIFEST, ProjectManifest


def built_project(root):
    root.mkdir(parents=True)
    (root/'src').mkdir();(root/'src/config.ts').write_text('export const mode="tower_defense";')
    (root/MANIFEST).write_text(ProjectManifest(template_id='phaser-tower_defense',template_version='1').model_dump_json())
    (root/'dist/assets').mkdir(parents=True)
    (root/'dist/index.html').write_text('<script type="module" src="./assets/main.js"></script>')
    (root/'dist/assets/main.js').write_text('fetch("./assets/pack.json");')
    (root/'dist/assets/pack.json').write_text('{"assets":[]}')
    (root/'dist/assets/tower.png').write_bytes(b'fixture image')
    (root/'dist/assets/main.js.map').write_text('not public')
    return capture_artifacts(root)


def test_build_manifest_binds_source_assets_and_bundles(tmp_path):
    root=tmp_path/'project';evidence=built_project(root)
    assert binding_errors(root,evidence)==[]
    assert artifact_file(root,'assets/pack.json')[1]=='application/json'
    with pytest.raises(ValueError):artifact_file(root,'assets/main.js.map')
    (root/'src/config.ts').write_text('changed after testing')
    assert binding_errors(root,evidence)==['源码或素材变化，必须重新验证']


@pytest.mark.parametrize('tamper',['bundle','manifest','symlink'])
def test_tampered_artifacts_rejected(tmp_path,tamper):
    root=tmp_path/'project';evidence=built_project(root)
    if tamper=='bundle':(root/'dist/assets/main.js').write_text('changed')
    elif tamper=='manifest':
        data=json.loads((root/BUILD_MANIFEST).read_text());data['files']['secret.txt']={}
        (root/BUILD_MANIFEST).write_text(json.dumps(data))
    else:
        (root/'dist/assets/main.js').unlink();(root/'dist/assets/main.js').symlink_to('/etc/hosts')
    assert binding_errors(root,evidence)


def test_preview_only_serves_verified_build_with_version_scoped_csp(tmp_path):
    vid=uid();root=tmp_path/'versions'/vid;built_project(root)
    with TestClient(create_preview_app(tmp_path),base_url='http://127.0.0.1:8081') as client:
        for name,mime in [('index.html','text/html'),('assets/main.js','text/javascript'),('assets/pack.json','application/json'),('assets/tower.png','image/png')]:
            response=client.get(f'/v/{vid}/{name}')
            assert response.status_code==200
            assert response.headers['content-type'].startswith(mime)
            assert response.headers['access-control-allow-origin']=='*'
            policy=response.headers['content-security-policy']
            assert f'connect-src http://127.0.0.1:8081/v/{vid}/;' in policy
            assert "sandbox allow-scripts;" in policy and 'allow-same-origin' not in policy
            assert f'img-src http://127.0.0.1:8081/v/{vid}/ data:;' in policy
        for name in ['src/config.ts',MANIFEST,BUILD_MANIFEST,'assets/main.js.map','assets/no.png']:
            assert client.get(f'/v/{vid}/{name}').status_code==404
        (root/'dist/assets/main.js').write_text('changed')
        assert client.get(f'/v/{vid}/assets/main.js').status_code==404


def test_inventory_and_on_demand_text_api(tmp_path):
    store=Store(tmp_path);vid=uid();root=tmp_path/'versions'/vid;evidence=built_project(root)
    store.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)',(vid,'project','run','game',str(root),json.dumps(evidence),'',now()))
    store.con.close()
    with TestClient(create_app(tmp_path)) as client:
        rows=client.get(f'/api/versions/{vid}/files').json()
        assert rows['project']['template_id']=='phaser-tower_defense'
        assert any(f['path']=='src/config.ts' and f['editable'] for f in rows['files'])
        assert client.get(f'/api/versions/{vid}/file',params={'path':'src/config.ts'}).json()['content'].startswith('export')
        assert client.get(f'/api/versions/{vid}/file',params={'path':'../studio.sqlite3'}).status_code==404
        assert client.get('/api/templates').json()[-1]['status']=='planned'


@pytest.mark.parametrize('tamper', [None,'source','bundle'])
def test_export_rechecks_binding_and_includes_only_manifest_files(tmp_path,tamper):
    import io, zipfile
    store=Store(tmp_path);vid=uid();root=tmp_path/'versions'/vid;evidence=built_project(root)
    store.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?,?)',(vid,'project','run','game',str(root),json.dumps(evidence),'',now()))
    store.con.close()
    (root/'unrelated.txt').write_text('not a project artifact')
    if tamper=='source':(root/'src/config.ts').write_text('changed')
    if tamper=='bundle':(root/'dist/assets/main.js').write_text('changed')
    with TestClient(create_app(tmp_path)) as client:
        response=client.get(f'/api/versions/{vid}/export')
        assert response.status_code==(409 if tamper else 200)
        if not tamper:
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                assert 'dist/assets/tower.png' in archive.namelist()
                assert BUILD_MANIFEST in archive.namelist()
                assert 'unrelated.txt' not in archive.namelist()
                assert 'dist/assets/main.js.map' not in archive.namelist()
                assert '--directory dist' in archive.read('RUN_GAME.md').decode()
