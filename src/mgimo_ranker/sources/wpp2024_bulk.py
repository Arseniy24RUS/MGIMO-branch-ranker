from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

WPP_SOURCE_KEY = "un_wpp2024_population_by_single_age_sex"
WPP_SOURCE_NAME = "UN World Population Prospects 2024"
WPP_SERIES_SOURCE = "UN WPP 2024 bulk official estimates 1950-2023"
WPP_FORECAST_SOURCE = "UN WPP 2024 bulk Medium official projection 2024-2100"
WPP_VARIANT = "Medium"

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WPP_RAW_DIR = PROJECT_ROOT / "data" / "demography" / "raw" / "wpp2024"
DEFAULT_WPP_HISTORICAL = DEFAULT_WPP_RAW_DIR / "WPP2024_PopulationBySingleAgeSex_Medium_1950-2023.csv.gz"
DEFAULT_WPP_PROJECTION = DEFAULT_WPP_RAW_DIR / "WPP2024_PopulationBySingleAgeSex_Medium_2024-2100.csv.gz"
WPP_MANIFEST_PATH = PROJECT_ROOT / "data" / "demography" / "un_wpp2024_official_manifest.json"

ACTUAL_YEARS = list(range(2000, 2024))
FORECAST_YEARS = list(range(2024, 2051))
HIGHLIGHT_YEARS = [2026, 2035, 2050]
PYRAMID_ACTUAL_YEARS = [2023]
PYRAMID_FORECAST_YEARS = [2024, 2026, 2035, 2050]

AGE_SEX_BANDS: list[dict[str, Any]] = [
    {"code": "0004", "label": "0-4", "start": 0, "end": 4},
    {"code": "0509", "label": "5-9", "start": 5, "end": 9},
    {"code": "1014", "label": "10-14", "start": 10, "end": 14},
    {"code": "1519", "label": "15-19", "start": 15, "end": 19},
    {"code": "2024", "label": "20-24", "start": 20, "end": 24},
    {"code": "2529", "label": "25-29", "start": 25, "end": 29},
    {"code": "3034", "label": "30-34", "start": 30, "end": 34},
    {"code": "3539", "label": "35-39", "start": 35, "end": 39},
    {"code": "4044", "label": "40-44", "start": 40, "end": 44},
    {"code": "4549", "label": "45-49", "start": 45, "end": 49},
    {"code": "5054", "label": "50-54", "start": 50, "end": 54},
    {"code": "5559", "label": "55-59", "start": 55, "end": 59},
    {"code": "6064", "label": "60-64", "start": 60, "end": 64},
    {"code": "6569", "label": "65-69", "start": 65, "end": 69},
    {"code": "7074", "label": "70-74", "start": 70, "end": 74},
    {"code": "7579", "label": "75-79", "start": 75, "end": 79},
    {"code": "80UP", "label": "80+", "start": 80, "end": None},
]
HIGHLIGHT_AGE_BANDS = ["15-19", "20-24"]

# World Bank uses CHI for Channel Islands, while WPP publishes the official rows
# for the constituent Country/Area records Guernsey and Jersey.
COMPOSITE_ISO_COMPONENTS = {"CHI": ["GGY", "JEY"]}
COMPOSITE_ISO_NAMES = {"CHI": "Channel Islands"}

WPP_USECOLS = [
    "ISO3_code",
    "Location",
    "Variant",
    "Time",
    "AgeGrpStart",
    "PopMale",
    "PopFemale",
    "PopTotal",
]


def default_wpp_paths() -> tuple[Path, Path]:
    return DEFAULT_WPP_HISTORICAL, DEFAULT_WPP_PROJECTION


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _manifest_file_spec(role: str) -> dict[str, Any]:
    if not WPP_MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Missing required UN WPP 2024 manifest: {WPP_MANIFEST_PATH}")
    manifest = json.loads(WPP_MANIFEST_PATH.read_text(encoding="utf-8"))
    item = (manifest.get("files") or {}).get(role)
    if not isinstance(item, dict):
        raise ValueError(f"UN WPP 2024 manifest lacks file spec for {role}")
    return item


