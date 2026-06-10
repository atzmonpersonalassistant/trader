"""
QuantConnect/LEAN POC: defined-risk ETF credit spread research algorithm.

Research only. Not live trading. Do not deploy live without separate review.
"""

from AlgorithmImports import *  # type: ignore  # QuantConnect runtime import


def calculate_safe_spread_quantity(portfolio_value, max_risk_fraction, spread_width):
    """Return spread quantity without exceeding max width-based risk budget."""
    if portfolio_value <= 0 or max_risk_fraction <= 0 or spread_width <= 0:
        return 0
    max_risk_dollars = portfolio_value * max_risk_fraction
    one_spread_width_risk = spread_width * 100
    return int(max_risk_dollars // one_spread_width_risk)


class SpyQqqCreditSpreadPoc(QCAlgorithm):
    """Small defined-risk options strategy scaffold for QuantConnect Cloud."""

    def Initialize(self):
        self.SetStartDate(2023, 1, 1)
        self.SetEndDate(2024, 1, 1)
        self.SetCash(100000)

        self.underlying_ticker = self.GetParameter("underlying") or "SPY"
        if self.underlying_ticker not in {"SPY", "QQQ"}:
            raise ValueError("underlying must be SPY or QQQ for this POC")

        self.strategy = self.GetParameter("strategy") or "bear_call"
        if self.strategy not in {"bear_call", "bull_put"}:
            raise ValueError("strategy must be bear_call or bull_put")

        self.min_dte = int(self.GetParameter("min_dte") or 14)
        self.max_dte = int(self.GetParameter("max_dte") or 45)
        self.short_delta_target = float(self.GetParameter("short_delta_target") or 0.20)
        self.spread_width = float(self.GetParameter("spread_width") or 10)
        self.max_risk_fraction = float(self.GetParameter("max_risk_fraction") or 0.005)

        if self.min_dte < 1 or self.max_dte < self.min_dte:
            raise ValueError("invalid DTE range")
        if self.max_risk_fraction <= 0 or self.max_risk_fraction > 0.02:
            raise ValueError("POC max_risk_fraction must be >0 and <=2%")

        equity = self.AddEquity(self.underlying_ticker, Resolution.Minute)
        self.underlying = equity.Symbol
        option = self.AddOption(self.underlying_ticker, Resolution.Minute)
        option.SetFilter(lambda u: u.IncludeWeeklys().Strikes(-30, 30).Expiration(self.min_dte, self.max_dte))
        self.option_symbol = option.Symbol

        self.SetWarmUp(5, Resolution.Daily)
        self.open_ticket_ids = set()
        self.last_entry_date = None

    def OnData(self, slice):
        if self.IsWarmingUp:
            return
        if self.Portfolio.Invested:
            return
        if self.last_entry_date == self.Time.date():
            return
        if self.Time.hour != 10 or self.Time.minute < 30:
            return

        chain = slice.OptionChains.get(self.option_symbol)
        if not chain:
            return

        contracts = [c for c in chain if self.min_dte <= (c.Expiry.date() - self.Time.date()).days <= self.max_dte]
        if self.strategy == "bear_call":
            short_leg = self._select_short_contract(contracts, OptionRight.Call)
            if not short_leg:
                return
            long_leg = self._select_long_call(contracts, short_leg)
        else:
            short_leg = self._select_short_contract(contracts, OptionRight.Put)
            if not short_leg:
                return
            long_leg = self._select_long_put(contracts, short_leg)

        if not long_leg:
            return

        width = abs(long_leg.Strike - short_leg.Strike)
        qty = calculate_safe_spread_quantity(
            portfolio_value=self.Portfolio.TotalPortfolioValue,
            max_risk_fraction=self.max_risk_fraction,
            spread_width=width,
        )
        if qty < 1:
            self.Debug(f"Skip trade: one spread width ${width} exceeds risk budget")
            return
        qty = min(qty, 1)  # POC safety: one spread max

        if self.strategy == "bear_call":
            legs = [Leg.Create(short_leg.Symbol, -qty), Leg.Create(long_leg.Symbol, qty)]
        else:
            legs = [Leg.Create(short_leg.Symbol, -qty), Leg.Create(long_leg.Symbol, qty)]

        ticket = self.ComboMarketOrder(legs, 1, tag=f"POC {self.strategy} credit spread")
        self.open_ticket_ids.add(ticket.OrderId)
        self.last_entry_date = self.Time.date()

    def _select_short_contract(self, contracts, right):
        candidates = [c for c in contracts if c.Right == right and c.Greeks is not None]
        if not candidates:
            return None
        return min(candidates, key=lambda c: abs(abs(c.Greeks.Delta) - self.short_delta_target))

    def _select_long_call(self, contracts, short_leg):
        target = short_leg.Strike + self.spread_width
        calls = [c for c in contracts if c.Right == OptionRight.Call and c.Expiry == short_leg.Expiry and c.Strike > short_leg.Strike]
        return min(calls, key=lambda c: abs(c.Strike - target)) if calls else None

    def _select_long_put(self, contracts, short_leg):
        target = short_leg.Strike - self.spread_width
        puts = [c for c in contracts if c.Right == OptionRight.Put and c.Expiry == short_leg.Expiry and c.Strike < short_leg.Strike]
        return min(puts, key=lambda c: abs(c.Strike - target)) if puts else None
