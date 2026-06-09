#!/usr/bin/env python3
"""Validate SAI_MGIMO_V3 and modelled student-flow separation."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "docs/data/mgimo_dashboard_data.json"
CSV_PATH = ROOT / "docs/data/student_attraction_v3.csv"
META_PATH = ROOT / "docs/data/student_model_v3_metadata.json"
FLOWS_PATH = ROOT / "docs/data/student_flows_modelled_v3.csv"
UIS_KEY = "A_OUTBOUND_MOBILITY_UIS"
OLD_UIS_BASE = "A_MOBILITY" + "_READINESS"
OLD_UIS_KEY = OLD_UIS_BASE + "_" + "PRO" + "XY"
REQUIRED_TRACE_FIELDS = {
    "source_key",
    "year",
    "raw_value",
    "normalized_value",
    "normalization_method",
    "weight",
    "observation_status",
}

WEIGHTS = {
    "A_YOUTH_OPPORTUNITY": 0.50,
    UIS_KEY: 0.16,
    "A_LEGAL_PARTNERSHIP_CONTEXT": 0.12,
    "A_PROGRAM_RELEVANCE": 0.08,
    "A_AFFORDABILITY_ACCESS": 0.06,
    "A_DIGITAL_REACH": 0.04,
    "A_DATAQ": 0.04,
}


def main() -> None:
    failures: list[str] = []
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    df = pd.read_csv(CSV_PATH)
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    flows = pd.read_csv(FLOWS_PATH)
    attraction = payload.get("studentAttraction") or {}
    model = attraction.get("model") or {}

    if model.get("name") != "SAI_MGIMO_V3":
        failures.append("studentAttraction model name is not SAI_MGIMO_V3")
    if model.get("weights") != WEIGHTS:
        failures.append(f"SAI weights mismatch: {model.get('weights')}")
    for iso3, row in (attraction.get("byCountry") or {}).items():
        has_score = row.get("saiMgimoV3Score") is not None
        for holder in ("components", "componentTrace"):
            keys = set((row.get(holder) or {}).keys())
            if OLD_UIS_BASE in keys or OLD_UIS_KEY in keys:
                failures.append(f"{iso3}: old mobility component remains in {holder}")
            if has_score and UIS_KEY not in keys:
                failures.append(f"{iso3}: UIS mobility component missing in {holder}")
        if has_score:
            trace = (row.get("componentTrace") or {}).get(UIS_KEY) or {}
            missing = [key for key in REQUIRED_TRACE_FIELDS if trace.get(key) in (None, "")]
            if missing:
                failures.append(f"{iso3}: UIS trace lacks {missing}")
    if OLD_UIS_KEY in df.columns or OLD_UIS_BASE in df.columns:
        failures.append("student_attraction_v3.csv keeps an old mobility column")
    if UIS_KEY not in df.columns:
        failures.append("student_attraction_v3.csv missing UIS mobility column")
    if meta.get("uis_component_policy", {}).get("component") != UIS_KEY:
        failures.append("metadata lacks UIS mobility component policy")
    if "uis_outbound_mobility_ratio" not in df.columns:
        failures.append("student_attraction_v3.csv missing UIS raw ratio column")

    scored = df[df["rank_practical_student_recruitment"].notna()]
    if len(scored) < 100:
        failures.append("too few practical student countries")
    hard_cols = ["is_unfriendly_430r", "is_domestic_russia", "is_non_sovereign_or_special"]
    hard = df[hard_cols].astype(bool).any(axis=1)
    if df.loc[hard, "SAI_MGIMO_V3_SCORE"].notna().any():
        failures.append("hard-filtered countries have SAI scores")

    observed_rows = payload.get("studentFlowsObserved", {}).get("rows", [])
    if observed_rows:
        failures.append("observed student flows must remain zero until factual MGIMO country source is loaded")
    modelled = payload.get("studentFlowsModelled") or {}
    if modelled.get("model", {}).get("scoreType") != "modelled_attraction_potential_from_open_indicators_not_mgimo_headcount":
        failures.append("modelled flows are not labelled as non-headcount potential")
    if len(modelled.get("rows", [])) != len(flows):
        failures.append("payload modelled flows do not match CSV row count")
    for row in modelled.get("rows", [])[:120]:
        if row.get("flowType") != "modelled_potential_not_observed_mgimo_students":
            failures.append(f"{row.get('originIso3')}: modelled flow type is ambiguous")
        if row.get("strokeWidth") is None or row.get("modelledPotentialIndex") is None:
            failures.append(f"{row.get('originIso3')}: modelled flow visual fields missing")
        trace = row.get("trace") or {}
        if trace.get("score_type") != "modelled_potential_not_observed_student_headcount":
            failures.append(f"{row.get('originIso3')}: modelled flow trace score_type missing")

    africa_regions = scored[scored["region"].astype(str).str.contains("Sub-Saharan Africa", na=False)]
    if len(africa_regions.head(30)) < 6:
        failures.append("regional focus should keep Africa visible in the practical student list")

    if failures:
        raise SystemExit("student model validation failed:\n" + "\n".join(failures[:80]))
    print("student model validation passed")


if __name__ == "__main__":
    main()
