"""真实网络访问的接缝（可替换）。

`ModelConfigService` 只通过 Transport 发请求——测试里换一个假 Transport 就能
完全不联网；宿主软件也可以换成自己带代理 / 日志的 Transport。
"""
from __future__ import annotations

from typing import Any, Protocol

from . import connection
from .connection import ConnectionResult
from .providers import LlmProvider, OpenAICompatProvider
from .registry import (
    instance_api_key,
    instance_base_url,
    instance_template,
)


class Transport(Protocol):
    def list_models(self, api_key: str, base_url: str) -> list[str]: ...

    def check_provider_models(
        self, api_key: str, base_url: str, label: str
    ) -> ConnectionResult: ...

    def check_model(
        self, inst: dict, api_key: str, model: str
    ) -> ConnectionResult: ...

    def build_provider(
        self, inst: dict, model: str, api_key: str, **kwargs: Any
    ) -> LlmProvider: ...


class DefaultTransport:
    """默认实现：httpx + OpenAICompatProvider。"""

    def __init__(self, provider_class=OpenAICompatProvider):
        self._provider_class = provider_class

    def list_models(self, api_key: str, base_url: str) -> list[str]:
        return connection.list_models(api_key, base_url)

    def check_provider_models(
        self, api_key: str, base_url: str, label: str
    ) -> ConnectionResult:
        return connection.check_provider_models(api_key, base_url, label)

    def build_provider(
        self, inst: dict, model: str, api_key: str, **kwargs: Any
    ) -> LlmProvider:
        """按实例现场构建客户端：接口地址、Key、家级默认参数、参数习惯都取自
        实例与它的模板。"""
        tpl = instance_template(inst)
        return self._provider_class(
            api_key=instance_api_key(inst) if api_key is None else api_key,
            model=model,
            base_url=instance_base_url(inst),
            request_extra=tpl.request_extra if tpl else None,
            param_style=tpl.param_style if tpl else "chat",
            label=inst["name"],
            **kwargs,
        )

    def check_model(
        self, inst: dict, api_key: str, model: str
    ) -> ConnectionResult:
        """一次极小真调（max_tokens=1），带回结构化结果。"""
        provider = self.build_provider(
            inst, model, api_key, sleep=lambda _s: None, timeout=15.0
        )
        try:
            return connection.check_connection(
                provider, model=model, provider_label=inst["name"]
            )
        finally:
            provider.close()
