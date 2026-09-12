"""热键管理：自动重复过滤、丢失 keyup 自愈、解绑无残留。"""
import time
from types import SimpleNamespace

import pytest

import app.hotkey as hotkey_mod
from app.hotkey import HotkeyManager


@pytest.fixture()
def hooked(monkeypatch):
    """捕获 bind 注册的 handler，代替真实 keyboard 全局钩子。"""
    registered = []
    removed = []

    def fake_hook(handler):
        registered.append(handler)

        def remove():
            removed.append(handler)
            registered.remove(handler)

        return remove

    monkeypatch.setattr(hotkey_mod.keyboard, "hook", fake_hook)
    return registered, removed


def _key(event_type: str, name: str | None = "f2"):
    return SimpleNamespace(event_type=event_type, name=name)


def test_press_release_and_repeat_filtered(hooked):
    registered, _ = hooked
    hm = HotkeyManager()
    calls = []
    hm.bind("f2", on_press=lambda: calls.append("press"), on_release=lambda: calls.append("release"))
    handler = registered[-1]

    handler(_key("down"))
    handler(_key("down"))  # 按住不放产生的系统自动重复
    handler(_key("up"))
    handler(_key("down"))  # 物理再次按下

    assert calls == ["press", "release", "press"]


def test_lost_keyup_self_heals(hooked, monkeypatch):
    # keyup 事件被吞（见 app/inject.py 的历史问题）后，未自愈时后续所有
    # keydown 都会被误判为自动重复，热键"永远按不动"。间隔超过重复窗口
    # 的 keydown 必须视作重新按下。
    registered, _ = hooked
    monkeypatch.setattr(hotkey_mod, "_REPEAT_WINDOW_S", 0.05)
    hm = HotkeyManager()
    presses = []
    hm.bind("f2", on_press=lambda: presses.append(1))
    handler = registered[-1]

    handler(_key("down"))  # 随后的 keyup 丢失
    time.sleep(0.08)
    handler(_key("down"))

    assert len(presses) == 2


def test_unbind_removes_handlers(hooked):
    registered, removed = hooked
    hm = HotkeyManager()
    hm.bind("f2", on_press=lambda: None)
    assert len(registered) == 1

    hm.unbind_all()

    assert registered == []
    assert len(removed) == 1


def test_rebind_after_unbind_no_stale_handlers(hooked):
    # 回归：keyboard.on_press_key/on_release_key 的 unhook 只能摘掉 release
    # 钩子，press 钩子残留 —— 重绑热键后旧 handler 仍然触发，开始/停止错乱
    registered, _ = hooked
    hm = HotkeyManager()
    old, new = [], []
    hm.bind("f2", on_press=lambda: old.append(1))
    hm.unbind_all()
    hm.bind("f2", on_press=lambda: new.append(1))

    registered[-1](_key("down"))

    assert old == []
    assert new == [1]


def test_other_keys_ignored(hooked):
    registered, _ = hooked
    hm = HotkeyManager()
    calls = []
    hm.bind("f2", on_press=lambda: calls.append("press"))
    handler = registered[-1]

    handler(_key("down", name="f3"))
    handler(_key("up", name=None))

    assert calls == []
