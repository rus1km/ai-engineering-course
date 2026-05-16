"""State для LangGraph crew."""
from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages


Route = Literal["stats", "advice", "analysis", "safety", "out_of_scope"]


class CrewState(TypedDict, total=False):
    messages: Annotated[list[dict[str, Any]], add_messages]
    user_query: str
    history: list[dict[str, Any]]
    route: Route
    route_reason: str
    final_answer: str
    # accumulated trace
    trace: list[dict[str, Any]]
    tools_used: list[str]
    tokens_in: int
    tokens_out: int
    cost_usd: float
    inter_agent_tokens: int
    cost_by_agent: dict[str, float]
