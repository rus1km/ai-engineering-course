"""Summarization for long documents using LLM."""

SUMMARIZE_THRESHOLD = 3000  # chars


def summarize_long_docs(
    texts: list[str],
    api_key: str | None = None,
    threshold: int = SUMMARIZE_THRESHOLD,
) -> tuple[list[str], int]:
    """Compress documents exceeding threshold using LLM.

    Short docs pass through unchanged.
    Returns (processed_texts, number_summarized).
    """
    if not api_key:
        result = []
        count = 0
        for t in texts:
            if len(t) > threshold:
                result.append(t[:threshold] + "\n\n[... truncated ...]")
                count += 1
            else:
                result.append(t)
        return result, count

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    result = []
    count = 0
    for t in texts:
        if len(t) <= threshold:
            result.append(t)
            continue
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": (
                        "You are a document summarizer for a healthcare RAG system. "
                        "Compress the document while preserving ALL: "
                        "1) Procedures and step-by-step instructions "
                        "2) Phone numbers, emails, and contact info "
                        "3) Policies, rules, and requirements "
                        "4) Dates, deadlines, and schedules "
                        "5) Specific numbers (costs, wait times, dosages) "
                        "Remove boilerplate, repetition, and filler text. "
                        "Output should be 30-50% of original length."
                    )},
                    {"role": "user", "content": f"Summarize this document:\n\n{t}"},
                ],
                temperature=0.1,
                max_tokens=1500,
            )
            result.append(resp.choices[0].message.content or t)
            count += 1
        except Exception:
            result.append(t)

    return result, count
