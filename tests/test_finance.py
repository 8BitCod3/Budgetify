import pytest
from datetime import date
from decimal import Decimal

from app import (
    DEMO_INITIAL_BALANCE,
    categories_for_event_type,
    load_transactions,
    reset_events_for_mode,
)
from src.finance import (
    CASH_FLOW_CATEGORIES,
    budget_summary,
    net_balance,
    project_cash_flow,
    spending_by_category,
    total_by_type,
)


TRANSACTIONS = [
    {"type": "income", "amount": 1000.00},
    {"type": "expense", "category": "food", "amount": 12.50},
    {"type": "expense", "category": "transport", "amount": 40.00},
    {"type": "expense", "category": "food", "amount": 7.50},
]


def test_total_by_type():
    assert total_by_type(TRANSACTIONS, "expense") == 60.00


def test_net_balance():
    assert net_balance(TRANSACTIONS) == 940.00


def test_spending_by_category():
    assert spending_by_category(TRANSACTIONS) == {"food": 20.00, "transport": 40.00}


def test_empty_transactions():
    assert total_by_type([], "income") == 0.0
    assert net_balance([]) == 0.0
    assert spending_by_category([]) == {}


def test_net_balance_accepts_one_use_generator():
    transactions = (transaction for transaction in TRANSACTIONS)
    assert net_balance(transactions) == 940.00


@pytest.mark.parametrize(
    ("transaction", "message"),
    [
        ("not a mapping", "must be a mapping"),
        ({"amount": 10}, "type must be"),
        ({"type": "income"}, "missing required field 'amount'"),
        ({"type": "refund", "amount": 10}, "type must be"),
        ({"type": "expense", "amount": 10}, "expense category"),
        ({"type": "expense", "category": 5, "amount": 10}, "expense category"),
        ({"type": "income", "amount": "10"}, "amount must be numeric"),
        ({"type": "income", "amount": True}, "amount must be numeric"),
        ({"type": "income", "amount": -1}, "amount cannot be negative"),
    ],
)
def test_all_public_functions_reject_invalid_transactions(transaction, message):
    for function in (total_by_type, net_balance, spending_by_category):
        with pytest.raises(ValueError, match=message):
            if function is total_by_type:
                function([transaction], "income")
            else:
                function([transaction])


def test_unrelated_valid_transaction_type_is_rejected():
    with pytest.raises(ValueError, match="type must be"):
        total_by_type(
            [
                {"type": "income", "amount": 100},
                {"type": "refund", "amount": 10},
            ],
            "income",
        )


def test_budget_summary_with_zero_budget():
    summary = budget_summary(TRANSACTIONS, 0)
    assert summary == {
        "limit": 0.0,
        "expenses": 60.0,
        "remaining": -60.0,
        "percentage_used": 0.0,
    }


def test_budget_summary_with_spending_below_budget():
    summary = budget_summary(TRANSACTIONS, 100)
    assert summary == {
        "limit": 100.0,
        "expenses": 60.0,
        "remaining": 40.0,
        "percentage_used": 60.0,
    }


def test_budget_summary_with_spending_equal_to_budget():
    summary = budget_summary(TRANSACTIONS, 60)
    assert summary == {
        "limit": 60.0,
        "expenses": 60.0,
        "remaining": 0.0,
        "percentage_used": 100.0,
    }


def test_budget_summary_with_spending_above_budget():
    summary = budget_summary(TRANSACTIONS, 40)
    assert summary == {
        "limit": 40.0,
        "expenses": 60.0,
        "remaining": -20.0,
        "percentage_used": 150.0,
    }


def test_budget_summary_counts_expenses_not_income_or_initial_balance():
    transactions = [
        {"type": "income", "amount": 1000.00},
        {"type": "expense", "category": "food", "amount": 60.00},
    ]
    assert budget_summary(transactions, 100) == {
        "limit": 100.0,
        "expenses": 60.0,
        "remaining": 40.0,
        "percentage_used": 60.0,
    }


def test_budget_summary_rejects_missing_budget():
    with pytest.raises(ValueError, match="spending_limit must be numeric"):
        budget_summary([], None)


