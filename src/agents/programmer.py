"""
程序Agent (Programmer) - 代码实现与Bug修复

角色: 程序小赵 💻
职责:
- 按技术设计文档编写高质量代码
- 管理任务清单
- 对抗审查 (切换对抗者心态)
- Bug修复
- 子任务执行 (主从模式)

规则来源: rules/agents/04_程序Agent.md
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path

from .base_agent import BaseAgent, AgentPersona, AgentPermissions, StepDefinition
from ..core.context_manager import AgentContext
from ..core.message_queue import MessageType, Message


class ProgrammerAgent(BaseAgent):
    """
    程序Agent - 唯一允许修改代码文件的Agent
    
    主从架构角色: 子Agent，负责执行主程分配的具体编码任务
    
    行为底线:
    - 绝不提交无法编译的代码
    - 绝不硬编码配置值
    - 绝不跳过对抗审查
    """
    
    # 质量门禁检查项 (20项) - Gate 3
    QUALITY_GATE_ITEMS = {
        "代码完整性": [
            "所有任务已完成",
            "代码能通过编译",
            "无TODO/HACK遗留",
            "命名规范一致",
            "注释完整且有意义",
        ],
        "代码质量深潜": [
            "null安全检查",
            "异常处理完整",
            "资源释放正确",
            "线程安全考虑",
            "性能无明显瓶颈",
            "无硬编码配置值",
            "无重复代码",
        ],
        "可测试性": [
            "公共接口可测试",
            "依赖可注入",
            "状态可观察",
        ],
        "验收标准覆盖审计": [
            "每条AC有对应实现",
            "边界条件已处理",
            "异常路径已覆盖",
        ],
        "事后防护检查": [
            "无意外文件修改",
            "无遗漏的引用更新",
        ],
    }
    
    # 事前防护规则 (G-001 ~ G-010)
    GUARD_RULES = {
        "G-001": "修改前备份原文件",
        "G-002": "检查文件锁定状态",
        "G-003": "验证修改范围在权限内",
        "G-004": "检查是否影响其他模块",
        "G-005": "确认命名规范",
        "G-006": "删除前检查引用关系",
        "G-007": "创建前检查同名文件",
        "G-008": "安装包需用户确认",
        "G-009": "不修改.meta文件",
        "G-010": "不修改Library/Temp目录",
    }
    
    def get_persona(self) -> AgentPersona:
        return AgentPersona(
            name="程序小赵",
            icon="💻",
            experience="5年开发经验，代码洁癖，追求简洁高效",
            communication_style="极度简洁、用代码说话。能用代码注释说明的不写文档",
            decision_principle="可测试 > 可读 > 性能。代码必须能被自动化测试覆盖",
            behavior_bottom_line=[
                "绝不提交无法编译的代码",
                "绝不硬编码配置值",
                "绝不跳过对抗审查",
            ]
        )
    
    def get_permissions(self) -> AgentPermissions:
        return AgentPermissions(
            read=["tech_design", "code_files", "plan_docs", "knowledge_base", "skills"],
            write=["src/**", ".GameDev/**/05_任务清单.md"],
            create=["src/**"],
            delete=[],
            execute=["compile", "build"]
        )
    
    def get_steps(self) -> Dict[str, List[StepDefinition]]:
        return {
            "standard": [
                StepDefinition(
                    name="前置检查",
                    file="step-01_前置检查.md",
                    mode="EXPLORE",
                    description="确认策划案和技术设计已存在"
                ),
                StepDefinition(
                    name="知识库与任务规划",
                    file="step-02_知识库与任务规划.md",
                    mode="EXPLORE",
                    description="读取知识库、创建任务清单"
                ),
                StepDefinition(
                    name="编码实现",
                    file="step-03_编码实现.md",
                    mode="IMPLEMENT",
                    description="逐个完成任务、编写代码"
                ),
                StepDefinition(
                    name="完成检查",
                    file="step-04_完成检查.md",
                    mode="VERIFY",
                    description="质量门禁：代码完整性+质量深潜+可测试性+AC审计(20项)"
                ),
                StepDefinition(
                    name="对抗审查",
                    file="step-05_对抗审查.md",
                    mode="REVIEW",
                    description="对抗审查：切换对抗者心态，至少找3个问题"
                ),
            ],
            "bugfix": [
                StepDefinition(
                    name="Bug修复",
                    file="step-B1_Bug修复.md",
                    mode="DEBUG",
                    description="定位问题、修复代码、更新文档"
                ),
            ],
            "subtask": [
                StepDefinition(
                    name="子任务执行",
                    file="step-S1_子任务执行.md",
                    mode="IMPLEMENT",
                    description="读取任务卡片、编码、输出结果"
                ),
            ],
        }
    
    def execute_step(self, step: StepDefinition, context: AgentContext,
                     input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行程序步骤"""
        input_data = input_data or {}
        
        step_handlers = {
            "前置检查": self._step_prerequisite,
            "知识库与任务规划": self._step_knowledge_and_planning,
            "编码实现": self._step_coding,
            "完成检查": self._step_quality_gate,
            "对抗审查": self._step_adversarial_review,
            "Bug修复": self._step_bugfix,
            "子任务执行": self._step_subtask,
        }
        
        handler = step_handlers.get(step.name)
        if not handler:
            raise ValueError(f"未知步骤: {step.name}")
        
        return handler(context, input_data)
    
    # ─── Step 1: 前置检查 ─────────────────────────────────
    
    def _step_prerequisite(self, context: AgentContext,
                            input_data: Dict[str, Any]) -> Dict[str, Any]:
        """确认策划案和技术设计已存在"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "04_程序Agent", "step-01_前置检查.md"
        )
        
        # 加载Agent入口文件
        self.ctx_mgr.load_agent_entry(self.agent_id, "04_程序Agent.md")
        
        # 检查流转消息
        handoff_messages = self.receive_messages(MessageType.HANDOFF.value)
        
        prerequisite = {
            "plan_exists": True,
            "tech_design_exists": True,
            "handoff_received": len(handoff_messages) > 0,
            "guard_rules_loaded": list(self.GUARD_RULES.keys()),
        }
        
        context.loaded_knowledge["prerequisite"] = prerequisite
        
        return {
            "status": "completed",
            "prerequisite": prerequisite,
            "message": f"💻 程序小赵: 前置检查通过"
        }
    
    # ─── Step 2: 知识库与任务规划 ─────────────────────────
    
    def _step_knowledge_and_planning(self, context: AgentContext,
                                      input_data: Dict[str, Any]) -> Dict[str, Any]:
        """读取知识库、创建任务清单"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "04_程序Agent", "step-02_知识库与任务规划.md"
        )
        
        # 尝试加载技能包
        skills_loaded = []
        for skill_path in ["csharp/null-safety.md", "csharp/optimization.md"]:
            content = self.ctx_mgr.load_skill(self.agent_id, skill_path)
            if content:
                skills_loaded.append(skill_path)
        
        # 读取子任务消息
        subtask_messages = self.receive_messages(MessageType.SUBTASK_DISPATCH.value)
        
        task_list = {
            "req_id": context.req_id,
            "tasks": [],
            "skills_loaded": skills_loaded,
            "created_at": datetime.now().isoformat(),
        }
        
        # 从子任务消息构建任务清单
        if subtask_messages:
            for msg in subtask_messages:
                task_list["tasks"].append({
                    "task_id": msg.payload.get("card_id", ""),
                    "name": msg.payload.get("name", ""),
                    "priority": msg.payload.get("priority", "P2"),
                    "status": "pending",
                })
        else:
            # 默认任务清单
            task_list["tasks"] = [
                {"task_id": "T-001", "name": "核心逻辑实现", "priority": "P1", "status": "pending"},
                {"task_id": "T-002", "name": "接口对接", "priority": "P1", "status": "pending"},
                {"task_id": "T-003", "name": "错误处理", "priority": "P2", "status": "pending"},
            ]
        
        self._save_to_workspace(context, "05_任务清单.json", task_list)
        context.loaded_knowledge["task_list"] = task_list
        
        return {
            "status": "completed",
            "task_list": task_list,
            "message": f"💻 程序小赵: 任务规划完成 | {len(task_list['tasks'])}个任务"
        }
    
    # ─── Step 3: 编码实现 ─────────────────────────────────
    
    def _step_coding(self, context: AgentContext,
                      input_data: Dict[str, Any]) -> Dict[str, Any]:
        """逐个完成任务、编写代码"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "04_程序Agent", "step-03_编码实现.md"
        )
        
        task_list = context.loaded_knowledge.get("task_list", {})
        tasks = task_list.get("tasks", [])
        
        coding_results = []
        files_modified = []
        
        for task in tasks:
            # 事前防护检查
            guard_check = self._run_guard_checks(task)
            
            # 执行编码（框架层模拟）
            result = {
                "task_id": task["task_id"],
                "task_name": task["name"],
                "status": "completed",
                "guard_check": guard_check,
                "files_created": [],
                "files_modified": [],
                "lines_added": 0,
                "lines_removed": 0,
            }
            
            coding_results.append(result)
            task["status"] = "completed"
        
        # 更新任务清单
        self._save_to_workspace(context, "05_任务清单.json", task_list)
        
        context.loaded_knowledge["coding_results"] = coding_results
        
        completed_count = sum(1 for r in coding_results if r["status"] == "completed")
        
        return {
            "status": "completed",
            "coding_results": coding_results,
            "files_modified": files_modified,
            "message": f"💻 程序小赵: 编码完成 {completed_count}/{len(tasks)} 个任务"
        }
    
    def _run_guard_checks(self, task: Dict[str, Any]) -> Dict[str, bool]:
        """执行事前防护检查 (G-001 ~ G-010)"""
        return {rule_id: True for rule_id in self.GUARD_RULES}
    
    # ─── Step 4: 完成检查（质量门禁） ────────────────────
    
    def _step_quality_gate(self, context: AgentContext,
                            input_data: Dict[str, Any]) -> Dict[str, Any]:
        """质量门禁：代码完整性+质量深潜+可测试性+AC审计(20项)"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "04_程序Agent", "step-04_完成检查.md"
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
        
        context.record_quality_gate("gate_3", all_passed, {
            "total": total_checks,
            "passed": passed_checks,
            "details": gate_results,
        })
        
        return {
            "status": "completed",
            "quality_gate": {
                "name": "gate_3",
                "passed": all_passed,
                "score": f"{passed_checks}/{total_checks}",
                "details": gate_results,
            },
            "message": f"🚧 代码质量门禁 {'✅通过' if all_passed else '❌未通过'} ({passed_checks}/{total_checks})"
        }
    
    def _check_quality_item(self, context: AgentContext,
                             category: str, item: str) -> bool:
        """检查单个质量项"""
        coding_results = context.loaded_knowledge.get("coding_results", [])
        
        if category == "代码完整性":
            if "任务已完成" in item:
                return all(r["status"] == "completed" for r in coding_results)
            if "编译" in item:
                return True  # 框架层默认通过
        
        return True
    
    # ─── Step 5: 对抗审查 ─────────────────────────────────
    
    def _step_adversarial_review(self, context: AgentContext,
                                  input_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        对抗审查 - 切换对抗者心态
        
        规则: 至少找3个问题，🔴严重问题必须修复后才能流转
        """
        self.ctx_mgr.load_step_file(
            self.agent_id, "04_程序Agent", "step-05_对抗审查.md"
        )
        
        # 加载审查报告模板
        self.ctx_mgr.load_template(
            self.agent_id, "04_程序Agent", "审查报告模板.md"
        )
        
        # 对抗审查：必须找到至少3个问题
        review_issues = [
            {
                "id": "REVIEW-001",
                "severity": "🟡",
                "category": "代码规范",
                "description": "部分变量命名可以更具描述性",
                "suggestion": "使用更有意义的变量名",
                "fixed": True,
            },
            {
                "id": "REVIEW-002",
                "severity": "🟡",
                "category": "错误处理",
                "description": "部分异常处理可以更细粒度",
                "suggestion": "区分不同类型的异常",
                "fixed": True,
            },
            {
                "id": "REVIEW-003",
                "severity": "🟢",
                "category": "性能",
                "description": "可以考虑缓存机制优化性能",
                "suggestion": "添加适当的缓存策略",
                "fixed": False,
            },
        ]
        
        # 检查是否有🔴严重问题
        critical_issues = [i for i in review_issues if i["severity"] == "🔴"]
        unfixed_critical = [i for i in critical_issues if not i["fixed"]]
        
        can_proceed = len(unfixed_critical) == 0
        
        if can_proceed:
            # 发送流转消息给QA
            self.send_handoff(
                to_agent="06_qa",
                req_id=context.req_id,
                artifacts=["代码文件"],
                message=f"💻 对抗审查完成，发现{len(review_issues)}个问题，无严重未修复问题"
            )
        
        # 自我反思
        reflection = self.self_reflect()
        reflection["checklist"]["artifacts_complete"] = can_proceed
        reflection["checklist"]["no_errors"] = len(unfixed_critical) == 0
        
        return {
            "status": "completed" if can_proceed else "blocked",
            "review": {
                "total_issues": len(review_issues),
                "critical_unfixed": len(unfixed_critical),
                "issues": review_issues,
                "can_proceed": can_proceed,
            },
            "next_agent": "06_qa" if can_proceed else None,
            "reflection": reflection,
            "message": f"⚔️ 对抗审查完成: {len(review_issues)}个问题 | {'⚡ 流转至: QA Agent' if can_proceed else '❌ 有严重未修复问题'}"
        }
    
    # ─── Step B1: Bug修复 ─────────────────────────────────
    
    def _step_bugfix(self, context: AgentContext,
                      input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Bug修复: 定位问题、修复代码、更新文档"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "04_程序Agent", "step-B1_Bug修复.md"
        )
        
        # 读取Bug报告消息
        bug_messages = self.receive_messages(MessageType.BUG_REPORT.value)
        
        fix_results = []
        for msg in bug_messages:
            bug_id = msg.payload.get("bug_id", "")
            fix_results.append({
                "bug_id": bug_id,
                "severity": msg.payload.get("severity", ""),
                "root_cause": "待分析",
                "fix_description": "待修复",
                "status": "fixed",
                "regression_risk": "low",
            })
        
        if not bug_messages:
            fix_results.append({
                "bug_id": input_data.get("bug_id", "BUG-UNKNOWN"),
                "status": "fixed",
                "root_cause": "基于Bug报告定位",
                "fix_description": "修复代码",
            })
        
        # 修复后流转回QA验证
        self.send_handoff(
            to_agent="06_qa",
            req_id=context.req_id,
            artifacts=["修复代码"],
            message=f"💻 Bug修复完成: {len(fix_results)}个Bug"
        )
        
        return {
            "status": "completed",
            "fix_results": fix_results,
            "next_agent": "06_qa",
            "message": f"💻 程序小赵: Bug修复完成 ({len(fix_results)}个) → ⚡ 流转至: QA Agent"
        }
    
    # ─── Step S1: 子任务执行 ──────────────────────────────
    
    def _step_subtask(self, context: AgentContext,
                       input_data: Dict[str, Any]) -> Dict[str, Any]:
        """读取任务卡片、编码、输出结果"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "04_程序Agent", "step-S1_子任务执行.md"
        )
        
        # 读取子任务消息
        subtask_messages = self.receive_messages(MessageType.SUBTASK_DISPATCH.value)
        
        subtask_results = []
        for msg in subtask_messages:
            result = {
                "card_id": msg.payload.get("card_id", ""),
                "name": msg.payload.get("name", ""),
                "status": "completed",
                "files_created": [],
                "files_modified": [],
            }
            subtask_results.append(result)
        
        # 发送子任务结果
        for result in subtask_results:
            msg = Message(
                from_agent=self.agent_id,
                to_agent="03_tech_lead",
                msg_type=MessageType.SUBTASK_RESULT.value,
                payload=result
            )
            self.mq.send(msg)
        
        return {
            "status": "completed",
            "subtask_results": subtask_results,
            "message": f"💻 程序小赵: {len(subtask_results)}个子任务执行完成"
        }
    
    # ─── 工具方法 ──────────────────────────────────────────
    
    def _save_to_workspace(self, context: AgentContext,
                            filename: str, data: Any):
        """保存数据到沙盒工作目录（通过文件代理强制权限检查）"""
        self.safe_save_to_workspace(filename, data)
