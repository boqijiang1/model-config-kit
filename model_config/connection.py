"""连接自检与自动选型。

- 一次极小的真实请求（max_tokens=1）验证 Key 与模型可用；
- 拉模型列表验证 Key（有在线列表的平台）；
- 自动选型：按清单顺序逐个真调，第一个能回包的当选；
- 所有失败翻译成给非程序员看的大白话。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import httpx

from .providers import LlmProvider, Message, ProviderError

# 自动选型真调验证的候选上限（总数）：控制最坏耗时（每个候选 1 token）。
MAX_PROBES = 13

# 已停用的模型名，调了必然失败，绝不进候选
_RETIRED_MODELS = {"deepseek-chat", "deepseek-reasoner"}
_RETIRED_MODEL_PREFIXES = ("minimax-m2",)

# 不是文本对话类的模型（视频/图像/3D/向量/语音）：本模块只做对话
_NON_CHAT_TAGS = (
    "seedance", "seedream", "seed3d", "seed-3d", "embedding", "embed",
    "whisper", "tts", "audio", "image", "dall-e", "moderation",
    "transcri", "realtime", "rerank", "sora",
)


def _network_message(label: str) -> str:
    return f"连不上{label}的服务器，请检查这台电脑的网络后重试。"


def _auth_message(label: str) -> str:
    return (
        f"Key 无效：请到{label}的控制台重新复制一遍 API Key"
        "（注意别带上空格），再粘贴到这里。"
    )


def _is_retired(model: str) -> bool:
    low = model.lower()
    return model in _RETIRED_MODELS or low.startswith(_RETIRED_MODEL_PREFIXES)


def is_chat_model(model: str) -> bool:
    low = (model or "").lower()
    return bool(low) and not _is_retired(low) and not any(
        tag in low for tag in _NON_CHAT_TAGS
    )


def chat_models(available: list[str]) -> list[str]:
    """账号模型列表里能用来对话的模型：去重、滤掉非对话类与已停用的；
    pro 优先，组内与其余按字母倒序（版本号新的在前）。"""
    text = [m for m in dict.fromkeys(available) if is_chat_model(m)]
    return [m for m in text if "pro" in m.lower()][::-1] + sorted(
        (m for m in text if "pro" not in m.lower()), reverse=True
    )


def list_models(api_key: str, base_url: str) -> list[str]:
    """拉这个 Key 在该平台账号下可用的模型 ID。任何失败回空列表。"""
    if not api_key.strip():
        return []
    try:
        r = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            timeout=15,
        )
        if r.status_code != 200:
            return []
        return sorted(
            {m.get("id") for m in r.json().get("data", []) if m.get("id")}
        )
    except (httpx.HTTPError, OSError, ValueError):
        return []


def check_provider_models(
    api_key: str, base_url: str, provider_label: str = "供应商"
) -> ConnectionResult:
    """拉那家 GET /models 验 Key，结果翻成大白话。"""
    if not api_key.strip():
        return ConnectionResult(
            False, "no_key", "还没有填写 API Key：先粘贴这家的 Key 再测。"
        )
    try:
        r = httpx.get(
            f"{base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            timeout=15,
        )
    except (httpx.HTTPError, OSError):
        return ConnectionResult(False, "network", _network_message(provider_label))
    if r.status_code in (401, 403):
        return ConnectionResult(False, "auth", _auth_message(provider_label))
    if r.status_code == 200:
        try:
            ids = {m.get("id") for m in r.json().get("data", []) if m.get("id")}
        except ValueError:
            ids = set()
        if ids:
            return ConnectionResult(
                True, "ok",
                f"通了：这家的 Key 是好的，{provider_label}账号下能看到 "
                f"{len(ids)} 个模型。",
            )
    if r.status_code == 404:
        # 平台不提供在线列表，但能吃到 404 说明过了鉴权——不是 Key 错
        return ConnectionResult(
            True, "ok",
            f"通了：这家的 Key 是好的。不过{provider_label}暂不支持在线拉取"
            "模型列表，模型以后以平台控制台里的名字为准。",
        )
    return ConnectionResult(
        False, "models_unavailable",
        f"{provider_label}暂时拉不到模型列表（也可能是网络暂时不通），"
        "检查网络或 Key 后再试一次。",
    )


@dataclass
class ConnectionResult:
    """「测试连接」的结果。code 供程序判断，message 直接展示给用户。"""

    ok: bool
    code: str
    message: str


def _contains(text: str, *needles: str) -> bool:
    low = text.lower()
    return any(n.lower() in low for n in needles)


def _translate_provider_error(
    e: ProviderError, model: str, label: str = "供应商"
) -> ConnectionResult:
    """把供应商原始报错翻译成大白话。"""
    text = str(e)
    if _contains(
        text,
        "connecterror", "connecttimeout", "readtimeout", "writetimeout",
        "timed out", "timeout", "getaddrinfo", "name or service not known",
        "connection refused", "connection reset", "server disconnected",
        "网络", "积极拒绝", "远程主机",
    ):
        return ConnectionResult(False, "network", _network_message(label))
    if _contains(
        text, "401", "403", "authentication", "invalidapikey", "invalid api key",
        "鉴权", "密钥",
    ):
        return ConnectionResult(False, "auth", _auth_message(label))
    if _contains(text, "modelnotopen", "has not activated"):
        return ConnectionResult(
            False, "model_not_open",
            f"模型还没开通：{model} 这个名字没写错，但你的{label}账号没有开通它"
            f"（部分模型要订阅才能用）。两个办法任选：到{label}控制台把它开通；"
            "或者点「自动（推荐）」让软件换一个你已开通的模型。",
        )
    if _contains(
        text, "404", "modelnotfound", "does not exist", "not exist", "not found",
        "不存在", "模型",
    ):
        return ConnectionResult(
            False, "model",
            f"模型名可能不对：请到{label}控制台核对模型 ID 再填（现在填的是 {model}）。",
        )
    if _contains(text, "429", "quota", "arrearage", "额度", "欠费", "余额"):
        return ConnectionResult(
            False, "quota",
            f"这个 Key 的额度不够或者请求太频繁了：请到{label}控制台确认额度，"
            "稍等一会儿再测。",
        )
    if _contains(text, "500", "502", "503", "504"):
        return ConnectionResult(False, "server", f"{label}服务器这边暂时出问题了，稍等一会儿再测。")
    return ConnectionResult(False, "unknown", f"测试没通过：{text[:150]}")


def check_connection(
    provider: LlmProvider, *, model: str, provider_label: str = "供应商"
) -> ConnectionResult:
    """发一次极小的真实请求（max_tokens=1）：能正常回话即 Key 与模型都可用。"""
    try:
        reply = provider.chat(
            [Message(role="user", content="连接测试，收到请回复：好")],
            {"max_tokens": 1},
        )
    except ProviderError as e:
        return _translate_provider_error(e, model, provider_label)
    except (httpx.HTTPError, OSError) as e:
        return ConnectionResult(False, "network", f"{_network_message(provider_label)}（{e}）")
    except Exception as e:  # 兜底：意外错误也不让调用方拿到堆栈
        return ConnectionResult(False, "unknown", f"测试没走通：{e}")

    if reply and reply.content and reply.content.strip():
        return ConnectionResult(True, "ok", f"连接成功，模型 {model} 可以正常对话。")
    # 思考型模型会把仅有的 1 个 token 花在思考上、回复为空——能回包就是通
    return ConnectionResult(
        True, "ok",
        f"连接成功：模型 {model} 的通道是通的"
        "（测试请求只给 1 个字的空间，思考型模型可能不吐字）。",
    )


def pick_auto_model(
    availability: dict[str, list[str]],
    order: list[str],
    probe: Callable[[str, str], bool] | None = None,
) -> tuple[str, str] | None:
    """跨供应商自动选型：把候选排成一列，逐个真调验证。

    候选顺序 = 清单顺序逐家（order）× 家内模型清单顺序。第一个验证通过的
    当选；探测全失败或没传 probe 时回清单首选（不冒充验证过）。已停用的
    模型名绝不进候选。一个候选都没有回 None。"""
    candidates = [
        (pid, m)
        for pid in order
        for m in availability.get(pid) or []
        if m and not _is_retired(m)
    ]
    if not candidates:
        return None
    if probe is not None:
        for pid, m in candidates[:MAX_PROBES]:
            try:
                if probe(pid, m):
                    return (pid, m)
            except Exception:
                continue
    return candidates[0]
