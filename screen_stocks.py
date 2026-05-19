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
from signal_rules import (  # noqa: E402
    action_note_for_signal,
    clean_number,
    financial_warnings,
    growth_signal_from_row,
    growth_signal_reason,
    number_greater_than,
    number_less_than,
    price_vs_ma,
    risk_level_for_signal,
    strategy_role_for_signal,
    technical_warning,
)


BASE_DIR = Path(__file__).resolve().parent
CONFIG = load_config()
SCREENING_CONFIG = CONFIG["screening"]
GROWTH_TICKERS = CONFIG["growth_tickers"]
MEGA_CAP_TICKERS = CONFIG["mega_cap_tickers"]
OUTPUT_DIR = output_dir_for(BASE_DIR, SCREENING_CONFIG)
YFINANCE_CACHE_DIR = BASE_DIR / ".yf_cache"
GROWTH_OUTPUT = OUTPUT_DIR / "growth_rebound_screen.csv"
MEGA_CAP_OUTPUT = OUTPUT_DIR / "mega_cap_valuation_screen.csv"
GROWTH_EXCEL_OUTPUT = OUTPUT_DIR / "growth_rebound_screen.xlsx"
MEGA_CAP_EXCEL_OUTPUT = OUTPUT_DIR / "mega_cap_valuation_screen.xlsx"
COMBINED_REPORT_OUTPUT = OUTPUT_DIR / "quant_step1_report.xlsx"

PRICE_HISTORY_PERIOD = str(SCREENING_CONFIG.get("price_history_period", "1y"))

INTERPRETATION_NOTES = {
    "NVDA": (
        "Strong fundamentals, but short-term technical overextension should "
        "be monitored."
    ),
    "TSLA": "Expensive relative to current margins and key trend remains weak.",
    "GOOG": (
        "High-quality cash-flow compounder, but recent rally creates timing risk."
    ),
    "AAPL": (
        "High-quality mature compounder; valuation depends on FCF durability "
        "and buybacks."
    ),
}


FUNDAMENTAL_KEYS = {
    "market_cap": "marketCap",
    "revenue": "totalRevenue",
    "revenue_growth": "revenueGrowth",
    "net_income": "netIncomeToCommon",
    "operating_cash_flow": "operatingCashflow",
    "free_cash_flow": "freeCashflow",
    "total_cash": "totalCash",
    "total_debt": "totalDebt",
    "trailing_pe": "trailingPE",
    "price_to_sales": "priceToSalesTrailing12Months",
    "price_to_book": "priceToBook",
    "profit_margin": "profitMargins",
    "operating_margin": "operatingMargins",
}

DEFAULT_VALUATION_PROFILE = {
    "valuation_profile": "default mega-cap profile",
    "interpretation": "generic valuation screen",
    "high_pe": 50,
    "high_ps": 12,
    "high_pb": 20,
}

VALUATION_PROFILES = {
    "NVDA": {
        "valuation_profile": "AI semiconductor growth premium",
        "interpretation": (
            "high valuation can be justified only if revenue growth, "
            "margins, and profitability remain strong"
        ),
        "high_pe": 60,
        "high_ps": 25,
        "high_pb": 35,
    },
    "TSLA": {
        "valuation_profile": "high-uncertainty growth / auto-plus-tech multiple",
        "interpretation": (
            "valuation risk is higher because the market may price both "
            "auto earnings and future optionality"
        ),
        "high_pe": 70,
        "high_ps": 10,
        "high_pb": 15,
    },
    "GOOG": {
        "valuation_profile": "mega-cap cash-flow compounder",
        "interpretation": (
            "valuation should focus on operating margin, FCF, cash position, "
            "and durable revenue growth"
        ),
        "high_pe": 35,
        "high_ps": 9,
        "high_pb": 10,
    },
    "AAPL": {
        "valuation_profile": "mature high-margin cash-flow / buyback compounder",
        "interpretation": (
            "valuation should focus on margin stability, FCF, balance sheet "
            "strength, and slower growth risk"
        ),
        "high_pe": 35,
        "high_ps": 9,
        "high_pb": 45,
    },
}


