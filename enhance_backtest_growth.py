from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config_loader import load_config, output_dir_for  # noqa: E402
from signal_rules import clean_number  # noqa: E402


BASE_DIR = Path(__file__).resolve().parent
CONFIG = load_config()
BACKTEST_CONFIG = CONFIG["backtest"]
OUTPUT_DIR = output_dir_for(BASE_DIR, BACKTEST_CONFIG)
YFINANCE_CACHE_DIR = BASE_DIR / ".yf_cache"

INPUT_TRADES_CSV = OUTPUT_DIR / "growth_signal_backtest_trades.csv"
ENHANCED_TRADES_CSV = OUTPUT_DIR / "growth_signal_enhanced_backtest_trades.csv"
ENHANCED_SUMMARY_CSV = OUTPUT_DIR / "growth_signal_enhanced_backtest_summary.csv"
ENHANCED_BY_TICKER_CSV = OUTPUT_DIR / "growth_signal_enhanced_backtest_by_ticker.csv"
ENHANCED_TRADES_XLSX = OUTPUT_DIR / "growth_signal_enhanced_backtest_trades.xlsx"
ENHANCED_SUMMARY_XLSX = OUTPUT_DIR / "growth_signal_enhanced_backtest_summary.xlsx"
ENHANCED_BY_TICKER_XLSX = OUTPUT_DIR / "growth_signal_enhanced_backtest_by_ticker.xlsx"
ENHANCED_REPORT_XLSX = OUTPUT_DIR / "growth_signal_enhanced_backtest_report.xlsx"

BENCHMARKS = ["SPY", "QQQ"]
HORIZONS = [5, 10, 20, 60]
TRANSACTION_COST_ROUND_TRIP = 0.001
SLIPPAGE_ROUND_TRIP = 0.002
TOTAL_COST_ASSUMPTION = TRANSACTION_COST_ROUND_TRIP + SLIPPAGE_ROUND_TRIP
STOP_LOSS_THRESHOLD = -0.08
TAKE_PROFIT_THRESHOLD = 0.20
HISTORY_PERIOD = str(BACKTEST_CONFIG.get("history_period", "2y"))


def required_inputs_exist() -> bool:
    if INPUT_TRADES_CSV.exists():
        return True
    print(
        "Backtest trades file not found. Please run py .\\backtesting\\backtest_growth.py first."
    )
    print(f"Missing file: {INPUT_TRADES_CSV}")
    return False


def download_close_history(symbol: str, period: str) -> pd.Series:
    history = yf.Ticker(symbol).history(period=period, auto_adjust=False)
    if history.empty or "Close" not in history.columns:
        raise ValueError(f"No close history returned for {symbol}")

    close = history["Close"].dropna().copy()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close


def forward_return(close: pd.Series, signal_date: pd.Timestamp, horizon: int) -> float | None:
    if signal_date not in close.index:
        return None

    start_position = close.index.get_loc(signal_date)
    if isinstance(start_position, slice):
        start_position = start_position.start
    future_position = int(start_position) + horizon
    if future_position >= len(close):
        return None

    start = clean_number(close.iloc[int(start_position)])
    end = clean_number(close.iloc[future_position])
    if start in (None, 0) or end is None:
        return None
    return end / start - 1


def future_window_return(
    close: pd.Series,
    signal_date: pd.Timestamp,
    horizon: int,
    stat: str,
) -> float | None:
    if signal_date not in close.index:
        return None

    start_position = close.index.get_loc(signal_date)
    if isinstance(start_position, slice):
        start_position = start_position.start
    start_position = int(start_position)
    if start_position + horizon >= len(close):
        return None

    start = clean_number(close.iloc[start_position])
    if start in (None, 0):
        return None

    window = close.iloc[start_position + 1 : start_position + horizon + 1]
    if window.empty:
        return None

    if stat == "min":
        value = clean_number(window.min())
    elif stat == "max":
        value = clean_number(window.max())
    else:
        raise ValueError(f"Unsupported stat: {stat}")

    if value is None:
        return None
    return value / start - 1


def first_threshold_hit(
    close: pd.Series,
    signal_date: pd.Timestamp,
    horizon: int,
    threshold: float,
    direction: str,
) -> bool | None:
    if signal_date not in close.index:
        return None

    start_position = close.index.get_loc(signal_date)
    if isinstance(start_position, slice):
        start_position = start_position.start
    start_position = int(start_position)
    if start_position + horizon >= len(close):
        return None

    start = clean_number(close.iloc[start_position])
    if start in (None, 0):
        return None

    window = close.iloc[start_position + 1 : start_position + horizon + 1]
    returns = window / start - 1
    if direction == "below":
        return bool((returns <= threshold).any())
    if direction == "above":
        return bool((returns >= threshold).any())
    raise ValueError(f"Unsupported direction: {direction}")


