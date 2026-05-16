"""In-memory transaction store на pandas.

Завантажує CSV один раз і кешує DataFrame. Усі tools читають із цього кешу.
"""
from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd

from app.config import settings


@lru_cache(maxsize=1)
def load_transactions(csv_path: str | None = None) -> pd.DataFrame:
    path = Path(csv_path) if csv_path else settings.transactions_path
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df["amount"] = df["amount"].astype(float)
    df["recurring"] = df["recurring"].astype(str).str.lower() == "true"
    df["hour"] = df["date"].dt.hour
    df["weekday"] = df["date"].dt.weekday  # 0=Mon
    df["is_weekend"] = df["weekday"] >= 5
    df["month"] = df["date"].dt.to_period("M").astype(str)
    df = df.sort_values("date").reset_index(drop=True)
    return df


def today() -> datetime:
    """Поточна дата для запитів. У dataset транзакції до 2025-11-30,
    тому фіксуємо 'сьогодні' як 2025-11-30 — інакше 'минулий тиждень' буде порожнім."""
    return datetime(2025, 11, 30, 23, 59)
