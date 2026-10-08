"""The four portfolios, plus the efficient frontier.

Every function takes annualized expected returns (`mu`, a Series) and an
annualized covariance matrix (`cov`, a DataFrame), and returns weights that
sum to 1. Weights are never negative (no short selling) and never above `cap`.
"""

from __future__ import annotations

from collections import Counter

import cvxpy as cp
import numpy as np
import pandas as pd
from scipy.optimize import minimize

# Counts how often maximum Sharpe gave up and used minimum variance instead.
# run.py prints this at the end.
FALLBACKS: Counter = Counter()


def _check_cap(n: int, cap: float) -> float:
    cap = 1.0 if cap is None else float(cap)
    if cap * n < 1 - 1e-12:
        raise ValueError(f"A {cap:.0%} cap can't work with {n} assets: weights couldn't add up to 100%.")
    return cap


def _psd(cov: pd.DataFrame):
    # symmetrize to kill floating-point noise, and tell cvxpy it's positive semidefinite
    s = np.asarray(cov, dtype=float)
    return cp.psd_wrap((s + s.T) / 2)


def _clean(w, index) -> pd.Series:
    w = np.clip(np.asarray(w, dtype=float).ravel(), 0, None)
    return pd.Series(w / w.sum(), index=index)


def _solve(prob: cp.Problem) -> bool:
    # Clarabel almost always works; the others are there in case it doesn't.
    for solver in ("CLARABEL", "OSQP", "SCS"):
        try:
            prob.solve(solver=solver)
        except Exception:  # noqa: BLE001
            continue
        if prob.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
            return True
    return False


def equal_weight(mu: pd.Series, cov: pd.DataFrame, cap: float | None = None) -> pd.Series:
    n = len(cov)
    return pd.Series(np.full(n, 1 / n), index=cov.index)


def min_variance(mu: pd.Series, cov: pd.DataFrame, cap: float | None = None) -> pd.Series:
    n = len(cov)
    cap = _check_cap(n, cap)
    w = cp.Variable(n)
    prob = cp.Problem(cp.Minimize(cp.quad_form(w, _psd(cov))),
                      [cp.sum(w) == 1, w >= 0, w <= cap])
    if not _solve(prob):
        raise RuntimeError(f"Minimum variance didn't solve ({prob.status})")
    return _clean(w.value, cov.index)


def max_sharpe(mu: pd.Series, cov: pd.DataFrame, cap: float | None = None, rf: float = 0.0) -> pd.Series:
    """Highest Sharpe ratio portfolio (the "tangency" portfolio).

    Maximizing a ratio isn't convex, so we use the usual trick: write the
    weights as w = y / k for some k > 0 and fix the excess return at 1:

        minimize  y' Σ y   subject to  (mu - rf)' y = 1,  sum(y) = k,  0 <= y <= cap * k

    That's a plain quadratic program, so the solver finds the true optimum,
    and the cap stays linear. If no allowed portfolio is expected to beat the
    risk-free rate, there's nothing to maximize and we return minimum variance.
    """
    n = len(cov)
    cap = _check_cap(n, cap)
    excess = np.asarray(mu, dtype=float) - rf

    if _max_return(excess, cap) <= 1e-10:
        FALLBACKS["no portfolio was expected to beat the risk-free rate"] += 1
        return min_variance(mu, cov, cap)

    y = cp.Variable(n)
    k = cp.Variable(nonneg=True)
    prob = cp.Problem(cp.Minimize(cp.quad_form(y, _psd(cov))),
                      [excess @ y == 1, cp.sum(y) == k, y >= 0, y <= cap * k])
    if not _solve(prob) or k.value is None or k.value <= 1e-12:
        FALLBACKS["the solver failed"] += 1
        return min_variance(mu, cov, cap)
    return _clean(y.value / k.value, cov.index)


