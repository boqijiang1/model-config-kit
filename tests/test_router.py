import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import add_provider
from model_config import create_router

BASE = "/api/model-config"


@pytest.fixture
def client(service):
    app = FastAPI()
    app.include_router(create_router(service), prefix=BASE)
    return TestClient(app)


def test_状态与目录(client):
    st = client.get(BASE + "/status").json()
    assert st["providers"] == [] and st["has_api_key"] is False
    assert len(st["catalog"]) == 5
    assert st["thinking_level"] == "auto"


def test_添加供应商_填Key_自动选型_全走接口(client, service):
    r = client.post(BASE + "/providers", json={"template": "ark-agent-plan"})
    assert r.status_code == 200
    provider = r.json()["provider"]
    assert provider["id"] == "ark-agent-plan"
    assert "api_key" not in provider

    r = client.post(BASE + "/providers/ark-agent-plan/key", json={"api_key": "k"})
    assert r.status_code == 200 and r.json()["ok"] is True

    st = client.get(BASE + "/status").json()
    assert st["has_api_key"] is True
    assert st["model"] == "doubao-seed-2.1-pro"
    assert st["model_verified"] is True


def test_Key没验证过_接口如实回结构化失败(client, service, transport):
    client.post(BASE + "/providers", json={"template": "ark-agent-plan"})
    transport.fail_keys.add("bad")
    r = client.post(BASE + "/providers/ark-agent-plan/key", json={"api_key": "bad"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False and data["code"] == "auth"


def test_改供应商与删除(client):
    client.post(BASE + "/providers", json={"template": "deepseek"})
    r = client.patch(BASE + "/providers/deepseek", json={"name": "我的 DS", "enabled": False})
    assert r.json()["provider"]["name"] == "我的 DS"
    assert r.json()["provider"]["enabled"] is False
    assert client.delete(BASE + "/providers/deepseek").status_code == 200
    assert client.get(BASE + "/status").json()["providers"] == []
    assert client.delete(BASE + "/providers/deepseek").status_code == 404


def test_模型清单接口_增删改开关与测试(client):
    client.post(BASE + "/providers", json={"template": "ark-agent-plan"})
    client.post(BASE + "/providers/ark-agent-plan/key", json={"api_key": "k"})

    r = client.post(BASE + "/providers/ark-agent-plan/models", json={"model": "extra"})
    assert [m["id"] for m in r.json()["provider"]["models"]][-1] == "extra"

    r = client.patch(BASE + "/providers/ark-agent-plan/models/enabled",
                     json={"model": "extra", "enabled": False})
    assert r.json()["provider"]["models"][-1]["enabled"] is False

    r = client.patch(BASE + "/providers/ark-agent-plan/models",
                     json={"model": "extra", "new_model": "extra-2"})
    assert r.json()["provider"]["models"][-1]["id"] == "extra-2"

    r = client.post(BASE + "/providers/ark-agent-plan/models/test", json={"model": "extra-2"})
    assert r.status_code == 200 and "ok" in r.json()

    assert client.delete(BASE + "/providers/ark-agent-plan/models?model=extra-2").status_code == 200
    assert client.post(BASE + "/providers/ghost/models", json={"model": "x"}).status_code == 404


def test_当前生效模型_自动与手动(client):
    client.post(BASE + "/providers", json={"template": "ark-agent-plan"})
    client.post(BASE + "/providers/ark-agent-plan/key", json={"api_key": "k"})

    r = client.post(BASE + "/config", json={
        "model_auto": False, "model": "doubao-seed-2.1-lite",
        "model_provider": "ark-agent-plan",
    })
    assert r.status_code == 200 and r.json()["model_verified"] is True
    assert client.get(BASE + "/status").json()["model_auto"] is False

    r = client.post(BASE + "/config", json={"model_auto": True})
    assert r.status_code == 200 and r.json()["model"] == "doubao-seed-2.1-pro"

    r = client.post(BASE + "/config", json={"model_auto": False, "model": "没有的",
                                            "model_provider": "ark-agent-plan"})
    assert r.status_code == 400 and "没有" in r.json()["detail"]


def test_思考深度与重新体检(client, service):
    client.post(BASE + "/providers", json={"template": "ark-agent-plan"})
    client.post(BASE + "/providers/ark-agent-plan/key", json={"api_key": "k"})

    assert client.post(BASE + "/config", json={"thinking_level": "deep"}).status_code == 200
    assert client.get(BASE + "/status").json()["thinking_level"] == "deep"
    assert client.post(BASE + "/config", json={"thinking_level": "乱写"}).status_code == 400

    r = client.post(BASE + "/health/recheck")
    assert r.status_code == 200 and r.json()["running"] is True
    service.health_recheck_done.wait(2)


def test_取Key明文接口_绝不进状态回包(client):
    client.post(BASE + "/providers", json={"template": "deepseek"})
    client.post(BASE + "/providers/deepseek/key", json={"api_key": "sk-123"})
    assert client.get(BASE + "/providers/deepseek/key").json() == {"api_key": "sk-123"}
    assert "sk-123" not in client.get(BASE + "/status").text
