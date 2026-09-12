"""DashScope 引擎的句子累积逻辑测试（桩替换真实 SDK，不联网）。"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.asr.dashscope_rt as mod
from app.asr.base import AsrCallbacks
from app.asr.dashscope_rt import DashScopeRealtimeAsr


class _FakeRecognition:
    """记录调用的假 Recognition；事件通过 callback 手动注入。"""

    instances: list["_FakeRecognition"] = []

    def __init__(self, model=None, callback=None, format=None, sample_rate=None, **_kwargs):
        self.started = False
        self.sent: list[bytes] = []
        self.stopped = False
        self._callback = callback
        _FakeRecognition.instances.append(self)

    def start(self, **_kwargs):
        self.started = True
        self._callback.on_open()

    def send_audio_frame(self, data: bytes):
        self.sent.append(data)

    def stop(self):
        self.stopped = True
        self._callback.on_close()

    # ---- 测试辅助：模拟服务端事件 ----
    def emit(self, text: str, sentence_end: bool):
        callback = self._callback

        class _Result:
            def get_sentence(self):
                return {"text": text, "sentence_end": sentence_end}

        callback.on_event(_Result())


def _make_engine():
    _FakeRecognition.instances.clear()
    partials: list[str] = []
    callbacks = AsrCallbacks(on_partial=partials.append)
    with patch.object(mod, "Recognition", _FakeRecognition):
        engine = DashScopeRealtimeAsr(api_key="test", callbacks=callbacks)
    return engine, _FakeRecognition.instances[-1], partials


def test_partial_accumulates_sentences():
    engine, rec, partials = _make_engine()
    engine.start()
    assert rec.started
    engine.feed(b"\x00\x01")
    rec.emit("你好", False)
    assert partials[-1] == "你好"
    rec.emit("你好世界", True)  # 第一句定稿
    rec.emit("今天", False)  # 第二句中间结果
    assert partials[-1] == "你好世界今天"
    engine.feed(b"\x00\x02")
    assert rec.sent == [b"\x00\x01", b"\x00\x02"]
    assert engine.stop() == "你好世界今天"


def test_stop_returns_committed_only_after_final():
    engine, rec, _ = _make_engine()
    engine.start()
    rec.emit("完整句子。", True)
    text = engine.stop()
    assert text == "完整句子。"
    assert rec.stopped


def test_feed_after_stop_is_ignored():
    engine, rec, _ = _make_engine()
    engine.start()
    engine.stop()
    engine.feed(b"should-not-send")
    assert rec.sent == []


def test_error_propagates_on_stop():
    engine, rec, _ = _make_engine()
    engine.start()
    rec._callback.on_error(type("E", (), {"message": "invalid key", "code": "401"})())
    try:
        engine.stop()
        raised = False
    except Exception as exc:
        raised = "invalid key" in str(exc)
    assert raised


def test_error_stops_feeding_and_partial_salvages_text():
    # 服务中断后：不再向死连接推流；已收文本可通过 partial() 抢救；
    # stop() 直接抛错，绝不再对 SDK 调 stop（避免在死连接上挂死）
    engine, rec, _ = _make_engine()
    engine.start()
    rec.emit("第一句。", True)
    rec.emit("第二句中", False)
    rec._callback.on_error(type("E", (), {"message": "connection closed"})())

    engine.feed(b"after-error")
    assert rec.sent == []  # 报错后 feed 静默丢弃
    assert engine.partial() == "第一句。第二句中"
    try:
        engine.stop(timeout=0.1)
        raised = False
    except Exception:
        raised = True
    assert raised
    assert not rec.stopped  # 死连接上不调用 SDK stop


def test_apply_base_url_variants():
    import dashscope

    original_ws = dashscope.base_websocket_api_url
    original_http = dashscope.base_http_api_url
    try:
        from app.asr.dashscope_rt import _DEFAULT_WS_URL, apply_base_url

        # 留空 / 与默认相同 → 不改动
        apply_base_url("")
        assert dashscope.base_websocket_api_url == original_ws
        apply_base_url(_DEFAULT_WS_URL)
        assert dashscope.base_websocket_api_url == original_ws

        # 纯域名 → 推导 WS + HTTP 两个端点
        apply_base_url("dashscope-intl.aliyuncs.com/")
        assert dashscope.base_websocket_api_url == "wss://dashscope-intl.aliyuncs.com/api-ws/v1/inference"
        assert dashscope.base_http_api_url == "https://dashscope-intl.aliyuncs.com/api/v1"

        # 完整 ws 地址 → 原样使用
        apply_base_url("wss://gw.example.com/api-ws/v1/inference")
        assert dashscope.base_websocket_api_url == "wss://gw.example.com/api-ws/v1/inference"
    finally:
        dashscope.base_websocket_api_url = original_ws
        dashscope.base_http_api_url = original_http
