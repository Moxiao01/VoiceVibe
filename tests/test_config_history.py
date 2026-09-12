"""配置与历史模块测试。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config, _merge, load_config, save_config, AsrConfig
from app.history import add_record, load_records


def test_merge_partial_and_unknown_fields():
    merged = _merge(AsrConfig, {"api_key": "sk-x", "unknown_field": 1})
    assert merged.api_key == "sk-x"
    assert merged.model == "paraformer-realtime-v2"  # 未提供的字段保持默认


def test_merge_bool_from_string():
    merged = _merge(AsrConfig, {"disfluency_removal": "true"})
    assert merged.disfluency_removal is True


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    import app.config as config_mod

    monkeypatch.setattr(config_mod, "CONFIG_PATH", tmp_path / "config.toml")
    cfg = Config()
    cfg.asr.api_key = "sk-test"
    cfg.llm.model = "glm-4-plus"
    cfg.hotkey.simple = "f9"
    cfg.hotkey.mode = "toggle"
    cfg.audio.device = 3
    cfg.polish.simple_llm_coherence = True
    save_config(cfg)

    loaded = load_config()
    assert loaded.asr.api_key == "sk-test"
    assert loaded.llm.model == "glm-4-plus"
    assert loaded.hotkey.simple == "f9"
    assert loaded.hotkey.mode == "toggle"
    assert loaded.audio.device == 3
    assert loaded.polish.simple_llm_coherence is True


def test_history_write_and_read(tmp_path, monkeypatch):
    import app.history as history_mod

    monkeypatch.setattr(history_mod, "HISTORY_PATH", tmp_path / "history.jsonl")
    add_record("simple", "嗯，测试", "测试", 1500)
    add_record("deep", "口述内容", "结构化提示词", 3200)
    records = load_records()
    assert len(records) == 2
    assert records[0]["final"] == "结构化提示词"  # 最新在前
    assert records[1]["mode"] == "simple"
    # 落盘内容是合法 JSONL
    lines = (tmp_path / "history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert all(isinstance(json.loads(line), dict) for line in lines)
