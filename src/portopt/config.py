"""Default settings. Most of these can be changed from the command line."""

# 13 exchange-traded funds, all trading before 2012, covering stocks,
# government bonds, corporate bonds, inflation-linked bonds, property,
# gold and commodities.
UNIVERSE = {
    "SPY": "US large-company stocks (S&P 500)",
    "QQQ": "US technology stocks (Nasdaq-100)",
    "IWM": "US small-company stocks (Russell 2000)",
    "EFA": "Developed-market stocks outside the US",
    "EEM": "Emerging-market stocks",
    "VNQ": "US real estate investment trusts",
    "TLT": "US Treasury bonds, 20+ years",
    "IEF": "US Treasury bonds, 7-10 years",
    "TIP": "US inflation-protected Treasury bonds",
    "LQD": "US investment-grade corporate bonds",
    "HYG": "US high-yield corporate bonds",
    "GLD": "Gold",
    "DBC": "Broad commodities",
}

START = "2012-01-01"
END = "2022-12-31"

ESTIMATION_WINDOW = 36   # months of history behind each rebalance (36-60 = 3-5 years)
REBALANCE_EVERY = 3      # months, i.e. quarterly
WEIGHT_CAP = 0.30        # no asset above 30%; no short selling anywhere

# "tbill" uses the 3-month US Treasury bill rate from FRED (series TB3MS),
# which changes every month. A number means a fixed annual rate, e.g. 0.
RISK_FREE = "tbill"
FRED_SERIES = "TB3MS"

COST_BPS = 0.0           # trading cost per trade, in basis points (1 bp = 0.01%)

PERIODS_PER_YEAR = 12
