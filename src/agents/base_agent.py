"""
Agent基类 - 所有Agent的通用抽象

定义Agent的通用行为:
- 人格系统
- 权限检查
- 步骤执行
- 质量门禁
- 消息收发
- 上下文管理
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from pathlib import Path

from ..core.sandbox import SandboxManager, SandboxConfig, SandboxFileProxy
from ..core.message_queue import MessageQueue, Message, MessageType
from ..core.context_manager import ContextManager, AgentContext


@dataclass
class AgentPersona:
    """Agent人格档案"""
    name: str                    # 人格名称
    icon: str                    # 图标
    experience: str              # 经验描述
    communication_style: str     # 沟通风格
    decision_principle: str      # 决策原则
    behavior_bottom_line: List[str] = field(default_factory=list)  # 行为底线


@dataclass
class AgentPermissions:
    """Agent权限声明"""
    read: List[str] = field(default_factory=list)
    write: List[str] = field(default_factory=list)
    create: List[str] = field(default_factory=list)
    delete: List[str] = field(default_factory=list)
    execute: List[str] = field(default_factory=list)


@dataclass
class StepDefinition:
    """步骤定义"""
    name: str           # 步骤名称
    file: str           # 步骤文件名
    mode: str = ""      # 行为模式 (EXPLORE/DESIGN/IMPLEMENT/REVIEW/DEBUG/VERIFY/REFLECT)
    description: str = ""


class BaseAgent(ABC):
    """
    Agent基类
    
    所有Agent必须继承此类并实现:
    - get_persona(): 返回人格档案
    - get_permissions(): 返回权限声明
    - get_steps(): 返回步骤定义列表
    - execute_step(): 执行具体步骤
    
    通用行为（已实现）:
    - 沙盒初始化
    - 上下文管理
    - 消息收发
    - 权限检查
    - 质量门禁
    - 步骤执行框架
    """
    
    # 行为模式映射
    MODE_DESCRIPTIONS = {
        "EXPLORE": "🧭 探索模式 - 发散思维，多角度思考",
        "DESIGN": "📐 设计模式 - 结构化思考，关注完整性",
        "IMPLEMENT": "💻 实现模式 - 专注编码，严谨细致",
        "REVIEW": "🔍 审查模式 - 对抗心态，怀疑一切",
        "DEBUG": "🐛 调试模式 - 系统排查，追踪根因",
        "VERIFY": "🧪 验证模式 - 边界优先，穷举测试",
        "REFLECT": "🪞 内省模式 - 客观回顾，提炼经验",
    }
    
    def __init__(self, agent_id: str, sandbox_mgr: SandboxManager,
                 message_queue: MessageQueue, context_mgr: ContextManager,
                 llm_invoker=None):
        """
        初始化Agent

        Args:
            agent_id: Agent唯一ID
            sandbox_mgr: 沙盒管理器
            message_queue: 消息队列
            context_mgr: 上下文管理器
            llm_invoker: LLM调用器（可选，有则真实调用LLM）
        """
        self.agent_id = agent_id
        self.sandbox_mgr = sandbox_mgr
        self.mq = message_queue
        self.ctx_mgr = context_mgr
        self.llm_invoker = llm_invoker  # 注入 LLM 调用器

        # 沙盒文件代理 — 所有文件操作必须通过此代理
        self.file_proxy = SandboxFileProxy(sandbox_mgr, agent_id)

        # 从子类获取配置
        self.persona = self.get_persona()
        self.permissions = self.get_permissions()
        self.steps = self.get_steps()

        # 当前上下文
        self.context: Optional[AgentContext] = None

        # 执行日志
        self._execution_log: List[dict] = []
    
    @abstractmethod
    def get_persona(self) -> AgentPersona:
        """返回Agent人格档案"""
        pass
    
    @abstractmethod
    def get_permissions(self) -> AgentPermissions:
        """返回Agent权限声明"""
        pass
    
    @abstractmethod
    def get_steps(self) -> Dict[str, List[StepDefinition]]:
        """
        返回步骤定义
        
        Returns:
            Dict[流程名称, List[StepDefinition]]
            如: {"standard": [...], "bugfix": [...]}
        """
        pass
    
    @abstractmethod
    def execute_step(self, step: StepDefinition, context: AgentContext,
                     input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行具体步骤
        
        Args:
            step: 步骤定义
            context: 当前上下文
            input_data: 输入数据
            
        Returns:
            步骤执行结果
        """
        pass
    
    def initialize(self, req_id: str = "", req_name: str = "",
                   req_type: str = "", req_scale: str = "") -> AgentContext:
        """
        初始化Agent（创建沙盒和上下文）
        
        Args:
            req_id: 需求ID
            req_name: 需求名称
            req_type: 需求类型
            req_scale: 需求规模
            
        Returns:
            AgentContext
        """
        # 1. 创建沙盒
        sandbox_config = SandboxConfig(
            agent_id=self.agent_id,
            agent_name=self.persona.name,
            sandbox_root=str(self.sandbox_mgr.sandbox_root),
            read_permissions=self.permissions.read,
            write_permissions=self.permissions.write,
            create_permissions=self.permissions.create,
            needs_sandbox=True
        )
        self.sandbox_mgr.create_sandbox(sandbox_config)
        
        # 2. 创建上下文
        self.context = self.ctx_mgr.create_context(
            agent_id=self.agent_id,
            agent_name=self.persona.name,
            req_id=req_id,
            req_name=req_name,
            req_type=req_type,
            req_scale=req_scale
        )
        
        self._log("initialized", f"Agent {self.persona.icon} {self.persona.name} 已初始化")
        return self.context
    
    def run_pipeline(self, flow_name: str = "standard",
                     input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        运行Agent的完整流程
        
        遵循微文件架构铁律:
        1. 每次只加载一个步骤
        2. 执行前完整阅读步骤文件
        3. 不跳步
        4. 每步完成后确认完成标志
        5. 不从未来步骤创建心理待办
        
        Args:
            flow_name: 流程名称（如 "standard", "bugfix"）
            input_data: 输入数据
            
        Returns:
            流程执行结果
        """
        steps = self.steps.get(flow_name)
        if not steps:
            raise ValueError(f"未定义的流程: {flow_name}")
        
        results = {}
        
        for i, step in enumerate(steps):
            # 1. 输出当前模式标识
            mode_desc = self.MODE_DESCRIPTIONS.get(step.mode, "")
            self._log("step_start", 
                      f"{mode_desc} 开始执行 {step.name} ({i+1}/{len(steps)})")
            
            # 2. 记录步骤开始
            if self.context:
                self.context.record_step_start(step.name, step.mode)
            
            # 3. 执行步骤
            try:
                result = self.execute_step(step, self.context, input_data)
                results[step.name] = result
                
                # 4. 记录步骤完成
                artifacts = result.get("artifacts", [])
                if self.context:
                    self.context.record_step_complete(step.name, artifacts)
                
                self._log("step_complete", f"✅ {step.name} 完成")
                
            except Exception as e:
                self._log("step_error", f"❌ {step.name} 执行出错: {str(e)}")
                results[step.name] = {"error": str(e)}
                raise
            
            # 5. 保存上下文快照
            if self.context:
                self.ctx_mgr.save_context(self.agent_id)
        
        return results
    
    def receive_messages(self, msg_type: Optional[str] = None) -> List[Message]:
        """接收消息"""
        return self.mq.receive(self.agent_id, msg_type)
    
    def send_handoff(self, to_agent: str, req_id: str, 
                     artifacts: List[str], message: str = ""):
        """发送流转消息"""
        return self.mq.send_handoff(
            from_agent=self.agent_id,
            to_agent=to_agent,
            req_id=req_id,
            artifacts=artifacts,
            message=message or f"⚡ 流转至下一阶段"
        )
    
    def check_file_access(self, file_path: str, operation: str) -> tuple:
        """检查文件访问权限"""
        return self.sandbox_mgr.check_access(self.agent_id, file_path, operation)
    
    def safe_save_to_workspace(self, filename: str, data) -> str:
        """
        安全保存数据到沙盒工作目录（强制权限检查）
        
        Args:
            filename: 文件名
            data: 要保存的数据（dict/list会序列化为JSON，str直接写入）
            
        Returns:
            保存的文件路径
        """
        workspace = self.sandbox_mgr.get_sandbox_workspace_path(self.agent_id)
        if not workspace:
            raise RuntimeError(f"Agent {self.agent_id} 沙盒工作目录不存在")
        
        filepath = workspace / filename
        if isinstance(data, (dict, list)):
            self.file_proxy.write_json(filepath, data)
        else:
            self.file_proxy.write_text(filepath, str(data))
        
        return str(filepath)
    
    def call_llm(self, prompt: str, system_prompt: str = "",
                 context_summary: str = "") -> str:
        """
        便利方法：同步调用 LLM 并返回文本响应

        Args:
            prompt: 用户侧提示词
            system_prompt: 系统提示词（覆盖默认）
            context_summary: 附加到 prompt 的上下文摘要

        Returns:
            LLM 响应文本；无 invoker 时返回占位字符串
        """
        if not self.llm_invoker:
            return (
                f"[{self.persona.icon} {self.persona.name}] "
                f"暂未配置 LLM，请在「智能体配置」页面设置 API Key。"
            )

        full_prompt = prompt
        if context_summary:
            full_prompt = f"{context_summary}\n\n---\n\n{prompt}"

        default_system = (
            f"你是 {self.persona.name}，{self.persona.experience}。"
            f"沟通风格：{self.persona.communication_style}。"
            f"决策原则：{self.persona.decision_principle}。"
        )

        result = self.llm_invoker.invoke_sync(
            agent_id=self.agent_id,
            messages=[{"role": "user", "content": full_prompt}],
            system_prompt=system_prompt or default_system,
        )
        return result.get("content", "")

    def self_reflect(self) -> Dict[str, Any]:
        """
        自我反思（流转前必须执行）
        
        反思清单:
        □ 本阶段产出物是否完整且准确？
        □ 产出物归属是否正确？
        □ 本阶段是否有流程偏差？
        □ 本阶段是否有可改进的做法？
        □ 本次执行中是否犯了错误？
        """
        reflection = {
            "agent_id": self.agent_id,
            "agent_name": self.persona.name,
            "timestamp": datetime.now().isoformat(),
            "checklist": {
                "artifacts_complete": None,
                "artifacts_ownership_correct": None,
                "no_process_deviation": None,
                "improvement_identified": None,
                "no_errors": None
            },
            "issues_found": [],
            "improvements": [],
            "iteration_needed": False
        }
        return reflection
    
    def get_status(self) -> dict:
        """获取Agent状态"""
        return {
            "agent_id": self.agent_id,
            "persona": {
                "name": self.persona.name,
                "icon": self.persona.icon
            },
            "context": self.context.get_progress_summary() if self.context else None,
            "execution_log_count": len(self._execution_log)
        }
    
    def _log(self, event_type: str, message: str):
        """记录执行日志"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "agent_id": self.agent_id,
            "event_type": event_type,
            "message": message
        }
        self._execution_log.append(entry)
        
        # 同时写入沙盒日志文件
        log_dir = self.sandbox_mgr.get_sandbox_path(self.agent_id)
        if log_dir:
            log_file = log_dir / "logs" / "execution.log"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{entry['timestamp']}] [{event_type}] {message}\n")
    
    def cleanup(self):
        """清理Agent资源"""
        # 保存最终上下文
        if self.context:
            self.ctx_mgr.save_context(self.agent_id)
        
        self._log("cleanup", f"Agent {self.persona.name} 清理完成")
