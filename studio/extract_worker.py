"""Bounded document extraction worker. Reads one supplied file; never executes it."""
import io
import json
import os
import stat
import sys
import zipfile
from pathlib import PurePosixPath

MAX_FILE=8*1024*1024
MAX_EXPANDED=20*1024*1024
MAX_MEMBERS=64
MAX_TEXT=60000
TEXT_EXTENSIONS={'.md','.txt','.json','.csv','.ts','.js','.py','.cs','.html','.css','.yaml','.yml','.xml'}
SUPPORTED=TEXT_EXTENSIONS|{'.pdf','.docx','.zip'}

class ExtractionError(ValueError):
    def __init__(self,message,documents=None):
        super().__init__(message);self.documents=documents or []


def safe_name(name,allow_hidden=False):
    if not name or len(name)>240 or '\\' in name or ':' in name or any(ord(c)<32 for c in name):raise ExtractionError('文件名或相对路径无效')
    path=PurePosixPath(name)
    if path.is_absolute() or any(p in ('','..','.') for p in name.split('/')):raise ExtractionError('文件路径不能越界')
    if len(path.parts)>12:raise ExtractionError('文件夹层级超过 12 层')
    if not allow_hidden and any(p.startswith('.') or p in ('node_modules','__pycache__') for p in path.parts):raise ExtractionError('请移除隐藏文件、依赖目录与缓存文件')
    return path.as_posix()


def archive_members(z,docx=False):
    members=z.infolist()
    if len(members)>(256 if docx else MAX_MEMBERS):raise ExtractionError('压缩包文件数量超过限制')
    total=0;seen=set();files=[]
    for item in members:
        name=item.filename.rstrip('/') if item.is_dir() else item.filename
        safe_name(name,allow_hidden=True)
        if name in seen:raise ExtractionError('压缩包含重复路径')
        seen.add(name)
        mode=item.external_attr>>16
        if stat.S_IFMT(mode) not in (0,stat.S_IFREG,stat.S_IFDIR):raise ExtractionError('压缩包不允许链接或特殊文件')
        if item.flag_bits&1:raise ExtractionError('不支持加密压缩包')
        total+=item.file_size
        if item.file_size>MAX_FILE or total>MAX_EXPANDED or item.file_size/max(item.compress_size,1)>200:
            raise ExtractionError('压缩包展开大小或压缩比超过限制')
        if not item.is_dir():files.append(item)
    return files


def docx_text(data):
    from defusedxml import ElementTree
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members=archive_members(z,True)
        by_name={item.filename:item for item in members}
        if 'word/document.xml' not in by_name:raise ExtractionError('DOCX 缺少正文文件')
        parts=['word/document.xml',*sorted(n for n in by_name if n.startswith(('word/header','word/footer','word/footnotes','word/endnotes')) and n.endswith('.xml'))]
        texts=[]
        for name in parts:
            root=ElementTree.fromstring(z.read(by_name[name]));paragraphs=[]
            ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            for paragraph in root.iter(ns+'p'):
                line=''.join(node.text or '' if node.tag==ns+'t' else '\t' if node.tag==ns+'tab' else '\n' if node.tag in (ns+'br',ns+'cr') else '' for node in paragraph.iter())
                if line.strip():paragraphs.append(line)
            if paragraphs:texts.append('【'+name+'】\n'+'\n'.join(paragraphs))
        return '\n\n'.join(texts),['按段落顺序提取正文、表格单元格与页眉页脚文字；不保留版式，不识别图片。']


def single(name,data):
    suffix=PurePosixPath(name).suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        try:text=data.decode('utf-8-sig')
        except UnicodeError:raise ExtractionError('文本不是 UTF-8 编码，请转换后上传') from None
        if '\0' in text:raise ExtractionError('文件含二进制内容，不能作为文本读取')
        return text,[]
    if suffix=='.docx':return docx_text(data)
    if suffix=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(data),strict=True)
        if reader.is_encrypted:raise ExtractionError('PDF 已加密，请先解密')
        if len(reader.pages)>80:raise ExtractionError('PDF 超过 80 页，请拆分后上传')
        texts=[];warnings=['PDF 仅提取已有文字，表格与排版可能变化，请核对。']
        chars=0
        for number,page in enumerate(reader.pages,1):
            stream=page.get_contents()
            if stream and len(stream.get_data())>MAX_EXPANDED:raise ExtractionError('PDF 页面展开内容过大')
            text=page.extract_text() or ''
            if not text.strip():warnings.append(f'第 {number} 页没有可提取文字，可能是扫描图片。')
            else:texts.append(f'【第 {number} 页】\n{text}');chars+=len(text)
            if chars>MAX_TEXT:warnings.append('PDF 后续页面未继续提取，请拆分或补充关键内容。');break
        if not texts:raise ExtractionError('PDF 没有可提取文字；扫描件需要先进行 OCR')
        return '\n\n'.join(texts),warnings
    raise ExtractionError('不支持此文件类型')


