from __future__ import annotations

import io
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from pypdf import PdfReader


MONEY_COLUMNS = ["Ordered Product Sales", "Ordered Product Sales - B2B"]
INTEGER_COLUMNS = [
    "Sessions - Total",
    "Page Views - Total",
    "Units Ordered",
    "Units Ordered - B2B",
    "Total Order Items",
]


@dataclass
class StatementData:
    period: str
    income: float
    expenses: float
    transfers: float
    fba_product_sales: float
    product_refunds: float
    advertising: float
    selling_fees: float
    transaction_fees: float
    inventory_credit: float
    shipping_credits: float
    source_text: str

    @property
    def net_before_transfers(self) -> float:
        return self.income + self.expenses

    @property
    def remaining_after_transfers(self) -> float:
        return self.net_before_transfers + self.transfers

    @property
    def expense_rate(self) -> float:
        return abs(self.expenses / self.fba_product_sales) if self.fba_product_sales else 0


def _money(value) -> float:
    if pd.isna(value):
        return 0.0
    cleaned = str(value).replace("$", "").replace(",", "").strip()
    if cleaned in {"", "-", "nan"}:
        return 0.0
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = f"-{cleaned[1:-1]}"
    return float(cleaned)


def _integer(value) -> int:
    if pd.isna(value):
        return 0
    return int(float(str(value).replace(",", "").strip() or 0))


def _percent(value) -> float:
    if pd.isna(value):
        return 0.0
    return float(str(value).replace("%", "").strip() or 0) / 100


def parse_business_report(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(file_bytes), encoding="utf-8-sig")
    required = {
        "(Child) ASIN",
        "Title",
        "Sessions - Total",
        "Page Views - Total",
        "Units Ordered",
        "Unit Session Percentage",
        "Ordered Product Sales",
        "Total Order Items",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Business Report is missing required columns: {', '.join(missing)}")

    for column in MONEY_COLUMNS:
        if column in df:
            df[column] = df[column].map(_money)
        else:
            df[column] = 0.0
    for column in INTEGER_COLUMNS:
        if column in df:
            df[column] = df[column].map(_integer)
        else:
            df[column] = 0
    df["Conversion"] = df["Unit Session Percentage"].map(_percent)
    df["Avg. Sale / Unit"] = df.apply(
        lambda row: row["Ordered Product Sales"] / row["Units Ordered"]
        if row["Units Ordered"]
        else 0,
        axis=1,
    )
    total_sales = df["Ordered Product Sales"].sum()
    df["Sales Share"] = (
        df["Ordered Product Sales"] / total_sales if total_sales else 0
    )
    df["Revenue / Session"] = df.apply(
        lambda row: row["Ordered Product Sales"] / row["Sessions - Total"]
        if row["Sessions - Total"]
        else 0,
        axis=1,
    )
    return df.sort_values("Ordered Product Sales", ascending=False).reset_index(drop=True)


def _all_money_values(text: str) -> list[float]:
    pattern = r"(?<![A-Za-z])(?:-?\d{1,3}(?:,\d{3})+(?:\.\d{2})|-?\d+\.\d{2})(?![A-Za-z])"
    return [float(match.replace(",", "")) for match in re.findall(pattern, text)]


def _repeated_statement_totals(values: list[float]) -> tuple[float, float, float]:
    counts = Counter(round(value, 2) for value in values if value != 0)
    repeated = {value: count for value, count in counts.items() if count >= 2}
    positive = [value for value in repeated if value > 1000]
    negative = [value for value in repeated if value < -100]
    if not positive or len(negative) < 2:
        raise ValueError("Could not identify Amazon statement summary totals.")

    income = max(positive)
    transfers = min(negative, key=lambda value: (-repeated[value], value))
    expense_candidates = [value for value in negative if value != transfers]
    expenses = min(expense_candidates)
    return income, expenses, transfers


def _period_from_text(text: str) -> str:
    match = re.search(
        r"Account activity from ([A-Z][a-z]{2} \d{1,2}, \d{4}).*?through ([A-Z][a-z]{2} \d{1,2}, \d{4})",
        text,
        re.DOTALL,
    )
    if not match:
        return "Uploaded reporting period"
    start = datetime.strptime(match.group(1), "%b %d, %Y")
    end = datetime.strptime(match.group(2), "%b %d, %Y")
    return f"{start.strftime('%B %-d')}–{end.strftime('%-d, %Y')}"


def parse_unified_summary(file_bytes: bytes) -> StatementData:
    reader = PdfReader(io.BytesIO(file_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    if "Net sales, credits, and refunds" not in text or "FBA product sales" not in text:
        raise ValueError("The PDF does not appear to be an Amazon Custom Unified Summary.")

    values = _all_money_values(text)
    income, expenses, transfers = _repeated_statement_totals(values)

    # Amazon's generated PDF stores financial values in a stable object sequence.
    # These positions cover the current Custom Unified Summary format. Fallbacks
    # keep headline totals usable if optional zero-value lines change the sequence.
    nonzero = [value for value in values if value != 0]
    gross_candidates = [value for value in nonzero if income < value < income * 1.1]
    fba_product_sales = min(gross_candidates) if gross_candidates else income
    product_refunds = nonzero[3] if len(nonzero) > 3 and nonzero[3] < 0 else 0
    shipping_credits = nonzero[0] if nonzero and nonzero[0] > 0 else 0

    excluded = {round(expenses, 2), round(transfers, 2), round(product_refunds, 2)}
    fee_candidates = sorted(
        {
            round(value, 2)
            for value in nonzero
            if value < 0
            and round(value, 2) not in excluded
            and abs(value) < abs(expenses)
        },
        key=abs,
        reverse=True,
    )
    transaction_fees = fee_candidates[0] if fee_candidates else 0
    selling_fees = fee_candidates[1] if len(fee_candidates) > 1 else 0
    advertising = fee_candidates[2] if len(fee_candidates) > 2 else 0

    credits = [value for value in nonzero if 0 < value < income * 0.1]
    inventory_credit = max(credits) if credits else 0

    return StatementData(
        period=_period_from_text(text),
        income=income,
        expenses=expenses,
        transfers=transfers,
        fba_product_sales=fba_product_sales,
        product_refunds=product_refunds,
        advertising=advertising,
        selling_fees=selling_fees,
        transaction_fees=transaction_fees,
        inventory_credit=inventory_credit,
        shipping_credits=shipping_credits,
        source_text=text,
    )


def product_summary(df: pd.DataFrame) -> dict[str, float]:
    sales = float(df["Ordered Product Sales"].sum())
    units = int(df["Units Ordered"].sum())
    sessions = int(df["Sessions - Total"].sum())
    orders = int(df["Total Order Items"].sum())
    return {
        "sales": sales,
        "units": units,
        "sessions": sessions,
        "orders": orders,
        "conversion": units / sessions if sessions else 0,
        "avg_sale_per_unit": sales / units if units else 0,
        "b2b_sales": float(df["Ordered Product Sales - B2B"].sum()),
    }
