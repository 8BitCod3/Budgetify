# Budgetify

Budgetify is a student-finance AI agent prototype for an international fintech
competition. It is intended to help students understand spending patterns and
build practical budgeting habits.

## Current scope

This initial prototype includes:

- Deterministic financial calculations in `src/finance.py`
- Synthetic transaction data for local development
- A minimal Streamlit app
- A pytest test suite

Financial calculations are performed by Python code. Future AI features must
not invent or replace authoritative financial numbers.

## Planned capabilities

- Categorizing and summarizing student spending
- Budget planning and progress views
- Explanations and educational guidance from an AI assistant
- Support for international student contexts and currencies

The project does not currently include an LLM, external API, database, or
real-money transfer functionality. Do not add real personal or banking data;
use synthetic data for development and testing.

## Local setup

```text
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Run the app:

```text
streamlit run app.py
```

Run the tests:

```text
pytest
```
