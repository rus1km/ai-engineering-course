"""Тонкий Anthropic-клієнт для live-режиму.

Не імпортує SDK, поки реально не викличуть Claude — щоб offline-прогін
працював без встановленого `anthropic` і без ключа.
"""
from __future__ import annotations

import time

from app import config


def _model_id(model: str) -> str:
    """Haiku 4.5 потребує версіонованого id; решта — як є."""
    if model == "claude-haiku-4-5":
        return "claude-haiku-4-5-20251001"
    return model


def complete(system: str, user: str, *, max_tokens: int = 512, temperature: float = 0.0) -> str:
    """Один turn до Claude. Кидає виняток, якщо ключ/SDK відсутні."""
    import anthropic  # локальний імпорт — лише в live-режимі

    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set — потрібен для LLM_MODE=live")

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=config.LLM_TIMEOUT_SECONDS)
    delay = 4.0
    for attempt in range(4):
        try:
            resp = client.messages.create(
                model=_model_id(config.MODEL),
                system=system,
                messages=[{"role": "user", "content": user}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return "".join(b.text for b in resp.content if b.type == "text")
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if ("429" in msg or "overloaded" in msg) and attempt < 3:
                time.sleep(delay)
                delay = min(delay * 2, 20)
                continue
            raise
    return ""
