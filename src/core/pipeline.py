"""
流水线引擎 - 需求流转路径管理和阶段调度

核心职责:
- 定义各需求类型的流转路径
- 管理阶段调度（串行/并行）
- 质量门禁检查
- Bug流转处理
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from pathlib import Path


class ReqType(Enum):
    """需求类型"""
    FEATURE = "FEATURE"
    FEATURE_UI = "FEATURE_UI"
    OPTIMIZE = "OPTIMIZE"
    BUGFIX = "BUGFIX"
    TEST = "TEST"
    DOC = "DOC"
    REVIEW = "REVIEW"
    CONFIG = "CONFIG"
    RESEARCH = "RESEARCH"


class ReqScale(Enum):
    """需求规模"""
    XS = "XS"  # 超小
    S = "S"    # 小
    M = "M"    # 中
    L = "L"    # 大 - 主从模式
    XL = "XL"  # 超大 - 深度模式


class PipelineStage(Enum):
    """流水线阶段"""
    PRODUCER = "producer"        # 制作人
    PM = "project_manager"       # 项目管理
    PLANNER = "planner"          # 策划
    UX = "ux_designer"           # UX设计
    TECH_LEAD = "tech_lead"      # 主程
    PROGRAMMER = "programmer"    # 程序
    ARTIST = "artist"            # 美术
    QA = "qa"                    # QA
    DELIVERY = "delivery"        # 交付（策划负责）


class StageExecution(Enum):
    """阶段执行方式"""
    SEQUENTIAL = "sequential"  # 串行
    PARALLEL = "parallel"      # 并行


@dataclass
class PipelineStep:
    """流水线步骤"""
    stage: str
    agent_id: str
    execution: str = "sequential"  # sequential/parallel
    parallel_with: List[str] = field(default_factory=list)  # 可并行的其他Agent
    quality_gate: Optional[str] = None  # 质量门禁名称
    optional: bool = False  # 是否可选步骤
    status: str = "pending"  # pending / running / completed / failed / skipped
    
    def to_dict(self) -> dict:
        return {
            "stage": self.stage,
            "name": self.stage,  # 前端兼容字段
            "agent_id": self.agent_id,
            "execution": self.execution,
            "parallel_with": self.parallel_with,
            "quality_gate": self.quality_gate,
            "optional": self.optional,
            "status": self.status,
        }


@dataclass
class QualityGate:
    """质量门禁"""
    name: str
    from_stage: str
    to_stage: str
    check_items: List[str] = field(default_factory=list)
    passed: Optional[bool] = None
    checked_at: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineInstance:
    """流水线实例（一个需求的完整流转记录）"""
    pipeline_id: str
    req_id: str
    req_type: str
    req_scale: str
    req_name: str = ""
    
    # 步骤定义
    steps: List[PipelineStep] = field(default_factory=list)
    
    # 当前状态
    current_step_index: int = 0
    status: str = "created"  # created, running, paused, completed, failed
    
    # 质量门禁
    quality_gates: Dict[str, QualityGate] = field(default_factory=dict)
    
    # Bug流转记录
    bug_rounds: int = 0
    max_bug_rounds: int = 3
    
    # 时间记录
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    @property
    def current_step(self) -> Optional[PipelineStep]:
        if 0 <= self.current_step_index < len(self.steps):
            return self.steps[self.current_step_index]
        return None
    
    @property
    def progress_pct(self) -> int:
        if not self.steps:
            return 0
        return round(self.current_step_index / len(self.steps) * 100)
    
    def advance(self) -> Optional[PipelineStep]:
        """推进到下一步骤"""
        self.current_step_index += 1
        return self.current_step
    
    def to_dict(self) -> dict:
        steps_list = [s.to_dict() for s in self.steps]
        current = self.current_step
        return {
            "pipeline_id": self.pipeline_id,
            "req_id": self.req_id,
            "req_type": self.req_type,
            "req_scale": self.req_scale,
            "req_name": self.req_name,
            "steps": steps_list,
            "stages": steps_list,  # 前端兼容字段
            "current_step_index": self.current_step_index,
            "current_stage": current.stage if current else "",
            "status": self.status,
            "bug_rounds": self.bug_rounds,
            "progress_pct": self.progress_pct,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at
        }


class PipelineEngine:
    """
    流水线引擎
    
    管理需求流转路径，支持:
    - 8种需求类型的流转定义
    - 3种规模模式（标准/主从/深度）
    - 3个质量门禁
    - Bug修复流转循环
    - 并行阶段调度
    """
    
    # 需求类型与流转路径定义
    PIPELINE_DEFINITIONS = {
        ReqType.FEATURE: {
            "name": "功能开发",
            "stages": [
                PipelineStep("producer", "00_producer"),
                PipelineStep("pm", "01_pm"),
                PipelineStep("planner", "02_planner", quality_gate="gate_1"),
                PipelineStep("tech_lead", "03_tech_lead", quality_gate="gate_2"),
                PipelineStep("programmer", "04_programmer", quality_gate="gate_3",
                            parallel_with=["05_artist"]),
                PipelineStep("qa", "06_qa"),
                PipelineStep("delivery", "02_planner"),
            ]
        },
        ReqType.FEATURE_UI: {
            "name": "功能开发(含UI)",
            "stages": [
                PipelineStep("producer", "00_producer"),
                PipelineStep("pm", "01_pm"),
                PipelineStep("planner", "02_planner", quality_gate="gate_1"),
                PipelineStep("ux", "07_ux", parallel_with=["05_artist"]),
                PipelineStep("planner_confirm", "02_planner"),
                PipelineStep("tech_lead", "03_tech_lead", quality_gate="gate_2"),
                PipelineStep("programmer", "04_programmer", quality_gate="gate_3"),
                PipelineStep("qa", "06_qa"),
                PipelineStep("delivery", "02_planner"),
            ]
        },
        ReqType.OPTIMIZE: {
            "name": "代码优化",
            "stages": [
                PipelineStep("producer", "00_producer"),
                PipelineStep("pm", "01_pm"),
                PipelineStep("tech_lead", "03_tech_lead", quality_gate="gate_2"),
                PipelineStep("programmer", "04_programmer", quality_gate="gate_3"),
                PipelineStep("qa", "06_qa"),
                PipelineStep("delivery", "02_planner"),
            ]
        },
        ReqType.BUGFIX: {
            "name": "Bug修复",
            "stages": [
                PipelineStep("producer", "00_producer"),
                PipelineStep("pm", "01_pm"),
                PipelineStep("programmer", "04_programmer"),
                PipelineStep("qa", "06_qa"),
                PipelineStep("delivery", "02_planner"),
            ]
        },
        ReqType.TEST: {
            "name": "测试相关",
            "stages": [
                PipelineStep("producer", "00_producer"),
                PipelineStep("pm", "01_pm"),
                PipelineStep("qa", "06_qa"),
                PipelineStep("delivery", "02_planner"),
            ]
        },
        ReqType.DOC: {
            "name": "文档相关",
            "stages": [
                PipelineStep("producer", "00_producer"),
                PipelineStep("pm", "01_pm"),
                PipelineStep("tech_lead", "03_tech_lead"),
            ]
        },
        ReqType.REVIEW: {
            "name": "代码审查",
            "stages": [
                PipelineStep("producer", "00_producer"),
                PipelineStep("pm", "01_pm"),
                PipelineStep("tech_lead", "03_tech_lead"),
                PipelineStep("programmer", "04_programmer"),
            ]
        },
        ReqType.CONFIG: {
            "name": "配置调整",
            "stages": [
                PipelineStep("producer", "00_producer"),
                PipelineStep("pm", "01_pm"),
                PipelineStep("programmer", "04_programmer"),
                PipelineStep("qa", "06_qa"),
                PipelineStep("delivery", "02_planner"),
            ]
        },
        ReqType.RESEARCH: {
            "name": "方向调研",
            "stages": [
                PipelineStep("producer", "00_producer"),
                PipelineStep("planner", "02_planner"),
            ]
        },
    }
    
    # 质量门禁定义
    QUALITY_GATES = {
        "gate_1": QualityGate(
            name="关卡1: 策划→主程/UX",
            from_stage="planner",
            to_stage="tech_lead",
            check_items=[
                "文件存在性(3项)", "格式完整性(6项)", "内容质量(9项)",
                "实现泄漏检查(4项)", "全局一致性(3项)"
            ]
        ),
        "gate_2": QualityGate(
            name="关卡2: 主程→程序",
            from_stage="tech_lead",
            to_stage="programmer",
            check_items=[
                "文件存在性(2项)", "架构完整性(6项)", "任务可执行性(4项)",
                "测试策略(3项)", "风险与兼容性(3项)"
            ]
        ),
        "gate_3": QualityGate(
            name="关卡3: 程序→QA",
            from_stage="programmer",
            to_stage="qa",
            check_items=[
                "代码完整性(5项)", "代码质量深潜(7项)", "Unity特定检查(4项)",
                "可测试性(3项)", "验收标准覆盖审计(3项)", "事后防护检查(7项)"
            ]
        ),
    }
    
    def __init__(self):
        """初始化流水线引擎"""
        self._instances: Dict[str, PipelineInstance] = {}
        self._instance_counter = 0
    
    def create_pipeline(self, req_id: str, req_type: ReqType, 
                        req_scale: ReqScale, req_name: str = "") -> PipelineInstance:
        """
        创建流水线实例
        
        Args:
            req_id: 需求ID
            req_type: 需求类型
            req_scale: 需求规模
            req_name: 需求名称
            
        Returns:
            PipelineInstance
        """
        self._instance_counter += 1
        pipeline_id = f"PL-{self._instance_counter:04d}"
        
        definition = self.PIPELINE_DEFINITIONS.get(req_type)
        if not definition:
            raise ValueError(f"未知的需求类型: {req_type}")
        
        # 复制步骤定义
        steps = [
            PipelineStep(
                stage=s.stage,
                agent_id=s.agent_id,
                execution=s.execution,
                parallel_with=s.parallel_with.copy(),
                quality_gate=s.quality_gate,
                optional=s.optional
            )
            for s in definition["stages"]
        ]
        
        # 根据规模调整步骤
        if req_scale in (ReqScale.L, ReqScale.XL):
            self._apply_master_slave_mode(steps, req_type)
        
        if req_scale == ReqScale.XL:
            self._apply_deep_mode(steps, req_type)
        
        instance = PipelineInstance(
            pipeline_id=pipeline_id,
            req_id=req_id,
            req_type=req_type.value,
            req_scale=req_scale.value,
            req_name=req_name,
            steps=steps,
        )
        
        # 设置质量门禁
        for step in steps:
            if step.quality_gate:
                gate_def = self.QUALITY_GATES.get(step.quality_gate)
                if gate_def:
                    instance.quality_gates[step.quality_gate] = QualityGate(
                        name=gate_def.name,
                        from_stage=gate_def.from_stage,
                        to_stage=gate_def.to_stage,
                        check_items=gate_def.check_items.copy()
                    )
        
        self._instances[pipeline_id] = instance
        return instance
    
    def _apply_master_slave_mode(self, steps: List[PipelineStep], 
                                  req_type: ReqType):
        """应用主从模式（L规模）"""
        # 标记需要拆分子任务的阶段
        for step in steps:
            if step.agent_id in ("02_planner", "04_programmer", "06_qa"):
                step.execution = "parallel"  # 标记为可并行
    
    def _apply_deep_mode(self, steps: List[PipelineStep], req_type: ReqType):
        """应用深度模式（XL规模）"""
        # XL模式的增强已经在Agent步骤文件中定义
        # 这里只做标记
        pass
    
    def get_pipeline(self, pipeline_id: str) -> Optional[PipelineInstance]:
        """获取流水线实例"""
        return self._instances.get(pipeline_id)
    
    def get_next_step(self, pipeline_id: str) -> Optional[PipelineStep]:
        """获取流水线下一步骤"""
        instance = self._instances.get(pipeline_id)
        if not instance:
            return None
        return instance.advance()
    
    def check_quality_gate(self, pipeline_id: str, gate_name: str,
                           check_results: Dict[str, bool]) -> bool:
        """
        执行质量门禁检查
        
        Args:
            pipeline_id: 流水线ID
            gate_name: 门禁名称
            check_results: 各检查项结果
            
        Returns:
            是否通过
        """
        instance = self._instances.get(pipeline_id)
        if not instance:
            return False
        
        gate = instance.quality_gates.get(gate_name)
        if not gate:
            return True  # 没有门禁则直接通过
        
        all_passed = all(check_results.values())
        gate.passed = all_passed
        gate.checked_at = datetime.now().isoformat()
        gate.details = check_results
        
        return all_passed
    
    def handle_bug_flow(self, pipeline_id: str) -> Optional[PipelineStep]:
        """
        处理Bug流转（QA发现Bug后回到程序修复）
        
        Returns:
            程序Agent的步骤，如果超过最大修复轮数返回None
        """
        instance = self._instances.get(pipeline_id)
        if not instance:
            return None
        
        instance.bug_rounds += 1
        
        if instance.bug_rounds > instance.max_bug_rounds:
            instance.status = "paused"
            return None  # 超过最大轮数，暂停等待用户介入
        
        # 回退到程序Agent步骤
        for i, step in enumerate(instance.steps):
            if step.agent_id == "04_programmer":
                instance.current_step_index = i
                return step
        
        return None
    
    def delete_pipeline(self, pipeline_id: str) -> bool:
        """
        删除流水线实例
        
        Args:
            pipeline_id: 流水线ID
            
        Returns:
            是否删除成功
        """
        if pipeline_id in self._instances:
            del self._instances[pipeline_id]
            return True
        return False

    def rename_pipeline(self, pipeline_id: str, new_name: str) -> Optional[PipelineInstance]:
        """
        重命名流水线
        
        Args:
            pipeline_id: 流水线ID
            new_name: 新名称
            
        Returns:
            更新后的实例，不存在则返回None
        """
        instance = self._instances.get(pipeline_id)
        if instance:
            instance.req_name = new_name
            return instance
        return None

    def complete_pipeline(self, pipeline_id: str):
        """完成流水线"""
        instance = self._instances.get(pipeline_id)
        if instance:
            instance.status = "completed"
            instance.completed_at = datetime.now().isoformat()
    
    def get_active_pipelines(self) -> List[dict]:
        """获取所有活跃流水线"""
        return [
            inst.to_dict()
            for inst in self._instances.values()
            if inst.status in ("created", "running")
        ]
    
    def get_pipeline_summary(self, pipeline_id: str) -> Optional[dict]:
        """获取流水线摘要"""
        instance = self._instances.get(pipeline_id)
        if not instance:
            return None
        return instance.to_dict()