def risk_parity(mu: pd.Series, cov: pd.DataFrame, cap: float | None = None, budget=None) -> pd.Series:
    """Portfolio where every asset contributes the same share of total risk.

    Without a cap this has a neat convex form (Spinu, 2013):

        minimize  0.5 y' Σ y - sum(b_i * log(y_i)),  then  w = y / sum(y)

    The log term keeps every weight positive. With 13 assets the cap only
    bites when one asset is far less volatile than the rest; in that case we
    hand the problem to SLSQP and get each asset's risk share as close to
    equal as the cap allows.
    """
    n = len(cov)
    cap = _check_cap(n, cap)
    S = np.asarray(cov, dtype=float)
    S = (S + S.T) / 2
    b = np.full(n, 1 / n) if budget is None else np.asarray(budget, float) / np.sum(budget)

    y = cp.Variable(n, pos=True)
    prob = cp.Problem(cp.Minimize(0.5 * cp.quad_form(y, cp.psd_wrap(S)) - b @ cp.log(y)))
    if _solve(prob):
        w = y.value / y.value.sum()
    else:
        # weighting by 1/volatility is close to risk parity and a fine fallback
        w = 1 / np.sqrt(np.diag(S))
        w /= w.sum()

    if w.max() <= cap + 1e-8:
        return _clean(w, cov.index)

    def gap(x):
        risk_share = x * (S @ x) / (x @ S @ x)
        return np.sum((risk_share - b) ** 2)

    x0 = _cap_project(w, cap)
    res = minimize(gap, x0, method="SLSQP", bounds=[(0.0, cap)] * n,
                   constraints=[{"type": "eq", "fun": lambda x: x.sum() - 1}],
                   options={"ftol": 1e-14, "maxiter": 1000})
    return pd.Series(_cap_project(res.x if res.success else x0, cap), index=cov.index)


def _cap_project(w: np.ndarray, cap: float) -> np.ndarray:
    """Cut anything above the cap and spread the excess over the other assets."""
    w = np.clip(np.asarray(w, float), 0, None)
    w = w / w.sum()
    for _ in range(len(w)):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        free = w < cap - 1e-12
        w[free] += excess * w[free] / w[free].sum()
    return w


STRATEGIES = {
    "equal_weight": equal_weight,
    "min_variance": min_variance,
    "max_sharpe": max_sharpe,
    "risk_parity": risk_parity,
}


def portfolio_stats(w, mu: pd.Series, cov: pd.DataFrame, rf: float = 0.0) -> dict:
    w = np.asarray(w, float)
    ret = float(w @ np.asarray(mu))
    vol = float(np.sqrt(w @ np.asarray(cov) @ w))
    return {"return": ret, "volatility": vol, "sharpe": (ret - rf) / vol if vol > 0 else np.nan}


def risk_contributions(w, cov: pd.DataFrame) -> pd.Series:
    """Each asset's share of the portfolio's variance. Adds up to 1."""
    S = np.asarray(cov)
    wv = np.asarray(w)
    return pd.Series(wv * (S @ wv) / (wv @ S @ wv), index=cov.index)


def _max_return(mu: np.ndarray, cap: float) -> float:
    # Best expected return the constraints allow: fill the best asset up to
    # the cap, then the next best, and so on until fully invested.
    total, left = 0.0, 1.0
    for m in np.sort(mu)[::-1]:
        take = min(cap, left)
        total += take * m
        left -= take
        if left <= 1e-12:
            break
    return total


def efficient_frontier(mu: pd.Series, cov: pd.DataFrame, cap: float | None = None,
                       n_points: int = 40) -> pd.DataFrame:
    """Lowest-volatility portfolio for each of `n_points` target returns."""
    n = len(cov)
    cap = _check_cap(n, cap)
    m = np.asarray(mu, float)
    lo = float(min_variance(mu, cov, cap) @ m)
    hi = _max_return(m, cap)
    S = _psd(cov)

    rows = []
    for target in np.linspace(lo, hi, n_points):
        w = cp.Variable(n)
        prob = cp.Problem(cp.Minimize(cp.quad_form(w, S)),
                          [cp.sum(w) == 1, w >= 0, w <= cap, m @ w >= target - 1e-9])
        if _solve(prob):
            wv = np.clip(w.value, 0, None)
            wv /= wv.sum()
            rows.append({"return": float(wv @ m),
                         "volatility": float(np.sqrt(wv @ np.asarray(cov) @ wv))})
    return pd.DataFrame(rows)