def calculate_rsi(close: pd.Series, period: int = 14) -> float | None:
    if len(close) <= period:
        return None

    delta = close.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)

    avg_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()

    last_loss = avg_loss.iloc[-1]
    if pd.isna(last_loss):
        return None
    if last_loss == 0:
        return 100.0

    rs = avg_gain.iloc[-1] / last_loss
    rsi = 100 - (100 / (1 + rs))
    return clean_number(rsi)


def percent_return(close: pd.Series, periods: int) -> float | None:
    if len(close) <= periods:
        return None

    start = clean_number(close.iloc[-periods - 1])
    end = clean_number(close.iloc[-1])
    if start in (None, 0) or end is None:
        return None

    return (end / start) - 1


def get_history(ticker: yf.Ticker, symbol: str) -> pd.DataFrame:
    history = ticker.history(period=PRICE_HISTORY_PERIOD, auto_adjust=False)
    if history.empty:
        raise ValueError(f"No price history returned for {symbol}")

    required_columns = {"Close", "Volume"}
    missing_columns = required_columns.difference(history.columns)
    if missing_columns:
        missing = ", ".join(sorted(missing_columns))
        raise ValueError(f"Missing required history columns for {symbol}: {missing}")

    return history.dropna(subset=["Close", "Volume"])


def get_fundamentals(ticker: yf.Ticker) -> dict[str, float | None]:
    try:
        info = ticker.get_info()
    except Exception as exc:
        print(f"Warning: failed to fetch fundamentals: {exc}")
        info = {}

    return {
        output_key: clean_number(info.get(yfinance_key))
        for output_key, yfinance_key in FUNDAMENTAL_KEYS.items()
    }


