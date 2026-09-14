import { useEffect, useRef, useState } from 'react';
import { StudioIcon as Icon } from './StudioIcon';
import { parameterLabels, type GameParameters } from './WorkbenchPanels';
import { OpenGameSettings } from './OpenGameSettings';

type Check = { id:string;label:string;status:'passed'|'failed'|'unverified';detail:string;checked_at?:string|null;command?:string;url?:string;action?:string };
type Diagnostics = { checked_at:string;checks:Check[];ready:boolean;model_called:boolean };
type VersionOption = { id:string;title:string;created_at:string };
type Comparison = { before:VersionOption;after:VersionOption;identical:boolean;added:number;removed:number;parameter_note:string|null;parameters:{key:string;before:unknown;after:unknown}[]|null;files:{path:string;added:number;removed:number;diff:string}[] };

function Command({value}:{value:string}) {
  const [copied,setCopied]=useState(false);
  return <div className="setup-command"><code>{value}</code><button type="button" onClick={async()=>{try{await navigator.clipboard.writeText(value);setCopied(true);}catch{setCopied(false);}}}>{copied?'已复制':'复制'}</button></div>;
}

export function SetupGuide({onClose,onSettings,onSample}:{onClose:()=>void;onSettings:()=>void;onSample?:()=>void}) {
  const [data,setData]=useState<Diagnostics|null>(null),[error,setError]=useState(''),[revision,setRevision]=useState(0),[loading,setLoading]=useState(true);
  const panel=useRef<HTMLElement>(null);
  const closeAction=useRef(onClose);closeAction.current=onClose;
  useEffect(()=>{
    const previous=document.activeElement as HTMLElement|null;
    const escape=(event:KeyboardEvent)=>{if(event.key==='Escape'&&!event.defaultPrevented){event.preventDefault();closeAction.current();}};
    document.addEventListener('keydown',escape);
    panel.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return ()=>{document.removeEventListener('keydown',escape);previous?.focus();};
  },[]);
  useEffect(()=>{
    const controller=new AbortController();let disposed=false;
    setLoading(true);setError('');
    const timeout=window.setTimeout(()=>controller.abort(),15000);
    fetch('/api/diagnostics',{signal:controller.signal}).then(async r=>{
      if(!r.ok)throw Error('环境检查失败，请确认工作台服务仍在运行。');
      const result=await r.json();if(!disposed)setData(result);
    }).catch(e=>{if(!disposed)setError(e.name==='AbortError'?'检查超时，请确认 Docker 和本地服务状态后重试。':String(e.message));})
      .finally(()=>{window.clearTimeout(timeout);if(!disposed)setLoading(false);});
    return ()=>{disposed=true;controller.abort();window.clearTimeout(timeout);};
  },[revision]);
  const statuses={passed:'就绪',failed:'需要处理',unverified:'待确认'};
  return <div className="modal-backdrop"><section ref={panel} className="modal setup-modal" role="dialog" aria-modal="true" aria-labelledby="setup-title" onKeyDown={e=>{
    if(e.key==='Escape'){e.preventDefault();onClose();}
    if(e.key==='Tab'){
      const nodes=Array.from(panel.current!.querySelectorAll<HTMLElement>('button:not(:disabled), a[href]'));
      const first=nodes[0],last=nodes[nodes.length-1];
      if(e.shiftKey && document.activeElement===first){e.preventDefault();last?.focus();}
      else if(!e.shiftKey && document.activeElement===last){e.preventDefault();first?.focus();}
    }
  }}>
    <button className="modal-close" aria-label="关闭使用引导" onClick={onClose}><Icon name="close"/></button>
    <div className="eyebrow">LET’S GET YOU STARTED</div><h2 id="setup-title">给创意，做好准备。</h2><p>检查本地环境，连接你的模型，再开始第一个作品。环境检查不会调用模型。</p>
    <div className="setup-progress"><span>{loading?'正在检查本地环境…':data?.ready?'环境检查与连接测试均已通过':`${data?.checks.filter(c=>c.status==='passed').length || 0} / 6 项已就绪`}</span><button className="subtle" onClick={()=>setRevision(n=>n+1)} disabled={loading}>重新检查</button></div>
    {error && <p className="run-error" role="alert">{error}</p>}
    <div className="setup-checks" aria-busy={loading}>{data?.checks.map(check=><article key={check.id}><div className="setup-check-heading"><span><Icon name={check.status==='passed'?'check':check.status==='failed'?'close':'history'} size={15}/><strong>{check.label}</strong></span><small className={check.status==='passed'?'check-pass':check.status==='failed'?'check-fail':'check-pending'}>{statuses[check.status]}</small></div><p>{check.detail}</p>{check.checked_at && <small className="check-timestamp">连接测试时间：{new Date(check.checked_at).toLocaleString()}</small>}
      {check.status!=='passed' && check.command && <Command value={check.command}/>}
      {check.status!=='passed' && check.url && <a className="setup-link" href={check.url} target="_blank" rel="noreferrer">查看官方安装说明 <Icon name="arrow" size={12}/></a>}
      {check.action==='settings' && <button className="setup-link" onClick={onSettings}>打开模型设置 <Icon name="arrow" size={12}/></button>}
    </article>)}</div>
    {data && <small className="check-timestamp">环境检查时间：{new Date(data.checked_at).toLocaleTimeString()}。连接测试通过不代表后续生成一定成功。</small>}
    <div className="setup-sample"><Icon name="game" size={24}/><div><strong>也可以先感受一下</strong><p>{onSample?'打开已有可玩作品，先熟悉试玩、参数和版本功能。':'可在本地导入四类经过容器测试的人工模板，不需要模型密钥。'}</p>{onSample?<button className="subtle" onClick={onSample}>打开可玩作品</button>:<Command value=".studio-venv/bin/python scripts/seed_examples.py"/>}</div></div>
    <OpenGameSettings onSettings={onSettings}/>
    <div className="modal-actions"><button className="subtle" onClick={onClose}>进入工作台</button><button className="primary" onClick={onSettings}>配置与测试模型 <Icon name="arrow"/></button></div>
  </section></div>;
}

