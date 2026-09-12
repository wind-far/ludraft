"""
CodeBuddy Team Mode 适配器 - 将多Agent系统映射为CodeBuddy团队模式

核心职责:
- 将系统内Agent定义映射到CodeBuddy Team Mode的spawn/send_message协议
- 管理Agent生命周期（启动、通信、关闭）
- 将内部消息队列桥接到CodeBuddy的团队通信
- 提供Agent状态的统一视图

映射关系:
- 系统Agent → CodeBuddy Team Member（通过 Task tool 的 name 参数）
- 消息队列消息 → send_message 调用
- 流水线步骤 → 团队成员的任务 prompt
- 并行组 → 并行的 Task tool 调用
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from adapters.rule_loader import RuleLoader, RuleInventory, AgentSpec


@dataclass
class TeamMemberSpec:
    """
    CodeBuddy 团队成员定义

    映射到 CodeBuddy Task tool 的参数:
    - name → 团队成员名称
    - subagent_name → 使用的子Agent类型
    - prompt → 任务指令
    """
    member_name: str = ""         # 团队成员名称（用于spawn）
    display_name: str = ""        # 显示名称（含emoji）
    agent_id: str = ""            # 内部Agent ID
    subagent_path: str = ""       # .codebuddy/agents/ 下的文件路径
    role: str = ""                # 角色描述
    parallel_group: str = ""      # 并行组
    tools: List[str] = field(default_factory=list)  # 可用工具
    mode: str = "default"         # 权限模式: acceptEdits/bypassPermissions/default/plan

    def to_dict(self) -> dict:
        return asdict(self)

    def to_task_params(self, prompt: str, team_name: str = "") -> Dict[str, Any]:
        """
        生成 CodeBuddy Task tool 的调用参数

        Args:
            prompt: 任务指令
            team_name: 团队名称

        Returns:
            Task tool 参数字典
        """
        params = {
            "name": self.member_name,
            "subagent_name": self.member_name,
            "subagent_path": self.subagent_path,
            "prompt": prompt,
            "mode": self.mode,
            "description": f"{self.display_name} 执行任务"
        }
        if team_name:
            params["team_name"] = team_name
        return params


@dataclass
class TeamMessage:
    """
    CodeBuddy 团队消息

    映射到 send_message tool 的参数
    """
    msg_type: str = "message"     # message/broadcast/shutdown_request
    sender: str = ""              # 发送方成员名称
    recipient: str = ""           # 接收方成员名称（广播时为空）
    content: str = ""             # 消息内容
    summary: str = ""             # 消息摘要（5-10字）

    def to_send_params(self) -> Dict[str, Any]:
        """生成 send_message 参数"""
        params = {
            "type": self.msg_type,
            "content": self.content,
            "summary": self.summary
        }
        if self.recipient:
            params["recipient"] = self.recipient
        return params


@dataclass
class TeamConfig:
    """团队配置"""
    team_name: str = "openclaw-gamedev"
    description: str = "OpenClaw 多智能体游戏开发团队"
    max_members: int = 8
    members: Dict[str, TeamMemberSpec] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class CodeBuddyAdapter:
    """
    CodeBuddy Team Mode 适配器

    将多Agent系统的概念映射到CodeBuddy Team Mode:

    内部概念              CodeBuddy概念
    ─────────────────────────────────────
    Agent                → Team Member
    并行组(parallel)     → 并行Task调用
    消息队列             → send_message
    流水线步骤           → Task prompt
    Agent沙盒            → Member工作目录
    质量门禁             → Member间消息确认
    """

    # Agent ID → CodeBuddy Agent 定义文件映射
    AGENT_FILE_MAP = {
        "00_制作人Agent": "00_producer.md",
        "01_项目管理Agent": "01_pm.md",
        "02_策划Agent": "02_planner.md",
        "03_主程Agent": "03_tech_lead.md",
        "04_程序Agent": "04_programmer.md",
        "05_美术Agent": "05_artist.md",
        "06_QAAgent": "06_qa.md",
        "07_UXAgent": "07_ux.md",
    }

    # Agent 显示名映射
    AGENT_DISPLAY_MAP = {
        "00_制作人Agent": "制作人老梁 🎬",
        "01_项目管理Agent": "PM小李 📊",
        "02_策划Agent": "策划小张 📋",
        "03_主程Agent": "主程老陈 🔧",
        "04_程序Agent": "程序小赵 💻",
        "05_美术Agent": "美术小周 🎨",
        "06_QAAgent": "QA小吴 🧪",
        "07_UXAgent": "UX小林 ✨",
    }

    # 并行组定义
    PARALLEL_GROUPS = {
        "control": {
            "execution": "sequential",
            "members": ["00_制作人Agent", "01_项目管理Agent"]
        },
        "design": {
            "execution": "parallel",
            "members": ["02_策划Agent", "07_UXAgent", "05_美术Agent"]
        },
        "architecture": {
            "execution": "sequential",
            "members": ["03_主程Agent"]
        },
        "implementation": {
            "execution": "parallel",
            "members": ["04_程序Agent"]
        },
        "verification": {
            "execution": "parallel",
            "members": ["06_QAAgent"]
        }
    }

    def __init__(self, project_root: str,
                 codebuddy_agents_dir: str = ".codebuddy/agents"):
        """
        初始化适配器

        Args:
            project_root: 项目根目录
            codebuddy_agents_dir: CodeBuddy agent定义目录
        """
        self.project_root = Path(project_root)
        self.agents_dir = self.project_root / codebuddy_agents_dir
        self._team_config: Optional[TeamConfig] = None
        self._rule_loader: Optional[RuleLoader] = None

    def initialize(self, rule_loader: Optional[RuleLoader] = None) -> TeamConfig:
        """
        初始化团队配置

        读取 .codebuddy/agents/ 下的Agent定义，
        生成完整的团队成员注册表

        Args:
            rule_loader: 可选的规则加载器

        Returns:
            TeamConfig 团队配置
        """
        self._rule_loader = rule_loader
        config = TeamConfig()

        for agent_id, agent_file in self.AGENT_FILE_MAP.items():
            agent_path = self.agents_dir / agent_file

            # 确定并行组
            group = self._find_parallel_group(agent_id)

            member = TeamMemberSpec(
                member_name=agent_file.replace(".md", ""),
                display_name=self.AGENT_DISPLAY_MAP.get(agent_id, agent_id),
                agent_id=agent_id,
                subagent_path=str(agent_path) if agent_path.exists() else "",
                role=self._get_agent_role(agent_id),
                parallel_group=group,
                tools=self._get_agent_tools(agent_id),
                mode=self._get_agent_mode(agent_id)
            )

            config.members[agent_id] = member

        self._team_config = config
        return config

    def _find_parallel_group(self, agent_id: str) -> str:
        """查找Agent所属并行组"""
        for group_name, group_def in self.PARALLEL_GROUPS.items():
            if agent_id in group_def["members"]:
                return group_name
        return "unknown"

    def _get_agent_role(self, agent_id: str) -> str:
        """获取Agent角色描述"""
        roles = {
            "00_制作人Agent": "需求入口与分类路由",
            "01_项目管理Agent": "需求管理与进度监控",
            "02_策划Agent": "策划案编写与验收标准定义",
            "03_主程Agent": "技术评审与架构设计",
            "04_程序Agent": "代码实现与Bug修复",
            "05_美术Agent": "UI设计与美术需求",
            "06_QAAgent": "自动化测试与Bug报告",
            "07_UXAgent": "交互设计与界面布局",
        }
        return roles.get(agent_id, "")

    def _get_agent_tools(self, agent_id: str) -> List[str]:
        """获取Agent可用工具列表"""
        # 根据 .codebuddy/agents/ 中的 frontmatter tools 字段
        tools_map = {
            "00_制作人Agent": ["read_file", "search_content", "list_dir"],
            "01_项目管理Agent": ["read_file", "write_to_file", "search_content", "list_dir"],
            "02_策划Agent": ["read_file", "write_to_file", "search_content", "list_dir",
                           "replace_in_file"],
            "03_主程Agent": ["read_file", "write_to_file", "search_content", "list_dir",
                           "replace_in_file", "execute_command"],
            "04_程序Agent": ["read_file", "write_to_file", "search_content", "list_dir",
                           "replace_in_file", "execute_command"],
            "05_美术Agent": ["read_file", "write_to_file", "list_dir"],
            "06_QAAgent": ["read_file", "write_to_file", "search_content", "list_dir",
                          "replace_in_file", "execute_command"],
            "07_UXAgent": ["read_file", "write_to_file", "search_content", "list_dir"],
        }
        return tools_map.get(agent_id, [])

    def _get_agent_mode(self, agent_id: str) -> str:
        """获取Agent的权限模式"""
        # 控制层Agent使用 plan 模式（只读为主）
        # 其他Agent使用 acceptEdits 模式
        if agent_id in ("00_制作人Agent",):
            return "plan"
        elif agent_id in ("01_项目管理Agent",):
            return "default"
        else:
            return "acceptEdits"

    def generate_team_create_params(self) -> Dict[str, Any]:
        """
        生成 team_create 工具的调用参数

        Returns:
            team_create 参数字典
        """
        if not self._team_config:
            self.initialize()

        return {
            "team_name": self._team_config.team_name,
            "description": self._team_config.description
        }

    def generate_spawn_params(self, agent_id: str, prompt: str,
                               max_turns: int = 20) -> Dict[str, Any]:
        """
        生成 Task tool（团队模式）的调用参数

        Args:
            agent_id: Agent ID
            prompt: 任务指令
            max_turns: 最大对话轮数

        Returns:
            Task tool 参数字典
        """
        if not self._team_config:
            self.initialize()

        member = self._team_config.members.get(agent_id)
        if not member:
            raise ValueError(f"未知的Agent: {agent_id}")

        params = member.to_task_params(
            prompt=prompt,
            team_name=self._team_config.team_name
        )
        params["max_turns"] = max_turns
        return params

    def generate_message_params(self, from_agent: str, to_agent: str,
                                  content: str, summary: str = "") -> Dict[str, Any]:
        """
        生成 send_message 工具的调用参数

        Args:
            from_agent: 发送方Agent ID
            to_agent: 接收方Agent ID
            content: 消息内容
            summary: 消息摘要

        Returns:
            send_message 参数字典
        """
        if not self._team_config:
            self.initialize()

        sender = self._team_config.members.get(from_agent)
        recipient = self._team_config.members.get(to_agent)

        msg = TeamMessage(
            msg_type="message",
            sender=sender.member_name if sender else from_agent,
            recipient=recipient.member_name if recipient else to_agent,
            content=content,
            summary=summary or content[:10]
        )

        return msg.to_send_params()

    def generate_broadcast_params(self, from_agent: str,
                                    content: str, summary: str = "") -> Dict[str, Any]:
        """生成广播消息参数"""
        msg = TeamMessage(
            msg_type="broadcast",
            sender=from_agent,
            content=content,
            summary=summary or content[:10]
        )
        return msg.to_send_params()

    def generate_pipeline_prompts(self, pipeline_steps: List[dict],
                                    req_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        将流水线步骤转换为团队成员任务指令

        Args:
            pipeline_steps: 流水线步骤列表
            req_context: 需求上下文

        Returns:
            任务指令列表，每项包含 agent_id, prompt, parallel 信息
        """
        prompts = []

        for step in pipeline_steps:
            agent_id = step.get("agent_id", "")
            stage = step.get("stage", "")
            parallel_with = step.get("parallel_with", [])

            prompt = self._build_step_prompt(agent_id, stage, req_context)

            prompts.append({
                "agent_id": agent_id,
                "stage": stage,
                "prompt": prompt,
                "parallel_with": parallel_with,
                "is_parallel": len(parallel_with) > 0
            })

        return prompts

    def _build_step_prompt(self, agent_id: str, stage: str,
                            req_context: Dict[str, Any]) -> str:
        """构建Agent步骤的任务指令"""
        display_name = self.AGENT_DISPLAY_MAP.get(agent_id, agent_id)
        role = self._get_agent_role(agent_id)

        req_id = req_context.get("req_id", "")
        req_name = req_context.get("req_name", "")
        req_type = req_context.get("req_type", "")

        prompt = f"""你是 {display_name}，负责{role}。

## 当前任务
- 需求ID: {req_id}
- 需求名称: {req_name}
- 需求类型: {req_type}
- 当前阶段: {stage}

## 工作要求
1. 在你的独立沙盒中完成所有工作
2. 完成后通过消息将产出物传递给下一阶段
3. 不要修改 rules/ 目录下的任何文件
4. 遵循质量门禁的检查标准
"""
        return prompt

    def get_team_status(self) -> Dict[str, Any]:
        """获取团队状态"""
        if not self._team_config:
            return {"status": "not_initialized"}

        members_status = {}
        for agent_id, member in self._team_config.members.items():
            members_status[agent_id] = {
                "name": member.display_name,
                "role": member.role,
                "group": member.parallel_group,
                "mode": member.mode,
                "has_agent_file": bool(member.subagent_path)
            }

        return {
            "team_name": self._team_config.team_name,
            "member_count": len(self._team_config.members),
            "members": members_status,
            "parallel_groups": self.PARALLEL_GROUPS
        }

    def export_config(self, output_path: str):
        """导出团队配置为JSON"""
        if not self._team_config:
            self.initialize()

        config_data = {
            "team_name": self._team_config.team_name,
            "description": self._team_config.description,
            "members": {k: v.to_dict() for k, v in self._team_config.members.items()},
            "parallel_groups": self.PARALLEL_GROUPS,
            "created_at": self._team_config.created_at,
            "exported_at": datetime.now().isoformat()
        }

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
