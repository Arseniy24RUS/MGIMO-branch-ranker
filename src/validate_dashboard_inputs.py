from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA = DOCS / "data"


def term(*parts: str) -> str:
    return "".join(parts)

REQUIRED_MODEL_FILES = [
    "country_ranking.csv",
    "country_scores_full.csv",
    "financial_model_best.csv",
    "financial_model_full.csv",
    "program_profile_ranking.csv",
    "excluded_countries.csv",
    "in_preparation_countries.csv",
    "top20_direct_open.csv",
    "top20_recommended.csv",
]

REQUIRED_REFERENCE_FILES = [
    "mgimo_existing_presence.csv",
    "unfriendly_countries_russia_430r.csv",
    "non_sovereign_or_special_exclusions.csv",
    "mgimo_partner_universities.csv",
]

TOP_COUNTRY_FIELDS = [
    "iso3",
    "country",
    "eligible",
    "rank_eligible",
    "PRIORITY",
    "I_MARKET",
    "I_PROGRAM",
    "I_RUSCOMP",
    "I_ECO",
    "I_FIN",
    "I_FEAS",
    "I_HRSTRAT",
    "DATAQ",
    "latitude",
    "longitude",
    "addressable_market_students_2026",
]

FORBIDDEN_PAYLOAD_TERMS = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(item)
        for item in [
            term("sce", "nario"),
            term("sce", "narios"),
            term("base", "line"),
            term("soft", "_power"),
            term("comm", "ercial"),
            term("risk", "_averse"),
            term("snapshot", "Countries"),
            term("live", "_final"),
            term("final", "_snapshot"),
            "control mode",
        ]
    )
    + r")\b",
    re.IGNORECASE,
)
FORBIDDEN_PUBLIC_TERMS = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(item)
        for item in [
            term("sce", "nario"),
            term("sce", "narios"),
            term("base", "line"),
            term("soft", "_power"),
            term("comm", "ercial"),
            term("risk", "_averse"),
            term("snapshot", "Countries"),
            term("live", "_final"),
            term("final", "_snapshot"),
            "control mode",
            "top strip",
        ]
    )
    + r")\b",
    re.IGNORECASE,
)
STATUS_FORBIDDEN = re.compile(r"\b(?:pipeline|priority|recommend|recommended|excluded|direct|open|hard)\b", re.IGNORECASE)
PREPARATION_STATUS = re.compile(r"\bin[_ -]?preparation\b|\u0412 \u043f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0435", re.IGNORECASE)
ISO_FIELDS = ["iso_a3", "adm0_a3", "wb_a3", "adm0_iso", "sov_a3", "gu_a3"]
KNOWN_UNMATCHED = {"GIB"}
AGE_BANDS = [
    "0-4",
    "5-9",
    "10-14",
    "15-19",
    "20-24",
    "25-29",
    "30-34",
    "35-39",
    "40-44",
    "45-49",
    "50-54",
    "55-59",
    "60-64",
    "65-69",
    "70-74",
    "75-79",
    "80+",
]
TARGET_AGE_BANDS = {"15-19", "20-24"}


class Validation:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def read_strict_json(path: Path, validation: Validation) -> Any:
    if not path.exists():
        validation.error(f"missing required file: {path}")
        return {}
    raw = path.read_text(encoding="utf-8")
    for token in ("NaN", "Infinity", "-Infinity"):
        if token in raw:
            validation.error(f"{path}: contains non-standard JSON token {token}")
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        validation.error(f"{path}: invalid JSON: {exc}")
        return {}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_finite(value: Any) -> bool:
    if value is None or value == "":
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def boolish(value: Any) -> bool:
    return value in (0, 1, False, True, "0", "1", "false", "true", "False", "True")


def require_file(path: Path, validation: Validation) -> None:
    if not path.exists():
        validation.error(f"missing required file: {path}")
    elif path.is_file() and path.stat().st_size == 0 and path.name != ".nojekyll":
        validation.error(f"empty required file: {path}")


def csv_row_count(path: Path) -> int:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def iter_public_text_files() -> Iterable[Path]:
    candidates = [
        ROOT / "README.md",
        DOCS / "DATA_DICTIONARY.md",
        DOCS / "METHODOLOGY.md",
        DOCS / "METHODOLOGY_RU.md",
        DOCS / "index.html",
        DOCS / "locales" / "ru.json",
        DOCS / "locales" / "en.json",
    ]
    return (path for path in candidates if path.exists())


