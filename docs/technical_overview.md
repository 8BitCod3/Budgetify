# Budgetify technical overview

## Runtime shape

Budgetify is a local Streamlit application launched from `app.py`. The app
loads the synthetic CSV into a pandas DataFrame, initializes Streamlit session
state, selects Demo Mode or Personal Planning Mode, and renders the dashboard
sections. The app imports shared calculation and assistant functions rather
than implementing separate versions of the financial formulas.

The main modules are:

- `app.py`: UI composition, CSV loading and normalization, mode switching,
  dashboard helpers, event forms, table/chart rendering, and user-facing
  error/warning messages.
- `src/finance.py`: validation of transaction/event records, income and expense
  totals, net balance, category spending, budget summaries, and chronological
  cash-flow projections.
- `src/insights.py`: Decimal-based category percentages, budget status
  (`no_budget`, `within_budget`, `approaching`, or `exceeded`), projected
  shortfalls, and recommendations derived from already-computed results.
- `src/storage.py`: validation, serialization, loading, atomic replacement,
  and clearing of personal planning state.
- `src/assistant.py`: local environment loading, aggregate context construction,
  prompt construction, Gemini calls, response normalization, and user-safe
  assistant errors.

## Data modes and local persistence

Demo Mode reads `data/sample_transactions.csv`, whose records are synthetic.
The app also creates a separate illustrative schedule for the Student Cash
Flow section. Demo changes to that schedule are reset when the app restarts.

Personal Planning Mode builds transaction-like dashboard rows from the
hypothetical scheduled events entered in the UI. It also uses a separately
entered opening balance and spending limit. The opening balance is a starting
point for projection, not an income transaction. Personal state is validated
and saved locally at `.budgetify/personal_state.json` with schema version 1.
The save uses a temporary file and `os.replace`; malformed or unsupported
existing state is not silently overwritten. The directory is ignored by Git.

## Financial calculation boundaries

`src/finance.py` is the calculation boundary. It accepts mappings with
validated `income` or `expense` types and non-negative numeric amounts.
Expenses require a category. Cash-flow events additionally require an ISO
date, non-empty description/category, and a category from the defined
income/expense vocabulary.

`total_by_type`, `net_balance`, `spending_by_category`, and `budget_summary`
operate on the supplied transaction collection. Budget summaries count
expenses only; they do not treat income or an opening balance as spending.
`project_cash_flow` sorts events by date, preserves input order for same-day
events, updates the running balance, and reports negative-balance shortfalls.

`src/insights.py` reuses those functions. It converts money values to
`Decimal` for the insight boundary and does not make model or network calls.
The UI labels Demo Mode as a synthetic sample period and Personal Planning
Mode as all active scheduled entries rather than silently presenting either as
bank history or a current-month ledger.

## Ask Budgetify request flow

When the user submits a question, `app.py` passes the active records, budget,
opening balance, scheduled events, scopes, currency, and question to
`build_context`. That function computes totals, category aggregates, budget
status, today/range spending, event counts, projected balances, and shortfall
aggregates. It deliberately returns no raw transaction or event descriptions.

`build_prompt` normalizes whitespace, rejects an empty question, and rejects
questions longer than 2,000 characters. The prompt instructs Gemini to use
only the aggregate facts, distinguish sample transaction aggregates from
scheduled cash-flow aggregates, avoid invented figures, and return concise
plain text. `ask_budgetify` reads `GEMINI_API_KEY` from the process environment
or a local `.env` file, with Streamlit secrets supplied by the UI as a
fallback. `GEMINI_MODEL` can override the built-in default model. The request
contains the user question and constructed aggregate prompt; it does not
send the raw records used to construct that context.

The Gemini response is whitespace-normalized, rejected if empty, and truncated
to 4,000 characters. Expected configuration, provider, quota, and network
failures are converted to `AssistantError` messages that the UI displays as a
warning. A live Gemini call is not needed for the normal test suite.

## Test strategy

The pytest suite tests the calculation boundary with valid and invalid inputs,
chronological projection and shortfall behavior, insight classifications and
recommendations, dashboard mode separation, and local persistence failure
paths. Assistant tests verify aggregate-only context, exclusion of descriptions,
date/range facts, the 2,000-character question limit, model selection, empty
responses, API failure redaction, and mocked Gemini calls. Tests use fake
clients where an external model interaction would otherwise be required.
