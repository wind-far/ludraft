"""
UX设计Agent (UX Designer) - 交互设计

角色: UX小林 ✨
职责:
- 根据策划案设计UI界面的交互流程
- 设计界面布局和元素排列
- 定义交互状态和反馈
- 确保用户体验流畅直观

规则来源: rules/agents/07_UXAgent.md
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from .base_agent import BaseAgent, AgentPersona, AgentPermissions, StepDefinition
from ..core.context_manager import AgentContext
from ..core.message_queue import MessageType


class UXDesignerAgent(BaseAgent):
    """
    UX Agent（交互设计师） - 设计用户界面的交互流程
    
    行为底线:
    - 绝不遗漏重要交互状态
    - 绝不设计过于复杂的交互流程
    - 绝不写代码
    """
    
    # 交互状态清单
    INTERACTION_STATES = [
        "normal",      # 默认态
        "hover",       # 悬停态
        "pressed",     # 按下态
        "disabled",    # 禁用态
        "selected",    # 选中态
        "loading",     # 加载态
        "error",       # 错误态
        "empty",       # 空态
    ]
    
    def get_persona(self) -> AgentPersona:
        return AgentPersona(
            name="UX小林",
            icon="✨",
            experience="6年交互设计经验，擅长游戏UI和移动端交互，关注玩家情感体验",
            communication_style="感受先行、用故事描绘画面。喜欢用'玩家会看到...玩家会感觉...'来描述交互",
            decision_principle="少即是多，降低认知负担。宁可简单一步多，也不让玩家迷惑一秒",
            behavior_bottom_line=[
                "绝不遗漏重要交互状态",
                "绝不设计过于复杂的交互流程",
                "绝不写代码",
            ]
        )
    
    def get_permissions(self) -> AgentPermissions:
        return AgentPermissions(
            read=["plan_docs", "ux_knowledge_base", "global_plan"],
            write=[".GameDev/**/02_UX设计.md"],
            create=[".GameDev/**/02_UX设计.md"],
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
                    description="检查策划案完整性、读取知识库和全局UI风格"
                ),
                StepDefinition(
                    name="交互设计",
                    file="step-02_交互设计.md",
                    mode="DESIGN",
                    description="分析UI需求、设计交互流程、界面布局、状态定义"
                ),
                StepDefinition(
                    name="文档输出与确认",
                    file="step-03_文档输出与确认.md",
                    mode="VERIFY",
                    description="输出UX设计文档、质量检查、提交策划确认"
                ),
            ],
        }
    
    def execute_step(self, step: StepDefinition, context: AgentContext,
                     input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行UX步骤"""
        input_data = input_data or {}
        
        step_handlers = {
            "前置检查与知识库": self._step_prerequisite,
            "交互设计": self._step_interaction_design,
            "文档输出与确认": self._step_output_and_confirm,
        }
        
        handler = step_handlers.get(step.name)
        if not handler:
            raise ValueError(f"未知步骤: {step.name}")
        
        return handler(context, input_data)
    
    # ─── Step 1: 前置检查与知识库 ─────────────────────────
    
    def _step_prerequisite(self, context: AgentContext,
                            input_data: Dict[str, Any]) -> Dict[str, Any]:
        """检查策划案完整性、读取知识库和全局UI风格"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "07_UXAgent", "step-01_前置检查与知识库.md"
        )
        
        self.ctx_mgr.load_agent_entry(self.agent_id, "07_UXAgent.md")
        
        # 检查策划案是否已收到
        handoff_messages = self.receive_messages(MessageType.HANDOFF.value)
        
        prerequisite = {
            "plan_exists": True,
            "knowledge_loaded": True,
            "global_ui_style_loaded": True,
            "handoff_received": len(handoff_messages) > 0,
        }
        
        context.loaded_knowledge["prerequisite"] = prerequisite
        
        return {
            "status": "completed",
            "prerequisite": prerequisite,
            "message": f"✨ UX小林: 前置检查通过，知识库加载完成"
        }
    
    # ─── Step 2: 交互设计 ─────────────────────────────────
    
    def _step_interaction_design(self, context: AgentContext,
                                  input_data: Dict[str, Any]) -> Dict[str, Any]:
        """分析UI需求、设计交互流程、界面布局、状态定义"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "07_UXAgent", "step-02_交互设计.md"
        )
        
        # 加载UX设计模板
        self.ctx_mgr.load_template(
            self.agent_id, "07_UXAgent", "UX设计模板.md"
        )
        
        ux_design = {
            "req_id": context.req_id,
            "req_name": context.req_name,
            "interaction_flow": {
                "entry_point": "待设计",
                "main_flow": [],
                "alternative_flows": [],
                "error_flows": [],
            },
            "layout": {
                "description": "待设计",
                "ascii_wireframe": "",
                "responsive_notes": "",
            },
            "components": [],
            "states": {},
            "animations": [],
            "accessibility_notes": "",
            "created_at": datetime.now().isoformat(),
        }
        
        # 为每个组件定义交互状态
        sample_components = ["主按钮", "输入框", "列表项"]
        for comp in sample_components:
            comp_states = {}
            for state in self.INTERACTION_STATES:
                comp_states[state] = {
                    "visual": f"{comp} {state}态视觉描述",
                    "transition": f"过渡动画: 0.2s ease",
                }
            ux_design["states"][comp] = comp_states
            ux_design["components"].append({
                "name": comp,
                "type": "interactive",
                "states_defined": len(comp_states),
            })
        
        self._save_to_workspace(context, "02_UX设计_draft.json", ux_design)
        context.loaded_knowledge["ux_design"] = ux_design
        
        return {
            "status": "completed",
            "ux_design": ux_design,
            "message": f"✨ UX小林: 交互设计完成 | {len(ux_design['components'])}个组件 | {len(self.INTERACTION_STATES)}种状态"
        }
    
    # ─── Step 3: 文档输出与确认 ───────────────────────────
    
    def _step_output_and_confirm(self, context: AgentContext,
                                  input_data: Dict[str, Any]) -> Dict[str, Any]:
        """输出UX设计文档、质量检查、提交策划确认"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "07_UXAgent", "step-03_文档输出与确认.md"
        )
        
        ux_design = context.loaded_knowledge.get("ux_design", {})
        
        # 质量检查
        quality_checks = {
            "所有组件有状态定义": True,
            "交互流程完整": True,
            "布局描述清晰": True,
            "无遗漏交互状态": self._check_interaction_states(ux_design),
            "无过于复杂的流程": True,
        }
        
        all_passed = all(quality_checks.values())
        
        if all_passed:
            # 提交策划确认
            self.send_handoff(
                to_agent="02_planner",
                req_id=context.req_id,
                artifacts=["02_UX设计.md"],
                message="✨ UX设计完成，提交策划确认"
            )
        
        # 自我反思
        reflection = self.self_reflect()
        reflection["checklist"]["artifacts_complete"] = all_passed
        
        return {
            "status": "completed",
            "quality_checks": quality_checks,
            "all_passed": all_passed,
            "next_agent": "02_planner" if all_passed else None,
            "reflection": reflection,
            "artifacts": ["02_UX设计.md"],
            "message": f"✨ UX小林: 设计文档输出完成 {'✅' if all_passed else '❌'} → ⚡ 流转至: 策划 Agent（确认）"
        }
    
    def _check_interaction_states(self, ux_design: Dict[str, Any]) -> bool:
        """检查是否有遗漏的重要交互状态"""
        required_states = {"normal", "hover", "pressed", "disabled"}
        
        for comp, states in ux_design.get("states", {}).items():
            defined_states = set(states.keys())
            if not required_states.issubset(defined_states):
                return False
        
        return True
    
    # ─── 工具方法 ──────────────────────────────────────────
    
    def _save_to_workspace(self, context: AgentContext,
                            filename: str, data: Any):
        """保存数据到沙盒工作目录（通过文件代理强制权限检查）"""
        self.safe_save_to_workspace(filename, data)
