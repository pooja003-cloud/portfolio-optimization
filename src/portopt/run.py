"""End-to-end pipeline: data -> frontier -> rolling backtest -> metrics -> figures -> commentary.

    python -m portopt.run                 # real data via yfinance
    python -m portopt.run --window 60     # 5-year estimation window
    python -m portopt.run --synthetic     # offline demo on random data (NOT market data)
"""

from __future__ import annotations

import argparse
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

from . import commentary, config as C, data, estimators as E, metrics as M, optimizers as O, plots as P, stats as S
from .backtest import Strategy, run_all


def build_strategies() -> list[Strategy]:
    # max_sharpe takes an `rf` argument, so the backtest passes it the T-bill
    # rate known at each rebalance date.
    ms = O.max_sharpe
    return [
        Strategy("Equal weight", O.equal_weight),
        Strategy("Min variance (sample)", O.min_variance, "sample"),
        Strategy("Min variance (LW)", O.min_variance, "ledoit_wolf"),
        Strategy("Max Sharpe (sample)", ms, "sample"),
        Strategy("Max Sharpe (LW)", ms, "ledoit_wolf"),
        Strategy("Max Sharpe (LW + shrunk mean)", ms, "ledoit_wolf", mean_fn=E.shrunk_mean_returns),
        Strategy("Risk parity (sample)", O.risk_parity, "sample"),
        Strategy("Risk parity (LW)", O.risk_parity, "ledoit_wolf"),
    ]


README_START, README_END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


