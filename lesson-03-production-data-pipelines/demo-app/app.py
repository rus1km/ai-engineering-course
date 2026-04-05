"""
Broken RAG -> Fixed RAG: Healthcare Clinic Demo
Streamlit UI — all logic in separate modules.
"""

import os
from difflib import SequenceMatcher

import streamlit as st
from dotenv import load_dotenv

from loader import load_docs_from_folder
from preprocessing import (
    CHUNKING_STRATEGIES,
    SUMMARIZE_THRESHOLD,
    chunk_texts,
    deduplicate_texts,
    redact_pii,
    scan_pii_total,
    summarize_long_docs,
)
from quality import compute_quality, detect_issues
from rag import ask_gpt, search_chunks

load_dotenv()


def _render_sidebar() -> dict:
    """Render sidebar controls, return pipeline config."""
    with st.sidebar:
        st.header("Pipeline Steps")

        step_pii = st.toggle(
            "\U0001f6a8 PII/PHI Redaction", value=False,
            help="Redact emails, phones, SSNs, DOBs, insurance IDs, credit cards.",
        )
        st.divider()

        step_dedup = st.toggle(
            "\U0001f501 Deduplication", value=False,
            help="Remove near-duplicate documents that bias retrieval.",
        )
        dedup_threshold = 0.7
        if step_dedup:
            dedup_threshold = st.slider("Similarity threshold", 0.3, 1.0, 0.7, 0.05)
        st.divider()

        step_summarize = st.toggle(
            "\U0001f4dd Summarize long docs", value=False,
            help=f"Compress documents longer than {SUMMARIZE_THRESHOLD} chars using LLM.",
        )
        st.divider()

        st.markdown("**\u2702\ufe0f Chunking Strategy**")
        chunk_strategy = st.selectbox("Strategy", CHUNKING_STRATEGIES)
        step_chunk = chunk_strategy != "No chunking"
        chunk_size, chunk_overlap = 512, 50
        if step_chunk:
            chunk_size = st.slider("Chunk size (chars)", 128, 2048, 512, 64)
            chunk_overlap = st.slider("Overlap (chars)", 0, 200, 50, 10)

        st.divider()
        st.header("Data")
        use_sample = st.button("Load sample clinic data", type="primary")

    return {
        "pii": step_pii, "dedup": step_dedup, "dedup_threshold": dedup_threshold,
        "summarize": step_summarize, "chunk": step_chunk,
        "chunk_strategy": chunk_strategy, "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap, "use_sample": use_sample,
    }


def _run_pipeline(raw_texts: list[str], cfg: dict, api_key: str) -> tuple[list[str], list[str], list[str]]:
    """Execute preprocessing pipeline. Returns (texts, chunks, log)."""
    log: list[str] = []
    texts = list(raw_texts)
    log.append(f"Input: {len(texts)} documents")

    if cfg["pii"]:
        texts = [redact_pii(t) for t in texts]
        log.append(f"PII redacted: {len(texts)} docs")

    if cfg["summarize"]:
        texts, n = summarize_long_docs(texts, api_key=api_key or None)
        log.append(f"Summarized: {n} long docs (>{SUMMARIZE_THRESHOLD} chars)")

    if cfg["dedup"]:
        pre = len(texts)
        texts, removed = deduplicate_texts(texts, cfg["dedup_threshold"])
        log.append(f"Dedup: {pre} -> {len(texts)} (-{removed})")

    chunks = texts
    if cfg["chunk"]:
        chunks = chunk_texts(texts, cfg["chunk_strategy"], cfg["chunk_size"], cfg["chunk_overlap"], api_key=api_key or None)
        log.append(f"Chunking ({cfg['chunk_strategy']}): {len(texts)} docs -> {len(chunks)} chunks")

    return texts, chunks, log


