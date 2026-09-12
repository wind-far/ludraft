"""
OpenClaw 端到端集成测试

验证项目:
1. 规则加载器 - 扫描/解析/验证
2. 文件操作工具 - 安全读写/路径验证
3. 日志系统 - Agent日志/系统日志
4. 沙盒隔离 - 权限控制/源文档保护
5. 消息队列 - 发送/接收/消费
6. 上下文管理 - 创建/保存/恢复
7. 流水线引擎 - 创建/推进/质量门禁
8. 编排器 - 需求分析/流水线调度
9. CodeBuddy适配器 - 团队映射
"""

import sys
import json
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# 确保src目录在路径中
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

passed = 0
failed = 0
errors = []


def test(name: str, func):
    """执行单个测试"""
    global passed, failed
    try:
        func()
        passed += 1
        print(f"  ✅ {name}")
    except Exception as e:
        failed += 1
        errors.append((name, str(e)))
        print(f"  ❌ {name}: {e}")


def assert_eq(actual, expected, msg=""):
    if actual != expected:
        raise AssertionError(f"{msg}: expected {expected}, got {actual}")


def assert_true(cond, msg=""):
    if not cond:
        raise AssertionError(f"Assertion failed: {msg}")


def assert_gt(a, b, msg=""):
    if not a > b:
        raise AssertionError(f"{msg}: {a} <= {b}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("=" * 70)
print("🧪 OpenClaw 端到端集成测试")
print(f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 70)

# ── Test 1: 文件操作工具 ─────────────────────────────────
print("\n📁 Test 1: 文件操作工具")
from utils.file_ops import (
    safe_read, safe_write, safe_json_read, safe_json_write,
    resolve_path, is_path_within, parse_frontmatter,
    extract_title, scan_directory, ensure_dir, count_files
)

test("safe_read 读取存在的文件",
     lambda: assert_true(safe_read(str(PROJECT_ROOT / "README.md")) is not None))

test("safe_read 读取不存在的文件返回None",
     lambda: assert_eq(safe_read("/nonexistent/file.txt"), None))

# 临时文件测试
tmp_dir = Path(tempfile.mkdtemp())
try:
    test("safe_write 写入文件",
         lambda: assert_true(safe_write(str(tmp_dir / "test.txt"), "hello")))

    test("safe_json_write/read 往返测试", lambda: (
        assert_true(safe_json_write(str(tmp_dir / "test.json"), {"key": "value"})),
        assert_eq(safe_json_read(str(tmp_dir / "test.json")), {"key": "value"})
    ))

    test("resolve_path 规范化路径",
         lambda: assert_true(resolve_path("test", "/base").is_absolute()))

    test("is_path_within 路径包含检查",
         lambda: (
             assert_true(is_path_within(str(tmp_dir / "sub" / "file.txt"), str(tmp_dir))),
             assert_true(not is_path_within("/other/path", str(tmp_dir)))
         ))

    test("parse_frontmatter 解析YAML头", lambda: (
        assert_eq(
            parse_frontmatter("---\ntitle: test\n---\nbody")[0],
            {"title": "test"}
        )
    ))

    test("extract_title 提取Markdown标题",
         lambda: assert_eq(extract_title("# Hello World\ncontent"), "Hello World"))

    test("scan_directory 扫描rules目录",
         lambda: assert_gt(len(scan_directory(str(PROJECT_ROOT / "rules"), "*.md")), 0,
                           "rules下应有md文件"))

    test("count_files 统计文件",
         lambda: assert_gt(count_files(str(PROJECT_ROOT / "rules")).get(".md", 0), 0,
                           "rules下应有md文件"))
finally:
    shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Test 2: 日志系统 ─────────────────────────────────────
print("\n📝 Test 2: 日志系统")
from utils.logger import AgentLogger, SystemLogger, LogEntry

log_tmp = Path(tempfile.mkdtemp())
try:
    test("AgentLogger 创建和写入", lambda: (
        (logger := AgentLogger("test_agent", "测试Agent", str(log_tmp / "test"))),
        logger.info("test_event", "测试消息"),
        logger.warning("warn_event", "警告消息"),
        assert_eq(len(logger.get_recent_logs()), 2)
    ))

    test("AgentLogger 统计",
         lambda: assert_gt(AgentLogger("test2", "T2", str(log_tmp / "t2"), level="DEBUG").get_stats().get("total", -1), -1))

    test("LogEntry 序列化", lambda: (
        (entry := LogEntry(level="INFO", agent_id="test", event="e", message="m")),
        assert_true('"level"' in entry.to_json())
    ))

    SystemLogger.reset()
    test("SystemLogger 单例模式", lambda: (
        (sl1 := SystemLogger(str(log_tmp / "sys"))),
        (sl2 := SystemLogger()),
        assert_true(sl1 is sl2)
    ))
    SystemLogger.reset()
finally:
    shutil.rmtree(log_tmp, ignore_errors=True)


# ── Test 3: 规则加载器 ──────────────────────────────────
print("\n📦 Test 3: 规则加载器")
from adapters.rule_loader import RuleLoader, RuleInventory

loader = RuleLoader(str(PROJECT_ROOT / "rules"))
inventory = loader.scan_all()

test("扫描返回RuleInventory",
     lambda: assert_true(isinstance(inventory, RuleInventory)))

test("检测到Agent入口文件",
     lambda: assert_gt(len(inventory.agents), 0, "应发现Agent"))

test("检测到Agent数量为8",
     lambda: assert_eq(len(inventory.agents), 8))

test("检测到全局规则",
     lambda: assert_gt(len(inventory.rules), 0, "应发现全局规则"))

test("统计数据完整", lambda: (
    assert_gt(inventory.statistics["total_agents"], 0),
    assert_gt(inventory.statistics["total_files"], 0)
))

test("get_summary_text 可读摘要",
     lambda: assert_true("Agent数量" in inventory.get_summary_text()))

test("validate_inventory 验证通过",
     lambda: assert_eq(len(loader.validate_inventory()), 0, "不应有验证问题"))

test("get_agent_spec 获取Agent信息",
     lambda: assert_true(loader.get_agent_spec("02_策划Agent") is not None))

test("load_agent_entry_content 读取入口文件",
     lambda: assert_true(loader.load_agent_entry_content("02_策划Agent") is not None))


# ── Test 4: 沙盒隔离 ─────────────────────────────────────
print("\n🔒 Test 4: 沙盒隔离")
from core.sandbox import SandboxManager, SandboxConfig

sandbox_tmp = Path(tempfile.mkdtemp())
try:
    mgr = SandboxManager(str(sandbox_tmp), "_sandboxes", ["rules"])

    # 创建模拟的 rules 目录
    (sandbox_tmp / "rules").mkdir(exist_ok=True)
    (sandbox_tmp / "rules" / "test.md").write_text("protected")

    config = SandboxConfig(
        agent_id="test_agent",
        agent_name="测试Agent",
        sandbox_root="_sandboxes"
    )

    sandbox_path = mgr.create_sandbox(config)
    test("创建沙盒",
         lambda: assert_true(sandbox_path.exists()))

    test("沙盒标准目录存在", lambda: (
        assert_true((sandbox_path / "context").exists()),
        assert_true((sandbox_path / "workspace").exists()),
        assert_true((sandbox_path / "output").exists()),
    ))

    test("源文档写入被阻止", lambda: (
        assert_eq(
            mgr.check_access("test_agent",
                              str(sandbox_tmp / "rules" / "test.md"), "write")[0],
            False, "rules下写入应被拒"
        )
    ))

    test("沙盒内写入允许", lambda: (
        assert_eq(
            mgr.check_access("test_agent",
                              str(sandbox_path / "workspace" / "file.txt"), "write")[0],
            True, "沙盒内写入应允许"
        )
    ))

    test("跨沙盒访问被阻止", lambda: (
        mgr.create_sandbox(SandboxConfig(
            agent_id="other_agent", agent_name="其他",
            sandbox_root="_sandboxes"
        )),
        assert_eq(
            mgr.check_access("test_agent",
                              str(sandbox_tmp / "_sandboxes" / "other_agent" / "context" / "f.json"),
                              "read")[0],
            False, "跨沙盒读取应被拒"
        )
    ))

    test("操作日志记录",
         lambda: assert_gt(len(mgr.get_operation_log()), 0))

    mgr.cleanup_all()
    test("清理所有沙盒",
         lambda: assert_eq(len(mgr.list_active_sandboxes()), 0))
finally:
    shutil.rmtree(sandbox_tmp, ignore_errors=True)


# ── Test 5: 消息队列 ─────────────────────────────────────
print("\n📬 Test 5: 消息队列")
from core.message_queue import MessageQueue, Message, MessageType, MessagePriority

mq_tmp = Path(tempfile.mkdtemp())
try:
    mq = MessageQueue(str(mq_tmp / "mq"))

    test("发送流转消息", lambda: (
        (mid := mq.send_handoff("02_planner", "03_tech_lead", "REQ-001",
                                 ["doc.md"], True)),
        assert_true(mid.startswith("MSG-"))
    ))

    test("发送Bug报告", lambda: (
        (mid := mq.send_bug_report("06_qa", "04_programmer", "REQ-001",
                                     "BUG-001", "P1", "Test bug")),
        assert_true(mid.startswith("MSG-"))
    ))

    test("发送广播", lambda: (
        (mid := mq.broadcast("01_pm", {"event": "sprint_start"})),
        assert_true(mid.startswith("MSG-"))
    ))

    test("接收消息",
         lambda: assert_gt(len(mq.receive("03_tech_lead")), 0, "主程应收到消息"))

    test("队列统计",
         lambda: assert_gt(sum(mq.get_queue_stats().values()), 0))

    mq.clear_all()
    test("清空队列",
         lambda: assert_eq(sum(mq.get_queue_stats().values()), 0))
finally:
    shutil.rmtree(mq_tmp, ignore_errors=True)


# ── Test 6: 上下文管理 ───────────────────────────────────
print("\n🧠 Test 6: 上下文管理")
from core.context_manager import ContextManager, AgentContext

ctx_tmp = Path(tempfile.mkdtemp())
try:
    ctx_mgr = ContextManager(str(ctx_tmp / "sandboxes"), str(ctx_tmp / "rules"))

    test("创建上下文", lambda: (
        (ctx := ctx_mgr.create_context("02_planner", "策划Agent",
                                         req_id="REQ-001", req_type="FEATURE")),
        assert_true(isinstance(ctx, AgentContext)),
        assert_eq(ctx.agent_id, "02_planner")
    ))

    test("记录步骤", lambda: (
        ctx_mgr.get_context("02_planner").record_step_start("step-01", "EXPLORE"),
        ctx_mgr.get_context("02_planner").record_step_complete("step-01", ["out.md"]),
        assert_eq(len(ctx_mgr.get_context("02_planner").step_history), 1)
    ))

    test("记录质量门禁", lambda: (
        ctx_mgr.get_context("02_planner").record_quality_gate("gate_1", True),
        assert_true(ctx_mgr.get_context("02_planner").quality_gates["gate_1"]["passed"])
    ))

    # 保存和恢复
    (ctx_tmp / "sandboxes" / "02_planner" / "context").mkdir(parents=True, exist_ok=True)
    test("保存上下文",
         lambda: assert_true(ctx_mgr.save_context("02_planner").endswith(".json")))

    ctx_mgr.clear_context("02_planner")
    test("恢复上下文", lambda: (
        (restored := ctx_mgr.load_context("02_planner")),
        assert_true(restored is not None),
        assert_eq(restored.req_id, "REQ-001")
    ))

    test("进度摘要",
         lambda: assert_true("progress" in ctx_mgr.get_context("02_planner").get_progress_summary()))
finally:
    shutil.rmtree(ctx_tmp, ignore_errors=True)


# ── Test 7: 流水线引擎 ───────────────────────────────────
print("\n🔧 Test 7: 流水线引擎")
from core.pipeline import PipelineEngine, PipelineInstance, ReqType, ReqScale

pe = PipelineEngine()

test("创建FEATURE流水线", lambda: (
    (pl := pe.create_pipeline("REQ-001", ReqType.FEATURE, ReqScale.M, "测试功能")),
    assert_true(isinstance(pl, PipelineInstance)),
    assert_gt(len(pl.steps), 0)
))

test("创建BUGFIX流水线", lambda: (
    (pl := pe.create_pipeline("REQ-002", ReqType.BUGFIX, ReqScale.S, "修复Bug")),
    assert_gt(len(pl.steps), 0)
))

test("9种需求类型全覆盖", lambda: (
    assert_eq(len(PipelineEngine.PIPELINE_DEFINITIONS), 9)
))

test("3个质量门禁定义", lambda: (
    assert_eq(len(PipelineEngine.QUALITY_GATES), 3)
))

test("质量门禁检查", lambda: (
    (pl := pe.create_pipeline("REQ-003", ReqType.FEATURE, ReqScale.M)),
    assert_true(pe.check_quality_gate(
        pl.pipeline_id, "gate_1", {"check1": True, "check2": True}
    ))
))

test("Bug流转最大3轮", lambda: (
    (pl := pe.create_pipeline("REQ-004", ReqType.FEATURE, ReqScale.M)),
    pe.handle_bug_flow(pl.pipeline_id),
    pe.handle_bug_flow(pl.pipeline_id),
    pe.handle_bug_flow(pl.pipeline_id),
    assert_eq(pe.handle_bug_flow(pl.pipeline_id), None, "第4轮应为None")
))

test("L规模启用并行", lambda: (
    (pl := pe.create_pipeline("REQ-005", ReqType.FEATURE, ReqScale.L)),
    assert_true(any(s.execution == "parallel" for s in pl.steps))
))


# ── Test 8: 编排器 ───────────────────────────────────────
print("\n⚙️ Test 8: 编排器")
from core.orchestrator import Orchestrator, RequirementAnalysis

orch_tmp = Path(tempfile.mkdtemp())
try:
    (orch_tmp / "rules").mkdir()
    (orch_tmp / "rules" / "rule.md").write_text("# Test Rule")

    orch = Orchestrator(str(orch_tmp), {
        "sandbox_root": "_sandboxes",
        "protected_paths": ["rules"]
    })

    test("编排器初始化", lambda: assert_true(orch is not None))

    test("/gd:命令解析", lambda: (
        (ra := orch._parse_gd_command("/gd:feature 实现背包系统")),
        assert_eq(ra.req_type, "FEATURE"),
        assert_true("背包系统" in ra.req_name)
    ))

    test("自然语言分析 - Bug", lambda: (
        (ra := orch._analyze_natural_language("修复角色移动Bug")),
        assert_eq(ra.req_type, "BUGFIX")
    ))

    test("自然语言分析 - 优化", lambda: (
        (ra := orch._analyze_natural_language("优化场景加载性能")),
        assert_eq(ra.req_type, "OPTIMIZE")
    ))

    test("规模评估 - XL", lambda: (
        (ra := orch._analyze_natural_language("全新的系统架构设计")),
        assert_eq(ra.req_scale, "XL")
    ))

    test("系统状态查询", lambda: (
        (status := orch.get_system_status()),
        assert_true("active_pipelines" in status)
    ))

    orch.shutdown()
finally:
    shutil.rmtree(orch_tmp, ignore_errors=True)


# ── Test 9: CodeBuddy适配器 ──────────────────────────────
print("\n🔗 Test 9: CodeBuddy适配器")
from adapters.codebuddy_adapter import CodeBuddyAdapter

adapter = CodeBuddyAdapter(str(PROJECT_ROOT))
team_config = adapter.initialize()

test("团队配置初始化",
     lambda: assert_eq(len(team_config.members), 8))

test("团队名称", lambda: assert_eq(team_config.team_name, "openclaw-gamedev"))

test("团队创建参数", lambda: (
    (params := adapter.generate_team_create_params()),
    assert_true("team_name" in params)
))

test("Agent spawn参数", lambda: (
    (params := adapter.generate_spawn_params("02_策划Agent", "执行策划任务")),
    assert_true("name" in params),
    assert_true("prompt" in params)
))

test("消息参数生成", lambda: (
    (params := adapter.generate_message_params(
        "02_策划Agent", "03_主程Agent", "策划完成", "策划流转"
    )),
    assert_true("type" in params)
))

test("并行组定义完整",
     lambda: assert_eq(len(CodeBuddyAdapter.PARALLEL_GROUPS), 5))

test("团队状态查询", lambda: (
    (status := adapter.get_team_status()),
    assert_eq(status["member_count"], 8)
))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 测试报告
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
print("\n" + "=" * 70)
print(f"📊 测试结果: ✅ {passed} 通过 | ❌ {failed} 失败 | 共 {passed + failed} 项")
print("=" * 70)

if errors:
    print("\n❌ 失败详情:")
    for name, err in errors:
        print(f"  • {name}: {err}")

if failed == 0:
    print("\n🎉 所有测试通过！系统验证完成。")
else:
    print(f"\n⚠️ 有 {failed} 项测试失败，请检查。")

sys.exit(0 if failed == 0 else 1)
