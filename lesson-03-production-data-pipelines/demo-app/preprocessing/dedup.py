"""Exact and near-duplicate detection."""

import hashlib
from difflib import SequenceMatcher


def deduplicate_texts(
    texts: list[str], threshold: float = 0.7
) -> tuple[list[str], int]:
    """Remove exact (SHA-256) and near-duplicate (SequenceMatcher) texts.

    Returns (deduplicated_texts, number_removed).
    """
    if not texts:
        return texts, 0

    # Phase 1: exact dedup via hash
    seen: set[str] = set()
    phase1: list[str] = []
    for t in texts:
        h = hashlib.sha256(t.encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            phase1.append(t)

    # Phase 2: near-dedup via SequenceMatcher
    keep: list[str] = []
    for t in phase1:
        is_dup = any(
            SequenceMatcher(None, t, k).ratio() >= threshold for k in keep
        )
        if not is_dup:
            keep.append(t)

    return keep, len(texts) - len(keep)
