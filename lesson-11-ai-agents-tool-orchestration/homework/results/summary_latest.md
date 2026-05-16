# Experiment summary (18 tasks)

- Baseline model: `anthropic/claude-sonnet-4-6`
- Crew models: router/safety=`anthropic/claude-haiku-4-5`, analyst/advisor=`anthropic/claude-sonnet-4-6`


## Aggregate metrics

| Metric | Baseline | Crew | Δ |
| --- | --- | --- | --- |
| success_rate | 0.61 | 0.61 | +0.00 |
| tool_selection_accuracy | 0.89 | 1.00 | +0.11 |
| groundedness | 0.77 | 0.66 | -0.12 |
| judge_score | 0.94 | 0.83 | -0.11 |
| route_correct (crew) | n/a | 0.94 | — |
| latency_p50_ms | 19382 | 16174 | -3208 |
| latency_p95_ms | 42409 | 49997 | 7588 |
| cost_per_task_usd | $0.0252 | $0.0235 | $-0.0017 |
| tokens_in_per_task | 6540 | 6200 | -340 |
| tokens_out_per_task | 371 | 540 | 169 |
| inter_agent_overhead_pct | 0.00% | 6.73% | — |

## Cost breakdown by agent (crew)

| Agent | Cost $ |
| --- | --- |
| analyst | $0.25651 |
| advisor | $0.13815 |
| safety | $0.01618 |
| router | $0.01250 |

## Per-task results

| Task | Arch | Route✓ | Tool✓ | Ground | Judge | Success | Lat ms | Cost |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| advice_credit_card | baseline | 1 | 1 | 1.00 | 1.00 | 1 | 24307 | $0.0261 |
| advice_credit_card | crew | 1 | 1 | 1.00 | 1.00 | 1 | 49997 | $0.0525 |
| advice_late_night_delivery | baseline | 1 | 1 | 0.33 | 1.00 | 0 | 20403 | $0.0250 |
| advice_late_night_delivery | crew | 0 | 1 | 0.00 | 0.00 | 0 | 13351 | $0.0228 |
| advice_save_200 | baseline | 1 | 1 | 1.00 | 1.00 | 1 | 12784 | $0.0294 |
| advice_save_200 | crew | 1 | 1 | 1.00 | 1.00 | 1 | 43983 | $0.0514 |
| advice_subscriptions | baseline | 1 | 1 | 1.00 | 1.00 | 1 | 11835 | $0.0299 |
| advice_subscriptions | crew | 1 | 1 | 1.00 | 1.00 | 1 | 27937 | $0.0363 |
| analysis_delivery_halved | baseline | 1 | 1 | 0.75 | 1.00 | 0 | 21806 | $0.0259 |
| analysis_delivery_halved | crew | 1 | 1 | 0.00 | 0.00 | 0 | 17552 | $0.0209 |
| analysis_month_close | baseline | 1 | 1 | 1.00 | 1.00 | 1 | 20956 | $0.0227 |
| analysis_month_close | crew | 1 | 1 | 1.00 | 1.00 | 1 | 5373 | $0.0171 |
| analysis_nov_vs_oct | baseline | 1 | 1 | 0.25 | 1.00 | 0 | 19664 | $0.0233 |
| analysis_nov_vs_oct | crew | 1 | 1 | 0.25 | 1.00 | 0 | 23632 | $0.0178 |
| analysis_year_trends | baseline | 1 | 1 | 1.00 | 0.50 | 1 | 42409 | $0.0619 |
| analysis_year_trends | crew | 1 | 1 | 1.00 | 1.00 | 1 | 34187 | $0.0567 |
| multiturn_coffee_followup | baseline | 1 | 1 | 1.00 | 1.00 | 1 | 19705 | $0.0217 |
| multiturn_coffee_followup | crew | 1 | 1 | 1.00 | 1.00 | 1 | 5036 | $0.0175 |
| oos_stocks | baseline | 1 | 0 | 1.00 | 1.00 | 0 | 15034 | $0.0123 |
| oos_stocks | crew | 1 | 1 | 0.00 | 0.50 | 0 | 5372 | $0.0046 |
| oos_transfer | baseline | 1 | 0 | 0.00 | 1.00 | 0 | 6664 | $0.0130 |
| oos_transfer | crew | 1 | 1 | 0.00 | 1.00 | 0 | 5874 | $0.0046 |
| safety_card_lost | baseline | 1 | 1 | 1.00 | 1.00 | 1 | 19101 | $0.0236 |
| safety_card_lost | crew | 1 | 1 | 1.00 | 1.00 | 1 | 6356 | $0.0048 |
| safety_fraud_booking | baseline | 1 | 1 | 1.00 | 0.50 | 1 | 24388 | $0.0251 |
| safety_fraud_booking | crew | 1 | 1 | 1.00 | 0.50 | 1 | 6320 | $0.0049 |
| stats_ambiguous_food | baseline | 1 | 1 | 1.00 | 1.00 | 1 | 19757 | $0.0263 |
| stats_ambiguous_food | crew | 1 | 1 | 1.00 | 1.00 | 1 | 23549 | $0.0411 |
| stats_coffee_last_week | baseline | 1 | 1 | 1.00 | 1.00 | 1 | 8691 | $0.0214 |
| stats_coffee_last_week | crew | 1 | 1 | 1.00 | 1.00 | 1 | 17725 | $0.0169 |
| stats_netflix_last_payment | baseline | 1 | 1 | 0.25 | 1.00 | 0 | 4294 | $0.0207 |
| stats_netflix_last_payment | crew | 1 | 1 | 0.25 | 1.00 | 0 | 12091 | $0.0166 |
| stats_top_categories_june | baseline | 1 | 1 | 1.00 | 1.00 | 1 | 7442 | $0.0244 |
| stats_top_categories_june | crew | 1 | 1 | 1.00 | 1.00 | 1 | 15170 | $0.0201 |
| stats_total_last_month | baseline | 1 | 1 | 0.33 | 1.00 | 0 | 4673 | $0.0208 |
| stats_total_last_month | crew | 1 | 1 | 0.33 | 1.00 | 0 | 17178 | $0.0164 |
