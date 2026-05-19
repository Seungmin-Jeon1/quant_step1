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
FIRST_HIT_TRADES_CSV = OUTPUT_DIR / "growth_signal_first_hit_trades.csv"
FIRST_HIT_SUMMARY_CSV = OUTPUT_DIR / "growth_signal_first_hit_summary.csv"
FIRST_HIT_BY_TICKER_CSV = OUTPUT_DIR / "growth_signal_first_hit_by_ticker.csv"
FIRST_HIT_REPORT_XLSX = OUTPUT_DIR / "growth_signal_first_hit_report.xlsx"

BENCHMARKS = ["SPY", "QQQ"]
HISTORY_PERIOD = str(BACKTEST_CONFIG.get("history_period", "2y"))
MAX_HOLDING_DAYS = 20
STOP_LOSS_THRESHOLD = -0.08
TAKE_PROFIT_THRESHOLD = 0.20
TRANSACTION_COST_ROUND_TRIP = 0.001
SLIPPAGE_ROUND_TRIP = 0.002
TOTAL_COST_ASSUMPTION = TRANSACTION_COST_ROUND_TRIP + SLIPPAGE_ROUND_TRIP

TRADE_COLUMNS = [
    "ticker",
    "signal",
    "entry_date",
    "entry_price",
    "exit_date",
    "exit_price",
    "exit_type",
    "holding_days",
    "gross_return",
    "net_return_after_cost",
    "benchmark_return_spy",
    "benchmark_return_qqq",
    "excess_return_vs_spy",
    "excess_return_vs_qqq",
]

SUMMARY_COLUMNS = [
    "signal",
    "event_count",
    "avg_holding_days",
    "avg_gross_return",
    "median_gross_return",
    "win_rate_gross_return",
    "avg_net_return_after_cost",
    "median_net_return_after_cost",
    "win_rate_net_return_after_cost",
    "avg_benchmark_return_spy",
    "avg_benchmark_return_qqq",
    "avg_excess_return_vs_spy",
    "avg_excess_return_vs_qqq",
    "stop_loss_exit_count",
    "take_profit_exit_count",
    "time_exit_count",
    "stop_loss_exit_rate",
    "take_profit_exit_rate",
    "time_exit_rate",
]

BY_TICKER_COLUMNS = ["ticker", *SUMMARY_COLUMNS]


def normalize_history_index(history: pd.DataFrame) -> pd.DataFrame:
    df = history.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df


