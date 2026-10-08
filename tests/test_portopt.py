import numpy as np
import pandas as pd
import pytest

from portopt import backtest as B, data, estimators as E, metrics as M, optimizers as O
from portopt.config import UNIVERSE

TICKERS = list(UNIVERSE)
CAP = 0.30


@pytest.fixture(scope="module")
def rets():
    return data.synthetic_returns(TICKERS, n_months=120, seed=1)


@pytest.fixture(scope="module")
def est(rets):
    return E.estimate(rets.iloc[:48], "sample")


# ---------------------------------------------------------------- optimizers
@pytest.mark.parametrize("name", list(O.STRATEGIES))
def test_weights_are_long_only_capped_and_fully_invested(est, name):
    mu, cov = est
    w = O.STRATEGIES[name](mu, cov, CAP)
    assert w.sum() == pytest.approx(1, abs=1e-8)
    assert (w >= -1e-8).all()
    assert (w <= CAP + 1e-6).all()


def test_min_variance_has_lowest_in_sample_variance(est):
    mu, cov = est
    v = {k: O.portfolio_stats(f(mu, cov, CAP), mu, cov)["volatility"] for k, f in O.STRATEGIES.items()}
    assert v["min_variance"] <= min(v.values()) + 1e-8


def test_max_sharpe_has_highest_in_sample_sharpe(est):
    mu, cov = est
    s = {k: O.portfolio_stats(f(mu, cov, CAP), mu, cov)["sharpe"] for k, f in O.STRATEGIES.items()}
    assert s["max_sharpe"] >= max(s.values()) - 1e-6


def test_max_sharpe_beats_random_feasible_portfolios(est):
    mu, cov = est
    best = O.portfolio_stats(O.max_sharpe(mu, cov, CAP), mu, cov)["sharpe"]
    rng = np.random.default_rng(0)
    for _ in range(500):
        w = rng.dirichlet(np.ones(len(mu)))
        if w.max() <= CAP:
            assert O.portfolio_stats(w, mu, cov)["sharpe"] <= best + 1e-6


def test_risk_parity_equalizes_risk_contributions(est):
    mu, cov = est
    rc = O.risk_contributions(O.risk_parity(mu, cov, cap=1.0), cov)
    assert rc.sum() == pytest.approx(1)
    assert np.allclose(rc, 1 / len(rc), atol=1e-4)


def test_risk_parity_respects_a_binding_cap():
    # One very low-vol asset would take most of the weight without a cap.
    cov = pd.DataFrame(np.diag([0.0001, 0.04, 0.05, 0.06]), index=list("ABCD"), columns=list("ABCD"))
    mu = pd.Series(0.05, index=cov.index)
    assert O.risk_parity(mu, cov, cap=1.0)["A"] > 0.5
    w = O.risk_parity(mu, cov, cap=0.4)
    assert w.max() <= 0.4 + 1e-6 and w.sum() == pytest.approx(1)
    assert w["A"] == pytest.approx(0.4, abs=1e-4)
    rc = O.risk_contributions(w, cov)  # the uncapped names still share risk equally
    assert np.allclose(rc[["B", "C", "D"]], rc["B"], atol=1e-3)


def test_max_sharpe_falls_back_when_all_returns_negative(est):
    _, cov = est
    mu = pd.Series(-0.05, index=cov.index)
    w = O.max_sharpe(mu, cov, CAP)
    assert np.allclose(w, O.min_variance(mu, cov, CAP), atol=1e-6)


def test_infeasible_cap_raises(est):
    mu, cov = est
    with pytest.raises(ValueError):
        O.min_variance(mu, cov, cap=0.05)  # 13 assets x 5% < 100%


def test_frontier_is_increasing_and_starts_at_min_variance(est):
    mu, cov = est
    fr = O.efficient_frontier(mu, cov, CAP, n_points=15)
    assert (np.diff(fr["return"]) >= -1e-9).all()
    assert (np.diff(fr["volatility"]) >= -1e-6).all()
    mv = O.portfolio_stats(O.min_variance(mu, cov, CAP), mu, cov)
    assert fr["volatility"].iloc[0] == pytest.approx(mv["volatility"], rel=1e-3)


# ---------------------------------------------------------------- estimators
def test_ledoit_wolf_is_well_conditioned(rets):
    short = rets.iloc[:10]  # fewer months than assets: sample cov is singular
    assert np.linalg.matrix_rank(E.sample_cov(short)) < len(TICKERS)
    assert np.linalg.eigvalsh(E.ledoit_wolf_cov(short)).min() > 0
    assert 0 <= E.ledoit_wolf_intensity(short) <= 1


