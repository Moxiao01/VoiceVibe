"""全局热键：keyboard 库，按住开始 / 松开结束，忽略系统按键自动重复。"""
from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

import keyboard


class HotkeyManager:
    """把多个热键绑定到 (按下, 松开) 回调。

    回调运行在 keyboard 的监听线程里，必须快速返回（启动线程即可）。
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, Tuple] = {}
        self._down: set[str] = set()

    def bind(
        self,
        key: str,
        on_press: Optional[Callable[[], None]] = None,
        on_release: Optional[Callable[[], None]] = None,
    ) -> None:
        key = key.strip().lower()

        def press_handler(_event) -> None:
            if key in self._down:  # 按住时系统会重复发送 keydown
                return
            self._down.add(key)
            if on_press:
                on_press()

        def release_handler(_event) -> None:
            self._down.discard(key)
            if on_release:
                on_release()

        keyboard.on_press_key(key, press_handler, suppress=False)
        keyboard.on_release_key(key, release_handler, suppress=False)
        self._handlers[key] = (press_handler, release_handler)

    def unbind_all(self) -> None:
        for key in list(self._handlers):
            try:
                keyboard.unhook_key(key)
            except (KeyError, ValueError):
                pass
        self._handlers.clear()
        self._down.clear()
