"""
OpenClaw 数据库层 — SQLite 持久化

设计原则:
- 零外部依赖: 仅用 Python 标准库 sqlite3
- 服务重启不丢数据: Pipeline / Step / 上传文件 / 日志全部持久化
- 简单高效: 单文件 SQLite，适合本地 AI 开发工具场景
- 向后兼容: 现有 PipelineEngine 内存逻辑保持不变，DB 层作为镜像同步
"""

import sqlite3
import json
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any


# 数据库文件路径（项目根目录下）
_DB_PATH: Optional[Path] = None
_lock = threading.Lock()


def init_db(db_path: Path):
    """初始化数据库（创建表结构）"""
    global _DB_PATH
    _DB_PATH = db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with _connect() as conn:
        conn.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;

        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        -- 流水线实例表
        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        CREATE TABLE IF NOT EXISTS pipelines (
            pipeline_id     TEXT PRIMARY KEY,
            req_id          TEXT NOT NULL,
            req_type        TEXT NOT NULL,
            req_scale       TEXT NOT NULL DEFAULT 'M',
            req_name        TEXT NOT NULL DEFAULT '',
            status          TEXT NOT NULL DEFAULT 'created',
            -- created / running / paused / completed / failed
            current_step_index  INTEGER NOT NULL DEFAULT 0,
            bug_rounds      INTEGER NOT NULL DEFAULT 0,
            max_bug_rounds  INTEGER NOT NULL DEFAULT 3,
            user_input      TEXT,           -- 原始用户输入（含文件提取文本）
            created_at      TEXT NOT NULL,
            started_at      TEXT,
            completed_at    TEXT,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        -- 流水线步骤表（每个 Pipeline 的阶段列表）
        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        CREATE TABLE IF NOT EXISTS pipeline_steps (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_id     TEXT NOT NULL REFERENCES pipelines(pipeline_id) ON DELETE CASCADE,
            step_index      INTEGER NOT NULL,
            stage           TEXT NOT NULL,
            agent_id        TEXT NOT NULL,
            execution       TEXT NOT NULL DEFAULT 'sequential',
            parallel_with   TEXT NOT NULL DEFAULT '[]',  -- JSON array
            quality_gate    TEXT,
            optional        INTEGER NOT NULL DEFAULT 0,  -- 0/1 bool
            status          TEXT NOT NULL DEFAULT 'pending',
            -- pending / running / completed / failed / skipped
            started_at      TEXT,
            completed_at    TEXT,
            output_summary  TEXT,           -- Agent 输出摘要
            UNIQUE(pipeline_id, step_index)
        );

        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        -- 上传文件记录表
        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_id     TEXT REFERENCES pipelines(pipeline_id) ON DELETE SET NULL,
            filename        TEXT NOT NULL,
            original_path   TEXT,           -- 服务器保存路径
            file_size       INTEGER NOT NULL DEFAULT 0,
            mime_type       TEXT,
            extracted_text  TEXT,           -- 提取的文本内容
            text_length     INTEGER NOT NULL DEFAULT 0,
            upload_status   TEXT NOT NULL DEFAULT 'ok',  -- ok / error
            error_msg       TEXT,
            uploaded_at     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        -- 活动日志表（每个 Pipeline 的操作历史）
        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        CREATE TABLE IF NOT EXISTS activity_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_id     TEXT REFERENCES pipelines(pipeline_id) ON DELETE CASCADE,
            event_type      TEXT NOT NULL,
            message         TEXT NOT NULL,
            level           TEXT NOT NULL DEFAULT 'info',  -- info / warning / error
            agent_id        TEXT,
            extra_data      TEXT,           -- JSON blob
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        -- Agent 上下文快照表（用于恢复工作状态）
        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        CREATE TABLE IF NOT EXISTS agent_context_snapshots (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_id     TEXT NOT NULL REFERENCES pipelines(pipeline_id) ON DELETE CASCADE,
            agent_id        TEXT NOT NULL,
            snapshot_type   TEXT NOT NULL DEFAULT 'checkpoint',  -- checkpoint / final
            context_json    TEXT NOT NULL DEFAULT '{}',
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );

        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        -- 消息队列持久化表（防止重启丢失未处理消息）
        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        CREATE TABLE IF NOT EXISTS message_queue (
            msg_id          TEXT PRIMARY KEY,
            pipeline_id     TEXT REFERENCES pipelines(pipeline_id) ON DELETE CASCADE,
            from_agent      TEXT NOT NULL,
            to_agent        TEXT NOT NULL,
            msg_type        TEXT NOT NULL DEFAULT 'handoff',
            priority        TEXT NOT NULL DEFAULT 'normal',
            payload         TEXT NOT NULL DEFAULT '{}',  -- JSON
            status          TEXT NOT NULL DEFAULT 'pending',
            -- pending / delivered / consumed / failed
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            delivered_at    TEXT,
            consumed_at     TEXT
        );

        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        -- 索引
        -- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        CREATE INDEX IF NOT EXISTS idx_pipelines_status   ON pipelines(status);
        CREATE INDEX IF NOT EXISTS idx_pipelines_created  ON pipelines(created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_steps_pipeline     ON pipeline_steps(pipeline_id, step_index);
        CREATE INDEX IF NOT EXISTS idx_logs_pipeline      ON activity_logs(pipeline_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_logs_type          ON activity_logs(event_type);
        CREATE INDEX IF NOT EXISTS idx_files_pipeline     ON uploaded_files(pipeline_id);
        CREATE INDEX IF NOT EXISTS idx_mq_status          ON message_queue(status, to_agent);
        CREATE INDEX IF NOT EXISTS idx_mq_pipeline        ON message_queue(pipeline_id);
        """)


def _connect() -> sqlite3.Connection:
    """获取带行工厂的连接"""
    if _DB_PATH is None:
        raise RuntimeError("数据库未初始化，请先调用 init_db()")
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pipeline CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def save_pipeline(pipeline_dict: dict, user_input: str = ""):
    """插入或更新一条 Pipeline 记录"""
    with _lock, _connect() as conn:
        conn.execute("""
            INSERT INTO pipelines
                (pipeline_id, req_id, req_type, req_scale, req_name,
                 status, current_step_index, bug_rounds, max_bug_rounds,
                 user_input, created_at, started_at, completed_at, updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(pipeline_id) DO UPDATE SET
                status              = excluded.status,
                current_step_index  = excluded.current_step_index,
                bug_rounds          = excluded.bug_rounds,
                req_name            = excluded.req_name,
                started_at          = excluded.started_at,
                completed_at        = excluded.completed_at,
                updated_at          = excluded.updated_at
        """, (
            pipeline_dict["pipeline_id"],
            pipeline_dict.get("req_id", ""),
            pipeline_dict.get("req_type", "FEATURE"),
            pipeline_dict.get("req_scale", "M"),
            pipeline_dict.get("req_name", ""),
            pipeline_dict.get("status", "created"),
            pipeline_dict.get("current_step_index", 0),
            pipeline_dict.get("bug_rounds", 0),
            pipeline_dict.get("max_bug_rounds", 3),
            user_input,
            pipeline_dict.get("created_at") or datetime.now().isoformat(),
            pipeline_dict.get("started_at"),
            pipeline_dict.get("completed_at"),
            datetime.now().isoformat(),
        ))

        # 同步步骤列表
        steps = pipeline_dict.get("steps") or pipeline_dict.get("stages") or []
        for i, step in enumerate(steps):
            conn.execute("""
                INSERT INTO pipeline_steps
                    (pipeline_id, step_index, stage, agent_id, execution,
                     parallel_with, quality_gate, optional, status)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(pipeline_id, step_index) DO UPDATE SET
                    status       = excluded.status,
                    started_at   = excluded.started_at,
                    completed_at = excluded.completed_at
            """, (
                pipeline_dict["pipeline_id"],
                i,
                step.get("stage", step.get("name", "")),
                step.get("agent_id", ""),
                step.get("execution", "sequential"),
                json.dumps(step.get("parallel_with", [])),
                step.get("quality_gate"),
                1 if step.get("optional") else 0,
                step.get("status", "pending"),
            ))


def load_all_pipelines() -> List[dict]:
    """加载所有 Pipeline（含 steps），用于服务启动时恢复内存状态"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM pipelines ORDER BY created_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            p = dict(row)
            steps = conn.execute(
                "SELECT * FROM pipeline_steps WHERE pipeline_id=? ORDER BY step_index",
                (p["pipeline_id"],)
            ).fetchall()
            p["steps"] = [_step_row_to_dict(s) for s in steps]
            p["stages"] = p["steps"]
            result.append(p)
        return result


def load_pipeline(pipeline_id: str) -> Optional[dict]:
    """加载单条 Pipeline"""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM pipelines WHERE pipeline_id=?", (pipeline_id,)
        ).fetchone()
        if not row:
            return None
        p = dict(row)
        steps = conn.execute(
            "SELECT * FROM pipeline_steps WHERE pipeline_id=? ORDER BY step_index",
            (pipeline_id,)
        ).fetchall()
        p["steps"] = [_step_row_to_dict(s) for s in steps]
        p["stages"] = p["steps"]
        return p


def delete_pipeline_db(pipeline_id: str) -> bool:
    """删除 Pipeline 及其关联数据（ON DELETE CASCADE 自动清理 steps/logs/files）"""
    with _lock, _connect() as conn:
        cur = conn.execute(
            "DELETE FROM pipelines WHERE pipeline_id=?", (pipeline_id,)
        )
        return cur.rowcount > 0


def update_pipeline_status(pipeline_id: str, status: str,
                            started_at: str = None, completed_at: str = None):
    """快速更新 Pipeline 状态"""
    with _lock, _connect() as conn:
        conn.execute("""
            UPDATE pipelines SET
                status       = ?,
                started_at   = COALESCE(?, started_at),
                completed_at = COALESCE(?, completed_at),
                updated_at   = ?
            WHERE pipeline_id = ?
        """, (status, started_at, completed_at, datetime.now().isoformat(), pipeline_id))


def update_step_status(pipeline_id: str, step_index: int, status: str,
                       output_summary: str = None):
    """更新某个步骤的状态"""
    now = datetime.now().isoformat()
    with _lock, _connect() as conn:
        conn.execute("""
            UPDATE pipeline_steps SET
                status          = ?,
                started_at      = CASE WHEN ? = 'running' AND started_at IS NULL THEN ? ELSE started_at END,
                completed_at    = CASE WHEN ? IN ('completed','failed','skipped') THEN ? ELSE completed_at END,
                output_summary  = COALESCE(?, output_summary)
            WHERE pipeline_id = ? AND step_index = ?
        """, (status, status, now, status, now, output_summary, pipeline_id, step_index))


def rename_pipeline_db(pipeline_id: str, new_name: str):
    """重命名 Pipeline"""
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE pipelines SET req_name=?, updated_at=? WHERE pipeline_id=?",
            (new_name, datetime.now().isoformat(), pipeline_id)
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 上传文件 CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def save_uploaded_file(pipeline_id: Optional[str], filename: str, original_path: str,
                       file_size: int, mime_type: str = None,
                       extracted_text: str = "", upload_status: str = "ok",
                       error_msg: str = None) -> int:
    """记录上传文件信息，返回插入的 id"""
    with _lock, _connect() as conn:
        cur = conn.execute("""
            INSERT INTO uploaded_files
                (pipeline_id, filename, original_path, file_size, mime_type,
                 extracted_text, text_length, upload_status, error_msg)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            pipeline_id, filename, original_path, file_size, mime_type,
            extracted_text, len(extracted_text or ""), upload_status, error_msg
        ))
        return cur.lastrowid


def get_pipeline_files(pipeline_id: str) -> List[dict]:
    """获取某条 Pipeline 关联的所有上传文件"""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM uploaded_files WHERE pipeline_id=? ORDER BY uploaded_at",
            (pipeline_id,)
        ).fetchall()
        return [dict(r) for r in rows]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 活动日志 CRUD
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def log_event(event_type: str, message: str, pipeline_id: str = None,
              agent_id: str = None, level: str = "info", extra: dict = None):
    """写入活动日志"""
    with _lock, _connect() as conn:
        conn.execute("""
            INSERT INTO activity_logs
                (pipeline_id, event_type, message, level, agent_id, extra_data)
            VALUES (?,?,?,?,?,?)
        """, (
            pipeline_id, event_type, message, level, agent_id,
            json.dumps(extra) if extra else None
        ))


def get_logs(pipeline_id: str = None, limit: int = 100,
             event_type: str = None) -> List[dict]:
    """查询日志"""
    with _connect() as conn:
        clauses, params = [], []
        if pipeline_id:
            clauses.append("pipeline_id = ?"); params.append(pipeline_id)
        if event_type:
            clauses.append("event_type = ?"); params.append(event_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM activity_logs {where} ORDER BY created_at DESC LIMIT ?",
            params
        ).fetchall()
        return [dict(r) for r in rows]


def delete_pipeline_logs(pipeline_id: str):
    """删除某条 Pipeline 的所有日志"""
    with _lock, _connect() as conn:
        conn.execute(
            "DELETE FROM activity_logs WHERE pipeline_id=?", (pipeline_id,)
        )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agent 上下文快照
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def save_agent_snapshot(pipeline_id: str, agent_id: str, context: dict,
                        snapshot_type: str = "checkpoint"):
    """保存 Agent 上下文快照"""
    with _lock, _connect() as conn:
        conn.execute("""
            INSERT INTO agent_context_snapshots
                (pipeline_id, agent_id, snapshot_type, context_json)
            VALUES (?,?,?,?)
        """, (pipeline_id, agent_id, snapshot_type, json.dumps(context, ensure_ascii=False)))


def get_latest_agent_snapshot(pipeline_id: str, agent_id: str) -> Optional[dict]:
    """获取某 Agent 最新快照"""
    with _connect() as conn:
        row = conn.execute("""
            SELECT context_json FROM agent_context_snapshots
            WHERE pipeline_id=? AND agent_id=?
            ORDER BY created_at DESC LIMIT 1
        """, (pipeline_id, agent_id)).fetchone()
        if row:
            try:
                return json.loads(row["context_json"])
            except Exception:
                return None
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 消息队列持久化
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def persist_message(msg_id: str, pipeline_id: str, from_agent: str,
                    to_agent: str, msg_type: str, priority: str, payload: dict):
    """将消息写入持久化队列"""
    with _lock, _connect() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO message_queue
                (msg_id, pipeline_id, from_agent, to_agent, msg_type, priority, payload)
            VALUES (?,?,?,?,?,?,?)
        """, (msg_id, pipeline_id, from_agent, to_agent, msg_type, priority,
              json.dumps(payload, ensure_ascii=False)))


def mark_message_consumed(msg_id: str):
    """标记消息已消费"""
    with _lock, _connect() as conn:
        conn.execute(
            "UPDATE message_queue SET status='consumed', consumed_at=? WHERE msg_id=?",
            (datetime.now().isoformat(), msg_id)
        )


def get_pending_messages(to_agent: str, pipeline_id: str = None) -> List[dict]:
    """获取未消费消息"""
    with _connect() as conn:
        if pipeline_id:
            rows = conn.execute("""
                SELECT * FROM message_queue
                WHERE to_agent=? AND pipeline_id=? AND status='pending'
                ORDER BY created_at
            """, (to_agent, pipeline_id)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM message_queue
                WHERE to_agent=? AND status='pending'
                ORDER BY created_at
            """, (to_agent,)).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d["payload"])
            except Exception:
                pass
            result.append(d)
        return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 统计查询
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_stats() -> dict:
    """获取系统统计数据"""
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM pipelines").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM pipelines GROUP BY status"
        ).fetchall()
        files_count = conn.execute("SELECT COUNT(*) FROM uploaded_files").fetchone()[0]
        logs_count = conn.execute("SELECT COUNT(*) FROM activity_logs").fetchone()[0]
        return {
            "total_pipelines": total,
            "by_status": {r["status"]: r["cnt"] for r in by_status},
            "total_uploaded_files": files_count,
            "total_logs": logs_count,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 内部工具
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _step_row_to_dict(row) -> dict:
    d = dict(row)
    try:
        d["parallel_with"] = json.loads(d.get("parallel_with", "[]"))
    except Exception:
        d["parallel_with"] = []
    d["optional"] = bool(d.get("optional", 0))
    d["name"] = d.get("stage", "")  # 前端兼容字段
    return d
