"""Run the whole study: data, efficient frontier, backtest, results, charts, commentary.

    python -m portopt.run                 # real data (downloaded once, then cached)
    python -m portopt.run --window 60     # use 5 years of history instead of 3
    python -m portopt.run --synthetic     # offline demo on made-up data
"""

from __future__ import annotations

import argparse
import re
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd

from . import commentary, config as C, data, estimators as E, metrics as M, optimizers as O, plots as P, stats as S
from .backtest import Strategy, run_all

README_START, README_END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"

# Charts that go in the README's results section. The growth-of-$1 chart is
# left out because it already sits at the top of the README.
README_FIGURES = {
    "metric_comparison": "Sharpe ratio, volatility, drawdown and turnover by strategy",
    "drawdowns": "Drawdowns over the test period",
    "efficient_frontier": "Efficient frontier over the full sample",
    "weights_heatmap": "Weights chosen at each rebalance",
}


def build_strategies() -> list[Strategy]:
    # max_sharpe has an `rf` argument, so the backtest hands it the Treasury
    # bill rate that was known on each rebalance date.
    return [
        Strategy("Equal weight", O.equal_weight),
        Strategy("Minimum variance (sample)", O.min_variance, "sample"),
        Strategy("Minimum variance (Ledoit-Wolf)", O.min_variance, "ledoit_wolf"),
        Strategy("Maximum Sharpe (sample)", O.max_sharpe, "sample"),
        Strategy("Maximum Sharpe (Ledoit-Wolf)", O.max_sharpe, "ledoit_wolf"),
        Strategy("Maximum Sharpe (Ledoit-Wolf, shrunk means)", O.max_sharpe, "ledoit_wolf",
                 mean_fn=E.shrunk_mean_returns),
        Strategy("Risk parity (sample)", O.risk_parity, "sample"),
        Strategy("Risk parity (Ledoit-Wolf)", O.risk_parity, "ledoit_wolf"),
    ]


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def update_readme(table_md: str, setup: dict, out: Path, sig_md: str = "", readme: Path = Path("README.md")):
    """Replace the README's results section with the latest real-data numbers."""
    if not readme.exists():
        return
    text = readme.read_text()
    if README_START not in text or README_END not in text:
        return
    setup_md = "\n".join(f"- **{k}:** {v}" for k, v in setup.items())
    figs = "\n\n".join(f"![{alt}]({out.as_posix()}/figures/{name}.png)" for name, alt in README_FIGURES.items())
    sig = ""
    if sig_md:
        sig = ("\n\n**Are the differences real?** Each strategy's Sharpe ratio compared with equal "
               "weight's, using 10,000 resampled histories built from 6-month blocks:\n\n" + sig_md)
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
    p.add_argument("--window", type=int, default=C.ESTIMATION_WINDOW, help="months of history per rebalance")
    p.add_argument("--rebalance", type=int, default=C.REBALANCE_EVERY, help="months between rebalances")
    p.add_argument("--cap", type=float, default=C.WEIGHT_CAP, help="largest weight allowed per asset")
    p.add_argument("--rf", default=C.RISK_FREE,
                   help='"tbill" for the 3-month Treasury bill rate (default), or a fixed annual rate such as 0')
    p.add_argument("--cost-bps", type=float, default=C.COST_BPS, help="trading cost per trade, in basis points")
    p.add_argument("--out", default=None, help="output folder (default: results/)")
    p.add_argument("--refresh", action="store_true", help="download the data again even if it's cached")
    p.add_argument("--synthetic", action="store_true", help="use made-up data (offline demo and the GitHub test run)")
    p.add_argument("--no-llm", action="store_true", help="don't call the language model for the commentary")
    return p.parse_args(argv)


