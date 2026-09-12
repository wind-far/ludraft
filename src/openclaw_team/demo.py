"""
OpenClaw 系统演示脚本

完整演示:
1. 规则资产扫描与注册
2. 系统初始化（沙盒、消息队列、上下文管理器）
3. 模拟需求处理流程
4. CodeBuddy 隔离验证
5. 生成综合报告
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# 确保项目根目录在路径中
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))


def run_demo(verbose: bool = False):
    """运行完整系统演示"""
    from adapters.rule_loader import RuleLoader
    from adapters.codebuddy_adapter import CodeBuddyAdapter
    from core.orchestrator import Orchestrator
    from core.sandbox import SandboxManager, SandboxConfig
    from core.message_queue import MessageQueue, Message, MessageType, MessagePriority
    from core.context_manager import ContextManager
    from core.pipeline import PipelineEngine, ReqType, ReqScale
    from utils.logger import SystemLogger
    from utils.file_ops import safe_yaml_read, ensure_dir

    project_root = str(PROJECT_ROOT)
    report_lines = []

    def log(msg: str):
        """打印并记录"""
        print(msg)
        report_lines.append(msg)

    log("=" * 70)
    log("🎮 OpenClaw 多智能体游戏开发团队系统 - 完整演示")
    log(f"📅 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log("=" * 70)

    # ── Phase 1: 规则资产扫描 ─────────────────────────────
    log("\n" + "━" * 60)
    log("📦 Phase 1: 规则资产扫描与注册")
    log("━" * 60)

    loader = RuleLoader(str(PROJECT_ROOT / "rules"))
    inventory = loader.scan_all()
    stats = inventory.statistics

    log(f"\n  ✅ 扫描完成!")
    log(f"  • Agent数量:    {stats['total_agents']}")
    log(f"  • 技能包数量:   {stats['total_skills']}")
    log(f"  • 全局规则:     {stats['total_rules']}")
    log(f"  • 步骤文件:     {stats['total_steps']}")
    log(f"  • 模板文件:     {stats['total_templates']}")
    log(f"  • 总文件数:     {stats['total_files']}")

    if verbose:
        log("\n  🤖 Agent详情:")
        for aid, spec in sorted(inventory.agents.items()):
            log(f"    [{aid}] steps={len(spec.steps)} templates={len(spec.templates)}")

    issues = loader.validate_inventory()
    if issues:
        log(f"\n  ⚠️ 发现 {len(issues)} 个问题")
        for issue in issues:
            log(f"    • {issue}")
    else:
        log("  ✅ 所有文件验证通过")

    # ── Phase 2: 系统初始化 ──────────────────────────────
    log("\n" + "━" * 60)
    log("⚙️ Phase 2: 系统初始化")
    log("━" * 60)

    # 读取系统配置
    config = safe_yaml_read(PROJECT_ROOT / "config" / "system.yaml") or {}
    parallel_config = config.get("parallel_architecture", {})

    # 初始化日志系统
    log_root = str(PROJECT_ROOT / ".openclaw-runtime" / "logs")
    sys_logger = SystemLogger(log_root=log_root, console_output=False)
    sys_logger.info("demo", "系统演示开始")

    # 初始化编排器
    orch = Orchestrator(
        project_root=project_root,
        config={
            "sandbox_root": parallel_config.get("sandbox_root", ".sandboxes"),
            "protected_paths": ["rules"],
            "max_parallel_agents": parallel_config.get("max_parallel_agents", 4)
        }
    )
    orch.setup()
    log("  ✅ 编排器初始化完成")
    log("  ✅ 源文档工作副本已创建")

    # 初始化Agent沙盒
    agents_config = config.get("agents", {})
    sandbox_count = 0
    for agent_key, agent_def in agents_config.items():
        if agent_def.get("sandbox", False):
            agent_id = agent_def.get("id", agent_key)
            sc = SandboxConfig(
                agent_id=agent_id,
                agent_name=agent_def.get("name", agent_key),
                sandbox_root=parallel_config.get("sandbox_root", ".sandboxes"),
                read_permissions=["rules/**"],
                write_permissions=[".GameDev/**"]
            )
            orch.sandbox_mgr.create_sandbox(sc)
            sandbox_count += 1

    log(f"  ✅ 已创建 {sandbox_count} 个Agent沙盒")

    # 消息队列统计
    mq_stats = orch.mq.get_queue_stats()
    total_channels = len(mq_stats)
    log(f"  ✅ 消息队列初始化: {total_channels} 个频道")

    # ── Phase 3: CodeBuddy 适配器 ─────────────────────────
    log("\n" + "━" * 60)
    log("🔗 Phase 3: CodeBuddy Team Mode 适配器")
    log("━" * 60)

    adapter = CodeBuddyAdapter(project_root)
    team_config = adapter.initialize(rule_loader=loader)

    log(f"  ✅ 团队名称: {team_config.team_name}")
    log(f"  ✅ 团队成员: {len(team_config.members)} 个")

    for agent_id, member in sorted(team_config.members.items()):
        log(f"    • {member.display_name} [{member.parallel_group}] mode={member.mode}")

    # 导出团队配置
    team_config_path = str(PROJECT_ROOT / ".openclaw-runtime" / "team_config.json")
    adapter.export_config(team_config_path)
    log(f"  ✅ 团队配置已导出: {team_config_path}")

    # ── Phase 4: 模拟需求处理 ────────────────────────────
    log("\n" + "━" * 60)
    log("🎯 Phase 4: 模拟需求处理流程")
    log("━" * 60)

    # 创建流水线
    pipeline_engine = PipelineEngine()

    test_reqs = [
        ("实现玩家背包系统", ReqType.FEATURE, ReqScale.M),
        ("修复角色移动卡顿Bug", ReqType.BUGFIX, ReqScale.S),
        ("优化场景加载性能", ReqType.OPTIMIZE, ReqScale.M),
    ]

    for req_name, req_type, req_scale in test_reqs:
        pipeline = pipeline_engine.create_pipeline(
            req_id=f"REQ-DEMO-{req_type.value[:3]}",
            req_type=req_type,
            req_scale=req_scale,
            req_name=req_name
        )

        step_count = len(pipeline.steps)
        stages = [s.stage for s in pipeline.steps]
        parallel_stages = [s.stage for s in pipeline.steps if s.parallel_with]

        log(f"\n  📋 需求: {req_name}")
        log(f"     类型: {req_type.value} | 规模: {req_scale.value}")
        log(f"     流水线: {pipeline.pipeline_id} | 步骤数: {step_count}")
        log(f"     路径: {' → '.join(stages)}")
        if parallel_stages:
            log(f"     并行阶段: {', '.join(parallel_stages)}")

        # 模拟质量门禁
        for step in pipeline.steps:
            if step.quality_gate:
                gate_results = {item: True for item in
                               PipelineEngine.QUALITY_GATES.get(step.quality_gate, type('', (), {'check_items': []})()).check_items}
                if not gate_results:
                    gate_def = PipelineEngine.QUALITY_GATES.get(step.quality_gate)
                    if gate_def:
                        gate_results = {item: True for item in gate_def.check_items}
                passed = pipeline_engine.check_quality_gate(
                    pipeline.pipeline_id, step.quality_gate, gate_results
                )
                log(f"     🚧 {step.quality_gate}: {'✅ 通过' if passed else '❌ 未通过'}")

    # ── Phase 5: 消息队列演示 ────────────────────────────
    log("\n" + "━" * 60)
    log("📬 Phase 5: 消息队列通信演示")
    log("━" * 60)

    mq = orch.mq

    # 发送流转消息
    msg_id1 = mq.send_handoff(
        from_agent="02_planner",
        to_agent="03_tech_lead",
        req_id="REQ-DEMO-FEA",
        artifacts=["策划案_v1.md", "验收标准.md"],
        message="策划完成，移交主程评审"
    )
    log(f"  ✅ 阶段流转消息: {msg_id1}")

    msg_id2 = mq.send_bug_report(
        from_agent="06_qa",
        to_agent="04_programmer",
        req_id="REQ-DEMO-BUG",
        bug_id="BUG-001",
        severity="P1",
        description="角色移动卡顿"
    )
    log(f"  ✅ Bug报告消息: {msg_id2}")

    msg_id3 = mq.broadcast(
        from_agent="01_pm",
        payload={"event": "sprint_start", "sprint": "Sprint-01"}
    )
    log(f"  ✅ 广播消息: {msg_id3}")

    # 接收消息
    tech_msgs = mq.receive("03_tech_lead")
    log(f"  📥 主程收到 {len(tech_msgs)} 条消息")

    prog_msgs = mq.receive("04_programmer")
    log(f"  📥 程序收到 {len(prog_msgs)} 条消息")

    mq_stats = mq.get_queue_stats()
    log(f"  📊 队列统计: {json.dumps(mq_stats)}")

    # ── Phase 6: 隔离验证 ────────────────────────────────
    log("\n" + "━" * 60)
    log("🔒 Phase 6: 沙盒隔离验证")
    log("━" * 60)

    test_cases = [
        ("02_planner", str(PROJECT_ROOT / "rules" / "test.md"), "write", False),
        ("02_planner",
         str(PROJECT_ROOT / ".sandboxes" / "02_planner" / "workspace" / "plan.md"),
         "write", True),
        ("04_programmer",
         str(PROJECT_ROOT / ".sandboxes" / "02_planner" / "context" / "secret.json"),
         "read", False),
    ]

    for agent_id, path, op, expected in test_cases:
        allowed, reason = orch.sandbox_mgr.check_access(agent_id, path, op)
        status = "✅" if (allowed == expected) else "❌"
        result = "允许" if allowed else "拒绝"
        log(f"  {status} [{agent_id}] {op} → {result}")
        if verbose:
            log(f"     路径: {path}")
            log(f"     原因: {reason}")

    # ── Phase 7: 上下文管理演示 ───────────────────────────
    log("\n" + "━" * 60)
    log("🧠 Phase 7: 上下文管理演示")
    log("━" * 60)

    ctx_mgr = orch.ctx_mgr

    # 为策划Agent创建上下文
    planner_ctx = ctx_mgr.create_context(
        agent_id="02_planner",
        agent_name="策划Agent",
        req_id="REQ-DEMO-FEA",
        req_name="实现玩家背包系统",
        req_type="FEATURE",
        req_scale="M"
    )

    planner_ctx.record_step_start("step-01_知识库加载", mode="EXPLORE")
    planner_ctx.record_step_complete("step-01_知识库加载", artifacts=["knowledge_loaded"])
    planner_ctx.record_step_start("step-02_策划案编写", mode="DESIGN")
    planner_ctx.record_step_complete("step-02_策划案编写",
                                      artifacts=["策划案_v1.md", "验收标准.md"])
    planner_ctx.record_quality_gate("gate_1", True,
                                     {"total_items": 21, "passed_items": 21})

    ctx_path = ctx_mgr.save_context("02_planner")
    summary = planner_ctx.get_progress_summary()

    log(f"  ✅ 上下文已保存: {ctx_path}")
    log(f"  📊 进度: {summary['progress']} ({summary['progress_pct']}%)")
    log(f"  📄 产出物: {summary['artifacts_count']} 个")

    # 模拟跨会话恢复
    ctx_mgr.clear_context("02_planner")
    restored_ctx = ctx_mgr.load_context("02_planner")
    if restored_ctx:
        log(f"  ✅ 跨会话恢复成功: req_id={restored_ctx.req_id}")
    else:
        log("  ⚠️ 上下文恢复未找到文件（沙盒可能未持久化）")

    # ── 生成综合报告 ────────────────────────────────────
    log("\n" + "━" * 60)
    log("📊 系统综合报告")
    log("━" * 60)

    system_status = orch.get_system_status()
    log(f"\n  🤖 注册Agent:     {len(system_status['registered_agents'])}")
    log(f"  📦 活跃沙盒:       {len(system_status['active_sandboxes'])}")
    log(f"  🔧 活跃流水线:     {system_status['active_pipelines']}")
    log(f"  📝 系统日志:       {system_status['log_entries']} 条")

    log("\n" + "=" * 70)
    log("✅ 系统演示完成!")
    log("=" * 70)

    # 保存报告
    report_dir = ensure_dir(PROJECT_ROOT / ".openclaw-runtime" / "reports")
    report_file = report_dir / f"demo_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    report_file.write_text("\n".join(report_lines), encoding='utf-8')
    print(f"\n📄 报告已保存: {report_file}")

    # 清理
    orch.shutdown()
    SystemLogger.reset()


def ensure_dir(dir_path: Path) -> Path:
    """确保目录存在"""
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


if __name__ == "__main__":
    run_demo(verbose="--verbose" in sys.argv or "-v" in sys.argv)
