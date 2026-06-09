#!/usr/bin/env python3
"""Validate branch factor source lineage rows used by the methodology UI."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINEAGE_JSON = ROOT / "docs/data/branch_factor_source_lineage.json"
FACTOR_INPUTS = ROOT / "docs/data/factor_inputs_long.json"

REQUIRED = {
    "iso3",
    "factor_key",
    "input_key",
    "lineage_type",
    "official_indicator_code",
    "official_indicator_name_en",
    "official_indicator_name_ru",
    "provider",
    "source_name",
    "source_key",
    "source_note",
    "year",
    "raw_value",
    "normalized_value",
    "normalization_method",
    "within_factor_weight",
    "factor_weight",
    "scoring_role",
    "observation_status",
}

OFFICIAL_REQUIRED = {"official_url", "raw_file"}
WGI_CODES = {"PV.EST", "GE.EST", "RQ.EST", "RL.EST", "CC.EST"}
MODELLED_CODE = "not_applicable_modelled_component"


def direct_row(row: dict) -> bool:
    role = str(row.get("scoring_role") or "")
    try:
        weight = float(row.get("within_factor_weight") or 0)
    except (TypeError, ValueError):
        weight = 0.0
    return weight != 0 or "direct_factor_formula_component" in role


def main() -> None:
    failures: list[str] = []
    if not LINEAGE_JSON.exists():
        raise SystemExit("branch factor source lineage JSON missing")
    if not FACTOR_INPUTS.exists():
        raise SystemExit("factor_inputs_long.json missing")
    rows = json.loads(LINEAGE_JSON.read_text(encoding="utf-8"))
    factor_rows = json.loads(FACTOR_INPUTS.read_text(encoding="utf-8"))
    if len(rows) != len(factor_rows):
        failures.append(f"lineage row count mismatch: {len(rows)} != {len(factor_rows)}")
    keys = {(row.get("iso3"), row.get("factor_key"), row.get("input_key")) for row in rows}
    expected_keys = {(row.get("iso3"), row.get("factor_key"), row.get("input_key")) for row in factor_rows}
    if keys != expected_keys:
        failures.append("lineage keys do not match factor_inputs_long")
    for index, row in enumerate(rows, 1):
        label = f"{row.get('iso3')}|{row.get('factor_key')}|{row.get('input_key')}"
        missing = [key for key in REQUIRED if row.get(key) in (None, "")]
        if missing and direct_row(row):
            failures.append(f"{label}: missing {missing}")
        code = str(row.get("official_indicator_code") or "")
        if code != MODELLED_CODE and direct_row(row):
            missing_source = [key for key in OFFICIAL_REQUIRED if row.get(key) in (None, "")]
            if missing_source:
                failures.append(f"{label}: missing source fields {missing_source}")
        if code in WGI_CODES:
            if "data.worldbank.org/indicator/" not in str(row.get("official_url") or ""):
                failures.append(f"{label}: WGI official URL missing")
            if "Worldwide Governance Indicators" not in str(row.get("source_note") or ""):
                failures.append(f"{label}: WGI source note missing")
        if str(row.get("lineage_type") or "") == "derived_component" and code != MODELLED_CODE:
            failures.append(f"{label}: derived row exposes non-derived code")
        if index == 1 and not isinstance(row, dict):
            failures.append("lineage rows must be objects")
    if failures:
        raise SystemExit("branch factor source lineage validation failed:\n" + "\n".join(failures[:120]))
    print("branch factor source lineage validation passed")


if __name__ == "__main__":
    main()
