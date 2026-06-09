from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from mgimo_ranker.config import load_config
from mgimo_ranker.model.flags import apply_eligibility, apply_static_flags
from mgimo_ranker.model.indices import compute_indices, compute_priority
from mgimo_ranker.utils import geometric_score


PLAN_WEIGHTS = {
    "I_MARKET": 0.22,
    "I_PROGRAM": 0.12,
    "I_RUSCOMP": 0.16,
    "I_ECO": 0.14,
    "I_FIN": 0.16,
    "I_FEAS": 0.14,
    "I_HRSTRAT": 0.06,
}


def test_config_exposes_one_plan_weight_set_that_sums_to_one():
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "configs" / "default.yaml")
    weights = cfg.raw["weights"]

    assert weights
    assert all(not isinstance(value, dict) for value in weights.values())
    assert math.isclose(sum(float(value) for value in weights.values()), 1.0, abs_tol=1e-12)


def test_unfriendly_country_is_zero_compatibility_and_ineligible():
    features = pd.DataFrame(
        {
            "iso3": ["USA", "IND"],
            "country": ["United States", "India"],
            "region": ["North America", "South Asia"],
            "pop_15_24_2026": [10, 100],
            "pop_15_24_2035": [10, 110],
            "pop_15_24_2050": [10, 120],
            "tertiary_enrollment_gross": [80, 30],
            "secondary_completion_upper": [95, 80],
            "gdp_ppp_current": [1000, 900],
            "gdp_pc_ppp_current": [80000, 10000],
            "gdp_growth_real": [2, 6],
            "inflation_cpi": [2, 5],
            "unemployment": [4, 5],
        }
    )
    unfriendly = pd.DataFrame({"iso3": ["USA"], "entry_type": ["state"], "group_label": [""], "source_basis": ["test"], "hard_exclude": [1]})
    presence = pd.DataFrame({"iso3": [], "presence_type": [], "exclude_from_new_branch_ranking": [], "city": [], "notes": []})
    out = apply_static_flags(features, unfriendly, presence)
    out = compute_indices(out)
    out = apply_eligibility(out, hard_exclude_unfriendly=True)
    assert out.loc[out.iso3.eq("USA"), "I_RUSCOMP"].iloc[0] == 0
    assert not bool(out.loc[out.iso3.eq("USA"), "eligible"].iloc[0])
    assert bool(out.loc[out.iso3.eq("IND"), "eligible"].iloc[0])


def test_priority_sets_ineligible_to_zero():
    df = pd.DataFrame({"iso3": ["A", "B"], "eligible": [True, False], "I_DEM": [0.8, 1.0], "I_ECO": [0.8, 1.0], "I_RUSCOMP": [1.0, 0.0], "I_FIN": [0.8, 1.0], "I_FEAS": [0.8, 1.0], "I_HRSTRAT": [0.8, 1.0]})
    scored = compute_priority(df, {"I_DEM": 0.25, "I_ECO": 0.2, "I_RUSCOMP": 0.2, "I_FIN": 0.15, "I_FEAS": 0.15, "I_HRSTRAT": 0.05})
    assert scored.loc[scored.iso3.eq("B"), "PRIORITY"].iloc[0] == 0
    assert scored.loc[scored.iso3.eq("A"), "PRIORITY"].iloc[0] > 0


def test_priority_formula_uses_backend_geometric_contract():
    df = pd.DataFrame(
        {
            "iso3": ["AAA"],
            "eligible": [True],
            "I_MARKET": [0.9],
            "I_PROGRAM": [0.7],
            "I_RUSCOMP": [0.8],
            "I_ECO": [0.6],
            "I_FIN": [0.5],
            "I_FEAS": [0.75],
            "I_HRSTRAT": [0.65],
        }
    )
    scored = compute_priority(df, PLAN_WEIGHTS, epsilon=0.05)
    expected = geometric_score(df, PLAN_WEIGHTS, epsilon=0.05).iloc[0]

    assert scored.loc[0, "PRIORITY_RAW"] == expected
    assert scored.loc[0, "PRIORITY"] == expected
