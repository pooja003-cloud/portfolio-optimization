"""Is a Sharpe-ratio gap real or noise?

Paired circular block bootstrap of the Sharpe-ratio difference between each
strategy and a benchmark (equal weight). Months are resampled in blocks so
that volatility clustering and autocorrelation survive, and the *same* blocks
are drawn for both strategies so their correlation is preserved; that pairing
is what makes the test far sharper than comparing two separate intervals.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PERIODS_PER_YEAR


def _sharpe_cols(x: np.ndarray, periods: int) -> np.ndarray:
    """Annualized Sharpe of each column (axis=-2 is time)."""
    return x.mean(axis=-2) / x.std(axis=-2, ddof=1) * np.sqrt(periods)


def block_indices(n: int, block: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """(n_boot, n) array of circular-block-bootstrap row indices."""
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(n_boot, -1)[:, :n]


def sharpe_diff_test(
    r: pd.Series,
    bench: pd.Series,
    rf: float = 0.0,
    block: int = 6,
    n_boot: int = 10_000,
    seed: int = 0,
    periods: int = PERIODS_PER_YEAR,
) -> dict:
    """Bootstrap test of H0: Sharpe(r) == Sharpe(bench).

    Returns the observed difference, a 95% percentile interval and a two-sided
    p-value from the bootstrap distribution re-centred on zero.
    """
    x = pd.concat([r, bench], axis=1).dropna().values - rf / periods
    obs = _sharpe_cols(x, periods)
    d_obs = obs[0] - obs[1]

    rng = np.random.default_rng(seed)
    idx = block_indices(len(x), block, n_boot, rng)
    boot = _sharpe_cols(x[idx], periods)            # (n_boot, 2)
    d = boot[:, 0] - boot[:, 1]

    lo, hi = np.percentile(d, [2.5, 97.5])
    p = float(np.mean(np.abs(d - d_obs) >= abs(d_obs)))
    return {"sharpe": obs[0], "bench_sharpe": obs[1], "diff": d_obs,
            "ci_low": lo, "ci_high": hi, "p_value": p}


def sharpe_se(r: pd.Series, rf: float = 0.0, periods: int = PERIODS_PER_YEAR) -> float:
    """Lo (2002) iid standard error of an annualized Sharpe ratio."""
    ex = r - rf / periods
    sr_m = ex.mean() / ex.std(ddof=1)
    return float(np.sqrt((1 + 0.5 * sr_m**2) / len(ex)) * np.sqrt(periods))


def significance_table(
    results: dict, benchmark: str = "Equal weight", rf: float = 0.0, **kwargs
) -> pd.DataFrame:
    bench = results[benchmark].returns
    rows = {}
    for name, res in results.items():
        if name == benchmark:
            continue
        t = sharpe_diff_test(res.returns, bench, rf=rf, **kwargs)
        rows[name] = {
            "Sharpe": t["sharpe"],
            f"Δ vs {benchmark.lower()}": t["diff"],
            "95% CI low": t["ci_low"],
            "95% CI high": t["ci_high"],
            "p-value": t["p_value"],
        }
    return pd.DataFrame(rows).T


def format_significance(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    delta = [c for c in df.columns if c.startswith("Δ")][0]
    out["Sharpe"] = df["Sharpe"].map(lambda x: f"{x:.2f}")
    out[delta] = df[delta].map(lambda x: f"{x:+.2f}")
    out["95% CI"] = [f"[{a:+.2f}, {b:+.2f}]" for a, b in zip(df["95% CI low"], df["95% CI high"])]
    out["p-value"] = df["p-value"].map(lambda p: f"{p:.2f}")
    out["Significant at 5%?"] = np.where(df["p-value"] < 0.05, "yes", "no")
    return out
