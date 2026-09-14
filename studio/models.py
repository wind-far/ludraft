from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


RoleName = Literal['制作人', 'PM', '策划', '主程', '程序', '美术', 'UX', 'QA']


class AgentMessage(Strict):
    recipient: RoleName | Literal['all']
    content: str = Field(min_length=1, max_length=2000)


class AgentOutput(Strict):
    messages: list[AgentMessage] = Field(default_factory=list, max_length=3)
    clarification: str | None = Field(default=None, min_length=1, max_length=2000)


class UserMessage(Strict):
    content: str = Field(min_length=1, max_length=2000)
    reply_to: str | None = None


RequestType = Literal['auto', 'feature', 'bugfix', 'visual', 'optimize', 'config', 'test', 'doc', 'review', 'research']

class ResearchChoice(Strict):
    run_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    direction_id: str = Field(pattern=r'^[a-z][a-z0-9_-]{0,39}$')


class MaterialReference(Strict):
    upload_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    text: str = Field(min_length=1,max_length=20000)


class Requirement(Strict):
    research_urls: list[str] = Field(default_factory=list,max_length=5)
    research_choice: ResearchChoice | None = None
    code_review_id: str | None = Field(default=None,pattern=r'^[a-f0-9]{32}$')
    materials: list[MaterialReference] = Field(default_factory=list,max_length=8)
    task_type: RequestType = 'auto'
    text: str = Field(min_length=3, max_length=8000)


class Plan(AgentOutput):
    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(min_length=5, max_length=2000)
    mode: Literal["collector", "dodger", "clicker", "match3"]
    controls: str = Field(min_length=3, max_length=500)
    acceptance: list[str] = Field(min_length=3, max_length=12)


class FileChange(Strict):
    path: Literal["src/config.ts", "src/game.ts", "style.css"]
    content: str = Field(min_length=1, max_length=60000)


class Changes(AgentOutput):
    summary: str = Field(min_length=1, max_length=2000)
    files: list[FileChange] = Field(min_length=1, max_length=3)


class Decision(Strict):
    expected_scope_revision: str | None = None
    expected_config_revision: str | None = None
    expected_revision: int | None = None
    approve: bool
    expected_plan: str | None = None


class ModelSettings(Strict):
    base_url: str = Field(default="https://api.openai.com/v1", max_length=500)
    model: str = Field(default="", max_length=200)
    api_key: str = Field(default="", max_length=1000)
    clear_key: bool = False


class Rollback(Strict):
    version_id: str


class ProjectUpdate(Strict):
    title: str | None = Field(default=None, min_length=1, max_length=80)
    state: Literal['active', 'archived', 'trash'] | None = None


class PlanEdit(Strict):
    expected_revision: int | None = None
    plan: Plan
    expected_plan: str


class Parameters(Strict):
    speed: float = Field(gt=0, le=1500)
    lives: int = Field(ge=1, le=10, strict=True)
    spawnMs: float = Field(ge=100, le=10000)
    fallSpeed: float = Field(gt=0, le=1000)
    duration: float = Field(ge=5, le=600)
    background: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    playerColor: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    targetColor: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    hazardColor: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')


class Match3Parameters(Strict):
    moves: int = Field(ge=5,le=100,strict=True)
    targetScore: int = Field(ge=100,le=20000,strict=True)
    gemTypes: int = Field(ge=4,le=6,strict=True)
    background: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    playerColor: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    targetColor: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    hazardColor: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')


class ParameterEdit(Strict):
    base_version: str
    parameters: Parameters | Match3Parameters
