"""Deterministic financial calculations used by Budgetify."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal, InvalidOperation
from numbers import Real
from typing import Iterable, Mapping, TypeAlias


Transaction: TypeAlias = Mapping[str, object]
CashFlowEvent: TypeAlias = Mapping[str, object]
VALID_TRANSACTION_TYPES = frozenset({"income", "expense"})
CASH_FLOW_CATEGORIES = {
    "income": (
        "stipend",
        "scholarship",
        "grant",
        "family support",
        "other income",
        "tuition refund",
        "salary",
    ),
    "expense": (
        "tuition & university fees",
        "rent",
        "food",
        "bills",
        "transport",
        "study materials",
        "payments & fees",
        "other expenses",
    ),
}


def _validate_transactions(
    transactions: Iterable[Transaction],
) -> tuple[Transaction, ...]:
    """Materialize and validate transactions once for safe iterable reuse."""
    if isinstance(transactions, (str, bytes)) or not isinstance(transactions, Iterable):
        raise ValueError("transactions must be an iterable of mappings")

    validated: list[Transaction] = []
    for index, transaction in enumerate(transactions):
        if not isinstance(transaction, Mapping):
            raise ValueError(f"transaction {index} must be a mapping")

        transaction_type = transaction.get("type")
        if transaction_type not in VALID_TRANSACTION_TYPES:
            raise ValueError(
                f"transaction {index} type must be 'income' or 'expense'"
            )

        if "amount" not in transaction:
            raise ValueError(f"transaction {index} is missing required field 'amount'")
        amount = transaction["amount"]
        if isinstance(amount, bool) or not isinstance(amount, Real):
            raise ValueError(f"transaction {index} amount must be numeric")
        if not math.isfinite(float(amount)):
            raise ValueError(f"transaction {index} amount must be finite")
        if amount < 0:
            raise ValueError(f"transaction {index} amount cannot be negative")

        if transaction_type == "expense":
            category = transaction.get("category")
            if not isinstance(category, str) or not category.strip():
                raise ValueError(
                    f"transaction {index} expense category must be a non-empty string"
                )

        validated.append(transaction)
    return tuple(validated)


def total_by_type(
    transactions: Iterable[Transaction], transaction_type: str
) -> float:
    """Return the total amount for transactions matching ``transaction_type``."""
    if not isinstance(transaction_type, str) or not transaction_type:
        raise ValueError("transaction_type must be a non-empty string")

    validated_transactions = _validate_transactions(transactions)
    total = 0.0
    for transaction in validated_transactions:
        if transaction.get("type") != transaction_type:
            continue
        total += float(transaction["amount"])
    return round(total, 2)


def net_balance(transactions: Iterable[Transaction]) -> float:
    """Return income minus expenses for a transaction collection."""
    validated_transactions = _validate_transactions(transactions)
    return round(
        total_by_type(validated_transactions, "income")
        - total_by_type(validated_transactions, "expense"),
        2,
    )


def spending_by_category(
    transactions: Iterable[Transaction],
) -> dict[str, float]:
    """Return expense totals grouped by category in deterministic key order."""
    validated_transactions = _validate_transactions(transactions)
    totals: dict[str, float] = {}
    for transaction in validated_transactions:
        if transaction.get("type") != "expense":
            continue
        category = transaction["category"]
        amount = transaction["amount"]
        totals[category] = round(totals.get(category, 0.0) + float(amount), 2)
    return dict(sorted(totals.items()))


def budget_summary(
    transactions: Iterable[Transaction], spending_limit: Real
) -> dict[str, float]:
    """Return deterministic sample-period budget figures."""
    if isinstance(spending_limit, bool) or not isinstance(spending_limit, Real):
        raise ValueError("spending_limit must be numeric")
    if not math.isfinite(float(spending_limit)):
        raise ValueError("spending_limit must be finite")
    if spending_limit < 0:
        raise ValueError("spending_limit cannot be negative")

    expenses = total_by_type(transactions, "expense")
    limit = round(float(spending_limit), 2)
    remaining = round(limit - expenses, 2)
    percentage_used = round((expenses / limit) * 100, 2) if limit else 0.0
    return {
        "limit": limit,
        "expenses": expenses,
        "remaining": remaining,
        "percentage_used": percentage_used,
    }


def _decimal_amount(value: object, field_name: str, index: int) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (Decimal, Real)):
        raise ValueError(f"event {index} {field_name} must be numeric")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"event {index} {field_name} must be numeric") from exc
    if not amount.is_finite():
        raise ValueError(f"event {index} {field_name} must be finite")
    if amount < 0:
        raise ValueError(f"event {index} {field_name} cannot be negative")
    return amount


def _event_date(value: object, index: int) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(
                f"event {index} date must be an ISO date (YYYY-MM-DD)"
            ) from exc
    raise ValueError(f"event {index} date must be an ISO date (YYYY-MM-DD)")


def project_cash_flow(
    initial_balance: object, events: Iterable[CashFlowEvent]
) -> list[dict[str, object]]:
    """Project a dated event schedule and identify negative balances.

    Events are sorted by date, with original order preserved for same-day events.
    Returned amounts and balances are ``Decimal`` values.
    """
    balance = _decimal_amount(initial_balance, "initial_balance", 0)
    if isinstance(events, (str, bytes)) or not isinstance(events, Iterable):
        raise ValueError("events must be an iterable of mappings")

    validated_events: list[dict[str, object]] = []
    for index, event in enumerate(events):
        if not isinstance(event, Mapping):
            raise ValueError(f"event {index} must be a mapping")
        for field in ("date", "description", "type", "category", "amount"):
            if field not in event:
                raise ValueError(f"event {index} is missing required field '{field}'")

        event_date = _event_date(event["date"], index)
        description = event["description"]
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"event {index} description must be a non-empty string")
        event_type = event["type"]
        if event_type not in VALID_TRANSACTION_TYPES:
            raise ValueError(
                f"event {index} type must be 'income' or 'expense'"
            )
        category = event["category"]
        if not isinstance(category, str) or not category.strip():
            raise ValueError(f"event {index} category must be a non-empty string")
        category_key = category.strip().lower()
        if category_key not in CASH_FLOW_CATEGORIES[event_type]:
            raise ValueError(
                f"event {index} category '{category}' is not valid for {event_type}"
            )
        amount = _decimal_amount(event["amount"], "amount", index)
        normalized_event = {
            "date": event_date,
            "description": description.strip(),
            "type": event_type,
            "category": category.strip(),
            "amount": amount,
            "_index": index,
        }
        if "id" in event:
            normalized_event["id"] = event["id"]
        validated_events.append(normalized_event)

    validated_events.sort(key=lambda event: (event["date"], event["_index"]))
    projection: list[dict[str, object]] = []
    for event in validated_events:
        signed_amount = event["amount"]
        if event["type"] == "expense":
            signed_amount = -signed_amount
        balance += signed_amount
        shortfall = max(-balance, Decimal("0"))
        projected_event = {
            "date": event["date"],
            "description": event["description"],
            "type": event["type"],
            "category": event["category"],
            "amount": event["amount"],
            "projected_balance": balance,
            "is_shortfall": balance < 0,
            "shortfall": shortfall,
        }
        if "id" in event:
            projected_event["id"] = event["id"]
        projection.append(projected_event)
    return projection
