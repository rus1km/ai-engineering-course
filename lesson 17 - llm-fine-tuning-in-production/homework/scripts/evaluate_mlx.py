"""
Evaluate a local MLX model (base or LoRA fine-tuned) against eval.jsonl.

Metrics are IDENTICAL to scripts/evaluate.py (OpenAI) so numbers are comparable:
    json_valid_rate, exact_match_rate, field_accuracy (5 fields),
    avg_input_tokens, avg_output_tokens.

Usage:
    python scripts/evaluate_mlx.py \
        --model mlx-community/Meta-Llama-3.1-8B-Instruct-4bit \
        --output results/baseline_8b_mlx.json

    python scripts/evaluate_mlx.py \
        --model mlx-community/Meta-Llama-3.1-8B-Instruct-4bit \
        --adapter adapters \
        --output results/finetuned_8b_mlx.json
"""

import argparse
import json
import time
from pathlib import Path
from collections import defaultdict

from mlx_lm import load, generate
from mlx_lm.sample_utils import make_sampler

SYSTEM_PROMPT = (
    "You extract structured data from customer support emails. "
    "Return only a single valid JSON object with fields: "
    "customer_name (string or null), product (string), "
    "issue_category (one of: billing, technical, account, feature_request, other), "
    "urgency (one of: low, medium, high, critical), "
    "summary (one short sentence). No extra text."
)

FIELDS = ["customer_name", "product", "issue_category", "urgency", "summary"]


def safe_json_parse(s):
    s = (s or "").strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        s = s.rsplit("```", 1)[0].strip()
        if s.startswith("json"):
            s = s[4:].strip()
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        s = s[start:end + 1]
    try:
        return json.loads(s), True
    except json.JSONDecodeError:
        return None, False


def field_match(predicted, expected, field):
    if field == "summary":
        if not isinstance(predicted, str) or not isinstance(expected, str):
            return False
        p = {w.lower().strip(".,!?") for w in predicted.split() if len(w) > 3}
        e = {w.lower().strip(".,!?") for w in expected.split() if len(w) > 3}
        if not p or not e:
            return False
        return len(p & e) / max(len(e), 1) >= 0.4
    if field == "customer_name":
        if predicted is None and expected is None:
            return True
        if predicted is None or expected is None:
            return False
        return expected.split()[0].lower() in predicted.lower() if predicted else False
    if predicted is None:
        return False
    return str(predicted).strip().lower() == str(expected).strip().lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--adapter", default=None, help="path to LoRA adapter dir")
    ap.add_argument("--eval-file", default="data/eval.jsonl")
    ap.add_argument("--output", required=True)
    ap.add_argument("--max-tokens", type=int, default=200)
    args = ap.parse_args()

    here = Path(__file__).resolve().parent.parent
    examples = [json.loads(l) for l in open(here / args.eval_file) if l.strip()]
    out_path = here / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)

    label = f"{args.model}" + (f" + adapter({args.adapter})" if args.adapter else " (base)")
    print(f"Loading {label} ...")
    model, tokenizer = load(args.model, adapter_path=args.adapter)
    sampler = make_sampler(temp=0.0)  # greedy / deterministic

    results = []
    tot_in = tot_out = 0
    json_valid = exact_match = 0
    field_correct = defaultdict(int)
    t0 = time.time()

    for i, ex in enumerate(examples, 1):
        email, expected = ex["email"], ex["expected"]
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": email},
        ]
        prompt = tokenizer.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=False
        )
        n_in = len(tokenizer.encode(prompt))
        raw = generate(
            model, tokenizer, prompt=prompt,
            max_tokens=args.max_tokens, sampler=sampler, verbose=False,
        )
        n_out = len(tokenizer.encode(raw))
        tot_in += n_in
        tot_out += n_out

        predicted, valid = safe_json_parse(raw)
        if valid:
            json_valid += 1
        per_field, all_match = {}, True
        for fld in FIELDS:
            ok = valid and field_match(predicted.get(fld) if predicted else None, expected[fld], fld)
            per_field[fld] = ok
            if ok:
                field_correct[fld] += 1
            else:
                all_match = False
        if valid and all_match:
            exact_match += 1

        results.append({
            "i": i, "email": email, "expected": expected,
            "raw_output": raw, "predicted": predicted, "valid_json": valid,
            "exact_match": valid and all_match, "field_match": per_field,
            "in_tokens": n_in, "out_tokens": n_out,
        })
        m = "✓" if (valid and all_match) else "✗"
        print(f"  [{i}/{len(examples)}] {m} valid={valid} exact={valid and all_match}")

    n = len(examples)
    elapsed = time.time() - t0
    metrics = {
        "model": args.model,
        "adapter": args.adapter,
        "n_examples": n,
        "json_valid_rate": round(json_valid / n, 4),
        "exact_match_rate": round(exact_match / n, 4),
        "field_accuracy": {f: round(field_correct[f] / n, 4) for f in FIELDS},
        "avg_input_tokens": round(tot_in / n, 1),
        "avg_output_tokens": round(tot_out / n, 1),
        "total_input_tokens": tot_in,
        "total_output_tokens": tot_out,
        "wall_seconds": round(elapsed, 1),
        "avg_seconds_per_example": round(elapsed / n, 2),
        "details": results,
    }
    with open(out_path, "w") as f:
        json.dump(metrics, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print(f"Model: {label}")
    print(f"JSON valid:  {metrics['json_valid_rate']*100:.1f}%")
    print(f"Exact match: {metrics['exact_match_rate']*100:.1f}%")
    print("Field accuracy:")
    for f in FIELDS:
        print(f"  {f:18s} {metrics['field_accuracy'][f]*100:.1f}%")
    print(f"Avg I/O tokens: {metrics['avg_input_tokens']} / {metrics['avg_output_tokens']}")
    print(f"Latency: {metrics['avg_seconds_per_example']}s/example  ({elapsed:.0f}s total)")
    print(f"Saved -> {out_path}")


if __name__ == "__main__":
    main()
