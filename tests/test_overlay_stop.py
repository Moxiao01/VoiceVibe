"""悬浮条停止按钮：录音中可见，点击取消会话并回到初始样式。"""
import os

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


def test_stop_click_cancels_session_and_reverts(app):
    ov = Overlay()
    ov.show()
    controller = Controller(load_config(), ov)
    ov.stopClicked.connect(controller._cancel)

    recorder, engine = _Stub(), _Stub()
    controller._state = "recording"
    controller._session = {"mode": "simple", "recorder": recorder, "engine": engine, "start": 0.0}
    ov.set_state(OverlayState.RECORDING, "简单润色")
    assert ov._stop_btn.isVisible()

    ov.stopClicked.emit()

    assert recorder.calls == ["stop"]
    assert engine.calls == ["abort"]
    assert controller._state == "idle"
    assert controller._session is None
    assert ov._state is OverlayState.IDLE
    assert ov._chip.text() == "Voice Vibe"
    assert not ov._stop_btn.isVisible()
    ov.hide()
