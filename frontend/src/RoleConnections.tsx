import {useEffect,useState} from 'react';
type Profile={mode:'shared'|'independent';provider:string;base_url:string;model:string;max_tokens:number;has_key:boolean;effective_has_key:boolean;effective:{model:string;base_url:string;provider:string};check?:{status:string;checked_at?:string}};
type Draft={mode:'shared'|'independent';provider:string;base_url:string;model:string;max_tokens:number;api_key:string;clear_key:boolean};
const providers:Record<string,string>={openai:'OpenAI',anthropic:'Anthropic',deepseek:'DeepSeek',custom:'自定义兼容服务'};
const urls:Record<string,string>={openai:'https://api.openai.com/v1',anthropic:'https://api.anthropic.com/v1',deepseek:'https://api.deepseek.com/v1',custom:''};
const roles=['制作人','PM','策划','主程','美术','UX','程序','QA'];
const draftOf=(p:Profile):Draft=>({mode:p.mode,provider:p.provider,base_url:p.base_url,model:p.model,max_tokens:p.max_tokens,api_key:'',clear_key:false});
export function RoleModels(){
  const [data,setData]=useState<Record<string,Profile>>({}),[drafts,setDrafts]=useState<Record<string,Draft>>({}),[role,setRole]=useState('制作人'),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const read=async()=>{const r=await fetch('/api/settings/connections');const value=await r.json();if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:'角色连接读取失败');return value.roles as Record<string,Profile>;};
  useEffect(()=>{let disposed=false;read().then(v=>{if(!disposed){setData(v);setDrafts(Object.fromEntries(Object.entries(v).map(([k,p])=>[k,draftOf(p)])));}}).catch(e=>{if(!disposed)setMessage(e.message);});return()=>{disposed=true;};},[]);
  const p=data[role],d=drafts[role];
  const dirty=!!p&&!!d&&JSON.stringify(d)!==JSON.stringify(draftOf(p));
  const anyDirty=roles.some(r=>data[r]&&drafts[r]&&JSON.stringify(drafts[r])!==JSON.stringify(draftOf(data[r])));
  const update=(v:Partial<Draft>)=>setDrafts(prev=>({...prev,[role]:{...prev[role],...v}}));
  const save=async()=>{setBusy(true);setMessage('');try{const r=await fetch('/api/settings/connections/'+encodeURIComponent(role),{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});const result=await r.json();if(!r.ok)throw Error(typeof result.detail==='string'?result.detail:'角色连接保存失败');const profiles=await read();setData(profiles);setDrafts(prev=>({...prev,[role]:draftOf(profiles[role])}));setMessage(role+'连接已保存，将用于后续调用。');}catch(e){setMessage(e instanceof Error?e.message:'保存失败');}finally{setBusy(false);}};
  const test=async(all=false)=>{setBusy(true);setMessage('正在测试已保存连接…');const results:string[]=[];try{for(const name of all?roles:[role]){setMessage('正在测试 '+name+'…');const r=await fetch('/api/settings/connections/'+encodeURIComponent(name)+'/test',{method:'POST'});const result=await r.json();results.push(name+'：'+(r.ok?'通过':typeof result.detail==='string'?result.detail:'失败'));}setData(await read());setMessage(results.join('\n'));}catch(e){setMessage([...results,e instanceof Error?e.message:'连接测试失败'].join('\n'));}finally{setBusy(false);}};
  return <details className="role-model-settings"><summary>八角色独立连接</summary><p>每个角色可沿用默认连接，或使用独立服务商、地址与密钥。测试会调用已保存的模型；只验证连接与结构化响应，不代表生成质量。</p>
    <div className="team-filters connection-roles">{roles.map(r=><button type="button" key={r} className={r===role?'selected':''} disabled={busy} onClick={()=>{setRole(r);setMessage('');}}>{r}<small>{data[r]?.check?.status==='passed'?'已验证':data[r]?.check?.status==='failed'?'失败':'未验证'}</small></button>)}</div>
    {d&&p&&<fieldset disabled={busy} className="connection-editor"><legend>{role}连接</legend>
      <label>连接方式<select aria-label={role+'连接方式'} value={d.mode} onChange={e=>update({mode:e.target.value as Draft['mode']})}><option value="shared">沿用默认连接</option><option value="independent">独立连接</option></select></label>
      {d.mode==='independent'&&<><label>服务商<select aria-label={role+'服务商'} value={d.provider} onChange={e=>update({provider:e.target.value,base_url:urls[e.target.value],api_key:'',max_tokens:e.target.value==='deepseek'?8000:12000})}>{Object.entries(providers).map(([k,n])=><option value={k} key={k}>{n}</option>)}</select></label>
      <label>API 基础地址<input aria-label={role+'API地址'} value={d.base_url} onChange={e=>update({base_url:e.target.value})} placeholder={urls[d.provider]||'http://127.0.0.1:端口/v1'}/></label></>}
      <label>模型名称<input aria-label={role+'模型'} value={d.model} placeholder={d.mode==='shared'?p.effective.model||'沿用默认模型':'填写服务商提供的模型 ID'} onChange={e=>update({model:e.target.value})}/></label>
      {d.mode==='independent'&&<><label>API Key <span>{p.has_key?'已保存；同一地址留空保留':'尚未配置独立密钥'}</span><input aria-label={role+'API Key'} type="password" autoComplete="off" value={d.api_key} onChange={e=>update({api_key:e.target.value,clear_key:false})}/></label>
      <label className="connection-clear"><input type="checkbox" checked={d.clear_key} onChange={e=>update({clear_key:e.target.checked,api_key:''})}/>清除该角色已保存的密钥</label>
      <label>最大输出 tokens<input aria-label={role+'最大输出tokens'} type="number" min={256} max={64000} value={d.max_tokens} onChange={e=>update({max_tokens:Number(e.target.value)})}/></label>
      <p className="inline-note">改变服务商或地址需要重填密钥，或勾选清除。独立连接不会自动取用默认密钥；切回默认连接会删除该角色的独立密钥。</p></>}
      <p className="inline-note">已保存的生效连接：{providers[p.effective.provider]||p.effective.provider} · {p.effective.model||'未填模型'}<br/>{p.effective.base_url}</p>
      <div className="connection-actions"><button type="button" className="subtle" disabled={!dirty} onClick={save}>保存{role}连接</button><button type="button" className="subtle" disabled={dirty} onClick={()=>void test()}>测试{role}连接</button></div>
    </fieldset>}
    <button type="button" className="subtle" disabled={busy||anyDirty||!p} onClick={()=>void test(true)}>测试全部 8 个角色</button>
    {anyDirty&&<p className="inline-note">有未保存的角色设置，请逐一保存后再测试全部连接。</p>}
    {message&&<p className="connection-result" role="status">{message}</p>}
  </details>;
}
