from __future__ import annotations

import numpy as np
import pandas as pd

from mgimo_ranker.model.indices import compute_priority


def monte_carlo_weight_sensitivity(
    df: pd.DataFrame,
    base_weights: dict[str, float],
    n: int = 1000,
    concentration: float = 80.0,
    epsilon: float = 0.05,
    seed: int = 42,
) -> pd.DataFrame:
    """Estimate rank robustness under random perturbations of component weights."""
    rng = np.random.default_rng(seed)
    keys = list(base_weights)
    alpha = np.array([max(1e-6, base_weights[k] * concentration) for k in keys], dtype=float)
    rank_records = {iso3: [] for iso3 in df["iso3"].astype(str)}
    eligible = df["eligible"].astype(bool) if "eligible" in df else pd.Series(True, index=df.index)
    for _ in range(n):
        w = rng.dirichlet(alpha)
        weights = dict(zip(keys, w))
        scored = compute_priority(df, weights, epsilon=epsilon)
        scored.loc[~eligible, "PRIORITY"] = 0.0
        ranks = scored["PRIORITY"].where(eligible).rank(method="min", ascending=False)
        for iso3, rank in zip(scored["iso3"].astype(str), ranks):
            rank_records[iso3].append(float(rank) if pd.notna(rank) else np.nan)
    rows = []
    for iso3, ranks in rank_records.items():
        arr = np.array(ranks, dtype=float)
        arr = arr[~np.isnan(arr)]
        if arr.size == 0:
            rows.append({"iso3": iso3, "rank_median_mc": np.nan, "rank_q25_mc": np.nan, "rank_q75_mc": np.nan, "p_top5_mc": 0.0, "p_top10_mc": 0.0, "p_top20_mc": 0.0})
        else:
            rows.append(
                {
                    "iso3": iso3,
                    "rank_median_mc": float(np.median(arr)),
                    "rank_q25_mc": float(np.quantile(arr, 0.25)),
                    "rank_q75_mc": float(np.quantile(arr, 0.75)),
                    "p_top5_mc": float(np.mean(arr <= 5)),
                    "p_top10_mc": float(np.mean(arr <= 10)),
                    "p_top20_mc": float(np.mean(arr <= 20)),
                }
            )
    return pd.DataFrame(rows)


def category_assignment(row: pd.Series) -> str:
    if not bool(row.get("eligible", True)):
        return "D_excluded"
    if bool(row.get("has_mgimo_pipeline", False)):
        return "neutral_in_preparation"
    priority = row.get("PRIORITY", 0)
    npv = row.get("npv_10y_usd", np.nan)
    p_positive = row.get("npv_positive_probability", np.nan)
    feas = row.get("I_FEAS", 0.5)
    financially_viable = (pd.notna(p_positive) and p_positive >= 0.50) or (pd.isna(p_positive) and pd.notna(npv) and npv > 0)
    if pd.notna(priority) and priority >= 55 and financially_viable and feas >= 0.45:
        return "A_open_priority"
    if pd.notna(priority) and priority >= 45 and row.get("I_RUSCOMP", 0) >= 0.72 and row.get("I_HRSTRAT", 0) >= 0.55:
        return "B_strategic_with_subsidy"
    if pd.notna(priority) and priority >= 30:
        return "C_watchlist"
    return "D_not_recommended"


def make_explainability(df: pd.DataFrame, component_cols: list[str] | None = None) -> pd.DataFrame:
    component_cols = component_cols or ["I_DEM", "I_ECO", "I_RUSCOMP", "I_FIN", "I_FEAS", "I_HRSTRAT", "PROGRAM_FIT"]
    rows = []
    for _, row in df.iterrows():
        comps = {c: row.get(c, np.nan) for c in component_cols}
        valid = {c: v for c, v in comps.items() if pd.notna(v)}
        top = sorted(valid.items(), key=lambda kv: kv[1], reverse=True)[:3]
        bottom = sorted(valid.items(), key=lambda kv: kv[1])[:3]
        rows.append(
            {
                "iso3": row["iso3"],
                "top_strengths": "; ".join(f"{k}={v:.2f}" for k, v in top),
                "main_weaknesses": "; ".join(f"{k}={v:.2f}" for k, v in bottom),
            }
        )
    return pd.DataFrame(rows)
