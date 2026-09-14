import asyncio
import io
import json
import stat
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from studio.app import create_app
from studio.db import Store
from studio.extract_worker import extract,ExtractionError,MAX_FILE
from studio.uploads import Extractor,material_references,run_materials
from studio.models import MaterialReference
from test_studio import FakeRunner
from team_fixture import TeamGateway
from test_messages import wait_run


def archive(files):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
        for name,content in files:z.writestr(name,content)
    return b.getvalue()


def word():
    return archive([('[Content_Types].xml','<Types/>'),('_rels/.rels','<Relationships/>'),
        ('word/document.xml','''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>三消需求</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>步数 20</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>目标 1200</w:t></w:r></w:p></w:tc></w:tr></w:tbl><w:p><w:r><w:t>允许连锁</w:t></w:r></w:p></w:body></w:document>'''),
        ('word/header1.xml','''<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>页眉需求</w:t></w:r></w:p></w:hdr>''')])


def pdf(blank=False,encrypted=False):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
    w=PdfWriter();p=w.add_blank_page(300,300)
    if not blank:
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        p[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):w._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 100 Td (Match3 20 moves target 1200) Tj ET');p[NameObject('/Contents')]=w._add_object(stream)
    if encrypted:w.encrypt('password')
    b=io.BytesIO();w.write(b);return b.getvalue()


def test_supported_formats_order_and_partial_zip():
    result=extract('需求/策划.docx',word());text=result['text']
    assert text.index('三消需求')<text.index('步数 20')<text.index('目标 1200')<text.index('允许连锁')<text.index('页眉需求')
    assert 'Match3 20 moves' in extract('spec.pdf',pdf())['text']
    result=extract('game.zip',archive([('docs/玩法.md','三消玩法：20步'),('docs/spec.docx',word()),('bad.pdf',b'broken'),('picture.png',b'png'),('.env',b'SECRET')]))
    assert [d['status'] for d in result['documents']]==['ready','ready','failed','skipped','skipped']
    assert result['warnings'] and 'SECRET' not in result['text']


@pytest.mark.parametrize('name,data',[('scan.pdf',pdf(True)),('locked.pdf',pdf(encrypted=True)),('bad.docx',b'wrong'),('bad.md',b'\xff'),('binary.txt',b'a\0b'),('old.doc',b'old'),('../escape.md',b'escape')])
def test_failures_are_not_extracted_placeholders(name,data):
    with pytest.raises((ExtractionError,zipfile.BadZipFile)):extract(name,data)


def test_archive_traversal_links_duplicates_limits_and_entities():
    for files in [('../out.md','bad'),('/absolute.md','bad'),('a\\b.md','bad')]:
        with pytest.raises(ExtractionError):extract('bad.zip',archive([files]))
    with pytest.raises(ExtractionError):extract('count.zip',archive([(f'{i}.txt','x') for i in range(65)]))
    with pytest.raises(ExtractionError):extract('ratio.zip',archive([('bomb.txt','a'*100000)]))
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        i=zipfile.ZipInfo('link.md');i.create_system=3;i.external_attr=(stat.S_IFLNK|0o777)<<16;z.writestr(i,'/etc/passwd')
    with pytest.raises(ExtractionError):extract('link.zip',b.getvalue())
    entity=archive([('word/document.xml','<!DOCTYPE x [<!ENTITY x SYSTEM "file:///etc/passwd">]><x>&x;</x>')])
    with pytest.raises(ExtractionError):extract('entity.docx',entity)
    with pytest.raises(ExtractionError):extract('large.txt',b'x'*(MAX_FILE+1))
    cut=extract('long.txt',b'x'*61000);assert cut['documents'][0]['truncated'] and cut['warnings']


@pytest.mark.asyncio
async def test_real_worker_pdf_docx_and_environment(tmp_path,monkeypatch):
    parser=Extractor()
    for name,data in [('spec.pdf',pdf()),('spec.docx',word())]:
        path=tmp_path/name;path.write_bytes(data);result=await parser.parse(path,name)
        assert result['ok'] and result['text']
    sentinel=tmp_path/'env.py';sentinel.write_text("import json,os;print(json.dumps({'ok':True,'text':'present' if 'STUDIO_API_KEY' in os.environ else 'absent'}))")
    monkeypatch.setenv('STUDIO_API_KEY','PRIVATE-KEY');parser.worker=sentinel
    assert (await parser.parse(tmp_path/'spec.pdf','spec.pdf'))['text']=='absent'
    assert not parser.processes


