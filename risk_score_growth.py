from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


OUTPUT_DIR = PROJECT_ROOT / "output"
SCREENING_CSV = PROJECT_ROOT / "screening" / "output" / "growth_rebound_screen.csv"
PRIORITY_CSV = OUTPUT_DIR / "daily_growth_priority.csv"
INTERPRETATION_CSV = (
    PROJECT_ROOT / "backtesting" / "output" / "growth_signal_backtest_interpretation.csv"
)
ENHANCED_SUMMARY_CSV = (
    PROJECT_ROOT / "backtesting" / "output" / "growth_signal_enhanced_backtest_summary.csv"
)

RISK_SCORE_CSV = OUTPUT_DIR / "growth_risk_score.csv"
RISK_SCORE_XLSX = OUTPUT_DIR / "growth_risk_score.xlsx"
FINAL_REPORT_XLSX = OUTPUT_DIR / "final_daily_research_report.xlsx"

MISSING_INPUT_MESSAGE = (
    "Required input files not found. Please run py .\\screening\\screen_stocks.py "
    "and py .\\rank_screening_results.py first."
)


def text_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value)


def number_value(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def has_text(value: Any, needle: str) -> bool:
    return needle.lower() in text_value(value).lower()


def required_inputs_exist() -> bool:
    missing = [path for path in [SCREENING_CSV, PRIORITY_CSV] if not path.exists()]
    if not missing:
        return True

    print(MISSING_INPUT_MESSAGE)
    print("Missing files:")
    for path in missing:
        print(f"- {path}")
    return False


def clamp(score: float, low: int = 0, high: int = 100) -> int:
    return int(max(low, min(high, round(score))))


def volatility_risk_score(row: pd.Series) -> int:
    score = 0
    return_20d = abs(number_value(row.get("return_20d")) or 0)
    return_60d = abs(number_value(row.get("return_60d")) or 0)
    rsi = number_value(row.get("rsi_14"))

    if return_20d >= 0.50:
        score += 35
    elif return_20d >= 0.30:
        score += 25
    elif return_20d >= 0.15:
        score += 15
    else:
        score += 5

    if return_60d >= 1.00:
        score += 35
    elif return_60d >= 0.50:
        score += 25
    elif return_60d >= 0.25:
        score += 15
    else:
        score += 5

    if rsi is not None and (rsi > 70 or rsi < 30):
        score += 20

    if has_text(row.get("technical_warning"), "Short-term Extended"):
        score += 10
    if has_text(row.get("technical_warning"), "Overbought"):
        score += 10

    return clamp(score)


def liquidity_risk_score(row: pd.Series) -> int:
    score = 0
    avg_volume = number_value(row.get("avg_volume_20d"))
    volume_ratio = number_value(row.get("volume_ratio_vs_20d"))

    if avg_volume is None:
        score += 50
    elif avg_volume < 500_000:
        score += 45
    elif avg_volume < 1_000_000:
        score += 30
    elif avg_volume < 3_000_000:
        score += 15
    else:
        score += 5

    if volume_ratio is None:
        score += 20
    elif volume_ratio < 0.5:
        score += 25
    elif volume_ratio < 0.8:
        score += 15
    elif volume_ratio > 2.0:
        score += 10

    return clamp(score)


def financial_risk_score(row: pd.Series) -> int:
    score = 0
    net_income = number_value(row.get("net_income"))
    operating_cash_flow = number_value(row.get("operating_cash_flow"))
    free_cash_flow = number_value(row.get("free_cash_flow"))
    total_cash = number_value(row.get("total_cash"))
    total_debt = number_value(row.get("total_debt"))

    if net_income is None:
        score += 10
    elif net_income < 0:
        score += 20

    if operating_cash_flow is None:
        score += 10
    elif operating_cash_flow < 0:
        score += 20

    if free_cash_flow is None:
        score += 10
    elif free_cash_flow < 0:
        score += 25

    if total_cash in (None, 0):
        score += 20
    elif total_debt is not None:
        debt_to_cash = total_debt / total_cash
        if debt_to_cash > 2.0:
            score += 25
        elif debt_to_cash > 1.0:
            score += 15
        elif debt_to_cash > 0.5:
            score += 5

    if text_value(row.get("error")):
        score += 30
    if text_value(row.get("financial_warning")):
        score += 10

    return clamp(score)


def valuation_risk_score(row: pd.Series) -> int:
    score = 0
    price_to_sales = number_value(row.get("price_to_sales"))
    price_to_book = number_value(row.get("price_to_book"))

    if price_to_sales is None:
        score += 10
    elif price_to_sales > 100:
        score += 45
    elif price_to_sales > 50:
        score += 35
    elif price_to_sales > 20:
        score += 25
    elif price_to_sales > 10:
        score += 15
    else:
        score += 5

    if price_to_book is None:
        score += 5
    elif price_to_book < 0:
        score += 35
    elif price_to_book > 50:
        score += 25
    elif price_to_book > 20:
        score += 15

    if has_text(row.get("financial_warning"), "Extreme PSR"):
        score += 15
    if has_text(row.get("financial_warning"), "Negative P/B"):
        score += 15

    return clamp(score)


def technical_risk_score(row: pd.Series) -> int:
    score = 0
    signal = text_value(row.get("signal"))
    current_risk = text_value(row.get("current_risk_level") or row.get("risk_level"))

    signal_scores = {
        "Trend Positive": 25,
        "Pullback Watch": 45,
        "High Volume Risk Monitor": 70,
        "Weak Trend / Low Volume": 60,
        "Early Watch": 65,
        "Confirmed Watch": 50,
        "Neutral": 50,
        "Data Issue": 70,
        "Error": 90,
    }
    score += signal_scores.get(signal, 60)

    risk_scores = {
        "Medium": 5,
        "Medium-High": 15,
        "High": 25,
        "Very High": 35,
        "Unknown": 25,
    }
    score += risk_scores.get(current_risk, 15)

    if row.get("price_vs_50ma") == "Below":
        score += 10
    if row.get("price_vs_200ma") == "Below":
        score += 20
    if text_value(row.get("technical_warning")):
        score += 10

    return clamp(score)


def risk_label(score: int) -> str:
    if score >= 75:
        return "Very High"
    if score >= 55:
        return "High"
    if score >= 35:
        return "Medium"
    return "Low"


def risk_reason(row: pd.Series) -> str:
    reasons = []
    if row["technical_risk_score"] >= 65:
        reasons.append("technical setup requires caution")
    if row["financial_risk_score"] >= 65:
        reasons.append("financial risk is elevated")
    if row["valuation_risk_score"] >= 65:
        reasons.append("valuation metrics are stretched or distorted")
    if row["volatility_risk_score"] >= 65:
        reasons.append("recent volatility is high")
    if row["liquidity_risk_score"] >= 50:
        reasons.append("liquidity or participation risk is meaningful")
    if text_value(row.get("financial_warning")):
        reasons.append(f"financial warning: {row.get('financial_warning')}")
    if text_value(row.get("technical_warning")):
        reasons.append(f"technical warning: {row.get('technical_warning')}")

    if not reasons:
        return "No major risk warning from current rules, but this remains a high-growth equity screen."
    return "; ".join(reasons)


def build_risk_scores(screening_df: pd.DataFrame, priority_df: pd.DataFrame) -> pd.DataFrame:
    priority_cols = [
        "ticker",
        "final_priority",
        "priority_score",
        "enhanced_backtest_score",
        "current_risk_level",
    ]
    merged = screening_df.merge(
        priority_df[[column for column in priority_cols if column in priority_df.columns]],
        on="ticker",
        how="left",
    )

    merged["volatility_risk_score"] = merged.apply(volatility_risk_score, axis=1)
    merged["liquidity_risk_score"] = merged.apply(liquidity_risk_score, axis=1)
    merged["financial_risk_score"] = merged.apply(financial_risk_score, axis=1)
    merged["valuation_risk_score"] = merged.apply(valuation_risk_score, axis=1)
    merged["technical_risk_score"] = merged.apply(technical_risk_score, axis=1)

    merged["overall_risk_score"] = (
        merged["volatility_risk_score"] * 0.20
        + merged["liquidity_risk_score"] * 0.10
        + merged["financial_risk_score"] * 0.25
        + merged["valuation_risk_score"] * 0.20
        + merged["technical_risk_score"] * 0.25
    ).round().astype(int)
    merged["risk_label"] = merged["overall_risk_score"].apply(risk_label)
    merged["risk_reason"] = merged.apply(risk_reason, axis=1)

    output_columns = [
        "ticker",
        "signal",
        "strategy_role",
        "final_priority",
        "priority_score",
        "overall_risk_score",
        "risk_label",
        "volatility_risk_score",
        "liquidity_risk_score",
        "financial_risk_score",
        "valuation_risk_score",
        "technical_risk_score",
        "technical_warning",
        "financial_warning",
        "risk_reason",
    ]
    return merged[output_columns].sort_values(
        by=["overall_risk_score", "priority_score"],
        ascending=[False, False],
    )


def write_final_report(
    risk_df: pd.DataFrame,
    priority_df: pd.DataFrame,
    enhanced_df: pd.DataFrame | None,
    interpretation_df: pd.DataFrame | None,
) -> None:
    with pd.ExcelWriter(FINAL_REPORT_XLSX, engine="openpyxl") as writer:
        priority_df.to_excel(writer, sheet_name="Final_Daily_Priority", index=False)
        risk_df.to_excel(writer, sheet_name="Risk_Score", index=False)
        if enhanced_df is not None:
            enhanced_df.to_excel(
                writer, sheet_name="Enhanced_Backtest_By_Signal", index=False
            )
        if interpretation_df is not None:
            interpretation_df.to_excel(
                writer, sheet_name="Signal_Interpretation", index=False
            )


def main() -> None:
    if not required_inputs_exist():
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    screening_df = pd.read_csv(SCREENING_CSV)
    priority_df = pd.read_csv(PRIORITY_CSV)
    enhanced_df = (
        pd.read_csv(ENHANCED_SUMMARY_CSV) if ENHANCED_SUMMARY_CSV.exists() else None
    )
    interpretation_df = (
        pd.read_csv(INTERPRETATION_CSV) if INTERPRETATION_CSV.exists() else None
    )

    risk_df = build_risk_scores(screening_df, priority_df)
    risk_df.to_csv(RISK_SCORE_CSV, index=False)
    risk_df.to_excel(RISK_SCORE_XLSX, index=False, engine="openpyxl")
    write_final_report(risk_df, priority_df, enhanced_df, interpretation_df)

    print(f"Wrote {RISK_SCORE_CSV}")
    print(f"Wrote {RISK_SCORE_XLSX}")
    print(f"Updated {FINAL_REPORT_XLSX} with Risk_Score sheet")
    print(f"Scored tickers: {len(risk_df)}")
    print("Done. Risk scores are research context only, not investment advice.")


if __name__ == "__main__":
    main()
