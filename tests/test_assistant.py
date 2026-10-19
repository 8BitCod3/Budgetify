from decimal import Decimal
from datetime import date

import pytest

from src.assistant import (
    AssistantError,
    ask_budgetify,
    build_context,
    build_prompt,
)


TRANSACTIONS = [
    {"type": "income", "amount": 1000.0, "description": "private detail"},
    {"type": "expense", "category": "food", "amount": 40.0, "description": "private detail"},
]
EVENTS = [
    {
        "date": "2026-11-01",
        "description": "private event detail",
        "type": "expense",
        "category": "rent",
        "amount": Decimal("100.00"),
    }
]


def test_context_contains_aggregates_but_not_raw_descriptions():
    context = build_context(TRANSACTIONS, 100, 250, EVENTS)
    rendered = repr(context)
    assert context["total_income"] == "1000.00"
    assert context["total_expenses"] == "40.00"
    assert "private detail" not in rendered
    assert "private event detail" not in rendered


def test_prompt_states_scopes_and_safety_limits():
    prompt = build_prompt("Can I afford rent?", {"cash_flow_scope": "active schedule"})
    assert "sample CSV transaction aggregates" in prompt
    assert "active schedule" in prompt
    assert "Do not invent amounts" in prompt
    assert "1 to 3 sentences" in prompt
    assert "plain, natural, helpful language" in prompt
    assert "under 60 words" in prompt
    assert "qualified yes or no" in prompt
    assert "projected ending balance" in prompt
    assert "timing or other information is insufficient" in prompt
    assert "opening balance before the earliest" in prompt
    with pytest.raises(AssistantError, match="under 2,000"):
        build_prompt("x" * 2001, {})


def test_empty_question_is_rejected_before_api_call():
    with pytest.raises(AssistantError, match="enter a question"):
        build_prompt("   ", {})


class FakeResponse:
    text = "  A concise answer.  "


class FakeModels:
    def __init__(self):
        self.model = None
        self.contents = None

    def generate_content(self, *, model, contents):
        self.model = model
        self.contents = contents
        return FakeResponse()


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


def test_mocked_gemini_call_uses_configured_model_and_returns_text():
    client = FakeClient()
    answer = ask_budgetify(
        "What is my budget status?",
        {"budget": {"status": "within_budget"}},
        secrets={"GEMINI_API_KEY": "test-key"},
        model="test-model",
        client=client,
    )
    assert answer == "A concise answer."
    assert client.models.model == "test-model"
    assert "within_budget" in client.models.contents


