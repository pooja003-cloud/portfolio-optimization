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


# --------------------------------------------------------------------------- #
# Risk-free rate
# --------------------------------------------------------------------------- #
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


def tbill_to_monthly(yields_pct: pd.Series) -> pd.Series:
    """Turn a monthly-average T-bill yield (annual %, one row per month) into the
    monthly risk-free return earned in each *following* month.

    The rate for, say, March is February's average yield / 12: the rate an
    investor could lock in at the start of March. It is indexed by month-end
    so it lines up with the return series.
    """
    s = yields_pct.astype(float).dropna().copy()
    s.index = pd.to_datetime(s.index) + pd.offsets.MonthEnd(0)
    s = s.groupby(level=0).mean()                 # one value per month
    return (s / 100 / 12).shift(1).dropna().rename("rf")


def _fetch_fred(series: str) -> pd.Series:
    import io

    import requests  # installed with yfinance; uses certifi, so no macOS SSL issues

    resp = requests.get(FRED_URL.format(series=series), timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), index_col=0)
    col = series if series in df.columns else df.columns[0]
    return pd.to_numeric(df[col], errors="coerce")


def _fetch_irx(start: str, end: str) -> pd.Series:
    """Fallback: Yahoo's ^IRX (13-week T-bill yield, annual %), averaged by month."""
    import yfinance as yf

    raw = yf.download("^IRX", start=start, end=end, auto_adjust=False, progress=False)
    close = raw["Close"]
    close = close.iloc[:, 0] if isinstance(close, pd.DataFrame) else close
    return close.resample("ME").mean()


def download_risk_free(
    start: str,
    end: str,
    series: str = "TB3MS",
    cache: str | Path | None = "data/tbill.csv",
    refresh: bool = False,
) -> pd.Series:
    """Monthly risk-free rate (decimal per month), indexed by month-end.

    Source: FRED 3-month T-bill (TB3MS). If FRED is unreachable, falls back to
    Yahoo's ^IRX. Cached to CSV like the returns.
    """
    cache = Path(cache) if cache else None
    if cache and cache.exists() and not refresh:
        return pd.read_csv(cache, index_col=0, parse_dates=True)["rf"]

    pad = (pd.Timestamp(start) - pd.DateOffset(months=2)).strftime("%Y-%m-%d")
    try:
        y = _fetch_fred(series)
        source = f"FRED {series}"
    except Exception as exc:  # noqa: BLE001
        print(f"  FRED unavailable ({type(exc).__name__}); using Yahoo ^IRX instead.")
        y = _fetch_irx(pad, end)
        source = "Yahoo ^IRX"

    rf = tbill_to_monthly(y).loc[start:end]
    if rf.empty:
        raise RuntimeError("No risk-free data returned.")
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        rf.rename_axis("date").to_frame().to_csv(cache)
    print(f"  Risk-free rate: {source}, {rf.index[0]:%Y-%m} to {rf.index[-1]:%Y-%m}")
    return rf


def resolve_risk_free(spec, index: pd.DatetimeIndex, synthetic: bool = False, refresh: bool = False):
    """Turn the --rf option into what the rest of the code expects.

    "tbill" -> Series of monthly rates aligned to `index`; a number -> float
    annual rate. Synthetic runs never download and use 0%.
    """
    if isinstance(spec, str) and spec.lower() == "tbill":
        if synthetic:
            return 0.0
        start = index[0].strftime("%Y-%m-01")
        end = index[-1].strftime("%Y-%m-%d")
        rf = download_risk_free(start, end, refresh=refresh)
        return rf.reindex(index)
    return float(spec)
