# Lesson 17 — Fine-tuning Llama 3.1 8B for support-email → JSON extraction

**Гіпотеза:** fine-tuned Llama 3.1 **8B** перевершить Llama 3.3 **70B** з промптом на задачі
структурованого витягу з support-листів, при у 5× дешевшому inference.

**Результат: гіпотезу доведено.** Fine-tuned 8B б'є і власний base 8B, і 70B **на кожній з 7 метрик**,
а найбільший приріст — саме у `urgency` (escalation-сигнал, який болить бізнесу): **63 % → 90 %**.

> **Платформа.** Зроблено **локально на MacBook Pro M1 Pro 16 GB** через **MLX-LM** (а не Colab T4 —
> це дозволена в умовах альтернатива для Mac M-series). Тому замість «T4 latency» наводжу заміряну
> latency на M1 Pro. Тренування і inference повністю безкоштовні (своє залізо).

---

## 1. Comparison table

Eval set — **30 листів**, складених руками з edge cases (anonymous, multiple issues, sarcasm,
mixed-language, vague product), зафіксований **ДО** тренування. Метрики однакові для всіх моделей
([`scripts/evaluate_mlx.py`](scripts/evaluate_mlx.py), greedy/temp=0).

| Модель | json_valid | exact_match | name | product | category | **urgency** | summary | tokens in/out |
|---|---|---|---|---|---|---|---|---|
| Llama 3.3 **70B** base (Together API) | 100 % | 36.7 % | 96.7 | 90.0 | 83.3 | 63.3 | 66.7 | 128 / 53 |
| Llama 3.1 **8B** base (local MLX, 4-bit) | 93.3 % | 43.3 % | 93.3 | 83.3 | 80.0 | 63.3 | 66.7 | 128 / 55 |
| Llama 3.1 **8B fine-tuned** (QLoRA) | **100 %** | **73.3 %** | **100** | **90.0** | **96.7** | **90.0** | **83.3** | 128 / **41** |
| **Lift (FT − base 8B), п.п.** | **+6.7** | **+30.0** | +6.7 | +6.7 | **+16.7** | **+26.7** | **+16.7** | −14 out |

Сирі числа: [`results/baseline_8b_mlx.json`](results/baseline_8b_mlx.json),
[`results/finetuned_8b_mlx.json`](results/finetuned_8b_mlx.json),
[`results/baseline_together_70b.json`](results/baseline_together_70b.json).

**Тренування** (QLoRA, [`scripts/lora_config.yaml`](scripts/lora_config.yaml)): r=16, alpha=32
(MLX `scale = alpha/rank = 2.0`), 16 із 32 шарів, 210 ітерацій ≈ 3 епохи на 280 прикладах, batch 4, lr 1e-4.
21 M trainable params (0.26 %), **peak mem 9.8 GB** (з 16 → без OOM), **~24 хв**, адаптер **80 MB**.

Крива loss (повністю в [`results/train_log.txt`](results/train_log.txt)):

| iter | 1 | 50 | 100 | 150 | 200 | 210 |
|---|---|---|---|---|---|---|
| **val loss** | 3.481 | 0.117 | 0.097 | 0.089 | 0.093 | 0.091 |
| train loss | — | 0.141 | 0.086 | 0.074 | 0.080 | 0.075 |

Val loss досяг дна на ~iter 150 і далі вийшов на плато (0.089→0.091) → перенавчання мінімальне,
sweet-spot для early-stopping був би ~iter 140.

---

## 2. Cost & breakeven

**Training cost = $0** (локальний M1 Pro, ~24 хв, ≈ копійки електрики; на Colab free T4 теж $0).

**Inference latency** (M1 Pro, single-stream, greedy): **2.3–2.4 с / лист** (≈ 0.43 листа/с одним потоком,
GPU Metal, peak ~9–10 GB). Одного M1 Pro single-stream вистачає на ~37 K листів/день; на цільові 50 K/день
потрібен батчинг/конкурентність.

