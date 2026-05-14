from __future__ import annotations

import math
from typing import Any

import pandas as pd


CLOSE_TO_MA_THRESHOLD = 0.03
EXTREME_REVENUE_GROWTH_THRESHOLD = 5.0
EXTREME_PRICE_TO_SALES_THRESHOLD = 100.0

GROWTH_RISK_LEVELS = {
    "Confirmed Watch": "Medium-High",
    "Early Watch": "High",
    "Trend Positive": "Medium",
    "Pullback Watch": "Medium-High",
    "High Volume Risk Monitor": "High",
    "Weak Trend / Low Volume": "Medium-High",
    "Data Issue": "Unknown",
    "Neutral": "Medium",
    "Error": "Unknown",
}

GROWTH_ACTION_NOTES = {
    "Confirmed Watch": "Rebound setup confirmed by RSI, volume, and 50MA proximity.",
    "Early Watch": "Early rebound setup; wait for trend confirmation.",
    "Trend Positive": "Trend is intact; monitor pullback and volume confirmation.",
    "Pullback Watch": "Watch for 50MA recovery and improving volume.",
    "High Volume Risk Monitor": (
        "Monitor whether high volume reflects accumulation or distribution."
    ),
    "Weak Trend / Low Volume": (
        "Treat as a weak-trend state. Do not assume it is an avoid signal; "
        "check for reversal or further deterioration."
    ),
    "Data Issue": "Review fundamentals manually before interpretation.",
    "Neutral": "No actionable technical setup from current rules.",
    "Error": "Could not screen this ticker.",
}

STRATEGY_ROLES = {
    "Confirmed Watch": "Rebound Confirmation Signal",
    "Early Watch": "Early Alert Only",
    "Trend Positive": "Trend Filter",
    "Pullback Watch": "Primary Watch Signal",
    "High Volume Risk Monitor": "Volatility Monitor / Confirmation Required",
    "Weak Trend / Low Volume": "Reversal Monitor",
    "Neutral": "No Clear Setup",
    "Data Issue": "Data Quality Review",
    "Error": "Error / Review Required",
}

TICKER_ACTION_NOTES = {
    "LUNR": "Wait for pullback; recent move is already extended.",
    "RKLB": "Trend intact; monitor volume confirmation.",
    "ASTS": "Watch 50MA recovery.",
    "PL": "Trend intact; verify FCF quality.",
    "SPCE": "Weak trend state; wait for trend and fundamentals to improve.",
    "ACHR": "Weak trend state; watch whether price can recover above 200MA.",
    "JOBY": "Monitor whether high volume is accumulation or distribution.",
}


def clean_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(number) or math.isinf(number):
        return None
    return number


def number_less_than(value: Any, threshold: float) -> bool:
    number = clean_number(value)
    return number is not None and number < threshold


def number_greater_than(value: Any, threshold: float) -> bool:
    number = clean_number(value)
    return number is not None and number > threshold


def number_between(value: Any, low: float, high: float) -> bool:
    number = clean_number(value)
    return number is not None and low <= number <= high


def price_vs_ma(price: float | None, moving_average: float | None) -> str:
    if price is None or moving_average is None:
        return "Insufficient Data"
    if price > moving_average:
        return "Above"
    if price < moving_average:
        return "Below"
    return "Equal"


def is_above_or_close_to_50ma(price: float | None, ma_50: float | None) -> bool:
    if price is None or ma_50 in (None, 0):
        return False
    return price >= ma_50 * (1 - CLOSE_TO_MA_THRESHOLD)


def growth_signal_from_row(row: dict[str, Any] | pd.Series) -> str:
    price = clean_number(row.get("last_close_price", row.get("close")))
    rsi = clean_number(row.get("rsi_14"))
    volume_ratio = clean_number(row.get("volume_ratio_vs_20d"))
    ma_50 = clean_number(row.get("ma_50d"))
    price_50 = row.get("price_vs_50ma")
    price_200 = row.get("price_vs_200ma")

    if price_200 == "Below" and number_less_than(volume_ratio, 1.0):
        return "Weak Trend / Low Volume"
    if (
        number_less_than(rsi, 35)
        and number_greater_than(volume_ratio, 1.5)
        and is_above_or_close_to_50ma(price, ma_50)
    ):
        return "Confirmed Watch"
    if number_less_than(rsi, 35) and number_greater_than(volume_ratio, 1.5):
        return "Early Watch"
    if (
        price_50 == "Below"
        and price_200 == "Below"
        and number_greater_than(volume_ratio, 1.5)
        and not number_less_than(rsi, 35)
    ):
        return "High Volume Risk Monitor"
    if (
        price_50 == "Below"
        and price_200 == "Above"
        and number_between(rsi, 35, 50)
    ):
        return "Pullback Watch"
    if (
        price_50 == "Above"
        and price_200 == "Above"
        and number_between(rsi, 40, 70)
    ):
        return "Trend Positive"
    return "Neutral"


