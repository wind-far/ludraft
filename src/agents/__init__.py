"""
Agent实现包 - 8个游戏开发专业Agent

Agent注册表:
- 00_producer:    制作人老梁 🎬 - 需求入口与分类路由
- 01_pm:          PM小李 📊 - 需求管理与进度监控
- 02_planner:     策划小张 📋 - 策划案编写与验收标准
- 03_tech_lead:   主程老陈 🔧 - 技术评审与架构设计
- 04_programmer:  程序小赵 💻 - 代码实现与Bug修复
- 05_artist:      美术小周 🎨 - UI设计与美术需求
- 06_qa:          QA小吴 🧪 - 自动化测试与Bug报告
- 07_ux:          UX小林 ✨ - 交互设计与界面布局
"""

from .base_agent import BaseAgent, AgentPersona, AgentPermissions, StepDefinition
from .producer import ProducerAgent
from .project_manager import ProjectManagerAgent
from .planner import PlannerAgent
from .tech_lead import TechLeadAgent
from .programmer import ProgrammerAgent
from .qa import QAAgent
from .ux_designer import UXDesignerAgent
from .artist import ArtistAgent

# Agent注册表: agent_id → Agent类
AGENT_REGISTRY = {
    "00_producer": ProducerAgent,
    "01_pm": ProjectManagerAgent,
    "02_planner": PlannerAgent,
    "03_tech_lead": TechLeadAgent,
    "04_programmer": ProgrammerAgent,
    "05_artist": ArtistAgent,
    "06_qa": QAAgent,
    "07_ux": UXDesignerAgent,
}

__all__ = [
    "BaseAgent",
    "AgentPersona",
    "AgentPermissions",
    "StepDefinition",
    "ProducerAgent",
    "ProjectManagerAgent",
    "PlannerAgent",
    "TechLeadAgent",
    "ProgrammerAgent",
    "QAAgent",
    "UXDesignerAgent",
    "ArtistAgent",
    "AGENT_REGISTRY",
]
