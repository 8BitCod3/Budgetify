import json
from decimal import Decimal

import pytest

from src.storage import (
    StorageError,
    clear_personal_state,
    default_personal_state,
    load_personal_state,
    save_personal_state,
)


PERSONAL_EVENT = {
    "id": "personal-event-1",
    "date": "2026-11-02",
    "description": "Hypothetical rent",
    "type": "expense",
    "category": "rent",
    "amount": Decimal("700.00"),
}


def personal_state():
    return {
        "mode": "Personal Planning Mode",
        "personal_events": [PERSONAL_EVENT],
        "personal_initial_balance": Decimal("125.50"),
        "spending_limit": Decimal("900.00"),
    }


def test_save_and_reload_personal_state(tmp_path):
    path = tmp_path / ".budgetify" / "personal_state.json"

    assert save_personal_state(personal_state(), path) is True
    loaded, warning = load_personal_state(path)

    assert warning is None
    assert loaded["mode"] == "Personal Planning Mode"
    assert loaded["personal_events"][0]["id"] == "personal-event-1"
    assert loaded["personal_events"][0]["amount"] == Decimal("700.00")
    assert loaded["personal_initial_balance"] == Decimal("125.50")
    assert loaded["spending_limit"] == Decimal("900.00")


def test_missing_storage_file_returns_defaults(tmp_path):
    state, warning = load_personal_state(tmp_path / "missing.json")

    assert state == default_personal_state()
    assert warning is None


@pytest.mark.parametrize(
    "contents",
    [
        "{not-json",
        json.dumps({"schema_version": 99}),
    ],
)
def test_malformed_or_unsupported_storage_returns_defaults_without_overwrite(
    tmp_path, contents
):
    path = tmp_path / "personal_state.json"
    path.write_text(contents, encoding="utf-8")

    state, warning = load_personal_state(path)

    assert state == default_personal_state()
    assert warning is not None
    assert path.read_text(encoding="utf-8") == contents


def test_invalid_event_data_is_rejected_without_overwrite(tmp_path):
    path = tmp_path / "personal_state.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "settings": {
                    "mode": "Personal Planning Mode",
                    "personal_initial_balance": "0.00",
                    "spending_limit": "500.00",
                },
                "personal_events": [
                    {
                        **PERSONAL_EVENT,
                        "amount": "-1.00",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    state, warning = load_personal_state(path)

    assert state == default_personal_state()
    assert warning is not None


def test_unchanged_state_is_not_rewritten(tmp_path):
    path = tmp_path / "personal_state.json"
    assert save_personal_state(personal_state(), path) is True
    first_contents = path.read_text(encoding="utf-8")

    assert save_personal_state(personal_state(), path) is False
    assert path.read_text(encoding="utf-8") == first_contents


def test_atomic_save_failure_does_not_replace_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "personal_state.json"
    save_personal_state(personal_state(), path)
    original_contents = path.read_text(encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr("src.storage.os.replace", fail_replace)
    with pytest.raises(StorageError, match="could not be saved safely"):
        save_personal_state(
            {
                **personal_state(),
                "spending_limit": Decimal("1000.00"),
            },
            path,
        )

    assert path.read_text(encoding="utf-8") == original_contents


def test_clear_personal_state_does_not_affect_demo_fixtures(tmp_path):
    path = tmp_path / "personal_state.json"
    save_personal_state(personal_state(), path)

    clear_personal_state(path)

    assert not path.exists()
