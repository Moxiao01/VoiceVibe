"""托盘图标与菜单。"""
from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QAction, QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon


def _make_icon() -> QIcon:
    """手绘麦克风图标（不依赖图标素材）。"""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(35, 38, 48))
    painter.drawRoundedRect(QRectF(2, 2, 60, 60), 14, 14)
    painter.setBrush(QColor(236, 238, 242))
    painter.drawRoundedRect(QRectF(25, 12, 14, 24), 7, 7)  # 拾音头
    painter.setPen(QPen(QColor(236, 238, 242), 3))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawArc(QRectF(18, 20, 28, 24), 0, -180 * 16)  # 支架弧
    painter.drawLine(32, 44, 32, 52)  # 杆
    painter.drawLine(24, 52, 40, 52)  # 底座
    painter.end()
    return QIcon(pixmap)


class TrayController:
    def __init__(
        self,
        on_toggle_overlay,
        on_open_settings,
        on_open_history,
        on_quit,
    ):
        self.icon = QSystemTrayIcon(_make_icon())
        self.icon.setToolTip("Voice Vibe 语音输入")

        menu = QMenu()
        # QAction 不挂父对象时由 Python 引用计数管理，局部变量会在构造后被 GC，
        # 表现为菜单项凭空消失——必须用 self 持有全部引用
        self.act_overlay = QAction("显示悬浮条", checkable=True, checked=True)
        self.act_settings = QAction("设置…")
        self.act_history = QAction("历史记录…")
        self.act_quit = QAction("退出")
        self.act_overlay.toggled.connect(on_toggle_overlay)
        self.act_settings.triggered.connect(on_open_settings)
        self.act_history.triggered.connect(on_open_history)
        self.act_quit.triggered.connect(on_quit)
        menu.addAction(self.act_overlay)
        menu.addSeparator()
        menu.addAction(self.act_settings)
        menu.addAction(self.act_history)
        menu.addSeparator()
        menu.addAction(self.act_quit)

        self.menu = menu
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

    def _on_activated(self, reason) -> None:
        # 左键单击托盘图标同样弹出菜单（右键由系统自动处理）
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.menu.popup(QCursor.pos())

    def notify(self, message: str) -> None:
        self.icon.showMessage("Voice Vibe", message, QSystemTrayIcon.MessageIcon.Information, 2500)

    def hide(self) -> None:
        self.icon.hide()
