"""Figures. Colour encodes the strategy family; line style encodes the estimator."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import metrics as M  # noqa: E402

# Colour-blind-checked categorical palette, used in fixed order.
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

FAMILY_COLOR = {
    "Equal weight": PALETTE[0],
    "Min variance": PALETTE[1],
    "Max Sharpe": PALETTE[2],
    "Risk parity": PALETTE[3],
}
STYLE = {"sample": "-", "LW": "--", "LW + shrunk mean": ":"}


def _style_for(name: str) -> dict:
    family = next((f for f in FAMILY_COLOR if name.startswith(f)), None)
    color = FAMILY_COLOR.get(family, INK_2)
    if "shrunk mean" in name:
        ls = STYLE["LW + shrunk mean"]
    elif "(LW" in name:
        ls = STYLE["LW"]
    else:
        ls = STYLE["sample"]
    return {"color": color, "linestyle": ls, "linewidth": 2}


def _base(ax, title: str, ylabel: str | None = None):
    ax.set_title(title, loc="left", fontsize=12, color=INK, pad=10, fontweight="bold")
    if ylabel:
        ax.set_ylabel(ylabel, color=INK_2)
    ax.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=9)


def _pct(ax, axis="y", decimals=0):
    fmt = matplotlib.ticker.PercentFormatter(1.0, decimals=decimals)
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def _legend_below(ax):
    ax.legend(frameon=False, fontsize=8.5, ncol=4, loc="upper center",
              bbox_to_anchor=(0.5, -0.08), handlelength=3)


def _save(fig, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def plot_frontier(frontiers: dict, assets: pd.DataFrame, points: dict, path: Path, subtitle: str = ""):
    """frontiers: {label: DataFrame(volatility, return)}; assets: DataFrame(volatility, return)
    indexed by ticker; points: {label: (vol, ret)} for marked portfolios."""
    fig, ax = plt.subplots(figsize=(9, 6))
    for (label, fr), ls in zip(frontiers.items(), ["-", "--"]):
        ax.plot(fr["volatility"], fr["return"], color=INK, linestyle=ls, linewidth=2, label=f"Frontier ({label})")
    ax.scatter(assets["volatility"], assets["return"], s=36, color="#a9a8a3", zorder=3, label="Individual assets")
    for t, row in assets.iterrows():
        ax.annotate(t, (row["volatility"], row["return"]), xytext=(4, 3),
                    textcoords="offset points", fontsize=8, color=INK_2)
    for label, (v, r) in points.items():
        st = _style_for(label)
        ax.scatter(v, r, s=90, color=st["color"], edgecolor="white", linewidth=2, zorder=4, label=label)
    _base(ax, "Efficient frontier (long-only, capped)" + (f" — {subtitle}" if subtitle else ""), "Expected return (ann.)")
    ax.set_xlabel("Volatility (ann.)", color=INK_2)
    _pct(ax, "y"); _pct(ax, "x")
    ax.legend(frameon=False, fontsize=9, loc="best")
    _save(fig, path)


def plot_wealth(results: dict, path: Path):
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for name, res in results.items():
        wealth = (1 + res.returns).cumprod()
        ax.plot(wealth.index, wealth.values, label=name, **_style_for(name))
    _base(ax, "Out-of-sample growth of $1", "Wealth")
    _legend_below(ax)
    _save(fig, path)


def plot_drawdowns(results: dict, path: Path):
    fig, ax = plt.subplots(figsize=(10, 4.5))
    for name, res in results.items():
        dd = M.drawdown(res.returns)
        ax.plot(dd.index, dd.values, label=name, **_style_for(name))
    _base(ax, "Out-of-sample drawdowns", "Drawdown from peak")
    _pct(ax, "y")
    _legend_below(ax)
    _save(fig, path)


def plot_metric_bars(summary: pd.DataFrame, path: Path):
    """Small multiples: one panel per metric, never two scales on one axis."""
    cols = [("Sharpe ratio", False), ("Ann. volatility", True), ("Max drawdown", True), ("Ann. turnover", True)]
    fig, axes = plt.subplots(1, len(cols), figsize=(15, 0.45 * len(summary) + 1.6), sharey=True)
    names = summary.index[::-1]
    y = np.arange(len(names))
    for ax, (col, is_pct) in zip(axes, cols):
        vals = summary.loc[names, col].values
        colors = [_style_for(n)["color"] for n in names]
        ax.barh(y, vals, color=colors, height=0.6, edgecolor="white", linewidth=2)
        for yi, v in zip(y, vals):
            ax.annotate(f"{v:.1%}" if is_pct else f"{v:.2f}", (v, yi), xytext=(4 if v >= 0 else -4, 0),
                        textcoords="offset points", va="center", ha="left" if v >= 0 else "right",
                        fontsize=8, color=INK_2)
        _base(ax, col)
        ax.axvline(0, color=INK_2, linewidth=0.8)
        if is_pct:
            _pct(ax, "x")
        ax.margins(x=0.25)
    axes[0].set_yticks(y, names)
    _save(fig, path)


def plot_weights(results: dict, path: Path):
    """Heatmaps of target weights over time, one panel per strategy (sequential blue)."""
    from matplotlib.colors import LinearSegmentedColormap

    cmap = LinearSegmentedColormap.from_list("blue", ["#ffffff", "#cde2fb", "#6da7ec", "#2a78d6", "#184f95", "#0d366b"])
    names = [n for n in results if not n.startswith("Equal weight")]
    fig, axes = plt.subplots(len(names), 1, figsize=(11, 1.9 * len(names) + 0.6), sharex=True,
                             layout="constrained")
    axes = np.atleast_1d(axes)
    vmax = max(results[n].weights.values.max() for n in names)
    for ax, name in zip(axes, names):
        w = results[name].weights
        im = ax.imshow(w.T.values, aspect="auto", cmap=cmap, vmin=0, vmax=vmax, interpolation="nearest")
        ax.set_yticks(range(w.shape[1]), w.columns, fontsize=7, color=INK_2)
        ax.set_title(name, loc="left", fontsize=10, color=INK, fontweight="bold")
        for s in ax.spines.values():
            s.set_visible(False)
    ticks = range(0, len(w.index), max(1, len(w.index) // 8))
    axes[-1].set_xticks(list(ticks), [w.index[i].strftime("%Y-%m") for i in ticks], fontsize=8, color=INK_2)
    cbar = fig.colorbar(im, ax=axes, fraction=0.02, pad=0.01, shrink=0.5)
    cbar.ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
    cbar.set_label("Target weight", color=INK_2)
    fig.suptitle("Target weights at each rebalance", x=0.01, ha="left", fontsize=12, fontweight="bold")
    _save(fig, path)
