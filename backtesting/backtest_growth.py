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
from signal_rules import clean_number, growth_signal_from_row, price_vs_ma  # noqa: E402


SIGNALS_TO_BACKTEST = {
    "Trend Positive",
    "Pullback Watch",
    "High Volume Risk Monitor",
    "Weak Trend / Low Volume",
    "Early Watch",
    "Confirmed Watch",
}

BASE_DIR = Path(__file__).resolve().parent
CONFIG = load_config()
BACKTEST_CONFIG = CONFIG["backtest"]
GROWTH_TICKERS = CONFIG["growth_tickers"]
OUTPUT_DIR = output_dir_for(BASE_DIR, BACKTEST_CONFIG)
YFINANCE_CACHE_DIR = BASE_DIR / ".yf_cache"

TRADES_CSV = OUTPUT_DIR / "growth_signal_backtest_trades.csv"
SUMMARY_CSV = OUTPUT_DIR / "growth_signal_backtest_summary.csv"
BY_TICKER_CSV = OUTPUT_DIR / "growth_signal_backtest_by_ticker.csv"
TRADES_XLSX = OUTPUT_DIR / "growth_signal_backtest_trades.xlsx"
SUMMARY_XLSX = OUTPUT_DIR / "growth_signal_backtest_summary.xlsx"
BY_TICKER_XLSX = OUTPUT_DIR / "growth_signal_backtest_by_ticker.xlsx"
REPORT_XLSX = OUTPUT_DIR / "growth_signal_backtest_report.xlsx"

BACKTEST_HISTORY_PERIOD = str(BACKTEST_CONFIG.get("history_period", "2y"))
BACKTEST_SIGNAL_COOLDOWN_DAYS = int(BACKTEST_CONFIG.get("cooldown_days", 10))


def calculate_rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi = rsi.mask(avg_loss == 0, 100.0)
    return rsi


