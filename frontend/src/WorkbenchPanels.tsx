import { useState } from 'react';
import { StudioIcon as Icon } from './StudioIcon';

export type GamePlan = { title: string; summary: string; mode: string; controls: string; acceptance: string[] };
export type GameParameters = Record<string,string|number>;
export const parameterLabels: Record<keyof GameParameters,string> = {moves:'可用步数',targetScore:'目标分数',gemTypes:'宝石种类',speed:'移动速度',lives:'初始生命',spawnMs:'生成间隔',fallSpeed:'下落速度',duration:'游戏时长',background:'背景颜色',playerColor:'玩家颜色',targetColor:'目标颜色',hazardColor:'危险物颜色'};

export function PlanEditor({plan,busy,error,onClose,onSave}:{error?:string;plan:GamePlan;busy:boolean;onClose:()=>void;onSave:(p:GamePlan)=>void}) {
  const [draft,setDraft]=useState(plan),[acceptance,setAcceptance]=useState(plan.acceptance.join('\n'));
  const items=acceptance.split('\n').map(s=>s.trim()).filter(Boolean);
  return <div className="modal-backdrop"><form className="modal editor-modal" role="dialog" aria-modal="true" aria-labelledby="plan-editor-title" onSubmit={e=>{e.preventDefault();onSave({...draft,acceptance:items});}}>
    <button type="button" className="modal-close" aria-label="关闭玩法编辑" onClick={onClose}><Icon name="close" /></button>
    <div className="eyebrow">YOUR GAME PLAN</div><h2 id="plan-editor-title">把玩法调整到位</h2><p>保存后仍需确认方案，才会开始生成。每行填写一条可观察的验收条件。</p>
    <label>游戏名称<input required maxLength={80} value={draft.title} onChange={e=>setDraft({...draft,title:e.target.value})}/></label>
    <label>游戏模式<select value={draft.mode} onChange={e=>setDraft({...draft,mode:e.target.value})}><option value="match3">三消游戏</option><option value="collector">接物收集</option><option value="dodger">生存躲避</option><option value="clicker">点击目标</option></select></label>
    <label>玩法说明<textarea required minLength={5} maxLength={2000} value={draft.summary} onChange={e=>setDraft({...draft,summary:e.target.value})}/></label>
    <label>操作方式<input required minLength={3} maxLength={500} value={draft.controls} onChange={e=>setDraft({...draft,controls:e.target.value})}/></label>
    <label>验收条件（3–12 条）<textarea required value={acceptance} onChange={e=>setAcceptance(e.target.value)} /></label>
    {error && <p role="alert" className="run-error">{error}</p>}<div className="modal-actions"><button type="button" className="subtle" onClick={onClose}>取消</button><button className="primary" disabled={busy || items.length<3 || items.length>12}>保存玩法</button></div>
  </form></div>;
}

