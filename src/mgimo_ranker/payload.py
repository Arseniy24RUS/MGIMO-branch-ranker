from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mgimo_ranker.config import ProjectConfig
from mgimo_ranker.model.indices import PROFILE_LABELS
from mgimo_ranker.sources.wpp2024_bulk import (
    WPP_SOURCE_KEY,
    load_wpp_demography_payload_blocks,
)

SCHEMA_VERSION = "2.0.0"
PREPARATION_STATUS = "В подготовке"


def _term(*parts: str) -> str:
    return "".join(parts)

FACTOR_COLUMNS = ["I_MARKET", "I_PROGRAM", "I_RUSCOMP", "I_ECO", "I_FIN", "I_FEAS", "I_HRSTRAT"]
FACTOR_GROUPS = {
    "I_MARKET": "market",
    "I_PROGRAM": "program",
    "I_RUSCOMP": "russiaCompatibility",
    "I_ECO": "economy",
    "I_FIN": "finance",
    "I_FEAS": "feasibility",
    "I_HRSTRAT": "strategicHr",
}
FACTOR_GROUP_SOURCES = {
    "market": WPP_SOURCE_KEY,
    "program": "live_merged_features",
    "russiaCompatibility": "mgimo_presence",
    "economy": "world_bank_indicators_long",
    "finance": "live_merged_features",
    "feasibility": "world_bank_wgi_long",
    "strategicHr": "live_merged_features",
}
FACTOR_GROUP_OBSERVATION = {
    "market": "official_or_reference",
    "program": "modelled",
    "russiaCompatibility": "official_or_reference",
    "economy": "official_or_reference",
    "finance": "modelled",
    "feasibility": "official_or_reference",
    "strategicHr": "modelled",
}
FACTOR_INPUT_TRACE_META: dict[str, dict[str, dict[str, Any]]] = {
    "market": {
        "addressableMarketStudents2026": {"weight": 0.50, "normalized": "__normalized.addressableMarketStudents2026", "method": "robust_norm(log1p(raw), positive=True)"},
        "addressableMarketStudents2035": {"weight": 0.15, "normalized": "__normalized.addressableMarketStudents2035", "method": "robust_norm(log1p(raw), positive=True)"},
        "addressableMarketStudents2050": {"weight": 0.10, "normalized": "__normalized.addressableMarketStudents2050", "method": "robust_norm(log1p(raw), positive=True)"},
        "amsGrowth2026_2035": {"weight": 0.08, "normalized": "__normalized.amsGrowth2026_2035", "method": "robust_norm(raw growth, positive=True)"},
        "amsGrowth2026_2050": {"weight": 0.07, "normalized": "__normalized.amsGrowth2026_2050", "method": "robust_norm(raw growth, positive=True)"},
        "educationScore": {"weight": 0.05, "normalized": "__normalized.educationScore", "method": "prepared_0_1_score"},
        "educationHubScore": {"weight": 0.05, "normalized": "__normalized.educationHubScore", "method": "prepared_0_1_score"},
    },
    "program": {
        "programFit": {"weight": 1.00, "normalized": "__normalized.programFit", "method": "0.65*max(profile_scores)+0.35*mean(profile_scores)"},
        "profiles.diplomatic_analytic": {"weight": 0.0, "normalized": "__normalized.profiles.diplomatic_analytic", "method": "profile_component_for_program_fit", "role": "model_component_context"},
        "profiles.economic_legal": {"weight": 0.0, "normalized": "__normalized.profiles.economic_legal", "method": "profile_component_for_program_fit", "role": "model_component_context"},
        "profiles.digital_finance_business_informatics": {"weight": 0.0, "normalized": "__normalized.profiles.digital_finance_business_informatics", "method": "profile_component_for_program_fit", "role": "model_component_context"},
        "profiles.energy_logistics": {"weight": 0.0, "normalized": "__normalized.profiles.energy_logistics", "method": "profile_component_for_program_fit", "role": "model_component_context"},
    },
    "russiaCompatibility": {
        "isUnfriendly": {"weight": 0.0, "normalized": "__normalized.isUnfriendly", "method": "legal_filter_gate; unfriendly => I_RUSCOMP=0", "role": "multiplicative_gate"},
        "hasExistingMgimoBranch": {"weight": -0.20, "normalized": "__normalized.hasExistingMgimoBranch", "method": "-0.20*existing_branch_flag", "role": "direct_penalty"},
        "partnerUniversitiesMgimoCount": {"weight": 0.14, "normalized": "__normalized.partnerUniversitiesMgimoCount", "method": "robust_norm(log1p(raw), positive=True)"},
        "strategicHrFit": {"weight": 0.12, "normalized": "__normalized.strategicHrFit", "method": "prepared_0_1_score"},
        "programFit": {"weight": 0.10, "normalized": "__normalized.programFit", "method": "prepared_0_1_score"},
        "inPreparation": {"weight": 0.0, "normalized": None, "method": "reference_status_flag_not_scored", "role": "reference_status_not_scored"},
        "isDomesticRussia": {"weight": 0.0, "normalized": None, "method": "eligibility_reference_flag_not_scored_in_index", "role": "hard_filter_context"},
        "isNonSovereignOrSpecial": {"weight": 0.0, "normalized": None, "method": "eligibility_reference_flag_not_scored_in_index", "role": "hard_filter_context"},
        "strategicPartnerUniversitiesCount": {"weight": 0.0, "normalized": None, "method": "reference_context_not_scored", "role": "reference_context_not_scored"},
    },
    "economy": {
        "gdpPcPppCurrent": {"weight": 0.25, "normalized": "__normalized.gdpPcPppCurrent", "method": "robust_norm(log1p(raw), positive=True)"},
        "gdpPppCurrent": {"weight": 0.15, "normalized": "__normalized.gdpPppCurrent", "method": "robust_norm(log1p(raw), positive=True)"},
        "gdpGrowthReal": {"weight": 0.17, "normalized": "__normalized.gdpGrowthReal", "method": "robust_norm(raw, positive=True)"},
        "programFit": {"weight": 0.18, "normalized": "__normalized.programFit", "method": "prepared_0_1_score"},
        "inflationCpi": {"weight": 0.05, "normalized": "__normalized.inflationCpi", "method": "0.10*N_macro_stability*0.5; robust_norm(raw, positive=False)"},
        "unemployment": {"weight": 0.05, "normalized": "__normalized.unemployment", "method": "0.10*N_macro_stability*0.5; robust_norm(raw, positive=False)"},
        "tradePercentGdp": {"weight": 0.08, "normalized": "__normalized.tradePercentGdp", "method": "robust_norm(raw, positive=True)"},
        "sectorDepthScore": {"weight": 0.07, "normalized": "__normalized.sectorDepthScore", "method": "mean(normalized sector depth indicators)"},
    },
    "finance": {
        "npvPositiveProbability": {"weight": 0.70, "normalized": "__normalized.npvPositiveProbability", "method": "probability_0_1"},
        "npvExpectedUsd": {"weight": 0.30, "normalized": "__normalized.npvExpectedUsd", "method": "robust_norm(raw, positive=True)"},
    },
    "feasibility": {
        "politicalStability": {"weight": 0.15, "normalized": "__normalized.politicalStability", "method": "robust_norm(raw, positive=True)"},
        "governmentEffectiveness": {"weight": 0.12, "normalized": "__normalized.governmentEffectiveness", "method": "robust_norm(raw, positive=True)"},
        "regulatoryQuality": {"weight": 0.12, "normalized": "__normalized.regulatoryQuality", "method": "robust_norm(raw, positive=True)"},
        "ruleOfLaw": {"weight": 0.12, "normalized": "__normalized.ruleOfLaw", "method": "robust_norm(raw, positive=True)"},
        "controlCorruption": {"weight": 0.09, "normalized": "__normalized.controlCorruption", "method": "robust_norm(raw, positive=True)"},
        "logisticsPerformanceIndex": {"weight": 0.14, "normalized": "__normalized.logisticsPerformanceIndex", "method": "robust_norm(raw, positive=True)"},
        "internetUsersPct": {"weight": 0.11, "normalized": "__normalized.internetUsersPct", "method": "robust_norm(raw, positive=True)"},
        "urbanPopulationPct": {"weight": 0.08, "normalized": "__normalized.urbanPopulationPct", "method": "robust_norm(raw, positive=True)"},
        "partnerUniversitiesMgimoCount": {"weight": 0.07, "normalized": "__normalized.partnerUniversitiesMgimoCount", "method": "robust_norm(log1p(raw), positive=True)"},
    },
    "strategicHr": {
        "nationalPriorityEnergy": {"weight": 0.16, "normalized": "__normalized.nationalPriorityEnergy", "method": "robust_norm(raw, positive=True)"},
        "nationalPriorityLogistics": {"weight": 0.16, "normalized": "__normalized.nationalPriorityLogistics", "method": "robust_norm(raw, positive=True)"},
        "nationalPriorityDiplomacy": {"weight": 0.18, "normalized": "__normalized.nationalPriorityDiplomacy", "method": "robust_norm(raw, positive=True)"},
        "digitalFinanceProfileScore": {"weight": 0.20, "normalized": "__normalized.digitalFinanceProfileScore", "method": "prepared_0_1_score"},
        "economicLegalProfileScore": {"weight": 0.15, "normalized": "__normalized.economicLegalProfileScore", "method": "prepared_0_1_score"},
        "energyLogisticsProfileScore": {"weight": 0.15, "normalized": "__normalized.energyLogisticsProfileScore", "method": "prepared_0_1_score"},
    },
}
SAI_V3_COMPONENT_TRACE_META = {
    "A_YOUTH_OPPORTUNITY": {
        "year_field": "pop_15_24_latest_year",
        "source_key": WPP_SOURCE_KEY,
        "raw_fields": ["pop_15_24_latest", "pop_15_24_growth_10y_pct"],
        "normalization_method": "0.70*log_norm(pop_15_24_latest) + 0.30*minmax(pop_15_24_growth_10y_pct)",
        "observation_status": "official_or_reference",
    },
    "A_OUTBOUND_MOBILITY_UIS": {
        "year_field": "uis_outbound_mobility_year",
        "source_key_field": "uis_source_key",
        "raw_field": "uis_outbound_mobility_ratio",
        "normalization_method": "minmax(p05-p95, outbound mobility ratio)",
        "observation_status_field": "uis_observation_status",
        "score_type": "official_uis_outbound_mobility",
    },
    "A_LEGAL_PARTNERSHIP_CONTEXT": {
        "year": "current reference",
        "source_key": "student_attraction_v3.csv",
        "raw_fields": ["is_unfriendly_430r", "is_domestic_russia", "is_non_sovereign_or_special"],
        "normalization_method": "official hard filters plus open partnership context; ineligible countries receive no SAI score",
        "observation_status": "official_or_reference",
    },
    "A_PROGRAM_RELEVANCE": {
        "year": "current dashboard build",
        "source_key": "student_attraction_v3.csv",
        "raw_field": "program_relevance_score",
        "normalization_method": "prepared program-industry relevance score from open sector, education, and profile indicators",
        "observation_status": "modelled_from_open_inputs",
    },
    "A_AFFORDABILITY_ACCESS": {
        "year": "latest WDI in payload",
        "source_key": "student_attraction_v3.csv",
        "raw_field": "gdp_pc_ppp_current",
        "normalization_method": "log_norm(gdp_pc_ppp_current)",
        "observation_status": "official_or_reference",
    },
    "A_DIGITAL_REACH": {
        "year": "latest WDI in payload",
        "source_key": "student_attraction_v3.csv",
        "raw_field": "internet_users_pct",
        "normalization_method": "internet_users_pct min-max normalization",
        "observation_status": "official_or_reference",
    },
    "A_DATAQ": {
        "year": "latest available source years",
        "source_key": "student_attraction_v3.csv",
        "raw_fields": ["dataq_required_available", "dataq_required_total"],
        "normalization_method": "coverage share of required public indicators",
        "observation_status": "build_audit",
    },
}
PROFILE_PUBLIC_NAMES = {v: v for v in PROFILE_LABELS.values()}
PROFILE_PUBLIC_NAMES.update(
    {
        "digital_finance": "digital_finance_business_informatics",
        "diplo_analytic": "diplomatic_analytic",
        "econ_legal": "economic_legal",
    }
)

