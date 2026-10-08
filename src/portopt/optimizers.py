"""Long-only portfolio construction with a per-asset weight cap.

All functions take annualized inputs (mu as a Series, cov as a DataFrame)
and return weights as a Series that sums to 1.
"""

from __future__ import annotations

from collections import Counter

import cvxpy as cp
import numpy as np
import pandas as pd
from scipy.optimize import minimize

# How often max-Sharpe had to fall back to min-variance (reported by run.py).
FALLBACKS: Counter = Counter()


def _check_cap(n: int, cap: float) -> float:
    cap = 1.0 if cap is None else float(cap)
    if cap * n < 1 - 1e-12:
        raise ValueError(f"Weight cap {cap} is infeasible for {n} assets (needs cap >= 1/n).")
    return cap


def _psd(cov: pd.DataFrame) -> np.ndarray:
    s = np.asarray(cov, dtype=float)
    return cp.psd_wrap((s + s.T) / 2)


def _clean(w: np.ndarray, index) -> pd.Series:
    w = np.clip(np.asarray(w, dtype=float).ravel(), 0, None)
    return pd.Series(w / w.sum(), index=index)


def _solve(prob: cp.Problem) -> bool:
    for solver in ("CLARABEL", "OSQP", "SCS"):
        try:
            prob.solve(solver=solver)
        except (cp.SolverError, Exception):  # noqa: BLE001 - fall through to next solver
            continue
        if prob.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
            return True
    return False


# --------------------------------------------------------------------------- #
# Portfolios
# --------------------------------------------------------------------------- #
def equal_weight(mu: pd.Series, cov: pd.DataFrame, cap: float | None = None) -> pd.Series:
    n = len(cov)
    return pd.Series(np.full(n, 1 / n), index=cov.index)


def min_variance(mu: pd.Series, cov: pd.DataFrame, cap: float | None = None) -> pd.Series:
    n = len(cov)
    cap = _check_cap(n, cap)
    w = cp.Variable(n)
    prob = cp.Problem(
        cp.Minimize(cp.quad_form(w, _psd(cov))),
        [cp.sum(w) == 1, w >= 0, w <= cap],
    )
    if not _solve(prob):
        raise RuntimeError(f"Minimum-variance problem failed: {prob.status}")
    return _clean(w.value, cov.index)


def max_sharpe(
    mu: pd.Series, cov: pd.DataFrame, cap: float | None = None, rf: float = 0.0
) -> pd.Series:
    """Tangency portfolio via the standard convex reformulation.

    Substitute y = k * w with k > 0 and normalise excess return to 1:
        min y' S y   s.t.  (mu - rf)' y = 1,  sum(y) = k,  0 <= y <= cap * k
    then w = y / k. If no feasible portfolio has positive expected excess
    return, the Sharpe ratio cannot be made positive and we fall back to
    minimum variance.
    """
    n = len(cov)
    cap = _check_cap(n, cap)
    excess = np.asarray(mu, dtype=float) - rf

    # Best achievable excess return under the constraints (a tiny LP).
    best = _max_return(excess, cap)
    if best <= 1e-10:
        FALLBACKS["max_sharpe: no positive excess return"] += 1
        return min_variance(mu, cov, cap)

    y = cp.Variable(n)
    k = cp.Variable(nonneg=True)
    prob = cp.Problem(
        cp.Minimize(cp.quad_form(y, _psd(cov))),
        [excess @ y == 1, cp.sum(y) == k, y >= 0, y <= cap * k],
    )
    if not _solve(prob) or k.value is None or k.value <= 1e-12:
        FALLBACKS["max_sharpe: solver failed"] += 1
        return min_variance(mu, cov, cap)
    return _clean(y.value / k.value, cov.index)


def risk_parity(
    mu: pd.Series, cov: pd.DataFrame, cap: float | None = None, budget=None
) -> pd.Series:
    """Equal risk contribution (ERC) portfolio.

    Unconstrained ERC is found with Spinu's convex formulation
        min 0.5 y' S y - sum(b_i log y_i),  w = y / sum(y)
    which is long-only by construction. If that solution breaks the weight
    cap, we solve the capped problem directly with SLSQP, minimising the
    squared gap between each asset's risk share and its budget.
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
    else:  # inverse-vol is a sensible starting point
        w = 1 / np.sqrt(np.diag(S))
        w /= w.sum()

    if w.max() <= cap + 1e-8:
        return _clean(w, cov.index)

    def gap(x):
        port_var = x @ S @ x
        rc = x * (S @ x) / port_var
        return np.sum((rc - b) ** 2)

    x0 = _cap_project(w, cap)
    res = minimize(
        gap, x0, method="SLSQP",
        bounds=[(0.0, cap)] * n,
        constraints=[{"type": "eq", "fun": lambda x: x.sum() - 1}],
        options={"ftol": 1e-14, "maxiter": 1000},
    )
    x = res.x if res.success else x0
    return pd.Series(_cap_project(x, cap), index=cov.index)


def _cap_project(w: np.ndarray, cap: float) -> np.ndarray:
    """Rescale non-negative weights to sum to 1 with none above `cap`,
    redistributing any excess pro rata to the uncapped names."""
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


# --------------------------------------------------------------------------- #
# Diagnostics and the efficient frontier
# --------------------------------------------------------------------------- #
def portfolio_stats(w: pd.Series, mu: pd.Series, cov: pd.DataFrame, rf: float = 0.0) -> dict:
    w = np.asarray(w, float)
    ret = float(w @ np.asarray(mu))
    vol = float(np.sqrt(w @ np.asarray(cov) @ w))
    return {"return": ret, "volatility": vol, "sharpe": (ret - rf) / vol if vol > 0 else np.nan}


def risk_contributions(w: pd.Series, cov: pd.DataFrame) -> pd.Series:
    """Fraction of portfolio variance contributed by each asset (sums to 1)."""
    S = np.asarray(cov)
    wv = np.asarray(w)
    return pd.Series(wv * (S @ wv) / (wv @ S @ wv), index=cov.index)


def _max_return(mu: np.ndarray, cap: float) -> float:
    """Highest expected return reachable with long-only weights capped at `cap`.

    Greedy fill: put `cap` in the best asset, then the next, until fully invested.
    """
    total, left = 0.0, 1.0
    for m in np.sort(mu)[::-1]:
        take = min(cap, left)
        total += take * m
        left -= take
        if left <= 1e-12:
            break
    return total


def efficient_frontier(
    mu: pd.Series, cov: pd.DataFrame, cap: float | None = None, n_points: int = 40
) -> pd.DataFrame:
    """Minimum-variance portfolio for a grid of target returns."""
    n = len(cov)
    cap = _check_cap(n, cap)
    m = np.asarray(mu, float)
    w_mv = min_variance(mu, cov, cap)
    lo = float(w_mv @ m)
    hi = _max_return(m, cap)
    S = _psd(cov)

    rows = []
    for target in np.linspace(lo, hi, n_points):
        w = cp.Variable(n)
        prob = cp.Problem(
            cp.Minimize(cp.quad_form(w, S)),
            [cp.sum(w) == 1, w >= 0, w <= cap, m @ w >= target - 1e-9],
        )
        if _solve(prob):
            wv = np.clip(w.value, 0, None)
            wv /= wv.sum()
            rows.append({"return": float(wv @ m), "volatility": float(np.sqrt(wv @ np.asarray(cov) @ wv))})
    return pd.DataFrame(rows)
