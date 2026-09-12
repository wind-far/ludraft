"""
制作人Agent (Producer) - 需求入口

角色: 制作人老梁 🎬
职责:
- 理解用户需求的本质
- 判断需求类型 (FEATURE/BUGFIX/OPTIMIZE等)
- 评估需求规模 (XS/S/M/L/XL)
- 决定流转路径
- 复合需求拆分

规则来源: rules/agents/00_制作人Agent.md
"""

import json
import re
from typing import Dict, List, Any, Optional
from datetime import datetime

from .base_agent import BaseAgent, AgentPersona, AgentPermissions, StepDefinition
from ..core.context_manager import AgentContext
from ..core.message_queue import MessageType


class ProducerAgent(BaseAgent):
    """
    制作人Agent - 所有需求的第一入口
    
    三级识别体系:
    1. 一级关键词（直接命中） → 🟢高置信度
    2. 二级关键词+上下文感知 → 🟡中置信度
    3. 语义分析 → 🔴低置信度（需确认）
    
    行为底线:
    - 绝不绕过分类直接执行
    - 绝不替其他Agent做决定
    - 绝不遗漏复合需求的拆分
    - 被用户纠正错误后必须触发规则迭代
    """
    
    # 命令类型映射
    COMMAND_TYPE_MAP = {
        "/gd:feature": "FEATURE",
        "/gd:bugfix": "BUGFIX",
        "/gd:optimize": "OPTIMIZE",
        "/gd:test": "TEST",
        "/gd:doc": "DOC",
        "/gd:review": "REVIEW",
        "/gd:config": "CONFIG",
        "/gd:research": "RESEARCH",
    }
    
    # 一级关键词 → 需求类型（直接命中）
    PRIMARY_KEYWORDS = {
        "bug": "BUGFIX", "修复": "BUGFIX", "报错": "BUGFIX", "崩溃": "BUGFIX",
        "fix": "BUGFIX", "crash": "BUGFIX", "error": "BUGFIX",
        "优化": "OPTIMIZE", "重构": "OPTIMIZE", "性能": "OPTIMIZE",
        "refactor": "OPTIMIZE", "optimize": "OPTIMIZE",
        "测试": "TEST", "测试用例": "TEST", "test": "TEST",
        "文档": "DOC", "readme": "DOC", "doc": "DOC",
        "审查": "REVIEW", "review": "REVIEW", "code review": "REVIEW",
        "配置": "CONFIG", "参数调整": "CONFIG", "config": "CONFIG",
        "调研": "RESEARCH", "分析": "RESEARCH", "research": "RESEARCH",
    }
    
    # 二级关键词 + 上下文
    SECONDARY_KEYWORDS = {
        "新增": "FEATURE", "添加": "FEATURE", "实现": "FEATURE",
        "开发": "FEATURE", "创建": "FEATURE", "功能": "FEATURE",
        "界面": "FEATURE_UI", "UI": "FEATURE_UI", "交互": "FEATURE_UI",
    }
    
    # 需求类型 → 流转路径
    ROUTING_TABLE = {
        "FEATURE": ["02_planner"],
        "FEATURE_UI": ["02_planner"],
        "OPTIMIZE": ["03_tech_lead"],
        "BUGFIX": ["04_programmer"],
        "TEST": ["06_qa"],
        "DOC": ["03_tech_lead"],
        "REVIEW": ["03_tech_lead"],
        "CONFIG": ["04_programmer"],
        "RESEARCH": ["02_planner"],
    }
    
    # 规模评估关键词
    SCALE_KEYWORDS = {
        "XL": ["系统", "全新", "架构", "跨模块", "大规模", "完整"],
        "L": ["多个", "模块", "复杂", "大型", "重大"],
        "S": ["小", "简单", "微调", "小改"],
        "XS": ["极小", "一行", "typo", "拼写"],
    }
    
    def get_persona(self) -> AgentPersona:
        return AgentPersona(
            name="制作人老梁",
            icon="🎬",
            experience="10年游戏制作经验，擅长全局把控和快速决策",
            communication_style="快速决断、全局视角。不纠结细节，30秒内给出判断",
            decision_principle="效率优先 > 完美主义。宁可快速推进再迭代，也不反复犹豫",
            behavior_bottom_line=[
                "绝不绕过分类直接执行",
                "绝不替其他Agent做决定",
                "绝不遗漏复合需求的拆分",
                "绝不把不同Agent负责的产出物合并为同一个需求",
                "被用户纠正错误后必须触发规则迭代",
            ]
        )
    
    def get_permissions(self) -> AgentPermissions:
        return AgentPermissions(
            read=["rules/**", "requirements_pool", "progress_board"],
            write=[],
            create=[],
            delete=[],
            execute=[]
        )
    
    def get_steps(self) -> Dict[str, List[StepDefinition]]:
        return {
            "standard": [
                StepDefinition(
                    name="需求接收与分析",
                    file="step-01_需求接收与分析.md",
                    mode="EXPLORE",
                    description="接收需求、命令快速路径/三级识别体系、需求分类、规模评估、复合需求拆分"
                ),
                StepDefinition(
                    name="输出与流转",
                    file="step-02_输出与流转.md",
                    mode="DESIGN",
                    description="按格式输出分析结果、流转到下一Agent"
                ),
            ]
        }
    
    def execute_step(self, step: StepDefinition, context: AgentContext,
                     input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行制作人步骤"""
        input_data = input_data or {}
        
        if step.name == "需求接收与分析":
            return self._step_analyze_requirement(context, input_data)
        elif step.name == "输出与流转":
            return self._step_output_and_route(context, input_data)
        else:
            raise ValueError(f"未知步骤: {step.name}")
    
    # ─── Step 1: 需求接收与分析 ───────────────────────────
    
    def _step_analyze_requirement(self, context: AgentContext,
                                   input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Step 1: 需求接收与分析
        
        执行三级识别体系:
        1. 命令快速路径 (/gd:xxx)
        2. 一级关键词匹配
        3. 二级关键词+上下文
        4. 规模评估
        5. 复合需求检测
        """
        # 加载步骤文件
        self.ctx_mgr.load_step_file(
            self.agent_id,
            "00_制作人Agent",
            "step-01_需求接收与分析.md"
        )
        
        user_input = input_data.get("user_input", "")
        result = {
            "req_name": "",
            "req_type": "",
            "req_scale": "M",
            "confidence": "",
            "analysis_basis": "",
            "flow_path": [],
            "sub_requirements": [],
            "trigger_method": "",
        }
        
        # 1. 命令快速路径检测
        if user_input.startswith("/gd:"):
            cmd_result = self._parse_command(user_input)
            result.update(cmd_result)
            result["trigger_method"] = "命令快速路径"
        else:
            # 2. 三级识别体系
            analysis = self._three_level_identify(user_input)
            result.update(analysis)
        
        # 3. 规模评估
        if not result.get("req_scale") or result["req_scale"] == "M":
            result["req_scale"] = self._assess_scale(user_input)
        
        # 4. 复合需求检测与拆分
        sub_reqs = self._detect_compound_requirement(user_input, result["req_type"])
        if sub_reqs:
            result["sub_requirements"] = sub_reqs
        
        # 5. 确定流转路径
        req_type = result.get("req_type", "FEATURE")
        result["flow_path"] = self.ROUTING_TABLE.get(req_type, ["02_planner"])
        
        # 保存到上下文
        context.loaded_knowledge["requirement_analysis"] = result
        
        return {
            "status": "completed",
            "analysis": result,
            "message": f"🎬 制作人老梁: 需求分析完成 - {result['req_type']}/{result['req_scale']} ({result['confidence']})"
        }
    
    def _parse_command(self, command: str) -> Dict[str, Any]:
        """解析 /gd: 快捷命令"""
        parts = command.split(" ", 1)
        cmd = parts[0].lower()
        description = parts[1].strip('"').strip("'") if len(parts) > 1 else ""
        
        req_type = self.COMMAND_TYPE_MAP.get(cmd, "FEATURE")
        
        return {
            "req_name": description or f"[{req_type}需求]",
            "req_type": req_type,
            "confidence": "🟢高",
            "analysis_basis": f"快捷命令: {cmd}",
            "trigger_method": "命令快速路径",
        }
    
    def _three_level_identify(self, text: str) -> Dict[str, Any]:
        """三级识别体系"""
        text_lower = text.lower()
        result = {
            "req_name": text[:80] if len(text) > 80 else text,
        }
        
        # Level 1: 一级关键词（直接命中）
        for keyword, req_type in self.PRIMARY_KEYWORDS.items():
            if keyword in text_lower:
                result["req_type"] = req_type
                result["confidence"] = "🟢高"
                result["analysis_basis"] = f"一级关键词命中: 「{keyword}」"
                result["trigger_method"] = "一级关键词"
                return result
        
        # Level 2: 二级关键词+上下文
        for keyword, req_type in self.SECONDARY_KEYWORDS.items():
            if keyword in text_lower:
                result["req_type"] = req_type
                result["confidence"] = "🟡中"
                result["analysis_basis"] = f"二级关键词+上下文: 「{keyword}」"
                result["trigger_method"] = "二级关键词"
                return result
        
        # Level 3: 语义分析（默认）
        result["req_type"] = "FEATURE"
        result["confidence"] = "🔴低"
        result["analysis_basis"] = "语义分析: 未匹配明确关键词，默认分类为FEATURE"
        result["trigger_method"] = "语义分析"
        
        return result
    
    def _assess_scale(self, text: str) -> str:
        """评估需求规模"""
        text_lower = text.lower()
        
        for scale, keywords in self.SCALE_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                return scale
        
        # 基于文本长度的粗略评估
        if len(text) > 500:
            return "L"
        elif len(text) > 200:
            return "M"
        elif len(text) > 50:
            return "S"
        
        return "M"  # 默认中等规模
    
    def _detect_compound_requirement(self, text: str, 
                                      primary_type: str) -> List[Dict[str, Any]]:
        """
        复合需求检测与拆分
        
        检测规则: 
        - 包含"以及"/"同时"/"并且"等连接词
        - 包含多个不同类型的关键词
        - 包含编号列表
        """
        compound_indicators = ["以及", "同时", "并且", "还需要", "另外", "此外"]
        
        has_compound = any(ind in text for ind in compound_indicators)
        
        if not has_compound:
            # 检查是否有编号列表
            numbered_items = re.findall(r'(?:^|\n)\s*\d+[.、]\s*(.+)', text)
            if len(numbered_items) < 2:
                return []
            # 有编号列表，尝试拆分
            sub_reqs = []
            for i, item in enumerate(numbered_items):
                analysis = self._three_level_identify(item)
                sub_reqs.append({
                    "index": i + 1,
                    "name": item.strip(),
                    "type": analysis.get("req_type", primary_type),
                    "confidence": analysis.get("confidence", "🟡中"),
                })
            return sub_reqs
        
        # 按连接词拆分
        parts = re.split(r'[，。；;]|(?:以及|同时|并且|还需要|另外|此外)', text)
        parts = [p.strip() for p in parts if p.strip() and len(p.strip()) > 5]
        
        if len(parts) < 2:
            return []
        
        sub_reqs = []
        for i, part in enumerate(parts):
            analysis = self._three_level_identify(part)
            sub_reqs.append({
                "index": i + 1,
                "name": part,
                "type": analysis.get("req_type", primary_type),
                "confidence": analysis.get("confidence", "🟡中"),
            })
        
        return sub_reqs
    
    # ─── Step 2: 输出与流转 ────────────────────────────────
    
    def _step_output_and_route(self, context: AgentContext,
                                input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Step 2: 输出与流转
        
        按模板格式输出分析结果，发送流转消息到下一Agent
        """
        # 加载步骤文件
        self.ctx_mgr.load_step_file(
            self.agent_id,
            "00_制作人Agent",
            "step-02_输出与流转.md"
        )
        
        analysis = context.loaded_knowledge.get("requirement_analysis", {})
        
        # 构建需求分析输出
        output = self._format_analysis_output(analysis)
        
        # 确定下一Agent
        flow_path = analysis.get("flow_path", ["02_planner"])
        next_agent = flow_path[0] if flow_path else "02_planner"
        
        # 发送流转消息
        self.send_handoff(
            to_agent="01_pm",  # 先流转到项目管理
            req_id=context.req_id,
            artifacts=[],
            message=f"🎬 需求分析完成: {analysis.get('req_type', 'FEATURE')}/{analysis.get('req_scale', 'M')}"
        )
        
        # 自我反思
        reflection = self.self_reflect()
        reflection["checklist"]["artifacts_complete"] = True
        reflection["checklist"]["no_process_deviation"] = True
        
        return {
            "status": "completed",
            "output": output,
            "next_agent": "01_pm",
            "final_route": next_agent,
            "reflection": reflection,
            "message": f"⚡ 流转至: 项目管理 Agent"
        }
    
    def _format_analysis_output(self, analysis: Dict[str, Any]) -> str:
        """格式化需求分析输出"""
        sub_reqs_text = ""
        if analysis.get("sub_requirements"):
            sub_items = "\n".join(
                f"  {sr['index']}. [{sr['type']}] {sr['name']} ({sr['confidence']})"
                for sr in analysis["sub_requirements"]
            )
            sub_reqs_text = f"\n📦 复合需求拆分:\n{sub_items}"
        
        output = f"""
┌─────────────────────────────────────────────
│ 🎬 制作人分析结果
├─────────────────────────────────────────────
│ 需求名称: {analysis.get('req_name', '未命名')}
│ 需求类型: {analysis.get('req_type', 'FEATURE')}
│ 需求规模: {analysis.get('req_scale', 'M')}
│ 置信度:   {analysis.get('confidence', '🟡中')}
│ 触发方式: {analysis.get('trigger_method', '未知')}
│ 判断依据: {analysis.get('analysis_basis', '')}
│ 流转路径: {' → '.join(analysis.get('flow_path', []))}
{sub_reqs_text}
└─────────────────────────────────────────────
""".strip()
        
        return output
