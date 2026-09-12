"""把文本注入当前焦点应用：写剪贴板 → 模拟 Ctrl+V → 延迟恢复剪贴板。"""
from __future__ import annotations

import ctypes
import threading
import time

import pyperclip

# 不用 keyboard.send() 注入按键：它会把 keyboard 库监听器的 is_replaying
# 标志置真，期间用户按下的真实按键（包括"停止"热键 F2/F3/F4/Esc）会被
# 当作回放事件直接丢弃 —— 表现为流式修正刚发生时按热键停止不了。
# 这里用 keybd_event 直接发 VK，效果相同但不触碰该标志。
_user32 = ctypes.windll.user32
_KEYEVENTF_KEYUP = 0x0002

# (虚拟键码, 扫描码)
_KEY_CODES = {
    "ctrl": (0x11, 0x1D),
    "v": (0x56, 0x2F),
    "backspace": (0x08, 0x0E),
}
_COMBO_KEYS = {"ctrl+v": ("ctrl", "v")}


def send_keys(spec: str) -> None:
    """发送组合键（如 "ctrl+v"）或单键（如 "backspace"），按下/抬起逆序交错。"""
    keys = _COMBO_KEYS.get(spec, (spec,))
    for name in keys:
        vk, scan = _KEY_CODES[name]
        _user32.keybd_event(vk, scan, 0, 0)
    for name in reversed(keys):
        vk, scan = _KEY_CODES[name]
        _user32.keybd_event(vk, scan, _KEYEVENTF_KEYUP, 0)


def inject_text(text: str, restore_delay: float = 1.2) -> None:
    """在最前台、当前有焦点的输入光标处粘贴文本。

    恢复剪贴板延迟足够长，保证目标应用完成读取；期间用户复制的
    内容可能被覆盖，属已知取舍（见 README）。
    """
    backup: str | None
    try:
        backup = pyperclip.paste()
    except Exception:
        backup = None
    try:
        pyperclip.copy(text)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"写入剪贴板失败：{exc}") from exc
    time.sleep(0.08)  # 等剪贴板更新对系统可见
    send_keys("ctrl+v")
    if backup is not None and backup != text:
        threading.Timer(restore_delay, lambda: _safe_restore(backup)).start()


def _safe_restore(content: str) -> None:
    try:
        pyperclip.copy(content)
    except Exception:
        pass


def _safe_paste() -> str | None:
    try:
        return pyperclip.paste()
    except Exception:
        return None


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


class LiveInjector:
    """流式上屏：把不断增长的文本实时打进当前焦点输入框。

    新文本只是追加时只粘增量；被修订（识别改写、语气词删除）时先按
    字符数退格抹掉差异尾部，再补粘正确内容。
    局限：要求光标始终停在已打入文本的末尾（中途点击/切换窗口会错位），
    且目标程序需支持 Ctrl+V 粘贴。
    """

    def __init__(self, restore_delay: float = 1.2):
        self._backup: str | None = None
        self._injected = ""
        self._pasted = False
        self._restore_delay = restore_delay

    @property
    def injected(self) -> str:
        return self._injected

    def begin(self) -> None:
        self._backup = _safe_paste()
        self._injected = ""
        self._pasted = False

    def update(self, text: str) -> None:
        if text == self._injected:
            return
        common = _common_prefix_len(self._injected, text)
        self._erase(len(self._injected) - common)
        if common < len(text):
            try:
                pyperclip.copy(text[common:])
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"写入剪贴板失败：{exc}") from exc
            time.sleep(0.08)  # 等剪贴板更新对系统可见
            send_keys("ctrl+v")
            self._pasted = True
        self._injected = text

    def _erase(self, count: int) -> None:
        if count <= 0:
            return
        for _ in range(count):
            send_keys("backspace")
        time.sleep(0.03)  # 等编辑器处理完退格再粘补

    def cancel(self) -> None:
        """撤销已打入的文字并安排恢复剪贴板。"""
        self.update("")
        self.end()

    def end(self) -> None:
        backup, self._backup = self._backup, None
        if backup is not None and self._pasted:
            threading.Timer(self._restore_delay, lambda: _safe_restore(backup)).start()
        self._injected = ""