def test_missing_key_is_user_safe(monkeypatch):
    monkeypatch.setattr("src.assistant._load_local_env", lambda path: None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(AssistantError, match="GEMINI_API_KEY"):
        ask_budgetify("What happened?", {}, secrets={})


def test_api_failure_redacts_key():
    class FailingModels:
        def generate_content(self, **kwargs):
            raise RuntimeError("request failed for test-secret")

    class FailingClient:
        models = FailingModels()

    with pytest.raises(AssistantError) as error:
        ask_budgetify(
            "What happened?",
            {},
            secrets={"GEMINI_API_KEY": "test-secret"},
            client=FailingClient(),
        )
    assert "test-secret" not in str(error.value)
    assert "Gemini could not answer" in str(error.value)


def test_context_accepts_personal_scope_and_currency():
    context = build_context(
        TRANSACTIONS,
        100,
        250,
        EVENTS,
        transaction_scope="Scheduled personal cash-flow aggregates",
        cash_flow_scope="Personal Planning Mode schedule",
        currency="USD",
    )
    assert context["transaction_scope"] == "Scheduled personal cash-flow aggregates"
    assert context["cash_flow_scope"] == "Personal Planning Mode schedule"
    assert (
        context["budget_scope"]
        == "all supplied active entries; no date-bounded reporting period"
    )
    assert context["total_expenses"] == "USD 40.00"
    assert "private detail" not in repr(context)


def test_affordability_question_receives_projected_balance_and_timing_context():
    context = build_context(
        [],
        1000,
        250,
        [
            {
                "date": "2026-11-01",
                "description": "scheduled income",
                "type": "income",
                "category": "grant",
                "amount": Decimal("430.00"),
            }
        ],
        currency="USD",
    )
    client = FakeClient()
    ask_budgetify(
        "Can I afford another USD 250 expense at the end of the month?",
        context,
        secrets={"GEMINI_API_KEY": "test-key"},
        client=client,
    )
    assert "USD 680.00" in client.models.contents
    assert "end of the month" in client.models.contents
    assert "Do not invent amounts" in client.models.contents


def test_context_exposes_historical_and_upcoming_counts_without_descriptions():
    context = build_context(
        [],
        1000,
        250,
        [
            {
                "date": "2020-01-01",
                "description": "historical private detail",
                "type": "expense",
                "category": "food",
                "amount": Decimal("25.00"),
            },
            {
                "date": "2099-01-01",
                "description": "future private detail",
                "type": "expense",
                "category": "rent",
                "amount": Decimal("100.00"),
            },
        ],
    )
    assert context["cash_flow_historical_event_count"] == 1
    assert context["cash_flow_upcoming_event_count"] == 1
    assert (
        context["cash_flow_balance_semantics"]
        == "initial balance is the opening balance before the earliest supplied event"
    )
    assert "private detail" not in repr(context)


def test_context_calculates_today_and_inclusive_requested_range_spending():
    context = build_context(
        [
            {"date": "2026-10-01", "type": "expense", "category": "food", "amount": 10},
            {"date": "2026-10-20", "type": "expense", "category": "rent", "amount": 20},
            {"date": "2026-10-21", "type": "expense", "category": "bills", "amount": 30},
            {"date": "2026-10-20", "type": "income", "amount": 500},
        ],
        1000,
        0,
        [],
        currency="USD",
        question="How much from 2026-10-01 to 2026-10-20?",
    )
    assert context["requested_date_range_spending"]["expenses"] == "USD 30.00"
    assert context["spending_through_today"] == "USD 30.00"


def test_context_calculates_requested_date_balance_without_later_events():
    context = build_context(
        [],
        1000,
        1000,
        [
            {
                "date": "2026-10-24",
                "description": "private event detail",
                "type": "expense",
                "category": "food",
                "amount": Decimal("300.00"),
            },
            {
                "date": "2026-10-31",
                "description": "private event detail",
                "type": "expense",
                "category": "bills",
                "amount": Decimal("90.00"),
            },
            {
                "date": "2026-11-01",
                "description": "private event detail",
                "type": "income",
                "category": "grant",
                "amount": Decimal("500.00"),
            },
        ],
        currency="USD",
        question="What is my projected balance on 2026-10-31?",
    )
    assert context["cash_flow_requested_date"] == "2026-10-31"
    assert context["cash_flow_projected_balance_at_requested_date"] == "USD 610.00"
    assert "private event detail" not in repr(context)


def test_context_resolves_natural_language_requested_date_from_schedule_year():
    context = build_context(
        [],
        1000,
        1000,
        [
            {
                "date": "2026-10-24",
                "description": "private event detail",
                "type": "expense",
                "category": "food",
                "amount": Decimal("300.00"),
            },
            {
                "date": "2026-10-31",
                "description": "private event detail",
                "type": "expense",
                "category": "bills",
                "amount": Decimal("90.00"),
            },
            {
                "date": "2026-11-01",
                "description": "private event detail",
                "type": "income",
                "category": "grant",
                "amount": Decimal("500.00"),
            },
        ],
        currency="USD",
        question=(
            "What is my projected balance on October 31 after all scheduled "
            "income and expenses?"
        ),
    )
    assert context["cash_flow_requested_date"] == "2026-10-31"
    assert context["cash_flow_projected_balance_at_requested_date"] == "USD 610.00"
    assert "private event detail" not in repr(context)


def test_context_leaves_natural_language_date_unresolved_when_schedule_year_is_ambiguous():
    context = build_context(
        [],
        1000,
        1000,
        [
            {
                "date": "2026-10-31",
                "description": "private event detail",
                "type": "expense",
                "category": "food",
                "amount": Decimal("100.00"),
            },
            {
                "date": "2027-10-31",
                "description": "private event detail",
                "type": "expense",
                "category": "food",
                "amount": Decimal("200.00"),
            },
        ],
        currency="USD",
        question="What is my projected balance on October 31?",
    )
    assert context["cash_flow_requested_date"] is None
    assert context["cash_flow_projected_balance_at_requested_date"] is None


def test_context_distinguishes_spending_today_from_spending_through_today(
    monkeypatch,
):
    class FixedDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 10, 20)

    monkeypatch.setattr("src.assistant.date", FixedDate)
    context = build_context(
        [
            {
                "date": "2026-10-01",
                "type": "expense",
                "category": "food",
                "amount": 245,
            },
            {
                "date": "2026-10-20",
                "type": "expense",
                "category": "food",
                "amount": 65,
            },
            {
                "date": "2026-10-24",
                "type": "expense",
                "category": "food",
                "amount": 300,
            },
        ],
        1000,
        0,
        [],
        currency="USD",
        question="How much have I spent so far today?",
    )
    assert context["spending_today"] == "USD 65.00"
    assert context["spending_through_today"] == "USD 310.00"
