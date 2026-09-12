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

    def partial(self):
        return self.result

    def abort(self):
        self.calls.append("abort")


def _make(app, engine_result=""):
    ov = Overlay()
    ov.show()
    controller = Controller(load_config(), ov)
    return ov, controller


def test_successful_dictation_ends_with_done_state(app, monkeypatch, tmp_path):
    # 完整成功链路：不得抛"处理失败"，且界面最终停在"✓ 已上屏"
    # （回归：PyQt6 emit() 不接受关键字参数，曾让收尾线程在 DONE 处崩溃）
    import app.history as history_mod
    import main as main_mod

    monkeypatch.setattr(history_mod, "HISTORY_PATH", tmp_path / "history.jsonl")
    injected = []
    monkeypatch.setattr(main_mod, "inject_text", lambda text: injected.append(text))
    toasts = []

    ov = Overlay()
    ov.show()
    controller = Controller(load_config(), ov)
    controller._sig_toast.connect(toasts.append)
    recorder, engine = _StubRecorder(), _StubEngine(result="你好世界这是测试语音")
    controller._state = "recording"
    controller._session = _session(recorder, engine)

    controller._release("simple")

    deadline = time.time() + 2
    while (controller._state != "idle" or ov._state is OverlayState.PROCESSING) and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()

    assert injected == ["你好世界这是测试语音"]
    assert toasts == []  # 不应有任何"处理失败/识别失败"提示
    assert ov._state is OverlayState.DONE
    ov.hide()


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


def test_toggle_starts_when_idle_and_stops_when_recording(app):
    # 切换模式：idle 下按一下 → 开始；recording 下再按一下 → 走松开停麦流程
    ov, controller = _make(app)
    controller.cfg.hotkey.mode = "toggle"
    controller.cfg.asr.api_key = "sk-test"
    started = []
    controller._start_worker = lambda mode: started.append(mode)

    controller._toggle("simple")
    assert started == ["simple"]  # idle → 请求开始

    recorder = _StubRecorder()
    gate = threading.Event()
    engine = _StubEngine(gate=gate)  # 挡住收尾，便于断言 finalizing 中间态
    controller._state = "recording"
    controller._session = _session(recorder, engine, started_ago=2.0)
    controller._toggle("simple")
    assert recorder.calls[0] == "stop"  # 第二次按下 = 松手停麦
    assert controller._state == "finalizing"
    gate.set()
    ov.hide()


def test_toggle_during_starting_marks_pending_release(app):
    # 切换模式：还在连接识别服务时再按一下，应记为"连上后立即停止"
    ov, controller = _make(app)
    controller._state = "starting"
    controller._state_since = time.monotonic()
    controller._session = None

    controller._toggle("simple")

    assert controller._pending_release is True
    assert controller._state == "starting"
    ov.hide()


def test_engine_error_ends_session_and_salvages_partial(app, monkeypatch, tmp_path):
    # 回归：识别服务长时间录音后中断，之前只弹提示 —— 状态机留在 recording、
    # 麦克风继续采集，而悬浮条已自动回到初始样式，按住/按下全部失灵。
    # 现在报错必须等同松手：立即停麦、收尾，并上屏已识别到的部分文本。
    import app.history as history_mod
    import main as main_mod

    monkeypatch.setattr(history_mod, "HISTORY_PATH", tmp_path / "history.jsonl")
    injected = []
    monkeypatch.setattr(main_mod, "inject_text", lambda text: injected.append(text))

    ov = Overlay()
    ov.show()
    controller = Controller(load_config(), ov)
    recorder = _StubRecorder()

    class _DeadEngine(_StubEngine):
        def stop(self, timeout=6.0):
            self.calls.append("stop")
            raise RuntimeError("connection closed")  # 模拟服务已中断

    engine = _DeadEngine(result="中断前识别到的内容")
    session = _session(recorder, engine)
    controller._state = "recording"
    controller._session = session

    controller._on_engine_error(session, "连接被服务端关闭")

    deadline = time.time() + 2
    while controller._state != "idle" and time.time() < deadline:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()

    assert "stop" in recorder.calls  # 报错后立即停麦
    assert controller._state == "idle"  # 状态机不残留 recording
    assert injected == ["中断前识别到的内容"]  # 部分文本被抢救上屏
    assert ov._state is OverlayState.DONE
    ov.hide()


def test_engine_error_during_starting_defers_and_no_double_finish(app):
    # 还在连接识别服务时报错：记为 pending_release，等连接建立后立即收尾；
    # 重复的报错回调不得重复触发
    ov, controller = _make(app)
    session = _session(_StubRecorder(), _StubEngine())
    controller._state = "starting"
    controller._state_since = time.monotonic()
    controller._session = session

    controller._on_engine_error(session, "early error")
    controller._on_engine_error(session, "early error again")  # 重复回调

    assert controller._pending_release is True
    assert controller._state == "starting"  # 不在 starting 期强行收尾
    ov.hide()


def test_other_hotkeys_fully_disabled_while_session_active(app):
    # 回归：切换模式下 F2 开始后误按 F3/F4 会把状态搅乱 —— 此前 F3 在连接期
    # 把 F2 会话标记成"连上就停"，F4 又趁空闲开了新会话，F2 反而结束不了。
    # 现在会话进行中其他热键必须完全失效：只有开启会话的键能结束它。
    ov, controller = _make(app)
    controller.cfg.hotkey.mode = "toggle"
    controller.cfg.asr.api_key = "sk-test"
    started = []
    controller._start_worker = lambda mode: started.append(mode)

    controller._toggle("simple")  # F2 开始
    assert started == ["simple"]
    assert controller._active_mode == "simple"

    # 连接建立期：误按 F3 必须被完全忽略，不得劫持 F2 的会话
    controller._state = "starting"
    controller._state_since = time.monotonic()
    controller._session = None
    controller._toggle("deep")
    assert controller._pending_release is False
    controller._toggle("raw")
    assert controller._pending_release is False

    # 录音中：误按 F3/F4 同样忽略，F2 仍能正常结束
    controller._state = "recording"
    recorder = _StubRecorder()
    gate = threading.Event()
    engine = _StubEngine(gate=gate)  # 挡住收尾，便于断言 finalizing 中间态
    session = _session(recorder, engine)
    controller._session = session
    controller._toggle("deep")
    assert controller._state == "recording"
    assert recorder.calls == []
    controller._toggle("raw")
    assert controller._state == "recording"

    controller._toggle("simple")  # 只有开始的键能结束
    assert recorder.calls[0] == "stop"
    assert controller._state == "finalizing"
    gate.set()
    ov.hide()


def test_release_of_other_key_during_starting_is_ignored(app):
    # 按住模式同样受保护：F2 按住后连接期误触 F3，其松开不得把会话标记成待停止
    ov, controller = _make(app)
    controller._state = "starting"
    controller._state_since = time.monotonic()
    controller._session = None
    controller._active_mode = "simple"

    controller._release("deep")
    assert controller._pending_release is False

    controller._release("simple")  # 本尊的松开仍然有效
    assert controller._pending_release is True
    ov.hide()
