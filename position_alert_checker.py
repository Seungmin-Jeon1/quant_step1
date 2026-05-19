from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf


PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_DIR = PROJECT_ROOT / "config"
OUTPUT_DIR = PROJECT_ROOT / "output"

POSITIONS_CSV = CONFIG_DIR / "my_positions.csv"
POSITION_ALERTS_CSV = OUTPUT_DIR / "position_alerts.csv"
POSITION_ALERTS_XLSX = OUTPUT_DIR / "position_alerts.xlsx"
FINAL_REPORT_XLSX = OUTPUT_DIR / "final_daily_research_report.xlsx"
DAILY_PRIORITY_CSV = OUTPUT_DIR / "daily_growth_priority.csv"
MEGA_CAP_VALUATION_CSV = PROJECT_ROOT / "screening" / "output" / "mega_cap_valuation_screen.csv"

POSITION_COLUMNS = [
    "ticker",
    "entry_price",
    "position_note",
    "take_profit_pct",
    "stop_loss_pct",
    "position_status",
    "sold_date",
]

OUTPUT_COLUMNS = [
    "ticker",
    "entry_price",
    "current_price",
    "current_return_pct",
    "take_profit_pct",
    "stop_loss_pct",
    "position_status",
    "sold_date",
    "alert_status",
    "position_note",
    "checked_at",
    "korean_interpretation",
    "fetch_error",
]

EXAMPLE_POSITIONS = [
    {
        "ticker": "PL",
        "entry_price": 5.20,
        "position_note": "manual position",
        "take_profit_pct": 20,
        "stop_loss_pct": -8,
        "position_status": "OPEN",
        "sold_date": "",
    },
    {
        "ticker": "RKLB",
        "entry_price": 4.80,
        "position_note": "small tracking position",
        "take_profit_pct": 25,
        "stop_loss_pct": -10,
        "position_status": "OPEN",
        "sold_date": "",
    },
    {
        "ticker": "LUNR",
        "entry_price": 8.50,
        "position_note": "event trade",
        "take_profit_pct": 20,
        "stop_loss_pct": -8,
        "position_status": "SOLD",
        "sold_date": "2026-05-15",
    },
]


def text_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value).strip()


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


def create_example_positions_file() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    example_df = pd.DataFrame(EXAMPLE_POSITIONS, columns=POSITION_COLUMNS)
    example_df.to_csv(POSITIONS_CSV, index=False)
    print(f"Created example positions file: {POSITIONS_CSV}")
    print(
        "Please edit config/my_positions.csv with your real tickers, entry prices, "
        "alert thresholds, and position_status before relying on alerts."
    )


def read_positions() -> pd.DataFrame:
    if not POSITIONS_CSV.exists():
        create_example_positions_file()

    positions = pd.read_csv(POSITIONS_CSV)
    for column in POSITION_COLUMNS:
        if column not in positions.columns:
            positions[column] = None

    positions = positions[POSITION_COLUMNS].copy()
    positions["ticker"] = positions["ticker"].apply(lambda value: text_value(value).upper())
    positions["position_status"] = positions["position_status"].apply(normalize_status)
    return positions


def normalize_status(value: Any) -> str:
    status = text_value(value).upper()
    if not status:
        return "OPEN"
    if status == "SOLD":
        return "SOLD"
    if status == "WATCHLIST":
        return "WATCHLIST"
    return "OPEN"


def latest_price(symbol: str) -> float:
    ticker = yf.Ticker(symbol)

    history = ticker.history(period="5d", auto_adjust=False)
    if not history.empty and "Close" in history.columns:
        close = history["Close"].dropna()
        if not close.empty:
            price = number_value(close.iloc[-1])
            if price is not None:
                return price

    info = ticker.get_info()
    for key in ["regularMarketPrice", "currentPrice", "previousClose"]:
        price = number_value(info.get(key))
        if price is not None:
            return price

    raise ValueError(f"No current price returned for {symbol}")


def alert_status_for(
    current_return_pct: float | None,
    take_profit_pct: float | None,
    stop_loss_pct: float | None,
) -> str:
    if current_return_pct is None:
        return "Price Fetch Error"
    if take_profit_pct is not None and current_return_pct >= take_profit_pct:
        return "Take Profit Alert"
    if stop_loss_pct is not None and current_return_pct <= stop_loss_pct:
        return "Stop Loss Alert"
    return "Holding / Watch"


