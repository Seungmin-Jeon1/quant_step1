from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

SCREENING_CSV = BASE_DIR / "screening" / "output" / "growth_rebound_screen.csv"
INTERPRETATION_CSV = (
    BASE_DIR / "backtesting" / "output" / "growth_signal_backtest_interpretation.csv"
)
ENHANCED_SUMMARY_CSV = (
    BASE_DIR / "backtesting" / "output" / "growth_signal_enhanced_backtest_summary.csv"
)

DAILY_PRIORITY_CSV = OUTPUT_DIR / "daily_growth_priority.csv"
DAILY_PRIORITY_XLSX = OUTPUT_DIR / "daily_growth_priority.xlsx"
DAILY_PRIORITY_REPORT_XLSX = OUTPUT_DIR / "daily_growth_priority_report.xlsx"
FINAL_DAILY_REPORT_XLSX = OUTPUT_DIR / "final_daily_research_report.xlsx"

MISSING_INPUT_MESSAGE = (
    "Required input files not found. Please run py .\\screening\\screen_stocks.py "
    "and py .\\backtesting\\analyze_backtest.py first."
)

SIGNAL_SCORES = {
    "Pullback Watch": 35,
    "Trend Positive": 25,
    "High Volume Risk Monitor": 15,
    "Weak Trend / Low Volume": 10,
    "Early Watch": 10,
    "Confirmed Watch": 30,
    "Neutral": 0,
    "Data Issue": -10,
    "Error": -50,
}

EFFECTIVENESS_SCORES = {
    "Strong": 30,
    "Moderate": 15,
    "Weak": -20,
    "Inconclusive": -5,
}

RISK_RATING_SCORES = {
    "Lower Relative Risk": 10,
    "Medium Risk": 5,
    "Medium-High Risk": -5,
    "High Risk": -15,
    "Insufficient Risk Data": -5,
}

CURRENT_RISK_LEVEL_SCORES = {
    "Medium": 5,
    "Medium-High": -5,
    "High": -15,
    "Very High": -25,
    "Unknown": -10,
}


def required_inputs_exist() -> bool:
    missing = [path for path in [SCREENING_CSV, INTERPRETATION_CSV] if not path.exists()]
    if not missing:
        return True

    print(MISSING_INPUT_MESSAGE)
    print("Missing files:")
    for path in missing:
        print(f"- {path}")
    return False


def text_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value)


def contains_text(value: Any, needle: str) -> bool:
    return needle.lower() in text_value(value).lower()


def warning_adjustment(technical_warning: Any, financial_warning: Any) -> int:
    score = 0

    technical_rules = {
        "Short-term Extended": -10,
        "Overbought": -10,
        "Below Trend / Weak Volume": -10,
        "High Volume Below Trend": -5,
        "Trend Positive but Volume Weak": -5,
        "Pullback with Weak Volume": -5,
    }
    for text, adjustment in technical_rules.items():
        if contains_text(technical_warning, text):
            score += adjustment

    financial_text = text_value(financial_warning)
    if financial_text:
        score -= 5
    if contains_text(financial_text, "Extreme PSR"):
        score -= 5
    if contains_text(financial_text, "Negative P/B"):
        score -= 5

    return score


def priority_score(row: pd.Series) -> int:
    score = 0
    score += SIGNAL_SCORES.get(text_value(row.get("signal")), 0)
    score += EFFECTIVENESS_SCORES.get(text_value(row.get("effectiveness_rating")), -5)
    score += RISK_RATING_SCORES.get(text_value(row.get("risk_rating")), -5)
    score += CURRENT_RISK_LEVEL_SCORES.get(text_value(row.get("risk_level")), -10)
    score += warning_adjustment(row.get("technical_warning"), row.get("financial_warning"))
    score += enhanced_backtest_score(row)
    return int(score)


def final_priority(score: int) -> str:
    if score >= 80:
        return "Very High"
    if score >= 60:
        return "High"
    if score >= 40:
        return "Medium-High"
    if score >= 20:
        return "Medium"
    if score >= 0:
        return "Low"
    return "Avoid / Review Only"


