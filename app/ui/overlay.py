"""置顶悬浮条：录音状态指示、流式文字、音量波形，可拖动、不抢焦点。"""
from __future__ import annotations

import enum
import math

from PyQt6.QtCore import QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QLabel, QWidget


class OverlayState(enum.Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


_STATE_COLORS = {
    OverlayState.IDLE: QColor("#9aa0a6"),
    OverlayState.RECORDING: QColor("#ff5f57"),
    OverlayState.PROCESSING: QColor("#febc2e"),
    OverlayState.DONE: QColor("#28c840"),
    OverlayState.ERROR: QColor("#ff6b64"),
}

_W, _H = 520, 68
_BARS = 5


class _StopButton(QWidget):
    """录音时显示在最右侧的暂停按钮（自绘，窗口不抢焦点也可点击）。"""

    clicked = pyqtSignal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("结束本次输入并保留文字（Esc 取消丢弃）")
        self._hover = False

    def enterEvent(self, _event) -> None:  # noqa: N802
        self._hover = True
        self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N802
        self._hover = False
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 255, 255, 30))
            painter.drawEllipse(QRectF(0.5, 0.5, 27, 27))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(236, 238, 242, 220))
        painter.drawRoundedRect(QRectF(9.5, 8, 3.5, 12), 1.5, 1.5)
        painter.drawRoundedRect(QRectF(15.0, 8, 3.5, 12), 1.5, 1.5)


class Overlay(QWidget):
    """线程安全：所有公开方法都通过 Qt 信号槽在主线程执行（跨线程请 emit 信号）。"""

    positionMoved = pyqtSignal(int, int)
    stopClicked = pyqtSignal()

    def __init__(self, hint: str = "按住 F2 说话 · F3 深度润色 · F4 原文 · Esc 取消"):
        super().__init__(
            None,
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(_W, _H)
        self.setMouseTracking(True)

        self._state = OverlayState.IDLE
        self._detail = ""
        self._partial = ""
        self._level = 0.0
        self._pulse = 0
        self._token = 0

        self._chip = QLabel(self)
        self._chip.setGeometry(88, 9, _W - 100, 16)
        chip_font = QFont()
        chip_font.setPointSize(8)
        self._chip.setFont(chip_font)
        self._chip.setStyleSheet("color:#9aa0a6; background:transparent;")

        self._text = QLabel(self)
        self._text.setGeometry(88, 27, _W - 100, 32)
        text_font = QFont()
        text_font.setPointSize(11)
        self._text.setFont(text_font)
        self._text.setStyleSheet("color:#eceef2; background:transparent;")

        self._hint = hint
        self._stop_btn = _StopButton(self)
        self._stop_btn.move(_W - 40, (_H - 28) // 2)
        self._stop_btn.clicked.connect(self.stopClicked)
        self._stop_btn.hide()
        self._apply_state()

        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._tick)
        self._pulse_timer.start(90)

    # ---- 状态与文本 ----
    def set_hint(self, hint: str) -> None:
        self._hint = hint
        self._refresh_text()

    def set_state(self, state: OverlayState, detail: str = "", auto_idle_ms: int = 0) -> None:
        self._token += 1
        self._state = state
        self._detail = detail
        if state is OverlayState.RECORDING:
            self._partial = ""
        token = self._token
        self._apply_state()
        if auto_idle_ms > 0:
            QTimer.singleShot(
                auto_idle_ms,
                lambda: self._auto_idle(token),
            )

    def set_partial(self, text: str) -> None:
        self._partial = text
        self._refresh_text()

    def set_level(self, level: float) -> None:
        self._level = max(0.0, min(1.0, level))

    def _auto_idle(self, token: int) -> None:
        if token == self._token and self._state in (OverlayState.DONE, OverlayState.ERROR):
            self.set_state(OverlayState.IDLE)

    def _apply_state(self) -> None:
        color = _STATE_COLORS[self._state].name()
        self._chip.setStyleSheet(f"color:{color}; background:transparent;")
        # 录音时按钮占住最右侧，文字区让出宽度；其余状态按钮隐藏
        recording = self._state is OverlayState.RECORDING
        width = _W - 140 if recording else _W - 100
        self._stop_btn.setVisible(recording)
        self._chip.setGeometry(88, 9, width, 16)
        self._text.setGeometry(88, 27, width, 32)
        self._refresh_text()

    def _refresh_text(self) -> None:
        if self._state is OverlayState.IDLE:
            self._chip.setText("Voice Vibe")
            main = self._hint
        elif self._state is OverlayState.RECORDING:
            self._chip.setText(f"● 正在聆听 — {self._detail}")
            main = self._partial or "请说话…"
        elif self._state is OverlayState.PROCESSING:
            self._chip.setText(f"◐ 处理中 — {self._detail}")
            main = self._partial or "…"
        elif self._state is OverlayState.DONE:
            self._chip.setText(f"✓ 已上屏 — {self._detail}")
            main = self._partial
        else:  # ERROR
            self._chip.setText("✗ 出错了")
            main = self._detail or "未知错误"
        fm = QFontMetrics(self._text.font())
        self._text.setText(fm.elidedText(main, Qt.TextElideMode.ElideRight, self._text.width()))

    # ---- 波形/呼吸动画 ----
    def _tick(self) -> None:
        if self._state is OverlayState.RECORDING:
            self._pulse += 1
        self.update()

    # ---- 绘制 ----
    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 药丸背景
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        painter.setBrush(QColor(17, 18, 24, 236))
        painter.drawRoundedRect(QRectF(0.5, 0.5, _W - 1, _H - 1), 26, 26)

        # 状态圆点（录音时呼吸）
        color = QColor(_STATE_COLORS[self._state])
        radius = 6.0
        if self._state is OverlayState.RECORDING:
            breathe = 0.5 + 0.5 * math.sin(self._pulse / 3.0)
            radius = 6.0 + 2.0 * breathe
            halo = QColor(color)
            halo.setAlpha(int(50 + 40 * breathe))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(halo)
            painter.drawEllipse(QRectF(20 - 6, _H / 2 - 6 - radius, 12 + 2 * radius, 12 + 2 * radius))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(20, _H / 2 - radius, 2 * radius, 2 * radius))

        # 音量波形（录音时跳动，其余为静态刻度）
        painter.setBrush(QColor(154, 160, 166, 200))
        base_x, bar_w, gap = 44.0, 3.0, 4.0
        for i in range(_BARS):
            if self._state is OverlayState.RECORDING and self._level > 0.01:
                factor = 0.45 + 0.55 * abs(math.sin(self._pulse / 2.0 + i * 0.9))
                h = 4.0 + (self._level * 26.0 + 2.0) * factor
            else:
                h = 4.0
            x = base_x + i * (bar_w + gap)
            painter.drawRoundedRect(QRectF(x, _H / 2 - h / 2, bar_w, h), 1.5, 1.5)

    # ---- 拖动 ----
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _event) -> None:  # noqa: N802
        self.positionMoved.emit(self.x(), self.y())
