"""Expected-return and covariance estimators (annualized)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

from .config import PERIODS_PER_YEAR


def mean_returns(rets: pd.DataFrame, periods: int = PERIODS_PER_YEAR) -> pd.Series:
    """Historical (sample) mean, annualized."""
    return rets.mean() * periods


def shrunk_mean_returns(
    rets: pd.DataFrame, intensity: float = 0.5, periods: int = PERIODS_PER_YEAR
) -> pd.Series:
    """Shrink each asset's sample mean toward the cross-sectional grand mean.

    A simple James-Stein style fix for noisy expected returns.
    intensity = 0 -> sample means, 1 -> every asset gets the grand mean.
    """
    mu = rets.mean()
    return ((1 - intensity) * mu + intensity * mu.mean()) * periods


def sample_cov(rets: pd.DataFrame, periods: int = PERIODS_PER_YEAR) -> pd.DataFrame:
    return rets.cov() * periods


def ledoit_wolf_cov(rets: pd.DataFrame, periods: int = PERIODS_PER_YEAR) -> pd.DataFrame:
    """Ledoit-Wolf shrinkage toward a scaled identity (sklearn implementation)."""
    lw = LedoitWolf().fit(rets.values)
    return pd.DataFrame(lw.covariance_ * periods, index=rets.columns, columns=rets.columns)


def ledoit_wolf_intensity(rets: pd.DataFrame) -> float:
    """Estimated shrinkage weight (0 = sample covariance, 1 = fully shrunk target)."""
    return float(LedoitWolf().fit(rets.values).shrinkage_)


COV_ESTIMATORS = {"sample": sample_cov, "ledoit_wolf": ledoit_wolf_cov}


def estimate(rets: pd.DataFrame, cov_method: str = "sample") -> tuple[pd.Series, pd.DataFrame]:
    return mean_returns(rets), COV_ESTIMATORS[cov_method](rets)
