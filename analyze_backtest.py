from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_loader import load_config, output_dir_for  # noqa: E402
from signal_rules import strategy_role_for_signal  # noqa: E402


BASE_DIR = Path(__file__).resolve().parent
CONFIG = load_config()
OUTPUT_DIR = output_dir_for(BASE_DIR, CONFIG["backtest"])

SUMMARY_CSV = OUTPUT_DIR / "growth_signal_backtest_summary.csv"
BY_TICKER_CSV = OUTPUT_DIR / "growth_signal_backtest_by_ticker.csv"
TRADES_CSV = OUTPUT_DIR / "growth_signal_backtest_trades.csv"

INTERPRETATION_CSV = OUTPUT_DIR / "growth_signal_backtest_interpretation.csv"
INTERPRETATION_XLSX = OUTPUT_DIR / "growth_signal_backtest_interpretation.xlsx"
SCORECARD_XLSX = OUTPUT_DIR / "growth_signal_backtest_scorecard.xlsx"
TICKER_INSIGHTS_CSV = OUTPUT_DIR / "growth_signal_ticker_insights.csv"
TICKER_INSIGHTS_XLSX = OUTPUT_DIR / "growth_signal_ticker_insights.xlsx"

TRADES_SAMPLE_LIMIT = 500


def clean_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def percent(value: Any) -> str:
    number = clean_number(value)
    if number is None:
        return "n/a"
    return f"{number:.2%}"


def required_inputs_exist() -> bool:
    missing = [
        path
        for path in [SUMMARY_CSV, BY_TICKER_CSV, TRADES_CSV]
        if not path.exists()
    ]
    if not missing:
        return True

    print("Backtest output files not found. Please run python backtest_growth.py first.")
    print("Missing files:")
    for path in missing:
        print(f"- {path}")
    return False


def sample_size_quality(event_count: int) -> str:
    if event_count < 5:
        return "Very Small / Inconclusive"
    if event_count < 15:
        return "Small / Use Caution"
    if event_count < 30:
        return "Moderate"
    return "Good"


def best_horizon(row: pd.Series) -> str:
    candidates = {
        "5d": clean_number(row.get("avg_return_5d")),
        "20d": clean_number(row.get("avg_return_20d")),
        "60d": clean_number(row.get("avg_return_60d")),
    }
    valid = {key: value for key, value in candidates.items() if value is not None}
    if not valid:
        return "Insufficient Data"
    return max(valid, key=lambda key: valid[key])


def risk_rating(row: pd.Series) -> str:
    drawdown_60 = clean_number(row.get("avg_max_drawdown_60d"))
    drawdown_20 = clean_number(row.get("avg_max_drawdown_20d"))

    if drawdown_60 is None and drawdown_20 is None:
        return "Insufficient Risk Data"
    if drawdown_60 is not None and drawdown_60 <= -0.25:
        return "High Risk"
    if drawdown_60 is not None and drawdown_60 <= -0.15:
        return "Medium-High Risk"
    if drawdown_20 is not None and drawdown_20 <= -0.10:
        return "Medium Risk"
    return "Lower Relative Risk"


def effectiveness_rating(row: pd.Series, sample_quality: str) -> str:
    if sample_quality == "Very Small / Inconclusive":
        return "Inconclusive"

    avg_20 = clean_number(row.get("avg_return_20d"))
    avg_60 = clean_number(row.get("avg_return_60d"))
    win_20 = clean_number(row.get("win_rate_20d"))
    win_60 = clean_number(row.get("win_rate_60d"))

    values = [avg_20, avg_60, win_20, win_60]
    if sum(value is not None for value in values) < 3:
        return "Inconclusive"

    strong_return = (avg_20 is not None and avg_20 > 0.05) or (
        avg_60 is not None and avg_60 > 0.10
    )
    strong_win = (win_20 is not None and win_20 >= 0.55) or (
        win_60 is not None and win_60 >= 0.55
    )
    if strong_return and strong_win:
        return "Strong"

    moderate_return = (avg_20 is not None and avg_20 > 0) or (
        avg_60 is not None and avg_60 > 0
    )
    moderate_win = (win_20 is not None and win_20 >= 0.50) or (
        win_60 is not None and win_60 >= 0.50
    )
    if moderate_return and moderate_win:
        return "Moderate"

    weak_returns = (avg_20 is not None and avg_20 <= 0) and (
        avg_60 is not None and avg_60 <= 0
    )
    weak_wins = (win_20 is not None and win_20 < 0.50) and (
        win_60 is not None and win_60 < 0.50
    )
    if weak_returns or weak_wins:
        return "Weak"

    return "Inconclusive"


