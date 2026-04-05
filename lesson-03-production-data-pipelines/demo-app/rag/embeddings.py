"""Embedding providers: OpenAI and TF-IDF fallback."""

import numpy as np
import streamlit as st


@st.cache_data(show_spinner="Computing embeddings...")
def get_openai_embeddings(texts: tuple[str, ...], api_key: str) -> np.ndarray:
    """Embed texts via OpenAI text-embedding-3-small."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    resp = client.embeddings.create(model="text-embedding-3-small", input=list(texts))
    return np.array([item.embedding for item in resp.data])


@st.cache_data(show_spinner="TF-IDF embeddings (fallback)...")
def get_tfidf_embeddings(texts: tuple[str, ...]) -> np.ndarray:
    """Fallback when no API key is available."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    return TfidfVectorizer(max_features=512).fit_transform(list(texts)).toarray()
