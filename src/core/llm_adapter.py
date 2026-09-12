"""
LLM 适配器层 - 多模型提供商支持

支持的提供商:
- OpenAI (GPT-4, GPT-4o, GPT-3.5-turbo)
- Anthropic (Claude 3.5 Sonnet, Claude 3 Opus)
- DeepSeek (DeepSeek-V3, DeepSeek-Coder)
- 自定义 OpenAI 兼容 API (本地模型等)

功能:
- Per-agent 独立模型配置
- API Key 管理
- 配置持久化 (JSON)
- 运行时热切换
"""

import json
import os
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 模型提供商定义
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROVIDERS = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": [
            {"id": "gpt-4o", "name": "GPT-4o", "context_window": 128000},
            {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "context_window": 128000},
            {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "context_window": 128000},
            {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "context_window": 16385},
        ],
    },
    "anthropic": {
        "name": "Anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "models": [
            {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "context_window": 200000},
            {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet", "context_window": 200000},
            {"id": "claude-3-opus-20240229", "name": "Claude 3 Opus", "context_window": 200000},
            {"id": "claude-3-haiku-20240307", "name": "Claude 3 Haiku", "context_window": 200000},
        ],
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": [
            {"id": "deepseek-chat", "name": "DeepSeek-V3", "context_window": 64000},
            {"id": "deepseek-coder", "name": "DeepSeek Coder", "context_window": 64000},
            {"id": "deepseek-reasoner", "name": "DeepSeek R1", "context_window": 64000},
        ],
    },
    "custom": {
        "name": "自定义 (OpenAI 兼容)",
        "base_url": "",
        "models": [],
    },
}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 配置数据类
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class AgentModelConfig:
    """单个 Agent 的模型配置"""
    agent_id: str
    agent_name: str = ""
    provider: str = "openai"           # openai / anthropic / deepseek / custom
    model: str = "gpt-4o"              # 具体模型ID
    api_key: str = ""                  # API密钥
    base_url: str = ""                 # 自定义 base URL (覆盖默认)
    temperature: float = 0.7           # 温度参数
    max_tokens: int = 4096             # 最大输出 token 数
    enabled: bool = True               # 是否启用 LLM 调用
    extra_params: Dict[str, Any] = field(default_factory=dict)  # 额外参数

    def to_dict(self) -> dict:
        """转为字典（API密钥脱敏）"""
        d = asdict(self)
        if d["api_key"]:
            key = d["api_key"]
            d["api_key_masked"] = key[:8] + "****" + key[-4:] if len(key) > 12 else "****"
        else:
            d["api_key_masked"] = ""
        return d

    def to_dict_full(self) -> dict:
        """转为字典（含完整密钥, 仅内部使用）"""
        return asdict(self)

    def get_effective_base_url(self) -> str:
        """获取有效的 base_url"""
        if self.base_url:
            return self.base_url
        provider_info = PROVIDERS.get(self.provider, {})
        return provider_info.get("base_url", "")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 配置管理器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class ModelConfigManager:
    """
    模型配置管理器

    负责:
    - 加载/保存 per-agent 模型配置
    - 提供默认配置
    - API 密钥管理
    """

    # 默认 Agent 列表及其推荐模型
    DEFAULT_AGENT_CONFIGS = {
        "00_producer": {"agent_name": "制作人老梁", "provider": "openai", "model": "gpt-4o", "temperature": 0.3},
        "01_pm": {"agent_name": "PM小李", "provider": "openai", "model": "gpt-4o-mini", "temperature": 0.3},
        "02_planner": {"agent_name": "策划小张", "provider": "openai", "model": "gpt-4o", "temperature": 0.7},
        "03_tech_lead": {"agent_name": "主程老陈", "provider": "anthropic", "model": "claude-sonnet-4-20250514", "temperature": 0.4},
        "04_programmer": {"agent_name": "程序小赵", "provider": "anthropic", "model": "claude-sonnet-4-20250514", "temperature": 0.2},
        "05_artist": {"agent_name": "美术小周", "provider": "openai", "model": "gpt-4o", "temperature": 0.8},
        "06_qa": {"agent_name": "QA小吴", "provider": "deepseek", "model": "deepseek-chat", "temperature": 0.3},
        "07_ux": {"agent_name": "UX小林", "provider": "openai", "model": "gpt-4o", "temperature": 0.7},
    }

    def __init__(self, config_path: str):
        """
        Args:
            config_path: 配置文件路径 (JSON)
        """
        self.config_path = Path(config_path)
        self._configs: Dict[str, AgentModelConfig] = {}
        self._load()

    def _load(self):
        """加载配置文件"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for agent_id, cfg_dict in data.get("agents", {}).items():
                    self._configs[agent_id] = AgentModelConfig(
                        agent_id=agent_id,
                        agent_name=cfg_dict.get("agent_name", ""),
                        provider=cfg_dict.get("provider", "openai"),
                        model=cfg_dict.get("model", "gpt-4o"),
                        api_key=cfg_dict.get("api_key", ""),
                        base_url=cfg_dict.get("base_url", ""),
                        temperature=cfg_dict.get("temperature", 0.7),
                        max_tokens=cfg_dict.get("max_tokens", 4096),
                        enabled=cfg_dict.get("enabled", True),
                        extra_params=cfg_dict.get("extra_params", {}),
                    )
                logger.info(f"已加载 {len(self._configs)} 个 Agent 模型配置")
            except Exception as e:
                logger.warning(f"加载模型配置失败: {e}, 使用默认配置")
                self._init_defaults()
        else:
            self._init_defaults()

    def _init_defaults(self):
        """初始化默认配置"""
        for agent_id, defaults in self.DEFAULT_AGENT_CONFIGS.items():
            self._configs[agent_id] = AgentModelConfig(
                agent_id=agent_id,
                agent_name=defaults["agent_name"],
                provider=defaults["provider"],
                model=defaults["model"],
                temperature=defaults["temperature"],
            )
        self._save()

    def _save(self):
        """保存配置到文件"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "1.0.0",
            "updated_at": datetime.now().isoformat(),
            "agents": {}
        }
        for agent_id, cfg in self._configs.items():
            data["agents"][agent_id] = cfg.to_dict_full()
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_config(self, agent_id: str) -> Optional[AgentModelConfig]:
        """获取 Agent 的模型配置"""
        return self._configs.get(agent_id)

    def get_all_configs(self) -> Dict[str, AgentModelConfig]:
        """获取所有 Agent 的模型配置"""
        return dict(self._configs)

    def update_config(self, agent_id: str, updates: Dict[str, Any]) -> AgentModelConfig:
        """
        更新 Agent 的模型配置

        Args:
            agent_id: Agent ID
            updates: 需要更新的字段

        Returns:
            更新后的配置
        """
        cfg = self._configs.get(agent_id)
        if not cfg:
            cfg = AgentModelConfig(agent_id=agent_id)
            self._configs[agent_id] = cfg

        # 可更新的字段
        updatable_fields = [
            "agent_name", "provider", "model", "api_key", "base_url",
            "temperature", "max_tokens", "enabled", "extra_params"
        ]
        for key in updatable_fields:
            if key in updates:
                setattr(cfg, key, updates[key])

        self._save()
        logger.info(f"已更新 Agent {agent_id} 的模型配置: provider={cfg.provider}, model={cfg.model}")
        return cfg

    def get_all_configs_masked(self) -> List[dict]:
        """获取所有配置（脱敏版本，用于前端展示）"""
        result = []
        for agent_id, cfg in self._configs.items():
            d = cfg.to_dict()
            del d["api_key"]  # 删除原始密钥
            result.append(d)
        return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LLM 调用器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LLMInvoker:
    """
    LLM 调用器

    统一接口调用不同提供商的模型。
    使用 OpenAI 兼容接口 + Anthropic 原生接口。
    """

    def __init__(self, config_mgr: ModelConfigManager):
        self.config_mgr = config_mgr

    async def invoke(self, agent_id: str, messages: List[dict],
                     system_prompt: str = "", **kwargs) -> dict:
        """
        调用 LLM

        Args:
            agent_id: Agent ID (用于查找配置)
            messages: 消息列表 [{role, content}]
            system_prompt: 系统提示词
            **kwargs: 覆盖配置参数

        Returns:
            {content: str, usage: dict, model: str, provider: str}
        """
        cfg = self.config_mgr.get_config(agent_id)
        if not cfg or not cfg.enabled:
            return {
                "content": f"[LLM未配置] Agent {agent_id} 的模型未配置或未启用",
                "usage": {},
                "model": "none",
                "provider": "none",
                "simulated": True
            }

        if not cfg.api_key:
            return {
                "content": f"[API密钥未设置] Agent {agent_id} ({cfg.agent_name}) 的 {cfg.provider} API密钥未配置",
                "usage": {},
                "model": cfg.model,
                "provider": cfg.provider,
                "simulated": True
            }

        # 根据提供商选择调用方式
        if cfg.provider == "anthropic":
            return await self._invoke_anthropic(cfg, messages, system_prompt, **kwargs)
        else:
            # OpenAI 兼容接口 (openai, deepseek, custom)
            return await self._invoke_openai_compatible(cfg, messages, system_prompt, **kwargs)

    async def _invoke_openai_compatible(self, cfg: AgentModelConfig,
                                         messages: List[dict],
                                         system_prompt: str = "",
                                         **kwargs) -> dict:
        """OpenAI 兼容接口调用"""
        try:
            import httpx
        except ImportError:
            return {"content": "[依赖缺失] 请安装 httpx: pip install httpx", "usage": {}, "model": cfg.model, "provider": cfg.provider, "simulated": True}

        base_url = cfg.get_effective_base_url().rstrip("/")
        url = f"{base_url}/chat/completions"

        # 构建消息
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        payload = {
            "model": cfg.model,
            "messages": full_messages,
            "temperature": kwargs.get("temperature", cfg.temperature),
            "max_tokens": kwargs.get("max_tokens", cfg.max_tokens),
        }
        # 合并额外参数
        for k, v in cfg.extra_params.items():
            if k not in payload:
                payload[k] = v

        headers = {
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            choice = data["choices"][0]
            return {
                "content": choice["message"]["content"],
                "usage": data.get("usage", {}),
                "model": cfg.model,
                "provider": cfg.provider,
                "simulated": False,
            }
        except Exception as e:
            logger.error(f"LLM 调用失败 ({cfg.provider}/{cfg.model}): {e}")
            return {
                "content": f"[调用失败] {cfg.provider}/{cfg.model}: {str(e)}",
                "usage": {},
                "model": cfg.model,
                "provider": cfg.provider,
                "simulated": True,
                "error": str(e),
            }

    async def _invoke_anthropic(self, cfg: AgentModelConfig,
                                 messages: List[dict],
                                 system_prompt: str = "",
                                 **kwargs) -> dict:
        """Anthropic 原生接口调用"""
        try:
            import httpx
        except ImportError:
            return {"content": "[依赖缺失] 请安装 httpx: pip install httpx", "usage": {}, "model": cfg.model, "provider": cfg.provider, "simulated": True}

        base_url = (cfg.base_url or "https://api.anthropic.com").rstrip("/")
        url = f"{base_url}/v1/messages"

        payload = {
            "model": cfg.model,
            "max_tokens": kwargs.get("max_tokens", cfg.max_tokens),
            "temperature": kwargs.get("temperature", cfg.temperature),
            "messages": messages,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": cfg.api_key,
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01",
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            content = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    content += block["text"]

            return {
                "content": content,
                "usage": data.get("usage", {}),
                "model": cfg.model,
                "provider": cfg.provider,
                "simulated": False,
            }
        except Exception as e:
            logger.error(f"Anthropic 调用失败 ({cfg.model}): {e}")
            return {
                "content": f"[调用失败] anthropic/{cfg.model}: {str(e)}",
                "usage": {},
                "model": cfg.model,
                "provider": cfg.provider,
                "simulated": True,
                "error": str(e),
            }

    def invoke_sync(self, agent_id: str, messages: List[dict],
                    system_prompt: str = "", **kwargs) -> dict:
        """
        同步版本的 LLM 调用（供非异步上下文使用）

        有 API Key 时：用 asyncio 真实调用 LLM
        无 API Key 时：返回友好占位响应，提示用户配置
        """
        import asyncio

        cfg = self.config_mgr.get_config(agent_id)
        if not cfg or not cfg.enabled:
            return {
                "content": f"[Agent {agent_id} 未启用] 请在智能体配置页面启用该 Agent",
                "usage": {},
                "model": cfg.model if cfg else "none",
                "provider": cfg.provider if cfg else "none",
                "simulated": True,
            }

        if not cfg.api_key:
            return {
                "content": (
                    f"[{cfg.agent_name or agent_id} 待配置] "
                    f"请在「智能体配置」页面为 {cfg.agent_name or agent_id} "
                    f"配置 {cfg.provider.upper()} API Key，配置后将真正调用 LLM。"
                ),
                "usage": {},
                "model": cfg.model,
                "provider": cfg.provider,
                "simulated": True,
            }

        # 有 API Key — 真实调用
        try:
            # 若当前有 event loop（FastAPI/asyncio 环境），用 run_coroutine_threadsafe
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    future = asyncio.run_coroutine_threadsafe(
                        self.invoke(agent_id, messages, system_prompt, **kwargs),
                        loop
                    )
                    return future.result(timeout=120)
            except RuntimeError:
                pass

            # 无 event loop — 直接 asyncio.run
            return asyncio.run(
                self.invoke(agent_id, messages, system_prompt, **kwargs)
            )
        except Exception as e:
            logger.error(f"invoke_sync 调用失败 ({agent_id}): {e}")
            return {
                "content": f"[LLM 调用失败] {agent_id}: {str(e)}",
                "usage": {},
                "model": cfg.model,
                "provider": cfg.provider,
                "simulated": True,
                "error": str(e),
            }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 提供商信息查询
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_available_providers() -> dict:
    """获取所有可用的模型提供商信息"""
    return PROVIDERS


def get_provider_models(provider: str) -> List[dict]:
    """获取指定提供商的模型列表"""
    provider_info = PROVIDERS.get(provider, {})
    return provider_info.get("models", [])
