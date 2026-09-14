import { useEffect, useRef, useState, type ReactNode, type PointerEvent } from 'react';
import { StudioIcon as Icon, type StudioIconName } from './StudioIcon';

export type Surface = 'home' | 'canvas' | 'projects' | 'materials';
type ProjectCard = {id:string; title:string; active_version:string|null; last_status?:string; created_at:string};
const actions: {id:string; icon:StudioIconName; title:string; description:string; color:string}[] = [
  {id:'plan',icon:'game',title:'玩法方案',description:'从创意到清晰玩法',color:'green'},
  {id:'materials',icon:'upload',title:'上传材料',description:'文档、需求与参考',color:'blue'},
  {id:'visual',icon:'image',title:'视觉方案',description:'定义配色与界面风格',color:'purple'},
  {id:'research',icon:'plan',title:'从示例开始',description:'寻找下一份创作灵感',color:'orange'},
];
export function CreationActions({onAction,home=false}:{onAction:(id:string)=>void;home?:boolean}) {
  return <div className={'creation-actions '+(home?'home-actions':'')}>{actions.map(a=><button key={a.id} onClick={()=>onAction(a.id)}><span className={'action-symbol '+a.color}><Icon name={a.icon} size={23}/></span><span><strong>{a.title}</strong><small>{a.description}</small></span></button>)}</div>;
}
export function HomeScreen({onOpenNav,projects,onOpen,onNew,onAction,onAll,composer,examples,onExample}:{onOpenNav:()=>void;projects:ProjectCard[];onOpen:(id:string)=>void;onNew:()=>void;onAction:(id:string)=>void;onAll:()=>void;composer:ReactNode;examples:{label:string;text:string}[];onExample:(text:string)=>void}) {
  return <section className="creation-home">
    <div className="creation-home-heading"><button className="mobile-nav-toggle" aria-label="打开导航" onClick={onOpenNav}><Icon name="menu"/></button><h1>让游戏想法，在画布上展开。</h1></div>
    <div className="garden-banner"><img src="/assets/garden-banner.png" alt="阳光下的花园、石拱门与熟睡的小猫"/><div className="garden-caption">让每一个<br/>游戏想法<br/>都开花<span>LET YOUR IDEAS BLOOM</span></div><span className="banner-note">一份灵感，无限可能</span></div>
    <div className="creation-grid"><button className="new-canvas-card" onClick={onNew}><span><Icon name="plus" size={34}/></span><strong>新建游戏画布</strong><small>从空白开始，创造一点不同</small></button><CreationActions onAction={onAction} home/></div>
    <div className="recent-heading"><h2>最近项目 <span>{projects.length?String(projects.length).padStart(2,'0'):''}</span></h2><button onClick={onAll}>查看全部 <Icon name="chevron" size={13}/></button></div>
    <div className="recent-projects">{projects.slice(0,4).map((p,i)=><button className="recent-project" key={p.id} onClick={()=>onOpen(p.id)}><span className={'project-cover cover-'+i}><Icon name={p.active_version?'game':'folder'} size={29}/></span><span><strong>{p.title}</strong><small>{p.active_version?'可试玩 · 继续创作':p.last_status==='failed'?'上次执行失败 · 查看详情':p.last_status==='waiting_confirmation'?'等待确认玩法':'打开项目'}</small></span><Icon name="chevron" size={15}/></button>)}{!projects.length&&<button className="recent-empty" onClick={onNew}><Icon name="folder" size={24}/><span>第一个作品，从这里开始。<small>创建画布后，你的项目会保存在这里。</small></span><Icon name="arrow"/></button>}</div>
    {composer}
    <div className="quick-start"><span>快速开始：</span>{examples.map((e,i)=><button key={e.label} onClick={()=>onExample(e.text)}>{['三消','接物','躲避','点击'][i]}</button>)}</div>
    <div className="home-footer">八个专业角色协作 <span/> 确认玩法后生成 <span/> 验证通过再试玩</div>
  </section>;
}
export function BlankCanvas({onAction,composer,composing,onCompose,onClose,onHelp,onMaterials}:{onAction:(id:string)=>void;composer:ReactNode;composing:boolean;onCompose:()=>void;onClose:()=>void;onHelp:()=>void;onMaterials:()=>void}) {
  return <section className="blank-canvas dot-canvas" onDoubleClick={e=>{if(e.target===e.currentTarget)onCompose();}} aria-label="空白项目画布">
    <div className="blank-onboarding"><Icon name="cursor" size={32}/><h1>双击画布，添加创作内容</h1><p>先确认玩法，再生成可试玩版本</p><CreationActions onAction={onAction}/><button className="blank-text-entry" onClick={onCompose}>或直接描述你的游戏想法 <Icon name="arrow" size={14}/></button></div>
    {composing&&<div className="blank-composer"><div className="floating-heading"><strong>从一个想法开始</strong><button aria-label="收起需求输入" onClick={onClose}><Icon name="close"/></button></div>{composer}</div>}
    <div className="canvas-bottom"><button className="canvas-small-button" onClick={onMaterials}><Icon name="image"/> 材料库</button><div className="canvas-dock"><button className="dark-tool" aria-label="添加创作内容" onClick={onCompose}><Icon name="plus" size={23}/></button><span className="selected-tool" title="选择工具"><Icon name="cursor" size={21}/></span><span className="dock-divider"/><button aria-label="画布使用帮助" onClick={onHelp}><Icon name="help" size={21}/></button></div><span className="canvas-hint">你的下一个小世界</span></div>
  </section>;
}

