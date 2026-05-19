# quant_step1

`quant_step1` is a first-version US stock screening tool for two ticker groups:

- Growth / Space rebound candidates: `LUNR`, `RKLB`, `ASTS`, `PL`, `SPCE`, `ACHR`, `JOBY`
- Mega-cap valuation screen: `NVDA`, `TSLA`, `GOOG`, `AAPL`

The script uses `yfinance` for price, volume, and basic fundamental data. It does not connect to any brokerage account and does not place trades.

## Setup

```powershell
cd quant_step1
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

```powershell
python .\screening\screen_stocks.py
```

The script writes:

- `screening/output/growth_rebound_screen.csv`
- `screening/output/mega_cap_valuation_screen.csv`
- `screening/output/growth_rebound_screen.xlsx`
- `screening/output/mega_cap_valuation_screen.xlsx`
- `screening/output/quant_step1_report.xlsx`

The combined workbook includes:

- `Growth_Rebound`
- `Mega_Cap_Valuation`

## Metrics

For each ticker, the script calculates:

- Last close price
- RSI 14
- 20-day average volume
- Volume ratio versus 20-day average
- 20-day return
- 60-day return
- 50-day moving average
- 200-day moving average
- Whether price is above or below the 50-day and 200-day moving averages

Where available from `yfinance`, it also collects:

- Market cap
- Revenue
- Revenue growth
- Net income
- Operating cash flow
- Free cash flow
- Total cash
- Total debt
- Trailing PE
- Price to sales
- Price to book
- Profit margin
- Operating margin

## Signal Logic

### Growth / Space screen

- `Confirmed Watch`: RSI is below 35, volume ratio is above 1.5, and price is above or close to the 50-day moving average.
- `Early Watch`: RSI is below 35 and volume ratio is above 1.5, but price is not yet above or close to the 50-day moving average.
- `Trend Positive`: Price is above both the 50-day and 200-day moving averages, with RSI between 40 and 70.
- `Pullback Watch`: Price is below the 50-day moving average but above the 200-day moving average, with RSI between 35 and 50.
- `High Volume Risk Monitor`: Price is below both the 50-day and 200-day moving averages while volume ratio is above 1.5.
- `Weak Trend / Low Volume`: Price is below the 200-day moving average and current volume is below the 20-day average.
- `Data Issue`: Important financial data is missing from `yfinance`, so the ticker should be reviewed manually.
- `Neutral`: Anything else.

The CSV includes `signal_reason` so missing data can be separated from confirmed risk conditions.

`Weak Trend / Low Volume` replaced the older `Avoid` label because backtesting showed the condition did not behave like a pure avoid signal. It is a weak-trend condition, not an automatic sell or avoid instruction.

The output also includes `financial_warning` for unusual fundamental values such as extreme revenue growth, extreme price-to-sales ratios, or negative price-to-book values. These warnings are data quality and interpretation flags, not trade signals.

The output also includes:

- `technical_warning`: Technical interpretation flags such as overbought conditions, short-term extension, weak volume, below-trend risk, or high-volume trading below key moving averages.
- `risk_level`: A simple Growth / Space risk label derived from the signal. Growth names are not marked Low risk because early-stage and high-growth equities can remain volatile even when trend conditions are positive.
- `action_note`: A watchlist note for interpretation. These notes are not buy or sell recommendations.

### Mega-cap valuation screen

The mega-cap valuation screen is profile-adjusted by ticker. It uses different valuation thresholds for `NVDA`, `TSLA`, `GOOG`, and `AAPL` instead of applying one generic PER/PSR/PBR rule to all of them.

The output includes:

- `valuation_profile`
- `valuation_status`
- `valuation_reason`
- `quality_score`
- `valuation_risk_score`
- `debt_to_cash`

The valuation status is a scenario indicator only:

- `High Quality / Reasonable vs Profile`
- `Fair / Watch Valuation`
- `Expensive / Needs Growth Justification`
- `High Quality / Premium`
- `Insufficient Data`

This tool does not predict future stock prices. It is only a screening aid for comparing valuation scenarios. It intentionally avoids using `Cheap` too aggressively for mega-cap technology stocks.

The mega-cap output also includes:

- `technical_warning`: Technical flags such as overbought conditions, short-term extension, below-trend risk, weak-volume uptrends, and AAPL-specific high P/B context.
- `interpretation_note`: A ticker-specific scenario note that should be read together with valuation profile, quality score, valuation risk score, and technical trend.

## Next Step: Backtesting

Full backtesting is not implemented yet. The next phase should test forward returns after growth signals:

- 5 trading day return after `Early Watch`
- 20 trading day return after `Early Watch`
- 60 trading day return after `Early Watch`
- 5 trading day return after `Confirmed Watch`
- 20 trading day return after `Confirmed Watch`
- 60 trading day return after `Confirmed Watch`

## Notes

`yfinance` data availability varies by ticker and over time. If one ticker fails, the script logs the error, continues with the remaining tickers, and includes an error message in the output row for the failed ticker.

This tool does not provide investment advice. It does not connect to a brokerage account, does not place trades, and does not predict future stock prices.
