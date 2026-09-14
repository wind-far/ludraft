"""Contracts for the eight-role workflow; model output cannot redefine tool gates."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .models import Strict, AgentOutput, Parameters, Match3Parameters

Text = Annotated[str, Field(min_length=1, max_length=2000)]
DesignKey = Literal['tech', 'art', 'ux']
WorkType = Literal['feature', 'bugfix', 'visual', 'optimize', 'config', 'test', 'doc', 'review', 'research']
Role = Literal['制作人', 'PM', '策划', '主程', '程序', '美术', 'UX', 'QA']
TaskKey = Literal['tech', 'art', 'ux', 'code', 'qa']
OWNERS = {'tech':'主程', 'art':'美术', 'ux':'UX', 'code':'程序', 'qa':'QA'}

class Brief(AgentOutput):
    task_type: WorkType = 'feature'
    routing_reason: Text = '按完整功能流程处理'
    summary: Text
    scope: list[Text] = Field(min_length=1, max_length=10)
    constraints: list[Text] = Field(min_length=1, max_length=10)
    risks: list[Text] = Field(max_length=10)

class ConfigProposal(AgentOutput):
    summary: Text
    parameters: Match3Parameters | Parameters
    acceptance: list[Text] = Field(min_length=3,max_length=8)

class TestScope(AgentOutput):
    summary: Text
    focus: list[Text] = Field(min_length=1,max_length=12)
    acceptance: list[Text] = Field(min_length=3,max_length=8)
    manual_checks: list[Text] = Field(max_length=12)

DocId = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]{0,39}$')]
Heading = Annotated[str, Field(min_length=1,max_length=120)]

class DocumentTarget(Strict):
    id: DocId
    title: Heading
    sections: list[Heading] = Field(min_length=1,max_length=8)

    @model_validator(mode='after')
    def headings(self):
        if any(not value.strip() or '\n' in value or '\r' in value for value in [self.title,*self.sections]):
            raise ValueError('文档标题与章节必须为非空单行文本')
        return self

class DocumentScope(AgentOutput):
    title: Annotated[str,Field(min_length=1,max_length=80)]
    summary: Text
    documents: list[DocumentTarget] = Field(min_length=1,max_length=3)
    acceptance: list[Text] = Field(min_length=3,max_length=8)

    @model_validator(mode='after')
    def distinct(self):
        if len({d.id for d in self.documents})!=len(self.documents):raise ValueError('文档编号不能重复')
        if any(len(set(d.sections))!=len(d.sections) for d in self.documents):raise ValueError('章节不能重复')
        return self

class Citation(Strict):
    source_id: Annotated[str,Field(min_length=1,max_length=240)]
    start: Annotated[int,Field(ge=1,le=20000,strict=True)]
    end: Annotated[int,Field(ge=1,le=20000,strict=True)]
    quote: Annotated[str,Field(min_length=1,max_length=1000)]

class DocumentSection(Strict):
    heading: Heading
    kind: Literal['fact','proposal']
    body: Annotated[str,Field(min_length=1,max_length=4000)]
    citations: list[Citation] = Field(max_length=6)

class DocumentArtifact(Strict):
    id: DocId
    title: Heading
    sections: list[DocumentSection] = Field(min_length=1,max_length=8)

class DocumentBundle(AgentOutput):
    summary: Text
    documents: list[DocumentArtifact] = Field(min_length=1,max_length=3)

    @model_validator(mode='after')
    def distinct(self):
        if len({d.id for d in self.documents})!=len(self.documents):raise ValueError('文档编号不能重复')
        return self

class DocumentReview(AgentOutput):
    summary: Text
    accepted: bool
    issues: list[Text] = Field(max_length=12)
    limitations: list[Text] = Field(max_length=12)


class ReviewScope(AgentOutput):
    summary: Text
    files: list[Heading] = Field(min_length=1,max_length=20)
    focus: list[Text] = Field(min_length=1,max_length=8)
    acceptance: list[Text] = Field(min_length=3,max_length=8)

class ReviewCoverage(Strict):
    path: Heading
    summary: Text
    citations: list[Citation] = Field(min_length=1,max_length=4)

class ReviewFinding(Strict):
    id: DocId
    title: Heading
    severity: Literal['blocking','suggestion']
    description: Text
    impact: Text
    recommendation: Text
    citations: list[Citation] = Field(min_length=1,max_length=4)

class CodeAudit(AgentOutput):
    summary: Text
    coverage: list[ReviewCoverage] = Field(min_length=1,max_length=20)
    findings: list[ReviewFinding] = Field(max_length=20)
    limitations: list[Text] = Field(max_length=12)

class FindingResponse(Strict):
    finding_id: DocId
    position: Literal['agree','dispute']
    reason: Text
    suggestion: Text
    citations: list[Citation] = Field(min_length=1,max_length=4)

class AuditResponse(AgentOutput):
    summary: Text
    responses: list[FindingResponse] = Field(max_length=20)

class FindingDecision(Strict):
    finding_id: DocId
    decision: Literal['confirmed','dismissed','unresolved']
    reason: Text
    citations: list[Citation] = Field(min_length=1,max_length=4)

class AuditVerdict(AgentOutput):
    summary: Text
    accepted: bool
    decisions: list[FindingDecision] = Field(max_length=20)
    limitations: list[Text] = Field(max_length=12)

class ResearchQuestion(Strict):
    id: DocId
    text: Text

class ResearchDirection(Strict):
    id: DocId
    title: Heading
    summary: Text

class ResearchScope(AgentOutput):
    title: Annotated[str,Field(min_length=1,max_length=80)]
    summary: Annotated[str,Field(min_length=5,max_length=2000)]
    questions: list[ResearchQuestion] = Field(min_length=1,max_length=6)
    directions: list[ResearchDirection] = Field(min_length=2,max_length=4)
    criteria: list[Heading] = Field(min_length=2,max_length=6)
    acceptance: list[Text] = Field(min_length=3,max_length=8)

    @model_validator(mode='after')
    def distinct(self):
        texts=[self.title,self.summary,*self.criteria,*self.acceptance,*[q.text for q in self.questions],*[d.title for d in self.directions],*[d.summary for d in self.directions]]
        if any(not text.strip() for text in texts):raise ValueError('调研范围不能包含空白内容')
        for values in ([q.id for q in self.questions],[d.id for d in self.directions],self.criteria):
            if len(values)!=len(set(values)):raise ValueError('调研范围编号与比较维度不能重复')
        return self

class ResearchStatement(Strict):
    kind: Literal['fact','inference','hypothesis']
    text: Text
    citations: list[Citation] = Field(max_length=6)

class ResearchAnswer(Strict):
    question_id: DocId
    statement: ResearchStatement

class DirectionAssessment(Strict):
    criterion: Heading
    statement: ResearchStatement

class ComparedDirection(ResearchDirection):
    assessments: list[DirectionAssessment] = Field(min_length=2,max_length=6)
    next_steps: list[Text] = Field(min_length=1,max_length=6)

class ResearchBacklog(Strict):
    title: Heading
    priority: Literal['must','should','could']
    rationale: Text
    validation: Text

class ResearchResult(AgentOutput):
    summary: Text
    answers: list[ResearchAnswer] = Field(min_length=1,max_length=6)
    directions: list[ComparedDirection] = Field(min_length=2,max_length=4)
    recommendation: DocId
    rationale: ResearchStatement
    backlog: list[ResearchBacklog] = Field(min_length=1,max_length=10)
    unknowns: list[Text] = Field(max_length=12)

class ResearchReview(AgentOutput):
    summary: Text
    accepted: bool
    issues: list[Text] = Field(max_length=12)
    limitations: list[Text] = Field(max_length=12)

class Task(Strict):
    key: TaskKey
    goal: Text
    depends_on: list[TaskKey] = Field(max_length=4)
    acceptance: list[Text] = Field(min_length=1, max_length=8)

class TaskBoard(AgentOutput):
    design_updates: list[DesignKey] = Field(default_factory=list, max_length=3)
    summary: Text
    tasks: list[Task] = Field(min_length=5, max_length=5)

    @model_validator(mode='after')
    def dependencies(self):
        tasks = {t.key:t for t in self.tasks}
        if len(tasks)!=5:
            raise ValueError('PM 必须为 tech、art、ux、code、qa 各安排一项任务')
        for task in self.tasks:
            if len(set(task.depends_on)) != len(task.depends_on):
                raise ValueError('任务依赖不能重复')
        if not {'tech','art','ux'}.issubset(tasks['code'].depends_on) or 'code' not in tasks['qa'].depends_on:
            raise ValueError('程序必须等待三方设计交付，QA 必须等待代码交付')
        completed=set()
        while len(completed)<5:
            ready={key for key,t in tasks.items() if key not in completed and set(t.depends_on)<=completed}
            if not ready:raise ValueError('任务依赖存在循环或无法执行')
            completed.update(ready)
        return self

class Design(AgentOutput):
    summary: Text
    decisions: list[Text] = Field(min_length=1, max_length=12)
    acceptance: list[Text] = Field(min_length=1, max_length=12)

class Issue(Strict):
    owner: Literal['主程', '程序', '美术', 'UX']
    severity: Literal['blocking', 'suggestion']
    description: Text
    evidence: Text

class Review(AgentOutput):
    summary: Text
    issues: list[Issue] = Field(max_length=15)

class TestStrategy(AgentOutput):
    summary: Text
    focus: list[Text] = Field(min_length=1, max_length=12)
    manual_checks: list[Text] = Field(max_length=12)

class QAReport(Review):
    manual_checks: list[Text] = Field(max_length=12)

class Delivery(AgentOutput):
    summary: Text
    ready: bool
    limitations: list[Text] = Field(max_length=12)

class TeamModels(Strict):
    models: dict[Role, Annotated[str, Field(max_length=200)]]


class CodingTask(Strict):
    id: Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]{0,39}$')]
    goal: Text
    files: list[Literal['src/config.ts','src/game.ts','style.css']] = Field(min_length=1,max_length=3)
    depends_on: list[Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]{0,39}$')]] = Field(max_length=11)
    acceptance: list[Text] = Field(min_length=1,max_length=8)


class CodingPlan(AgentOutput):
    summary: Text
    tasks: list[CodingTask] = Field(min_length=1,max_length=12)

    @model_validator(mode='after')
    def graph(self):
        tasks={t.id:t for t in self.tasks}
        if len(tasks)!=len(self.tasks):raise ValueError('编码子任务 ID 不能重复')
        completed=set();ancestors={}
        while len(completed)<len(tasks):
            ready=[t for t in self.tasks if t.id not in completed and set(t.depends_on)<=completed]
            if not ready:raise ValueError('编码子任务依赖缺失或存在循环')
            for task in ready:
                if len(set(task.files))!=len(task.files) or len(set(task.depends_on))!=len(task.depends_on):
                    raise ValueError('文件归属与依赖不能重复')
                ancestors[task.id]=set(task.depends_on)
                for dependency in task.depends_on:ancestors[task.id].update(ancestors[dependency])
                completed.add(task.id)
        for index,a in enumerate(self.tasks):
            for b in self.tasks[index+1:]:
                if set(a.files)&set(b.files) and a.id not in ancestors[b.id] and b.id not in ancestors[a.id]:
                    raise ValueError('修改同一文件的子任务必须通过依赖串行执行')
        return self
