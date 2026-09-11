"""深度润色：LLM 后处理。简单润色的连贯增强 + 提示词化。"""
from __future__ import annotations

from ..config import Config
from .llm import LlmError, chat_completion
from .prompts import COHERENCE_SYSTEM, PROMPTIFY_SYSTEM
from .simple import simple_polish


def coherence_polish(text: str, cfg: Config) -> str:
    """简单润色的 LLM 连贯性增强；任何失败都回退到规则润色结果。"""
    base = simple_polish(text)
    if not base or not cfg.llm_ready:
        return base
    try:
        return chat_completion(cfg.llm, COHERENCE_SYSTEM, base) or base
    except LlmError:
        return base


def promptify(text: str, cfg: Config) -> str:
    """深度润色：先做规则清理（给 LLM 干净的输入），再让 LLM 重写为提示词。

    失败时抛 LlmError，由调用方决定降级策略。
    """
    base = simple_polish(text)
    if not base:
        return ""
    return chat_completion(cfg.llm, PROMPTIFY_SYSTEM, base)
