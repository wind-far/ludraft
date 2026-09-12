"""
OpenClaw 多智能体游戏开发团队系统 - CLI 入口

提供命令行接口:
- inventory: 扫描规则目录并输出资产清单
- status: 查看系统状态
- demo: 运行演示流程
- verify: 验证系统隔离机制
- web: 启动Web仪表盘
"""

import argparse
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# 确保项目根目录在路径中
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))


def get_project_root() -> Path:
    """获取项目根目录"""
    return PROJECT_ROOT


def cmd_inventory(args):
    """执行规则资产清单扫描"""
    from adapters.rule_loader import RuleLoader

    rules_root = args.rules_dir or str(get_project_root() / "rules")
    print(f"\n📂 扫描规则目录: {rules_root}")
    print("─" * 60)

    loader = RuleLoader(rules_root)
    inventory = loader.scan_all()

    # 打印摘要
    print(inventory.get_summary_text())

    # 验证
    issues = loader.validate_inventory()
    if issues:
        print("\n⚠️ 发现以下问题:")
        for issue in issues:
            print(f"  • {issue}")
    else:
        print("\n✅ 所有文件验证通过")

    # 导出 JSON（可选）
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(inventory.to_dict(), f, ensure_ascii=False, indent=2)
        print(f"\n📄 清单已导出: {output_path}")


def cmd_status(args):
    """查看系统状态"""
    from core.orchestrator import Orchestrator
    from utils.file_ops import safe_yaml_read

    project_root = str(get_project_root())
    config_path = get_project_root() / "config" / "system.yaml"

    config = safe_yaml_read(config_path) or {}

    orch = Orchestrator(
        project_root=project_root,
        config={
            "sandbox_root": config.get("parallel_architecture", {}).get("sandbox_root", ".sandboxes"),
            "protected_paths": ["rules"],
            "max_parallel_agents": config.get("parallel_architecture", {}).get("max_parallel_agents", 4)
        }
    )

    status = orch.get_system_status()

    print("\n🎮 OpenClaw 多智能体游戏开发团队系统")
    print("=" * 60)
    print(f"  📍 项目根目录:     {project_root}")
    print(f"  🔧 活跃流水线:     {status['active_pipelines']}")
    print(f"  🤖 已注册Agent:    {len(status['registered_agents'])}")
    print(f"  📦 活跃沙盒:       {len(status['active_sandboxes'])}")
    print(f"  📬 消息队列:")
    for channel, count in status['message_queue_stats'].items():
        print(f"      {channel}: {count} 条")
    print(f"  📝 日志条目:       {status['log_entries']}")
    print("=" * 60)

    orch.shutdown()


def cmd_demo(args):
    """运行演示流程"""
    from demo import run_demo
    run_demo(verbose=args.verbose)


