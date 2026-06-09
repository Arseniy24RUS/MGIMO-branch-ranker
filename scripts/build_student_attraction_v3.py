#!/usr/bin/env python3
"""Build SAI_MGIMO_V3 from factual open indicators in the dashboard payload.

The modelled flow output is a visual attraction-potential layer only. It is not
an observed MGIMO student headcount and stays separate from factual country-level
student flow rows.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = ROOT / "docs/data/mgimo_dashboard_data.json"
OUT_CSV = ROOT / "docs/data/student_attraction_v3.csv"
OUT_FLOWS = ROOT / "docs/data/student_flows_modelled_v3.csv"
OUT_META = ROOT / "docs/data/student_model_v3_metadata.json"
UIS_CSV = ROOT / "data/education/uis_outbound_mobility.csv"

MOBILITY_UIS_KEY = "A_OUTBOUND_MOBILITY_UIS"

WEIGHTS = {
    "A_YOUTH_OPPORTUNITY": 0.50,
    MOBILITY_UIS_KEY: 0.16,
    "A_LEGAL_PARTNERSHIP_CONTEXT": 0.12,
    "A_PROGRAM_RELEVANCE": 0.08,
    "A_AFFORDABILITY_ACCESS": 0.06,
    "A_DIGITAL_REACH": 0.04,
    "A_DATAQ": 0.04,
}

REQUIRED_SCORE_COLUMNS = [
    "pop_15_24_latest",
    "pop_15_24_growth_10y_pct",
    "uis_outbound_mobility_ratio",
    "internet_users_pct",
    "gdp_pc_ppp_current",
    "program_relevance_score",
]

FLOW_COLUMNS = [
    "origin_iso3",
    "origin_country",
    "region",
    "origin_lat",
    "origin_lon",
    "destination_city",
    "destination_lat",
    "destination_lon",
    "flow_type",
    "modelled_potential_index",
    "stroke_width",
    "SAI_MGIMO_V3_SCORE",
    "rank_practical_student_recruitment",
    "student_recruitment_status",
    "due_diligence_warnings",
    "source",
    "year",
]


def _num(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def _minmax(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    lo = values.quantile(0.05)
    hi = values.quantile(0.95)
    out = pd.Series(np.nan, index=values.index, dtype=float)
    if np.isfinite(lo) and np.isfinite(hi) and hi != lo:
        out = ((values - lo) / (hi - lo)).clip(0, 1)
    return out


def _lognorm(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return _minmax(np.log1p(values.clip(lower=0)))


def _load_uis_latest(path: Path = UIS_CSV) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing required UNESCO UIS file: {path}")
    uis = pd.read_csv(path)
    required = {
        "iso3",
        "country",
        "year",
        "outbound_mobility_ratio_tertiary",
        "source_key",
        "observation_status",
    }
    missing = required - set(uis.columns)
    if missing:
        raise ValueError(f"UNESCO UIS file lacks required columns: {sorted(missing)}")
    uis["iso3"] = uis["iso3"].astype(str).str.upper().str.strip()
    uis["year"] = pd.to_numeric(uis["year"], errors="coerce")
    uis["outbound_mobility_ratio_tertiary"] = pd.to_numeric(
        uis["outbound_mobility_ratio_tertiary"],
        errors="coerce",
    )
    uis = uis.dropna(subset=["iso3", "year", "outbound_mobility_ratio_tertiary"])
    if uis.empty:
        raise ValueError("UNESCO UIS file contains no usable outbound mobility rows.")
    latest = (
        uis.sort_values(["iso3", "year"])
        .drop_duplicates("iso3", keep="last")
        .rename(
            columns={
                "outbound_mobility_ratio_tertiary": "uis_outbound_mobility_ratio",
                "year": "uis_outbound_mobility_year",
                "source_key": "uis_source_key",
                "observation_status": "uis_observation_status",
            }
        )
    )
    return latest[
        [
            "iso3",
            "uis_outbound_mobility_ratio",
            "uis_outbound_mobility_year",
            "uis_source_key",
            "uis_observation_status",
        ]
    ]


def _latest_actual(series: dict) -> dict:
    actual = [row for row in series.get("actual", []) if _num(row.get("pop_15_24")) is not None]
    if not actual:
        return {}
    return max(actual, key=lambda row: int(row.get("year") or 0))


def _growth_10y(series: dict, latest_year: int | None, latest_value: float | None) -> tuple[float | None, int | None]:
    if latest_year is None or latest_value in (None, 0):
        return None, None
    actual = series.get("actual", [])
    target_year = latest_year - 10
    candidates = [
        row for row in actual
        if _num(row.get("pop_15_24")) not in (None, 0) and int(row.get("year") or 0) <= latest_year
    ]
    if not candidates:
        return None, None
    base = min(candidates, key=lambda row: abs(int(row.get("year") or 0) - target_year))
    base_value = _num(base.get("pop_15_24"))
    base_year = int(base.get("year") or 0)
    if base_value in (None, 0) or base_year >= latest_year:
        return None, None
    return (latest_value / base_value - 1) * 100, base_year


def _status(row: pd.Series) -> str:
    if bool(row.get("is_domestic_russia")):
        return "domestic_excluded"
    if bool(row.get("is_unfriendly_430r")):
        return "unfriendly_reference_only"
    if bool(row.get("is_non_sovereign_or_special")):
        return "special_territory_reference_only"
    if not bool(row.get("has_required_open_data")):
        return "data_unavailable"
    if bool(row.get("in_preparation")):
        return "in_preparation_but_ranked"
    return "practical_priority_pool"


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    uis_latest = _load_uis_latest()
    rows: list[dict] = []
    for country in payload.get("countries", []):
        iso = country.get("iso3")
        fi = payload.get("factorInputs", {}).get(iso, {})
        rc = fi.get("russiaCompatibility", {})
        econ = fi.get("economy", {})
        feas = fi.get("feasibility", {})
        market = fi.get("market", {})
        dem_series = payload.get("demographySeries", {}).get(iso, {})
        latest = _latest_actual(dem_series)
        latest_year = int(latest.get("year")) if latest.get("year") else None
        pop_latest = _num(latest.get("pop_15_24"))
        growth, base_year = _growth_10y(dem_series, latest_year, pop_latest)
        coords = country.get("coordinates") or {}
        is_unfriendly = bool(rc.get("isUnfriendly", False))
        is_domestic = bool(rc.get("isDomesticRussia", False)) or iso == "RUS"
        is_special = bool(rc.get("isNonSovereignOrSpecial", False))
        rows.append({
            "iso3": iso,
            "country": country.get("name"),
            "region": country.get("region"),
            "income_group": country.get("incomeGroup"),
            "latitude": coords.get("lat"),
            "longitude": coords.get("lon"),
            "branch_recommendation_category": country.get("recommendationCategory"),
            "branch_priority_score": country.get("priorityScore"),
            "is_unfriendly_430r": is_unfriendly,
            "is_domestic_russia": is_domestic,
            "is_non_sovereign_or_special": is_special,
            "has_existing_mgimo_presence": bool(rc.get("hasExistingMgimoBranch", False)),
            "in_preparation": bool(rc.get("inPreparation", False)),
            "pop_15_24_latest": pop_latest,
            "pop_15_24_latest_year": latest_year,
            "pop_15_24_base_year": base_year,
            "pop_15_24_growth_10y_pct": growth,
            "student_pool_latest": _num(latest.get("student_pool")),
            "student_pool_latest_year": latest_year,
            "internet_users_pct": _num(feas.get("internetUsersPct")),
            "gdp_pc_ppp_current": _num(econ.get("gdpPcPppCurrent")),
            "program_relevance_score": _num(fi.get("program", {}).get("programFit")) or _num(country.get("program", {}).get("fitScore")),
            "score_source_policy": "open_api_factual_only",
        })
    df = pd.DataFrame(rows)
    df = df.merge(uis_latest, on="iso3", how="left")
    hard_filter = df[["is_unfriendly_430r", "is_domestic_russia", "is_non_sovereign_or_special"]].astype(bool).any(axis=1)
    df["has_required_open_data"] = df[REQUIRED_SCORE_COLUMNS].notna().all(axis=1)
    scoreable = ~hard_filter & df["has_required_open_data"]

    youth_size = _lognorm(df["pop_15_24_latest"])
    youth_growth = _minmax(df["pop_15_24_growth_10y_pct"])
    outbound_mobility = _minmax(df["uis_outbound_mobility_ratio"])
    internet = _minmax(df["internet_users_pct"])
    gdp = _lognorm(df["gdp_pc_ppp_current"])

    df["A_YOUTH_OPPORTUNITY"] = 0.70 * youth_size + 0.30 * youth_growth
    df[MOBILITY_UIS_KEY] = outbound_mobility
    df["A_LEGAL_PARTNERSHIP_CONTEXT"] = np.where(hard_filter, 0.0, 1.0)
    df["A_PROGRAM_RELEVANCE"] = pd.to_numeric(df["program_relevance_score"], errors="coerce").clip(0, 1)
    df["A_AFFORDABILITY_ACCESS"] = gdp
    df["A_DIGITAL_REACH"] = internet
    df["dataq_required_available"] = df[REQUIRED_SCORE_COLUMNS].notna().sum(axis=1)
    df["dataq_required_total"] = len(REQUIRED_SCORE_COLUMNS)
    df["A_DATAQ"] = df["dataq_required_available"] / df["dataq_required_total"]

    component_cols = list(WEIGHTS)
    df.loc[~scoreable, component_cols] = np.nan
    df["SAI_MGIMO_V3_SCORE"] = np.nan
    weighted = sum(df[col] * weight for col, weight in WEIGHTS.items() if weight > 0)
    df.loc[scoreable, "SAI_MGIMO_V3_SCORE"] = weighted[scoreable] * 100
    df["practical_recruitment_eligible"] = scoreable
    df["student_recruitment_status"] = df.apply(_status, axis=1)
    df["rank_practical_student_recruitment"] = df.loc[scoreable, "SAI_MGIMO_V3_SCORE"].rank(ascending=False, method="first").astype("Int64")
    df["rank_reference_all"] = df["rank_practical_student_recruitment"]

    warnings = []
    for _, row in df.iterrows():
        row_warnings = []
        if row["is_unfriendly_430r"]:
            row_warnings.append("hard_filter_unfriendly_430r")
        if row["is_domestic_russia"]:
            row_warnings.append("domestic_russia_excluded")
        if row["is_non_sovereign_or_special"]:
            row_warnings.append("special_territory")
        if not row["has_required_open_data"]:
            row_warnings.append("insufficient_open_api_indicators")
        warnings.append(";".join(row_warnings))
    df["due_diligence_warnings"] = warnings

    columns = [
        "rank_practical_student_recruitment",
        "rank_reference_all",
        "iso3",
        "country",
        "region",
        "income_group",
        "student_recruitment_status",
        "SAI_MGIMO_V3_SCORE",
        *component_cols,
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
        "is_unfriendly_430r",
        "is_domestic_russia",
        "is_non_sovereign_or_special",
        "has_existing_mgimo_presence",
        "in_preparation",
        "has_required_open_data",
        "due_diligence_warnings",
        "latitude",
        "longitude",
    ]
    out = df[columns].sort_values(
        ["rank_practical_student_recruitment", "country"],
        na_position="last",
    )
    flow_source = out[out["rank_practical_student_recruitment"].notna()].copy()
    if not flow_source.empty:
        youth_norm = _lognorm(flow_source["pop_15_24_latest"]).fillna(0)
        sai_norm = (pd.to_numeric(flow_source["SAI_MGIMO_V3_SCORE"], errors="coerce") / 100).fillna(0)
        flow_source["modelled_potential_index"] = (0.72 * sai_norm + 0.28 * youth_norm).clip(0, 1) * 100
        flow_source["stroke_width"] = 0.65 + (flow_source["modelled_potential_index"] / 100) * 2.35
        flows = flow_source.assign(
            origin_iso3=flow_source["iso3"],
            origin_country=flow_source["country"],
            origin_lat=flow_source["latitude"],
            origin_lon=flow_source["longitude"],
            destination_city="Moscow",
            destination_lat=55.7558,
            destination_lon=37.6176,
            flow_type="modelled_potential_not_observed_mgimo_students",
            source="student_attraction_v3.csv",
            year="latest open indicators",
        )[FLOW_COLUMNS]
    else:
        flows = pd.DataFrame(columns=FLOW_COLUMNS)
    return out, flows


if __name__ == "__main__":
    out, flows = build()
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_CSV, index=False)
    flows.to_csv(OUT_FLOWS, index=False)
    meta = {
        "model_name": "SAI_MGIMO_V3",
        "score_type": "open-data index from observed public indicators; not MGIMO student headcount",
        "weights": WEIGHTS,
        "hard_filters": ["unfriendly_430r", "domestic_russia", "non_sovereign_or_special"],
        "required_open_indicators": REQUIRED_SCORE_COLUMNS,
        "uis_component_policy": {
            "component": MOBILITY_UIS_KEY,
            "source_key": "unesco_uis_uis006_mor_5t8_40510",
            "source_name": "UNESCO DataHub UIS",
            "dataset_id": "uis006",
            "indicator_id": "MOR.5T8.40510",
            "indicator_label": "Outbound mobility ratio, all regions, both sexes (UIS estimate) (%)",
            "missing_country_policy": "countries without a UIS row receive no SAI score or rank",
        },
        "flow_policy": "modelled map arrows show attraction potential from open indicators; they are not factual MGIMO student headcounts",
        "top20_practical": out.head(20)[[
            "rank_practical_student_recruitment",
            "iso3",
            "country",
            "SAI_MGIMO_V3_SCORE",
            "student_recruitment_status",
        ]].to_dict(orient="records"),
    }
    OUT_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {OUT_CSV}")
    print(f"saved {OUT_FLOWS}")