export function VersionCompare({projectId,versions,activeVersion,onPreview,selection,onSelection}:{selection:{before:string;after:string}|null;onSelection:(pair:{before:string;after:string})=>void;projectId:string;versions:VersionOption[];activeVersion:string|null;onPreview:(id:string)=>void}) {
  const [before,setBefore]=useState(selection?.before || versions[1]?.id || versions[0]?.id || ''),[after,setAfter]=useState(selection?.after || versions[0]?.id || '');
  const [data,setData]=useState<Comparison|null>(null),[loading,setLoading]=useState(false),[error,setError]=useState('');
  useEffect(()=>onSelection({before,after}),[before,after,onSelection]);
  useEffect(()=>{
    if(!before || !after)return;
    const controller=new AbortController();let disposed=false;
    setLoading(true);setError('');setData(null);
    fetch(`/api/projects/${projectId}/compare?${new URLSearchParams({before,after})}`,{signal:controller.signal}).then(async r=>{
      const result=await r.json();if(!r.ok)throw Error(typeof result.detail==='string'?result.detail:'版本对比失败');
      if(!disposed)setData(result);
    }).catch(e=>{if(!disposed && e.name!=='AbortError')setError(e.message);}).finally(()=>{if(!disposed)setLoading(false);});
    return ()=>{disposed=true;controller.abort();};
  },[projectId,before,after]);
  const optionLabel=(v:VersionOption)=>`V${versions.length-versions.findIndex(x=>x.id===v.id)} · ${v.title}${v.id===activeVersion?' · 当前':''}`;
  const fieldLabels:Record<string,string>={...parameterLabels,title:'游戏标题',mode:'游戏模式'};
  if(!versions.length)return <div className="panel-empty"><Icon name="diff" size={32}/><h3>每一次变化，都值得记录。</h3><p>生成第一个可玩版本后，可以在这里查看对比。</p></div>;
  return <div className="comparison-panel"><div className="eyebrow">SEE WHAT CHANGED</div><h3>这一次，哪里不同？</h3><p>选择两个版本，查看参数和源码变化。查看与试玩不会改变当前活动版本。</p>
    <div className="compare-selectors"><label>对比基准<select aria-label="对比基准" value={before} onChange={e=>setBefore(e.target.value)}>{versions.map(v=><option key={v.id} value={v.id}>{optionLabel(v)}</option>)}</select></label><button className="swap-versions" aria-label="交换对比版本" onClick={()=>{setBefore(after);setAfter(before);}}><Icon name="arrow"/></button><label>目标版本<select aria-label="目标版本" value={after} onChange={e=>setAfter(e.target.value)}>{versions.map(v=><option key={v.id} value={v.id}>{optionLabel(v)}</option>)}</select></label></div>
    {versions.length===1 && <p className="inline-note">目前只有一个版本。继续修改并通过验证后，就能对比不同版本。</p>}
    {error && <p className="run-error" role="alert">{error}</p>}
    {loading && <p role="status">正在读取版本差异…</p>}
    {data && data.before.id===before && data.after.id===after && <>
      <div className="compare-stats"><strong>{data.identical?'源文件一致':`${data.files.length} 个文件有变化`}</strong><span className="check-pass">+{data.added} 行</span><span className="check-fail">−{data.removed} 行</span></div>
      <div className="compare-play"><button className="subtle" onClick={()=>onPreview(before)}><Icon name="play" size={14}/> 试玩基准版本</button><button className="subtle" onClick={()=>onPreview(after)}><Icon name="play" size={14}/> 试玩目标版本</button></div>
      <section className="compare-parameters"><h4>参数变化</h4>{data.parameter_note?<p>{data.parameter_note}</p>:data.parameters?.length ? <div className="parameter-diff-table"><div className="parameter-diff-head"><span>参数</span><span>修改前</span><span>修改后</span></div>{data.parameters.map(row=><div key={row.key}><span>{fieldLabels[row.key]||row.key}</span>{[row.before,row.after].map((value,i)=><span key={i}>{typeof value==='string' && /^#[0-9a-f]{6}$/i.test(value) && <i className="color-dot" style={{backgroundColor:value}}/>}{value==null?'不适用':String(value)}</span>)}</div>)}</div>:<p>没有可识别的参数变化。</p>}</section>
      <section className="compare-files"><h4>源码差异</h4>{!data.files.length?<p>这两个版本的可编辑源文件相同。</p>:data.files.map(file=><details key={file.path} open><summary>{file.path}<span>+{file.added} / −{file.removed}</span></summary><pre>{file.diff.split('\n').map((line,i)=><span className={line.startsWith('+')&&!line.startsWith('+++')?'diff-add':line.startsWith('-')&&!line.startsWith('---')?'diff-remove':''} key={i}>{line || ' '}<br/></span>)}</pre></details>)}</section>
      <p className="compare-footnote">参数取自源文件的受限字面量配置；行数反映文本变化，不代表功能增减或质量评价。</p>
    </>}
  </div>;
}
