"""Windows 当前用户开机自启动设置。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

STARTUP_VALUE_NAME = "VoiceVibe"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _startup_command() -> str:
    """返回启动项使用的命令，开发运行时避免打开控制台窗口。"""
    executable = Path(sys.executable)
    if not getattr(sys, "frozen", False):
        if executable.name.lower() == "python.exe":
            executable = executable.with_name("pythonw.exe")
        return f'"{executable}" "{Path(__file__).resolve().parent.parent / "main.py"}"'
    return f'"{executable}"'


def is_startup_enabled() -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False


def set_startup_enabled(enabled: bool) -> None:
    """启用或关闭当前用户自启动，不需要管理员权限。"""
    if os.name != "nt":
        if enabled:
            raise OSError("开机自启动仅支持 Windows")
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, STARTUP_VALUE_NAME, 0, winreg.REG_SZ, _startup_command())
        else:
            try:
                winreg.DeleteValue(key, STARTUP_VALUE_NAME)
            except FileNotFoundError:
                pass