CITY_COORDS: dict[str, tuple[float, float]] = {
    "moscow": (55.7558, 37.6173),
    "odintsovo": (55.6789, 37.2636),
    "tashkent": (41.2995, 69.2401),
    "astana": (51.1694, 71.4491),
    "geneva": (46.2044, 6.1432),
    "hanoi": (21.0069, 105.825),
}
PRIMARY_GEO_ISO_FIELDS = ["iso_a3", "adm0_a3", "wb_a3"]
GEO_ISO_FIELDS = [*PRIMARY_GEO_ISO_FIELDS, "adm0_iso", "sov_a3", "gu_a3"]
ISO2_BY_SPECIAL_ISO3 = {
    "CHI": "JE",
    "GIB": "GI",
    "NOR": "NO",
    "XKX": "XK",
}


def _clean(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items() if _clean(v) is not None}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        if not math.isfinite(float(value)):
            return None
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _finite(value: Any) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _num(row: pd.Series, key: str) -> float | None:
    value = pd.to_numeric(pd.Series([row.get(key)]), errors="coerce").iloc[0]
    return None if pd.isna(value) or not math.isfinite(float(value)) else float(value)


def _bool(row: pd.Series, key: str) -> bool:
    value = row.get(key)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value) if not pd.isna(value) else False


def _text(row: pd.Series, key: str) -> str | None:
    value = row.get(key)
    if value is None or pd.isna(value):
        return None
    stripped = str(value).strip()
    return stripped or None


def _int_or_none(value: Any) -> int | None:
    if not _finite(value):
        return None
    return int(float(value))


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [_clean(row) for row in df.to_dict(orient="records")]