def recommended_use(signal: str, effectiveness: str, row: pd.Series) -> str:
    if signal == "Confirmed Watch":
        return {
            "Strong": "Potential Entry Signal",
            "Moderate": "Entry Signal with Risk Controls",
            "Weak": "Do Not Use Alone",
            "Inconclusive": "Needs More Data",
        }[effectiveness]
    if signal == "Early Watch":
        if effectiveness in {"Strong", "Moderate"}:
            return "Early Monitor Signal"
        if effectiveness == "Weak":
            return "Too Early / Wait for Confirmation"
        return "Needs More Data"
    if signal == "Trend Positive":
        return {
            "Strong": "Trend-Following Signal",
            "Moderate": "Trend Monitor",
            "Weak": "Trend Signal Not Reliable",
            "Inconclusive": "Needs More Data",
        }[effectiveness]
    if signal == "Pullback Watch":
        return {
            "Strong": "Pullback Opportunity Signal",
            "Moderate": "Watch for Recovery Confirmation",
            "Weak": "Pullback Risk / Avoid Early Entry",
            "Inconclusive": "Needs More Data",
        }[effectiveness]
    if signal == "High Volume Risk Monitor":
        if effectiveness in {"Strong", "Moderate"}:
            return "Volatility Monitor / Not Automatic Entry"
        if effectiveness == "Weak":
            return "Distribution Risk / Avoid as Entry Signal"
        return "Needs More Data"
    if signal == "Weak Trend / Low Volume":
        if effectiveness in {"Strong", "Moderate"}:
            return "Weak-Trend Reversal Monitor"
        if effectiveness == "Weak":
            return "Weak Trend Not Useful"
        return "Needs More Data"
    return "Review Manually"


def key_evidence(row: pd.Series) -> str:
    return (
        f"events={int(row['event_count'])}; "
        f"avg20d={percent(row.get('avg_return_20d'))}; "
        f"win20d={percent(row.get('win_rate_20d'))}; "
        f"avg60d={percent(row.get('avg_return_60d'))}; "
        f"win60d={percent(row.get('win_rate_60d'))}; "
        f"avgDD60d={percent(row.get('avg_max_drawdown_60d'))}"
    )


def interpretation_text(
    signal: str,
    effectiveness: str,
    risk: str,
    row: pd.Series,
) -> str:
    avg_20 = percent(row.get("avg_return_20d"))
    avg_60 = percent(row.get("avg_return_60d"))
    win_20 = percent(row.get("win_rate_20d"))
    drawdown_60 = percent(row.get("avg_max_drawdown_60d"))

    if signal == "Trend Positive":
        return (
            f"Trend Positive rated {effectiveness} with avg20d={avg_20}, "
            f"avg60d={avg_60}, and win20d={win_20}. It may be useful as a "
            "trend-following filter, but it should not be treated as a "
            "short-term entry trigger."
        )
    if signal == "Pullback Watch":
        return (
            f"Pullback Watch rated {effectiveness} with avg20d={avg_20}, "
            f"avg60d={avg_60}, and avgDD60d={drawdown_60}. If returns are weak "
            "or drawdowns are high, wait for 50MA recovery before relying on it."
        )
    if signal == "High Volume Risk Monitor":
        return (
            f"High Volume Risk Monitor rated {effectiveness} and carries {risk}. "
            "High volume below both moving averages can reflect accumulation or "
            "distribution, so it should not be used as a standalone entry signal."
        )
    if signal == "Weak Trend / Low Volume":
        return (
            "Weak Trend / Low Volume identifies stocks below the 200MA with "
            "weak volume. In this Growth / Space universe, historical results "
            "suggest it may capture pullback/reversal zones rather than pure "
            "avoid zones. Use it as a risk-and-reversal monitor, not a "
            "standalone avoid signal."
        )
    if signal == "Early Watch":
        return (
            f"Early Watch rated {effectiveness} with avg20d={avg_20}, avg60d={avg_60}, "
            f"and avgDD60d={drawdown_60}. Treat it as an early monitor signal, "
            "not a complete setup, unless confirmation improves."
        )
    if signal == "Confirmed Watch":
        return (
            f"Confirmed Watch rated {effectiveness} with avg20d={avg_20}, "
            f"avg60d={avg_60}, and win20d={win_20}. It is the most complete "
            "rebound setup, but still requires risk controls."
        )
    return (
        f"{signal} rated {effectiveness} with avg20d={avg_20}, avg60d={avg_60}, "
        f"and risk rating {risk}. Review manually."
    )


