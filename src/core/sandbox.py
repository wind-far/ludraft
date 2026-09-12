"""
沙盒管理器 - Agent独立工作环境隔离

核心职责:
- 创建/销毁Agent沙盒目录
- 文件访问权限控制
- 源文档保护（只读镜像）
- 工作副本管理
"""

import os
import shutil
import json
import stat
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SandboxConfig:
    """沙盒配置"""
    agent_id: str
    agent_name: str
    sandbox_root: str
    # 允许的读取路径（相对于项目根目录）
    read_permissions: List[str] = field(default_factory=list)
    # 允许的写入路径
    write_permissions: List[str] = field(default_factory=list)
    # 允许的创建路径
    create_permissions: List[str] = field(default_factory=list)
    # 是否需要独立沙盒
    needs_sandbox: bool = True


@dataclass 
class FileOperation:
    """文件操作记录"""
    timestamp: str
    agent_id: str
    operation: str  # read, write, create, delete
    path: str
    allowed: bool
    reason: str = ""


class SourceProtectionGuard:
    """
    源文档保护守卫
    
    确保 rules/ 目录下的源文件不被修改
    """
    
    def __init__(self, protected_paths: List[str], project_root: str):
        self.protected_paths = [Path(project_root) / p for p in protected_paths]
        self.project_root = Path(project_root)
    
    def is_protected(self, file_path: str) -> bool:
        """检查文件是否受保护"""
        abs_path = Path(file_path).resolve()
        for protected in self.protected_paths:
            protected_resolved = protected.resolve()
            try:
                abs_path.relative_to(protected_resolved)
                return True
            except ValueError:
                continue
        return False
    
    def check_write(self, file_path: str) -> tuple:
        """
        检查写入操作是否允许
        
        Returns:
            (allowed: bool, reason: str)
        """
        if self.is_protected(file_path):
            return False, f"🔒 源文档保护: {file_path} 位于受保护目录，禁止写入"
        return True, ""
    
    def check_delete(self, file_path: str) -> tuple:
        """检查删除操作是否允许"""
        if self.is_protected(file_path):
            return False, f"🔒 源文档保护: {file_path} 位于受保护目录，禁止删除"
        return True, ""


