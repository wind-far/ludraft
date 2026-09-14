import { useEffect, useState } from 'react';
import {StepRules} from './RoleRules';
import { StudioIcon as Icon, type StudioIconName } from './StudioIcon';

type TeamEvent={role:string;kind:string;payload:Record<string,any>};
const roles:[string,string,StudioIconName][]=[['制作人','需求与交付','target'],['PM','任务与依赖','folder'],['策划','玩法设计','plan'],['主程','方案与审查','code'],['美术','视觉规范','sparkles'],['UX','交互规范','play'],['程序','实现与修复','code'],['QA','实测与分析','verified']];
const taskNames:Record<string,string>={research_scope:'调研范围',research:'方向调研',research_review:'调研复核',review_scope:'审查范围',code_audit:'代码审查',audit_response:'程序回应',audit_verdict:'审查复核',document_scope:'文档范围',documents:'文档编写',document_review:'文档审阅',test_scope:'测试范围',test_delivery:'报告审阅',config_plan:'参数提案',brief:'需求范围',tasks:'初步任务拆解',plan:'玩法方案',confirmed_tasks:'确认后的任务安排',coding_plan:'编码任务分工',tech:'技术方案',art:'视觉规范',ux:'交互规范',code:'代码交付',review:'代码审查',test_strategy:'测试策略',qa_report:'测试分析',delivery:'交付说明'};
const statuses:Record<string,string>={waiting_input:'待答复',running:'执行中',succeeded:'已产出',failed:'失败',cancelled:'已取消',reused:'沿用设计',assembled:'已合并'};
type Step={rules_snapshot?:string|null;connection?:{provider?:string;base_url?:string};inherited?:boolean;source_version?:string;id:string;task_key:string;role:string;status:string;inputs:string[];output:Record<string,unknown>|null;model:string|null;usage:Record<string,number>|null;elapsed:number|null;error:string|null};
type TeamData={mode:string;roles:{name:string;duty:string}[];steps:Step[];inherited_steps?:Step[]};

export function TeamCrew({events,status,onSelect}:{events:TeamEvent[];status:string;onSelect:(role:string)=>void}) {
  return <div className="team-crew" aria-label="八角色协作团队">{roles.map(([name,duty,icon])=>{
    const latest=[...events].reverse().find(e=>e.role===name && ['agent_start','agent_artifact','agent_failed','agent_cancelled','agent_question','testing','artifact_reused'].includes(e.kind));
    const finished=new Set(events.filter(e=>['agent_artifact','agent_failed','agent_cancelled','agent_question'].includes(e.kind)).map(e=>e.payload.step_id));
    const working=events.some(e=>e.role===name && e.kind==='agent_start' && !finished.has(e.payload.step_id));
    const state=working && !['failed','cancelled'].includes(status)?'running':latest?.kind==='artifact_reused'?'reused':(latest?.kind==='agent_start'||latest?.kind==='testing')?(['failed','cancelled'].includes(status)?'cancelled':'running'):latest?.kind==='agent_question'?'waiting_input':latest?.kind==='agent_artifact'?'succeeded':latest?.kind==='agent_failed'?'failed':latest?.kind==='agent_cancelled'?'cancelled':'pending';
    return <button type="button" key={name} className={'team-member '+state} onClick={()=>onSelect(name)}><Icon name={icon} size={18}/><strong>{name}</strong><small>{duty}</small><span>{statuses[state]||'未执行'}</span></button>;
  })}</div>;
}

