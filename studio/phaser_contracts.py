"""Trusted contracts for the first Phaser workflow, not a capability promotion."""
from .team_models import CodingTask, CodingPlan
from .models import AgentOutput, Strict
from .project_files import safe_name
from pydantic import Field, field_validator


CONTRACT = '''固定 Phaser 塔防候选工程，模板 phaser-tower_defense 版本 1。
玩法以已确认方案为准；固定路线、建塔、升级、金币、敌人波次、基地生命、胜负和重开。
先按工程清单读取现有配置、场景和实体实现，不假设上游 API 存在；业务扩展只在模板实际允许的文件内完成。
只能修改任务分配的 src/config.ts、src/gameConfig.json、style.css 或允许的 src/scenes/*.ts、src/entities/*.ts。
Base*、_Template*、固定 UI 场景、加载器、模板核心、依赖、构建、测试与工程/资源清单受保护。
保留素材键、未涉及的规则和现有文件；模型不直接返回整份工程，由受控工具原子应用明确增改删。
新增场景/实体必须接入实际游戏运行，新增机制明确持续时间、叠加和复位规则。
只使用已锁定的内置素材，不安装依赖，不访问外部网络。诊断通过不代表完整玩法验收。
同一工程串行编码；读取时分批选相关文件，收到真实失败诊断后有限修复，不虚构测试结果。'''

ROLE_RULES = {
    '策划': '围绕确认的固定路线塔防形成可观察规则和验收。超出模板扩展能力时请求澄清，不替换为 Canvas 玩法。',
    '主程': '围绕 Phaser 模板实际类与接口形成设计和编码分工；给每个任务具体可写文件、依赖与验收。不得分配受保护文件。',
    '美术': '定义已锁定内置图片的用途、层次、比例和反馈，不声称生成了新素材。',
    'UX': '定义 Phaser 场景中的操作、HUD、开始、胜负、重开及反馈；遵守固定 UI 与加载场景的保护范围。',
}


class ProjectCodingTask(CodingTask):
    files: list[str] = Field(min_length=1, max_length=50)

    @field_validator('files')
    @classmethod
    def paths(cls, paths):
        return [safe_name(path) for path in paths]


class ProjectCodingPlan(CodingPlan):
    tasks: list[ProjectCodingTask] = Field(min_length=1, max_length=12)


class ChangedFile(Strict):
    path: str
    operation: str
    before_sha256: str | None = None
    after_sha256: str | None = None


class CodeArtifact(AgentOutput):
    summary: str
    files: list[ChangedFile]
    source_digest: str
    execution_ids: list[str]
    gameplay_verified: bool = False
