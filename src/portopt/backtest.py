"""Rolling out-of-sample backtest.

On each rebalance date the strategy only gets to see the `window` months
before that date. It picks weights, we hold them (letting them drift as
prices move) until the next rebalance, and record what they earned. So the
returns that judge a strategy never feed into the weights it chose.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .config import PERIODS_PER_YEAR
from .estimators import COV_ESTIMATORS, mean_returns
from .metrics import rf_monthly


@dataclass
class Strategy:
    name: str
    weight_fn: Callable                  # (mu, cov, cap) -> weights
    cov_method: str = "sample"           # "sample" or "ledoit_wolf"
    mean_fn: Callable = mean_returns     # how expected returns are estimated
    kwargs: dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    name: str
    returns: pd.Series       # monthly returns after costs, test period only
    weights: pd.DataFrame    # target weights chosen at each rebalance
    turnover: pd.Series      # share of the portfolio traded at each rebalance (one-way)


def run_backtest(
    rets: pd.DataFrame,
    strategy: Strategy,
    window: int = 36,
    rebalance_every: int = 3,
    cap: float | None = 0.30,
    cost_bps: float = 0.0,
    rf=0.0,
) -> BacktestResult:
    """`rf` is a fixed annual rate or a monthly Series. If the strategy's weight
    function has an `rf` argument (maximum Sharpe does), it gets the rate that
    was known on each rebalance date."""
    if window >= len(rets):
        raise ValueError(f"The window ({window} months) has to be shorter than the data ({len(rets)} months).")

    R = rets.values
    rf_m = rf_monthly(rf, rets.index).values
    wants_rf = "rf" in inspect.signature(strategy.weight_fn).parameters
    n_obs, n_assets = R.shape
    port_rets = np.full(n_obs, np.nan)
    holdings = np.zeros(n_assets)   # start in cash
    weights, turnover = {}, {}

    for t in range(window, n_obs):
        if (t - window) % rebalance_every == 0:
            history = rets.iloc[t - window : t]    # stops the month before t
            mu = strategy.mean_fn(history)
            cov = COV_ESTIMATORS[strategy.cov_method](history)
            kw = dict(strategy.kwargs)
            if wants_rf:
                kw.setdefault("rf", rf_m[t] * PERIODS_PER_YEAR)
            target = strategy.weight_fn(mu, cov, cap, **kw).values

            date = rets.index[t]
            weights[date] = target
            # The first allocation is buying from cash, so it isn't counted as turnover.
            traded = 0.0 if t == window else 0.5 * np.abs(target - holdings).sum()
            turnover[date] = traded
            holdings = target.copy()
            cost = 2 * traded * cost_bps / 1e4   # pay on the buys and the sells
        else:
            cost = 0.0

        r_p = float(holdings @ R[t])
        port_rets[t] = r_p - cost
        holdings = holdings * (1 + R[t]) / (1 + r_p)   # weights drift with prices

    return BacktestResult(
        name=strategy.name,
        returns=pd.Series(port_rets, index=rets.index, name=strategy.name).iloc[window:],
        weights=pd.DataFrame(weights, index=rets.columns).T,
        turnover=pd.Series(turnover, name=strategy.name),
    )


def run_all(rets: pd.DataFrame, strategies: list[Strategy], **kwargs) -> dict[str, BacktestResult]:
    return {s.name: run_backtest(rets, s, **kwargs) for s in strategies}
