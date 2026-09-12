"""
结构化日志模块 - 多Agent环境下的统一日志管理

核心职责:
- 为每个Agent创建独立日志文件
- 结构化JSON格式日志输出
- 操作审计追踪
- 日志分级与过滤
- 性能指标收集
"""

import json
import os
import sys
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass, field, asdict
from enum import Enum


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class LogEntry:
    """结构化日志条目"""
    timestamp: str = ""
    level: str = "INFO"
    agent_id: str = ""
    module: str = ""
    event: str = ""
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    req_id: str = ""
    pipeline_id: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        result = asdict(self)
        # 移除空值字段以保持日志简洁
        return {k: v for k, v in result.items() if v is not None and v != "" and v != {}}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class AgentLogger:
    """
    Agent专用日志记录器

    每个Agent实例拥有独立的日志记录器，
    输出到Agent沙盒的 logs/ 目录
    """

    def __init__(self, agent_id: str, agent_name: str,
                 log_dir: Optional[str] = None,
                 console_output: bool = False,
                 level: str = "INFO"):
        """
        初始化Agent日志记录器

        Args:
            agent_id: Agent ID
            agent_name: Agent名称
            log_dir: 日志目录路径
            console_output: 是否输出到控制台
            level: 日志级别
        """
        self.agent_id = agent_id
        self.agent_name = agent_name
        self.log_dir = Path(log_dir) if log_dir else None
        self.console_output = console_output
        self._level = getattr(logging, level.upper(), logging.INFO)
        self._lock = threading.Lock()

        # 内存日志缓冲
        self._buffer: List[LogEntry] = []
        self._max_buffer_size = 1000

        # 初始化Python标准日志器
        self._logger = logging.getLogger(f"openclaw.agent.{agent_id}")
        self._logger.setLevel(self._level)
        self._logger.propagate = False

        # 清除已有处理器
        self._logger.handlers.clear()

        # 设置处理器
        self._setup_handlers()

    def _setup_handlers(self):
        """设置日志处理器"""
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # 文件处理器
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            log_file = self.log_dir / f"{self.agent_id}.log"
            file_handler = logging.FileHandler(
                str(log_file), encoding='utf-8'
            )
            file_handler.setLevel(self._level)
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

            # JSON格式日志文件
            json_log_file = self.log_dir / f"{self.agent_id}.jsonl"
            self._json_log_path = json_log_file

        # 控制台处理器
        if self.console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self._level)
            console_handler.setFormatter(formatter)
            self._logger.addHandler(console_handler)

    def _write_entry(self, entry: LogEntry):
        """写入日志条目"""
        with self._lock:
            # 写入内存缓冲
            self._buffer.append(entry)
            if len(self._buffer) > self._max_buffer_size:
                self._buffer = self._buffer[-self._max_buffer_size:]

            # 写入标准日志
            log_msg = f"[{entry.agent_id}] [{entry.event}] {entry.message}"
            level = getattr(logging, entry.level, logging.INFO)
            self._logger.log(level, log_msg)

            # 写入JSON日志
            if self.log_dir and hasattr(self, '_json_log_path'):
                try:
                    with open(self._json_log_path, 'a', encoding='utf-8') as f:
                        f.write(entry.to_json() + '\n')
                except Exception:
                    pass  # 日志写入失败不应影响主流程

    def debug(self, event: str, message: str, **kwargs):
        """DEBUG级别日志"""
        entry = LogEntry(
            level="DEBUG", agent_id=self.agent_id,
            event=event, message=message, **kwargs
        )
        self._write_entry(entry)

    def info(self, event: str, message: str, **kwargs):
        """INFO级别日志"""
        entry = LogEntry(
            level="INFO", agent_id=self.agent_id,
            event=event, message=message, **kwargs
        )
        self._write_entry(entry)

    def warning(self, event: str, message: str, **kwargs):
        """WARNING级别日志"""
        entry = LogEntry(
            level="WARNING", agent_id=self.agent_id,
            event=event, message=message, **kwargs
        )
        self._write_entry(entry)

    def error(self, event: str, message: str, **kwargs):
        """ERROR级别日志"""
        entry = LogEntry(
            level="ERROR", agent_id=self.agent_id,
            event=event, message=message, **kwargs
        )
        self._write_entry(entry)

    def critical(self, event: str, message: str, **kwargs):
        """CRITICAL级别日志"""
        entry = LogEntry(
            level="CRITICAL", agent_id=self.agent_id,
            event=event, message=message, **kwargs
        )
        self._write_entry(entry)

    def audit(self, event: str, message: str,
              data: Optional[Dict[str, Any]] = None, **kwargs):
        """
        审计日志 - 记录重要操作（始终以INFO级别写入）

        用于记录:
        - 文件操作
        - 权限检查
        - 质量门禁
        - 流水线流转
        """
        entry = LogEntry(
            level="INFO", agent_id=self.agent_id,
            module="audit", event=event, message=message,
            data=data or {}, **kwargs
        )
        self._write_entry(entry)

    def step_start(self, step_name: str, req_id: str = "",
                   pipeline_id: str = ""):
        """记录步骤开始"""
        self.info(
            event="step_start",
            message=f"📍 开始步骤: {step_name}",
            req_id=req_id, pipeline_id=pipeline_id
        )

    def step_complete(self, step_name: str, duration_ms: float = 0,
                      artifacts: Optional[List[str]] = None,
                      req_id: str = "", pipeline_id: str = ""):
        """记录步骤完成"""
        self.info(
            event="step_complete",
            message=f"✅ 步骤完成: {step_name}",
            duration_ms=duration_ms,
            data={"artifacts": artifacts or []},
            req_id=req_id, pipeline_id=pipeline_id
        )

    def quality_gate(self, gate_name: str, passed: bool,
                     details: Optional[Dict[str, Any]] = None,
                     req_id: str = ""):
        """记录质量门禁结果"""
        status = "✅ 通过" if passed else "❌ 未通过"
        self.info(
            event="quality_gate",
            message=f"🚧 质量门禁 {gate_name}: {status}",
            data={"gate": gate_name, "passed": passed, **(details or {})},
            req_id=req_id
        )

    def get_recent_logs(self, count: int = 50,
                        level: Optional[str] = None) -> List[dict]:
        """获取最近的日志条目"""
        logs = self._buffer[-count:]
        if level:
            logs = [e for e in logs if e.level == level.upper()]
        return [e.to_dict() for e in logs]

    def get_stats(self) -> Dict[str, int]:
        """获取日志统计"""
        stats = {"total": len(self._buffer)}
        for entry in self._buffer:
            stats[entry.level] = stats.get(entry.level, 0) + 1
        return stats


