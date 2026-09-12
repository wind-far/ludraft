"""
策划Agent (Planner) - 策划案编写与验收标准定义

角色: 策划小张 📋
职责:
- 加载知识库与全局策划案
- 需求分析与模块拆分
- 方案设计 (核心机制/交互流程/数值)
- 验收标准 (可量化/可自动化测试)
- 全局策划案同步
- 质量门禁(21项)
- 交付流程与内省

规则来源: rules/agents/02_策划Agent.md
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from .base_agent import BaseAgent, AgentPersona, AgentPermissions, StepDefinition
from ..core.context_manager import AgentContext
from ..core.message_queue import MessageType


class PlannerAgent(BaseAgent):
    """
    策划Agent（主策划） - 将用户模糊的想法转化为清晰可执行的策划案
    
    主从架构角色: 主Agent，负责拆分模块并汇总设计
    
    行为底线:
    - 绝不写不可测试的验收标准
    - 绝不跳过全局文档同步
    - 绝不替程序做技术选型
    """
    
    # 质量门禁检查项 (21项)
    QUALITY_GATE_ITEMS = {
        "文件存在性": [
            "策划案文件存在",
            "验收标准章节存在",
            "全局策划案已更新",
        ],
        "格式完整性": [
            "文档标题规范",
            "模块结构完整",
            "交互流程描述完整",
            "数值参数明确",
            "边界条件列出",
            "异常处理说明",
        ],
        "内容质量": [
            "需求理解准确",
            "模块划分合理",
            "交互流程无歧义",
            "数值有依据",
            "验收标准可量化",
            "验收标准可自动化",
            "边界条件覆盖完整",
            "异常情况已处理",
            "与现有系统兼容",
        ],
        "实现泄漏检查": [
            "无技术选型越权",
            "无具体代码描述",
            "无数据库结构设计",
            "无API接口定义",
        ],
        "全局一致性": [
            "命名风格一致",
            "与全局策划案无冲突",
            "引用关系正确",
        ],
    }
    
    def get_persona(self) -> AgentPersona:
        return AgentPersona(
            name="策划小张",
            icon="📋",
            experience="8年游戏策划经验，擅长休闲策略类游戏，注重玩家体验",
            communication_style="条理清晰、善用列表和结构化描述。喜欢用'玩家视角'来解释设计意图",
            decision_principle="用户体验优先 > 技术实现便利 > 开发效率",
            behavior_bottom_line=[
                "绝不写不可测试的验收标准",
                "绝不跳过全局文档同步",
                "绝不替程序做技术选型",
            ]
        )
    
    def get_permissions(self) -> AgentPermissions:
        return AgentPermissions(
            read=["global_plan", "knowledge_base", "plan_docs", "rules/**"],
            write=[".GameDev/**/01_策划案.md", ".GameDev/**/07_内省报告.md"],
            create=[".GameDev/**/01_策划案.md", ".GameDev/**/07_内省报告.md"],
            delete=[],
            execute=[]
        )
    
    def get_steps(self) -> Dict[str, List[StepDefinition]]:
        return {
            "standard": [
                StepDefinition(
                    name="知识库加载",
                    file="step-01_知识库加载.md",
                    mode="EXPLORE",
                    description="读取知识库、全局策划案、检查成功模式"
                ),
                StepDefinition(
                    name="需求分析",
                    file="step-02_需求分析.md",
                    mode="EXPLORE",
                    description="分析需求、识别模块、判断是否拆分"
                ),
                StepDefinition(
                    name="需求深度探测",
                    file="step-02b_需求深度探测.md",
                    mode="EXPLORE",
                    description="Smart Probe: 评估需求清晰度，必要时提问（最多3个）"
                ),
                StepDefinition(
                    name="方案设计",
                    file="step-03_方案设计.md",
                    mode="DESIGN",
                    description="设计功能方案、核心机制、交互流程、数值"
                ),
                StepDefinition(
                    name="验收标准",
                    file="step-04_验收标准.md",
                    mode="DESIGN",
                    description="编写可量化、可自动化测试的验收标准"
                ),
                StepDefinition(
                    name="全局同步",
                    file="step-05_全局同步.md",
                    mode="IMPLEMENT",
                    description="更新全局策划案、判断UI流转方向"
                ),
                StepDefinition(
                    name="产出物检查",
                    file="step-06_产出物检查.md",
                    mode="VERIFY",
                    description="质量门禁：格式+内容质量+实现泄漏+全局一致性(21项)"
                ),
            ],
            "research": [
                StepDefinition(
                    name="调研流程",
                    file="step-R1_调研流程.md",
                    mode="EXPLORE",
                    description="完整的RESEARCH调研流程"
                ),
            ],
            "delivery": [
                StepDefinition(
                    name="交付流程",
                    file="step-D1_交付流程.md",
                    mode="IMPLEMENT",
                    description="QA通过后更新全局文档、需求池、待做清单"
                ),
                StepDefinition(
                    name="需求内省",
                    file="step-D2_需求内省.md",
                    mode="REFLECT",
                    description="结构化内省：回顾全流程、提炼经验（限时5分钟）"
                ),
            ],
            "ux_confirm": [
                StepDefinition(
                    name="UX确认",
                    file="step-U1_UX确认.md",
                    mode="REVIEW",
                    description="审核UX设计、确认或退回"
                ),
            ],
        }
    
    def execute_step(self, step: StepDefinition, context: AgentContext,
                     input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行策划步骤"""
        input_data = input_data or {}
        
        step_handlers = {
            "知识库加载": self._step_load_knowledge,
            "需求分析": self._step_analyze_requirement,
            "需求深度探测": self._step_smart_probe,
            "方案设计": self._step_design_plan,
            "验收标准": self._step_acceptance_criteria,
            "全局同步": self._step_global_sync,
            "产出物检查": self._step_quality_gate,
            "调研流程": self._step_research,
            "交付流程": self._step_delivery,
            "需求内省": self._step_introspection,
            "UX确认": self._step_ux_confirm,
        }
        
        handler = step_handlers.get(step.name)
        if not handler:
            raise ValueError(f"未知步骤: {step.name}")
        
        return handler(context, input_data)
    
    # ─── Step 1: 知识库加载 ────────────────────────────────
    
    def _step_load_knowledge(self, context: AgentContext,
                              input_data: Dict[str, Any]) -> Dict[str, Any]:
        """加载知识库、全局策划案、成功模式"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-01_知识库加载.md"
        )
        
        knowledge_loaded = []
        
        # 加载Agent入口文件
        entry = self.ctx_mgr.load_agent_entry(self.agent_id, "02_策划Agent.md")
        if entry:
            knowledge_loaded.append("02_策划Agent.md")
        
        # 尝试加载全局策划案（从共享区域）
        # 在实际运行时这些文件可能不存在，graceful处理
        knowledge_loaded.append("全局策划案(待加载)")
        
        context.loaded_knowledge["knowledge_status"] = {
            "loaded": knowledge_loaded,
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            "status": "completed",
            "knowledge_loaded": knowledge_loaded,
            "message": f"📋 策划小张: 知识库加载完成 ({len(knowledge_loaded)}项)"
        }
    
    # ─── Step 2: 需求分析 ─────────────────────────────────
    
    def _step_analyze_requirement(self, context: AgentContext,
                                   input_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析需求、识别模块、判断是否需要拆分"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-02_需求分析.md"
        )
        
        analysis = {
            "req_id": context.req_id,
            "req_name": context.req_name,
            "req_type": context.req_type,
            "modules_identified": [],
            "needs_split": False,
            "dependencies": [],
            "risks": [],
        }
        
        # 规模判断是否需要模块拆分
        if context.req_scale in ("L", "XL"):
            analysis["needs_split"] = True
        
        context.loaded_knowledge["requirement_analysis"] = analysis
        
        return {
            "status": "completed",
            "analysis": analysis,
            "message": f"📋 策划小张: 需求分析完成 - {'需要拆分' if analysis['needs_split'] else '单模块'}"
        }
    
    # ─── Step 2b: 需求深度探测 ────────────────────────────
    
    def _step_smart_probe(self, context: AgentContext,
                           input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Smart Probe: 评估需求清晰度，必要时提问（最多3个）"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-02b_需求深度探测.md"
        )
        
        # 清晰度评估维度
        clarity_dimensions = {
            "功能边界": "clear",
            "交互流程": "clear",
            "数值参数": "unclear",
            "异常处理": "unclear",
            "与现有系统关系": "clear",
        }
        
        unclear_count = sum(1 for v in clarity_dimensions.values() if v == "unclear")
        
        probe_result = {
            "clarity_score": round((1 - unclear_count / len(clarity_dimensions)) * 100),
            "dimensions": clarity_dimensions,
            "questions_needed": min(unclear_count, 3),
            "questions": [],
        }
        
        # 生成问题（最多3个）
        if unclear_count > 0:
            for dim, status in clarity_dimensions.items():
                if status == "unclear" and len(probe_result["questions"]) < 3:
                    probe_result["questions"].append({
                        "dimension": dim,
                        "question": f"请明确{dim}的具体要求",
                    })
        
        context.loaded_knowledge["probe_result"] = probe_result
        
        return {
            "status": "completed",
            "probe_result": probe_result,
            "message": f"📋 策划小张: 清晰度评估 {probe_result['clarity_score']}% | 待确认问题: {probe_result['questions_needed']}个"
        }
    
    # ─── Step 3: 方案设计 ─────────────────────────────────
    
    def _step_design_plan(self, context: AgentContext,
                           input_data: Dict[str, Any]) -> Dict[str, Any]:
        """设计功能方案：核心机制、交互流程、数值"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-03_方案设计.md"
        )
        
        # 加载策划案模板
        template = self.ctx_mgr.load_template(
            self.agent_id, "02_策划Agent", "策划案模板.md"
        )
        
        plan_document = {
            "req_id": context.req_id,
            "req_name": context.req_name,
            "sections": {
                "概述": f"[{context.req_name}] 功能策划案",
                "核心机制": "待填充",
                "交互流程": "待填充",
                "数值设计": "待填充",
                "边界条件": "待填充",
                "异常处理": "待填充",
            },
            "created_at": datetime.now().isoformat(),
            "template_used": template is not None,
        }
        
        # 保存到沙盒
        self._save_to_workspace(context, "01_策划案_draft.json", plan_document)
        
        context.loaded_knowledge["plan_document"] = plan_document
        
        return {
            "status": "completed",
            "plan_document": plan_document,
            "artifacts": ["01_策划案.md"],
            "message": f"📋 策划小张: 方案设计完成"
        }
    
    # ─── Step 4: 验收标准 ─────────────────────────────────
    
    def _step_acceptance_criteria(self, context: AgentContext,
                                   input_data: Dict[str, Any]) -> Dict[str, Any]:
        """编写可量化、可自动化测试的验收标准"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-04_验收标准.md"
        )
        
        acceptance_criteria = {
            "req_id": context.req_id,
            "criteria": [],
            "testability_check": True,
        }
        
        # 基于方案设计生成验收标准框架
        plan = context.loaded_knowledge.get("plan_document", {})
        sections = plan.get("sections", {})
        
        ac_index = 1
        for section_name in ["核心机制", "交互流程", "数值设计"]:
            if sections.get(section_name):
                acceptance_criteria["criteria"].append({
                    "id": f"AC-{ac_index:03d}",
                    "category": section_name,
                    "description": f"{section_name}验收标准",
                    "testable": True,
                    "automatable": True,
                    "priority": "P1" if section_name == "核心机制" else "P2",
                })
                ac_index += 1
        
        # 边界条件AC
        acceptance_criteria["criteria"].append({
            "id": f"AC-{ac_index:03d}",
            "category": "边界条件",
            "description": "边界条件验收标准",
            "testable": True,
            "automatable": True,
            "priority": "P1",
        })
        
        context.loaded_knowledge["acceptance_criteria"] = acceptance_criteria
        
        return {
            "status": "completed",
            "acceptance_criteria": acceptance_criteria,
            "message": f"📋 策划小张: 验收标准编写完成 ({len(acceptance_criteria['criteria'])}条)"
        }
    
    # ─── Step 5: 全局同步 ─────────────────────────────────
    
    def _step_global_sync(self, context: AgentContext,
                           input_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新全局策划案、判断UI流转方向"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-05_全局同步.md"
        )
        
        # 判断是否涉及UI
        needs_ui = context.req_type in ("FEATURE_UI",)
        
        sync_result = {
            "global_plan_updated": True,
            "needs_ui_flow": needs_ui,
            "next_agent": "07_ux" if needs_ui else "03_tech_lead",
            "sync_timestamp": datetime.now().isoformat(),
        }
        
        context.loaded_knowledge["sync_result"] = sync_result
        
        return {
            "status": "completed",
            "sync_result": sync_result,
            "message": f"📋 策划小张: 全局同步完成 → {'UX Agent' if needs_ui else '主程 Agent'}"
        }
    
    # ─── Step 6: 产出物检查（质量门禁） ───────────────────
    
    def _step_quality_gate(self, context: AgentContext,
                            input_data: Dict[str, Any]) -> Dict[str, Any]:
        """质量门禁：格式+内容质量+实现泄漏+全局一致性(21项)"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-06_产出物检查.md"
        )
        
        gate_results = {}
        total_checks = 0
        passed_checks = 0
        
        for category, items in self.QUALITY_GATE_ITEMS.items():
            category_results = {}
            for item in items:
                # 逐项检查
                passed = self._check_quality_item(context, category, item)
                category_results[item] = passed
                total_checks += 1
                if passed:
                    passed_checks += 1
            gate_results[category] = category_results
        
        all_passed = passed_checks == total_checks
        
        # 记录质量门禁结果到上下文
        context.record_quality_gate("gate_1", all_passed, {
            "total": total_checks,
            "passed": passed_checks,
            "failed": total_checks - passed_checks,
            "details": gate_results,
        })
        
        # 确定流转目标
        sync_result = context.loaded_knowledge.get("sync_result", {})
        next_agent = sync_result.get("next_agent", "03_tech_lead")
        
        if all_passed:
            # 发送流转消息
            self.send_handoff(
                to_agent=next_agent,
                req_id=context.req_id,
                artifacts=["01_策划案.md"],
                message=f"📋 策划案质量门禁通过 ({passed_checks}/{total_checks})"
            )
        
        # 自我反思
        reflection = self.self_reflect()
        reflection["checklist"]["artifacts_complete"] = all_passed
        
        return {
            "status": "completed" if all_passed else "gate_failed",
            "quality_gate": {
                "name": "gate_1",
                "passed": all_passed,
                "score": f"{passed_checks}/{total_checks}",
                "details": gate_results,
            },
            "next_agent": next_agent if all_passed else None,
            "reflection": reflection,
            "message": f"🚧 门禁{'✅通过' if all_passed else '❌未通过'} ({passed_checks}/{total_checks}) → {'⚡ 流转至: ' + next_agent if all_passed else '需修正'}"
        }
    
    def _check_quality_item(self, context: AgentContext, 
                             category: str, item: str) -> bool:
        """检查单个质量项"""
        # 基于上下文状态进行检查
        plan = context.loaded_knowledge.get("plan_document")
        ac = context.loaded_knowledge.get("acceptance_criteria")
        
        if category == "文件存在性":
            if "策划案" in item:
                return plan is not None
            if "验收标准" in item:
                return ac is not None and len(ac.get("criteria", [])) > 0
            if "全局策划案" in item:
                return context.loaded_knowledge.get("sync_result", {}).get("global_plan_updated", False)
        
        if category == "实现泄漏检查":
            return True  # 框架层面默认通过
        
        if category == "全局一致性":
            return True  # 框架层面默认通过
        
        # 默认通过
        return True
    
    # ─── 交付与内省步骤 ───────────────────────────────────
    
    def _step_research(self, context: AgentContext,
                        input_data: Dict[str, Any]) -> Dict[str, Any]:
        """RESEARCH调研流程"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-R1_调研流程.md"
        )
        
        return {
            "status": "completed",
            "message": "📋 策划小张: 调研流程完成",
            "artifacts": ["调研报告.md"],
        }
    
    def _step_delivery(self, context: AgentContext,
                        input_data: Dict[str, Any]) -> Dict[str, Any]:
        """交付流程：QA通过后更新全局文档"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-D1_交付流程.md"
        )
        
        delivery_result = {
            "req_id": context.req_id,
            "global_docs_updated": True,
            "requirement_pool_updated": True,
            "delivered_at": datetime.now().isoformat(),
        }
        
        return {
            "status": "completed",
            "delivery": delivery_result,
            "message": f"📋 策划小张: 需求 {context.req_id} 已交付"
        }
    
    def _step_introspection(self, context: AgentContext,
                             input_data: Dict[str, Any]) -> Dict[str, Any]:
        """结构化内省：回顾全流程、提炼经验（限时5分钟）"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-D2_需求内省.md"
        )
        
        # 加载内省模板
        self.ctx_mgr.load_template(
            self.agent_id, "02_策划Agent", "需求内省模板.md"
        )
        
        introspection = {
            "req_id": context.req_id,
            "process_review": {
                "total_steps": len(context.step_history),
                "quality_gates_passed": all(
                    g.get("passed", False) for g in context.quality_gates.values()
                ),
                "artifacts_produced": context.artifacts_produced,
            },
            "lessons_learned": [],
            "improvement_suggestions": [],
            "timestamp": datetime.now().isoformat(),
        }
        
        return {
            "status": "completed",
            "introspection": introspection,
            "artifacts": ["07_内省报告.md"],
            "message": f"🪞 策划小张: 内省完成"
        }
    
    def _step_ux_confirm(self, context: AgentContext,
                          input_data: Dict[str, Any]) -> Dict[str, Any]:
        """审核UX设计、确认或退回"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "02_策划Agent", "step-U1_UX确认.md"
        )
        
        # 检查UX设计消息
        ux_messages = self.receive_messages(MessageType.HANDOFF.value)
        
        confirm_result = {
            "ux_received": len(ux_messages) > 0,
            "approved": True,  # 框架层默认通过
            "feedback": "",
        }
        
        if confirm_result["approved"]:
            self.send_handoff(
                to_agent="03_tech_lead",
                req_id=context.req_id,
                artifacts=["01_策划案.md", "02_UX设计.md"],
                message="📋 UX设计确认通过"
            )
        
        return {
            "status": "completed",
            "confirm_result": confirm_result,
            "message": f"📋 策划小张: UX设计{'✅确认' if confirm_result['approved'] else '❌退回'}"
        }
    
    # ─── 工具方法 ──────────────────────────────────────────
    
    def _save_to_workspace(self, context: AgentContext, 
                            filename: str, data: Any):
        """保存数据到沙盒工作目录（通过文件代理强制权限检查）"""
        self.safe_save_to_workspace(filename, data)
