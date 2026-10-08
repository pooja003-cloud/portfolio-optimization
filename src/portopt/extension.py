"""Does it still hold? The same study, tested on 2023-2025.

    python -m portopt.extension               # downloads 2020-2025 data the first time
    python -m portopt.extension --synthetic   # offline demo on made-up data

Nothing is re-tuned. The strategies, the 36-month window, the quarterly
rebalancing and the 30% cap are exactly as in the main study. The first
portfolios, chosen at the start of 2023, use 2020-2022 data; everything after
that is new.

Three years is only 36 monthly returns, so the significance tests here have
even less power than in the main study. Read this as a check on whether the
pattern held, not as fresh proof of anything.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from . import config as C, data, metrics as M, plots as P, stats as S
from .backtest import run_all
from .run import build_strategies, slug

TEST_START = "2023-01-01"
TEST_END = "2025-12-31"
README_START, README_END = "<!-- EXTENSION:START -->", "<!-- EXTENSION:END -->"


def compare_periods(main_dir: Path, summary: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame | None:
    """Side-by-side Sharpe ratios and p-values: main study versus 2023-2025."""
    try:
        old = pd.read_csv(main_dir / "metrics.csv", index_col=0)
        old_sig = pd.read_csv(main_dir / "significance.csv", index_col=0)
    except FileNotFoundError:
        return None
    rows = {}
    for name in summary.index:
        def cell(table, p_table):
            if name not in table.index:
                return "n/a"
            sharpe = f"{table.loc[name, M.SHARPE]:.2f}"
            if name in p_table.index:
                sharpe += f" (p = {p_table.loc[name, 'p-value']:.2f})"
            return sharpe
        rows[name] = {
            "Sharpe ratio, 2015-2022": cell(old, old_sig),
            "Sharpe ratio, 2023-2025": cell(summary, sig),
            "Annual return, 2023-2025": f"{summary.loc[name, M.RETURN]:.1%}",
            "Maximum drawdown, 2023-2025": f"{summary.loc[name, M.DRAWDOWN]:.1%}",
            "Annual turnover, 2023-2025": f"{summary.loc[name, M.TURNOVER]:.1%}",
        }
    return pd.DataFrame(rows).T


def combined_test(main_dir: Path, ext_returns: pd.DataFrame, ext_rf, n_boot: int) -> pd.DataFrame | None:
    """Join the main study's test period (2015-2022) to 2023-2025 and test all 11 years at once."""
    try:
        main = pd.read_csv(main_dir / "oos_returns.csv", index_col=0, parse_dates=True)
    except FileNotFoundError:
        return None
    both = pd.concat([main, ext_returns[main.columns]])
    rf = None
    if isinstance(ext_rf, pd.Series):
        old_rf = data.download_risk_free(f"{main.index[0]:%Y-%m-01}", f"{main.index[-1]:%Y-%m-%d}")
        rf = pd.concat([old_rf, ext_rf.reindex(ext_returns.index)]).reindex(both.index)
    rf = 0.0 if rf is None else rf
    bench = both["Equal weight"]
    rows = {}
    for name in both.columns:
        row = {M.SHARPE: f"{M.sharpe(both[name], rf):.2f}",
               M.RETURN: f"{M.cagr(both[name]):.1%}",
               M.DRAWDOWN: f"{M.max_drawdown(both[name]):.1%}"}
        if name != "Equal weight":
            t = S.sharpe_diff_test(both[name], bench, rf=rf, n_boot=n_boot)
            row[S.DIFF] = f"{t['diff']:+.2f}"
            row["95% interval for the difference"] = f"{t['ci_low']:+.2f} to {t['ci_high']:+.2f}"
            row["p-value"] = f"{t['p_value']:.2f}"
        rows[name] = row
    out = pd.DataFrame(rows).T.fillna("")
    out.index.name = f"{both.index[0]:%Y-%m} to {both.index[-1]:%Y-%m} ({len(both)} months)"
    return out


