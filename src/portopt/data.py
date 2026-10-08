"""Getting the data: monthly fund returns and the Treasury bill rate.

Both are cached under data/ after the first download, so later runs work
offline and always use the same numbers.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
import pandas as pd

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


def download_returns(
    tickers: list[str],
    start: str,
    end: str,
    cache: str | Path | None = "data/returns.csv",
    refresh: bool = False,
) -> pd.DataFrame:
    """Monthly returns from dividend-adjusted month-end prices."""
    cache = Path(cache) if cache else None
    if cache and cache.exists() and not refresh:
        rets = pd.read_csv(cache, index_col=0, parse_dates=True)
        if set(tickers) <= set(rets.columns):
            return rets[tickers]

    import yfinance as yf

    # Start a month early: January 2012's return needs December 2011's price.
    pad_start = (pd.Timestamp(start) - pd.DateOffset(months=1)).strftime("%Y-%m-%d")
    end_excl = (pd.Timestamp(end) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    raw = yf.download(tickers, start=pad_start, end=end_excl, auto_adjust=True, progress=False)
    if raw.empty:
        raise RuntimeError("yfinance returned nothing - check the connection and tickers.")

    prices = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    prices = prices.reindex(columns=tickers)
    missing = [t for t in tickers if prices[t].dropna().empty]
    if missing:
        raise RuntimeError(f"No prices for {missing}")

    rets = prices.resample("ME").last().pct_change().loc[start:end].dropna(how="any")
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        rets.to_csv(cache)
    return rets


def synthetic_returns(
    tickers: list[str], n_months: int = 132, start: str = "2012-01-31", seed: int = 7
) -> pd.DataFrame:
    """Made-up returns for the tests and the offline demo. Not market data."""
    rng = np.random.default_rng(seed)
    n = len(tickers)
    # a stock-like factor, a bond-like factor and some noise for each asset
    stock_beta = rng.uniform(-0.2, 1.2, n)
    bond_beta = rng.uniform(-0.3, 1.0, n)
    stock_factor = rng.normal(0.007, 0.040, n_months)
    bond_factor = rng.normal(0.002, 0.020, n_months)
    noise = rng.normal(0.0, 1.0, (n_months, n)) * rng.uniform(0.01, 0.04, n)
    alpha = rng.normal(0.0, 0.002, n)
    r = alpha + np.outer(stock_factor, stock_beta) + np.outer(bond_factor, bond_beta) + noise
    idx = pd.date_range(start, periods=n_months, freq="ME")
    return pd.DataFrame(r, index=idx, columns=tickers)


def tbill_to_monthly(yields_pct: pd.Series) -> pd.Series:
    """Monthly average Treasury bill yields (annual %) -> monthly risk-free returns.

    Each month gets the *previous* month's average yield divided by 12, i.e. the
    rate you could have locked in at the start of the month. Indexed by month-end
    to line up with the fund returns.
    """
    s = yields_pct.astype(float).dropna().copy()
    s.index = pd.to_datetime(s.index) + pd.offsets.MonthEnd(0)
    s = s.groupby(level=0).mean()
    return (s / 100 / 12).shift(1).dropna().rename("rf")


def _fetch_fred(series: str) -> pd.Series:
    # requests ships its own certificates, which avoids the SSL errors
    # python.org builds of Python often hit on macOS
    import requests

    resp = requests.get(FRED_URL.format(series=series), timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), index_col=0)
    col = series if series in df.columns else df.columns[0]
    return pd.to_numeric(df[col], errors="coerce")


def _fetch_irx(start: str, end: str) -> pd.Series:
    # Backup source: Yahoo's 13-week Treasury bill yield, averaged by month.
    import yfinance as yf

    raw = yf.download("^IRX", start=start, end=end, auto_adjust=False, progress=False)
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    return close.resample("ME").mean()


def download_risk_free(
    start: str,
    end: str,
    series: str = "TB3MS",
    cache: str | Path | None = "data/tbill.csv",
    refresh: bool = False,
) -> pd.Series:
    """Monthly risk-free rate as a decimal per month, indexed by month-end."""
    cache = Path(cache) if cache else None
    if cache and cache.exists() and not refresh:
        return pd.read_csv(cache, index_col=0, parse_dates=True)["rf"]

    try:
        yields = _fetch_fred(series)
        source = f"FRED {series}"
    except Exception as exc:  # noqa: BLE001
        print(f"  Couldn't reach FRED ({type(exc).__name__}), using Yahoo's ^IRX instead.")
        pad = (pd.Timestamp(start) - pd.DateOffset(months=2)).strftime("%Y-%m-%d")
        yields = _fetch_irx(pad, end)
        source = "Yahoo ^IRX"

    rf = tbill_to_monthly(yields).loc[start:end]
    if rf.empty:
        raise RuntimeError("Got no risk-free rate data.")
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        rf.rename_axis("date").to_frame().to_csv(cache)
    print(f"  Risk-free rate: {source}, {rf.index[0]:%Y-%m} to {rf.index[-1]:%Y-%m}")
    return rf


def resolve_risk_free(spec, index: pd.DatetimeIndex, synthetic: bool = False, refresh: bool = False):
    """Turn the --rf option into a monthly Series ("tbill") or a fixed annual rate.

    Synthetic runs never download anything and just use 0%.
    """
    if isinstance(spec, str) and spec.lower() == "tbill":
        if synthetic:
            return 0.0
        rf = download_risk_free(index[0].strftime("%Y-%m-01"), index[-1].strftime("%Y-%m-%d"),
                                refresh=refresh)
        return rf.reindex(index)
    return float(spec)
