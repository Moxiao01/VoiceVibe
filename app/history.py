"""历史记录：JSONL 落盘 + 读取最近若干条。"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from app.config import _data_dir

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = _data_dir() / "history.jsonl"

_lock = threading.Lock()


def add_record(mode: str, raw: str, final: str, duration_ms: int) -> None:
    record = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode,
        "raw": raw,
        "final": final,
        "duration_ms": duration_ms,
    }
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        try:
            with open(HISTORY_PATH, "a", encoding="utf-8") as fp:
                fp.write(line + "\n")
        except OSError:
            pass  # 历史记录失败不影响主流程


def load_records(limit: int = 200) -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    records: list[dict] = []
    with _lock:
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as fp:
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
    return list(reversed(records[-limit:]))
