# AI commentary

_Written by Claude in a Claude chat from [`commentary_prompt.md`](commentary_prompt.md), which contains only the setup and results shown there. The model was told to use only those numbers._

Over January 2015 to December 2022, no allocation separated itself from a simple equal-weight portfolio. Equal weight returned 4.9% a year with 9.5% volatility, a Sharpe ratio of 0.46 and a 20.0% maximum drawdown, while trading only 8.3% of the portfolio a year. Max Sharpe with the sample covariance posted the highest Sharpe ratio, 0.52, and a shallower 17.1% drawdown. But the bootstrap p-value for its gap over equal weight is 0.78, and it turned over 76.6% of the portfolio a year to get there. None of the seven strategies differs from equal weight at the 5% level; the smallest p-value is 0.15.

The estimation-light portfolios split in an informative way. Min variance and risk parity cut volatility to between 5.3% and 7.5%, but they earned much less, so their Sharpe ratios (0.19 to 0.34) trailed equal weight while their drawdowns still reached 14% to 19%. Max Sharpe kept pace with equal weight only by repositioning heavily every quarter. That is the signature of an optimizer reacting to noisy expected-return estimates: small changes in trailing means move the weights a lot, and here that churn bought no reliable improvement.

Ledoit-Wolf shrinkage, with an average intensity of 0.19, helped the portfolios that depend only on the covariance matrix. It raised min variance from 0.19 to 0.25 and risk parity from 0.31 to 0.34, and it lowered turnover for every optimizer. It did not help max Sharpe, which fell from 0.52 to 0.45, because shrinkage acts on the covariance matrix, not on the expected returns that drive that portfolio. Shrinking the means instead cut max Sharpe's volatility to 7.6% at a similar Sharpe ratio.

All of this rests on one 96-month path. Different start dates or a different universe could reorder the strategies.
