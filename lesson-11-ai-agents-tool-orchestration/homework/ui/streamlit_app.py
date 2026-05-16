"""Streamlit dev UI для Personal Finance Coach.

Запуск:
    .venv/bin/streamlit run ui/streamlit_app.py

Очікує, що FastAPI працює на API_BASE_URL (за замовч. http://localhost:8000).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import requests  # noqa: E402
import streamlit as st  # noqa: E402

from app.config import settings  # noqa: E402

RESULTS_DIR = ROOT / "results"

st.set_page_config(page_title="Personal Finance Coach", page_icon="💸", layout="wide")

# ----------------------- sidebar -----------------------
st.sidebar.title("⚙️ Settings")
arch = st.sidebar.radio("Architecture", ["crew", "baseline"], index=0,
                         help="crew = multi-agent (LangGraph); baseline = single agent з tool_use loop")
api_base = st.sidebar.text_input("API base URL", value=settings.api_base_url)
st.sidebar.divider()
st.sidebar.caption(f"Models:\n- baseline: `{settings.model_baseline}`\n- analyst/advisor: `{settings.model_smart}`\n- router/safety: `{settings.model_fast}`")
st.sidebar.divider()
if st.sidebar.button("🩺 Health"):
    try:
        r = requests.get(f"{api_base}/health", timeout=5)
        st.sidebar.json(r.json())
    except Exception as exc:
        st.sidebar.error(str(exc))

if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_response" not in st.session_state:
    st.session_state.last_response = None

# ----------------------- tabs -----------------------
tab_chat, tab_eval = st.tabs(["💬 Chat", "📊 Eval"])

with tab_chat:
    st.title("💸 Personal Finance Coach")
    st.caption("Multi-agent finance assistant. Усі суми — USD. Сьогодні (фіксовано в датасеті): 2025-11-30.")

    if st.button("🗑️ Clear chat"):
        st.session_state.messages = []
        st.session_state.last_response = None
        st.rerun()

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_input = st.chat_input("Запитай: 'Скільки витратив на каву минулого тижня?'")
    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)
        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("_..._")
            t0 = time.time()
            try:
                resp = requests.post(
                    f"{api_base}/chat",
                    json={
                        "message": user_input,
                        "architecture": arch,
                        "history": st.session_state.messages,
                    },
                    timeout=120,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                placeholder.error(f"Request failed: {exc}")
                data = None

            wall = int((time.time() - t0) * 1000)
            if data:
                placeholder.markdown(data["answer"])
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Latency", f"{data['latency_ms']} ms")
                col2.metric("Cost", f"${data['cost_usd']:.4f}")
                col3.metric("Tokens", f"{data['tokens_in']} → {data['tokens_out']}")
                col4.metric("Inter-agent", f"{data['inter_agent_tokens']} tok")

                with st.expander("🪜 Trace (agents + tools)", expanded=False):
                    rows = []
                    for s in data["trace"]:
                        rows.append({
                            "kind": s["kind"],
                            "agent": s["agent"],
                            "name": s["name"],
                            "latency_ms": s["latency_ms"],
                            "tokens": f"{s['tokens_in']}/{s['tokens_out']}" if s["tokens_in"] else "",
                            "cost": f"${s['cost_usd']:.5f}" if s["cost_usd"] else "",
                        })
                    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                    if data.get("cost_by_agent"):
                        st.write("**Cost by agent:**")
                        st.json(data["cost_by_agent"])

                st.session_state.messages.append({"role": "user", "content": user_input})
                st.session_state.messages.append({"role": "assistant", "content": data["answer"]})
                st.session_state.last_response = data

with tab_eval:
    st.title("📊 Golden set evaluation")
    st.caption("Запускає 18 задач на обох архітектурах і порівнює метрики.")

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("▶️ Run golden set (~10 хв)"):
            with st.spinner("Запускаю eval... це може зайняти кілька хвилин."):
                import subprocess
                proc = subprocess.run(
                    [sys.executable, "-m", "eval.run_experiments"],
                    cwd=str(ROOT), capture_output=True, text=True, timeout=900,
                )
                if proc.returncode != 0:
                    st.error(proc.stderr[-2000:])
                else:
                    st.success("Done")
                    st.text(proc.stdout[-500:])
    with col2:
        if st.button("🔄 Reload latest results"):
            st.rerun()

    summary_path = RESULTS_DIR / "summary_latest.json"
    runs_path = RESULTS_DIR / "runs_latest.json"
    if not summary_path.exists():
        st.info("Поки немає результатів. Натисни 'Run golden set' або запусти `.venv/bin/python -m eval.run_experiments` у терміналі.")
    else:
        summary = json.loads(summary_path.read_text())
        b = summary["baseline"]
        c = summary["crew"]
        st.subheader("Aggregate metrics (side-by-side)")
        df = pd.DataFrame([
            {"metric": "success_rate", "baseline": b["success_rate"], "crew": c["success_rate"],
             "delta": round(c["success_rate"] - b["success_rate"], 3)},
            {"metric": "tool_selection_accuracy", "baseline": b["tool_selection_accuracy"], "crew": c["tool_selection_accuracy"],
             "delta": round(c["tool_selection_accuracy"] - b["tool_selection_accuracy"], 3)},
            {"metric": "groundedness", "baseline": b["groundedness"], "crew": c["groundedness"],
             "delta": round(c["groundedness"] - b["groundedness"], 3)},
            {"metric": "judge_score", "baseline": b["judge_score"], "crew": c["judge_score"],
             "delta": round(c["judge_score"] - b["judge_score"], 3)},
            {"metric": "latency_p50_ms", "baseline": b["latency_p50_ms"], "crew": c["latency_p50_ms"],
             "delta": c["latency_p50_ms"] - b["latency_p50_ms"]},
            {"metric": "latency_p95_ms", "baseline": b["latency_p95_ms"], "crew": c["latency_p95_ms"],
             "delta": c["latency_p95_ms"] - b["latency_p95_ms"]},
            {"metric": "cost_per_task_usd", "baseline": b["cost_per_task_usd"], "crew": c["cost_per_task_usd"],
             "delta": round(c["cost_per_task_usd"] - b["cost_per_task_usd"], 5)},
            {"metric": "tokens_in_per_task", "baseline": b["tokens_in_per_task"], "crew": c["tokens_in_per_task"],
             "delta": c["tokens_in_per_task"] - b["tokens_in_per_task"]},
            {"metric": "tokens_out_per_task", "baseline": b["tokens_out_per_task"], "crew": c["tokens_out_per_task"],
             "delta": c["tokens_out_per_task"] - b["tokens_out_per_task"]},
            {"metric": "inter_agent_overhead_pct", "baseline": 0.0, "crew": c["inter_agent_overhead_pct"], "delta": None},
        ])
        st.dataframe(df, hide_index=True, use_container_width=True)

        st.subheader("Cost breakdown by agent (crew)")
        cb = c.get("cost_by_agent_total", {})
        if cb:
            st.dataframe(pd.DataFrame([{"agent": k, "cost_usd": round(v, 5)} for k, v in sorted(cb.items(), key=lambda kv: -kv[1])]),
                         hide_index=True, use_container_width=True)

        if runs_path.exists():
            st.subheader("Per-task scores")
            runs = json.loads(runs_path.read_text())
            rows = []
            for r in runs:
                scores = {e["name"]: e["score"] for e in r["evals"]}
                rows.append({
                    "task_id": r["task_id"],
                    "arch": r["architecture"],
                    "category": r["category"],
                    "success": scores.get("success", 0),
                    "tool✓": scores.get("tool_selection_accuracy", 0),
                    "ground": scores.get("groundedness", 0),
                    "judge": scores.get("judge_llm", 0),
                    "lat_ms": r["result"]["latency_ms"],
                    "cost": round(r["result"]["cost_usd"], 4),
                })
            df_runs = pd.DataFrame(rows).sort_values(["task_id", "arch"])
            st.dataframe(df_runs, hide_index=True, use_container_width=True)

            with st.expander("Debug: full traces"):
                pick = st.selectbox("Pick task", sorted({r["task_id"] for r in runs}))
                for r in runs:
                    if r["task_id"] == pick:
                        st.write(f"**{r['architecture']}** — {r['result']['answer']}")
                        st.dataframe(pd.DataFrame(r["result"]["trace"]), hide_index=True, use_container_width=True)