def win_rate(series: pd.Series) -> float | None:
    clean = series.dropna()
    if clean.empty:
        return None
    return float((clean > 0).mean())


def average_gain(series: pd.Series) -> float | None:
    gains = series.dropna()
    gains = gains[gains > 0]
    if gains.empty:
        return None
    return float(gains.mean())


def average_loss(series: pd.Series) -> float | None:
    losses = series.dropna()
    losses = losses[losses < 0]
    if losses.empty:
        return None
    return float(losses.mean())


def payoff_ratio(series: pd.Series) -> float | None:
    gain = average_gain(series)
    loss = average_loss(series)
    if gain is None or loss in (None, 0):
        return None
    return gain / abs(loss)


def add_enhanced_metrics(
    trades_df: pd.DataFrame,
    close_histories: dict[str, pd.Series],
    benchmark_histories: dict[str, pd.Series],
) -> pd.DataFrame:
    enhanced = trades_df.copy()
    enhanced["signal_date"] = pd.to_datetime(enhanced["signal_date"]).dt.normalize()

    for horizon in HORIZONS:
        if horizon not in {5, 20, 60}:
            enhanced[f"return_{horizon}d"] = None
        enhanced[f"net_return_{horizon}d_after_cost"] = None
        enhanced[f"benchmark_return_{horizon}d_spy"] = None
        enhanced[f"benchmark_return_{horizon}d_qqq"] = None
        enhanced[f"excess_return_{horizon}d_vs_spy"] = None
        enhanced[f"excess_return_{horizon}d_vs_qqq"] = None

    enhanced["stop_loss_20d_hit"] = None
    enhanced["take_profit_20d_hit"] = None
    enhanced["stop_loss_60d_hit"] = None
    enhanced["take_profit_60d_hit"] = None
    enhanced["transaction_cost_assumption"] = TRANSACTION_COST_ROUND_TRIP
    enhanced["slippage_assumption"] = SLIPPAGE_ROUND_TRIP
    enhanced["total_cost_assumption"] = TOTAL_COST_ASSUMPTION
    enhanced["stop_loss_threshold"] = STOP_LOSS_THRESHOLD
    enhanced["take_profit_threshold"] = TAKE_PROFIT_THRESHOLD

    for index, row in enhanced.iterrows():
        ticker = row["ticker"]
        signal_date = row["signal_date"]
        close = close_histories.get(ticker)
        if close is None:
            continue

        for horizon in HORIZONS:
            ticker_return = forward_return(close, signal_date, horizon)
            if ticker_return is not None:
                enhanced.at[index, f"return_{horizon}d"] = ticker_return
                enhanced.at[index, f"net_return_{horizon}d_after_cost"] = (
                    ticker_return - TOTAL_COST_ASSUMPTION
                )

            for benchmark in BENCHMARKS:
                benchmark_return = forward_return(
                    benchmark_histories[benchmark], signal_date, horizon
                )
                column_suffix = benchmark.lower()
                enhanced.at[index, f"benchmark_return_{horizon}d_{column_suffix}"] = (
                    benchmark_return
                )
                if ticker_return is not None and benchmark_return is not None:
                    enhanced.at[index, f"excess_return_{horizon}d_vs_{column_suffix}"] = (
                        ticker_return - benchmark_return
                    )

        enhanced.at[index, "stop_loss_20d_hit"] = first_threshold_hit(
            close, signal_date, 20, STOP_LOSS_THRESHOLD, "below"
        )
        enhanced.at[index, "take_profit_20d_hit"] = first_threshold_hit(
            close, signal_date, 20, TAKE_PROFIT_THRESHOLD, "above"
        )
        enhanced.at[index, "stop_loss_60d_hit"] = first_threshold_hit(
            close, signal_date, 60, STOP_LOSS_THRESHOLD, "below"
        )
        enhanced.at[index, "take_profit_60d_hit"] = first_threshold_hit(
            close, signal_date, 60, TAKE_PROFIT_THRESHOLD, "above"
        )

    return enhanced


