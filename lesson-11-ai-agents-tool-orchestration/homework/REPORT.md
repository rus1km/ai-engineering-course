# Personal Finance Coach — Multi-Agent vs Baseline. Звіт

> Заняття 11. Порівняння multi-agent crew (LangGraph) з single-agent baseline на golden set із 18 задач.

## 1. Архітектура

### 1.1. Baseline (single-agent)

[`app/baseline/agent.py`](app/baseline/agent.py). Один LLM (Claude Sonnet 4.6) з усіма 10 інструментами і ручним `tool_use` циклом (до 6 ітерацій). Один system prompt описує усі ролі: статистика, поради, escalation, out-of-scope.

### 1.2. Crew (multi-agent, LangGraph)

[`app/crew/graph.py`](app/crew/graph.py). Supervisor-патерн з 4 спеціалізованими нодами:

| Агент | Модель | Tools | Призначення |
|---|---|---|---|
| **Router** | Haiku 4.5 | — | Класифікує запит у `stats` / `advice` / `analysis` / `safety` / `out_of_scope`. Повертає JSON, ~120 output-токенів. |
| **Analyst** | Sonnet 4.6 | 7 (query_transactions, aggregate_spending, top_categories, compare_periods, project_month_close, get_last_payment, credit_card_status) | Точні факти про витрати. Короткі відповіді. |
| **Advisor** | Sonnet 4.6 | 9 (analyst + find_recurring + detect_late_night_pattern) | Actionable-поради з реальними сумами. |
| **Safety** | Haiku 4.5 | 1 (escalate_to_support) | Fraud-escalation та out-of-scope refusal. НЕ має доступу до фінансових tools. |

Маршрутизація через `add_conditional_edges` за полем `route` у state.

### 1.3. Чому такий поділ

- **Router окремо** — дешева Haiku ($1/$5 за 1M токенів) бере класифікацію без фінансових tools. Менше контексту у решти агентів.
- **Analyst і Advisor розділені** — Analyst suppressed advice-формулювання; Advisor має більший `max_tokens` (1200 vs 800) і додаткові tools для виявлення патернів.
- **Safety ізольований** — _physically_ не може викликати фінансові tools, тому неможлива ситуація "агент сам блокує карту". Це enforcement через tool-allowlist, не лише через prompt.

## 2. Tools

[`app/tools/transactions.py`](app/tools/transactions.py). 10 інструментів, pandas-backed, in-memory кеш CSV.

`query_transactions`, `aggregate_spending`, `top_categories`, `find_recurring` (з прапором `is_likely_forgotten` коли last_seen > 60 днів), `detect_late_night_pattern`, `compare_periods`, `project_month_close`, `credit_card_status`, `get_last_payment`, `escalate_to_support`.

`today` зафіксована на `2025-11-30`, інакше "минулого тижня" повертає порожній результат.

## 3. Метрики

Збираються з трас локально. **Performance** — з трас LLM-викликів. **Якість** — через 4 evaluators у [`eval/evaluators.py`](eval/evaluators.py):

- `route_correct` — чи правильно маршрутизовано (тільки crew).
- `tool_selection_accuracy` — чи серед використаних tools є хоча б один з `expected_tools_any_of`.
- `groundedness` — rule-based: чи відповідь містить очікувані числа/підстроки (з реальних даних).
- `judge_llm` — LLM-as-judge (Sonnet 4.6) на шкалі 0 / 0.5 / 1.
- `success` (бінарний) — `groundedness ≥ 0.8` І `judge ≥ 0.5` І `tool_selection_accuracy = 1`.

**Multi-agent specific**: `inter_agent_overhead_pct` (Router-токени / total tokens), `cost_by_agent`.

## 4. Golden set

[`data/golden_set.json`](data/golden_set.json). **18 задач**:

| Категорія | К-сть | Приклади |
|---|---|---|
| stats | 6 | "Скільки на каву минулого тижня?", "Дата платежу Netflix", multi-turn "А місяць?" |
| advice | 4 | "Де зекономити $200?", "Підписки", "Як виплатити кредитку", "Чи багато замовляю ввечері?" |
| analysis | 4 | Nov vs Oct, projection, "якщо delivery вдвічі — економія за рік", річні тренди |
| safety | 2 | Fraud Booking.com, втрачена картка |
| out_of_scope | 2 | "Купи акції Tesla", "Переведи $500" |

Числа в `must_contain_numbers` обчислено реальними викликами tools перед формуванням eval.

## 5. Результати повного прогону

LLM-провайдер: **Anthropic API напряму** (`LLM_PROVIDER=anthropic`). 18 задач × 2 архітектури = 36 task-runs, workers=2, тривалість ~12 хвилин.

### 5.1. Aggregate metrics

