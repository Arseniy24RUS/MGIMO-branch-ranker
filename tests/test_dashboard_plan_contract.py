from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

SAI_UIS_KEY = "A_OUTBOUND_MOBILITY_UIS"
OLD_SAI_BASE = "A_MOBILITY" + "_READINESS"
OLD_SAI_KEY = OLD_SAI_BASE + "_" + "PRO" + "XY"


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_PLAN_RE = re.compile(
    r"\b(?:"
    + "|".join(
        re.escape(item)
        for item in [
            _term("sce", "nario"),
            _term("sce", "narios"),
            _term("base", "line"),
            _term("soft", "_power"),
            _term("comm", "ercial"),
            _term("risk", "_averse"),
            _term("snapshot", "Countries"),
            _term("live", "_final"),
            _term("final", "_snapshot"),
        ]
    )
    + r")\b",
    re.IGNORECASE,
)
PREPARATION_RE = re.compile(r"\bin[_ -]?preparation\b|\u0412 \u043f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u043a\u0435", re.IGNORECASE)
STATUS_FORBIDDEN_RE = re.compile(r"\b(?:pipeline|priority|recommend|excluded|direct|open|hard)\b", re.IGNORECASE)


def _payload() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "docs" / "data" / "mgimo_dashboard_data.json").read_text(encoding="utf-8"))