class SystemLogger:
    """
    系统级日志管理器

    管理所有Agent日志器的生命周期，
    提供全局日志视图和聚合查询
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, log_root: Optional[str] = None,
                 console_output: bool = False,
                 default_level: str = "INFO"):
        """
        初始化系统日志管理器

        Args:
            log_root: 日志根目录
            console_output: 是否输出到控制台
            default_level: 默认日志级别
        """
        if self._initialized:
            return

        self.log_root = Path(log_root) if log_root else None
        self.console_output = console_output
        self.default_level = default_level
        self._agent_loggers: Dict[str, AgentLogger] = {}
        self._system_logger: Optional[AgentLogger] = None

        # 创建系统日志器
        if self.log_root:
            self.log_root.mkdir(parents=True, exist_ok=True)
            self._system_logger = AgentLogger(
                agent_id="system",
                agent_name="系统",
                log_dir=str(self.log_root / "_system"),
                console_output=console_output,
                level=default_level
            )

        self._initialized = True

    def get_agent_logger(self, agent_id: str,
                         agent_name: str = "") -> AgentLogger:
        """
        获取或创建Agent日志器

        Args:
            agent_id: Agent ID
            agent_name: Agent名称

        Returns:
            AgentLogger实例
        """
        if agent_id not in self._agent_loggers:
            log_dir = None
            if self.log_root:
                log_dir = str(self.log_root / agent_id)

            logger = AgentLogger(
                agent_id=agent_id,
                agent_name=agent_name or agent_id,
                log_dir=log_dir,
                console_output=self.console_output,
                level=self.default_level
            )
            self._agent_loggers[agent_id] = logger

        return self._agent_loggers[agent_id]

    def get_system_logger(self) -> Optional[AgentLogger]:
        """获取系统日志器"""
        return self._system_logger

    def info(self, event: str, message: str, **kwargs):
        """系统级INFO日志"""
        if self._system_logger:
            self._system_logger.info(event, message, **kwargs)

    def warning(self, event: str, message: str, **kwargs):
        """系统级WARNING日志"""
        if self._system_logger:
            self._system_logger.warning(event, message, **kwargs)

    def error(self, event: str, message: str, **kwargs):
        """系统级ERROR日志"""
        if self._system_logger:
            self._system_logger.error(event, message, **kwargs)

    def get_all_recent_logs(self, count: int = 100) -> List[dict]:
        """获取所有Agent的最近日志（聚合视图）"""
        all_logs = []

        if self._system_logger:
            all_logs.extend(self._system_logger.get_recent_logs(count))

        for logger in self._agent_loggers.values():
            all_logs.extend(logger.get_recent_logs(count))

        # 按时间排序
        all_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return all_logs[:count]

    def get_all_stats(self) -> Dict[str, Dict[str, int]]:
        """获取所有日志器的统计"""
        stats = {}
        if self._system_logger:
            stats["system"] = self._system_logger.get_stats()

        for agent_id, logger in self._agent_loggers.items():
            stats[agent_id] = logger.get_stats()

        return stats

    def export_all_logs(self, output_dir: str):
        """导出所有日志到指定目录"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 导出聚合日志
        all_logs = self.get_all_recent_logs(10000)
        with open(output_path / "all_logs.json", 'w', encoding='utf-8') as f:
            json.dump(all_logs, f, ensure_ascii=False, indent=2)

        # 导出统计
        stats = self.get_all_stats()
        with open(output_path / "log_stats.json", 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)

    @classmethod
    def reset(cls):
        """重置单例（用于测试）"""
        cls._instance = None
