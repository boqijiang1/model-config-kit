import pytest

from conftest import FakeProvider, add_provider
from model_config.service import NotFound, ServiceError


def _row(status, provider_id, model):
    provider = next(p for p in status["providers"] if p["id"] == provider_id)
    return next(m for m in provider["models"] if m["id"] == model)


def test_空状态_没有Key_不冒充已验证(service):
    st = service.status()
    assert st["providers"] == [] and st["has_api_key"] is False
    assert [c["template"] for c in st["catalog"]] == [
        "ark-api", "ark-coding-plan", "ark-agent-plan", "deepseek", "openai",
    ]
    service.start()
    assert service.status()["health"]["state"] == "none"


def test_添加供应商_Key验证通过才落盘_自动选型生效(service, transport):
    provider = add_provider(service)
    assert provider["id"] == "ark-agent-plan"
    st = service.status()
    assert st["has_api_key"] is True
    assert st["enabled_providers"] == ["ark-agent-plan"]
    assert st["model"] == "doubao-seed-2.1-pro" and st["model_auto"] is True
    assert st["model_verified"] is True
    # Key 真的落了盘（重新读文件还在）
    again = service.store.load()
    assert again.provider_instances[0]["api_key"] == "k"
    # Key 绝不会出现在 /status 回包里
    assert all("api_key" not in p for p in st["providers"])


def test_Key无效_不落盘_原来能用的Key不被覆盖(service, transport):
    add_provider(service)
    old = service.cfg.provider_instances[0]["api_key"]
    transport.fail_keys.add("bad")
    result = service.set_key("ark-agent-plan", "bad")
    assert result["ok"] is False and "Key 无效" in result["message"]
    assert service.cfg.provider_instances[0]["api_key"] == old


def test_自动选型_调不通的模型跳过_选下一个能用的(service, transport):
    transport.fail_models.add("doubao-seed-2.1-pro")
    provider = add_provider(service)
    assert provider["models"][0]["id"] == "doubao-seed-2.1-pro"
    st = service.status()
    assert st["model"] == "doubao-seed-2.1-lite"
    assert st["model_provider"] == "ark-agent-plan"
    assert st["model_verified"] is True


def test_手动指定模型_必须在清单里且开关打开_当场真调验证(service, transport):
    add_provider(service)
    result = service.choose_model("ark-agent-plan", "doubao-seed-2.1-lite")
    assert result["ok"] is True and result["model_verified"] is True
    assert service.status()["model_auto"] is False

    with pytest.raises(ServiceError) as e:
        service.choose_model("ark-agent-plan", "不存在的模型")
    assert "没有" in str(e.value)

    service.set_model_enabled("ark-agent-plan", "doubao-seed-2.1-pro", False)
    with pytest.raises(ServiceError) as e:
        service.choose_model("ark-agent-plan", "doubao-seed-2.1-pro")
    assert "开关是关着的" in str(e.value)

    transport.fail_models.add("doubao-seed-2.1-lite")
    with pytest.raises(ServiceError) as e:
        service.choose_model("ark-agent-plan", "doubao-seed-2.1-lite")
    assert "还没开通" in str(e.value)


def test_模型行实测结果_真调过才标_换Key或改名后作废(service, transport):
    add_provider(service)
    assert _row(service.status(), "ark-agent-plan", "doubao-seed-2.1-lite")["check"] is None

    transport.fail_models.add("doubao-seed-2.1-lite")
    result = service.test_model("ark-agent-plan", "doubao-seed-2.1-lite")
    assert result["ok"] is False
    assert _row(service.status(), "ark-agent-plan", "doubao-seed-2.1-lite")["check"] is False
    # 别的模型没被测过，不连累
    assert _row(service.status(), "ark-agent-plan", "doubao-seed-2.1-pro")["check"] in (True, False)

    # 输入框里没保存的 Key 测出来的结果，不写到已存的模型行上
    transport.fail_models.clear()
    service.test_model("ark-agent-plan", "doubao-seed-2.1-lite", api_key="other")
    assert _row(service.status(), "ark-agent-plan", "doubao-seed-2.1-lite")["check"] is False

    service.test_model("ark-agent-plan", "doubao-seed-2.1-lite")
    assert _row(service.status(), "ark-agent-plan", "doubao-seed-2.1-lite")["check"] is True

    # 换 Key：旧结果作废
    service.set_key("ark-agent-plan", "k2")
    assert _row(service.status(), "ark-agent-plan", "doubao-seed-2.1-lite")["check"] is None

    # 改名：旧名字的结果不跟到新名字上
    service.test_model("ark-agent-plan", "doubao-seed-2.1-lite")
    service.rename_model("ark-agent-plan", "doubao-seed-2.1-lite", "lite-2")
    assert _row(service.status(), "ark-agent-plan", "lite-2")["check"] is None


