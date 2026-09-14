"""Upload review and immutable run material references; source files never become code."""
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from fastapi import HTTPException,Request
from fastapi.responses import JSONResponse
from .db import now,uid
from .extract_worker import MAX_FILE,SUPPORTED,safe_name


def sha(text):return hashlib.sha256(text.encode()).hexdigest()

class ParseFailure(ValueError):
    def __init__(self,result):super().__init__(result.get('error','文档解析失败'));self.result=result


class Extractor:
    def __init__(self):self.limit=asyncio.Semaphore(2);self.processes=set();self.timeout=20;self.worker=Path(__file__).with_name('extract_worker.py')
    async def parse(self,path,name):
        async with self.limit:
            proc=await asyncio.create_subprocess_exec(sys.executable,str(self.worker),str(path),name,
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
                env={'PATH':os.defpath,'LANG':'C.UTF-8','PYTHONIOENCODING':'utf-8'})
            self.processes.add(proc)
            try:
                output,_=await asyncio.wait_for(proc.communicate(),self.timeout)
                if len(output)>1024*1024:raise ValueError('解析结果超过限制')
                try:result=json.loads(output)
                except (ValueError,UnicodeError):raise ValueError('解析进程失败或超过资源限制，请拆分文件后重试') from None
                if proc.returncode or not result.get('ok'):raise ParseFailure(result)
                return result
            except asyncio.TimeoutError:raise ValueError('文档解析超过 20 秒，请拆分后重试') from None
            finally:
                if proc.returncode is None:proc.kill()
                await proc.wait();self.processes.discard(proc)
    async def close(self):
        processes=list(self.processes)
        for proc in processes:
            if proc.returncode is None:proc.kill()
        await asyncio.gather(*(p.wait() for p in processes),return_exceptions=True)


def material_references(store,refs):
    if len({r.upload_id for r in refs})!=len(refs):raise HTTPException(400,'同一材料不能重复引用')
    if sum(len(r.text) for r in refs)>40000:raise HTTPException(400,'本轮核对后的材料总计不能超过 40000 字，请精简关键内容')
    result=[]
    for ref in refs:
        row=store.one('SELECT * FROM uploads WHERE id=?',(ref.upload_id,))
        if not row or row['status']!='ready':raise HTTPException(400,'材料不存在或未解析成功，请重新选择')
        if not ref.text.strip():raise HTTPException(400,'核对后的材料不能为空')
        result.append({'upload_id':ref.upload_id,'name':row['name'],'original_sha256':row['sha256'],
            'extracted_sha256':sha(row['text']),'reviewed_text':ref.text,'reviewed_sha256':sha(ref.text),
            'documents':json.loads(row['documents']),'warnings':json.loads(row['warnings'])})
    return result


def run_materials(store,rid):
    return [json.loads(r['payload']) for r in store.query('SELECT payload FROM run_materials WHERE run_id=? ORDER BY rowid',(rid,))]


def register(app,store,extractor,run):
    folder=store.root/'uploads';folder.mkdir(exist_ok=True)
    def read(upload_id):
        row=store.one('SELECT * FROM uploads WHERE id=?',(upload_id,))
        if not row:raise HTTPException(404,'上传材料不存在')
        for key in ('documents','warnings'):row[key]=json.loads(row[key] or '[]')
        row['referenced']=bool(store.one('SELECT run_id FROM run_materials WHERE upload_id=? LIMIT 1',(upload_id,)))
        return row

    @app.post('/api/uploads',status_code=201)
    async def upload(request:Request,name:str):
        try:safe_name(name)
        except ValueError as exc:raise HTTPException(400,str(exc)) from None
        if Path(name).suffix.lower() not in SUPPORTED:raise HTTPException(400,'支持文本、PDF、DOCX 和 ZIP；不支持 DOC/RAR')
        data=bytearray()
        async for chunk in request.stream():
            if len(data)+len(chunk)>MAX_FILE:raise HTTPException(413,'单个文件不得超过 8 MB')
            data.extend(chunk)
        if not data:raise HTTPException(400,'上传文件为空')
        stored=store.one("SELECT COALESCE(SUM(size),0) AS total FROM uploads")['total']
        if stored+len(data)>200*1024*1024:raise HTTPException(413,'本地材料已达 200 MB，请删除未引用材料后重试')
        upload_id=uid();path=folder/(upload_id+'.bin')
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        try:
            with os.fdopen(fd,'wb') as f:f.write(data)
            store.execute('INSERT INTO uploads(id,name,size,sha256,status,text,documents,warnings,error,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                (upload_id,name,len(data),hashlib.sha256(data).hexdigest(),'processing',None,None,None,None,now()))
        except Exception:
            path.unlink(missing_ok=True)
            raise HTTPException(500,'材料保存失败，请检查本地存储后重试') from None
        del data
        try:
            result=await extractor.parse(path,name)
            store.execute("UPDATE uploads SET status='ready',text=?,documents=?,warnings=? WHERE id=?",(result['text'],json.dumps(result['documents'],ensure_ascii=False),json.dumps(result['warnings'],ensure_ascii=False),upload_id))
        except asyncio.CancelledError:
            store.execute("UPDATE uploads SET status='failed',error='解析已中断，请重新上传' WHERE id=?",(upload_id,));raise
        except Exception as exc:
            store.execute("UPDATE uploads SET status='failed',error=?,documents=? WHERE id=?",(str(exc) if isinstance(exc,ValueError) else '文档解析工具失败，请重试',json.dumps(getattr(exc,'result',{}).get('documents',[]),ensure_ascii=False),upload_id))
            return JSONResponse(read(upload_id),status_code=422)
        return read(upload_id)

    @app.get('/api/uploads')
    async def uploads():
        return [{k:v for k,v in read(r['id']).items() if k not in ('text','documents')} for r in store.query('SELECT id FROM uploads ORDER BY created_at DESC LIMIT 100')]

    @app.get('/api/uploads/{upload_id}')
    async def get_upload(upload_id:str):return read(upload_id)

    @app.post('/api/uploads/{upload_id}/discard')
    async def discard(upload_id:str):
        row=read(upload_id)
        if row['referenced'] or row['status']=='processing':raise HTTPException(409,'任务已引用或正在解析的材料不能删除')
        (folder/(upload_id+'.bin')).unlink(missing_ok=True)
        store.execute('DELETE FROM uploads WHERE id=?',(upload_id,))
        return {'deleted':True}

    @app.get('/api/runs/{rid}/materials')
    async def materials(rid:str):
        run(rid);return run_materials(store,rid)
