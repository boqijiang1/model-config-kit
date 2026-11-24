"""供应商模板与实例清单。

两层结构：
- **模板（TEMPLATES）**：内置的供应商种类（火山方舟三条线 / DeepSeek / OpenAI，
  外加只给老配置搬家用的隐藏模板）——带默认接口地址、领 Key 的网址、默认模型
  清单，以及这家特有的调用习惯；
- **实例（ModelConfig.provider_instances）**：用户清单里的一条：
  `{id, template, name, base_url, format, api_key, enabled, models[]}`。
  同一种模板可以加多条；`template` 留空 = 用户自建供应商。

本模块是实例清单的唯一读写口径：业务层、执行链路、保存都从这里取，别绕过它
直接改 cfg.provider_instances。

地址纪律：火山方舟三条线的 OpenAI 协议地址都带 `/v3`——裸的 `/api/plan`、
`/api/coding` 是 Anthropic 协议工具用的；两种订阅套餐都没有在线模型列表
（GET /models 实测 404，与 Key 对错无关），模型靠用户手动加。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .store import ModelConfig

API_FORMAT = "openai"

# ---- 火山方舟三条线的 OpenAI 协议地址 ----
ARK_API_URL = "https://ark.cn-beijing.volces.com/api/v3"  # 按量计费
ARK_CODING_URL = "https://ark.cn-beijing.volces.com/api/coding/v3"  # Coding Plan
ARK_AGENT_URL = "https://ark.cn-beijing.volces.com/api/plan/v3"  # Agent Plan

_THINKING_SWITCH = {
    "off": {"thinking": {"type": "disabled"}},
    "deep": {"thinking": {"type": "enabled"}},
}
_PLAN_PROBE_MODEL = "doubao-seed-2.1-pro"


@dataclass(frozen=True)
class TemplateInfo:
    template_id: str
    label: str
    base_url: str
    key_url: str
    models: tuple[str, ...]
    in_catalog: bool = True
    logo: str = ""
    hint: str = ""
    supports_model_list: bool = True
    probe_model: str = ""
    # 随每次对话请求附带的家级默认参数（并入 payload，调用级 opts 可覆盖）
    request_extra: dict = field(default_factory=dict)
    # 思考深度的参数形状：{"off": {...}, "deep": {...}}，auto 不传
    thinking_extras: dict[str, dict] = field(default_factory=dict)
    max_tokens_cap: int = 16384
    # 请求参数习惯：chat = 标准 OpenAI 兼容；openai-reasoning = 推理系模型
    param_style: str = "chat"


_TEMPLATES: tuple[TemplateInfo, ...] = (
    TemplateInfo(
        template_id="ark-api",
        label="火山方舟 API",
        base_url=ARK_API_URL,
        key_url="https://ark.volcengine.com/region:cn-beijing/apikey",
        models=(
            "doubao-seed-2-1-pro-260628",
            "doubao-seed-2-1-pro-260915",
            "doubao-seed-2-1-turbo-260628",
            "doubao-seed-2-1-lite-260915",
        ),
        logo="ark",
        hint="按量计费：用多少付多少",
        thinking_extras=_THINKING_SWITCH,
        max_tokens_cap=32768,
    ),
    TemplateInfo(
        template_id="ark-coding-plan",
        label="火山方舟 Coding Plan",
        base_url=ARK_CODING_URL,
        key_url="https://ark.volcengine.com/region:cn-beijing",
        models=("doubao-seed-2.1-pro", "doubao-seed-2.1-lite"),
        logo="ark",
        hint="订阅套餐：走 Coding Plan 的额度",
        supports_model_list=False,
        probe_model=_PLAN_PROBE_MODEL,
        thinking_extras=_THINKING_SWITCH,
        max_tokens_cap=32768,
    ),
    TemplateInfo(
        template_id="ark-agent-plan",
        label="火山方舟 Agent Plan",
        base_url=ARK_AGENT_URL,
        key_url="https://ark.volcengine.com/region:cn-beijing",
        models=("doubao-seed-2.1-pro", "doubao-seed-2.1-lite"),
        logo="ark",
        hint="订阅套餐：走 Agent Plan 的额度",
        supports_model_list=False,
        probe_model=_PLAN_PROBE_MODEL,
        thinking_extras=_THINKING_SWITCH,
        max_tokens_cap=32768,
    ),
    TemplateInfo(
        template_id="deepseek",
        label="DeepSeek",
        base_url="https://api.deepseek.com",
        key_url="https://platform.deepseek.com/api_keys",
        models=("deepseek-flash", "deepseek-v4-pro"),
        logo="deepseek",
        hint="按量计费：用多少付多少",
        # 思考默认关：该家默认开思考，思考与正文共享 max_tokens，正文会被挤没
        request_extra={"thinking": {"type": "disabled"}},
        thinking_extras=_THINKING_SWITCH,
    ),
    TemplateInfo(
        template_id="openai",
        label="OpenAI",
        base_url="https://api.openai.com/v1",
        key_url="https://platform.openai.com/api-keys",
        models=("gpt-5.6", "gpt-5.4", "gpt-5.4-mini"),
        logo="openai",
        hint="按量计费：用多少付多少",
        param_style="openai-reasoning",
    ),
    # ---- 隐藏模板：只给老配置搬家用（不进「添加供应商」目录） ----
    TemplateInfo(
        template_id="kimi",
        label="Kimi 官方",
        base_url="https://api.moonshot.cn/v1",
        key_url="https://platform.moonshot.cn/console/api-keys",
        models=("kimi-k3.1-pro",),
        in_catalog=False,
    ),
    TemplateInfo(
        template_id="zhipu",
        label="智谱开放平台",
        base_url="https://open.bigmodel.cn/api/paas/v4",
        key_url="https://open.bigmodel.cn/usercenter/apikeys",
        models=("glm-5.3",),
        in_catalog=False,
        supports_model_list=False,
        probe_model="glm-5.3",
        thinking_extras=_THINKING_SWITCH,
    ),
    TemplateInfo(
        template_id="minimax",
        label="MiniMax 开放平台",
        base_url="https://api.minimaxi.com/v1",
        key_url="https://platform.minimaxi.com/user-center/basic-information/interface-key",
        models=("MiniMax-M3",),
        in_catalog=False,
    ),
    TemplateInfo(
        template_id="dashscope",
        label="阿里云百炼",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        key_url="https://bailian.console.aliyun.com/?apiKey=1",
        models=("qwen4-max",),
        in_catalog=False,
    ),
    TemplateInfo(
        template_id="tencent-tokenhub",
        label="腾讯 TokenHub",
        base_url="https://tokenhub.tencentmaas.com/v1",
        key_url="https://tokenhub.tencentmaas.com/console/api-keys",
        models=("hy4",),
        in_catalog=False,
    ),
)

TEMPLATES: dict[str, TemplateInfo] = {t.template_id: t for t in _TEMPLATES}
ARK_TEMPLATE_IDS = frozenset(
    t.template_id for t in _TEMPLATES if t.template_id.startswith("ark-")
)

_LEGACY_KEY_FIELDS = {
    "ark": "ark_api_key",
    "deepseek": "deepseek_api_key",
    "kimi": "kimi_api_key",
}
_LEGACY_ARK_URL_TEMPLATE = {
    "": "ark-api",
    ARK_API_URL: "ark-api",
    ARK_CODING_URL: "ark-coding-plan",
    ARK_AGENT_URL: "ark-agent-plan",
}

LEGACY_LABELS: dict[str, str] = {
    "ark": "火山方舟（豆包）",
    "deepseek": "DeepSeek 官方",
    "kimi": "Kimi 官方",
    "zhipu": "智谱开放平台",
    "minimax": "MiniMax 开放平台",
    "dashscope": "阿里云百炼",
    "tencent-tokenhub": "腾讯 TokenHub",
}


def catalog_templates() -> list[TemplateInfo]:
    """「添加供应商」目录里的模板（按注册顺序）。"""
    return [t for t in _TEMPLATES if t.in_catalog]


def template_of(instance_id: str) -> TemplateInfo | None:
    """按实例 id 认模板：id = 模板 id 或 模板 id-序号。认不出回 None。"""
    tid = (instance_id or "").strip()
    if tid == "ark":
        return TEMPLATES["ark-api"]
    if tid in TEMPLATES:
        return TEMPLATES[tid]
    head, _, tail = tid.rpartition("-")
    if head and tail.isdigit():
        return TEMPLATES.get(head)
    return None


def instance_template(inst: dict) -> TemplateInfo | None:
    return TEMPLATES.get(inst.get("template") or "")


# ---------- 实例清单读写（唯一口径） ----------


def instance_list(cfg: "ModelConfig") -> list[dict]:
    ensure_provider_instances(cfg)
    return cfg.provider_instances


def get_instance(cfg: "ModelConfig", instance_id: str) -> dict | None:
    return _find(instance_list(cfg), instance_id)


def _find(instances: list[dict], instance_id: str) -> dict | None:
    for inst in instances:
        if inst.get("id") == instance_id:
            return inst
    return None


def instance_base_url(inst: dict) -> str:
    """实例实际使用的接口地址：自己填了的以填的为准，留空跟模板默认。"""
    filled = (inst.get("base_url") or "").strip()
    if filled:
        return filled
    tpl = instance_template(inst) or template_of(inst.get("id", ""))
    return tpl.base_url if tpl else ""


def instance_api_key(inst: dict) -> str:
    return (inst.get("api_key") or "").strip()


def instance_enabled(inst: dict) -> bool:
    return bool(inst.get("enabled", True))


def instance_models(inst: dict) -> list[dict]:
    return [
        {"id": m["id"], "enabled": bool(m.get("enabled", True))}
        for m in inst.get("models") or []
        if isinstance(m, dict) and (m.get("id") or "").strip()
    ]


def instance_model_ids(inst: dict, only_enabled: bool = False) -> list[str]:
    return [
        m["id"] for m in instance_models(inst) if m["enabled"] or not only_enabled
    ]


def usable_instances(cfg: "ModelConfig") -> list[dict]:
    """能用的实例：开关打开且填了 Key。"""
    return [
        inst
        for inst in instance_list(cfg)
        if instance_enabled(inst) and instance_api_key(inst)
    ]


def has_any_key(cfg: "ModelConfig") -> bool:
    return any(instance_api_key(inst) for inst in instance_list(cfg))


def next_instance_id(template_id: str, taken: set[str]) -> str:
    stem = template_id or "custom"
    if stem not in taken:
        return stem
    n = 2
    while f"{stem}-{n}" in taken:
        n += 1
    return f"{stem}-{n}"


def new_instance(
    template_id: str = "",
    taken: set[str] | None = None,
    *,
    name: str = "",
    base_url: str = "",
    api_key: str = "",
) -> dict:
    """造一条新实例：目录模板带出默认名字/地址/模型清单；自建供应商要名字和
    地址，模型清单先空着、由用户添加。"""
    tpl = TEMPLATES.get((template_id or "").strip()) if template_id else None
    label = (name or "").strip() or (tpl.label if tpl else "自定义供应商")
    return {
        "id": next_instance_id(tpl.template_id if tpl else "", taken or set()),
        "template": tpl.template_id if tpl else "",
        "name": label,
        "base_url": (base_url or "").strip(),
        "format": API_FORMAT,
        "api_key": (api_key or "").strip(),
        "enabled": True,
        "models": [{"id": m, "enabled": True} for m in tpl.models] if tpl else [],
    }


def add_instance(cfg: "ModelConfig", inst: dict) -> dict:
    instance_list(cfg).append(inst)
    _sync_legacy_mirrors(cfg)
    return inst


def remove_instance(cfg: "ModelConfig", instance_id: str) -> bool:
    """删掉一条实例。它正被锁定使用时回到自动模式。"""
    instances = instance_list(cfg)
    inst = _find(instances, instance_id)
    if inst is None:
        return False
    instances.remove(inst)
    if cfg.model_provider == instance_id and not cfg.model_auto:
        cfg.model_auto = True
    _sync_legacy_mirrors(cfg)
    return True


def set_instance_key(cfg: "ModelConfig", instance_id: str, key: str) -> dict | None:
    inst = get_instance(cfg, instance_id)
    if inst is None:
        return None
    inst["api_key"] = (key or "").strip()
    _sync_legacy_mirrors(cfg)
    return inst


def add_instance_model(
    cfg: "ModelConfig", instance_id: str, model: str
) -> dict | None:
    """往这家的模型清单末尾加一个模型（已有了就原样返回，不重复）。"""
    inst = get_instance(cfg, instance_id)
    if inst is None:
        return None
    model = (model or "").strip()
    for m in inst["models"]:
        if m["id"] == model:
            return m
    entry = {"id": model, "enabled": True}
    inst["models"].append(entry)
    return entry


def remove_instance_model(
    cfg: "ModelConfig", instance_id: str, model: str
) -> bool:
    """从这家清单删掉一个模型。它正被锁定使用时回到自动模式。"""
    inst = get_instance(cfg, instance_id)
    if inst is None:
        return False
    for m in inst["models"]:
        if m["id"] == model:
            inst["models"].remove(m)
            if (
                cfg.model_provider == instance_id
                and cfg.model == model
                and not cfg.model_auto
            ):
                cfg.model_auto = True
            return True
    return False


def set_instance_model_enabled(
    cfg: "ModelConfig", instance_id: str, model: str, enabled: bool
) -> bool:
    """拨某个模型的开关：开 = 可以被自动选型挑中；关 = 跳过它（清单里留着）。
    它正被指定使用时关掉 = 回到自动模式。"""
    inst = get_instance(cfg, instance_id)
    if inst is None:
        return False
    for m in inst["models"]:
        if m["id"] == model:
            m["enabled"] = bool(enabled)
            if (
                not enabled
                and cfg.model_provider == instance_id
                and cfg.model == model
                and not cfg.model_auto
            ):
                cfg.model_auto = True
            return True
    return False


def rename_instance_model(
    cfg: "ModelConfig", instance_id: str, old: str, new: str
) -> bool:
    """改模型名字；正在锁定使用时锁定跟着改名。新名字空着或已被占用回 False。"""
    inst = get_instance(cfg, instance_id)
    new = (new or "").strip()
    if inst is None or not new:
        return False
    if any(m["id"] == new for m in inst["models"] if m["id"] != old):
        return False
    for m in inst["models"]:
        if m["id"] == old:
            m["id"] = new
            if (
                cfg.model_provider == instance_id
                and cfg.model == old
                and not cfg.model_auto
            ):
                cfg.model = new
            return True
    return False


def provider_labels(cfg: "ModelConfig") -> dict[str, str]:
    out = dict(LEGACY_LABELS)
    for inst in instance_list(cfg):
        out[inst["id"]] = inst["name"]
    return out


# ---------- 建档：校验、老配置搬家、回滚镜像 ----------


def ensure_provider_instances(cfg: "ModelConfig") -> None:
    """把实例清单整理成可信的形状（加载与保存共用这一份规则）。"""
    if cfg.provider_instances is None:
        cfg.provider_instances = _migrate_legacy(cfg)
    raw_list = cfg.provider_instances
    if not isinstance(raw_list, list):
        raw_list = []
    seen: set[str] = set()
    keep: list[dict] = []
    for raw in raw_list:
        inst = _normalize_instance(raw, seen)
        if inst is not None:
            keep.append(inst)
    cfg.provider_instances = keep
    # 锁定落空（实例被删 / 模型被删）：回自动，绝不留指向空处的锁定
    if not cfg.model_auto:
        inst = _find(keep, (cfg.model_provider or "").strip())
        if inst is None or not any(
            m["id"] == cfg.model for m in instance_models(inst)
        ):
            cfg.model_auto = True
    _sync_legacy_mirrors(cfg)


def _normalize_instance(raw: object, seen: set[str]) -> dict | None:
    """就地整理一条实例；不是字典 / 没有 id / id 重复的丢弃。"""
    if not isinstance(raw, dict):
        return None
    inst_id = str(raw.get("id") or "").strip()
    if not inst_id or inst_id in seen:
        return None
    # template 字段手改坏了但 id 还认得出模板：按 id 认回来
    tpl = TEMPLATES.get(str(raw.get("template") or "").strip()) or template_of(inst_id)
    models: list[dict] = []
    taken: set[str] = set()
    for m in raw.get("models") or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or "").strip()
        if mid and mid not in taken:
            taken.add(mid)
            models.append({"id": mid, "enabled": bool(m.get("enabled", True))})
    if "models" not in raw and tpl is not None:
        models = [{"id": m, "enabled": True} for m in tpl.models]
    base_url = str(raw.get("base_url") or "").strip()
    if tpl and base_url == tpl.base_url:
        base_url = ""  # 与模板默认一致 = 没手改过，留空跟着模板走
    clean = {
        "id": inst_id,
        "template": tpl.template_id if tpl else "",
        "name": str(raw.get("name") or "").strip()
        or (tpl.label if tpl else "自定义供应商"),
        "base_url": base_url,
        "format": API_FORMAT,
        "api_key": str(raw.get("api_key") or "").strip(),
        "enabled": bool(raw.get("enabled", True)),
        "models": models,
    }
    seen.add(inst_id)
    raw.clear()
    raw.update(clean)
    return raw


def _migrate_legacy(cfg: "ModelConfig") -> list[dict]:
    """老配置搬家：升级前的「一家一行写死在代码里」变成「一家一条实例」，
    Key、开关、锁定的模型一样不丢。没填 Key 的家不凭空建实例。"""
    records = cfg.providers if isinstance(cfg.providers, dict) else {}
    out: list[dict] = []
    taken: set[str] = set()

    def legacy_key(pid: str, field_name: str) -> str:
        legacy = str(getattr(cfg, field_name, "") or "").strip() if field_name else ""
        if legacy:
            return legacy
        rec = records.get(pid)
        return str(rec.get("api_key") or "").strip() if isinstance(rec, dict) else ""

    def legacy_enabled(pid: str) -> bool:
        rec = records.get(pid)
        if not isinstance(rec, dict) or "enabled" not in rec:
            return True
        return bool(rec["enabled"])

    def push(inst: dict) -> None:
        out.append(inst)
        taken.add(inst["id"])

    ark_key = legacy_key("ark", "ark_api_key")
    if ark_key:
        base = (getattr(cfg, "ark_base_url", "") or "").strip().rstrip("/")
        template_id = _LEGACY_ARK_URL_TEMPLATE.get(base, "ark-api")
        standard = base in _LEGACY_ARK_URL_TEMPLATE
        inst = new_instance(
            template_id,
            taken,
            base_url="" if standard else base,
            api_key=ark_key,
        )
        inst["enabled"] = legacy_enabled("ark")
        push(inst)
        if (cfg.model_provider or "").strip() in ("", "ark"):
            cfg.model_provider = inst["id"]

    for tpl in _TEMPLATES:
        if tpl.template_id in ARK_TEMPLATE_IDS:
            continue
        key = legacy_key(tpl.template_id, _LEGACY_KEY_FIELDS.get(tpl.template_id, ""))
        if not key:
            continue
        inst = new_instance(tpl.template_id, taken, api_key=key)
        inst["enabled"] = legacy_enabled(tpl.template_id)
        push(inst)
        if (cfg.model_provider or "").strip() == tpl.template_id:
            cfg.model_provider = inst["id"]

    # 锁定中的模型必须在这家的清单里（比如老配置锁的是带日期的版本号）
    model = (cfg.model or "").strip()
    owner = _find(out, (cfg.model_provider or "").strip())
    if owner is not None and model and not any(m["id"] == model for m in owner["models"]):
        owner["models"].insert(0, {"id": model, "enabled": True})
    return out


def _sync_legacy_mirrors(cfg: "ModelConfig") -> None:
    """旧 Key 字段镜像（回滚保险）：实例清单是唯一事实源，这里顺手把老字段
    同步成清单里第一条对应实例的值——万一回滚到旧版，Key 不会丢。"""
    instances = cfg.provider_instances if isinstance(cfg.provider_instances, list) else []

    def first(template_ids: set[str]) -> dict | None:
        for inst in instances:
            if isinstance(inst, dict) and inst.get("template") in template_ids:
                return inst
        return None

    ark = first(set(ARK_TEMPLATE_IDS))
    cfg.ark_base_url = instance_base_url(ark) if ark else ARK_API_URL
    mirror: dict[str, dict] = {}
    for legacy_id in _LEGACY_KEY_FIELDS:
        tpl_ids = set(ARK_TEMPLATE_IDS) if legacy_id == "ark" else {legacy_id}
        inst = first(tpl_ids)
        setattr(
            cfg,
            _LEGACY_KEY_FIELDS[legacy_id],
            instance_api_key(inst) if inst else "",
        )
        if inst is not None:
            mirror[legacy_id] = {
                "api_key": instance_api_key(inst),
                "enabled": instance_enabled(inst),
            }
    for legacy_id in ("zhipu", "minimax", "dashscope", "tencent-tokenhub"):
        inst = first({legacy_id})
        if inst is not None:
            mirror[legacy_id] = {
                "api_key": instance_api_key(inst),
                "enabled": instance_enabled(inst),
            }
    cfg.providers = mirror
