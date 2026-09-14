import {useEffect,useRef,useState} from 'react';
import {StudioIcon as Icon} from './StudioIcon';
export type Material={upload_id:string;text:string;name:string};
type Upload={id:string;name:string;size:number;status:string;text?:string;warnings:string[];documents?:{path:string;status:string;error?:string}[];error?:string;referenced?:boolean};
async function get(path:string){const r=await fetch('/api/'+path);const body=await r.json();if(!r.ok)throw Error(body.detail||'材料读取失败');return body;}
export function MaterialPicker({value,onChange,disabled,onBusy}:{value:Material[];onChange:(v:Material[])=>void;disabled:boolean;onBusy:(v:boolean)=>void}){
  const fileInput=useRef<HTMLInputElement>(null),folderInput=useRef<HTMLInputElement>(null),mounted=useRef(true),controller=useRef<AbortController|null>(null);
  const [items,setItems]=useState<Upload[]>([]),[editing,setEditing]=useState<string|null>(null),[review,setReview]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[library,setLibrary]=useState<Upload[]|null>(null);
  useEffect(()=>{mounted.current=true;folderInput.current?.setAttribute('webkitdirectory','');return()=>{mounted.current=false;controller.current?.abort();onBusy(false);};},[onBusy]);
  const inspect=(u:Upload)=>{setEditing(u.id);setReview(value.find(v=>v.upload_id===u.id)?.text||u.text?.slice(0,20000)||'');};
  const upload=async(files:FileList|null)=>{
    if(!files?.length)return;setError('');const batch=Array.from(files);
    if(batch.length>50||batch.reduce((n,f)=>n+f.size,0)>32*1024*1024){setError('每批最多 50 个文件、合计 32 MB，请拆分后上传。');return;}
    setBusy(true);onBusy(true);controller.current=new AbortController();const errors:string[]=[];
    try{for(const file of batch){
      const name=file.webkitRelativePath||file.name;
      const r=await fetch('/api/uploads?name='+encodeURIComponent(name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file,signal:controller.current.signal});const body=await r.json();if(!mounted.current)return;
      if(body.id){setItems(prev=>[body,...prev.filter(x=>x.id!==body.id)]);if(r.ok)inspect(body);}
      if(!r.ok)errors.push(name+'：'+(body.error||body.detail||'上传失败'));
    }}catch(e){errors.push(e instanceof Error?e.message:'上传连接失败');}finally{if(!mounted.current)return;setBusy(false);onBusy(false);setError(errors.join('\n'));if(fileInput.current)fileInput.current.value='';if(folderInput.current)folderInput.current.value='';}
  };
  const useMaterial=()=>{const current=items.find(x=>x.id===editing);if(!current||!review.trim())return;
    const selected=[...value.filter(v=>v.upload_id!==current.id),{upload_id:current.id,text:review,name:current.name}];
    if(selected.length>8||selected.reduce((n,m)=>n+m.text.length,0)>40000){setError('每轮最多引用 8 份材料、合计 40000 字，请精简或移除部分材料。');return;}
    onChange(selected);setEditing(null);setError('');
  };
  const openLibrary=async()=>{setError('');try{setLibrary(await get('uploads'));}catch(e){setError(String(e));}};
  const load=async(id:string)=>{try{const u=await get('uploads/'+id);setItems(prev=>[u,...prev.filter(x=>x.id!==id)]);setLibrary(null);inspect(u);}catch(e){setError(String(e));}};
  const discard=async(id:string)=>{try{const r=await fetch('/api/uploads/'+id+'/discard',{method:'POST'});const body=await r.json();if(!r.ok)throw Error(body.detail||'删除失败');setLibrary((await get('uploads')));setItems(prev=>prev.filter(x=>x.id!==id));onChange(value.filter(v=>v.upload_id!==id));}catch(e){setError(String(e));}};
  const item=items.find(x=>x.id===editing);
  return <div className="material-picker"><div className="material-actions"><button type="button" className="subtle" disabled={disabled||busy} onClick={()=>fileInput.current?.click()}><Icon name="folder" size={14}/> 上传材料</button><button type="button" className="subtle" disabled={disabled||busy} onClick={()=>folderInput.current?.click()}>上传文件夹</button><button type="button" className="subtle" disabled={disabled||busy} onClick={()=>void openLibrary()}>材料库</button></div>
    <input hidden type="file" multiple ref={fileInput} aria-label="上传需求材料" accept=".md,.txt,.pdf,.docx,.zip,.json,.csv,.ts,.js,.py,.cs,.html,.css,.yaml,.yml,.xml" onChange={e=>void upload(e.target.files)}/>
    <input hidden type="file" multiple ref={folderInput} aria-label="上传需求文件夹" onChange={e=>void upload(e.target.files)}/>
    <p className="inline-note">支持文本、PDF、DOCX、ZIP；单文件最多 8 MB。先核对提取内容，再选入本轮需求。</p>
    {busy&&<p role="status">正在上传并提取文档，请稍候…</p>}{error&&<p className="run-error message-content" role="alert">{error}</p>}
    {!!value.length&&<div className="material-selected">{value.map(m=><div key={m.upload_id}><span title={m.name}>{m.name} · 已核对</span><button type="button" disabled={disabled||busy} onClick={()=>void load(m.upload_id)}>查看</button><button type="button" disabled={disabled||busy} aria-label={'移除材料 '+m.name} onClick={()=>onChange(value.filter(v=>v.upload_id!==m.upload_id))}><Icon name="close" size={12}/></button></div>)}</div>}
    {items.filter(u=>!value.some(v=>v.upload_id===u.id)).map(u=><div className="material-row" key={u.id}><span>{u.name} · {u.status==='ready'?'待核对':u.error||'解析失败'}</span>{u.status!=='ready'&&!!u.documents?.length&&<details><summary>逐文件错误</summary>{u.documents.map(d=><p key={d.path}>{d.path}：{d.error}</p>)}</details>}{u.status==='ready'&&<button type="button" disabled={disabled||busy} onClick={()=>inspect(u)}>核对内容</button>}</div>)}
    {item&&<div className="material-review"><strong>{item.name}</strong>{item.warnings?.map((w,i)=><p className="inline-note" key={i}>{w}</p>)}{(item.text?.length||0)>20000&&<p className="inline-note">提取内容超过 20000 字，编辑框先保留前段。可展开全文选取关键内容，每份引用限 20000 字。</p>}
      <details><summary>逐文件提取结果与原提取全文</summary>{item.documents?.map(d=><p key={d.path}>{d.path}：{d.status==='ready'?'已提取':d.error}</p>)}<pre>{item.text}</pre></details>
      <label>核对后的需求材料<textarea aria-label="核对后的需求材料" rows={6} maxLength={20000} value={review} disabled={disabled||busy} onChange={e=>setReview(e.target.value)}/></label><div className="material-actions"><button type="button" className="subtle" onClick={()=>setEditing(null)}>收起</button><button type="button" className="primary" disabled={disabled||busy||!review.trim()} onClick={useMaterial}>核对并用于本轮需求</button></div>
    </div>}
    {library&&<div className="material-library"><strong>已上传材料</strong><button type="button" className="subtle" onClick={()=>setLibrary(null)}>收起材料库</button>{!library.length&&<p>暂无材料。</p>}{library.map(u=><div className="material-row" key={u.id}><span>{u.name}<small>{u.status==='ready'?'可核对引用':u.error||'解析中'}</small></span>{u.status==='ready'&&<button type="button" onClick={()=>void load(u.id)}>查看并选用</button>}{!u.referenced&&u.status!=='processing'&&<button type="button" onClick={()=>void discard(u.id)}>删除未引用材料</button>}</div>)}</div>}
  </div>;
}
export function RunMaterials({runId}:{runId:string}){
  const [materials,setMaterials]=useState<any[]>([]),[error,setError]=useState('');
  useEffect(()=>{let disposed=false;get('runs/'+runId+'/materials').then(v=>{if(!disposed)setMaterials(v);}).catch(e=>{if(!disposed)setError(e.message);});return()=>{disposed=true;};},[runId]);
  if(error)return <p className="run-error">材料记录读取失败：{error}</p>;
  if(!materials.length)return null;
  return <details className="run-materials"><summary>本轮需求材料 · {materials.length} 份</summary>{materials.map(m=><article key={m.upload_id}><strong>{m.name}</strong><small>原文件 {m.original_sha256.slice(0,12)} · 核对稿 {m.reviewed_sha256.slice(0,12)}</small><pre>{m.reviewed_text}</pre></article>)}</details>;
}
