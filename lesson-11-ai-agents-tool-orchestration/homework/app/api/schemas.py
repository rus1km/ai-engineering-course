from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatTurnDTO(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    architecture: Literal["baseline", "crew"] = "crew"
    history: list[ChatTurnDTO] = Field(default_factory=list)


class TraceStepDTO(BaseModel):
    kind: str
    agent: str
    name: str = ""
    output: Any = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class ChatResponse(BaseModel):
    architecture: str
    answer: str
    tools_used: list[str]
    tokens_in: int
    tokens_out: int
    cost_usd: float
    latency_ms: int
    inter_agent_tokens: int
    cost_by_agent: dict[str, float]
    trace: list[TraceStepDTO]
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    transactions_count: int
    dataset_period: dict[str, str]
