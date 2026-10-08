# Portfolio optimization: which allocation survives out of sample?

A Python rebuild of a MATLAB mean-variance project. It estimates the efficient frontier for a 13-ETF multi-asset universe, builds four classic portfolios under realistic constraints, and runs a rolling quarterly backtest to see which allocation actually holds up on data it has not seen. An LLM writes a short commentary on the results at the end.

**The question:** mean-variance optimization looks best on paper. Does it still look best when the inputs have to be estimated from the past?

## What it does

1. **Data.** Monthly total returns (dividend-adjusted) for 13 ETFs, Jan 2012 to Dec 2022, downloaded with `yfinance` and cached to `data/returns.csv`.
2. **Estimation.** Sample mean and covariance, plus Ledoit-Wolf covariance shrinkage and a shrunk-mean variant.
3. **Portfolios.** Equal weight, minimum variance, maximum Sharpe and risk parity (equal risk contribution). All are long-only, fully invested, with a 30% cap per asset.
4. **Rolling backtest.** At each quarter, estimate on the previous 36 months only, rebalance, then let weights drift with prices until the next rebalance. Out of sample runs Jan 2015 to Dec 2022.
5. **Comparison.** CAGR, volatility, Sharpe ratio, max drawdown, turnover, plus a paired block-bootstrap test of whether each strategy's Sharpe ratio really differs from equal weight's.
6. **AI commentary.** The results table goes to Claude via the Anthropic API, with instructions to use only the numbers provided.

## Universe

| Ticker | Exposure | Ticker | Exposure |
|---|---|---|---|
| SPY | US large cap | TLT | Treasuries 20y+ |
| QQQ | Nasdaq-100 | IEF | Treasuries 7-10y |
| IWM | US small cap | TIP | TIPS |
| EFA | Developed ex-US | LQD | IG corporates |
| EEM | Emerging markets | HYG | High yield |
| VNQ | US REITs | GLD | Gold |
| | | DBC | Commodities |

All 13 traded well before 2012, so there is no survivorship or late-listing gap.

## Results

Run `python -m portopt.run` and this section fills itself in with the real-data table and charts.

<!-- RESULTS:START -->
- **Data:** 13 ETFs (SPY, QQQ, IWM, EFA, EEM, VNQ, TLT, IEF, TIP, LQD, HYG, GLD, DBC), monthly, 2012-01 to 2022-12
- **Out-of-sample period:** 2015-01 to 2022-12 (96 months)
- **Estimation window:** 36 months, rebalanced every 3 months
- **Constraints:** long-only, max 30% per asset, fully invested
- **Risk-free rate in Sharpe:** 0.00% p.a.
- **Transaction costs:** 0 bps one-way

|                               | Ann. return (CAGR)   | Ann. volatility   |   Sharpe ratio | Max drawdown   | Ann. turnover   | Avg. max weight   |
|:------------------------------|:---------------------|:------------------|---------------:|:---------------|:----------------|:------------------|
| Equal weight                  | 4.9%                 | 9.5%              |           0.55 | -20.0%         | 8.3%            | 7.7%              |
| Min variance (sample)         | 1.8%                 | 5.3%              |           0.36 | -14.8%         | 29.0%           | 30.0%             |
| Min variance (LW)             | 2.2%                 | 5.4%              |           0.42 | -14.1%         | 22.2%           | 29.0%             |
| Max Sharpe (sample)           | 4.9%                 | 8.1%              |           0.63 | -16.9%         | 78.4%           | 30.0%             |
| Max Sharpe (LW)               | 4.7%                 | 9.1%              |           0.55 | -19.5%         | 64.0%           | 28.7%             |
| Max Sharpe (LW + shrunk mean) | 3.7%                 | 7.1%              |           0.55 | -15.8%         | 54.4%           | 27.5%             |
| Risk parity (sample)          | 2.9%                 | 7.1%              |           0.44 | -18.2%         | 13.2%           | 20.9%             |
| Risk parity (LW)              | 3.2%                 | 7.5%              |           0.46 | -18.8%         | 11.4%           | 16.7%             |

**Is the Sharpe gap real?** Paired block bootstrap of each strategy's Sharpe ratio minus equal weight's (6-month blocks, 10,000 draws):

|                               | Sharpe   | Δ vs equal weight   | 95% CI         | p-value   | Significant at 5%?   |
|:------------------------------|:---------|:--------------------|:---------------|:----------|:---------------------|
| Min variance (sample)         | 0.36     | -0.19               | [-0.56, +0.23] | 0.33      | no                   |
| Min variance (LW)             | 0.42     | -0.13               | [-0.48, +0.25] | 0.46      | no                   |
| Max Sharpe (sample)           | 0.63     | +0.08               | [-0.39, +0.54] | 0.73      | no                   |
| Max Sharpe (LW)               | 0.55     | -0.00               | [-0.48, +0.46] | 0.99      | no                   |
| Max Sharpe (LW + shrunk mean) | 0.55     | +0.00               | [-0.43, +0.39] | 1.00      | no                   |
| Risk parity (sample)          | 0.44     | -0.11               | [-0.37, +0.15] | 0.40      | no                   |
| Risk parity (LW)              | 0.46     | -0.09               | [-0.32, +0.14] | 0.41      | no                   |

