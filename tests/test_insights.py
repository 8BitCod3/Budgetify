from decimal import Decimal

import pytest

from src.insights import (
    assess_budget,
    generate_recommendations,
    identify_projected_shortfalls,
    summarize_expenses_by_category,
)


TRANSACTIONS = [
    {"type": "income", "amount": 1000.00},
    {"type": "expense", "category": "food", "amount": 25.00},
    {"type": "expense", "category": "food", "amount": 15.00},
    {"type": "expense", "category": "rent", "amount": 60.00},
]


def test_summarize_expenses_by_category_returns_amounts_and_percentages():
    assert summarize_expenses_by_category(TRANSACTIONS) == {
        "food": {"amount": Decimal("40.00"), "percentage": Decimal("40.00")},
        "rent": {"amount": Decimal("60.00"), "percentage": Decimal("60.00")},
    }


def test_empty_transactions_have_empty_expense_summary():
    assert summarize_expenses_by_category([]) == {}


def test_expense_summary_accepts_one_use_transaction_iterables():
    transactions = (transaction for transaction in TRANSACTIONS)
    assert summarize_expenses_by_category(transactions)["rent"]["percentage"] == Decimal(
        "60.00"
    )


def test_budget_assessment_distinguishes_within_approaching_exceeded_and_zero():
    assert assess_budget(TRANSACTIONS, Decimal("200"))["status"] == "within_budget"
    assert assess_budget(TRANSACTIONS, Decimal("110"))["status"] == "approaching"
    assert assess_budget(TRANSACTIONS, Decimal("100"))["status"] == "exceeded"
    zero = assess_budget(TRANSACTIONS, Decimal("0"))
    assert zero["status"] == "no_budget"
    assert zero["percentage_used"] == Decimal("0.00")


def test_budget_assessment_reports_actual_expenses_and_remaining_budget():
    assessment = assess_budget(TRANSACTIONS, Decimal("150"))
    assert assessment["expenses"] == Decimal("100.00")
    assert assessment["remaining"] == Decimal("50.00")
    assert assessment["percentage_used"] == Decimal("66.67")


def test_budget_assessment_rejects_invalid_threshold():
    with pytest.raises(ValueError, match="between 0 and 1"):
        assess_budget([], 100, Decimal("1.1"))


def test_identify_projected_shortfalls_reuses_chronological_projection():
    shortfalls = identify_projected_shortfalls(
        Decimal("0.00"),
        [
            {
                "date": "2026-11-05",
                "description": "Late income",
                "type": "income",
                "category": "grant",
                "amount": Decimal("500.00"),
            },
            {
                "date": "2026-11-01",
                "description": "Rent due",
                "type": "expense",
                "category": "rent",
                "amount": Decimal("200.00"),
            },
        ],
    )
    assert len(shortfalls) == 1
    assert shortfalls[0]["description"] == "Rent due"
    assert shortfalls[0]["projected_balance"] == Decimal("-200.00")
    assert shortfalls[0]["shortfall"] == Decimal("200.00")


def test_no_projected_shortfalls_returns_empty_list():
    assert identify_projected_shortfalls(100, []) == []


def test_recommendations_are_grounded_in_supplied_results():
    recommendations = generate_recommendations(
        summarize_expenses_by_category(TRANSACTIONS),
        assess_budget(TRANSACTIONS, 100),
        [],
    )
    assert any("exceeded" in recommendation for recommendation in recommendations)
    assert any("Rent" in recommendation for recommendation in recommendations)
    assert any("No projected cash-flow shortfalls" in recommendation for recommendation in recommendations)


def test_recommendations_handle_empty_data_and_zero_budget():
    recommendations = generate_recommendations(
        {},
        assess_budget([], 0),
        [],
    )
    assert any("Set a monthly budget" in recommendation for recommendation in recommendations)
    assert any("No expense transactions" in recommendation for recommendation in recommendations)