def download_ohlcv_history(symbol: str, period: str) -> pd.DataFrame:
    history = yf.Ticker(symbol).history(period=period, auto_adjust=False)
    if history.empty:
        raise ValueError(f"No price history returned for {symbol}")

    required_columns = {"Open", "High", "Low", "Close", "Volume"}
    missing_columns = required_columns.difference(history.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required history columns for {symbol}: {missing}")

    history = normalize_history_index(history)
    return history.dropna(subset=["High", "Low", "Close"]).copy()


def download_benchmark_close(symbol: str, period: str) -> pd.Series:
    history = download_ohlcv_history(symbol, period)
    close = history["Close"].dropna().copy()
    close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
    return close


def position_for_date(index: pd.DatetimeIndex, trade_date: pd.Timestamp) -> int | None:
    trade_date = pd.Timestamp(trade_date).normalize()
    if trade_date not in index:
        return None

    position = index.get_loc(trade_date)
    if isinstance(position, slice):
        position = position.start
    return int(position)


def benchmark_return(
    benchmark_close: pd.Series,
    entry_date: pd.Timestamp,
    exit_date: pd.Timestamp,
) -> float | None:
    entry_position = position_for_date(benchmark_close.index, entry_date)
    exit_position = position_for_date(benchmark_close.index, exit_date)
    if entry_position is None or exit_position is None:
        return None

    start = clean_number(benchmark_close.iloc[entry_position])
    end = clean_number(benchmark_close.iloc[exit_position])
    if start in (None, 0) or end is None:
        return None
    return end / start - 1


def find_first_hit_exit(
    history: pd.DataFrame,
    entry_date: pd.Timestamp,
    entry_price: float,
    max_holding_days: int = MAX_HOLDING_DAYS,
) -> dict[str, Any] | None:
    entry_position = position_for_date(history.index, entry_date)
    if entry_position is None:
        return None

    stop_price = entry_price * (1 + STOP_LOSS_THRESHOLD)
    take_profit_price = entry_price * (1 + TAKE_PROFIT_THRESHOLD)
    last_position = min(entry_position + max_holding_days, len(history) - 1)

    if last_position <= entry_position:
        return None

    for position in range(entry_position + 1, last_position + 1):
        row = history.iloc[position]
        low = clean_number(row["Low"])
        high = clean_number(row["High"])
        exit_date = history.index[position]
        holding_days = position - entry_position

        # Daily OHLC data cannot tell intraday order when both thresholds hit.
        # Use the conservative assumption that stop-loss fires first.
        if low is not None and low <= stop_price:
            return {
                "exit_date": exit_date,
                "exit_price": stop_price,
                "exit_type": "stop_loss_exit",
                "holding_days": holding_days,
            }
        if high is not None and high >= take_profit_price:
            return {
                "exit_date": exit_date,
                "exit_price": take_profit_price,
                "exit_type": "take_profit_exit",
                "holding_days": holding_days,
            }

    exit_close = clean_number(history["Close"].iloc[last_position])
    if exit_close is None:
        return None

    return {
        "exit_date": history.index[last_position],
        "exit_price": exit_close,
        "exit_type": "time_exit",
        "holding_days": last_position - entry_position,
    }


def build_first_hit_trade_row(
    trade: pd.Series,
    ticker_history: pd.DataFrame,
    benchmark_histories: dict[str, pd.Series],
) -> dict[str, Any] | None:
    entry_date = pd.Timestamp(trade["signal_date"]).normalize()
    entry_price = clean_number(trade.get("close_on_signal"))
    if entry_price in (None, 0):
        entry_position = position_for_date(ticker_history.index, entry_date)
        if entry_position is None:
            return None
        entry_price = clean_number(ticker_history["Close"].iloc[entry_position])
    if entry_price in (None, 0):
        return None

    exit_info = find_first_hit_exit(ticker_history, entry_date, float(entry_price))
    if exit_info is None:
        return None

    exit_price = clean_number(exit_info["exit_price"])
    if exit_price is None:
        return None

    gross_return = exit_price / float(entry_price) - 1
    benchmark_spy = benchmark_return(
        benchmark_histories["SPY"], entry_date, exit_info["exit_date"]
    )
    benchmark_qqq = benchmark_return(
        benchmark_histories["QQQ"], entry_date, exit_info["exit_date"]
    )

    return {
        "ticker": trade["ticker"],
        "signal": trade["signal"],
        "entry_date": entry_date.date().isoformat(),
        "entry_price": float(entry_price),
        "exit_date": exit_info["exit_date"].date().isoformat(),
        "exit_price": exit_price,
        "exit_type": exit_info["exit_type"],
        "holding_days": exit_info["holding_days"],
        "gross_return": gross_return,
        "net_return_after_cost": gross_return - TOTAL_COST_ASSUMPTION,
        "benchmark_return_spy": benchmark_spy,
        "benchmark_return_qqq": benchmark_qqq,
        "excess_return_vs_spy": (
            gross_return - benchmark_spy if benchmark_spy is not None else None
        ),
        "excess_return_vs_qqq": (
            gross_return - benchmark_qqq if benchmark_qqq is not None else None
        ),
    }


def win_rate(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return float((clean > 0).mean())


def summarize_group(trades_df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    columns = BY_TICKER_COLUMNS if keys == ["ticker", "signal"] else SUMMARY_COLUMNS
    if trades_df.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for group_key, group in trades_df.groupby(keys, sort=True):
        if not isinstance(group_key, tuple):
            group_key = (group_key,)

        row = {key: value for key, value in zip(keys, group_key, strict=False)}
        row["event_count"] = len(group)
        row["avg_holding_days"] = group["holding_days"].mean()

        for column in [
            "gross_return",
            "net_return_after_cost",
            "benchmark_return_spy",
            "benchmark_return_qqq",
            "excess_return_vs_spy",
            "excess_return_vs_qqq",
        ]:
            values = pd.to_numeric(group[column], errors="coerce")
            row[f"avg_{column}"] = values.mean()
            if column in {"gross_return", "net_return_after_cost"}:
                row[f"median_{column}"] = values.median()
                row[f"win_rate_{column}"] = win_rate(values)

        exit_counts = group["exit_type"].value_counts()
        for exit_type in ["stop_loss_exit", "take_profit_exit", "time_exit"]:
            count = int(exit_counts.get(exit_type, 0))
            row[f"{exit_type}_count"] = count
            row[f"{exit_type}_rate"] = count / len(group) if len(group) else None

        rows.append(row)

    return pd.DataFrame(rows, columns=columns)


def build_first_hit_backtest() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    if not INPUT_TRADES_CSV.exists():
        print(
            "Base backtest trades file not found. Please run py .\\backtesting\\backtest_growth.py first."
        )
        print(f"Missing file: {INPUT_TRADES_CSV}")
        return (
            pd.DataFrame(columns=TRADE_COLUMNS),
            pd.DataFrame(columns=SUMMARY_COLUMNS),
            pd.DataFrame(columns=BY_TICKER_COLUMNS),
            [f"Missing input file: {INPUT_TRADES_CSV}"],
        )

    trades_df = pd.read_csv(INPUT_TRADES_CSV)
    if trades_df.empty:
        print("Input trades file is empty. Empty first-hit output files will be created.")
        return (
            pd.DataFrame(columns=TRADE_COLUMNS),
            pd.DataFrame(columns=SUMMARY_COLUMNS),
            pd.DataFrame(columns=BY_TICKER_COLUMNS),
            [],
        )

    first_hit_rows = []
    errors = []
    ticker_histories: dict[str, pd.DataFrame] = {}
    benchmark_histories: dict[str, pd.Series] = {}

    for benchmark in BENCHMARKS:
        try:
            print(f"Downloading benchmark history for {benchmark}...")
            benchmark_histories[benchmark] = download_benchmark_close(
                benchmark, HISTORY_PERIOD
            )
        except Exception as exc:
            message = f"{benchmark}: {exc}"
            print(f"Error: failed to download benchmark history: {message}")
            errors.append(message)
            benchmark_histories[benchmark] = pd.Series(dtype="float64")

    for ticker in sorted(trades_df["ticker"].dropna().unique().tolist()):
        try:
            print(f"Downloading history for {ticker}...")
            ticker_histories[ticker] = download_ohlcv_history(ticker, HISTORY_PERIOD)
        except Exception as exc:
            message = f"{ticker}: {exc}"
            print(f"Error: failed to download ticker history: {message}")
            errors.append(message)

    for _, trade in trades_df.iterrows():
        ticker = trade.get("ticker")
        ticker_history = ticker_histories.get(ticker)
        if ticker_history is None:
            continue

        try:
            row = build_first_hit_trade_row(
                trade, ticker_history, benchmark_histories
            )
            if row is not None:
                first_hit_rows.append(row)
        except Exception as exc:
            message = f"{ticker} {trade.get('signal_date')}: {exc}"
            print(f"Error: failed to build first-hit trade: {message}")
            errors.append(message)

    first_hit_trades = pd.DataFrame(first_hit_rows, columns=TRADE_COLUMNS)
    if first_hit_trades.empty:
        print("No valid first-hit trades were produced. Empty output files will be created.")

    first_hit_summary = summarize_group(first_hit_trades, ["signal"])
    first_hit_by_ticker = summarize_group(first_hit_trades, ["ticker", "signal"])
    return first_hit_trades, first_hit_summary, first_hit_by_ticker, errors


def write_outputs(
    first_hit_trades: pd.DataFrame,
    first_hit_summary: pd.DataFrame,
    first_hit_by_ticker: pd.DataFrame,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    first_hit_trades.to_csv(FIRST_HIT_TRADES_CSV, index=False)
    first_hit_summary.to_csv(FIRST_HIT_SUMMARY_CSV, index=False)
    first_hit_by_ticker.to_csv(FIRST_HIT_BY_TICKER_CSV, index=False)

    with pd.ExcelWriter(FIRST_HIT_REPORT_XLSX, engine="openpyxl") as writer:
        first_hit_trades.to_excel(writer, sheet_name="First_Hit_Trades", index=False)
        first_hit_summary.to_excel(
            writer, sheet_name="First_Hit_By_Signal", index=False
        )
        first_hit_by_ticker.to_excel(
            writer, sheet_name="First_Hit_By_Ticker", index=False
        )

    print(f"Wrote {FIRST_HIT_TRADES_CSV}")
    print(f"Wrote {FIRST_HIT_SUMMARY_CSV}")
    print(f"Wrote {FIRST_HIT_BY_TICKER_CSV}")
    print(f"Wrote {FIRST_HIT_REPORT_XLSX}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(YFINANCE_CACHE_DIR))

    first_hit_trades, first_hit_summary, first_hit_by_ticker, errors = (
        build_first_hit_backtest()
    )
    write_outputs(first_hit_trades, first_hit_summary, first_hit_by_ticker)

    print(f"First-hit events: {len(first_hit_trades)}")
    if not first_hit_summary.empty:
        print("Exit counts by signal:")
        for _, row in first_hit_summary.iterrows():
            print(
                f"- {row['signal']}: events={int(row['event_count'])}, "
                f"stop_loss={int(row['stop_loss_exit_count'])}, "
                f"take_profit={int(row['take_profit_exit_count'])}, "
                f"time_exit={int(row['time_exit_count'])}"
            )

    if errors:
        print("Errors:")
        for error in errors:
            print(f"- {error}")
    else:
        print("Errors: none")

    print("Done. First-hit backtest results are historical research only, not predictions.")


if __name__ == "__main__":
    main()
