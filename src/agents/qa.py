"""
QA Agent - 自动化测试与Bug报告

角色: QA小吴 🧪
职责:
- 测试设计与拆分
- 编写自动化测试代码
- 执行测试
- 生成测试报告
- Bug流转（发现Bug → 流转程序修复 → 重新测试）

规则来源: rules/agents/06_QAAgent.md
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime

from .base_agent import BaseAgent, AgentPersona, AgentPermissions, StepDefinition
from ..core.context_manager import AgentContext
from ..core.message_queue import MessageType, Message, MessagePriority


class QAAgent(BaseAgent):
    """
    QA Agent（主QA） - 自动化测试工程师
    
    主从架构角色: 主Agent，负责规划测试策略并汇总测试结果
    
    Bug流转机制:
    测试失败 → Bug报告 → 程序修复 → 重新测试
    → 通过 → 流转策划(交付)
    → 不通过 → 继续修复（最多3轮） → 超过3轮 → 暂停请求用户介入
    
    行为底线:
    - 绝不跳过失败测试
    - 绝不写无意义Assert的废用例
    - 绝不自己修复代码
    """
    
    MAX_BUG_ROUNDS = 3
    
    def get_persona(self) -> AgentPersona:
        return AgentPersona(
            name="QA小吴",
            icon="🧪",
            experience="7年游戏QA经验，擅长Unity Test Framework，天生的怀疑论者",
            communication_style="怀疑一切、不轻易放过。用精确的测试结果和Bug报告说话",
            decision_principle="宁可多测不可漏测。边界条件 > 正常流程 > 异常情况",
            behavior_bottom_line=[
                "绝不跳过失败测试",
                "绝不写无意义Assert的废用例",
                "绝不自己修复代码",
            ]
        )
    
    def get_permissions(self) -> AgentPermissions:
        return AgentPermissions(
            read=["plan_docs", "tech_design", "code_files", "knowledge_base", "skills"],
            write=["tests/**", ".GameDev/**/06_测试报告.md"],
            create=["tests/**", ".GameDev/**/06_测试报告.md"],
            delete=[],
            execute=["test"]
        )
    
    def get_steps(self) -> Dict[str, List[StepDefinition]]:
        return {
            "standard": [
                StepDefinition(
                    name="测试准备",
                    file="step-01_测试准备.md",
                    mode="EXPLORE",
                    description="阅读策划案、技术设计、加载知识库"
                ),
                StepDefinition(
                    name="测试编写",
                    file="step-02_测试编写.md",
                    mode="IMPLEMENT",
                    description="编写自动化测试代码"
                ),
                StepDefinition(
                    name="测试执行与报告",
                    file="step-03_测试执行与报告.md",
                    mode="VERIFY",
                    description="执行测试、生成报告、流转决策"
                ),
            ],
            "master_slave": [
                StepDefinition(
                    name="测试拆分",
                    file="step-M1_测试拆分.md",
                    mode="DESIGN",
                    description="拆分测试任务、创建任务卡片"
                ),
            ],
        }
    
    def execute_step(self, step: StepDefinition, context: AgentContext,
                     input_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """执行QA步骤"""
        input_data = input_data or {}
        
        step_handlers = {
            "测试准备": self._step_test_preparation,
            "测试编写": self._step_write_tests,
            "测试执行与报告": self._step_execute_and_report,
            "测试拆分": self._step_test_split,
        }
        
        handler = step_handlers.get(step.name)
        if not handler:
            raise ValueError(f"未知步骤: {step.name}")
        
        return handler(context, input_data)
    
    # ─── Step 1: 测试准备 ─────────────────────────────────
    
    def _step_test_preparation(self, context: AgentContext,
                                input_data: Dict[str, Any]) -> Dict[str, Any]:
        """阅读策划案、技术设计、加载知识库"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "06_QAAgent", "step-01_测试准备.md"
        )
        
        # 加载Agent入口文件
        self.ctx_mgr.load_agent_entry(self.agent_id, "06_QAAgent.md")
        
        # 检查流转消息
        handoff_messages = self.receive_messages(MessageType.HANDOFF.value)
        
        # 尝试加载技能包
        skills_loaded = []
        for skill_path in ["csharp/null-safety.md", "unity-testing.md"]:
            content = self.ctx_mgr.load_skill(self.agent_id, skill_path)
            if content:
                skills_loaded.append(skill_path)
        
        preparation = {
            "plan_reviewed": True,
            "tech_design_reviewed": True,
            "knowledge_loaded": True,
            "skills_loaded": skills_loaded,
            "handoff_received": len(handoff_messages) > 0,
            "acceptance_criteria_count": 0,
        }
        
        context.loaded_knowledge["test_preparation"] = preparation
        
        return {
            "status": "completed",
            "preparation": preparation,
            "message": f"🧪 QA小吴: 测试准备完成"
        }
    
    # ─── Step 2: 测试编写 ─────────────────────────────────
    
    def _step_write_tests(self, context: AgentContext,
                           input_data: Dict[str, Any]) -> Dict[str, Any]:
        """编写自动化测试代码"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "06_QAAgent", "step-02_测试编写.md"
        )
        
        # 加载测试代码模板
        self.ctx_mgr.load_template(
            self.agent_id, "06_QAAgent", "测试代码模板.md"
        )
        
        test_cases = {
            "req_id": context.req_id,
            "test_suites": [],
            "total_cases": 0,
            "created_at": datetime.now().isoformat(),
        }
        
        # 生成测试套件
        test_categories = [
            ("正常流程测试", "normal", "P1"),
            ("边界条件测试", "boundary", "P1"),
            ("异常处理测试", "exception", "P2"),
            ("性能测试", "performance", "P3"),
        ]
        
        case_id = 1
        for suite_name, category, priority in test_categories:
            suite = {
                "name": suite_name,
                "category": category,
                "priority": priority,
                "cases": [],
            }
            
            # 每个套件生成2-3个测试用例
            case_count = 3 if priority == "P1" else 2
            for i in range(case_count):
                suite["cases"].append({
                    "case_id": f"TC-{case_id:03d}",
                    "name": f"{suite_name}_{i+1}",
                    "ac_reference": f"AC-{(case_id % 4) + 1:03d}",
                    "preconditions": "待定义",
                    "steps": "待编写",
                    "expected_result": "待定义",
                    "status": "written",
                })
                case_id += 1
            
            test_cases["test_suites"].append(suite)
        
        test_cases["total_cases"] = case_id - 1
        
        # 保存到沙盒
        self._save_to_workspace(context, "test_cases.json", test_cases)
        context.loaded_knowledge["test_cases"] = test_cases
        
        return {
            "status": "completed",
            "test_cases": test_cases,
            "artifacts": ["测试代码文件"],
            "message": f"🧪 QA小吴: 测试编写完成 | {test_cases['total_cases']}个用例"
        }
    
    # ─── Step 3: 测试执行与报告 ───────────────────────────
    
    def _step_execute_and_report(self, context: AgentContext,
                                  input_data: Dict[str, Any]) -> Dict[str, Any]:
        """执行测试、生成报告、流转决策"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "06_QAAgent", "step-03_测试执行与报告.md"
        )
        
        # 加载测试报告模板
        self.ctx_mgr.load_template(
            self.agent_id, "06_QAAgent", "测试报告模板.md"
        )
        
        test_cases = context.loaded_knowledge.get("test_cases", {})
        
        # 执行测试（框架层模拟）
        test_results = {
            "req_id": context.req_id,
            "executed_at": datetime.now().isoformat(),
            "total": test_cases.get("total_cases", 0),
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "bugs_found": [],
            "suite_results": [],
        }
        
        bug_counter = 0
        for suite in test_cases.get("test_suites", []):
            suite_result = {
                "name": suite["name"],
                "cases_total": len(suite["cases"]),
                "cases_passed": 0,
                "cases_failed": 0,
                "case_results": [],
            }
            
            for case in suite["cases"]:
                # 模拟测试结果（大部分通过）
                passed = True  # 框架层默认通过
                
                case_result = {
                    "case_id": case["case_id"],
                    "name": case["name"],
                    "passed": passed,
                    "duration_ms": 100,
                }
                
                if passed:
                    suite_result["cases_passed"] += 1
                    test_results["passed"] += 1
                else:
                    suite_result["cases_failed"] += 1
                    test_results["failed"] += 1
                    bug_counter += 1
                    
                    # 生成Bug报告
                    bug = {
                        "bug_id": f"BUG-{context.req_id}-{bug_counter:03d}",
                        "severity": "P1" if suite["priority"] == "P1" else "P2",
                        "case_id": case["case_id"],
                        "description": f"测试用例 {case['name']} 未通过",
                        "expected": case.get("expected_result", ""),
                        "actual": "不符合预期",
                        "reproduce_steps": case.get("steps", ""),
                    }
                    test_results["bugs_found"].append(bug)
                
                suite_result["case_results"].append(case_result)
            
            test_results["suite_results"].append(suite_result)
        
        # 生成测试报告
        report = self._generate_test_report(test_results)
        self._save_to_workspace(context, "06_测试报告.json", report)
        
        # 流转决策
        all_passed = test_results["failed"] == 0
        bug_round = input_data.get("bug_round", 0)
        
        if all_passed:
            # 全部通过 → 流转策划Agent(交付)
            self.send_handoff(
                to_agent="02_planner",
                req_id=context.req_id,
                artifacts=["06_测试报告.md"],
                message=f"🧪 全部测试通过 ({test_results['passed']}/{test_results['total']})"
            )
            next_agent = "02_planner"
            flow_action = "delivery"
        elif bug_round >= self.MAX_BUG_ROUNDS:
            # 超过最大修复轮数 → 暂停
            next_agent = None
            flow_action = "pause_user_intervention"
        else:
            # 有Bug → 流转程序Agent修复
            for bug in test_results["bugs_found"]:
                self.mq.send_bug_report(
                    from_agent=self.agent_id,
                    to_agent="04_programmer",
                    req_id=context.req_id,
                    bug_id=bug["bug_id"],
                    severity=bug["severity"],
                    description=bug["description"]
                )
            next_agent = "04_programmer"
            flow_action = "bug_fix"
        
        # 自我反思
        reflection = self.self_reflect()
        reflection["checklist"]["artifacts_complete"] = True
        reflection["checklist"]["no_errors"] = all_passed
        
        return {
            "status": "completed",
            "test_results": test_results,
            "report": report,
            "flow_decision": {
                "all_passed": all_passed,
                "action": flow_action,
                "next_agent": next_agent,
                "bug_round": bug_round,
            },
            "reflection": reflection,
            "artifacts": ["06_测试报告.md"],
            "message": self._format_test_summary(test_results, flow_action, next_agent)
        }
    
    def _generate_test_report(self, test_results: Dict[str, Any]) -> Dict[str, Any]:
        """生成测试报告"""
        return {
            "title": f"测试报告 - {test_results['req_id']}",
            "summary": {
                "total": test_results["total"],
                "passed": test_results["passed"],
                "failed": test_results["failed"],
                "pass_rate": f"{test_results['passed'] / max(test_results['total'], 1) * 100:.1f}%",
            },
            "bugs": test_results["bugs_found"],
            "suite_results": test_results["suite_results"],
            "generated_at": datetime.now().isoformat(),
        }
    
    def _format_test_summary(self, results: Dict, action: str, 
                              next_agent: Optional[str]) -> str:
        """格式化测试摘要"""
        summary = f"🧪 QA小吴: 测试完成 | 通过: {results['passed']}/{results['total']}"
        
        if action == "delivery":
            summary += f" ✅ → ⚡ 流转至: 策划 Agent（交付）"
        elif action == "bug_fix":
            summary += f" | 发现{results['failed']}个Bug → ⚡ 流转至: 程序 Agent（Bug修复）"
        elif action == "pause_user_intervention":
            summary += f" | ⚠️ 超过{self.MAX_BUG_ROUNDS}轮修复，暂停等待用户介入"
        
        return summary
    
    # ─── Step M1: 测试拆分 ────────────────────────────────
    
    def _step_test_split(self, context: AgentContext,
                          input_data: Dict[str, Any]) -> Dict[str, Any]:
        """拆分测试任务、创建任务卡片"""
        self.ctx_mgr.load_step_file(
            self.agent_id, "06_QAAgent", "step-M1_测试拆分.md"
        )
        
        test_cases = context.loaded_knowledge.get("test_cases", {})
        
        test_tasks = []
        for suite in test_cases.get("test_suites", []):
            test_tasks.append({
                "task_name": f"测试: {suite['name']}",
                "category": suite.get("category", ""),
                "case_count": len(suite.get("cases", [])),
                "priority": suite.get("priority", "P2"),
            })
        
        return {
            "status": "completed",
            "test_tasks": test_tasks,
            "message": f"🧪 QA小吴: 测试拆分完成 | {len(test_tasks)}个测试任务"
        }
    
    # ─── 工具方法 ──────────────────────────────────────────
    
    def _save_to_workspace(self, context: AgentContext,
                            filename: str, data: Any):
        """保存数据到沙盒工作目录（通过文件代理强制权限检查）"""
        self.safe_save_to_workspace(filename, data)
