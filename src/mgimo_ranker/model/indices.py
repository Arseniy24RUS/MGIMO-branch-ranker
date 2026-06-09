from __future__ import annotations

import numpy as np
import pandas as pd

from mgimo_ranker.utils import geometric_score, robust_norm


INDEX_COLUMNS = ["I_MARKET", "I_PROGRAM", "I_DEM", "I_ECO", "I_RUSCOMP", "I_FIN", "I_FEAS", "I_HRSTRAT"]
PROFILE_COLUMNS = [
    "I_PROFILE_DIPLO_ANALYTIC",
    "I_PROFILE_ECON_LEGAL",
    "I_PROFILE_DIGITAL_FINANCE",
    "I_PROFILE_ENERGY_LOGISTICS",
]
PROFILE_LABELS = {
    "I_PROFILE_DIPLO_ANALYTIC": "diplomatic_analytic",
    "I_PROFILE_ECON_LEGAL": "economic_legal",
    "I_PROFILE_DIGITAL_FINANCE": "digital_finance_business_informatics",
    "I_PROFILE_ENERGY_LOGISTICS": "energy_logistics",
}


def _present_cols(df: pd.DataFrame, cols: list[str]) -> list[str]:
    return [c for c in cols if c in df.columns]


def compute_data_quality(df: pd.DataFrame) -> pd.Series:
    """Share of key analytical fields observed in source-backed inputs.

    Optional fields are included when present in the dataset. This means a richer
    live dataset is judged against a richer evidence base, whereas a minimal
    fixture remains testable.
    """
    key_cols = [
        "pop_15_24_2026",
        "pop_15_24_2035",
        "pop_15_24_2050",
        "tertiary_enrollment_gross",
        "secondary_completion_upper",
        "gdp_ppp_current",
        "gdp_pc_ppp_current",
        "gdp_growth_real",
        "inflation_cpi",
        "unemployment",
        "internet_users",
        "wgi_political_stability",
        "wgi_government_effectiveness",
        "wgi_regulatory_quality",
        "wgi_rule_of_law",
        "trade_percent_gdp",
        "services_value_added",
        "price_level_index",
    ]
    optional_if_present = [
        "gender_parity_tertiary",
        "inbound_mobile_students",
        "inbound_mobility_ratio",
        "urban_population_pct",
        "lpi_overall",
        "price_level_index",
        "partner_universities_mgimo_count",
    ]
    work = df.copy()
    if "secondary_completion_upper_is_model_prior" in work.columns and "secondary_completion_upper" in work.columns:
        prior_mask = work["secondary_completion_upper_is_model_prior"].fillna(False).astype(bool)
        work.loc[prior_mask, "secondary_completion_upper"] = np.nan
    cols = _present_cols(work, key_cols + optional_if_present)
    if not cols:
        return pd.Series(0.0, index=df.index)
    observed_share = work[cols].notna().mean(axis=1).clip(0, 1)
    stale_penalty = pd.Series(0.0, index=df.index)
    if "latest_observation_lag_years" in df.columns:
        lag = pd.to_numeric(df["latest_observation_lag_years"], errors="coerce")
        stale_penalty = (lag.fillna(0).clip(lower=0) / 10.0).clip(0, 0.20)
    return (observed_share - stale_penalty).clip(0, 1)


def _gender_parity_score(series: pd.Series) -> pd.Series:
    gpi = pd.to_numeric(series, errors="coerce")
    return (1.0 - ((gpi - 1.0).abs() / 0.50)).clip(0, 1)


def _ratio01(series: pd.Series, upper: float = 1.0, lower: float = 0.0) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce") / 100.0
    return s.clip(lower, upper)


def _affordability_factor(df: pd.DataFrame) -> pd.Series:
    gdp_pc = pd.to_numeric(df.get("gdp_pc_ppp_current", pd.Series(np.nan, index=df.index)), errors="coerce")
    # Smooth income channel: below roughly 18k PPP dollars, self-funded international education becomes substantially harder.
    x = np.log(gdp_pc.clip(lower=500))
    center = np.log(18000)
    return pd.Series(1.0 / (1.0 + np.exp(-(x - center) / 0.90)), index=df.index).clip(0.05, 1.0)


