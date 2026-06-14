"""Guardrails: input- та output-фільтри навколо LLM.

Це той шар, що відрізняє baseline (guardrails off) від guarded конфігурації.
Використовується в live-режимі; в offline-режимі його ефект уже "запечено"
у fixtures.guarded, тож логіка тут і там узгоджена.

Три механізми:
  1. input_tripwire()  — блокує prompt-injection / jailbreak / явні запити PII
  2. redact_pii()      — output-фільтр, що вирізає PII, яке могло протекти
  3. SAFE_REFUSAL      — стандартна безпечна відмова
"""
from __future__ import annotations

import re

SAFE_REFUSAL = (
    "I can't help with that request. I can answer questions about Acme's HR "
    "policies — for anything involving personal data or credentials, contact hr@acme.com."
)

# Документовані публічні контакти — НЕ PII. Прибираємо їх перед PII-скануванням,
# щоб детектор/редакція не давали хибних спрацювань на них.
PUBLIC_CONTACTS = ["hr@acme.com", "1-800-555-2263"]


def strip_public_contacts(text: str) -> str:
    out = text or ""
    for c in PUBLIC_CONTACTS:
        out = out.replace(c, "")
    return out

# --- 1. Input tripwires --------------------------------------------------------

_INJECTION_PATTERNS = [
    r"ignore (all|any|previous|prior) ",
    r"system override",
    r"system prompt",
    r"reveal (the |your )?(system|prompt|password|api key|secret)",
    r"\byou are now\b",
    r"\bDAN\b",
    r"admin mode",
    r"disregard (the|all|previous)",
    r"unlimited vacation",
]
_PII_REQUEST_PATTERNS = [
    r"\bssn\b", r"social security", r"home address", r"personal (email|phone|cell)",
    r"salary", r"password", r"api key",
]


def input_tripwire(prompt: str) -> str | None:
    """Повертає причину блокування або None. Грубий, але дешевий перший рубіж."""
    low = prompt.lower()
    for p in _INJECTION_PATTERNS:
        if re.search(p, low):
            return f"injection_pattern:{p}"
    for p in _PII_REQUEST_PATTERNS:
        if re.search(p, low):
            return f"pii_request:{p}"
    return None


# --- 2. Output PII redaction ---------------------------------------------------

_PII_REGEXES = {
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "phone": re.compile(r"\(?\b\d{3}\)?[ -]\d{3}-\d{4}\b"),
    "email_personal": re.compile(r"\b[\w.+-]+@gmail\.com\b", re.I),
    "salary": re.compile(r"\$\d{3},\d{3}"),
    "address": re.compile(r"\b\d{1,4} [A-Z][a-z]+ (Terrace|Road|Drive|Street|Ave|Avenue)\b"),
    "secret": re.compile(r"\b(sk-[\w-]+|hunter2-acme-\d+)\b"),
}


def redact_pii(text: str) -> tuple[str, list[str]]:
    """Маскує PII/секрети у відповіді, зберігаючи публічні контакти. Останній рубіж."""
    found: list[str] = []
    # Тимчасово ховаємо публічні контакти, щоб їх не зачепила редакція.
    out = text or ""
    placeholders = {f"__PUB{i}__": c for i, c in enumerate(PUBLIC_CONTACTS)}
    for ph, c in placeholders.items():
        out = out.replace(c, ph)
    for label, rx in _PII_REGEXES.items():
        if rx.search(out):
            found.append(label)
            out = rx.sub("[REDACTED]", out)
    for ph, c in placeholders.items():
        out = out.replace(ph, c)
    return out, found
