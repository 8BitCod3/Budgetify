"""Secure, minimally scoped Gemini assistant integration for Budgetify."""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.finance import (
    CashFlowEvent,
    Transaction,
    net_balance,
    project_cash_flow,
    total_by_type,
)
from src.insights import (
    assess_budget,
    identify_projected_shortfalls,
    summarize_expenses_by_category,
)


DEFAULT_MODEL = "gemini-3.5-flash-lite"
MAX_QUESTION_LENGTH = 2000
MAX_RESPONSE_LENGTH = 4000
DATE_RANGE_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b.*?\b(\d{4}-\d{2}-\d{2})\b")


class AssistantError(Exception):
    """An expected, user-safe assistant failure."""


def _load_local_env(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _api_key(secrets: Mapping[str, Any] | None = None) -> str:
    _load_local_env(Path(__file__).resolve().parents[1] / ".env")
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    if secrets is not None:
        secret_value = secrets.get("GEMINI_API_KEY", "")
        if isinstance(secret_value, str) and secret_value.strip():
            return secret_value.strip()
    raise AssistantError(
        "Ask Budgetify is unavailable because GEMINI_API_KEY is not configured."
    )


def _money(value: object, currency: str = "") -> str:
    formatted = f"{value:.2f}"
    return f"{currency} {formatted}" if currency else formatted


def _expense_total(
    transactions: Iterable[Transaction],
    start: date | None = None,
    end: date | None = None,
) -> object:
    total = 0.0
    for transaction in transactions:
        if transaction.get("type") != "expense":
            continue
        if "date" not in transaction:
            if start is not None or end is not None:
                continue
            total += float(transaction["amount"])
            continue
        transaction_date = date.fromisoformat(str(transaction["date"]))
        if start is not None and transaction_date < start:
            continue
        if end is not None and transaction_date > end:
            continue
        total += float(transaction["amount"])
    return round(total, 2)


def build_context(
    transactions: Iterable[Transaction],
    budget_limit: object,
    initial_balance: object,
    events: Iterable[CashFlowEvent],
    *,
    transaction_scope: str = "sample CSV transaction aggregates",
    cash_flow_scope: str = "active selected-mode scheduled cash-flow aggregates",
    budget_scope: str = "all supplied active entries; no date-bounded reporting period",
    currency: str = "",
    question: str = "",
) -> dict[str, object]:
    """Build aggregate facts only; raw records and descriptions are excluded."""
    transaction_records = tuple(transactions)
    event_records = tuple(events)
    category_summary = summarize_expenses_by_category(transaction_records)
    budget = assess_budget(transaction_records, budget_limit)
    projection = project_cash_flow(initial_balance, event_records)
    shortfalls = identify_projected_shortfalls(initial_balance, event_records)
    today = date.today()
    requested_range = DATE_RANGE_PATTERN.search(question)
    range_summary = None
    if requested_range:
        start = date.fromisoformat(requested_range.group(1))
        end = date.fromisoformat(requested_range.group(2))
        if start > end:
            start, end = end, start
        range_summary = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "expenses": _money(
                _expense_total(transaction_records, start, end), currency
            ),
        }
    return {
        "transaction_scope": transaction_scope,
        "cash_flow_scope": cash_flow_scope,
        "budget_scope": budget_scope,
        "transaction_count": len(transaction_records),
        "total_income": _money(
            total_by_type(transaction_records, "income"), currency
        ),
        "total_expenses": _money(
            total_by_type(transaction_records, "expense"), currency
        ),
        "net_balance": _money(net_balance(transaction_records), currency),
        "expense_categories": {
            category: {
                "amount": _money(values["amount"], currency),
                "percentage": _money(values["percentage"]),
            }
            for category, values in category_summary.items()
        },
        "budget": {
            "limit": _money(budget["limit"], currency),
            "expenses": _money(budget["expenses"], currency),
            "remaining": _money(budget["remaining"], currency),
            "percentage_used": _money(budget["percentage_used"]),
            "status": budget["status"],
        },
        "spending_through_today": _money(
            _expense_total(transaction_records, end=today), currency
        ),
        "requested_date_range_spending": range_summary,
        "cash_flow_event_count": len(event_records),
        "cash_flow_historical_event_count": sum(
            1
            for event in event_records
            if str(event["date"]) < today.isoformat()
        ),
        "cash_flow_upcoming_event_count": sum(
            1
            for event in event_records
            if str(event["date"]) >= today.isoformat()
        ),
        "cash_flow_balance_semantics": (
            "initial balance is the opening balance before the earliest supplied event"
        ),
        "cash_flow_initial_balance": _money(initial_balance, currency),
        "cash_flow_projected_ending_balance": (
            _money(projection[-1]["projected_balance"], currency)
            if projection
            else _money(initial_balance, currency)
        ),
        "cash_flow_shortfall_count": len(shortfalls),
        "cash_flow_total_shortfall": _money(
            sum((item["shortfall"] for item in shortfalls), start=0),
            currency,
        ),
        "cash_flow_earliest_shortfall_date": (
            shortfalls[0]["date"] if shortfalls else None
        ),
    }


