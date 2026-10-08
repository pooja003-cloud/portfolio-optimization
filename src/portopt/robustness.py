"""Rerun the backtest under different settings to see whether the conclusions hold.

    python -m portopt.robustness              # uses the cached real data
    python -m portopt.robustness --synthetic  # offline demo on made-up data

Each setting reports every strategy's Sharpe ratio and its p-value against
equal weight. Only compare numbers within a column: a 60-month window
starts testing in 2017 instead of 2015.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import config as C, data, metrics as M, stats as S
from .backtest import run_all
from .run import build_strategies

# label, estimation window (months), weight cap, trading cost (basis points),
# risk-free rate (None = Treasury bill rate)
SCENARIOS = [
    ("36-month window (main setup)",     36, 0.30, 0,  None),
    ("Risk-free rate set to 0%",         36, 0.30, 0,  0.0),
    ("Trading costs of 0.1% per trade",  36, 0.30, 10, None),
    ("Weight cap of 20%",                36, 0.20, 0,  None),
    ("60-month window",                  60, 0.30, 0,  None),
    ("60-month window, 0.1% costs",      60, 0.30, 10, None),
]

README_START, README_END = "<!-- ROBUSTNESS:START -->", "<!-- ROBUSTNESS:END -->"


def run_scenarios(rets: pd.DataFrame, rf=0.0, n_boot: int = 5_000):
    sharpe, pvals, turnover = {}, {}, {}
    for label, window, cap, cost, rf_override in SCENARIOS:
        r = rf if rf_override is None else rf_override
        res = run_all(rets, build_strategies(), window=window,
                      rebalance_every=C.REBALANCE_EVERY, cap=cap, cost_bps=cost, rf=r)
        summ = M.summarize(res, r)
        sig = S.significance_table(res, rf=r, n_boot=n_boot)
        test = res["Equal weight"].returns.index
        col = f"{label}<br>tested {test[0]:%Y}–{test[-1]:%Y}"
        sharpe[col] = summ[M.SHARPE]
        pvals[col] = sig["p-value"]
        turnover[col] = summ[M.TURNOVER]
    return pd.DataFrame(sharpe), pd.DataFrame(pvals), pd.DataFrame(turnover)


def format_grid(sharpe: pd.DataFrame, pvals: pd.DataFrame) -> pd.DataFrame:
    out = sharpe.map(lambda x: f"{x:.2f}").astype(object)
    for c in sharpe.columns:
        for i in sharpe.index:
            p = pvals.loc[i, c] if i in pvals.index else None
            if p is not None and pd.notna(p):
                out.loc[i, c] = f"{sharpe.loc[i, c]:.2f} (p = {p:.2f})"
    return out


def _update_readme(md: str, readme: Path = Path("README.md")):
    if not readme.exists():
        return
    text = readme.read_text()
    if README_START not in text or README_END not in text:
        return
    head, rest = text.split(README_START, 1)
    tail = rest.split(README_END, 1)[1]
    note = ("Each cell is a Sharpe ratio, with the p-value against equal weight in brackets. "
            "All columns use the Treasury bill rate except the one that sets it to 0%.")
    readme.write_text(f"{head}{README_START}\n{note}\n\n{md}\n{README_END}{tail}")
    print("  README.md robustness section updated.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--rf", default=C.RISK_FREE, help='"tbill" (default) or a fixed annual rate')
    p.add_argument("--n-boot", type=int, default=5_000, help="resampled histories per test")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)

    tickers = list(C.UNIVERSE)
    if a.synthetic:
        rets = data.synthetic_returns(tickers)
        out = Path(a.out or "results_synthetic")
    else:
        rets = data.download_returns(tickers, C.START, C.END)
        out = Path(a.out or "results")
    out.mkdir(parents=True, exist_ok=True)
    rf = data.resolve_risk_free(a.rf, rets.index, synthetic=a.synthetic)

    print(f"Running {len(SCENARIOS)} settings...")
    sharpe, pvals, turnover = run_scenarios(rets, rf, a.n_boot)
    sharpe.to_csv(out / "robustness_sharpe.csv", float_format="%.4f")
    pvals.to_csv(out / "robustness_pvalues.csv", float_format="%.4f")
    turnover.to_csv(out / "robustness_turnover.csv", float_format="%.4f")

    md = format_grid(sharpe, pvals).to_markdown(disable_numparse=True)
    (out / "robustness.md").write_text(md + "\n")
    print("\nSharpe ratio (p-value against equal weight)\n")
    print(md.replace("<br>", " "))
    if not a.synthetic and a.out is None:
        _update_readme(md)
    return sharpe, pvals


if __name__ == "__main__":
    main()