def cmd_verify(args):
    """验证系统隔离机制"""
    from core.sandbox import SandboxManager, SandboxConfig

    project_root = str(get_project_root())

    print("\n🔒 OpenClaw 系统隔离验证")
    print("=" * 60)

    # 1. 沙盒管理器初始化
    print("\n📦 1. 初始化沙盒管理器...")
    mgr = SandboxManager(project_root, ".sandboxes", ["rules"])
    print("   ✅ 沙盒管理器初始化成功")

    # 2. 创建测试沙盒
    print("\n📦 2. 创建测试Agent沙盒...")
    test_config = SandboxConfig(
        agent_id="test_agent",
        agent_name="测试Agent",
        sandbox_root=".sandboxes",
        read_permissions=["rules/**"],
        write_permissions=[".GameDev/**"]
    )
    sandbox_path = mgr.create_sandbox(test_config)
    print(f"   ✅ 沙盒已创建: {sandbox_path}")

    # 3. 测试源文档保护
    print("\n🔐 3. 测试源文档保护机制...")
    test_write_path = str(get_project_root() / "rules" / "test_write.md")
    allowed, reason = mgr.check_access("test_agent", test_write_path, "write")
    if not allowed:
        print(f"   ✅ 源文档保护生效: {reason}")
    else:
        print(f"   ❌ 源文档保护失败! 写入被允许!")

    # 4. 测试沙盒内操作
    print("\n📁 4. 测试沙盒内操作...")
    sandbox_file = str(sandbox_path / "workspace" / "test.txt")
    allowed, reason = mgr.check_access("test_agent", sandbox_file, "write")
    if allowed:
        print(f"   ✅ 沙盒内写入允许: {reason}")
    else:
        print(f"   ❌ 沙盒内写入被拒: {reason}")

    # 5. 测试跨沙盒访问
    print("\n🚫 5. 测试跨沙盒访问...")
    other_sandbox = str(Path(project_root) / ".sandboxes" / "other_agent" / "workspace" / "file.txt")
    allowed, reason = mgr.check_access("test_agent", other_sandbox, "read")
    if not allowed:
        print(f"   ✅ 跨沙盒访问被阻止: {reason}")
    else:
        print(f"   ❌ 跨沙盒访问未阻止!")

    # 6. 清理
    print("\n🧹 6. 清理测试沙盒...")
    mgr.destroy_sandbox("test_agent", preserve_output=False)
    print("   ✅ 清理完成")

    # 7. 操作日志
    print("\n📝 7. 操作日志:")
    for log in mgr.get_operation_log():
        status = "✅" if log["allowed"] else "❌"
        print(f"   {status} [{log['operation']}] {log['path'][:60]}")
        if log["reason"]:
            print(f"      └─ {log['reason']}")

    print("\n" + "=" * 60)
    print("🔒 隔离验证完成!")


def cmd_web(args):
    """启动Web仪表盘"""
    try:
        from web.app import create_app
    except ImportError:
        print("❌ Web模块未安装，请先安装依赖: pip install fastapi uvicorn")
        sys.exit(1)

    host = args.host or "0.0.0.0"
    port = args.port or 8080

    print(f"\n🌐 启动 OpenClaw Web 仪表盘...")
    print(f"   地址: http://{host}:{port}")
    print(f"   按 Ctrl+C 停止\n")

    import uvicorn
    app = create_app(str(get_project_root()))
    uvicorn.run(app, host=host, port=port)


def main():
    """CLI主入口"""
    parser = argparse.ArgumentParser(
        prog="openclaw-team",
        description="🎮 OpenClaw 多智能体游戏开发团队系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  openclaw-team inventory                  # 扫描规则资产
  openclaw-team inventory -o report.json   # 导出清单JSON
  openclaw-team status                     # 查看系统状态
  openclaw-team demo                       # 运行演示
  openclaw-team demo -v                    # 详细模式运行演示
  openclaw-team verify                     # 验证隔离机制
  openclaw-team web                        # 启动Web仪表盘
  openclaw-team web --port 3000            # 指定端口启动Web
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # inventory 命令
    inv_parser = subparsers.add_parser("inventory", help="扫描规则目录并输出资产清单")
    inv_parser.add_argument("-r", "--rules-dir", help="规则目录路径")
    inv_parser.add_argument("-o", "--output", help="输出JSON文件路径")

    # status 命令
    subparsers.add_parser("status", help="查看系统状态")

    # demo 命令
    demo_parser = subparsers.add_parser("demo", help="运行演示流程")
    demo_parser.add_argument("-v", "--verbose", action="store_true", help="详细模式")

    # verify 命令
    subparsers.add_parser("verify", help="验证系统隔离机制")

    # web 命令
    web_parser = subparsers.add_parser("web", help="启动Web仪表盘")
    web_parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    web_parser.add_argument("--port", type=int, default=8080, help="监听端口")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    # 路由到对应命令
    commands = {
        "inventory": cmd_inventory,
        "status": cmd_status,
        "demo": cmd_demo,
        "verify": cmd_verify,
        "web": cmd_web,
    }

    cmd_func = commands.get(args.command)
    if cmd_func:
        try:
            cmd_func(args)
        except KeyboardInterrupt:
            print("\n\n👋 已中断")
            sys.exit(0)
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            if os.environ.get("DEBUG"):
                import traceback
                traceback.print_exc()
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
