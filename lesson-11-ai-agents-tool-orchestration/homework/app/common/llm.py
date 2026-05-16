"""LLM-клієнт з двома провайдерами: OpenRouter та Anthropic direct.

Уніфікований інтерфейс LLMClient.chat() приймає OpenAI-style повідомлення/tools
і повертає однаковий LLMResponse незалежно від провайдера. Це дозволяє baseline і
crew не знати, який LLM-бекенд активний.

Перемикання — через .env: LLM_PROVIDER=openrouter (default) або anthropic.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from app.config import settings

# Approximate prices (USD per 1M tokens). Для звіту достатньо.
PRICING: dict[str, tuple[float, float]] = {
    "anthropic/claude-haiku-4-5": (1.0, 5.0),
    "anthropic/claude-sonnet-4-6": (3.0, 15.0),
    "anthropic/claude-opus-4-7": (15.0, 75.0),
    "openai/gpt-4o-mini": (0.15, 0.6),
    "openai/gpt-4o": (2.5, 10.0),
}


def _price_for(model: str) -> tuple[float, float]:
    if model in PRICING:
        return PRICING[model]
    for k, v in PRICING.items():
        if model.endswith(k.split("/")[-1]):
            return v
    return (3.0, 15.0)  # fallback ≈ Sonnet


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict[str, Any]]
    usage_in: int
    usage_out: int
    cost_usd: float
    latency_ms: int
    stop_reason: str
    raw: Any = None


# ----------------------- OpenRouter provider -----------------------


class OpenRouterProvider:
    def __init__(self) -> None:
        from openai import OpenAI
        api_key = settings.openrouter_api_key
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self.client = OpenAI(
            base_url=settings.openrouter_base_url,
            api_key=api_key,
            timeout=settings.llm_timeout_seconds,
        )

    def chat(self, *, model, messages, tools, temperature, max_tokens) -> LLMResponse:
        t0 = time.time()
        kwargs: dict[str, Any] = {
            "model": model, "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        try:
            resp = self.client.chat.completions.create(**kwargs)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "can only afford" in msg:
                m = re.search(r"afford (\d+)", msg)
                if m:
                    kwargs["max_tokens"] = max(200, int(m.group(1)) - 50)
                    resp = self.client.chat.completions.create(**kwargs)
                else:
                    raise
            else:
                raise
        latency_ms = int((time.time() - t0) * 1000)
        choice = resp.choices[0]
        msg_obj = choice.message
        text = msg_obj.content or ""
        tc = []
        if getattr(msg_obj, "tool_calls", None):
            for c in msg_obj.tool_calls:
                tc.append({
                    "id": c.id,
                    "name": c.function.name,
                    "arguments": c.function.arguments,
                })
        usage = resp.usage
        u_in = getattr(usage, "prompt_tokens", 0) or 0
        u_out = getattr(usage, "completion_tokens", 0) or 0
        p_in, p_out = _price_for(model)
        cost = (u_in / 1_000_000) * p_in + (u_out / 1_000_000) * p_out
        return LLMResponse(
            text=text, tool_calls=tc, usage_in=u_in, usage_out=u_out,
            cost_usd=round(cost, 6), latency_ms=latency_ms,
            stop_reason=choice.finish_reason or "stop", raw=resp,
        )


# ----------------------- Anthropic provider -----------------------


def _anthropic_model_name(model: str) -> str:
    """'anthropic/claude-sonnet-4-6' -> 'claude-sonnet-4-6'. Haiku 4.5 needs versioned id."""
    name = model.split("/", 1)[1] if "/" in model else model
    if name == "claude-haiku-4-5":
        return "claude-haiku-4-5-20251001"
    return name


def _to_anthropic_messages(openai_messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Конвертує OpenAI-style messages в Anthropic-style.

    OpenAI:
      system msg → окремий рядок з role=system
      assistant з tool_calls → assistant з content_blocks tool_use
      tool result → user з content_blocks tool_result
    Anthropic:
      system — окремий параметр у API
      кожне assistant з tool_use містить blocks: [{type:text,...}, {type:tool_use,...}]
      tool_result повертається у наступному user-повідомленні як block
    """
    system_parts: list[str] = []
    anth: list[dict[str, Any]] = []

    i = 0
    while i < len(openai_messages):
        m = openai_messages[i]
        role = m["role"]
        if role == "system":
            if m.get("content"):
                system_parts.append(m["content"])
            i += 1
            continue
        if role == "user":
            anth.append({"role": "user", "content": m["content"]})
            i += 1
            continue
        if role == "assistant":
            blocks: list[dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m.get("tool_calls") or []:
                fn = tc["function"]
                args = fn["arguments"]
                if isinstance(args, str):
                    try:
                        args = json.loads(args) if args.strip() else {}
                    except json.JSONDecodeError:
                        args = {}
                blocks.append({"type": "tool_use", "id": tc["id"], "name": fn["name"], "input": args})
            anth.append({"role": "assistant", "content": blocks if blocks else [{"type": "text", "text": ""}]})
            i += 1
            continue
        if role == "tool":
            # Collect consecutive tool results into one user message
            results = []
            while i < len(openai_messages) and openai_messages[i]["role"] == "tool":
                tm = openai_messages[i]
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tm["tool_call_id"],
                    "content": tm["content"],
                })
                i += 1
            anth.append({"role": "user", "content": results})
            continue
        # unknown role
        i += 1
    system_text = "\n\n".join(system_parts) if system_parts else None
    return system_text, anth


