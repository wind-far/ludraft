"""
消息队列模块 - Agent间异步通信的核心组件

提供基于文件的消息队列，支持：
- 点对点消息传递
- 频道广播
- 消息优先级
- 消息确认(ACK)机制
"""

import json
import os
import time
import uuid
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime


class _FileLock:
    """
    跨平台文件锁
    
    Windows 使用 msvcrt.locking()，Unix 使用 fcntl.flock()
    提供上下文管理器接口，确保并发安全。
    """
    
    def __init__(self, lock_path: str, timeout: float = 5.0):
        self._lock_path = lock_path
        self._timeout = timeout
        self._lock_file = None
        # 线程级互斥锁（进程内线程安全）
        self._thread_lock = threading.Lock()
    
    @contextmanager
    def acquire(self):
        """获取锁（上下文管理器）"""
        self._thread_lock.acquire()
        try:
            # 确保锁文件目录存在
            os.makedirs(os.path.dirname(self._lock_path), exist_ok=True)
            self._lock_file = open(self._lock_path, 'w')
            
            # 尝试获取文件级锁
            self._platform_lock()
            try:
                yield
            finally:
                self._platform_unlock()
                self._lock_file.close()
                self._lock_file = None
        finally:
            self._thread_lock.release()
    
    def _platform_lock(self):
        """平台特定的文件锁获取"""
        try:
            import msvcrt
            # Windows: 锁定文件第一个字节
            deadline = time.time() + self._timeout
            while True:
                try:
                    msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                    return
                except (OSError, IOError):
                    if time.time() >= deadline:
                        raise TimeoutError(f"获取文件锁超时: {self._lock_path}")
                    time.sleep(0.05)
        except ImportError:
            try:
                import fcntl
                # Unix: flock
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX)
            except ImportError:
                # 都不支持则仅依赖线程锁
                pass
    
    def _platform_unlock(self):
        """平台特定的文件锁释放"""
        if not self._lock_file:
            return
        try:
            import msvcrt
            try:
                msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            except (OSError, IOError):
                pass
        except ImportError:
            try:
                import fcntl
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            except ImportError:
                pass


class MessageType(Enum):
    """消息类型枚举"""
    HANDOFF = "handoff"              # 阶段流转
    BUG_REPORT = "bug_report"        # Bug报告
    STATUS_UPDATE = "status_update"  # 状态更新
    SUBTASK_DISPATCH = "subtask_dispatch"  # 子任务派发
    SUBTASK_RESULT = "subtask_result"      # 子任务结果
    QUALITY_GATE = "quality_gate"    # 质量门禁结果
    BROADCAST = "broadcast"          # 广播消息
    ACK = "ack"                      # 确认消息


class MessagePriority(Enum):
    """消息优先级"""
    URGENT = "urgent"      # 紧急（Bug修复流转）
    HIGH = "high"          # 高（质量门禁失败）
    NORMAL = "normal"      # 正常（阶段流转）
    LOW = "low"            # 低（状态更新）


class MessageChannel(Enum):
    """消息频道"""
    CONTROL = "channel_control"    # 控制通道（制作人、项目管理）
    DESIGN = "channel_design"      # 设计通道（策划、UX、美术）
    IMPL = "channel_impl"          # 实现通道（主程、程序）
    VERIFY = "channel_verify"      # 验证通道（QA）
    GLOBAL = "channel_global"      # 全局通道（广播）


@dataclass
class Message:
    """消息数据结构"""
    msg_id: str = ""
    timestamp: str = ""
    from_agent: str = ""
    to_agent: str = ""
    channel: str = ""
    msg_type: str = ""
    priority: str = "normal"
    payload: Dict[str, Any] = field(default_factory=dict)
    ack_required: bool = False
    ack_received: bool = False
    
    def __post_init__(self):
        if not self.msg_id:
            self.msg_id = f"MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Message":
        return cls.from_dict(json.loads(json_str))


