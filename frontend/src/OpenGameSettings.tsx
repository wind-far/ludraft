import {useEffect, useRef, useState} from 'react';

type Check = {id:string;label:string;status:'passed'|'failed'|'unverified';detail:string;action?:string};
type Attempt = {id:string;run_id:string|null;kind:'cli'|'build';parent_id:string|null;state:string;cleanup:string;reason:string|null;updated_at:string};
type Executions = {pending_cleanup:number;can_start:boolean;busy:boolean;attempts:Attempt[]};
type Budget = {enabled:boolean;enforce_limits?:boolean;cap_cny?:number|null;settled_cny?:number;held_cny?:number;remaining_cny?:number|null;unsettled_calls?:number;unpriced_calls?:number};
type Status = {checked_at:string;preflight_passed:boolean;model_called:false;tower_creation_available:boolean;checks:Check[];budget:Budget|null;price:{input_cny_per_million:number;output_cny_per_million:number}|null;executions:Executions};
const money=(value?:number|null)=>value==null?'—':new Intl.NumberFormat('zh-CN',{style:'currency',currency:'CNY',maximumFractionDigits:6}).format(value);
const states:Record<string,string>={prepared:'准备中',creating:'创建中',created:'已创建',running:'执行中',succeeded:'执行完成',failed:'执行失败',cancelled:'已取消',interrupted:'已中断'};
const cleanupStates:Record<string,string>={pending:'待清理',unknown:'清理待确认',removed:'已清理'};

export function OpenGameSettings({onSettings}:{onSettings?:()=>void}) {
  const [open,setOpen]=useState(false);
  return <details className="role-model-settings opengame-settings" onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>OpenGame 执行与预算</summary>
    {open&&<ExecutionStatus onSettings={onSettings}/>}
  </details>;
}

