import json

import pytest

from model_config.registry import (
    ARK_AGENT_URL,
    ARK_API_URL,
    ARK_CODING_URL,
    TEMPLATES,
    add_instance,
    add_instance_model,
    catalog_templates,
    ensure_provider_instances,
    get_instance,
    instance_api_key,
    instance_base_url,
    instance_model_ids,
    new_instance,
    remove_instance,
    remove_instance_model,
    rename_instance_model,
    set_instance_key,
    set_instance_model_enabled,
    template_of,
)
from model_config.store import ModelConfig, ModelConfigStore


def test_目录只列五家_方舟三条线各带自己的地址与模型清单():
    ids = [t.template_id for t in catalog_templates()]
    assert ids == ["ark-api", "ark-coding-plan", "ark-agent-plan", "deepseek", "openai"]
    assert TEMPLATES["ark-api"].base_url == ARK_API_URL == "https://ark.cn-beijing.volces.com/api/v3"
    assert TEMPLATES["ark-coding-plan"].base_url == ARK_CODING_URL
    assert TEMPLATES["ark-agent-plan"].base_url == ARK_AGENT_URL
    # 套餐没有在线模型列表，模型靠手动加
    for tid in ("ark-coding-plan", "ark-agent-plan"):
        assert TEMPLATES[tid].supports_model_list is False
        assert TEMPLATES[tid].probe_model
    # 隐藏模板不进目录，但认得出模板
    assert "kimi" not in ids and TEMPLATES["kimi"].in_catalog is False
    assert template_of("kimi") is TEMPLATES["kimi"]


def test_模板地址钉死_v3结尾(): 
    for tid in ("ark-api", "ark-coding-plan", "ark-agent-plan"):
        assert TEMPLATES[tid].base_url.endswith("/v3")


def test_新实例带出默认名字地址与模型清单():
    inst = new_instance("ark-agent-plan", set())
    assert inst["id"] == "ark-agent-plan"
    assert inst["name"] == "火山方舟 Agent Plan"
    assert inst["base_url"] == ""  # 留空 = 跟模板默认走
    assert instance_base_url(inst) == ARK_AGENT_URL
    assert instance_model_ids(inst) == ["doubao-seed-2.1-pro", "doubao-seed-2.1-lite"]
    assert inst["format"] == "openai" and inst["enabled"] is True


def test_同模板第二条起加序号_自定义供应商要有名字地址():
    cfg = ModelConfig(provider_instances=[])
    add_instance(cfg, new_instance("ark-agent-plan", set()))
    second = new_instance("ark-agent-plan", {"ark-agent-plan"})
    assert second["id"] == "ark-agent-plan-2"
    custom = new_instance("", set(), name="我的中转站", base_url="https://proxy.example.com/v1")
    assert custom["id"] == "custom"
    assert custom["template"] == "" and custom["models"] == []


def test_模型开关改名删除_锁定跟着回落():
    cfg = ModelConfig(
        provider_instances=[new_instance("ark-agent-plan", set(), api_key="k")],
        model="doubao-seed-2.1-pro", model_provider="ark-agent-plan", model_auto=False,
    )
    ensure_provider_instances(cfg)
    assert set_instance_model_enabled(cfg, "ark-agent-plan", "doubao-seed-2.1-pro", False)
    assert cfg.model_auto is True  # 关掉正被指定的模型 = 回自动

    cfg.model_auto, cfg.model = False, "doubao-seed-2.1-lite"
    assert rename_instance_model(cfg, "ark-agent-plan", "doubao-seed-2.1-lite", "lite-2")
    assert cfg.model == "lite-2"  # 锁定跟着改名
    assert rename_instance_model(cfg, "ark-agent-plan", "lite-2", "doubao-seed-2.1-pro") is False  # 重名
    assert remove_instance_model(cfg, "ark-agent-plan", "lite-2")
    assert cfg.model_auto is True


def test_添加模型不重复_Key与开关读写():
    cfg = ModelConfig(provider_instances=[new_instance("deepseek", set())])
    entry = add_instance_model(cfg, "deepseek", "  extra-model ")
    assert entry == {"id": "extra-model", "enabled": True}
    again = add_instance_model(cfg, "deepseek", "extra-model")
    assert again["id"] == "extra-model"  # 已有了：原样返回那条，不重复
    assert len(get_instance(cfg, "deepseek")["models"]) == 3
    assert set_instance_key(cfg, "deepseek", "  sk-1 ") is not None
    assert instance_api_key(get_instance(cfg, "deepseek")) == "sk-1"
    assert set_instance_key(cfg, "ghost", "x") is None
    assert remove_instance(cfg, "ghost") is False


def test_老配置搬家_平铺字段变实例_Key开关与锁定都不丢(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "ark_api_key": " sk-ark ",
        "ark_base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "deepseek_api_key": "sk-ds",
        "kimi_api_key": "",
        "model": "doubao-seed-2-1-pro-260628",
        "model_provider": "ark",
        "model_auto": False,
        "providers": {"deepseek": {"api_key": "sk-ds", "enabled": False}},
    }), encoding="utf-8")

    cfg = ModelConfigStore(path).load()
    assert [(i["id"], i["template"]) for i in cfg.provider_instances] == [
        ("ark-agent-plan", "ark-agent-plan"), ("deepseek", "deepseek"),
    ]
    ark = get_instance(cfg, "ark-agent-plan")
    assert instance_api_key(ark) == "sk-ark"
    assert instance_base_url(ark) == ARK_AGENT_URL
    # 老配置锁的是带日期的模型名：补进清单首位，锁定不丢
    assert instance_model_ids(ark)[0] == "doubao-seed-2-1-pro-260628"
    assert cfg.model_provider == "ark-agent-plan" and cfg.model_auto is False
    assert get_instance(cfg, "deepseek")["enabled"] is False


def test_手改坏的数据被丢弃_模板按id认回来(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({
        "provider_instances": [
            {"id": "ark-agent-plan-2", "template": "写错了", "api_key": "k"},
            {"id": "ark-agent-plan-2", "api_key": "重复id"},
            "垃圾",
            {"id": "", "api_key": "没id"},
        ]
    }), encoding="utf-8")
    cfg = ModelConfigStore(path).load()
    assert [i["id"] for i in cfg.provider_instances] == ["ark-agent-plan-2"]
    inst = cfg.provider_instances[0]
    assert inst["template"] == "ark-agent-plan"  # 按 id 认回模板
    assert inst["name"] == "火山方舟 Agent Plan"
    assert instance_model_ids(inst)  # 缺 models 键：补回模板默认清单


def test_保存回读一致_旧字段镜像同步(tmp_path):
    path = tmp_path / "config.json"
    store = ModelConfigStore(path)
    cfg = store.load()
    add_instance(cfg, new_instance("deepseek", set(), api_key="sk-1"))
    store.save(cfg)

    again = store.load()
    assert instance_api_key(get_instance(again, "deepseek")) == "sk-1"
    on_disk = json.loads(path.read_text(encoding="utf-8"))
    assert on_disk["deepseek_api_key"] == "sk-1"  # 回滚镜像
    assert on_disk["provider_instances"][0]["api_key"] == "sk-1"


def test_存储原子写_损坏的JSON不会留下半个文件(tmp_path):
    path = tmp_path / "config.json"
    store = ModelConfigStore(path)
    cfg = store.load()
    store.save(cfg)
    assert path.exists() and not path.with_name("config.json.tmp").exists()