const numeric: [keyof GameParameters,number,number,number,string][]=[['speed',1,1500,1,'px / s'],['lives',1,10,1,'条'],['spawnMs',100,10000,1,'ms'],['fallSpeed',1,1000,1,'px / s'],['duration',5,600,1,'秒']];
const colors: (keyof GameParameters)[]=['background','playerColor','targetColor','hazardColor'];
export function ParameterPanel({initial,disabled,busy,onSave}:{initial:GameParameters;disabled:boolean;busy:boolean;onSave:(p:GameParameters)=>void}) {
  const labels=initial.mode==='match3'?{...parameterLabels,playerColor:'翡翠宝石',targetColor:'琥珀宝石',hazardColor:'玫瑰宝石'}:parameterLabels;
  const keys=Object.keys(parameterLabels).filter(k=>initial[k]!==undefined);
  const controls=initial.mode==='match3'?([['moves',5,100,1,'步'],['targetScore',100,20000,50,'分'],['gemTypes',4,6,1,'种']] as typeof numeric):numeric;
  const [draft,setDraft]=useState<GameParameters>(()=>Object.fromEntries(keys.map(k=>[k,initial[k as keyof GameParameters]])) as GameParameters);
  const changed=keys.filter(k=>draft[k as keyof GameParameters]!==initial[k as keyof GameParameters]);
  const set=(key:keyof GameParameters,value:string|number)=>setDraft(p=>({...p,[key]:value}));
  return <form className="parameter-panel" onSubmit={e=>{e.preventDefault();onSave(draft);}}>
    <div className="eyebrow">TUNE YOUR GAME</div><h3>手感，在细节里。</h3><p>直接调整参数，不调用模型。保存前运行构建与交互验证，失败会保留上一可玩版本。</p>
    <fieldset disabled={disabled||busy}>
      {controls.map(([key,min,max,step,unit])=><label className="parameter-row" key={key}><span>{labels[key]}<small>{unit}</small></span><input aria-label={labels[key]+'滑块'} type="range" min={min} max={max} step={step} value={draft[key]} onChange={e=>set(key,Number(e.target.value))}/><input aria-label={labels[key]} required type="number" min={min} max={max} step={step} value={draft[key]} onChange={e=>set(key,e.target.value===''?'':Number(e.target.value))}/></label>)}
      <div className="color-grid">{colors.map(key=><label key={key}><input type="color" aria-label={labels[key]} value={String(draft[key])} onChange={e=>set(key,e.target.value)}/><span>{labels[key]}<small>{draft[key]}</small></span></label>)}</div>
    </fieldset>
    <div className="parameter-summary"><strong>{changed.length ? `${changed.length} 项待确认变更` : '调整参数后，变更会显示在这里'}</strong>{changed.map(k=><div key={k}><span>{labels[k as keyof GameParameters]}</span><span>{initial[k as keyof GameParameters]} → {draft[k as keyof GameParameters]}</span></div>)}</div>
    {disabled && <p className="inline-note">仅可调整当前活动版本；请先恢复项目、结束当前任务，或返回当前版本。</p>}
    <div className="panel-actions"><button type="button" className="subtle" disabled={busy||!changed.length} onClick={()=>setDraft(Object.fromEntries(keys.map(k=>[k,initial[k as keyof GameParameters]])) as GameParameters)}>重置</button><button className="primary" disabled={busy||disabled||!changed.length}>验证并保存参数 <Icon name="check" /></button></div>
  </form>;
}

const checks=['TypeScript 构建','参数边界','开始游戏','键盘移动','真实得分及界面更新','危险目标扣命','游戏结束','重新开始','无浏览器异常'];
export function TestResults({evidence,pending,label}:{evidence:Record<string,any>|null;pending:boolean;label:string}) {
  const actual: {name:string;passed:unknown}[]=Array.isArray(evidence?.checks)?evidence.checks.filter((c:unknown):c is {name:string;passed:unknown}=>!!c && typeof c==='object' && 'name' in c && typeof c.name==='string'):[];
  const baseChecks=(evidence?.expected_mode||evidence?.config?.mode)==='match3'?['TypeScript 构建','三消参数边界','开始游戏','棋盘初始可玩','无效交换回退','禁止跨格交换','结算期间禁止重复操作','真实交换消除与步数','下落补位与连锁','无解棋盘重排','目标达成与失败','重新开始','无浏览器异常']:checks;
  const mobileChecks=evidence?.runtime==='match3-v1'?['移动端布局','触屏交换消除']:evidence?.runtime==='canvas-input-v2'?['移动端布局',evidence?.config?.mode==='clicker'?'触屏点击得分':'触屏拖动与停止','倒计时与重开']:[];
  const names=[...new Set([...baseChecks,...mobileChecks,...actual.map(c=>c.name)])];
  const state=(name:string)=>{const items=actual.filter(c=>c.name===name);return items.length?items.every(c=>c.passed===true)?true:false:undefined;};
  const format=(value:unknown)=>typeof value==='string'?value:JSON.stringify(value);
  const gates=Array.isArray(evidence?.gate_errors)?evidence.gate_errors.filter((v:unknown)=>typeof v==='string'):[];
  const consoleIssue=Array.isArray(evidence?.console_errors)?evidence.console_errors.length>0:!!evidence?.console_errors;
  const verified=evidence?.passed===true && evidence?.build===true && evidence?.exit_code===0 && gates.length===0 && !consoleIssue && names.every(name=>state(name)===true);
  const elapsed=evidence?.finished_at && evidence?.started_at ? (new Date(evidence.finished_at).getTime()-new Date(evidence.started_at).getTime())/1000:null;
  return <div className="test-panel"><div className="eyebrow">QUALITY REPORT</div><h3>{!evidence ? pending?'正在准备验证':'尚无本轮测试证据':verified?'核心验证通过':'验证未通过'}</h3><p>{label}。未执行的检查不会记作通过。</p>
    <div className="test-overview"><span><strong>{names.filter(name=>state(name)===true).length} / {names.length}</strong>检查通过</span><span><strong>{elapsed!=null && Number.isFinite(elapsed)?`${elapsed.toFixed(2)} s`:'—'}</strong>测试耗时</span></div>
    <div className="check-list">{names.map(name=>{const passed=state(name);return <div key={name}><span>{name}</span><span className={passed===true?'check-pass':passed===false?'check-fail':'check-pending'}><Icon name={passed===true?'check':passed===false?'close':'history'} size={14}/>{passed===true?'通过':passed===false?'失败':'未执行'}</span></div>})}</div>
    {evidence?.parameter_match!==undefined && <p className={evidence.parameter_match?'check-pass':'check-fail'}>参数一致性：{evidence.parameter_match?'通过':'失败'}</p>}
    {evidence?.error && <p className="run-error">{format(evidence.error)}</p>}
    {gates.length>0 && <details open><summary>验证门禁未通过</summary><ul>{gates.map((error:string,i:number)=><li key={i}>{error}</li>)}</ul></details>}
    {evidence?.mobile?.status==='unverified' && <p className="inline-note">手机操作尚未验证：{format(evidence.mobile.reason)}</p>}
    {consoleIssue && <details open><summary>浏览器错误</summary><pre>{format(evidence?.console_errors)}</pre></details>}
    {(evidence?.build_log || evidence?.log) && <details><summary>构建与执行日志</summary><pre>{format(evidence.build_log || evidence.log)}</pre></details>}
    <div className="human-review"><Icon name="game" size={20}/><div><strong>玩法体验，仍需你来确认</strong><p>自动检查覆盖固定核心交互。难度、趣味性及个性化验收条件需要人工试玩。</p></div></div>
  </div>;
}

