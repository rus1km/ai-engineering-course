"""Інструменти для запитів до транзакцій.

Усі функції приймають серіалізовувані Python-типи і повертають JSON-сумісні dict-и.
Дві ролі: (1) використовуватися як tools у LLM (через схеми), (2) викликатися напряму
у тестах.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from app.tools.data import load_transactions, today

# ----------------------------- helpers -----------------------------


def _parse_period(period: str | None) -> tuple[datetime, datetime]:
    """Перетворює людський період у (start, end) datetime.

    Підтримує: 'last_week', 'this_week', 'last_month', 'this_month',
    'last_3_months', 'this_year', 'last_year', 'ytd',
    або ISO-діапазон 'YYYY-MM-DD..YYYY-MM-DD',
    або 'YYYY-MM' (конкретний місяць).
    """
    now = today()
    p = (period or "last_30_days").lower().strip()

    if ".." in p:
        a, b = p.split("..")
        return datetime.fromisoformat(a), datetime.fromisoformat(b) + timedelta(days=1) - timedelta(seconds=1)

    if len(p) == 7 and p[4] == "-":  # YYYY-MM
        y, m = int(p[:4]), int(p[5:])
        start = datetime(y, m, 1)
        end = datetime(y + (m == 12), (m % 12) + 1, 1) - timedelta(seconds=1)
        return start, end

    if p == "last_week":
        end = now - timedelta(days=now.weekday() + 1)
        start = end - timedelta(days=6)
        return start.replace(hour=0, minute=0), end.replace(hour=23, minute=59)
    if p == "this_week":
        start = now - timedelta(days=now.weekday())
        return start.replace(hour=0, minute=0), now
    if p == "last_month":
        first_this = now.replace(day=1)
        last_prev = first_this - timedelta(seconds=1)
        first_prev = last_prev.replace(day=1, hour=0, minute=0, second=0)
        return first_prev, last_prev
    if p == "this_month":
        return now.replace(day=1, hour=0, minute=0, second=0), now
    if p == "last_3_months":
        return (now - timedelta(days=90)), now
    if p == "last_30_days":
        return (now - timedelta(days=30)), now
    if p == "this_year":
        return datetime(now.year, 1, 1), now
    if p == "last_year":
        return datetime(now.year - 1, 1, 1), datetime(now.year - 1, 12, 31, 23, 59)
    if p == "ytd":
        return datetime(now.year, 1, 1), now
    if p == "all":
        return datetime(2000, 1, 1), now
    raise ValueError(f"Unknown period: {period!r}")


def _filter(
    df: pd.DataFrame,
    period: str | None = None,
    category: str | list[str] | None = None,
    merchant_contains: str | None = None,
    account: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    hour_min: int | None = None,
    hour_max: int | None = None,
    recurring: bool | None = None,
    spending_only: bool = True,
) -> pd.DataFrame:
    out = df
    if period:
        start, end = _parse_period(period)
        out = out[(out["date"] >= start) & (out["date"] <= end)]
    if category:
        cats = [category] if isinstance(category, str) else list(category)
        out = out[out["category"].isin(cats)]
    if merchant_contains:
        out = out[out["merchant"].str.contains(merchant_contains, case=False, na=False)]
    if account:
        out = out[out["account"] == account]
    if recurring is not None:
        out = out[out["recurring"] == recurring]
    if hour_min is not None:
        out = out[out["hour"] >= hour_min]
    if hour_max is not None:
        out = out[out["hour"] <= hour_max]
    if spending_only:
        out = out[out["amount"] < 0]
    if min_amount is not None:
        out = out[out["amount"].abs() >= min_amount]
    if max_amount is not None:
        out = out[out["amount"].abs() <= max_amount]
    return out


# ----------------------------- public tools -----------------------------


def query_transactions(
    period: str | None = None,
    category: str | list[str] | None = None,
    merchant_contains: str | None = None,
    account: str | None = None,
    min_amount: float | None = None,
    max_amount: float | None = None,
    hour_min: int | None = None,
    hour_max: int | None = None,
    recurring: bool | None = None,
    spending_only: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    """Повертає список транзакцій під фільтр + summary."""
    df = load_transactions()
    sub = _filter(
        df, period, category, merchant_contains, account, min_amount, max_amount,
        hour_min, hour_max, recurring, spending_only,
    )
    rows = sub.head(limit)[["date", "merchant", "amount", "category", "account", "recurring"]].copy()
    rows["date"] = rows["date"].dt.strftime("%Y-%m-%d %H:%M")
    return {
        "count": int(len(sub)),
        "total_amount": round(float(sub["amount"].sum()), 2),
        "transactions": rows.to_dict(orient="records"),
        "filter": {k: v for k, v in {
            "period": period, "category": category, "merchant_contains": merchant_contains,
            "account": account, "min_amount": min_amount, "max_amount": max_amount,
            "hour_min": hour_min, "hour_max": hour_max, "recurring": recurring,
        }.items() if v is not None},
    }


def aggregate_spending(
    period: str | None = None,
    category: str | list[str] | None = None,
    merchant_contains: str | None = None,
    group_by: str | None = None,
) -> dict[str, Any]:
    """Сума витрат із опційним групуванням ('category', 'merchant', 'month', 'weekday', 'account')."""
    df = load_transactions()
    sub = _filter(df, period=period, category=category, merchant_contains=merchant_contains)
    spend = -sub["amount"].sum()
    result: dict[str, Any] = {
        "period": period or "last_30_days",
        "total_spending": round(float(spend), 2),
        "transaction_count": int(len(sub)),
    }
    if group_by:
        if group_by not in {"category", "merchant", "month", "weekday", "account"}:
            raise ValueError(f"Unsupported group_by: {group_by}")
        g = sub.groupby(group_by)["amount"].agg(["sum", "count"]).reset_index()
        g["total_spent"] = (-g["sum"]).round(2)
        g = g.sort_values("total_spent", ascending=False)
        result["groups"] = [
            {group_by: row[group_by], "total_spent": float(row["total_spent"]), "count": int(row["count"])}
            for _, row in g.iterrows()
        ]
    return result


def top_categories(period: str = "this_month", n: int = 5) -> dict[str, Any]:
    res = aggregate_spending(period=period, group_by="category")
    res["groups"] = res.get("groups", [])[:n]
    res["top_n"] = n
    return res


def find_recurring(min_months: int = 2) -> dict[str, Any]:
    """Виявляє recurring мерчантів і повертає останню транзакцію + середню суму.

    Виявляє 'забуті' підписки — ті, де last_seen > 60 днів тому.
    """
    df = load_transactions()
    rec = df[df["recurring"] & (df["amount"] < 0)].copy()
    if rec.empty:
        return {"merchants": []}

    grouped = rec.groupby("merchant").agg(
        category=("category", "first"),
        avg_amount=("amount", lambda s: round(-s.mean(), 2)),
        months_active=("month", "nunique"),
        last_seen=("date", "max"),
        first_seen=("date", "min"),
        total_paid=("amount", lambda s: round(-s.sum(), 2)),
    ).reset_index()

    now = today()
    grouped["days_since_last"] = (now - grouped["last_seen"]).dt.days
    grouped["is_forgotten"] = grouped["days_since_last"] > 60
    grouped = grouped[grouped["months_active"] >= min_months]
    grouped = grouped.sort_values("avg_amount", ascending=False)

    merchants = []
    for _, r in grouped.iterrows():
        merchants.append({
            "merchant": r["merchant"],
            "category": r["category"],
            "avg_amount_monthly": float(r["avg_amount"]),
            "months_active": int(r["months_active"]),
            "last_seen": r["last_seen"].strftime("%Y-%m-%d"),
            "days_since_last": int(r["days_since_last"]),
            "is_likely_forgotten": bool(r["is_forgotten"]),
            "total_paid": float(r["total_paid"]),
        })
    return {"merchants": merchants}


def detect_late_night_pattern(
    period: str = "last_3_months",
    categories: list[str] | None = None,
    hour_threshold: int = 21,
) -> dict[str, Any]:
    """Частка транзакцій у заданих категоріях після hour_threshold."""
    cats = categories or ["delivery", "restaurants"]
    df = load_transactions()
    sub = _filter(df, period=period, category=cats)
    total = len(sub)
    if total == 0:
        return {"period": period, "categories": cats, "total": 0, "late_night_count": 0, "late_night_share": 0.0}
    late = sub[sub["hour"] >= hour_threshold]
    return {
        "period": period,
        "categories": cats,
        "hour_threshold": hour_threshold,
        "total": total,
        "late_night_count": int(len(late)),
        "late_night_share": round(len(late) / total, 3),
        "late_night_amount": round(-late["amount"].sum(), 2),
        "total_amount": round(-sub["amount"].sum(), 2),
    }


def compare_periods(
    metric: str = "total_spending",
    period_a: str = "this_month",
    period_b: str = "last_month",
    category: str | list[str] | None = None,
) -> dict[str, Any]:
    """Порівнює суму витрат / транзакцій між двома періодами."""
    a = aggregate_spending(period=period_a, category=category)
    b = aggregate_spending(period=period_b, category=category)
    if metric == "total_spending":
        va, vb = a["total_spending"], b["total_spending"]
    elif metric == "transaction_count":
        va, vb = a["transaction_count"], b["transaction_count"]
    else:
        raise ValueError(f"Unsupported metric: {metric}")
    delta = round(va - vb, 2)
    pct = round((delta / vb) * 100, 1) if vb else None
    return {
        "metric": metric,
        "category": category,
        "period_a": {"label": period_a, "value": va},
        "period_b": {"label": period_b, "value": vb},
        "delta_absolute": delta,
        "delta_pct": pct,
    }


def project_month_close(month: str | None = None) -> dict[str, Any]:
    """Прогноз закриття місяця: salary - поточні витрати - середні витрати/день * залишок днів."""
    now = today()
    if month is None:
        month = now.strftime("%Y-%m")
    df = load_transactions()
    sub = _filter(df, period=month, spending_only=False)
    income = float(sub[sub["amount"] > 0]["amount"].sum())
    spent = float(-sub[sub["amount"] < 0]["amount"].sum())

    # Скільки днів пройшло й залишилось
    y, m = int(month[:4]), int(month[5:])
    month_start = datetime(y, m, 1)
    next_month = datetime(y + (m == 12), (m % 12) + 1, 1)
    month_end = next_month - timedelta(seconds=1)
    today_in_month = min(now, month_end)
    days_passed = max(1, (today_in_month - month_start).days + 1)
    total_days = (month_end - month_start).days + 1
    days_left = max(0, total_days - days_passed)

    avg_spend_per_day = spent / days_passed if days_passed else 0
    projected_extra = avg_spend_per_day * days_left
    projected_total_spend = spent + projected_extra
    projected_net = income - projected_total_spend

    return {
        "month": month,
        "income_so_far": round(income, 2),
        "spent_so_far": round(spent, 2),
        "days_passed": days_passed,
        "days_left": days_left,
        "avg_spend_per_day": round(avg_spend_per_day, 2),
        "projected_additional_spend": round(projected_extra, 2),
        "projected_total_spend": round(projected_total_spend, 2),
        "projected_net": round(projected_net, 2),
    }


def credit_card_status(months: int = 6) -> dict[str, Any]:
    """Аналіз поведінки по credit card: payments vs spending."""
    df = load_transactions()
    start, end = _parse_period(f"last_{months * 30}_days") if False else (today() - timedelta(days=months * 31), today())
    cc_spend = df[(df["account"] == "credit_card") & (df["amount"] < 0) & (df["date"] >= start)]
    cc_pay = df[(df["category"] == "credit_payment") & (df["date"] >= start)]
    return {
        "months_analyzed": months,
        "total_credit_spending": round(float(-cc_spend["amount"].sum()), 2),
        "total_credit_payments": round(float(-cc_pay["amount"].sum()), 2),
        "payment_count": int(len(cc_pay)),
        "minimum_payments_50": int((cc_pay["amount"] == -50.0).sum()),
        "credit_spending_count": int(len(cc_spend)),
        "avg_payment": round(float(-cc_pay["amount"].mean()), 2) if len(cc_pay) else 0,
    }


def get_last_payment(merchant_contains: str) -> dict[str, Any]:
    """Дата та сума останнього платежу мерчанту."""
    df = load_transactions()
    sub = df[df["merchant"].str.contains(merchant_contains, case=False, na=False) & (df["amount"] < 0)]
    if sub.empty:
        return {"merchant_query": merchant_contains, "found": False}
    last = sub.sort_values("date").iloc[-1]
    return {
        "merchant_query": merchant_contains,
        "found": True,
        "merchant": last["merchant"],
        "date": last["date"].strftime("%Y-%m-%d %H:%M"),
        "amount": round(float(-last["amount"]), 2),
        "category": last["category"],
        "account": last["account"],
    }


# ----------------------------- tool schemas -----------------------------


PERIOD_HELP = (
    "Period string. Supported: 'last_week', 'this_week', 'last_month', 'this_month', "
    "'last_3_months', 'last_30_days', 'this_year', 'last_year', 'ytd', "
    "'YYYY-MM' (specific month), or 'YYYY-MM-DD..YYYY-MM-DD' (range). "
    "Current 'today' is 2025-11-30."
)

CATEGORY_HELP = (
    "Category. One of: coffee, groceries, restaurants, delivery, transport, entertainment, "
    "shopping, health, subscriptions, utilities, salary, credit_payment, travel. "
    "Or a list of these strings."
)


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "query_transactions",
        "description": (
            "Return individual transactions matching filter and a sum. Use when user asks for a list or "
            "exact transactions. Always prefer aggregate_spending when only a total is needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": PERIOD_HELP},
                "category": {"type": "string", "description": CATEGORY_HELP},
                "merchant_contains": {"type": "string", "description": "Substring of merchant name (case-insensitive)."},
                "account": {"type": "string", "enum": ["main_debit", "credit_card"]},
                "min_amount": {"type": "number", "description": "Filter abs(amount) >= this."},
                "max_amount": {"type": "number"},
                "hour_min": {"type": "integer", "minimum": 0, "maximum": 23},
                "hour_max": {"type": "integer", "minimum": 0, "maximum": 23},
                "recurring": {"type": "boolean"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "aggregate_spending",
        "description": (
            "Compute total spending, optionally grouped. Use for 'how much did I spend on X' and 'top categories'. "
            "Cheaper than query_transactions when only totals are needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": PERIOD_HELP},
                "category": {"type": "string", "description": CATEGORY_HELP},
                "merchant_contains": {"type": "string"},
                "group_by": {"type": "string", "enum": ["category", "merchant", "month", "weekday", "account"]},
            },
        },
    },
    {
        "name": "top_categories",
        "description": "Return top-N spending categories for a period.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": PERIOD_HELP, "default": "this_month"},
                "n": {"type": "integer", "default": 5},
            },
        },
    },
    {
        "name": "find_recurring",
        "description": (
            "List all recurring merchants (subscriptions/utilities) with last_seen and is_likely_forgotten flag "
            "(true when last payment was > 60 days ago). Use to answer questions about subscriptions and forgotten ones."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "min_months": {"type": "integer", "default": 2, "description": "Minimum months active to qualify."},
            },
        },
    },
    {
        "name": "detect_late_night_pattern",
        "description": (
            "Share of transactions after a given hour for given categories. Default: delivery+restaurants after 21:00. "
            "Useful for detecting impulse spending patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": PERIOD_HELP, "default": "last_3_months"},
                "categories": {"type": "array", "items": {"type": "string"}},
                "hour_threshold": {"type": "integer", "default": 21},
            },
        },
    },
    {
        "name": "compare_periods",
        "description": "Compare a metric between two periods (e.g., this_month vs last_month).",
        "input_schema": {
            "type": "object",
            "properties": {
                "metric": {"type": "string", "enum": ["total_spending", "transaction_count"], "default": "total_spending"},
                "period_a": {"type": "string", "description": PERIOD_HELP},
                "period_b": {"type": "string", "description": PERIOD_HELP},
                "category": {"type": "string", "description": CATEGORY_HELP},
            },
            "required": ["period_a", "period_b"],
        },
    },
    {
        "name": "project_month_close",
        "description": (
            "Project end-of-month cashflow: income - spent_so_far - avg_daily_spend*days_left. "
            "Use for 'will this month close in the plus' or 'will I run out'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "description": "YYYY-MM, defaults to current month."},
            },
        },
    },
    {
        "name": "credit_card_status",
        "description": "Credit card: total spent, total paid, count of minimum-only payments, last N months.",
        "input_schema": {
            "type": "object",
            "properties": {"months": {"type": "integer", "default": 6}},
        },
    },
    {
        "name": "get_last_payment",
        "description": "Find the date and amount of the last payment to a merchant (substring match).",
        "input_schema": {
            "type": "object",
            "properties": {"merchant_contains": {"type": "string"}},
            "required": ["merchant_contains"],
        },
    },
    {
        "name": "escalate_to_support",
        "description": (
            "Use this when user reports suspicious/unauthorized transactions or asks for fraud-related action "
            "(blocking cards, chargebacks). The agent CANNOT block cards itself. This returns the official "
            "escalation message and recommended user steps."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "enum": ["fraud_suspected", "card_lost", "dispute_charge", "out_of_scope"]},
                "transaction_hint": {"type": "string", "description": "Merchant/amount/date if user mentioned it."},
            },
            "required": ["reason"],
        },
    },
]


def escalate_to_support(reason: str, transaction_hint: str | None = None) -> dict[str, Any]:
    """Структуроване escalation повідомлення (не виконує реальних дій)."""
    base_steps = [
        "Заблокувати картку: Картки → ця карта → Заблокувати",
        "Написати в чат служби підтримки — у них є окрема процедура для disputed transactions",
    ]
    if reason == "fraud_suspected":
        return {
            "type": "escalation",
            "reason": reason,
            "message": "Імовірний fraud. Блокування картки та chargeback виходять за межі моїх можливостей.",
            "user_steps": base_steps,
            "transaction_hint": transaction_hint,
        }
    if reason == "card_lost":
        return {
            "type": "escalation",
            "reason": reason,
            "message": "Втрачену картку треба негайно заблокувати — це робить служба підтримки.",
            "user_steps": base_steps,
            "transaction_hint": transaction_hint,
        }
    if reason == "dispute_charge":
        return {
            "type": "escalation",
            "reason": reason,
            "message": "Оскарження транзакції оформлюється підтримкою через окрему процедуру.",
            "user_steps": [base_steps[1]],
            "transaction_hint": transaction_hint,
        }
    return {
        "type": "out_of_scope",
        "reason": reason,
        "message": "Цей запит поза межами того, що я можу. Доступні функції: статистика витрат, поради щодо економії, аналіз підписок.",
        "user_steps": [],
    }


TOOL_REGISTRY: dict[str, Any] = {
    "query_transactions": query_transactions,
    "aggregate_spending": aggregate_spending,
    "top_categories": top_categories,
    "find_recurring": find_recurring,
    "detect_late_night_pattern": detect_late_night_pattern,
    "compare_periods": compare_periods,
    "project_month_close": project_month_close,
    "credit_card_status": credit_card_status,
    "get_last_payment": get_last_payment,
    "escalate_to_support": escalate_to_support,
}


def run_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {name}"}
    try:
        return TOOL_REGISTRY[name](**(arguments or {}))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