def download_history(symbol: str, period: str) -> pd.DataFrame:
    history = yf.Ticker(symbol).history(period=period, auto_adjust=False)
    if history.empty:
        raise ValueError(f"No price history returned for {symbol}")

    required_columns = {"Close", "Volume"}
    missing_columns = required_columns.difference(history.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required history columns for {symbol}: {missing}")

    return history.dropna(subset=["Close", "Volume"]).copy()


def add_indicators(history: pd.DataFrame) -> pd.DataFrame:
    df = history.copy()
    df["close"] = df["Close"]
    df["volume"] = df["Volume"]
    df["rsi_14"] = calculate_rsi_series(df["close"], 14)
    df["avg_volume_20d"] = df["volume"].rolling(20).mean()
    df["volume_ratio_vs_20d"] = df["volume"] / df["avg_volume_20d"]
    df["return_20d"] = df["close"] / df["close"].shift(20) - 1
    df["return_60d"] = df["close"] / df["close"].shift(60) - 1
    df["ma_50d"] = df["close"].rolling(50).mean()
    df["ma_200d"] = df["close"].rolling(200).mean()
    df["price_vs_50ma"] = [
        price_vs_ma(price, ma)
        for price, ma in zip(df["close"], df["ma_50d"], strict=False)
    ]
    df["price_vs_200ma"] = [
        price_vs_ma(price, ma)
        for price, ma in zip(df["close"], df["ma_200d"], strict=False)
    ]
    df["signal"] = df.apply(growth_signal_from_row, axis=1)
    return df


def forward_return(close: pd.Series, index_position: int, horizon: int) -> float | None:
    future_position = index_position + horizon
    if future_position >= len(close):
        return None

    start = clean_number(close.iloc[index_position])
    end = clean_number(close.iloc[future_position])
    if start in (None, 0) or end is None:
        return None
    return end / start - 1


def future_window_stat(
    close: pd.Series, index_position: int, horizon: int, stat: str
) -> float | None:
    if index_position + horizon >= len(close):
        return None

    start = clean_number(close.iloc[index_position])
    if start in (None, 0):
        return None

    future_window = close.iloc[index_position + 1 : index_position + horizon + 1]
    if future_window.empty:
        return None

    if stat == "min":
        value = clean_number(future_window.min())
    elif stat == "max":
        value = clean_number(future_window.max())
    else:
        raise ValueError(f"Unsupported future window stat: {stat}")

    if value is None:
        return None
    return value / start - 1


def should_count_event(
    symbol: str,
    signal: str,
    index_position: int,
    last_event_positions: dict[tuple[str, str], int],
    cooldown_days: int,
) -> bool:
    key = (symbol, signal)
    last_position = last_event_positions.get(key)
    if last_position is None:
        return True
    return index_position - last_position > cooldown_days


def build_trade_row(symbol: str, df: pd.DataFrame, index_position: int) -> dict[str, Any]:
    row = df.iloc[index_position]
    close = df["close"]

    return {
        "ticker": symbol,
        "signal_date": df.index[index_position].date().isoformat(),
        "signal": row["signal"],
        "close_on_signal": clean_number(row["close"]),
        "rsi_14": clean_number(row["rsi_14"]),
        "volume_ratio_vs_20d": clean_number(row["volume_ratio_vs_20d"]),
        "price_vs_50ma": row["price_vs_50ma"],
        "price_vs_200ma": row["price_vs_200ma"],
        "return_5d": forward_return(close, index_position, 5),
        "return_20d": forward_return(close, index_position, 20),
        "return_60d": forward_return(close, index_position, 60),
        "max_drawdown_20d": future_window_stat(close, index_position, 20, "min"),
        "max_drawdown_60d": future_window_stat(close, index_position, 60, "min"),
        "max_gain_20d": future_window_stat(close, index_position, 20, "max"),
        "max_gain_60d": future_window_stat(close, index_position, 60, "max"),
    }


def backtest_ticker(
    symbol: str,
    period: str,
    cooldown_days: int,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        history = download_history(symbol, period)
        df = add_indicators(history)
    except Exception as exc:
        return [], f"{symbol}: {exc}"

    trade_rows = []
    last_event_positions: dict[tuple[str, str], int] = {}

    for index_position, row in enumerate(df.itertuples(index=False)):
        signal = getattr(row, "signal")
        if signal not in SIGNALS_TO_BACKTEST:
            continue
        if not should_count_event(
            symbol, signal, index_position, last_event_positions, cooldown_days
        ):
            continue

        trade_rows.append(build_trade_row(symbol, df, index_position))
        last_event_positions[(symbol, signal)] = index_position

    return trade_rows, None


def win_rate(series: pd.Series) -> float | None:
    clean = series.dropna()
    if clean.empty:
        return None
    return float((clean > 0).mean())


def summarize_by_signal(trades_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "signal",
        "event_count",
        "avg_return_5d",
        "median_return_5d",
        "win_rate_5d",
        "avg_return_20d",
        "median_return_20d",
        "win_rate_20d",
        "avg_return_60d",
        "median_return_60d",
        "win_rate_60d",
        "avg_max_drawdown_20d",
        "avg_max_drawdown_60d",
        "avg_max_gain_20d",
        "avg_max_gain_60d",
    ]
    if trades_df.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for signal, group in trades_df.groupby("signal", sort=True):
        rows.append(
            {
                "signal": signal,
                "event_count": len(group),
                "avg_return_5d": group["return_5d"].mean(),
                "median_return_5d": group["return_5d"].median(),
                "win_rate_5d": win_rate(group["return_5d"]),
                "avg_return_20d": group["return_20d"].mean(),
                "median_return_20d": group["return_20d"].median(),
                "win_rate_20d": win_rate(group["return_20d"]),
                "avg_return_60d": group["return_60d"].mean(),
                "median_return_60d": group["return_60d"].median(),
                "win_rate_60d": win_rate(group["return_60d"]),
                "avg_max_drawdown_20d": group["max_drawdown_20d"].mean(),
                "avg_max_drawdown_60d": group["max_drawdown_60d"].mean(),
                "avg_max_gain_20d": group["max_gain_20d"].mean(),
                "avg_max_gain_60d": group["max_gain_60d"].mean(),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def summarize_by_ticker_signal(trades_df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "ticker",
        "signal",
        "event_count",
        "avg_return_5d",
        "win_rate_5d",
        "avg_return_20d",
        "win_rate_20d",
        "avg_return_60d",
        "win_rate_60d",
        "avg_max_drawdown_20d",
        "avg_max_drawdown_60d",
    ]
    if trades_df.empty:
        return pd.DataFrame(columns=columns)

    rows = []
    for (ticker, signal), group in trades_df.groupby(["ticker", "signal"], sort=True):
        rows.append(
            {
                "ticker": ticker,
                "signal": signal,
                "event_count": len(group),
                "avg_return_5d": group["return_5d"].mean(),
                "win_rate_5d": win_rate(group["return_5d"]),
                "avg_return_20d": group["return_20d"].mean(),
                "win_rate_20d": win_rate(group["return_20d"]),
                "avg_return_60d": group["return_60d"].mean(),
                "win_rate_60d": win_rate(group["return_60d"]),
                "avg_max_drawdown_20d": group["max_drawdown_20d"].mean(),
                "avg_max_drawdown_60d": group["max_drawdown_60d"].mean(),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def build_backtest(
    period: str = BACKTEST_HISTORY_PERIOD,
    cooldown_days: int = BACKTEST_SIGNAL_COOLDOWN_DAYS,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    trade_rows = []
    errors = []

    for symbol in GROWTH_TICKERS:
        print(f"Backtesting {symbol}...")
        rows, error = backtest_ticker(symbol, period, cooldown_days)
        trade_rows.extend(rows)
        if error:
            print(f"Error: {error}")
            errors.append(error)

    trades_df = pd.DataFrame(
        trade_rows,
        columns=[
            "ticker",
            "signal_date",
            "signal",
            "close_on_signal",
            "rsi_14",
            "volume_ratio_vs_20d",
            "price_vs_50ma",
            "price_vs_200ma",
            "return_5d",
            "return_20d",
            "return_60d",
            "max_drawdown_20d",
            "max_drawdown_60d",
            "max_gain_20d",
            "max_gain_60d",
        ],
    )
    summary_df = summarize_by_signal(trades_df)
    by_ticker_df = summarize_by_ticker_signal(trades_df)
    return trades_df, summary_df, by_ticker_df, errors


def write_outputs(
    trades_df: pd.DataFrame,
    summary_df: pd.DataFrame,
    by_ticker_df: pd.DataFrame,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    trades_df.to_csv(TRADES_CSV, index=False)
    summary_df.to_csv(SUMMARY_CSV, index=False)
    by_ticker_df.to_csv(BY_TICKER_CSV, index=False)

    trades_df.to_excel(TRADES_XLSX, index=False, engine="openpyxl")
    summary_df.to_excel(SUMMARY_XLSX, index=False, engine="openpyxl")
    by_ticker_df.to_excel(BY_TICKER_XLSX, index=False, engine="openpyxl")

    with pd.ExcelWriter(REPORT_XLSX, engine="openpyxl") as writer:
        trades_df.to_excel(writer, sheet_name="Trades", index=False)
        summary_df.to_excel(writer, sheet_name="Summary_By_Signal", index=False)
        by_ticker_df.to_excel(writer, sheet_name="Summary_By_Ticker", index=False)

    print(f"Wrote {TRADES_CSV}")
    print(f"Wrote {SUMMARY_CSV}")
    print(f"Wrote {BY_TICKER_CSV}")
    print(f"Wrote {TRADES_XLSX}")
    print(f"Wrote {SUMMARY_XLSX}")
    print(f"Wrote {BY_TICKER_XLSX}")
    print(f"Wrote {REPORT_XLSX}")


def count_insufficient_future_data(trades_df: pd.DataFrame) -> dict[str, int]:
    return {
        "return_5d": int(trades_df["return_5d"].isna().sum()) if not trades_df.empty else 0,
        "return_20d": int(trades_df["return_20d"].isna().sum()) if not trades_df.empty else 0,
        "return_60d": int(trades_df["return_60d"].isna().sum()) if not trades_df.empty else 0,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(YFINANCE_CACHE_DIR))

    trades_df, summary_df, by_ticker_df, errors = build_backtest()
    write_outputs(trades_df, summary_df, by_ticker_df)

    print(f"Total signal events: {len(trades_df)}")
    if not summary_df.empty:
        print("Event counts by signal:")
        for _, row in summary_df[["signal", "event_count"]].iterrows():
            print(f"- {row['signal']}: {int(row['event_count'])}")

    insufficient_counts = count_insufficient_future_data(trades_df)
    print("Insufficient future data counts:")
    for column, count in insufficient_counts.items():
        print(f"- {column}: {count}")

    if errors:
        print("yfinance errors:")
        for error in errors:
            print(f"- {error}")
    else:
        print("yfinance errors: none")

    print("Done. Backtest results are historical research only, not predictions.")


if __name__ == "__main__":
    main()