const labels:Record<string,string>={messages:'协作消息',clarification:'澄清问题',recipient:'接收角色',id:'任务编号',summary:'摘要',task_type:'任务类型',routing_reason:'判断依据',design_updates:'补充设计范围',scope:'本轮范围',constraints:'约束',risks:'风险',tasks:'任务安排',key:'任务',goal:'目标',depends_on:'依赖',acceptance:'验收条件',title:'名称',mode:'模式',controls:'操作',decisions:'设计决策',issues:'问题',owner:'责任角色',severity:'级别',description:'问题描述',evidence:'依据',focus:'测试关注点',manual_checks:'待人工检查',ready:'接受交付',limitations:'交付限制',files:'文件变更',path:'路径',content:'源码'};
function Artifact({value}:{value:unknown}) {
  if(Array.isArray(value))return value.length?<ul className="team-values">{value.map((v,i)=><li key={i}><Artifact value={v}/></li>)}</ul>:<span className="team-muted">无</span>;
  if(value && typeof value==='object')return <dl className="team-artifact">{Object.entries(value).map(([k,v])=><div key={k}><dt>{labels[k]||k}</dt><dd>{k==='content'?<details><summary>展开源文件</summary><pre>{String(v)}</pre></details>:<Artifact value={v}/>}</dd></div>)}</dl>;
  return <span>{typeof value==='boolean'?(value?'是':'否'):({research:'方向调研',review:'代码审查',doc:'文档编写',test:'独立测试',config:'配置调整',feature:'功能开发',bugfix:'修复问题',visual:'视觉调整',optimize:'性能优化',tech:'技术方案',art:'视觉规范',ux:'交互规范',code:'代码实现',qa:'QA 验证',blocking:'阻断',suggestion:'建议'} as Record<string,string>)[String(value)]||String(value??'—')}</span>;
}

export function TeamPanel({runId,revision,role,onRole}:{runId:string;revision:number;role:string;onRole:(role:string)=>void}) {
  const [data,setData]=useState<TeamData|null>(null),[error,setError]=useState(''),[target,setTarget]=useState('');
  useEffect(()=>{if(target){document.getElementById('step-'+target)?.scrollIntoView({block:'start'});setTarget('');}},[target,role]);
  useEffect(()=>{const controller=new AbortController();let disposed=false;
    fetch('/api/runs/'+runId+'/team',{signal:controller.signal}).then(async r=>{if(!r.ok)throw Error('团队记录读取失败');return r.json();}).then(v=>{if(!disposed){setData(v);setError('');}}).catch(e=>{if(!disposed && e.name!=='AbortError')setError(e.message);});return()=>{disposed=true;controller.abort();};
  },[runId,revision]);
  const allSteps=[...(data?.steps||[]),...(data?.inherited_steps||[])];
  const steps=allSteps.filter(s=>!role||s.role===role);
  return <div className="team-panel"><div className="eyebrow">YOUR AI TEAM</div><h3>每一份交付，都有来处。</h3><p>查看角色成果、交接关系与审查依据。模型审查和实际工具验证分别记录。</p>
    <div className="team-filters"><button className={!role?'selected':''} onClick={()=>onRole('')}>全部</button>{roles.map(([name])=><button className={role===name?'selected':''} onClick={()=>onRole(name)} key={name}>{name}</button>)}</div>
    {error && <p className="run-error" role="alert">{error}</p>}
    {data && data.mode!=='team8' && <p className="inline-note">这是历史记录或直接调参任务，未执行八角色协作。新建作品或提交自然语言修改会使用八角色流程。</p>}
    {!steps.length && <p className="team-empty">{data?'该角色尚无执行记录。完成上游交付并确认玩法后，依赖满足的步骤才会开始。':'正在读取团队记录…'}</p>}
    {steps.map(step=><article className="team-step" key={step.id} id={'step-'+step.id}><div className="team-step-heading"><strong>{step.role} · {taskNames[step.task_key]||(step.task_key.startsWith('code:')?'编码子任务 · '+step.task_key.slice(5):step.task_key)}</strong><small className={step.status==='failed'?'check-fail':step.status==='succeeded'?'check-pass':'check-pending'}>{step.inherited?'来源交付物':statuses[step.status]||step.status}</small></div>
      <div className="team-step-meta"><span>{step.status==='assembled'?'系统合并 · 未调用模型':step.model||(step.status==='running'?'模型调用中':'模型信息不可用')}</span>{step.elapsed!=null && <span>{step.elapsed.toFixed(1)} 秒</span>}{step.usage?.total_tokens!=null && <span>{step.usage.total_tokens.toLocaleString()} tokens</span>}</div>
      {step.connection?.provider && <p className="inline-note">调用连接：{step.connection.provider} · {step.connection.base_url}</p>}
      {step.inherited && <p className="inline-note">继承自版本 {step.source_version?.slice(0,8)}；此处用量及耗时属于来源任务，本轮未重新执行。</p>}
      {!!step.inputs.length && <div className="team-inputs"><span>依据交付：</span>{step.inputs.map(id=>{const input=allSteps.find(s=>s.id===id);return <a key={id} href={'#step-'+id} onClick={e=>{e.preventDefault();onRole('');setTarget(id);}}>{input?`${input.role} · ${taskNames[input.task_key]||input.task_key}`:'交付记录'}</a>;})}</div>}
      {step.error && <p className="run-error">{step.error}</p>}
      {step.rules_snapshot && <StepRules stepId={step.id}/>}
      {step.output && <p className="team-output-summary">{String(step.output.summary||step.output.title||'')}</p>}
      {step.output && <details open={Boolean(role)&&step.task_key!=='code'}><summary>查看交付物</summary><Artifact value={step.output}/></details>}
    </article>)}
  </div>;
}