def update_readme(table_md: str, setup: dict, out: Path, sig_md: str = "", readme: Path = Path("README.md")):
    """Write the latest real-data results table into README.md between the markers."""
    if not readme.exists():
        return
    text = readme.read_text()
    if README_START not in text or README_END not in text:
        return
    setup_md = "\n".join(f"- **{k}:** {v}" for k, v in setup.items())
    figs = "\n\n".join(f"![{n}]({out.as_posix()}/figures/{n}.png)" for n in
                        ["metric_comparison", "drawdowns", "efficient_frontier", "weights_heatmap"])  # growth chart is in the README summary
    sig = ("\n\n**Is the Sharpe gap real?** Paired block bootstrap of each strategy's Sharpe ratio "
           "minus equal weight's (6-month blocks, 10,000 draws):\n\n" + sig_md) if sig_md else ""
    block = f"{README_START}\n{setup_md}\n\n{table_md}{sig}\n\n{figs}\n{README_END}"
    head, rest = text.split(README_START, 1)
    tail = rest.split(README_END, 1)[1]
    readme.write_text(head + block + tail)
    print("  README.md results section updated.")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tickers", nargs="+", default=list(C.UNIVERSE))
    p.add_argument("--start", default=C.START)
    p.add_argument("--end", default=C.END)
    p.add_argument("--window", type=int, default=C.ESTIMATION_WINDOW, help="estimation window in months")
    p.add_argument("--rebalance", type=int, default=C.REBALANCE_EVERY, help="months between rebalances")
    p.add_argument("--cap", type=float, default=C.WEIGHT_CAP, help="max weight per asset")
    p.add_argument("--rf", default=C.RISK_FREE,
                   help='"tbill" (3-month T-bill from FRED, default) or a constant annual rate, e.g. 0')
    p.add_argument("--cost-bps", type=float, default=C.COST_BPS, help="one-way trading cost in bps")
    p.add_argument("--out", default=None, help="output folder (default: results/)")
    p.add_argument("--refresh", action="store_true", help="re-download data even if cached")
    p.add_argument("--synthetic", action="store_true", help="use random data (offline demo / CI)")
    p.add_argument("--no-llm", action="store_true", help="skip the LLM commentary call")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    out = Path(a.out or ("results_synthetic" if a.synthetic else "results"))
    figs = out / "figures"
    figs.mkdir(parents=True, exist_ok=True)

    # 1. Data --------------------------------------------------------------
    if a.synthetic:
        print("Using SYNTHETIC returns (random numbers, not market data).")
        rets = data.synthetic_returns(a.tickers, start=pd.Timestamp(a.start) + pd.offsets.MonthEnd(0))
    else:
        print(f"Loading monthly returns for {len(a.tickers)} tickers, {a.start} to {a.end} ...")
        rets = data.download_returns(a.tickers, a.start, a.end, refresh=a.refresh)
    print(f"  {rets.shape[0]} months x {rets.shape[1]} assets "
          f"({rets.index[0]:%Y-%m} to {rets.index[-1]:%Y-%m})")
    rf = data.resolve_risk_free(a.rf, rets.index, synthetic=a.synthetic, refresh=a.refresh)
    rf_full = M.rf_monthly(rf, rets.index)
    rf_ann_avg = float(rf_full.mean() * C.PERIODS_PER_YEAR)

    # 2. Full-sample estimates and efficient frontier (in sample) ----------
    mu = E.mean_returns(rets)
    cov_s, cov_lw = E.sample_cov(rets), E.ledoit_wolf_cov(rets)
    assets = pd.DataFrame({"return": mu, "volatility": np.sqrt(np.diag(cov_s))}, index=rets.columns)

    frontiers = {
        "sample cov": O.efficient_frontier(mu, cov_s, a.cap),
        "Ledoit-Wolf cov": O.efficient_frontier(mu, cov_lw, a.cap),
    }
    in_sample, points = {}, {}
    for label, fn in [("Equal weight", O.equal_weight), ("Min variance", O.min_variance),
                      ("Max Sharpe", partial(O.max_sharpe, rf=rf_ann_avg)), ("Risk parity", O.risk_parity)]:
        w = fn(mu, cov_s, a.cap)
        in_sample[label] = w
        st = O.portfolio_stats(w, mu, cov_s, rf_ann_avg)
        points[label] = (st["volatility"], st["return"])
    P.plot_frontier(frontiers, assets, points, figs / "efficient_frontier.png", "full sample, in sample")
    pd.DataFrame(in_sample).to_csv(out / "in_sample_weights.csv", float_format="%.4f")

    # 3-4. Rolling out-of-sample backtest ---------------------------------
    print(f"Backtesting: {a.window}-month window, rebalance every {a.rebalance} months, "
          f"cap {a.cap:.0%}, cost {a.cost_bps:g} bps ...")
    results = run_all(rets, build_strategies(), window=a.window,
                      rebalance_every=a.rebalance, cap=a.cap, cost_bps=a.cost_bps, rf=rf)

    if O.FALLBACKS:
        for why, k in O.FALLBACKS.items():
            print(f"  note: {k} rebalance(s) fell back to min-variance ({why})")

    # 5. Compare -----------------------------------------------------------
    summary = M.summarize(results, rf)
    summary.to_csv(out / "metrics.csv", float_format="%.6f")
    table_md = M.format_table(summary).to_markdown()
    (out / "metrics.md").write_text(table_md + "\n")
    print("\n" + table_md + "\n")

    sig = S.significance_table(results, rf=rf)
    sig.to_csv(out / "significance.csv", float_format="%.4f")
    sig_md = S.format_significance(sig).to_markdown(disable_numparse=True)
    (out / "significance.md").write_text(sig_md + "\n")
    print("Sharpe ratio vs equal weight (paired block bootstrap, 6-month blocks, 10,000 draws)\n")
    print(sig_md + "\n")

    pd.concat({n: r.returns for n, r in results.items()}, axis=1).to_csv(out / "oos_returns.csv", float_format="%.6f")
    (out / "weights").mkdir(exist_ok=True)
    for n, r in results.items():
        slug = n.lower().replace(" + ", "_").replace(" ", "_").replace("(", "").replace(")", "")
        r.weights.to_csv(out / "weights" / f"{slug}.csv", float_format="%.4f")

    P.plot_wealth(results, figs / "cumulative_wealth.png")
    P.plot_drawdowns(results, figs / "drawdowns.png")
    P.plot_metric_bars(summary, figs / "metric_comparison.png")
    P.plot_weights(results, figs / "weights_heatmap.png")

    # 6. AI commentary -----------------------------------------------------
    oos = results["Equal weight"].returns.index
    lw_int = np.mean([E.ledoit_wolf_intensity(rets.iloc[t - a.window:t])
                      for t in range(a.window, len(rets), a.rebalance)])
    setup = {
        "Data": ("SYNTHETIC random returns (not market data)" if a.synthetic
                 else f"{len(a.tickers)} ETFs ({', '.join(a.tickers)}), monthly, {rets.index[0]:%Y-%m} to {rets.index[-1]:%Y-%m}"),
        "Out-of-sample period": f"{oos[0]:%Y-%m} to {oos[-1]:%Y-%m} ({len(oos)} months)",
        "Estimation window": f"{a.window} months, rebalanced every {a.rebalance} months",
        "Constraints": f"long-only, max {a.cap:.0%} per asset, fully invested",
        "Risk-free rate in Sharpe": (
            f"3-month US T-bill (FRED TB3MS), varying monthly; averaged "
            f"{M.rf_monthly(rf, oos).mean() * 12:.2%} p.a. out of sample "
            f"(range {M.rf_monthly(rf, oos).min() * 12:.2%} to {M.rf_monthly(rf, oos).max() * 12:.2%})"
            if isinstance(rf, pd.Series) else f"{rf:.2%} p.a. (constant)"),
        "Transaction costs": f"{a.cost_bps:g} bps one-way",
    }
    sig_lines = [f"{n}: Sharpe difference vs equal weight {row.iloc[1]:+.2f}, bootstrap p-value {row['p-value']:.2f}"
                 for n, row in sig.iterrows()]
    notes = sig_lines + [
        f"Average Ledoit-Wolf shrinkage intensity across rebalances: {lw_int:.2f} (0 = sample covariance, 1 = fully shrunk).",
        "'Shrunk mean' moves each asset's historical mean 50% toward the cross-asset average.",
        "Turnover is one-way, averaged per year.",
    ]
    if not a.synthetic and a.out is None:
        update_readme(table_md, setup, out, sig_md)
    path = commentary.write_commentary(commentary.build_prompt(table_md, setup, notes), out, enabled=not a.no_llm)
    print(f"Done. Figures in {figs}/, tables in {out}/, commentary: {path}")
    return summary


if __name__ == "__main__":
    main()