class SandboxManager:
    """
    沙盒管理器
    
    为每个Agent创建独立的工作环境，实现:
    - 目录隔离: 每个Agent有独立的工作目录
    - 权限控制: 基于白名单的文件访问控制
    - 源文档保护: rules/ 目录只读
    - 工作副本: 源文档的只读镜像
    """
    
    # 沙盒标准子目录
    SANDBOX_DIRS = ["context", "workspace", "output", "logs", "inbox", "outbox"]
    
    def __init__(self, project_root: str, sandbox_root: str = ".sandboxes",
                 protected_paths: Optional[List[str]] = None):
        """
        初始化沙盒管理器
        
        Args:
            project_root: 项目根目录
            sandbox_root: 沙盒根目录（相对于项目根目录）
            protected_paths: 受保护的源文档路径列表
        """
        self.project_root = Path(project_root)
        self.sandbox_root = self.project_root / sandbox_root
        self.working_copies_dir = self.sandbox_root / "_working_copies"
        self.shared_dir = self.sandbox_root / "_shared"
        self.message_queue_dir = self.sandbox_root / "_message_queue"
        
        # 源文档保护
        protected = protected_paths or ["rules"]
        self.source_guard = SourceProtectionGuard(protected, project_root)
        
        # Agent沙盒注册表
        self._sandboxes: Dict[str, SandboxConfig] = {}
        
        # 操作日志
        self._operation_log: List[FileOperation] = []
        
        # 确保基础目录存在
        self._init_base_dirs()
    
    def _init_base_dirs(self):
        """初始化基础目录"""
        self.sandbox_root.mkdir(parents=True, exist_ok=True)
        self.working_copies_dir.mkdir(parents=True, exist_ok=True)
        self.shared_dir.mkdir(parents=True, exist_ok=True)
        self.message_queue_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建共享的 .GameDev 目录
        (self.shared_dir / ".GameDev" / "_ProjectManagement").mkdir(parents=True, exist_ok=True)
    
    def create_working_copy(self, source_dir: str = "rules"):
        """
        创建源文档的工作副本（只读镜像）
        
        复制后设置文件系统只读权限，确保工作副本真正不可修改。
        
        Args:
            source_dir: 源目录名（相对于项目根）
        """
        source = self.project_root / source_dir
        target = self.working_copies_dir / source_dir
        
        if not source.exists():
            raise FileNotFoundError(f"源目录不存在: {source}")
        
        # 如果目标已存在，先恢复可写再删除
        if target.exists():
            self._restore_writable(target)
            shutil.rmtree(target)
        
        # 复制目录
        shutil.copytree(source, target)
        
        # 🔒 设置所有文件为只读（文件系统级别强制保护）
        self._set_readonly_recursive(target)
        
        # 记录创建时间
        meta_file = self.working_copies_dir / f"{source_dir}_meta.json"
        with open(meta_file, 'w', encoding='utf-8') as f:
            json.dump({
                "source": str(source),
                "target": str(target),
                "created_at": datetime.now().isoformat(),
                "status": "readonly",
                "fs_permissions": "read-only enforced"
            }, f, ensure_ascii=False, indent=2)
    
    def _set_readonly_recursive(self, target_dir: Path):
        """递归设置目录下所有文件为只读"""
        for root, dirs, files in os.walk(target_dir):
            for f in files:
                filepath = os.path.join(root, f)
                # 移除写权限，保留读和执行权限
                current = os.stat(filepath).st_mode
                os.chmod(filepath, current & ~stat.S_IWUSR & ~stat.S_IWGRP & ~stat.S_IWOTH)
    
    def _restore_writable(self, target_dir: Path):
        """递归恢复目录下所有文件为可写（用于删除前）"""
        for root, dirs, files in os.walk(target_dir):
            for f in files:
                filepath = os.path.join(root, f)
                current = os.stat(filepath).st_mode
                os.chmod(filepath, current | stat.S_IWUSR)
    
    def create_sandbox(self, config: SandboxConfig) -> Path:
        """
        为Agent创建沙盒目录
        
        Args:
            config: 沙盒配置
            
        Returns:
            沙盒根目录路径
        """
        sandbox_dir = self.sandbox_root / config.agent_id
        
        # 创建标准子目录
        for subdir in self.SANDBOX_DIRS:
            (sandbox_dir / subdir).mkdir(parents=True, exist_ok=True)
        
        # 写入沙盒元数据
        meta = {
            "agent_id": config.agent_id,
            "agent_name": config.agent_name,
            "created_at": datetime.now().isoformat(),
            "read_permissions": config.read_permissions,
            "write_permissions": config.write_permissions,
            "create_permissions": config.create_permissions,
            "status": "active"
        }
        with open(sandbox_dir / "sandbox_meta.json", 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        
        # 注册沙盒
        self._sandboxes[config.agent_id] = config
        
        return sandbox_dir
    
    def destroy_sandbox(self, agent_id: str, preserve_output: bool = True):
        """
        销毁Agent沙盒
        
        Args:
            agent_id: Agent ID
            preserve_output: 是否保留output目录中的产出物
        """
        sandbox_dir = self.sandbox_root / agent_id
        
        if not sandbox_dir.exists():
            return
        
        if preserve_output:
            # 将output目录内容移动到共享区域
            output_dir = sandbox_dir / "output"
            if output_dir.exists():
                shared_output = self.shared_dir / "archived_outputs" / agent_id
                shared_output.mkdir(parents=True, exist_ok=True)
                for item in output_dir.iterdir():
                    dest = shared_output / item.name
                    if item.is_file():
                        shutil.copy2(item, dest)
                    elif item.is_dir():
                        shutil.copytree(item, dest, dirs_exist_ok=True)
        
        # 删除沙盒目录
        shutil.rmtree(sandbox_dir)
        
        # 注销
        self._sandboxes.pop(agent_id, None)
    
    def check_access(self, agent_id: str, file_path: str, 
                     operation: str) -> tuple:
        """
        检查Agent的文件访问权限
        
        Args:
            agent_id: Agent ID
            file_path: 文件路径
            operation: 操作类型 (read/write/create/delete)
            
        Returns:
            (allowed: bool, reason: str)
        """
        config = self._sandboxes.get(agent_id)
        if not config:
            reason = f"Agent {agent_id} 未注册沙盒"
            self._log_operation(agent_id, operation, file_path, False, reason)
            return False, reason
        
        abs_path = Path(file_path).resolve()
        sandbox_dir = (self.sandbox_root / agent_id).resolve()
        
        # 1. 源文档保护检查
        if operation in ("write", "create", "delete"):
            allowed, reason = self.source_guard.check_write(file_path)
            if not allowed:
                self._log_operation(agent_id, operation, file_path, False, reason)
                return False, reason
        
        # 2. 沙盒内操作始终允许
        try:
            abs_path.relative_to(sandbox_dir)
            self._log_operation(agent_id, operation, file_path, True, "沙盒内操作")
            return True, "沙盒内操作"
        except ValueError:
            pass
        
        # 3. 共享只读区域检查
        shared_readonly_dirs = [
            self.working_copies_dir.resolve(),
            (self.shared_dir / ".GameDev" / "_ProjectManagement").resolve(),
        ]
        
        if operation == "read":
            for readonly_dir in shared_readonly_dirs:
                try:
                    abs_path.relative_to(readonly_dir)
                    self._log_operation(agent_id, operation, file_path, True, "共享只读区域")
                    return True, "共享只读区域"
                except ValueError:
                    continue
        
        # 4. 共享写入区域检查（.GameDev 产出物目录）
        shared_gamedev = (self.shared_dir / ".GameDev").resolve()
        if operation in ("write", "create"):
            try:
                abs_path.relative_to(shared_gamedev)
                # 进一步检查Agent的写入权限
                for pattern in config.write_permissions:
                    if self._match_permission_pattern(abs_path, pattern, shared_gamedev):
                        self._log_operation(agent_id, operation, file_path, True, 
                                          f"匹配写入权限: {pattern}")
                        return True, f"匹配写入权限: {pattern}"
                
                reason = f"Agent {agent_id} 无权写入: {file_path}"
                self._log_operation(agent_id, operation, file_path, False, reason)
                return False, reason
            except ValueError:
                pass
        
        # 5. 其他Agent沙盒访问检查（禁止）
        try:
            abs_path.relative_to(self.sandbox_root.resolve())
            reason = f"🔒 禁止跨沙盒访问: Agent {agent_id} 试图{operation} {file_path}"
            self._log_operation(agent_id, operation, file_path, False, reason)
            return False, reason
        except ValueError:
            pass
        
        # 默认拒绝
        reason = f"未授权的文件操作: Agent {agent_id}, {operation} {file_path}"
        self._log_operation(agent_id, operation, file_path, False, reason)
        return False, reason
    
    def _match_permission_pattern(self, file_path: Path, pattern: str, 
                                   base_dir: Path) -> bool:
        """
        路径模式匹配（修复版本）
        
        支持的模式:
        - .GameDev/**/*.md → 匹配 base_dir/.GameDev/ 下任意深度的 .md 文件
        - src/** → 匹配 base_dir/src/ 下的所有文件
        - tests/**/*.cs → 匹配 base_dir/tests/ 下任意深度的 .cs 文件
        """
        try:
            rel_path = file_path.relative_to(base_dir)
            rel_str = str(rel_path).replace("\\", "/")
        except (ValueError, IndexError):
            return False
        
        pattern_clean = pattern.replace("\\", "/")
        
        # 拆分为前缀部分和文件通配部分
        # 例如 ".GameDev/**/*.md" → prefix=".GameDev", suffix="*.md"
        parts = pattern_clean.split("/**/")
        
        if len(parts) == 2:
            prefix = parts[0]    # 如 ".GameDev"
            suffix = parts[1]    # 如 "*.md" 或 "01_策划案.md"
            
            # 1. 检查路径前缀是否匹配
            if not rel_str.startswith(prefix.lstrip("/")):
                return False
            
            # 2. 检查文件名/扩展名后缀是否匹配
            filename = file_path.name
            if suffix.startswith("*"):
                # 通配符后缀匹配，如 "*.md" → 只需检查扩展名
                ext = suffix[1:]  # 如 ".md"
                return filename.endswith(ext)
            else:
                # 精确文件名匹配，如 "01_策划案.md"
                return filename == suffix
        
        elif "/**" in pattern_clean:
            # 模式如 "src/**" → 匹配 src/ 下所有文件
            prefix = pattern_clean.replace("/**", "")
            return rel_str.startswith(prefix.lstrip("/"))
        
        else:
            # 精确路径匹配
            return rel_str == pattern_clean.lstrip("/")
    
    def _log_operation(self, agent_id: str, operation: str, path: str, 
                       allowed: bool, reason: str = ""):
        """记录文件操作"""
        op = FileOperation(
            timestamp=datetime.now().isoformat(),
            agent_id=agent_id,
            operation=operation,
            path=path,
            allowed=allowed,
            reason=reason
        )
        self._operation_log.append(op)
    
    def get_sandbox_path(self, agent_id: str) -> Optional[Path]:
        """获取Agent的沙盒根目录"""
        sandbox_dir = self.sandbox_root / agent_id
        return sandbox_dir if sandbox_dir.exists() else None
    
    def get_sandbox_context_path(self, agent_id: str) -> Optional[Path]:
        """获取Agent的上下文目录"""
        sandbox_dir = self.get_sandbox_path(agent_id)
        return sandbox_dir / "context" if sandbox_dir else None
    
    def get_sandbox_workspace_path(self, agent_id: str) -> Optional[Path]:
        """获取Agent的工作目录"""
        sandbox_dir = self.get_sandbox_path(agent_id)
        return sandbox_dir / "workspace" if sandbox_dir else None
    
    def get_sandbox_output_path(self, agent_id: str) -> Optional[Path]:
        """获取Agent的产出物目录"""
        sandbox_dir = self.get_sandbox_path(agent_id)
        return sandbox_dir / "output" if sandbox_dir else None
    
    def get_shared_gamedev_path(self) -> Path:
        """获取共享的 .GameDev 目录"""
        return self.shared_dir / ".GameDev"
    
    def get_working_copy_path(self, relative_path: str = "") -> Path:
        """获取工作副本路径"""
        return self.working_copies_dir / relative_path
    
    def list_active_sandboxes(self) -> Dict[str, dict]:
        """列出所有活跃沙盒"""
        result = {}
        for agent_id, config in self._sandboxes.items():
            sandbox_dir = self.sandbox_root / agent_id
            meta_file = sandbox_dir / "sandbox_meta.json"
            if meta_file.exists():
                with open(meta_file, 'r', encoding='utf-8') as f:
                    result[agent_id] = json.load(f)
        return result
    
    def get_operation_log(self, agent_id: Optional[str] = None,
                          operation: Optional[str] = None) -> List[dict]:
        """获取操作日志"""
        logs = self._operation_log
        if agent_id:
            logs = [op for op in logs if op.agent_id == agent_id]
        if operation:
            logs = [op for op in logs if op.operation == operation]
        return [
            {
                "timestamp": op.timestamp,
                "agent_id": op.agent_id,
                "operation": op.operation,
                "path": op.path,
                "allowed": op.allowed,
                "reason": op.reason
            }
            for op in logs
        ]
    
    def export_operation_log(self, output_path: str):
        """导出操作日志到文件"""
        logs = self.get_operation_log()
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
    
    def cleanup_all(self):
        """清理所有沙盒（保留共享产出物）"""
        for agent_id in list(self._sandboxes.keys()):
            self.destroy_sandbox(agent_id, preserve_output=True)


class SandboxPermissionError(PermissionError):
    """沙盒权限违规异常"""
    
    def __init__(self, agent_id: str, operation: str, path: str, reason: str):
        self.agent_id = agent_id
        self.operation = operation
        self.path = path
        self.reason = reason
        super().__init__(
            f"🔒 权限违规: Agent [{agent_id}] 尝试 {operation} '{path}' — {reason}"
        )


class SandboxFileProxy:
    """
    沙盒文件代理 — 强制权限检查的文件操作接口
    
    所有Agent的文件读写操作必须通过此代理执行，
    在每次操作前自动调用 SandboxManager.check_access()，
    拒绝则抛出 SandboxPermissionError，杜绝权限绕过。
    
    用法:
        proxy = SandboxFileProxy(sandbox_mgr, agent_id)
        proxy.write_json(filepath, data)    # 自动检查 write 权限
        proxy.write_text(filepath, content) # 自动检查 write 权限
        content = proxy.read_text(filepath) # 自动检查 read 权限
        proxy.delete_file(filepath)         # 自动检查 delete 权限
    """
    
    def __init__(self, sandbox_mgr: SandboxManager, agent_id: str):
        self._sandbox_mgr = sandbox_mgr
        self._agent_id = agent_id
    
    def _enforce(self, file_path: str, operation: str):
        """强制权限检查 — 不通过则抛异常"""
        allowed, reason = self._sandbox_mgr.check_access(
            self._agent_id, file_path, operation
        )
        if not allowed:
            raise SandboxPermissionError(
                self._agent_id, operation, file_path, reason
            )
    
    def write_json(self, file_path, data, *, ensure_ascii=False, indent=2):
        """写入JSON文件（自动权限检查）"""
        path = Path(file_path)
        operation = "create" if not path.exists() else "write"
        self._enforce(str(path.resolve()), operation)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent)
    
    def write_text(self, file_path, content: str):
        """写入文本文件（自动权限检查）"""
        path = Path(file_path)
        operation = "create" if not path.exists() else "write"
        self._enforce(str(path.resolve()), operation)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    
    def read_text(self, file_path) -> str:
        """读取文本文件（自动权限检查）"""
        path = Path(file_path)
        self._enforce(str(path.resolve()), "read")
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def read_json(self, file_path):
        """读取JSON文件（自动权限检查）"""
        content = self.read_text(file_path)
        return json.loads(content)
    
    def delete_file(self, file_path):
        """删除文件（自动权限检查）"""
        path = Path(file_path)
        self._enforce(str(path.resolve()), "delete")
        if path.exists():
            path.unlink()