def calculate_technicals(history: pd.DataFrame) -> dict[str, Any]:
    close = history["Close"]
    volume = history["Volume"]

    last_close = clean_number(close.iloc[-1])
    avg_volume_20 = clean_number(volume.tail(20).mean()) if len(volume) >= 20 else None
    latest_volume = clean_number(volume.iloc[-1])
    volume_ratio = (
        latest_volume / avg_volume_20
        if latest_volume is not None and avg_volume_20 not in (None, 0)
        else None
    )
    ma_50 = clean_number(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else None
    ma_200 = clean_number(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else None

    return {
        "last_close_price": last_close,
        "rsi_14": calculate_rsi(close, 14),
        "avg_volume_20d": avg_volume_20,
        "volume_ratio_vs_20d": clean_number(volume_ratio),
        "return_20d": percent_return(close, 20),
        "return_60d": percent_return(close, 60),
        "ma_50d": ma_50,
        "ma_200d": ma_200,
        "price_vs_50ma": price_vs_ma(last_close, ma_50),
        "price_vs_200ma": price_vs_ma(last_close, ma_200),
    }


def missing_important_financial_fields(row: dict[str, Any]) -> list[str]:
    required_fields = [
        "market_cap",
        "revenue",
        "operating_cash_flow",
        "free_cash_flow",
        "total_cash",
        "total_debt",
    ]
    return [field for field in required_fields if row.get(field) is None]


def important_financial_data_missing(row: dict[str, Any]) -> bool:
    return bool(missing_important_financial_fields(row))


def valuation_profile_for(symbol: str) -> dict[str, Any]:
    return VALUATION_PROFILES.get(symbol.upper(), DEFAULT_VALUATION_PROFILE)


def calculate_debt_to_cash(row: dict[str, Any]) -> float | None:
    total_debt = clean_number(row.get("total_debt"))
    total_cash = clean_number(row.get("total_cash"))
    if total_debt is None or total_cash in (None, 0):
        return None
    return total_debt / total_cash


def quality_score(row: dict[str, Any]) -> int:
    score = 0
    debt_to_cash = clean_number(row.get("debt_to_cash"))

    if number_greater_than(row.get("profit_margin"), 0.15):
        score += 1
    if number_greater_than(row.get("operating_margin"), 0.20):
        score += 1
    if number_greater_than(row.get("free_cash_flow"), 0):
        score += 1
    if number_greater_than(row.get("revenue_growth"), 0.05):
        score += 1
    if debt_to_cash is not None and debt_to_cash < 1.5:
        score += 1

    return score


def valuation_risk_score(row: dict[str, Any], profile: dict[str, Any]) -> int:
    score = 0

    if number_greater_than(row.get("trailing_pe"), profile["high_pe"]):
        score += 1
    if number_greater_than(row.get("price_to_sales"), profile["high_ps"]):
        score += 1
    if number_greater_than(row.get("price_to_book"), profile["high_pb"]):
        score += 1
    if number_less_than(row.get("profit_margin"), 0.05):
        score += 1
    if number_less_than(row.get("revenue_growth"), 0):
        score += 1

    return score


def valuation_status(row: dict[str, Any]) -> str:
    required_fields = [
        "trailing_pe",
        "price_to_sales",
        "price_to_book",
        "profit_margin",
        "operating_margin",
        "free_cash_flow",
    ]
    available_fields = [field for field in required_fields if row.get(field) is not None]
    if len(available_fields) < 3:
        return "Insufficient Data"

    risk_score = row.get("valuation_risk_score")
    q_score = row.get("quality_score")

    if risk_score >= 3 and q_score >= 4:
        return "High Quality / Premium"
    if risk_score >= 3 and q_score <= 3:
        return "Expensive / Needs Growth Justification"
    if risk_score <= 1 and q_score >= 4:
        return "High Quality / Reasonable vs Profile"
    return "Fair / Watch Valuation"


def valuation_reason(row: dict[str, Any], profile: dict[str, Any]) -> str:
    status = row.get("valuation_status")
    quality = row.get("quality_score")
    risk = row.get("valuation_risk_score")
    return (
        f"{status}: profile='{profile['valuation_profile']}', "
        f"quality_score={quality}, valuation_risk_score={risk}. "
        f"{profile['interpretation']}."
    )


def apply_valuation_analysis(symbol: str, row: dict[str, Any]) -> dict[str, Any]:
    profile = valuation_profile_for(symbol)
    row["valuation_profile"] = profile["valuation_profile"]
    row["debt_to_cash"] = calculate_debt_to_cash(row)
    row["quality_score"] = quality_score(row)
    row["valuation_risk_score"] = valuation_risk_score(row, profile)
    row["valuation_status"] = valuation_status(row)
    row["valuation_reason"] = valuation_reason(row, profile)
    row["interpretation_note"] = INTERPRETATION_NOTES.get(
        symbol.upper(),
        "Review valuation profile, fundamentals, and technical trend together.",
    )
    return row


def empty_error_row(symbol: str, group: str, error: Exception) -> dict[str, Any]:
    base_columns = {
        "ticker": symbol,
        "group": group,
        "last_close_price": None,
        "rsi_14": None,
        "avg_volume_20d": None,
        "volume_ratio_vs_20d": None,
        "return_20d": None,
        "return_60d": None,
        "ma_50d": None,
        "ma_200d": None,
        "price_vs_50ma": "Insufficient Data",
        "price_vs_200ma": "Insufficient Data",
        **{key: None for key in FUNDAMENTAL_KEYS},
        "signal": "Error",
        "signal_reason": str(error),
        "financial_warning": None,
        "technical_warning": None,
        "risk_level": "Unknown",
        "strategy_role": strategy_role_for_signal("Error"),
        "action_note": "Could not screen this ticker.",
        "valuation_profile": None,
        "valuation_status": "Insufficient Data",
        "valuation_reason": str(error),
        "interpretation_note": None,
        "quality_score": None,
        "valuation_risk_score": None,
        "debt_to_cash": None,
        "error": str(error),
    }
    return base_columns


def screen_ticker(symbol: str, group: str) -> dict[str, Any]:
    try:
        ticker = yf.Ticker(symbol)
        history = get_history(ticker, symbol)
        row = {
            "ticker": symbol,
            "group": group,
            **calculate_technicals(history),
            **get_fundamentals(ticker),
            "error": None,
        }
        row["financial_warning"] = financial_warnings(row)

        if group == "Growth / Space rebound":
            technical_signal = growth_signal_from_row(row)
            if technical_signal == "Weak Trend / Low Volume":
                row["signal"] = technical_signal
            elif important_financial_data_missing(row):
                row["signal"] = "Data Issue"
            else:
                row["signal"] = technical_signal
            row["signal_reason"] = growth_signal_reason(
                row, missing_important_financial_fields(row)
            )
            row["technical_warning"] = technical_warning(row, group)
            row["risk_level"] = risk_level_for_signal(row["signal"])
            row["strategy_role"] = strategy_role_for_signal(row["signal"])
            row["action_note"] = action_note_for_signal(symbol, row["signal"])
            row["valuation_profile"] = None
            row["valuation_status"] = None
            row["valuation_reason"] = None
            row["interpretation_note"] = None
            row["quality_score"] = None
            row["valuation_risk_score"] = None
            row["debt_to_cash"] = None
        else:
            row["signal"] = None
            row["signal_reason"] = None
            row = apply_valuation_analysis(symbol, row)
            row["technical_warning"] = technical_warning(row, group)
            row["risk_level"] = None
            row["strategy_role"] = "Mega-Cap Valuation Review"
            row["action_note"] = None

        return row
    except Exception as exc:
        print(f"Error: failed to screen {symbol}: {exc}")
        return empty_error_row(symbol, group, exc)


def screen_group(tickers: list[str], group: str) -> pd.DataFrame:
    rows = []
    for symbol in tickers:
        print(f"Screening {symbol}...")
        rows.append(screen_ticker(symbol, group))
    return pd.DataFrame(rows)


def build_screens() -> tuple[pd.DataFrame, pd.DataFrame]:
    growth_df = screen_group(GROWTH_TICKERS, "Growth / Space rebound")
    mega_cap_df = screen_group(MEGA_CAP_TICKERS, "Mega-cap valuation")
    return growth_df, mega_cap_df


def write_csv_outputs(growth_df: pd.DataFrame, mega_cap_df: pd.DataFrame) -> None:
    growth_df.to_csv(GROWTH_OUTPUT, index=False)
    mega_cap_df.to_csv(MEGA_CAP_OUTPUT, index=False)
    print(f"Wrote {GROWTH_OUTPUT}")
    print(f"Wrote {MEGA_CAP_OUTPUT}")


def write_excel_outputs(growth_df: pd.DataFrame, mega_cap_df: pd.DataFrame) -> None:
    growth_df.to_excel(GROWTH_EXCEL_OUTPUT, index=False, engine="openpyxl")
    mega_cap_df.to_excel(MEGA_CAP_EXCEL_OUTPUT, index=False, engine="openpyxl")

    with pd.ExcelWriter(COMBINED_REPORT_OUTPUT, engine="openpyxl") as writer:
        growth_df.to_excel(writer, sheet_name="Growth_Rebound", index=False)
        mega_cap_df.to_excel(writer, sheet_name="Mega_Cap_Valuation", index=False)

    print(f"Wrote {GROWTH_EXCEL_OUTPUT}")
    print(f"Wrote {MEGA_CAP_EXCEL_OUTPUT}")
    print(f"Wrote {COMBINED_REPORT_OUTPUT}")


def write_outputs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    YFINANCE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    yf.set_tz_cache_location(str(YFINANCE_CACHE_DIR))

    growth_df, mega_cap_df = build_screens()
    write_csv_outputs(growth_df, mega_cap_df)
    write_excel_outputs(growth_df, mega_cap_df)

    print("Done. Results are screening indicators only, not price predictions.")


if __name__ == "__main__":
    write_outputs()
