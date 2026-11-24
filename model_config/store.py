"""模型配置的落盘存储。

只保存「模型配置」这一块，不掺宿主软件自己的字段：

    {
      "provider_instances": [ {供应商实例}, … ],
      "model": "现在生效的模型名",
      "model_provider": "归属的供应商实例 id",
      "model_auto": true,
      "thinking_level": "auto",
      "ark_api_key": "…",            ← 以下是老版单家平铺字段，仅作搬家来源/回滚镜像
      "ark_base_url": "…",
      "deepseek_api_key": "…",
      "kimi_api_key": "…",
      "providers": { "…": {"api_key": "…", "enabled": true} }
    }

- 默认写到 `data/model_config.json`，路径可配；
- 原子写（先写 .tmp 再替换），断电不写坏原文件；
- 读的时候缺字段补默认值，老配置（平铺字段）自动搬成实例清单；
- 文件里有 Key：这个文件不要提交到 git（见 .gitignore）。
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .registry import ARK_API_URL, ensure_provider_instances

DEFAULT_MODEL = "doubao-seed-2-1-pro-260628"
THINKING_LEVELS = ("off", "auto", "deep")


@dataclass
class ModelConfig:
    # None = 还没初始化：首次加载时按下面的老字段搬一次家
    provider_instances: list[dict] | None = None
    # ---- 老版单家平铺字段：只作搬家来源与回滚镜像，软件自己不再读它们 ----
    ark_api_key: str = ""
    ark_base_url: str = ARK_API_URL
    deepseek_api_key: str = ""
    kimi_api_key: str = ""
    providers: dict[str, dict] = field(default_factory=dict)
    # ---- 当前生效的模型 ----
    model: str = DEFAULT_MODEL
    model_provider: str = ""
    model_auto: bool = True
    # 与模型一起落盘的思考深度（"off" / "auto" / "deep"）：本模块只负责存，
    # 具体怎么翻成请求参数由宿主软件决定；不用这个功能可以忽略。
    thinking_level: str = "auto"

    def to_dict(self) -> dict:
        return asdict(self)


class ModelConfigStore:
    """配置文件的读写口。线程安全：读改写用同一把锁。"""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    def load(self) -> ModelConfig:
        with self._lock:
            if not self.path.exists():
                cfg = ModelConfig(provider_instances=[])
                ensure_provider_instances(cfg)
                return cfg
            data = json.loads(self.path.read_text(encoding="utf-8"))
            known = {f.name for f in fields(ModelConfig)}
            cfg = ModelConfig(**{k: v for k, v in data.items() if k in known})
            ensure_provider_instances(cfg)
            return cfg

    def save(self, cfg: ModelConfig) -> Path:
        with self._lock:
            ensure_provider_instances(cfg)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(
                json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self.path)  # 原子替换
            return self.path

    # 便捷包一层：读 → 改 → 写，整段持锁（宿主传进来的回调里改 cfg 即可）
    def update(self, mutator) -> ModelConfig:
        with self._lock:
            cfg = self.load()
            mutator(cfg)
            self.save(cfg)
            return cfg