def _update_readme(block_md: str, readme: Path = Path("README.md")):
    if not readme.exists():
        return
    text = readme.read_text()
    if README_START not in text or README_END not in text:
        return
    head, rest = text.split(README_START, 1)
    tail = rest.split(README_END, 1)[1]
    readme.write_text(f"{head}{README_START}\n{block_md}\n{README_END}{tail}")
    print("  README.md 2023-2025 section updated.")


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--synthetic", action="store_true", help="use made-up data (offline demo and tests)")
    p.add_argument("--refresh", action="store_true", help="download the data again even if it's cached")
    p.add_argument("--n-boot", type=int, default=10_000, help="resampled histories per test")
    p.add_argument("--out", default=None)
    a = p.parse_args(argv)

    window = C.ESTIMATION_WINDOW
    history_start = (pd.Timestamp(TEST_START) - pd.DateOffset(months=window)).strftime("%Y-%m-%d")
    tickers = list(C.UNIVERSE)

    if a.synthetic:
        print("Using SYNTHETIC returns (random numbers, not market data).")
        n_months = window + 36
        rets = data.synthetic_returns(tickers, n_months=n_months, start="2020-01-31", seed=11)
        rf = 0.0
        out = Path(a.out or "results_synthetic/extension_2023_2025")
        main_dir = None
    else:
        print(f"Loading monthly returns, {history_start} to {TEST_END}...")
        rets = data.download_returns(tickers, history_start, TEST_END,
                                     cache="data/returns_2020_2025.csv", refresh=a.refresh)
        rf = data.download_risk_free(history_start, TEST_END, cache="data/tbill_2020_2025.csv",
                                     refresh=a.refresh).reindex(rets.index)
        out = Path(a.out or "results/extension_2023_2025")
        main_dir = Path("results")
    print(f"  {rets.shape[0]} months x {rets.shape[1]} funds ({rets.index[0]:%Y-%m} to {rets.index[-1]:%Y-%m})")
    (out / "figures").mkdir(parents=True, exist_ok=True)

    results = run_all(rets, build_strategies(), window=window, rebalance_every=C.REBALANCE_EVERY,
                      cap=C.WEIGHT_CAP, cost_bps=C.COST_BPS, rf=rf)
    test = results["Equal weight"].returns.index
    print(f"  Test period: {test[0]:%Y-%m} to {test[-1]:%Y-%m} ({len(test)} months)")

    summary = M.summarize(results, rf)
    summary.to_csv(out / "metrics.csv", float_format="%.6f")
    table_md = M.format_table(summary).to_markdown(disable_numparse=True)
    (out / "metrics.md").write_text(table_md + "\n")

    sig = S.significance_table(results, rf=rf, n_boot=a.n_boot)
    sig.to_csv(out / "significance.csv", float_format="%.4f")
    sig_md = S.format_significance(sig).to_markdown(disable_numparse=True)
    (out / "significance.md").write_text(sig_md + "\n")

    ext_returns = pd.concat({n: r.returns for n, r in results.items()}, axis=1)
    ext_returns.to_csv(out / "oos_returns.csv", float_format="%.6f")
    (out / "weights").mkdir(exist_ok=True)
    for old in (out / "weights").glob("*.csv"):
        old.unlink()
    for n, r in results.items():
        r.weights.to_csv(out / "weights" / f"{slug(n)}.csv", float_format="%.4f")
    P.plot_wealth(results, out / "figures" / "cumulative_wealth.png")
    P.plot_drawdowns(results, out / "figures" / "drawdowns.png")
    P.plot_weights(results, out / "figures" / "weights_heatmap.png")

    print("\n" + table_md + "\n")
    print(sig_md + "\n")

    comparison = compare_periods(main_dir, summary, sig) if main_dir else None
    if comparison is not None:
        comp_md = comparison.to_markdown(disable_numparse=True)
        (out / "comparison.md").write_text(comp_md + "\n")
        print(comp_md + "\n")
        rf_line = ""
        if isinstance(rf, pd.Series):
            new_avg = float(M.rf_monthly(rf, test).mean() * 12)
            old_avg = float(data.download_risk_free("2015-01-01", "2022-12-31").mean() * 12)
            rf_line = (f"The Treasury bill rate averaged {new_avg:.1%} a year over 2023-2025, against "
                       f"{old_avg:.1%} over 2015-2022, so Sharpe ratios here are measured against a higher bar.")
        combined = combined_test(main_dir, ext_returns, rf, a.n_boot)
        combined_md = ""
        if combined is not None:
            combined_md = combined.to_markdown(disable_numparse=True)
            (out / "combined_2015_2025.md").write_text(combined_md + "\n")
            print(combined_md + "\n")
            combined_md = ("\n\n**Both periods together.** The same comparison over the whole test period, "
                           f"{combined.index.name}:\n\n" + combined_md)
        block = (f"Sharpe ratios for both periods, with the p-value against equal weight in brackets. "
                 f"The 2023-2025 test has {len(test)} months. {rf_line}\n\n{comp_md}{combined_md}\n\n"
                 f"![Growth of $1 over 2023-2025]({out.as_posix()}/figures/cumulative_wealth.png)")
        if a.out is None:
            _update_readme(block)
    print(f"Done. Tables and charts in {out}/")
    return summary, sig


if __name__ == "__main__":
    main()