def korean_interpretation_for_alert(row: dict[str, Any]) -> str:
    ticker = text_value(row.get("ticker")) or "확인 필요"
    status = text_value(row.get("position_status")) or "확인 필요"
    alert_status = text_value(row.get("alert_status")) or "확인 필요"
    current_return = number_value(row.get("current_return_pct"))
    take_profit = number_value(row.get("take_profit_pct"))
    stop_loss = number_value(row.get("stop_loss_pct"))
    fetch_error = text_value(row.get("fetch_error"))

    if status == "SOLD":
        return (
            f"{ticker}는 이미 매도 처리된 포지션입니다. 현재가 조회와 손익률 계산에서 "
            "제외되며, 이후 추가 알림을 띄우지 않습니다."
        )

    if status == "WATCHLIST":
        return (
            f"{ticker}는 보유 포지션이 아니라 리서치 후보로만 표시됩니다. 진입가가 "
            "입력되지 않았으므로 익절/손절 알림은 계산하지 않습니다."
        )

    if fetch_error:
        return (
            f"{ticker}의 현재가를 가져오지 못했습니다. 티커, 네트워크, yfinance 데이터 "
            "상태를 확인해 주세요. 이는 매수/매도 판단이 아니라 데이터 점검 알림입니다."
        )

    if alert_status == "Take Profit Alert":
        return (
            f"{ticker}의 현재 수익률이 설정한 익절 점검 기준({take_profit:.2f}%) 이상입니다. "
            "이는 자동 매도 지시가 아니라 포지션을 다시 확인하라는 리서치 알림입니다."
        )

    if alert_status == "Stop Loss Alert":
        return (
            f"{ticker}의 현재 수익률이 설정한 손절 점검 기준({stop_loss:.2f}%) 이하입니다. "
            "포지션 위험 점검이 필요하지만, 이는 자동 매도 지시가 아닙니다."
        )

    if current_return is not None:
        return (
            f"{ticker}의 현재 수익률은 {current_return:.2f}%입니다. 설정한 익절/손절 "
            "점검 기준에는 아직 도달하지 않았으며, 계속 관찰 대상으로 분류됩니다."
        )

    return (
        f"{ticker}는 알림 계산에 필요한 정보가 부족합니다. 진입가와 알림 기준을 확인해 주세요."
    )


def sold_alert_row(row: pd.Series, checked_at: str) -> dict[str, Any]:
    result = {
        "ticker": row["ticker"],
        "entry_price": number_value(row.get("entry_price")),
        "current_price": None,
        "current_return_pct": None,
        "take_profit_pct": number_value(row.get("take_profit_pct")),
        "stop_loss_pct": number_value(row.get("stop_loss_pct")),
        "position_status": "SOLD",
        "sold_date": text_value(row.get("sold_date")),
        "alert_status": "Sold / No Further Alert",
        "position_note": text_value(row.get("position_note")),
        "checked_at": checked_at,
        "fetch_error": "",
    }
    result["korean_interpretation"] = korean_interpretation_for_alert(result)
    return result


def open_alert_row(row: pd.Series, checked_at: str) -> dict[str, Any]:
    ticker = row["ticker"]
    entry_price = number_value(row.get("entry_price"))
    take_profit_pct = number_value(row.get("take_profit_pct"))
    stop_loss_pct = number_value(row.get("stop_loss_pct"))
    current_price = None
    current_return_pct = None
    fetch_error = ""

    try:
        if not ticker:
            raise ValueError("Missing ticker")
        if entry_price in (None, 0):
            raise ValueError("Missing or invalid entry_price")

        current_price = latest_price(ticker)
        current_return_pct = (current_price - entry_price) / entry_price * 100
    except Exception as exc:
        fetch_error = str(exc)
        print(f"Warning: failed to check {ticker or 'UNKNOWN'}: {exc}")

    result = {
        "ticker": ticker,
        "entry_price": entry_price,
        "current_price": current_price,
        "current_return_pct": current_return_pct,
        "take_profit_pct": take_profit_pct,
        "stop_loss_pct": stop_loss_pct,
        "position_status": "OPEN",
        "sold_date": text_value(row.get("sold_date")),
        "alert_status": alert_status_for(
            current_return_pct,
            take_profit_pct,
            stop_loss_pct,
        ),
        "position_note": text_value(row.get("position_note")),
        "checked_at": checked_at,
        "fetch_error": fetch_error,
    }
    result["korean_interpretation"] = korean_interpretation_for_alert(result)
    return result