def _walk_forbidden(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if FORBIDDEN_PLAN_RE.search(str(key)):
                hits.append(child_path)
            hits.extend(_walk_forbidden(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            hits.extend(_walk_forbidden(child, f"{path}[{index}]"))
    elif isinstance(value, str) and FORBIDDEN_PLAN_RE.search(value):
        hits.append(path)
    return hits


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _raw_present(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value) and all(_finite(item) for item in value.values())
    return _finite(value)


def _weights(data: dict[str, Any]) -> dict[str, float]:
    raw = data.get("weights") or data.get("weightsDefault")
    if raw is None:
        raw = {row["code"]: row["weight"] for row in data.get("methodology", {}).get("factors", [])}
    return {key: float(value) for key, value in raw.items()}


def _factor(country: dict[str, Any], key: str) -> Any:
    return (country.get("factorScores") or {}).get(key, country.get(key))


def _priority(country: dict[str, Any]) -> Any:
    return country.get("PRIORITY", country.get("priorityScore"))


def _demography(country: dict[str, Any], key: str) -> Any:
    demography = country.get("demography") or {}
    aliases = {
        "population_total_current": "populationTotalCurrent",
        "student_pool_2026": "studentPool2026",
        "student_pool_2035": "studentPool2035",
        "student_pool_2050": "studentPool2050",
    }
    return country.get(key, demography.get(aliases.get(key, key)))


def test_dashboard_payload_is_plan_only_and_weights_sum_to_one():
    data = _payload()
    forbidden = _walk_forbidden(data)
    assert forbidden == []

    weights = _weights(data)
    assert weights
    assert math.isclose(sum(float(value) for value in weights.values()), 1.0, abs_tol=1e-9)
    assert set(row["iso3"] for row in data["countries"]).issubset(set(data.get("factorInputs", {})))


def test_dashboard_priority_matches_backend_formula_for_plan_weights():
    data = _payload()
    weights = _weights(data)
    countries = [row for row in data["countries"] if row.get("eligible") in (1, True, "1", "true")]
    assert len(countries) > 50

    for row in countries:
        acc = 0.0
        weight_sum = 0.0
        for factor, weight in weights.items():
            value = _factor(row, factor)
            if not _finite(value):
                continue
            acc += weight * math.log(0.05 + min(1.0, max(0.0, float(value))))
            weight_sum += weight
        assert weight_sum > 0
        score = 100 * math.exp(acc / weight_sum)
        assert math.isclose(float(_priority(row)), score, rel_tol=0, abs_tol=1e-9)


def test_vietnam_has_in_preparation_table_and_map_status():
    data = _payload()
    vietnam = next(row for row in data["countries"] if row["iso3"] == "VNM")
    status = " ".join(
        str(vietnam.get(field) or "")
        for field in ["status", "public_status", "publicStatus", "table_status", "tableStatus", "map_status", "mapStatus", "recommendation_category", "recommendationCategory", "branchStatus"]
    )
    assert PREPARATION_RE.search(status)
    assert not STATUS_FORBIDDEN_RE.search(status)

    marker_statuses = []
    for rows in (data.get("markers") or data.get("branchMarkers") or {}).values():
        marker_statuses.extend(
            " ".join(str(marker.get(field) or "") for field in ["status", "public_status", "publicStatus", "map_status", "mapStatus", "category", "presenceType", "branchStatus"])
            for marker in rows
            if isinstance(marker, dict) and marker.get("iso3") == "VNM"
    )
    assert marker_statuses
    assert all(PREPARATION_RE.search(status) for status in marker_statuses)


def test_factor_inputs_have_complete_source_metadata():
    data = _payload()
    countries = data["countries"]
    sources = {
        str(row.get("id") or row.get("source_key") or row.get("category") or row.get("provider")): row
        for row in data.get("sources", [])
        if isinstance(row, dict)
    }
    assert sources

    def source_is_traceable(source: dict[str, Any]) -> bool:
        trace = source.get("url") or source.get("retrieved_at") or source.get("date") or source.get("version") or source.get("rawFile")
        return bool(source.get("provider") or source.get("title")) and bool(source.get("description") or source.get("citation")) and bool(trace) and not FORBIDDEN_PLAN_RE.search(str(trace))

    assert all(source_is_traceable(source) for source in sources.values())

    required_groups = ["market", "program", "russiaCompatibility", "economy", "finance", "feasibility", "strategicHr"]
    for country in countries[:40]:
        entry = data["factorInputs"][country["iso3"]]
        for group in required_groups:
            assert isinstance(entry.get(group), dict)
            assert entry[group]
        for factor in _weights(data):
            assert _finite(_factor(country, factor))


def test_factor_inputs_long_trace_fields_and_real_years():
    root = Path(__file__).resolve().parents[1]
    rows = json.loads((root / "docs" / "data" / "factor_inputs_long.json").read_text(encoding="utf-8"))
    assert rows
    required = {
        "source_key",
        "year",
        "raw_value",
        "normalized_value",
        "normalization_method",
        "input_weight",
        "factor_weight",
        "observation_status",
        "scoring_role",
        "weight_note",
    }
    for row in rows[:500]:
        assert required.issubset(row), row
        assert _finite(row["input_weight"])
        assert _finite(row["factor_weight"])
        assert row["source_key"]
        assert row["normalization_method"]
        assert row["scoring_role"]
        if row["scoring_role"] == "direct_factor_formula_component":
            assert _finite(row["normalized_value"]), row
    years = {int(row["year"]) for row in rows if _finite(row.get("year"))}
    assert len(years) > 3
    assert years != {2026}
    vietnam_prep = [
        row for row in rows
        if row["iso3"] == "VNM" and row["factor_key"] == "I_RUSCOMP" and row["input_key"] == "inPreparation"
    ]
    assert vietnam_prep
    assert vietnam_prep[0]["input_weight"] == 0
    assert vietnam_prep[0]["normalized_value"] is None
    assert vietnam_prep[0]["scoring_role"] == "reference_status_not_scored"


def test_demography_series_matches_country_rows():
    data = _payload()
    by_iso = {row["iso3"]: row for row in data["countries"]}
    assert set(data["demographySeries"]) == set(by_iso)
    assert set(data["ageSexPyramid"]) == set(by_iso)

    for iso3, country in list(by_iso.items())[:40]:
        series = data["demographySeries"][iso3]
        actual = {row["year"]: row for row in series["actual"]}
        forecast = {row["year"]: row for row in series["forecast"]}
        assert series["sourceKey"] == "un_wpp2024_population_by_single_age_sex"
        assert "UN WPP 2024" in series["source"]
        assert data["ageSexPyramid"][iso3]["highlightAgeBands"] == ["15-19", "20-24"]
        assert {row["observation_status"] for row in actual.values()} == {"official_estimate"}
        assert {row["observation_status"] for row in forecast.values()} == {"official_projection"}
        assert sorted(actual) == list(range(2000, 2024))
        assert sorted(forecast) == list(range(2024, 2051))
        assert math.isclose(float(forecast[2024]["population_total"]), float(_demography(country, "population_total_current")), rel_tol=0.015, abs_tol=1.0)
        for year in (2026, 2035, 2050):
            assert math.isclose(float(forecast[year]["student_pool"]), float(_demography(country, f"student_pool_{year}")), rel_tol=0.015, abs_tol=1.0)
            assert year in series["highlightYears"]


def test_student_sai_schema_splits_fact_and_model_values():
    data = _payload()
    country_iso = {row["iso3"] for row in data["countries"]}
    attraction = data["studentAttraction"]
    observed = data["studentFlowsObserved"]
    modelled = data["studentFlowsModelled"]

    assert attraction["model"]["name"] == "SAI_MGIMO_V3"
    serialized_attraction = json.dumps(attraction, ensure_ascii=False)
    assert "I_MARKET" not in json.dumps(attraction.get("model", {}), ensure_ascii=False)
    assert _term("fall", "back", "_from_prepared_inputs") not in serialized_attraction
    assert "top20ByDefaultPriority" not in serialized_attraction
    assert country_iso.issubset(set(attraction["byCountry"]))
    assert isinstance(observed["byCountry"], dict)
    if not observed["byCountry"]:
        assert observed["coverage"]["status"] == "not_available_country_level_mgimo"
        assert "student_flows_observed.csv" in observed["coverage"]["source"]
    assert modelled["model"]["name"] == "SAI_MGIMO_V3"
    assert modelled["model"]["scoreType"] == "modelled_attraction_potential_from_open_indicators_not_mgimo_headcount"
    assert "financial_model_recommended_format_student_ramp" not in json.dumps(modelled, ensure_ascii=False)
    assert len(modelled["rows"]) > 20
    assert all(row["flowType"] == "modelled_potential_not_observed_mgimo_students" for row in modelled["rows"])

    for iso3 in ["NGA", "VNM", "SAU", "IND", "BRA"]:
        assert attraction["byCountry"][iso3]["model"] == "SAI_MGIMO_V3"
        assert _finite(attraction["byCountry"][iso3]["saiMgimoV3Score"])
        assert {
            "A_YOUTH_OPPORTUNITY",
            SAI_UIS_KEY,
            "A_AFFORDABILITY_ACCESS",
            "A_DIGITAL_REACH",
            "A_DATAQ",
        }.issubset(set(attraction["byCountry"][iso3]["components"]))
        assert OLD_SAI_BASE not in attraction["byCountry"][iso3]["components"]
        assert OLD_SAI_KEY not in attraction["byCountry"][iso3]["components"]
        trace = attraction["byCountry"][iso3]["componentTrace"]
        assert {
            "A_YOUTH_OPPORTUNITY",
            SAI_UIS_KEY,
            "A_LEGAL_PARTNERSHIP_CONTEXT",
            "A_PROGRAM_RELEVANCE",
            "A_AFFORDABILITY_ACCESS",
            "A_DIGITAL_REACH",
            "A_DATAQ",
        } == set(trace)
        assert OLD_SAI_BASE not in trace
        assert OLD_SAI_KEY not in trace
        assert trace[SAI_UIS_KEY]["source_key"] == "unesco_uis_uis006_mor_5t8_40510"
        for item in trace.values():
            assert item["source_key"]
            assert item["year"]
            assert _finite(item["weight"])
            if item["weight"]:
                assert _raw_present(item["raw_value"])
                assert _finite(item["normalized_value"])
            assert item["observation_status"]
            assert item["normalization_method"]
