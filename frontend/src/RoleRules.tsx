import {useEffect,useState} from 'react';
import {StudioIcon as Icon} from './StudioIcon';
type Source={id:string;title:string;kind:string;origin:string;sha256:string;content?:string;revision?:string};
type Profile={role:string;revision:string;instructions:string;skills:string[];builtin:string;upstream:string};
type Data={roles:Record<string,Profile>;catalog:Source[]};
async function request(path:string,body?:unknown,method='POST'){
  const r=await fetch('/api/'+path,{method:body===undefined?'GET':method,headers:body===undefined?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const result=await r.json();if(!r.ok)throw Error(typeof result.detail==='string'?result.detail:'规则请求失败');return result;
}
export function StepRules({stepId}:{stepId:string}){
  const [snapshot,setSnapshot]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const read=async()=>{if(snapshot||busy)return;setBusy(true);try{setSnapshot(await request('steps/'+stepId+'/rules'));setError('');}catch(e){setError(e instanceof Error?e.message:'读取失败');}finally{setBusy(false);}};
  return <details className="step-rules" onToggle={e=>{if(e.currentTarget.open)void read();}}><summary>查看本次调用的规则快照</summary>
    {error&&<p role="alert">{error}</p>}{busy&&<p>正在读取…</p>}{snapshot&&<><p className="inline-note">快照 {snapshot.id.slice(0,12)} · 设置版本 {snapshot.payload.profile_revision.slice(0,12)}。这是实际装入上下文的内容，后续编辑不会覆盖。</p>
      {snapshot.payload.instructions&&<p className="message-content">自定义补充：{snapshot.payload.instructions}</p>}
      {snapshot.payload.sources.map((s:Source)=><details key={s.id}><summary>{s.title} · {s.sha256.slice(0,8)}</summary><small>{s.id}</small><pre>{s.content}</pre></details>)}</>}
  </details>;
}
export function RoleRulesModal({onClose}:{onClose:()=>void}){
  const [data,setData]=useState<Data|null>(null),[drafts,setDrafts]=useState<Record<string,Profile>>({}),[role,setRole]=useState('制作人'),[tab,setTab]=useState('roles'),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[source,setSource]=useState<Source|null>(null),[sourceKey,setSourceKey]=useState(''),[history,setHistory]=useState<{id:string;created_at:string}[]>([]),[historical,setHistorical]=useState('');
  const [skillKey,setSkillKey]=useState(''),[skillTitle,setSkillTitle]=useState(''),[skillContent,setSkillContent]=useState(''),[skillRevision,setSkillRevision]=useState<string|null>(null);
  useEffect(()=>{let disposed=false;request('settings/rules').then(v=>{if(!disposed){setData(v);setDrafts(v.roles);}}).catch(e=>{if(!disposed)setMessage(e.message);});return()=>{disposed=true;};},[]);
  useEffect(()=>{let disposed=false;setHistory([]);setHistorical('');request('settings/rules/'+encodeURIComponent(role)+'/history').then(v=>{if(!disposed)setHistory(v);}).catch(e=>{if(!disposed)setMessage(e.message);});return()=>{disposed=true;};},[role,data]);
  const perform=async(action:()=>Promise<void>)=>{setBusy(true);setMessage('');try{await action();}catch(e){setMessage(e instanceof Error?e.message:'操作失败');}finally{setBusy(false);}};
  const reload=async()=>{const v=await request('settings/rules') as Data;setData(v);return v;};
  const showSource=async(key:string)=>{setSourceKey(key);setSource(null);const v=await request('settings/rules/source?key='+encodeURIComponent(key));setSource(v);};
  const p=drafts[role];const update=(changes:Partial<Profile>)=>setDrafts(prev=>({...prev,[role]:{...prev[role],...changes}}));
  const save=()=>perform(async()=>{await request('settings/rules/'+encodeURIComponent(role),{expected_revision:p.revision,instructions:p.instructions,skills:p.skills},'PUT');const v=await reload();setDrafts(prev=>({...prev,[role]:v.roles[role]}));setMessage('已保存；从该角色后续调用开始使用，历史快照保持不变。');});
  const restore=(revision:string|null)=>perform(async()=>{await request('settings/rules/'+encodeURIComponent(role)+'/restore',{expected_revision:p.revision,revision});const v=await reload();setDrafts(prev=>({...prev,[role]:v.roles[role]}));setMessage('已恢复为新的设置版本。');});
  const editSkill=async(s:Source)=>{const v=await request('settings/rules/source?key='+encodeURIComponent(s.id));setSkillKey(v.id.slice(7));setSkillTitle(v.title);setSkillContent(v.content);setSkillRevision(v.revision);};
  const saveSkill=()=>perform(async()=>{const v=await request('settings/skills/'+encodeURIComponent(skillKey),{expected_revision:skillRevision,title:skillTitle,content:skillContent},'PUT');setSkillRevision(v.revision);await reload();setMessage('技能已保存。回到角色设置勾选后生效；已选用的角色将在后续调用使用新版。');});
  return <div className="modal-backdrop" onClick={onClose}><section className="modal rules-modal" role="dialog" aria-modal="true" aria-labelledby="rules-title" onKeyDown={e=>{if(e.key==='Escape'){e.stopPropagation();onClose();}}} onClick={e=>e.stopPropagation()}><header className="rules-modal-header"><div className="rules-modal-title"><h2 id="rules-title">角色规则与技能</h2><button className="modal-close" aria-label="关闭规则设置" onClick={onClose}><Icon name="close"/></button></div>
    <div className="team-filters"><button className={tab==='roles'?'selected':''} onClick={()=>setTab('roles')}>角色设置</button><button className={tab==='library'?'selected':''} onClick={()=>setTab('library')}>规则与技能库</button></div></header>
    <div className="rules-modal-body" role="region" aria-label="规则设置内容" tabIndex={0}><p className="rules-description">上游原文只读保留，三消 Canvas 规则明确适用边界。自定义内容不会改变文件权限、审批和实际测试门禁。</p>
    {message&&<p className="notice" role="status">{message}</p>}
    {tab==='roles'&&data&&p&&<><div className="team-filters">{Object.keys(data.roles).map(r=><button key={r} disabled={busy} className={role===r?'selected':''} onClick={()=>{setRole(r);setMessage('');}}>{r}</button>)}</div>
      <div className="rules-columns"><div><h3>{role} · 固定职责</h3><p className="rule-prose">{p.builtin}</p><button className="subtle" disabled={busy} onClick={()=>perform(async()=>{await showSource(p.upstream);setTab('library');})}>查看上游角色原文</button><p className="inline-note">当前设置版本 {p.revision.slice(0,12)}。每一步还会按任务加载对应步骤文件，实际内容在团队记录中查看。</p></div><div><label>自定义补充<textarea aria-label={role+'规则补充'} rows={6} maxLength={8000} value={p.instructions} disabled={busy} onChange={e=>update({instructions:e.target.value})} placeholder="例如：目标用户是儿童，所有宝石同时通过颜色和形状区分。"/></label></div></div>
      <fieldset disabled={busy} className="rule-skill-list"><legend>选用技能 · {p.skills.length}/8</legend>{data.catalog.filter(s=>s.kind==='skill').map(s=><label key={s.id}><input type="checkbox" checked={p.skills.includes(s.id)} disabled={!p.skills.includes(s.id)&&p.skills.length>=8} onChange={e=>update({skills:e.target.checked?[...p.skills,s.id]:p.skills.filter(k=>k!==s.id)})}/><span>{s.title}<small>{s.origin==='upstream'?'上游参考 · 部分面向 Unity':s.origin==='custom'?'自定义技能':'三消工作台技能'}</small></span></label>)}</fieldset>
      <div className="connection-actions"><button className="primary" disabled={busy} onClick={save}>保存{role}规则</button><button className="subtle" disabled={busy} onClick={()=>restore(null)}>恢复默认设置</button></div>
      {!!history.length&&<details><summary>设置历史 · 最近 {history.length} 个版本</summary><label>历史版本<select aria-label="历史规则版本" value={historical} onChange={e=>setHistorical(e.target.value)}><option value="">选择历史版本</option>{history.map(h=><option key={h.id} value={h.id}>{new Date(h.created_at).toLocaleString('zh-CN')} · {h.id.slice(0,8)}</option>)}</select></label><button className="subtle" disabled={busy||!historical} onClick={()=>restore(historical)}>恢复所选版本</button></details>}</>}
    {tab==='library'&&data&&<><label>查阅参考文档<select aria-label="规则文档" value={sourceKey} disabled={busy} onChange={e=>perform(()=>showSource(e.target.value))}><option value="">选择文档</option>{data.catalog.map(s=><option key={s.id} value={s.id}>{s.id}</option>)}</select></label>
      {source&&<details open><summary>{source.title} · {source.origin} · {source.sha256.slice(0,12)}</summary><pre className="rule-source">{source.content}</pre></details>}
      <h3>自定义技能</h3><p>创建或编辑技能文档，再到角色设置勾选。编辑已选技能会影响后续调用，旧调用快照保留原文。</p><div className="team-filters"><button className="subtle" disabled={busy} onClick={()=>{setSkillKey('');setSkillTitle('');setSkillContent('');setSkillRevision(null);}}>新建技能</button>{data.catalog.filter(s=>s.origin==='custom').map(s=><button className="subtle" disabled={busy} key={s.id} onClick={()=>perform(()=>editSkill(s))}>{s.title}</button>)}</div>
      <div className="rules-columns"><label>技能 ID<input aria-label="自定义技能ID" value={skillKey} disabled={busy||!!skillRevision} onChange={e=>setSkillKey(e.target.value)} placeholder="match3-accessibility" pattern="[a-z][a-z0-9_-]{0,63}"/></label><label>名称<input aria-label="自定义技能名称" value={skillTitle} disabled={busy} maxLength={80} onChange={e=>setSkillTitle(e.target.value)}/></label></div><label>技能内容<textarea aria-label="自定义技能内容" value={skillContent} disabled={busy} maxLength={12000} rows={8} onChange={e=>setSkillContent(e.target.value)}/></label><button className="primary" disabled={busy||!skillKey||!skillTitle.trim()||!skillContent.trim()} onClick={saveSkill}>保存技能</button></>}
  </div></section></div>;
}