def validate_files(validation: Validation) -> None:
    for path in [
        DOCS / ".nojekyll",
        DOCS / "index.html",
        DOCS / "assets" / "app.js",
        DOCS / "assets" / "style.css",
        DOCS / "assets" / "i18n.js",
        DOCS / "assets" / "mgimo-home.png",
        DOCS / "assets" / "fnisc.png",
        DOCS / "assets" / "vendor" / "leaflet" / "leaflet.css",
        DOCS / "assets" / "vendor" / "leaflet" / "leaflet.js",
        DOCS / "assets" / "vendor" / "plotly" / "plotly.min.js",
        DATA / "mgimo_dashboard_data.json",
        DATA / "dashboard_payload.json",
        DATA / "world_admin_boundaries_ru_claimed_update_2026.geojson",
        DOCS / "locales" / "ru.json",
        DOCS / "locales" / "en.json",
    ]:
        require_file(path, validation)

    for path in [
        DATA / "country_ranking_snapshot.csv",
        DATA / "priority_matrix_snapshot.csv",
        DATA / "model_outputs" / term("final", "_snapshot"),
        DATA / "model_outputs" / term("live", "_final"),
    ]:
        if path.exists():
            validation.error(f"forbidden public snapshot artifact present: {path}")

    current_outputs = DATA / "model_outputs" / "current"
    if not current_outputs.exists():
        validation.error(f"missing model output folder: {current_outputs}")
    else:
        for name in REQUIRED_MODEL_FILES:
            path = current_outputs / name
            require_file(path, validation)
            if path.exists() and path.suffix == ".csv":
                try:
                    if csv_row_count(path) == 0:
                        validation.error(f"{path}: CSV has no rows")
                except Exception as exc:  # noqa: BLE001
                    validation.error(f"{path}: cannot read CSV: {exc}")

    reference = DATA / "reference"
    for name in REQUIRED_REFERENCE_FILES:
        require_file(reference / name, validation)

    for path in iter_public_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if FORBIDDEN_PUBLIC_TERMS.search(text):
            validation.error(f"{path}: scenario/snapshot/internal wording remains in public copy")


def collect_forbidden_payload_paths(value: Any, prefix: str = "$", limit: int = 30) -> list[str]:
    hits: list[str] = []

    def walk(node: Any, path: str) -> None:
        if len(hits) >= limit:
            return
        if isinstance(node, dict):
            for key, child in node.items():
                key_path = f"{path}.{key}"
                if FORBIDDEN_PAYLOAD_TERMS.search(str(key)):
                    hits.append(key_path)
                walk(child, key_path)
        elif isinstance(node, list):
            for index, child in enumerate(node):
                walk(child, f"{path}[{index}]")
        elif isinstance(node, str) and FORBIDDEN_PAYLOAD_TERMS.search(node):
            hits.append(path)

    walk(value, prefix)
    return hits