def enhanced_backtest_score(row: pd.Series) -> int:
    if not enhanced_data_available(row):
        return 0

    score = 0
    avg_net_20d = numeric_value(row.get("avg_net_return_20d_after_cost"))
    excess_spy = numeric_value(row.get("avg_excess_return_20d_vs_spy"))
    excess_qqq = numeric_value(row.get("avg_excess_return_20d_vs_qqq"))
    payoff = numeric_value(row.get("payoff_ratio_20d"))
    stop_loss = numeric_value(row.get("stop_loss_20d_hit_rate"))
    take_profit = numeric_value(row.get("take_profit_20d_hit_rate"))

    if avg_net_20d is not None:
        if avg_net_20d >= 0.10:
            score += 25
        elif avg_net_20d >= 0.05:
            score += 15
        elif avg_net_20d >= 0:
            score += 5
        else:
            score -= 15

    if excess_spy is not None:
        score += 10 if excess_spy > 0 else -5
    if excess_qqq is not None:
        score += 10 if excess_qqq > 0 else -5

    if payoff is not None:
        if payoff >= 1.5:
            score += 10
        elif payoff >= 1.0:
            score += 5
        else:
            score -= 10

    if stop_loss is not None:
        if stop_loss >= 0.40:
            score -= 15
        elif stop_loss >= 0.25:
            score -= 5
        else:
            score += 5

    if take_profit is not None:
        if take_profit >= 0.30:
            score += 10
        elif take_profit >= 0.15:
            score += 5

    return int(score)


def numeric_value(value: Any) -> float | None:
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def enhanced_data_available(row: pd.Series) -> bool:
    return numeric_value(row.get("avg_net_return_20d_after_cost")) is not None


def ranking_reason(row: pd.Series) -> str:
    signal = text_value(row.get("signal")) or "Unknown signal"
    effectiveness = text_value(row.get("effectiveness_rating")) or "Inconclusive"
    strategy_role = text_value(row.get("strategy_role")) or "Review Manually"
    current_risk = text_value(row.get("risk_level")) or "Unknown"
    risk_rating = text_value(row.get("risk_rating")) or "Insufficient Risk Data"

    reason = (
        f"{signal} is historically {effectiveness.lower()} and is marked as "
        f"{strategy_role}; current risk is {current_risk} and backtest risk is "
        f"{risk_rating}."
    )

    if enhanced_data_available(row):
        reason += (
            " Enhanced backtest: "
            f"20D net after cost {format_percent(row.get('avg_net_return_20d_after_cost'))}, "
            f"excess vs SPY {format_percent(row.get('avg_excess_return_20d_vs_spy'))}, "
            f"excess vs QQQ {format_percent(row.get('avg_excess_return_20d_vs_qqq'))}, "
            f"payoff ratio {format_number(row.get('payoff_ratio_20d'))}."
        )
    else:
        reason += " Enhanced backtest data unavailable."

    warning_notes = []
    if text_value(row.get("technical_warning")):
        warning_notes.append(f"technical warning: {row.get('technical_warning')}")
    if text_value(row.get("financial_warning")):
        warning_notes.append(f"financial warning: {row.get('financial_warning')}")
    if warning_notes:
        reason += " " + " ".join(warning_notes)

    return reason


def format_percent(value: Any) -> str:
    number = numeric_value(value)
    if number is None:
        return "n/a"
    return f"{number:.2%}"


def format_number(value: Any) -> str:
    number = numeric_value(value)
    if number is None:
        return "n/a"
    return f"{number:.2f}"


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    screening_df = pd.read_csv(SCREENING_CSV)
    interpretation_df = pd.read_csv(INTERPRETATION_CSV)
    enhanced_df = None
    if ENHANCED_SUMMARY_CSV.exists():
        enhanced_df = pd.read_csv(ENHANCED_SUMMARY_CSV)
    else:
        print(
            "Enhanced backtest summary not found. Run py .\\backtesting\\enhance_backtest_growth.py for improved ranking."
        )
    return screening_df, interpretation_df, enhanced_df