def build_prompt(question: str, context: Mapping[str, object]) -> str:
    """Construct a constrained prompt from aggregate facts and the user question."""
    cleaned_question = " ".join(question.split())
    if not cleaned_question:
        raise AssistantError("Please enter a question for Ask Budgetify.")
    if len(cleaned_question) > MAX_QUESTION_LENGTH:
        raise AssistantError("Please keep the question under 2,000 characters.")
    return (
        "You are Ask Budgetify, a concise budgeting explainer. "
        "Use only the supplied aggregate facts and answer the user's question. "
        "Do not invent amounts, transactions, categories, dates, or trends. "
        "If the facts are insufficient, say what is missing. "
        "Distinguish sample CSV transaction aggregates from the active scheduled "
        "cash-flow aggregates. Do not claim to be a financial adviser or guarantee "
        "that an expense is affordable. State relevant assumptions only when they "
        "materially affect the answer. "
        "Answer the exact question in the first sentence. Default to 1 to 3 "
        "sentences, keep them short, and preferably stay under 60 words. Use plain, "
        "natural, helpful "
        "language and only the numbers needed. "
        "For an affordability question, give a qualified yes or no only when the "
        "supplied projection and timing support it. If the proposed expense clearly "
        "occurs after the existing scheduled events, calculate the resulting balance "
        "from the projected ending balance; otherwise briefly say the timing or "
        "other information is insufficient. Mention a budget overrun or upcoming "
        "cash-flow risk in one short phrase when relevant. Give at most one "
        "practical next step. Avoid generic disclaimers, "
        "Treat the supplied initial balance as an opening balance before the earliest "
        "supplied event; do not double-count historical events already reflected in "
        "a current balance. The budget figures cover the stated budget scope only. "
        "repeated headings, and lengthy assumption lists unless a limitation "
        "materially affects the answer. "
        "Return plain text only; never return executable code or HTML.\n\n"
        f"Aggregate facts:\n{context}\n\n"
        f"User question:\n{cleaned_question}"
    )


def ask_budgetify(
    question: str,
    context: Mapping[str, object],
    *,
    secrets: Mapping[str, Any] | None = None,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    """Ask Gemini using only a pre-built aggregate context."""
    prompt = build_prompt(question, context)
    api_key = _api_key(secrets)
    selected_model = (
        model or os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    )
    try:
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=selected_model,
            contents=prompt,
        )
        text = " ".join((response.text or "").split())
    except Exception as error:
        message = " ".join(str(error).lower().split())
        if any(term in message for term in ("quota", "rate", "resource exhausted")):
            failure = "Gemini quota may be exhausted."
        elif any(term in message for term in ("401", "403", "api key", "permission")):
            failure = "Gemini authentication or permission failed."
        else:
            failure = "Gemini network or service request failed."
        raise AssistantError(
            f"Gemini could not answer right now: {failure}"
        ) from error
    if not text:
        raise AssistantError("Gemini returned an empty response.")
    return text[:MAX_RESPONSE_LENGTH]