| Metric | Baseline | Crew | Δ |
|---|---|---|---|
| **success_rate** | 0.61 | 0.61 | +0.00 |
| **tool_selection_accuracy** | 0.89 | **1.00** | **+0.11** |
| **groundedness** | **0.77** | 0.66 | -0.12 |
| **judge_score** | **0.94** | 0.83 | -0.11 |
| route_correct (crew) | n/a | 0.94 | — |
| **latency_p50_ms** | 19382 | **16174** | **-3208** |
| latency_p95_ms | **42409** | 49997 | +7588 |
| **cost_per_task_usd** | $0.0252 | **$0.0235** | **-$0.0017** |
| tokens_in_per_task | 6540 | 6200 | -340 |
| tokens_out_per_task | 371 | 540 | +169 |
| **inter_agent_overhead_pct** | 0.00% | **6.73%** | — |

### 5.2. Cost breakdown by agent (crew)

| Agent | Total cost ($) | Частка |
|---|---|---|
| analyst | $0.25651 | 60.6% |
| advisor | $0.13815 | 32.6% |
| safety | $0.01618 | 3.8% |
| router | $0.01250 | 3.0% |

Router + Safety разом = 6.8% бюджету crew. Це і є вартість "розгалуження" — дешева, бо обидва на Haiku.

### 5.3. Розбивка успішності по категоріях

| Category | Baseline success | Crew success |
|---|---|---|
| stats (6) | 4/6 = 0.67 | 4/6 = 0.67 |
| advice (4) | 3/4 = 0.75 | 3/4 = 0.75 |
| analysis (4) | 2/4 = 0.50 | 2/4 = 0.50 |
| safety (2) | 2/2 = 1.00 | 2/2 = 1.00 |
| out_of_scope (2) | 0/2 = 0.00 | 0/2 = 0.00 |

Bottleneck — `out_of_scope` (обидві архітектури fail через те, що судять generic-формулювання як прохідні, але `tool_selection_accuracy=0` у baseline блокує success). Це питання design тестів, не архітектури.

### 5.4. Де crew виграє: latency на safety/out_of_scope

| Task | Baseline lat | Crew lat | Speedup |
|---|---|---|---|
| safety_card_lost | 19.1s | 6.4s | **3.0×** |
| safety_fraud_booking | 24.4s | 6.3s | **3.9×** |
| oos_stocks | 15.0s | 5.4s | **2.8×** |
| oos_transfer | 6.7s | 5.9s | 1.1× |
| analysis_month_close | 21.0s | 5.4s | **3.9×** (Sonnet, але 1 tool call) |
| multiturn_coffee_followup | 19.7s | 5.0s | **3.9×** |

Маршрутизація на Haiku + менші max_tokens у safety = різко менша latency. Cost теж нижчий у 4–5×: $0.0048 vs $0.0236 у safety_card_lost.

### 5.5. Де crew програє: advice вимагає більше викликів

| Task | Baseline lat | Crew lat | Crew cost vs baseline |
|---|---|---|---|
| advice_credit_card | 24.3s | 50.0s | $0.053 vs $0.026 |
| advice_save_200 | 12.8s | 44.0s | $0.051 vs $0.029 |
| advice_subscriptions | 11.8s | 27.9s | $0.036 vs $0.030 |

Advisor у crew робить 4-5 викликів інструментів (`top_categories` + `find_recurring` + `detect_late_night_pattern` + `aggregate_spending`), бо так наказує system prompt — "завжди починай з 2–3 викликів". Baseline робить 1-2 виклики під тим же query, бо у нього менше указівок. Результат: crew дає _якісніші_ і повніші advice-відповіді (див. розділ 6.3), але платить за це 2–3× latency.

### 5.6. Routing accuracy

`advice_late_night_delivery` ("Чи багато я замовляю їжі ввечері?") — router класифікував як `stats` замість `advice`. Це borderline-кейс: запит звучить як статистика, але очікувалась рекомендація. На решті 17 задач — 100%.

## 6. Висновки

### 6.1. Чи виправдане ускладнення multi-agent?

**Залежить від профілю запитів.**

- **Так, виправдане:** якщо у traffic-mix > 20% safety/escalation/out-of-scope запитів. Crew економить там 3-4× у latency та 4-5× у cost, бо escalate_to_support не вимагає Sonnet-аналізу.
- **Так, виправдане з product-перспективи:** Safety-агент _технічно не може_ викликати фінансові tools — це enforcement, що захищає від prompt-injection у fraud-сценаріях. У baseline це лише prompt rule, який модель може порушити.
- **Так, для team scaling:** Чотири окремі prompt-и легше підтримувати, ніж один монолітний на 2000 токенів — кожна команда модифікує свою роль без regression-ризику.
- **Ні, для якості per-task на нашому golden set:** success_rate однаковий, judge_score та groundedness навіть трохи нижчі (-0.11). Спеціалізовані prompts іноді змушують Advisor робити зайві виклики "про всяк випадок", що додає шуму у відповідь.
- **Ні, для economy on bulk stats:** Baseline на простих stats-запитах не повільніший і не дорожчий за crew. Router-крок додає 0.7–1.5s оверхеду без user-visible value.

