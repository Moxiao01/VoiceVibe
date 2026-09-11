"""Voice Vibe 语音输入 —— 入口与总控。

按住热键说话 → 松开后润色 → 自动粘贴到当前光标处。
  F2 简单润色（规则去语气词，瞬时）
  F3 深度润色（LLM 把口述重写为 AI 提示词）
  F4 原始转写
  Esc 取消本次
"""
from __future__ import annotations

import os
import queue
import sys
import threading
import time

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication

from app.asr.base import AsrCallbacks
from app.asr.dashscope_rt import DashScopeRealtimeAsr
from app.config import Config, load_config
from app.history import add_record
from app.hotkey import HotkeyManager
from app.inject import LiveInjector, inject_text
from app.polish.deep import coherence_polish, promptify
from app.polish.llm import LlmError
from app.polish.simple import simple_polish
from app.ui.overlay import Overlay, OverlayState
from app.ui.settings import HistoryDialog, SettingsDialog
from app.ui.tray import TrayController

MODE_NAMES = {"simple": "简单润色", "deep": "深度润色", "raw": "原始转写"}
MIN_DURATION_S = 0.3  # 短于此视为误触
STUCK_RESET_S = 30.0  # starting/finalizing 停留超过此时长视为卡死，按下热键时强制重置


