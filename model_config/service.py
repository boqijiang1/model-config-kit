"""模型配置业务层（与 Web 框架无关）。

对外主要入口（供路由层和宿主软件直接调用）：
- status()                          界面所需的全部状态
- create_provider / update_provider / delete_provider
- set_key / get_key / test_provider
- add_model / rename_model / delete_model / set_model_enabled / test_model
- sync_models
- choose_auto() / choose_model() / set_thinking()
- recheck_health()                  后台重跑体检
- build_current_provider()          宿主拿「现在生效的模型」发对话请求
- start() / stop()                  启动/停止后台体检线程

所有会发网络请求的方法都通过 self.transport（可注入假实现）——测试不联网。
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from . import connection
from .connection import ConnectionResult
from .providers import LlmProvider
from .registry import (
    ARK_TEMPLATE_IDS,
    API_FORMAT,
    LEGACY_LABELS,
    TEMPLATES,
    TemplateInfo,
    add_instance,
    add_instance_model,
    catalog_templates,
    get_instance,
    has_any_key,
    instance_api_key,
    instance_base_url,
    instance_enabled,
    instance_list,
    instance_model_ids,
    instance_models,
    instance_template,
    new_instance,
    provider_labels,
    remove_instance,
    remove_instance_model,
    rename_instance_model,
    set_instance_key,
    set_instance_model_enabled,
    usable_instances,
)
from .store import DEFAULT_MODEL, THINKING_LEVELS, ModelConfig, ModelConfigStore
from .transport import DefaultTransport, Transport

_LOGGER = logging.getLogger("model_config")

# Key 本身没错、只是被模型 / 额度 / 服务器挡下：Key 体检照样算过
_KEY_OK_CODES = ("model", "model_not_open", "quota", "server")


class ServiceError(Exception):
    """给用户看的大白话错误（status 默认 400）。"""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class NotFound(ServiceError):
    def __init__(self, message: str):
        super().__init__(message, 404)


def _clean_base_url(raw: str) -> str:
    """整理接口地址：去空白与末尾斜杠；整个 /chat/completions 贴进来的去掉。"""
    base = (raw or "").strip().rstrip("/")
    if base.lower().endswith("/chat/completions"):
        base = base[: -len("/chat/completions")].rstrip("/")
    if not base.lower().startswith(("http://", "https://")):
        raise ServiceError(
            "接口地址要以 http:// 或 https:// 开头，比如 https://api.deepseek.com"
        )
    if any(ch.isspace() for ch in base):
        raise ServiceError("接口地址里不能有空格：重新复制一遍再粘贴")
    return base


def _clean_model_name(raw: str) -> str:
    model = (raw or "").strip()
    if not model:
        raise ServiceError("模型名不能是空的：照平台上写的名字填")
    if any(ch.isspace() for ch in model):
        raise ServiceError("模型名中间不能有空格：照平台上写的名字重新复制一遍")
    return model


class ModelConfigService:
    def __init__(
        self,
        store: ModelConfigStore,
        *,
        transport: Transport | None = None,
        auto_start: bool = False,
        synchronous: bool = False,
    ):
        self.store = store
        self.transport: Transport = transport or DefaultTransport()
        self.cfg: ModelConfig = store.load()
        self.synchronous = synchronous  # True：体检在调用线程里跑（测试/脚本用）
        self._config_lock = threading.Lock()
        self._checks_lock = threading.Lock()
        # 当前生效模型是否真调验证过（界面 ✓已验证 的依据）；内存态
        self.model_state: dict[str, Any] = {"verified": False, "model_checks": {}}
        # 启动体检结果：state = pending / ok / manual_broken / all_down / none / no_model
        self.model_health: dict[str, Any] = {"state": "pending", "providers": []}
        self._recheck_state = threading.RLock()
        self._recheck_flags = {"running": False, "again": False}
        self.health_recheck_done = threading.Event()
        self.health_recheck_done.set()
        self.health_done = threading.Event()  # 启动体检完成（测试可等）
        self._started = False
        self._stopped = False
        if auto_start:
            self.start()

    # ---------- 生命周期 ----------

    def start(self) -> None:
        """启动后台体检（不阻塞）。重复调用无副作用。"""
        if self._started:
            return
        self._started = True
        if self.synchronous:
            try:
                self._startup_health_check()
            finally:
                self.health_done.set()
            return

        def run():
            try:
                self._startup_health_check()
            finally:
                self.health_done.set()

        threading.Thread(target=run, daemon=True, name="model-health").start()

    def stop(self) -> None:
        self._stopped = True

    # ---------- 存储 ----------

    def _save(self) -> None:
        self.store.save(self.cfg)

    def reload(self) -> None:
        """从磁盘重读配置（宿主在别的进程/工具里改过文件时用）。"""
        with self._config_lock:
            self.cfg = self.store.load()

    # ---------- 模型行实测凭据 ----------

    def _record_model_check(self, inst: dict, model: str, ok: bool) -> None:
        name = (model or "").strip()
        if not name:
            return
        with self._checks_lock:
            self.model_state["model_checks"][(inst["id"], name)] = bool(ok)

    def _forget_model_checks(self, instance_id: str, model: str | None = None) -> None:
        with self._checks_lock:
            checks = self.model_state["model_checks"]
            if model is None:
                for key in [k for k in checks if k[0] == instance_id]:
                    del checks[key]
            else:
                checks.pop((instance_id, (model or "").strip()), None)

    def _model_check_of(self, instance_id: str, model: str) -> bool | None:
        with self._checks_lock:
            return self.model_state["model_checks"].get((instance_id, model))

    # ---------- 取数口 ----------

    def _find(self, instance_id: str) -> dict | None:
        return get_instance(self.cfg, (instance_id or "").strip())

    def _tpl(self, inst: dict | None) -> TemplateInfo | None:
        return instance_template(inst) if inst else None

    def _resolve_instance(self, instance_id: str) -> dict | None:
        """按 id 找实例；老 id（「ark」等）认到搬家后同类的第一条实例上。"""
        inst = self._find(instance_id)
        if inst is not None:
            return inst
        legacy = (instance_id or "").strip()
        if legacy in LEGACY_LABELS:
            family = ARK_TEMPLATE_IDS if legacy == "ark" else {legacy}
            return next(
                (i for i in instance_list(self.cfg) if i.get("template") in family),
                None,
            )
        return None

    def _no_provider_message(self, instance_id: str) -> str:
        name = provider_labels(self.cfg).get(instance_id) or (instance_id or "这家")
        return f"供应商「{name}」已经不在了（被删除，或配置文件被改坏）：刷新页面看看。"

    def _probe_model(self, inst: dict, prefer: str = "") -> str:
        prefer = (prefer or "").strip()
        if prefer:
            return prefer
        ids = instance_model_ids(inst)
        if ids:
            return ids[0]
        tpl = self._tpl(inst)
        return tpl.probe_model if tpl else ""

    # ---------- 验证 ----------

    def _check_key(self, inst: dict, key: str, *, record: bool = True) -> ConnectionResult:
        """验证这家的 Key：有在线列表的拉列表；没有列表（订阅套餐）拿清单里
        第一个模型真调；拉不到列表再退到真调判一次。"""
        base = instance_base_url(inst)
        tpl = self._tpl(inst)
        if tpl is None or tpl.supports_model_list:
            listed = self.transport.check_provider_models(key, base, inst["name"])
            if listed.ok:
                return listed
        model = self._probe_model(inst)
        if model:
            result = self._verify_model(inst, key, model, record=record)
            if result.ok:
                return ConnectionResult(
                    True, "ok",
                    f"通了：这家的 Key 是好的（已按模型 {model} 实测对话成功）。",
                )
            if result.code in _KEY_OK_CODES:
                return ConnectionResult(
                    True, "ok",
                    f"Key 是好的，不过模型 {model} 现在调不通：{result.message}",
                )
            return result
        return ConnectionResult(
            False, "models_unavailable",
            f"{inst['name']}暂时验证不了：拉不到它的模型列表，清单里也没有模型"
            "可以试。先用「添加模型」给这家加一个模型，再保存 Key。",
        )

    def _verify_model(
        self, inst: dict, key: str, model: str, *, record: bool = True
    ) -> ConnectionResult:
        """一次极小真调验证指定模型。record=False：用输入框里还没保存的 Key
        测的结果，不标到已存的模型行上。"""
        result = self.transport.check_model(inst, key, model)
        if record:
            self._record_model_check(inst, model, result.ok)
        return result

    def _model_works(self, inst: dict, key: str, model: str) -> bool:
        ok = self.transport.check_model(inst, key, model).ok
        self._record_model_check(inst, model, ok)
        return ok

    def _key_works(self, inst: dict, key: str) -> bool:
        return self._check_key(inst, key).ok

    # ---------- 选型 ----------

    def _has_candidates(self) -> bool:
        return any(
            instance_model_ids(inst, only_enabled=True)
            for inst in usable_instances(self.cfg)
        )

    def _selected_pair(self) -> tuple[str, str]:
        inst = self._find(self.cfg.model_provider)
        if inst is not None and self.cfg.model in instance_model_ids(inst):
            return inst["id"], self.cfg.model
        return self._reselect_if_dangling()

    def _reselect_if_dangling(self) -> tuple[str, str]:
        record: dict = {}
        chosen, resolved = self._resolve_auto(record)
        with self._config_lock:
            self.cfg.model, self.cfg.model_provider = resolved, chosen
            self.model_state["verified"] = bool(record.get("verified"))
            self._save()
        return chosen, resolved

    def _resolve_auto(self, record: dict | None = None) -> tuple[str, str]:
        usable = usable_instances(self.cfg)
        by_id = {inst["id"]: inst for inst in usable}
        availability = {
            inst["id"]: instance_model_ids(inst, only_enabled=True) for inst in usable
        }
        probed: dict[tuple[str, str], bool] = {}

        def probe(pid: str, m: str) -> bool:
            ok = self._model_works(by_id[pid], instance_api_key(by_id[pid]), m)
            probed[(pid, m)] = ok
            return ok

        chosen = connection.pick_auto_model(availability, list(by_id), probe=probe)
        current = ((self.cfg.model_provider or "").strip(), (self.cfg.model or "").strip())
        if (
            chosen is not None
            and not probed.get(chosen)
            and current != chosen
            and current[0] in by_id
            and current[1] in availability.get(current[0], [])
        ):
            # 探测全失败（比如断网）：当前生效的还在候选里就不瞎换
            chosen = current
        if record is not None:
            record["verified"] = bool(chosen is not None and probed.get(chosen))
        return chosen if chosen is not None else ("", "")

    # ---------- 体检 ----------

    def _set_health(self, state: str, providers: list[dict]) -> None:
        with self._recheck_state:
            if self._recheck_flags["running"] and self._recheck_flags["again"]:
                return  # 这一轮是旧账，不落地
            self.model_health["providers"] = providers
            self.model_health["state"] = state

    def _startup_health_check(self) -> None:
        try:
            enabled = usable_instances(self.cfg)
            self.model_state["verified"] = False
            if not enabled:
                self._set_health("none", [])
                return
            rows: dict[str, dict] = {}
            state: str | None = None
            if self.cfg.model_auto:
                record: dict = {}
                chosen_pid, resolved = self._resolve_auto(record)
                if resolved:
                    model_changed = resolved != (self.cfg.model or "").strip()
                    provider_changed = (self.cfg.model_provider or "") != chosen_pid
                    if model_changed or provider_changed:
                        with self._config_lock:
                            self.cfg.model = resolved
                            self.cfg.model_provider = chosen_pid
                            self._save()
                    verified = bool(record.get("verified"))
                    self.model_state["verified"] = verified
                    rows[chosen_pid] = {"provider": chosen_pid, "ok": verified}
                    state = "ok" if verified else "all_down"
                else:
                    state = "all_down" if self._has_candidates() else "no_model"
            else:
                model = (self.cfg.model or "").strip()
                provider_id = (self.cfg.model_provider or "").strip()
                inst = self._find(provider_id)
                if inst is None or not instance_enabled(inst):
                    pass  # 锁定那家被关：按禁用跳过，交给下面的 Key 体检
                elif not model:
                    rows[provider_id] = {"provider": provider_id, "ok": False}
                    state = "manual_broken"
                else:
                    key = instance_api_key(inst)
                    if key:
                        result = self._verify_model(inst, key, model)
                        if result.ok:
                            self.model_state["verified"] = True
                            rows[provider_id] = {"provider": provider_id, "ok": True}
                            state = "ok"
                        else:
                            rows[provider_id] = {"provider": provider_id, "ok": False}
                            state = "manual_broken"
            for inst in enabled:
                if inst["id"] in rows:
                    continue
                rows[inst["id"]] = {
                    "provider": inst["id"],
                    "ok": self._key_works(inst, instance_api_key(inst)),
                }
            if state is None:
                state = "ok" if any(r["ok"] for r in rows.values()) else "all_down"
            self._set_health(
                state, [rows[inst["id"]] for inst in enabled if inst["id"] in rows]
            )
        except Exception as e:  # 体检尽力而为：失败不影响使用
            _LOGGER.warning("体检没跑成（不影响使用，保存设置时会再试）：%s", e)

    def recheck_health(self) -> None:
        """后台重跑一次体检：先标 pending，再开线程；同一时刻只跑一轮，跑着
        又来了新请求就记一笔「还要再跑」，保证最后落地的是最新配置。"""
        with self._recheck_state:
            self._recheck_flags["again"] = True
            self._set_health("pending", [])
            self.health_recheck_done.clear()
            if self._recheck_flags["running"]:
                return
            self._recheck_flags["running"] = True

        if self.synchronous:
            self._recheck_flags["again"] = False
            self._recheck_flags["running"] = False
            self._startup_health_check()
            self.health_recheck_done.set()
            return

        def run():
            while True:
                with self._recheck_state:
                    if not self._recheck_flags["again"]:
                        self._recheck_flags["running"] = False
                        self.health_recheck_done.set()
                        return
                    self._recheck_flags["again"] = False
                self._startup_health_check()

        threading.Thread(target=run, daemon=True, name="model-health-recheck").start()

    # ---------- 状态 ----------

    def _provider_json(self, inst: dict) -> dict:
        tpl = self._tpl(inst)
        return {
            "id": inst["id"],
            "name": inst["name"],
            "template": inst["template"],
            "logo": tpl.logo if tpl else "",
            "base_url": instance_base_url(inst),
            "base_url_custom": bool(inst.get("base_url")),
            "format": inst.get("format") or API_FORMAT,
            "enabled": instance_enabled(inst),
            "has_key": bool(instance_api_key(inst)),
            "key_url": tpl.key_url if tpl else "",
            "models": [
                {**m, "check": self._model_check_of(inst["id"], m["id"])}
                for m in instance_models(inst)
            ],
            "supports_model_list": tpl.supports_model_list if tpl else True,
        }

    def status(self) -> dict:
        with self._config_lock:
            selected = self._find(self.cfg.model_provider)
            return {
                "has_api_key": has_any_key(self.cfg),
                "enabled_providers": [i["id"] for i in usable_instances(self.cfg)],
                "providers": [self._provider_json(i) for i in instance_list(self.cfg)],
                "provider_labels": provider_labels(self.cfg),
                "catalog": [
                    {"template": t.template_id, "name": t.label,
                     "logo": t.logo, "hint": t.hint}
                    for t in catalog_templates()
                ],
                "model": self.cfg.model,
                "model_provider": selected["id"] if selected else "",
                "model_auto": bool(self.cfg.model_auto),
                "model_verified": bool(self.model_state["verified"]),
                "thinking_level": self.cfg.thinking_level,
                "health": {
                    "state": self.model_health["state"],
                    "providers": list(self.model_health["providers"]),
                },
            }

    # ---------- 供应商 CRUD ----------

    def create_provider(
        self, template: str = "", name: str = "", base_url: str = ""
    ) -> dict:
        with self._config_lock:
            taken = {inst["id"] for inst in instance_list(self.cfg)}
            template = (template or "").strip()
            if template:
                if template not in {t.template_id for t in catalog_templates()}:
                    raise NotFound(f"目录里没有这家供应商：{template}")
                inst = new_instance(template, taken)
            else:
                name = (name or "").strip()
                if not name:
                    raise ServiceError("先给这家供应商起个名字，比如「我的中转站」")
                inst = new_instance(
                    "", taken, name=name, base_url=_clean_base_url(base_url)
                )
            add_instance(self.cfg, inst)
            self._save()
            return self._provider_json(inst)

    def update_provider(
        self,
        instance_id: str,
        *,
        name: str | None = None,
        base_url: str | None = None,
        enabled: bool | None = None,
    ) -> tuple[dict, bool]:
        """改名字 / 地址 / 开关。回 (实例, 是否需要后台复检)。"""
        with self._config_lock:
            inst = self._find(instance_id)
            if inst is None:
                raise NotFound(self._no_provider_message(instance_id))
            recheck = False
            url_changed = False
            if name is not None:
                name = name.strip()
                if not name:
                    raise ServiceError("名字不能是空的")
                inst["name"] = name
            if base_url is not None:
                base = _clean_base_url(base_url)
                tpl = self._tpl(inst)
                base = "" if tpl and base == tpl.base_url else base
                url_changed = base != inst.get("base_url")
                recheck = recheck or url_changed
                inst["base_url"] = base
            if enabled is not None:
                recheck = recheck or bool(enabled) != instance_enabled(inst)
                inst["enabled"] = bool(enabled)
            if url_changed:
                self._forget_model_checks(instance_id)
            self._save()
            return self._provider_json(inst), recheck

    def delete_provider(self, instance_id: str) -> None:
        with self._config_lock:
            if not remove_instance(self.cfg, instance_id):
                raise NotFound(self._no_provider_message(instance_id))
            self._forget_model_checks(instance_id)
            self._save()

    # ---------- Key ----------

    def set_key(self, instance_id: str, api_key: str) -> dict:
        """填/换 Key：当场验证，通过才落盘；空串 = 清掉。"""
        inst = self._find(instance_id)
        if inst is None:
            raise NotFound(self._no_provider_message(instance_id))
        key = (api_key or "").strip()
        if not key:
            with self._config_lock:
                set_instance_key(self.cfg, instance_id, "")
                self._forget_model_checks(instance_id)
                self._save()
            self.recheck_health()
            return {"ok": True, "message": "已清掉这家的 Key。"}
        result = self._check_key(inst, key, record=False)
        if not result.ok:
            return {"ok": False, "code": result.code, "message": result.message}
        with self._config_lock:
            set_instance_key(self.cfg, instance_id, key)
            self._forget_model_checks(instance_id)
            self._save()
        self.recheck_health()
        return {"ok": True, "message": result.message}

    def get_key(self, instance_id: str) -> str:
        """已存的 Key 明文（本机单机界面点小眼睛时用；宿主可自行决定是否暴露）。"""
        with self._config_lock:
            inst = self._find(instance_id)
            if inst is None:
                raise NotFound(self._no_provider_message(instance_id))
            return instance_api_key(inst)

    def test_provider(self, instance_id: str, api_key: str | None = None,
                      model: str = "") -> dict:
        inst = self._find(instance_id)
        if inst is None:
            raise NotFound(self._no_provider_message(instance_id))
        key = instance_api_key(inst) if api_key is None else (api_key or "").strip()
        key = (key or "").strip()
        if not key:
            return {"ok": False, "code": "no_key",
                    "message": "还没有填写 API Key：先粘贴这家的 Key 再测。"}
        model = (model or "").strip()
        if model:
            result = self._verify_model(
                inst, key, model, record=(key == instance_api_key(inst))
            )
            if result.ok:
                result = ConnectionResult(
                    True, "ok",
                    f"通了：模型 {model} 在 {inst['name']} 上能正常对话。",
                )
        else:
            result = self._check_key(
                inst, key, record=(key == instance_api_key(inst))
            )
        return {"ok": result.ok, "code": result.code, "message": result.message}

    # ---------- 模型清单 ----------

    def add_model(self, instance_id: str, model: str) -> dict:
        with self._config_lock:
            inst = self._find(instance_id)
            if inst is None:
                raise NotFound(self._no_provider_message(instance_id))
            add_instance_model(self.cfg, instance_id, _clean_model_name(model))
            self._save()
            return self._provider_json(inst)

    def set_model_enabled(self, instance_id: str, model: str, enabled: bool) -> dict:
        with self._config_lock:
            inst = self._find(instance_id)
            if inst is None:
                raise NotFound(self._no_provider_message(instance_id))
            if not set_instance_model_enabled(
                self.cfg, instance_id, (model or "").strip(), bool(enabled)
            ):
                raise NotFound("这家清单里没有这个模型")
            self._save()
            payload = self._provider_json(inst)
        self.recheck_health()
        return payload

    def rename_model(self, instance_id: str, model: str, new_model: str) -> dict:
        with self._config_lock:
            inst = self._find(instance_id)
            if inst is None:
                raise NotFound(self._no_provider_message(instance_id))
            old = (model or "").strip()
            if not rename_instance_model(
                self.cfg, instance_id, old, _clean_model_name(new_model)
            ):
                raise ServiceError("这家清单里没有这个模型，或者新名字已经被别的模型用了")
            self._forget_model_checks(instance_id, old)
            self._save()
            return self._provider_json(inst)

    def delete_model(self, instance_id: str, model: str) -> None:
        with self._config_lock:
            if self._find(instance_id) is None:
                raise NotFound(self._no_provider_message(instance_id))
            if not remove_instance_model(self.cfg, instance_id, (model or "").strip()):
                raise NotFound("这家清单里没有这个模型")
            self._forget_model_checks(instance_id, model)
            self._save()
        self.recheck_health()

    def test_model(self, instance_id: str, model: str,
                   api_key: str | None = None) -> dict:
        inst = self._find(instance_id)
        if inst is None:
            raise NotFound(self._no_provider_message(instance_id))
        key = instance_api_key(inst) if api_key is None else (api_key or "").strip()
        key = (key or "").strip()
        if not key:
            return {"ok": False, "code": "no_key",
                    "message": "还没有填写 API Key：先粘贴这家的 Key 再测。"}
        result = self._verify_model(
            inst, key, (model or "").strip(), record=(key == instance_api_key(inst))
        )
        return {"ok": result.ok, "code": result.code, "message": result.message}

    def sync_models(self, instance_id: str) -> dict:
        """从账号拉模型列表，清单里没有的加到末尾。订阅套餐给大白话让人手动加。"""
        inst = self._find(instance_id)
        if inst is None:
            raise NotFound(self._no_provider_message(instance_id))
        name = inst["name"]
        tpl = self._tpl(inst)
        if tpl is not None and not tpl.supports_model_list:
            return {
                "ok": False, "added": [],
                "message": f"{name}是订阅套餐，不提供在线模型列表：请点「添加模型」手动加。",
            }
        key = instance_api_key(inst)
        if not key:
            return {
                "ok": False, "added": [],
                "message": "先把这家的 API Key 填好并验证通过，才能从账号同步模型。",
            }
        found = connection.chat_models(
            self.transport.list_models(key, instance_base_url(inst))
        )
        if not found:
            return {
                "ok": False, "added": [],
                "message": f"暂时拉不到{name}的模型列表（也可能是网络暂时不通）："
                "稍后再试，或者点「添加模型」手动加。",
            }
        added: list[str] = []
        with self._config_lock:
            existing = instance_model_ids(inst)
            for m in found:
                if m not in existing:
                    add_instance_model(self.cfg, instance_id, m)
                    added.append(m)
            self._save()
        return {"ok": True, "added": added}

    # ---------- 当前生效模型 ----------

    def choose_auto(self) -> tuple[str, str]:
        """回到自动挑选：按清单真调验证重选并落盘。回 (实例 id, 模型名)。"""
        self.cfg.model_auto = True
        chosen, resolved = self._reselect_if_dangling()
        return chosen, resolved

    def choose_model(self, instance_id: str, model: str) -> dict:
        """手动指定模型：必须在那家清单里且开关打开；有 Key 就当场真调验证，
        调不通不允许保存。"""
        model = (model or "").strip()
        instance_id = (instance_id or "").strip()
        if not model or not instance_id:
            raise ServiceError(
                "还没定下用哪个模型：打开清单里某个模型右边的开关，或点「自动」。"
            )
        inst = self._find(instance_id)
        if inst is None:
            raise ServiceError(self._no_provider_message(instance_id), 404)
        if model not in instance_model_ids(inst):
            raise ServiceError(
                f"「{inst['name']}」的模型清单里没有 {model}：先用「添加模型」把它加进去。"
            )
        if model not in instance_model_ids(inst, only_enabled=True):
            raise ServiceError(
                f"「{model}」右边的开关是关着的：先打开它，再指定用它。"
            )
        verified = False
        key = instance_api_key(inst)
        if key:
            result = self._verify_model(inst, key, model)
            if not result.ok:
                raise ServiceError(result.message)
            verified = True
        with self._config_lock:
            self.cfg.model_auto = False
            self.cfg.model = model
            self.cfg.model_provider = instance_id
            self.model_state["verified"] = verified
            self._save()
        self._refresh_health_after_save()
        notice = None
        if "doubao" not in model.lower():
            notice = "这个模型没跑过分镜任务，建议先拿一章试跑"
        return {
            "ok": True,
            "model_notice": notice,
            "model": model,
            "model_provider": instance_id,
            "model_verified": verified,
        }

    def set_thinking(self, level: str) -> None:
        if level not in THINKING_LEVELS:
            raise ServiceError(
                "思考深度只有三档：不思考、适当思考、深度思考；请在「模型」页重新选一下。"
            )
        with self._config_lock:
            self.cfg.thinking_level = level
            self._save()

    def _refresh_health_after_save(self) -> None:
        usable = usable_instances(self.cfg)
        if not usable:
            self._set_health("none", [])
            return
        prev = {d["provider"]: bool(d.get("ok")) for d in self.model_health["providers"]}
        rows = [
            {
                "provider": inst["id"],
                "ok": (
                    bool(self.model_state["verified"])
                    if inst["id"] == self.cfg.model_provider
                    else prev.get(inst["id"], False)
                ),
            }
            for inst in usable
        ]
        if self.model_state["verified"]:
            state = "ok"
        elif self.cfg.model_auto and not self._has_candidates():
            state = "no_model"
        elif any(r["ok"] for r in rows):
            state = "ok"
        else:
            state = "all_down"
        self._set_health(state, rows)

    # ---------- 给宿主软件用 ----------

    def current(self) -> tuple[str, str]:
        """现在生效的 (供应商 id, 模型名)；没有回 ("", "")。"""
        return self._selected_pair()

    def build_current_provider(self, **kwargs: Any) -> LlmProvider | None:
        """按现在生效的模型构建一个可直接 chat() 的客户端；没有可用模型回 None。

        宿主用法：
            provider = service.build_current_provider(timeout=300)
            reply = provider.chat([{"role": "user", "content": "..."}], {"max_tokens": 512})
        """
        pid, model = self._selected_pair()
        inst = self._find(pid)
        if inst is None or not model:
            return None
        key = instance_api_key(inst)
        if not key:
            return None
        return self.transport.build_provider(inst, model, key, **kwargs)

    def template_thinking_extras(self) -> dict[str, dict]:
        """当前生效模型所属模板的思考参数形状（宿主把 thinking_level 翻成请求参数用）。"""
        pid, _ = self._selected_pair()
        tpl = self._tpl(self._find(pid))
        return dict(tpl.thinking_extras) if tpl else {}

    def template_max_tokens_cap(self) -> int:
        pid, _ = self._selected_pair()
        tpl = self._tpl(self._find(pid))
        return tpl.max_tokens_cap if tpl else 16384
