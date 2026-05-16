"""Опційна інтеграція з LangSmith Experiments.

Запуск: .venv/bin/python -m eval.langsmith_push [--limit N]

Створює dataset (idempotent) та запускає `evaluate()` для обох архітектур.
Якщо LANGCHAIN_API_KEY не встановлений — повідомляє і завершується без помилки.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from app.baseline.agent import run_baseline
from app.common.types import ChatTurn
from app.config import settings
from app.crew.graph import run_crew
from eval.evaluators import groundedness as _groundedness
from eval.evaluators import judge_llm as _judge
from eval.evaluators import route_correct as _route
from eval.evaluators import tool_selection_accuracy as _tool

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden_set.json"
DATASET_NAME = "personal-finance-coach-golden"


def _ensure_dataset(client, tasks: list[dict[str, Any]]) -> str:
    try:
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        return dataset.id
    except Exception:
        pass
    dataset = client.create_dataset(dataset_name=DATASET_NAME,
                                    description="Golden set for Personal Finance Coach (multi-agent vs baseline).")
    for t in tasks:
        client.create_example(
            inputs={
                "query": t["query"],
                "history": t.get("history", []),
            },
            outputs={"criteria": t.get("judge_criteria", "")},
            metadata={
                "task_id": t["id"],
                "category": t["category"],
                "expected_route": t.get("expected_route"),
                "expected_tools_any_of": t.get("expected_tools_any_of", []),
                "must_contain_numbers": t.get("must_contain_numbers", []),
                "must_contain_substrings_any_of": t.get("must_contain_substrings_any_of", []),
                "must_not_contain": t.get("must_not_contain", []),
            },
            dataset_id=dataset.id,
        )
    return dataset.id


def _make_target(arch: str):
    def target(inputs: dict[str, Any]) -> dict[str, Any]:
        history = [ChatTurn(**t) for t in (inputs.get("history") or [])]
        if arch == "baseline":
            r = run_baseline(inputs["query"], history=history)
        else:
            r = run_crew(inputs["query"], history=history)
        return {
            "answer": r.answer,
            "tools_used": r.tools_used,
            "tokens_in": r.tokens_in,
            "tokens_out": r.tokens_out,
            "cost_usd": r.cost_usd,
            "latency_ms": r.latency_ms,
            "inter_agent_tokens": r.inter_agent_tokens,
            "architecture": r.architecture,
            "trace": [{"kind": s.kind, "agent": s.agent, "name": s.name} for s in r.trace],
        }
    return target


def _make_eval(fn_name: str):
    def evaluator(run, example) -> dict[str, Any]:
        task = {
            "query": example.inputs["query"],
            "judge_criteria": example.outputs.get("criteria", "") if example.outputs else "",
            **(example.metadata or {}),
        }
        result = run.outputs or {}
        if fn_name == "route_correct":
            s = _route(task, result)
        elif fn_name == "tool_selection_accuracy":
            s = _tool(task, result)
        elif fn_name == "groundedness":
            s = _groundedness(task, result)
        else:
            s = _judge(task, result)
        return {"key": s.name, "score": s.score, "comment": s.reason}
    return evaluator


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    key = settings.langchain_api_key or ""
    if not key or key.endswith("..."):
        print("⚠ LANGCHAIN_API_KEY not set (or still a placeholder) — skipping LangSmith publish.")
        print("  Set a real LANGCHAIN_API_KEY in .env to enable.")
        return

    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_ENDPOINT"] = settings.langchain_endpoint

    from langsmith import Client
    from langsmith.evaluation import evaluate

    client = Client()
    tasks = json.loads(GOLDEN.read_text(encoding="utf-8"))["tasks"]
    if args.limit:
        tasks = tasks[: args.limit]
    print(f"Ensuring dataset '{DATASET_NAME}' has {len(tasks)} examples...")
    _ensure_dataset(client, tasks)

    evaluators = [
        _make_eval("route_correct"),
        _make_eval("tool_selection_accuracy"),
        _make_eval("groundedness"),
        _make_eval("judge_llm"),
    ]
    for arch in ("baseline", "crew"):
        print(f"\n→ Running experiment: arch={arch}")
        evaluate(
            _make_target(arch),
            data=DATASET_NAME,
            evaluators=evaluators,
            experiment_prefix=f"{settings.langchain_project}-{arch}",
            max_concurrency=2,
        )
    print("\n✔ Done. See experiments in LangSmith UI under project:", settings.langchain_project)


if __name__ == "__main__":
    main()