export {RoleModels} from './RoleConnections';

export function TaskTypeSelect({value,onChange,disabled=false,hasVersion=false}:{value:string;onChange:(v:string)=>void;disabled?:boolean;hasVersion?:boolean}) {
  return <label className="task-type-select">任务类型<select aria-label="任务类型" value={value} disabled={disabled} onChange={e=>onChange(e.target.value)}>
    <option value="auto">自动判断</option><option value="feature">功能开发</option><option value="bugfix">修复问题</option><option value="visual">视觉调整</option><option value="optimize">性能优化</option>
    <option value="config" disabled={!hasVersion}>配置调整{!hasVersion?'（需已有版本）':''}</option>
    <option value="doc">文档编写</option><option value="research">方向调研</option>
    <option value="review" disabled={!hasVersion}>代码审查{!hasVersion?'（需已有版本）':''}</option>
    <option value="test" disabled={!hasVersion}>独立测试{!hasVersion?'（需已有版本）':''}</option>
  </select></label>;
}

export function TaskRoute({events}:{events:TeamEvent[]}) {
  const event=[...events].reverse().find(e=>['route_selected','route_confirmed','route_revised'].includes(e.kind));
  if(!event)return null;
  const route=event.payload;
  if(route.task_type==='research')return <div className="task-route"><strong>方向调研 · {event.kind==='route_selected'?'建议安排':'执行安排'}</strong><p>{route.reason}</p><small>制作人 → 策划调研范围 → 你确认 → 来源读取与方向比较 → 制作人复核。供你决策，不自动进入开发。</small></div>;
  if(route.task_type==='review')return <div className="task-route"><strong>代码审查 · {event.kind==='route_selected'?'建议安排':'执行安排'}</strong><p>{route.reason}</p><small>制作人 → PM 审查范围 → 你确认 → 主程审查 → 程序回应 → 主程复核。仅审查，不自动修改代码或执行测试。</small></div>;
  if(route.task_type==='doc')return <div className="task-route"><strong>文档编写 · {event.kind==='route_selected'?'建议安排':'执行安排'}</strong><p>{route.reason}</p><small>制作人 → PM 文档范围 → 你确认 → 主程编写 → 引用校验 → PM 审阅。最多修订两轮，独立保存文档产物。</small></div>;
  if(route.task_type==='test')return <div className="task-route"><strong>独立测试 · {event.kind==='route_selected'?'建议安排':'执行安排'}</strong><p>{route.reason}</p><small>制作人 → PM 测试范围 → 你确认 → QA 策略与实测 → 策划审阅报告。不会修改或发布游戏版本。</small></div>;
  return <div className="task-route"><strong>{route.label} · {event.kind==='route_selected'?'建议安排':'执行安排'}</strong><p>{route.reason}</p>
    {route.task_type==='config'?<small>制作人 → PM 参数提案 → 你确认 → 程序调整 → QA 实测 → 制作人交付。涉及玩法或视觉结构变化时，请选择功能开发。</small>:<><small>更新设计：{(route.update||[]).map((k:string)=>taskNames[k]).join('、')||'无'}{route.reuse?.length>0 && <> · 沿用：{route.reuse.map((k:string)=>taskNames[k]).join('、')}</>}</small>
    {event.kind==='route_selected' && <small>确认玩法后 PM 可扩大设计范围；编辑玩法将重新执行完整设计。</small>}</>}
  </div>;
}
