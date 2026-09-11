"""深度润色链路测试（mock LLM，不联网）。"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import Config
from app.polish import deep
from app.polish.llm import LlmError, _FENCE


def _cfg(llm_key="sk-x") -> Config:
    cfg = Config()
    cfg.llm.api_key = llm_key
    return cfg


def test_promptify_success_and_clean_input():
    with patch.object(deep, "chat_completion", return_value="# 任务\n写一首诗") as mock:
        out = deep.promptify("嗯，帮我写一首诗", _cfg())
    assert out == "# 任务\n写一首诗"
    # 传给 LLM 的输入应先经过规则清理
    assert mock.call_args[0][2] == "帮我写一首诗"


def test_promptify_error_raises_for_caller_fallback():
    with patch.object(deep, "chat_completion", side_effect=LlmError("boom")):
        try:
            deep.promptify("写诗", _cfg())
            raised = False
        except LlmError:
            raised = True
    assert raised


def test_coherence_falls_back_to_rules_on_error():
    with patch.object(deep, "chat_completion", side_effect=LlmError("网络超时")):
        assert deep.coherence_polish("嗯，测试一下功能", _cfg()) == "测试一下功能"


def test_coherence_skips_llm_without_key():
    assert deep.coherence_polish("嗯，测试一下功能", _cfg(llm_key="")) == "测试一下功能"


def test_coherence_uses_llm_when_available():
    with patch.object(deep, "chat_completion", return_value="整理后的通顺文本") as mock:
        out = deep.coherence_polish("嗯，测试一下功能", _cfg())
    assert out == "整理后的通顺文本"
    assert mock.call_args[0][1]  # system 提示词非空


def test_markdown_fence_stripped():
    text = "```text\n# 任务\n写诗\n```"
    assert _FENCE.sub("", text).strip() == "# 任务\n写诗"
