from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

import pandas as pd
import yfinance as yf

from config_loader import PROJECT_ROOT, load_config


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"

EVENT_RISK_CSV = OUTPUT_DIR / "growth_event_risk.csv"
EVENT_RISK_XLSX = OUTPUT_DIR / "growth_event_risk.xlsx"
FINAL_REPORT_XLSX = OUTPUT_DIR / "final_daily_research_report.xlsx"

DAILY_PRIORITY_CSV = OUTPUT_DIR / "daily_growth_priority.csv"
RISK_CSV = OUTPUT_DIR / "growth_risk_score.csv"
QUALITY_CSV = OUTPUT_DIR / "long_term_growth_quality.csv"
ENHANCED_SUMMARY_CSV = (
    BASE_DIR / "backtesting" / "output" / "growth_signal_enhanced_backtest_summary.csv"
)
INTERPRETATION_CSV = (
    BASE_DIR / "backtesting" / "output" / "growth_signal_backtest_interpretation.csv"
)

RECENT_NEWS_DAYS = 14
MAX_NEWS_TITLES = 5

POSITIVE_KEYWORDS = {
    "award",
    "contract",
    "customer",
    "launch",
    "mission",
    "milestone",
    "nasa",
    "order",
    "partnership",
    "raise guidance",
    "upgrade",
}

NEGATIVE_KEYWORDS = {
    "accident",
    "bankruptcy",
    "convertible",
    "debt",
    "delay",
    "delisting",
    "dilution",
    "downgrade",
    "failure",
    "going concern",
    "investigation",
    "lawsuit",
    "miss",
    "offering",
    "public offering",
    "reverse split",
}

EVENT_KEYWORDS = {
    "conference",
    "earnings",
    "investor day",
    "launch",
    "mission",
    "presentation",
}


