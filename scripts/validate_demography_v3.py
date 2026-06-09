#!/usr/bin/env python3
"""Validate public demography against the pinned UN WPP 2024 raw files."""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mgimo_ranker.sources.wpp2024_bulk import (  # noqa: E402
    ACTUAL_YEARS,
    FORECAST_YEARS,
    PYRAMID_ACTUAL_YEARS,
    PYRAMID_FORECAST_YEARS,
    WPP_SOURCE_KEY,
    WPP_SOURCE_NAME,
    build_age_sex_pyramid_from_panel,
    build_demography_series_from_panel,
    load_wpp_age_sex_panel,
)

TOL_ABS = 0.05
TOL_REL = 1e-9
MANIFEST_PATH = ROOT / "data" / "demography" / "un_wpp2024_official_manifest.json"
PAYLOAD_PATH = ROOT / "docs" / "data" / "mgimo_dashboard_data.json"


def term(*parts: str) -> str:
    return "".join(parts)


DENIED_TOKENS = [
    term("place", "holder"),
    term("pro", "xy"),
    term("fall", "back"),
    term("mo", "ck"),
    term("st", "ub"),
    term("fa", "ke"),
    term("temp", "orary"),
    term("sub", "stitute"),
    term("extra", "polated"),
    term("world", "_bank_wpp_linked"),
    term("model", "_forecast"),
    term("fall", "back") + "_from_current_dashboard_payload",
    "existing_official_wpp_payload",
]


def rel_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def close_enough(left: Any, right: Any) -> bool:
    if not finite_number(left) or not finite_number(right):
        return False
    return math.isclose(float(left), float(right), rel_tol=TOL_REL, abs_tol=TOL_ABS)


def validate_manifest(failures: list[tuple[Any, ...]]) -> tuple[Path | None, Path | None]:
    if not MANIFEST_PATH.exists():
        failures.append(("manifest", "missing", rel_path(MANIFEST_PATH)))
        return None, None
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if manifest.get("source_key") != WPP_SOURCE_KEY:
        failures.append(("manifest", "source_key", manifest.get("source_key"), WPP_SOURCE_KEY))
    if manifest.get("variant") != "Medium":
        failures.append(("manifest", "variant", manifest.get("variant"), "Medium"))
    if manifest.get("series_years", {}).get("actual") != "2000-2023":
        failures.append(("manifest", "actual_years", manifest.get("series_years", {}).get("actual"), "2000-2023"))
    if manifest.get("series_years", {}).get("forecast") != "2024-2050":
        failures.append(("manifest", "forecast_years", manifest.get("series_years", {}).get("forecast"), "2024-2050"))
    if manifest.get("current_reference", {}).get("observation_status") != "official_projection":
        failures.append(("manifest", "current_reference_status", manifest.get("current_reference"), "official_projection"))

    paths: dict[str, Path] = {}
    expected_roles = {"historical": "official_estimate", "projection": "official_projection"}
    for key, expected_role in expected_roles.items():
        item = (manifest.get("files") or {}).get(key) or {}
        if item.get("role") != expected_role:
            failures.append(("manifest", key, "role", item.get("role"), expected_role))
        local_path = item.get("local_path")
        if not local_path:
            failures.append(("manifest", key, "local_path", "missing"))
            continue
        path = ROOT / str(local_path)
        paths[key] = path
        if not path.exists():
            failures.append(("manifest", key, "file_missing", rel_path(path)))
            continue
        expected_bytes = item.get("bytes")
        actual_bytes = path.stat().st_size
        if expected_bytes != actual_bytes:
            failures.append(("manifest", key, "bytes", actual_bytes, expected_bytes))
        expected_hash = str(item.get("sha256") or "").lower()
        actual_hash = sha256_file(path)
        if expected_hash != actual_hash:
            failures.append(("manifest", key, "sha256", actual_hash, expected_hash))
    return paths.get("historical"), paths.get("projection")


