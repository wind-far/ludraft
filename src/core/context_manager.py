"""
上下文管理器 - Agent独立上下文的加载、保存和恢复

核心职责:
- 管理每个Agent的独立上下文
- 实现微文件架构的按需加载
- 支持跨会话的上下文恢复
- 知识库精准加载
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class StepState:
    """步骤状态"""
    step_name: str
    status: str = "pending"   # pending, in_progress, completed, skipped
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_min: Optional[float] = None
    artifacts: List[str] = field(default_factory=list)


@dataclass
class AgentContext:
    """
    Agent独立上下文
    
    遵循微文件架构原则：
    - 每次只加载当前步骤文件
    - 按需加载知识库和技能包
    - 上下文大小控制在5-7KB
    """
    agent_id: str
    agent_name: str
    session_id: str = ""
    req_id: str = ""
    req_name: str = ""
    req_type: str = ""
    req_scale: str = ""  # XS/S/M/L/XL
    
    # 当前执行状态
    current_step: str = ""
    current_mode: str = ""  # EXPLORE/DESIGN/IMPLEMENT/REVIEW/DEBUG/VERIFY/REFLECT
    
    # 已加载的规则和文件
    loaded_rules: List[str] = field(default_factory=list)
    loaded_skills: List[str] = field(default_factory=list)
    loaded_knowledge: Dict[str, Any] = field(default_factory=dict)
    
    # 步骤历史
    step_history: List[dict] = field(default_factory=list)
    
    # 产出物
    artifacts_produced: List[str] = field(default_factory=list)
    
    # 消息记录
    messages_sent: List[str] = field(default_factory=list)
    messages_received: List[str] = field(default_factory=list)
    
    # 质量门禁结果
    quality_gates: Dict[str, dict] = field(default_factory=dict)
    
    # 时间戳
    created_at: str = ""
    last_updated: str = ""
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if not self.session_id:
            self.session_id = f"sess-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.last_updated = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "AgentContext":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def record_step_start(self, step_name: str, mode: str = ""):
        """记录步骤开始"""
        self.current_step = step_name
        self.current_mode = mode
        self.step_history.append({
            "step": step_name,
            "mode": mode,
            "status": "in_progress",
            "start_time": datetime.now().isoformat()
        })
        self.last_updated = datetime.now().isoformat()
    
    def record_step_complete(self, step_name: str, artifacts: Optional[List[str]] = None):
        """记录步骤完成"""
        for entry in self.step_history:
            if entry["step"] == step_name and entry["status"] == "in_progress":
                entry["status"] = "completed"
                entry["end_time"] = datetime.now().isoformat()
                if entry.get("start_time"):
                    start = datetime.fromisoformat(entry["start_time"])
                    end = datetime.fromisoformat(entry["end_time"])
                    entry["duration_min"] = round((end - start).total_seconds() / 60, 1)
                if artifacts:
                    entry["artifacts"] = artifacts
                    self.artifacts_produced.extend(artifacts)
                break
        self.last_updated = datetime.now().isoformat()
    
    def record_quality_gate(self, gate_name: str, passed: bool, 
                            details: Dict[str, Any] = None):
        """记录质量门禁结果"""
        self.quality_gates[gate_name] = {
            "passed": passed,
            "timestamp": datetime.now().isoformat(),
            "details": details or {}
        }
        self.last_updated = datetime.now().isoformat()
    
    def get_progress_summary(self) -> dict:
        """获取进度摘要"""
        total = len(self.step_history)
        completed = sum(1 for s in self.step_history if s["status"] == "completed")
        return {
            "agent_id": self.agent_id,
            "req_id": self.req_id,
            "current_step": self.current_step,
            "current_mode": self.current_mode,
            "progress": f"{completed}/{total}",
            "progress_pct": round(completed / max(total, 1) * 100),
            "artifacts_count": len(self.artifacts_produced),
            "last_updated": self.last_updated
        }


class ContextManager:
    """
    上下文管理器
    
    管理所有Agent的独立上下文，支持:
    - 创建新上下文
    - 保存/加载上下文到沙盒
    - 微文件架构的按需加载
    - 跨会话恢复
    """
    
    def __init__(self, sandbox_root: str, rules_working_copy: str):
        """
        初始化上下文管理器
        
        Args:
            sandbox_root: 沙盒根目录
            rules_working_copy: 规则工作副本路径
        """
        self.sandbox_root = Path(sandbox_root)
        self.rules_path = Path(rules_working_copy)
        
        # 活跃上下文注册表
        self._contexts: Dict[str, AgentContext] = {}
    
    def create_context(self, agent_id: str, agent_name: str,
                       req_id: str = "", req_name: str = "",
                       req_type: str = "", req_scale: str = "") -> AgentContext:
        """
        为Agent创建新的上下文
        
        Args:
            agent_id: Agent ID
            agent_name: Agent名称
            req_id: 需求ID
            req_name: 需求名称
            req_type: 需求类型
            req_scale: 需求规模
            
        Returns:
            AgentContext
        """
        ctx = AgentContext(
            agent_id=agent_id,
            agent_name=agent_name,
            req_id=req_id,
            req_name=req_name,
            req_type=req_type,
            req_scale=req_scale
        )
        self._contexts[agent_id] = ctx
        return ctx
    
    def get_context(self, agent_id: str, 
                    caller_agent_id: str = None) -> Optional[AgentContext]:
        """
        获取Agent的当前上下文
        
        Args:
            agent_id: 目标Agent ID
            caller_agent_id: 调用方Agent ID（用于权限验证）
                - 如果提供了caller_agent_id，则只允许Agent访问自己的上下文
                - 如果为 None（系统内部调用，如Orchestrator），则不做限制
        
        Returns:
            AgentContext，如果不存在或权限不足返回None
        """
        # 权限验证：Agent只能访问自己的上下文
        if caller_agent_id is not None and caller_agent_id != agent_id:
            return None  # 拒绝跨Agent上下文访问
        
        return self._contexts.get(agent_id)
    
    def save_context(self, agent_id: str) -> str:
        """
        保存Agent上下文到沙盒
        
        Returns:
            保存的文件路径
        """
        ctx = self._contexts.get(agent_id)
        if not ctx:
            raise ValueError(f"Agent {agent_id} 没有活跃上下文")
        
        context_dir = self.sandbox_root / agent_id / "context"
        context_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存上下文快照
        snapshot_file = context_dir / "context_snapshot.json"
        with open(snapshot_file, 'w', encoding='utf-8') as f:
            json.dump(ctx.to_dict(), f, ensure_ascii=False, indent=2)
        
        # 保存当前步骤状态（用于快速恢复）
        step_file = context_dir / "current_step.json"
        with open(step_file, 'w', encoding='utf-8') as f:
            json.dump({
                "current_step": ctx.current_step,
                "current_mode": ctx.current_mode,
                "req_id": ctx.req_id,
                "last_updated": ctx.last_updated
            }, f, ensure_ascii=False, indent=2)
        
        return str(snapshot_file)
    
    def load_context(self, agent_id: str) -> Optional[AgentContext]:
        """
        从沙盒加载Agent上下文
        
        Returns:
            AgentContext，如果不存在返回None
        """
        snapshot_file = self.sandbox_root / agent_id / "context" / "context_snapshot.json"
        
        if not snapshot_file.exists():
            return None
        
        with open(snapshot_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        ctx = AgentContext.from_dict(data)
        self._contexts[agent_id] = ctx
        return ctx
    
    def load_rule_file(self, agent_id: str, rule_path: str) -> Optional[str]:
        """
        为Agent加载规则文件（从工作副本）
        
        遵循微文件架构原则：
        - 每次只加载一个文件
        - 记录到上下文的loaded_rules
        
        Args:
            agent_id: Agent ID
            rule_path: 规则文件相对路径
            
        Returns:
            文件内容
        """
        ctx = self._contexts.get(agent_id)
        if not ctx:
            return None
        
        full_path = self.rules_path / rule_path
        if not full_path.exists():
            return None
        
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 记录加载
        if rule_path not in ctx.loaded_rules:
            ctx.loaded_rules.append(rule_path)
        ctx.last_updated = datetime.now().isoformat()
        
        return content
    
    def load_agent_entry(self, agent_id: str, agent_file: str) -> Optional[str]:
        """
        加载Agent入口文件
        
        Args:
            agent_id: Agent ID
            agent_file: Agent入口文件名（如 "02_策划Agent.md"）
            
        Returns:
            文件内容
        """
        return self.load_rule_file(agent_id, f"agents/{agent_file}")
    
    def load_step_file(self, agent_id: str, agent_dir: str, 
                       step_file: str) -> Optional[str]:
        """
        加载步骤文件
        
        遵循铁律：每次只加载一个步骤文件
        
        Args:
            agent_id: Agent ID
            agent_dir: Agent目录名（如 "02_策划Agent"）
            step_file: 步骤文件名（如 "step-01_知识库加载.md"）
            
        Returns:
            文件内容
        """
        return self.load_rule_file(agent_id, f"agents/{agent_dir}/{step_file}")
    
    def load_template(self, agent_id: str, agent_dir: str,
                      template_file: str) -> Optional[str]:
        """加载模板文件（按需）"""
        return self.load_rule_file(
            agent_id, f"agents/{agent_dir}/templates/{template_file}"
        )
    
    def load_skill(self, agent_id: str, skill_path: str) -> Optional[str]:
        """
        加载技能包文件
        
        Args:
            agent_id: Agent ID
            skill_path: 技能包路径（如 "csharp/null-safety.md"）
            
        Returns:
            文件内容
        """
        ctx = self._contexts.get(agent_id)
        if not ctx:
            return None
        
        content = self.load_rule_file(agent_id, f"skills/{skill_path}")
        if content and skill_path not in ctx.loaded_skills:
            ctx.loaded_skills.append(skill_path)
        
        return content
    
    def get_all_contexts_summary(self) -> List[dict]:
        """获取所有活跃上下文的摘要"""
        return [ctx.get_progress_summary() for ctx in self._contexts.values()]
    
    def restore_from_frontmatter(self, frontmatter: dict) -> Optional[AgentContext]:
        """
        从需求文档的frontmatter恢复上下文
        
        用于跨会话恢复
        
        Args:
            frontmatter: 需求文档头部的YAML frontmatter
            
        Returns:
            恢复的AgentContext
        """
        agent_id_map = {
            "制作人Agent": "00_producer",
            "项目管理Agent": "01_pm",
            "策划Agent": "02_planner",
            "主程Agent": "03_tech_lead",
            "程序Agent": "04_programmer",
            "美术Agent": "05_artist",
            "QAAgent": "06_qa",
            "UXAgent": "07_ux",
        }
        
        current_agent_name = frontmatter.get("current_agent", "")
        agent_id = agent_id_map.get(current_agent_name, "")
        
        if not agent_id:
            return None
        
        ctx = AgentContext(
            agent_id=agent_id,
            agent_name=current_agent_name,
            req_id=frontmatter.get("req_id", ""),
            req_name=frontmatter.get("req_name", ""),
            req_type=frontmatter.get("req_type", ""),
            req_scale=frontmatter.get("scale", ""),
            current_step=frontmatter.get("current_step", ""),
        )
        
        # 恢复步骤历史
        for step_data in frontmatter.get("steps_completed", []):
            ctx.step_history.append(step_data)
        
        self._contexts[agent_id] = ctx
        return ctx
    
    def clear_context(self, agent_id: str):
        """清除Agent上下文"""
        self._contexts.pop(agent_id, None)
    
    def clear_all_contexts(self):
        """清除所有上下文"""
        self._contexts.clear()
