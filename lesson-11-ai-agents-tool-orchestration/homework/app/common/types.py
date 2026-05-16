"""Спільні типи для baseline та crew."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class TraceStep:
    """Одна подія у трасі виконання — виклик інструмента, перехід між агентами або відповідь LLM."""

    kind: Literal["llm_call", "tool_call", "tool_result", "agent_handoff", "final"]
    agent: str  # ім'я агента ('baseline', 'router', 'analyst', 'advisor', 'safety')
    name: str = ""  # назва інструмента / повідомлення
    input: Any = None
    output: Any = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


@dataclass
class AgentResult:
    """Уніфікований результат запуску архітектури."""

    answer: str
    trace: list[TraceStep] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    architecture: Literal["baseline", "crew"] = "baseline"
    error: str | None = None
    # Multi-agent specific:
    inter_agent_tokens: int = 0  # токени, витрачені на handoffs/routing/safety
    cost_by_agent: dict[str, float] = field(default_factory=dict)


@dataclass
class ChatTurn:
    role: Literal["user", "assistant"]
    content: str