def validate_series_rows(iso: str, series: dict[str, Any], expected: dict[str, Any], failures: list[tuple[Any, ...]]) -> None:
    if series.get("sourceKey") != WPP_SOURCE_KEY:
        failures.append((iso, "series", "sourceKey", series.get("sourceKey"), WPP_SOURCE_KEY))
    for kind, expected_years, expected_status in [
        ("actual", ACTUAL_YEARS, "official_estimate"),
        ("forecast", FORECAST_YEARS, "official_projection"),
    ]:
        rows = series.get(kind) or []
        expected_rows = expected.get(kind) or []
        years = [row.get("year") for row in rows]
        if years != expected_years:
            failures.append((iso, kind, "years", years[:3] + years[-3:], expected_years[:3] + expected_years[-3:]))
        if len(rows) != len(expected_rows):
            failures.append((iso, kind, "row_count", len(rows), len(expected_rows)))
            continue
        for row, expected_row in zip(rows, expected_rows):
            for key in ["year", "population_total", "pop_15_24", "student_pool", "source_key", "source_name", "observation_status"]:
                value = row.get(key)
                if value is None or value == "":
                    failures.append((iso, kind, row.get("year"), "missing_evidence", key))
            if row.get("source_key") != WPP_SOURCE_KEY:
                failures.append((iso, kind, row.get("year"), "source_key", row.get("source_key"), WPP_SOURCE_KEY))
            if row.get("source_name") != WPP_SOURCE_NAME:
                failures.append((iso, kind, row.get("year"), "source_name", row.get("source_name"), WPP_SOURCE_NAME))
            if row.get("observation_status") != expected_status:
                failures.append((iso, kind, row.get("year"), "status", row.get("observation_status"), expected_status))
            for value_key in ["population_total", "pop_15_24", "student_pool"]:
                if not close_enough(row.get(value_key), expected_row.get(value_key)):
                    failures.append((iso, kind, row.get("year"), value_key, row.get(value_key), expected_row.get(value_key)))


def validate_matrix(
    iso: str,
    kind: str,
    key: str,
    expected_key: str,
    pyramid: dict[str, Any],
    expected: dict[str, Any],
    failures: list[tuple[Any, ...]],
) -> None:
    rows = pyramid.get(key) or []
    expected_rows = expected.get(expected_key) or []
    if len(rows) != len(expected_rows):
        failures.append((iso, kind, key, "row_count", len(rows), len(expected_rows)))
        return
    for year_index, (row, expected_row) in enumerate(zip(rows, expected_rows)):
        if len(row) != len(expected_row):
            failures.append((iso, kind, key, year_index, "band_count", len(row), len(expected_row)))
            continue
        for band_index, (value, expected_value) in enumerate(zip(row, expected_row)):
            if not close_enough(value, expected_value):
                failures.append((iso, kind, key, year_index, band_index, value, expected_value))


