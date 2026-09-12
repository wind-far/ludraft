"""
规则加载器 - 规则目录扫描与资产注册

核心职责:
- 扫描 rules/ 目录下所有规则资产
- 自动注册 Agent 入口文件
- 自动注册 Skill 文件
- 建立 Step/Template 关联索引
- 输出完整的 RuleInventory

目录结构预期:
rules/
├── rule.md                     # 全局规则
├── rule_*.md                   # 其他全局规则
├── agents/
│   ├── 00_制作人Agent.md       # Agent入口文件
│   ├── 00_制作人Agent/         # Agent子目录
│   │   ├── step-01_xxx.md      # 步骤文件
│   │   └── templates/          # 模板目录
│   │       └── xxx_template.md
│   ├── ...
│   └── 主从Agent架构.md        # 架构说明
└── skills/
    ├── architecture/           # 技能分类目录
    ├── csharp/
    ├── testing/
    └── unity/
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime

# 使用项目内的文件操作工具
from utils.file_ops import (
    safe_read, scan_directory, parse_frontmatter,
    extract_title, get_file_info
)


@dataclass
class AgentSpec:
    """Agent规格说明（从规则文件解析）"""
    agent_id: str = ""
    agent_name: str = ""
    entry_file: str = ""          # 入口文件相对路径
    directory: str = ""           # 子目录相对路径
    steps: List[str] = field(default_factory=list)       # step文件列表
    templates: List[str] = field(default_factory=list)   # 模板文件列表
    title: str = ""
    description: str = ""
    file_count: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SkillSpec:
    """技能规格说明"""
    skill_id: str = ""
    skill_name: str = ""
    category: str = ""            # 技能分类
    file_path: str = ""           # 文件相对路径
    title: str = ""
    description: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RuleSpec:
    """全局规则说明"""
    rule_id: str = ""
    rule_name: str = ""
    file_path: str = ""
    title: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RuleInventory:
    """
    规则资产清单 - 完整的规则目录索引结果

    包含:
    - agents: Agent注册表
    - skills: 技能注册表
    - rules: 全局规则列表
    - steps: 步骤文件索引
    - templates: 模板文件索引
    - statistics: 统计摘要
    """
    agents: Dict[str, AgentSpec] = field(default_factory=dict)
    skills: Dict[str, SkillSpec] = field(default_factory=dict)
    rules: List[RuleSpec] = field(default_factory=list)
    scan_time: str = ""
    source_root: str = ""

    def __post_init__(self):
        if not self.scan_time:
            self.scan_time = datetime.now().isoformat()

    @property
    def statistics(self) -> Dict[str, int]:
        """统计摘要"""
        total_steps = sum(len(a.steps) for a in self.agents.values())
        total_templates = sum(len(a.templates) for a in self.agents.values())
        return {
            "total_agents": len(self.agents),
            "total_skills": len(self.skills),
            "total_rules": len(self.rules),
            "total_steps": total_steps,
            "total_templates": total_templates,
            "total_files": (
                len(self.agents) + len(self.skills) +
                len(self.rules) + total_steps + total_templates
            )
        }

    def to_dict(self) -> dict:
        return {
            "agents": {k: v.to_dict() for k, v in self.agents.items()},
            "skills": {k: v.to_dict() for k, v in self.skills.items()},
            "rules": [r.to_dict() for r in self.rules],
            "statistics": self.statistics,
            "scan_time": self.scan_time,
            "source_root": self.source_root
        }

    def get_summary_text(self) -> str:
        """生成可读摘要"""
        stats = self.statistics
        lines = [
            "=" * 60,
            "📦 OpenClaw 规则资产清单",
            "=" * 60,
            f"📂 扫描目录: {self.source_root}",
            f"🕐 扫描时间: {self.scan_time}",
            "",
            "📊 统计摘要:",
            f"  • Agent数量:   {stats['total_agents']}",
            f"  • 技能包数量:  {stats['total_skills']}",
            f"  • 全局规则:    {stats['total_rules']}",
            f"  • 步骤文件:    {stats['total_steps']}",
            f"  • 模板文件:    {stats['total_templates']}",
            f"  • 总文件数:    {stats['total_files']}",
            "",
            "🤖 Agent注册表:",
        ]

        for agent_id, agent in sorted(self.agents.items()):
            lines.append(
                f"  [{agent_id}] {agent.agent_name}"
                f" | steps={len(agent.steps)}"
                f" | templates={len(agent.templates)}"
            )

        lines.append("")
        lines.append("🎯 技能包注册表:")
        for skill_id, skill in sorted(self.skills.items()):
            lines.append(f"  [{skill.category}] {skill.skill_name}")

        lines.append("")
        lines.append("📜 全局规则:")
        for rule in self.rules:
            lines.append(f"  • {rule.rule_name}: {rule.title}")

        lines.append("=" * 60)
        return "\n".join(lines)


class RuleLoader:
    """
    规则加载器

    扫描 rules/ 目录，解析所有规则资产，
    建立完整索引供运行时使用。
    """

    # Agent入口文件命名模式: XX_名称Agent.md
    AGENT_ENTRY_PATTERN = re.compile(r'^(\d{2})_(.+Agent)\.md$')

    # Agent子目录命名模式: XX_名称Agent/
    AGENT_DIR_PATTERN = re.compile(r'^(\d{2})_(.+Agent)$')

    # Step文件命名模式: step-XX_描述.md
    STEP_FILE_PATTERN = re.compile(r'^step-(\d{2})_(.+)\.md$')

    def __init__(self, rules_root: str):
        """
        初始化规则加载器

        Args:
            rules_root: 规则目录根路径（绝对路径或相对路径）
        """
        self.rules_root = Path(rules_root).resolve()
        self._inventory: Optional[RuleInventory] = None

    def scan_all(self) -> RuleInventory:
        """
        执行完整扫描，建立资产清单

        Returns:
            RuleInventory 完整资产清单
        """
        inventory = RuleInventory(source_root=str(self.rules_root))

        # 依次扫描各类资产
        self._scan_global_rules(inventory)
        self._scan_agents(inventory)
        self._scan_skills(inventory)

        self._inventory = inventory
        return inventory

    def _scan_global_rules(self, inventory: RuleInventory):
        """扫描全局规则文件"""
        if not self.rules_root.exists():
            return

        for md_file in sorted(self.rules_root.glob("rule*.md")):
            if md_file.is_file():
                content = safe_read(md_file) or ""
                title = extract_title(content)

                rule = RuleSpec(
                    rule_id=md_file.stem,
                    rule_name=md_file.name,
                    file_path=str(md_file.relative_to(self.rules_root)),
                    title=title
                )
                inventory.rules.append(rule)

    def _scan_agents(self, inventory: RuleInventory):
        """扫描Agent入口文件和子目录"""
        agents_dir = self.rules_root / "agents"
        if not agents_dir.exists():
            return

        # 1. 扫描Agent入口文件
        for md_file in sorted(agents_dir.glob("*.md")):
            match = self.AGENT_ENTRY_PATTERN.match(md_file.name)
            if not match:
                # 非标准Agent入口（如 主从Agent架构.md），跳过
                continue

            agent_num = match.group(1)
            agent_name = match.group(2)
            agent_id = f"{agent_num}_{agent_name}"

            content = safe_read(md_file) or ""
            title = extract_title(content)

            spec = AgentSpec(
                agent_id=agent_id,
                agent_name=agent_name,
                entry_file=str(md_file.relative_to(self.rules_root)),
                title=title
            )

            # 2. 检查是否有对应子目录
            agent_dir = agents_dir / agent_id
            if agent_dir.exists() and agent_dir.is_dir():
                spec.directory = str(agent_dir.relative_to(self.rules_root))
                self._scan_agent_steps(spec, agent_dir)
                self._scan_agent_templates(spec, agent_dir)
                spec.file_count = 1 + len(spec.steps) + len(spec.templates)
            else:
                spec.file_count = 1

            inventory.agents[agent_id] = spec

    def _scan_agent_steps(self, spec: AgentSpec, agent_dir: Path):
        """扫描Agent的步骤文件"""
        for step_file in sorted(agent_dir.glob("step-*.md")):
            if step_file.is_file():
                rel_path = str(step_file.relative_to(self.rules_root))
                spec.steps.append(rel_path)

    def _scan_agent_templates(self, spec: AgentSpec, agent_dir: Path):
        """扫描Agent的模板文件"""
        templates_dir = agent_dir / "templates"
        if not templates_dir.exists():
            return

        for tmpl_file in sorted(templates_dir.rglob("*.md")):
            if tmpl_file.is_file():
                rel_path = str(tmpl_file.relative_to(self.rules_root))
                spec.templates.append(rel_path)

    def _scan_skills(self, inventory: RuleInventory):
        """扫描技能包目录"""
        skills_dir = self.rules_root / "skills"
        if not skills_dir.exists():
            return

        # 遍历技能分类目录
        for category_dir in sorted(skills_dir.iterdir()):
            if not category_dir.is_dir():
                continue

            category = category_dir.name

            # 扫描分类下的所有md文件
            for skill_file in sorted(category_dir.rglob("*.md")):
                if skill_file.is_file():
                    content = safe_read(skill_file) or ""
                    title = extract_title(content)
                    rel_path = str(skill_file.relative_to(self.rules_root))

                    skill_id = f"{category}/{skill_file.stem}"
                    spec = SkillSpec(
                        skill_id=skill_id,
                        skill_name=skill_file.stem,
                        category=category,
                        file_path=rel_path,
                        title=title
                    )
                    inventory.skills[skill_id] = spec

    def get_inventory(self) -> Optional[RuleInventory]:
        """获取已扫描的资产清单"""
        return self._inventory

    def get_agent_spec(self, agent_id: str) -> Optional[AgentSpec]:
        """获取指定Agent的规格说明"""
        if self._inventory:
            return self._inventory.agents.get(agent_id)
        return None

    def get_agent_steps(self, agent_id: str) -> List[str]:
        """获取指定Agent的所有步骤文件路径"""
        spec = self.get_agent_spec(agent_id)
        return spec.steps if spec else []

    def get_agent_templates(self, agent_id: str) -> List[str]:
        """获取指定Agent的所有模板文件路径"""
        spec = self.get_agent_spec(agent_id)
        return spec.templates if spec else []

    def load_agent_entry_content(self, agent_id: str) -> Optional[str]:
        """读取Agent入口文件内容"""
        spec = self.get_agent_spec(agent_id)
        if not spec:
            return None
        return safe_read(self.rules_root / spec.entry_file)

    def load_step_content(self, step_path: str) -> Optional[str]:
        """读取步骤文件内容"""
        return safe_read(self.rules_root / step_path)

    def load_template_content(self, template_path: str) -> Optional[str]:
        """读取模板文件内容"""
        return safe_read(self.rules_root / template_path)

    def load_skill_content(self, skill_id: str) -> Optional[str]:
        """读取技能包内容"""
        if not self._inventory:
            return None
        skill = self._inventory.skills.get(skill_id)
        if not skill:
            return None
        return safe_read(self.rules_root / skill.file_path)

    def validate_inventory(self) -> List[str]:
        """
        验证资产清单完整性

        Returns:
            问题列表（空列表表示无问题）
        """
        issues = []

        if not self._inventory:
            issues.append("未执行扫描，请先调用 scan_all()")
            return issues

        # 检查Agent入口文件是否都存在
        for agent_id, spec in self._inventory.agents.items():
            entry_path = self.rules_root / spec.entry_file
            if not entry_path.exists():
                issues.append(f"Agent {agent_id} 入口文件不存在: {spec.entry_file}")

            # 检查步骤文件
            for step in spec.steps:
                step_path = self.rules_root / step
                if not step_path.exists():
                    issues.append(f"Agent {agent_id} 步骤文件不存在: {step}")

            # 检查模板文件
            for tmpl in spec.templates:
                tmpl_path = self.rules_root / tmpl
                if not tmpl_path.exists():
                    issues.append(f"Agent {agent_id} 模板文件不存在: {tmpl}")

        # 检查技能文件
        for skill_id, spec in self._inventory.skills.items():
            skill_path = self.rules_root / spec.file_path
            if not skill_path.exists():
                issues.append(f"技能 {skill_id} 文件不存在: {spec.file_path}")

        return issues
