Write a commentary of about 250 words on this out-of-sample backtest, for a reader who knows some finance but not this project.

Setup
- Data: 13 exchange-traded funds (SPY, QQQ, IWM, EFA, EEM, VNQ, TLT, IEF, TIP, LQD, HYG, GLD, DBC), monthly, 2012-01 to 2022-12
- Test period (out of sample): 2015-01 to 2022-12 (96 months)
- Estimation window: 36 months, rebalanced every 3 months
- Constraints: no short selling, at most 30% in any asset, fully invested
- Risk-free rate: 3-month US Treasury bill (FRED series TB3MS), changing monthly; averaged 0.92% a year over the test period (lowest 0.02%, highest 4.15%)
- Trading costs: 0 basis points per trade

Results over the test period (from monthly returns, annualized)
|                                            | Annual return   | Annual volatility   | Sharpe ratio   | Maximum drawdown   | Annual turnover   | Average largest weight   |
|:-------------------------------------------|:----------------|:--------------------|:---------------|:-------------------|:------------------|:-------------------------|
| Equal weight                               | 4.9%            | 9.5%                | 0.46           | -20.0%             | 8.3%              | 7.7%                     |
| Minimum variance (sample)                  | 1.8%            | 5.3%                | 0.19           | -14.8%             | 29.0%             | 30.0%                    |
| Minimum variance (Ledoit-Wolf)             | 2.2%            | 5.4%                | 0.25           | -14.1%             | 22.2%             | 29.0%                    |
| Maximum Sharpe (sample)                    | 5.4%            | 9.0%                | 0.52           | -17.1%             | 76.6%             | 30.0%                    |
| Maximum Sharpe (Ledoit-Wolf)               | 5.0%            | 9.8%                | 0.45           | -19.7%             | 66.4%             | 29.5%                    |
| Maximum Sharpe (Ledoit-Wolf, shrunk means) | 4.2%            | 7.6%                | 0.46           | -16.1%             | 65.0%             | 27.3%                    |
| Risk parity (sample)                       | 2.9%            | 7.1%                | 0.31           | -18.2%             | 13.2%             | 20.9%                    |
| Risk parity (Ledoit-Wolf)                  | 3.2%            | 7.5%                | 0.34           | -18.8%             | 11.4%             | 16.7%                    |

Additional facts
- Minimum variance (sample): Sharpe ratio -0.27 against equal weight, p-value 0.15
- Minimum variance (Ledoit-Wolf): Sharpe ratio -0.20 against equal weight, p-value 0.23
- Maximum Sharpe (sample): Sharpe ratio +0.07 against equal weight, p-value 0.78
- Maximum Sharpe (Ledoit-Wolf): Sharpe ratio -0.01 against equal weight, p-value 0.98
- Maximum Sharpe (Ledoit-Wolf, shrunk means): Sharpe ratio +0.00 against equal weight, p-value 0.98
- Risk parity (sample): Sharpe ratio -0.14 against equal weight, p-value 0.26
- Risk parity (Ledoit-Wolf): Sharpe ratio -0.12 against equal weight, p-value 0.28
- Average Ledoit-Wolf shrinkage intensity across rebalances: 0.19 (0 = plain sample covariance, 1 = fully shrunk).
- 'Shrunk means' moves each asset's historical average return halfway toward the average across all assets.
- Turnover is one-way (the share of the portfolio bought each year).

Cover, in plain prose (no headings, no bullet lists):
1. Which allocation held up best out of sample, judged on risk-adjusted return and drawdown, and the cost in turnover. Use the bootstrap p-values to say whether any Sharpe gap versus equal weight is statistically meaningful; do not call a gap real if p >= 0.05.
2. How maximum Sharpe compared with the portfolios that need little or no return forecasting (equal weight, minimum variance, risk parity), and why noisy expected-return estimates explain the gap.
3. What Ledoit-Wolf covariance shrinkage changed, and what it cannot fix (it shrinks the covariance, not the expected returns).
4. One caveat about drawing conclusions from a single historical sample.