def growth_signal_reason(
    row: dict[str, Any] | pd.Series,
    missing_fields: list[str] | None = None,
) -> str | None:
    signal = row.get("signal")
    if signal == "Weak Trend / Low Volume":
        return (
            "Price is below 200MA and volume is below its 20-day average; this "
            "indicates weak trend and low participation, not necessarily a sell signal."
        )
    if signal == "Data Issue":
        fields = ", ".join(missing_fields or [])
        return f"Missing important financial fields: {fields}."
    if signal == "Confirmed Watch":
        return "RSI is below 35, volume ratio is above 1.5, and price is above or close to 50MA."
    if signal == "Early Watch":
        return "RSI is below 35 and volume ratio is above 1.5, but price is not yet above or close to 50MA."
    if signal == "High Volume Risk Monitor":
        return "Price is below both 50MA and 200MA while volume ratio is above 1.5."
    if signal == "Pullback Watch":
        return "Price is below 50MA but above 200MA, with RSI between 35 and 50."
    if signal == "Trend Positive":
        return "Price is above both 50MA and 200MA, with RSI between 40 and 70."
    if signal == "Neutral":
        return "No growth rebound watch or weak-trend condition was triggered."
    return None


def financial_warnings(row: dict[str, Any] | pd.Series) -> str | None:
    warnings = []

    if number_greater_than(row.get("revenue_growth"), EXTREME_REVENUE_GROWTH_THRESHOLD):
        warnings.append("Extreme revenue growth; verify low base effect")
    if number_greater_than(row.get("price_to_sales"), EXTREME_PRICE_TO_SALES_THRESHOLD):
        warnings.append(
            "Extreme PSR; revenue base may be too small for PSR to be meaningful"
        )
    if number_less_than(row.get("price_to_book"), 0):
        warnings.append("Negative P/B; check book value and balance sheet structure")

    return "; ".join(warnings) if warnings else None


def technical_warning(row: dict[str, Any] | pd.Series, group: str) -> str | None:
    warnings = []

    if number_greater_than(row.get("rsi_14"), 70):
        warnings.append("Overbought")

    if group == "Growth / Space rebound":
        if number_greater_than(row.get("return_20d"), 0.30):
            warnings.append("Short-term Extended / Avoid Chasing")
        if row.get("signal") == "Trend Positive" and number_less_than(
            row.get("volume_ratio_vs_20d"), 1.0
        ):
            warnings.append("Trend Positive but Volume Weak")
        if row.get("signal") == "Pullback Watch" and number_less_than(
            row.get("volume_ratio_vs_20d"), 1.0
        ):
            warnings.append("Pullback with Weak Volume")

    if group == "Mega-cap valuation":
        if number_greater_than(row.get("return_20d"), 0.25):
            warnings.append("Short-term Extended")
        if (
            row.get("price_vs_50ma") == "Below"
            and row.get("price_vs_200ma") == "Below"
        ):
            warnings.append("Below Key Trend")
        if (
            row.get("price_vs_50ma") == "Above"
            and number_less_than(row.get("volume_ratio_vs_20d"), 0.8)
        ):
            warnings.append("Uptrend but Weak Volume")

    if (
        row.get("price_vs_50ma") == "Below"
        and row.get("price_vs_200ma") == "Below"
        and number_greater_than(row.get("volume_ratio_vs_20d"), 1.5)
    ):
        warnings.append("High Volume Below Trend")
    if (
        row.get("price_vs_50ma") == "Below"
        and row.get("price_vs_200ma") == "Below"
        and number_less_than(row.get("volume_ratio_vs_20d"), 1.0)
    ):
        warnings.append("Below Trend / Weak Volume")
    if row.get("ticker") == "AAPL" and number_greater_than(
        row.get("price_to_book"), 30
    ):
        warnings.append("High P/B; interpret with buybacks and capital return policy")

    return "; ".join(dict.fromkeys(warnings)) if warnings else None


def risk_level_for_signal(signal: str | None) -> str | None:
    return GROWTH_RISK_LEVELS.get(signal, "Unknown")


def action_note_for_signal(symbol: str, signal: str | None) -> str | None:
    return TICKER_ACTION_NOTES.get(symbol.upper(), GROWTH_ACTION_NOTES.get(signal))


def strategy_role_for_signal(signal: str | None) -> str:
    return STRATEGY_ROLES.get(signal, "Review Manually")
