from __future__ import annotations

import hashlib
import hmac
from dataclasses import replace

import pandas as pd
import plotly.express as px
import streamlit as st

from amazon_reports import parse_business_report, parse_unified_summary, product_summary
from excel_report import create_excel_report


st.set_page_config(
    page_title="Amazon USA Dashboard",
    page_icon="📊",
    layout="wide",
)


def check_password() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.title("Amazon USA Reporting Dashboard")
    st.caption("Authorized access only")
    try:
        expected = str(st.secrets["APP_PASSWORD"])
    except Exception:
        st.error("APP_PASSWORD has not been configured in Streamlit secrets.")
        st.stop()

    with st.form("login"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)
    if submitted:
        entered_hash = hashlib.sha256(password.encode()).digest()
        expected_hash = hashlib.sha256(expected.encode()).digest()
        if hmac.compare_digest(entered_hash, expected_hash):
            st.session_state.authenticated = True
            st.rerun()
        st.error("Incorrect password.")
    return False


if not check_password():
    st.stop()

with st.sidebar:
    st.header("Amazon USA Dashboard")
    st.success("Password protected")
    if st.button("Log out", use_container_width=True):
        st.session_state.clear()
        st.rerun()
    st.divider()
    st.caption(
        "Uploaded files are processed in memory for the current session. "
        "The app does not intentionally save them."
    )

st.title("Amazon Finance & Product Dashboard")
st.write(
    "Upload the matching Amazon Business Report CSV and Custom Unified Summary PDF."
)

left, right = st.columns(2)
with left:
    csv_file = st.file_uploader("Business Report CSV", type=["csv"])
with right:
    pdf_file = st.file_uploader("Custom Unified Summary PDF", type=["pdf"])

if not csv_file or not pdf_file:
    st.info("Upload both reports to generate the dashboard.")
    st.stop()

try:
    product_df = parse_business_report(csv_file.getvalue())
    statement = parse_unified_summary(pdf_file.getvalue())
except Exception as exc:
    st.error(f"Could not process the uploaded reports: {exc}")
    st.stop()

with st.sidebar.expander("Review parsed statement values"):
    st.caption("Confirm these figures against the PDF before relying on the summary.")
    parsed_gross = st.number_input(
        "Gross FBA product sales", value=statement.fba_product_sales, step=0.01
    )
    parsed_income = st.number_input(
        "Net income after refunds/credits", value=statement.income, step=0.01
    )
    parsed_expenses = st.number_input(
        "Amazon fees and other expenses", value=statement.expenses, step=0.01
    )
    parsed_transfers = st.number_input(
        "Transfers to bank", value=statement.transfers, step=0.01
    )
statement = replace(
    statement,
    fba_product_sales=parsed_gross,
    income=parsed_income,
    expenses=parsed_expenses,
    transfers=parsed_transfers,
)

totals = product_summary(product_df)
difference = totals["sales"] - statement.fba_product_sales
reconciled = abs(difference) <= 5

st.subheader(statement.period)
k1, k2, k3, k4 = st.columns(4)
k1.metric("ASIN Report Sales", f"${totals['sales']:,.2f}")
k2.metric("Units Ordered", f"{totals['units']:,}")
k3.metric("Net Proceeds Before Transfers", f"${statement.net_before_transfers:,.2f}")
k4.metric("Amazon Expense Rate", f"{statement.expense_rate:.1%}")

if reconciled:
    st.success(f"Reports reconcile within tolerance. Difference: ${difference:,.2f}")
else:
    st.warning(
        f"Reconciliation review required: ASIN report differs from the financial "
        f"statement by ${difference:,.2f}. Check date filters, adjustments, and omitted ASINs."
    )

tab_summary, tab_products, tab_finance = st.tabs(
    ["Executive Summary", "Products by ASIN", "Financial Detail"]
)

with tab_summary:
    chart_col, insight_col = st.columns([1.5, 1])
    with chart_col:
        chart_df = product_df.head(12).copy()
        chart_df["Product"] = chart_df["Title"].str.slice(0, 42)
        fig = px.bar(
            chart_df,
            x="Product",
            y="Ordered Product Sales",
            title="Sales by Product",
            labels={"Ordered Product Sales": "Sales (USD)"},
        )
        fig.update_layout(showlegend=False, xaxis_tickangle=-35)
        st.plotly_chart(fig, use_container_width=True)
    with insight_col:
        top = product_df.iloc[0]
        top_three_share = product_df.head(3)["Sales Share"].sum()
        best_conversion = product_df.loc[product_df["Conversion"].idxmax()]
        st.markdown("#### Management Takeaways")
        st.write(
            f"**{top['Title'][:55]}** generated **{top['Sales Share']:.1%}** of ASIN-report sales."
        )
        st.write(f"The top three ASINs generated **{top_three_share:.1%}** of sales.")
        st.write(
            f"Highest conversion: **{best_conversion['Title'][:55]}** at "
            f"**{best_conversion['Conversion']:.1%}**, from "
            f"**{best_conversion['Sessions - Total']:,} sessions**."
        )
        st.write(
            f"Amazon fees and other expenses were **{statement.expense_rate:.1%}** "
            "of gross FBA product sales."
        )

with tab_products:
    display = product_df[
        [
            "(Child) ASIN",
            "Title",
            "Sessions - Total",
            "Units Ordered",
            "Ordered Product Sales",
            "Sales Share",
            "Conversion",
            "Avg. Sale / Unit",
            "Revenue / Session",
        ]
    ].rename(
        columns={
            "(Child) ASIN": "ASIN",
            "Title": "Product",
            "Sessions - Total": "Sessions",
            "Units Ordered": "Units",
            "Ordered Product Sales": "Sales",
        }
    )
    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Sales": st.column_config.NumberColumn(format="$%.2f"),
            "Sales Share": st.column_config.ProgressColumn(format="%.1%%", min_value=0, max_value=1),
            "Conversion": st.column_config.NumberColumn(format="%.1%%"),
            "Avg. Sale / Unit": st.column_config.NumberColumn(format="$%.2f"),
            "Revenue / Session": st.column_config.NumberColumn(format="$%.2f"),
        },
    )

with tab_finance:
    finance = pd.DataFrame(
        [
            ["Gross FBA product sales", statement.fba_product_sales],
            ["Net income after refunds/credits", statement.income],
            ["Amazon fees and other expenses", statement.expenses],
            ["Net proceeds before transfers", statement.net_before_transfers],
            ["Transfers to bank", statement.transfers],
            ["Remaining after transfers", statement.remaining_after_transfers],
            ["ASIN report sales", totals["sales"]],
            ["Reconciliation difference", difference],
        ],
        columns=["Metric", "Amount"],
    )
    st.dataframe(
        finance,
        use_container_width=True,
        hide_index=True,
        column_config={"Amount": st.column_config.NumberColumn(format="$%.2f")},
    )
    st.caption(
        "Net proceeds are not business profit. Product costs, freight, payroll, "
        "and expenses outside Amazon are not included."
    )

excel_bytes = create_excel_report(product_df, statement)
st.download_button(
    "Download Excel Summary",
    excel_bytes,
    file_name="Amazon_USA_Summary.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
)
