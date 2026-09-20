"""Windows 自启动模块测试。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.startup as startup


def test_startup_is_disabled_on_non_windows(monkeypatch):
    monkeypatch.setattr(startup.os, "name", "posix")
    assert startup.is_startup_enabled() is False
    startup.set_startup_enabled(False)


def test_enabling_on_non_windows_reports_unsupported(monkeypatch):
    monkeypatch.setattr(startup.os, "name", "posix")
    try:
        startup.set_startup_enabled(True)
    except OSError as exc:
        assert "Windows" in str(exc)
    else:
        raise AssertionError("expected unsupported-platform error")


def test_development_startup_command_includes_main_script(monkeypatch):
    monkeypatch.setattr(startup.sys, "executable", r"C:\Python\pythonw.exe")
    monkeypatch.setattr(startup.sys, "frozen", False, raising=False)
    command = startup._startup_command()
    assert command.endswith("main.py\"")
    assert "pythonw.exe" in command