class Controller(QObject):
    # 跨线程 UI 更新全部走信号（keyboard/PortAudio/网络线程 → 主线程）
    _sig_state = pyqtSignal(object, str, int)  # state, detail, auto_idle_ms
    _sig_partial = pyqtSignal(str)
    _sig_level = pyqtSignal(float)
    _sig_toast = pyqtSignal(str)

    def __init__(self, cfg: Config, overlay: Overlay):
        super().__init__()
        self.cfg = cfg
        self.overlay = overlay
        self.hotkeys = HotkeyManager()

        self._lock = threading.Lock()
        self._state = "idle"  # idle / starting / recording / finalizing
        self._state_since = time.monotonic()
        self._pending_release = False
        self._session = None

        self._sig_partial.connect(overlay.set_partial)
        self._sig_level.connect(overlay.set_level)
        self._sig_state.connect(overlay.set_state)
        self._sig_toast.connect(lambda msg: overlay.set_state(OverlayState.ERROR, msg, auto_idle_ms=3200))

    # ---- 热键注册 ----
    def register_hotkeys(self) -> None:
        self.hotkeys.unbind_all()
        for mode, attr in (("simple", "simple"), ("deep", "deep"), ("raw", "raw")):
            key = getattr(self.cfg.hotkey, attr)
            self.hotkeys.bind(
                key,
                on_press=lambda m=mode: self._press(m),
                on_release=lambda m=mode: self._release(m),
            )
        self.hotkeys.bind(self.cfg.hotkey.cancel, on_press=self._cancel)
        self.overlay.set_hint(
            f"按住 {self.cfg.hotkey.simple.upper()} 说话 · "
            f"{self.cfg.hotkey.deep.upper()} 深度润色 · "
            f"{self.cfg.hotkey.raw.upper()} 原文 · Esc 取消"
        )

    # ---- 会话状态机 ----
    def _press(self, mode: str) -> None:
        with self._lock:
            if self._state != "idle" and not self._reset_stuck_locked():
                if self._state == "starting":
                    self._sig_toast.emit("正在连接识别服务，请稍候…")
                # recording/finalizing：悬浮条正在如实展示状态，不再弹误导性错误条
                return
            if not self.cfg.asr_ready:
                self._sig_toast.emit("未配置识别 API Key：请复制 config.example.toml 为 config.toml 并填写 asr.api_key")
                return
            self._state = "starting"
            self._state_since = time.monotonic()
            self._pending_release = False
        threading.Thread(target=self._start_worker, args=(mode,), daemon=True).start()

    def _reset_stuck_locked(self) -> bool:
        """starting/finalizing 卡死时的自愈：强制回 idle，返回是否已重置（须持锁调用）。"""
        if self._state not in ("starting", "finalizing"):
            return False
        if time.monotonic() - self._state_since <= STUCK_RESET_S:
            return False
        session = self._session
        self._session = None
        self._state = "idle"
        self._state_since = time.monotonic()
        self._pending_release = False
        if session is not None:
            threading.Thread(target=self._abort_session, args=(session,), daemon=True).start()
        return True

    def _start_worker(self, mode: str) -> None:
        engine = recorder = None
        error = None
        # 流式上屏：深度润色要等 LLM 整体重写，只保留悬浮条展示
        live = None
        if self.cfg.input.streaming and mode in ("simple", "raw"):
            live = LiveInjector()
            live.begin()
        session: dict = {
            "mode": mode, "engine": None, "recorder": None, "start": 0.0,
            "injector": live, "q": queue.Queue(), "pump": None, "stream_error": "",
        }
        pump = threading.Thread(target=self._pump_injector, args=(session,), daemon=True)
        session["pump"] = pump
        pump.start()
        try:
            engine = DashScopeRealtimeAsr(
                api_key=self.cfg.asr.api_key,
                model=self.cfg.asr.model,
                sample_rate=self.cfg.audio.sample_rate,
                base_url=self.cfg.asr.base_url,
                callbacks=AsrCallbacks(
                    on_partial=lambda t: self._on_partial(session, mode, t),
                    on_error=lambda msg: self._sig_toast.emit(f"识别服务：{msg}"),
                ),
            )
            engine.start()
            recorder = _make_recorder(self.cfg, engine, self._sig_level, self._sig_toast)
            recorder.start()
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            if engine is not None:
                engine.abort()

        with self._lock:
            if self._state != "starting":  # 已被取消
                if recorder is not None:
                    recorder.stop()
                self._abort_session(session)
                return
            if error is not None:
                self._state = "idle"
                self._state_since = time.monotonic()
                self._sig_toast.emit(f"启动失败：{error}")
                self._abort_session(session)
                return
            self._state = "recording"
            self._state_since = time.monotonic()
            session["start"] = time.monotonic()
            session["engine"] = engine
            session["recorder"] = recorder
            self._session = session
        self._sig_partial.emit("")
        self._sig_state.emit(OverlayState.RECORDING, MODE_NAMES[mode], 0)
        if self._pending_release:
            self._release(mode)

    def _on_partial(self, session: dict, mode: str, text: str) -> None:
        # 悬浮条与输入框展示同一份清理后文本，语气词删除天然同步
        shown = simple_polish(text) if mode == "simple" else text
        self._sig_partial.emit(shown)
        if session.get("injector") is None or session.get("stream_error"):
            return
        q = session["q"]
        try:  # 只保留最新一条，打字速度跟不上识别速度时自动合并
            q.get_nowait()
        except queue.Empty:
            pass
        q.put_nowait(shown)

    def _pump_injector(self, session: dict) -> None:
        inj = session["injector"]
        q = session["q"]
        while True:
            item = q.get()
            if item is None:
                return
            if session.get("stream_error"):
                continue
            try:
                inj.update(item)
            except Exception as exc:  # noqa: BLE001
                session["stream_error"] = str(exc)
                self._sig_toast.emit(f"实时上屏中断，将在松开后整体写入：{exc}")

    def _release(self, mode: str) -> None:
        with self._lock:
            if self._state == "starting":
                self._pending_release = True
                return
            if self._state != "recording" or not self._session:
                return
            session = self._session
            if session["mode"] != mode:
                return
            duration = time.monotonic() - session["start"]
            if duration < MIN_DURATION_S:
                self._abort_session(session)
                self._state = "idle"
                self._state_since = time.monotonic()
                self._session = None
                self._sig_toast.emit("说话时间太短，已忽略")
                return
            self._state = "finalizing"
            self._state_since = time.monotonic()
        # 松手 = 立即停麦并离开"正在聆听"；识别收尾在后台进行
        session["recorder"].stop()
        self._sig_state.emit(OverlayState.PROCESSING, "转写中…", 0)
        threading.Thread(target=self._finalize, args=(session,), daemon=True).start()

    def _finalize(self, session: dict) -> None:
        mode = session["mode"]
        engine = session["engine"]
        try:
            raw = engine.stop(timeout=4.0)
        except Exception as exc:  # noqa: BLE001
            raw = None
            self._sig_toast.emit(f"识别失败：{exc}")
        session["recorder"].stop()
        if raw is None:
            self._end_session(session)
            return
        if not self._owns(session):  # 会话已被卡死自愈强制重置，丢弃结果
            return
        try:
            if not raw.strip():
                self._sig_toast.emit("未识别到内容")
                return

            if mode == "deep":
                self._sig_state.emit(OverlayState.PROCESSING, "深度润色中…", 0)
            elif mode == "simple" and self.cfg.polish.simple_llm_coherence and self.cfg.llm_ready:
                self._sig_state.emit(OverlayState.PROCESSING, "连贯润色中…", 0)

            final, note = self._polish(raw, mode)
            if not final:
                self._sig_toast.emit("润色后无有效内容")
                return
            if note:
                self._sig_toast.emit(note)

            if session.get("stream_error"):
                try:  # 流式已中断：整段补写
                    inject_text(final)
                except Exception as exc:  # noqa: BLE001
                    self._sig_toast.emit(f"注入失败（已复制到剪贴板）：{exc}")
                    return
            else:
                inj = session.get("injector")
                if inj is None:  # 深度润色：等 LLM 重写完一次性上屏
                    try:
                        inject_text(final)
                    except Exception as exc:  # noqa: BLE001
                        self._sig_toast.emit(f"注入失败（已复制到剪贴板）：{exc}")
                        return
                else:
                    session["q"].put(None)  # 停流式线程，避免并发打字
                    session["pump"].join(timeout=2.0)
                    try:  # 润色删掉的语气词在这里通过退格+补粘同步到输入框
                        inj.update(final)
                    except Exception as exc:  # noqa: BLE001
                        self._sig_toast.emit(f"注入失败（已复制到剪贴板）：{exc}")
                        return
                    inj.end()

            add_record(mode, raw, final, int((time.monotonic() - session["start"]) * 1000))
            self._sig_partial.emit(final)
            # PyQt6 的 emit() 不接受关键字参数，只能按位置传 auto_idle_ms
            self._sig_state.emit(OverlayState.DONE, MODE_NAMES[mode], 1600)
        except Exception as exc:  # noqa: BLE001 兜底：任何异常都不能让状态卡在 finalizing
            self._sig_toast.emit(f"处理失败：{exc}")
        finally:
            self._end_session(session)

    def _polish(self, raw: str, mode: str) -> tuple[str, str]:
        """返回 (最终文本, 可选提示)。"""
        if mode == "raw":
            return raw.strip(), ""
        if mode == "deep":
            try:
                return promptify(raw, self.cfg), ""
            except LlmError as exc:
                note = f"LLM 失败，已用简单润色兜底：{exc}"
                return simple_polish(raw), note
        # simple：规则润色；可选 LLM 连贯性增强（失败回退规则结果）
        if self.cfg.polish.simple_llm_coherence and self.cfg.llm_ready:
            return coherence_polish(raw, self.cfg), ""
        return simple_polish(raw), ""

    def _cancel(self) -> None:
        with self._lock:
            if self._state in ("idle", "finalizing"):
                return
            session = self._session
            self._state = "idle"
            self._state_since = time.monotonic()
            self._session = None
            self._pending_release = False
        if session is not None:
            self._abort_session(session)
        # 直接回到初始样式，不弹 ERROR 样式提示
        self._sig_state.emit(OverlayState.IDLE, "", 0)

    def _owns(self, session: dict) -> bool:
        with self._lock:
            return self._session is session

    def _end_session(self, session: dict | None = None) -> None:
        with self._lock:
            if session is not None and self._session is not session:
                return  # 会话已被强制重置或新会话开始，不要覆盖新状态
            self._state = "idle"
            self._state_since = time.monotonic()
            self._session = None

    def shutdown(self) -> None:
        """应用退出前：中止进行中的识别会话，释放音频与 WebSocket。"""
        with self._lock:
            session = self._session
            self._session = None
            self._state = "idle"
            self._state_since = time.monotonic()
        if session is not None:
            self._abort_session(session)

    @staticmethod
    def _abort_session(session: dict) -> None:
        try:
            session["recorder"].stop()
        except Exception:
            pass
        try:
            session["engine"].abort()
        except Exception:
            pass
        if session.get("q") is None:
            return

        def _stop_stream_and_undo() -> None:
            try:
                session["q"].put(None)  # 停掉流式上屏线程
                pump = session.get("pump")
                if pump is not None:
                    pump.join(timeout=1.0)
                inj = session.get("injector")
                if inj is not None:
                    inj.cancel()  # 退格撤销已打入的文字并恢复剪贴板
            except Exception:
                pass

        threading.Thread(target=_stop_stream_and_undo, daemon=True).start()


