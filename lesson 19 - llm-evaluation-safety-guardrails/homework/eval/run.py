"""Головний раннер eval pipeline.

  python -m eval.run                # offline (default), обидві конфігурації
  LLM_MODE=live MODEL=claude-sonnet-4-6 python -m eval.run   # проти реального Claude

Кроки: load golden -> прогнати baseline і guarded -> per-case evaluators ->
агрегувати метрики 4 класів -> verdict за порогами -> results/*.json + REPORT.md.
"""
from __future__ import annotations

import json

from app import config
from app.assistant import Assistant
from eval import report
from eval.evaluators import CaseResult, evaluate_case

GOLDEN_FILES = ["pii.jsonl", "injection.jsonl", "faithfulness.jsonl", "refusal.jsonl"]


def load_golden() -> list[dict]:
    cases: list[dict] = []
    for fname in GOLDEN_FILES:
        path = config.GOLDEN / fname
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _rate(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def aggregate(results: list[CaseResult]) -> dict:
    """Метрики 4 класів з атомарних прапорців."""
    def flag_universe(name: str) -> list[CaseResult]:
        return [r for r in results if name in r.flags]

    pii = [r for r in results if r.category in ("pii", "pii_control")]
    inj = [r for r in results if r.category in ("injection", "injection_control")]
    faith = [r for r in results if r.category in ("faithfulness", "faithfulness_oos")]
    benign = flag_universe("false_refusal")
    should = flag_universe("correct_refusal")

    return {
        "pii_leak_rate": _rate(sum(r.flags.get("leaked", False) for r in pii), len(pii)),
        "pii_n": len(pii),
        "injection_bypass_rate": _rate(sum(r.flags.get("bypassed", False) for r in inj), len(inj)),
        "injection_n": len(inj),
        "faithfulness_rate": _rate(sum(r.flags.get("faithful", False) for r in faith), len(faith)),
        "faithfulness_n": len(faith),
        "false_refusal_rate": _rate(sum(r.flags.get("false_refusal", False) for r in benign), len(benign)),
        "false_refusal_n": len(benign),
        "correct_refusal_rate": _rate(sum(r.flags.get("correct_refusal", False) for r in should), len(should)),
        "correct_refusal_n": len(should),
        "cases_total": len(results),
        "cases_passed": sum(r.passed for r in results),
    }


def verdict(metrics: dict) -> dict:
    t = config.THRESHOLDS
    gates = {
        "pii_leakage": {"value": metrics["pii_leak_rate"], "op": "<=", "threshold": t["pii_leak_rate_max"]},
        "prompt_injection": {"value": metrics["injection_bypass_rate"], "op": "<=", "threshold": t["injection_bypass_rate_max"]},
        "faithfulness": {"value": metrics["faithfulness_rate"], "op": ">=", "threshold": t["faithfulness_rate_min"]},
        "false_refusal": {"value": metrics["false_refusal_rate"], "op": "<=", "threshold": t["false_refusal_rate_max"]},
        "correct_refusal": {"value": metrics["correct_refusal_rate"], "op": ">=", "threshold": t["correct_refusal_rate_min"]},
    }
    for g in gates.values():
        g["pass"] = (g["value"] <= g["threshold"]) if g["op"] == "<=" else (g["value"] >= g["threshold"])
    ship = all(g["pass"] for g in gates.values())
    return {"ship": ship, "gates": gates}


def run() -> dict:
    cases = load_golden()
    assistant = Assistant()
    out: dict = {"mode": assistant.mode, "model": config.MODEL if assistant.mode == "live" else "fixtures", "configs": {}}

    for guarded in (False, True):
        cfg = "guarded" if guarded else "baseline"
        results: list[CaseResult] = []
        for case in cases:
            ans = assistant.answer(case, guarded=guarded)
            results.append(evaluate_case(case, ans.text, cfg))
        metrics = aggregate(results)
        out["configs"][cfg] = {
            "metrics": metrics,
            "verdict": verdict(metrics),
            "cases": [
                {"id": r.id, "category": r.category, "passed": r.passed, "detail": r.detail, "flags": r.flags}
                for r in results
            ],
        }

    config.RESULTS.mkdir(exist_ok=True)
    (config.RESULTS / "results_latest.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report_md = report.build(out)
    (config.ROOT / "REPORT.md").write_text(report_md, encoding="utf-8")
    return out


if __name__ == "__main__":
    data = run()
    b = data["configs"]["baseline"]["verdict"]["ship"]
    g = data["configs"]["guarded"]["verdict"]["ship"]
    print(f"mode={data['mode']}  baseline ship={b}  guarded ship={g}")
    print(f"Written: results/results_latest.json and REPORT.md")
