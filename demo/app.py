"""模型配置模块 · 独立演示。

运行：
    pip install -r requirements.txt
    python demo/app.py
然后打开 http://127.0.0.1:8765

配置会写到 demo/data/model_config.json（含 API Key，已被 .gitignore 忽略）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from model_config import ModelConfigService, ModelConfigStore, create_router  # noqa: E402

app = FastAPI(title="模型配置模块 Demo")

service = ModelConfigService(
    ModelConfigStore(ROOT / "demo" / "data" / "model_config.json"),
    auto_start=True,  # 启动后台体检（没配 Key 时不发网络请求）
)

app.include_router(create_router(service), prefix="/api/model-config")
app.mount("/static/ui", StaticFiles(directory=ROOT / "ui"), name="ui")


@app.get("/")
def index():
    return FileResponse(ROOT / "demo" / "index.html")


@app.get("/api/demo/current")
def demo_current():
    """演示宿主软件怎么拿「现在生效的模型」。"""
    provider_id, model = service.current()
    return {
        "provider": provider_id,
        "model": model,
        "auto": bool(service.cfg.model_auto),
        "verified": bool(service.model_state["verified"]),
        "thinking_level": service.cfg.thinking_level,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