def build_signal_interpretation(summary_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in summary_df.iterrows():
        event_count = int(row["event_count"])
        signal = row["signal"]
        sample_quality = sample_size_quality(event_count)
        horizon = best_horizon(row)
        risk = risk_rating(row)
        effectiveness = effectiveness_rating(row, sample_quality)

        rows.append(
            {
                "signal": signal,
                "strategy_role": strategy_role_for_signal(signal),
                "event_count": event_count,
                "sample_size_quality": sample_quality,
                "best_horizon": horizon,
                "effectiveness_rating": effectiveness,
                "risk_rating": risk,
                "recommended_use": recommended_use(signal, effectiveness, row),
                "interpretation": interpretation_text(signal, effectiveness, risk, row),
                "key_evidence": key_evidence(row),
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "signal",
            "strategy_role",
            "event_count",
            "sample_size_quality",
            "best_horizon",
            "effectiveness_rating",
            "risk_rating",
            "recommended_use",
            "interpretation",
            "key_evidence",
        ],
    )


def signal_with_extreme(
    group: pd.DataFrame,
    column: str,
    choose: str,
) -> str | None:
    clean = group.dropna(subset=[column])
    if clean.empty:
        return None
    index = clean[column].idxmax() if choose == "max" else clean[column].idxmin()
    return str(clean.loc[index, "signal"])


def ticker_interpretation(ticker: str, row: dict[str, Any]) -> str:
    strongest = row.get("strongest_signal") or "n/a"
    weakest = row.get("weakest_signal") or "n/a"
    drawdown = row.get("worst_avg_drawdown_60d_signal") or "n/a"
    return (
        f"{ticker}: strongest 20d signal was {strongest}; weakest 20d signal "
        f"was {weakest}; worst 60d drawdown signal was {drawdown}. Use this as "
        "ticker-specific historical context, not a prediction."
    )


def build_ticker_insights(by_ticker_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for ticker, group in by_ticker_df.groupby("ticker", sort=True):
        strongest = signal_with_extreme(group, "avg_return_20d", "max")
        weakest = signal_with_extreme(group, "avg_return_20d", "min")
        worst_drawdown = signal_with_extreme(group, "avg_max_drawdown_60d", "min")
        row = {
            "ticker": ticker,
            "event_count": int(group["event_count"].sum()),
            "strongest_signal": strongest,
            "weakest_signal": weakest,
            "best_avg_return_20d_signal": strongest,
            "worst_avg_drawdown_60d_signal": worst_drawdown,
        }
        row["ticker_interpretation"] = ticker_interpretation(ticker, row)
        rows.append(row)

    return pd.DataFrame(
        rows,
        columns=[
            "ticker",
            "event_count",
            "strongest_signal",
            "weakest_signal",
            "best_avg_return_20d_signal",
            "worst_avg_drawdown_60d_signal",
            "ticker_interpretation",
        ],
    )


def write_outputs(
    interpretation_df: pd.DataFrame,
    ticker_insights_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    by_ticker_df: pd.DataFrame,
    trades_df: pd.DataFrame,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    trades_sample = trades_df.head(TRADES_SAMPLE_LIMIT)

    interpretation_df.to_csv(INTERPRETATION_CSV, index=False)
    interpretation_df.to_excel(INTERPRETATION_XLSX, index=False, engine="openpyxl")
    ticker_insights_df.to_csv(TICKER_INSIGHTS_CSV, index=False)
    ticker_insights_df.to_excel(TICKER_INSIGHTS_XLSX, index=False, engine="openpyxl")

    with pd.ExcelWriter(SCORECARD_XLSX, engine="openpyxl") as writer:
        interpretation_df.to_excel(
            writer, sheet_name="Signal_Interpretation", index=False
        )
        summary_df.to_excel(writer, sheet_name="Summary_By_Signal", index=False)
        by_ticker_df.to_excel(writer, sheet_name="Summary_By_Ticker", index=False)
        trades_sample.to_excel(writer, sheet_name="Trades_Sample", index=False)

    print(f"Wrote {INTERPRETATION_CSV}")
    print(f"Wrote {INTERPRETATION_XLSX}")
    print(f"Wrote {SCORECARD_XLSX}")
    print(f"Wrote {TICKER_INSIGHTS_CSV}")
    print(f"Wrote {TICKER_INSIGHTS_XLSX}")


def main() -> None:
    if not required_inputs_exist():
        return

    summary_df = pd.read_csv(SUMMARY_CSV)
    by_ticker_df = pd.read_csv(BY_TICKER_CSV)
    trades_df = pd.read_csv(TRADES_CSV)

    interpretation_df = build_signal_interpretation(summary_df)
    ticker_insights_df = build_ticker_insights(by_ticker_df)

    write_outputs(
        interpretation_df,
        ticker_insights_df,
        summary_df,
        by_ticker_df,
        trades_df,
    )

    print(f"Signals interpreted: {len(interpretation_df)}")
    print(f"Tickers interpreted: {len(ticker_insights_df)}")
    print("Done. Interpretation is historical research only, not investment advice.")


if __name__ == "__main__":
    main()
