from __future__ import annotations

import hashlib
import hmac
import html
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


def short_product_name(title: str) -> str:
    title_lower = title.lower()
    names = [
        ("gum arabic", "Gum Arabic"),
        ("frereana", "Frereana Resin"),
        ("hydrosol", "Hydrosol Spray"),
        ("hotel diffuser", "Hotel Diffuser Oil"),
        ("hair growth", "Hair Growth Oil"),
        ("skin regenerative", "Skin Oil"),
        ("essential oil", "Essential Oil"),
        ("carterii", "Carterii Resin"),
    ]
    for keyword, name in names:
        if keyword in title_lower:
            return name
    return title[:36]


def product_performance_table(product_df: pd.DataFrame, totals: dict[str, float]) -> str:
    rows = []
    for _, product in product_df.iterrows():
        rows.append(
            "<tr>"
            f"<td>{html.escape(short_product_name(str(product['Title'])))}</td>"
            f"<td class='number'>{int(product['Units Ordered']):,}</td>"
            f"<td class='number'>${product['Ordered Product Sales']:,.2f}</td>"
            f"<td class='number'>{product['Sales Share']:.1%}</td>"
            f"<td class='number'>{product['Conversion']:.1%}</td>"
            "</tr>"
        )
    rows.append(
        "<tr class='total-row'>"
        "<td>Total / Overall</td>"
        f"<td class='number'>{totals['units']:,}</td>"
        f"<td class='number'>${totals['sales']:,.2f}</td>"
        "<td class='number'>100.0%</td>"
        f"<td class='number'>{totals['conversion']:.1%}</td>"
        "</tr>"
    )
    return """
    <style>
    .performance-wrap {
        border-bottom: 4px solid #3276a8;
        margin-top: 0.5rem;
        overflow-x: auto;
    }
    .performance-title {
        background: #3b79a6;
        color: white;
        font-size: 0.95rem;
        font-weight: 700;
        padding: 0.45rem 0.55rem;
    }
    table.performance {
        border-collapse: collapse;
        color: #263444;
        font-size: 0.88rem;
        width: 100%;
    }
    table.performance th {
        background: #1e3852;
        color: white;
        font-weight: 700;
        padding: 0.42rem 0.5rem;
        text-align: left;
        white-space: nowrap;
    }
    table.performance td {
        border: 1px solid #d1dce6;
        padding: 0.34rem 0.5rem;
    }
    table.performance tr:nth-child(even) td {
        background: #f1f4f7;
    }
    table.performance .number {
        text-align: right;
        white-space: nowrap;
    }
    table.performance .total-row td {
        background: #e8edf3 !important;
        font-weight: 700;
    }
    </style>
    <div class="performance-wrap">
      <div class="performance-title">PRODUCT PERFORMANCE</div>
      <table class="performance">
        <thead>
          <tr>
            <th>Product</th><th>Units</th><th>Sales</th>
            <th>Sales Share</th><th>Conversion</th>
          </tr>
        </thead>
        <tbody>
    """ + "".join(rows) + """
        </tbody>
      </table>
    </div>
    """


def financial_overview_table(statement) -> str:
    gross = statement.fba_product_sales

    def pct(value: float) -> str:
        return f"{abs(value / gross):.1%}" if gross else "-"

    rows = [
        (
            "Gross FBA product sales",
            statement.fba_product_sales,
            pct(statement.fba_product_sales),
            "Product refunds",
            statement.product_refunds,
            pct(statement.product_refunds),
        ),
        (
            "Net income after refunds/credits",
            statement.income,
            pct(statement.income),
            "Amazon advertising",
            statement.advertising,
            pct(statement.advertising),
        ),
        (
            "Amazon fees and other expenses",
            statement.expenses,
            pct(statement.expenses),
            "FBA selling fees",
            statement.selling_fees,
            pct(statement.selling_fees),
        ),
        (
            "Net proceeds before transfers",
            statement.net_before_transfers,
            pct(statement.net_before_transfers),
            "FBA transaction fees",
            statement.transaction_fees,
            pct(statement.transaction_fees),
        ),
        (
            "Proceeds remaining after transfers",
            statement.remaining_after_transfers,
            pct(statement.remaining_after_transfers),
            "Bank transfers",
            statement.transfers,
            pct(statement.transfers),
        ),
    ]
    body = []
    for left_label, left_amount, left_pct, right_label, right_amount, right_pct in rows:
        body.append(
            "<tr>"
            f"<td>{left_label}</td><td class='number'>{money_html(left_amount)}</td>"
            f"<td class='number'>{left_pct}</td>"
            f"<td>{right_label}</td><td class='number'>{money_html(right_amount)}</td>"
            f"<td class='number'>{right_pct}</td>"
            "</tr>"
        )
    return """
    <div class="summary-table-wrap">
      <div class="section-title">FINANCIAL OVERVIEW</div>
      <table class="summary-table">
        <thead><tr>
          <th>Metric</th><th>Amount</th><th>% of Gross Sales</th>
          <th>Metric</th><th>Amount</th><th>% of Gross Sales</th>
        </tr></thead>
        <tbody>
    """ + "".join(body) + """
        </tbody>
      </table>
    </div>
    """