def _make_recorder(cfg: Config, engine, sig_level, sig_toast):
    from app.recorder import MicrophoneRecorder

    return MicrophoneRecorder(
        sample_rate=cfg.audio.sample_rate,
        device=cfg.audio.device,
        on_frame=engine.feed,
        on_level=lambda v: sig_level.emit(v),
        on_error=lambda msg: sig_toast.emit(msg),
    )


def main() -> int:
    cfg = load_config()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    overlay = Overlay()
    controller = Controller(cfg, overlay)
    overlay.stopClicked.connect(controller._cancel)

    def place_overlay() -> None:
        if cfg.ui.x >= 0 and cfg.ui.y >= 0:
            overlay.move(cfg.ui.x, cfg.ui.y)
        else:
            screen = app.primaryScreen().availableGeometry()
            overlay.move(
                screen.x() + (screen.width() - overlay.width()) // 2,
                screen.y() + screen.height() - overlay.height() - 90,
            )

    def on_position_moved(x: int, y: int) -> None:
        cfg.ui.x, cfg.ui.y = x, y
        from app.config import save_config

        save_config(cfg)

    overlay.positionMoved.connect(on_position_moved)
    place_overlay()
    controller.register_hotkeys()
    overlay.show()

    dialogs: dict[str, QDialog] = {}

    def open_settings() -> None:
        dlg = SettingsDialog(cfg, on_saved=lambda new_cfg: _on_cfg_saved(new_cfg, controller))
        dialogs["settings"] = dlg
        dlg.exec()

    def open_history() -> None:
        dlg = HistoryDialog()
        dialogs["history"] = dlg
        dlg.exec()

    def toggle_overlay(visible: bool) -> None:
        overlay.setVisible(visible)

    tray = TrayController(
        on_toggle_overlay=toggle_overlay,
        on_open_settings=open_settings,
        on_open_history=open_history,
        on_quit=app.quit,
    )

    if not cfg.asr_ready:
        tray.notify("请先配置 DashScope API Key（托盘 → 设置）")

    def _cleanup() -> None:
        controller.shutdown()
        controller.hotkeys.unbind_all()
        tray.hide()

    app.aboutToQuit.connect(_cleanup)

    def _on_cfg_saved(new_cfg: Config, ctrl: Controller) -> None:
        # 原地更新 cfg：拖动悬浮条等闭包持有的是这个对象，若整体替换，
        # 下次拖动会 save_config(旧对象) 把刚保存的设置覆盖回去
        for section in ("asr", "llm", "hotkey", "audio", "polish", "ui"):
            setattr(cfg, section, getattr(new_cfg, section))
        ctrl.cfg = cfg
        ctrl.register_hotkeys()
        tray.notify("设置已保存，热键已更新")

    code = app.exec()
    # dashscope Recognition 的接收线程不是 daemon，正常 sys.exit 会一直等它，
    # 表现为托盘"退出"后 pythonw.exe 仍驻留 —— 清理完成后强制结束进程。
    os._exit(code)


if __name__ == "__main__":
    sys.exit(main())