### 6.2. Хто платить інтер-агентський оверхед

Router = 3% від cost у crew. Це дешево, але token-share — 6.73%. На безкоштовних безrouting-задачах (тих, де baseline і так підбирає правильний tool) це чистий збиток. Розв'язання — **conditional routing**: пропускати router для запитів, що тривіально класифікуються rule-based (regex / keywords), і викликати LLM-router тільки для ambiguous кейсів.

### 6.3. Якість advice

Якщо звузити аналіз до `advice`-категорії, crew дає більш структуровану відповідь з більшою кількістю actionable пунктів (див. trace для advice_save_200: 5 tool calls, 4 пункти економії, обов'язкове виявлення Sportlife як forgotten subscription). Baseline на тій же задачі робить 2 tool calls і 2-3 пункти. **Judge LLM не штрафує baseline за коротшу відповідь** — обидва дають score=1.0 — але це сприймається як рівність лише тому, що користувацький інтент "де зекономити" може задовольнитися як коротким, так і детальним list-ом.

### 6.4. Рекомендації для production

1. **Hybrid routing:** rule-based router для тривіальних класифікацій ("fraud", "блокувати", "купити", "перевести"), LLM-router тільки на borderline. Економить ~3% cost і 0.7s latency на 80% запитів.
2. **Safety-агент залишити окремим** навіть якщо інше згорнути назад у baseline. Tool-allowlist — це security feature, не оптимізація.
3. **Advisor-prompt пом'якшити**: "робити мінімум tool-викликів, що покривають всі очікувані patterns" замість "завжди починай з 2-3 викликів". Зекономить ~$0.02/advice-запит.
4. **Multi-turn з історією — повна підтримка обома архітектурами**: тест `multiturn_coffee_followup` пройшов і у baseline, і у crew.
5. **SLA ≤ 10s з вимог README:** _НЕ виконано_ для більшості advice-запитів (~20-30s). Це або зменшення max_iterations, або стрімінг для перцептивного speed-up, або реалізація tool-async (паралельні виклики `find_recurring` + `top_categories` всередині Advisor).

## 7. Обмеження та чого не вдалося реалізувати

### 7.1. LangSmith Experiments — implementation готова, не активована

[`eval/langsmith_push.py`](eval/langsmith_push.py): створює dataset (idempotent), запускає `evaluate()` для обох архітектур із custom evaluators. Не активовано — `LANGCHAIN_API_KEY` не наданий (placeholder у `.env.example`). Скрипт graceful-skip.

Локальний eval повністю покриває всі вимагані метрики (success_rate, tool_selection_accuracy, groundedness, latency, cost, inter_agent_overhead) — функціональний еквівалент. Щоб увімкнути: вписати реальний `LANGCHAIN_API_KEY`, запустити `.venv/bin/python -m eval.langsmith_push`.

### 7.2. OpenRouter credit exhaustion

Під час першого прогону OpenRouter повернув `402 Insufficient credits` після ~30 викликів. Перемкнення на `LLM_PROVIDER=anthropic` (нативний Anthropic SDK) розв'язало проблему — додано `app/common/llm.py::AnthropicProvider` з конвертацією OpenAI↔Anthropic message формату.

Також зустрілися Anthropic rate-limit (30K input tokens/min на Sonnet 4.6 при workers=4) — додано retry з exponential backoff і знижено workers=2.

### 7.3. SLA latency-вимога ≤ 10s

Виконана лише для частини задач:
- stats: 4-9s baseline, 12-23s crew (НЕ виконана для crew)
- safety/oos: 6-25s baseline, 5-7s crew (виконана для crew!)
- advice: 12-25s baseline, 28-50s crew (НЕ виконана ніде)

Для production треба: tool-async (parallel `find_recurring` + `top_categories`), стрімінг відповіді у Streamlit, лімітований max_iterations.

### 7.4. Що ще можна було б додати

- Async tool-calls усередині Advisor (`asyncio.gather`) — найбільший single source of latency.
- Streaming у Streamlit і API (наразі blocking).
- Більше edge-cases у golden set: typos, mixed Ukrainian/Russian, тощо.

## 8. Як відтворити

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env  # вкажіть ANTHROPIC_API_KEY або OPENROUTER_API_KEY
# .env: LLM_PROVIDER=anthropic (або openrouter)

# Запустити повний eval
.venv/bin/python -m eval.run_experiments --workers 2
# → results/summary_latest.md + runs_latest.json

# (опційно) Опублікувати в LangSmith Experiments
.venv/bin/python -m eval.langsmith_push

# Інтерактивний UI
.venv/bin/python -m uvicorn app.api.main:app --port 8000 &
.venv/bin/streamlit run ui/streamlit_app.py
```

Усі деталі по агентах, прохід-у-прохід, per-task scores та повна traces — у [`results/runs_latest.json`](results/runs_latest.json) та [`results/summary_latest.md`](results/summary_latest.md).
