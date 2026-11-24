import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_config.connection import ConnectionResult  # noqa: E402
from model_config.providers import LlmProvider, Reply  # noqa: E402
from model_config.service import ModelConfigService  # noqa: E402
from model_config.store import ModelConfigStore  # noqa: E402


class FakeProvider(LlmProvider):
    def __init__(self, replies=None):
        self.replies = list(replies or ["好"])
        self.calls = []

    def chat(self, messages, opts, *, on_chunk=None):
        self.calls.append((messages, opts))
        return Reply(self.replies.pop(0) if self.replies else "好")


class FakeTransport:
    """不联网的替身：能调通与否由 fail_models / works 决定，调用都记下来。"""

    def __init__(self):
        self.works = True
        self.fail_models: set[str] = set()
        self.fail_keys: set[str] = set()
        self.listed: dict[str, list[str]] = {}
        self.model_calls: list[tuple[str, str, str]] = []
        self.provider = FakeProvider()

    def list_models(self, api_key, base_url):
        return list(self.listed.get(base_url, []))

    def check_provider_models(self, api_key, base_url, label):
        if not self.works or api_key in self.fail_keys:
            return ConnectionResult(False, "auth", f"Key 无效：请到{label}的控制台重新复制一遍。")
        return ConnectionResult(True, "ok", f"通了：{label}账号下能看到 3 个模型。")

    def check_model(self, inst, api_key, model):
        self.model_calls.append((inst["id"], model, api_key))
        if api_key in self.fail_keys:
            return ConnectionResult(False, "auth", "Key 无效：请重新复制一遍 API Key。")
        ok = self.works and model not in self.fail_models
        if ok:
            return ConnectionResult(True, "ok", f"连接成功，模型 {model} 可以正常对话。")
        return ConnectionResult(False, "model_not_open", f"模型还没开通：{model}")

    def build_provider(self, inst, model, api_key, **kwargs):
        return self.provider


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def service(tmp_path, transport):
    return ModelConfigService(
        ModelConfigStore(tmp_path / "model_config.json"),
        transport=transport,
        synchronous=True,  # 体检在调用线程里跑，测试结果确定
    )


def add_provider(service, template="ark-agent-plan", key="k"):
    provider = service.create_provider(template=template)
    if key is not None:
        result = service.set_key(provider["id"], key)
        assert result["ok"], result
    return provider
