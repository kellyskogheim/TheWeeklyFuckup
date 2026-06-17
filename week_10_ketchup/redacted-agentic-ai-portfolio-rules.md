# Agentic AI Infrastructure Portfolio Rules

## Account

- Robinhood account nickname: Nick
- Account number: 999999999
- Strategy capital: about half of account value at launch
- Initial target capital: about $160, based on $320 account value
- Trade universe: equities and ETFs only
- Options, margin, shorting, crypto, futures, and event contracts are out of scope unless explicitly changed later.

## Initial Portfolio Target

- VGT: $55, broad U.S. technology exposure
- SMH: $50, semiconductor and AI compute infrastructure exposure
- AIQ: $25, broader AI theme exposure
- SGOV: $30, short-term Treasury ETF / cash-like ballast and dry powder

This is a target allocation, not standing authorization to trade.

## Trading Workflow

- Monitoring may suggest trades.
- Order reviews may be generated when requested by the user.
- No buy or sell order may be placed without explicit user confirmation in the current thread.
- Prefer regular-hours, good-for-day orders.
- Prefer dollar-based market reviews for small fractional buys unless the user asks for limit orders.
- Surface Robinhood broker alerts and required quote disclosures before asking for confirmation.

## Monitoring Rules

### Buy-Low Alerts

Suggest adding from cash or SGOV when one of the AI positions is down meaningfully:

- A position falls 5% or more below its average cost.
- A position falls 8% or more from a recent monitored high.
- The broad AI/semiconductor theme sells off while the account still has cash or SGOV available.

Suggestions should be modest, usually $10 to $25, unless the user asks for a larger move.

### Trim-High Alerts

Suggest trimming when gains become meaningful:

- A position rises 12% to 15% above average cost.
- A position rises sharply in one day and becomes overweight.
- A position grows above 45% of the AI infrastructure sleeve.

Suggestions should usually trim $10 to $25 and move proceeds to SGOV or cash.

### Recover-Principal Rule

If the AI infrastructure sleeve grows from roughly $160 to $200-$250:

- Suggest selling enough to recover the original invested principal.
- Suggest moving recovered principal to SGOV, cash, or another safer holding.
- Leave remaining profits invested only if the user wants continued upside exposure.

### Risk Controls

- Do not chase a spike without acknowledging the risk of reversal.
- Do not suggest adding to a falling position repeatedly without noting concentration risk.
- Do not suggest trades based only on one stale after-hours quote.
- If markets are closed, provide suggestions only as watchlist guidance unless the user asks for an order review.
- If Robinhood data is unavailable, say so and do not infer positions or prices.

## Monitoring Output

Each monitoring check should report:

- Current account value and buying power.
- Current positions, if any.
- Approximate value and unrealized gain/loss for VGT, SMH, AIQ, and SGOV.
- Any triggered rules.
- Suggested action, if any.
- Whether an order review is recommended.

If nothing actionable is triggered, keep the update short.

## Notification Intent

Monitoring should post suggestions into the synced Codex/ChatGPT thread so the user can see them on iPhone if notifications are enabled. Robinhood app notifications may be used separately for raw price, fill, or account alerts, but Robinhood will not apply these strategy rules.
