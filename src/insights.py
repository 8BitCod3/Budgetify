"""Deterministic, explainable financial insights for Budgetify."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from numbers import Real
from typing import Iterable, Mapping

from src.finance import (
    CashFlowEvent,
    Transaction,
    budget_summary,
    project_cash_flow,
    spending_by_category,
    total_by_type,
)


Money = Decimal
CENT = Decimal("0.01")
PERCENT = Decimal("0.01")


def _money(value: object, name: str) -> Money:
    if isinstance(value, bool) or not isinstance(value, (Decimal, Real)):
        raise ValueError(f"{name} must be numeric")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not amount.is_finite():
        raise ValueError(f"{name} must be finite")
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def summarize_expenses_by_category(
    transactions: Iterable[Transaction],
) -> dict[str, dict[str, Money]]:
    """Return deterministic expense amounts and shares by category."""
    reusable_transactions = tuple(transactions)
    expense_totals = spending_by_category(reusable_transactions)
    total_expenses = _money(
        total_by_type(reusable_transactions, "expense"), "expenses"
    )
    summary: dict[str, dict[str, Money]] = {}
    for category, amount in expense_totals.items():
        category_amount = _money(amount, f"category '{category}' amount")
        percentage = (
            (category_amount / total_expenses * Decimal("100")).quantize(
                PERCENT, rounding=ROUND_HALF_UP
            )
            if total_expenses
            else Decimal("0.00")
        )
        summary[category] = {
            "amount": category_amount,
            "percentage": percentage,
        }
    return summary


def assess_budget(
    transactions: Iterable[Transaction],
    budget_limit: object,
    approaching_threshold: object = Decimal("0.80"),
) -> dict[str, object]:
    """Assess actual expenses against a supplied budget limit.

    ``approaching_threshold`` is the fraction of the limit at which the status
    changes from ``within_budget`` to ``approaching``.
    """
    limit = _money(budget_limit, "budget_limit")
    threshold = _money(approaching_threshold, "approaching_threshold")
    if limit < 0:
        raise ValueError("budget_limit cannot be negative")
    if threshold < 0 or threshold > 1:
        raise ValueError("approaching_threshold must be between 0 and 1")

    # budget_summary is the existing source of truth for expense-vs-limit math.
    existing_summary = budget_summary(transactions, float(limit))
    expenses = _money(existing_summary["expenses"], "expenses")
    remaining = limit - expenses
    if limit == 0:
        status = "no_budget"
        percentage_used = Decimal("0.00")
    else:
        percentage_used = (expenses / limit * Decimal("100")).quantize(
            PERCENT, rounding=ROUND_HALF_UP
        )
        status = (
            "exceeded"
            if expenses >= limit
            else "approaching"
            if expenses / limit >= threshold
            else "within_budget"
        )
    return {
        "limit": limit,
        "expenses": expenses,
        "remaining": remaining.quantize(CENT, rounding=ROUND_HALF_UP),
        "percentage_used": percentage_used,
        "status": status,
    }


def identify_projected_shortfalls(
    initial_balance: object,
    events: Iterable[CashFlowEvent],
) -> list[dict[str, object]]:
    """Return projected events whose balance is negative after the event."""
    projection = project_cash_flow(initial_balance, events)
    return [
        {
            "date": event["date"],
            "description": event["description"],
            "projected_balance": event["projected_balance"],
            "shortfall": event["shortfall"],
        }
        for event in projection
        if event["is_shortfall"]
    ]


def generate_recommendations(
    category_summary: Mapping[str, Mapping[str, Money]],
    budget_assessment: Mapping[str, object],
    shortfalls: Iterable[Mapping[str, object]],
) -> list[str]:
    """Generate concise recommendations from supplied computed results only."""
    recommendations: list[str] = []
    status = budget_assessment.get("status")
    if status == "no_budget":
        recommendations.append(
            "Set a monthly budget to compare actual expenses with a spending limit."
        )
    elif status == "exceeded":
        recommendations.append(
            "Spending has exceeded the supplied monthly budget; review upcoming "
            "expenses before adding discretionary spending."
        )
    elif status == "approaching":
        recommendations.append(
            "Spending is approaching the supplied monthly budget; review remaining "
            "planned expenses."
        )

    if category_summary:
        top_category, top_values = max(
            category_summary.items(),
            key=lambda item: item[1]["amount"],
        )
        if top_values["amount"] > 0:
            recommendations.append(
                f"{top_category.title()} is the largest recorded expense category "
                f"at {top_values['percentage']:.2f}% of expenses."
            )
    else:
        recommendations.append("No expense transactions are available to summarize.")

    shortfall_list = list(shortfalls)
    if shortfall_list:
        first = shortfall_list[0]
        recommendations.append(
            f"Plan for the projected shortfall after {first['description']}: "
            f"{first['shortfall']}."
        )
    else:
        recommendations.append("No projected cash-flow shortfalls were identified.")
    return recommendations
