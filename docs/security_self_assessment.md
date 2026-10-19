# Budgetify security self-assessment

This document describes controls that exist in the current prototype. Future
mitigations are explicitly separated from existing behavior; they are not
claims about the current application.

## Existing secrets protections

- `.gitignore` excludes `.env`, `.env.*`, secret files, `secrets.toml`, and the
  local `.budgetify/` persistence directory. `.env.example` is explicitly
  allowed and contains placeholders only.
- The application reads `GEMINI_API_KEY` from the process environment or a
  local `.env`; the Streamlit UI can also pass `st.secrets` to the assistant.
- The repository contains no credential in `.env.example` or this document.
- The Gemini smoke test does not print the API key and replaces the key in a
  caught error message before printing it.

These are repository/configuration protections, not a guarantee that a local
machine, its environment, or a user’s secret store is secure.

## Data sent to Gemini

For Ask Budgetify, the constructed request includes:

- the user’s question, after whitespace normalization;
- aggregate transaction facts such as counts, income, expenses, net balance,
  category amounts/percentages, and budget status;
- aggregate scheduled cash-flow facts such as event counts, opening/projected
  balances, requested-date information, and shortfall totals;
- scope labels and currency formatting used to interpret those figures.

`build_context` excludes raw transaction descriptions and raw scheduled-event
descriptions from the aggregate context. The prompt therefore does not include
the raw transaction history used to calculate the facts. This does **not**
prevent a user from typing personal or identifying information into the
question; that question is included in the provider request. Gemini is an
external API, so users should avoid entering information they do not want to
share with that provider.

## Existing request limits and error handling

- Questions longer than 2,000 characters are rejected before an API call.
- Empty questions are rejected before an API call.
- The prompt requests a concise answer of one to three sentences, preferably
  under 60 words; this is an instruction, not a hard provider token limit.
- Returned text is whitespace-normalized, empty responses are rejected, and
  the returned string is capped at 4,000 characters.
- Provider failures are mapped to user-safe messages for quota/rate-limit,
  authentication/permission, and other network/service failures.
- API failure messages are not allowed to expose the configured key.
- Relevant coverage is in `tests/test_assistant.py`, including description
  exclusion, limits, mocked model selection, missing-key behavior, and
  redacted API errors. `tests/test_storage.py` covers malformed state,
  validation, atomic-save failure, and clear behavior.

## Permissions and access tiers

No permission tiers are implemented. The prototype has no accounts,
authentication, authorization roles, user/session identity, or multi-user
access-control boundary. A person who can run the local app can use its local
planning interface and access the local state file according to operating
system permissions. Streamlit secrets and environment variables provide
configuration/secret inputs; they are not user permission controls.

## Known risks and limitations

- Local personal planning data is stored as JSON in `.budgetify\personal_state.json`.
  The application does not provide encryption at rest, key management, or
  secure deletion.
- The local `.env` and Streamlit secret mechanisms depend on the host and
  operator protecting those files/environment values.
- Ask Budgetify depends on Gemini availability, provider policy, quota,
  transport, and model behavior. Data sent to Gemini is subject to that
  provider’s handling and retention terms.
- Aggregate-only context reduces exposure of raw descriptions but does not
  eliminate privacy risk: totals, categories, dates/counts, and the user’s
  question can still be sensitive.
- Model output may be inaccurate, overconfident, or unsuitable for a user’s
  circumstances. Deterministic calculations constrain the facts supplied to
  the model but do not make its explanation authoritative.
- There is no bank connection, transaction reconciliation, fraud detection,
  audit log, deployment hardening, rate limiting for users, or production
  monitoring.
- The prototype supports a displayed currency label but does not perform
  foreign-exchange conversion.

## Practical mitigations and future work

The following are recommendations, not implemented controls:

- Add explicit user consent and a pre-send preview of the aggregate context
  and question, with an option to use deterministic insights without Gemini.
- Add authenticated, per-user storage with authorization checks and a
  documented retention/deletion policy before any shared deployment.
- Use managed secret storage and key rotation rather than local `.env` files
  for hosted operation; restrict access to logs and provider telemetry.
- Add provider request quotas, abuse controls, timeout/retry policy, and
  monitoring that does not record sensitive prompts or credentials.
- Evaluate model responses against financial-safety test cases and visibly
  label model output as explanatory rather than financial advice.
- Consider encrypted storage and a threat-model review if personal data is
  retained beyond a local prototype.
