"""松手即停与状态机自愈：松手立即停麦、忙碌期不误导、卡死可恢复。"""
import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from app.config import load_config
from app.ui.overlay import Overlay, OverlayState
from main import Controller


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _StubRecorder:
    def __init__(self):
        self.calls = []

    def stop(self):
        self.calls.append("stop")

    def abort(self):
        self.calls.append("abort")


class _StubEngine:
    def __init__(self, result="", gate=None):
        self.result = result
        self.gate = gate
        self.calls = []

    def start(self):
        self.calls.append("start")

    def feed(self, _pcm):
        pass

    def stop(self, timeout=6.0):
        self.calls.append("stop")
        if self.gate is not None:
            self.gate.wait(2.0)  # 模拟识别服务收尾耗时，便于断言中间状态
        return self.result

    def abort(self):
        self.calls.append("abort")


def _make(app, engine_result=""):
    ov = Overlay()
    ov.show()
    controller = Controller(load_config(), ov)
    return ov, controller


def _session(recorder, engine, started_ago=2.0):
    return {
        "mode": "simple",
        "recorder": recorder,
        "engine": engine,
        "start": time.monotonic() - started_ago,
    }


def test_release_stops_mic_immediately_and_shows_processing(app):
    ov, controller = _make(app)
    gate = threading.Event()
    recorder = _StubRecorder()
    engine = _StubEngine(result="", gate=gate)
    controller._state = "recording"
    controller._session = _session(recorder, engine)
    ov.set_state(OverlayState.RECORDING, "简单润色", 0)

    controller._release("simple")

    assert recorder.calls[0] == "stop"  # 松手立即停麦
    assert controller._state == "finalizing"
    assert ov._state is OverlayState.PROCESSING  # 不再停留"正在聆听"
    gate.set()  # 放行收尾；stub 未识别到内容 → 回 idle
    deadline = time.time() + 2
    while controller._state != "idle" and time.time() < deadline:
        time.sleep(0.02)
    assert controller._state == "idle"
    ov.hide()


def test_press_during_finalize_does_not_override_overlay(app):
    ov, controller = _make(app)
    controller._state = "finalizing"
    controller._state_since = time.monotonic()
    controller._session = _session(_StubRecorder(), _StubEngine())
    ov.set_state(OverlayState.PROCESSING, "转写中…", 0)

    controller._press("simple")

    assert controller._state == "finalizing"  # 忙碌期拒绝新的会话
    assert ov._state is OverlayState.PROCESSING  # 不弹错误条覆盖当前状态
    ov.hide()


def test_short_tap_aborts_and_returns_to_idle(app):
    ov, controller = _make(app)
    recorder, engine = _StubRecorder(), _StubEngine()
    controller._state = "recording"
    controller._session = _session(recorder, engine, started_ago=0.05)

    controller._release("simple")

    assert controller._state == "idle"
    assert "stop" in recorder.calls and "abort" in engine.calls
    ov.hide()


def test_stuck_finalize_resets_on_next_press(app):
    ov, controller = _make(app)
    recorder, engine = _StubRecorder(), _StubEngine()
    controller._state = "finalizing"
    controller._state_since = time.monotonic() - 31  # 视为卡死
    controller._session = _session(recorder, engine)
    controller.cfg.asr.api_key = "sk-test"  # 跳过未配置分支
    controller._start_worker = lambda mode: None  # 测试不真正联网

    controller._press("simple")

    assert controller._state == "starting"  # 卡死会话被重置并直接开始新会话
    assert controller._session is None
    deadline = time.time() + 2
    while "abort" not in engine.calls and time.time() < deadline:
        time.sleep(0.02)
    assert "abort" in engine.calls  # 旧会话在后台被中止
    ov.hide()


def test_end_session_does_not_clobber_new_session(app):
    ov, controller = _make(app)
    old = _session(_StubRecorder(), _StubEngine())
    new = _session(_StubRecorder(), _StubEngine())
    controller._session = new
    controller._state = "starting"  # 新会话已开始

    controller._end_session(old)  # 旧会话收尾，不得覆盖新会话状态

    assert controller._state == "starting"
    assert controller._session is new
    ov.hide()