![cumulative_wealth](results/figures/cumulative_wealth.png)

![metric_comparison](results/figures/metric_comparison.png)

![drawdowns](results/figures/drawdowns.png)

![efficient_frontier](results/figures/efficient_frontier.png)

![weights_heatmap](results/figures/weights_heatmap.png)
<!-- RESULTS:END -->

The AI commentary is written to `results/commentary.md`.

### Robustness

`python -m portopt.robustness` re-runs everything with trading costs, a tighter cap and a 5-year window.

<!-- ROBUSTNESS:START -->
Sharpe ratio, with the bootstrap p-value against equal weight in brackets. Compare within a column: the 60-month runs start out of sample in 2017.

|                               | 36m window (base)<br>2015–2022   | 36m + 10 bps costs<br>2015–2022   | 36m, 20% cap<br>2015–2022   | 60m window<br>2017–2022   | 60m + 10 bps costs<br>2017–2022   |
|:------------------------------|:---------------------------------|:----------------------------------|:----------------------------|:--------------------------|:----------------------------------|
| Equal weight                  | 0.55                             | 0.55                              | 0.55                        | 0.60                      | 0.60                              |
| Min variance (sample)         | 0.36 (p=0.32)                    | 0.35 (p=0.30)                     | 0.42 (p=0.43)               | 0.41 (p=0.41)             | 0.41 (p=0.40)                     |
| Min variance (LW)             | 0.42 (p=0.45)                    | 0.41 (p=0.43)                     | 0.43 (p=0.46)               | 0.47 (p=0.53)             | 0.46 (p=0.52)                     |
| Max Sharpe (sample)           | 0.63 (p=0.73)                    | 0.61 (p=0.79)                     | 0.61 (p=0.80)               | 0.77 (p=0.51)             | 0.75 (p=0.54)                     |
| Max Sharpe (LW)               | 0.55 (p=1.00)                    | 0.54 (p=0.95)                     | 0.56 (p=0.96)               | 0.74 (p=0.58)             | 0.73 (p=0.61)                     |
| Max Sharpe (LW + shrunk mean) | 0.55 (p=1.00)                    | 0.54 (p=0.95)                     | 0.54 (p=0.94)               | 0.74 (p=0.57)             | 0.73 (p=0.60)                     |
| Risk parity (sample)          | 0.44 (p=0.40)                    | 0.44 (p=0.39)                     | 0.45 (p=0.43)               | 0.52 (p=0.52)             | 0.52 (p=0.51)                     |
| Risk parity (LW)              | 0.46 (p=0.41)                    | 0.46 (p=0.40)                     | 0.46 (p=0.42)               | 0.53 (p=0.55)             | 0.53 (p=0.54)                     |
<!-- ROBUSTNESS:END -->

## Quick start

```bash
git clone https://github.com/pooja003-cloud/portfolio-optimization.git
cd portfolio-optimization
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,llm]"

python -m portopt.run                    # downloads data, runs everything, updates this README
python -m portopt.robustness             # costs / cap / window scenarios, updates this README
python -m pytest                         # 22 tests

export ANTHROPIC_API_KEY=sk-ant-...      # optional: enables the AI commentary
python -m portopt.run
```

Useful options:

```bash
python -m portopt.run --window 60        # 5-year estimation window (OOS starts 2017)
python -m portopt.run --cap 0.25         # tighter weight cap
python -m portopt.run --cost-bps 10      # 10 bps one-way trading cost
python -m portopt.run --rf 0.015         # risk-free rate used in Sharpe ratios
python -m portopt.run --synthetic        # offline demo on random data (not market data)
```

Without an API key, the prompt is saved to `results/commentary_prompt.md` so you can paste it into any chat assistant.

## Method

**Max Sharpe** is solved as a convex problem rather than with a nonlinear solver. Substituting $y = \kappa w$ and normalizing the excess return to 1 gives

$$\min_{y,\kappa}\ y^\top \Sigma y \quad \text{s.t.}\quad (\mu - r_f)^\top y = 1,\ \ \mathbf{1}^\top y = \kappa,\ \ 0 \le y \le c\,\kappa$$

with $w = y/\kappa$. This finds the global optimum and keeps the cap $c$ linear. If no feasible portfolio has positive expected excess return, it falls back to minimum variance and the run reports how often that happened.

**Risk parity** uses Spinu's convex formulation $\min_y \tfrac12 y^\top\Sigma y - \sum_i b_i \log y_i$, then normalizes. When that solution breaks the cap, an SLSQP step finds the capped portfolio whose risk contributions are closest to equal.

**Ledoit-Wolf** shrinks the sample covariance toward a scaled identity with a data-driven intensity (`sklearn.covariance.LedoitWolf`). With 36 months and 13 assets the sample covariance is noisy, and the optimizer amplifies that noise.

**Shrunk mean** moves each asset's historical mean 50% toward the cross-asset average. It is a deliberately simple fix aimed at the expected-return problem that Ledoit-Wolf does not touch.

