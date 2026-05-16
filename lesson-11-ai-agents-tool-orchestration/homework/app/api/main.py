from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse

from app.api.schemas import ChatRequest, ChatResponse, HealthResponse, TraceStepDTO
from app.baseline.agent import run_baseline
from app.common.types import ChatTurn
from app.crew.graph import run_crew
from app.tools.data import load_transactions

app = FastAPI(title="Personal Finance Coach", version="0.1.0")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    df = load_transactions()
    return HealthResponse(
        status="ok",
        transactions_count=int(len(df)),
        dataset_period={
            "start": df["date"].min().strftime("%Y-%m-%d"),
            "end": df["date"].max().strftime("%Y-%m-%d"),
        },
    )


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest) -> ChatResponse:
    history = [ChatTurn(role=t.role, content=t.content) for t in req.history]
    if req.architecture == "baseline":
        result = run_baseline(req.message, history=history)
    elif req.architecture == "crew":
        result = run_crew(req.message, history=history)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown architecture: {req.architecture}")

    trace_dtos = [
        TraceStepDTO(
            kind=s.kind, agent=s.agent, name=s.name,
            output=s.output, tokens_in=s.tokens_in, tokens_out=s.tokens_out,
            cost_usd=s.cost_usd, latency_ms=s.latency_ms,
        )
        for s in result.trace
    ]
    return ChatResponse(
        architecture=result.architecture,
        answer=result.answer,
        tools_used=result.tools_used,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
        inter_agent_tokens=result.inter_agent_tokens,
        cost_by_agent=result.cost_by_agent,
        trace=trace_dtos,
        error=result.error,
    )