def _validate_manifest_file(role: str, path: Path) -> None:
    item = _manifest_file_spec(role)
    expected_path = (PROJECT_ROOT / str(item.get("local_path"))).resolve()
    actual_path = path.resolve()
    if actual_path != expected_path:
        raise ValueError(f"UN WPP 2024 {role} path does not match pinned manifest: {actual_path} != {expected_path}")
    expected_bytes = int(item.get("bytes"))
    actual_bytes = actual_path.stat().st_size
    if actual_bytes != expected_bytes:
        raise ValueError(f"UN WPP 2024 {role} byte size changed: {actual_bytes} != {expected_bytes}")
    expected_hash = str(item.get("sha256") or "").lower()
    actual_hash = _sha256_file(actual_path)
    if actual_hash != expected_hash:
        raise ValueError(f"UN WPP 2024 {role} sha256 changed: {actual_hash} != {expected_hash}")


def resolve_wpp_paths(
    historical_path: str | Path | None = None,
    projection_path: str | Path | None = None,
) -> tuple[Path, Path]:
    historical = Path(historical_path) if historical_path else DEFAULT_WPP_HISTORICAL
    projection = Path(projection_path) if projection_path else DEFAULT_WPP_PROJECTION
    if not historical.is_absolute():
        historical = PROJECT_ROOT / historical
    if not projection.is_absolute():
        projection = PROJECT_ROOT / projection
    missing = [str(path) for path in (historical, projection) if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required UN WPP 2024 bulk file(s): {missing}")
    _validate_manifest_file("historical", historical)
    _validate_manifest_file("projection", projection)
    return historical, projection


def _required_iso_set(iso_filter: Iterable[str] | None) -> set[str] | None:
    if iso_filter is None:
        return None
    requested = {str(iso).upper().strip() for iso in iso_filter if str(iso).strip()}
    expanded = set(requested)
    for iso3 in requested:
        expanded.update(COMPOSITE_ISO_COMPONENTS.get(iso3, []))
    return expanded


def _read_one_wpp_file(
    path: Path,
    iso_filter: Iterable[str] | None,
    start_year: int,
    end_year: int,
    observation_status: str,
    chunksize: int,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    keep_iso = _required_iso_set(iso_filter)
    for chunk in pd.read_csv(
        path,
        compression="infer",
        usecols=WPP_USECOLS,
        dtype={"ISO3_code": "string", "Location": "string", "Variant": "string"},
        chunksize=chunksize,
    ):
        chunk["year"] = pd.to_numeric(chunk["Time"], errors="coerce")
        chunk = chunk[
            chunk["Variant"].eq(WPP_VARIANT)
            & chunk["year"].between(start_year, end_year)
            & chunk["ISO3_code"].notna()
        ].copy()
        if chunk.empty:
            continue
        chunk["iso3"] = chunk["ISO3_code"].astype(str).str.upper().str.strip()
        chunk = chunk[chunk["iso3"].str.len().eq(3)]
        if keep_iso is not None:
            chunk = chunk[chunk["iso3"].isin(keep_iso)]
        if chunk.empty:
            continue
        chunk["age_start"] = pd.to_numeric(chunk["AgeGrpStart"], errors="coerce")
        chunk = chunk.dropna(subset=["age_start", "year"])
        if chunk.empty:
            continue
        out = pd.DataFrame(
            {
                "iso3": chunk["iso3"].astype(str),
                "country": chunk["Location"].astype(str),
                "year": chunk["year"].astype(int),
                "age_start": chunk["age_start"].astype(int),
                "male": pd.to_numeric(chunk["PopMale"], errors="coerce") * 1000.0,
                "female": pd.to_numeric(chunk["PopFemale"], errors="coerce") * 1000.0,
                "total": pd.to_numeric(chunk["PopTotal"], errors="coerce") * 1000.0,
            }
        )
        out["observation_status"] = observation_status
        frames.append(out)
    if not frames:
        return pd.DataFrame(columns=["iso3", "country", "year", "age_start", "male", "female", "total", "observation_status"])
    return pd.concat(frames, ignore_index=True)


def _append_composite_iso(panel: pd.DataFrame, requested_iso: set[str] | None) -> pd.DataFrame:
    if panel.empty or requested_iso is None:
        return panel
    additions: list[pd.DataFrame] = []
    for composite, components in COMPOSITE_ISO_COMPONENTS.items():
        if composite not in requested_iso:
            continue
        part = panel[panel["iso3"].isin(components)].copy()
        if part.empty:
            continue
        grouped = (
            part.groupby(["year", "age_start", "observation_status"], as_index=False)[["male", "female", "total"]]
            .sum(min_count=1)
            .assign(iso3=composite, country=COMPOSITE_ISO_NAMES.get(composite, composite))
        )
        additions.append(grouped[["iso3", "country", "year", "age_start", "male", "female", "total", "observation_status"]])
    if not additions:
        return panel
    return pd.concat([panel, *additions], ignore_index=True)


def load_wpp_age_sex_panel(
    historical_path: str | Path | None = None,
    projection_path: str | Path | None = None,
    iso_filter: Iterable[str] | None = None,
    start_year: int = 2000,
    end_year: int = 2050,
    chunksize: int = 500_000,
) -> pd.DataFrame:
    historical, projection = resolve_wpp_paths(historical_path, projection_path)
    requested_iso = {str(iso).upper().strip() for iso in iso_filter if str(iso).strip()} if iso_filter is not None else None
    frames = [
        _read_one_wpp_file(historical, iso_filter, start_year, min(2023, end_year), "official_estimate", chunksize),
        _read_one_wpp_file(projection, iso_filter, max(2024, start_year), end_year, "official_projection", chunksize),
    ]
    panel = pd.concat([frame for frame in frames if not frame.empty], ignore_index=True)
    panel = _append_composite_iso(panel, requested_iso)
    if requested_iso is not None:
        panel = panel[panel["iso3"].isin(requested_iso)].copy()
    if panel.empty:
        raise ValueError("UN WPP 2024 bulk loader produced no country-level age-sex rows.")
    return panel.sort_values(["iso3", "year", "age_start"]).reset_index(drop=True)


def _aggregate_years(panel: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        panel.groupby(["iso3", "country", "year", "observation_status"], as_index=False)
        .agg(
            population_total=("total", "sum"),
            pop_15_24=("total", lambda s: float(s[panel.loc[s.index, "age_start"].between(15, 24)].sum())),
            pop_25_29=("total", lambda s: float(s[panel.loc[s.index, "age_start"].between(25, 29)].sum())),
        )
    )
    grouped["student_pool"] = grouped["pop_15_24"] + 0.45 * grouped["pop_25_29"]
    return grouped


def _require_year_coverage(aggregated: pd.DataFrame, iso_keep: Iterable[str], years: Iterable[int]) -> None:
    expected_years = {int(year) for year in years}
    missing: dict[str, list[int]] = {}
    for iso3 in sorted({str(iso).upper().strip() for iso in iso_keep if str(iso).strip()}):
        have = set(pd.to_numeric(aggregated.loc[aggregated["iso3"].eq(iso3), "year"], errors="coerce").dropna().astype(int))
        diff = sorted(expected_years - have)
        if diff:
            missing[iso3] = diff
    if missing:
        sample = {iso: years[:8] for iso, years in list(missing.items())[:20]}
        raise ValueError(f"UN WPP 2024 bulk coverage missing for ISO/year combinations: {sample}")


def build_demographic_features_from_panel(
    panel: pd.DataFrame,
    target_years: Iterable[int] = (2026, 2035, 2050),
    base_year: int = 2026,
) -> pd.DataFrame:
    aggregated = _aggregate_years(panel)
    target_years = [int(year) for year in target_years]
    rows: list[dict[str, Any]] = []
    for iso3, group in aggregated.groupby("iso3"):
        group = group.sort_values("year")
        current_candidates = group[group["year"].le(2024)]
        if current_candidates.empty:
            continue
        current = current_candidates.iloc[-1]
        item: dict[str, Any] = {
            "iso3": iso3,
            "population_total_current": float(current["population_total"]),
            "population_total_current_year": int(current["year"]),
            "pop_15_24_current": float(current["pop_15_24"]),
            "pop_15_24_current_year": int(current["year"]),
            "student_pool_current": float(current["student_pool"]),
            "student_pool_current_year": int(current["year"]),
            "latest_observation_lag_years": int(base_year) - int(current["year"]),
            "demography_source": WPP_SOURCE_KEY,
            "demography_source_name": WPP_SOURCE_NAME,
        }
        for year in target_years:
            row = group[group["year"].eq(year)]
            if row.empty:
                item[f"population_total_{year}"] = np.nan
                item[f"pop_15_24_{year}"] = np.nan
                item[f"student_pool_{year}"] = np.nan
                continue
            row0 = row.iloc[0]
            item[f"population_total_{year}"] = float(row0["population_total"])
            item[f"pop_15_24_{year}"] = float(row0["pop_15_24"])
            item[f"student_pool_{year}"] = float(row0["student_pool"])
        if {f"student_pool_{target_years[0]}", f"student_pool_{target_years[1]}"}.issubset(item):
            start = item.get(f"student_pool_{target_years[0]}")
            end = item.get(f"student_pool_{target_years[1]}")
            item[f"student_pool_growth_{target_years[0]}_{target_years[1]}_pct"] = (
                (end / start - 1.0) * 100.0 if start and end and np.isfinite(start) and np.isfinite(end) else np.nan
            )
        if len(target_years) >= 3:
            start = item.get(f"student_pool_{target_years[0]}")
            end = item.get(f"student_pool_{target_years[2]}")
            item[f"student_pool_growth_{target_years[0]}_{target_years[2]}_pct"] = (
                (end / start - 1.0) * 100.0 if start and end and np.isfinite(start) and np.isfinite(end) else np.nan
            )
        rows.append(item)
    return pd.DataFrame(rows).sort_values("iso3").reset_index(drop=True)


def build_demography_series_from_panel(
    panel: pd.DataFrame,
    highlight_years: Iterable[int] = HIGHLIGHT_YEARS,
) -> dict[str, Any]:
    aggregated = _aggregate_years(panel)
    result: dict[str, Any] = {}
    for iso3, group in aggregated.groupby("iso3"):
        group = group.sort_values("year")
        actual = group[group["year"].isin(ACTUAL_YEARS)]
        forecast = group[group["year"].isin(FORECAST_YEARS)]

        def row_to_public(row: pd.Series) -> dict[str, Any]:
            return {
                "year": int(row["year"]),
                "population_total": float(row["population_total"]),
                "pop_15_24": float(row["pop_15_24"]),
                "student_pool": float(row["student_pool"]),
                "source_key": WPP_SOURCE_KEY,
                "source_name": WPP_SOURCE_NAME,
                "observation_status": str(row["observation_status"]),
            }

        result[iso3] = {
            "actual": [row_to_public(row) for _, row in actual.iterrows()],
            "forecast": [row_to_public(row) for _, row in forecast.iterrows()],
            "source": WPP_SERIES_SOURCE,
            "forecastSource": WPP_FORECAST_SOURCE,
            "sourceKey": WPP_SOURCE_KEY,
            "highlightYears": [int(year) for year in highlight_years],
        }
    return result


def _band_values(group: pd.DataFrame, year: int, sex_col: str) -> list[float]:
    year_group = group[group["year"].eq(year)]
    values: list[float] = []
    for band in AGE_SEX_BANDS:
        start = int(band["start"])
        end = band["end"]
        if end is None:
            mask = year_group["age_start"].ge(start)
        else:
            mask = year_group["age_start"].between(start, int(end))
        values.append(float(pd.to_numeric(year_group.loc[mask, sex_col], errors="coerce").sum()))
    return values


def build_age_sex_pyramid_from_panel(panel: pd.DataFrame) -> dict[str, Any]:
    result: dict[str, Any] = {}
    labels = [str(band["label"]) for band in AGE_SEX_BANDS]
    for iso3, group in panel.groupby("iso3"):
        years = sorted(pd.to_numeric(group["year"], errors="coerce").dropna().astype(int).unique())
        actual_years = [year for year in PYRAMID_ACTUAL_YEARS if year in years]
        forecast_years = [year for year in PYRAMID_FORECAST_YEARS if year in years]
        statuses = {
            str(int(row["year"])): str(row["observation_status"])
            for _, row in group[["year", "observation_status"]].drop_duplicates().iterrows()
            if int(row["year"]) in set(actual_years + forecast_years)
        }
        result[iso3] = {
            "schema": "matrix_v2_un_wpp2024_single_age_sex",
            "ageBands": labels,
            "actualYears": actual_years,
            "actualMale": [_band_values(group, year, "male") for year in actual_years],
            "actualFemale": [_band_values(group, year, "female") for year in actual_years],
            "forecastYears": forecast_years,
            "forecastMale": [_band_values(group, year, "male") for year in forecast_years],
            "forecastFemale": [_band_values(group, year, "female") for year in forecast_years],
            "availableYears": actual_years + forecast_years,
            "yearStatuses": statuses,
            "highlightAgeBands": HIGHLIGHT_AGE_BANDS,
            "source": WPP_SERIES_SOURCE,
            "forecastSource": WPP_FORECAST_SOURCE,
            "sourceKey": WPP_SOURCE_KEY,
            "sourceName": WPP_SOURCE_NAME,
            "dataStatus": "available",
            "missingAgeBands": [],
        }
    return result


def load_wpp_demography_payload_blocks(
    historical_path: str | Path | None = None,
    projection_path: str | Path | None = None,
    iso_filter: Iterable[str] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    panel = load_wpp_age_sex_panel(historical_path, projection_path, iso_filter=iso_filter)
    requested_iso = {str(iso).upper().strip() for iso in iso_filter if str(iso).strip()} if iso_filter is not None else set(panel["iso3"])
    aggregated = _aggregate_years(panel)
    _require_year_coverage(aggregated, requested_iso, ACTUAL_YEARS + FORECAST_YEARS)
    series = build_demography_series_from_panel(panel)
    pyramid = build_age_sex_pyramid_from_panel(panel)
    return (
        {iso3: series[iso3] for iso3 in sorted(requested_iso)},
        {iso3: pyramid[iso3] for iso3 in sorted(requested_iso)},
        {
            "source": WPP_SOURCE_KEY,
            "sourceName": WPP_SOURCE_NAME,
            "variant": WPP_VARIANT,
            "manifestPath": str(WPP_MANIFEST_PATH.relative_to(PROJECT_ROOT)).replace("\\", "/"),
            "countriesWithSeries": len(requested_iso),
            "countriesWithPyramid": len(requested_iso),
            "actualYears": ACTUAL_YEARS,
            "forecastYears": FORECAST_YEARS,
            "pyramidActualYears": PYRAMID_ACTUAL_YEARS,
            "pyramidForecastYears": PYRAMID_FORECAST_YEARS,
            "highlightYears": HIGHLIGHT_YEARS,
            "currentReferenceYear": 2024,
            "currentReferenceStatus": "official_projection",
        },
    )


def load_wpp_demographic_features(
    historical_path: str | Path | None = None,
    projection_path: str | Path | None = None,
    iso_filter: Iterable[str] | None = None,
    target_years: Iterable[int] = (2026, 2035, 2050),
    base_year: int = 2026,
) -> pd.DataFrame:
    panel = load_wpp_age_sex_panel(historical_path, projection_path, iso_filter=iso_filter)
    requested_iso = {str(iso).upper().strip() for iso in iso_filter if str(iso).strip()} if iso_filter is not None else set(panel["iso3"])
    aggregated = _aggregate_years(panel)
    _require_year_coverage(aggregated, requested_iso, [2024, *[int(year) for year in target_years]])
    features = build_demographic_features_from_panel(panel, target_years=target_years, base_year=base_year)
    missing = sorted(requested_iso - set(features["iso3"].astype(str)))
    if missing:
        raise ValueError(f"UN WPP 2024 demographic features missing ISO3: {missing}")
    return features[features["iso3"].isin(requested_iso)].sort_values("iso3").reset_index(drop=True)
