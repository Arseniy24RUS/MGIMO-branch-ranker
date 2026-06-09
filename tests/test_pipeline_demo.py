from __future__ import annotations

from pathlib import Path

import pandas as pd

from mgimo_ranker.config import load_config
from mgimo_ranker.pipeline import run_pipeline


def term(*parts: str) -> str:
    return "".join(parts)


def test_demo_pipeline_creates_plan_ranking_without_old_mode_columns(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "configs" / "default.yaml")
    files = run_pipeline(cfg, root / "data", tmp_path, mode="demo", mc_iterations=20, usd_rub=73.3436)
    ranking = pd.read_csv(files["ranking"])

    assert not ranking.empty
    assert "PRIORITY" in ranking.columns
    assert "PROGRAM_FIT" in ranking.columns
    assert "npv_positive_probability" in ranking.columns
    old_mode_rank_columns = {
        term("rank_", "base", "line"),
        term("rank_", "soft", "_power"),
        term("rank_", "comm", "ercial"),
        term("rank_", "risk", "_averse"),
    }
    old_mode_columns = [
        column
        for column in ranking.columns
        if column.startswith("PRIORITY_") or column in old_mode_rank_columns
    ]
    assert old_mode_columns == []
    assert ranking.loc[ranking.iso3.eq("USA"), "eligible"].iloc[0] in [False, "False", 0]
    assert ranking.loc[ranking.iso3.eq("KAZ"), "eligible"].iloc[0] in [False, "False", 0]
    assert ranking[ranking["eligible"].astype(str).str.lower().isin(["true", "1"])].shape[0] > 0


def test_pipeline_marks_vietnam_as_neutral_plan_status(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "configs" / "default.yaml")
    files = run_pipeline(cfg, root / "data", tmp_path, mode="demo", mc_iterations=10, usd_rub=73.3436)
    ranking = pd.read_csv(files["ranking"])
    vnm = ranking.loc[ranking.iso3.eq("VNM")].iloc[0]

    assert bool(vnm["has_mgimo_pipeline"])
    public_status = " ".join(
        str(vnm.get(field, ""))
        for field in ["status", "public_status", "table_status", "map_status", "recommendation_category"]
        if field in ranking.columns
    ).lower()
    assert "neutral" in public_status or "\u043d\u0435\u0439\u0442\u0440" in public_status
    assert "pipeline" not in public_status
    assert "priority" not in public_status
    assert "excluded" not in public_status
    assert vnm["recommended_program_profile"] == "digital_finance_business_informatics"
    assert "program_profile_ranking" in files