def build_priority(
    screening_df: pd.DataFrame,
    interpretation_df: pd.DataFrame,
    enhanced_df: pd.DataFrame | None,
) -> pd.DataFrame:
    backtest_columns = [
        "signal",
        "effectiveness_rating",
        "risk_rating",
        "recommended_use",
        "key_evidence",
    ]
    if "strategy_role" in interpretation_df.columns:
        backtest_columns.insert(1, "strategy_role")

    merged = screening_df.merge(
        interpretation_df[backtest_columns],
        on="signal",
        how="left",
        suffixes=("", "_backtest"),
    )

    enhanced_columns = [
        "signal",
        "avg_return_10d",
        "avg_net_return_20d_after_cost",
        "avg_excess_return_20d_vs_spy",
        "avg_excess_return_20d_vs_qqq",
        "payoff_ratio_20d",
        "stop_loss_20d_hit_rate",
        "take_profit_20d_hit_rate",
    ]
    if enhanced_df is not None:
        available_columns = [
            column for column in enhanced_columns if column in enhanced_df.columns
        ]
        merged = merged.merge(
            enhanced_df[available_columns],
            on="signal",
            how="left",
        )
    else:
        for column in enhanced_columns:
            if column != "signal":
                merged[column] = "Not Available"

    if "strategy_role_backtest" in merged.columns:
        merged["strategy_role"] = merged["strategy_role"].fillna(
            merged["strategy_role_backtest"]
        )
        merged = merged.drop(columns=["strategy_role_backtest"])

    merged["effectiveness_rating"] = merged["effectiveness_rating"].fillna(
        "Inconclusive"
    )
    merged["risk_rating"] = merged["risk_rating"].fillna("Insufficient Risk Data")
    merged["recommended_use"] = merged["recommended_use"].fillna("Review Manually")
    merged["key_backtest_evidence"] = merged["key_evidence"].fillna(
        "No backtest interpretation available"
    )
    merged["strategy_role"] = merged["strategy_role"].fillna("Review Manually")
    enhanced_value_columns = [
        "avg_return_10d",
        "avg_net_return_20d_after_cost",
        "avg_excess_return_20d_vs_spy",
        "avg_excess_return_20d_vs_qqq",
        "payoff_ratio_20d",
        "stop_loss_20d_hit_rate",
        "take_profit_20d_hit_rate",
    ]
    for column in enhanced_value_columns:
        if column not in merged.columns:
            merged[column] = "Not Available"

    merged["payoff_ratio"] = merged["payoff_ratio_20d"]
    merged["stop_loss_hit_rate"] = merged["stop_loss_20d_hit_rate"]
    merged["take_profit_hit_rate"] = merged["take_profit_20d_hit_rate"]
    merged["enhanced_backtest_score"] = merged.apply(enhanced_backtest_score, axis=1)

    merged["priority_score"] = merged.apply(priority_score, axis=1)
    merged["final_priority"] = merged["priority_score"].apply(final_priority)
    merged["current_risk_level"] = merged["risk_level"]
    merged["ranking_reason"] = merged.apply(ranking_reason, axis=1)

    output_columns = [
        "ticker",
        "signal",
        "strategy_role",
        "final_priority",
        "priority_score",
        "enhanced_backtest_score",
        "effectiveness_rating",
        "risk_rating",
        "recommended_use",
        "avg_return_10d",
        "avg_net_return_20d_after_cost",
        "avg_excess_return_20d_vs_spy",
        "avg_excess_return_20d_vs_qqq",
        "payoff_ratio",
        "stop_loss_hit_rate",
        "take_profit_hit_rate",
        "current_risk_level",
        "technical_warning",
        "financial_warning",
        "action_note",
        "ranking_reason",
        "key_backtest_evidence",
    ]
    priority_df = merged[output_columns].sort_values(
        by=["priority_score", "ticker"],
        ascending=[False, True],
    )
    return priority_df.reset_index(drop=True)


def write_outputs(
    priority_df: pd.DataFrame,
    screening_df: pd.DataFrame,
    interpretation_df: pd.DataFrame,
    enhanced_df: pd.DataFrame | None,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    priority_df.to_csv(DAILY_PRIORITY_CSV, index=False)
    priority_df.to_excel(DAILY_PRIORITY_XLSX, index=False, engine="openpyxl")

    with pd.ExcelWriter(DAILY_PRIORITY_REPORT_XLSX, engine="openpyxl") as writer:
        priority_df.to_excel(writer, sheet_name="Daily_Priority", index=False)
        screening_df.to_excel(writer, sheet_name="Current_Screening", index=False)
        interpretation_df.to_excel(
            writer, sheet_name="Signal_Backtest_Interpretation", index=False
        )
        if enhanced_df is not None:
            enhanced_df.to_excel(
                writer, sheet_name="Enhanced_Backtest_By_Signal", index=False
            )

    with pd.ExcelWriter(FINAL_DAILY_REPORT_XLSX, engine="openpyxl") as writer:
        priority_df.to_excel(writer, sheet_name="Final_Daily_Priority", index=False)
        if enhanced_df is not None:
            enhanced_df.to_excel(
                writer, sheet_name="Enhanced_Backtest_By_Signal", index=False
            )
        interpretation_df.to_excel(
            writer, sheet_name="Signal_Interpretation", index=False
        )

    print(f"Wrote {DAILY_PRIORITY_CSV}")
    print(f"Wrote {DAILY_PRIORITY_XLSX}")
    print(f"Wrote {DAILY_PRIORITY_REPORT_XLSX}")
    print(f"Wrote {FINAL_DAILY_REPORT_XLSX}")


def main() -> None:
    if not required_inputs_exist():
        return

    screening_df, interpretation_df, enhanced_df = load_inputs()
    priority_df = build_priority(screening_df, interpretation_df, enhanced_df)
    write_outputs(priority_df, screening_df, interpretation_df, enhanced_df)

    print(f"Ranked tickers: {len(priority_df)}")
    print("Done. Ranking is for research prioritization only, not investment advice.")


if __name__ == "__main__":
    main()
