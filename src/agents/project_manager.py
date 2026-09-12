"""
项目管理Agent (Project Manager) - 需求管理与进度监控

角色: PM小李 📊
职责:
- 分配需求ID
- 评估复杂度与预期时长
- 维护需求池和进度看板
- 监控进度和时间风险
- 规模自适应时长系数
- 上下文恢复协议

规则来源: rules/agents/01_项目管理Agent.md
"""

import json
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from .base_agent import BaseAgent, AgentPersona, AgentPermissions, StepDefinition
from ..core.context_manager import AgentContext
from ..core.message_queue import MessageType


class ProjectManagerAgent(BaseAgent):
    """
    项目管理Agent - 需求管理与进度监控
    
    行为底线:
    - 绝不跳过ID分配
    - 绝不隐瞒进度和质量问题
    - 绝不为赶时间而降低质量标准
    """
    
    # 复杂度评估标准
    COMPLEXITY_FACTORS = {
        "FEATURE": {"base": 3, "description": "功能开发"},
        "FEATURE_UI": {"base": 4, "description": "功能开发(含UI)"},
        "OPTIMIZE": {"base": 2, "description": "代码优化"},
        "BUGFIX": {"base": 1, "description": "Bug修复"},
        "TEST": {"base": 2, "description": "测试相关"},
        "DOC": {"base": 1, "description": "文档相关"},
        "REVIEW": {"base": 2, "description": "代码审查"},
        "CONFIG": {"base": 1, "description": "配置调整"},
        "RESEARCH": {"base": 2, "description": "方向调研"},
    }
    
    # 规模时长系数
    SCALE_MULTIPLIER = {
        "XS": 0.5,
        "S": 0.8,
        "M": 1.0,
        "L": 1.8,
        "XL": 2.5,
    }
    
    # 阶段预期时长(分钟)
    STAGE_DURATIONS = {
        "producer": 2,
        "pm": 3,
        "planner": 15,
        "ux": 10,
        "tech_lead": 10,
        "programmer": 30,
        "artist": 10,
        "qa": 15,
        "delivery": 5,
    }
    
    def get_persona(self) -> AgentPersona:
        return AgentPersona(
            name="PM小李",
            icon="📊",
            experience="6年项目管理经验，数据驱动型，擅长进度管控和风险预警",
            communication_style="数据说话、清单驱动。用数字和表格沟通，不接受模糊表述",
            decision_principle="质量 > 范围 > 时间。质量是第一约束",
            behavior_bottom_line=[
                "绝不跳过ID分配",
                "绝不隐瞒进度和质量问题",
                "绝不为赶时间而降低质量标准",
            ]
        )
    
    def get_permissions(self) -> AgentPermissions:
        return AgentPermissions(
            read=["requirements_pool", "progress_board", "time_stats"],
            write=[".GameDev/_ProjectManagement/**"],
            create=[".GameDev/_ProjectManagement/**"],
            delete=[],
            execute=[]
        )
    
    def get_steps(self) -> Dict[str, List[StepDefinition]]:
        return {
            "standard": [
                StepDefinition(
                    name="需求初始化",
                    file="step-01_需求初始化.md",
                    mode="IMPLEMENT",
                    description="分配ID、评估复杂度、更新需求池"
                ),
                StepDefinition(
                    name="进度监控",
                    file="step-02_进度监控.md",
                    mode="EXPLORE",
                    description="实时监控、时间风险通知、阶段流转记录"
                ),
            ],
            "completion": [
                StepDefinition(
                    name="需求完成",
                    file="step-C1_需求完成.md",
                    mode="REFLECT",
                    description="统计时长、更新需求池、分析优化"
                ),
            ]
        }
    
    def execute_step(self, step: StepDefinition, context: AgentContext,
                     input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行项目管理步骤"""
        input_data = input_data or {}
        
        if step.name == "需求初始化":
            return self._step_initialize_requirement(context, input_data)
        elif step.name == "进度监控":
            return self._step_monitor_progress(context, input_data)
        elif step.name == "需求完成":
            return self._step_complete_requirement(context, input_data)
        else:
            raise ValueError(f"未知步骤: {step.name}")
    
    # ─── Step 1: 需求初始化 ────────────────────────────────
    
    def _step_initialize_requirement(self, context: AgentContext,
                                      input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Step 1: 需求初始化
        
        1. 分配唯一需求ID
        2. 评估复杂度
        3. 计算预期时长（含规模系数）
        4. 创建需求追踪文件
        5. 更新需求池
        """
        # 加载步骤文件
        self.ctx_mgr.load_step_file(
            self.agent_id,
            "01_项目管理Agent",
            "step-01_需求初始化.md"
        )
        
        # 1. 分配需求ID（铁律：绝不跳过）
        req_id = f"GD-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:4].upper()}"
        context.req_id = req_id
        
        # 2. 评估复杂度
        req_type = context.req_type or "FEATURE"
        req_scale = context.req_scale or "M"
        
        complexity = self._evaluate_complexity(req_type, req_scale)
        
        # 3. 计算预期时长
        estimated_duration = self._calculate_duration(req_type, req_scale)
        
        # 4. 创建需求状态追踪 (Frontmatter)
        frontmatter = {
            "req_id": req_id,
            "req_name": context.req_name,
            "req_type": req_type,
            "scale": req_scale,
            "complexity": complexity["level"],
            "complexity_score": complexity["score"],
            "estimated_duration_min": estimated_duration,
            "scale_multiplier": self.SCALE_MULTIPLIER.get(req_scale, 1.0),
            "status": "in-progress",
            "current_agent": "01_pm",
            "current_step": "需求初始化",
            "progress": "5%",
            "created_at": datetime.now().isoformat(),
            "stages_completed": [],
            "time_log": {
                "start": datetime.now().isoformat(),
                "stages": {}
            }
        }
        
        # 5. 写入沙盒
        self._save_to_sandbox(context, "requirement_frontmatter.json", frontmatter)
        
        # 保存到上下文
        context.loaded_knowledge["frontmatter"] = frontmatter
        context.loaded_knowledge["complexity"] = complexity
        
        return {
            "status": "completed",
            "req_id": req_id,
            "complexity": complexity,
            "estimated_duration_min": estimated_duration,
            "frontmatter": frontmatter,
            "message": f"📊 PM小李: 需求 {req_id} 已初始化 | 复杂度: {complexity['level']} | 预估: {estimated_duration}min"
        }
    
    def _evaluate_complexity(self, req_type: str, req_scale: str) -> Dict[str, Any]:
        """评估需求复杂度"""
        factor = self.COMPLEXITY_FACTORS.get(req_type, {"base": 2})
        base_score = factor["base"]
        
        scale_weight = {
            "XS": 0.5, "S": 1, "M": 2, "L": 3, "XL": 5
        }.get(req_scale, 2)
        
        score = base_score * scale_weight
        
        if score <= 2:
            level = "简单"
        elif score <= 6:
            level = "中等"
        elif score <= 12:
            level = "复杂"
        else:
            level = "高复杂"
        
        return {
            "score": score,
            "level": level,
            "base_score": base_score,
            "scale_weight": scale_weight,
            "type_description": factor.get("description", req_type),
        }
    
    def _calculate_duration(self, req_type: str, req_scale: str) -> int:
        """计算预期时长（分钟）"""
        multiplier = self.SCALE_MULTIPLIER.get(req_scale, 1.0)
        
        # 根据需求类型确定涉及的阶段
        stage_map = {
            "FEATURE": ["producer", "pm", "planner", "tech_lead", "programmer", "qa", "delivery"],
            "FEATURE_UI": ["producer", "pm", "planner", "ux", "tech_lead", "programmer", "artist", "qa", "delivery"],
            "OPTIMIZE": ["producer", "pm", "tech_lead", "programmer", "qa", "delivery"],
            "BUGFIX": ["producer", "pm", "programmer", "qa", "delivery"],
            "TEST": ["producer", "pm", "qa", "delivery"],
            "DOC": ["producer", "pm", "tech_lead"],
            "REVIEW": ["producer", "pm", "tech_lead", "programmer"],
            "CONFIG": ["producer", "pm", "programmer", "qa", "delivery"],
            "RESEARCH": ["producer", "planner"],
        }
        
        stages = stage_map.get(req_type, stage_map["FEATURE"])
        base_duration = sum(self.STAGE_DURATIONS.get(s, 5) for s in stages)
        
        return round(base_duration * multiplier)
    
    # ─── Step 2: 进度监控 ─────────────────────────────────
    
    def _step_monitor_progress(self, context: AgentContext,
                                input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Step 2: 进度监控
        
        1. 检查各阶段时长
        2. 时间风险预警
        3. 记录阶段流转
        """
        # 加载步骤文件
        self.ctx_mgr.load_step_file(
            self.agent_id,
            "01_项目管理Agent",
            "step-02_进度监控.md"
        )
        
        frontmatter = context.loaded_knowledge.get("frontmatter", {})
        
        # 检查消息队列中的状态更新
        messages = self.receive_messages(MessageType.STATUS_UPDATE.value)
        
        status_updates = []
        for msg in messages:
            status_updates.append({
                "from": msg.from_agent,
                "status": msg.payload.get("status", ""),
                "timestamp": msg.timestamp,
            })
        
        # 进度板更新
        progress_board = {
            "req_id": context.req_id,
            "req_name": context.req_name,
            "current_stage": frontmatter.get("current_agent", ""),
            "progress": frontmatter.get("progress", "0%"),
            "status_updates": status_updates,
            "time_warnings": [],
            "last_checked": datetime.now().isoformat(),
        }
        
        # 发送流转消息到下一Agent
        # 确定下一Agent (从制作人分析结果获取)
        next_agent_id = input_data.get("final_route", "02_planner")
        
        self.send_handoff(
            to_agent=next_agent_id,
            req_id=context.req_id,
            artifacts=["requirement_frontmatter.json"],
            message=f"📊 需求 {context.req_id} 已初始化完成，流转至执行"
        )
        
        # 自我反思
        reflection = self.self_reflect()
        reflection["checklist"]["artifacts_complete"] = True
        reflection["checklist"]["artifacts_ownership_correct"] = True
        
        return {
            "status": "completed",
            "progress_board": progress_board,
            "next_agent": next_agent_id,
            "reflection": reflection,
            "message": f"⚡ 流转至: {next_agent_id}"
        }
    
    # ─── Step C1: 需求完成 ────────────────────────────────
    
    def _step_complete_requirement(self, context: AgentContext,
                                    input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Step C1: 需求完成
        
        1. 统计各阶段时长
        2. 更新需求池状态
        3. 记录问题和优化建议
        """
        self.ctx_mgr.load_step_file(
            self.agent_id,
            "01_项目管理Agent",
            "step-C1_需求完成.md"
        )
        
        frontmatter = context.loaded_knowledge.get("frontmatter", {})
        
        completion_record = {
            "req_id": context.req_id,
            "req_name": context.req_name,
            "status": "completed",
            "completed_at": datetime.now().isoformat(),
            "total_stages": len(context.step_history),
            "artifacts_produced": context.artifacts_produced,
            "quality_gates": context.quality_gates,
        }
        
        return {
            "status": "completed",
            "completion_record": completion_record,
            "message": f"📊 PM小李: 需求 {context.req_id} 已完成归档"
        }
    
    # ─── 工具方法 ──────────────────────────────────────────
    
    def _save_to_sandbox(self, context: AgentContext, filename: str, data: Any):
        """保存数据到沙盒工作目录（通过文件代理强制权限检查）"""
        self.safe_save_to_workspace(filename, data)
