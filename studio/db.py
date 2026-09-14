import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ACTIVE = ("queued", "running", "waiting_confirmation", "testing")
TERMINAL = ("succeeded", "failed", "cancelled")


def now():
    return datetime.now(timezone.utc).isoformat()


def uid():
    return uuid4().hex


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.con = sqlite3.connect(root / "studio.sqlite3", check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, title TEXT, active_version TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS project_meta(project_id TEXT PRIMARY KEY, display_name TEXT,
          state TEXT NOT NULL DEFAULT 'active', last_opened TEXT);
        CREATE TABLE IF NOT EXISTS run_options(run_id TEXT PRIMARY KEY, kind TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS agent_steps(id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
          task_key TEXT NOT NULL, role TEXT NOT NULL, status TEXT NOT NULL, inputs TEXT NOT NULL,
          output TEXT, model TEXT, usage TEXT, elapsed REAL, error TEXT, created_at TEXT, finished_at TEXT);
        CREATE INDEX IF NOT EXISTS agent_steps_run ON agent_steps(run_id);
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, run_id TEXT NOT NULL,
          sender TEXT NOT NULL, recipient TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
          reply_to TEXT UNIQUE, source_step TEXT, slot INTEGER, created_at TEXT NOT NULL,
          UNIQUE(source_step,slot));
        CREATE INDEX IF NOT EXISTS messages_run ON messages(run_id);
        CREATE TABLE IF NOT EXISTS message_receipts(message_id TEXT NOT NULL, step_id TEXT NOT NULL,
          created_at TEXT NOT NULL, PRIMARY KEY(message_id,step_id));
        CREATE TABLE IF NOT EXISTS role_rule_profiles(role TEXT PRIMARY KEY, revision TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS role_rule_revisions(id TEXT PRIMARY KEY, role TEXT NOT NULL, config TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS custom_skills(id TEXT PRIMARY KEY, revision TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS skill_editions(id TEXT PRIMARY KEY, skill_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rule_snapshots(id TEXT PRIMARY KEY, role TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS step_rules(step_id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS uploads(id TEXT PRIMARY KEY, name TEXT NOT NULL, size INTEGER NOT NULL,
          sha256 TEXT NOT NULL, status TEXT NOT NULL, text TEXT, documents TEXT, warnings TEXT, error TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS run_materials(run_id TEXT NOT NULL, upload_id TEXT NOT NULL, payload TEXT NOT NULL,
          PRIMARY KEY(run_id,upload_id));
        CREATE TABLE IF NOT EXISTS run_reports(run_id TEXT PRIMARY KEY, kind TEXT NOT NULL,
          payload TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, project_id TEXT, status TEXT, requirement TEXT,
          base_version TEXT, plan TEXT, error TEXT, repairs INTEGER DEFAULT 0, created_at TEXT, finished_at TEXT);
        CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY, project_id TEXT, run_id TEXT, title TEXT,
          path TEXT, evidence TEXT, diff TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, role TEXT,
          kind TEXT, payload TEXT, created_at TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_run ON runs(project_id)
          WHERE status IN ('queued','running','waiting_confirmation','testing');
        ''')
        self.con.commit()

    def query(self, sql, params=()):
        with self.lock:
            return [dict(row) for row in self.con.execute(sql, params).fetchall()]

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql, params=()):
        with self.lock, self.con:
            return self.con.execute(sql, params).rowcount

    def event(self, run_id, role, kind, **payload):
        self.execute("INSERT INTO events(run_id,role,kind,payload,created_at) VALUES(?,?,?,?,?)",
                     (run_id, role, kind, json.dumps(payload, ensure_ascii=False), now()))

    def run(self, run_id):
        return self.one("SELECT * FROM runs WHERE id=?", (run_id,))

    def recover(self):
        from .file_transactions import recover_edits
        for journal in (self.root/'candidates').glob('.*.transaction.json'):
            candidate_id=journal.name[1:-len('.transaction.json')]
            if len(candidate_id)!=32 or any(c not in '0123456789abcdef' for c in candidate_id):
                continue
            try:
                recover_edits(self.root/'candidates'/candidate_id)
                self.event(candidate_id,'system','files_recovered',message='已恢复中断的文件事务；不代表游戏验证通过')
            except (ValueError,OSError):
                self.event(candidate_id,'system','file_recovery_failed',message='文件事务恢复失败，保留原始数据待检查')
        self.execute("UPDATE uploads SET status='failed',error='服务重启中断解析，请重新上传' WHERE status='processing'")
        self.execute("UPDATE agent_steps SET status='failed',error='服务重启中断步骤',finished_at=? WHERE status='running'", (now(),))
        # Approval waits are durable; interrupted work must never be reported as success.
        for run in self.query("SELECT * FROM runs WHERE status IN ('queued','running','testing')"):
            self.execute("UPDATE runs SET status='failed',error=?,finished_at=? WHERE id=?",
                         ("服务重启中断了执行，请重新提交；上一可玩版本已保留。", now(), run['id']))
            self.event(run['id'], 'system', 'interrupted', message='服务重启，执行已中断')
