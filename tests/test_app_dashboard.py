import pandas as pd
from datetime import date, timedelta
from decimal import Decimal

from app import (
    cash_flow_display_table,
    dashboard_transactions,
    maximum_projected_shortfall,
    month_end_projection,
    todays_transactions,
    todays_expenses,
)
from src.finance import budget_summary, net_balance, total_by_type


SAMPLE = pd.DataFrame(
    [
        {
            "date": "2026-01-01",
            "description": "Sample income",
            "category": "stipend",
            "amount": 500.0,
            "currency": "USD",
            "type": "income",
        }
    ]
)


PERSONAL_EVENTS = [
    {
        "id": "income-1",
        "date": "2026-11-01",
        "description": "Personal grant",
        "category": "grant",
        "amount": Decimal("1000.00"),
        "type": "income",
    },
    {
        "id": "expense-1",
        "date": "2026-11-02",
        "description": "Personal rent",
        "category": "rent",
        "amount": Decimal("400.00"),
        "type": "expense",
    },
]


def test_demo_dashboard_uses_sample_transactions():
    active, scope, net_label = dashboard_transactions(
        SAMPLE, "Demo Mode", PERSONAL_EVENTS, "USD"
    )
    assert active.to_dict(orient="records") == SAMPLE.to_dict(orient="records")
    assert scope == "Recorded sample transactions"
    assert net_label == "Net balance"


def test_personal_dashboard_uses_only_scheduled_personal_entries():
    active, scope, net_label = dashboard_transactions(
        SAMPLE, "Personal Planning Mode", PERSONAL_EVENTS, "USD"
    )
    assert len(active) == 2
    assert active["description"].tolist() == ["Personal grant", "Personal rent"]
    assert active["type"].tolist() == ["income", "expense"]
    assert active["amount"].tolist() == [1000.0, 400.0]
    assert scope == "Scheduled personal cash-flow entries"
    assert net_label == "Net scheduled cash flow"


def test_personal_starting_balance_is_not_a_dashboard_income_entry():
    active, _, _ = dashboard_transactions(
        SAMPLE, "Personal Planning Mode", PERSONAL_EVENTS, "USD"
    )
    assert "starting balance" not in active["description"].str.lower().tolist()
    records = active.to_dict(orient="records")
    assert total_by_type(records, "income") == 1000.0
    assert net_balance(records) == 600.0


def test_personal_budget_uses_personal_scheduled_expenses_only():
    active, _, _ = dashboard_transactions(
        SAMPLE, "Personal Planning Mode", PERSONAL_EVENTS, "USD"
    )
    budget = budget_summary(active.to_dict(orient="records"), 500.0)
    assert budget["expenses"] == 400.0
    assert budget["remaining"] == 100.0


def test_personal_dashboard_table_has_no_timing_column():
    active, _, _ = dashboard_transactions(
        SAMPLE, "Personal Planning Mode", PERSONAL_EVENTS, "USD"
    )
    assert "timing" not in active.columns


def test_projected_cash_flow_table_hides_internal_event_id():
    table = cash_flow_display_table(
        [
            {
                **PERSONAL_EVENTS[1],
                "projected_balance": Decimal("100.00"),
                "is_shortfall": False,
                "shortfall": Decimal("0.00"),
            }
        ],
        "USD",
    )
    assert "id" not in table.columns
    assert "ID" not in table.columns
    assert table["Description"].tolist() == ["Personal rent"]


def test_todays_expenses_filters_by_date_and_type():
    today = date(2026, 10, 20)
    events = [
        {
            **PERSONAL_EVENTS[0],
            "date": today.isoformat(),
        },
        {
            **PERSONAL_EVENTS[1],
            "date": today.isoformat(),
        },
        {
            **PERSONAL_EVENTS[0],
            "id": "future-income",
            "date": (today + timedelta(days=1)).isoformat(),
        },
        {
            **PERSONAL_EVENTS[1],
            "id": "historical-expense",
            "date": (today - timedelta(days=1)).isoformat(),
        },
    ]
    table, total = todays_expenses(events, "USD", today)
    assert table["Description"].tolist() == ["Personal rent"]
    assert table["Type"].tolist() == ["expense"]
    assert total == 400.0


def test_todays_expenses_empty_result_has_zero_total():
    table, total = todays_expenses(
        [
            {
                **PERSONAL_EVENTS[0],
                "date": (date.today() + timedelta(days=1)).isoformat(),
            }
        ],
        "USD",
        date.today(),
    )
    assert table.empty
    assert list(table.columns) == [
        "Date",
        "Description",
        "Category",
        "Amount",
        "Currency",
        "Type",
    ]
    assert total == 0.0


def test_todays_transactions_returns_independent_income_and_expense_totals():
    today = date(2026, 10, 20)
    table, income_total, expense_total = todays_transactions(
        [
            {**PERSONAL_EVENTS[0], "date": today.isoformat()},
            {**PERSONAL_EVENTS[1], "date": today.isoformat()},
            {
                **PERSONAL_EVENTS[0],
                "id": "future-income",
                "date": "2026-10-21",
            },
        ],
        "USD",
        today,
    )
    assert len(table) == 2
    assert income_total == 1000.0
    assert expense_total == 400.0


def test_todays_transactions_returns_zero_for_missing_transaction_types():
    today = date(2026, 10, 20)
    table, income_total, expense_total = todays_transactions(
        [{**PERSONAL_EVENTS[1], "date": today.isoformat()}],
        "USD",
        today,
    )
    assert not table.empty
    assert income_total == 0.0
    assert expense_total == 400.0

    empty_table, empty_income, empty_expenses = todays_transactions(
        [{**PERSONAL_EVENTS[0], "date": "2026-10-21"}],
        "USD",
        today,
    )
    assert empty_table.empty
    assert empty_income == 0.0
    assert empty_expenses == 0.0


def test_month_end_projection_uses_events_through_current_month_end():
    month_end, balance = month_end_projection(
        250,
        [
            {
                **PERSONAL_EVENTS[1],
                "date": "2026-10-25",
            },
            {
                **PERSONAL_EVENTS[0],
                "date": "2026-11-01",
            },
        ],
        date(2026, 10, 20),
    )
    assert month_end == date(2026, 10, 31)
    assert balance == Decimal("-150.00")


def test_maximum_projected_shortfall_survives_later_income():
    shortfall = maximum_projected_shortfall(
        0,
        [
            {
                **PERSONAL_EVENTS[1],
                "date": "2026-10-21",
            },
            {
                **PERSONAL_EVENTS[0],
                "date": "2026-10-22",
            },
        ],
    )
    assert shortfall == Decimal("400.00")


def test_maximum_projected_shortfall_is_zero_when_balance_stays_nonnegative():
    assert maximum_projected_shortfall(500, PERSONAL_EVENTS) == Decimal("0.00")
