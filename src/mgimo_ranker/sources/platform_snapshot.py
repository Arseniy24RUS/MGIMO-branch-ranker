from __future__ import annotations

from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


COLUMN_MAP = {
    "Country Code": "iso3",
    "Country Name": "country",
    "Region": "region",
    "IncomeGroup": "income_group",
    "gdp_pc_ppp": "gdp_pc_ppp_current",
    "gdp_growth": "gdp_growth_real",
    "trade_gdp": "trade_percent_gdp",
    "services_share": "services_value_added",
    "urban_share": "urban_population_pct",
    "internet_users": "internet_users",
    "tertiary_enrollment": "tertiary_enrollment_gross",
    "gov_effectiveness": "wgi_government_effectiveness",
    "rule_of_law": "wgi_rule_of_law",
    "reg_quality": "wgi_regulatory_quality",
    "pol_stability": "wgi_political_stability",
    "price_level_index": "price_level_index",
    "population_total": "population_total_current",
    "population_total_2026": "population_total_2026",
    "population_total_2035": "population_total_2035",
    "population_total_2050": "population_total_2050",
    "student_pool_2026": "pop_15_24_2026",
    "student_pool_2035": "pop_15_24_2035",
    "student_pool_2050": "pop_15_24_2050",
}

YEAR_SOURCE_COLUMNS = {
    "population_total_year": "population_total_current_year",
    "gdp_pc_ppp_year": "gdp_pc_ppp_current_year",
    "gdp_growth_year": "gdp_growth_real_year",
    "trade_gdp_year": "trade_percent_gdp_year",
    "services_share_year": "services_value_added_year",
    "urban_share_year": "urban_population_pct_year",
    "internet_users_year": "internet_users_year",
    "tertiary_enrollment_year": "tertiary_enrollment_gross_year",
    "gov_effectiveness_year": "wgi_government_effectiveness_year",
    "rule_of_law_year": "wgi_rule_of_law_year",
    "reg_quality_year": "wgi_regulatory_quality_year",
    "pol_stability_year": "wgi_political_stability_year",
    "price_level_index_year": "price_level_index_year",
}


def _latest_observation_lag(row: pd.Series, base_year: int) -> float:
    year_vals = []
    for col in YEAR_SOURCE_COLUMNS.values():
        val = pd.to_numeric(row.get(col, np.nan), errors="coerce")
        if pd.notna(val):
            year_vals.append(float(val))
    if not year_vals:
        return np.nan
    # Median is deliberately used instead of max to avoid hiding stale governance data behind one fresh indicator.
    return max(0.0, float(base_year) - float(np.nanmedian(year_vals)))


def load_platform_snapshot(data_dir: str | Path, panel_path: str | Path | None = None, base_year: int = 2026) -> pd.DataFrame:
    """Load the full offline country panel produced by ``mgimo_branch_platform_project``.

    The platform project already contains a reproducible World Bank snapshot for 217 economies.
    This adapter maps the platform column nomenclature to the richer v0.3 analytical core used
    by ``mgimo_ranker``. It does not treat the platform's own scores as model inputs; only the
    underlying country features and diagnostics are imported.
    """
    if panel_path is None:
        panel_path = Path(data_dir) / "platform_snapshot" / "country_master_panel.csv"
    panel_path = Path(panel_path)
    if not panel_path.exists():
        raise FileNotFoundError(
            f"Platform snapshot panel was not found: {panel_path}. "
            "Provide --platform-panel or place country_master_panel.csv under data/platform_snapshot/."
        )
    raw = pd.read_csv(panel_path)
    out = raw.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in raw.columns}).copy()
    out = out.rename(columns={k: v for k, v in YEAR_SOURCE_COLUMNS.items() if k in out.columns})

    if "iso3" not in out.columns:
        raise ValueError("Platform snapshot panel must contain Country Code / iso3")
    out["iso3"] = out["iso3"].astype(str).str.upper()

    # Preserve platform diagnostics without allowing them to drive the new score directly.
    if "student_pool_2026" in raw.columns:
        out["student_pool_platform_2026"] = raw["student_pool_2026"]
    if "student_pool_2035" in raw.columns:
        out["student_pool_platform_2035"] = raw["student_pool_2035"]
    if "student_pool_2050" in raw.columns:
        out["student_pool_platform_2050"] = raw["student_pool_2050"]
    if "data_coverage_pct" in raw.columns:
        out["platform_data_coverage_pct"] = pd.to_numeric(raw["data_coverage_pct"], errors="coerce")
    # Add gdp_ppp_current when the snapshot only supplies GDP per capita and population.
    if "gdp_ppp_current" not in out.columns and {"gdp_pc_ppp_current", "population_total_current"}.issubset(out.columns):
        out["gdp_ppp_current"] = pd.to_numeric(out["gdp_pc_ppp_current"], errors="coerce") * pd.to_numeric(
            out["population_total_current"], errors="coerce"
        )

    # Snapshot youth columns are retained only until the mandatory WPP 2024 overlay replaces them.
    for year in [2026, 2035, 2050]:
        src = f"pop_15_24_{year}"
        if src in out.columns:
            out[f"student_pool_model_input_{year}"] = out[src]

    out["latest_observation_lag_years"] = out.apply(_latest_observation_lag, axis=1, base_year=base_year)
    out["source_panel"] = "platform_snapshot_world_bank_217_economies"

    # Platform flags are copied as diagnostics; the v0.3 statutory filters are recomputed from references.
    platform_flag_cols = ["is_unfriendly", "has_existing_mgimo_branch", "is_domestic_russia", "is_non_sovereign_or_special", "eligible", "eligibility_reason"]
    for col in platform_flag_cols:
        if col in raw.columns:
            out[f"platform_{col}"] = raw[col]
    out = out.drop(columns=[c for c in platform_flag_cols if c in out.columns], errors="ignore")

    return out


def copy_snapshot_source_manifest(data_dir: str | Path, output_dir: str | Path) -> Path | None:
    src = Path(data_dir) / "platform_snapshot" / "source_manifest.csv"
    if not src.exists():
        return None
    dst = Path(output_dir) / "source_manifest.csv"
    dst.parent.mkdir(parents=True, exist_ok=True)
    manifest = pd.read_csv(src)
    if "indicator_group" in manifest.columns:
        manifest = manifest[~manifest["indicator_group"].astype(str).str.lower().eq("demography")].copy()
    wpp_row = {
        "provider": "UN World Population Prospects 2024",
        "indicator_code": "UN_WPP2024.PopulationBySingleAgeSex.Medium",
        "indicator_label": "Population by single age, sex and year",
        "indicator_group": "demography",
        "official_url": "https://population.un.org/wpp/",
        "source_note": "Official WPP 2024 bulk files supply total population, 15-24 cohort, student pool inputs and age-sex pyramids.",
        "raw_file": r"C:\Codex projects\gdam_research\data\raw\wpp2024",
        "latest_observed_year_in_run": 2024,
    }
    manifest = pd.concat([pd.DataFrame([wpp_row]), manifest], ignore_index=True)
    manifest.to_csv(dst, index=False, encoding="utf-8-sig")
    return dst
