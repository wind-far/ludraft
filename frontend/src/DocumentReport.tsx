import {useEffect,useState} from 'react';
type Citation={source_id:string;start:number;end:number;quote:string};
type Document={id:string;title:string;sections:{heading:string;kind:'fact'|'proposal';body:string;citations:Citation[]}[]};
type Report={title:string;passed:boolean;boundary:string;sha256:string;documents:Document[];sources:Record<string,{label:string;text:string;sha256:string}>;review:{summary:string;issues:string[];limitations:string[]}|null;analysis_error:string|null;validation:{errors:string[]}};
export function DocumentReport({runId,status,revision}:{runId:string;status:string;revision:number}){
  const [report,setReport]=useState<Report|null>(null),[error,setError]=useState('');
  useEffect(()=>{const c=new AbortController();setError('');
    fetch('/api/runs/'+runId+'/report',{signal:c.signal}).then(async r=>{if(r.status===404)return null;if(!r.ok)throw Error('文档读取失败，请重试');return r.json();}).then(setReport).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>c.abort();
  },[runId,revision]);
  return <div className="task-report document-report"><section className="report-intro"><div className="eyebrow">PROJECT DOCUMENTS</div>
    <h3>{report?.title||'让设计与依据一起留下'}</h3><p>{report?.boundary||'确认文档范围后，主程编写、系统校验引用，PM 审阅。文档会保存为独立产物。'}</p>
    {error&&<p className="run-error" role="alert">{error}</p>}
    {!report&&<p>{status==='waiting_confirmation'?'等待你确认文档与章节范围。':['failed','cancelled'].includes(status)?'本轮未形成最终文档，请查看阶段日志。':'文档准备中，可在团队页查看交接记录。'}</p>}
    {report&&<><p className={report.passed?'check-pass':'check-fail'}>{report.passed?'文档门禁通过 · 待人工复核内容准确性':'草稿未通过门禁 · 不作为后续任务依据'}</p><a className="subtle report-download" href={'/api/runs/'+runId+'/report/export'}>下载文档与引用 ZIP</a></>}
    </section>
    {report?.documents.map(doc=><article className="report-analysis" key={doc.id}><h3>{doc.title}</h3>{doc.sections.map((section,i)=><section className="document-section" key={i}><div className="card-label"><b>{section.heading}</b><span>{section.kind==='fact'?'依据陈述':'设计建议'}</span></div><p className="document-body">{section.body}</p>
      {section.citations.map((citation,j)=>{const source=report.sources[citation.source_id];return <details key={j}><summary>引用 · {source?.label||citation.source_id} · 第 {citation.start}–{citation.end} 行</summary><blockquote>{citation.quote}</blockquote><p className="inline-note">来源编号：{citation.source_id}</p>{source&&<pre>{source.text.split('\n').slice(Math.max(0,citation.start-1),citation.end).map((line,k)=>`${citation.start+k}: ${line}`).join('\n')}</pre>}</details>;})}
    </section>)}</article>)}
    {report&&<section className="report-analysis"><h3>PM 审阅</h3><p>{report.review?.summary||'未形成有效审阅。'}</p>{report.analysis_error&&<p className="run-error">{report.analysis_error}</p>}
      {!!report.validation.errors.length&&<ul>{report.validation.errors.map((v,i)=><li key={i}>{v}</li>)}</ul>}
      {report.review?.limitations.map((v,i)=><p className="inline-note" key={i}>{v}</p>)}
      <details><summary>来源与报告摘要</summary><pre>{JSON.stringify({report_sha256:report.sha256,sources:Object.fromEntries(Object.entries(report.sources).map(([k,v])=>[k,v.sha256]))},null,2)}</pre></details>
    </section>}
  </div>;
}