def test_project_cash_flow_orders_events_chronologically():
    projection = project_cash_flow(
        Decimal("100.00"),
        [
            {
                "date": "2026-02-10",
                "description": "Rent",
                "type": "expense",
                "category": "rent",
                "amount": Decimal("30.00"),
            },
            {
                "date": "2026-02-01",
                "description": "Scholarship",
                "type": "income",
                "category": "scholarship",
                "amount": Decimal("50.00"),
            },
        ],
    )
    assert [event["date"] for event in projection] == [
        date(2026, 2, 1),
        date(2026, 2, 10),
    ]
    assert [event["projected_balance"] for event in projection] == [
        Decimal("150.00"),
        Decimal("120.00"),
    ]


def test_project_cash_flow_preserves_same_date_event_order():
    projection = project_cash_flow(
        Decimal("100.00"),
        [
            {
                "date": "2026-02-01",
                "description": "Payment due",
                "type": "expense",
                "category": "rent",
                "amount": Decimal("150.00"),
            },
            {
                "date": "2026-02-01",
                "description": "Same-day support",
                "type": "income",
                "category": "family support",
                "amount": Decimal("200.00"),
            },
        ],
    )
    assert [event["description"] for event in projection] == [
        "Payment due",
        "Same-day support",
    ]
    assert [event["projected_balance"] for event in projection] == [
        Decimal("-50.00"),
        Decimal("150.00"),
    ]
    assert projection[0]["shortfall"] == Decimal("50.00")
    assert projection[1]["shortfall"] == Decimal("0")


def test_project_cash_flow_reports_shortfall_before_late_income_arrives():
    projection = project_cash_flow(
        Decimal("0.00"),
        [
            {
                "date": "2026-02-01",
                "description": "Rent due",
                "type": "expense",
                "category": "rent",
                "amount": Decimal("500.00"),
            },
            {
                "date": "2026-02-05",
                "description": "Scholarship payment",
                "type": "income",
                "category": "scholarship",
                "amount": Decimal("700.00"),
            },
        ],
    )
    assert projection[0]["projected_balance"] == Decimal("-500.00")
    assert projection[0]["is_shortfall"] is True
    assert projection[0]["shortfall"] == Decimal("500.00")
    assert projection[1]["projected_balance"] == Decimal("200.00")
    assert projection[1]["is_shortfall"] is False
    assert projection[1]["shortfall"] == Decimal("0")


def test_project_cash_flow_initial_balance_is_not_income():
    projection = project_cash_flow(
        Decimal("250.00"),
        [
            {
                "date": "2026-02-01",
                "description": "Food",
                "type": "expense",
                "category": "food",
                "amount": Decimal("50.00"),
            }
        ],
    )
    assert projection[0]["projected_balance"] == Decimal("200.00")


def test_project_cash_flow_uses_zero_initial_balance_for_income():
    projection = project_cash_flow(
        Decimal("0.00"),
        [
            {
                "date": "2026-02-01",
                "description": "Grant",
                "type": "income",
                "category": "grant",
                "amount": Decimal("1000.00"),
            }
        ],
    )
    assert projection[0]["projected_balance"] == Decimal("1000.00")


def test_demo_initial_balance_is_explicit():
    assert DEMO_INITIAL_BALANCE == 250.0


def test_project_cash_flow_handles_empty_schedule():
    assert project_cash_flow(Decimal("100.00"), []) == []


def test_project_cash_flow_preserves_stable_event_id():
    projection = project_cash_flow(
        Decimal("100.00"),
        [
            {
                "id": "event-a",
                "date": "2026-02-01",
                "description": "Same description",
                "type": "expense",
                "category": "food",
                "amount": Decimal("10.00"),
            },
            {
                "id": "event-b",
                "date": "2026-02-02",
                "description": "Same description",
                "type": "expense",
                "category": "food",
                "amount": Decimal("10.00"),
            },
        ],
    )
    assert [event["id"] for event in projection] == ["event-a", "event-b"]


def test_project_cash_flow_flags_negative_balance_and_shortfall():
    projection = project_cash_flow(
        Decimal("25.00"),
        [
            {
                "date": "2026-02-01",
                "description": "Housing",
                "type": "expense",
                "category": "rent",
                "amount": Decimal("40.00"),
            }
        ],
    )
    assert projection[0]["is_shortfall"] is True
    assert projection[0]["projected_balance"] == Decimal("-15.00")
    assert projection[0]["shortfall"] == Decimal("15.00")


