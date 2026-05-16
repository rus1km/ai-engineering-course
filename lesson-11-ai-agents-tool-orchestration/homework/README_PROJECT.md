# Personal Finance Coach — Multi-Agent vs Baseline

Домашнє завдання заняття 11. Реалізує AI-помічник для банківського застосунку у двох архітектурах і порівнює їх на golden set.

## Що тут є

- **Baseline** ([app/baseline/agent.py](app/baseline/agent.py)) — один LLM (Claude Sonnet) з усіма tools і ручним `tool_use` циклом.
- **Crew** ([app/crew/graph.py](app/crew/graph.py)) — LangGraph supervisor з 4 ролями:
  - **Router** (Haiku) — класифікує запит у `stats` / `advice` / `analysis` / `safety` / `out_of_scope`.
  - **Analyst** (Sonnet) — точні факти про витрати (`stats`, `analysis`).
  - **Advisor** (Sonnet) — actionable-поради з числами (`advice`).
  - **Safety** (Haiku) — escalation до підтримки (`safety`, `out_of_scope`).
- **Tools** ([app/tools/transactions.py](app/tools/transactions.py)) — 10 функцій: `query_transactions`, `aggregate_spending`, `top_categories`, `find_recurring`, `detect_late_night_pattern`, `compare_periods`, `project_month_close`, `credit_card_status`, `get_last_payment`, `escalate_to_support`.
- **API** ([app/api/main.py](app/api/main.py)) — FastAPI з `POST /chat` (вибір архітектури в body).
- **UI** ([ui/streamlit_app.py](ui/streamlit_app.py)) — Streamlit chat + eval-таб.
- **Golden set** ([data/golden_set.json](data/golden_set.json)) — 18 задач по 5 категоріях.
- **Eval** ([eval/run_experiments.py](eval/run_experiments.py)) — 4 evaluators + side-by-side метрики; опціональний push у LangSmith ([eval/langsmith_push.py](eval/langsmith_push.py)).
- **Report** ([REPORT.md](REPORT.md)) — числові показники й висновок про multi-agent.

## Стек

Python 3.11+ · FastAPI · Pydantic · LangGraph · OpenRouter (Anthropic Haiku 4.5 / Sonnet 4.6) · Streamlit · pandas · LangSmith (опціонально).

## Запуск

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # вкажіть OPENROUTER_API_KEY

# 1. API
.venv/bin/python -m uvicorn app.api.main:app --reload --port 8000

# 2. UI (в іншому терміналі)
.venv/bin/streamlit run ui/streamlit_app.py

# 3. Прогнати golden set
.venv/bin/python -m eval.run_experiments

# 4. (опційно) Опублікувати в LangSmith Experiments
.venv/bin/python -m eval.langsmith_push
```

## Архітектура

```
                ┌────────────┐
   user query → │   Router   │ (Haiku, ~120 tok, classify only)
                └─────┬──────┘
                      │ route
        ┌─────────────┼──────────────┐
        ▼             ▼              ▼
   ┌─────────┐  ┌───────────┐  ┌──────────┐
   │ Analyst │  │  Advisor  │  │  Safety  │
   │ (Sonnet)│  │  (Sonnet) │  │ (Haiku)  │
   └─────────┘  └───────────┘  └──────────┘
        │             │              │
        └──────tools──┴──────tools───┘
              (transactions.py)
```

Дата "сьогодні" фіксована = 2025-11-30 (остання дата у датасеті), щоб "минулого тижня" не повертало порожній результат.

## Дослідження результатів

Див. [REPORT.md](REPORT.md) — таблиці метрик і висновок.

Свіжий прогін зберігається у `results/summary_latest.{json,md}` та `results/runs_latest.json`.
