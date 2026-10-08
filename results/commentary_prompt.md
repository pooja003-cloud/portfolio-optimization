Write a commentary of about 250 words on this out-of-sample backtest.

Setup
- Data: 13 ETFs (SPY, QQQ, IWM, EFA, EEM, VNQ, TLT, IEF, TIP, LQD, HYG, GLD, DBC), monthly, 2012-01 to 2022-12
- Out-of-sample period: 2015-01 to 2022-12 (96 months)
- Estimation window: 36 months, rebalanced every 3 months
- Constraints: long-only, max 30% per asset, fully invested
- Risk-free rate in Sharpe: 0.00% p.a.
- Transaction costs: 0 bps one-way

Out-of-sample results (monthly returns, annualized)
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

Additional facts
- Min variance (sample): Sharpe difference vs equal weight -0.19, bootstrap p-value 0.33
- Min variance (LW): Sharpe difference vs equal weight -0.13, bootstrap p-value 0.46
- Max Sharpe (sample): Sharpe difference vs equal weight +0.08, bootstrap p-value 0.73
- Max Sharpe (LW): Sharpe difference vs equal weight -0.00, bootstrap p-value 0.99
- Max Sharpe (LW + shrunk mean): Sharpe difference vs equal weight +0.00, bootstrap p-value 1.00
- Risk parity (sample): Sharpe difference vs equal weight -0.11, bootstrap p-value 0.40
- Risk parity (LW): Sharpe difference vs equal weight -0.09, bootstrap p-value 0.41
- Average Ledoit-Wolf shrinkage intensity across rebalances: 0.19 (0 = sample covariance, 1 = fully shrunk).
- 'Shrunk mean' moves each asset's historical mean 50% toward the cross-asset average.
- Turnover is one-way, averaged per year.

Cover, in plain prose (no headings, no bullet lists):
1. Which allocation held up best out of sample, judged on risk-adjusted return and drawdown, and the cost in turnover. Use the bootstrap p-values to say whether any Sharpe gap versus equal weight is statistically meaningful; do not call a gap real if p >= 0.05.
2. How max-Sharpe compared with the estimation-light portfolios (equal weight, min variance, risk parity), and why noisy expected-return estimates explain the gap.
3. What Ledoit-Wolf covariance shrinkage changed, and what it cannot fix (it shrinks the covariance, not the expected returns).
4. One caveat about drawing conclusions from a single historical sample.
