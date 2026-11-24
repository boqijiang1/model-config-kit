"""OpenAI 兼容供应商客户端（本模块唯一的模型调用实现）。

任何支持 `POST {base_url}/chat/completions` + `Authorization: Bearer <key>`
的平台（火山方舟、DeepSeek、OpenAI、各类中转站……）都用这一个类，不写
各家适配器。

- 流式接收：大输出（上万字）非流式容易读超时；流式下读超时只管「下一小片」，
  模型正常出字就不会假超时。usage 走流式尾块。
- 总时长保险丝：一次 chat 必有终局，到点掐断连接池，给出大白话错误。
- 手动停止：cancel() 置旗标 + 掐连接池，立即中断。
- 参数习惯：OpenAI 推理系模型的 temperature/max_tokens 参数形状不同，
  由 param_style 处理（见 _shape）。
"""
from __future__ import annotations

import json
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx

# on_chunk(delta, is_content)：delta 是本次增量文本，is_content 表明是否正文。
OnChunk = Callable[[str, bool], None]

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1, 2, 4)
DEFAULT_TOTAL_DEADLINE = 1800.0  # 一次 chat 调用的总预算（30 分钟）


@dataclass
class Message:
    """一轮对话消息。也接受 {"role": ..., "content": ...} 字典作为入参。"""

    role: str
    content: str


@dataclass
class Reply:
    content: str
    usage: dict = field(default_factory=dict)


class ProviderError(RuntimeError):
    """供应商调用失败的统一出口（重试耗尽后的最终失败）。"""


class ProviderCancelled(ProviderError):
    """用户手动停止：调用方应单独捕获、绝不进入自动重试。"""

    def __init__(self, message: str = "你手动停止了这次调用"):
        super().__init__(message)


class LlmProvider(ABC):
    """模型供应商接缝。"""

    @abstractmethod
    def chat(
        self,
        messages: list[Message] | list[dict],
        opts: dict,
        *,
        on_chunk: OnChunk | None = None,
    ) -> Reply:
        """一轮对话补全。opts 透传平台特有参数（temperature、max_tokens 等）。
        on_chunk 必须走 keyword-only——它绝不能混进 opts 被展开进请求体。"""

    def cancel(self) -> None:
        """请求停止当前（或下一次即将开始的）调用。默认无操作。"""

    def is_cancelled(self) -> bool:
        return False

    def close(self) -> None:
        """释放连接池。默认无操作。"""


def _as_payload(messages: list[Message] | list[dict]) -> list[dict]:
    out: list[dict] = []
    for m in messages:
        if isinstance(m, dict):
            out.append({"role": m.get("role", "user"), "content": m.get("content", "")})
        else:
            out.append({"role": m.role, "content": m.content})
    return out