export function ProjectManager({project,busy,pending,error,onClose,onUpdate,onDuplicate}:{error?:string;project:{title:string;state?:string;active_version:string|null};busy:boolean;pending:boolean;onClose:()=>void;onUpdate:(body:Record<string,string>)=>void;onDuplicate:()=>void}) {
  const [title,setTitle]=useState(project.title),[trash,setTrash]=useState(false);
  return <div className="modal-backdrop"><section className="modal" role="dialog" aria-modal="true" aria-labelledby="project-manager-title"><button className="modal-close" aria-label="关闭项目管理" onClick={onClose}><Icon name="close"/></button><div className="eyebrow">YOUR WORKSPACE</div><h2 id="project-manager-title">管理这个作品</h2><p>复制保留可玩版本；归档和回收站中的项目都可以恢复。</p>
    <form onSubmit={e=>{e.preventDefault();onUpdate({title:title.trim()});}}><label>项目名称<input required maxLength={80} value={title} onChange={e=>setTitle(e.target.value)}/></label><div className="panel-actions"><button className="primary" disabled={busy||pending||!title.trim()||title.trim()===project.title}>保存名称</button></div></form>
    {error && <p role="alert" className="run-error">{error}</p>}<div className="project-operations"><button className="subtle" onClick={onDuplicate} disabled={busy||!project.active_version||project.state==='trash'}>复制可玩版本为新项目</button>{project.state!=='active' ? <button className="subtle" onClick={()=>onUpdate({state:'active'})} disabled={busy||pending}>恢复到工作空间</button>:<button className="subtle" onClick={()=>onUpdate({state:'archived'})} disabled={busy||pending}>归档项目</button>}
    {project.state!=='trash' && <button className="danger-button" onClick={()=>setTrash(true)} disabled={busy||pending}>移到回收站</button>}
    {trash && <div className="trash-confirm"><p>项目将从工作空间隐藏，源码和历史版本仍会保留。</p><button className="danger-button" disabled={busy||pending} onClick={()=>onUpdate({state:'trash'})}>确认移到回收站</button><button className="subtle" onClick={()=>setTrash(false)}>取消</button></div>}
    {pending && <p className="inline-note">请先完成或取消当前任务，再整理项目。</p>}</div>
  </section></div>;
}
