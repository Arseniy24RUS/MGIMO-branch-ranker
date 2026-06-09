#!/usr/bin/env python3
"""Validate the public branch indicator dictionary v3.6 contract."""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "docs/data/branch_factor_indicator_dictionary_v3.json"
CSV_PATH = ROOT / "docs/data/branch_factor_indicator_dictionary_v3.csv"
FACTORS = {"I_MARKET", "I_PROGRAM", "I_RUSCOMP", "I_ECO", "I_FIN", "I_FEAS", "I_HRSTRAT"}
REQUIRED = {
    "factor_key",
    "input_key",
    "official_indicator_code",
    "official_indicator_name_ru",
    "source_name",
    "year",
    "unit",
    "normalization_method",
    "observation_status",
    "within_factor_weight",
    "scoring_role",
}


def term(*parts: str) -> str:
    return "".join(parts)


def main() -> None:
    failures: list[str] = []
    if not JSON_PATH.exists():
        failures.append("branch dictionary JSON missing")
    if not CSV_PATH.exists():
        failures.append("branch dictionary CSV missing")
    if failures:
        raise SystemExit("; ".join(failures))

    rows = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        csv_rows = list(csv.DictReader(f))

    if len(rows) != len(csv_rows):
        failures.append(f"CSV/JSON row count mismatch: {len(csv_rows)} != {len(rows)}")
    factors = {row.get("factor_key") for row in rows}
    if factors != FACTORS:
        failures.append(f"factor set mismatch: {sorted(factors)}")

    for index, row in enumerate(rows, 1):
        missing = [key for key in REQUIRED if key not in row]
        if missing:
            failures.append(f"row {index} missing {missing}")
            continue
        code = str(row.get("official_indicator_code") or "")
        input_key = str(row.get("input_key") or "")
        if not code:
            failures.append(f"{input_key}: official_indicator_code empty")
        if code.startswith("I_") or ".".join([str(row.get("factor_key")), input_key]) == code:
            failures.append(f"{input_key}: internal pseudo-code exposed as official code")
        serialized = json.dumps(row, ensure_ascii=False)
        if term("17", "-24") in serialized or term("youth", "17_24") in serialized:
            failures.append(f"{input_key}: obsolete youth cohort token remains")
        role = str(row.get("scoring_role") or "")
        weight = float(row.get("within_factor_weight") or 0)
        if weight != 0 or "direct_factor_formula_component" in role:
            for key in ("source_name", "year", "unit", "normalization_method", "observation_status"):
                if row.get(key) in (None, ""):
                    failures.append(f"{input_key}: direct evidence field {key} empty")
        if code == "not_applicable_modelled_component" and not row.get("notes"):
            failures.append(f"{input_key}: modelled component lacks notes")

    if failures:
        raise SystemExit("branch indicator dictionary validation failed:\n" + "\n".join(failures[:80]))
    print("branch indicator dictionary validation passed")


if __name__ == "__main__":
    main()