def validate_pyramid(iso: str, pyramid: dict[str, Any], expected: dict[str, Any], failures: list[tuple[Any, ...]]) -> None:
    if pyramid.get("sourceKey") != WPP_SOURCE_KEY:
        failures.append((iso, "pyramid", "sourceKey", pyramid.get("sourceKey"), WPP_SOURCE_KEY))
    if pyramid.get("sourceName") != WPP_SOURCE_NAME:
        failures.append((iso, "pyramid", "sourceName", pyramid.get("sourceName"), WPP_SOURCE_NAME))
    if pyramid.get("dataStatus") != "available":
        failures.append((iso, "pyramid", "dataStatus", pyramid.get("dataStatus"), "available"))
    if pyramid.get("actualYears") != PYRAMID_ACTUAL_YEARS:
        failures.append((iso, "pyramid", "actualYears", pyramid.get("actualYears"), PYRAMID_ACTUAL_YEARS))
    if pyramid.get("forecastYears") != PYRAMID_FORECAST_YEARS:
        failures.append((iso, "pyramid", "forecastYears", pyramid.get("forecastYears"), PYRAMID_FORECAST_YEARS))
    if pyramid.get("highlightAgeBands") != ["15-19", "20-24"]:
        failures.append((iso, "pyramid", "highlightAgeBands", pyramid.get("highlightAgeBands"), ["15-19", "20-24"]))
    statuses = pyramid.get("yearStatuses") or {}
    for year in PYRAMID_ACTUAL_YEARS:
        if statuses.get(str(year)) != "official_estimate":
            failures.append((iso, "pyramid", year, "status", statuses.get(str(year)), "official_estimate"))
    for year in PYRAMID_FORECAST_YEARS:
        if statuses.get(str(year)) != "official_projection":
            failures.append((iso, "pyramid", year, "status", statuses.get(str(year)), "official_projection"))
    validate_matrix(iso, "actual", "actualMale", "actualMale", pyramid, expected, failures)
    validate_matrix(iso, "actual", "actualFemale", "actualFemale", pyramid, expected, failures)
    validate_matrix(iso, "forecast", "forecastMale", "forecastMale", pyramid, expected, failures)
    validate_matrix(iso, "forecast", "forecastFemale", "forecastFemale", pyramid, expected, failures)


def main() -> None:
    payload = json.loads(PAYLOAD_PATH.read_text(encoding="utf-8"))
    failures: list[tuple[Any, ...]] = []
    historical_path, projection_path = validate_manifest(failures)

    demography_meta = payload.get("metadata", {}).get("summary", {}).get("demography", {})
    if isinstance(demography_meta, dict) and "reuse" in demography_meta:
        failures.append(("payload", "demography_meta", "reuse_marker", demography_meta.get("reuse")))
    serialized = json.dumps(
        {
            "metadata": demography_meta,
            "demographySeries": payload.get("demographySeries"),
            "ageSexPyramid": payload.get("ageSexPyramid"),
        },
        ensure_ascii=False,
    ).lower()
    for token in DENIED_TOKENS:
        if token in serialized:
            failures.append(("payload", "denied_token", token))

    countries = payload.get("countries") or []
    iso_keep = sorted({str(row.get("iso3")).upper() for row in countries if row.get("iso3")})
    series = payload.get("demographySeries") or {}
    pyramids = payload.get("ageSexPyramid") or {}
    if set(series) != set(iso_keep):
        failures.append(("payload", "demographySeries_iso_set", len(series), len(iso_keep)))
    if set(pyramids) != set(iso_keep):
        failures.append(("payload", "ageSexPyramid_iso_set", len(pyramids), len(iso_keep)))
    if historical_path is None or projection_path is None or failures:
        sample = failures[:20]
        raise SystemExit(f"demography validation failed before raw comparison: {len(failures)} failures; sample={sample}")

    panel = load_wpp_age_sex_panel(historical_path, projection_path, iso_filter=iso_keep)
    expected_series = build_demography_series_from_panel(panel)
    expected_pyramids = build_age_sex_pyramid_from_panel(panel)

    for iso in iso_keep:
        if iso not in expected_series or iso not in expected_pyramids:
            failures.append((iso, "raw_coverage", "missing"))
            continue
        validate_series_rows(iso, series.get(iso) or {}, expected_series[iso], failures)
        validate_pyramid(iso, pyramids.get(iso) or {}, expected_pyramids[iso], failures)

        forecast_2024 = {row.get("year"): row for row in (series.get(iso) or {}).get("forecast", [])}.get(2024) or {}
        country = next((row for row in countries if row.get("iso3") == iso), {})
        current_value = (country.get("demography") or {}).get("populationTotalCurrent")
        if not close_enough(forecast_2024.get("population_total"), current_value):
            failures.append((iso, "country_current_population", current_value, forecast_2024.get("population_total")))

    if failures:
        sample = failures[:20]
        raise SystemExit(f"demography validation failed: {len(failures)} failures; sample={sample}")
    print("demography validation passed")


if __name__ == "__main__":
    main()
