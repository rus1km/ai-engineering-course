"""Vector search over embedded chunks."""

import numpy as np

from .embeddings import get_openai_embeddings, get_tfidf_embeddings


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def search_chunks(
    query: str,
    chunks: list[str],
    api_key: str | None,
    top_k: int = 3,
) -> list[tuple[str, float]]:
    """Embed chunks + query, return top-k by cosine similarity."""
    chunk_tuple = tuple(chunks)

    if api_key:
        chunk_embs = get_openai_embeddings(chunk_tuple, api_key)
        query_emb = get_openai_embeddings((query,), api_key)[0]
    else:
        all_embs = get_tfidf_embeddings(tuple(list(chunk_tuple) + [query]))
        chunk_embs, query_emb = all_embs[:-1], all_embs[-1]

    scores = [_cosine_sim(query_emb, ce) for ce in chunk_embs]
    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
    return [(chunks[idx], score) for idx, score in ranked]