def summarize_group(group: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    rows = []
    for group_key, subset in group.groupby(keys, sort=True):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)

        row = {key: value for key, value in zip(keys, group_key, strict=False)}
        row["event_count"] = len(subset)

        for horizon in HORIZONS:
            returns = pd.to_numeric(subset[f"return_{horizon}d"], errors="coerce")
            net_returns = pd.to_numeric(
                subset[f"net_return_{horizon}d_after_cost"], errors="coerce"
            )
            excess_spy = pd.to_numeric(
                subset[f"excess_return_{horizon}d_vs_spy"], errors="coerce"
            )
            excess_qqq = pd.to_numeric(
                subset[f"excess_return_{horizon}d_vs_qqq"], errors="coerce"
            )

            row[f"avg_return_{horizon}d"] = returns.mean()
            row[f"median_return_{horizon}d"] = returns.median()
            row[f"win_rate_{horizon}d"] = win_rate(returns)
            row[f"avg_net_return_{horizon}d_after_cost"] = net_returns.mean()
            row[f"avg_excess_return_{horizon}d_vs_spy"] = excess_spy.mean()
            row[f"avg_excess_return_{horizon}d_vs_qqq"] = excess_qqq.mean()
            row[f"avg_gain_{horizon}d"] = average_gain(returns)
            row[f"avg_loss_{horizon}d"] = average_loss(returns)
            row[f"payoff_ratio_{horizon}d"] = payoff_ratio(returns)

        for horizon in [20, 60]:
            row[f"stop_loss_{horizon}d_hit_rate"] = (
                subset[f"stop_loss_{horizon}d_hit"].dropna().mean()
            )
            row[f"take_profit_{horizon}d_hit_rate"] = (
                subset[f"take_profit_{horizon}d_hit"].dropna().mean()
            )

        rows.append(row)

    return pd.DataFrame(rows)


def build_enhanced_backtest() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trades_df = pd.read_csv(INPUT_TRADES_CSV)
    if trades_df.empty:
        return trades_df, pd.DataFrame(), pd.DataFrame()

    tickers = sorted(trades_df["ticker"].dropna().unique().tolist())
    close_histories = {}
    benchmark_histories = {}

    for ticker in tickers:
        print(f"Downloading history for {ticker}...")
        close_histories[ticker] = download_close_history(ticker, HISTORY_PERIOD)

    for benchmark in BENCHMARKS:
        print(f"Downloading benchmark history for {benchmark}...")
        benchmark_histories[benchmark] = download_close_history(benchmark, HISTORY_PERIOD)

    enhanced_trades = add_enhanced_metrics(
        trades_df, close_histories, benchmark_histories
    )
    enhanced_summary = summarize_group(enhanced_trades, ["signal"])
    enhanced_by_ticker = summarize_group(enhanced_trades, ["ticker", "signal"])
    return enhanced_trades, enhanced_summary, enhanced_by_ticker


def write_outputs(
    enhanced_trades: pd.DataFrame,
    enhanced_summary: pd.DataFrame,
    enhanced_by_ticker: pd.DataFrame,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    enhanced_trades.to_csv(ENHANCED_TRADES_CSV, index=False)
    enhanced_summary.to_csv(ENHANCED_SUMMARY_CSV, index=False)
    enhanced_by_ticker.to_csv(ENHANCED_BY_TICKER_CSV, index=False)

    enhanced_trades.to_excel(ENHANCED_TRADES_XLSX, index=False, engine="openpyxl")
    enhanced_summary.to_excel(ENHANCED_SUMMARY_XLSX, index=False, engine="openpyxl")
    enhanced_by_ticker.to_excel(ENHANCED_BY_TICKER_XLSX, index=False, engine="openpyxl")

    with pd.ExcelWriter(ENHANCED_REPORT_XLSX, engine="openpyxl") as writer:
        enhanced_trades.to_excel(writer, sheet_name="Enhanced_Trades", index=False)
        enhanced_summary.to_excel(writer, sheet_name="Enhanced_By_Signal", index=False)
        enhanced_by_ticker.to_excel(
            writer, sheet_name="Enhanced_By_Ticker", index=False
        )

    print(f"Wrote {ENHANCED_TRADES_CSV}")
    print(f"Wrote {ENHANCED_SUMMARY_CSV}")
    print(f"Wrote {ENHANCED_BY_TICKER_CSV}")
    print(f"Wrote {ENHANCED_TRADES_XLSX}")
    print(f"Wrote {ENHANCED_SUMMARY_XLSX}")
    print(f"Wrote {ENHANCED_BY_TICKER_XLSX}")
    print(f"Wrote {ENHANCED_REPORT_XLSX}")


def main() -> None:
    if not INPUT_TRADES_CSV.exists():
        print(
            "Base backtest trades file not found. Please run py .\\backtesting\\backtest_growth.py first."
        )
        print(f"Missing file: {INPUT_TRADES_CSV}")
        return

    YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(YFINANCE_CACHE_DIR))

    enhanced_trades, enhanced_summary, enhanced_by_ticker = build_enhanced_backtest()
    write_outputs(enhanced_trades, enhanced_summary, enhanced_by_ticker)

    print(f"Enhanced events: {len(enhanced_trades)}")
    print(
        "Done. Enhanced backtest results are historical research only, not predictions."
    )


if __name__ == "__main__":
    main()
