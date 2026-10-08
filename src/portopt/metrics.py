"""Performance statistics for monthly return series."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PERIODS_PER_YEAR


def cagr(r: pd.Series, periods: int = PERIODS_PER_YEAR) -> float:
    years = len(r) / periods
    return float((1 + r).prod() ** (1 / years) - 1)


def ann_vol(r: pd.Series, periods: int = PERIODS_PER_YEAR) -> float:
    return float(r.std(ddof=1) * np.sqrt(periods))


def sharpe(r: pd.Series, rf: float = 0.0, periods: int = PERIODS_PER_YEAR) -> float:
    """Annualized Sharpe ratio of monthly returns, rf given as an annual rate."""
    excess = r - rf / periods
    sd = excess.std(ddof=1)
    return float(excess.mean() / sd * np.sqrt(periods)) if sd > 0 else np.nan


def drawdown(r: pd.Series) -> pd.Series:
    wealth = (1 + r).cumprod()
    return wealth / wealth.cummax() - 1


def max_drawdown(r: pd.Series) -> float:
    return float(drawdown(r).min())


def annual_turnover(turnover: pd.Series, n_months: int, periods: int = PERIODS_PER_YEAR) -> float:
    """Average one-way turnover per year (0.5 = half the portfolio traded each year)."""
    return float(turnover.sum() / (n_months / periods))


def summarize(results: dict, rf: float = 0.0) -> pd.DataFrame:
    rows = {}
    for name, res in results.items():
        r = res.returns
        rows[name] = {
            "Ann. return (CAGR)": cagr(r),
            "Ann. volatility": ann_vol(r),
            "Sharpe ratio": sharpe(r, rf),
            "Max drawdown": max_drawdown(r),
            "Ann. turnover": annual_turnover(res.turnover, len(r)),
            "Avg. max weight": float(res.weights.max(axis=1).mean()),
        }
    return pd.DataFrame(rows).T


def format_table(df: pd.DataFrame) -> pd.DataFrame:
    """Human-readable copy of the summary table."""
    out = df.copy().astype(object)
    pct = ["Ann. return (CAGR)", "Ann. volatility", "Max drawdown", "Ann. turnover", "Avg. max weight"]
    for c in pct:
        out[c] = df[c].map(lambda x: f"{x:.1%}")
    out["Sharpe ratio"] = df["Sharpe ratio"].map(lambda x: f"{x:.2f}")
    return out