def text_value(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except TypeError:
        pass
    return str(value)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        parsed = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.to_pydatetime()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def nested_get(data: dict[str, Any], keys: list[str]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def parse_news_item(item: dict[str, Any]) -> dict[str, Any]:
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    title = (
        item.get("title")
        or content.get("title")
        or nested_get(item, ["content", "title"])
        or ""
    )
    summary = item.get("summary") or content.get("summary") or ""
    publisher = (
        item.get("publisher")
        or content.get("provider", {}).get("displayName")
        or content.get("provider")
        or ""
    )
    link = (
        item.get("link")
        or item.get("url")
        or content.get("canonicalUrl", {}).get("url")
        or content.get("clickThroughUrl", {}).get("url")
        or ""
    )
    published_at = parse_timestamp(
        item.get("providerPublishTime")
        or item.get("pubDate")
        or content.get("pubDate")
        or content.get("displayTime")
    )
    return {
        "title": text_value(title).strip(),
        "summary": text_value(summary).strip(),
        "publisher": text_value(publisher).strip(),
        "link": text_value(link).strip(),
        "published_at": published_at,
    }


def recent_news(news_items: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    cutoff = now_utc() - timedelta(days=days)
    parsed_items = [parse_news_item(item) for item in news_items if isinstance(item, dict)]
    recent = []
    undated = []
    for item in parsed_items:
        published_at = item.get("published_at")
        if published_at is None:
            undated.append(item)
        elif published_at >= cutoff:
            recent.append(item)
    recent.sort(key=lambda item: item.get("published_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return recent or undated[:MAX_NEWS_TITLES]


def matched_keywords(text: str, keywords: set[str]) -> list[str]:
    lowered = text.lower()
    matches = []
    for keyword in keywords:
        pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
        if re.search(pattern, lowered):
            matches.append(keyword)
    return sorted(matches)


def summarize_titles(items: list[dict[str, Any]]) -> str:
    titles = [text_value(item.get("title")) for item in items if text_value(item.get("title"))]
    if not titles:
        return "No recent yfinance news items found."
    return " | ".join(titles[:MAX_NEWS_TITLES])


def summarize_links(items: list[dict[str, Any]]) -> str:
    links = [text_value(item.get("link")) for item in items if text_value(item.get("link"))]
    return "; ".join(links[:MAX_NEWS_TITLES]) if links else ""


def get_calendar_note(ticker: yf.Ticker) -> str:
    try:
        calendar = ticker.calendar
    except Exception:
        return ""

    if calendar is None:
        return ""
    try:
        if isinstance(calendar, pd.DataFrame) and not calendar.empty:
            return "; ".join(
                f"{index}: {value}"
                for index, value in calendar.iloc[:, 0].dropna().head(5).items()
            )
        if isinstance(calendar, dict):
            return "; ".join(
                f"{key}: {value}" for key, value in list(calendar.items())[:5] if value
            )
    except Exception:
        return ""
    return ""


def classify_event_risk(
    recent_items: list[dict[str, Any]],
    positive_matches: list[str],
    negative_matches: list[str],
    event_matches: list[str],
    fetch_error: str,
) -> tuple[str, bool, str]:
    if fetch_error:
        return "Unknown / Data Error", True, f"Could not fetch news cleanly: {fetch_error}"
    if not recent_items:
        return "Data Limited", True, "No recent yfinance news items were available."
    if negative_matches:
        return (
            "High",
            True,
            "Negative or financing-risk keywords appeared in recent news; manual review is required.",
        )
    if event_matches and positive_matches:
        return (
            "Medium-High",
            True,
            "Recent catalyst or event keywords appeared; verify whether price action is event-driven.",
        )
    if event_matches or len(recent_items) >= 5:
        return (
            "Medium",
            True,
            "Recent event flow is active enough to justify manual review.",
        )
    if positive_matches:
        return (
            "Medium",
            True,
            "Positive catalyst keywords appeared; confirm source quality and market impact.",
        )
    return "Low", False, "No obvious event-risk keywords were found in recent yfinance news."


def analyze_ticker(ticker_symbol: str) -> dict[str, Any]:
    checked_at = now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")
    fetch_error = ""
    news_items: list[dict[str, Any]] = []
    calendar_note = ""

    try:
        ticker = yf.Ticker(ticker_symbol)
        raw_news = ticker.news
        if isinstance(raw_news, list):
            news_items = recent_news(raw_news, RECENT_NEWS_DAYS)
        calendar_note = get_calendar_note(ticker)
    except Exception as exc:
        fetch_error = str(exc)

    combined_text = " ".join(
        f"{item.get('title', '')} {item.get('summary', '')}" for item in news_items
    )
    if calendar_note:
        combined_text = f"{combined_text} {calendar_note}"

    positive_matches = matched_keywords(combined_text, POSITIVE_KEYWORDS)
    negative_matches = matched_keywords(combined_text, NEGATIVE_KEYWORDS)
    event_matches = matched_keywords(combined_text, EVENT_KEYWORDS)
    risk_level, needs_manual_review, risk_reason = classify_event_risk(
        news_items,
        positive_matches,
        negative_matches,
        event_matches,
        fetch_error,
    )

    return {
        "ticker": ticker_symbol,
        "checked_at": checked_at,
        "lookback_days": RECENT_NEWS_DAYS,
        "recent_news_count": len(news_items),
        "event_risk_level": risk_level,
        "positive_catalyst": "; ".join(positive_matches) if positive_matches else None,
        "negative_catalyst": "; ".join(negative_matches) if negative_matches else None,
        "upcoming_or_event_keywords": "; ".join(event_matches) if event_matches else None,
        "calendar_note": calendar_note or None,
        "needs_manual_review": needs_manual_review,
        "event_risk_reason": risk_reason,
        "recent_news_summary": summarize_titles(news_items),
        "source_url": summarize_links(news_items) or None,
        "fetch_error": fetch_error or None,
    }


def build_event_risk_report(tickers: list[str]) -> pd.DataFrame:
    rows = []
    for ticker in tickers:
        print(f"Checking event risk for {ticker}...")
        rows.append(analyze_ticker(ticker))
    risk_order = {
        "High": 4,
        "Medium-High": 3,
        "Medium": 2,
        "Data Limited": 1,
        "Unknown / Data Error": 1,
        "Low": 0,
    }
    df = pd.DataFrame(rows)
    df["_risk_order"] = df["event_risk_level"].map(risk_order).fillna(0)
    df = df.sort_values(by=["_risk_order", "ticker"], ascending=[False, True])
    return df.drop(columns=["_risk_order"]).reset_index(drop=True)


def read_csv_if_exists(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None


def update_final_report(event_df: pd.DataFrame) -> None:
    priority_df = read_csv_if_exists(DAILY_PRIORITY_CSV)
    risk_df = read_csv_if_exists(RISK_CSV)
    quality_df = read_csv_if_exists(QUALITY_CSV)
    enhanced_df = read_csv_if_exists(ENHANCED_SUMMARY_CSV)
    interpretation_df = read_csv_if_exists(INTERPRETATION_CSV)

    with pd.ExcelWriter(FINAL_REPORT_XLSX, engine="openpyxl") as writer:
        if priority_df is not None:
            priority_df.to_excel(writer, sheet_name="Final_Daily_Priority", index=False)
        if risk_df is not None:
            risk_df.to_excel(writer, sheet_name="Risk_Score", index=False)
        if quality_df is not None:
            quality_df.to_excel(writer, sheet_name="Long_Term_Quality", index=False)
        event_df.to_excel(writer, sheet_name="Event_Risk_Check", index=False)
        if enhanced_df is not None:
            enhanced_df.to_excel(
                writer, sheet_name="Enhanced_Backtest_By_Signal", index=False
            )
        if interpretation_df is not None:
            interpretation_df.to_excel(
                writer, sheet_name="Signal_Interpretation", index=False
            )


def main() -> None:
    config = load_config(PROJECT_ROOT / "config.yaml")
    tickers = config.get("growth_tickers", [])
    if not tickers:
        print("No growth_tickers found in config.yaml.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    event_df = build_event_risk_report(tickers)
    event_df.to_csv(EVENT_RISK_CSV, index=False)
    event_df.to_excel(EVENT_RISK_XLSX, index=False, engine="openpyxl")
    update_final_report(event_df)

    print(f"Wrote {EVENT_RISK_CSV}")
    print(f"Wrote {EVENT_RISK_XLSX}")
    print(f"Updated {FINAL_REPORT_XLSX} with Event_Risk_Check sheet")
    print(f"Checked tickers: {len(event_df)}")
    print("Done. Event risk is research context only, not investment advice.")


if __name__ == "__main__":
    main()
