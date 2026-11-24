"""模型配置模块（可直接复用到别的软件）。

典型接法（FastAPI + 本模块自带前端组件）：

    from model_config import ModelConfigService, ModelConfigStore, create_router

    store = ModelConfigStore("data/model_config.json")
    service = ModelConfigService(store, auto_start=True)   # 启动后台体检
    app.include_router(create_router(service), prefix="/api/model-config")

    # 页面里：
    #   <model-config-panel api-base="/api/model-config"></model-config-panel>
    #   <script src="/static/model_config/model-config.js"></script>

宿主要用「现在生效的模型」发请求：

    provider = service.build_current_provider(timeout=300)
    reply = provider.chat([{"role": "user", "content": "你好"}], {"max_tokens": 512})
"""
from .providers import (
    ArkProvider,
    LlmProvider,
    Message,
    OnChunk,
    OpenAICompatProvider,
    ProviderCancelled,
    ProviderError,
    Reply,
)
from .registry import (
    ARK_AGENT_URL,
    ARK_API_URL,
    ARK_CODING_URL,
    TEMPLATES,
    TemplateInfo,
    catalog_templates,
)
from .service import ModelConfigService, NotFound, ServiceError
from .store import (
    DEFAULT_MODEL,
    THINKING_LEVELS,
    ModelConfig,
    ModelConfigStore,
)
from .transport import DefaultTransport, Transport


def __getattr__(name):
    """create_router 懒加载：不装 FastAPI 也能只用核心层（service / 客户端）。"""
    if name == "create_router":
        from .router import create_router
        return create_router
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "ArkProvider",
    "DefaultTransport",
    "LlmProvider",
    "Message",
    "ModelConfig",
    "ModelConfigService",
    "ModelConfigStore",
    "NotFound",
    "OnChunk",
    "OpenAICompatProvider",
    "ProviderCancelled",
    "ProviderError",
    "Reply",
    "ServiceError",
    "THINKING_LEVELS",
    "TEMPLATES",
    "TemplateInfo",
    "Transport",
    "ARK_AGENT_URL",
    "ARK_API_URL",
    "ARK_CODING_URL",
    "DEFAULT_MODEL",
    "catalog_templates",
    "create_router",
]
