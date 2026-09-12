"""
编排器 - 多Agent调度和流水线生命周期管理

核心职责:
- 接收用户需求
- 调度Agent执行
- 管理流水线生命周期
- 并行任务协调
- Bug流转循环管理
"""

import json
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from .sandbox import SandboxManager
from .message_queue import MessageQueue, Message, MessageType
from .context_manager import ContextManager
from .pipeline import (
    PipelineEngine, PipelineInstance, PipelineStep,
    ReqType, ReqScale
)


@dataclass
class RequirementAnalysis:
    """需求分析结果（制作人Agent的输出）"""
    req_id: str = ""
    req_name: str = ""
    req_type: str = ""
    req_scale: str = ""
    flow_path: List[str] = field(default_factory=list)
    sub_requirements: List[dict] = field(default_factory=list)  # 复合需求拆分
    confidence: str = ""  # 🟢高/🟡中/🔴低
    analysis_basis: str = ""  # 判断依据


class Orchestrator:
    """
    编排器 - 系统总指挥
    
    负责:
    1. 接收用户需求
    2. 通过制作人Agent进行需求分析
    3. 创建流水线实例
    4. 按照流转路径调度各Agent
    5. 管理并行执行
    6. 处理Bug流转循环
    7. 最终交付
    """
    
    def __init__(self, project_root: str, config: Dict[str, Any] = None):
        """
        初始化编排器
        
        Args:
            project_root: 项目根目录
            config: 系统配置字典
        """
        self.project_root = Path(project_root)
        self.config = config or {}
        
        # 初始化核心组件
        sandbox_root = self.config.get("sandbox_root", ".sandboxes")
        protected_paths = self.config.get("protected_paths", ["rules"])
        
        self.sandbox_mgr = SandboxManager(
            project_root=str(self.project_root),
            sandbox_root=sandbox_root,
            protected_paths=protected_paths
        )
        
        self.mq = MessageQueue(
            queue_root=str(self.project_root / sandbox_root / "_message_queue")
        )
        
        self.ctx_mgr = ContextManager(
            sandbox_root=str(self.project_root / sandbox_root),
            rules_working_copy=str(
                self.project_root / sandbox_root / "_working_copies" / "rules"
            )
        )
        
        self.pipeline_engine = PipelineEngine()
        
        # Agent注册表
        self._agents: Dict[str, Any] = {}  # agent_id -> BaseAgent instance
        
        # 活跃流水线
        self._active_pipelines: Dict[str, PipelineInstance] = {}
        
        # 并行执行器
        max_parallel = self.config.get("max_parallel_agents", 4)
        self._executor = ThreadPoolExecutor(max_workers=max_parallel)
        
        # 执行日志 — 全局系统日志（兼容旧接口）
        self._log: List[dict] = []
        # 按流水线 ID 分组存储的日志
        self._pipeline_logs: Dict[str, List[dict]] = {}
    
    def setup(self):
        """
        系统初始化设置
        
        1. 创建源文档工作副本
        2. 初始化共享目录
        3. 注册所有Agent
        """
        # 1. 创建源文档工作副本（保护源文档）
        self.sandbox_mgr.create_working_copy("rules")
        
        # 2. 确保共享目录存在
        shared_gamedev = self.sandbox_mgr.get_shared_gamedev_path()
        (shared_gamedev / "_ProjectManagement").mkdir(parents=True, exist_ok=True)
        
        self._record_log("setup", "系统初始化完成")
    
    def register_agent(self, agent_id: str, agent_instance):
        """注册Agent实例"""
        self._agents[agent_id] = agent_instance
        self._record_log("register_agent", f"注册Agent: {agent_id}")
    
    def process_requirement(self, user_input: str) -> Dict[str, Any]:
        """
        处理用户需求（系统入口）
        
        流程:
        1. 制作人分析需求
        2. 项目管理分配ID
        3. 创建流水线
        4. 按步骤调度Agent
        5. 返回最终结果
        
        Args:
            user_input: 用户输入的需求描述
            
        Returns:
            处理结果
        """
        self._record_log("requirement_received", f"收到需求: {user_input}")
        
        # Phase 1: 需求分析（制作人Agent）
        analysis = self._analyze_requirement(user_input)
        
        # Phase 2: 需求初始化（项目管理Agent）
        req_id = self._initialize_requirement(analysis)
        analysis.req_id = req_id
        
        # Phase 3: 创建流水线
        try:
            req_type = ReqType(analysis.req_type)
            req_scale = ReqScale(analysis.req_scale)
        except (ValueError, KeyError):
            req_type = ReqType.FEATURE
            req_scale = ReqScale.M
        
        pipeline = self.pipeline_engine.create_pipeline(
            req_id=req_id,
            req_type=req_type,
            req_scale=req_scale,
            req_name=analysis.req_name
        )
        pipeline.status = "running"
        pipeline.started_at = datetime.now().isoformat()
        self._active_pipelines[pipeline.pipeline_id] = pipeline
        
        self._record_log("pipeline_created", 
                        f"流水线 {pipeline.pipeline_id} 已创建: {analysis.req_type}/{analysis.req_scale}",
                        pipeline_id=pipeline.pipeline_id)
        
        # Phase 4: 执行流水线
        result = self._execute_pipeline(pipeline)
        
        return result
    
    def _analyze_requirement(self, user_input: str) -> RequirementAnalysis:
        """
        制作人Agent分析需求
        
        Args:
            user_input: 用户输入
            
        Returns:
            RequirementAnalysis
        """
        # 命令快速路径识别
        analysis = RequirementAnalysis()
        
        if user_input.startswith("/gd:"):
            # 解析快捷命令
            analysis = self._parse_gd_command(user_input)
        else:
            # 自然语言分析
            analysis = self._analyze_natural_language(user_input)
        
        return analysis
    
    def _parse_gd_command(self, command: str) -> RequirementAnalysis:
        """解析 /gd: 快捷命令"""
        analysis = RequirementAnalysis()
        
        # 命令映射
        cmd_type_map = {
            "/gd:feature": "FEATURE",
            "/gd:bugfix": "BUGFIX",
            "/gd:optimize": "OPTIMIZE",
            "/gd:test": "TEST",
            "/gd:doc": "DOC",
            "/gd:review": "REVIEW",
            "/gd:config": "CONFIG",
            "/gd:research": "RESEARCH",
        }
        
        parts = command.split(" ", 1)
        cmd = parts[0].lower()
        description = parts[1] if len(parts) > 1 else ""
        
        analysis.req_type = cmd_type_map.get(cmd, "FEATURE")
        analysis.req_name = description.strip('"').strip("'")
        analysis.req_scale = "M"  # 默认中等规模
        analysis.confidence = "🟢高"
        analysis.analysis_basis = f"快捷命令: {cmd}"
        
        return analysis
    
    def _analyze_natural_language(self, text: str) -> RequirementAnalysis:
        """
        自然语言需求分析
        
        三级识别体系:
        1. 一级关键词（直接命中）
        2. 二级关键词+上下文感知
        3. 语义分析
        """
        analysis = RequirementAnalysis()
        analysis.req_name = text[:50]  # 取前50字符作为名称
        
        # 一级关键词匹配
        keyword_map = {
            "bug": "BUGFIX", "修复": "BUGFIX", "报错": "BUGFIX", "崩溃": "BUGFIX",
            "优化": "OPTIMIZE", "重构": "OPTIMIZE", "性能": "OPTIMIZE",
            "测试": "TEST", "测试用例": "TEST",
            "文档": "DOC", "readme": "DOC",
            "审查": "REVIEW", "review": "REVIEW",
            "配置": "CONFIG", "参数调整": "CONFIG",
            "调研": "RESEARCH", "分析": "RESEARCH",
        }
        
        text_lower = text.lower()
        for keyword, req_type in keyword_map.items():
            if keyword in text_lower:
                analysis.req_type = req_type
                analysis.confidence = "🟢高"
                analysis.analysis_basis = f"一级关键词: {keyword}"
                break
        
        if not analysis.req_type:
            # 默认为FEATURE
            analysis.req_type = "FEATURE"
            analysis.confidence = "🟡中"
            analysis.analysis_basis = "默认分类"
        
        # 规模评估（简化版）
        if any(kw in text_lower for kw in ["系统", "全新", "架构", "跨模块"]):
            analysis.req_scale = "XL"
        elif any(kw in text_lower for kw in ["多个", "模块", "复杂", "大型"]):
            analysis.req_scale = "L"
        else:
            analysis.req_scale = "M"
        
        return analysis
    
    def _initialize_requirement(self, analysis: RequirementAnalysis) -> str:
        """
        项目管理Agent初始化需求
        
        Returns:
            分配的需求ID
        """
        # 生成需求ID
        req_id = f"REQ-{uuid.uuid4().hex[:6].upper()}"
        
        # 创建需求追踪文件
        gamedev_dir = self.sandbox_mgr.get_shared_gamedev_path()
        req_dir = gamedev_dir / analysis.req_name.replace(" ", "_")[:30]
        req_dir.mkdir(parents=True, exist_ok=True)
        
        # 写入frontmatter状态追踪
        frontmatter = {
            "req_id": req_id,
            "req_name": analysis.req_name,
            "req_type": analysis.req_type,
            "complexity": "中等",
            "scale": analysis.req_scale,
            "status": "in-progress",
            "current_agent": "",
            "current_step": "",
            "progress": "0%",
            "created_at": datetime.now().isoformat(),
            "steps_completed": []
        }
        
        meta_file = req_dir / "requirement_meta.json"
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump(frontmatter, f, ensure_ascii=False, indent=2)
        
        self._record_log("requirement_initialized", 
                        f"需求 {req_id} ({analysis.req_name}) 已初始化")
        
        return req_id
    
    def _execute_pipeline(self, pipeline: PipelineInstance) -> Dict[str, Any]:
        """
        执行流水线
        
        按步骤调度Agent，支持并行执行
        
        Args:
            pipeline: 流水线实例
            
        Returns:
            执行结果
        """
        results = {}
        
        while pipeline.current_step:
            step = pipeline.current_step
            
            # 更新步骤状态为 running
            step.status = "running"
            
            self._record_log("step_dispatch", 
                           f"调度 {step.stage} -> Agent {step.agent_id}",
                           pipeline_id=pipeline.pipeline_id)
            
            # 检查是否有并行步骤
            if step.parallel_with:
                # 并行执行
                parallel_results = self._execute_parallel(
                    pipeline, step, step.parallel_with
                )
                results[step.stage] = parallel_results
            else:
                # 串行执行
                result = self._execute_agent_step(pipeline, step)
                results[step.stage] = result
            
            # 更新步骤状态为 completed
            step.status = "completed"
            
            # 质量门禁检查
            if step.quality_gate:
                gate_passed = self._check_quality_gate(
                    pipeline, step.quality_gate
                )
                if not gate_passed:
                    self._record_log("quality_gate_failed", 
                                   f"🚧 质量门禁 {step.quality_gate} 未通过",
                                   pipeline_id=pipeline.pipeline_id)
                    # 阻断流转，返回上游
                    results["quality_gate_failure"] = step.quality_gate
                    break
                else:
                    self._record_log("quality_gate_passed",
                                   f"🚧 质量门禁 {step.quality_gate} 通过",
                                   pipeline_id=pipeline.pipeline_id)
            
            # 推进到下一步
            pipeline.advance()
        
        # 流水线完成
        self.pipeline_engine.complete_pipeline(pipeline.pipeline_id)
        results["status"] = "completed"
        results["pipeline_id"] = pipeline.pipeline_id
        
        self._record_log("pipeline_completed", 
                        f"流水线 {pipeline.pipeline_id} 已完成",
                        pipeline_id=pipeline.pipeline_id)
        
        return results
    
    def _execute_agent_step(self, pipeline: PipelineInstance,
                            step: PipelineStep) -> Dict[str, Any]:
        """执行单个Agent步骤"""
        agent = self._agents.get(step.agent_id)
        
        if not agent:
            # Agent未注册，记录警告并返回模拟结果
            self._record_log(
                "agent_not_registered",
                f"⚠️ Agent {step.agent_id} 未注册，步骤 {step.stage} 以模拟模式执行",
                pipeline_id=pipeline.pipeline_id
            )
            return {
                "agent_id": step.agent_id,
                "stage": step.stage,
                "status": "simulated",
                "warning": f"Agent {step.agent_id} 未注册，结果为模拟数据，不代表真实执行",
                "message": f"Agent {step.agent_id} 未注册，模拟执行"
            }
        
        # 初始化Agent
        agent.initialize(
            req_id=pipeline.req_id,
            req_name=pipeline.req_name,
            req_type=pipeline.req_type,
            req_scale=pipeline.req_scale
        )
        
        # 确定流程名称
        flow_name = "standard"
        if pipeline.req_type == "BUGFIX":
            flow_name = "bugfix"
        
        # 执行Agent流程
        try:
            result = agent.run_pipeline(flow_name, {
                "pipeline_id": pipeline.pipeline_id,
                "req_id": pipeline.req_id,
            })
            return result
        except Exception as e:
            return {
                "agent_id": step.agent_id,
                "stage": step.stage,
                "status": "error",
                "error": str(e)
            }
    
    def _execute_parallel(self, pipeline: PipelineInstance,
                          main_step: PipelineStep,
                          parallel_agents: List[str]) -> Dict[str, Any]:
        """
        并行执行多个Agent
        
        Args:
            pipeline: 流水线实例
            main_step: 主步骤
            parallel_agents: 并行执行的Agent ID列表
            
        Returns:
            合并的执行结果
        """
        futures = {}
        
        # 提交主步骤
        futures[main_step.agent_id] = self._executor.submit(
            self._execute_agent_step, pipeline, main_step
        )
        
        # 提交并行步骤
        for agent_id in parallel_agents:
            parallel_step = PipelineStep(
                stage=f"parallel_{agent_id}",
                agent_id=agent_id,
                execution="parallel"
            )
            futures[agent_id] = self._executor.submit(
                self._execute_agent_step, pipeline, parallel_step
            )
        
        # 等待所有完成
        results = {}
        for agent_id, future in futures.items():
            try:
                results[agent_id] = future.result(timeout=300)  # 5分钟超时
            except Exception as e:
                results[agent_id] = {"status": "error", "error": str(e)}
        
        return results
    
    def _check_quality_gate(self, pipeline: PipelineInstance,
                            gate_name: str) -> bool:
        """
        执行质量门禁检查
        
        从对应Agent的上下文中读取实际的质量门禁结果。
        如果Agent已记录了该门禁的检查结果，使用实际结果；
        否则回退到逐项检查，未执行的项视为未通过。
        """
        gate = pipeline.quality_gates.get(gate_name)
        if not gate:
            return True  # 没有定义门禁则直接通过
        
        # 确定是哪个Agent负责此门禁
        gate_agent_map = {
            "gate_1": "02_planner",
            "gate_2": "03_tech_lead",
            "gate_3": "04_programmer",
        }
        agent_id = gate_agent_map.get(gate_name, "")
        
        # 尝试从Agent上下文获取实际门禁结果
        agent_ctx = self.ctx_mgr.get_context(agent_id) if agent_id else None
        
        if agent_ctx and gate_name in agent_ctx.quality_gates:
            # ✅ 使用Agent实际记录的质量门禁结果
            gate_data = agent_ctx.quality_gates[gate_name]
            actual_passed = gate_data.get("passed", False)
            details = gate_data.get("details", {})
            
            # 将详细结果传递给引擎
            check_results = {}
            if details:
                # details 格式: {"category": {"item": bool, ...}, ...}
                for category, items in details.items():
                    if isinstance(items, dict):
                        for item, passed in items.items():
                            check_results[f"{category}:{item}"] = passed
                    else:
                        check_results[category] = items
            else:
                # 没有详细结果，使用整体 passed 状态
                for item in gate.check_items:
                    check_results[item] = actual_passed
            
            self._record_log(
                "quality_gate_check",
                f"质量门禁 {gate_name}: 从 Agent {agent_id} 上下文获取实际结果 — {'通过' if actual_passed else '未通过'}",
                pipeline_id=pipeline.pipeline_id
            )
            
            return self.pipeline_engine.check_quality_gate(
                pipeline.pipeline_id, gate_name, check_results
            )
        else:
            # ⚠️ Agent 未记录门禁结果 — 视为未执行，默认不通过
            self._record_log(
                "quality_gate_check",
                f"⚠️ 质量门禁 {gate_name}: Agent {agent_id} 未记录检查结果，门禁未通过",
                pipeline_id=pipeline.pipeline_id
            )
            check_results = {item: False for item in gate.check_items}
            return self.pipeline_engine.check_quality_gate(
                pipeline.pipeline_id, gate_name, check_results
            )
    
    def handle_bug_flow(self, pipeline_id: str, bug_report: dict) -> bool:
        """
        处理Bug流转
        
        Returns:
            True如果成功回退到程序修复，False如果超过最大轮数
        """
        pipeline = self._active_pipelines.get(pipeline_id)
        if not pipeline:
            return False
        
        step = self.pipeline_engine.handle_bug_flow(pipeline_id)
        if step is None:
            self._record_log("bug_max_rounds", 
                           f"Bug修复超过{pipeline.max_bug_rounds}轮，暂停等待用户介入",
                           pipeline_id=pipeline_id)
            return False
        
        self._record_log("bug_flow", 
                        f"Bug流转回程序Agent修复（第{pipeline.bug_rounds}轮）",
                        pipeline_id=pipeline_id)
        return True
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            "active_pipelines": len(self._active_pipelines),
            "registered_agents": list(self._agents.keys()),
            "active_sandboxes": self.sandbox_mgr.list_active_sandboxes(),
            "message_queue_stats": self.mq.get_queue_stats(),
            "contexts": self.ctx_mgr.get_all_contexts_summary(),
            "log_entries": len(self._log)
        }
    
    def get_pipeline_status(self, pipeline_id: str) -> Optional[dict]:
        """获取流水线状态"""
        return self.pipeline_engine.get_pipeline_summary(pipeline_id)
    
    def _record_log(self, event_type: str, message: str, pipeline_id: str = None):
        """记录编排器日志（同时写入全局日志和按项目日志）"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "message": message,
        }
        if pipeline_id:
            entry["pipeline_id"] = pipeline_id
        # 全局日志（兼容旧接口）
        self._log.append(entry)
        # 按项目日志
        if pipeline_id:
            if pipeline_id not in self._pipeline_logs:
                self._pipeline_logs[pipeline_id] = []
            self._pipeline_logs[pipeline_id].append(entry)

    def get_pipeline_logs(self, pipeline_id: str, count: int = 50) -> List[dict]:
        """获取指定流水线的日志"""
        logs = self._pipeline_logs.get(pipeline_id, [])
        return logs[-count:]

    def delete_pipeline_logs(self, pipeline_id: str) -> bool:
        """删除指定流水线的所有日志"""
        if pipeline_id in self._pipeline_logs:
            del self._pipeline_logs[pipeline_id]
            return True
        return False
    
    def shutdown(self):
        """关闭编排器"""
        self._executor.shutdown(wait=True)
        self.sandbox_mgr.cleanup_all()
        self.mq.clear_all()
        self._record_log("shutdown", "编排器已关闭")