def _openai_tools_to_anthropic(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Конвертує OpenAI tool format назад у Anthropic native (input_schema)."""
    out = []
    for t in tools:
        if t.get("type") == "function":
            fn = t["function"]
            out.append({"name": fn["name"], "description": fn.get("description", ""), "input_schema": fn.get("parameters", {})})
        elif "input_schema" in t:
            out.append(t)
    return out


class AnthropicProvider:
    def __init__(self) -> None:
        import anthropic
        api_key = settings.anthropic_api_key
        if not api_key or api_key.endswith("..."):
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.client = anthropic.Anthropic(api_key=api_key, timeout=settings.llm_timeout_seconds)

    def chat(self, *, model, messages, tools, temperature, max_tokens) -> LLMResponse:
        t0 = time.time()
        anth_model = _anthropic_model_name(model)
        system_text, anth_messages = _to_anthropic_messages(messages)
        anth_tools = _openai_tools_to_anthropic(tools) if tools else None
        kwargs: dict[str, Any] = {
            "model": anth_model, "messages": anth_messages,
            "max_tokens": max_tokens, "temperature": temperature,
        }
        if system_text:
            kwargs["system"] = system_text
        if anth_tools:
            kwargs["tools"] = anth_tools
        # Retry on 429 (rate limit) and overloaded errors with exponential backoff
        delay = 5.0
        for attempt in range(5):
            try:
                resp = self.client.messages.create(**kwargs)
                break
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                is_rate = "429" in msg or "rate_limit" in msg or "overloaded" in msg
                if is_rate and attempt < 4:
                    time.sleep(delay)
                    delay = min(delay * 2, 30)
                    continue
                raise
        latency_ms = int((time.time() - t0) * 1000)

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": json.dumps(block.input, ensure_ascii=False),
                })

        u_in = resp.usage.input_tokens
        u_out = resp.usage.output_tokens
        p_in, p_out = _price_for(model)
        cost = (u_in / 1_000_000) * p_in + (u_out / 1_000_000) * p_out
        return LLMResponse(
            text="".join(text_parts),
            tool_calls=tool_calls,
            usage_in=u_in, usage_out=u_out,
            cost_usd=round(cost, 6), latency_ms=latency_ms,
            stop_reason=resp.stop_reason or "end_turn",
            raw=resp,
        )


# ----------------------- public client -----------------------


class LLMClient:
    def __init__(self) -> None:
        provider = (settings.llm_provider or "openrouter").lower()
        if provider == "anthropic":
            self._impl = AnthropicProvider()
        else:
            self._impl = OpenRouterProvider()
        self.provider = provider

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        return self._impl.chat(model=model, messages=messages, tools=tools,
                               temperature=temperature, max_tokens=max_tokens)


_client_singleton: LLMClient | None = None


def get_llm() -> LLMClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = LLMClient()
    return _client_singleton


def tools_for_openai(tool_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tool_defs
    ]