**Significance test.** Sharpe ratios estimated from 8 years of monthly data have a standard error of roughly ±0.35, so small gaps are easy to over-read. For each strategy, `stats.py` resamples the out-of-sample months in 6-month blocks (keeping volatility clustering) and draws the *same* blocks for the strategy and for equal weight (keeping their correlation). It reports the Sharpe difference, a 95% bootstrap interval and a two-sided p-value from the re-centred bootstrap distribution.

**Backtest rules**
- Weights chosen at month *t* use only months *t-36* to *t-1*. A test scrambles the future and checks that earlier weights do not change.
- Between rebalances, holdings drift with prices (buy and hold), so turnover reflects real trades back to target.
- Turnover is one-way: ½ Σ|w_target − w_drifted|, averaged per year. The initial purchase from cash is not counted.
- Costs, when set, are charged on both buys and sells.

## Repository layout

```
src/portopt/
  config.py        universe, dates, window, cap
  data.py          yfinance download + cache, synthetic data for tests
  estimators.py    sample / Ledoit-Wolf covariance, sample / shrunk means
  optimizers.py    EW, min variance, max Sharpe, risk parity, efficient frontier
  backtest.py      rolling out-of-sample engine with drift and turnover
  metrics.py       CAGR, volatility, Sharpe, max drawdown, turnover
  stats.py         paired block-bootstrap test of Sharpe differences
  robustness.py    scenario grid: costs, weight cap, estimation window
  plots.py         figures
  commentary.py    LLM commentary via the Anthropic API
  run.py           end-to-end CLI
tests/             22 tests incl. look-ahead, risk parity, costs, bootstrap
results/           metrics.csv/.md, OOS returns, weights, figures, commentary
```

## From MATLAB to Python

| MATLAB (Financial Toolbox) | Here |
|---|---|
| `Portfolio`, `setDefaultConstraints` | long-only + budget constraints in `cvxpy` |
| `setBounds(p, 0, 0.3)` | `cap=0.30` |
| `estimateFrontier`, `plotFrontier` | `efficient_frontier()`, `plot_frontier()` |
| `estimateMaxSharpeRatio` | `max_sharpe()` (convex reformulation) |
| `estimateFrontierLimits(p,'min')` | `min_variance()` |
| `estimateAssetMoments` | `estimators.estimate()` |
| `robustcov` / `shrinkcovariance` | `ledoit_wolf_cov()` |
| `quadprog` / `fmincon` | `cvxpy` (Clarabel/OSQP), `scipy.optimize` |

## Key findings

- **No optimizer beat equal weight by a margin you could tell apart from luck.** Every bootstrap p-value against equal weight is above 0.3, in every scenario. Max Sharpe (sample) had the highest point estimate (0.63 vs 0.55), but its 95% interval for the gap runs from about −0.4 to +0.5.
- **Max Sharpe paid for its edge in trading.** It turned over about 78% of the portfolio a year against 8% for equal weight (about nine times as much), for the same 4.9% return. Costs of 10 bps barely change that here, but its weights jump from quarter to quarter (see the weight heatmap): the classic sign of an optimizer chasing noisy expected returns.
- **Ledoit-Wolf helped exactly where theory says.** It raised the Sharpe ratio of min variance (0.36 → 0.42) and risk parity, and cut turnover for every optimizer, because those portfolios lean only on the covariance matrix. It did not help max Sharpe, whose weakness is the expected returns, not the covariance.
- **Shrinking the expected returns is what calmed max Sharpe.** Moving each mean halfway to the cross-asset average cut its volatility, drawdown and turnover while keeping a similar Sharpe ratio.
- **Min variance was not a safe haven in 2022.** Going into 2022 it held about 95% in bonds and credit (IEF, TIP, HYG, TLT), the assets that had been least volatile. When rates rose, bonds fell with stocks, and its 5% volatility came with a 15% drawdown. Every strategy had its worst drawdown in the same window, January to September 2022.

## Talking points

- **Why expected returns are the weak input.** Mean estimates from 3–5 years of data are dominated by noise, and max Sharpe is the portfolio most sensitive to them. In this sample it happened not to hurt the Sharpe ratio, but the gap was insignificant and turnover was about nine times higher.
- **What Ledoit-Wolf fixes and what it does not.** It stabilizes the covariance matrix, which helps min variance and risk parity; it cannot repair noisy means.
- **Why equal weight is hard to beat.** It has zero estimation error. DeMiguel, Garlappi and Uppal (2009) find sample-based optimizers rarely beat 1/N out of sample, and this project's significance test reaches the same verdict.
- **Constraints act as regularization.** Long-only limits and weight caps block the most extreme estimation-error bets.

## Limitations and next steps

- One historical path, one universe. 2015–2022 contains a long equity bull market and the 2022 stock-bond sell-off, which matter a lot for these rankings.
- With about 8 years out of sample, the test has little power: a true Sharpe gap of 0.2 would usually go undetected. "Not significant" means "not distinguishable", not "equal".
- Possible extensions: Black-Litterman expected returns, hierarchical risk parity, factor-model covariance, turnover penalties in the objective, longer history (start in 2007 to include 2008).
