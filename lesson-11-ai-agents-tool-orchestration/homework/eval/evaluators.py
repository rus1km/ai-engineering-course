"""Кастомні evaluators: groundedness, tool_selection_accuracy, route_correct, judge."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from app.common.llm import get_llm
from app.config import settings


@dataclass
class EvalScore:
    name: str
    score: float  # 0..1
    reason: str = ""


def route_correct(task: dict[str, Any], result: dict[str, Any]) -> EvalScore:
    """Чи маршрутизовано до правильного агента (тільки для crew)."""
    expected = task.get("expected_route")
    actual_route = None
    if result.get("architecture") == "crew":
        for s in result.get("trace", []):
            if s.get("kind") == "agent_handoff" and s.get("agent") == "router":
                # name format: "-> <route>"
                m = re.match(r"^->\s*(\w+)", s.get("name", "") or "")
                if m:
                    actual_route = m.group(1)
                    break
    if actual_route is None:
        # Baseline doesn't have explicit routing; we infer from tools_used
        return EvalScore(name="route_correct", score=1.0, reason="N/A for baseline")
    ok = actual_route == expected
    return EvalScore(name="route_correct", score=1.0 if ok else 0.0,
                     reason=f"expected={expected}, actual={actual_route}")


def tool_selection_accuracy(task: dict[str, Any], result: dict[str, Any]) -> EvalScore:
    """Чи серед використаних tools є хоча б один з expected_tools_any_of."""
    expected = set(task.get("expected_tools_any_of", []))
    used = set(result.get("tools_used", []))
    if not expected:
        return EvalScore(name="tool_selection_accuracy", score=1.0, reason="No expected tools")
    ok = bool(expected & used)
    return EvalScore(name="tool_selection_accuracy", score=1.0 if ok else 0.0,
                     reason=f"expected_any_of={sorted(expected)}, used={sorted(used)}")


def groundedness(task: dict[str, Any], result: dict[str, Any]) -> EvalScore:
    """Чи містить відповідь очікувані числа/підстроки."""
    answer = (result.get("answer") or "").lower()
    must_numbers = task.get("must_contain_numbers", [])
    must_subs = task.get("must_contain_substrings_any_of", [])
    must_not = task.get("must_not_contain", [])

    checks = []
    for n in must_numbers:
        checks.append((f"number:{n}", str(n).lower() in answer))
    if must_subs:
        checks.append((
            f"subs_any:{must_subs}",
            any(s.lower() in answer for s in must_subs),
        ))
    for s in must_not:
        checks.append((f"!{s}", s.lower() not in answer))
    if not checks:
        return EvalScore(name="groundedness", score=1.0, reason="No groundedness rules")
    passed = sum(1 for _, ok in checks if ok)
    total = len(checks)
    score = passed / total
    failed = [name for name, ok in checks if not ok]
    return EvalScore(name="groundedness", score=score,
                     reason=f"{passed}/{total} checks passed" + (f"; failed: {failed}" if failed else ""))


JUDGE_SYSTEM = """\
You are a strict evaluator for a Personal Finance Coach AI. You will be given:
- the user's query (Ukrainian or mixed),
- the criteria the response must satisfy,
- the agent's response.

Return STRICTLY a JSON object: {"score": <0|0.5|1>, "reason": "<short reason in English>"}.
Score guide:
- 1.0: response fully satisfies the criteria.
- 0.5: response partially satisfies (e.g., mentions right numbers but is too generic / misses one criterion).
- 0.0: response fails (wrong number, generic advice without data, refuses when it shouldn't, hallucinated facts).

Be strict: generic phrases like "consider reducing dining out" without numbers MUST score ≤ 0.5.
Refusing a legitimate stats query scores 0.
"""


def judge_llm(task: dict[str, Any], result: dict[str, Any]) -> EvalScore:
    """LLM judge: оцінює відповідність judge_criteria."""
    criteria = task.get("judge_criteria")
    if not criteria:
        return EvalScore(name="judge_llm", score=1.0, reason="No judge criteria")
    payload = json.dumps({
        "query": task["query"],
        "criteria": criteria,
        "response": result.get("answer", ""),
    }, ensure_ascii=False)
    llm = get_llm()
    try:
        resp = llm.chat(
            model=settings.model_judge,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": payload},
            ],
            tools=None,
            max_tokens=200,
            temperature=0.0,
        )
        text = resp.text.strip()
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1].rstrip("`")
        parsed = json.loads(text)
        score = float(parsed.get("score", 0.0))
        reason = parsed.get("reason", "")
        return EvalScore(name="judge_llm", score=max(0.0, min(1.0, score)), reason=reason)
    except Exception as exc:  # noqa: BLE001
        return EvalScore(name="judge_llm", score=0.0, reason=f"judge_error: {exc}")


def success(task: dict[str, Any], evals: list[EvalScore]) -> EvalScore:
    """Бінарна метрика: groundedness >= 0.8 і judge >= 0.5 і tool_selection_accuracy == 1."""
    by_name = {e.name: e for e in evals}
    g = by_name.get("groundedness")
    j = by_name.get("judge_llm")
    t = by_name.get("tool_selection_accuracy")
    ok = bool(
        (g is None or g.score >= 0.8)
        and (j is None or j.score >= 0.5)
        and (t is None or t.score == 1.0)
    )
    return EvalScore(name="success", score=1.0 if ok else 0.0,
                     reason=f"g={g.score if g else 'n/a'}, j={j.score if j else 'n/a'}, t={t.score if t else 'n/a'}")


def run_all_evaluators(task: dict[str, Any], result: dict[str, Any]) -> list[EvalScore]:
    evals = [
        route_correct(task, result),
        tool_selection_accuracy(task, result),
        groundedness(task, result),
        judge_llm(task, result),
    ]
    evals.append(success(task, evals))
    return evals