def money_html(value: float) -> str:
    formatted = f"${abs(value):,.2f}"
    return f"<span class='negative'>({formatted})</span>" if value < 0 else formatted


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

st.markdown(
    """
    <style>
    .section-title {
        background: #17365d;
        color: white;
        font-size: 0.95rem;
        font-weight: 700;
        padding: 0.45rem 0.55rem;
    }
    .summary-table-wrap {
        border-bottom: 4px solid #3276a8;
        margin: 0.5rem 0 1rem 0;
        overflow-x: auto;
    }
    table.summary-table {
        border-collapse: collapse;
        color: #263444;
        font-size: 0.85rem;
        width: 100%;
    }
    table.summary-table th {
        background: #d9eaf7;
        color: #17365d;
        font-weight: 700;
        padding: 0.42rem 0.5rem;
        text-align: left;
        white-space: nowrap;
    }
    table.summary-table td {
        border: 1px solid #c5d4e0;
        padding: 0.38rem 0.5rem;
    }
    table.summary-table tr:nth-child(even) td {
        background: #f4f7fa;
    }
    table.summary-table .number {
        text-align: right;
        white-space: nowrap;
    }
    .negative { color: #c00000; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.subheader(f"Amazon USA | {statement.period} Finance & Product Summary")
st.caption(
    "All amounts USD. Net proceeds exclude product costs, freight, payroll, "
    "and external operating expenses."
)
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

st.markdown(financial_overview_table(statement), unsafe_allow_html=True)

product_col, chart_col = st.columns([1.35, 1])
with product_col:
    st.markdown(
        product_performance_table(product_df, totals),
        unsafe_allow_html=True,
    )
with chart_col:
    chart_df = product_df.copy()
    chart_df["Product"] = chart_df["Title"].map(short_product_name)
    fig = px.bar(
        chart_df,
        x="Product",
        y="Ordered Product Sales",
        title="Sales by Product",
        labels={"Ordered Product Sales": "Sales (USD)"},
    )
    fig.update_traces(marker_color="#176889")
    fig.update_layout(
        showlegend=False,
        xaxis_tickangle=-35,
        height=max(380, 250 + len(chart_df) * 20),
        margin=dict(l=20, r=20, t=55, b=80),
    )
    st.plotly_chart(fig, use_container_width=True)

top = product_df.iloc[0]
top_three_share = product_df.head(3)["Sales Share"].sum()
best_conversion = product_df.loc[product_df["Conversion"].idxmax()]
st.markdown('<div class="section-title">MANAGEMENT TAKEAWAYS</div>', unsafe_allow_html=True)
st.markdown(
    "\n".join(
        [
            f"- **{short_product_name(str(top['Title']))}** generated "
            f"**{top['Sales Share']:.1%}** of ASIN-report sales; the top three products "
            f"generated **{top_three_share:.1%}**.",
            f"- **{short_product_name(str(best_conversion['Title']))}** had the highest "
            f"conversion at **{best_conversion['Conversion']:.1%}**, from "
            f"**{best_conversion['Sessions - Total']:,} sessions**.",
            f"- Amazon fees and other expenses were **{statement.expense_rate:.1%}** "
            "of gross FBA product sales.",
            (
                f"- Reports reconcile within the $5 tolerance; difference: **${difference:,.2f}**."
                if reconciled
                else f"- Reconciliation requires review; ASIN sales differ from the "
                f"financial statement by **${difference:,.2f}**."
            ),
        ]
    )
)

excel_bytes = create_excel_report(product_df, statement)
st.download_button(
    "Download Excel Summary",
    excel_bytes,
    file_name="Amazon_USA_Summary.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    type="primary",
)
