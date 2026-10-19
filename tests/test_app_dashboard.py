import pandas as pd

from app import dashboard_transactions
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
        "amount": 1000.0,
        "type": "income",
    },
    {
        "id": "expense-1",
        "date": "2026-11-02",
        "description": "Personal rent",
        "category": "rent",
        "amount": 400.0,
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
