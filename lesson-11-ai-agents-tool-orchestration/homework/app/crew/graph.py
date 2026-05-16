"""LangGraph supervisor для Personal Finance Coach."""
from __future__ import annotations

import time
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.common.types import AgentResult, ChatTurn, TraceStep
from app.crew.agents import advisor_node, analyst_node, router_node, safety_node
from app.crew.state import CrewState


def _route_decision(state: CrewState) -> str:
    route = state.get("route", "stats")
    if route in {"stats", "analysis"}:
        return "analyst"
    if route == "advice":
        return "advisor"
    if route in {"safety", "out_of_scope"}:
        return "safety"
    return "analyst"


def build_crew():
    g = StateGraph(CrewState)
    g.add_node("router", router_node)
    g.add_node("analyst", analyst_node)
    g.add_node("advisor", advisor_node)
    g.add_node("safety", safety_node)

    g.add_edge(START, "router")
    g.add_conditional_edges(
        "router", _route_decision,
        {"analyst": "analyst", "advisor": "advisor", "safety": "safety"},
    )
    g.add_edge("analyst", END)
    g.add_edge("advisor", END)
    g.add_edge("safety", END)
    return g.compile()


_compiled_graph = None


def get_crew():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_crew()
    return _compiled_graph


def run_crew(user_message: str, history: list[ChatTurn] | None = None) -> AgentResult:
    t0 = time.time()
    history_dicts = [{"role": h.role, "content": h.content} for h in (history or [])]
    graph = get_crew()

    initial: CrewState = {
        "user_query": user_message,
        "history": history_dicts,
        "trace": [],
        "tools_used": [],
        "tokens_in": 0,
        "tokens_out": 0,
        "cost_usd": 0.0,
        "inter_agent_tokens": 0,
        "cost_by_agent": {},
    }
    final_state: CrewState = graph.invoke(initial)

    answer = final_state.get("final_answer", "") or ""
    trace_steps = [TraceStep(**s) if not isinstance(s, TraceStep) else s for s in final_state.get("trace", [])]

    return AgentResult(
        answer=answer,
        trace=trace_steps,
        tools_used=final_state.get("tools_used", []),
        tokens_in=final_state.get("tokens_in", 0),
        tokens_out=final_state.get("tokens_out", 0),
        cost_usd=round(final_state.get("cost_usd", 0.0), 6),
        latency_ms=int((time.time() - t0) * 1000),
        architecture="crew",
        inter_agent_tokens=final_state.get("inter_agent_tokens", 0),
        cost_by_agent=final_state.get("cost_by_agent", {}),
    )
