import {useEffect,useState} from 'react';
import {TestResults} from './WorkbenchPanels';
type Report={title:string;base_version:string;passed:boolean;sha256:string;boundary:string;finished_at:string;manual_checks:string[];scope:{summary:string;focus:string[]};tool_evidence:Record<string,any>;analysis_error:string|null;qa_report:{summary:string;issues:{owner:string;severity:string;description:string;evidence:string}[]}|null;delivery:{summary:string;ready:boolean;limitations:string[]}|null;input_hashes:Record<string,string>};
export function TaskReport({runId,status,revision,evidence}:{runId:string;status:string;revision:number;evidence:Record<string,any>|null}){
  const [report,setReport]=useState<Report|null>(null),[error,setError]=useState('');
  useEffect(()=>{const c=new AbortController();setError('');
    fetch('/api/runs/'+runId+'/report',{signal:c.signal}).then(async r=>{if(r.status===404)return null;if(!r.ok)throw Error('测试报告读取失败，请刷新后重试');return r.json();}).then(setReport).catch(e=>{if(e.name!=='AbortError')setError(e.message);});return()=>c.abort();
  },[runId,revision]);
  const pending=['queued','running','waiting_confirmation','testing'].includes(status);
  return <div className="task-report">
    <section className="report-intro"><div className="eyebrow">TEST REPORT</div><h3>{report?'独立测试报告':pending?'测试报告正在准备':'尚未形成最终报告'}</h3>
      <p>{report?.boundary||'本轮对已有版本运行测试，原游戏与可玩版本保持不变。'}</p>
      {error && <p className="run-error" role="alert">{error}</p>}
      {report && <><p className={report.passed?'check-pass':'check-fail'}>{report.passed?'报告门禁通过':'报告门禁未通过'}</p><p>测试版本 {report.base_version.slice(0,8)} · {new Date(report.finished_at).toLocaleString('zh-CN')}</p><p>{report.scope.summary}</p><a className="subtle report-download" href={'/api/runs/'+runId+'/report/export'}>下载完整测试报告 ZIP</a></>}
    </section>
    <TestResults evidence={report?.tool_evidence||evidence} pending={pending} label="本次独立测试的实际工具证据"/>
    {report && <section className="report-analysis"><h3>QA 分析</h3><p>{report.qa_report?.summary||'没有有效分析；工具结果仍保留在报告中。'}</p>
      {report.analysis_error && <p className="run-error">{report.analysis_error}</p>}
      {report.qa_report?.issues.map((item,i)=><article className="team-step" key={i}><strong>{item.severity==='blocking'?'阻断':'建议'} · {item.owner}</strong><p>{item.description}</p><p className="inline-note">依据：{item.evidence}</p></article>)}
      <h3>交付审阅</h3><p>{report.delivery?.summary||'未接受交付或未执行交付审阅。'}</p>{report.delivery?.limitations.map((v,i)=><p className="inline-note" key={i}>{v}</p>)}
      <h3>待人工检查</h3><ul>{report.manual_checks.map((v,i)=><li key={i}>{v}</li>)}</ul>
      <details><summary>测试文件与报告摘要</summary><pre>{JSON.stringify({report_sha256:report.sha256,input_hashes:report.input_hashes},null,2)}</pre></details>
    </section>}
  </div>;
}