def untracked_watchlist_row(
    ticker: str,
    checked_at: str,
    source: str = "daily_growth_priority.csv",
) -> dict[str, Any]:
    current_price = None
    fetch_error = ""

    try:
        current_price = latest_price(ticker)
    except Exception as exc:
        fetch_error = str(exc)
        print(f"Warning: failed to check untracked ticker {ticker}: {exc}")

    result = {
        "ticker": ticker,
        "entry_price": None,
        "current_price": current_price,
        "current_return_pct": None,
        "take_profit_pct": None,
        "stop_loss_pct": None,
        "position_status": "WATCHLIST",
        "sold_date": "",
        "alert_status": "Not In Positions / Research Only",
        "position_note": (
            f"Auto-detected from {source}; add entry_price "
            "to config/my_positions.csv to enable position alerts."
        ),
        "checked_at": checked_at,
        "fetch_error": fetch_error,
    }
    result["korean_interpretation"] = korean_interpretation_for_alert(result)
    return result


def read_untracked_tickers_from_csv(
    source_csv: Path,
    positions: pd.DataFrame,
    existing_watchlist: set[str],
) -> list[str]:
    if not source_csv.exists():
        return []

    try:
        source_df = pd.read_csv(source_csv)
    except Exception as exc:
        print(f"Warning: failed to read {source_csv}: {exc}")
        return []

    if "ticker" not in source_df.columns:
        return []

    tracked_tickers = {
        text_value(ticker).upper()
        for ticker in positions["ticker"].dropna().tolist()
        if text_value(ticker)
    }

    untracked = []
    for value in source_df["ticker"].dropna().tolist():
        ticker = text_value(value).upper()
        if not ticker or ticker in tracked_tickers or ticker in existing_watchlist:
            continue
        untracked.append(ticker)
        existing_watchlist.add(ticker)
    return untracked


def build_position_alerts(positions: pd.DataFrame) -> pd.DataFrame:
    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rows = []

    for _, row in positions.iterrows():
        status = normalize_status(row.get("position_status"))
        if status == "SOLD":
            rows.append(sold_alert_row(row, checked_at))
            continue
        rows.append(open_alert_row(row, checked_at))

    watchlist_tickers: set[str] = set()
    watchlist_sources = [
        (DAILY_PRIORITY_CSV, "daily_growth_priority.csv"),
        (MEGA_CAP_VALUATION_CSV, "mega_cap_valuation_screen.csv"),
    ]
    for source_csv, source_label in watchlist_sources:
        for ticker in read_untracked_tickers_from_csv(
            source_csv,
            positions,
            watchlist_tickers,
        ):
            rows.append(untracked_watchlist_row(ticker, checked_at, source_label))

    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def update_final_report(alerts_df: pd.DataFrame) -> None:
    if not FINAL_REPORT_XLSX.exists():
        print(f"Final report not found. Skipped Position_Alerts sheet: {FINAL_REPORT_XLSX}")
        return

    with pd.ExcelWriter(
        FINAL_REPORT_XLSX,
        engine="openpyxl",
        mode="a",
        if_sheet_exists="replace",
    ) as writer:
        alerts_df.to_excel(writer, sheet_name="Position_Alerts", index=False)

    print(f"Updated {FINAL_REPORT_XLSX} with Position_Alerts sheet")


def write_outputs(alerts_df: pd.DataFrame) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    alerts_df.to_csv(POSITION_ALERTS_CSV, index=False)
    alerts_df.to_excel(POSITION_ALERTS_XLSX, index=False, engine="openpyxl")
    update_final_report(alerts_df)

    print(f"Wrote {POSITION_ALERTS_CSV}")
    print(f"Wrote {POSITION_ALERTS_XLSX}")


def main() -> None:
    positions = read_positions()
    alerts_df = build_position_alerts(positions)
    write_outputs(alerts_df)

    open_count = int((alerts_df["position_status"] == "OPEN").sum())
    sold_count = int((alerts_df["position_status"] == "SOLD").sum())
    watchlist_count = int((alerts_df["position_status"] == "WATCHLIST").sum())
    alert_count = int(
        alerts_df["alert_status"].isin(["Take Profit Alert", "Stop Loss Alert"]).sum()
    )

    print(f"Positions checked: {len(alerts_df)}")
    print(f"Open positions checked with alerts enabled: {open_count}")
    print(f"Sold positions preserved without further alerts: {sold_count}")
    print(f"Untracked priority tickers shown as research-only watchlist: {watchlist_count}")
    print(f"Active alerts: {alert_count}")
    print("Done. Position alerts are research reminders only, not trading advice.")


if __name__ == "__main__":
    main()