def _render_metrics(raw_texts: list[str], texts: list[str], chunks: list[str], cfg: dict):
    """Render pipeline metrics dashboard."""
    raw_pii = scan_pii_total("\n".join(raw_texts))
    cur_pii = scan_pii_total("\n".join(texts))
    raw_dups = deduplicate_texts(raw_texts, cfg["dedup_threshold"])[1]
    cur_dups = 0 if cfg["dedup"] else raw_dups
    quality = compute_quality(cur_pii, cur_dups, len(raw_texts), cfg["chunk"])

    st.subheader("Pipeline Metrics")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Documents", len(texts), delta=len(texts) - len(raw_texts) if cfg["dedup"] else None)
    with c2:
        st.metric("PII/PHI Found", cur_pii, delta=cur_pii - raw_pii if cfg["pii"] else None)
    with c3:
        st.metric("Duplicates", cur_dups, delta=-raw_dups if cfg["dedup"] else None)
    with c4:
        st.metric("Chunks", len(chunks))

    st.markdown(f"**RAG Quality Score: {quality:.0%}**")
    st.progress(quality)
    st.divider()


def _render_query(chunks: list[str], api_key: str):
    """Render query input, search results, GPT answer, and issues."""
    st.subheader("RAG Query")
    query = st.text_input("Question", value="How do I schedule a cardiology appointment?")
    ask = st.button("Ask RAG", type="primary")

    if not (ask and query):
        return
    if not chunks:
        st.error("No data to search.")
        return

    with st.spinner("Searching..."):
        results = search_chunks(query, chunks, api_key or None, top_k=3)

    # Retrieval metrics
    scores = [s for _, s in results]
    avg_sim = sum(scores) / len(scores) if scores else 0
    avg_chunk_len = sum(len(c) for c in chunks) / len(chunks) if chunks else 0

    st.markdown("#### Retrieval Metrics")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Avg similarity", f"{avg_sim:.3f}")
    with m2:
        st.metric("Total chunks", len(chunks))
    with m3:
        st.metric("Avg chunk size", f"{int(avg_chunk_len)} chars")
    with m4:
        dup_pairs = sum(
            1 for i in range(len(results)) for j in range(i + 1, len(results))
            if SequenceMatcher(None, results[i][0], results[j][0]).ratio() > 0.7
        )
        st.metric("Duplicate pairs in top-3", dup_pairs)

    # Chunks
    st.markdown("#### Retrieved Chunks")
    context_chunks = []
    for i, (text, score) in enumerate(results, 1):
        context_chunks.append(text)
        with st.expander(f"Chunk {i} (similarity: {score:.3f}) \u2014 {len(text)} chars", expanded=(i == 1)):
            st.text(text)

    # GPT answer
    st.markdown("#### GPT Answer")
    answer = ""
    if api_key:
        with st.spinner("Generating answer..."):
            answer = ask_gpt(query, context_chunks, api_key)
        st.success(answer)
    else:
        st.warning("No API key \u2014 GPT answer unavailable.")

    # Issues
    st.markdown("#### Issues Detected")
    issues = detect_issues(context_chunks, answer, has_api_key=bool(api_key))
    if not issues:
        st.success("\u2705 No issues detected. HIPAA compliant response.")
    else:
        for issue in issues:
            st.error(issue)


def main():
    st.set_page_config(page_title="Broken RAG -> Fixed RAG", page_icon="\U0001f3e5", layout="wide")
    st.title("Broken RAG \u2192 Fixed RAG")
    st.caption(
        "Healthcare clinic RAG demo. Toggle each preprocessing step and see "
        "how it changes the answer quality. Without preprocessing, the chatbot "
        "leaks patient data (HIPAA violation)."
    )

    api_key = os.environ.get("OPENAI_KEY") or os.environ.get("OPENAI_API_KEY") or ""
    if not api_key:
        st.sidebar.error("Set OPENAI_KEY in .env file")

    cfg = _render_sidebar()

    # Load data
    if "docs" not in st.session_state:
        st.session_state["docs"] = None
    if cfg["use_sample"]:
        st.session_state["docs"] = [d["text"] for d in load_docs_from_folder()]

    raw_texts = st.session_state.get("docs")
    if raw_texts is None:
        st.info("Click **'Load sample clinic data'** in the sidebar to start.")
        return

    # Pipeline
    texts, chunks, log = _run_pipeline(raw_texts, cfg, api_key)

    # UI
    _render_metrics(raw_texts, texts, chunks, cfg)
    _render_query(chunks, api_key)

    with st.expander("Pipeline execution log"):
        for entry in log:
            st.text(entry)


if __name__ == "__main__":
    main()
