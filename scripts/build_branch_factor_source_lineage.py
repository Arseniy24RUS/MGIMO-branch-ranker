#!/usr/bin/env python3
"""Build country-factor source lineage rows for the branch methodology UI."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FACTOR_INPUTS = ROOT / "docs/data/factor_inputs_long.json"
DICTIONARY = ROOT / "docs/data/branch_factor_indicator_dictionary_v3.json"
OUT_JSON = ROOT / "docs/data/branch_factor_source_lineage.json"
OUT_CSV = ROOT / "docs/data/branch_factor_source_lineage.csv"
SOURCE_REGISTRY = ROOT / "data/reference/source_registry.csv"
MANIFESTS = [
    ROOT / "docs/data/model_outputs/current/source_manifest.csv",
    ROOT / "data/platform_snapshot/source_manifest.csv",
]

MODELLED_CODE = "not_applicable_modelled_component"

CODE_ALIASES = {
    "NY.GDP.PCAP.PP.CD": "NY.GDP.PCAP.PP.KD",
    "PA.NUS.PPPC.RF": "PA.NUS.GDP.PLI",
    "UN_WPP2024.POP.TOTAL.BOTH_SEXES": "UN_WPP2024.PopulationBySingleAgeSex.Medium",
    "UN_WPP2024.POP.15_24.BOTH_SEXES": "UN_WPP2024.PopulationBySingleAgeSex.Medium",
}

REFERENCE_SOURCES = {
    "MGIMO_PARTNER_UNIVERSITIES.COUNT": {
        "provider": "MGIMO",
        "official_url": "https://mgimo.ru/about/structure/int/docs/partner-universities/",
        "raw_file": "data/reference/mgimo_partner_universities.csv",
        "source_note": "MGIMO partner universities country table",
    },
    "MGIMO_BRANCH_PRESENCE.FLAG": {
        "provider": "MGIMO",
        "official_url": "https://mgimo.ru/about/",
        "raw_file": "data/reference/mgimo_existing_presence.csv",
        "source_note": "MGIMO country presence reference table",
    },
    "MGIMO_PIPELINE_STATUS.FLAG": {
        "provider": "MGIMO",
        "official_url": "https://mgimo.ru/about/",
        "raw_file": "data/reference/mgimo_existing_presence.csv",
        "source_note": "MGIMO country presence reference table",
    },
    "RU_GOV_ORDER_430R.UNFRIENDLY_COUNTRY_FLAG": {
        "provider": "Government of the Russian Federation",
        "official_url": "https://www.alta.ru/tamdoc/22rs0430/",
        "raw_file": "data/reference/unfriendly_countries_platform_2026.csv",
        "source_note": "Government Order No. 430-r country table",
    },
    "ISO3166.RUS.DOMESTIC_FLAG": {
        "provider": "ISO 3166 / project country boundary reference",
        "official_url": "https://www.iso.org/iso-3166-country-codes.html",
        "raw_file": "docs/data/world_admin_boundaries_ru_claimed_update_2026.geojson",
        "source_note": "ISO country code and dashboard boundary reference",
    },
    "ISO3166.SPECIAL_TERRITORY_FLAG": {
        "provider": "ISO 3166 / project country boundary reference",
        "official_url": "https://www.iso.org/iso-3166-country-codes.html",
        "raw_file": "docs/data/world_admin_boundaries_ru_claimed_update_2026.geojson",
        "source_note": "ISO country code and dashboard boundary reference",
    },
}

REGISTRY_BY_SOURCE_KEY = {
    "un_wpp2024_population_by_single_age_sex": "un_wpp2024_population_by_single_age_sex",
    "world_bank_indicators_long": "world_bank_indicators",
    "world_bank_wgi_long": "world_bank_indicators",
    "mgimo_presence": "mgimo_presence",
    "live_merged_features": "platform_snapshot_world_bank_panel",
}

FIELDNAMES = [
    "iso3",
    "country",
    "factor_key",
    "factor_group",
    "input_key",
    "lineage_type",
    "official_indicator_code",
    "official_indicator_name_en",
    "official_indicator_name_ru",
    "provider",
    "source_name",
    "source_key",
    "source_note",
    "official_url",
    "raw_file",
    "source_manifest_code",
    "latest_observed_year_in_run",
    "year",
    "unit",
    "raw_value",
    "normalized_value",
    "normalization_method",
    "within_factor_weight",
    "factor_weight",
    "scoring_role",
    "weight_note",
    "observation_status",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def clean(value: Any) -> Any:
    if value == "":
        return None
    return value


def registry_rows() -> dict[str, dict[str, str]]:
    return {row["source_id"]: row for row in read_csv(SOURCE_REGISTRY) if row.get("source_id")}


def manifest_rows() -> dict[str, dict[str, str]]:
    indexed: dict[str, dict[str, str]] = {}
    for path in MANIFESTS:
        for row in read_csv(path):
            code = row.get("indicator_code")
            if code and code not in indexed:
                indexed[code] = row
    return indexed


def build() -> list[dict[str, Any]]:
    factor_rows = json.loads(FACTOR_INPUTS.read_text(encoding="utf-8"))
    dictionary_rows = json.loads(DICTIONARY.read_text(encoding="utf-8"))
    dictionary = {
        (row.get("factor_key"), row.get("input_key")): row
        for row in dictionary_rows
        if row.get("factor_key") and row.get("input_key")
    }
    manifests = manifest_rows()
    registry = registry_rows()
    out: list[dict[str, Any]] = []
    for row in factor_rows:
        factor_key = row.get("factor_key")
        input_key = row.get("input_key")
        meta = dictionary.get((factor_key, input_key), {})
        code = meta.get("official_indicator_code") or input_key
        manifest_code = CODE_ALIASES.get(code, code)
        manifest = manifests.get(manifest_code, {})
        reference = REFERENCE_SOURCES.get(code, {})
        registry_key = REGISTRY_BY_SOURCE_KEY.get(str(row.get("source_key") or ""))
        registry_row = registry.get(registry_key, {})
        is_derived = code == MODELLED_CODE
        provider = (
            manifest.get("provider")
            or reference.get("provider")
            or registry_row.get("name")
            or meta.get("source_name")
            or row.get("source_key")
        )
        source_url = (
            manifest.get("official_url")
            or reference.get("official_url")
            or registry_row.get("api_or_page_url")
            or ""
        )
        raw_file = manifest.get("raw_file") or reference.get("raw_file") or registry_row.get("api_or_page_url") or ""
        source_note = (
            manifest.get("source_note")
            or reference.get("source_note")
            or registry_row.get("notes")
            or meta.get("notes")
            or ""
        )
        out.append({
            "iso3": row.get("iso3"),
            "country": row.get("country"),
            "factor_key": factor_key,
            "factor_group": row.get("factor_group"),
            "input_key": input_key,
            "lineage_type": "derived_component" if is_derived else "official_indicator",
            "official_indicator_code": code,
            "official_indicator_name_en": manifest.get("indicator_label") or meta.get("official_indicator_name_en") or input_key,
            "official_indicator_name_ru": meta.get("official_indicator_name_ru") or input_key,
            "provider": provider,
            "source_name": meta.get("source_name") or provider,
            "source_key": row.get("source_key"),
            "source_note": source_note,
            "official_url": source_url,
            "raw_file": raw_file,
            "source_manifest_code": manifest.get("indicator_code") or manifest_code if manifest else "",
            "latest_observed_year_in_run": manifest.get("latest_observed_year_in_run") or "",
            "year": row.get("year"),
            "unit": meta.get("unit") or "",
            "raw_value": row.get("raw_value"),
            "normalized_value": row.get("normalized_value"),
            "normalization_method": row.get("normalization_method"),
            "within_factor_weight": row.get("input_weight"),
            "factor_weight": row.get("factor_weight"),
            "scoring_role": row.get("scoring_role"),
            "weight_note": row.get("weight_note"),
            "observation_status": row.get("observation_status"),
        })
    return [{key: clean(item.get(key)) for key in FIELDNAMES} for item in out]


def main() -> int:
    rows = build()
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    print(f"saved {OUT_JSON}")
    print(f"saved {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
