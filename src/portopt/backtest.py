"""Rolling out-of-sample backtest.

At each rebalance date t the strategy sees only the `window` months that end
*before* t, picks target weights, and then holds them (letting them drift with
prices) until the next rebalance. Nothing from month t onward is used to
choose the weights that earn month t's return.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .estimators import COV_ESTIMATORS, mean_returns


@dataclass
class Strategy:
    name: str
    weight_fn: Callable                  # f(mu, cov, cap) -> pd.Series
    cov_method: str = "sample"           # key into estimators.COV_ESTIMATORS
    mean_fn: Callable = mean_returns     # f(rets) -> annualized pd.Series
    kwargs: dict = field(default_factory=dict)


@dataclass
class BacktestResult:
    name: str
    returns: pd.Series          # monthly net portfolio returns (out of sample)
    weights: pd.DataFrame       # target weights at each rebalance date
    turnover: pd.Series         # one-way turnover at each rebalance date


def run_backtest(
    rets: pd.DataFrame,
    strategy: Strategy,
    window: int = 36,
    rebalance_every: int = 3,
    cap: float | None = 0.30,
    cost_bps: float = 0.0,
) -> BacktestResult:
    if window >= len(rets):
        raise ValueError(f"Window ({window}) must be shorter than the sample ({len(rets)} months).")

    R = rets.values
    n_obs, n_assets = R.shape
    port_rets = np.full(n_obs, np.nan)
    w_hold = np.zeros(n_assets)          # current (drifted) holdings, starts in cash
    weights, turnover = {}, {}

    for t in range(window, n_obs):
        if (t - window) % rebalance_every == 0:
            hist = rets.iloc[t - window : t]           # strictly before month t
            mu = strategy.mean_fn(hist)
            cov = COV_ESTIMATORS[strategy.cov_method](hist)
            target = strategy.weight_fn(mu, cov, cap, **strategy.kwargs).values

            date = rets.index[t]
            weights[date] = target
            # The very first allocation is a purchase from cash, not a rebalance.
            trade = 0.0 if t == window else 0.5 * np.abs(target - w_hold).sum()
            turnover[date] = trade
            w_hold = target.copy()
            cost = 2 * trade * cost_bps / 1e4      # charge buys and sells (2x one-way)
        else:
            cost = 0.0

        r_p = float(w_hold @ R[t])
        port_rets[t] = r_p - cost
        w_hold = w_hold * (1 + R[t]) / (1 + r_p)  # drift until next rebalance

    idx = rets.index
    return BacktestResult(
        name=strategy.name,
        returns=pd.Series(port_rets, index=idx, name=strategy.name).iloc[window:],
        weights=pd.DataFrame(weights, index=rets.columns).T,
        turnover=pd.Series(turnover, name=strategy.name),
    )


def run_all(rets: pd.DataFrame, strategies: list[Strategy], **kwargs) -> dict[str, BacktestResult]:
    return {s.name: run_backtest(rets, s, **kwargs) for s in strategies}