@pytest.mark.asyncio
async def test_worker_timeout_and_cancel_join_process(tmp_path):
    script=tmp_path/'wait.py';script.write_text('import time;time.sleep(30)')
    parser=Extractor();parser.worker=script;parser.timeout=.05
    with pytest.raises(ValueError,match='20 秒'):await parser.parse(script,'wait.txt')
    assert not parser.processes
    parser.timeout=20;task=asyncio.create_task(parser.parse(script,'wait.txt'))
    while not parser.processes:await asyncio.sleep(.001)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert not parser.processes


def test_upload_review_binding_and_export(tmp_path):
    g=TeamGateway();app=create_app(tmp_path,g,FakeRunner())
    with TestClient(app) as c:
        uploaded=c.post('/api/uploads',params={'name':'三消/需求.md'},content='原始材料：接金币测试协议'.encode()).json()
        assert uploaded['status']=='ready' and uploaded['documents'][0]['path']=='三消/需求.md'
        assert stat.S_IMODE((tmp_path/'uploads'/(uploaded['id']+'.bin')).stat().st_mode)==0o600
        assert not g.trace
        ids=c.post('/api/projects',json={'text':'根据材料设计小游戏','materials':[{'upload_id':uploaded['id'],'text':'核对稿：明确开始、移动和重开。'}]}).json()
        pid,rid=ids['project_id'],ids['run_id'];wait_run(c,pid,lambda r:r['status']=='waiting_confirmation')
        assert all('核对稿：明确开始' in prompt for _,_,prompt in g.trace)
        assert c.post('/api/uploads/'+uploaded['id']+'/discard').status_code==409
        refs=c.get('/api/runs/'+rid+'/materials').json();assert refs[0]['reviewed_text'].startswith('核对稿')
        assert refs[0]['original_sha256']==uploaded['sha256']
        assert c.post('/api/runs/'+rid+'/decision',json={'approve':True}).status_code==200
        done=wait_run(c,pid,lambda r:r['status'] in ('succeeded','failed'));assert done['status']=='succeeded'
        assert all('核对稿：明确开始' in prompt for _,_,prompt in g.trace)
        vid=c.get('/api/projects/'+pid).json()['active_version']
        with zipfile.ZipFile(io.BytesIO(c.get('/api/versions/'+vid+'/export').content)) as z:
            assert json.loads(z.read('requirements.json'))[rid]==refs
        failed=c.post('/api/uploads',params={'name':'bad.pdf'},content=b'wrong');assert failed.status_code==422 and failed.json()['status']=='failed'
        assert c.post('/api/uploads/'+failed.json()['id']+'/discard').json()['deleted']
        assert c.get('/api/uploads/'+failed.json()['id']).status_code==404


def test_api_rejects_unready_unknown_duplicate_and_oversized_materials(tmp_path):
    with TestClient(create_app(tmp_path,TeamGateway(),FakeRunner())) as c:
        assert c.post('/api/uploads',params={'name':'../unsafe.md'},content=b'bad').status_code==400
        assert c.post('/api/uploads',params={'name':'safe.md'},content=b'hello',headers={'Origin':'null'}).status_code==403
        assert c.post('/api/uploads',params={'name':'big.md'},content=b'x'*(MAX_FILE+1)).status_code==413
        assert c.post('/api/projects',json={'text':'未知材料','materials':[{'upload_id':'a'*32,'text':'test'}]}).status_code==400
        assert c.get('/api/projects').json()==[]
        ready=c.post('/api/uploads',params={'name':'a.md'},content=b'hello').json()
        ref={'upload_id':ready['id'],'text':'hello'}
        assert c.post('/api/projects',json={'text':'重复材料','materials':[ref,ref]}).status_code==400
        assert c.post('/api/projects',json={'text':'空白材料','materials':[{**ref,'text':' '}]}).status_code==400
        assert c.post('/api/uploads/'+ready['id']+'/discard').json()['deleted']


def test_failed_metadata_write_removes_untracked_original(tmp_path,monkeypatch):
    with TestClient(create_app(tmp_path,TeamGateway(),FakeRunner())) as c:
        execute=Store.execute
        def fail_insert(self,sql,*args,**kwargs):
            if sql.startswith('INSERT INTO uploads'):raise OSError('private database location')
            return execute(self,sql,*args,**kwargs)
        monkeypatch.setattr(Store,'execute',fail_insert)
        response=c.post('/api/uploads',params={'name':'spec.md'},content=b'Match3')
        assert response.status_code==500 and 'private database' not in response.text
        assert c.get('/api/uploads').json()==[]
        assert not list((tmp_path/'uploads').iterdir())
