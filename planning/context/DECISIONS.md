# Decisions and Source-of-Truth Notes

## Workflow

- Project work should move to GitHub: issues for tasks, branches for implementation, PRs for review/approval.
- No new task starts until Uriel explicitly approves continuing from the latest completed task.

## Scope

- Build a modular research pipeline for challenging and evaluating options trades.
- MVP should be research/scanning/backtesting/reporting first, not live execution.
- Do not build a full historical-options backtesting engine from scratch for the MVP.
- Validate stock-level signal quality before spending effort on complex options simulation.

## Data and Tracking Sources

- For Uriel's options preferences, the source of truth discovered earlier was Google Sheet `Options Setups Tracker`, especially tabs `Setups`, `Executed Trades`, `Candidates - May 18 Week`, and `Rules`.
- Important correction: rows in `Executed Trades` must **not** be assumed to represent Uriel's current open options. Current open positions must be re-identified from the correct source before answering.
- Yahoo option quotes are often stale or broken (`bid/ask 0/0`, IV 0%, stale last trade). Scanner output must be treated as candidates only until live broker quotes confirm liquidity and price.

## Trading Constraints / Preferences Observed

- Uriel prefers short-dated, defined-risk options ideas, but wants discipline and clear candidate cards.
- For continuation setups:
  - LONG setups use OTM calls.
  - SHORT setups use ITM puts.
  - Default max option premium: `$1`.
  - Default expiry window previously used: 6–45 DTE.
  - Do not show/buy options with less than 6 days to expiry.
  - Require strong liquidity/volume/open interest where possible.
  - Avoid adding to losing options.
  - Take profits quickly around events.
- Uriel prefers buying options only in some contexts because he does not want assignment/stock risk.
- Long calls, long puts, long straddles, and long strangles are acceptable structures to study because max loss is premium paid.

## Risk Framing

- Scanner output is not investment advice and not an automatic trade recommendation.
- Always require live bid/ask verification in broker before considering entry.
- Avoid market orders in options.
- Backtests are guilty until proven innocent: watch for look-ahead bias, slippage, transaction costs, stale data, and low sample size.
