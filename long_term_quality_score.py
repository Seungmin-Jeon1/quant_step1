from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

SCREENING_CSV = BASE_DIR / "screening" / "output" / "growth_rebound_screen.csv"
PRIORITY_CSV = OUTPUT_DIR / "daily_growth_priority.csv"
RISK_CSV = OUTPUT_DIR / "growth_risk_score.csv"
FINAL_REPORT_XLSX = OUTPUT_DIR / "final_daily_research_report.xlsx"

QUALITY_CSV = OUTPUT_DIR / "long_term_growth_quality.csv"
QUALITY_XLSX = OUTPUT_DIR / "long_term_growth_quality.xlsx"

MISSING_INPUT_MESSAGE = (
    "Required input files not found. Please run py .\\screening\\screen_stocks.py, "
    "py .\\rank_screening_results.py, and py .\\risk\\risk_score_growth.py first."
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


def clamp(score: float, low: int = 0, high: int = 100) -> int:
    return int(max(low, min(high, round(score))))


def required_inputs_exist() -> bool:
    missing = [
        path for path in [SCREENING_CSV, PRIORITY_CSV, RISK_CSV] if not path.exists()
    ]
    if not missing:
        return True

    print(MISSING_INPUT_MESSAGE)
    print("Missing files:")
    for path in missing:
        print(f"- {path}")
    return False


def revenue_growth_score(row: pd.Series) -> int:
    growth = number_value(row.get("revenue_growth"))
    revenue = number_value(row.get("revenue"))
    if growth is None:
        return 30

    score = 0
    if growth >= 0.50:
        score = 85
    elif growth >= 0.20:
        score = 70
    elif growth >= 0.05:
        score = 55
    elif growth >= 0:
        score = 40
    else:
        score = 20

    if revenue is not None and revenue < 50_000_000 and growth > 1.0:
        score -= 20
    return clamp(score)


def profitability_score(row: pd.Series) -> int:
    profit_margin = number_value(row.get("profit_margin"))
    operating_margin = number_value(row.get("operating_margin"))
    net_income = number_value(row.get("net_income"))

    score = 50
    if profit_margin is not None:
        if profit_margin > 0.15:
            score += 25
        elif profit_margin > 0:
            score += 10
        else:
            score -= 20
    else:
        score -= 10

    if operating_margin is not None:
        if operating_margin > 0.10:
            score += 20
        elif operating_margin > 0:
            score += 10
        else:
            score -= 20
    else:
        score -= 10

    if net_income is not None and net_income < 0:
        score -= 15

    return clamp(score)


def cash_runway_score(row: pd.Series) -> int:
    total_cash = number_value(row.get("total_cash"))
    free_cash_flow = number_value(row.get("free_cash_flow"))
    operating_cash_flow = number_value(row.get("operating_cash_flow"))

    if total_cash is None:
        return 25

    burn = None
    if free_cash_flow is not None and free_cash_flow < 0:
        burn = abs(free_cash_flow)
    elif operating_cash_flow is not None and operating_cash_flow < 0:
        burn = abs(operating_cash_flow)

    if burn is None or burn == 0:
        return 80

    runway_years = total_cash / burn
    if runway_years >= 3:
        return 85
    if runway_years >= 2:
        return 70
    if runway_years >= 1:
        return 50
    if runway_years >= 0.5:
        return 30
    return 15


def debt_risk_score(row: pd.Series) -> int:
    total_cash = number_value(row.get("total_cash"))
    total_debt = number_value(row.get("total_debt"))

    if total_cash is None or total_cash == 0:
        return 25
    if total_debt is None:
        return 45

    debt_to_cash = total_debt / total_cash
    if debt_to_cash < 0.25:
        return 85
    if debt_to_cash < 0.75:
        return 70
    if debt_to_cash < 1.5:
        return 50
    if debt_to_cash < 2.5:
        return 30
    return 15


def valuation_risk_score(row: pd.Series) -> int:
    price_to_sales = number_value(row.get("price_to_sales"))
    price_to_book = number_value(row.get("price_to_book"))

    score = 70
    if price_to_sales is None:
        score -= 15
    elif price_to_sales > 100:
        score -= 45
    elif price_to_sales > 50:
        score -= 35
    elif price_to_sales > 20:
        score -= 25
    elif price_to_sales > 10:
        score -= 15
    elif price_to_sales < 5:
        score += 10

    if price_to_book is not None and price_to_book < 0:
        score -= 30
    elif price_to_book is not None and price_to_book > 30:
        score -= 15

    if has_text(row.get("financial_warning"), "Extreme PSR"):
        score -= 15
    if has_text(row.get("financial_warning"), "Negative P/B"):
        score -= 15

    return clamp(score)


def free_cash_flow_score(row: pd.Series) -> int:
    free_cash_flow = number_value(row.get("free_cash_flow"))
    operating_cash_flow = number_value(row.get("operating_cash_flow"))
    revenue = number_value(row.get("revenue"))

    if free_cash_flow is None:
        return 35
    if free_cash_flow > 0:
        score = 75
        if revenue not in (None, 0) and free_cash_flow / revenue > 0.10:
            score += 15
        return clamp(score)

    score = 35
    if operating_cash_flow is not None and operating_cash_flow > 0:
        score += 15
    if revenue not in (None, 0) and abs(free_cash_flow) / revenue > 1.0:
        score -= 20
    return clamp(score)


def dilution_risk_score(row: pd.Series) -> int:
    total_cash = number_value(row.get("total_cash"))
    free_cash_flow = number_value(row.get("free_cash_flow"))
    market_cap = number_value(row.get("market_cap"))

    score = 70
    if free_cash_flow is not None and free_cash_flow < 0:
        score -= 20
        if market_cap not in (None, 0):
            burn_to_market_cap = abs(free_cash_flow) / market_cap
            if burn_to_market_cap > 0.20:
                score -= 25
            elif burn_to_market_cap > 0.10:
                score -= 15
            elif burn_to_market_cap > 0.05:
                score -= 5

    if total_cash is None:
        score -= 15
    elif free_cash_flow is not None and free_cash_flow < 0:
        runway_years = total_cash / abs(free_cash_flow) if free_cash_flow != 0 else None
        if runway_years is not None and runway_years < 1:
            score -= 20

    return clamp(score)


def business_quality_score(row: pd.Series) -> int:
    score = 50
    revenue = number_value(row.get("revenue"))
    revenue_growth = number_value(row.get("revenue_growth"))
    operating_cash_flow = number_value(row.get("operating_cash_flow"))
    free_cash_flow = number_value(row.get("free_cash_flow"))

    if revenue is not None:
        if revenue >= 500_000_000:
            score += 20
        elif revenue >= 100_000_000:
            score += 10
        elif revenue < 10_000_000:
            score -= 20

    if revenue_growth is not None and revenue_growth > 0.20:
        score += 15
    elif revenue_growth is not None and revenue_growth < 0:
        score -= 15

    if operating_cash_flow is not None and operating_cash_flow > 0:
        score += 10
    if free_cash_flow is not None and free_cash_flow > 0:
        score += 10

    if has_text(row.get("financial_warning"), "Extreme revenue growth"):
        score -= 10

    return clamp(score)


def quality_label(score: int) -> str:
    if score >= 75:
        return "High"
    if score >= 55:
        return "Medium"
    if score >= 35:
        return "Speculative"
    return "Low"


def candidate_type(row: pd.Series) -> str:
    priority = text_value(row.get("final_priority"))
    risk = text_value(row.get("risk_label"))
    quality = text_value(row.get("long_term_quality_label"))

    high_priority = priority in {"Very High", "High", "Medium-High"}
    high_quality = quality in {"High", "Medium"}
    high_risk = risk in {"High", "Very High"}

    if high_priority and high_quality and not high_risk:
        return "Type A: Priority + Quality"
    if high_priority and not high_quality:
        return "Type B: Trading Watch / Quality Risk"
    if not high_priority and high_quality:
        return "Type C: Long-Term Watchlist"
    return "Type D: Low Priority / Low Quality or High Risk"


def quality_reason(row: pd.Series) -> str:
    reasons = []
    if row["revenue_growth_score"] >= 70:
        reasons.append("strong revenue growth")
    elif row["revenue_growth_score"] <= 35:
        reasons.append("weak or questionable revenue growth")

    if row["cash_runway_score"] >= 70:
        reasons.append("cash runway appears relatively healthier")
    elif row["cash_runway_score"] <= 35:
        reasons.append("cash runway or burn profile is a concern")

    if row["free_cash_flow_score"] >= 70:
        reasons.append("free cash flow profile is supportive")
    elif row["free_cash_flow_score"] <= 35:
        reasons.append("free cash flow profile is weak")

    if row["valuation_risk_score"] <= 35:
        reasons.append("valuation metrics are stretched or distorted")
    if row["profitability_score"] <= 35:
        reasons.append("profitability remains weak")
    if text_value(row.get("financial_warning")):
        reasons.append(f"financial warning: {row.get('financial_warning')}")

    if not reasons:
        return "Mixed long-term quality profile; review business progress manually."
    return "; ".join(reasons)


def build_quality_scores(
    screening_df: pd.DataFrame,
    priority_df: pd.DataFrame,
    risk_df: pd.DataFrame,
) -> pd.DataFrame:
    priority_cols = ["ticker", "final_priority", "priority_score"]
    risk_cols = ["ticker", "overall_risk_score", "risk_label"]
    merged = screening_df.merge(priority_df[priority_cols], on="ticker", how="left")
    merged = merged.merge(risk_df[risk_cols], on="ticker", how="left")

    merged["revenue_growth_score"] = merged.apply(revenue_growth_score, axis=1)
    merged["profitability_score"] = merged.apply(profitability_score, axis=1)
    merged["cash_runway_score"] = merged.apply(cash_runway_score, axis=1)
    merged["debt_risk_score"] = merged.apply(debt_risk_score, axis=1)
    merged["valuation_risk_score"] = merged.apply(valuation_risk_score, axis=1)
    merged["free_cash_flow_score"] = merged.apply(free_cash_flow_score, axis=1)
    merged["dilution_risk_score"] = merged.apply(dilution_risk_score, axis=1)
    merged["business_quality_score"] = merged.apply(business_quality_score, axis=1)

    merged["long_term_quality_score"] = (
        merged["revenue_growth_score"] * 0.15
        + merged["profitability_score"] * 0.15
        + merged["cash_runway_score"] * 0.15
        + merged["debt_risk_score"] * 0.10
        + merged["valuation_risk_score"] * 0.15
        + merged["free_cash_flow_score"] * 0.15
        + merged["dilution_risk_score"] * 0.05
        + merged["business_quality_score"] * 0.10
    ).round().astype(int)

    merged["long_term_quality_label"] = merged["long_term_quality_score"].apply(
        quality_label
    )
    merged["candidate_type"] = merged.apply(candidate_type, axis=1)
    merged["long_term_quality_reason"] = merged.apply(quality_reason, axis=1)

    output_columns = [
        "ticker",
        "signal",
        "strategy_role",
        "final_priority",
        "priority_score",
        "risk_label",
        "overall_risk_score",
        "long_term_quality_score",
        "long_term_quality_label",
        "candidate_type",
        "revenue_growth_score",
        "profitability_score",
        "cash_runway_score",
        "debt_risk_score",
        "valuation_risk_score",
        "free_cash_flow_score",
        "dilution_risk_score",
        "business_quality_score",
        "long_term_quality_reason",
    ]
    return merged[output_columns].sort_values(
        by=["long_term_quality_score", "priority_score"],
        ascending=[False, False],
    )


def update_final_report(
    quality_df: pd.DataFrame,
    priority_df: pd.DataFrame,
    risk_df: pd.DataFrame,
) -> None:
    enhanced_path = BASE_DIR / "backtesting" / "output" / "growth_signal_enhanced_backtest_summary.csv"
    interpretation_path = (
        BASE_DIR / "backtesting" / "output" / "growth_signal_backtest_interpretation.csv"
    )
    enhanced_df = pd.read_csv(enhanced_path) if enhanced_path.exists() else None
    interpretation_df = (
        pd.read_csv(interpretation_path) if interpretation_path.exists() else None
    )

    with pd.ExcelWriter(FINAL_REPORT_XLSX, engine="openpyxl") as writer:
        priority_df.to_excel(writer, sheet_name="Final_Daily_Priority", index=False)
        risk_df.to_excel(writer, sheet_name="Risk_Score", index=False)
        quality_df.to_excel(writer, sheet_name="Long_Term_Quality", index=False)
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
    risk_df = pd.read_csv(RISK_CSV)

    quality_df = build_quality_scores(screening_df, priority_df, risk_df)
    quality_df.to_csv(QUALITY_CSV, index=False)
    quality_df.to_excel(QUALITY_XLSX, index=False, engine="openpyxl")
    update_final_report(quality_df, priority_df, risk_df)

    print(f"Wrote {QUALITY_CSV}")
    print(f"Wrote {QUALITY_XLSX}")
    print(f"Updated {FINAL_REPORT_XLSX} with Long_Term_Quality sheet")
    print(f"Scored tickers: {len(quality_df)}")
    print(
        "Done. Long-term quality scores are research context only, not investment advice."
    )


if __name__ == "__main__":
    main()
