# quant_step1

`quant_step1` is organized into project stages.

## Current Folders

- `screening/`: Current US stock screening tool using `yfinance`.
- `backtesting/`: First-version Growth / Space signal backtest.
- `signal_rules.py`: Shared Growth / Space signal, warning, risk, and action-note rules.

This project does not connect to a brokerage account, does not place trades, and does not predict future stock prices.

## Daily One-Command Run

For normal daily use, run the full pipeline from the project root:

```powershell
py .\run_all_reports.py
```

This runs the screener, backtest, backtest interpretation, enhanced backtest, priority ranking, risk score, long-term quality score, and event risk check in order. It then rebuilds:

```text
output/final_daily_research_report.xlsx
```

The final report starts with an `Executive_Summary` sheet, followed by the detailed sheets:

- `Final_Daily_Priority`
- `Risk_Score`
- `Long_Term_Quality`
- `Event_Risk_Check`
- `Enhanced_Backtest_By_Signal`
- `Signal_Interpretation`

This one-command run is still a research workflow only. It does not connect to a brokerage account, does not place trades, and does not provide investment advice.

## Architecture

- `screening/screen_stocks.py` runs the current-day screener.
- `backtesting/backtest_growth.py` runs historical Growth / Space signal backtests.
- `signal_rules.py` contains the shared Growth / Space technical signal rules.
- `config.yaml` contains ticker lists, screening history period, backtest period, cooldown, and output folder settings.

Both the screener and the backtest import the same Growth / Space signal logic from `signal_rules.py`. This keeps live screening signals and historical backtest signals from drifting apart.

## Strategy Role

`strategy_role` is not a trading command. It explains how each Growth / Space signal should be treated in the research workflow:

- `Pullback Watch` -> `Primary Watch Signal`
- `Trend Positive` -> `Trend Filter`
- `High Volume Risk Monitor` -> `Volatility Monitor / Confirmation Required`
- `Weak Trend / Low Volume` -> `Reversal Monitor`
- `Early Watch` -> `Early Alert Only`
- `Confirmed Watch` -> `Rebound Confirmation Signal`
- `Neutral` -> `No Clear Setup`
- `Data Issue` -> `Data Quality Review`
- `Error` -> `Error / Review Required`

## Configuration

Edit `config.yaml` to reuse the project with another ticker group without changing Python code.

```yaml
growth_tickers:
  - LUNR
  - RKLB
  - ASTS

mega_cap_tickers:
  - NVDA
  - TSLA

screening:
  price_history_period: 1y
  output_dir: output

backtest:
  history_period: 2y
  cooldown_days: 10
  output_dir: output
```

The Growth / Space signal rules can be reused for other high-growth watchlists, but financial interpretation may need industry-specific adjustments.

## Screening

Run the current screener from the project root:

```powershell
py .\screening\screen_stocks.py
```

Or from the `screening` folder:

```powershell
cd .\screening
py screen_stocks.py
```

Screening outputs are written to:

```text
screening/output/
```

See `screening/README.md` for the detailed screening documentation.

## Backtesting

The first backtest applies only to the Growth / Space tickers:

```text
LUNR, RKLB, ASTS, PL, SPCE, ACHR, JOBY
```

It replays historical daily data from `yfinance`, assigns the same technical signal types used by the screener, and measures 5, 20, and 60 trading day forward returns after each signal event.

Run it from the project root:

```powershell
py .\backtesting\backtest_growth.py
```

Or from the `backtesting` folder:

```powershell
cd .\backtesting
py backtest_growth.py
```

Backtesting outputs are written to:

```text
backtesting/output/
```

Output files:

- `growth_signal_backtest_trades.csv`
- `growth_signal_backtest_summary.csv`
- `growth_signal_backtest_by_ticker.csv`
- `growth_signal_backtest_trades.xlsx`
- `growth_signal_backtest_summary.xlsx`
- `growth_signal_backtest_by_ticker.xlsx`
- `growth_signal_backtest_report.xlsx`

The combined workbook includes:

- `Trades`
- `Summary_By_Signal`
- `Summary_By_Ticker`

The backtest uses a 10-trading-day cooldown for the same ticker and same signal so one continuous signal regime is not counted every day.

The former `Avoid` signal was renamed to `Weak Trend / Low Volume` after backtesting showed it did not behave like a pure avoid signal in the Growth / Space universe. The condition is unchanged: price is below the 200-day moving average and current volume is below the 20-day average. The new label describes a weak-trend, low-participation state, not an automatic sell or avoid instruction. This is a useful reminder that signal labels should be validated by backtesting.

Limitations:

- It does not account for transaction costs, slippage, taxes, bid-ask spreads, liquidity constraints, or survivorship bias.
- It does not backtest the mega-cap valuation screen yet.
- It does not prove future profitability.
- It is for research only and is not investment advice.

## Backtest Interpretation

`backtesting/analyze_backtest.py` reads existing backtest output files and creates signal-level and ticker-level interpretation reports. It does not rerun the backtest and does not call `yfinance`.

Run it after `backtest_growth.py`:

```powershell
py .\backtesting\analyze_backtest.py
```

