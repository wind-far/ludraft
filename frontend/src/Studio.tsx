import { useCallback, useEffect, useRef, useState } from "react";
import "./studio.css";
import "./canvas.css";
import {HomeScreen, BlankCanvas, CanvasBoard, type Surface} from "./CanvasUI";
import {MaterialPicker,RunMaterials,type Material} from "./Materials";
import {TaskReport} from './TaskReport';
import {DocumentReport} from './DocumentReport';
import {CodeReviewReport} from './CodeReviewReport';
import {ResearchReport} from './ResearchReport';
import {RoleRulesModal} from "./RoleRules";
import { MessagesPanel } from "./MessagesPanel";
import { TeamCrew, TeamPanel, RoleModels, TaskTypeSelect, TaskRoute } from "./TeamPanels";
import { SetupGuide, VersionCompare } from "./DiscoveryPanels";
import { OpenGameSettings } from './OpenGameSettings';
import { PlanEditor, ParameterPanel, TestResults, ProjectManager, parameterLabels, type GameParameters, type GamePlan } from "./WorkbenchPanels";
import { StudioIcon as Icon, type StudioIconName } from "./StudioIcon";

type ProjectSummary = {
  last_status?: string;
  state?: string;
  last_opened?: string;
  id: string;
  title: string;
  active_version: string | null;
  created_at: string;
};
type Run = {
  task_type?: string;
  has_report?: boolean;
  approval_revision?: number;
  engine?: string;
  id: string;
  status: string;
  requirement: string;
  plan: string | null;
  error: string | null;
  repairs: number;
  created_at: string;
};
type VersionSummary = {
  id: string;
  title: string;
  created_at: string;
  run_id: string;
};
type Project = ProjectSummary & {
  runs: Run[];
  versions: VersionSummary[];
  preview_origin: string;
};
type Event = {
  id: number;
  role: string;
  kind: string;
  created_at: string;
  payload: Record<string, any>;
};
type Version = VersionSummary & {
  parameters: (GameParameters & {title:string;mode:string}) | null;
  parameter_error?: string;
  files: Record<string, string>;
  diff: string;
  evidence: Record<string, any>;
};
const states: Record<string, string> = {
  queued: "排队中",
  running: "执行中",
  waiting_confirmation: "等待确认",
  testing: "验证中",
  succeeded: "已交付",
  failed: "执行失败",
  cancelled: "已取消",
};
const active = ["queued", "running", "waiting_confirmation", "testing"];
const examples = [
  {label:'宝石花园',mode:'经典三消',icon:'sparkles' as StudioIconName,text:'做一个 match3 宝石三消游戏，8×8 棋盘，20 步获得 1200 分，六种宝石，清新花园配色。'},
  {label:'星光收集站',mode:'接物挑战',icon:'game' as StudioIconName,text:'做一个 collector 接物游戏，左右移动接金币、躲炸弹，3 条生命、60 秒一局，金币加分，支持重开。'},
  {label:'流星闪避',mode:'生存躲避',icon:'target' as StudioIconName,text:'做一个 dodger 躲避游戏，左右移动避开落下的流星，3 条生命、60 秒一局，按生存时间得分，深蓝色背景。'},
  {label:'点亮星星',mode:'点击得分',icon:'sparkles' as StudioIconName,text:'做一个 clicker 点击游戏，点击星星得分，误点炸弹扣生命，3 条生命、30 秒一局，结束后可以重新开始。'},
];
async function api<T = any>(
  path: string,
  body?: unknown,
  method?: string,
): Promise<T> {
  const r = await fetch("/api" + path, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await r.json();
  if (!r.ok)
    throw Error(
      typeof data.detail === "string" ? data.detail : "请求失败，请检查输入",
    );
  return data;
}
export default function Studio() {
  const [surface,setSurface]=useState<Surface>('home');
  const [composing,setComposing]=useState(false),[materialModal,setMaterialModal]=useState(false),[canvasHelp,setCanvasHelp]=useState(false),[mobileNav,setMobileNav]=useState(false);
  const [composerAdvanced,setComposerAdvanced]=useState(false);
  const [projects, setProjects] = useState<ProjectSummary[]>([]),
    [project, setProject] = useState<Project | null>(null);
  const [materials,setMaterials]=useState<Material[]>([]),[uploadBusy,setUploadBusy]=useState(false);
  const [text, setText] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [events, setEvents] = useState<Event[]>([]),
    [version, setVersion] = useState<Version | null>(null);
  const [tab, setTab] = useState("preview"),
    [file, setFile] = useState("src/config.ts"),
    [runId, setRunId] = useState("");
  const [settings, setSettings] = useState(false),
    [model, setModel] = useState({
      base_url: "https://api.openai.com/v1",
      model: "",
      api_key: "",
      has_key: false,
    });
  const [notice, setNotice] = useState(""),
    [runner, setRunner] = useState<boolean | null>(null);
  const [search,setSearch]=useState(''),[projectFilter,setProjectFilter]=useState('active');
  const [manageProject,setManageProject]=useState(false),[editingPlan,setEditingPlan]=useState(false);
  const [planSnapshot,setPlanSnapshot]=useState('');
  const [taskType,setTaskType]=useState('auto');
  const [reviewReference,setReviewReference]=useState<string|null>(null);
  const [researchUrls,setResearchUrls]=useState('');
  const [researchChoice,setResearchChoice]=useState<{run_id:string;direction_id:string}|null>(null);
  const [showRules,setShowRules]=useState(false);
  const [teamRole,setTeamRole]=useState('');
  const [comparisonSelection,setComparisonSelection]=useState<{before:string;after:string}|null>(null);
  const [showSetup,setShowSetup]=useState(()=>{try{return localStorage.getItem('ludraft.setup.seen')!=='1';}catch{return true;}});
  const returnToSetup=useRef(false);
  const closeSetup=()=>{setShowSetup(false);try{localStorage.setItem('ludraft.setup.seen','1');}catch{ /* Storage can be unavailable in private mode. */ }};
  const closeSettings=()=>{setSettings(false);if(returnToSetup.current){setShowSetup(true);returnToSetup.current=false;}};
  const selected = useRef<string | null>(null),
    generation = useRef(0), versionRequest = useRef(0);
  const run = project?.runs.find((r) => r.id === runId) || project?.runs[0];
  const pending = !!project?.runs.some((r) => active.includes(r.status));
  const plan = run?.plan ? JSON.parse(run.plan) : null;
  const configRun = [...events].reverse().find(e=>['route_selected','route_confirmed','route_revised'].includes(e.kind))?.payload.task_type==='config';
  const configProposal = [...events].reverse().find(e=>e.kind==='config_proposed')?.payload;
  const researchRun = run?.task_type==='research';
  const researchScope = [...events].reverse().find(e=>e.kind==='research_scope_ready')?.payload;
  const reviewRun = run?.task_type==='review';
  const reviewScope = [...events].reverse().find(e=>e.kind==='review_scope_ready')?.payload;
  const docRun = run?.task_type==='doc';
  const docScope = [...events].reverse().find(e=>e.kind==='document_scope_ready')?.payload;
  const testRun = run?.task_type==='test';
  const testScope = [...events].reverse().find(e=>e.kind==='test_scope_ready')?.payload;
  const readOnly = !!project && (project.state || 'active') !== 'active';
  const filteredProjects=projects.filter(p=>(p.state||'active')===projectFilter && p.title.toLowerCase().includes(search.toLowerCase()));
  const parameterRun = events.some(e=>e.kind==='parameters_confirmed');
  const latestTest = [...events].reverse().find(e=>e.kind==='test_result');
  const list = useCallback(async () => setProjects(await api("/projects")), []);
  const refresh = useCallback(async (id: string) => {
    const p = await api<Project>("/projects/" + id);
    if (selected.current === id) setProject(p);
    return p;
  }, []);
  const loadVersion = useCallback(async (id: string) => {
    const gen = generation.current, request = ++versionRequest.current;
    const v = await api<Version>("/versions/" + id);
    if (gen === generation.current && request === versionRequest.current) setVersion(v);
  }, []);
  const select = async (id: string) => {
    setSurface('canvas');setComposing(false);setMobileNav(false);window.scrollTo(0,0);
    generation.current++;
    selected.current = id;
    setComparisonSelection(null);setTeamRole('');
    setProject(null);
    setTab("preview");
    setText("");setTaskType("auto");setMaterials([]);setReviewReference(null);setResearchUrls('');setResearchChoice(null);
    setEditingPlan(false);
    setManageProject(false);
    setVersion(null);
    setEvents([]);
    setRunId("");
    setError("");
    try {
      const p = await refresh(id);
      if (selected.current !== id) return;
      await api("/projects/" + id + "/open", {});
      if (selected.current !== id) return;
      list().catch(() => {});
      setRunId(p.runs[0]?.id || "");
      if(!p.active_version) setTab("flow");
      if (p.active_version) await loadVersion(p.active_version);
    } catch (e) {
      setError(String(e));
    }
  };
  useEffect(() => {
    list().catch((e) => setError(String(e)));
    api("/settings/model")
      .then((v) => setModel({ ...v, api_key: "" }))
      .catch(() => {});
    api("/health")
      .then((v) => setRunner(v.runner_available))
      .catch(() => setRunner(false));
  }, [list]);
  useEffect(() => {
    if (!project || !runId) return;
    setEvents([]);
    const id = project.id,
      source = new EventSource("/api/runs/" + runId + "/events");
    source.onmessage = (e) => {
      const ev = JSON.parse(e.data) as Event;
      setEvents((prev) =>
        prev.some((x) => x.id === ev.id) ? prev : [...prev, ev],
      );
      refresh(id)
        .then((p) => {
          if (selected.current === id && ev.kind === "published" && p.active_version)
            loadVersion(p.active_version);
        })
        .catch(() => {});
      list().catch(() => {});
    };
    return () => source.close();
  }, [project?.id, runId, refresh, list, loadVersion]);
  const perform = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const submit = () =>
    perform(async () => {
      if (text.trim().length < 3)
        throw Error("请用至少 3 个字描述游戏或修改要求");
      const result = await api(
        project ? "/projects/" + project.id + "/runs" : "/projects",
        { text: text.trim(), task_type: taskType, code_review_id:reviewReference, research_urls:researchUrls.split('\n').map(x=>x.trim()).filter(Boolean), research_choice:researchChoice, materials:materials.map(({upload_id,text})=>({upload_id,text})) },
      );
      setText("");setTaskType("auto");setMaterials([]);setReviewReference(null);setResearchUrls('');setResearchChoice(null);
      await list();
      await select(result.project_id);
      setRunId(result.run_id);
    });
  const decide = (approve: boolean) =>
    perform(async () => {
      await api("/runs/" + run!.id + "/decision", { approve, expected_scope_revision: researchRun?researchScope?.scope_revision:reviewRun?reviewScope?.scope_revision:docRun?docScope?.scope_revision:testScope?.scope_revision, expected_config_revision: configProposal?.config_revision, expected_revision: run!.approval_revision, expected_plan: run!.plan });
      await refresh(project!.id);
    });
  const updateProject = (body:Record<string,string>) => perform(async()=>{
    await api('/projects/'+project!.id,body,'PUT');
    await refresh(project!.id); await list(); setManageProject(false);
    if(body.state) setProjectFilter(body.state);
  });
  const duplicateProject = () => perform(async()=>{
    const result=await api('/projects/'+project!.id+'/duplicate',{});
    setProjectFilter('active');setSearch('');await list();await select(result.project_id);
  });
  const savePlan = (draft:GamePlan) => perform(async()=>{
    await api('/runs/'+run!.id+'/plan',{plan:draft,expected_revision:run!.approval_revision, expected_plan:planSnapshot},'PUT');
    await refresh(project!.id);setEditingPlan(false);
  });
  const saveParameters = (parameters:GameParameters) => perform(async()=>{
    const result=await api('/projects/'+project!.id+'/parameters',{base_version:version!.id,parameters});
    await refresh(project!.id);setRunId(result.run_id);setTab('tests');await list();
  });
  const saveModel = (test = false) =>
    perform(async () => {
      setNotice("");
      const v = await api(
        "/settings/model",
        {
          base_url: model.base_url,
          model: model.model,
          api_key: model.api_key,
        },
        "PUT",
      );
      setModel({ ...v, api_key: "" });
      if (test) {
        const result = await api("/settings/model/test", {});
        setNotice("真实模型连接成功 · " + result.model);
      } else setNotice("配置已保存，仅保存在本机");
    });
  const reset = (destination:Surface='home') => {
    setSurface(destination);setComposing(false);setMobileNav(false);setTab('preview');window.scrollTo(0,0);
    generation.current++;
    selected.current = null;
    setComparisonSelection(null);setTeamRole('');
    setProject(null);
    setVersion(null);
    setEvents([]);
    setRunId("");
    setError("");
    setText("");setTaskType("auto");setMaterials([]);setReviewReference(null);setResearchUrls('');setResearchChoice(null);
    setEditingPlan(false);setManageProject(false);
  };
  const tokens = events
    .filter((e) => ["model_result", "model_error"].includes(e.kind))
    .reduce((n, e) => n + (e.payload.usage?.total_tokens || 0), 0);
  const panelNames:Record<string,string>={team:'八角色协作团队',messages:'协作消息',code:'项目源码',diff:'版本对比',history:'版本历史',parameters:'调整参数',tests:'验证与报告',materials:'材料库'};
  const launchAction=(id:string)=>{
    if(id==='materials'){setMaterialModal(true);return;}
    setSurface('canvas');setComposing(true);
    setTaskType(id==='visual'?'visual':'auto');
    if(id==='research'){setSurface('home');setComposing(false);requestAnimationFrame(()=>document.getElementById('brief')?.focus());}
  };
  useEffect(()=>{const escape=(e:KeyboardEvent)=>{if(e.key!=='Escape')return;setTab('preview');setComposing(false);setMaterialModal(false);setCanvasHelp(false);setMobileNav(false);};window.addEventListener('keydown',escape);return()=>window.removeEventListener('keydown',escape);},[]);
  const composer=<div className="composer canvas-composer">
    <div className="brief-input-row"><button className="attachment-button" aria-label="添加需求材料" onClick={()=>setMaterialModal(true)}><Icon name="link" size={20}/></button><textarea id="brief" aria-label="游戏创作需求" placeholder="描述你的游戏想法，或选择一个任务开始…" value={text} onChange={e=>setText(e.target.value)} maxLength={8000}/><button className="send-brief" aria-label="提交创作需求" onClick={submit} disabled={busy||uploadBusy||text.trim().length<3}><Icon name="arrow" size={20}/></button></div>
    <div className="brief-options"><button onClick={()=>setComposerAdvanced(v=>!v)} aria-expanded={composerAdvanced}><Icon name="settings" size={13}/> {taskType==='auto'?'任务选项':'已选择任务类型'}</button>{materials.length>0&&<button onClick={()=>setMaterialModal(true)}>{materials.length} 份已核对材料</button>}<span>先确认玩法，再开始生成</span></div>
    {composerAdvanced&&<TaskTypeSelect value={taskType} onChange={v=>{setTaskType(v);setReviewReference(null);setResearchChoice(null);setResearchUrls('');}} disabled={busy}/>}
    {taskType==='research'&&<label className="research-urls">公开网页来源（可选，每行一个，最多五个）<textarea aria-label="调研网页来源" rows={2} value={researchUrls} disabled={busy} onChange={e=>setResearchUrls(e.target.value)} placeholder="https://…"/><span>确认范围后读取；也可上传并核对参考材料。</span></label>}
  </div>;
  const iteration=project?(
              <div className="iteration">
                <div className="run-metrics">
                  <span>
                    {parameterRun ? "本轮未调用模型" : tokens
                      ? `已记录 ${tokens.toLocaleString()} tokens`
                      : "用量随真实调用记录"}
                  </span>
                  <span>{testRun?'独立测试 · 不自动修复':parameterRun ? "参数验证 · 单次执行" : `修复 ${run?.repairs || 0} / 2`}</span>
                  {pending && (
                    <button
                      onClick={() =>
                        perform(async () => {
                          await api(
                            "/runs/" + project.runs[0].id + "/cancel",
                            {},
                          );
                          await refresh(project.id);
                        })
                      }
                    >
                      取消任务
                    </button>
                  )}
                </div>
                {reviewReference&&<p className="inline-note">修复依据：所选审查 {reviewReference.slice(0,8)} <button className="subtle" onClick={()=>setReviewReference(null)}>取消引用</button></p>}
                <details className="iteration-options"><summary>修改范围与任务类型</summary><TaskTypeSelect value={taskType} onChange={v=>{setTaskType(v);setReviewReference(null);setResearchChoice(null);setResearchUrls('');}} disabled={pending||readOnly||busy} hasVersion={!!project.active_version}/></details>
                {researchChoice&&<p className="inline-note">采用调研 {researchChoice.run_id.slice(0,8)} · {researchChoice.direction_id} <button className="subtle" onClick={()=>setResearchChoice(null)}>取消引用</button></p>}
                {taskType==='research'&&<label className="research-urls">公开网页来源（可选，每行一个，最多五个）<textarea aria-label="调研网页来源" rows={2} value={researchUrls} disabled={pending||readOnly||busy} onChange={e=>setResearchUrls(e.target.value)} placeholder="https://…"/><span>确认后读取；也可上传并核对材料。不会执行全网搜索。</span></label>}
                <textarea
                  aria-label="修改要求"
                  placeholder={
                    pending
                      ? "当前任务结束后，可以继续修改…"
                      : "描述希望调整的规则、难度、操作反馈或配色…"
                  }
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  disabled={pending || readOnly}
                  maxLength={8000}
                />
                <button className="attach-materials" disabled={pending||readOnly||busy} onClick={()=>setMaterialModal(true)}><Icon name="plus" size={13}/> 参考材料{materials.length?` · ${materials.length} 份`:""}</button>
                <div className="iteration-actions">
                  <small>每次改动都会保留上一可玩版本</small>
                  <button
                    className="primary"
                    disabled={pending || readOnly || busy || uploadBusy || text.trim().length < 3}
                    onClick={submit}
                  >
                    确认修改 <Icon name="arrow" />
                  </button>
                </div>
              </div>
  ):null;
  const gamePreview=project&&version?(
                    <div className="preview-area">
                      <div className="browser-chrome">
                        <span className="window-dots" aria-hidden="true"><i /><i /><i /></span>
                        <small>{version.id===project.active_version?'当前版本':'历史版本'} / {version.id.slice(0, 8)}</small>
                        <span><Icon name="lock" size={12} /></span>
                      </div>
                      <iframe
                        title="游戏隔离预览"
                        key={version.id}
                        src={
                          project.preview_origin +
                          "/v/" +
                          version.id +
                          "/index.html"
                        }
                        sandbox="allow-scripts"
                      />
                      {version.id!==project.active_version && <div className="historical-preview"><span>正在试玩历史版本，当前作品未改变</span><button onClick={()=>perform(async()=>{await loadVersion(project.active_version!);})}>返回当前版本</button><button onClick={()=>setTab('diff')}>继续对比</button></div>}
                      <div className="preview-foot">
                        <span className="verified"><Icon name="verified" size={13} /> {version.evidence.scope==='phaser-integration-smoke'?'接入检查通过 · 完整玩法待验收':'构建与核心交互已验证'}</span>
                        <span>玩法体验请亲自试玩</span>
                      </div>
                    </div>
  ):(
                <div className="artifact-empty">
                  <div className="orbit">
                    <span><Icon name="game" size={44} /></span>
                  </div>
                  <span className="eyebrow">A LITTLE WORLD IN THE MAKING</span>
                  <h3>你的游戏，即将在这里诞生。</h3>
                  <p>
                    确认玩法后，团队将生成代码并运行测试。
                    <br />
                    通过验证的版本会自动出现在这里。
                  </p>
                  <div className="empty-pipeline">策划 <Icon name="chevron" size={11} /> 代码 <Icon name="chevron" size={11} /> 构建 <Icon name="chevron" size={11} /> 试玩</div>
                </div>
  );
  return (
    <div className={'studio canvas-studio '+(surface==='canvas'?'canvas-mode ':'')+(mobileNav?'nav-open':'')}>

      <aside className="sidebar">
        <a className="brand" href="#" onClick={e=>{e.preventDefault();reset();}}><span className="brand-mark"><Icon name="game" size={25}/></span><div>游芽 <span className="brand-english">Ludraft</span></div></a>
        <button className="new-project" onClick={()=>reset('canvas')}><Icon name="plus"/> 新建项目</button>
        <nav className="main-navigation" aria-label="工作空间导航"><button className={surface==='home'?'active':''} onClick={()=>reset()}><Icon name="home"/> 首页</button><button className={surface==='projects'?'active':''} onClick={()=>{reset('projects');setProjectFilter('active');}}><Icon name="folder"/> 项目</button><button className={surface==='materials'?'active':''} onClick={()=>reset('materials')}><Icon name="image"/> 材料库</button></nav>
        <div className="sidebar-spacer"/><div className="sidebar-bottom"><button className="settings-btn" onClick={()=>{setSettings(true);setNotice('');}}><Icon name="settings"/> 模型与连接</button><button className="settings-btn" onClick={()=>setShowRules(true)}><Icon name="team"/> 角色规则与技能</button><button className="settings-btn" onClick={()=>setShowSetup(true)}><Icon name="help"/> 帮助与环境检查</button><div className="local-profile" role="group" aria-label="本地创作者信息"><span className="local-profile-avatar"><Icon name="user" size={21}/></span><div><strong>本地创作者</strong><span>本地工作空间</span></div></div></div>
      </aside>
      <main className="studio-main">
        {surface!=='home'&&<header className="topbar">
          <div className="workspace-identity"><button className="mobile-nav-toggle" aria-label="打开导航" onClick={()=>setMobileNav(v=>!v)}><Icon name="menu"/></button>{surface==='canvas'?<><button className="back-home" onClick={()=>reset('projects')}><span className="back-arrow"><Icon name="arrow" size={15}/></span> 我的作品</button><button className="canvas-project-title" onClick={()=>project?setManageProject(true):setComposing(true)}><Icon name="game" size={22}/><span>游芽</span><i/> <strong>{project?.title||'未命名项目'}</strong><Icon name="chevron" size={12}/></button><span className="main-canvas-label">主画布</span></>:<strong className="workbench-title">游戏创作工作台</strong>}</div>
          <div className="top-right">{surface==='canvas'?<>{version?<a className="canvas-small-button" href={'/api/versions/'+version.id+'/export'}><Icon name="download" size={14}/> 导出</a>:<button className="canvas-small-button" disabled><Icon name="download" size={14}/> 导出</button>}<button className="canvas-small-button" onClick={()=>project?setTab('team'):setShowRules(true)}><Icon name="team" size={15}/> 团队</button></>:<><span className="top-tagline">用 AI 让每一个游戏想法，都能变成可玩的作品。</span><button className="connection" onClick={()=>{setSettings(true);setNotice('');}}><i className={model.model?'':'offline'}/>{model.model?'模型已配置':'连接模型'}</button></>}</div>
        </header>}
        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button aria-label="关闭错误" onClick={() => setError("")}>
              <Icon name="close" />
            </button>
          </div>
        )}
        {!project ? (
          surface==='canvas'?<BlankCanvas onAction={launchAction} composer={composer} composing={composing} onCompose={()=>setComposing(true)} onClose={()=>setComposing(false)} onHelp={()=>setCanvasHelp(true)} onMaterials={()=>setMaterialModal(true)}/>:
          surface==='materials'?<section className="library-page"><div className="home-heading"><div><h1>材料库</h1><p>整理参考，让每次创作都有依据。</p></div></div><MaterialPicker value={materials} onChange={setMaterials} disabled={busy} onBusy={setUploadBusy}/>{materials.length>0&&<button className="primary" disabled={uploadBusy||busy} onClick={()=>{setSurface('canvas');setComposing(true);}}>用所选材料开始创作 <Icon name="arrow"/></button>}</section>:
          surface==='projects'?<section className="projects-page"><div className="home-heading"><div><h1>我的项目</h1><p>每一次灵感，都值得继续。</p></div><button className="primary" onClick={()=>reset('canvas')}><Icon name="plus"/> 新建项目</button></div><div className="project-filters"><input type="search" aria-label="搜索项目" placeholder="搜索作品…" value={search} onChange={e=>setSearch(e.target.value)}/><div role="group" aria-label="项目分类">{[['active','作品'],['archived','归档'],['trash','回收站']].map(([id,label])=><button key={id} aria-pressed={projectFilter===id} className={projectFilter===id?'active':''} onClick={()=>setProjectFilter(id)}>{label}</button>)}</div></div><div className="project-gallery">{filteredProjects.map((p,i)=><button key={p.id} className="gallery-project" onClick={()=>select(p.id)}><div className={'gallery-cover cover-'+i%4}><Icon name={p.active_version?'game':'folder'} size={46}/><span>{p.active_version?'可试玩':'创作中'}</span></div><strong>{p.title}</strong><small>{states[p.last_status||'']||'打开项目'} <Icon name="arrow" size={13}/></small></button>)}{!filteredProjects.length&&<p className="empty-projects">还没有匹配的项目。试试其他关键词，或新建一张画布。</p>}</div></section>:
          <HomeScreen onOpenNav={()=>setMobileNav(true)} projects={projects.filter(p=>(p.state||'active')==='active')} onOpen={select} onNew={()=>reset('canvas')} onAction={launchAction} onAll={()=>{setSurface('projects');setProjectFilter('active');}} composer={composer} examples={examples} onExample={value=>{setText(value);document.getElementById('brief')?.focus();}}/>
        ) : (
          <div className="workspace">
            {run && (pending||run.status==='failed') && <button className={"canvas-run-notice "+run.status} onClick={()=>setTab('flow')} aria-live="polite"><span className={"status-pill "+run.status}>{states[run.status]}</span><span>{run.status==='waiting_confirmation'?'团队正在等待你确认或答复':run.status==='failed'?'查看错误与执行记录':'查看八角色执行进度'}</span><Icon name="arrow" size={14}/></button>}
            {readOnly && <div className="project-readonly">此项目在{project.state==='trash'?'回收站':'归档'}中，恢复后可继续修改。<button onClick={()=>updateProject({state:'active'})} disabled={busy}>恢复项目</button></div>}
            <section className="flow-panel canvas-flow-inspector" hidden={tab!=='flow'} aria-label="玩法与执行日志"><div className="floating-heading"><strong>玩法与执行日志</strong><button aria-label="关闭执行日志" onClick={()=>setTab('preview')}><Icon name="close"/></button></div>
              <div className="panel-heading">
                <div>
                  <span className="eyebrow">YOUR AI CREW</span>
                  <h2>一起，把游戏做出来。</h2>
                </div>
                <span className={"status-pill " + run?.status}>
                  {run?.status==='waiting_confirmation'&&!run.plan?'等待答复':researchRun&&run?.status==='succeeded'?'调研完成':reviewRun&&run?.status==='succeeded'?'审查完成':docRun&&run?.status==='succeeded'?'文档完成':testRun&&run?.status==='succeeded'?'测试完成':states[run?.status || ""] || "准备中"}
                </span>
              </div>
              <TeamCrew events={run?.engine==='team8'?events:[]} status={run?.status||''} onSelect={role=>{setTeamRole(role);setTab('team');}}/>
              {run?.engine!=='team8' && <p className="legacy-team-note">此历史 / 直接调参记录未运行八角色。新的自然语言任务将使用八角色协作。</p>}
              <div className="conversation">
                <div className="request-card">
                  <small>你的需求</small>
                  <p>{run?.requirement}</p>
                </div>
                {run && <RunMaterials key={run.id} runId={run.id}/>}
                <TaskRoute events={events}/>
                {run?.status==='waiting_confirmation' && !run.plan && <div className="clarification-banner" role="status"><strong>团队需要你补充信息</strong><p>答复后重新策划，再次确认玩法才会继续执行。</p><button className="subtle" onClick={()=>setTab('messages')}>查看并答复</button></div>}
                {plan && (
                  <article className="plan-card">
                    <div className="card-label">
                      <b><Icon name="plan" size={14} /> {researchRun?'策划调研范围':reviewRun?'PM 审查范围':docRun?'PM 文档范围':testRun?'PM 测试范围':configRun?'PM 参数提案':'策划交付'}</b> <span>{researchRun?'方向调研':reviewRun?'静态审查':docRun?'文档':plan.mode}</span>
                    </div>
                    <h3>{plan.title}</h3>
                    <p>{plan.summary}</p>
                    <p className="controls">{testRun||docRun||reviewRun||researchRun?'执行方式':'操作'}：{plan.controls}</p>
                    {researchRun && researchScope && <div className="config-proposal"><strong>调研问题</strong><ul>{researchScope.scope.questions.map((q:{id:string;text:string})=><li key={q.id}>{q.text}</li>)}</ul><p>比较：{researchScope.scope.directions.map((d:{title:string})=>d.title).join(' / ')}</p><p>维度：{researchScope.scope.criteria.join('、')}</p><details><summary>确认后读取的公开网页（{researchScope.urls.length}）</summary>{researchScope.urls.map((url:string)=><p key={url}>{url}</p>)}</details>{!researchScope.urls.length&&<p className="inline-note">没有公开网页来源，将基于需求、材料和项目快照进行分析；假设需单独验证。</p>}</div>}
                    {reviewRun && reviewScope && <div className="config-proposal"><strong>审查版本 · {reviewScope.base_version.slice(0,8)}</strong><p>{reviewScope.scope.focus.join('、')}</p><ul>{reviewScope.scope.files.map((path:string)=><li key={path}>{path}</li>)}</ul><p className="inline-note">静态审查结果不代表游戏测试通过。调整范围请在协作消息中补充需求。</p></div>}
                    {docRun && docScope && <div className="config-proposal"><strong>本轮文档与章节</strong>{docScope.scope.documents.map((d:{id:string;title:string;sections:string[]})=><div key={d.id}><p>{d.title}</p><ol>{d.sections.map(h=><li key={h}>{h}</li>)}</ol></div>)}<p className="inline-note">调整文档范围请在协作消息中补充需求，再次确认后继续。</p></div>}
                    {testRun && testScope && <div className="config-proposal"><strong>测试版本 · {testScope.base_version.slice(0,8)}</strong><p>{testScope.scope.focus.join('、')}</p><details><summary>固定工具检查范围</summary><ul>{testScope.available_checks.map((name:string)=><li key={name}>{name}</li>)}</ul></details><p className="inline-note">其余需求需人工验证；本轮产出报告，游戏版本保持不变。调整范围请在消息中补充需求。</p></div>}
                    {configRun && configProposal && <div className="config-proposal"><strong>本轮参数变更</strong><div className="event-parameters">{Object.entries(configProposal.parameters||{}).map(([key,value])=>{const d=value as {before:unknown;after:unknown};return <div key={key}><span>{parameterLabels[key as keyof GameParameters]||key}</span><span>{String(d.before)} → {String(d.after)}</span></div>})}</div><p className="inline-note">其余参数与游戏规则保留。需调整提案时，请在「协作消息」补充需求并重新确认。</p></div>}
                    <p className="acceptance-label">{researchRun?'验收目标 · 由来源校验与制作人复核确认':reviewRun?'验收目标 · 由代码引用与角色复核确认':docRun?'验收目标 · 由引用校验与 PM 审阅确认':'验收目标 · 由后续测试与试玩确认'}</p>
                    <ul>
                      {plan.acceptance.map((a: string, i: number) => (
                        <li key={i}><Icon name="target" size={13} /><span>{a}</span></li>
                      ))}
                    </ul>
                    {run?.status === "waiting_confirmation" && (
                      <div className="decision-actions">
                        {!configRun && !testRun && !docRun && !reviewRun && !researchRun && <button className="subtle" disabled={busy || readOnly} onClick={()=>{setPlanSnapshot(run!.plan!);setEditingPlan(true);}}>编辑玩法</button>}
                        <button
                          className="primary"
                          disabled={busy || editingPlan || readOnly || (configRun&&!configProposal) || (testRun&&!testScope) || (docRun&&!docScope) || (reviewRun&&!reviewScope) || (researchRun&&!researchScope)}
                          onClick={() => decide(true)}
                        >
                          {researchRun?'确认范围，开始调研':reviewRun?'确认范围，开始审查':docRun?'确认范围，开始编写':testRun?'确认范围，开始测试':configRun?'确认参数，开始验证':'确认玩法，开始生成'} <Icon name="arrow" />
                        </button>
                        <button
                          className="subtle"
                          disabled={busy}
                          onClick={() => decide(false)}
                        >
                          退回修改
                        </button>
                      </div>
                    )}
                  </article>
                )}
                {events
                  .filter(
                    (e) =>
                      !["model_result", "queued", "plan_ready"].includes(
                        e.kind,
                      ),
                  )
                  .map((e) => (
                    <article key={e.id} className={"event-card " + e.kind}>
                      <div className="event-head">
                        <b>{e.role}</b>
                        <time>
                          {new Date(e.created_at).toLocaleTimeString("zh-CN", {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </time>
                      </div>
                      <p>
                        {e.payload.message ||
                          (e.kind === "test_result"
                            ? e.payload.passed
                              ? "实际构建与交互验证通过"
                              : "验证未通过，查看证据"
                            : e.kind)}
                      </p>
                      {e.payload.step_id && <button className="team-artifact-link" onClick={()=>{setTeamRole(e.role);setTab('team');}}>查看角色交付 <Icon name="arrow" size={12}/></button>}
                      {e.kind==='report_ready' && <button className="team-artifact-link" onClick={()=>setTab('tests')}>{researchRun?'查看调研报告':reviewRun?'查看审查报告':docRun?'查看文档':'查看测试报告'} <Icon name="arrow" size={12}/></button>}
                      {e.kind==='revision_requested' && <ul className="team-issues">{e.payload.issues?.map((issue:any,i:number)=><li key={i}><b>{issue.owner}</b>：{issue.description}<small>{issue.evidence}</small></li>)}</ul>}
                      {e.kind === "test_result" && (
                        <details>
                          <summary>查看运行证据</summary>
                          <pre>{JSON.stringify(e.payload, null, 2)}</pre>
                        </details>
                      )}
                      {e.payload.parameters && e.kind==='files_changed' && <div className="event-parameters">{Object.entries(e.payload.parameters).map(([key,value])=>{const delta=value as {before:unknown;after:unknown};return <div key={key}><span>{parameterLabels[key as keyof GameParameters] || key}</span><span>{String(delta.before)} → {String(delta.after)}</span></div>})}</div>}
                      {e.payload.files && (
                        <div className="file-chips">
                          {e.payload.files.map((f: string) => (
                            <span key={f}>{f}</span>
                          ))}
                        </div>
                      )}
                    </article>
                  ))}
                {run?.error && <div className="run-error">{run.error}</div>}
              </div>

            </section>
            <section className="artifact-panel">
              <div className="artifact-toolbar">
                <div className="tabs" role="tablist">
                  {[
                    ["preview", "进入试玩", "play"],
                    ["flow", "进度", "plan"],
                    ["materials", "材料", "image"],
                                        ["code", "源码", "code"],
                                        ["history", "版本", "history"],
                    ["parameters", "参数", "settings"],
                    ["tests", researchRun?"调研":reviewRun?"审查":docRun?"文档":"验证", "verified"],
                  ].map(([id, label, icon]) => (
                    <button
                      role="tab"
                      aria-selected={tab === id}
                      className={tab === id ? "active" : ""}
                      key={id}
                      onClick={() => setTab(id)}
                    >
                      <Icon name={icon as StudioIconName} size={14} /> {label}
                    </button>
                  ))}
                </div>
                {(testRun||docRun||reviewRun||researchRun) && run?.has_report ? <a className="export" href={'/api/runs/'+run.id+'/report/export'}><Icon name="download" size={14}/> 导出报告</a> : version && (
                  <a
                    className="export"
                    href={"/api/versions/" + version.id + "/export"}
                  >
                    <Icon name="download" size={14} /> 导出
                  </a>
                )}
              </div>
              <CanvasBoard key={project.id} projectId={project.id} title={version?.title||plan?.title||project.title} versionLabel={version?'V'+(project.versions.length-project.versions.findIndex(v=>v.id===version.id)):'待生成'} status={version?'可试玩':states[run?.status||'']||'准备中'} game={gamePreview} iteration={iteration} summary={plan?.summary||run?.requirement||''} controls={plan?.controls||''} onPanel={setTab} onHelp={()=>setCanvasHelp(true)}/>
              {tab!=='preview' && tab!=='flow' && <section className="canvas-inspector" role="region" aria-label={panelNames[tab]||'项目面板'}><div className="floating-heading"><strong>{panelNames[tab]||'项目面板'}</strong><button aria-label="关闭项目面板" onClick={()=>setTab('preview')}><Icon name="close"/></button></div><div className="inspector-body">
              {tab === 'materials' ? (<div className="panel-empty"><Icon name="image" size={30}/><h3>需求材料与参考</h3><p>上传文档、核对内容，再交给团队。</p><button className="primary" onClick={()=>setMaterialModal(true)}>打开材料库</button></div>) : tab === 'messages' ? (
                <MessagesPanel key={run?.id} runId={run?.id||''} revision={events.length} disabled={busy||readOnly} onChanged={()=>refresh(project.id)}/>
              ) : tab === 'team' ? (
                <TeamPanel key={run?.id} runId={run?.id||''} revision={events.length} role={teamRole} onRole={setTeamRole}/>
              ) : tab === 'diff' ? (
                <VersionCompare selection={comparisonSelection} onSelection={setComparisonSelection} key={project.id} projectId={project.id} versions={project.versions} activeVersion={project.active_version} onPreview={id=>perform(async()=>{await loadVersion(id);setTab('preview');})}/>
              ) : tab === 'parameters' ? (
                version?.parameters ? <ParameterPanel key={version.id} initial={version.parameters} disabled={pending || readOnly || version.id!==project.active_version} busy={busy} onSave={saveParameters}/> : <div className="panel-empty"><Icon name="settings" size={32}/><h3>从可玩版本开始调参</h3><p>{version?.parameter_error || '生成并验证第一个版本后，就能调整速度、生命与颜色。'}</p></div>
              ) : tab === 'tests' ? (
                researchRun && run ? <ResearchReport key={run.id} runId={run.id} status={run.status} revision={events.length} activeVersion={project.active_version} disabled={pending||readOnly} onChoose={d=>{setTaskType('feature');setReviewReference(null);setResearchUrls('');setResearchChoice({run_id:run.id,direction_id:d.id});setText('采用调研方向「'+d.title+'」制作网页游戏，先形成具体玩法与验收，再确认开发。');}}/> : reviewRun && run ? <CodeReviewReport key={run.id} runId={run.id} status={run.status} revision={events.length} activeVersion={project.active_version} disabled={pending||readOnly} onFix={()=>{setResearchChoice(null);setResearchUrls('');setTaskType('bugfix');setReviewReference(run.id);setText('根据所选代码审查报告，复核并修复尚未排除的问题，保留其他已确认的玩法规则。');}}/> : docRun && run ? <DocumentReport key={run.id} runId={run.id} status={run.status} revision={events.length}/> : testRun && run ? <TaskReport key={run.id} runId={run.id} status={run.status} revision={events.length} evidence={latestTest?.payload||null}/> : <TestResults evidence={latestTest?.payload || (run?.id===version?.run_id ? version?.evidence : null) || null} pending={!!run && active.includes(run.status)} label={latestTest ? '所选任务的最近一次实际验证' : run?.id===version?.run_id && version ? '所选版本保存的验证证据（复制版本沿用来源证据）' : '所选任务尚未产出测试结果'}/>
              ) : tab === "history" ? (
                <div className="history">
                  <div className="history-heading"><h3>每一步，都可以回来。</h3><button className="subtle" disabled={!project.versions.length} onClick={()=>setTab('diff')}><Icon name="diff" size={14}/> 对比版本</button></div>
                  {project.versions.length === 0 ? (
                    <p>第一个通过验证的版本会出现在这里。</p>
                  ) : (
                    project.versions.map((v, i) => (
                      <article key={v.id}>
                        <div>
                          <b>
                            V{project.versions.length - i} · {v.title}
                          </b>
                          <small>
                            {new Date(v.created_at).toLocaleString()}{" "}
                            {v.id === project.active_version
                              ? "· 当前版本"
                              : ""}
                          </small>
                        </div>
                        <div>
                          <button
                            onClick={() => {
                              loadVersion(v.id);
                              setTab("preview");
                            }}
                          >
                            查看
                          </button>
                          <button
                            disabled={
                              pending || readOnly || busy || v.id === project.active_version
                            }
                            onClick={() =>
                              perform(async () => {
                                await api(
                                  "/projects/" + project.id + "/rollback",
                                  { version_id: v.id },
                                );
                                await refresh(project.id);
                                await loadVersion(v.id);
                              })
                            }
                          >
                            回退
                          </button>
                        </div>
                      </article>
                    ))
                  )}
                  <h3>执行记录</h3>
                  {project.runs.map((r) => (
                    <button
                      className="run-link"
                      key={r.id}
                      onClick={() => setRunId(r.id)}
                    >
                      {r.task_type==='research'&&r.status==='succeeded'?'调研完成':r.task_type==='review'&&r.status==='succeeded'?'审查完成':r.task_type==='doc'&&r.status==='succeeded'?'文档完成':r.task_type==='test'&&r.status==='succeeded'?'测试完成':states[r.status]} · {r.requirement.slice(0, 32)}
                    </button>
                  ))}
                </div>
              ) : version ? (
                <>
                  {tab === "code" ? (
                    <div className="source-view">
                      <div className="file-tabs">
                        {Object.keys(version.files).map((f) => (
                          <button
                            className={file === f ? "active" : ""}
                            key={f}
                            onClick={() => setFile(f)}
                          >
                            {f}
                          </button>
                        ))}
                      </div>
                      <pre>{version.files[file]}</pre>
                    </div>
                  ) : (
                    <div className="panel-empty">请选择试玩、源码或对比视图。</div>
                  )}
                </>
              ) : (
<div className="panel-empty"><Icon name="code" size={32}/><h3>还没有可查看的源码</h3><p>生成并验证第一个版本后，源码会出现在这里。</p></div>
              )}
              </div></section>}

            </section>
          </div>
        )}
      </main>
      {materialModal&&<div className="modal-backdrop" onClick={()=>setMaterialModal(false)}><section className="modal canvas-material-modal" role="dialog" aria-modal="true" aria-labelledby="canvas-material-title" onClick={e=>e.stopPropagation()}><button className="modal-close" aria-label="关闭材料库" onClick={()=>setMaterialModal(false)}><Icon name="close"/></button><h2 id="canvas-material-title">材料与参考</h2><p>文档核对后可用于下一次需求。图片参考在画布左侧卡片中上传。</p><MaterialPicker value={materials} onChange={setMaterials} disabled={pending||readOnly||busy} onBusy={setUploadBusy}/><div className="modal-actions"><button className="primary" onClick={()=>setMaterialModal(false)}>完成</button></div></section></div>}
      {canvasHelp&&<div className="modal-backdrop" onClick={()=>setCanvasHelp(false)}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="canvas-help-title" onClick={e=>e.stopPropagation()}><button className="modal-close" aria-label="关闭画布帮助" onClick={()=>setCanvasHelp(false)}><Icon name="close"/></button><h2 id="canvas-help-title">在画布上，展开创意。</h2><p>双击空白画布或点击加号，添加创作需求。生成前会先请你确认玩法。</p><p>拖动卡片标题栏可调整位置；选择手掌工具后拖动空白区域可平移。底部可缩放或复位视图，小屏自动切换纵向布局。</p><p>顶部查看参数、源码、版本与验证；「进度」查看方案与错误，「团队」查看八角色真实交付，「消息」补充需求或答复澄清。</p><p>参考图片仅保存在当前浏览器。请在需求中描述风格要求，或上传并核对文档，再交给团队。</p></section></div>}
      {showSetup && <SetupGuide onClose={closeSetup} onSettings={()=>{setShowSetup(false);returnToSetup.current=true;setSettings(true);setNotice('');}} onSample={projects.some(p=>p.active_version && (p.state||'active')==='active')?()=>{closeSetup();setProjectFilter('active');setSearch('');select(projects.find(p=>p.active_version && (p.state||'active')==='active')!.id);}:undefined}/>}
      {manageProject && project && <ProjectManager error={error} key={project.id} project={project} busy={busy} pending={pending} onClose={()=>setManageProject(false)} onUpdate={updateProject} onDuplicate={duplicateProject}/>}
      {editingPlan && plan && <PlanEditor error={error} key={run!.id} plan={JSON.parse(planSnapshot)} busy={busy} onClose={()=>setEditingPlan(false)} onSave={savePlan}/>}
      {showRules && <RoleRulesModal onClose={()=>setShowRules(false)}/>}
      {settings && (
        <div className="modal-backdrop" onClick={closeSettings}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close"
              aria-label="关闭设置"
              onClick={closeSettings}
            >
              <Icon name="close" />
            </button>
            <div className="eyebrow">MODEL CONNECTION</div>
            <h2 id="settings-title">连接你的模型</h2>
            <p>
              使用 OpenAI 兼容接口。密钥仅保存在本机，不会进入生成游戏的容器。
            </p>
            <label>
              API 基础地址
              <input
                value={model.base_url}
                onChange={(e) =>
                  setModel({ ...model, base_url: e.target.value })
                }
              />
            </label>
            <label>
              模型名称
              <input
                placeholder="填写服务商提供的模型 ID"
                value={model.model}
                onChange={(e) => setModel({ ...model, model: e.target.value })}
              />
            </label>
            <label>
              API Key{" "}
              <span>{model.has_key ? "已保存 · 留空保留" : "尚未配置"}</span>
              <input
                type="password"
                autoComplete="off"
                value={model.api_key}
                onChange={(e) =>
                  setModel({ ...model, api_key: e.target.value })
                }
              />
            </label>
            <RoleModels/>
            <OpenGameSettings/>
            {notice && (
              <div className="notice" role="status">
                {notice}
              </div>
            )}
            {error && (
              <p role="alert" className="run-error">
                {error}
              </p>
            )}
            <div className="modal-actions">
              <button
                className="subtle"
                disabled={busy}
                onClick={() => saveModel()}
              >
                保存配置
              </button>
              <button
                className="primary"
                disabled={busy}
                onClick={() => saveModel(true)}
              >
                {busy ? "连接中…" : "保存并测试连接"} <Icon name="arrow" />
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
