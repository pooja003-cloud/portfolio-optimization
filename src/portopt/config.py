"""Project defaults. Everything here can be overridden from the command line."""

# 13 liquid ETFs that all trade before 2012, spanning equities, rates,
# credit, inflation, real estate and commodities.
UNIVERSE = {
    "SPY": "US large cap equity",
    "QQQ": "US tech / Nasdaq-100",
    "IWM": "US small cap equity",
    "EFA": "Developed ex-US equity",
    "EEM": "Emerging market equity",
    "VNQ": "US REITs",
    "TLT": "US Treasuries 20y+",
    "IEF": "US Treasuries 7-10y",
    "TIP": "US TIPS",
    "LQD": "US investment-grade corporates",
    "HYG": "US high yield corporates",
    "GLD": "Gold",
    "DBC": "Broad commodities",
}

START = "2012-01-01"
END = "2022-12-31"

ESTIMATION_WINDOW = 36      # months of history used at each rebalance (3 to 5 years -> 36 to 60)
REBALANCE_EVERY = 3         # months (quarterly)
WEIGHT_CAP = 0.30           # max weight per asset; long-only throughout
# Risk-free rate: "tbill" = 3-month US T-bill (FRED series TB3MS), varying by
# month; or a number = constant annual rate (e.g. 0.0).
RISK_FREE = "tbill"
FRED_SERIES = "TB3MS"
COST_BPS = 0.0              # one-way transaction cost in basis points (0 = frictionless)

PERIODS_PER_YEAR = 12