It rates signal effectiveness using event count, average forward returns, win rates, and drawdowns. These ratings are historical research summaries only. They do not prove future profitability and do not include transaction costs, slippage, taxes, liquidity constraints, or survivorship bias.

Interpretation outputs are written to `backtesting/output/`:

- `growth_signal_backtest_interpretation.csv`
- `growth_signal_backtest_interpretation.xlsx`
- `growth_signal_backtest_scorecard.xlsx`
- `growth_signal_ticker_insights.csv`
- `growth_signal_ticker_insights.xlsx`

## Enhanced Backtest

`backtesting/enhance_backtest_growth.py` extends the Growth / Space backtest with more practical research metrics. It reads the existing backtest trades file, downloads ticker and benchmark history, and adds:

- 10 trading day forward return
- SPY and QQQ benchmark returns
- excess returns versus SPY and QQQ
- transaction cost and slippage assumptions
- net returns after cost
- stop-loss and take-profit hit checks
- average gain, average loss, and payoff ratio summaries

Run it after `backtest_growth.py`:

```powershell
py .\backtesting\enhance_backtest_growth.py
```

Enhanced backtest outputs are written to `backtesting/output/`:

- `growth_signal_enhanced_backtest_trades.csv`
- `growth_signal_enhanced_backtest_summary.csv`
- `growth_signal_enhanced_backtest_by_ticker.csv`
- `growth_signal_enhanced_backtest_trades.xlsx`
- `growth_signal_enhanced_backtest_summary.xlsx`
- `growth_signal_enhanced_backtest_by_ticker.xlsx`
- `growth_signal_enhanced_backtest_report.xlsx`

The default assumptions are 0.10% round-trip transaction cost, 0.20% round-trip slippage, -8% stop-loss threshold, and +20% take-profit threshold. These are research assumptions only, not trading instructions.

## Daily Priority Ranking

`rank_screening_results.py` combines the current Growth / Space screening output with the historical backtest interpretation output. When enhanced backtest output is available, it also incorporates net returns after cost, SPY/QQQ excess returns, payoff ratio, stop-loss hit rate, and take-profit hit rate.

Run it after the screener and backtest interpretation are up to date:

```powershell
py .\rank_screening_results.py
```

This ranking is not a buy or sell signal. It is a research prioritization layer that helps decide which tickers deserve closer review. It does not include taxes, liquidity constraints, future news, or survivorship bias, and it does not prove future profitability. The enhanced stop-loss and take-profit fields are event flags within the period, not a full first-hit trade execution simulation.

Daily ranking outputs are written to project-level `output/`:

- `daily_growth_priority.csv`
- `daily_growth_priority.xlsx`
- `daily_growth_priority_report.xlsx`
- `final_daily_research_report.xlsx`

For normal daily review, open `output/final_daily_research_report.xlsx` first. It is the compact final report.

## Growth Risk Score

`risk/risk_score_growth.py` creates a separate risk score for the current Growth / Space tickers. This keeps priority and risk separate:

- `priority_score`: which tickers deserve review first
- `overall_risk_score`: how cautious the review should be

Run it after `rank_screening_results.py`:

```powershell
py .\risk\risk_score_growth.py
```

Risk outputs are written to project-level `output/`:

- `growth_risk_score.csv`
- `growth_risk_score.xlsx`

The script also updates `output/final_daily_research_report.xlsx` with a `Risk_Score` sheet. The risk score combines volatility, liquidity, financial, valuation, and technical risk. It is research context only, not a position-size recommendation or investment advice.

## Long-Term Quality Score

`long_term_quality_score.py` creates a separate long-term quality score for the current Growth / Space tickers. This keeps short-term priority, risk, and long-term business quality separate.

Run it after `risk_score_growth.py`:

```powershell
py .\long_term_quality_score.py
```

Quality outputs are written to project-level `output/`:

- `long_term_growth_quality.csv`
- `long_term_growth_quality.xlsx`

The script also updates `output/final_daily_research_report.xlsx` with a `Long_Term_Quality` sheet. The score uses available `yfinance` fundamentals from the screener, including revenue growth, profitability, cash runway, debt risk, valuation risk, free cash flow, dilution risk, and business quality. It is research context only and should be manually reviewed, especially for early-stage companies where reported fundamentals can be distorted.

## Event Risk Check

`event_risk_checker.py` checks recent `yfinance` news and available calendar data for the current Growth / Space tickers. It is designed to flag whether recent price action may be tied to news, financing risk, launch or mission events, earnings, contracts, partnerships, analyst actions, or other catalysts.

Run it after the daily priority, risk, and long-term quality files are up to date:

```powershell
py .\event_risk_checker.py
```

Event risk outputs are written to project-level `output/`:

- `growth_event_risk.csv`
- `growth_event_risk.xlsx`

The script also updates `output/final_daily_research_report.xlsx` with an `Event_Risk_Check` sheet.

The event risk check is not a news-based buy or sell signal. It is a manual-review layer that helps identify whether a ticker needs extra context before interpreting the technical, risk, or quality scores. It depends on available `yfinance` news data, so missing or sparse news should be treated as data limitation, not as proof that no relevant event exists.
