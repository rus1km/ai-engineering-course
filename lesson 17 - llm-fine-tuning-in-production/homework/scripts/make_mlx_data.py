"""
Split data/train.jsonl (300 chat-format rows) into MLX-LM LoRA train/valid sets.

MLX-LM accepts chat format directly: each line is {"messages": [...]}.
Writes data/mlx/{train,valid}.jsonl and re-verifies ZERO hash overlap with eval.jsonl.

Usage:
    python scripts/make_mlx_data.py
"""

import json
import hashlib
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
OUT = DATA / "mlx"
OUT.mkdir(parents=True, exist_ok=True)


def hash_email(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


def user_email(row: dict) -> str:
    for m in row["messages"]:
        if m["role"] == "user":
            return m["content"]
    return ""


def main():
    train_rows = [json.loads(l) for l in open(DATA / "train.jsonl") if l.strip()]
    eval_rows = [json.loads(l) for l in open(DATA / "eval.jsonl") if l.strip()]

    eval_hashes = {hash_email(e["email"]) for e in eval_rows}

    # Re-verify zero overlap (defense-in-depth; generator already deduped)
    overlap = [r for r in train_rows if hash_email(user_email(r)) in eval_hashes]
    assert not overlap, f"LEAK: {len(overlap)} train rows overlap eval!"
    print(f"Hash-check OK: 0 / {len(train_rows)} train rows overlap the {len(eval_rows)} eval rows")

    rng = random.Random(7)
    rng.shuffle(train_rows)
    n_valid = 20
    valid_rows = train_rows[:n_valid]
    train_split = train_rows[n_valid:]

    with open(OUT / "train.jsonl", "w") as f:
        for r in train_split:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    with open(OUT / "valid.jsonl", "w") as f:
        for r in valid_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Wrote {len(train_split)} train + {len(valid_rows)} valid -> {OUT}")


if __name__ == "__main__":
    main()
