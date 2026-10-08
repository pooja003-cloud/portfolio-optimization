"""Download and cache monthly total returns."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def download_returns(
    tickers: list[str],
    start: str,
    end: str,
    cache: str | Path | None = "data/returns.csv",
    refresh: bool = False,
) -> pd.DataFrame:
    """Monthly simple returns from dividend-adjusted month-end prices.

    Results are cached to CSV so reruns are fast and reproducible offline.
    """
    cache = Path(cache) if cache else None
    if cache and cache.exists() and not refresh:
        rets = pd.read_csv(cache, index_col=0, parse_dates=True)
        if set(tickers) <= set(rets.columns):
            return rets[tickers]

    import yfinance as yf

    # Pull daily prices from one month before `start` so the first monthly
    # return (Jan 2012) has a prior month-end price to compare against.
    pad_start = (pd.Timestamp(start) - pd.DateOffset(months=1)).strftime("%Y-%m-%d")
    end_excl = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    raw = yf.download(
        tickers, start=pad_start, end=end_excl, auto_adjust=True, progress=False
    )
    if raw.empty:
        raise RuntimeError("yfinance returned no data. Check your connection or tickers.")

    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    prices = prices.reindex(columns=tickers)
    missing = [t for t in tickers if prices[t].dropna().empty]
    if missing:
        raise RuntimeError(f"No price data for: {missing}")

    monthly = prices.resample("ME").last()
    rets = monthly.pct_change().loc[start:end].dropna(how="any")

    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        rets.to_csv(cache)
    return rets


def synthetic_returns(
    tickers: list[str], n_months: int = 132, start: str = "2012-01-31", seed: int = 7
) -> pd.DataFrame:
    """Random monthly returns with a plausible multi-asset structure.

    Used only for tests and offline demos. These are NOT market data.
    """
    rng = np.random.default_rng(seed)
    n = len(tickers)
    # Two factors (equity-like, rates-like) plus idiosyncratic noise.
    eq_beta = rng.uniform(-0.2, 1.2, n)
    rt_beta = rng.uniform(-0.3, 1.0, n)
    f_eq = rng.normal(0.007, 0.040, n_months)
    f_rt = rng.normal(0.002, 0.020, n_months)
    idio = rng.normal(0.0, 1.0, (n_months, n)) * rng.uniform(0.01, 0.04, n)
    alpha = rng.normal(0.0, 0.002, n)
    r = alpha + np.outer(f_eq, eq_beta) + np.outer(f_rt, rt_beta) + idio
    idx = pd.date_range(start, periods=n_months, freq="ME")
    return pd.DataFrame(r, index=idx, columns=tickers)