@pytest.mark.parametrize(
    ("events", "message"),
    [
        ([{"date": "bad"}], "missing required field"),
        (
            [
                {
                    "date": "2026-02-01",
                    "description": "Food",
                    "type": "refund",
                    "category": "food",
                    "amount": 10,
                }
            ],
            "type must be",
        ),
        (
            [
                {
                    "date": "2026-02-01",
                    "description": "Food",
                    "type": "expense",
                    "category": "food",
                    "amount": -1,
                }
            ],
            "cannot be negative",
        ),
        (
            [
                {
                    "date": "not-a-date",
                    "description": "Food",
                    "type": "expense",
                    "category": "food",
                    "amount": 1,
                }
            ],
            "date must be",
        ),
        (
            [
                {
                    "date": "2026-02-01",
                    "description": "",
                    "type": "expense",
                    "category": "food",
                    "amount": 1,
                }
            ],
            "description must be",
        ),
    ],
)
def test_project_cash_flow_rejects_invalid_events(events, message):
    with pytest.raises(ValueError, match=message):
        project_cash_flow(100, events)


def test_grant_is_valid_income_category():
    projection = project_cash_flow(
        0,
        [
            {
                "date": "2026-02-01",
                "description": "Family support",
                "type": "income",
                "category": "grant",
                "amount": 100,
            }
        ],
    )
    assert projection[0]["projected_balance"] == Decimal("100")


def test_grant_is_rejected_for_expense_event():
    with pytest.raises(ValueError, match="not valid for expense"):
        project_cash_flow(
            100,
            [
                {
                    "date": "2026-02-01",
                    "description": "Invalid grant expense",
                    "type": "expense",
                    "category": "grant",
                    "amount": 10,
                }
            ],
        )


def test_tuition_refund_is_income_and_tuition_payment_is_expense():
    projection = project_cash_flow(
        0,
        [
            {
                "date": "2026-02-01",
                "description": "Tuition refund",
                "type": "income",
                "category": "tuition refund",
                "amount": 500,
            },
            {
                "date": "2026-02-02",
                "description": "Tuition payment",
                "type": "expense",
                "category": "tuition & university fees",
                "amount": 300,
            },
        ],
    )
    assert [event["projected_balance"] for event in projection] == [
        Decimal("500"),
        Decimal("200"),
    ]


def test_cash_flow_category_validation_is_case_insensitive_and_preserves_label():
    projection = project_cash_flow(
        100,
        [
            {
                "date": "2026-02-01",
                "description": "Rent",
                "type": "expense",
                "category": "Rent",
                "amount": 25,
            }
        ],
    )
    assert projection[0]["category"] == "Rent"


def test_cash_flow_categories_include_required_type_specific_options():
    assert {
        "stipend",
        "scholarship",
        "grant",
        "family support",
        "other income",
    }.issubset(CASH_FLOW_CATEGORIES["income"])
    assert {
        "tuition & university fees",
        "rent",
        "food",
        "bills",
        "transport",
        "study materials",
        "payments & fees",
        "other expenses",
    }.issubset(CASH_FLOW_CATEGORIES["expense"])
    assert "grant" not in CASH_FLOW_CATEGORIES["expense"]
    assert "education" not in CASH_FLOW_CATEGORIES["expense"]


def test_category_options_are_filtered_by_event_type():
    assert "grant" in categories_for_event_type("Income")
    assert "food" not in categories_for_event_type("Income")
    assert "food" in categories_for_event_type("Expense")
    assert "grant" not in categories_for_event_type("Expense")


def test_category_options_reject_unknown_event_type():
    with pytest.raises(ValueError, match="event_type must be"):
        categories_for_event_type("refund")


def test_existing_demo_categories_remain_available():
    assert "scholarship" in CASH_FLOW_CATEGORIES["income"]
    assert {"rent", "bills", "food", "transport", "study materials"}.issubset(
        CASH_FLOW_CATEGORIES["expense"]
    )


def test_sample_transactions_use_canonical_categories():
    transactions = load_transactions()
    assert set(transactions["category"]) == {
        "food",
        "other income",
        "scholarship",
        "transport",
        "rent",
        "study materials",
        "bills",
    }


def test_personal_planning_reset_is_empty():
    assert reset_events_for_mode("Personal Planning Mode") == []


def test_demo_reset_restores_demo_fixture_shape():
    demo_events = reset_events_for_mode("Demo Mode")
    assert len(demo_events) == 5
    assert all(event["id"] for event in demo_events)


def test_invalid_mode_reset_is_rejected():
    with pytest.raises(ValueError, match="Unsupported cash-flow mode"):
        reset_events_for_mode("Unknown Mode")