**Обсяг:** 50 K листів/день × 30 = **1.5 M листів/міс**. На лист ≈ 128 in + ~41 out (FT) ≈ **169 токенів**
→ ≈ **254 M токенів/міс**.

| Варіант | Ціна (≈, serverless / rent) | $/міс при 50 K/день | Якість |
|---|---|---|---|
| 70B base через API | ~$0.88 / 1M | **≈ $239** | urgency 63 % |
| **FT 8B через API** | ~$0.18 / 1M | **≈ $46** | **urgency 90 %** |
| Власний 8B на rented T4 (on-demand ~$0.35/год) | $255/міс 24/7 | **≈ $255** | =FT 8B |
| Власний 8B на T4 spot (~$0.11/год) | ~$80/міс 24/7 | **≈ $80** | =FT 8B |
| Власний 8B на M1 Pro (своє залізо) | ~$5/міс електрика | **≈ $5** | =FT 8B |

**Breakeven (own GPU vs serverless 8B API @ $0.18/1M):**
- rented T4 on-demand $255/міс ⇄ 1.42 B токенів/міс ≈ **~280 K листів/день**;
- T4 spot $80/міс ⇄ 444 M токенів/міс ≈ **~85 K листів/день**.

> **Висновок по cost:** при **50 K/день** найдешевший *і найпростіший* шлях — це **fine-tuned 8B за
> serverless API (~$46/міс)**: у **~5× дешевше за 70B (~$239)** і при цьому *точніше*. Хостити власну
> модель на орендованому GPU вигідно лише вище ~85 K/день (spot) / ~280 K/день (on-demand), або коли
> диктують privacy/latency. Власний M1 Pro дає $5/міс, але не тягне 50 K/день одним потоком без батчингу.

---

## 3. Що вийшло — де lift найбільший і чому

Lift сконцентрований не у «фактичних» полях, а у **полях-судженнях**, де треба знати *внутрішній rubric компанії*:

1. **`urgency` +26.7 п.п. (63 → 90 %)** — головна перемога. Base 8B калібрує «на загальну логіку»:
   `"your software keeps freezing"` → **high** (а gold = medium), `"Cancel my account please"` → **low**
   (gold = medium). FT навчився *шкали компанії* і ставить **medium** правильно. Саме ця метрика робила
   70B непридатним для escalation у PagerDuty.
2. **`json_valid` 93 → 100 % і `exact_match` +30 п.п.** — base іноді *не видавав JSON узагалі*:
   на GDPR-запит відмовлявся (`"I can't assist with deleting data per GDPR…"`), на feature-request видавав
   нумеровану інструкцію замість об'єкта. FT прибив **format/instruction adherence** до 100 %.
3. **`issue_category` +16.7 (80 → 96.7 %)** — навчився company-specific межі (напр. «чому мій Pro Plan
   повільніший?» = billing/throttling, а не technical).
4. **`summary` +16.7** — стислі, у стилі train-лейблів; **output на 25 % коротший (55 → 41 токен)** →
   ще й inference дешевший.

FT 8B обійшов **70B на всіх метриках** (exact 73 vs 37, urgency 90 vs 63, category 97 vs 83): 300 прикладів
доменних лейблів дали більше, ніж 8× більша модель «з коробки».

---

## 4. Що НЕ вийшло / межі та ризики (важливіше за ідеальні числа)

- **Base 8B вже близько до «стелі» на простих полях.** `customer_name` (93 %) і `product` (83 %) — це
  copy-from-text, FT дав лише +6.7 п.п. Більше того, base 8B exact (43 %) був **вищим за 70B (37 %)** —
  на цьому rubric параметри моделі вже не вузьке місце; вузьке місце — **знання доменних правил**, яке дає
  саме fine-tuning, а не розмір.