def test_模型增删改与开关_落盘(service):
    add_provider(service)
    provider = service.add_model("ark-agent-plan", " extra-model ")
    assert provider["models"][-1] == {"id": "extra-model", "enabled": True, "check": None}
    provider = service.set_model_enabled("ark-agent-plan", "extra-model", False)
    assert provider["models"][-1]["enabled"] is False
    provider = service.rename_model("ark-agent-plan", "extra-model", "extra-2")
    assert provider["models"][-1]["id"] == "extra-2"
    service.delete_model("ark-agent-plan", "extra-2")
    assert all(m["id"] != "extra-2" for m in service.status()["providers"][0]["models"])

    with pytest.raises(NotFound):
        service.add_model("ghost", "x")
    with pytest.raises(ServiceError):
        service.add_model("ark-agent-plan", "有 空格")


def test_从账号同步_只加对话模型_已有的不动(service, transport):
    add_provider(service, template="ark-api")
    from model_config.registry import ARK_API_URL

    transport.listed[ARK_API_URL] = [
        "gpt-5.6", "doubao-seed-3-0-pro-270101", "doubao-seed-2-1-pro-260628",
        "text-embedding-v4", "seedance-1", "deepseek-chat",
    ]
    result = service.sync_models("ark-api")
    assert result["ok"] is True
    added = result["added"]
    assert "doubao-seed-3-0-pro-270101" in added and "gpt-5.6" in added
    assert "doubao-seed-2-1-pro-260628" not in added  # 已有
    assert "text-embedding-v4" not in added and "seedance-1" not in added
    assert "deepseek-chat" not in added  # 已停用


def test_订阅套餐不提供在线列表_同步给大白话(service):
    add_provider(service)
    result = service.sync_models("ark-agent-plan")
    assert result["ok"] is False and "订阅套餐" in result["message"]


def test_删除供应商_锁定回自动并重选(service):
    add_provider(service)
    service.choose_model("ark-agent-plan", "doubao-seed-2.1-lite")
    assert service.status()["model_auto"] is False
    service.delete_provider("ark-agent-plan")
    assert service.status()["providers"] == []
    assert service.cfg.model_auto is True
    with pytest.raises(NotFound):
        service.delete_provider("ark-agent-plan")


def test_体检_手动锁定调不通_报manual_broken_不改配置(service, transport):
    add_provider(service)
    service.choose_model("ark-agent-plan", "doubao-seed-2.1-lite")
    transport.fail_models.add("doubao-seed-2.1-lite")
    service.start()
    st = service.status()
    assert st["health"]["state"] == "manual_broken"
    assert st["model"] == "doubao-seed-2.1-lite"  # 尊重锁定，不偷换
    assert st["model_verified"] is False


def test_面向宿主_build_current_provider(service, transport):
    add_provider(service)
    provider = service.build_current_provider(timeout=30)
    assert provider is transport.provider
    reply = provider.chat([{"role": "user", "content": "你好"}], {"max_tokens": 8})
    assert reply.content


def test_思考深度三档_非法值拦下(service):
    service.set_thinking("deep")
    assert service.status()["thinking_level"] == "deep"
    with pytest.raises(ServiceError):
        service.set_thinking("想很多")