def test_shrunk_mean_interpolates(rets):
    m0, m1 = E.shrunk_mean_returns(rets, 0), E.shrunk_mean_returns(rets, 1)
    assert np.allclose(m0, E.mean_returns(rets))
    assert np.allclose(m1, m1.iloc[0])


# ---------------------------------------------------------------- backtest
def test_no_look_ahead(rets):
    """Scrambling the future must not change any weight chosen before it."""
    strat = B.Strategy("ms", O.max_sharpe, "sample")
    base = B.run_backtest(rets, strat, window=36, cap=CAP)
    cut = 72
    future = rets.copy()
    future.iloc[cut:] = np.random.default_rng(9).normal(0, 0.1, future.iloc[cut:].shape)
    alt = B.run_backtest(future, strat, window=36, cap=CAP)
    before = base.weights.index < rets.index[cut]
    after = base.weights.index > rets.index[cut]
    pd.testing.assert_frame_equal(base.weights[before], alt.weights[before])
    assert not np.allclose(base.weights[after], alt.weights[after])
    pd.testing.assert_series_equal(base.returns.loc[: rets.index[cut - 1]], alt.returns.loc[: rets.index[cut - 1]])


def test_backtest_matches_manual_buy_and_hold(rets):
    strat = B.Strategy("ew", O.equal_weight)
    res = B.run_backtest(rets, strat, window=36, rebalance_every=3, cap=CAP)
    assert res.returns.index[0] == rets.index[36]
    assert len(res.weights) == int(np.ceil((len(rets) - 36) / 3))
    # Three months of drifting equal weights == average growth of each asset.
    block = rets.iloc[36:39]
    manual = (1 + block).prod().mean() - 1
    assert (1 + res.returns.iloc[:3]).prod() - 1 == pytest.approx(manual)


def test_costs_reduce_returns_by_turnover(rets):
    strat = B.Strategy("mv", O.min_variance)
    free = B.run_backtest(rets, strat, window=36, cap=CAP)
    paid = B.run_backtest(rets, strat, window=36, cap=CAP, cost_bps=10)
    drag = (free.returns - paid.returns).sum()
    assert drag == pytest.approx(2 * free.turnover.sum() * 10 / 1e4)


# ---------------------------------------------------------------- metrics
def test_metrics_on_known_series():
    r = pd.Series([0.10, -0.50, 0.20, 0.10])
    assert M.max_drawdown(r) == pytest.approx(-0.5)
    assert M.cagr(pd.Series([0.01] * 12)) == pytest.approx(1.01**12 - 1)
    assert M.sharpe(pd.Series([0.01, 0.03] * 6)) == pytest.approx(0.02 / np.std([0.01, 0.03] * 6, ddof=1) * np.sqrt(12))


# ---------------------------------------------------------------- significance
from portopt import stats as S  # noqa: E402


def test_block_indices_are_contiguous_blocks():
    idx = S.block_indices(n=20, block=5, n_boot=50, rng=np.random.default_rng(0))
    assert idx.shape == (50, 20) and idx.min() >= 0 and idx.max() < 20
    first = idx[:, :5]
    assert ((np.diff(first, axis=1) % 20) == 1).all()


def test_identical_strategies_have_zero_gap_and_p_one(rets):
    r = rets["SPY"]
    t = S.sharpe_diff_test(r, r, n_boot=500)
    assert t["diff"] == pytest.approx(0)
    assert t["p_value"] == pytest.approx(1)


def test_clearly_better_strategy_is_significant():
    rng = np.random.default_rng(3)
    noise = rng.normal(0, 0.03, 240)
    good = pd.Series(0.02 + noise + rng.normal(0, 0.005, 240))
    bad = pd.Series(-0.005 + noise + rng.normal(0, 0.005, 240))
    t = S.sharpe_diff_test(good, bad, n_boot=2000)
    assert t["diff"] > 0 and t["p_value"] < 0.01 and t["ci_low"] > 0


def test_pure_noise_is_not_significant_on_average():
    rng = np.random.default_rng(4)
    pvals = []
    for _ in range(20):
        a = pd.Series(rng.normal(0.005, 0.04, 96))
        b = pd.Series(rng.normal(0.005, 0.04, 96))
        pvals.append(S.sharpe_diff_test(a, b, n_boot=500)["p_value"])
    assert np.mean(np.array(pvals) < 0.05) <= 0.15
