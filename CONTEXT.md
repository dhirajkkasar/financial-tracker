# CONTEXT.md — Financial Portfolio Tracker (domain glossary)

Single household portfolio context. Implementation details live in code/ADRs, never here.

## Assets

- **US Stock**: any US-listed equity or ETF held via a foreign broker. Stored as asset type `STOCK_US`, `currency=USD`, `identifier` = ticker symbol (e.g. `AAPL`). `VOO` (ETF) is a US Stock, not a separate type.
- **RSU Vest**: employer stock granted at vest, distinct from a market purchase. Stored as `STOCK_US` with txn type `VEST` (preserves vesting history for perquisite-tax notes).
- **Ticker**: canonical asset identity for US holdings. `identifier` = `Symbol` upper-cased; `ISIN` kept as reference in notes/`isin` field only (price feed looks up `identifier` via YFinance).

## IBKR import

- **IBKR Flex Trades CSV**: the Activity Flex Query export (`Trades` section, CSV). The only supported IBKR report in v1.
- **IBKR Trade**: one `ExchTrade` row on a `STK` asset. `Buy/Sell` column decides direction (`BUY` → outflow, `SELL` → inflow); Quantity sign is the fallback. Units stored as absolute value; fractional units allowed.
- **TradeID**: IBKR's native row id. Imported as `txn_id = ibkr_<TradeID>` — the deduplication key, stable across re-imports.
- **Monthly USD/INR rate**: user-supplied conversion rate per calendar month (`YYYY-MM → rate`), same convention as Fidelity imports. Missing month blocks preview; broker `FXRateToBase` column is ignored.
- **Cost basis (BUY)**: `(|Proceeds| + |Commission| + |Taxes|) × monthly rate`, outflow (negative). **Net proceeds (SELL)**: `(|Proceeds| − |Commission| − |Taxes|) × monthly rate`, inflow (positive).
- **Out of scope (v1)**: dividends, withholding tax, options, RSU/ESPP grants, non-USD `CurrencyPrimary`, non-`STK` asset classes. Non-trade rows are skipped with a warning.
