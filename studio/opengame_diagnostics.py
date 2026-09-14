"""Local preflight only: never call models or clean resources on a read."""
import asyncio
import json
import re

from .budget import BudgetLedger
from .db import now
from .opengame_executor import docker, verified_image
from .opengame_proxy import ModelProxy
from .opengame_tools import TOOL_MODELS
from .runner import PHASER_IMAGE
from .template_registry import TEMPLATES


def execution_status(executor):
    try:
        with executor.records.lease():
            return {**executor.records.summary(), 'busy': False}
    except RuntimeError:
        return {**executor.records.summary(), 'busy': True, 'can_start': False}


async def diagnostics(executor, gateway):
    async def image_check(cli):
        try:
            async with asyncio.timeout(8):
                if cli:
                    await verified_image()
                else:
                    info = json.loads(await docker('image', 'inspect', PHASER_IMAGE))[0]
                    if not re.fullmatch(r'sha256:[a-f0-9]{64}', info['Id']):
                        raise ValueError
            return True
        except Exception:
            return False
    cli, phaser = await asyncio.gather(image_check(True), image_check(False))
    checks = []
    def add(id, label, passed, detail, action=None):
        checks.append({'id': id, 'label': label, 'status': 'passed' if passed else 'failed',
                       'detail': detail, 'action': action})
    add('cli_image', 'OpenGame 执行环境', cli,
        '固定 CLI 与转发程序版本匹配。' if cli else '无法确认固定执行镜像；请检查 Docker 服务，并按项目计划构建 OpenGame 镜像。')
    add('phaser_image', 'Phaser 构建环境', phaser,
        'Phaser 构建镜像可访问。' if phaser else '无法确认 Phaser 镜像；请检查 Docker 并构建游戏环境。')
    ledger = BudgetLedger(executor.records.store.root)
    config = None
    try:
        # Constructor validates the same contract used at execution time. It does
        # not open clients, create requests, or reserve budget.
        config = gateway.effective('程序')
        ModelProxy(config, ledger, allowed_tools=TOOL_MODELS, deadline=0, active=lambda: False)
        model_ok = True
    except Exception:
        model_ok = False
    add('model_config', '程序角色连接配置', model_ok,
        '配置格式符合编码接口要求，真实工具调用仍需验证。' if model_ok else
        '请保存程序角色的 OpenAI 兼容连接、模型与凭据；本机免密服务可不填密钥。', 'settings')
    try:
        budget = ledger.summary()
        price = ledger.model_price(config) if model_ok else None
        unlimited = budget.get('enabled') and budget.get('enforce_limits') is False
        budget_ok = budget.get('enabled') and (unlimited or (
            budget.get('remaining_cny', 0) > 0 and not budget.get('over_budget')))
    except Exception:
        budget, price, budget_ok, unlimited = None, None, False, False
    add('price', '编码模型单价', price is not None or unlimited,
        '已登记当前服务地址与模型对应的输入、输出单价。' if price is not None else
        '未登记单价；不限额模式下可调用，费用记为未知，用量仍会记录。' if unlimited else
        '当前编码连接缺少单价。按服务商实际价格登记后才能发起计费请求。')
    add('budget', '调用预算', budget_ok,
        '本项目不限额，不因金额、单价或图片尝试次数拦截调用；保留用量与费用记录。' if unlimited else
        '预算已启用且有余额；每次请求仍需足够的费用预留。' if budget_ok else
        '预算未启用、无法读取或可用余额不足；检查预算和待核账费用。')
    executions = execution_status(executor)
    if executions['busy']:
        checks.append({'id': 'resources', 'label': '任务资源', 'status': 'unverified',
                       'detail': '已有执行或恢复正在进行，请稍后刷新。', 'action': None})
    else:
        add('resources', '任务资源', executions['can_start'],
            '没有待清理资源。' if executions['can_start'] else
            f"有 {executions['pending_cleanup']} 条资源记录待确认。可重新核查所属资源；不会重跑模型。", 'recover')
    preflight = all(c['status'] == 'passed' for c in checks)
    return {'checked_at': now(), 'model_called': False, 'preflight_passed': preflight,
            'live_tool_call_verified': False,
            'tower_creation_available': TEMPLATES['phaser-tower_defense'].status == 'available',
            'checks': checks, 'budget': budget, 'price': price, 'executions': executions}
