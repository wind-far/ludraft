"""
美术Agent (Artist) - UI设计与美术需求

角色: 美术小周 🎨
职责:
- 设计UI界面布局
- 定义资源规格（尺寸/格式）
- 定义交互状态视觉表现
- 编写美术需求文档

规则来源: rules/agents/05_美术Agent.md
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from .base_agent import BaseAgent, AgentPersona, AgentPermissions, StepDefinition
from ..core.context_manager import AgentContext
from ..core.message_queue import MessageType


class ArtistAgent(BaseAgent):
    """
    美术Agent - UI/UX设计师，输出美术需求文档
    
    行为底线:
    - 绝不模糊资源规格
    - 绝不遗漏交互状态
    - 绝不写代码
    """
    
    # 标准资源规格
    STANDARD_FORMATS = {
        "icon": {"size": "128x128", "format": "PNG", "dpi": 72},
        "button": {"size": "256x64", "format": "PNG", "dpi": 72},
        "background": {"size": "1920x1080", "format": "PNG/JPG", "dpi": 72},
        "sprite": {"size": "variable", "format": "PNG", "dpi": 72},
        "atlas": {"size": "2048x2048", "format": "PNG", "dpi": 72},
    }
    
    # 交互状态列表
    UI_STATES = [
        "Normal",
        "Hover",
        "Pressed",
        "Disabled",
        "Selected",
        "Focus",
    ]
    
    def get_persona(self) -> AgentPersona:
        return AgentPersona(
            name="美术小周",
            icon="🎨",
            experience="5年游戏UI设计经验，注重视觉一致性和资源规格精确度",
            communication_style="视觉化表达、规格精确。每个元素都有明确的尺寸、色值、间距",
            decision_principle="一致性 > 创意。确保新UI与现有风格统一",
            behavior_bottom_line=[
                "绝不模糊资源规格",
                "绝不遗漏交互状态",
                "绝不写代码",
            ]
        )
    
    def get_permissions(self) -> AgentPermissions:
        return AgentPermissions(
            read=["plan_docs", "tech_design_ui", "art_knowledge_base"],
            write=[".GameDev/**/04_美术需求.md"],
            create=[".GameDev/**/04_美术需求.md"],
            delete=[],
            execute=[]
        )
    
    def get_steps(self) -> Dict[str, List[StepDefinition]]:
        return {
            "standard": [
                StepDefinition(
                    name="需求阅读与知识库",
                    file="step-01_需求阅读与知识库.md",
                    mode="EXPLORE",
                    description="阅读策划案、技术设计中的UI架构、读取知识库"
                ),
                StepDefinition(
                    name="UI设计",
                    file="step-02_UI设计.md",
                    mode="DESIGN",
                    description="布局设计、色彩规范、交互状态、动画需求、资源清单"
                ),
                StepDefinition(
                    name="产出物检查",
                    file="step-03_产出物检查.md",
                    mode="VERIFY",
                    description="质量检查、确认所有规格明确、流转"
                ),
            ],
        }
    
    def execute_step(self, step: StepDefinition, context: AgentContext,
                     input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行美术步骤"""
        input_data = input_data or {}
        
        step_handlers = {
            "需求阅读与知识库": self._step_read_requirements,
            "UI设计": self._step_ui_design,
            "产出物检查": self._step_quality_check,
        }
        
        handler = step_handlers.get(step.name)
        if not handler:
            raise ValueError(f"未知步骤: {step.name}")
        
        return handler(context, input_data)
    
    # ─── Step 1: 需求阅读与知识库 ─────────────────────────
    
    def _step_read_requirements(self, context: AgentContext,
                                 input_data: Dict[str, Any]) -> Dict[str, Any]:
        """阅读策划案、技术设计中的UI架构、读取知识库"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "05_美术Agent", "step-01_需求阅读与知识库.md"
        )
        
        self.ctx_mgr.load_agent_entry(self.agent_id, "05_美术Agent.md")
        
        # 检查流转消息
        handoff_messages = self.receive_messages(MessageType.HANDOFF.value)
        
        preparation = {
            "plan_reviewed": True,
            "tech_design_ui_section": True,
            "knowledge_loaded": True,
            "existing_art_style_loaded": True,
            "handoff_received": len(handoff_messages) > 0,
        }
        
        context.loaded_knowledge["preparation"] = preparation
        
        return {
            "status": "completed",
            "preparation": preparation,
            "message": f"🎨 美术小周: 需求阅读完成，知识库加载完成"
        }
    
    # ─── Step 2: UI设计 ──────────────────────────────────
    
    def _step_ui_design(self, context: AgentContext,
                         input_data: Dict[str, Any]) -> Dict[str, Any]:
        """布局设计、色彩规范、交互状态、动画需求、资源清单"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "05_美术Agent", "step-02_UI设计.md"
        )
        
        # 加载美术需求模板
        self.ctx_mgr.load_template(
            self.agent_id, "05_美术Agent", "美术需求模板.md"
        )
        
        art_requirement = {
            "req_id": context.req_id,
            "req_name": context.req_name,
            "layout": {
                "description": "待设计",
                "responsive": {
                    "min_resolution": "1280x720",
                    "max_resolution": "1920x1080",
                    "safe_area": True,
                },
            },
            "color_scheme": {
                "primary": "#3498db",
                "secondary": "#2ecc71",
                "accent": "#e74c3c",
                "background": "#2c3e50",
                "text": "#ecf0f1",
            },
            "ui_elements": [],
            "resource_list": [],
            "animations": [],
            "created_at": datetime.now().isoformat(),
        }
        
        # 定义UI元素及其状态
        sample_elements = [
            {"name": "主按钮", "type": "button"},
            {"name": "次级按钮", "type": "button"},
            {"name": "标题文字", "type": "text"},
            {"name": "列表项", "type": "list_item"},
        ]
        
        for elem in sample_elements:
            element_spec = {
                "name": elem["name"],
                "type": elem["type"],
                "states": {},
                "specs": {},
            }
            
            # 为每个元素定义所有交互状态
            for state in self.UI_STATES:
                element_spec["states"][state] = {
                    "visual_description": f"{elem['name']} - {state}态",
                    "color": "",
                    "opacity": 1.0 if state != "Disabled" else 0.5,
                }
            
            # 资源规格
            resource_type = "button" if elem["type"] == "button" else "sprite"
            element_spec["specs"] = self.STANDARD_FORMATS.get(resource_type, {}).copy()
            
            art_requirement["ui_elements"].append(element_spec)
            
            # 添加到资源清单
            art_requirement["resource_list"].append({
                "name": f"{elem['name']}_atlas",
                "type": resource_type,
                "format": element_spec["specs"].get("format", "PNG"),
                "size": element_spec["specs"].get("size", "variable"),
                "states_count": len(self.UI_STATES),
            })
        
        # 动画需求
        art_requirement["animations"] = [
            {
                "name": "按钮点击反馈",
                "type": "scale",
                "duration": "0.15s",
                "easing": "ease-out",
                "from": "1.0",
                "to": "0.95",
            },
            {
                "name": "页面切换过渡",
                "type": "fade",
                "duration": "0.3s",
                "easing": "ease-in-out",
            },
        ]
        
        self._save_to_workspace(context, "04_美术需求_draft.json", art_requirement)
        context.loaded_knowledge["art_requirement"] = art_requirement
        
        return {
            "status": "completed",
            "art_requirement": art_requirement,
            "message": f"🎨 美术小周: UI设计完成 | {len(art_requirement['ui_elements'])}个元素 | {len(art_requirement['resource_list'])}项资源"
        }
    
    # ─── Step 3: 产出物检查 ───────────────────────────────
    
    def _step_quality_check(self, context: AgentContext,
                             input_data: Dict[str, Any]) -> Dict[str, Any]:
        """质量检查、确认所有规格明确、流转"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "05_美术Agent", "step-03_产出物检查.md"
        )
        
        art_req = context.loaded_knowledge.get("art_requirement", {})
        
        # 质量检查
        quality_checks = {
            "多分辨率适配": art_req.get("layout", {}).get("responsive") is not None,
            "资源规格明确": self._check_resource_specs(art_req),
            "交互状态完整": self._check_interaction_states(art_req),
            "动画参数明确": self._check_animation_params(art_req),
            "色彩规范统一": art_req.get("color_scheme") is not None,
        }
        
        all_passed = all(quality_checks.values())
        
        if all_passed:
            # 美术与程序并行工作
            self.mq.broadcast(
                from_agent=self.agent_id,
                payload={
                    "action": "art_requirement_ready",
                    "req_id": context.req_id,
                    "artifacts": ["04_美术需求.md"],
                }
            )
        
        reflection = self.self_reflect()
        reflection["checklist"]["artifacts_complete"] = all_passed
        
        return {
            "status": "completed",
            "quality_checks": quality_checks,
            "all_passed": all_passed,
            "reflection": reflection,
            "artifacts": ["04_美术需求.md"],
            "message": f"🎨 美术小周: 产出物检查{'✅通过' if all_passed else '❌未通过'} → ⚡ 美术需求已输出，与程序 Agent 并行工作"
        }
    
    def _check_resource_specs(self, art_req: Dict[str, Any]) -> bool:
        """检查所有资源规格是否明确"""
        for resource in art_req.get("resource_list", []):
            if not resource.get("format") or not resource.get("size"):
                return False
        return True
    
    def _check_interaction_states(self, art_req: Dict[str, Any]) -> bool:
        """检查交互状态是否完整"""
        required = {"Normal", "Hover", "Pressed", "Disabled"}
        for elem in art_req.get("ui_elements", []):
            if elem.get("type") in ("button", "list_item"):
                defined = set(elem.get("states", {}).keys())
                if not required.issubset(defined):
                    return False
        return True
    
    def _check_animation_params(self, art_req: Dict[str, Any]) -> bool:
        """检查动画参数是否明确"""
        for anim in art_req.get("animations", []):
            if not anim.get("duration") or not anim.get("type"):
                return False
        return True
    
    # ─── 工具方法 ──────────────────────────────────────────
    
    def _save_to_workspace(self, context: AgentContext,
                            filename: str, data: Any):
        """保存数据到沙盒工作目录（通过文件代理强制权限检查）"""
        self.safe_save_to_workspace(filename, data)
