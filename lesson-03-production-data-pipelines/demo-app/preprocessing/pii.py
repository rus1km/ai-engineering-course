"""PII / PHI detection and redaction."""

import re

PII_PATTERNS = {
    "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    "phone": r"\(\d{3}\)\s?\d{3}[\s-]?\d{4}",
    "card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "ssn_masked": r"\*{3}-\*{2}-\d{4}",
    "dob": r"\b\d{2}/\d{2}/\d{4}\b",
    "insurance_id": r"\b[A-Z]{2,4}-\d{5,10}\b",
    "mrn": r"\bMRN-\d{4}-\d{4,6}\b",
}

_REPLACEMENTS = {
    "email": "[EMAIL]",
    "phone": "[PHONE]",
    "card": "[CARD]",
    "ssn": "[SSN]",
    "ssn_masked": "[SSN]",
    "dob": "[DOB]",
    "insurance_id": "[ID]",
    "mrn": "[MRN]",
}


def redact_pii(text: str) -> str:
    """Replace all PII/PHI patterns with placeholders."""
    for pii_type, pattern in PII_PATTERNS.items():
        text = re.sub(pattern, _REPLACEMENTS[pii_type], text)
    return text


def scan_pii(text: str) -> dict[str, int]:
    """Count PII items by type."""
    counts: dict[str, int] = {}
    for pii_type, pattern in PII_PATTERNS.items():
        key = pii_type.replace("_masked", "")
        counts[key] = counts.get(key, 0) + len(re.findall(pattern, text))
    return counts


def scan_pii_total(text: str) -> int:
    """Total count of all PII items."""
    return sum(scan_pii(text).values())
