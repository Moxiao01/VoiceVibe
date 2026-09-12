"""流式 ASR 引擎抽象：任何云端/本地引擎实现同一接口即可替换。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Optional


class AsrCallbacks:
    """引擎通过这些回调上报进度；回调可能来自网络线程，注意线程安全。"""

    def __init__(
        self,
        on_partial: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_open: Optional[Callable[[], None]] = None,
    ):
        self.on_partial = on_partial
        self.on_error = on_error
        self.on_open = on_open


class StreamingAsrError(RuntimeError):
    pass


class StreamingAsrEngine(ABC):
    """生命周期：start() → feed()*N → stop()（返回完整文本） / abort()。"""

    def __init__(self, callbacks: AsrCallbacks):
        self.callbacks = callbacks

    @abstractmethod
    def start(self) -> None:
        """建立识别会话，之后才能 feed。"""

    @abstractmethod
    def feed(self, pcm16_bytes: bytes) -> None:
        """推送 16k 16bit 单声道 PCM 音频帧。"""

    @abstractmethod
    def stop(self, timeout: float = 6.0) -> str:
        """结束识别，阻塞直到拿到完整文本或超时（超时返回已收到的部分）。"""

    def partial(self) -> str:
        """服务中断等异常时可抢救的已收文本快照（默认为空）。"""
        return ""

    @abstractmethod
    def abort(self) -> None:
        """放弃本次识别，立即释放资源，不产生 final 回调。"""