function ExecutionStatus({onSettings}:{onSettings?:()=>void}) {
  const [data,setData]=useState<Status|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState('');
  const mounted=useRef(true),request=useRef<AbortController|null>(null);
  const read=async(signal:AbortSignal)=>{
    const response=await fetch('/api/settings/opengame/diagnostics',{signal});
    if(!response.ok)throw Error('执行环境读取失败，请检查本地服务后刷新。');
    const value=await response.json();
    if(!Array.isArray(value.checks)||!Array.isArray(value.executions?.attempts)||typeof value.preflight_passed!=='boolean')throw Error('执行环境响应不完整，请刷新重试。');
    return value as Status;
  };
  const refresh=async(recover=false)=>{
    request.current?.abort();
    const controller=new AbortController();request.current=controller;
    setBusy(true);setError('');setMessage('');
    const timeout=window.setTimeout(()=>controller.abort(),25000);
    try{
      let recoveryMessage='';
      if(recover){
        const response=await fetch('/api/settings/opengame/recover',{method:'POST',signal:controller.signal});
        if(!response.ok)throw Error('清理请求未成功返回，请刷新资源状态后重试。');
        const result=await response.json() as Executions;
        recoveryMessage=result.busy?'已有任务或恢复正在进行，本次未清理。':result.pending_cleanup===0?'所属资源核查完成，没有待清理记录。':'仍有资源未确认清理，请检查 Docker 和记录中的原因。';
      }
      const value=await read(controller.signal);
      if(mounted.current&&request.current===controller){setData(value);setMessage(recoveryMessage);}
    }catch(e){
      if(mounted.current&&request.current===controller)setError(e instanceof Error&&e.name==='AbortError'
        ?(recover?'等待清理结果超时，关闭页面不会撤销已提交请求。请刷新查看实际状态。':'环境检查超时，请检查 Docker 和本地服务后刷新。')
        :e instanceof Error?e.message:'检查失败，请刷新。');
    }finally{
      window.clearTimeout(timeout);
      if(mounted.current&&request.current===controller)setBusy(false);
    }
  };
  useEffect(()=>{mounted.current=true;void refresh();return()=>{mounted.current=false;request.current?.abort();};},[]);
  return <section className="opengame-status" aria-label="OpenGame 执行状态" aria-busy={busy}>
    <p>核查已保存的程序角色连接、构建环境、预算与任务资源。刷新不会调用模型，也不会自动清理资源。</p>
    <div className="setup-progress"><span role="status">{busy?'正在核查…':error?'本次检查未完成':data?.preflight_passed?'本地基础条件已通过，真实调用待验证':'仍有执行条件需要处理'}</span><button type="button" className="subtle" disabled={busy} onClick={()=>void refresh()}>刷新执行状态</button></div>
    {error&&<p className="run-error" role="alert">{error}{data?' 下方保留上次结果。':''}</p>}
    {message&&<p role="status">{message}</p>}
    {data&&<>
      <p className="inline-note">{data.tower_creation_available?'塔防入口已开放；本页检查不代表本次游戏已通过验收。':'塔防创作流程仍在接入，尚未开放创建。已有 Canvas 玩法可继续使用。'}</p>
      <div className="setup-checks">{data.checks.map(check=><article key={check.id}>
        <div className="setup-check-heading"><strong>{check.label}</strong><small className={check.status==='passed'?'check-pass':check.status==='failed'?'check-fail':'check-pending'}>{check.status==='passed'?'通过':check.status==='failed'?'需要处理':'待确认'}</small></div>
        <p>{check.detail}</p>
        {check.action==='settings'&&check.status!=='passed'&&(onSettings?<button type="button" className="setup-link" onClick={onSettings}>打开模型设置</button>:<p>在上方“八角色独立连接”中选择“程序”，保存后刷新本页。</p>)}
      </article>)}</div>
      <h3>费用记录</h3>
      {data.budget?.enabled?<><dl className="opengame-budget">
        {([['预算上限',data.budget.cap_cny],['已记费用',data.budget.settled_cny],['已知预留金额',data.budget.held_cny],['可用余额',data.budget.remaining_cny]] as const).map(([label,value])=><div key={label}><dt>{label}</dt><dd>{data.budget?.enforce_limits===false&&(label==='预算上限'||label==='可用余额')?'不限额':money(value)}</dd></div>)}
      </dl>{data.budget.enforce_limits===false&&<p>本项目预算拦截已关闭，金额、单价缺失和图片尝试次数均不限制调用。</p>}<p>{data.budget.unsettled_calls||0} 条请求尚未结算，其中 {data.budget.unpriced_calls||0} 条缺少单价、费用未知，未计入金额合计。金额按登记单价估算，最终以服务商账单为准。</p></>:<p>预算尚未启用或无法读取，可通过 scripts/budget.py unlimited 启用不限额记账。</p>}
      {data.price&&<p>每百万 token：输入 {money(data.price.input_cny_per_million)}，输出 {money(data.price.output_cny_per_million)}。</p>}
      <p className="inline-note">使用项目中的 scripts/budget.py unlimited 取消本地预算限制；configure 可恢复限额，price 可登记单价。本页不修改设置或核销未知费用。</p>
      <div className="setup-progress"><h3>最近执行记录</h3><button type="button" className="subtle" disabled={busy||data.executions.busy||data.executions.pending_cleanup===0} onClick={()=>void refresh(true)}>核查并清理所属资源</button></div>
      <p>仅处理已登记且归属匹配的中断资源。此操作不会重新生成游戏；执行完成也不等于玩法验收通过。</p>
      {!data.executions.attempts.length?<p className="inline-note">还没有 OpenGame 执行记录。</p>:<ol className="opengame-executions">{data.executions.attempts.map(attempt=><li key={attempt.id}>
        <div><strong>{attempt.kind==='build'?'诊断构建':'编码任务'}</strong><span>{states[attempt.state]||'状态待确认'} · {cleanupStates[attempt.cleanup]||'清理状态待确认'}</span></div>
        <small>{new Date(attempt.updated_at).toLocaleString()} · 记录 {attempt.id.slice(0,8)}{attempt.parent_id?` · 关联编码 ${attempt.parent_id.slice(0,8)}`:''}</small>
        {attempt.reason&&<p className="check-fail">{attempt.reason}</p>}
      </li>)}</ol>}
      <p className="check-timestamp">最近 30 条记录；检查时间 {new Date(data.checked_at).toLocaleString()}。执行期间可刷新查看最新状态。</p>
    </>}
  </section>;
}
