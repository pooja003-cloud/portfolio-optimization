"""Is a gap in Sharpe ratios real, or could it be luck?

With only 96 monthly returns, a Sharpe ratio is a noisy number. To see how
much two of them could differ by chance, we resample history: draw random
6-month blocks of the test period (blocks rather than single months, so calm
and turbulent stretches stay together), rebuild a fake 96-month history from
them, and recompute both Sharpe ratios. The *same* blocks are used for the
strategy and for equal weight, because the two move together month to month,
and ignoring that would make every gap look less certain than it is.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PERIODS_PER_YEAR
from .metrics import rf_monthly

DIFF = "Difference from equal weight"


def _sharpe_cols(x: np.ndarray, periods: int) -> np.ndarray:
    # time runs along axis -2, so this works on one sample or a stack of them
    return x.mean(axis=-2) / x.std(axis=-2, ddof=1) * np.sqrt(periods)


def block_indices(n: int, block: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    """Row numbers for `n_boot` resampled histories, built from blocks that wrap around."""
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]) % n
    return idx.reshape(n_boot, -1)[:, :n]


def sharpe_diff_test(
    r: pd.Series,
    bench: pd.Series,
    rf=0.0,
    block: int = 6,
    n_boot: int = 10_000,
    seed: int = 0,
    periods: int = PERIODS_PER_YEAR,
) -> dict:
    """Test whether Sharpe(r) and Sharpe(bench) really differ.

    Gives the observed gap, a 95% interval for it, and a two-sided p-value:
    the share of resampled gaps (shifted so they're centred on zero) that are
    at least as large as the one we actually saw.
    """
    both = pd.concat([r, bench], axis=1).dropna()
    x = both.values - rf_monthly(rf, both.index, periods).values[:, None]
    obs = _sharpe_cols(x, periods)
    d_obs = obs[0] - obs[1]

    idx = block_indices(len(x), block, n_boot, np.random.default_rng(seed))
    boot = _sharpe_cols(x[idx], periods)
    d = boot[:, 0] - boot[:, 1]

    lo, hi = np.percentile(d, [2.5, 97.5])
    p = float(np.mean(np.abs(d - d_obs) >= abs(d_obs)))
    return {"sharpe": obs[0], "bench_sharpe": obs[1], "diff": d_obs,
            "ci_low": lo, "ci_high": hi, "p_value": p}


def sharpe_se(r: pd.Series, rf=0.0, periods: int = PERIODS_PER_YEAR) -> float:
    """Rough standard error of an annualized Sharpe ratio (Lo, 2002)."""
    ex = r - rf_monthly(rf, r.index, periods)
    sr_m = ex.mean() / ex.std(ddof=1)
    return float(np.sqrt((1 + 0.5 * sr_m**2) / len(ex)) * np.sqrt(periods))


def significance_table(results: dict, benchmark: str = "Equal weight", rf=0.0, **kwargs) -> pd.DataFrame:
    bench = results[benchmark].returns
    rows = {}
    for name, res in results.items():
        if name == benchmark:
            continue
        t = sharpe_diff_test(res.returns, bench, rf=rf, **kwargs)
        rows[name] = {
            "Sharpe ratio": t["sharpe"],
            DIFF: t["diff"],
            "95% interval low": t["ci_low"],
            "95% interval high": t["ci_high"],
            "p-value": t["p_value"],
        }
    return pd.DataFrame(rows).T


def format_significance(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["Sharpe ratio"] = df["Sharpe ratio"].map(lambda x: f"{x:.2f}")
    out[DIFF] = df[DIFF].map(lambda x: f"{x:+.2f}")
    out["95% interval for the difference"] = [
        f"{a:+.2f} to {b:+.2f}" for a, b in zip(df["95% interval low"], df["95% interval high"])]
    out["p-value"] = df["p-value"].map(lambda p: f"{p:.2f}")
    out["Real difference? (p < 0.05)"] = np.where(df["p-value"] < 0.05, "yes", "no")
    return out
