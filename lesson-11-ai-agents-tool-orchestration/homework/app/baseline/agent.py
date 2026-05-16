"""Single-agent baseline: один LLM з усіма tools + ручний tool_use loop.

Зумисно "плаский" — без LangGraph/CrewAI. Якщо crew покращує метрики порівняно
з цим бейслайном, ускладнення виправдане.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.common.llm import LLMResponse, get_llm, tools_for_openai
from app.common.types import AgentResult, ChatTurn, TraceStep
from app.config import settings
from app.tools.transactions import TOOL_DEFINITIONS, run_tool

SYSTEM_PROMPT = """\
Ти — Personal Finance Coach, AI-помічник у банківському застосунку. Користувач звертається до тебе \
з питаннями про свої витрати, бюджет і поради щодо економії.

ПРАВИЛА:
1. Тон — дружній, на "ти", без менторства. У стресових темах (борги, fraud) — емпатично.
2. Всі числа БЕРИ ЛИШЕ з результатів tool calls. Якщо інструмент не повернув даних — кажи, що даних немає.
3. Поради повинні бути конкретними: посилатися на реальні merchants та суми, містити одну actionable-дію.
4. Дата "сьогодні" = 2025-11-30 (dataset). Усі суми у USD — пиши "$" або "USD", НЕ "грн".
5. Якщо користувач повідомляє про fraud, втрачену картку або просить заблокувати/оскаржити транзакцію — \
викликай escalate_to_support (НЕ намагайся виконати дію сам).
6. Out-of-scope запити ("купи акції", "переклади гроші") — ввічливо відмовляй з переадресацією на доступні функції.
7. Multi-turn: якщо запит лаконічний ("а минулого місяця?"), інтерпретуй його у контексті попереднього питання.
8. Уникай generic-фраз "consider reducing dining out" — користуйся числами.

ФОРМАТ ВІДПОВІДЕЙ:
- Короткі — до 4 коротких речень або до 4 пунктів зі сумами.
- Без зайвих фраз "based on the data". Дані — це норма, не варто це акцентувати.

ІНСТРУМЕНТИ: викликай скільки потрібно для відповіді (часто 1–3). Не вигадуй мерчантів — якщо merchant_contains \
не знаходить запис, скажи про це і запропонуй уточнити.
"""


def _to_openai_messages(history: list[ChatTurn], user_message: str) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for t in history:
        msgs.append({"role": t.role, "content": t.content})
    msgs.append({"role": "user", "content": user_message})
    return msgs


def run_baseline(
    user_message: str,
    history: list[ChatTurn] | None = None,
    model: str | None = None,
    max_iters: int | None = None,
) -> AgentResult:
    t0 = time.time()
    history = history or []
    model = model or settings.model_baseline
    max_iters = max_iters or settings.max_agent_iterations

    messages = _to_openai_messages(history, user_message)
    tools = tools_for_openai(TOOL_DEFINITIONS)
    llm = get_llm()

    result = AgentResult(answer="", architecture="baseline")
    tools_used: list[str] = []

    final_text: str | None = None
    for iter_idx in range(max_iters):
        try:
            resp: LLMResponse = llm.chat(model=model, messages=messages, tools=tools, max_tokens=800)
        except Exception as exc:  # noqa: BLE001
            result.error = f"LLM error: {exc}"
            break

        result.trace.append(TraceStep(
            kind="llm_call",
            agent="baseline",
            name=f"iter_{iter_idx}",
            input={"messages_count": len(messages)},
            output={"text": resp.text[:200], "tool_calls": [tc["name"] for tc in resp.tool_calls]},
            tokens_in=resp.usage_in,
            tokens_out=resp.usage_out,
            cost_usd=resp.cost_usd,
            latency_ms=resp.latency_ms,
        ))
        result.tokens_in += resp.usage_in
        result.tokens_out += resp.usage_out
        result.cost_usd += resp.cost_usd

        if not resp.tool_calls:
            final_text = resp.text
            break

        # Append the assistant message with tool calls in OpenAI format
        messages.append({
            "role": "assistant",
            "content": resp.text or None,
            "tool_calls": [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {"name": tc["name"], "arguments": tc["arguments"]},
                }
                for tc in resp.tool_calls
            ],
        })

        for tc in resp.tool_calls:
            try:
                args = json.loads(tc["arguments"] or "{}")
            except json.JSONDecodeError as exc:
                args = {}
                tool_result: Any = {"error": f"Invalid JSON arguments: {exc}"}
            else:
                tt0 = time.time()
                tool_result = run_tool(tc["name"], args)
                tool_latency = int((time.time() - tt0) * 1000)
                result.trace.append(TraceStep(
                    kind="tool_call",
                    agent="baseline",
                    name=tc["name"],
                    input=args,
                    output=tool_result,
                    latency_ms=tool_latency,
                ))
                tools_used.append(tc["name"])

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(tool_result, default=str, ensure_ascii=False),
            })
    else:
        result.error = f"Hit max iterations ({max_iters}) without final answer."

    if final_text is None and not result.error:
        result.error = "No final answer."
    result.answer = final_text or "Виникла помилка під час обробки. Спробуй переформулювати запит."
    result.tools_used = tools_used
    result.cost_by_agent = {"baseline": round(result.cost_usd, 6)}
    result.inter_agent_tokens = 0  # для single-agent — завжди 0
    result.latency_ms = int((time.time() - t0) * 1000)
    result.trace.append(TraceStep(kind="final", agent="baseline", name="answer", output=result.answer))
    return result
