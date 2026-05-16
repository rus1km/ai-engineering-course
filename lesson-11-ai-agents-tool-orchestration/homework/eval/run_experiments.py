"""Запускає golden set на обох архітектурах, обчислює метрики, зберігає результати.

Use: .venv/bin/python -m eval.run_experiments [--limit N]

Якщо встановлений LANGCHAIN_API_KEY — також публікує в LangSmith Experiments.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.baseline.agent import run_baseline
from app.common.types import AgentResult, ChatTurn, TraceStep
from app.config import settings
from app.crew.graph import run_crew
from eval.evaluators import run_all_evaluators

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "data" / "golden_set.json"
RESULTS_DIR = ROOT / "results"


def _result_to_dict(r: AgentResult) -> dict[str, Any]:
    return {
        "architecture": r.architecture,
        "answer": r.answer,
        "tools_used": r.tools_used,
        "tokens_in": r.tokens_in,
        "tokens_out": r.tokens_out,
        "cost_usd": r.cost_usd,
        "latency_ms": r.latency_ms,
        "inter_agent_tokens": r.inter_agent_tokens,
        "cost_by_agent": r.cost_by_agent,
        "trace": [
            {"kind": s.kind, "agent": s.agent, "name": s.name,
             "output": s.output, "tokens_in": s.tokens_in, "tokens_out": s.tokens_out,
             "cost_usd": s.cost_usd, "latency_ms": s.latency_ms}
            for s in r.trace
        ],
        "error": r.error,
    }


def _run_task(arch: str, task: dict[str, Any]) -> dict[str, Any]:
    history = [ChatTurn(**t) for t in task.get("history", [])]
    fn = run_baseline if arch == "baseline" else run_crew
    t0 = time.time()
    try:
        result = fn(task["query"], history=history)
    except Exception as exc:  # noqa: BLE001
        result = AgentResult(answer=f"[error: {exc}]", architecture=arch, error=str(exc))  # type: ignore
    wall_ms = int((time.time() - t0) * 1000)
    rd = _result_to_dict(result)
    rd["wall_ms"] = wall_ms
    return rd


def aggregate(arch_results: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [r["result"]["latency_ms"] for r in arch_results]
    costs = [r["result"]["cost_usd"] for r in arch_results]
    tokens_in = [r["result"]["tokens_in"] for r in arch_results]
    tokens_out = [r["result"]["tokens_out"] for r in arch_results]
    inter = [r["result"]["inter_agent_tokens"] for r in arch_results]
    cost_by_agent: dict[str, float] = {}
    for r in arch_results:
        for k, v in (r["result"].get("cost_by_agent") or {}).items():
            cost_by_agent[k] = round(cost_by_agent.get(k, 0.0) + v, 6)

    def metric(name: str) -> float:
        vals = [s["score"] for r in arch_results for s in r["evals"] if s["name"] == name]
        return round(sum(vals) / len(vals), 3) if vals else 0.0

    total_tokens = sum(tokens_in) + sum(tokens_out)
    inter_pct = round(sum(inter) / total_tokens * 100, 2) if total_tokens else 0.0

    return {
        "n_tasks": len(arch_results),
        "latency_p50_ms": int(statistics.median(latencies)) if latencies else 0,
        "latency_p95_ms": int(sorted(latencies)[int(len(latencies) * 0.95)]) if latencies else 0,
        "cost_per_task_usd": round(statistics.mean(costs), 5) if costs else 0.0,
        "cost_total_usd": round(sum(costs), 5),
        "tokens_in_per_task": int(statistics.mean(tokens_in)) if tokens_in else 0,
        "tokens_out_per_task": int(statistics.mean(tokens_out)) if tokens_out else 0,
        "inter_agent_overhead_pct": inter_pct,
        "cost_by_agent_total": cost_by_agent,
        "success_rate": metric("success"),
        "tool_selection_accuracy": metric("tool_selection_accuracy"),
        "groundedness": metric("groundedness"),
        "judge_score": metric("judge_llm"),
        "route_correct": metric("route_correct"),
    }


def _process(arch: str, task: dict[str, Any]) -> dict[str, Any]:
    print(f"  [{arch:8s}] {task['id']}", flush=True)
    result = _run_task(arch, task)
    evals = run_all_evaluators(task, result)
    return {
        "task_id": task["id"],
        "category": task["category"],
        "query": task["query"],
        "architecture": arch,
        "result": result,
        "evals": [asdict(e) for e in evals],
    }


def run(limit: int | None = None, workers: int = 4) -> dict[str, Any]:
    tasks = json.loads(GOLDEN.read_text(encoding="utf-8"))["tasks"]
    if limit:
        tasks = tasks[:limit]
    RESULTS_DIR.mkdir(exist_ok=True)

    plan = [(arch, t) for arch in ("baseline", "crew") for t in tasks]
    out: list[dict[str, Any]] = []
    print(f"Running {len(plan)} task-runs ({len(tasks)} tasks × 2 architectures) with {workers} workers...")
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_process, arch, t) for arch, t in plan]
        for fut in as_completed(futures):
            out.append(fut.result())
    print(f"Done in {int(time.time() - t0)}s")

    by_arch: dict[str, list[dict[str, Any]]] = {"baseline": [], "crew": []}
    for r in out:
        by_arch[r["architecture"]].append(r)

    summary = {
        "model_baseline": settings.model_baseline,
        "model_router": settings.model_fast,
        "model_analyst_advisor": settings.model_smart,
        "model_safety": settings.model_fast,
        "baseline": aggregate(by_arch["baseline"]),
        "crew": aggregate(by_arch["crew"]),
        "task_count": len(tasks),
    }

    ts = time.strftime("%Y%m%d_%H%M%S")
    detailed_path = RESULTS_DIR / f"runs_{ts}.json"
    summary_path = RESULTS_DIR / f"summary_{ts}.json"
    md_path = RESULTS_DIR / f"summary_{ts}.md"
    latest_summary = RESULTS_DIR / "summary_latest.json"
    latest_md = RESULTS_DIR / "summary_latest.md"
    latest_runs = RESULTS_DIR / "runs_latest.json"

    detailed_path.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    latest_summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    latest_runs.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    md_path.write_text(_format_markdown(summary, out))
    latest_md.write_text(_format_markdown(summary, out))

    print(f"\n→ summary: {summary_path}")
    print(f"→ runs:    {detailed_path}")
    print(f"→ md:      {md_path}")
    return summary


def _format_markdown(summary: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    b = summary["baseline"]
    c = summary["crew"]
    out: list[str] = []
    out.append(f"# Experiment summary ({summary['task_count']} tasks)\n")
    out.append(f"- Baseline model: `{summary['model_baseline']}`")
    out.append(f"- Crew models: router/safety=`{summary['model_router']}`, analyst/advisor=`{summary['model_analyst_advisor']}`\n")

    rows = [
        ("Metric", "Baseline", "Crew", "Δ"),
        ("---", "---", "---", "---"),
        ("success_rate", f"{b['success_rate']:.2f}", f"{c['success_rate']:.2f}", f"{c['success_rate']-b['success_rate']:+.2f}"),
        ("tool_selection_accuracy", f"{b['tool_selection_accuracy']:.2f}", f"{c['tool_selection_accuracy']:.2f}", f"{c['tool_selection_accuracy']-b['tool_selection_accuracy']:+.2f}"),
        ("groundedness", f"{b['groundedness']:.2f}", f"{c['groundedness']:.2f}", f"{c['groundedness']-b['groundedness']:+.2f}"),
        ("judge_score", f"{b['judge_score']:.2f}", f"{c['judge_score']:.2f}", f"{c['judge_score']-b['judge_score']:+.2f}"),
        ("route_correct (crew)", "n/a", f"{c['route_correct']:.2f}", "—"),
        ("latency_p50_ms", str(b["latency_p50_ms"]), str(c["latency_p50_ms"]), str(c["latency_p50_ms"] - b["latency_p50_ms"])),
        ("latency_p95_ms", str(b["latency_p95_ms"]), str(c["latency_p95_ms"]), str(c["latency_p95_ms"] - b["latency_p95_ms"])),
        ("cost_per_task_usd", f"${b['cost_per_task_usd']:.4f}", f"${c['cost_per_task_usd']:.4f}", f"${c['cost_per_task_usd']-b['cost_per_task_usd']:+.4f}"),
        ("tokens_in_per_task", str(b["tokens_in_per_task"]), str(c["tokens_in_per_task"]), str(c["tokens_in_per_task"] - b["tokens_in_per_task"])),
        ("tokens_out_per_task", str(b["tokens_out_per_task"]), str(c["tokens_out_per_task"]), str(c["tokens_out_per_task"] - b["tokens_out_per_task"])),
        ("inter_agent_overhead_pct", "0.00%", f"{c['inter_agent_overhead_pct']:.2f}%", "—"),
    ]
    out.append("\n## Aggregate metrics\n")
    out.append("| " + " | ".join(rows[0]) + " |")
    out.append("| " + " | ".join(rows[1]) + " |")
    for row in rows[2:]:
        out.append("| " + " | ".join(row) + " |")

    out.append("\n## Cost breakdown by agent (crew)\n")
    out.append("| Agent | Cost $ |")
    out.append("| --- | --- |")
    for k, v in sorted(c["cost_by_agent_total"].items(), key=lambda kv: -kv[1]):
        out.append(f"| {k} | ${v:.5f} |")

    out.append("\n## Per-task results\n")
    out.append("| Task | Arch | Route✓ | Tool✓ | Ground | Judge | Success | Lat ms | Cost |")
    out.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    runs_sorted = sorted(runs, key=lambda r: (r["task_id"], r["architecture"]))
    for r in runs_sorted:
        scores = {e["name"]: e["score"] for e in r["evals"]}
        out.append(
            f"| {r['task_id']} | {r['architecture']} | "
            f"{scores.get('route_correct', 1.0):.0f} | "
            f"{scores.get('tool_selection_accuracy', 0.0):.0f} | "
            f"{scores.get('groundedness', 0.0):.2f} | "
            f"{scores.get('judge_llm', 0.0):.2f} | "
            f"{scores.get('success', 0.0):.0f} | "
            f"{r['result']['latency_ms']} | "
            f"${r['result']['cost_usd']:.4f} |"
        )
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Run only first N tasks.")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    run(limit=args.limit, workers=args.workers)


if __name__ == "__main__":
    main()
