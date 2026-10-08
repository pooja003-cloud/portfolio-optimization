"""Estimates of expected returns and the covariance matrix, both annualized."""

from __future__ import annotations

import pandas as pd
from sklearn.covariance import LedoitWolf

from .config import PERIODS_PER_YEAR


def mean_returns(rets: pd.DataFrame, periods: int = PERIODS_PER_YEAR) -> pd.Series:
    return rets.mean() * periods


def shrunk_mean_returns(
    rets: pd.DataFrame, intensity: float = 0.5, periods: int = PERIODS_PER_YEAR
) -> pd.Series:
    """Pull each asset's average return toward the average across all assets.

    intensity=0 keeps the historical means; intensity=1 gives every asset the
    same expected return. Halfway is a crude but useful guard against noisy means.
    """
    mu = rets.mean()
    return ((1 - intensity) * mu + intensity * mu.mean()) * periods


def sample_cov(rets: pd.DataFrame, periods: int = PERIODS_PER_YEAR) -> pd.DataFrame:
    return rets.cov() * periods


def ledoit_wolf_cov(rets: pd.DataFrame, periods: int = PERIODS_PER_YEAR) -> pd.DataFrame:
    # scikit-learn shrinks toward a scaled identity matrix and picks the
    # shrinkage amount from the data.
    lw = LedoitWolf().fit(rets.values)
    return pd.DataFrame(lw.covariance_ * periods, index=rets.columns, columns=rets.columns)


def ledoit_wolf_intensity(rets: pd.DataFrame) -> float:
    """0 = plain sample covariance, 1 = fully shrunk."""
    return float(LedoitWolf().fit(rets.values).shrinkage_)


COV_ESTIMATORS = {"sample": sample_cov, "ledoit_wolf": ledoit_wolf_cov}


def estimate(rets: pd.DataFrame, cov_method: str = "sample") -> tuple[pd.Series, pd.DataFrame]:
    return mean_returns(rets), COV_ESTIMATORS[cov_method](rets)
