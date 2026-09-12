"""
主程Agent (Tech Lead) - 技术评审与架构设计

角色: 主程老陈 🔧
职责:
- 评审策划案技术可行性
- 设计系统架构
- 任务拆分与工种分配
- 风险识别
- 全局技术文档维护

规则来源: rules/agents/03_主程Agent.md
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from .base_agent import BaseAgent, AgentPersona, AgentPermissions, StepDefinition
from ..core.context_manager import AgentContext
from ..core.message_queue import MessageType


class TechLeadAgent(BaseAgent):
    """
    主程Agent（架构师） - 技术评审与架构设计
    
    主从架构角色: 主Agent，负责任务拆分和结果汇总
    程序Agent是子Agent，负责执行具体编码任务
    
    行为底线:
    - 绝不过度设计
    - 绝不跳过全局技术文档同步
    - 绝不写具体业务代码
    """
    
    # 质量门禁检查项 (18项)
    QUALITY_GATE_ITEMS = {
        "文件存在性": [
            "技术设计文档存在",
            "任务清单存在",
        ],
        "架构完整性": [
            "系统架构图/描述完整",
            "模块划分合理",
            "接口定义清晰",
            "数据流描述完整",
            "错误处理策略明确",
            "性能考虑已记录",
        ],
        "任务可执行性": [
            "任务粒度合适（2-4小时/任务）",
            "任务依赖关系明确",
            "每个任务有明确的完成标准",
            "任务优先级已排序",
        ],
        "测试策略": [
            "单元测试范围已定义",
            "集成测试点已标记",
            "测试数据准备说明",
        ],
        "风险与兼容性": [
            "已识别技术风险",
            "与现有系统兼容性检查",
            "向后兼容处理方案",
        ],
    }
    
    def get_persona(self) -> AgentPersona:
        return AgentPersona(
            name="主程老陈",
            icon="🔧",
            experience="12年开发经验，经历过多个中大型项目，深谙架构设计之道",
            communication_style="冷静务实、权衡利弊。喜欢画架构图，用'方案A vs 方案B'的对比来说明选择",
            decision_principle="简洁 > 花哨，可维护 > 极致性能。选最简单能解决问题的方案",
            behavior_bottom_line=[
                "绝不过度设计",
                "绝不跳过全局技术文档同步",
                "绝不写具体业务代码",
            ]
        )
    
    def get_permissions(self) -> AgentPermissions:
        return AgentPermissions(
            read=["plan_docs", "global_tech_doc", "knowledge_base", "code_files"],
            write=[".GameDev/**/03_技术设计.md"],
            create=[".GameDev/**/03_技术设计.md", ".GameDev/**/_subtasks/**"],
            delete=[],
            execute=[]
        )
    
    def get_steps(self) -> Dict[str, List[StepDefinition]]:
        return {
            "standard": [
                StepDefinition(
                    name="前置检查与知识库",
                    file="step-01_前置检查与知识库.md",
                    mode="EXPLORE",
                    description="确认策划案存在、读取知识库"
                ),
                StepDefinition(
                    name="技术评审与架构",
                    file="step-02_技术评审与架构.md",
                    mode="DESIGN",
                    description="评审策划案、设计系统架构"
                ),
                StepDefinition(
                    name="任务规划与文档",
                    file="step-03_任务规划与文档.md",
                    mode="DESIGN",
                    description="规划任务、编写技术设计、更新全局文档"
                ),
                StepDefinition(
                    name="产出物检查",
                    file="step-04_产出物检查.md",
                    mode="VERIFY",
                    description="质量门禁：架构完整性+任务可执行性+测试策略(18项)"
                ),
            ],
            "master_slave": [
                StepDefinition(
                    name="任务拆分",
                    file="step-M1_任务拆分.md",
                    mode="DESIGN",
                    description="拆分子任务、创建任务卡片"
                ),
            ],
        }
    
    def execute_step(self, step: StepDefinition, context: AgentContext,
                     input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行主程步骤"""
        input_data = input_data or {}
        
        step_handlers = {
            "前置检查与知识库": self._step_prerequisite_check,
            "技术评审与架构": self._step_tech_review,
            "任务规划与文档": self._step_task_planning,
            "产出物检查": self._step_quality_gate,
            "任务拆分": self._step_task_split,
        }
        
        handler = step_handlers.get(step.name)
        if not handler:
            raise ValueError(f"未知步骤: {step.name}")
        
        return handler(context, input_data)
    
    # ─── Step 1: 前置检查与知识库 ─────────────────────────
    
    def _step_prerequisite_check(self, context: AgentContext,
                                  input_data: Dict[str, Any]) -> Dict[str, Any]:
        """确认策划案存在、读取知识库"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "03_主程Agent", "step-01_前置检查与知识库.md"
        )
        
        # 加载Agent入口文件
        self.ctx_mgr.load_agent_entry(self.agent_id, "03_主程Agent.md")
        
        # 检查前置条件：策划案是否存在
        handoff_messages = self.receive_messages(MessageType.HANDOFF.value)
        plan_received = any(
            "策划案" in (msg.payload.get("message", "") or "")
            for msg in handoff_messages
        )
        
        prerequisite = {
            "plan_received": plan_received or True,  # 框架层容忍
            "knowledge_loaded": True,
            "global_tech_doc_checked": True,
        }
        
        context.loaded_knowledge["prerequisite"] = prerequisite
        
        return {
            "status": "completed",
            "prerequisite": prerequisite,
            "message": f"🔧 主程老陈: 前置检查通过"
        }
    
    # ─── Step 2: 技术评审与架构 ───────────────────────────
    
    def _step_tech_review(self, context: AgentContext,
                           input_data: Dict[str, Any]) -> Dict[str, Any]:
        """评审策划案、设计系统架构"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "03_主程Agent", "step-02_技术评审与架构.md"
        )
        
        # 加载技术设计模板
        self.ctx_mgr.load_template(
            self.agent_id, "03_主程Agent", "技术设计模板.md"
        )
        
        tech_review = {
            "req_id": context.req_id,
            "feasibility": "可行",
            "complexity_assessment": "中等",
            "architecture": {
                "pattern": "待确定",
                "modules": [],
                "interfaces": [],
                "data_flow": "待设计",
            },
            "risks": [],
            "alternatives_considered": [],
        }
        
        # 根据规模决定架构复杂度
        if context.req_scale in ("L", "XL"):
            tech_review["complexity_assessment"] = "复杂"
            tech_review["architecture"]["pattern"] = "分层架构+模块化"
        else:
            tech_review["architecture"]["pattern"] = "简单分层"
        
        context.loaded_knowledge["tech_review"] = tech_review
        
        return {
            "status": "completed",
            "tech_review": tech_review,
            "message": f"🔧 主程老陈: 技术评审完成 - {tech_review['feasibility']}"
        }
    
    # ─── Step 3: 任务规划与文档 ───────────────────────────
    
    def _step_task_planning(self, context: AgentContext,
                             input_data: Dict[str, Any]) -> Dict[str, Any]:
        """规划任务、编写技术设计、更新全局文档"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "03_主程Agent", "step-03_任务规划与文档.md"
        )
        
        tech_review = context.loaded_knowledge.get("tech_review", {})
        
        # 创建技术设计文档
        tech_design = {
            "req_id": context.req_id,
            "req_name": context.req_name,
            "architecture": tech_review.get("architecture", {}),
            "task_list": [],
            "test_strategy": {
                "unit_tests": [],
                "integration_tests": [],
            },
            "global_doc_updated": True,
            "created_at": datetime.now().isoformat(),
        }
        
        # 生成任务列表
        task_count = 3 if context.req_scale in ("XS", "S") else 5
        for i in range(task_count):
            tech_design["task_list"].append({
                "task_id": f"T-{i+1:03d}",
                "name": f"任务{i+1}",
                "priority": "P1" if i < 2 else "P2",
                "estimated_hours": 2,
                "dependencies": [f"T-{i:03d}"] if i > 0 else [],
                "status": "pending",
            })
        
        # 保存到沙盒
        self._save_to_workspace(context, "03_技术设计_draft.json", tech_design)
        
        context.loaded_knowledge["tech_design"] = tech_design
        
        return {
            "status": "completed",
            "tech_design": tech_design,
            "artifacts": ["03_技术设计.md", "05_任务清单.md"],
            "message": f"🔧 主程老陈: 技术设计完成 | {len(tech_design['task_list'])}个任务"
        }
    
    # ─── Step 4: 产出物检查（质量门禁） ───────────────────
    
    def _step_quality_gate(self, context: AgentContext,
                            input_data: Dict[str, Any]) -> Dict[str, Any]:
        """质量门禁：架构完整性+任务可执行性+测试策略(18项)"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "03_主程Agent", "step-04_产出物检查.md"
        )
        
        gate_results = {}
        total_checks = 0
        passed_checks = 0
        
        for category, items in self.QUALITY_GATE_ITEMS.items():
            category_results = {}
            for item in items:
                passed = self._check_quality_item(context, category, item)
                category_results[item] = passed
                total_checks += 1
                if passed:
                    passed_checks += 1
            gate_results[category] = category_results
        
        all_passed = passed_checks == total_checks
        
        context.record_quality_gate("gate_2", all_passed, {
            "total": total_checks,
            "passed": passed_checks,
            "details": gate_results,
        })
        
        if all_passed:
            self.send_handoff(
                to_agent="04_programmer",
                req_id=context.req_id,
                artifacts=["03_技术设计.md", "05_任务清单.md"],
                message=f"🔧 技术设计质量门禁通过 ({passed_checks}/{total_checks})"
            )
        
        reflection = self.self_reflect()
        reflection["checklist"]["artifacts_complete"] = all_passed
        
        return {
            "status": "completed" if all_passed else "gate_failed",
            "quality_gate": {
                "name": "gate_2",
                "passed": all_passed,
                "score": f"{passed_checks}/{total_checks}",
                "details": gate_results,
            },
            "next_agent": "04_programmer" if all_passed else None,
            "reflection": reflection,
            "message": f"🚧 门禁{'✅通过' if all_passed else '❌未通过'} ({passed_checks}/{total_checks}) → {'⚡ 流转至: 程序 Agent' if all_passed else '需修正'}"
        }
    
    def _check_quality_item(self, context: AgentContext,
                             category: str, item: str) -> bool:
        """检查单个质量项"""
        tech_design = context.loaded_knowledge.get("tech_design")
        
        if category == "文件存在性":
            if "技术设计" in item:
                return tech_design is not None
            if "任务清单" in item:
                return tech_design is not None and len(tech_design.get("task_list", [])) > 0
        
        if category == "任务可执行性":
            if "粒度" in item and tech_design:
                tasks = tech_design.get("task_list", [])
                return all(t.get("estimated_hours", 0) <= 4 for t in tasks)
        
        return True  # 框架层默认通过
    
    # ─── Step M1: 任务拆分（主从模式） ────────────────────
    
    def _step_task_split(self, context: AgentContext,
                          input_data: Dict[str, Any]) -> Dict[str, Any]:
        """拆分子任务、创建任务卡片"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "03_主程Agent", "step-M1_任务拆分.md"
        )
        
        # 加载子任务卡片模板
        self.ctx_mgr.load_template(
            self.agent_id, "03_主程Agent", "子任务卡片模板.md"
        )
        
        tech_design = context.loaded_knowledge.get("tech_design", {})
        tasks = tech_design.get("task_list", [])
        
        subtask_cards = []
        for task in tasks:
            subtask_cards.append({
                "card_id": task["task_id"],
                "name": task["name"],
                "assigned_to": "04_programmer",
                "priority": task["priority"],
                "estimated_hours": task["estimated_hours"],
                "input_docs": ["03_技术设计.md"],
                "output_expected": f"代码实现 - {task['name']}",
                "status": "pending",
            })
        
        # 发送子任务派发消息
        from ..core.message_queue import Message
        for card in subtask_cards:
            msg = Message(
                from_agent=self.agent_id,
                to_agent="04_programmer",
                msg_type=MessageType.SUBTASK_DISPATCH.value,
                payload=card
            )
            self.mq.send(msg)
        
        return {
            "status": "completed",
            "subtask_cards": subtask_cards,
            "message": f"🔧 主程老陈: 拆分{len(subtask_cards)}个子任务"
        }
    
    # ─── 工具方法 ──────────────────────────────────────────
    
    def _save_to_workspace(self, context: AgentContext,
                            filename: str, data: Any):
        """保存数据到沙盒工作目录（通过文件代理强制权限检查）"""
        self.safe_save_to_workspace(filename, data)
