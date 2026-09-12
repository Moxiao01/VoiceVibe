"""悬浮条停止按钮：录音中可见，点击等同松开热键（结束并保留）；Esc 才是取消。"""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from app.config import load_config
from app.ui.overlay import Overlay, OverlayState
from main import Controller


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def overlay(app):
    ov = Overlay()
    ov.show()
    yield ov
    ov.hide()


class _Stub:
    def __init__(self):
        self.calls = []

    def stop(self):
        self.calls.append("stop")

    def abort(self):
        self.calls.append("abort")


def test_stop_button_visible_only_while_recording(overlay):
    assert not overlay._stop_btn.isVisible()
    overlay.set_state(OverlayState.RECORDING, "简单润色")
    assert overlay._stop_btn.isVisible()
    overlay.set_state(OverlayState.DONE, "简单润色", auto_idle_ms=0)
    assert not overlay._stop_btn.isVisible()


def test_click_stop_emits_signal(overlay):
    got = []
    overlay.stopClicked.connect(lambda: got.append(True))
    overlay.set_state(OverlayState.RECORDING, "简单润色")
    QTest.mouseClick(overlay._stop_btn, Qt.MouseButton.LeftButton)
    assert got == [True]


def test_stop_click_finalizes_and_keeps_text(app, monkeypatch, tmp_path):
    # 回归：■ 按钮之前直接走取消，热键失灵时它是唯一能停的方式，一点就
    # 退格删光全部已上屏文字。现在录音中点它等同松开热键：正常收尾、
    # 保留并上屏已说的内容；引擎是 stop 而非 abort
    import app.history as history_mod
    import main as main_mod

    monkeypatch.setattr(history_mod, "HISTORY_PATH", tmp_path / "history.jsonl")
    injected = []
    monkeypatch.setattr(main_mod, "inject_text", lambda text: injected.append(text))

    class _Engine:
        def __init__(self):
            self.calls = []

        def stop(self, timeout=6.0):
            self.calls.append("stop")
            return "今天天气不错"

        def abort(self):
            self.calls.append("abort")

    ov = Overlay()
    ov.show()
    controller = Controller(load_config(), ov)
    ov.stopClicked.connect(controller._stop_requested)
    recorder, engine = _Stub(), _Engine()
    controller._state = "recording"
    controller._session = {
        "mode": "simple", "recorder": recorder, "engine": engine,
        "start": time.monotonic() - 2.0,
    }
    ov.set_state(OverlayState.RECORDING, "简单润色")
    assert ov._stop_btn.isVisible()

    ov.stopClicked.emit()

    assert recorder.calls[0] == "stop"  # 立即停麦（_finalize 里还会再停一次，防御性）
    deadline = time.time() + 3
    while controller._state != "idle" and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()

    assert injected == ["今天天气不错"]  # 已说的内容保留并上屏
    assert "abort" not in engine.calls  # 不是取消
    assert controller._state == "idle"
    ov.hide()


def test_stop_click_during_starting_cancels(app):
    # 连接建立期点 ■：还没有任何已上屏文字，走取消（中止连接）
    ov = Overlay()
    ov.show()
    controller = Controller(load_config(), ov)
    ov.stopClicked.connect(controller._stop_requested)

    recorder, engine = _Stub(), _Stub()
    controller._state = "starting"
    controller._session = {"mode": "simple", "recorder": recorder, "engine": engine, "start": 0.0}

    ov.stopClicked.emit()

    assert recorder.calls == ["stop"]
    assert engine.calls == ["abort"]
    assert controller._state == "idle"
    assert controller._session is None
    ov.hide()


def test_cancel_discards_session(app):
    # Esc（_cancel）保持取消语义：中止会话、引擎 abort、状态回 idle
    ov = Overlay()
    ov.show()
    controller = Controller(load_config(), ov)

    recorder, engine = _Stub(), _Stub()
    controller._state = "recording"
    controller._session = {"mode": "simple", "recorder": recorder, "engine": engine, "start": 0.0}
    ov.set_state(OverlayState.RECORDING, "简单润色")

    controller._cancel()

    assert recorder.calls == ["stop"]
    assert engine.calls == ["abort"]
    assert controller._state == "idle"
    assert controller._session is None
    assert ov._state is OverlayState.IDLE
    ov.hide()
