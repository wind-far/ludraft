import {useEffect,useState} from 'react';

type Message={id:string;sender:string;recipient:string;kind:string;content:string;reply_to:string|null;created_at:string;answered:boolean;receipts:{step_id:string;role:string;task_key:string;status:string}[]};
type Messages={messages:Message[];status:string;pending_questions:string[]};
export function MessagesPanel({runId,revision,disabled,onChanged}:{runId:string;revision:number;disabled:boolean;onChanged:()=>Promise<unknown>}){
  const [data,setData]=useState<Messages|null>(null),[text,setText]=useState(''),[reply,setReply]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[reload,setReload]=useState(0);
  useEffect(()=>{const controller=new AbortController();
    fetch('/api/runs/'+runId+'/messages',{signal:controller.signal}).then(async r=>{if(!r.ok)throw Error('消息记录读取失败');return r.json();}).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>controller.abort();
  },[runId,revision,reload]);
  const questions=data?.messages.filter(m=>data.pending_questions.includes(m.id))||[];
  const target=questions.find(q=>q.id===reply)||questions[0];
  const active=!!data && ['queued','running','waiting_confirmation','testing'].includes(data.status);
  const send=async()=>{setBusy(true);setError('');try{
    const r=await fetch('/api/runs/'+runId+'/messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:text.trim(),reply_to:target?.id||null})});
    const result=await r.json();if(!r.ok)throw Error(typeof result.detail==='string'?result.detail:'消息提交失败');
    setText('');setReply('');setReload(n=>n+1);await onChanged();
  }catch(e){setError(e instanceof Error?e.message:'消息提交失败');}finally{setBusy(false);}};
  return <div className="team-panel message-panel"><div className="eyebrow">TEAM CONVERSATION</div><h3>把问题说清楚，再往前走。</h3><p>角色可以定向留言或广播。投递记录表示消息进入了模型上下文，是否落实还需检查交付物与测试结果。</p>
    {error && <p className="run-error" role="alert">{error}</p>}
    {data?.messages.length===0 && <p className="team-empty">暂无协作消息。执行中可以补充需求，团队会重新策划并等待确认。</p>}
    {data?.messages.map(m=><article className={'team-step message-item '+m.kind} key={m.id}><div className="team-step-heading"><strong>{m.sender==='user'?'你':m.sender} → {m.recipient==='all'?'全体角色':m.recipient==='user'?'你':m.recipient}</strong><small>{m.kind==='question'?(m.answered?'已答复':active?'待答复':'任务已结束'):m.kind==='answer'?'答复':m.kind==='feedback'?'需求补充':'协作留言'}</small></div>
      <p className="message-content">{m.content}</p><small>{new Date(m.created_at).toLocaleString('zh-CN')}</small>
      {m.reply_to && <p className="inline-note">答复：{data.messages.find(q=>q.id===m.reply_to)?.content||m.reply_to.slice(0,8)}</p>}
      {!!m.receipts.length && <details><summary>已送入 {m.receipts.length} 次模型上下文</summary><ul className="team-values">{m.receipts.map(r=><li key={r.step_id}>{r.role} · {r.task_key} · {r.step_id.slice(0,8)}</li>)}</ul></details>}
      {!m.receipts.length && m.recipient!=='user' && <p className="inline-note">尚未进入后续模型上下文。</p>}
    </article>)}
    {active && <form className="message-compose" onSubmit={e=>{e.preventDefault();void send();}}>
      {target && <label>待答复的问题<select aria-label="待答复的问题" value={target.id} disabled={busy} onChange={e=>setReply(e.target.value)}>{questions.map(q=><option key={q.id} value={q.id}>{q.sender}：{q.content}</option>)}</select></label>}
      <label>{target?'你的答复':'补充本轮需求'}<textarea aria-label={target?'你的答复':'补充本轮需求'} maxLength={2000} rows={4} value={text} disabled={disabled||busy} onChange={e=>setText(e.target.value)} placeholder={target?'补充条件，帮助团队做出明确决策。':'例如：三消游戏面向儿童，使用四种宝石，目标降为 800 分。'}/></label>
      <p className="inline-note">提交会停止当前执行，旧审批失效；所有问题答复后重新生成玩法，由你再次确认。上一可玩版本保留。</p>
      <button className="primary" disabled={disabled||busy||!text.trim()}>{busy?'正在提交…':target?'提交答复':'补充需求并重新策划'}</button>
    </form>}
    {!active && data && <p className="inline-note">任务已结束，继续调整请提交新的修改需求。</p>}
  </div>;
}
