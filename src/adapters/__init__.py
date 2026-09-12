"""
适配器层包 - 外部系统集成

- rule_loader: 规则目录扫描与资产注册
- codebuddy_adapter: CodeBuddy Team Mode 适配器
"""

from .rule_loader import (
    RuleLoader, RuleInventory,
    AgentSpec, SkillSpec, RuleSpec
)
from .codebuddy_adapter import (
    CodeBuddyAdapter, TeamConfig, TeamMemberSpec, TeamMessage
)

__all__ = [
    "RuleLoader", "RuleInventory",
    "AgentSpec", "SkillSpec", "RuleSpec",
    "CodeBuddyAdapter", "TeamConfig", "TeamMemberSpec", "TeamMessage",
]