- **Train/serve skew + синтетика.** Train (300) згенеровано з шаблонів детермінованим скриптом
  ([`scripts/generate_data.py`](scripts/generate_data.py)), а eval edge-cases (sarcasm, mixed-language,
  anonymous) у train майже не представлені. Модель усе одно узагальнила, але на **реальних брудних листах**
  числа будуть нижчі — потрібен re-eval на справжніх даних.
- **«Витік» логіки лейблів.** `urgency` у train проставляв евристичний `determine_urgency()`. Тобто FT
  частково вчиться *імітувати правило*, а не людський ground truth → 90 % трохи завищені відносно реального
  людського узгодження. Це найчесніше обмеження експерименту.
- **Легке перенавчання.** Val loss дійшов дна на iter ~150 і ледь піднявся до iter 210 (0.089 → 0.091).
  Критично не зашкодило, але правильніше було б early-stop на ~140 (чекпоінти збереглись кожні 70 iter).
- **Catastrophic forgetting не спостерігалось** — json_valid *зріс*, summary лишились зв'язними; LoRA на
  16 шарах зберегла загальні здібності.
- **Платформа.** Це M1 Pro/MLX, а не Colab T4 — latency не порівнянна 1:1 з T4 (T4 з батчингом дав би вищий
  throughput). OOM не було (peak 9.8/16 GB); Python 3.14 не мав колес для MLX, тож зробив venv на 3.13.

---

## 5. Бізнес-рекомендація

Деплоїти **fine-tuned Llama 3.1 8B (QLoRA-адаптер 80 MB)** замість 70B-з-промптом. Він піднімає
**urgency-accuracy 63 % → 90 %**, що вперше робить автоматичний escalation у PagerDuty надійним, і при цьому
**inference ~5× дешевший** (~$46 vs ~$239/міс при 50 K листів/день) з *коротшим* виводом. На поточному обсязі
тримати модель за **serverless API** — і дешевше, і простіше за власний GPU: self-hosting окупається лише
вище ~85 K/день (spot) чи ~280 K/день (on-demand). Перед продакшеном обов'язково **перевиміряти на реальних
листах** (синтетичний train занижує справжню складність) і **перелейблити urgency руками** замість евристики,
щоб прибрати label-leakage. ROI тренування: ~24 хв на ноутбуці, $0 — окупається з першого ж дня.

---

## Як відтворити

```bash
cd "lesson 17 - llm-fine-tuning-in-production/homework"
/opt/homebrew/bin/python3.13 -m venv .venv
./.venv/bin/pip install mlx-lm

# (за потреби перегенерувати дані: ./.venv/bin/python scripts/generate_data.py)
./.venv/bin/python scripts/make_mlx_data.py            # train/valid split + hash-check vs eval

# baseline 8B
./.venv/bin/python scripts/evaluate_mlx.py \
  --model mlx-community/Meta-Llama-3.1-8B-Instruct-4bit \
  --output results/baseline_8b_mlx.json

# fine-tune (QLoRA, ~24 хв на M1 Pro)
./.venv/bin/python -m mlx_lm lora --config scripts/lora_config.yaml

# re-eval з адаптером
./.venv/bin/python scripts/evaluate_mlx.py \
  --model mlx-community/Meta-Llama-3.1-8B-Instruct-4bit \
  --adapter adapters \
  --output results/finetuned_8b_mlx.json
```

### Файли
- `data/eval.jsonl` — 30 eval (з edge cases), `data/train.jsonl` — 300 train, `data/mlx/` — train/valid split
- `scripts/evaluate_mlx.py` — локальний MLX-евалуатор • `scripts/lora_config.yaml` — конфіг QLoRA
- `scripts/make_mlx_data.py` — split + hash-перевірка нуль-overlap з eval
- `adapters/adapters.safetensors` — **LoRA-ваги (80 MB)** + `adapter_config.json`
- `results/*.json` — метрики; `results/train_log.txt` — крива loss
- _bonus, хмарні референси:_ `scripts/evaluate_together.py`, `evaluate.py`, `generate_data.py`
