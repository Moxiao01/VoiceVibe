"""OpenAI 兼容的大模型客户端（智谱/通义/Kimi/OpenAI/Ollama 等均可）。"""
from __future__ import annotations

import re
import time

from openai import OpenAI

from ..config import LlmConfig

_FENCE = re.compile(r"^```[\w-]*\s*\n?|\s*```$")


class LlmError(RuntimeError):
    pass


def chat_completion(cfg: LlmConfig, system: str, user: str, temperature: float | None = None) -> str:
    """单轮对话，返回模型输出文本；失败抛 LlmError。"""
    if not cfg.api_key:
        raise LlmError("未配置 llm.api_key")
    client = OpenAI(
        base_url=cfg.base_url or None,
        api_key=cfg.api_key,
        timeout=cfg.timeout,
        max_retries=0,
    )
    last_exc: Exception | None = None
    for attempt in range(2):  # 网络抖动重试一次
        try:
            resp = client.chat.completions.create(
                model=cfg.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=cfg.temperature if temperature is None else temperature,
            )
            content = (resp.choices[0].message.content or "").strip()
            if not content:
                raise LlmError("模型返回了空内容")
            return _FENCE.sub("", content).strip()
        except LlmError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == 0:
                time.sleep(0.6)
    raise LlmError(f"LLM 请求失败：{last_exc}")