def compute_indices(features: pd.DataFrame, q_low: float = 0.05, q_high: float = 0.95) -> pd.DataFrame:
    df = features.copy()
    numeric_cols = [
        "pop_15_24_2026",
        "pop_15_24_2035",
        "pop_15_24_2050",
        "tertiary_enrollment_gross",
        "secondary_completion_upper",
        "school_enrollment_secondary",
        "gender_parity_tertiary",
        "inbound_mobile_students",
        "inbound_mobility_ratio",
        "gdp_ppp_current",
        "gdp_pc_ppp_current",
        "gni_pc_ppp_current",
        "gdp_growth_real",
        "inflation_cpi",
        "unemployment",
        "industry_value_added",
        "manufacturing_value_added",
        "services_value_added",
        "trade_percent_gdp",
        "fdi_inflows_percent_gdp",
        "internet_users",
        "urban_population_pct",
        "wgi_political_stability",
        "wgi_government_effectiveness",
        "wgi_regulatory_quality",
        "wgi_rule_of_law",
        "wgi_control_corruption",
        "lpi_overall",
        "price_level_index",
        "student_pool_2026",
        "student_pool_2035",
        "student_pool_2050",
        "national_priority_energy",
        "national_priority_logistics",
        "national_priority_diplomacy",
        "business_informatics_priority",
        "partner_universities_mgimo_count",
        "strategic_partner_universities_count",
        "price_level_index",
        "population_total_current",
        "population_total_2026",
        "platform_data_coverage_pct",
    ]
    for col in numeric_cols:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["DATAQ"] = compute_data_quality(df)

    # Education and demographic readiness.
    edu_components: list[str] = []
    if "tertiary_enrollment_gross" in df:
        df["N_tertiary_enrollment"] = robust_norm(df["tertiary_enrollment_gross"], q_low, q_high, positive=True)
        edu_components.append("N_tertiary_enrollment")
    if "secondary_completion_upper" in df:
        df["N_secondary_completion"] = robust_norm(df["secondary_completion_upper"], q_low, q_high, positive=True)
        edu_components.append("N_secondary_completion")
    elif "school_enrollment_secondary" in df:
        df["N_secondary_completion"] = robust_norm(df["school_enrollment_secondary"], q_low, q_high, positive=True)
        edu_components.append("N_secondary_completion")
    if "gender_parity_tertiary" in df:
        df["N_gender_parity_tertiary"] = _gender_parity_score(df["gender_parity_tertiary"])
        edu_components.append("N_gender_parity_tertiary")
    df["N_education"] = df[edu_components].mean(axis=1) if edu_components else np.nan

    # Core normalized components used by economy, profiles and feasibility.
    if "gdp_ppp_current" in df:
        df["N_gdp_ppp"] = robust_norm(np.log1p(df["gdp_ppp_current"]), q_low, q_high, positive=True)
    if "gdp_pc_ppp_current" in df:
        df["N_gdp_pc_ppp"] = robust_norm(np.log1p(df["gdp_pc_ppp_current"]), q_low, q_high, positive=True)
    if "gdp_growth_real" in df:
        df["N_gdp_growth"] = robust_norm(df["gdp_growth_real"], q_low, q_high, positive=True)
    if "inflation_cpi" in df:
        df["N_inflation_stability"] = robust_norm(df["inflation_cpi"], q_low, q_high, positive=False)
    if "unemployment" in df:
        df["N_unemployment_stability"] = robust_norm(df["unemployment"], q_low, q_high, positive=False)
    if "trade_percent_gdp" in df:
        df["N_trade_open"] = robust_norm(df["trade_percent_gdp"], q_low, q_high, positive=True)
    if "fdi_inflows_percent_gdp" in df:
        df["N_fdi_inflows"] = robust_norm(df["fdi_inflows_percent_gdp"], q_low, q_high, positive=True)
    for c in ["industry_value_added", "manufacturing_value_added", "services_value_added"]:
        if c in df:
            df[f"N_{c}"] = robust_norm(df[c], q_low, q_high, positive=True)
    sector_norms = _present_cols(df, ["N_industry_value_added", "N_manufacturing_value_added", "N_services_value_added"])
    if sector_norms:
        df["N_sector_depth"] = df[sector_norms].mean(axis=1)
    if "internet_users" in df:
        df["N_internet"] = robust_norm(df["internet_users"], q_low, q_high, positive=True)
    if "urban_population_pct" in df:
        df["N_urban_population"] = robust_norm(df["urban_population_pct"], q_low, q_high, positive=True)
    if "lpi_overall" in df:
        df["N_lpi"] = robust_norm(df["lpi_overall"], q_low, q_high, positive=True)
    if "partner_universities_mgimo_count" in df:
        df["N_partner_universities"] = robust_norm(np.log1p(df["partner_universities_mgimo_count"]), q_low, q_high, positive=True)
    if "business_informatics_priority" in df:
        df["N_business_informatics_priority"] = robust_norm(df["business_informatics_priority"], q_low, q_high, positive=True)
    for c in ["national_priority_energy", "national_priority_logistics", "national_priority_diplomacy"]:
        if c in df:
            df[f"N_{c}"] = robust_norm(df[c], q_low, q_high, positive=True)
    for c in [
        "wgi_political_stability",
        "wgi_government_effectiveness",
        "wgi_regulatory_quality",
        "wgi_rule_of_law",
        "wgi_control_corruption",
    ]:
        if c in df:
            df[f"N_{c}"] = robust_norm(df[c], q_low, q_high, positive=True)

    # Profile-specific suitability of the future branch's academic portfolio.
    df["I_PROFILE_DIPLO_ANALYTIC"] = _weighted_available(
        df,
        {
            "N_education": 0.25,
            "N_services_value_added": 0.15,
            "N_trade_open": 0.15,
            "N_wgi_rule_of_law": 0.15,
            "N_wgi_government_effectiveness": 0.10,
            "N_national_priority_diplomacy": 0.20,
        },
    )
    df["I_PROFILE_ECON_LEGAL"] = _weighted_available(
        df,
        {
            "N_gdp_pc_ppp": 0.20,
            "N_services_value_added": 0.20,
            "N_trade_open": 0.20,
            "N_wgi_regulatory_quality": 0.15,
            "N_wgi_rule_of_law": 0.15,
            "N_fdi_inflows": 0.10,
        },
    )
    df["I_PROFILE_DIGITAL_FINANCE"] = _weighted_available(
        df,
        {
            "N_internet": 0.25,
            "N_services_value_added": 0.20,
            "N_gdp_pc_ppp": 0.15,
            "N_gdp_growth": 0.15,
            "N_business_informatics_priority": 0.15,
            "N_trade_open": 0.10,
        },
    )
    df["I_PROFILE_ENERGY_LOGISTICS"] = _weighted_available(
        df,
        {
            "N_national_priority_energy": 0.25,
            "N_national_priority_logistics": 0.20,
            "N_industry_value_added": 0.15,
            "N_trade_open": 0.15,
            "N_lpi": 0.15,
            "N_gdp_growth": 0.10,
        },
    )
    for col in PROFILE_COLUMNS:
        df[col] = df[col].clip(0, 1)
    df["PROGRAM_FIT"] = (0.65 * df[PROFILE_COLUMNS].max(axis=1) + 0.35 * df[PROFILE_COLUMNS].mean(axis=1)).clip(0, 1)
    df["recommended_program_profile"] = df[PROFILE_COLUMNS].idxmax(axis=1).map(PROFILE_LABELS)
    if "mgimo_planned_program_profile" in df.columns:
        planned = df["mgimo_planned_program_profile"].astype("string")
        mask = planned.notna() & planned.ne("")
        df.loc[mask, "recommended_program_profile"] = planned[mask]

    # Addressable market: official WPP 15-24 cohort adjusted by education, affordability and program fit.
    sec = _ratio01(df.get("secondary_completion_upper", df.get("school_enrollment_secondary", pd.Series(np.nan, index=df.index))))
    tert = _ratio01(df.get("tertiary_enrollment_gross", pd.Series(np.nan, index=df.index)))
    if "N_gender_parity_tertiary" in df:
        gpi_factor = (0.75 + 0.25 * df["N_gender_parity_tertiary"]).clip(0.50, 1.0)
    else:
        gpi_factor = pd.Series(1.0, index=df.index)
    affordability = _affordability_factor(df)
    df["AFFORDABILITY_FACTOR"] = affordability
    df["FIELD_FIT_FACTOR"] = (0.35 + 0.65 * df["PROGRAM_FIT"]).clip(0.1, 1.0)
    for year in [2026, 2035, 2050]:
        p15 = f"pop_15_24_{year}"
        youth = df[p15] if p15 in df else pd.Series(np.nan, index=df.index)
        df[f"weighted_youth_15_24_{year}"] = youth
        df[f"addressable_market_students_{year}"] = youth * sec * tert * gpi_factor * affordability * df["FIELD_FIT_FACTOR"]
        df[f"N_addressable_market_{year}"] = robust_norm(np.log1p(df[f"addressable_market_students_{year}"]), q_low, q_high, positive=True)

    if {"addressable_market_students_2026", "addressable_market_students_2035"}.issubset(df.columns):
        growth_26_35 = (df["addressable_market_students_2035"] / df["addressable_market_students_2026"].replace(0, np.nan)) - 1
        df["N_ams_growth_2026_2035"] = robust_norm(growth_26_35, q_low, q_high, positive=True)
    if {"addressable_market_students_2026", "addressable_market_students_2050"}.issubset(df.columns):
        growth_26_50 = (df["addressable_market_students_2050"] / df["addressable_market_students_2026"].replace(0, np.nan)) - 1
        df["N_ams_growth_2026_2050"] = robust_norm(growth_26_50, q_low, q_high, positive=True)

    hub_cols = []
    if "inbound_mobile_students" in df:
        df["N_inbound_mobile_students"] = robust_norm(np.log1p(df["inbound_mobile_students"]), q_low, q_high, positive=True)
        hub_cols.append("N_inbound_mobile_students")
    if "inbound_mobility_ratio" in df:
        df["N_inbound_mobility_ratio"] = robust_norm(df["inbound_mobility_ratio"], q_low, q_high, positive=True)
        hub_cols.append("N_inbound_mobility_ratio")
    if "N_partner_universities" in df:
        hub_cols.append("N_partner_universities")
    df["N_education_hub"] = df[hub_cols].mean(axis=1) if hub_cols else 0.5

    df["I_DEM"] = _weighted_available(
        df,
        {
            "N_addressable_market_2026": 0.50,
            "N_addressable_market_2035": 0.15,
            "N_addressable_market_2050": 0.10,
            "N_ams_growth_2026_2035": 0.08,
            "N_ams_growth_2026_2050": 0.07,
            "N_education": 0.05,
            "N_education_hub": 0.05,
        },
    )

    # Economy and sector fit.
    df["N_macro_stability"] = _weighted_available(df, {"N_inflation_stability": 0.5, "N_unemployment_stability": 0.5})
    df["I_ECO"] = _weighted_available(
        df,
        {
            "N_gdp_pc_ppp": 0.25,
            "N_gdp_ppp": 0.15,
            "N_gdp_growth": 0.17,
            "PROGRAM_FIT": 0.18,
            "N_macro_stability": 0.10,
            "N_trade_open": 0.08,
            "N_sector_depth": 0.07,
        },
    )

    # Russia compatibility: hard statutory stop-list plus a graded admissible-country score.
    # The hard stop itself is applied in apply_eligibility(); this diagnostic score
    # differentiates countries that remain formally admissible by partner base,
    # programme fit and strategic HR fit. Pipeline status is intentionally not
    # a scoring input.
    partner_norm = df.get("N_partner_universities", pd.Series(np.nan, index=df.index)).clip(0, 1)
    existing_branch = df["has_existing_mgimo_branch"].fillna(False).astype(bool) if "has_existing_mgimo_branch" in df.columns else pd.Series(False, index=df.index)
    unfriendly = df["is_unfriendly"].fillna(False).astype(bool) if "is_unfriendly" in df.columns else pd.Series(False, index=df.index)

    # Feasibility: institutions, logistics, digital/urban infrastructure and existing partner base.
    df["I_FEAS"] = _weighted_available(
        df,
        {
            "N_wgi_political_stability": 0.15,
            "N_wgi_government_effectiveness": 0.12,
            "N_wgi_regulatory_quality": 0.12,
            "N_wgi_rule_of_law": 0.12,
            "N_wgi_control_corruption": 0.09,
            "N_lpi": 0.14,
            "N_internet": 0.11,
            "N_urban_population": 0.08,
            "N_partner_universities": 0.07,
        },
    )

    # Strategic HR fit for Russian economy and foreign policy.
    df["I_HRSTRAT"] = _weighted_available(
        df,
        {
            "N_national_priority_energy": 0.16,
            "N_national_priority_logistics": 0.16,
            "N_national_priority_diplomacy": 0.18,
            "I_PROFILE_DIGITAL_FINANCE": 0.20,
            "I_PROFILE_ECON_LEGAL": 0.15,
            "I_PROFILE_ENERGY_LOGISTICS": 0.15,
        },
    )

    # v0.3 aliases expose the management interpretation of the older v0.2 blocks.
    df["I_MARKET"] = df["I_DEM"]
    df["I_PROGRAM"] = df["PROGRAM_FIT"]
    graded = (
        0.56
        + 0.14 * partner_norm
        + 0.12 * df["I_HRSTRAT"]
        + 0.10 * df["I_PROGRAM"]
        - 0.20 * existing_branch.astype(float)
    ).clip(0, 1)
    df["I_RUSCOMP_GRADED"] = np.where(unfriendly, 0.0, graded)
    df["I_RUSCOMP"] = df["I_RUSCOMP_GRADED"]
    df["I_PARTNERSHIP"] = _weighted_available(df, {"N_partner_universities": 0.70, "N_education_hub": 0.30}).clip(0, 1)

    for col in INDEX_COLUMNS + ["PROGRAM_FIT", "I_PARTNERSHIP", "I_RUSCOMP_GRADED"] + PROFILE_COLUMNS:
        if col in df:
            df[col] = df[col].clip(0, 1)
    return df


def _weighted_available(df: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    cols = [c for c in weights if c in df]
    if not cols:
        return pd.Series(np.nan, index=df.index)
    vals = df[cols].astype(float)
    w = pd.Series({c: float(weights[c]) for c in cols})
    weighted = vals.mul(w, axis=1)
    denom = vals.notna().mul(w, axis=1).sum(axis=1)
    return (weighted.sum(axis=1, skipna=True) / denom.replace(0, np.nan)).astype(float)


def compute_priority(df: pd.DataFrame, weights: dict[str, float], epsilon: float = 0.05) -> pd.DataFrame:
    out = df.copy()
    out["PRIORITY_RAW"] = geometric_score(out, weights, epsilon=epsilon)
    out["PRIORITY"] = out["PRIORITY_RAW"]
    if "eligible" in out:
        out.loc[~out["eligible"].astype(bool), "PRIORITY"] = 0.0
    out["rank_all_diagnostic"] = out["PRIORITY_RAW"].rank(method="min", ascending=False)
    out["rank_eligible"] = out["PRIORITY"].where(out.get("eligible", True)).rank(method="min", ascending=False)
    return out
