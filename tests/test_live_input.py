"""流式上屏：增量粘贴、退格修正、清理同步、取消撤销。"""
import os
import queue
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

import app.inject as inject_mod
import app.history as history_mod
import main as main_mod
from app.config import load_config
from app.inject import LiveInjector
from app.ui.overlay import Overlay, OverlayState
from main import Controller


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


class _FakeClip:
    def __init__(self):
        self.value = ""   # 最近一次复制的内容（= 真实剪贴板）
        self.buffer = ""  # 模拟目标输入框：粘贴追加、退格删除
        self.copies = []

    def paste(self):
        return self.value

    def copy(self, text):
        self.copies.append(text)
        self.value = text


class _KeyLog:
    def __init__(self, clip):
        self.keys = []
        self.clip = clip

    def send(self, key):
        self.keys.append(key)
        if key == "ctrl+v":  # 模拟输入框接收粘贴
            self.clip.buffer += self.clip.value
        elif key == "backspace" and self.clip.buffer:
            self.clip.buffer = self.clip.buffer[:-1]


class _NoopTimer:
    def __init__(self, delay, fn, *args, **kwargs):
        pass

    def start(self):
        pass


class _StubRecorder:
    def stop(self):
        pass

    def abort(self):
        pass


class _StubEngine:
    def __init__(self, result):
        self.result = result

    def stop(self, timeout=6.0):
        return self.result

    def abort(self):
        pass


@pytest.fixture()
def live_env(monkeypatch):
    clip = _FakeClip()
    keys = _KeyLog(clip)
    monkeypatch.setattr(inject_mod, "pyperclip", clip)
    # inject.py 用模块级 send_keys() 直接 keybd_event 注入（不经 keyboard 库，
    # 否则 is_replaying 会吞掉用户真实按键），测试替换成按键日志桩
    monkeypatch.setattr(inject_mod, "send_keys", keys.send)
    monkeypatch.setattr(inject_mod.threading, "Timer", _NoopTimer)  # 测试中不真正恢复剪贴板
    return clip, keys


def test_live_inject_increment_and_repair(live_env):
    clip, keys = live_env
    inj = LiveInjector()
    inj.begin()

    inj.update("今天天气不错")
    assert clip.buffer == "今天天气不错"

    inj.update("今天天气不错，我们去爬山")
    assert clip.copies[-1] == "，我们去爬山"  # 只粘增量

    n = len(keys.keys)
    inj.update("今天天气不错，我们去爬山")  # 无变化不触发任何按键
    assert keys.keys[n:] == []

    inj.update("今天天气不错，我们爬山")  # 尾部"去爬山"修订为"爬山"：退格3次再补粘
    assert keys.keys[n:].count("backspace") == 3
    assert clip.copies[-1] == "爬山"
    assert clip.buffer == "今天天气不错，我们爬山"

    injected_len = len(inj.injected)
    inj.cancel()  # 撤销全部
    assert keys.keys[-injected_len:] == ["backspace"] * injected_len
    assert inj.injected == ""
    assert clip.buffer == ""


def test_on_partial_cleans_for_simple_mode(app):
    ov = Overlay()
    ov.show()
    ctrl = Controller(load_config(), ov)
    shown = []
    ctrl._sig_partial.connect(shown.append)
    session = {"mode": "simple", "injector": LiveInjector(), "q": queue.Queue(), "stream_error": ""}

    ctrl._on_partial(session, "simple", "嗯，然后今天天气不错")
    app.processEvents()
    assert shown == ["今天天气不错"]  # 悬浮条显示清理后的文本
    assert session["q"].get_nowait() == "今天天气不错"  # 输入框拿到同一份

    ctrl._on_partial(session, "raw", "嗯，今天")
    app.processEvents()
    assert shown[-1] == "嗯，今天"  # 原文模式不清理
    ov.hide()


def test_full_flow_streams_and_finalizes(app, monkeypatch, tmp_path, live_env):
    clip, keys = live_env
    monkeypatch.setattr(history_mod, "HISTORY_PATH", tmp_path / "history.jsonl")

    ov = Overlay()
    ov.show()
    ctrl = Controller(load_config(), ov)
    ctrl.cfg.input.streaming = True

    inj = LiveInjector()
    inj.begin()
    session = {
        "mode": "simple", "engine": _StubEngine("今天天气不错，呃，我们去爬山"),
        "recorder": _StubRecorder(), "start": time.monotonic() - 2.0,
        "injector": inj, "q": queue.Queue(), "pump": None, "stream_error": "",
    }
    pump = threading.Thread(target=ctrl._pump_injector, args=(session,), daemon=True)
    session["pump"] = pump
    pump.start()

    ctrl._on_partial(session, "simple", "今天天气不错")
    time.sleep(0.2)  # 等 pump 把第一条打进去

    ctrl._state = "recording"
    ctrl._session = session
    ctrl._release("simple")  # 松开 → 收尾 → 润色删"呃"并同步

    deadline = time.time() + 3
    while (ctrl._state != "idle" or ov._state is OverlayState.PROCESSING) and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()

    assert clip.buffer == "今天天气不错，我们去爬山"  # "呃"在输入框里被同步删除
    assert ov._state is OverlayState.DONE
    ov.hide()
