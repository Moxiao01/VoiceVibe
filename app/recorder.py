"""麦克风采集：16k 单声道 16bit PCM，按块回调给 ASR 引擎。"""
from __future__ import annotations

import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd


class MicrophoneRecorder:
    """阻塞式启停的音频流。on_frame 在 PortAudio 线程里被调用，
    必须快速返回（只做一次 websocket 发送 / 入队）。"""

    def __init__(
        self,
        sample_rate: int = 16000,
        device: int = -1,
        block_ms: int = 100,
        on_frame: Optional[Callable[[bytes], None]] = None,
        on_level: Optional[Callable[[float], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self.sample_rate = sample_rate
        self.device = None if device is None or device < 0 else device
        self.blocksize = max(1, int(sample_rate * block_ms / 1000))
        self._on_frame = on_frame
        self._on_level = on_level
        self._on_error = on_error
        self._stream: Optional[sd.InputStream] = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._stream is not None:
                return
            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self.blocksize,
                    device=self.device,
                    callback=self._callback,
                )
                self._stream.start()
            except Exception as exc:  # 设备被占用 / 无麦克风等
                self._stream = None
                if self._on_error:
                    self._on_error(f"麦克风打开失败：{exc}")
                raise

    def stop(self) -> None:
        with self._lock:
            stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass

    @property
    def running(self) -> bool:
        return self._stream is not None

    def _callback(self, indata, frames, time_info, status) -> None:  # PortAudio 线程
        if status and self._on_error:
            self._on_error(f"音频流异常：{status}")
        if self._on_level is not None:
            rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
            self._on_level(min(1.0, rms / 3000.0))
        if self._on_frame is not None:
            self._on_frame(indata.tobytes())