class OpenAICompatProvider(LlmProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str,
        client: httpx.Client | None = None,
        sleep: Callable[[float], Any] = time.sleep,
        timeout: float = 300.0,
        total_deadline: float = DEFAULT_TOTAL_DEADLINE,
        request_extra: dict | None = None,
        param_style: str = "chat",
        label: str = "供应商",
    ):
        self._api_key = api_key
        self._model = model
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._client = client or httpx.Client(timeout=timeout)
        self._sleep = sleep
        self._owns_client = client is None
        self._total_deadline = total_deadline
        self._request_extra = dict(request_extra or {})
        self._param_style = param_style
        self._label = label or "供应商"
        self._abort = threading.Event()
        self._cancelled = threading.Event()

    def _shape(self, payload: dict) -> dict:
        """按这家的参数习惯整理请求体。

        openai-reasoning（OpenAI 推理系模型）：温度只认默认值（带了 400）、
        正文额度参数叫 max_completion_tokens、没有 thinking 开关。其余家原样。"""
        if self._param_style != "openai-reasoning":
            return payload
        payload = dict(payload)
        payload.pop("temperature", None)
        payload.pop("thinking", None)
        if "max_tokens" in payload:
            payload["max_completion_tokens"] = payload.pop("max_tokens")
        return payload

    def cancel(self) -> None:
        self._cancelled.set()
        try:
            self._client.close()
        except Exception:
            pass

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def chat(
        self,
        messages: list[Message] | list[dict],
        opts: dict,
        *,
        on_chunk: OnChunk | None = None,
    ) -> Reply:
        payload = self._shape({
            "model": self._model,
            "messages": _as_payload(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
            **self._request_extra,
            **(opts or {}),
        })
        headers = {"Authorization": f"Bearer {self._api_key}"}
        deadline = time.monotonic() + self._total_deadline

        last_error: Exception | None = None
        for attempt in range(MAX_ATTEMPTS):
            if self._cancelled.is_set():
                raise ProviderCancelled()
            if self._abort.is_set() or time.monotonic() >= deadline:
                break
            watchdog = threading.Timer(
                max(deadline - time.monotonic(), 0.1), self._fire_fuse
            )
            watchdog.start()
            try:
                with self._client.stream(
                    "POST", self._url, json=payload, headers=headers
                ) as resp:
                    if resp.status_code == 200:
                        return self._drain_sse(resp, on_chunk)
                    resp.read()
                    if resp.status_code in (429, 500, 502, 503, 504):
                        last_error = ProviderError(
                            f"{self._label}返回 {resp.status_code}：{resp.text[:200]}"
                        )
                    else:
                        raise ProviderError(
                            f"{self._label}拒绝请求（{resp.status_code}）：{resp.text[:300]}"
                        )
            except httpx.TransportError as e:
                if self._cancelled.is_set():
                    raise ProviderCancelled() from e
                last_error = e
            except RuntimeError as e:
                if self._cancelled.is_set():
                    raise ProviderCancelled() from e
                raise self._fuse_error(last_error) from e
            finally:
                watchdog.cancel()
            if attempt < MAX_ATTEMPTS - 1:
                self._sleep(BACKOFF_SECONDS[min(attempt, len(BACKOFF_SECONDS) - 1)])

        if self._cancelled.is_set():
            raise ProviderCancelled()
        if self._abort.is_set() or time.monotonic() >= deadline:
            raise self._fuse_error(last_error)
        raise ProviderError(f"重试 {MAX_ATTEMPTS} 次仍失败：{last_error}") from last_error

    def _fire_fuse(self) -> None:
        self._abort.set()
        try:
            self._client.close()
        except Exception:
            pass

    def _fuse_error(self, last_error: Exception | None) -> ProviderError:
        minutes = max(int(self._total_deadline // 60), 1)
        return ProviderError(
            f"这次调用总时长超过 {minutes} 分钟，软件把它停掉了（保险丝熔断）。"
            f"最后遇到的问题：{last_error}"
        )

    def _drain_sse(self, resp: httpx.Response, on_chunk: OnChunk | None = None) -> Reply:
        """读完一个 SSE 流：拼接正文增量，收集尾块 usage。

        正文增量 on_chunk(delta, True)；保活注释行 / 思考增量 on_chunk(…, False)
        只表「模型还活着」，不计正文。"""
        parts: list[str] = []
        usage: dict = {}
        for line in resp.iter_lines():
            if self._cancelled.is_set():
                raise ProviderCancelled()
            line = line.strip()
            if not line:
                continue
            if line.startswith(":"):
                if on_chunk:
                    on_chunk("", False)
                continue
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            choices = obj.get("choices") or []
            if choices:
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                reasoning = delta.get("reasoning_content")
                if content:
                    parts.append(content)
                    if on_chunk:
                        on_chunk(content, True)
                elif reasoning:
                    if on_chunk:
                        on_chunk(reasoning, False)
                elif on_chunk:
                    on_chunk("", False)
            if obj.get("usage"):
                usage = obj["usage"]
        return Reply(content="".join(parts), usage=usage)

    def close(self) -> None:
        self._abort.set()
        if self._owns_client:
            self._client.close()


# 兼容别名：老代码里叫 ArkProvider 的地方可以直接用这个名字。
ArkProvider = OpenAICompatProvider
