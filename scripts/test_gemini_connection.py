"""Minimal, safe Gemini connection smoke test for local development."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


DEFAULT_MODEL = "gemini-3.5-flash-lite"
PROMPT = "Reply with exactly: Budgetify Gemini connection successful."


def load_local_env(path: Path) -> None:
    """Load simple KEY=VALUE entries without printing or exposing their values."""
    if not path.is_file():
        raise RuntimeError(f"Local environment file not found: {path.name}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


def sanitized_error(error: Exception, secret: str) -> str:
    message = str(error).replace(secret, "[redacted]")
    message = " ".join(message.split())
    return message[:300] or error.__class__.__name__


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    try:
        load_local_env(project_root / ".env")
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is missing or empty in the local environment."
            )

        from google import genai

        model = os.environ.get("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=PROMPT)
        text = " ".join((response.text or "").split())
        if not text:
            raise RuntimeError("The model returned an empty response.")
        print(f"Gemini connection successful using {model}.")
        print(f"Model response: {text[:300]}")
        return 0
    except Exception as error:
        secret = locals().get("api_key", "")
        print(f"Gemini connection failed: {sanitized_error(error, secret)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
