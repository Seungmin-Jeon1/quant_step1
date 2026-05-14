from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"
FINAL_REPORT_XLSX = OUTPUT_DIR / "final_daily_research_report.xlsx"

PIPELINE_STEPS = [
    ("Current screener", PROJECT_ROOT / "screening" / "screen_stocks.py"),
    ("Signal backtest", PROJECT_ROOT / "backtesting" / "backtest_growth.py"),
    ("Backtest interpretation", PROJECT_ROOT / "backtesting" / "analyze_backtest.py"),
    ("Enhanced backtest", PROJECT_ROOT / "backtesting" / "enhance_backtest_growth.py"),
    ("Daily priority ranking", PROJECT_ROOT / "rank_screening_results.py"),
    ("Growth risk score", PROJECT_ROOT / "risk" / "risk_score_growth.py"),
    ("Long-term quality score", PROJECT_ROOT / "long_term_quality_score.py"),
    ("Event risk check", PROJECT_ROOT / "event_risk_checker.py"),
]

PRIORITY_CSV = OUTPUT_DIR / "daily_growth_priority.csv"
RISK_CSV = OUTPUT_DIR / "growth_risk_score.csv"
QUALITY_CSV = OUTPUT_DIR / "long_term_growth_quality.csv"
EVENT_CSV = OUTPUT_DIR / "growth_event_risk.csv"
ENHANCED_SUMMARY_CSV = (
    PROJECT_ROOT / "backtesting" / "output" / "growth_signal_enhanced_backtest_summary.csv"
)
INTERPRETATION_CSV = (
    PROJECT_ROOT / "backtesting" / "output" / "growth_signal_backtest_interpretation.csv"
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


def read_csv_if_exists(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def run_step(step_name: str, script_path: Path) -> None:
    print(f"\n=== {step_name} ===")
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=PROJECT_ROOT,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"{step_name} failed with exit code {result.returncode}.")


def key_metric_rows(
    priority_df: pd.DataFrame | None,
    risk_df: pd.DataFrame | None,
    quality_df: pd.DataFrame | None,
    event_df: pd.DataFrame | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = [
        {
            "metric": "report_generated_at",
            "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "note": "Local run timestamp.",
        }
    ]

    if priority_df is not None and not priority_df.empty:
        top = priority_df.iloc[0]
        rows.append(
            {
                "metric": "top_daily_priority",
                "value": text_value(top.get("ticker")),
                "note": (
                    f"{text_value(top.get('final_priority'))}; "
                    f"signal={text_value(top.get('signal'))}; "
                    f"score={text_value(top.get('priority_score'))}"
                ),
            }
        )
        high_count = priority_df[
            priority_df["final_priority"].isin(["Very High", "High", "Medium-High"])
        ].shape[0]
        rows.append(
            {
                "metric": "medium_high_or_better_priority_count",
                "value": high_count,
                "note": "Research priority count, not a buy list.",
            }
        )

    if risk_df is not None and not risk_df.empty:
        high_risk_count = risk_df[
            risk_df["risk_label"].isin(["High", "Very High"])
        ].shape[0]
        rows.append(
            {
                "metric": "high_or_very_high_risk_count",
                "value": high_risk_count,
                "note": "Use this to separate research priority from caution level.",
            }
        )

    if quality_df is not None and not quality_df.empty:
        type_a_count = quality_df[
            quality_df["candidate_type"].astype(str).str.contains("Type A", na=False)
        ].shape[0]
        rows.append(
            {
                "metric": "type_a_priority_quality_count",
                "value": type_a_count,
                "note": "Tickers with stronger mix of priority, risk, and quality.",
            }
        )

    if event_df is not None and not event_df.empty:
        event_review_count = event_df[event_df["needs_manual_review"] == True].shape[0]
        rows.append(
            {
                "metric": "event_manual_review_count",
                "value": event_review_count,
                "note": "Tickers that need recent news/event context checked manually.",
            }
        )

    return rows


def build_executive_summary(
    priority_df: pd.DataFrame | None,
    risk_df: pd.DataFrame | None,
    quality_df: pd.DataFrame | None,
    event_df: pd.DataFrame | None,
) -> pd.DataFrame:
    rows = key_metric_rows(priority_df, risk_df, quality_df, event_df)

    if priority_df is not None and not priority_df.empty:
        risk_lookup = (
            risk_df.set_index("ticker") if risk_df is not None and "ticker" in risk_df else None
        )
        quality_lookup = (
            quality_df.set_index("ticker")
            if quality_df is not None and "ticker" in quality_df
            else None
        )
        event_lookup = (
            event_df.set_index("ticker") if event_df is not None and "ticker" in event_df else None
        )

        for _, row in priority_df.head(5).iterrows():
            ticker = text_value(row.get("ticker"))
            risk_label = ""
            quality_label = ""
            event_risk = ""
            if risk_lookup is not None and ticker in risk_lookup.index:
                risk_label = text_value(risk_lookup.loc[ticker].get("risk_label"))
            if quality_lookup is not None and ticker in quality_lookup.index:
                quality_label = text_value(
                    quality_lookup.loc[ticker].get("long_term_quality_label")
                )
            if event_lookup is not None and ticker in event_lookup.index:
                event_risk = text_value(event_lookup.loc[ticker].get("event_risk_level"))

            rows.append(
                {
                    "metric": f"top_watch_{ticker}",
                    "value": text_value(row.get("final_priority")),
                    "note": (
                        f"signal={text_value(row.get('signal'))}; "
                        f"risk={risk_label or 'n/a'}; "
                        f"quality={quality_label or 'n/a'}; "
                        f"event_risk={event_risk or 'n/a'}"
                    ),
                }
            )

    rows.append(
        {
            "metric": "disclaimer",
            "value": "research_only",
            "note": (
                "This report is not investment advice, not a price prediction, "
                "and not a trading or brokerage system."
            ),
        }
    )
    return pd.DataFrame(rows, columns=["metric", "value", "note"])


def write_final_report() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    priority_df = read_csv_if_exists(PRIORITY_CSV)
    risk_df = read_csv_if_exists(RISK_CSV)
    quality_df = read_csv_if_exists(QUALITY_CSV)
    event_df = read_csv_if_exists(EVENT_CSV)
    enhanced_df = read_csv_if_exists(ENHANCED_SUMMARY_CSV)
    interpretation_df = read_csv_if_exists(INTERPRETATION_CSV)
    summary_df = build_executive_summary(priority_df, risk_df, quality_df, event_df)

    with pd.ExcelWriter(FINAL_REPORT_XLSX, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Executive_Summary", index=False)
        if priority_df is not None:
            priority_df.to_excel(writer, sheet_name="Final_Daily_Priority", index=False)
        if risk_df is not None:
            risk_df.to_excel(writer, sheet_name="Risk_Score", index=False)
        if quality_df is not None:
            quality_df.to_excel(writer, sheet_name="Long_Term_Quality", index=False)
        if event_df is not None:
            event_df.to_excel(writer, sheet_name="Event_Risk_Check", index=False)
        if enhanced_df is not None:
            enhanced_df.to_excel(
                writer, sheet_name="Enhanced_Backtest_By_Signal", index=False
            )
        if interpretation_df is not None:
            interpretation_df.to_excel(
                writer, sheet_name="Signal_Interpretation", index=False
            )

    print(f"\nWrote final report with Executive_Summary: {FINAL_REPORT_XLSX}")


def main() -> None:
    print("Starting quant_step1 daily report pipeline.")
    print("This is a research workflow only. It does not place trades.")

    for step_name, script_path in PIPELINE_STEPS:
        run_step(step_name, script_path)

    write_final_report()
    print("Done. Open output/final_daily_research_report.xlsx first.")


if __name__ == "__main__":
    main()
