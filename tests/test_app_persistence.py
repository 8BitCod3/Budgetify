from copy import deepcopy
from decimal import Decimal
from types import SimpleNamespace

import app


PERSONAL_EVENT = {
    "id": "personal-event-1",
    "date": "2026-11-02",
    "description": "Hypothetical rent",
    "type": "expense",
    "category": "rent",
    "amount": Decimal("700.00"),
}


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(name) from error

    def __setattr__(self, name, value):
        self[name] = value


def configure_persistent_session(monkeypatch, state):
    session_state = SessionState()
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))
    monkeypatch.setattr(
        app, "load_personal_state", lambda: (deepcopy(state), None)
    )
    monkeypatch.setattr(app, "save_personal_state", lambda saved_state: True)
    return session_state


def test_personal_events_restore_into_active_schedule_after_restart(monkeypatch):
    session_state = configure_persistent_session(
        monkeypatch,
        {
            "mode": "Personal Planning Mode",
            "personal_events": [PERSONAL_EVENT],
            "personal_initial_balance": Decimal("125.50"),
            "spending_limit": Decimal("900.00"),
        },
    )

    app.initialize_cash_flow_state()

    assert session_state["cash_flow_events"] == [PERSONAL_EVENT]
    assert session_state["cash_flow_events"] is not session_state[
        "personal_cash_flow_events"
    ]


def test_switching_from_restored_personal_mode_does_not_erase_events(monkeypatch):
    saved_states = []
    session_state = configure_persistent_session(
        monkeypatch,
        {
            "mode": "Personal Planning Mode",
            "personal_events": [PERSONAL_EVENT],
            "personal_initial_balance": Decimal("125.50"),
            "spending_limit": Decimal("900.00"),
        },
    )
    monkeypatch.setattr(
        app,
        "save_personal_state",
        lambda state: saved_states.append(deepcopy(state)) or True,
    )

    app.initialize_cash_flow_state()
    app.switch_cash_flow_mode("Demo Mode")

    assert session_state["personal_cash_flow_events"] == [PERSONAL_EVENT]
    assert saved_states[-1]["personal_events"] == [PERSONAL_EVENT]


def test_demo_mode_starts_with_fresh_fixture_events(monkeypatch):
    session_state = configure_persistent_session(
        monkeypatch,
        {
            "mode": "Demo Mode",
            "personal_events": [PERSONAL_EVENT],
            "personal_initial_balance": Decimal("125.50"),
            "spending_limit": Decimal("900.00"),
        },
    )

    app.initialize_cash_flow_state()

    assert session_state["cash_flow_events"] != [PERSONAL_EVENT]
    assert len(session_state["cash_flow_events"]) == len(app.SAMPLE_CASH_FLOW_EVENTS)


def test_demo_mode_persistence_keeps_personal_balance_when_widget_state_is_absent(
    monkeypatch,
):
    saved_states = []
    session_state = configure_persistent_session(
        monkeypatch,
        {
            "mode": "Personal Planning Mode",
            "personal_events": [PERSONAL_EVENT],
            "personal_initial_balance": Decimal("125.50"),
            "spending_limit": Decimal("900.00"),
        },
    )
    monkeypatch.setattr(
        app,
        "save_personal_state",
        lambda state: saved_states.append(deepcopy(state)) or True,
    )

    app.initialize_cash_flow_state()
    app.switch_cash_flow_mode("Demo Mode")
    session_state.pop("personal_initial_balance_input", None)
    app.persist_personal_state()

    assert saved_states[-1]["personal_initial_balance"] == 125.5


def test_initialization_recovers_missing_durable_balance_from_saved_state(
    monkeypatch,
):
    session_state = SessionState(
        {
            "persistent_state_initialized": True,
            "cash_flow_mode": "Demo Mode",
            "personal_cash_flow_events": [PERSONAL_EVENT],
            "spending_limit": 900.0,
        }
    )
    monkeypatch.setattr(app, "st", SimpleNamespace(session_state=session_state))
    monkeypatch.setattr(
        app,
        "load_personal_state",
        lambda: (
            {
                "mode": "Demo Mode",
                "personal_events": [PERSONAL_EVENT],
                "personal_initial_balance": Decimal("125.50"),
                "spending_limit": Decimal("900.00"),
            },
            None,
        ),
    )
    monkeypatch.setattr(app, "save_personal_state", lambda state: True)

    app.initialize_persistent_state()

    assert session_state["personal_initial_balance"] == 125.5
