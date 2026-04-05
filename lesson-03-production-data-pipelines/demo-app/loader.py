"""Load documents from PDF files."""

import os
from pathlib import Path

import pdfplumber


def load_docs_from_folder(docs_dir: str | None = None) -> list[dict]:
    """Load all PDF documents from docs/ folder."""
    if docs_dir is None:
        docs_dir = os.path.join(os.path.dirname(__file__), "docs")
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        return []
    docs = []
    for pdf_file in sorted(docs_path.glob("*.pdf")):
        try:
            with pdfplumber.open(pdf_file) as pdf:
                text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            if text.strip():
                docs.append({
                    "id": pdf_file.stem,
                    "text": text.strip(),
                    "source": pdf_file.name,
                })
        except Exception:
            continue
    return docs
