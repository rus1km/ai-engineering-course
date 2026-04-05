"""RAG quality scoring and issue detection."""

from difflib import SequenceMatcher

from preprocessing import scan_pii, scan_pii_total


def compute_quality(
    pii_count: int, dup_count: int, total_docs: int, chunking_on: bool
) -> float:
    """Composite RAG quality score 0.0 - 1.0."""
    pii_score = 1.0 if pii_count == 0 else max(0, 1 - pii_count / 30)
    dup_score = 1.0 - (dup_count / max(total_docs, 1))
    chunk_score = 1.0 if chunking_on else 0.3
    return round(min(1.0, 0.4 * pii_score + 0.3 * dup_score + 0.3 * chunk_score), 2)


def detect_issues(
    context_chunks: list[str], answer: str = "", has_api_key: bool = False
) -> list[str]:
    """Detect PII leaks and duplicate chunks in RAG results."""
    issues: list[str] = []

    # PII in retrieved chunks
    chunk_pii = scan_pii(" ".join(context_chunks))
    pii_parts = []
    for key, label in [
        ("email", "emails"), ("phone", "phones"), ("ssn", "SSNs"),
        ("dob", "DOBs"), ("card", "credit cards"), ("insurance_id", "insurance IDs"),
    ]:
        count = chunk_pii.get(key, 0)
        if count:
            pii_parts.append(f"{count} {label}")
    if pii_parts:
        issues.append(f"\U0001f6a8 HIPAA VIOLATION in retrieved chunks: {', '.join(pii_parts)}")

    # Duplicate chunks
    for i in range(len(context_chunks)):
        for j in range(i + 1, len(context_chunks)):
            if SequenceMatcher(None, context_chunks[i], context_chunks[j]).ratio() > 0.7:
                issues.append(f"Chunks {i+1} and {j+1} are near-duplicates (biased retrieval)")

    # PII in GPT answer
    if has_api_key and answer and scan_pii_total(answer) > 0:
        issues.append("\U0001f6a8 HIPAA VIOLATION: PII/PHI leaked in GPT answer!")

    return issues
