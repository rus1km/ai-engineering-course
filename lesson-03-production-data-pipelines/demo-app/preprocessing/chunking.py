"""Chunking strategies for RAG pipelines."""

import re


from openai import OpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

CHUNKING_STRATEGIES = [
    "No chunking",
    "Fixed-size",
    "Recursive character",
    "Semantic",
    "Parent-child",
    "Context-enriched",
    "By section",
]


def _chunk_by_section(text: str) -> list[str]:
    """Split by EHR-style section headers (--- HEADER ---, === HEADER ===)."""
    parts = re.split(r"\n(?=---\s*[A-Z]|===\s*[A-Z])", text)
    expanded: list[str] = []
    for part in parts:
        sub = re.split(r"\n(?=[A-Z][A-Z ]+\|)", part)
        expanded.extend(sub)
    return [p.strip() for p in expanded if len(p.strip()) > 30] or [text]


def _semantic_split(text: str, chunk_size: int, api_key: str | None = None) -> list[str]:
    """Split at semantic boundaries using embedding similarity."""
    import numpy as np

    sentences = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    if len(sentences) <= 2:
        return [text]

    if api_key:
        try:
            
            client = OpenAI(api_key=api_key)
            resp = client.embeddings.create(model="text-embedding-3-small", input=sentences)
            embs = np.array([e.embedding for e in resp.data])
        except Exception:
            from sklearn.feature_extraction.text import TfidfVectorizer
            embs = TfidfVectorizer(max_features=256).fit_transform(sentences).toarray()
    else:
        from sklearn.feature_extraction.text import TfidfVectorizer
        embs = TfidfVectorizer(max_features=256).fit_transform(sentences).toarray()

    similarities = []
    for i in range(len(embs) - 1):
        a, b = embs[i], embs[i + 1]
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        similarities.append(float(np.dot(a, b) / (na * nb)) if na > 0 and nb > 0 else 0.0)

    threshold = np.mean(similarities) - 0.5 * np.std(similarities)

    chunks: list[str] = []
    current: list[str] = [sentences[0]]
    for i, sent in enumerate(sentences[1:]):
        if similarities[i] < threshold and len(" ".join(current)) > 50:
            chunks.append(" ".join(current))
            current = [sent]
        else:
            current.append(sent)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _context_enrich(chunk: str, full_text: str) -> str:
    """Prepend document context header to a chunk."""
    lines = [line.strip() for line in full_text.split("\n") if line.strip()]
    header = lines[0][:100] if lines else "Document"
    return f"[Context: {header}]\n{chunk}"


def chunk_texts(
    texts: list[str],
    strategy: str,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    api_key: str | None = None,
) -> list[str]:
    """Split texts into chunks using the chosen strategy."""
    if strategy == "No chunking":
        return list(texts)

    chunks: list[str] = []

    if strategy == "Fixed-size":
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=[" "],
        )
        for t in texts:
            chunks.extend(splitter.split_text(t))

    elif strategy == "Recursive character":
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", " "],
        )
        for t in texts:
            chunks.extend(splitter.split_text(t))

    elif strategy == "Semantic":
        for t in texts:
            chunks.extend(_semantic_split(t, chunk_size, api_key))

    elif strategy == "Parent-child":
        parent_sp = RecursiveCharacterTextSplitter(chunk_size=chunk_size * 3, chunk_overlap=0, separators=["\n\n", "\n"])
        child_sp = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n\n", "\n", ". ", " "])
        for t in texts:
            for parent in parent_sp.split_text(t):
                chunks.extend(child_sp.split_text(parent))

    elif strategy == "Context-enriched":
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n\n", "\n", ". ", " "],
        )
        for t in texts:
            for c in splitter.split_text(t):
                chunks.append(_context_enrich(c, t))

    elif strategy == "By section":
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap, separators=["\n\n", "\n", ". ", " "],
        )
        for t in texts:
            for section in _chunk_by_section(t):
                if len(section) > chunk_size:
                    chunks.extend(splitter.split_text(section))
                else:
                    chunks.append(section)

    return chunks