def payload_sources(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = data.get("sources") or []
    out: dict[str, dict[str, Any]] = {}
    if isinstance(sources, dict):
        iterator = sources.items()
    else:
        iterator = (
            (row.get("id") or row.get("source_key") or row.get("category") or row.get("provider"), row)
            for row in sources
            if isinstance(row, dict)
        )
    for key, row in iterator:
        if key:
            out[str(key)] = row if isinstance(row, dict) else {"value": row}
    return out


def source_has_metadata(source: dict[str, Any]) -> bool:
    has_label = bool(source.get("provider") or source.get("title") or source.get("name"))
    has_description = bool(source.get("description") or source.get("citation") or source.get("note"))
    has_trace = bool(source.get("url") or source.get("href") or source.get("retrieved_at") or source.get("version") or source.get("date") or source.get("rawFile"))
    public_trace = not FORBIDDEN_PAYLOAD_TERMS.search(str(source.get("rawFile") or ""))
    return has_label and has_description and has_trace and public_trace


def normalize_factor_entries(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("inputs", "fields", "sources", "components"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        if any(key in value for key in ("field", "column", "sourceField", "formula")):
            return [value]
    return []


def validate_weights(data: dict[str, Any], validation: Validation) -> dict[str, float]:
    weights_raw = data.get("weights") or data.get("weightsDefault")
    if weights_raw is None:
        factors = data.get("methodology", {}).get("factors")
        if isinstance(factors, list):
            weights_raw = {row.get("code"): row.get("weight") for row in factors if isinstance(row, dict) and row.get("code")}
    if not isinstance(weights_raw, dict) or not weights_raw:
        validation.error("payload must expose a non-empty plan weight object as weights or weightsDefault")
        return {}
    if any(isinstance(value, dict) for value in weights_raw.values()):
        validation.error("payload.weights must be one plan weight set, not nested scenario weights")
        return {}

    weights: dict[str, float] = {}
    for key, value in weights_raw.items():
        if not is_finite(value):
            validation.error(f"weights.{key}: non-finite weight")
            continue
        number = float(value)
        if number < 0:
            validation.error(f"weights.{key}: negative weight")
        weights[key] = number

    total = sum(weights.values())
    if not math.isclose(total, 1.0, rel_tol=0, abs_tol=1e-9):
        validation.error(f"payload.weights must sum to 1.0, got {total:.12f}")
    if len(weights) < 5:
        validation.error("payload.weights should expose the full plan factor set")
    return weights


def country_id(row: dict[str, Any]) -> str | None:
    return row.get("iso3")


def country_name(row: dict[str, Any]) -> str | None:
    return row.get("country") or row.get("name")


def country_factor(row: dict[str, Any], factor: str) -> Any:
    factor_scores = row.get("factorScores")
    if isinstance(factor_scores, dict) and factor in factor_scores:
        return factor_scores.get(factor)
    return row.get(factor)


def country_priority(row: dict[str, Any]) -> Any:
    return row.get("PRIORITY") if "PRIORITY" in row else row.get("priorityScore")


def country_rank(row: dict[str, Any]) -> Any:
    return row.get("rank_eligible") if "rank_eligible" in row else row.get("rank")


def country_coord(row: dict[str, Any], key: str) -> Any:
    coords = row.get("coordinates")
    if isinstance(coords, dict):
        return coords.get("lat" if key == "latitude" else "lon")
    return row.get(key)


def country_demography_value(row: dict[str, Any], field: str) -> Any:
    direct = row.get(field)
    if direct is not None:
        return direct
    demography = row.get("demography")
    if not isinstance(demography, dict):
        return None
    aliases = {
        "population_total_current": "populationTotalCurrent",
        "pop_15_24_current": "youth15_24Current",
        "pop_15_24_2026": "youth15_24_2026",
        "pop_15_24_2035": "youth15_24_2035",
        "pop_15_24_2050": "youth15_24_2050",
        "student_pool_2026": "studentPool2026",
        "student_pool_2035": "studentPool2035",
        "student_pool_2050": "studentPool2050",
        "addressable_market_students_2026": "addressableMarketStudents2026",
    }
    return demography.get(aliases.get(field, field))


def priority_formula(row: dict[str, Any], weights: dict[str, float], epsilon: float = 0.05) -> float | None:
    acc = 0.0
    weight_sum = 0.0
    for key, weight in weights.items():
        value = country_factor(row, key)
        if not is_finite(value):
            continue
        score = min(1.0, max(0.0, float(value)))
        acc += weight * math.log(epsilon + score)
        weight_sum += weight
    if weight_sum <= 0:
        return None
    return 100 * math.exp(acc / weight_sum)


def validate_priority_formula(countries: list[dict[str, Any]], weights: dict[str, float], validation: Validation) -> None:
    checked = 0
    for row in countries:
        if row.get("eligible") not in (1, True, "1", "true"):
            continue
        expected = country_priority(row)
        calculated = priority_formula(row, weights)
        if calculated is None or not is_finite(expected):
            validation.error(f"{row.get('iso3')}: cannot evaluate plan priority formula")
            continue
        if abs(float(expected) - calculated) > 1e-6:
            validation.error(f"{row.get('iso3')}: PRIORITY {expected} does not match geometric formula {calculated:.9f}")
        checked += 1
    if checked < 50:
        validation.error(f"priority formula checked too few eligible countries: {checked}")


def validate_factor_inputs(data: dict[str, Any], countries: list[dict[str, Any]], weights: dict[str, float], validation: Validation) -> None:
    factor_inputs = data.get("factorInputs")
    if not isinstance(factor_inputs, dict) or not factor_inputs:
        validation.error("payload.factorInputs must describe source inputs for every weighted factor")
        return

    sources = payload_sources(data)
    source_errors = 0
    for source_id, source in sources.items():
        if not source_has_metadata(source):
            source_errors += 1
            if source_errors <= 8:
                validation.error(f"sources.{source_id}: missing provider/description/date-or-url metadata")
    if not sources:
        validation.error("payload.sources must contain source metadata")

    country_iso = {country_id(row) for row in countries if country_id(row)}
    country_keyed = len(country_iso & set(factor_inputs)) >= min(25, max(1, len(country_iso) // 4))
    if country_keyed:
        missing = sorted(country_iso - set(factor_inputs))
        if missing:
            validation.error(f"factorInputs missing countries: {missing[:12]}")
        required_groups = {
            "I_MARKET": "market",
            "I_PROGRAM": "program",
            "I_RUSCOMP": "russiaCompatibility",
            "I_ECO": "economy",
            "I_FIN": "finance",
            "I_FEAS": "feasibility",
            "I_HRSTRAT": "strategicHr",
        }
        for row in countries[:60]:
            iso3 = country_id(row)
            entry = factor_inputs.get(iso3) or {}
            if not isinstance(entry, dict):
                validation.error(f"factorInputs.{iso3}: must be an object")
                continue
            for factor in weights:
                if not is_finite(country_factor(row, factor)):
                    validation.error(f"{iso3}: missing finite factor score {factor}")
                group_name = required_groups.get(factor)
                if not group_name:
                    continue
                group = entry.get(group_name)
                if not isinstance(group, dict) or not group:
                    validation.error(f"factorInputs.{iso3}.{group_name}: missing input group for {factor}")
                elif not any(is_finite(value) for value in group.values() if not isinstance(value, (dict, list))):
                    nested_values = [
                        nested
                        for value in group.values()
                        if isinstance(value, dict)
                        for nested in value.values()
                    ]
                    if not any(is_finite(value) for value in nested_values):
                        validation.error(f"factorInputs.{iso3}.{group_name}: no finite input values")
        return

    country_fields = set().union(*(row.keys() for row in countries)) if countries else set()
    for factor in weights:
        factor_def = factor_inputs.get(factor)
        if factor_def is None:
            validation.error(f"factorInputs.{factor}: missing factor input metadata")
            continue
        entries = normalize_factor_entries(factor_def)
        if not entries:
            validation.error(f"factorInputs.{factor}: must contain at least one input/source row")
            continue
        if factor not in country_fields:
            validation.error(f"{factor}: weighted factor is missing from country rows")
        for index, entry in enumerate(entries):
            field = entry.get("field") or entry.get("column") or entry.get("sourceField")
            formula = entry.get("formula") or entry.get("derivedFormula") or entry.get("method")
            source_id = entry.get("sourceId") or entry.get("source") or entry.get("source_category") or entry.get("category")
            provider = entry.get("provider") or entry.get("sourceProvider")
            has_entry_trace = bool(entry.get("url") or entry.get("citation") or entry.get("retrieved_at") or entry.get("date"))
            if not field and not formula:
                validation.error(f"factorInputs.{factor}[{index}]: missing field or formula")
            if field and field not in country_fields:
                validation.error(f"factorInputs.{factor}[{index}]: field {field!r} is absent from country rows")
            if not source_id and not provider:
                validation.error(f"factorInputs.{factor}[{index}]: missing source identifier/provider")
            if source_id and str(source_id) not in sources and not provider:
                validation.error(f"factorInputs.{factor}[{index}]: source {source_id!r} not found in payload.sources")
            if source_id and str(source_id) in sources and not source_has_metadata(sources[str(source_id)]) and not has_entry_trace:
                validation.error(f"factorInputs.{factor}[{index}]: source {source_id!r} lacks trace metadata")


def validate_vietnam_status(countries: list[dict[str, Any]], markers: dict[str, Any], validation: Validation) -> None:
    by_iso = {row.get("iso3"): row for row in countries}
    vietnam = by_iso.get("VNM")
    if not vietnam:
        validation.error("missing Vietnam row")
        return
    status_bits = [
        vietnam.get("status"),
        vietnam.get("public_status"),
        vietnam.get("publicStatus"),
        vietnam.get("map_status"),
        vietnam.get("mapStatus"),
        vietnam.get("table_status"),
        vietnam.get("tableStatus"),
        vietnam.get("recommendation_category"),
        vietnam.get("recommendationCategory"),
        vietnam.get("branchStatus"),
    ]
    status_text = " ".join(str(part) for part in status_bits if part)
    if not PREPARATION_STATUS.search(status_text):
        validation.error(f"VNM: public status must be in preparation, got {status_text!r}")
    if STATUS_FORBIDDEN.search(status_text):
        validation.error(f"VNM: public status contains recommendation/exclusion wording: {status_text!r}")

    marker_rows = []
    for rows in (markers or {}).values():
        if isinstance(rows, list):
            marker_rows.extend(row for row in rows if isinstance(row, dict) and row.get("iso3") == "VNM")
    if not marker_rows:
        validation.error("VNM: map marker/status row missing")
    for marker in marker_rows:
        marker_status = " ".join(str(marker.get(key) or "") for key in ("status", "public_status", "publicStatus", "map_status", "mapStatus", "category", "presenceType", "branchStatus"))
        if not PREPARATION_STATUS.search(marker_status):
            validation.error(f"VNM marker: status must be in preparation, got {marker_status!r}")


def year_rows(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("year"), int):
            out[row["year"]] = row
    return out


def close_enough(left: Any, right: Any, *, rel: float = 0.015, abs_tol: float = 1.0) -> bool:
    if not is_finite(left) or not is_finite(right):
        return False
    return math.isclose(float(left), float(right), rel_tol=rel, abs_tol=abs_tol)


def pyramid_collection_rows(pyramid: dict[str, Any], collection_name: str) -> list[dict[str, Any]]:
    verbose = pyramid.get(collection_name)
    if isinstance(verbose, list):
        return [row for row in verbose if isinstance(row, dict)]

    years_key = "forecastYears" if collection_name == "forecast" else "actualYears"
    male_key = "forecastMale" if collection_name == "forecast" else "actualMale"
    female_key = "forecastFemale" if collection_name == "forecast" else "actualFemale"
    years = pyramid.get(years_key) or []
    male_matrix = pyramid.get(male_key) or []
    female_matrix = pyramid.get(female_key) or []
    bands = pyramid.get("ageBands") or AGE_BANDS
    rows: list[dict[str, Any]] = []
    for row_index, year in enumerate(years):
        male_row = male_matrix[row_index] if row_index < len(male_matrix) else []
        female_row = female_matrix[row_index] if row_index < len(female_matrix) else []
        for band_index, age_band in enumerate(bands):
            rows.append(
                {
                    "year": int(year) if isinstance(year, (int, float)) else year,
                    "ageBand": age_band,
                    "male": male_row[band_index] if band_index < len(male_row) else None,
                    "female": female_row[band_index] if band_index < len(female_row) else None,
                    "targetGroup": age_band in TARGET_AGE_BANDS,
                }
            )
    return rows


def validate_demography(countries: list[dict[str, Any]], data: dict[str, Any], validation: Validation) -> None:
    iso3_values = [row.get("iso3") for row in countries if row.get("iso3")]
    country_iso = set(iso3_values)
    demography_series = data.get("demographySeries") or {}
    age_pyramid = data.get("ageSexPyramid") or {}

    if set(demography_series) != country_iso:
        validation.error("demographySeries ISO3 set must match countries exactly")
    if set(age_pyramid) != country_iso:
        validation.error("ageSexPyramid ISO3 set must match countries exactly")

    for row in countries:
        iso3 = row.get("iso3")
        series = demography_series.get(iso3) or {}
        actual = year_rows(series.get("actual") or [])
        forecast = year_rows(series.get("forecast") or [])
        if sorted(actual) != list(range(2000, 2024)):
            validation.error(f"{iso3}: demography actual years must be 2000-2023")
        if sorted(forecast) != list(range(2024, 2051)):
            validation.error(f"{iso3}: demography forecast years must be 2024-2050")
        for year in (2026, 2035, 2050):
            if year not in (series.get("highlightYears") or []):
                validation.error(f"{iso3}: demography highlight year {year} missing")
            forecast_row = forecast.get(year) or {}
            target_pop = country_demography_value(row, f"pop_15_24_{year}")
            if target_pop is not None and not close_enough(forecast_row.get("pop_15_24"), target_pop):
                validation.error(f"{iso3}: demography pop_15_24 {year} does not match country row")
            if not close_enough(forecast_row.get("student_pool"), country_demography_value(row, f"student_pool_{year}")):
                validation.error(f"{iso3}: demography student_pool {year} does not match country row")
        forecast_2024 = forecast.get(2024) or {}
        if not close_enough(forecast_2024.get("population_total"), country_demography_value(row, "population_total_current")):
            validation.error(f"{iso3}: 2024 WPP projection population does not match current country population")

        pyramid = age_pyramid.get(iso3) or {}
        status = pyramid.get("dataStatus")
        if status not in {"available", "partial", "missing"}:
            validation.error(f"{iso3}: ageSexPyramid has invalid dataStatus {status!r}")
        if TARGET_AGE_BANDS - set(pyramid.get("highlightAgeBands") or []):
            validation.error(f"{iso3}: ageSexPyramid target age bands missing")
        if status == "available":
            for collection_name, expected_years in [("actual", [2023]), ("forecast", [2024, 2026, 2035, 2050])]:
                rows = pyramid_collection_rows(pyramid, collection_name)
                by_year: dict[int, set[str]] = {}
                for item in rows:
                    if item.get("ageBand") not in AGE_BANDS:
                        validation.error(f"{iso3}: invalid pyramid age band {item.get('ageBand')!r}")
                    if item.get("ageBand") in TARGET_AGE_BANDS and item.get("targetGroup") is not True:
                        validation.error(f"{iso3}: target age band {item.get('ageBand')} is not marked")
                    if is_finite(item.get("male")) and float(item["male"]) < 0:
                        validation.error(f"{iso3}: negative male pyramid value")
                    if is_finite(item.get("female")) and float(item["female"]) < 0:
                        validation.error(f"{iso3}: negative female pyramid value")
                    if isinstance(item.get("year"), int):
                        by_year.setdefault(item["year"], set()).add(item.get("ageBand"))
                for year in expected_years:
                    if by_year.get(year) != set(AGE_BANDS):
                        validation.error(f"{iso3}: ageSexPyramid {collection_name} year {year} lacks complete age bands")


def student_sai_payload(data: dict[str, Any]) -> Any:
    students = data.get("students")
    if isinstance(students, dict):
        return students.get("sai") or students.get("SAI") or students.get("studentAI") or students.get("studentAddressableIndex")
    return data.get("studentSai") or data.get("studentSAI")


def fact_model_rows(entry: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(entry, dict):
        facts = entry.get("facts") or entry.get("fact") or entry.get("actual") or []
        model = entry.get("model") or entry.get("forecast") or entry.get("modeled") or []
        if isinstance(facts, list) or isinstance(model, list):
            return (
                [row for row in facts if isinstance(row, dict)],
                [row for row in model if isinstance(row, dict)],
            )
        rows = entry.get("series")
    else:
        rows = entry
    if not isinstance(rows, list):
        return [], []
    facts = [row for row in rows if isinstance(row, dict) and str(row.get("kind") or row.get("type") or "").lower() in {"fact", "actual", "observed"}]
    model = [row for row in rows if isinstance(row, dict) and str(row.get("kind") or row.get("type") or "").lower() in {"model", "modeled", "forecast"}]
    return facts, model


def validate_student_sai(data: dict[str, Any], countries: list[dict[str, Any]], validation: Validation) -> None:
    attraction = data.get("studentAttraction")
    observed = data.get("studentFlowsObserved")
    modelled = data.get("studentFlowsModelled")
    country_iso = {row.get("iso3") for row in countries if row.get("iso3")}
    if isinstance(attraction, dict) or isinstance(observed, dict) or isinstance(modelled, dict):
        attraction_by_country = attraction.get("byCountry") if isinstance(attraction, dict) else None
        observed_by_country = observed.get("byCountry") if isinstance(observed, dict) else None
        modelled_by_country = modelled.get("byCountry") if isinstance(modelled, dict) else None
        if not isinstance(attraction_by_country, dict):
            validation.error("studentAttraction.byCountry must expose SAI values by ISO3")
        elif country_iso - set(attraction_by_country):
            validation.error(f"studentAttraction missing countries: {sorted(country_iso - set(attraction_by_country))[:12]}")
        if not isinstance(observed_by_country, dict):
            validation.error("studentFlowsObserved.byCountry must exist, even when observed facts are unavailable")
        else:
            coverage = observed.get("coverage") if isinstance(observed, dict) else {}
            if not observed_by_country and not (isinstance(coverage, dict) and coverage.get("status") and coverage.get("source")):
                validation.error("studentFlowsObserved empty byCountry must include coverage status and source")
        model_meta = modelled.get("model") if isinstance(modelled, dict) else {}
        model_coverage = modelled.get("coverage") if isinstance(modelled, dict) else {}
        if not isinstance(modelled_by_country, dict):
            validation.error("studentFlowsModelled.byCountry must exist, even when no factual open flow source is available")
        elif not modelled_by_country:
            disabled = isinstance(model_meta, dict) and str(model_meta.get("name") or "").startswith("disabled_no_open")
            disabled = disabled and isinstance(model_coverage, dict) and "disabled" in str(model_coverage.get("status") or "")
            if not disabled:
                validation.error("empty studentFlowsModelled requires disabled_no_open source metadata")
        else:
            if not isinstance(model_meta, dict) or not model_meta.get("source"):
                validation.error("studentFlowsModelled.model must include source metadata")
            if str(model_meta.get("scoreType") or "") != "modelled_attraction_potential_from_open_indicators_not_mgimo_headcount":
                validation.error("studentFlowsModelled.model must be labelled as modelled attraction potential, not observed student flows")
            rows = modelled.get("rows") if isinstance(modelled, dict) else []
            for item in rows[:80]:
                if item.get("flowType") != "modelled_potential_not_observed_mgimo_students":
                    validation.error(f"{item.get('originIso3')}: modelled flow must be explicitly marked not observed")
                if not is_finite(item.get("modelledPotentialIndex")):
                    validation.error(f"{item.get('originIso3')}: modelledPotentialIndex is required")
                if not is_finite(item.get("strokeWidth")):
                    validation.error(f"{item.get('originIso3')}: strokeWidth is required for modelled arrows")
        if isinstance(attraction_by_country, dict):
            for iso3, row in attraction_by_country.items():
                filters = row.get("hardFilters") if isinstance(row, dict) else {}
                hard = isinstance(filters, dict) and any(bool(filters.get(key)) for key in ("unfriendly_430r", "domestic_russia", "non_sovereign_or_special"))
                if hard:
                    if is_finite(row.get("saiMgimoV3Score")):
                        validation.error(f"{iso3}: hard-filtered student country has an index score")
                    if row.get("rankPracticalStudentRecruitment") is not None or row.get("rankReferenceAll") is not None:
                        validation.error(f"{iso3}: hard-filtered student country has a rank")
        return

    sai = student_sai_payload(data)
    if not isinstance(sai, (dict, list)) or not sai:
        validation.error("payload must expose students.sai or studentSai fact/model data")
        return

    if isinstance(sai, list):
        entries = {row.get("iso3"): row for row in sai if isinstance(row, dict) and row.get("iso3")}
    else:
        entries = {key: value for key, value in sai.items()}
    missing = sorted(country_iso - set(entries))
    if missing:
        validation.error(f"student SAI missing countries: {missing[:12]}")

    for iso3 in sorted(country_iso)[:25]:
        facts, model = fact_model_rows(entries.get(iso3))
        if not facts:
            validation.error(f"{iso3}: student SAI facts missing")
        if not model:
            validation.error(f"{iso3}: student SAI model rows missing")
        for label, rows in [("fact", facts), ("model", model)]:
            for row in rows:
                if not isinstance(row.get("year"), int):
                    validation.error(f"{iso3}: student SAI {label} row has invalid year")
                if not is_finite(row.get("value")):
                    validation.error(f"{iso3}: student SAI {label} row has invalid value")
                if not (row.get("source") or row.get("method") or row.get("sourceId")):
                    validation.error(f"{iso3}: student SAI {label} row lacks source/method metadata")


def validate_country_rows(countries: list[dict[str, Any]], validation: Validation) -> None:
    if len(countries) < 200:
        validation.error(f"countries too few: {len(countries)}")
    iso3_values = [row.get("iso3") for row in countries if row.get("iso3")]
    if len(iso3_values) != len(set(iso3_values)):
        validation.error("duplicate ISO3 values in countries")

    eligible = [row for row in countries if row.get("eligible") in (1, True, "1", "true")]
    if len(eligible) < 100:
        validation.error(f"eligible country count unexpectedly low: {len(eligible)}")

    for row in sorted(eligible, key=lambda item: country_rank(item) or 9999)[:30]:
        missing = []
        if not country_id(row):
            missing.append("iso3")
        if not country_name(row):
            missing.append("country/name")
        if not is_finite(country_rank(row)):
            missing.append("rank/rank_eligible")
        if not is_finite(country_priority(row)):
            missing.append("PRIORITY/priorityScore")
        for factor in ["I_MARKET", "I_PROGRAM", "I_RUSCOMP", "I_ECO", "I_FIN", "I_FEAS", "I_HRSTRAT"]:
            if not is_finite(country_factor(row, factor)):
                missing.append(f"factorScores.{factor}")
        if not is_finite(country_coord(row, "latitude")) or not is_finite(country_coord(row, "longitude")):
            missing.append("coordinates")
        if not is_finite(country_demography_value(row, "addressable_market_students_2026")):
            missing.append("addressable_market_students_2026")
        if missing:
            validation.error(f"{country_id(row)}: top country missing fields {missing}")
        for field in ["eligible", "is_unfriendly", "is_domestic_russia", "is_non_sovereign_or_special", "has_existing_mgimo_branch", "has_mgimo_pipeline"]:
            if field in row and not boolish(row.get(field)):
                validation.error(f"{country_id(row)}: {field} is not boolish")

    for row in countries:
        iso3 = country_id(row)
        for value, field in [(country_rank(row), "rank/rank_eligible"), (row.get("rank_all_diagnostic"), "rank_all_diagnostic")]:
            if value is not None and value == value:
                try:
                    if int(value) < 1:
                        validation.error(f"{iso3}: {field} must be positive")
                except (TypeError, ValueError):
                    validation.error(f"{iso3}: {field} is not an integer")
        for field in ["I_MARKET", "I_PROGRAM", "I_RUSCOMP", "I_ECO", "I_FIN", "I_FEAS", "I_HRSTRAT", "DATAQ"]:
            value = row.get(field) if field == "DATAQ" else country_factor(row, field)
            if value is not None and (not is_finite(value) or not (0 <= float(value) <= 1)):
                validation.error(f"{iso3}: {field} outside 0-1 range")


def validate_markers(markers: dict[str, Any], validation: Validation) -> None:
    existing = markers.get("existing") or []
    candidates = markers.get("candidates") or markers.get("inPreparation") or []
    platforms = markers.get("platforms") or []
    if len(existing) + len(platforms) < 5:
        validation.error(f"expected at least 5 existing/platform markers, got {len(existing) + len(platforms)}")
    if not candidates:
        validation.error("expected at least one candidate/in-preparation marker")
    for collection_name, collection in [("existing", existing), ("candidates", candidates), ("platforms", platforms)]:
        for marker in collection:
            lat = marker.get("lat")
            lon = marker.get("lon")
            if not is_finite(lat) or not is_finite(lon):
                validation.error(f"{collection_name} marker {marker.get('id') or marker.get('iso3')}: invalid coordinates")


def validate_payload(data: dict[str, Any], validation: Validation) -> None:
    alias = DATA / "dashboard_payload.json"
    canonical = DATA / "mgimo_dashboard_data.json"
    if canonical.exists() and alias.exists() and sha256(canonical) != sha256(alias):
        validation.error("dashboard_payload.json is not byte-equivalent to mgimo_dashboard_data.json")
    if canonical.exists() and canonical.stat().st_size > 8_000_000:
        validation.error("mgimo_dashboard_data.json is too heavy for first-load static delivery")

    for key in ["countries", "metadata", "sources", "methodology", "demographySeries", "ageSexPyramid", "factorInputs"]:
        if key not in data:
            validation.error(f"payload missing top-level key: {key}")
    if "markers" not in data and "branchMarkers" not in data:
        validation.error("payload missing top-level key: markers or branchMarkers")
    if "weights" not in data and "weightsDefault" not in data:
        validation.error("payload missing top-level key: weights or weightsDefault")

    forbidden_paths = collect_forbidden_payload_paths(data)
    if forbidden_paths:
        validation.error(f"payload contains forbidden scenario/snapshot/internal terms: {forbidden_paths}")

    countries = data.get("countries") or []
    if not isinstance(countries, list):
        validation.error("payload.countries must be a list")
        countries = []
    country_rows = [row for row in countries if isinstance(row, dict)]
    weights = validate_weights(data, validation)
    validate_country_rows(country_rows, validation)
    if weights:
        validate_priority_formula(country_rows, weights, validation)
        validate_factor_inputs(data, country_rows, weights, validation)
    validate_vietnam_status(country_rows, data.get("markers") or data.get("branchMarkers") or {}, validation)
    validate_demography(country_rows, data, validation)
    validate_student_sai(data, country_rows, validation)
    validate_markers(data.get("markers") or data.get("branchMarkers") or {}, validation)



def validate_geojson(data: dict[str, Any], geo: dict[str, Any], validation: Validation) -> None:
    if geo.get("type") != "FeatureCollection":
        validation.error("GeoJSON is not a FeatureCollection")
    features = geo.get("features") or []
    if len(features) < 200:
        validation.error(f"GeoJSON feature count too low: {len(features)}")

    geo_iso: set[str] = set()
    for feature in features:
        props = feature.get("properties") or {}
        if props.get("adm0_a3") == "KOS" or props.get("wb_a3") == "KSV":
            geo_iso.add("XKX")
        for field in ISO_FIELDS:
            value = props.get(field)
            if isinstance(value, str) and len(value) == 3 and value != "-99":
                geo_iso.add(value)

    country_iso = {row.get("iso3") for row in data.get("countries", []) if isinstance(row, dict) and row.get("iso3")}
    unmatched = sorted(country_iso - geo_iso)
    unexpected = [iso for iso in unmatched if iso not in KNOWN_UNMATCHED]
    if unexpected:
        validation.error(f"unexpected country ISO3 values unmatched to GeoJSON: {unexpected}")
    elif unmatched:
        validation.warn(f"known GeoJSON unmatched ISO3 values: {unmatched}")


def main() -> int:
    validation = Validation()
    validate_files(validation)
    payload = read_strict_json(DATA / "mgimo_dashboard_data.json", validation)
    _alias = read_strict_json(DATA / "dashboard_payload.json", validation)
    geo = read_strict_json(DATA / "world_admin_boundaries_ru_claimed_update_2026.geojson", validation)
    if isinstance(payload, dict):
        validate_payload(payload, validation)
    if isinstance(payload, dict) and isinstance(geo, dict):
        validate_geojson(payload, geo, validation)

    for warning in validation.warnings:
        print(f"WARNING: {warning}")
    if validation.errors:
        for error in validation.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"validation failed: {len(validation.errors)} error(s), {len(validation.warnings)} warning(s)", file=sys.stderr)
        return 1
    print(f"validation passed: {len(validation.warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
