from decimal import Decimal

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
    assert context["total_expenses"] == "USD 40.00"
    assert "private detail" not in repr(context)
