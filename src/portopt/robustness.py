"""Re-run the backtest across settings and check whether the conclusions move.

    python -m portopt.robustness              # uses cached data/returns.csv
    python -m portopt.robustness --synthetic  # offline demo

Each scenario gets its own Sharpe ratio and bootstrap p-value against equal
weight. Compare strategies *within* a column: windows of different length
start the out-of-sample period at different dates.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import config as C, data, metrics as M, stats as S
from .backtest import run_all
from .run import build_strategies

SCENARIOS = [
    # label,                 window, cap,  cost_bps, risk-free (None = T-bill)
    ("36m window (base)",        36, 0.30, 0,  None),
    ("36m, rf = 0%",             36, 0.30, 0,  0.0),
    ("36m + 10 bps costs",       36, 0.30, 10, None),
    ("36m, 20% cap",             36, 0.20, 0,  None),
    ("60m window",               60, 0.30, 0,  None),
    ("60m + 10 bps costs",       60, 0.30, 10, None),
]


def run_scenarios(rets: pd.DataFrame, rf=0.0, n_boot: int = 5_000):
    sharpe, pvals, turnover = {}, {}, {}
    for label, window, cap, cost, rf_override in SCENARIOS:
        r = rf if rf_override is None else rf_override
        res = run_all(rets, build_strategies(), window=window,
                      rebalance_every=C.REBALANCE_EVERY, cap=cap, cost_bps=cost, rf=r)
        summ = M.summarize(res, r)
        sig = S.significance_table(res, rf=r, n_boot=n_boot)
        oos = res["Equal weight"].returns.index
        col = f"{label}<br>{oos[0]:%Y}–{oos[-1]:%Y}"
        sharpe[col] = summ["Sharpe ratio"]
        pvals[col] = sig["p-value"]
        turnover[col] = summ["Ann. turnover"]
    return pd.DataFrame(sharpe), pd.DataFrame(pvals), pd.DataFrame(turnover)


def format_grid(sharpe: pd.DataFrame, pvals: pd.DataFrame) -> pd.DataFrame:
    """Sharpe ratio with the bootstrap p-value vs equal weight in brackets."""
    out = sharpe.map(lambda x: f"{x:.2f}").astype(object)
    for c in sharpe.columns:
        for i in sharpe.index:
            p = pvals.loc[i, c] if i in pvals.index else None
            if p is not None and pd.notna(p):
                out.loc[i, c] = f"{sharpe.loc[i, c]:.2f} (p={p:.2f})"
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--rf", default=C.RISK_FREE, help='"tbill" (default) or a constant annual rate')
    p.add_argument("--n-boot", type=int, default=5_000)
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

    print(f"Running {len(SCENARIOS)} scenarios ...")
    sharpe, pvals, turnover = run_scenarios(rets, rf, a.n_boot)
    sharpe.to_csv(out / "robustness_sharpe.csv", float_format="%.4f")
    pvals.to_csv(out / "robustness_pvalues.csv", float_format="%.4f")
    turnover.to_csv(out / "robustness_turnover.csv", float_format="%.4f")

    md = format_grid(sharpe, pvals).to_markdown(disable_numparse=True)
    (out / "robustness.md").write_text(md + "\n")
    print("\nSharpe ratio (bootstrap p-value vs equal weight)\n")
    print(md.replace("<br>", " "))
    if not a.synthetic and a.out is None:
        _update_readme(md)
    return sharpe, pvals


START, END = "<!-- ROBUSTNESS:START -->", "<!-- ROBUSTNESS:END -->"


def _update_readme(md: str, readme: Path = Path("README.md")):
    if not readme.exists():
        return
    text = readme.read_text()
    if START not in text or END not in text:
        return
    head, rest = text.split(START, 1)
    tail = rest.split(END, 1)[1]
    note = ("Sharpe ratio, with the bootstrap p-value against equal weight in brackets. "
            "Sharpe ratios use the 3-month T-bill rate unless the column says rf = 0%. "
            "Compare within a column: the 60-month runs start out of sample in 2017.")
    readme.write_text(f"{head}{START}\n{note}\n\n{md}\n{END}{tail}")
    print("  README.md robustness section updated.")


if __name__ == "__main__":
    main()
