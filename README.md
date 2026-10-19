# Budgetify

Budgetify is a student-finance prototype built with Streamlit. It helps a
student inspect transaction history, understand spending patterns, compare
expenses with a monthly spending limit, plan scheduled cash flow, and ask
plain-language questions through Ask Budgetify.

This is a local competition prototype, not a banking product. The application
does not connect to a bank, move money, authenticate users, or claim to provide
financial advice.

## What the prototype includes

- **Streamlit dashboard** with income, expense, net-balance, transaction-count,
  and spending-by-category views.
- **Transaction history** loaded from
  [`data/sample_transactions.csv`](./data/sample_transactions.csv) in Demo
  Mode. The fixture is synthetic and is not a real account.
- **Financial Insights** that calculate category totals and percentages,
  compare expenses with a supplied spending limit, identify projected
  shortfalls, and produce deterministic recommendations.
- **Monthly budgeting** using the active transaction-like entries. In Demo
  Mode this is the full synthetic sample period; it is not automatically the
  current calendar month.
- **Student Cash Flow** with dated income and expense events, chronological
  balance projections, and shortfall flags. Demo Mode uses illustrative
  synthetic events. Personal Planning Mode uses hypothetical events entered by
  the user.
- **Personal Planning Mode** with an opening balance, spending limit, editable
  scheduled events, today’s scheduled transactions, and local persistence.
  These entries are planning assumptions, not completed bank transactions.
- **Ask Budgetify**, an optional Gemini-backed question-and-answer feature.
  Python computes the financial facts first. The Gemini request receives the
  user’s question and aggregate financial context; it does not receive raw
  transaction descriptions or raw transaction history from the constructed
  context.

Financial totals, category summaries, budget assessments, cash-flow projections,
and shortfall calculations are deterministic Python results. Gemini is used to
explain the supplied aggregates, not to replace those calculations.

## Requirements

- Python 3.13 (the project is intended to run with Python 3.13)
- The packages listed in [`requirements.txt`](./requirements.txt)
- A Gemini API key only if Ask Budgetify is used

## Installation and launch

From the project directory in PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit. The dashboard and deterministic
features can be explored without Gemini. Ask Budgetify requires the optional
API configuration below.

If PowerShell blocks activation, run the project with the virtual-environment
interpreter directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

## Gemini configuration

Copy [`.env.example`](./.env.example) to `.env` and replace the placeholders
locally, or provide the same settings through Streamlit secrets or the process
environment. Never commit `.env` or put a real credential in documentation.

```text
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=your_model_name_here
```

`GEMINI_API_KEY` is required when Ask Budgetify is submitted. `GEMINI_MODEL`
is optional; when omitted, the application uses its built-in default model.
The application’s Gemini connection smoke test can be run only when a real
local key is configured:

```powershell
python scripts\test_gemini_connection.py
```

The smoke test makes an external Gemini request. Do not use it with a
credential that should not incur an API request.

## Tests

Install the requirements, activate the virtual environment, and run:

```powershell
pytest
```

The tests cover deterministic finance and insight calculations, validation,
personal-state persistence, dashboard helpers, aggregate-only assistant
context, question/response behavior, and mocked Gemini calls. They do not
require a live Gemini request.

## Data and persistence

Demo Mode reads the checked-in synthetic CSV and uses illustrative in-memory
cash-flow events. Personal Planning Mode saves validated hypothetical state to
`.budgetify\personal_state.json` on the local computer. The `.budgetify\`
directory is ignored by Git. Clearing personal data removes that local state;
it does not alter the demo fixture.

## Known limitations

- Gemini is an external service dependency for Ask Budgetify. Network,
  provider availability, quota, model behavior, and API-key permissions can
  affect that feature.
- Gemini responses can be inaccurate or incomplete. They are constrained to
  supplied aggregates but are not authoritative financial advice.
- The prototype has no user accounts, authentication, authorization roles,
  multi-user separation, encryption-at-rest feature, deployment configuration,
  bank synchronization, or real-money functionality.
- Personal planning data is local application state, not a secure financial
  records system. Users should avoid entering information they do not want
  stored locally or included in a question sent to Gemini.
- Amounts are displayed using the active currency label; the prototype does
  not perform foreign-exchange conversion.
- Scheduled events and the opening balance are user-entered assumptions.
  The projection does not prove that an expense is affordable.

## For judges

1. Use Python 3.13 and follow the installation commands above.
2. Run `streamlit run app.py`.
3. Start in **Demo Mode** to inspect the synthetic transaction history,
   spending chart, monthly budget tracker, insights, and illustrative cash-flow
   projection.
4. Switch to **Personal Planning Mode** to enter hypothetical events and an
   opening balance. The values are saved locally in the ignored `.budgetify`
   directory.
5. Configure `GEMINI_API_KEY` only if you want to demonstrate Ask Budgetify.
   Ask a question about the displayed aggregates and remember that the feature
   makes an external API request.
6. Run `pytest` to verify the local test suite.
