"""把文本注入当前焦点应用：写剪贴板 → 模拟 Ctrl+V → 延迟恢复剪贴板。"""
from __future__ import annotations

import threading
import time

import keyboard
import pyperclip


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
    keyboard.send("ctrl+v")
    if backup is not None and backup != text:
        threading.Timer(restore_delay, lambda: _safe_restore(backup)).start()


def _safe_restore(content: str) -> None:
    try:
        pyperclip.copy(content)
    except Exception:
        pass
