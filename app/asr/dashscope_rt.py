"""阿里云百炼 DashScope Paraformer 实时语音识别（WebSocket 流式）。"""
from __future__ import annotations

import threading

import dashscope
from dashscope.audio.asr import Recognition

from .base import AsrCallbacks, StreamingAsrEngine, StreamingAsrError

_SENTINEL = object()


def _make_sdk_callback(engine: "DashScopeRealtimeAsr"):
    """兼容不同版本 SDK 的回调基类（缺 RecognitionCallback 时用普通类）。"""
    base_cls = globals().get("RecognitionCallback", object)

    class _Callback(base_cls):  # type: ignore[misc,valid-type]
        def on_open(self) -> None:
            engine._on_open()

        def on_event(self, result) -> None:
            engine._on_event(result)

        def on_error(self, error) -> None:
            engine._on_error(error)

        def on_close(self) -> None:
            engine._on_close()

    return _Callback()


try:  # 新版 SDK 提供
    from dashscope.audio.asr import RecognitionCallback  # noqa: F401
except ImportError:  # pragma: no cover
    pass


_DEFAULT_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"


def apply_base_url(base_url: str) -> None:
    """把配置里的服务地址应用到 SDK。

    支持三种写法：
    - 留空            → SDK 默认（官方国内站）
    - 域名            → 同时推导 WebSocket 与 HTTP 端点，如 dashscope-intl.aliyuncs.com
    - 完整 ws:// 地址 → 直接使用
    """
    value = (base_url or "").strip().rstrip("/")
    if not value or value == _DEFAULT_WS_URL:
        return
    if value.startswith(("ws://", "wss://")):
        dashscope.base_websocket_api_url = value
    elif value.startswith(("http://", "https://")):
        dashscope.base_http_api_url = value
    else:
        dashscope.base_websocket_api_url = f"wss://{value}/api-ws/v1/inference"
        dashscope.base_http_api_url = f"https://{value}/api/v1"


class DashScopeRealtimeAsr(StreamingAsrEngine):
    """按句累积：中间结果实时回调 partial（累计全文），stop() 返回完整文本。"""

    def __init__(
        self,
        api_key: str,
        model: str = "paraformer-realtime-v2",
        sample_rate: int = 16000,
        disfluency_removal: bool = True,
        base_url: str = "",
        callbacks: AsrCallbacks | None = None,
    ):
        super().__init__(callbacks or AsrCallbacks())
        dashscope.api_key = api_key
        apply_base_url(base_url)
        self._model = model
        self._sample_rate = sample_rate
        self._disfluency_removal = disfluency_removal
        self._committed = ""  # 已定稿句子拼接
        self._current = ""  # 当前句中间结果
        self._started = False
        self._stopping = False
        self._closed = threading.Event()
        self._error: str | None = None
        self._rec = Recognition(
            model=model,
            sample_rate=sample_rate,
            format="pcm",
            callback=_make_sdk_callback(self),
        )

    # ---- 引擎接口 ----
    def start(self) -> None:
        self._committed = ""
        self._current = ""
        self._error = None
        self._stopping = False
        self._closed.clear()
        try:
            self._rec.start(disfluency_removal_enabled=self._disfluency_removal)
        except Exception as exc:
            raise StreamingAsrError(f"识别会话建立失败：{exc}") from exc

    def feed(self, pcm16_bytes: bytes) -> None:
        if not self._started or self._stopping:
            return
        try:
            self._rec.send_audio_frame(pcm16_bytes)
        except Exception as exc:
            if self.callbacks.on_error:
                self.callbacks.on_error(f"音频发送失败：{exc}")

    def stop(self, timeout: float = 6.0) -> str:
        self._stopping = True
        try:
            self._rec.stop()
        except Exception as exc:
            if self._error is None:
                self._error = f"结束识别失败：{exc}"
        self._closed.wait(timeout)
        if self._error:
            raise StreamingAsrError(self._error)
        return (self._committed + self._current).strip()

    def abort(self) -> None:
        self._stopping = True
        try:
            self._rec.stop()
        except Exception:
            pass

    # ---- SDK 回调（网络线程）----
    def _on_open(self) -> None:
        self._started = True
        if self.callbacks.on_open:
            self.callbacks.on_open()

    def _on_event(self, result) -> None:
        sentence = None
        try:
            sentence = result.get_sentence()
        except Exception:
            sentence = None
        if not sentence:
            return
        text = sentence.get("text", "") or ""
        ended = getattr(Recognition, "is_sentence_end", None)
        try:
            sentence_end = bool(ended(sentence)) if callable(ended) else bool(sentence.get("sentence_end"))
        except Exception:
            sentence_end = bool(sentence.get("sentence_end"))
        if sentence_end:
            self._committed += text
            self._current = ""
        else:
            self._current = text
        if self.callbacks.on_partial:
            self.callbacks.on_partial((self._committed + self._current).strip())

    def _on_error(self, error) -> None:
        message = getattr(error, "message", None) or getattr(error, "code", None) or str(error)
        self._error = message
        self._closed.set()
        if self.callbacks.on_error:
            self.callbacks.on_error(message)

    def _on_close(self) -> None:
        self._started = False
        self._closed.set()
