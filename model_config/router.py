"""FastAPI 路由（挂到任意 FastAPI / Starlette 应用上）。

    from model_config import ModelConfigService, ModelConfigStore, create_router
    service = ModelConfigService(ModelConfigStore("data/model_config.json"))
    app.include_router(create_router(service), prefix="/api/model-config")

前端组件默认也走 `/api/model-config` 这组地址；换前缀时给组件加
`api-base="/你的前缀"`。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .service import ModelConfigService, ServiceError


class ProviderCreateIn(BaseModel):
    template: str | None = None
    name: str | None = None
    base_url: str | None = None


class ProviderPatchIn(BaseModel):
    name: str | None = None
    base_url: str | None = None
    enabled: bool | None = None


class ProviderKeyIn(BaseModel):
    api_key: str


class ProviderTestIn(BaseModel):
    api_key: str | None = None
    model: str | None = None


class ModelIn(BaseModel):
    model: str


class ModelRenameIn(BaseModel):
    model: str
    new_model: str


class ModelToggleIn(BaseModel):
    model: str
    enabled: bool


class ModelTestIn(BaseModel):
    model: str
    api_key: str | None = None


class ConfigIn(BaseModel):
    model_auto: bool | None = None
    model: str | None = None
    model_provider: str | None = None
    thinking_level: str | None = None


def _fail(e: ServiceError) -> HTTPException:
    return HTTPException(e.status, e.message)


def create_router(service: ModelConfigService, prefix: str = "") -> APIRouter:
    """建路由。prefix 只是给文档看的（真正的前缀在 include_router 时给）。"""
    router = APIRouter()

    @router.get("/status")
    def status() -> dict:
        return service.status()

    # ---------- 供应商 ----------

    @router.post("/providers")
    def create_provider(body: ProviderCreateIn) -> dict:
        try:
            provider = service.create_provider(
                template=body.template or "",
                name=body.name or "",
                base_url=body.base_url or "",
            )
        except ServiceError as e:
            raise _fail(e)
        return {"ok": True, "provider": provider}

    @router.patch("/providers/{instance_id}")
    def update_provider(instance_id: str, body: ProviderPatchIn) -> dict:
        try:
            provider, recheck = service.update_provider(
                instance_id,
                name=body.name,
                base_url=body.base_url,
                enabled=body.enabled,
            )
        except ServiceError as e:
            raise _fail(e)
        if recheck:
            service.recheck_health()
        return {"ok": True, "provider": provider}

    @router.delete("/providers/{instance_id}")
    def delete_provider(instance_id: str) -> dict:
        try:
            service.delete_provider(instance_id)
        except ServiceError as e:
            raise _fail(e)
        service.recheck_health()
        return {"ok": True}

    # ---------- Key ----------

    @router.post("/providers/{instance_id}/key")
    def set_key(instance_id: str, body: ProviderKeyIn) -> dict:
        try:
            return service.set_key(instance_id, body.api_key)
        except ServiceError as e:
            raise _fail(e)

    @router.get("/providers/{instance_id}/key")
    def get_key(instance_id: str) -> dict:
        try:
            return {"api_key": service.get_key(instance_id)}
        except ServiceError as e:
            raise _fail(e)

    @router.post("/providers/{instance_id}/test")
    def test_provider(instance_id: str, body: ProviderTestIn) -> dict:
        try:
            return service.test_provider(
                instance_id, api_key=body.api_key, model=body.model or ""
            )
        except ServiceError as e:
            raise _fail(e)

    # ---------- 模型清单 ----------

    @router.post("/providers/{instance_id}/models")
    def add_model(instance_id: str, body: ModelIn) -> dict:
        try:
            provider = service.add_model(instance_id, body.model)
        except ServiceError as e:
            raise _fail(e)
        return {"ok": True, "provider": provider}

    @router.patch("/providers/{instance_id}/models/enabled")
    def toggle_model(instance_id: str, body: ModelToggleIn) -> dict:
        try:
            provider = service.set_model_enabled(
                instance_id, body.model, body.enabled
            )
        except ServiceError as e:
            raise _fail(e)
        return {"ok": True, "provider": provider}

    @router.patch("/providers/{instance_id}/models")
    def rename_model(instance_id: str, body: ModelRenameIn) -> dict:
        try:
            provider = service.rename_model(instance_id, body.model, body.new_model)
        except ServiceError as e:
            raise _fail(e)
        return {"ok": True, "provider": provider}

    @router.delete("/providers/{instance_id}/models")
    def delete_model(instance_id: str, model: str) -> dict:
        try:
            service.delete_model(instance_id, model)
        except ServiceError as e:
            raise _fail(e)
        return {"ok": True}

    @router.post("/providers/{instance_id}/models/sync")
    def sync_models(instance_id: str) -> dict:
        try:
            return service.sync_models(instance_id)
        except ServiceError as e:
            raise _fail(e)

    @router.post("/providers/{instance_id}/models/test")
    def test_model(instance_id: str, body: ModelTestIn) -> dict:
        try:
            return service.test_model(
                instance_id, body.model, api_key=body.api_key
            )
        except ServiceError as e:
            raise _fail(e)

    # ---------- 当前生效模型 ----------

    @router.post("/config")
    def update_config(body: ConfigIn) -> dict:
        try:
            if body.thinking_level is not None:
                service.set_thinking(body.thinking_level)
            touched = (
                body.model_auto is not None
                or body.model is not None
                or body.model_provider is not None
            )
            if not touched:
                return {"ok": True}
            if body.model_auto:
                chosen, model = service.choose_auto()
                return {
                    "ok": True,
                    "model": model,
                    "model_provider": chosen,
                    "model_verified": bool(service.model_state["verified"]),
                }
            return service.choose_model(
                body.model_provider or "", body.model or ""
            )
        except ServiceError as e:
            raise _fail(e)

    @router.post("/health/recheck")
    def recheck_health() -> dict:
        service.recheck_health()
        return {"ok": True, "running": True}

    return router