type View = {zoom:number;pan:{x:number;y:number};reference:{x:number;y:number};game:{x:number;y:number}};
const initialView=():View=>({zoom:.85,pan:{x:0,y:0},reference:{x:66,y:106},game:{x:570,y:42}});
function readView(key:string):View {
  try { const v=JSON.parse(localStorage.getItem('ludraft.canvas.'+key)||'null'); if(v&&typeof v.zoom==='number'&&v.zoom>=.5&&v.zoom<=1.5&&['pan','reference','game'].every(k=>Number.isFinite(v[k]?.x)&&Number.isFinite(v[k]?.y)))return v; } catch {} return initialView();
}
// Reference images stay in this browser; they are not sent to a model implicitly.
function referenceDB():Promise<IDBDatabase> {return new Promise((resolve,reject)=>{const r=indexedDB.open('ludraft-canvas',1);r.onupgradeneeded=()=>r.result.createObjectStore('references');r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(r.error);});}
async function referenceIO(key:string,value?:string|null):Promise<string|null>{const db=await referenceDB();return new Promise((resolve,reject)=>{const t=db.transaction('references',value===undefined?'readonly':'readwrite');const s=t.objectStore('references');const r=value===undefined?s.get(key):value===null?s.delete(key):s.put(value,key);t.oncomplete=()=>{db.close();resolve(typeof r.result==='string'?r.result:null);};t.onerror=()=>{db.close();reject(t.error);};});}
export function CanvasBoard({projectId,title,versionLabel,status,game,iteration,summary,controls,onPanel,onHelp}:{projectId:string;title:string;versionLabel:string;status:string;game:ReactNode;iteration:ReactNode;summary:string;controls:string;onPanel:(id:string)=>void;onHelp:()=>void}) {
  const [view,setView]=useState(()=>readView(projectId)),[tool,setTool]=useState<'cursor'|'hand'>('cursor'),[reference,setReference]=useState<string|null>(null),[imageError,setImageError]=useState('');
  const board=useRef<HTMLDivElement>(null),input=useRef<HTMLInputElement>(null),drag=useRef<{id:number;kind:'pan'|'reference'|'game';x:number;y:number;start:{x:number;y:number}}|null>(null);
  useEffect(()=>{try{localStorage.setItem('ludraft.canvas.'+projectId,JSON.stringify(view));}catch{}},[projectId,view]);
  useEffect(()=>{let live=true;referenceIO(projectId).then(v=>{if(live)setReference(v);}).catch(()=>{if(live)setImageError('浏览器无法读取参考图片；仍可使用文字描述。');});return()=>{live=false;};},[projectId]);
  const start=(e:PointerEvent,kind:'pan'|'reference'|'game')=>{if((e.target as HTMLElement).closest('button')||!e.isPrimary||e.button!==0||window.matchMedia('(max-width: 760px)').matches)return;e.stopPropagation();e.currentTarget.setPointerCapture(e.pointerId);drag.current={id:e.pointerId,kind,x:e.clientX,y:e.clientY,start:view[kind]};};
  const move=(e:PointerEvent)=>{const d=drag.current;if(!d||e.pointerId!==d.id)return;const scale=d.kind==='pan'?1:view.zoom;setView(v=>({...v,[d.kind]:{x:d.start.x+(e.clientX-d.x)/scale,y:d.start.y+(e.clientY-d.y)/scale}}));};
  const stop=()=>{drag.current=null;};
  const fit=()=>{const width=board.current?.clientWidth||1200;const height=board.current?.clientHeight||900;setView({...initialView(),zoom:Math.max(.5,Math.min(1,(width-40)/1110,(height-130)/850))});setTool('cursor');};
  const changeImage=async(file:File|undefined)=>{if(!file)return;setImageError('');if(!['image/png','image/jpeg','image/webp'].includes(file.type)||file.size>5*1024*1024){setImageError('请选择 5 MB 以内的 PNG、JPEG 或 WebP 图片。');return;}try{const data=await new Promise<string>((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result));r.onerror=()=>reject(Error('图片读取失败'));r.readAsDataURL(file);});await referenceIO(projectId,data);setReference(data);}catch{setImageError('图片保存失败，请检查浏览器存储空间。');}finally{if(input.current)input.current.value='';}};
  const handle={onPointerMove:move,onPointerUp:stop,onPointerCancel:stop,onLostPointerCapture:stop};
  return <div ref={board} className={'canvas-board dot-canvas tool-'+tool} aria-label="项目创作画布" onPointerDown={e=>{if(tool==='hand'&&e.target===e.currentTarget)start(e,'pan');}} {...handle}>
    <div className="canvas-world" style={{transform:`translate(${view.pan.x}px, ${view.pan.y}px) scale(${view.zoom})`}}>
      <svg className="canvas-connector" aria-hidden="true"><path d={`M${view.reference.x+394},${view.reference.y+225} C${view.reference.x+470},${view.reference.y+225} ${view.game.x-85},${view.game.y+260} ${view.game.x},${view.game.y+260}`}/><circle cx={view.reference.x+394} cy={view.reference.y+225} r="4"/><circle cx={view.game.x} cy={view.game.y+260} r="4"/></svg>
      <article className="canvas-node reference-node" style={{left:view.reference.x,top:view.reference.y}}>
        <div className="node-heading drag-handle" onPointerDown={e=>start(e,'reference')} {...handle}><strong><Icon name={reference?'image':'plan'}/> {reference?'风格参考':'玩法方案'}</strong><button aria-label="查看玩法与执行日志" onClick={()=>onPanel('flow')}><Icon name="more"/></button></div>
        {reference?<div className="reference-image"><img src={reference} alt="本项目的本地风格参考"/><button onClick={()=>input.current?.click()}><Icon name="upload" size={14}/> 更换参考</button></div>:<div className="plan-node-content"><span className="plan-node-symbol"><Icon name="game" size={40}/></span><span className="plan-node-label">从一个想法，长成一个游戏</span><h2>{title}</h2><p>{summary||'团队会在这里整理玩法、操作与验收条件。确认方案后，再生成你的第一份作品。'}</p>{controls&&<div className="plan-node-controls"><Icon name="cursor"/>{controls}</div>}<button onClick={()=>onPanel('flow')}>查看方案与进度 <Icon name="arrow" size={14}/></button></div>}
        <div className="reference-caption"><button onClick={()=>input.current?.click()}><Icon name="upload" size={14}/> {reference?'替换图片':'上传图片参考'}</button>{reference&&<button aria-label="移除画布参考" onClick={()=>{referenceIO(projectId,null).then(()=>setReference(null)).catch(()=>setImageError('移除失败，请重试。'));}}><Icon name="close" size={14}/></button>}<p>{reference?'仅保存在当前浏览器；给团队的风格要求请写入修改描述。':'支持本地图片参考，需求文档从材料库添加。'}</p></div>
        {imageError&&<p className="run-error" role="alert">{imageError}</p>}<input hidden type="file" ref={input} accept="image/png,image/jpeg,image/webp" aria-label="上传画布参考图片" onChange={e=>void changeImage(e.target.files?.[0])}/>
      </article>
      <div className="game-node-group" style={{left:view.game.x,top:view.game.y}}><article className="canvas-node game-node"><div className="node-heading drag-handle" onPointerDown={e=>start(e,'game')} {...handle}><strong>{title} <span>· {versionLabel}</span></strong><span className={'node-status '+(status==='可试玩'?'playable':'')}>{status}</span><button aria-label="查看版本历史" onClick={()=>onPanel('history')}><Icon name="more"/></button></div>{game}<i className="selection-corner tl"/><i className="selection-corner tr"/><i className="selection-corner bl"/><i className="selection-corner br"/></article><div className="canvas-iteration">{iteration}</div></div>
    </div>
    <div className="canvas-bottom"><div className="canvas-view-tools"><button className="canvas-small-button" onClick={()=>onPanel('materials')}><Icon name="image"/> 材料库</button><label className="canvas-zoom"><select aria-label="画布缩放" value={Math.round(view.zoom*100)} onChange={e=>setView(v=>({...v,zoom:Number(e.target.value)/100}))}>{[...new Set([50,65,75,85,100,125,150,Math.round(view.zoom*100)])].sort((a,b)=>a-b).map(z=><option key={z} value={z}>{z}%</option>)}</select></label></div><div className="canvas-dock"><button className="dark-tool" aria-label="添加参考图片" onClick={()=>input.current?.click()}><Icon name="plus" size={23}/></button><button className={tool==='cursor'?'selected-tool':''} aria-label="选择和拖动卡片" aria-pressed={tool==='cursor'} onClick={()=>setTool('cursor')}><Icon name="cursor" size={21}/></button><button className={tool==='hand'?'selected-tool':''} aria-label="平移画布" aria-pressed={tool==='hand'} onClick={()=>setTool('hand')}><Icon name="hand" size={21}/></button><span className="dock-divider"/><button aria-label="协作消息" onClick={()=>onPanel('messages')}><Icon name="message" size={20}/></button><button aria-label="版本历史" onClick={()=>onPanel('history')}><Icon name="history" size={20}/></button><button aria-label="画布帮助" onClick={onHelp}><Icon name="help" size={20}/></button></div><button className="canvas-small-button fit-canvas" aria-label="适应画布" onClick={fit}><Icon name="expand" size={19}/></button></div>
  </div>;
}