def _geojson_label_coords(public_data_dir: Path) -> dict[str, dict[str, float]]:
    geo_path = public_data_dir / "world_admin_boundaries_ru_claimed_update_2026.geojson"
    if not geo_path.exists():
        return {}
    try:
        geo = json.loads(geo_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    coords: dict[str, dict[str, float]] = {}
    for feature in geo.get("features") or []:
        props = feature.get("properties") or {}
        lon = props.get("label_x")
        lat = props.get("label_y")
        if not _finite(lat) or not _finite(lon):
            continue
        iso2_candidates = [props.get("iso_a2"), props.get("wb_a2"), props.get("postal")]
        iso2 = next(
            (
                str(value).upper()
                for value in iso2_candidates
                if isinstance(value, str) and len(value) == 2 and value != "-99"
            ),
            None,
        )
        primary_iso_values = set()
        if props.get("adm0_a3") == "KOS" or props.get("wb_a3") == "KSV":
            primary_iso_values.add("XKX")
        for field in PRIMARY_GEO_ISO_FIELDS:
            value = props.get(field)
            if isinstance(value, str) and len(value) == 3 and value != "-99":
                primary_iso_values.add(value.upper())
        secondary_iso_values = set()
        for field in GEO_ISO_FIELDS:
            value = props.get(field)
            if isinstance(value, str) and len(value) == 3 and value != "-99":
                secondary_iso_values.add(value.upper())
        for iso3 in primary_iso_values:
            coords[iso3] = {"lat": float(lat), "lon": float(lon)}
            if iso2:
                coords[iso3]["iso2"] = iso2
        for iso3 in secondary_iso_values - primary_iso_values:
            coords.setdefault(iso3, {"lat": float(lat), "lon": float(lon)})
    return coords


def _factor_scores(row: pd.Series) -> dict[str, float | None]:
    return {col: _num(row, col) for col in FACTOR_COLUMNS}


def _profile_scores(row: pd.Series) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for col, public_name in PROFILE_LABELS.items():
        out[public_name] = _num(row, col)
    return out


def _growth_ratio(row: pd.Series, start_col: str, end_col: str) -> float | None:
    start = _num(row, start_col)
    end = _num(row, end_col)
    if start is None or end is None or start == 0:
        return None
    return (end / start) - 1


def _binary_score(value: Any) -> float | None:
    if value is None or value is pd.NA:
        return None
    return 1.0 if bool(value) else 0.0


def _country_rows(full: pd.DataFrame, geo_coords: dict[str, dict[str, float]] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sort_cols = [c for c in ["eligible", "rank_eligible", "PRIORITY"] if c in full.columns]
    work = full.copy()
    if sort_cols:
        work = work.sort_values(sort_cols, ascending=[False, True, False][: len(sort_cols)])
    for _, row in work.iterrows():
        has_pipeline = _bool(row, "has_mgimo_pipeline")
        iso3 = _text(row, "iso3")
        geo_coord = (geo_coords or {}).get(str(iso3 or "").upper(), {})
        lat = _num(row, "latitude")
        lon = _num(row, "longitude")
        if lat is None and _finite(geo_coord.get("lat")):
            lat = float(geo_coord["lat"])
        if lon is None and _finite(geo_coord.get("lon")):
            lon = float(geo_coord["lon"])
        iso2 = _text(row, "iso2") or ISO2_BY_SPECIAL_ISO3.get(str(iso3 or "").upper()) or _text(pd.Series(geo_coord), "iso2")
        country: dict[str, Any] = {
            "iso3": iso3,
            "iso2": iso2,
            "name": _text(row, "country"),
            "region": _text(row, "region"),
            "incomeGroup": _text(row, "income_group"),
            "capitalCity": _text(row, "capital_city"),
            "coordinates": {"lat": lat, "lon": lon},
            "eligible": _bool(row, "eligible"),
            "eligibilityReason": _text(row, "exclusion_reason"),
            "rank": _int_or_none(row.get("rank_eligible")),
            "priorityScore": _num(row, "PRIORITY"),
            "recommendationCategory": "in_preparation" if has_pipeline else _text(row, "recommendation_category"),
            "branchStatus": PREPARATION_STATUS if has_pipeline else None,
            "factorScores": _factor_scores(row),
            "program": {
                "recommendedProfile": _text(row, "recommended_program_profile"),
                "fitScore": _num(row, "PROGRAM_FIT"),
                "profileScores": _profile_scores(row),
            },
            "finance": {
                "recommendedFormat": _text(row, "recommended_format"),
                "capexUsd": _num(row, "capex_usd"),
                "npv10yUsd": _num(row, "npv_10y_usd"),
                "npvExpectedUsd": _num(row, "npv_expected_usd"),
                "npvP10Usd": _num(row, "npv_p10_usd"),
                "npvP90Usd": _num(row, "npv_p90_usd"),
                "npvPositiveProbability": _num(row, "npv_positive_probability"),
                "paybackYears": _num(row, "payback_years"),
                "studentsYear10": _num(row, "students_year_10"),
                "averageTuitionUsd": _num(row, "avg_tuition_usd"),
            },
            "demography": {
                "populationTotalCurrent": _num(row, "population_total_current"),
                "youth15_24Current": _num(row, "pop_15_24_current"),
                "studentPool2026": _num(row, "student_pool_2026"),
                "studentPool2035": _num(row, "student_pool_2035"),
                "studentPool2050": _num(row, "student_pool_2050"),
                "addressableMarketStudents2026": _num(row, "addressable_market_students_2026"),
                "addressableMarketStudents2035": _num(row, "addressable_market_students_2035"),
                "addressableMarketStudents2050": _num(row, "addressable_market_students_2050"),
            },
        }
        rows.append(_clean(country))
    return rows


def _factor_inputs(full: pd.DataFrame) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for _, row in full.iterrows():
        iso3 = _text(row, "iso3")
        if not iso3:
            continue
        out[iso3] = _clean(
            {
                "market": {
                    "populationTotalCurrent": _num(row, "population_total_current"),
                    "populationTotalCurrentYear": _int_or_none(row.get("population_total_current_year")),
                    "youth15_24_2026": _num(row, "pop_15_24_2026"),
                    "youth15_24CurrentYear": _int_or_none(row.get("pop_15_24_current_year")),
                    "studentPool2026": _num(row, "student_pool_2026"),
                    "studentPoolCurrentYear": _int_or_none(row.get("student_pool_current_year")),
                    "addressableMarketStudents2026": _num(row, "addressable_market_students_2026"),
                    "addressableMarketStudents2035": _num(row, "addressable_market_students_2035"),
                    "addressableMarketStudents2050": _num(row, "addressable_market_students_2050"),
                    "amsGrowth2026_2035": _growth_ratio(row, "addressable_market_students_2026", "addressable_market_students_2035"),
                    "amsGrowth2026_2050": _growth_ratio(row, "addressable_market_students_2026", "addressable_market_students_2050"),
                    "tertiaryEnrollmentGross": _num(row, "tertiary_enrollment_gross"),
                    "tertiaryEnrollmentGrossYear": _int_or_none(row.get("tertiary_enrollment_gross_year")),
                    "secondaryCompletionUpper": _num(row, "secondary_completion_upper"),
                    "secondaryCompletionUpperYear": _int_or_none(row.get("secondary_completion_upper_year")),
                    "educationScore": _num(row, "N_education"),
                    "educationHubScore": _num(row, "N_education_hub"),
                    "affordabilityFactor": _num(row, "AFFORDABILITY_FACTOR"),
                    "fieldFitFactor": _num(row, "FIELD_FIT_FACTOR"),
                    "__normalized": {
                        "addressableMarketStudents2026": _num(row, "N_addressable_market_2026"),
                        "addressableMarketStudents2035": _num(row, "N_addressable_market_2035"),
                        "addressableMarketStudents2050": _num(row, "N_addressable_market_2050"),
                        "amsGrowth2026_2035": _num(row, "N_ams_growth_2026_2035"),
                        "amsGrowth2026_2050": _num(row, "N_ams_growth_2026_2050"),
                        "educationScore": _num(row, "N_education"),
                        "educationHubScore": _num(row, "N_education_hub"),
                    },
                },
                "program": {
                    "programFit": _num(row, "PROGRAM_FIT"),
                    "recommendedProfile": _text(row, "recommended_program_profile"),
                    "profiles": _profile_scores(row),
                    "__normalized": {
                        "programFit": _num(row, "PROGRAM_FIT"),
                        "profiles": _profile_scores(row),
                    },
                },
                "russiaCompatibility": {
                    "isUnfriendly": _bool(row, "is_unfriendly"),
                    "hasExistingMgimoBranch": _bool(row, "has_existing_mgimo_branch"),
                    "isDomesticRussia": _bool(row, "is_domestic_russia"),
                    "isNonSovereignOrSpecial": _bool(row, "is_non_sovereign_or_special"),
                    "inPreparation": _bool(row, "has_mgimo_pipeline"),
                    "partnerUniversitiesMgimoCount": _num(row, "partner_universities_mgimo_count"),
                    "strategicPartnerUniversitiesCount": _num(row, "strategic_partner_universities_count"),
                    "strategicHrFit": _num(row, "I_HRSTRAT"),
                    "programFit": _num(row, "PROGRAM_FIT"),
                    "__normalized": {
                        "isUnfriendly": _binary_score(_bool(row, "is_unfriendly")),
                        "hasExistingMgimoBranch": _binary_score(_bool(row, "has_existing_mgimo_branch")),
                        "partnerUniversitiesMgimoCount": _num(row, "N_partner_universities"),
                        "strategicHrFit": _num(row, "I_HRSTRAT"),
                        "programFit": _num(row, "PROGRAM_FIT"),
                    },
                },
                "economy": {
                    "gdpPppCurrent": _num(row, "gdp_ppp_current"),
                    "gdpPppCurrentYear": _int_or_none(row.get("gdp_ppp_current_year")),
                    "gdpPcPppCurrent": _num(row, "gdp_pc_ppp_current"),
                    "gdpPcPppCurrentYear": _int_or_none(row.get("gdp_pc_ppp_current_year")),
                    "gdpGrowthReal": _num(row, "gdp_growth_real"),
                    "gdpGrowthRealYear": _int_or_none(row.get("gdp_growth_real_year")),
                    "inflationCpi": _num(row, "inflation_cpi"),
                    "inflationCpiYear": _int_or_none(row.get("inflation_cpi_year")),
                    "unemployment": _num(row, "unemployment"),
                    "unemploymentYear": _int_or_none(row.get("unemployment_year")),
                    "tradePercentGdp": _num(row, "trade_percent_gdp"),
                    "tradePercentGdpYear": _int_or_none(row.get("trade_percent_gdp_year")),
                    "servicesValueAdded": _num(row, "services_value_added"),
                    "servicesValueAddedYear": _int_or_none(row.get("services_value_added_year")),
                    "priceLevelIndex": _num(row, "price_level_index"),
                    "priceLevelIndexYear": _int_or_none(row.get("price_level_index_year")),
                    "programFit": _num(row, "PROGRAM_FIT"),
                    "sectorDepthScore": _num(row, "N_sector_depth"),
                    "__normalized": {
                        "gdpPcPppCurrent": _num(row, "N_gdp_pc_ppp"),
                        "gdpPppCurrent": _num(row, "N_gdp_ppp"),
                        "gdpGrowthReal": _num(row, "N_gdp_growth"),
                        "programFit": _num(row, "PROGRAM_FIT"),
                        "inflationCpi": _num(row, "N_inflation_stability"),
                        "unemployment": _num(row, "N_unemployment_stability"),
                        "tradePercentGdp": _num(row, "N_trade_open"),
                        "sectorDepthScore": _num(row, "N_sector_depth"),
                    },
                },
                "finance": {
                    "recommendedFormat": _text(row, "recommended_format"),
                    "demandPoolStudents": _num(row, "demand_pool_students"),
                    "captureCeiling": _num(row, "capture_ceiling"),
                    "hostSubsidyShare": _num(row, "host_subsidy_share"),
                    "studentsYear1": _num(row, "students_year_1"),
                    "studentsYear10": _num(row, "students_year_10"),
                    "avgTuitionUsd": _num(row, "avg_tuition_usd"),
                    "capexUsd": _num(row, "capex_usd"),
                    "npvExpectedUsd": _num(row, "npv_expected_usd"),
                    "npvPositiveProbability": _num(row, "npv_positive_probability"),
                    "__normalized": {
                        "npvPositiveProbability": _num(row, "npv_positive_probability"),
                        "npvExpectedUsd": _num(row, "N_expected_npv"),
                    },
                },
                "feasibility": {
                    "politicalStability": _num(row, "wgi_political_stability"),
                    "politicalStabilityYear": _int_or_none(row.get("wgi_political_stability_year")),
                    "governmentEffectiveness": _num(row, "wgi_government_effectiveness"),
                    "governmentEffectivenessYear": _int_or_none(row.get("wgi_government_effectiveness_year")),
                    "regulatoryQuality": _num(row, "wgi_regulatory_quality"),
                    "regulatoryQualityYear": _int_or_none(row.get("wgi_regulatory_quality_year")),
                    "ruleOfLaw": _num(row, "wgi_rule_of_law"),
                    "ruleOfLawYear": _int_or_none(row.get("wgi_rule_of_law_year")),
                    "controlCorruption": _num(row, "wgi_control_corruption"),
                    "controlCorruptionYear": _int_or_none(row.get("wgi_control_corruption_year")),
                    "logisticsPerformanceIndex": _num(row, "lpi_overall"),
                    "logisticsPerformanceIndexYear": _int_or_none(row.get("lpi_overall_year")),
                    "internetUsersPct": _num(row, "internet_users"),
                    "internetUsersPctYear": _int_or_none(row.get("internet_users_year")),
                    "urbanPopulationPct": _num(row, "urban_population_pct"),
                    "urbanPopulationPctYear": _int_or_none(row.get("urban_population_pct_year")),
                    "partnerUniversitiesMgimoCount": _num(row, "partner_universities_mgimo_count"),
                    "__normalized": {
                        "politicalStability": _num(row, "N_wgi_political_stability"),
                        "governmentEffectiveness": _num(row, "N_wgi_government_effectiveness"),
                        "regulatoryQuality": _num(row, "N_wgi_regulatory_quality"),
                        "ruleOfLaw": _num(row, "N_wgi_rule_of_law"),
                        "controlCorruption": _num(row, "N_wgi_control_corruption"),
                        "logisticsPerformanceIndex": _num(row, "N_lpi"),
                        "internetUsersPct": _num(row, "N_internet"),
                        "urbanPopulationPct": _num(row, "N_urban_population"),
                        "partnerUniversitiesMgimoCount": _num(row, "N_partner_universities"),
                    },
                },
                "strategicHr": {
                    "nationalPriorityEnergy": _num(row, "national_priority_energy"),
                    "nationalPriorityLogistics": _num(row, "national_priority_logistics"),
                    "nationalPriorityDiplomacy": _num(row, "national_priority_diplomacy"),
                    "digitalFinanceProfileScore": _num(row, "I_PROFILE_DIGITAL_FINANCE"),
                    "economicLegalProfileScore": _num(row, "I_PROFILE_ECON_LEGAL"),
                    "energyLogisticsProfileScore": _num(row, "I_PROFILE_ENERGY_LOGISTICS"),
                    "__normalized": {
                        "nationalPriorityEnergy": _num(row, "N_national_priority_energy"),
                        "nationalPriorityLogistics": _num(row, "N_national_priority_logistics"),
                        "nationalPriorityDiplomacy": _num(row, "N_national_priority_diplomacy"),
                        "digitalFinanceProfileScore": _num(row, "I_PROFILE_DIGITAL_FINANCE"),
                        "economicLegalProfileScore": _num(row, "I_PROFILE_ECON_LEGAL"),
                        "energyLogisticsProfileScore": _num(row, "I_PROFILE_ENERGY_LOGISTICS"),
                    },
                },
            }
        )
    return out


def _eligibility(full: pd.DataFrame, cfg: ProjectConfig) -> dict[str, Any]:
    by_country: dict[str, Any] = {}
    for _, row in full.iterrows():
        iso3 = _text(row, "iso3")
        if not iso3:
            continue
        reason = _text(row, "exclusion_reason")
        item: dict[str, Any] = {
            "eligible": _bool(row, "eligible"),
            "reasons": [] if not reason else [part for part in reason.split(";") if part],
            "flags": {
                "unfriendly": _bool(row, "is_unfriendly"),
                "existingMgimoBranch": _bool(row, "has_existing_mgimo_branch"),
                "domesticRussia": _bool(row, "is_domestic_russia"),
                "nonSovereignOrSpecial": _bool(row, "is_non_sovereign_or_special"),
            },
        }
        if _bool(row, "has_mgimo_pipeline"):
            item["status"] = PREPARATION_STATUS
        by_country[iso3] = item
    return _clean(
        {
            "rules": {
                "hardExcludeUnfriendly": bool(cfg.get("rules", "hard_exclude_unfriendly", default=True)),
                "hardExcludeExistingBranch": bool(cfg.get("rules", "hard_exclude_existing_branch", default=True)),
                "hardExcludeDomesticRussia": bool(cfg.get("rules", "hard_exclude_domestic_russia", default=True)),
                "hardExcludeNonSovereignOrSpecial": bool(cfg.get("rules", "hard_exclude_non_sovereign", default=True)),
                "minDataQualityForPriority": float(cfg.get("rules", "min_data_quality_for_priority", default=0.0)),
            },
            "summary": {
                "totalCountries": int(len(full)),
                "eligibleCountries": int(full["eligible"].astype(bool).sum()) if "eligible" in full else 0,
                "inPreparationCountries": int(full.get("has_mgimo_pipeline", pd.Series(False, index=full.index)).astype(bool).sum()),
            },
            "byCountry": by_country,
        }
    )


def _load_demography(
    full: pd.DataFrame,
    wpp_age_sex_historical_path: Path | None = None,
    wpp_age_sex_projection_path: Path | None = None,
    raw_demography_path: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if raw_demography_path is not None:
        raise ValueError("--raw-demography is deprecated and disabled; use --wpp-age-sex-historical and --wpp-age-sex-projection.")
    iso_keep = {_text(row, "iso3") for _, row in full.iterrows()}
    iso_keep.discard(None)
    return load_wpp_demography_payload_blocks(
        historical_path=wpp_age_sex_historical_path,
        projection_path=wpp_age_sex_projection_path,
        iso_filter=sorted(iso_keep),
    )


def _marker_country(row: pd.Series) -> dict[str, Any]:
    presence_type = _text(row, "mgimo_presence_type")
    if presence_type == "branch_pipeline":
        presence_type = "branch_in_preparation"
    notes = _text(row, "mgimo_presence_notes")
    if _bool(row, "has_mgimo_pipeline") and notes:
        notes = notes.replace("; treat as pipeline until legal opening", "; status shown as in preparation until legal opening")
    lat = _num(row, "mgimo_presence_latitude")
    lon = _num(row, "mgimo_presence_longitude")
    return {
        "iso3": _text(row, "iso3"),
        "country": _text(row, "country"),
        "city": _text(row, "mgimo_presence_city") or _text(row, "capital_city"),
        "lat": lat,
        "lon": lon,
        "presenceType": presence_type,
        "notes": notes,
        "coordinateSource": _text(row, "mgimo_presence_coordinate_source"),
    }


def _branch_markers(full: pd.DataFrame) -> dict[str, Any]:
    by_iso = {str(row["iso3"]).upper(): row for _, row in full.iterrows() if _text(row, "iso3")}
    existing: list[dict[str, Any]] = [
        {
            "id": "moscow_hq",
            "iso3": "RUS",
            "country": "Russian Federation",
            "city": "Moscow",
            "presenceType": "headquarters",
            "lat": CITY_COORDS["moscow"][0],
            "lon": CITY_COORDS["moscow"][1],
        },
        {
            "id": "odintsovo",
            "iso3": "RUS",
            "country": "Russian Federation",
            "city": "Odintsovo",
            "presenceType": "domestic_campus",
            "lat": CITY_COORDS["odintsovo"][0],
            "lon": CITY_COORDS["odintsovo"][1],
        },
    ]
    platforms: list[dict[str, Any]] = []
    in_preparation: list[dict[str, Any]] = []
    for iso3, row in sorted(by_iso.items()):
        presence_type = _text(row, "mgimo_presence_type")
        if not presence_type:
            continue
        marker = _marker_country(row)
        marker["id"] = f"branch_{iso3.lower()}"
        if not _finite(marker.get("lat")) or not _finite(marker.get("lon")):
            continue
        marker = _clean(marker)
        if _bool(row, "has_mgimo_pipeline"):
            marker["status"] = PREPARATION_STATUS
            in_preparation.append(marker)
        elif presence_type == "educational_platform":
            platforms.append(marker)
        elif _bool(row, "has_existing_mgimo_branch"):
            existing.append(marker)
    return {"existing": existing, "inPreparation": in_preparation, "platforms": platforms}


def _trace_year(row: pd.Series, meta: dict[str, Any]) -> Any:
    field = meta.get("year_field")
    if field:
        value = row.get(field)
        if _finite(value):
            return int(float(value))
        return _text(row, field)
    return meta.get("year")


def _trace_raw_value(row: pd.Series, meta: dict[str, Any]) -> Any:
    field = meta.get("raw_field")
    if field:
        return _num(row, field)
    fields = meta.get("raw_fields") or []
    if fields:
        raw: dict[str, Any] = {}
        for key in fields:
            value = row.get(key)
            if isinstance(value, (bool, np.bool_)):
                raw[key] = bool(value)
            elif key.startswith("is_") or key.startswith("has_"):
                raw[key] = _bool(row, key)
            else:
                raw[key] = _num(row, key) if _finite(value) else _text(row, key)
        return raw
    return None


def _sai_component_trace(row: pd.Series, component_key: str, weight: Any) -> dict[str, Any]:
    meta = SAI_V3_COMPONENT_TRACE_META.get(component_key, {})
    source_key = (
        _text(row, meta.get("source_key_field"))
        if meta.get("source_key_field")
        else meta.get("source_key")
    )
    observation_status = (
        _text(row, meta.get("observation_status_field"))
        if meta.get("observation_status_field")
        else meta.get("observation_status")
    )
    return _clean(
        {
            "source_key": source_key,
            "year": _trace_year(row, meta),
            "raw_value": _trace_raw_value(row, meta),
            "normalized_value": _num(row, component_key),
            "normalization_method": meta.get("normalization_method"),
            "weight": weight,
            "observation_status": observation_status,
            "score_type": meta.get("score_type", "open_api_observed_indicator_index"),
        }
    )


def _student_attraction(full: pd.DataFrame, student_v3_path: Path | None = None, student_meta_path: Path | None = None) -> dict[str, Any]:
    if student_v3_path and student_v3_path.exists():
        student = pd.read_csv(student_v3_path)
        meta = _read_json(student_meta_path) if student_meta_path else {}
        by_country: dict[str, Any] = {}
        component_cols = [
            "A_YOUTH_OPPORTUNITY",
            "A_OUTBOUND_MOBILITY_UIS",
            "A_LEGAL_PARTNERSHIP_CONTEXT",
            "A_PROGRAM_RELEVANCE",
            "A_AFFORDABILITY_ACCESS",
            "A_DIGITAL_REACH",
            "A_DATAQ",
        ]
        input_cols = [
            "pop_15_24_latest",
            "pop_15_24_latest_year",
            "pop_15_24_base_year",
            "pop_15_24_growth_10y_pct",
            "student_pool_latest",
            "student_pool_latest_year",
            "uis_outbound_mobility_ratio",
            "uis_outbound_mobility_year",
            "uis_source_key",
            "uis_observation_status",
            "internet_users_pct",
            "gdp_pc_ppp_current",
            "program_relevance_score",
            "dataq_required_available",
            "dataq_required_total",
            "score_source_policy",
            "has_required_open_data",
        ]
        weights = meta.get("weights") or {}
        for _, row in student.iterrows():
            iso3 = _text(row, "iso3")
            if not iso3:
                continue
            component_trace = {}
            for col in component_cols:
                component_trace[col] = _sai_component_trace(row, col, weights.get(col))
            by_country[iso3] = _clean(
                {
                    "model": "SAI_MGIMO_V3",
                    "saiMgimoV3Score": _num(row, "SAI_MGIMO_V3_SCORE"),
                    "rankPracticalStudentRecruitment": _int_or_none(row.get("rank_practical_student_recruitment")),
                    "rankReferenceAll": _int_or_none(row.get("rank_reference_all")),
                    "studentRecruitmentStatus": _text(row, "student_recruitment_status"),
                    "hardFilters": {
                        "unfriendly_430r": _bool(row, "is_unfriendly_430r"),
                        "domestic_russia": _bool(row, "is_domestic_russia"),
                        "non_sovereign_or_special": _bool(row, "is_non_sovereign_or_special"),
                    },
                    "components": {col: _num(row, col) for col in component_cols},
                    "componentTrace": component_trace,
                    "inputs": {
                        col: (_num(row, col) if col not in {"score_source_policy"} else _text(row, col))
                        for col in input_cols
                    },
                    "dueDiligenceWarnings": _text(row, "due_diligence_warnings"),
                }
            )
        practical = student[student["rank_practical_student_recruitment"].notna()].copy() if "rank_practical_student_recruitment" in student else student.head(0)
        if not practical.empty:
            practical = practical.sort_values("rank_practical_student_recruitment").head(20)
        return _clean(
            {
                "model": {
                    "name": "SAI_MGIMO_V3",
                    "scoreType": meta.get("score_type") or "open-data index from observed public indicators; not MGIMO student headcount",
                    "weights": meta.get("weights"),
                    "hardFilters": meta.get("hard_filters") or ["unfriendly_430r", "domestic_russia", "non_sovereign_or_special"],
                    "requiredOpenIndicators": meta.get("required_open_indicators"),
                    "uisComponentPolicy": meta.get("uis_component_policy"),
                    "flowPolicy": meta.get("flow_policy"),
                    "source": str(student_v3_path.as_posix()),
                },
                "summary": {
                    "top20Practical": [
                        {
                            "rank": _int_or_none(row.get("rank_practical_student_recruitment")),
                            "iso3": _text(row, "iso3"),
                            "saiMgimoV3Score": _num(row, "SAI_MGIMO_V3_SCORE"),
                            "studentRecruitmentStatus": _text(row, "student_recruitment_status"),
                        }
                        for _, row in practical.iterrows()
                    ],
                    "countries": int(len(student)),
                },
                "byCountry": by_country,
            }
        )

    raise FileNotFoundError(
        f"Missing {student_v3_path}; SAI_MGIMO_V3 must be built from student_attraction_v3.csv."
    )


def _student_flows_observed(full: pd.DataFrame, observed_path: Path | None = None) -> dict[str, Any]:
    by_country: dict[str, Any] = {}
    rows: list[dict[str, Any]] = []
    if observed_path and observed_path.exists() and observed_path.stat().st_size > 0:
        try:
            observed = pd.read_csv(observed_path)
        except pd.errors.EmptyDataError:
            observed = pd.DataFrame()
        for _, row in observed.iterrows():
            iso3 = _text(row, "iso3") or _text(row, "origin_iso3")
            if not iso3:
                continue
            item = _clean(row.to_dict())
            by_country[iso3] = item
            rows.append(item)
    return {
        "coverage": {
            "status": "not_available_country_level_mgimo" if not by_country else "partial",
            "source": "student_flows_observed.csv; factual country MGIMO student rows only.",
            "countriesWithObservedFlows": len(by_country),
        },
        "rows": rows,
        "byCountry": by_country,
    }


def _student_flows_modelled(full: pd.DataFrame, cfg: ProjectConfig, modelled_v3_path: Path | None = None) -> dict[str, Any]:
    if modelled_v3_path and modelled_v3_path.exists():
        try:
            flows = pd.read_csv(modelled_v3_path)
        except pd.errors.EmptyDataError:
            flows = pd.DataFrame()
        rows: list[dict[str, Any]] = []
        by_country: dict[str, Any] = {}
        for _, row in flows.iterrows():
            iso3 = _text(row, "origin_iso3") or _text(row, "iso3")
            item = _clean(
                {
                    "originIso3": iso3,
                    "originCountry": _text(row, "origin_country"),
                    "region": _text(row, "region"),
                    "originLat": _num(row, "origin_lat"),
                    "originLon": _num(row, "origin_lon"),
                    "destinationCity": _text(row, "destination_city") or "Moscow",
                    "destinationLat": _num(row, "destination_lat"),
                    "destinationLon": _num(row, "destination_lon"),
                    "flowType": _text(row, "flow_type") or "modelled_potential_not_observed",
                    "modelledPotentialIndex": _num(row, "modelled_potential_index"),
                    "strokeWidth": _num(row, "stroke_width"),
                    "saiMgimoV3Score": _num(row, "SAI_MGIMO_V3_SCORE"),
                    "rankPracticalStudentRecruitment": _int_or_none(row.get("rank_practical_student_recruitment")),
                    "studentRecruitmentStatus": _text(row, "student_recruitment_status"),
                    "dueDiligenceWarnings": _text(row, "due_diligence_warnings"),
                    "trace": {
                        "source_key": "student_flows_modelled_v3.csv",
                        "year": "2026/2035",
                        "raw_value": _num(row, "modelled_potential_index"),
                        "normalized_value": (_num(row, "modelled_potential_index") / 100.0) if _num(row, "modelled_potential_index") is not None else None,
                        "normalization_method": "0.72*SAI_MGIMO_V3_SCORE/100 + 0.28*lognorm(pop_15_24_latest)",
                        "weight": 1.0,
                        "score_type": "modelled_potential_not_observed_student_headcount",
                    },
                }
            )
            rows.append(item)
            if iso3:
                by_country[iso3] = item
        return {
            "model": {
                "name": "disabled_no_open_student_flow_source" if not rows else "SAI_MGIMO_V3",
                "source": str(modelled_v3_path.as_posix()),
                    "scoreType": "not_rendered_without_factual_open_country_student_flow_source" if not rows else "modelled_attraction_potential_from_open_indicators_not_mgimo_headcount",
                },
                "coverage": {
                    "status": "disabled_no_open_country_level_source" if not rows else "modelled_potential_not_observed",
                    "note": "Modelled arrows are not factual MGIMO student rows; factual flows remain in studentFlowsObserved only.",
                },
            "rows": rows,
            "byCountry": by_country,
        }

    return {
        "model": {
            "name": "disabled_no_open_student_flow_source",
            "source": str(modelled_v3_path.as_posix()) if modelled_v3_path else None,
            "scoreType": "not_rendered_without_factual_open_country_student_flow_source",
        },
        "coverage": {
            "status": "disabled_no_open_country_level_source",
            "note": "No flow arcs are generated without factual open country-level MGIMO student rows.",
        },
        "rows": [],
        "byCountry": {},
    }


def _sources(model_output_dir: Path, data_dir: Path) -> list[dict[str, Any]]:
    registry = _read_csv(Path(data_dir) / "reference" / "source_registry.csv")
    registry_by_provider: dict[str, dict[str, Any]] = {}
    registry_by_key: dict[str, dict[str, Any]] = {}
    if not registry.empty:
        for _, row in registry.iterrows():
            item = _clean(row.to_dict()) or {}
            key = str(item.get("source_id") or "")
            provider = str(item.get("name") or "")
            if key:
                registry_by_key[key] = item
            if provider:
                registry_by_provider[provider.lower()] = item

    def public_row(row: dict[str, Any]) -> dict[str, Any]:
        manifest_token = _term("source", "_manifest")
        reference_token = _term("snap", "shot")
        old_mode_token = _term("base", "line")
        key = row.get("source_key") or row.get("source_id") or row.get("id") or row.get("provider")
        if key and (manifest_token in str(key).lower() or reference_token in str(key).lower()):
            return {}
        provider = row.get("provider") or row.get("name") or key
        if provider and (manifest_token in str(provider).lower() or reference_token in str(provider).lower()):
            return {}
        registry_row = registry_by_key.get(str(key or "")) or registry_by_provider.get(str(provider or "").lower()) or {}
        url = row.get("url") or row.get("officialUrl") or registry_row.get("api_or_page_url") or registry_row.get("url")
        if url and (manifest_token in str(url).lower() or reference_token in str(url).lower()):
            return {}
        used_for = (
            row.get("used_for")
            or row.get("usedFor")
            or registry_row.get("used_for")
            or row.get("description")
            or row.get("indicatorGroup")
            or row.get("indicatorLabel")
        )
        description = row.get("description") or registry_row.get("notes") or row.get("sourceNote") or row.get("indicatorLabel") or used_for
        if isinstance(description, str):
            description = description.replace(old_mode_token, "current").replace(reference_token, "reference")
        if isinstance(used_for, str):
            used_for = used_for.replace(old_mode_token, "current").replace(reference_token, "reference")
        out = {
            "source_key": key,
            "provider": provider,
            "description": description,
            "usedFor": used_for,
            "mode": row.get("mode"),
            "url": url or "docs/data/model_outputs/current/country_scores_full.csv",
            "date": dt.date.today().isoformat(),
        }
        return _clean(out)

    manifest = _read_csv(model_output_dir / "source_manifest.csv")
    if manifest.empty:
        manifest = _read_csv(Path(data_dir) / "platform_snapshot" / "source_manifest.csv")
    if manifest.empty:
        return [public_row(row) for row in _records(registry)]
    rename = {
        "indicator_code": "indicatorCode",
        "indicator_label": "indicatorLabel",
        "indicator_group": "indicatorGroup",
        "official_url": "officialUrl",
        "source_note": "sourceNote",
        "latest_observed_year_in_run": "latestObservedYearInRun",
    }
    manifest = manifest.rename(columns={k: v for k, v in rename.items() if k in manifest.columns})
    if "indicatorGroup" in manifest.columns:
        manifest = manifest[~manifest["indicatorGroup"].astype(str).str.lower().eq("demography")].copy()
    rows = [row for row in (public_row(row) for row in _records(manifest)) if row]
    existing_keys = {row.get("source_key") for row in rows}
    for row in _records(registry):
        if row.get("source_id") not in existing_keys:
            public = public_row(row)
            if public:
                rows.append(public)
    return rows


def _methodology(cfg: ProjectConfig) -> dict[str, Any]:
    weights = cfg.weights()
    return {
        "version": SCHEMA_VERSION,
        "priorityFormula": "geometric_weighted_index",
        "normalization": {
            "qLow": float(cfg.get("normalization", "q_low", default=0.05)),
            "qHigh": float(cfg.get("normalization", "q_high", default=0.95)),
            "epsilon": float(cfg.get("normalization", "epsilon", default=0.05)),
        },
        "factors": [
            {"code": "I_MARKET", "label": "Market attractiveness", "weight": weights.get("I_MARKET")},
            {"code": "I_PROGRAM", "label": "Program fit", "weight": weights.get("I_PROGRAM")},
            {"code": "I_RUSCOMP", "label": "Russia compatibility", "weight": weights.get("I_RUSCOMP")},
            {"code": "I_ECO", "label": "Economic context", "weight": weights.get("I_ECO")},
            {"code": "I_FIN", "label": "Financial feasibility", "weight": weights.get("I_FIN")},
            {"code": "I_FEAS", "label": "Operational feasibility", "weight": weights.get("I_FEAS")},
            {"code": "I_HRSTRAT", "label": "Strategic HR fit", "weight": weights.get("I_HRSTRAT")},
        ],
        "policyNotes": [
            "Unfriendly, domestic Russia, existing full branches and non-sovereign/special territories are hard eligibility filters.",
            "In-preparation branch status is shown for governance workflow only and is not a scoring or finance bonus.",
            "Data-quality diagnostics are retained for QA metadata and exports, not for executive UI display.",
        ],
    }


def _metadata(
    full: pd.DataFrame,
    cfg: ProjectConfig,
    model_output_dir: Path,
    run_metadata: dict[str, Any],
    demography_meta: dict[str, Any],
) -> dict[str, Any]:
    qa_export_name = "country_data_quality_qa.csv"
    quality_cols = [
        c
        for c in [
            "iso3",
            "country",
            "DATAQ",
            "latest_observation_lag_years",
            "platform_data_coverage_pct",
        ]
        if c in full.columns
    ]
    if quality_cols:
        full[quality_cols].to_csv(model_output_dir / qa_export_name, index=False, encoding="utf-8-sig")
    return _clean(
        {
            "schemaVersion": SCHEMA_VERSION,
            "modelVersion": cfg.get("project", "version", default="0.3.0"),
            "baseYear": cfg.base_year,
            "targetYears": cfg.target_years,
            "generatedAt": dt.datetime.now().isoformat(timespec="seconds"),
            "summary": {
                "totalCountries": int(len(full)),
                "eligibleCountries": int(full["eligible"].astype(bool).sum()) if "eligible" in full else 0,
                "inPreparationCountries": int(full.get("has_mgimo_pipeline", pd.Series(False, index=full.index)).astype(bool).sum()),
                "demography": demography_meta,
            },
            "qa": {
                "dataQualityHiddenFromUi": True,
                "dataQualityExport": f"model_outputs/current/{qa_export_name}",
                "sourceErrors": run_metadata.get("source_errors"),
                "sourceWarnings": run_metadata.get("source_warnings"),
                "wdiQualityCoverage": run_metadata.get("wdi_quality_coverage"),
                "wgiQualityCoverage": run_metadata.get("wgi_quality_coverage"),
                "criticalQualityWarnings": run_metadata.get("critical_quality_warnings"),
                "qualityThresholds": run_metadata.get("quality_thresholds")
                or run_metadata.get("live_quality_thresholds")
                or {
                    "wdiMinCoverageShare": 0.75,
                    "wgiMinCoverageShare": 0.80,
                },
            },
            "modelOutputs": sorted(path.name for path in model_output_dir.glob("*.csv") if path.name != "source_manifest.csv"),
        }
    )


def _flatten_factor_values(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        rows: list[tuple[str, Any]] = []
        for key, child in value.items():
            child_key = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(_flatten_factor_values(child, child_key))
        return rows
    if isinstance(value, list):
        return [(prefix, json.dumps(_clean(value), ensure_ascii=False))]
    return [(prefix, value)]


def _is_factor_year_field(key: str) -> bool:
    return key.endswith("Year") or key.endswith(".year") or key.lower().endswith("_year")


def _year_key_candidates(key: str) -> list[str]:
    parts = key.split(".")
    base = parts[-1]
    return [
        f"{key}Year",
        f"{base}Year",
        f"{key}_year",
        f"{base}_year",
    ]


def _source_year_for_input(group: dict[str, Any], key: str, base_year: Any) -> Any:
    for candidate in _year_key_candidates(key):
        value = group.get(candidate)
        if _finite(value):
            return int(float(value))
    for year in ("2026", "2035", "2050"):
        if year in key:
            return int(year)
    return base_year


def _hidden_trace_key(key: str) -> bool:
    return key == "__normalized" or key.startswith("__normalized.")


def _get_nested_value(value: Any, path: str | None) -> Any:
    if path is None:
        return None
    current = value
    for part in str(path).split("."):
        if isinstance(current, dict) and part in current:
            current = current.get(part)
        else:
            return None
    return current


def _trace_meta_for_input(group_name: str, key: str) -> dict[str, Any]:
    return FACTOR_INPUT_TRACE_META.get(group_name, {}).get(key, {})


def _trace_input_weight(group_name: str, key: str) -> float | None:
    meta = _trace_meta_for_input(group_name, key)
    if "weight" not in meta:
        return None
    weight = meta.get("weight")
    if _finite(weight):
        return float(weight)
    return None


def _trace_scoring_role(group_name: str, key: str) -> str:
    meta = _trace_meta_for_input(group_name, key)
    if meta.get("role"):
        return str(meta["role"])
    weight = _trace_input_weight(group_name, key)
    if weight is None or weight == 0:
        return "source_context_not_directly_weighted"
    return "direct_factor_formula_component"


def _trace_weight_note(group_name: str, key: str) -> str:
    role = _trace_scoring_role(group_name, key)
    weight = _trace_input_weight(group_name, key)
    if weight is None:
        return "not a direct additive term; see factor formula"
    if weight == 0:
        return "0%: reference/status/context value, not an index bonus"
    if role == "direct_penalty":
        return "direct formula penalty; negative sign is part of formula"
    return "within-factor formula weight"


def _keep_factor_trace_row(row_data: dict[str, Any]) -> bool:
    weight = row_data.get("input_weight")
    if _finite(weight) and float(weight) != 0:
        return True
    return row_data.get("scoring_role") in {
        "multiplicative_gate",
        "hard_filter_context",
        "reference_status_not_scored",
    }


def _normalization_method_for_input(group_name: str, key: str, value: Any) -> str:
    meta = _trace_meta_for_input(group_name, key)
    if meta.get("method"):
        return str(meta["method"])
    if isinstance(value, bool):
        return "binary_flag"
    if isinstance(value, str):
        return "categorical_reference"
    if key.startswith("N_") or key.startswith("I_") or "Score" in key or "Factor" in key or "profiles." in key:
        return "prepared_0_1_score"
    return "raw_input_context_for_factor_model"


def _normalized_value_for_input(group_name: str, group: dict[str, Any], key: str, value: Any) -> Any:
    meta = _trace_meta_for_input(group_name, key)
    if "normalized" in meta:
        normalized = _get_nested_value(group, meta.get("normalized"))
        return float(normalized) if _finite(normalized) else None
    if _finite(value):
        numeric = float(value)
        if 0 <= numeric <= 1:
            return numeric
    return None


def _factor_inputs_long(payload: dict[str, Any]) -> list[dict[str, Any]]:
    countries = {row.get("iso3"): row for row in payload.get("countries", []) if isinstance(row, dict)}
    factor_inputs = payload.get("factorInputs") or {}
    base_year = payload.get("metadata", {}).get("baseYear")
    rows: list[dict[str, Any]] = []
    for iso3, country in countries.items():
        groups = factor_inputs.get(iso3) or {}
        for factor_key, group_name in FACTOR_GROUPS.items():
            group = groups.get(group_name) or {}
            input_rows = [
                (key, value)
                for key, value in _flatten_factor_values(group)
                if not _is_factor_year_field(key) and not _hidden_trace_key(key)
            ]
            for input_key, value in input_rows:
                row_data = {
                    "iso3": iso3,
                    "country": country.get("name"),
                    "factor_key": factor_key,
                    "factor_group": group_name,
                    "input_key": input_key,
                    "raw_value": value,
                    "normalized_value": _normalized_value_for_input(group_name, group, input_key, value),
                    "normalization_method": _normalization_method_for_input(group_name, input_key, value),
                    "input_weight": _trace_input_weight(group_name, input_key),
                    "factor_weight": (payload.get("weightsDefault") or {}).get(factor_key),
                    "scoring_role": _trace_scoring_role(group_name, input_key),
                    "weight_note": _trace_weight_note(group_name, input_key),
                    "year": _source_year_for_input(group, input_key, base_year),
                    "source_key": FACTOR_GROUP_SOURCES.get(group_name),
                    "observation_status": FACTOR_GROUP_OBSERVATION.get(group_name, "modelled"),
                }
                if not _keep_factor_trace_row(row_data):
                    continue
                cleaned = _clean(row_data)
                if row_data["normalized_value"] is None:
                    cleaned["normalized_value"] = None
                rows.append(cleaned)
    return rows


def _student_attraction_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    countries = {row.get("iso3"): row for row in payload.get("countries", []) if isinstance(row, dict)}
    attraction = (payload.get("studentAttraction") or {}).get("byCountry") or {}
    rows: list[dict[str, Any]] = []
    for iso3, item in attraction.items():
        country = countries.get(iso3, {})
        rows.append(
            _clean(
                {
                    "iso3": iso3,
                    "country": country.get("name"),
                    "model": item.get("model"),
                    "student_attraction_index": item.get("saiMgimoV3Score", item.get("attractionScore")),
                    "rank_practical_student_recruitment": item.get("rankPracticalStudentRecruitment"),
                    "rank_reference_all": item.get("rankReferenceAll"),
                    "student_recruitment_status": item.get("studentRecruitmentStatus"),
                    "addressable_market_students_2026": (item.get("addressableMarketStudents") or {}).get("2026"),
                    "student_pool_2026": (item.get("studentPool") or {}).get("2026"),
                    "tertiary_enrollment_gross": (item.get("education") or {}).get("tertiaryEnrollmentGross"),
                }
            )
        )
    return rows


def _student_flow_rows(payload: dict[str, Any], key: str, evidence: str) -> list[dict[str, Any]]:
    countries = {row.get("iso3"): row for row in payload.get("countries", []) if isinstance(row, dict)}
    explicit_rows = (payload.get(key) or {}).get("rows") or []
    if explicit_rows:
        return [
            _clean(
                {
                    **row,
                    "evidence": evidence,
                    "iso3": row.get("originIso3") or row.get("iso3"),
                    "country": row.get("originCountry") or (countries.get(row.get("originIso3") or row.get("iso3")) or {}).get("name"),
                }
            )
            for row in explicit_rows
        ]
    flows = (payload.get(key) or {}).get("byCountry") or {}
    rows: list[dict[str, Any]] = []
    for iso3, item in flows.items():
        country = countries.get(iso3, {})
        if evidence == "observed":
            rows.append(
                _clean(
                    {
                        "iso3": iso3,
                        "country": country.get("name"),
                        "evidence": evidence,
                        "observed_students": item.get("inboundMobileStudents"),
                        "inbound_mobility_ratio": item.get("inboundMobilityRatio"),
                    }
                )
            )
            continue
        for point in item.get("series") or []:
            rows.append(
                _clean(
                    {
                        "iso3": iso3,
                        "country": country.get("name"),
                        "evidence": evidence,
                        "year": point.get("year"),
                        "study_year": point.get("studyYear"),
                        "modelled_expected_students": point.get("expectedStudents"),
                    }
                )
            )
    return rows


def write_dashboard_auxiliary_exports(payload: dict[str, Any], data_dir: str | Path) -> None:
    out_dir = Path(data_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    factor_rows = _factor_inputs_long(payload)
    (out_dir / "factor_inputs_long.json").write_text(
        json.dumps(factor_rows, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(factor_rows).to_csv(out_dir / "factor_inputs_long.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(_student_attraction_rows(payload)).to_csv(out_dir / "student_attraction.csv", index=False, encoding="utf-8-sig")
    observed_rows = _student_flow_rows(payload, "studentFlowsObserved", "observed")
    observed_columns = [
        "iso3",
        "country",
        "evidence",
        "originIso3",
        "originCountry",
        "observedStudents",
        "source",
        "year",
    ]
    pd.DataFrame(observed_rows, columns=observed_columns if not observed_rows else None).to_csv(
        out_dir / "student_flows_observed.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(_student_flow_rows(payload, "studentFlowsModelled", "modelled")).to_csv(
        out_dir / "student_flows_modelled.csv",
        index=False,
        encoding="utf-8-sig",
    )


def build_dashboard_payload(
    cfg: ProjectConfig,
    data_dir: str | Path,
    model_output_dir: str | Path,
    wpp_age_sex_historical_path: str | Path | None = None,
    wpp_age_sex_projection_path: str | Path | None = None,
    raw_demography_path: str | Path | None = None,
) -> dict[str, Any]:
    data_dir = Path(data_dir)
    model_output_dir = Path(model_output_dir)
    public_data_dir = model_output_dir.parent.parent if model_output_dir.name == "current" else model_output_dir.parent
    student_v3_path = public_data_dir / "student_attraction_v3.csv"
    student_model_meta_path = public_data_dir / "student_model_v3_metadata.json"
    student_flows_observed_path = public_data_dir / "student_flows_observed.csv"
    student_flows_modelled_v3_path = public_data_dir / "student_flows_modelled_v3.csv"
    full = _read_csv(model_output_dir / "country_scores_full.csv")
    if full.empty:
        raise FileNotFoundError(f"Missing or empty model output: {model_output_dir / 'country_scores_full.csv'}")
    geo_coords = _geojson_label_coords(public_data_dir)
    run_metadata = _read_json(model_output_dir / "run_metadata.json")
    raw_demo_path = Path(raw_demography_path) if raw_demography_path is not None else None
    wpp_historical_path = Path(wpp_age_sex_historical_path) if wpp_age_sex_historical_path is not None else None
    wpp_projection_path = Path(wpp_age_sex_projection_path) if wpp_age_sex_projection_path is not None else None
    demography_series, age_sex_pyramid, demography_meta = _load_demography(
        full,
        wpp_age_sex_historical_path=wpp_historical_path,
        wpp_age_sex_projection_path=wpp_projection_path,
        raw_demography_path=raw_demo_path,
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "countries": _country_rows(full, geo_coords=geo_coords),
        "factorInputs": _factor_inputs(full),
        "weightsDefault": cfg.weights(),
        "eligibility": _eligibility(full, cfg),
        "demographySeries": demography_series,
        "ageSexPyramid": age_sex_pyramid,
        "branchMarkers": _branch_markers(full),
        "studentAttraction": _student_attraction(full, student_v3_path=student_v3_path, student_meta_path=student_model_meta_path),
        "studentFlowsObserved": _student_flows_observed(full, observed_path=student_flows_observed_path),
        "studentFlowsModelled": _student_flows_modelled(full, cfg, modelled_v3_path=student_flows_modelled_v3_path),
        "sources": _sources(model_output_dir, data_dir),
        "methodology": _methodology(cfg),
        "metadata": _metadata(full, cfg, model_output_dir, run_metadata, demography_meta),
    }
    return _clean(payload)


def write_dashboard_payload(payload: dict[str, Any], canonical_path: str | Path, alias_path: str | Path | None = None) -> tuple[Path, Path | None]:
    canonical = Path(canonical_path)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
    canonical.write_text(text, encoding="utf-8")
    alias = Path(alias_path) if alias_path is not None else None
    if alias is not None:
        alias.parent.mkdir(parents=True, exist_ok=True)
        alias.write_text(text, encoding="utf-8")
    write_dashboard_auxiliary_exports(payload, canonical.parent)
    return canonical, alias
