"""LLM answer generation."""

SYSTEM_PROMPT = (
    "You are a healthcare clinic assistant. Answer using ONLY the provided context. "
    "Be helpful and detailed. ALWAYS include relevant contact information "
    "(names, emails, phone numbers, extensions) from the context so the patient "
    "knows exactly who to reach out to. Quote the contact details exactly as they appear."
)


def ask_gpt(query: str, context_chunks: list[str], api_key: str) -> str:
    """Send context + query to GPT-4o-mini."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    context = "\n---\n".join(context_chunks)
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {query}"},
        ],
        temperature=0.3,
        max_tokens=512,
    )
    return resp.choices[0].message.content or ""
