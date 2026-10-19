from pathlib import Path
from copy import deepcopy
from datetime import date
from uuid import uuid4

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from src.finance import (
    CASH_FLOW_CATEGORIES,
    budget_summary,
    net_balance,
    project_cash_flow,
    spending_by_category,
    total_by_type,
)
from src.assistant import AssistantError, ask_budgetify, build_context
from src.insights import (
    assess_budget,
    generate_recommendations,
    identify_projected_shortfalls,
    summarize_expenses_by_category,
)
from src.storage import (
    StorageError,
    clear_personal_state,
    default_personal_state,
    load_personal_state,
    save_personal_state,
)


DATA_PATH = Path(__file__).resolve().parent / "data" / "sample_transactions.csv"
REQUIRED_COLUMNS = {
    "date",
    "description",
    "category",
    "amount",
    "currency",
    "type",
}


def load_transactions() -> pd.DataFrame:
    """Load and validate the sample transaction CSV."""
    try:
        transactions = pd.read_csv(DATA_PATH)
    except FileNotFoundError as exc:
        raise ValueError(f"Transaction file was not found: {DATA_PATH}") from exc
    except (OSError, UnicodeDecodeError, pd.errors.ParserError) as exc:
        raise ValueError(f"Could not read transaction data: {exc}") from exc

    missing_columns = REQUIRED_COLUMNS.difference(transactions.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Transaction data is missing required columns: {missing}")
    if transactions.empty:
        return transactions

    transactions["type"] = transactions["type"].astype("string").str.strip().str.lower()
    transactions["category"] = (
        transactions["category"].astype("string").str.strip().str.lower()
    )
    transactions["category"] = transactions.apply(
        canonical_transaction_category,
        axis=1,
    )
    transactions["amount"] = pd.to_numeric(transactions["amount"], errors="coerce")
    transactions["currency"] = transactions["currency"].astype("string").str.strip()

    records = transactions.to_dict(orient="records")
    # Use the shared validation path so the dashboard cannot show invalid totals.
    net_balance(records)
    return transactions


def format_amount(amount: float, currency: str) -> str:
    return f"{currency} {amount:,.2f}"


def canonical_transaction_category(transaction: pd.Series) -> str:
    """Map legacy sample labels to the shared category vocabulary."""
    category = str(transaction["category"]).strip().lower()
    if transaction["type"] == "income":
        return {
            "education": "scholarship",
            "income": "other income",
        }.get(category, category)
    if transaction["type"] == "expense":
        return {
            "education": "study materials",
            "housing": "rent",
            "utilities": "bills",
            "other": "other expenses",
        }.get(category, category)
    return category


SAMPLE_CASH_FLOW_EVENTS = [
    {
        "date": "2026-11-01",
        "description": "Illustrative scholarship payment",
        "type": "income",
        "category": "scholarship",
        "amount": 900,
    },
    {
        "date": "2026-11-03",
        "description": "Illustrative accommodation payment",
        "type": "expense",
        "category": "rent",
        "amount": 700,
    },
    {
        "date": "2026-11-08",
        "description": "Illustrative grocery spending",
        "type": "expense",
        "category": "food",
        "amount": 120,
    },
    {
        "date": "2026-11-15",
        "description": "Illustrative transport pass",
        "type": "expense",
        "category": "transport",
        "amount": 80,
    },
    {
        "date": "2026-11-20",
        "description": "Illustrative study materials",
        "type": "expense",
        "category": "study materials",
        "amount": 300,
    },
]

MODE_OPTIONS = ("Demo Mode", "Personal Planning Mode")
DEMO_INITIAL_BALANCE = 250.0


def create_demo_events() -> list[dict[str, object]]:
    return [
        {**event, "id": uuid4().hex}
        for event in deepcopy(SAMPLE_CASH_FLOW_EVENTS)
    ]


def reset_events_for_mode(mode: str) -> list[dict[str, object]]:
    """Return a fresh schedule for the selected planning mode."""
    if mode == "Demo Mode":
        return create_demo_events()
    if mode == "Personal Planning Mode":
        return []
    raise ValueError(f"Unsupported cash-flow mode: {mode}")


def _personal_state_signature() -> str:
    return repr(
        (
            st.session_state.cash_flow_mode,
            st.session_state.personal_cash_flow_events,
            st.session_state.personal_initial_balance,
            st.session_state.spending_limit,
        )
    )


def persist_personal_state(force: bool = False) -> None:
    if st.session_state.get("storage_load_warning"):
        return
    signature = _personal_state_signature()
    if not force and signature == st.session_state.get("storage_signature"):
        return
    state = {
        "mode": st.session_state.cash_flow_mode,
        "personal_events": st.session_state.personal_cash_flow_events,
        "personal_initial_balance": st.session_state.personal_initial_balance,
        "spending_limit": st.session_state.spending_limit,
    }
    try:
        save_personal_state(state)
    except StorageError:
        st.session_state.storage_save_warning = (
            "Personal planning data could not be saved safely."
        )
        return
    st.session_state.storage_signature = signature


def initialize_persistent_state() -> None:
    required_state_keys = (
        "cash_flow_mode",
        "personal_cash_flow_events",
        "personal_initial_balance",
        "spending_limit",
    )
    if st.session_state.get("persistent_state_initialized") and all(
        key in st.session_state for key in required_state_keys
    ):
        return
    state, warning = load_personal_state()
    defaults = default_personal_state()
    st.session_state.cash_flow_mode = state.get("mode", defaults["mode"])
    st.session_state.personal_cash_flow_events = state.get(
        "personal_events", defaults["personal_events"]
    )
    st.session_state.personal_initial_balance = float(
        state.get(
            "personal_initial_balance",
            defaults["personal_initial_balance"],
        )
    )
    st.session_state.spending_limit = float(
        state.get("spending_limit", defaults["spending_limit"])
    )
    st.session_state.storage_load_warning = warning
    st.session_state.storage_save_warning = None
    st.session_state.persistent_state_initialized = True
    if warning is None:
        persist_personal_state(force=True)


def initialize_cash_flow_state() -> None:
    initialize_persistent_state()
    if "cash_flow_events" not in st.session_state:
        if st.session_state.cash_flow_mode == "Personal Planning Mode":
            st.session_state.cash_flow_events = deepcopy(
                st.session_state.personal_cash_flow_events
            )
        else:
            st.session_state.cash_flow_events = reset_events_for_mode(
                st.session_state.cash_flow_mode
            )


def switch_cash_flow_mode(selected_mode: str) -> None:
    previous_mode = st.session_state.cash_flow_mode
    if selected_mode == previous_mode:
        return
    if previous_mode == "Personal Planning Mode":
        st.session_state.personal_cash_flow_events = deepcopy(
            st.session_state.cash_flow_events
        )
    st.session_state.cash_flow_mode = selected_mode
    if selected_mode == "Personal Planning Mode":
        st.session_state.cash_flow_events = deepcopy(
            st.session_state.personal_cash_flow_events
        )
    else:
        st.session_state.cash_flow_events = reset_events_for_mode(selected_mode)
    persist_personal_state()


def category_label(category: str) -> str:
    return category.title()


def categories_for_event_type(event_type: str) -> tuple[str, ...]:
    normalized_type = event_type.strip().lower()
    try:
        return CASH_FLOW_CATEGORIES[normalized_type]
    except KeyError as error:
        raise ValueError(
            "event_type must be 'income' or 'expense'"
        ) from error


def dashboard_transactions(
    sample_transactions: pd.DataFrame,
    mode: str,
    events: list[dict[str, object]],
    currency: str,
) -> tuple[pd.DataFrame, str, str]:
    """Return the one transaction-like dataset displayed by the active mode."""
    if mode == "Demo Mode":
        return (
            sample_transactions.copy(),
            "Recorded sample transactions",
            "Net balance",
        )
    if mode != "Personal Planning Mode":
        raise ValueError(f"Unsupported cash-flow mode: {mode}")
    personal_transactions = pd.DataFrame(
        [
            {
                "date": event["date"],
                "description": event["description"],
                "category": event["category"],
                "amount": event["amount"],
                "currency": currency,
                "type": event["type"],
            }
            for event in events
        ],
        columns=["date", "description", "category", "amount", "currency", "type"],
    )
    return (
        personal_transactions,
        "Scheduled personal cash-flow entries",
        "Net scheduled cash flow",
    )


def render_financial_insights(
    transactions: pd.DataFrame,
    budget_limit: float,
    initial_balance: float,
    events: list[dict[str, object]],
    currency: str,
) -> None:
    """Render deterministic insights without changing existing dashboard flows."""
    st.subheader("Financial Insights")
    st.caption(
        "Insights are descriptive summaries of the synthetic transaction data and "
        "the selected cash-flow schedule; they are not financial advice."
    )
    records = transactions.to_dict(orient="records")
    try:
        category_summary = summarize_expenses_by_category(records)
        budget_assessment = assess_budget(records, budget_limit)
        shortfalls = identify_projected_shortfalls(initial_balance, events)
        recommendations = generate_recommendations(
            category_summary,
            budget_assessment,
            shortfalls,
        )
    except ValueError as error:
        st.error(f"Unable to calculate financial insights: {error}")
        return

    summary_column, budget_column = st.columns(2)
    with summary_column:
        st.markdown("**Expense categories**")
        if category_summary:
            category_rows = [
                {
                    "Category": category.title(),
                    "Amount": format_amount(float(values["amount"]), currency),
                    "Share of expenses": f"{values['percentage']:.2f}%",
                }
                for category, values in category_summary.items()
            ]
            st.dataframe(
                pd.DataFrame(category_rows),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.info("No expense transactions are available to summarize.")

    with budget_column:
        st.markdown("**Budget assessment**")
        status_labels = {
            "within_budget": "Within budget",
            "approaching": "Approaching budget",
            "exceeded": "Budget exceeded",
            "no_budget": "No budget set",
        }
        st.metric(
            "Budget status",
            status_labels[budget_assessment["status"]],
        )
        st.write(
            f"Actual expenses: "
            f"{format_amount(float(budget_assessment['expenses']), currency)}"
        )
        st.write(
            f"Budget limit: "
            f"{format_amount(float(budget_assessment['limit']), currency)}"
        )
        st.write(
            f"Budget used: {budget_assessment['percentage_used']:.2f}%"
        )
        if budget_assessment["status"] == "no_budget":
            st.info("Set a positive monthly budget to assess utilization.")
        elif budget_assessment["status"] == "exceeded":
            st.warning("Actual expenses have reached or exceeded the budget limit.")
        elif budget_assessment["status"] == "approaching":
            st.warning("Actual expenses are approaching the budget limit.")

    st.markdown("**Projected cash-flow shortfalls**")
    if shortfalls:
        for shortfall in shortfalls:
            st.warning(
                f"{shortfall['date']}: {shortfall['description']} would leave a "
                f"projected shortfall of "
                f"{format_amount(float(shortfall['shortfall']), currency)}."
            )
    else:
        st.success("No projected cash-flow shortfalls were identified.")

    st.markdown("**Recommendations**")
    for recommendation in recommendations:
        st.write(f"- {recommendation}")


def render_ask_budgetify(
    transactions: pd.DataFrame,
    budget_limit: float,
    initial_balance: float,
    events: list[dict[str, object]],
    transaction_scope: str,
    cash_flow_scope: str,
    currency: str,
) -> None:
    st.subheader("Ask Budgetify")
    st.caption(
        "Ask about the sample transaction aggregates or the active scheduled "
        "cash-flow plan. Gemini receives only summarized figures, not descriptions "
        "or transaction history."
    )
    question = st.text_input(
        "Your question",
        placeholder="How much of the sample budget has been used?",
        key="ask_budgetify_question",
    )
    if st.button("Ask Budgetify", key="ask_budgetify_submit"):
        try:
            context = build_context(
                transactions.to_dict(orient="records"),
                budget_limit,
                initial_balance,
                events,
                transaction_scope=transaction_scope,
                cash_flow_scope=cash_flow_scope,
                currency=currency,
            )
            try:
                streamlit_secrets = st.secrets
            except StreamlitSecretNotFoundError:
                streamlit_secrets = {}
            answer = ask_budgetify(
                question,
                context,
                secrets=streamlit_secrets,
            )
        except AssistantError as error:
            st.warning(str(error))
        else:
            st.text(answer)


def render_cash_flow(display_currency: str) -> None:
    initialize_cash_flow_state()
    st.subheader("Student Cash Flow")
    if st.session_state.get("storage_load_warning"):
        st.warning(
            "Saved personal planning data could not be loaded safely. "
            "It was not overwritten."
        )
    if st.session_state.get("storage_save_warning"):
        st.warning(st.session_state.storage_save_warning)
    selected_mode = st.radio(
        "Planning mode",
        MODE_OPTIONS,
        index=MODE_OPTIONS.index(st.session_state.cash_flow_mode),
        key="cash_flow_mode_selector",
    )
    if selected_mode != st.session_state.cash_flow_mode:
        switch_cash_flow_mode(selected_mode)
        st.rerun()

    if selected_mode == "Demo Mode":
        st.info(
            "Demo Mode shows illustrative synthetic events for presentations. "
            "They do not represent a real person's finances or bank balance, "
            "and any demo changes reset when the app restarts."
        )
    else:
        st.info(
            "Personal Planning Mode uses hypothetical events and saves its events, "
            "starting balance, spending limit, and selected mode locally on this "
            "computer."
        )

    if selected_mode == "Demo Mode":
        initial_balance = DEMO_INITIAL_BALANCE
        st.metric(
            "Initial available balance",
            format_amount(initial_balance, display_currency),
        )
        st.caption(
            "Demo scenario configuration: the illustrative schedule starts with "
            "USD 250.00 available."
        )
    else:
        previous_initial_balance = st.session_state.personal_initial_balance
        initial_balance = st.number_input(
            f"Initial available balance ({display_currency})",
            min_value=0.0,
            value=st.session_state.personal_initial_balance,
            step=50.0,
            format="%.2f",
            key="personal_initial_balance_input",
            help="No money is added automatically in Personal Planning Mode.",
        )
        if initial_balance != previous_initial_balance:
            st.session_state.personal_initial_balance = initial_balance
            persist_personal_state()
        st.caption(
            "Personal Planning Mode starts at the balance entered above; "
            "it defaults to USD 0.00."
        )

    st.markdown("**Add a hypothetical event**")
    event_type_label = st.selectbox(
        "Event type",
        ("Income", "Expense"),
        key="cash_flow_event_type",
        help="Changing this immediately updates the compatible category choices.",
    )
    event_type = event_type_label.lower()
    category_options = categories_for_event_type(event_type)
    category_labels = [category_label(category) for category in category_options]

    with st.form("add_cash_flow_event", clear_on_submit=True):
        description = st.text_input(
            "Description",
            key="cash_flow_event_description",
        )
        event_date = st.date_input(
            "Date",
            value=date.today(),
            min_value=date.today(),
            key="cash_flow_event_date",
        )
        category_label_value = st.selectbox(
            "Category",
            category_labels,
            key=f"cash_flow_event_category_{event_type}",
        )
        amount = st.number_input(
            "Amount",
            min_value=0.01,
            value=50.00,
            step=10.00,
            format="%.2f",
            key="cash_flow_event_amount",
        )
        add_event = st.form_submit_button("Add event")

    if add_event:
        new_event = {
            "id": uuid4().hex,
            "date": event_date.isoformat(),
            "description": description,
            "type": event_type,
            "category": category_label_value.lower(),
            "amount": amount,
        }
        try:
            project_cash_flow(
                initial_balance,
                [*st.session_state.cash_flow_events, new_event],
            )
        except ValueError as error:
            st.error(f"Event was not added: {error}")
        else:
            st.session_state.cash_flow_events.append(new_event)
            if selected_mode == "Personal Planning Mode":
                st.session_state.personal_cash_flow_events.append(new_event)
                persist_personal_state()
                st.rerun()

    st.markdown("**Manage hypothetical events**")
    reset_confirmation = st.checkbox(
        "I understand this will reset the current planning schedule.",
        key="confirm_cash_flow_reset",
    )
    reset_label = (
        "Reset to Demo Data"
        if selected_mode == "Demo Mode"
        else "Clear Personal Planning Events"
    )
    if st.button(reset_label, disabled=not reset_confirmation):
        st.session_state.cash_flow_events = reset_events_for_mode(selected_mode)
        if selected_mode == "Personal Planning Mode":
            st.session_state.personal_cash_flow_events = []
            persist_personal_state()
        st.rerun()

    if selected_mode == "Personal Planning Mode":
        clear_confirmation = st.checkbox(
            "I understand this permanently clears saved personal planning data.",
            key="confirm_clear_saved_personal_data",
        )
        if st.button(
            "Clear Saved Personal Planning Data",
            disabled=not clear_confirmation,
        ):
            try:
                clear_personal_state()
            except StorageError as error:
                st.error(str(error))
            else:
                defaults = default_personal_state()
                st.session_state.personal_cash_flow_events = []
                st.session_state.personal_initial_balance = float(
                    defaults["personal_initial_balance"]
                )
                st.session_state.spending_limit = float(
                    defaults["spending_limit"]
                )
                st.session_state.cash_flow_mode = "Demo Mode"
                st.session_state.cash_flow_events = reset_events_for_mode(
                    "Demo Mode"
                )
                st.session_state.storage_signature = None
                st.session_state.storage_load_warning = None
                st.session_state.storage_save_warning = None
                st.rerun()

    events = st.session_state.cash_flow_events
    try:
        cash_flow = project_cash_flow(initial_balance, events)
    except ValueError as error:
        st.error(f"Unable to calculate the cash-flow schedule: {error}")
        return

    if cash_flow:
        remove_columns = st.columns(len(cash_flow))
        for column, event in zip(remove_columns, cash_flow):
            if column.button(
                f"Remove {event['description']}",
                key=f"remove_cash_flow_{event['id']}",
            ):
                st.session_state.cash_flow_events = [
                    item
                    for item in st.session_state.cash_flow_events
                    if item["id"] != event["id"]
                ]
                if selected_mode == "Personal Planning Mode":
                    st.session_state.personal_cash_flow_events = [
                        item
                        for item in st.session_state.personal_cash_flow_events
                        if item["id"] != event["id"]
                    ]
                    persist_personal_state()
                st.rerun()

    if not cash_flow:
        st.info("No cash-flow events are scheduled.")
        return

    shortfalls = [event for event in cash_flow if event["is_shortfall"]]
    if shortfalls:
        for event in shortfalls:
            st.warning(
                f"Shortfall after {event['date']}: {event['description']} "
                f"leaves a projected shortfall of "
                f"{format_amount(float(event['shortfall']), display_currency)}."
            )
    else:
        st.success("No projected shortfalls in the selected planning schedule.")

    cash_flow_table = pd.DataFrame(cash_flow).rename(
        columns={
            "date": "Date",
            "description": "Description",
            "type": "Type",
            "category": "Category",
            "amount": "Amount",
            "projected_balance": "Projected balance",
            "is_shortfall": "Shortfall?",
            "shortfall": "Projected shortfall",
        }
    )
    cash_flow_table["Amount"] = cash_flow_table["Amount"].apply(
        lambda amount: format_amount(float(amount), display_currency)
    )
    cash_flow_table["Projected balance"] = cash_flow_table[
        "Projected balance"
    ].apply(lambda amount: format_amount(float(amount), display_currency))
    cash_flow_table["Projected shortfall"] = cash_flow_table[
        "Projected shortfall"
    ].apply(lambda amount: format_amount(float(amount), display_currency))
    st.dataframe(cash_flow_table, hide_index=True, use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="Budgetify", page_icon="💸", layout="wide")
    st.title("Budgetify")
    st.caption("A budgeting assistant for international students")
    initialize_persistent_state()

    with st.sidebar:
        st.header("Monthly Budget")
        spending_limit = st.number_input(
            "Spending limit",
            min_value=0.0,
            value=500.0,
            step=50.0,
            format="%.2f",
            key="spending_limit",
            help="This tracker uses the full synthetic sample period.",
        )
        persist_personal_state()

    try:
        transactions = load_transactions()
    except ValueError as error:
        st.error(f"Unable to load transaction data: {error}")
        return

    currencies = sorted(transactions["currency"].dropna().unique().tolist())
    currency_label = ", ".join(currencies) if currencies else "unspecified currency"
    display_currency = currencies[0] if len(currencies) == 1 else "CUR"
    active_mode = st.session_state.cash_flow_mode
    active_transactions, transaction_scope, net_label = dashboard_transactions(
        transactions,
        active_mode,
        st.session_state.cash_flow_events,
        display_currency,
    )
    if active_mode == "Demo Mode":
        st.caption(
            f"All amounts are illustrative sample data ({currency_label}); "
            "they are not connected to a real bank account."
        )
        st.caption(
            "The Monthly Budget tracker covers this synthetic sample period, "
            "not the current calendar month."
        )
    else:
        st.caption(
            "Personal Planning Mode shows scheduled entries entered in this plan. "
            "They are not completed bank transactions."
        )

    active_records = active_transactions.to_dict(orient="records")
    budget = budget_summary(active_records, spending_limit)
    with st.sidebar:
        st.caption(
            "Sample-period tracker"
            if active_mode == "Demo Mode"
            else "Personal scheduled-entry tracker"
        )
        st.metric(
            "Monthly spending limit",
            format_amount(budget["limit"], display_currency),
        )
        st.metric(
            "Expenses counted toward budget",
            format_amount(budget["expenses"], display_currency),
        )
        st.metric(
            "Remaining budget",
            format_amount(budget["remaining"], display_currency),
        )
        st.metric("Percentage of budget used", f"{budget['percentage_used']:.2f}%")
        st.progress(min(budget["percentage_used"] / 100, 1.0))
        if spending_limit == 0:
            st.warning(
                "The spending limit is zero. Set a limit to track remaining budget."
            )
        elif budget["expenses"] >= budget["limit"]:
            st.warning(
                "Spending has reached or exceeded the active planning limit."
            )

    filter_label = st.selectbox(
        "Transaction type",
        ("All transactions", "Income only", "Expenses only"),
    )
    filter_types = {
        "All transactions": {"income", "expense"},
        "Income only": {"income"},
        "Expenses only": {"expense"},
    }
    filtered = active_transactions[
        active_transactions["type"].isin(filter_types[filter_label])
    ]
    records = filtered.to_dict(orient="records")

    income = total_by_type(records, "income")
    expenses = total_by_type(records, "expense")
    balance = net_balance(records)
    transaction_count = len(filtered)

    metric_columns = st.columns(4)
    metric_columns[0].metric(
        "Total income", format_amount(income, display_currency)
    )
    metric_columns[1].metric(
        "Total expenses", format_amount(expenses, display_currency)
    )
    metric_columns[2].metric(net_label, format_amount(balance, display_currency))
    metric_columns[3].metric("Number of transactions", transaction_count)
    st.caption(
        f"{transaction_scope}; metrics reflect the selected view: "
        f"{filter_label.lower()}."
    )

    chart_column, table_column = st.columns((1, 2))
    with chart_column:
        st.subheader("Spending by category")
        category_totals = spending_by_category(records)
        if category_totals:
            chart_data = pd.DataFrame(
                {"Amount": category_totals}
            )
            st.bar_chart(chart_data, y="Amount")
        else:
            st.info("No expense transactions in the selected view.")

    with table_column:
        st.subheader("Transaction history")
        display_columns = {
            "date": "Date",
            "description": "Description",
            "category": "Category",
            "amount": "Amount",
            "currency": "Currency",
            "type": "Type",
        }
        history = filtered[list(display_columns)].rename(columns=display_columns)
        history["Amount"] = history.apply(
            lambda row: format_amount(row["Amount"], row["Currency"]),
            axis=1,
        )
        st.dataframe(
            history,
            hide_index=True,
            use_container_width=True,
        )

    render_cash_flow(display_currency)
    active_initial_balance = (
        DEMO_INITIAL_BALANCE
        if st.session_state.cash_flow_mode == "Demo Mode"
        else st.session_state.personal_initial_balance
    )
    render_financial_insights(
        active_transactions,
        spending_limit,
        active_initial_balance,
        st.session_state.cash_flow_events,
        display_currency,
    )
    render_ask_budgetify(
        active_transactions,
        spending_limit,
        active_initial_balance,
        st.session_state.cash_flow_events,
        transaction_scope,
        (
            "active Demo Mode scheduled cash-flow aggregates"
            if active_mode == "Demo Mode"
            else "active Personal Planning Mode scheduled cash-flow aggregates"
        ),
        display_currency,
    )


if __name__ == "__main__":
    main()
