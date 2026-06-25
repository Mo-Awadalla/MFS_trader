"""Transaction cost model — modular, configurable per asset class and venue.

Components:
  - commissions
  - SEC Section 31 fee (equities, sell-side)
  - FINRA TAF (equities, sell-side, per share)
  - exchange fees (crypto maker/taker)
  - slippage (hybrid: fixed % + variable market impact)
"""

from __future__ import annotations

from dataclasses import dataclass

from config.schema import AssetClass, CostModelConfig


@dataclass
class TradeCost:
    """Cost breakdown for a single round-trip or per-side trade."""

    commission: float = 0.0
    sec_fee: float = 0.0
    finra_taf: float = 0.0
    exchange_fee: float = 0.0
    slippage_fixed: float = 0.0
    slippage_variable: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.commission
            + self.sec_fee
            + self.finra_taf
            + self.exchange_fee
            + self.slippage_fixed
            + self.slippage_variable
        )


class CostModel:
    """Compute transaction costs per trade, per asset class."""

    def __init__(self, config: CostModelConfig):
        self.cfg = config

    def equity_trade_cost(
        self,
        *,
        side: str,  # "buy" or "sell"
        qty: float,
        price: float,
        notional: float | None = None,
        adv: float | None = None,
    ) -> TradeCost:
        """Cost for a single equity trade (one side)."""
        notional = notional if notional is not None else qty * price
        cost = TradeCost()

        # Commission
        cost.commission = notional * self.cfg.commission_pct

        # SEC Section 31 fee — sell side only
        if side == "sell":
            cost.sec_fee = notional * self.cfg.sec_fee_per_dollar_sold
            cost.finra_taf = qty * self.cfg.finra_taf_per_share_sold

        # Slippage: fixed + variable (market impact)
        cost.slippage_fixed = notional * self.cfg.slippage_fixed_pct
        if adv and adv > 0:
            participation = notional / adv
            cost.slippage_variable = notional * self.cfg.slippage_variable_coeff * participation

        return cost

    def crypto_trade_cost(
        self,
        *,
        side: str,
        qty: float,
        price: float,
        notional: float | None = None,
        adv: float | None = None,
        is_maker: bool = False,
    ) -> TradeCost:
        """Cost for a single crypto trade (one side)."""
        notional = notional if notional is not None else qty * price
        cost = TradeCost()

        # Exchange fee (taker by default — conservative)
        fee_pct = self.cfg.crypto_maker_fee_pct if is_maker else self.cfg.crypto_taker_fee_pct
        cost.exchange_fee = notional * fee_pct

        # Slippage
        cost.slippage_fixed = notional * self.cfg.slippage_fixed_pct
        if adv and adv > 0:
            participation = notional / adv
            cost.slippage_variable = notional * self.cfg.slippage_variable_coeff * participation

        return cost

    def trade_cost(
        self,
        asset_class: AssetClass,
        *,
        side: str,
        qty: float,
        price: float,
        notional: float | None = None,
        adv: float | None = None,
        is_maker: bool = False,
    ) -> TradeCost:
        """Dispatch to the right cost function by asset class."""
        if asset_class == AssetClass.EQUITY:
            return self.equity_trade_cost(side=side, qty=qty, price=price, notional=notional, adv=adv)
        elif asset_class == AssetClass.CRYPTO:
            return self.crypto_trade_cost(
                side=side, qty=qty, price=price, notional=notional, adv=adv, is_maker=is_maker
            )
        raise ValueError(f"Unknown asset class: {asset_class}")

    def per_trade_cost_pct(self, asset_class: AssetClass, is_sell: bool = False) -> float:
        """Approximate total cost as a percentage of notional (for quick vectorized backtests)."""
        pct = self.cfg.slippage_fixed_pct
        if asset_class == AssetClass.EQUITY:
            pct += self.cfg.commission_pct
            if is_sell:
                pct += self.cfg.sec_fee_per_dollar_sold
                # TAF is per share, approximate as a small pct
                pct += 0.0001  # rough estimate for typical share price
        elif asset_class == AssetClass.CRYPTO:
            pct += self.cfg.crypto_taker_fee_pct
        return pct

    def round_trip_cost_pct(self, asset_class: AssetClass) -> float:
        """Total cost for a buy + sell round trip, as % of notional."""
        buy_pct = self.per_trade_cost_pct(asset_class, is_sell=False)
        sell_pct = self.per_trade_cost_pct(asset_class, is_sell=True)
        return buy_pct + sell_pct
