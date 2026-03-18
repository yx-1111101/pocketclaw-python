"""
LLM 提供商适配器 + 路由配置加载

配置文件: llm_proxy/routing.yaml
  - providers:     所有可用的 LLM 提供商（按 base_url 区分，如 zhizengzeng、openai 等）
  - model_routing: 模型名 → 提供商 + 可选参数覆盖
  - default:       无匹配规则时的默认提供商/模型

术语说明:
  provider:      LLM API 服务提供商（如 zhizengzeng、openai），由 base_url 区分
  request_type:  API 协议类型（如 openai、anthropic），决定请求/响应格式
"""

from __future__ import annotations

import os
import json
import logging
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional

import httpx
import yaml


# ── Config dataclasses ────────────────────────────────────────────────────────

@dataclass
class ProviderConfig:
    name: str
    base_url: str
    api_key: str = ""
    api_key_env: str = ""
    request_type: str = "openai"   # API protocol: "openai" or "anthropic"


@dataclass
class ModelRoute:
    provider: str               # must match a ProviderConfig.name
    model: str                  # model name forwarded to the provider
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    timeout: float = 60.0


@dataclass
class RoutingConfig:
    providers: list[ProviderConfig] = field(default_factory=list)
    model_routing: Dict[str, ModelRoute] = field(default_factory=dict)
    default_provider: str = ""
    default_model: str = ""


# ── YAML loader ───────────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent / "routing.yaml"


def load_routing_config(path: Path = _CONFIG_PATH) -> RoutingConfig:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    providers = []
    for p in raw.get("providers", []):
        cfg = ProviderConfig(
            name=p["name"],
            base_url=p["base_url"].rstrip("/"),
            api_key=p.get("api_key", ""),
            api_key_env=p.get("api_key_env", ""),
            request_type=p.get("request_type", "openai"),
        )
        # env var takes precedence
        if cfg.api_key_env:
            env_val = os.environ.get(cfg.api_key_env, "")
            if env_val:
                cfg.api_key = env_val
        providers.append(cfg)

    model_routing: Dict[str, ModelRoute] = {}
    for model_name, v in raw.get("model_routing", {}).items():
        model_routing[model_name] = ModelRoute(
            provider=v["provider"],
            model=v.get("model", model_name),
            temperature=v.get("temperature"),
            max_tokens=v.get("max_tokens"),
            timeout=float(v.get("timeout", 60.0)),
        )

    default = raw.get("default", {})
    return RoutingConfig(
        providers=providers,
        model_routing=model_routing,
        default_provider=default.get("provider", ""),
        default_model=default.get("model", ""),
    )


# ── Debug logging setup ──────────────────────────────────────────────────────

def setup_debug_logger():
    """Setup logger for debugging HTTP requests"""
    logger = logging.getLogger('llm_proxy_debug')
    logger.setLevel(logging.DEBUG)

    # Avoid duplicate handlers
    if not logger.handlers:
        # Create debug_logs directory if it doesn't exist
        debug_dir = Path("./debug_logs")
        debug_dir.mkdir(exist_ok=True)

        # File handler for debug logs
        log_file = debug_dir / f"requests_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger

def log_request_response(logger, method, url, headers, payload, response=None, error=None):
    """Log full request and response details"""
    timestamp = datetime.now().isoformat()

    log_data = {
        "timestamp": timestamp,
        "method": method,
        "url": url,
        "request_headers": dict(headers),
        "request_body": payload,
    }

    if response is not None:
        log_data.update({
            "response_status": response.status_code,
            "response_headers": dict(response.headers),
            "response_body": response.text if hasattr(response, 'text') else str(response)
        })

    if error is not None:
        log_data["error"] = str(error)
        log_data["error_type"] = type(error).__name__

    # Log as JSON for easy parsing
    logger.debug(json.dumps(log_data, indent=2, ensure_ascii=False))

    # Also save individual request files for detailed inspection
    debug_dir = Path("./debug_logs")
    request_file = debug_dir / f"request_{timestamp.replace(':', '-').replace('.', '_')}.json"

    try:
        with open(request_file, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Failed to save request file: {e}")

# ── Provider HTTP client ──────────────────────────────────────────────────────

class OpenAIProvider:
    """通用 OpenAI-compatible 提供商"""

    def __init__(self, cfg: ProviderConfig):
        self.cfg = cfg
        self.logger = setup_debug_logger()

    async def chat_completion(
        self,
        messages: list,
        model: str,
        timeout: float = 60.0,
        **kwargs,
    ) -> Dict[str, Any]:
        payload = {"model": model, "messages": messages, **kwargs}
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.cfg.base_url}/chat/completions"

        # Log request details
        self.logger.info(f"Making request to {url}")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=payload)

                # Log full request and response
                log_request_response(
                    self.logger, "POST", url, headers, payload, response=response
                )

                response.raise_for_status()
                return response.json()

        except Exception as e:
            # Log error details
            log_request_response(
                self.logger, "POST", url, headers, payload, error=e
            )
            self.logger.error(f"Request failed: {e}")
            raise

    async def chat_completion_stream(
        self,
        messages: list,
        model: str,
        timeout: float = 60.0,
        **kwargs,
    ) -> AsyncIterator[str]:
        kwargs.pop("stream", None)
        payload = {"model": model, "messages": messages, "stream": True, **kwargs}
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.cfg.base_url}/chat/completions"

        # Log request details
        self.logger.info(f"Making streaming request to {url}")

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=payload
                ) as response:
                    # Log request and initial response
                    log_request_response(
                        self.logger, "POST", url, headers, payload, response=response
                    )

                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        yield line

        except Exception as e:
            # Log error details for streaming requests
            log_request_response(
                self.logger, "POST", url, headers, payload, error=e
            )
            self.logger.error(f"Streaming request failed: {e}")
            raise


# ── Registry ──────────────────────────────────────────────────────────────────

class ProviderRegistry:
    def __init__(self):
        self._providers: Dict[str, OpenAIProvider] = {}
        self._routing: RoutingConfig = RoutingConfig()

    def load(self, path: Path = _CONFIG_PATH) -> None:
        cfg = load_routing_config(path)
        self._routing = cfg
        self._providers = {
            p.name: OpenAIProvider(p) for p in cfg.providers
        }

    def resolve(self, model: str, provider_hint: Optional[str] = None) -> tuple[OpenAIProvider, ModelRoute]:
        """
        Return (provider, route) for a given model name.

        Resolution order:
          1. Explicit entry in model_routing for this model name
          2. default provider/model from config
        """
        route = self._routing.model_routing.get(model)

        if route is None:
            # fall back to default
            route = ModelRoute(
                provider=self._routing.default_provider,
                model=self._routing.default_model or model,
            )

        # provider_hint from request body can override the YAML provider
        provider_name = provider_hint if provider_hint and provider_hint in self._providers \
                        else route.provider

        provider = self._providers.get(provider_name)
        if not provider:
            raise KeyError(
                f"Provider '{provider_name}' not found. "
                f"Available: {list(self._providers)}"
            )
        return provider, route

    def list_providers(self) -> list[str]:
        return list(self._providers)

    def list_models(self) -> list[str]:
        return list(self._routing.model_routing)


# ── Module-level singleton ────────────────────────────────────────────────────

registry = ProviderRegistry()


def init_providers(path: Path = _CONFIG_PATH) -> None:
    registry.load(path)


def resolve(model: str, provider_hint: Optional[str] = None):
    return registry.resolve(model, provider_hint)