def main(argv=None):
    a = parse_args(argv)
    out = Path(a.out or ("results_synthetic" if a.synthetic else "results"))
    figs = out / "figures"
    figs.mkdir(parents=True, exist_ok=True)

    # Data
    if a.synthetic:
        print("Using SYNTHETIC returns (random numbers, not market data).")
        rets = data.synthetic_returns(a.tickers, start=pd.Timestamp(a.start) + pd.offsets.MonthEnd(0))
    else:
        print(f"Loading monthly returns for {len(a.tickers)} funds, {a.start} to {a.end}...")
        rets = data.download_returns(a.tickers, a.start, a.end, refresh=a.refresh)
    print(f"  {rets.shape[0]} months x {rets.shape[1]} funds ({rets.index[0]:%Y-%m} to {rets.index[-1]:%Y-%m})")
    rf = data.resolve_risk_free(a.rf, rets.index, synthetic=a.synthetic, refresh=a.refresh)
    rf_avg = float(M.rf_monthly(rf, rets.index).mean() * C.PERIODS_PER_YEAR)

    # Efficient frontier on the full sample. This one is in-sample on purpose:
    # it shows what the optimizers *think* is achievable with perfect hindsight.
    mu = E.mean_returns(rets)
    cov_s, cov_lw = E.sample_cov(rets), E.ledoit_wolf_cov(rets)
    assets = pd.DataFrame({"return": mu, "volatility": np.sqrt(np.diag(cov_s))}, index=rets.columns)
    frontiers = {
        "sample covariance": O.efficient_frontier(mu, cov_s, a.cap),
        "Ledoit-Wolf covariance": O.efficient_frontier(mu, cov_lw, a.cap),
    }
    in_sample, points = {}, {}
    for label, fn in [("Equal weight", O.equal_weight), ("Minimum variance", O.min_variance),
                      ("Maximum Sharpe", partial(O.max_sharpe, rf=rf_avg)), ("Risk parity", O.risk_parity)]:
        w = fn(mu, cov_s, a.cap)
        in_sample[label] = w
        st = O.portfolio_stats(w, mu, cov_s, rf_avg)
        points[label] = (st["volatility"], st["return"])
    P.plot_frontier(frontiers, assets, points, figs / "efficient_frontier.png", "full sample, in hindsight")
    pd.DataFrame(in_sample).to_csv(out / "in_sample_weights.csv", float_format="%.4f")

    # Backtest
    print(f"Backtesting: {a.window}-month window, rebalancing every {a.rebalance} months, "
          f"{a.cap:.0%} cap, {a.cost_bps:g} basis point costs...")
    results = run_all(rets, build_strategies(), window=a.window,
                      rebalance_every=a.rebalance, cap=a.cap, cost_bps=a.cost_bps, rf=rf)
    for why, k in O.FALLBACKS.items():
        print(f"  note: maximum Sharpe used minimum variance at {k} rebalance(s) because {why}")

    # Results
    summary = M.summarize(results, rf)
    summary.to_csv(out / "metrics.csv", float_format="%.6f")
    table_md = M.format_table(summary).to_markdown(disable_numparse=True)
    (out / "metrics.md").write_text(table_md + "\n")
    print("\n" + table_md + "\n")

    sig = S.significance_table(results, rf=rf)
    sig.to_csv(out / "significance.csv", float_format="%.4f")
    sig_md = S.format_significance(sig).to_markdown(disable_numparse=True)
    (out / "significance.md").write_text(sig_md + "\n")
    print("Sharpe ratio against equal weight (10,000 resampled histories, 6-month blocks)\n")
    print(sig_md + "\n")

    pd.concat({n: r.returns for n, r in results.items()}, axis=1).to_csv(
        out / "oos_returns.csv", float_format="%.6f")
    weights_dir = out / "weights"
    weights_dir.mkdir(exist_ok=True)
    for old in weights_dir.glob("*.csv"):   # strategy names can change; don't leave stale files
        old.unlink()
    for n, r in results.items():
        r.weights.to_csv(weights_dir / f"{slug(n)}.csv", float_format="%.4f")

    P.plot_wealth(results, figs / "cumulative_wealth.png")
    P.plot_drawdowns(results, figs / "drawdowns.png")
    P.plot_metric_bars(summary, figs / "metric_comparison.png")
    P.plot_weights(results, figs / "weights_heatmap.png")

    # Commentary
    test = results["Equal weight"].returns.index
    lw_intensity = np.mean([E.ledoit_wolf_intensity(rets.iloc[t - a.window:t])
                            for t in range(a.window, len(rets), a.rebalance)])
    if isinstance(rf, pd.Series):
        rf_test = M.rf_monthly(rf, test) * 12
        rf_text = (f"3-month US Treasury bill (FRED series TB3MS), changing monthly; "
                   f"averaged {rf_test.mean():.2%} a year over the test period "
                   f"(lowest {rf_test.min():.2%}, highest {rf_test.max():.2%})")
    else:
        rf_text = f"fixed at {rf:.2%} a year"
    setup = {
        "Data": ("SYNTHETIC random returns (not market data)" if a.synthetic else
                 f"{len(a.tickers)} exchange-traded funds ({', '.join(a.tickers)}), monthly, "
                 f"{rets.index[0]:%Y-%m} to {rets.index[-1]:%Y-%m}"),
        "Test period (out of sample)": f"{test[0]:%Y-%m} to {test[-1]:%Y-%m} ({len(test)} months)",
        "Estimation window": f"{a.window} months, rebalanced every {a.rebalance} months",
        "Constraints": f"no short selling, at most {a.cap:.0%} in any asset, fully invested",
        "Risk-free rate": rf_text,
        "Trading costs": f"{a.cost_bps:g} basis points per trade",
    }
    notes = [f"{n}: Sharpe ratio {row[S.DIFF]:+.2f} against equal weight, p-value {row['p-value']:.2f}"
             for n, row in sig.iterrows()]
    notes += [
        f"Average Ledoit-Wolf shrinkage intensity across rebalances: {lw_intensity:.2f} "
        "(0 = plain sample covariance, 1 = fully shrunk).",
        "'Shrunk means' moves each asset's historical average return halfway toward the average across all assets.",
        "Turnover is one-way (the share of the portfolio bought each year).",
    ]
    if not a.synthetic and a.out is None:
        update_readme(table_md, setup, out, sig_md)
    path = commentary.write_commentary(commentary.build_prompt(table_md, setup, notes), out, enabled=not a.no_llm)
    print(f"Done. Charts in {figs}/, tables in {out}/, commentary: {path}")
    return summary


if __name__ == "__main__":
    main()
