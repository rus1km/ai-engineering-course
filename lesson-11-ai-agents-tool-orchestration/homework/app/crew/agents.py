"""Node-функції для агентів у LangGraph.

Кожен агент — це функція state -> partial state. Внутрішньо вони викликають LLMClient
(той самий, що й baseline) — однакова cost-attribution.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.common.llm import get_llm, tools_for_openai
from app.config import settings
from app.crew.prompts import ADVISOR_SYSTEM, ANALYST_SYSTEM, ROUTER_SYSTEM, SAFETY_SYSTEM
from app.crew.state import CrewState
from app.tools.transactions import TOOL_DEFINITIONS, run_tool

ANALYST_TOOLS = [
    "query_transactions", "aggregate_spending", "top_categories",
    "compare_periods", "project_month_close", "get_last_payment", "credit_card_status",
]
ADVISOR_TOOLS = ANALYST_TOOLS + ["find_recurring", "detect_late_night_pattern"]
SAFETY_TOOLS = ["escalate_to_support"]


def _filter_tools(names: list[str]) -> list[dict[str, Any]]:
    return [t for t in TOOL_DEFINITIONS if t["name"] in names]


def _history_messages(state: CrewState) -> list[dict[str, Any]]:
    history = state.get("history") or []
    msgs: list[dict[str, Any]] = []
    for turn in history:
        msgs.append({"role": turn["role"], "content": turn["content"]})
    return msgs


def _accumulate(state: CrewState, *, agent: str, step: dict[str, Any]) -> dict[str, Any]:
    trace = state.get("trace") or []
    tools = state.get("tools_used") or []
    cost_by = dict(state.get("cost_by_agent") or {})

    trace = trace + [step]
    if step.get("kind") == "tool_call":
        tools = tools + [step["name"]]
    if step.get("kind") == "llm_call":
        cost_by[agent] = round(cost_by.get(agent, 0.0) + step.get("cost_usd", 0.0), 6)

    return {
        "trace": trace,
        "tools_used": tools,
        "cost_by_agent": cost_by,
        "tokens_in": (state.get("tokens_in") or 0) + step.get("tokens_in", 0),
        "tokens_out": (state.get("tokens_out") or 0) + step.get("tokens_out", 0),
        "cost_usd": round((state.get("cost_usd") or 0.0) + step.get("cost_usd", 0.0), 6),
    }


def _run_tool_loop(
    *,
    agent_name: str,
    state: CrewState,
    system_prompt: str,
    tool_names: list[str],
    model: str,
    max_tokens: int = 800,
) -> tuple[str, dict[str, Any]]:
    """Спільний tool_use loop для аналітика/радника/safety. Повертає (final_text, state_update)."""
    llm = get_llm()
    tools = tools_for_openai(_filter_tools(tool_names))

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.extend(_history_messages(state))
    messages.append({"role": "user", "content": state["user_query"]})

    update: dict[str, Any] = {}

    for iter_idx in range(settings.max_agent_iterations):
        try:
            resp = llm.chat(model=model, messages=messages, tools=tools, max_tokens=max_tokens)
        except Exception as exc:  # noqa: BLE001
            return f"[{agent_name} error: {exc}]", update

        step = {
            "kind": "llm_call",
            "agent": agent_name,
            "name": f"iter_{iter_idx}",
            "tokens_in": resp.usage_in,
            "tokens_out": resp.usage_out,
            "cost_usd": resp.cost_usd,
            "latency_ms": resp.latency_ms,
            "output": {"text": resp.text[:200], "tool_calls": [tc["name"] for tc in resp.tool_calls]},
        }
        new_state = _accumulate({**state, **update}, agent=agent_name, step=step)
        # merge accumulated counters
        for k, v in new_state.items():
            update[k] = v

        if not resp.tool_calls:
            return resp.text, update

        messages.append({
            "role": "assistant",
            "content": resp.text or None,
            "tool_calls": [
                {"id": tc["id"], "type": "function",
                 "function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in resp.tool_calls
            ],
        })
        for tc in resp.tool_calls:
            try:
                args = json.loads(tc["arguments"] or "{}")
            except json.JSONDecodeError as exc:
                args, tool_result = {}, {"error": f"Bad JSON: {exc}"}
            else:
                tt0 = time.time()
                tool_result = run_tool(tc["name"], args)
                tool_step = {
                    "kind": "tool_call",
                    "agent": agent_name,
                    "name": tc["name"],
                    "input": args,
                    "output": tool_result,
                    "latency_ms": int((time.time() - tt0) * 1000),
                }
                new_state = _accumulate({**state, **update}, agent=agent_name, step=tool_step)
                for k, v in new_state.items():
                    update[k] = v
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(tool_result, default=str, ensure_ascii=False),
            })
    return f"[{agent_name}: hit max iterations]", update


# ---------------- node implementations ----------------


def router_node(state: CrewState) -> dict[str, Any]:
    llm = get_llm()
    messages: list[dict[str, Any]] = [{"role": "system", "content": ROUTER_SYSTEM}]
    messages.extend(_history_messages(state))
    messages.append({"role": "user", "content": state["user_query"]})

    try:
        resp = llm.chat(
            model=settings.model_fast,
            messages=messages,
            tools=None,
            max_tokens=120,
            temperature=0.0,
        )
    except Exception as exc:  # noqa: BLE001
        return {"route": "stats", "route_reason": f"router_error: {exc}"}

    step = {
        "kind": "llm_call",
        "agent": "router",
        "name": "classify",
        "tokens_in": resp.usage_in,
        "tokens_out": resp.usage_out,
        "cost_usd": resp.cost_usd,
        "latency_ms": resp.latency_ms,
        "output": {"text": resp.text[:300]},
    }
    update = _accumulate(state, agent="router", step=step)

    route = "stats"
    reason = ""
    try:
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1].rstrip("`")
        parsed = json.loads(text)
        route = parsed.get("route", "stats")
        reason = parsed.get("reason", "")
    except Exception as exc:  # noqa: BLE001
        reason = f"router_parse_error: {exc}; raw={resp.text[:200]!r}"

    valid = {"stats", "advice", "analysis", "safety", "out_of_scope"}
    if route not in valid:
        route = "stats"

    update["route"] = route
    update["route_reason"] = reason
    # Router tokens count as inter-agent overhead
    update["inter_agent_tokens"] = (state.get("inter_agent_tokens") or 0) + resp.usage_in + resp.usage_out
    update["trace"] = (state.get("trace") or []) + [step, {
        "kind": "agent_handoff", "agent": "router", "name": f"-> {route}", "output": reason,
    }]
    return update


def analyst_node(state: CrewState) -> dict[str, Any]:
    final_text, update = _run_tool_loop(
        agent_name="analyst",
        state=state,
        system_prompt=ANALYST_SYSTEM,
        tool_names=ANALYST_TOOLS,
        model=settings.model_smart,
    )
    update["final_answer"] = final_text
    update["trace"] = update.get("trace", state.get("trace") or []) + [{
        "kind": "final", "agent": "analyst", "name": "answer", "output": final_text,
    }]
    return update


def advisor_node(state: CrewState) -> dict[str, Any]:
    final_text, update = _run_tool_loop(
        agent_name="advisor",
        state=state,
        system_prompt=ADVISOR_SYSTEM,
        tool_names=ADVISOR_TOOLS,
        model=settings.model_smart,
        max_tokens=1200,
    )
    update["final_answer"] = final_text
    update["trace"] = update.get("trace", state.get("trace") or []) + [{
        "kind": "final", "agent": "advisor", "name": "answer", "output": final_text,
    }]
    return update


def safety_node(state: CrewState) -> dict[str, Any]:
    final_text, update = _run_tool_loop(
        agent_name="safety",
        state=state,
        system_prompt=SAFETY_SYSTEM,
        tool_names=SAFETY_TOOLS,
        model=settings.model_fast,
        max_tokens=500,
    )
    update["final_answer"] = final_text
    update["trace"] = update.get("trace", state.get("trace") or []) + [{
        "kind": "final", "agent": "safety", "name": "answer", "output": final_text,
    }]
    return update
