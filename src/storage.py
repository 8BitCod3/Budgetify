"""Safe local persistence for Budgetify personal planning state."""

from __future__ import annotations

import json
import os
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

from src.finance import project_cash_flow


SCHEMA_VERSION = 1
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_DIRECTORY = PROJECT_ROOT / ".budgetify"
STORAGE_PATH = STORAGE_DIRECTORY / "personal_state.json"
DEFAULT_MODE = "Demo Mode"
DEFAULT_PERSONAL_INITIAL_BALANCE = Decimal("0.00")
DEFAULT_SPENDING_LIMIT = Decimal("500.00")
VALID_MODES = frozenset({"Demo Mode", "Personal Planning Mode"})


class StorageError(ValueError):
    """Raised when local personal-state storage cannot be safely used."""


def default_personal_state() -> dict[str, object]:
    return {
        "mode": DEFAULT_MODE,
        "personal_events": [],
        "personal_initial_balance": DEFAULT_PERSONAL_INITIAL_BALANCE,
        "spending_limit": DEFAULT_SPENDING_LIMIT,
    }


def _decimal_setting(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise StorageError(f"{name} must be a non-negative decimal")
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise StorageError(f"{name} must be a non-negative decimal") from exc
    if not decimal_value.is_finite() or decimal_value < 0:
        raise StorageError(f"{name} must be a non-negative decimal")
    return decimal_value.quantize(Decimal("0.01"))


def _validate_state(raw_state: object) -> dict[str, object]:
    if not isinstance(raw_state, Mapping):
        raise StorageError("saved personal state must be a JSON object")
    if raw_state.get("schema_version") != SCHEMA_VERSION:
        raise StorageError("unsupported personal-state schema version")

    settings = raw_state.get("settings")
    events = raw_state.get("personal_events")
    if not isinstance(settings, Mapping):
        raise StorageError("saved personal state is missing settings")
    if not isinstance(events, list):
        raise StorageError("saved personal state is missing personal events")

    mode = settings.get("mode", DEFAULT_MODE)
    if mode not in VALID_MODES:
        raise StorageError("saved planning mode is invalid")
    initial_balance = _decimal_setting(
        settings.get("personal_initial_balance", DEFAULT_PERSONAL_INITIAL_BALANCE),
        "personal_initial_balance",
    )
    spending_limit = _decimal_setting(
        settings.get("spending_limit", DEFAULT_SPENDING_LIMIT),
        "spending_limit",
    )

    normalized_events: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for index, event in enumerate(events):
        if not isinstance(event, Mapping):
            raise StorageError(f"saved personal event {index} must be an object")
        event_id = event.get("id")
        if not isinstance(event_id, str) or not event_id.strip():
            raise StorageError(f"saved personal event {index} has an invalid id")
        if event_id in seen_ids:
            raise StorageError(f"saved personal event {index} has a duplicate id")
        seen_ids.add(event_id)
        normalized_events.append(
            {
                "id": event_id,
                "date": event.get("date"),
                "description": event.get("description"),
                "type": event.get("type"),
                "category": event.get("category"),
                "amount": _decimal_setting(
                    event.get("amount"), f"event {index} amount"
                ),
            }
        )

    try:
        project_cash_flow(initial_balance, normalized_events)
    except ValueError as exc:
        raise StorageError(f"saved personal event data is invalid: {exc}") from exc

    return {
        "mode": mode,
        "personal_events": normalized_events,
        "personal_initial_balance": initial_balance,
        "spending_limit": spending_limit,
    }


def _json_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    return value


def _serializable_state(state: Mapping[str, object]) -> dict[str, object]:
    validated = _validate_state(
        {
            "schema_version": SCHEMA_VERSION,
            "settings": {
                "mode": state.get("mode", DEFAULT_MODE),
                "personal_initial_balance": state.get(
                    "personal_initial_balance", DEFAULT_PERSONAL_INITIAL_BALANCE
                ),
                "spending_limit": state.get(
                    "spending_limit", DEFAULT_SPENDING_LIMIT
                ),
            },
            "personal_events": state.get("personal_events", []),
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "settings": {
            "mode": validated["mode"],
            "personal_initial_balance": _json_value(
                validated["personal_initial_balance"]
            ),
            "spending_limit": _json_value(validated["spending_limit"]),
        },
        "personal_events": [
            {
                key: _json_value(value)
                for key, value in event.items()
            }
            for event in validated["personal_events"]
        ],
    }


def load_personal_state(
    path: Path = STORAGE_PATH,
) -> tuple[dict[str, object], str | None]:
    """Load validated personal state, returning a safe warning when unavailable."""
    if not path.exists():
        return default_personal_state(), None
    try:
        with path.open("r", encoding="utf-8") as state_file:
            raw_state = json.load(state_file)
        return _validate_state(raw_state), None
    except (OSError, json.JSONDecodeError, StorageError) as exc:
        return (
            default_personal_state(),
            "Saved personal planning data could not be loaded safely.",
        )


def save_personal_state(
    state: Mapping[str, object],
    path: Path = STORAGE_PATH,
) -> bool:
    """Atomically save validated personal state; return False if unchanged."""
    serializable = _serializable_state(state)
    encoded = json.dumps(serializable, indent=2, sort_keys=True) + "\n"
    if path.exists():
        try:
            if path.read_text(encoding="utf-8") == encoded:
                return False
            existing = json.loads(path.read_text(encoding="utf-8"))
            _validate_state(existing)
        except (OSError, json.JSONDecodeError, StorageError) as exc:
            raise StorageError(
                "existing personal-state file is not safely replaceable"
            ) from exc

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(encoded)
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    except OSError as exc:
        if "temporary_path" in locals():
            temporary_path.unlink(missing_ok=True)
        raise StorageError("personal planning data could not be saved safely") from exc
    return True


def clear_personal_state(path: Path = STORAGE_PATH) -> None:
    """Delete only the personal-state file; demo fixtures are never touched."""
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        raise StorageError("saved personal planning data could not be cleared") from exc
