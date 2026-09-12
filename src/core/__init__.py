"""
核心模块包 - 系统基础架构组件

- SandboxManager: 沙盒管理器 - Agent独立工作环境隔离
- MessageQueue: 消息队列 - Agent间异步通信
- ContextManager: 上下文管理器 - Agent独立上下文管理
- PipelineEngine: 流水线引擎 - 需求流转路径管理
- Orchestrator: 编排器 - 多Agent调度和生命周期管理
"""

from .sandbox import SandboxManager, SandboxConfig, SourceProtectionGuard
from .message_queue import MessageQueue, Message, MessageType, MessageChannel, MessagePriority
from .context_manager import ContextManager, AgentContext, StepState
from .pipeline import PipelineEngine, PipelineInstance, PipelineStep, QualityGate, ReqType, ReqScale
from .orchestrator import Orchestrator, RequirementAnalysis

__all__ = [
    "SandboxManager", "SandboxConfig", "SourceProtectionGuard",
    "MessageQueue", "Message", "MessageType", "MessageChannel", "MessagePriority",
    "ContextManager", "AgentContext", "StepState",
    "PipelineEngine", "PipelineInstance", "PipelineStep", "QualityGate", "ReqType", "ReqScale",
    "Orchestrator", "RequirementAnalysis",
]
