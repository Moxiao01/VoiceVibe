"""全局热键：keyboard 库全局钩子，按住开始 / 松开结束，忽略系统按键自动重复。

不用 keyboard.on_press_key/on_release_key：二者对同一个 key 会各注册一次
hook_key，而库内部 _hooks[key] 被后注册者覆盖，unhook_key(key) 只能摘掉
release 钩子 —— press 钩子永久残留，重绑热键（改设置保存）后新旧 handler
叠加，开始/停止逻辑错乱。keyboard.hook() 按回调精确解绑，无此问题。

注入文字造成的按键风暴也不再吞事件：inject.py 已弃用 keyboard.send()
（详见该文件说明）。这里仍保留一层自愈：若某次 keyup 事件丢失，后续
keydown 会被误判为自动重复 —— 超过 _REPEAT_WINDOW_S 的 keydown 视为
重新按下。
"""
from __future__ import annotations

import time
from typing import Callable, Dict, Optional

import keyboard

# 判定为"按住不放的自动重复"的最大 keydown 间隔。Windows 重复延迟最长
# 约 1 秒，物理松开后重新按下的间隔通常远大于此。
_REPEAT_WINDOW_S = 1.5


class HotkeyManager:
    """把多个热键绑定到 (按下, 松开) 回调。

    回调运行在 keyboard 的监听线程里，必须快速返回（启动线程即可）。
    """

    def __init__(self) -> None:
        self._removers: Dict[str, Callable[[], None]] = {}
        self._down_at: Dict[str, float] = {}  # key → 最近一次 keydown 时刻

    def bind(
        self,
        key: str,
        on_press: Optional[Callable[[], None]] = None,
        on_release: Optional[Callable[[], None]] = None,
    ) -> None:
        key = key.strip().lower()

        def handler(event) -> None:
            if event.name != key:
                return
            if event.event_type == keyboard.KEY_DOWN:
                now = time.monotonic()
                last = self._down_at.get(key)
                is_repeat = last is not None and now - last < _REPEAT_WINDOW_S
                self._down_at[key] = now  # 按住期间持续刷新，整段按住都视为重复
                if is_repeat:
                    return
                if on_press:
                    on_press()
            else:
                self._down_at.pop(key, None)
                if on_release:
                    on_release()

        self._removers[key] = keyboard.hook(handler)

    def unbind_all(self) -> None:
        for remove in self._removers.values():
            try:
                remove()
            except (KeyError, ValueError):
                pass
        self._removers.clear()
        self._down_at.clear()
