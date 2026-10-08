"""Performance numbers for monthly return series."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PERIODS_PER_YEAR

# Column names for the results table. Other modules import these so the
# labels only live in one place.
RETURN = "Annual return"
VOLATILITY = "Annual volatility"
SHARPE = "Sharpe ratio"
DRAWDOWN = "Maximum drawdown"
TURNOVER = "Annual turnover"
LARGEST_WEIGHT = "Average largest weight"


def cagr(r: pd.Series, periods: int = PERIODS_PER_YEAR) -> float:
    """Compound annual growth rate."""
    years = len(r) / periods
    return float((1 + r).prod() ** (1 / years) - 1)


def ann_vol(r: pd.Series, periods: int = PERIODS_PER_YEAR) -> float:
    return float(r.std(ddof=1) * np.sqrt(periods))


def rf_monthly(rf, index: pd.Index, periods: int = PERIODS_PER_YEAR) -> pd.Series:
    """Line the risk-free rate up with `index`, as a monthly rate.

    `rf` can be a fixed annual rate (a float) or a Series of monthly rates
    from data.download_risk_free().
    """
    if isinstance(rf, pd.Series):
        out = rf.reindex(index)
        if out.isna().any():
            gap = out.index[out.isna()]
            raise ValueError(f"No risk-free rate for {len(gap)} month(s), first one {gap[0]:%Y-%m}.")
        return out
    return pd.Series(float(rf) / periods, index=index)


def sharpe(r: pd.Series, rf=0.0, periods: int = PERIODS_PER_YEAR) -> float:
    """Annualized Sharpe ratio: average return above the risk-free rate, per unit of volatility."""
    excess = r - rf_monthly(rf, r.index, periods)
    sd = excess.std(ddof=1)
    return float(excess.mean() / sd * np.sqrt(periods)) if sd > 0 else np.nan


def drawdown(r: pd.Series) -> pd.Series:
    wealth = (1 + r).cumprod()
    return wealth / wealth.cummax() - 1


def max_drawdown(r: pd.Series) -> float:
    return float(drawdown(r).min())


def annual_turnover(turnover: pd.Series, n_months: int, periods: int = PERIODS_PER_YEAR) -> float:
    # one-way: 0.5 means half the portfolio was replaced over a year
    return float(turnover.sum() / (n_months / periods))


def summarize(results: dict, rf=0.0) -> pd.DataFrame:
    rows = {}
    for name, res in results.items():
        r = res.returns
        rows[name] = {
            RETURN: cagr(r),
            VOLATILITY: ann_vol(r),
            SHARPE: sharpe(r, rf),
            DRAWDOWN: max_drawdown(r),
            TURNOVER: annual_turnover(res.turnover, len(r)),
            LARGEST_WEIGHT: float(res.weights.max(axis=1).mean()),
        }
    return pd.DataFrame(rows).T


def format_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy().astype(object)
    for col in [RETURN, VOLATILITY, DRAWDOWN, TURNOVER, LARGEST_WEIGHT]:
        out[col] = df[col].map(lambda x: f"{x:.1%}")
    out[SHARPE] = df[SHARPE].map(lambda x: f"{x:.2f}")
    return out