class MessageQueue:
    """
    基于文件的消息队列
    
    目录结构:
    _message_queue/
    ├── channel_control/
    │   ├── msg_001.json
    │   └── msg_002.json
    ├── channel_design/
    ├── channel_impl/
    ├── channel_verify/
    └── channel_global/
    """
    
    def __init__(self, queue_root: str):
        """
        初始化消息队列
        
        Args:
            queue_root: 消息队列根目录路径
        """
        self.queue_root = Path(queue_root)
        self._ensure_channels()
        # 每个频道一个文件锁，避免跨频道操作互相阻塞
        self._channel_locks: Dict[str, _FileLock] = {}
        for channel in MessageChannel:
            lock_path = str(self.queue_root / f".{channel.value}.lock")
            self._channel_locks[channel.value] = _FileLock(lock_path)
    
    def _ensure_channels(self):
        """确保所有频道目录存在"""
        for channel in MessageChannel:
            channel_dir = self.queue_root / channel.value
            channel_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_agent_channel(self, agent_id: str) -> MessageChannel:
        """根据Agent ID获取对应频道"""
        channel_map = {
            "00_producer": MessageChannel.CONTROL,
            "01_pm": MessageChannel.CONTROL,
            "02_planner": MessageChannel.DESIGN,
            "07_ux": MessageChannel.DESIGN,
            "05_artist": MessageChannel.DESIGN,
            "03_tech_lead": MessageChannel.IMPL,
            "04_programmer": MessageChannel.IMPL,
            "06_qa": MessageChannel.VERIFY,
        }
        return channel_map.get(agent_id, MessageChannel.GLOBAL)
    
    def send(self, message: Message) -> str:
        """
        发送消息到队列（线程安全）
        
        Args:
            message: 消息对象
            
        Returns:
            消息ID
        """
        # 确定目标频道
        if message.msg_type == MessageType.BROADCAST.value:
            channel = MessageChannel.GLOBAL
        else:
            channel = self._get_agent_channel(message.to_agent)
        
        message.channel = channel.value
        
        # 🔒 加锁写入消息文件
        lock = self._channel_locks.get(channel.value)
        channel_dir = self.queue_root / channel.value
        msg_file = channel_dir / f"{message.msg_id}.json"
        
        with lock.acquire():
            with open(msg_file, 'w', encoding='utf-8') as f:
                f.write(message.to_json())
        
        return message.msg_id
    
    def receive(self, agent_id: str, msg_type: Optional[str] = None, 
                limit: int = 10) -> List[Message]:
        """
        接收指定Agent的消息（线程安全）
        
        Args:
            agent_id: 目标Agent ID
            msg_type: 可选的消息类型过滤
            limit: 最大返回数量
            
        Returns:
            消息列表（按时间排序）
        """
        messages = []
        
        # 搜索Agent对应频道和全局频道
        channels = [self._get_agent_channel(agent_id), MessageChannel.GLOBAL]
        
        for channel in channels:
            channel_dir = self.queue_root / channel.value
            if not channel_dir.exists():
                continue
            
            # 🔒 加锁读取
            lock = self._channel_locks.get(channel.value)
            with lock.acquire():
                for msg_file in sorted(channel_dir.glob("MSG-*.json")):
                    try:
                        with open(msg_file, 'r', encoding='utf-8') as f:
                            msg = Message.from_json(f.read())
                        
                        # 过滤目标Agent
                        if msg.to_agent != agent_id and msg.msg_type != MessageType.BROADCAST.value:
                            continue
                        
                        # 过滤消息类型
                        if msg_type and msg.msg_type != msg_type:
                            continue
                        
                        messages.append(msg)
                        
                    except (json.JSONDecodeError, KeyError) as e:
                        continue
        
        # 按时间排序，优先级高的在前
        priority_order = {
            MessagePriority.URGENT.value: 0,
            MessagePriority.HIGH.value: 1,
            MessagePriority.NORMAL.value: 2,
            MessagePriority.LOW.value: 3,
        }
        messages.sort(key=lambda m: (
            priority_order.get(m.priority, 2),
            m.timestamp
        ))
        
        return messages[:limit]
    
    def consume(self, agent_id: str, msg_id: str) -> Optional[Message]:
        """
        消费（读取并删除）指定消息（线程安全）
        
        读取和删除在同一把锁内原子执行，避免竞态条件。
        如果消息设置了 ack_required=True，会自动发送 ACK 回执。
        
        Args:
            agent_id: Agent ID
            msg_id: 消息ID
            
        Returns:
            消息对象，如果不存在返回None
        """
        for channel in MessageChannel:
            channel_dir = self.queue_root / channel.value
            msg_file = channel_dir / f"{msg_id}.json"
            
            # 🔒 加锁：读取 + 删除必须原子操作
            lock = self._channel_locks.get(channel.value)
            with lock.acquire():
                if msg_file.exists():
                    try:
                        with open(msg_file, 'r', encoding='utf-8') as f:
                            msg = Message.from_json(f.read())
                    except (json.JSONDecodeError, KeyError):
                        continue
                    
                    if msg.to_agent == agent_id or msg.msg_type == MessageType.BROADCAST.value:
                        msg_file.unlink()  # 消费后删除
                        
                        # ACK 机制：如果消息要求确认，自动发送回执
                        if msg.ack_required and not msg.ack_received:
                            self._send_ack(agent_id, msg)
                        
                        return msg
        
        return None
    
    def send_handoff(self, from_agent: str, to_agent: str, req_id: str,
                     artifacts: List[str], quality_gate_passed: bool = True,
                     message: str = "") -> str:
        """
        发送阶段流转消息（快捷方法）
        
        Args:
            from_agent: 发送方Agent ID
            to_agent: 接收方Agent ID
            req_id: 需求ID
            artifacts: 产出物文件路径列表
            quality_gate_passed: 质量门禁是否通过
            message: 流转说明
            
        Returns:
            消息ID
        """
        msg = Message(
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=MessageType.HANDOFF.value,
            priority=MessagePriority.NORMAL.value,
            payload={
                "req_id": req_id,
                "action": "flow_transfer",
                "artifacts": artifacts,
                "quality_gate_passed": quality_gate_passed,
                "message": message or f"⚡ 流转至下一阶段"
            }
        )
        return self.send(msg)
    
    def send_bug_report(self, from_agent: str, to_agent: str, req_id: str,
                        bug_id: str, severity: str, description: str) -> str:
        """
        发送Bug报告消息（快捷方法）
        """
        msg = Message(
            from_agent=from_agent,
            to_agent=to_agent,
            msg_type=MessageType.BUG_REPORT.value,
            priority=MessagePriority.URGENT.value if severity == "P0" else MessagePriority.HIGH.value,
            payload={
                "req_id": req_id,
                "bug_id": bug_id,
                "severity": severity,
                "description": description,
                "action": "bug_fix_required"
            }
        )
        return self.send(msg)
    
    def broadcast(self, from_agent: str, payload: Dict[str, Any]) -> str:
        """发送广播消息"""
        msg = Message(
            from_agent=from_agent,
            to_agent="*",
            msg_type=MessageType.BROADCAST.value,
            priority=MessagePriority.LOW.value,
            payload=payload
        )
        return self.send(msg)
    
    def get_queue_stats(self) -> Dict[str, int]:
        """获取队列统计信息（线程安全）"""
        stats = {}
        for channel in MessageChannel:
            channel_dir = self.queue_root / channel.value
            lock = self._channel_locks.get(channel.value)
            with lock.acquire():
                if channel_dir.exists():
                    stats[channel.value] = len(list(channel_dir.glob("MSG-*.json")))
                else:
                    stats[channel.value] = 0
        return stats
    
    def clear_channel(self, channel: MessageChannel):
        """清空指定频道（线程安全）"""
        channel_dir = self.queue_root / channel.value
        lock = self._channel_locks.get(channel.value)
        with lock.acquire():
            if channel_dir.exists():
                for msg_file in channel_dir.glob("MSG-*.json"):
                    msg_file.unlink()
    
    def clear_all(self):
        """清空所有频道（逐频道加锁）"""
        for channel in MessageChannel:
            self.clear_channel(channel)
    
    # ──────────────────────────────────────────────
    # ACK 确认机制
    # ──────────────────────────────────────────────
    
    def send_with_ack(self, message: Message, timeout: float = 30.0) -> str:
        """
        发送一条需要确认的消息
        
        消息的 ack_required 会被自动设置为 True。
        发送方可以随后调用 wait_for_ack() 阻塞等待确认，
        或通过 check_ack() 非阻塞轮询。
        
        Args:
            message: 消息对象
            timeout: ACK 等待超时时间（秒），仅记录到 payload 中供后续使用
            
        Returns:
            消息ID
        """
        message.ack_required = True
        message.ack_received = False
        message.payload["_ack_timeout"] = timeout
        message.payload["_ack_sent_at"] = time.time()
        return self.send(message)
    
    def _send_ack(self, consumer_agent_id: str, original_msg: Message):
        """
        内部方法：为已消费的消息发送 ACK 回执
        
        ACK 消息发送到原始消息发送方所在的频道。
        
        Args:
            consumer_agent_id: 消费者 Agent ID
            original_msg: 被消费的原始消息
        """
        ack_msg = Message(
            from_agent=consumer_agent_id,
            to_agent=original_msg.from_agent,
            msg_type=MessageType.ACK.value,
            priority=MessagePriority.HIGH.value,
            payload={
                "original_msg_id": original_msg.msg_id,
                "original_msg_type": original_msg.msg_type,
                "ack_status": "received",
                "ack_at": datetime.now().isoformat(),
                "consumer": consumer_agent_id,
            }
        )
        self.send(ack_msg)
    
    def check_ack(self, sender_agent_id: str, original_msg_id: str) -> Optional[Message]:
        """
        非阻塞检查某条消息是否已收到 ACK
        
        遍历发送方所在频道，查找 msg_type=ACK 且 payload 包含
        original_msg_id 的消息。找到后消费（删除）该 ACK 消息并返回。
        
        Args:
            sender_agent_id: 发送方 Agent ID
            original_msg_id: 原始消息 ID
            
        Returns:
            ACK 消息对象，未找到返回 None
        """
        channel = self._get_agent_channel(sender_agent_id)
        channel_dir = self.queue_root / channel.value
        
        lock = self._channel_locks.get(channel.value)
        with lock.acquire():
            if not channel_dir.exists():
                return None
            for msg_file in sorted(channel_dir.glob("MSG-*.json")):
                try:
                    with open(msg_file, 'r', encoding='utf-8') as f:
                        msg = Message.from_json(f.read())
                except (json.JSONDecodeError, KeyError):
                    continue
                
                if (msg.msg_type == MessageType.ACK.value
                        and msg.to_agent == sender_agent_id
                        and msg.payload.get("original_msg_id") == original_msg_id):
                    msg_file.unlink()  # 消费 ACK 消息
                    return msg
        
        return None
    
    def wait_for_ack(self, sender_agent_id: str, original_msg_id: str,
                     timeout: float = 30.0, poll_interval: float = 0.5) -> Optional[Message]:
        """
        阻塞等待 ACK 回执
        
        在超时时间内以 poll_interval 间隔轮询 check_ack()。
        
        Args:
            sender_agent_id: 发送方 Agent ID
            original_msg_id: 原始消息 ID
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）
            
        Returns:
            ACK 消息对象，超时返回 None
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            ack = self.check_ack(sender_agent_id, original_msg_id)
            if ack is not None:
                return ack
            time.sleep(poll_interval)
        return None
    
    def get_pending_acks(self, sender_agent_id: str) -> List[Dict[str, Any]]:
        """
        获取发送方所有未确认的消息（需要 ACK 但尚未收到）
        
        扫描所有频道，找出 ack_required=True 且尚无对应 ACK 回执的消息。
        
        Args:
            sender_agent_id: 发送方 Agent ID
            
        Returns:
            未确认消息的摘要列表，每项包含 msg_id, to_agent, msg_type, sent_at, elapsed
        """
        pending = []
        now = time.time()
        
        for channel in MessageChannel:
            channel_dir = self.queue_root / channel.value
            lock = self._channel_locks.get(channel.value)
            with lock.acquire():
                if not channel_dir.exists():
                    continue
                for msg_file in channel_dir.glob("MSG-*.json"):
                    try:
                        with open(msg_file, 'r', encoding='utf-8') as f:
                            msg = Message.from_json(f.read())
                    except (json.JSONDecodeError, KeyError):
                        continue
                    
                    if (msg.from_agent == sender_agent_id
                            and msg.ack_required
                            and not msg.ack_received):
                        sent_at = msg.payload.get("_ack_sent_at", 0)
                        timeout_val = msg.payload.get("_ack_timeout", 30.0)
                        elapsed = now - sent_at if sent_at else 0
                        pending.append({
                            "msg_id": msg.msg_id,
                            "to_agent": msg.to_agent,
                            "msg_type": msg.msg_type,
                            "sent_at": msg.timestamp,
                            "elapsed_seconds": round(elapsed, 1),
                            "timeout": timeout_val,
                            "is_expired": elapsed > timeout_val if sent_at else False,
                        })
        
        return pending
    
    def retry_unacked(self, sender_agent_id: str, max_retries: int = 3) -> List[str]:
        """
        重试所有超时未确认的消息
        
        对于已超过 ACK 超时且 retry_count < max_retries 的消息，
        重新发送（生成新 msg_id），并在 payload 中递增 retry_count。
        原始消息保留以备审计。
        
        Args:
            sender_agent_id: 发送方 Agent ID
            max_retries: 最大重试次数
            
        Returns:
            重新发送的消息ID列表
        """
        pending = self.get_pending_acks(sender_agent_id)
        retried_ids = []
        
        for item in pending:
            if not item["is_expired"]:
                continue
            
            # 在所有频道中找到原始消息
            original_msg = self._find_message(item["msg_id"])
            if original_msg is None:
                continue
            
            retry_count = original_msg.payload.get("_retry_count", 0)
            if retry_count >= max_retries:
                # 超过最大重试次数，标记为失败
                original_msg.payload["_ack_status"] = "failed"
                original_msg.payload["_failure_reason"] = f"超过最大重试次数 ({max_retries})"
                self._update_message_file(original_msg)
                continue
            
            # 创建重试消息
            retry_msg = Message(
                from_agent=original_msg.from_agent,
                to_agent=original_msg.to_agent,
                msg_type=original_msg.msg_type,
                priority=original_msg.priority,
                payload={
                    **original_msg.payload,
                    "_retry_count": retry_count + 1,
                    "_original_msg_id": item["msg_id"],
                    "_ack_sent_at": time.time(),
                },
                ack_required=True,
            )
            new_id = self.send(retry_msg)
            retried_ids.append(new_id)
        
        return retried_ids
    
    def _find_message(self, msg_id: str) -> Optional[Message]:
        """
        在所有频道中查找消息（不删除）
        
        Args:
            msg_id: 消息ID
            
        Returns:
            消息对象或 None
        """
        for channel in MessageChannel:
            channel_dir = self.queue_root / channel.value
            msg_file = channel_dir / f"{msg_id}.json"
            lock = self._channel_locks.get(channel.value)
            with lock.acquire():
                if msg_file.exists():
                    try:
                        with open(msg_file, 'r', encoding='utf-8') as f:
                            return Message.from_json(f.read())
                    except (json.JSONDecodeError, KeyError):
                        return None
        return None
    
    def _update_message_file(self, message: Message):
        """
        原地更新消息文件内容（线程安全）
        
        Args:
            message: 更新后的消息对象
        """
        channel_value = message.channel
        if not channel_value:
            return
        
        channel_dir = self.queue_root / channel_value
        msg_file = channel_dir / f"{message.msg_id}.json"
        lock = self._channel_locks.get(channel_value)
        
        with lock.acquire():
            if msg_file.exists():
                with open(msg_file, 'w', encoding='utf-8') as f:
                    f.write(message.to_json())