def extract(name,data):
    safe_name(name)
    if len(data)>MAX_FILE:raise ExtractionError('单个文件不得超过 8 MB')
    if not data:raise ExtractionError('文件为空')
    suffix=PurePosixPath(name).suffix.lower()
    if suffix not in SUPPORTED:raise ExtractionError('支持文本、PDF、DOCX 和 ZIP；不支持 DOC/RAR')
    documents=[];warnings=[];combined=[];chars=0
    def consume(path,raw):
        nonlocal chars
        if chars>=MAX_TEXT:
            documents.append({'path':path,'status':'skipped','error':'已达到提取文字上限'});return
        try:
            text,notes=single(path,raw)
            if not text.strip():raise ExtractionError('未提取到有效文字')
            original=len(text);text=text[:max(0,MAX_TEXT-chars)];chars+=len(text)
            entry={'path':path,'status':'ready','characters':len(text)}
            if len(text)<original:notes.append('文字超过提取上限，当前只保留前段内容。');entry['truncated']=True
            documents.append(entry);warnings.extend(path+'：'+n for n in notes)
            combined.append('【文件：'+path+'】\n'+text)
        except Exception as exc:
            message=str(exc) if isinstance(exc,ExtractionError) else '文档解析失败，文件可能损坏或格式不受支持'
            documents.append({'path':path,'status':'failed','error':message})
    if suffix=='.zip':
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            members=archive_members(z)
            for member in members:
                path=member.filename
                if any(p.startswith('.') or p in ('node_modules','__pycache__','__MACOSX') for p in PurePosixPath(path).parts):
                    documents.append({'path':path,'status':'skipped','error':'隐藏或缓存文件未提取'});continue
                if PurePosixPath(path).suffix.lower() not in SUPPORTED- {'.zip'}:
                    documents.append({'path':path,'status':'skipped','error':'未提取此类型或嵌套压缩包'});continue
                consume(path,z.read(member))
    else:consume(name,data)
    if not combined:
        raise ExtractionError(documents[0].get('error','没有可提取内容') if len(documents)==1 else '未找到可提取的文档内容',documents)
    if any(d['status']!='ready' for d in documents):warnings.append('部分文件未提取成功，请检查逐文件结果。')
    return {'text':'\n\n'.join(combined),'documents':documents,'warnings':warnings}


def main():
    try:
        if os.name=='posix':
            import resource
            resource.setrlimit(resource.RLIMIT_CPU,(12,12))
            if sys.platform!='darwin':resource.setrlimit(resource.RLIMIT_AS,(1024**3,1024**3))
            else:
                # Darwin does not enforce a usable RLIMIT_AS for this Python runtime.
                # Watch peak resident memory instead; this is not a kernel hard limit.
                import threading,time
                def monitor():
                    while True:
                        if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss>512*1024**2:
                            os.write(1,json.dumps({'ok':False,'error':'文档内存占用超过限制，请拆分后上传'},ensure_ascii=False).encode())
                            os._exit(2)
                        time.sleep(.05)
                threading.Thread(target=monitor,daemon=True).start()
        with open(sys.argv[1],'rb') as f:data=f.read(MAX_FILE+1)
        result=extract(sys.argv[2],data)
        print(json.dumps({'ok':True,**result},ensure_ascii=False))
    except BaseException as exc:
        print(json.dumps({'ok':False,'error':str(exc) if isinstance(exc,ExtractionError) else '文档解析失败，格式损坏或超过解析资源限制','documents':getattr(exc,'documents',[])},ensure_ascii=False))
        sys.exit(1)

if __name__=='__main__':main()
