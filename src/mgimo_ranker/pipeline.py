from __future__ import annotations

import datetime as dt
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from mgimo_ranker.config import ProjectConfig
from mgimo_ranker.model.finance import add_financial_index, run_financial_model
from mgimo_ranker.model.flags import apply_eligibility, apply_static_flags
from mgimo_ranker.model.indices import PROFILE_COLUMNS, compute_indices, compute_priority
from mgimo_ranker.model.ranking import category_assignment, make_explainability, monte_carlo_weight_sensitivity
from mgimo_ranker.model.transform import imf_long_to_features, merge_feature_sources, worldbank_long_to_features
from mgimo_ranker.sources.cbr import fetch_usd_rub
from mgimo_ranker.sources.imf import fetch_indicators as fetch_imf_indicators
from mgimo_ranker.sources.platform_snapshot import copy_snapshot_source_manifest, load_platform_snapshot
from mgimo_ranker.sources.static import (
    load_demo_features,
    load_existing_presence,
    load_non_sovereign_exclusions,
    load_partner_universities,
    load_unfriendly,
)
from mgimo_ranker.sources.wgi import WGI_SHEET_TO_FIELD, fetch_wgi_features, wgi_coverage
from mgimo_ranker.sources.wpp2024_bulk import (
    WPP_SOURCE_KEY,
    WPP_SOURCE_NAME,
    load_wpp_demographic_features,
    resolve_wpp_paths,
)
from mgimo_ranker.sources.worldbank import (
    fetch_countries,
    fetch_indicators as fetch_wb_indicators,
)
from mgimo_ranker.utils import ensure_dir, write_csv, write_json


def _term(*parts: str) -> str:
    return "".join(parts)


STRICT_OUTPUT_DROP_SUBSTRINGS = [
    _term("base", "line"),
    _term("soft", "_power"),
    _term("comm", "ercial"),
    _term("risk", "_averse"),
    _term("sce", "nario"),
    _term("imput", "ed"),
    _term("model", "_prior"),
    "score_balanced",
    "rank_balanced",
    "priority_tier",
    "mc_top10_prob_pct",
    "mc_mean_rank",
]


def _strict_output_frame(df: pd.DataFrame) -> pd.DataFrame:
    drop_cols = [
        col
        for col in df.columns
        if any(token in str(col).lower() for token in STRICT_OUTPUT_DROP_SUBSTRINGS)
    ]
    return df.drop(columns=drop_cols, errors="ignore")


def _record_raw_file(diagnostics: dict[str, Any], key: str, path: Path) -> None:
    diagnostics.setdefault("raw_source_files", {})[key] = str(path)


def _write_live_raw_csv(df: pd.DataFrame, raw_dir: Path | None, key: str, filename: str, diagnostics: dict[str, Any]) -> Path | None:
    if raw_dir is None:
        return None
    path = write_csv(df, raw_dir / filename)
    _record_raw_file(diagnostics, key, path)
    return path


def _write_live_raw_json(obj: Any, raw_dir: Path | None, key: str, filename: str, diagnostics: dict[str, Any]) -> Path | None:
    if raw_dir is None:
        return None
    path = write_json(obj, raw_dir / filename)
    _record_raw_file(diagnostics, key, path)
    return path


def _write_live_raw_bytes(content: bytes, raw_dir: Path | None, key: str, filename: str, diagnostics: dict[str, Any]) -> Path | None:
    if raw_dir is None:
        return None
    path = raw_dir / filename
    ensure_dir(path.parent)
    path.write_bytes(content)
    _record_raw_file(diagnostics, key, path)
    return path


WDI_QUALITY_FIELDS = [
    "gdp_ppp_current",
    "gdp_pc_ppp_current",
    "trade_percent_gdp",
    "services_value_added",
    "urban_population_pct",
    "lpi_overall",
    "price_level_index",
    "tertiary_enrollment_gross",
    "internet_users",
]
WDI_MIN_COVERAGE_SHARE = 0.75
WGI_MIN_COVERAGE_SHARE = 0.80


def _coverage_counts(features: pd.DataFrame, fields: list[str], countries: pd.DataFrame) -> dict[str, Any]:
    total = int(countries["iso3"].nunique()) if not countries.empty and "iso3" in countries else int(features["iso3"].nunique())
    counts = {
        field: int(pd.to_numeric(features[field], errors="coerce").notna().sum()) if field in features else 0
        for field in fields
    }
    min_coverage = min((count / total for count in counts.values()), default=0.0) if total else 0.0
    missing = [field for field, count in counts.items() if count == 0]
    return {
        "total_countries": total,
        "field_non_null_counts": counts,
        "min_field_coverage_share": float(min_coverage),
        "missing_fields": missing,
    }


def _update_live_quality_gates(features: pd.DataFrame, countries: pd.DataFrame, diagnostics: dict[str, Any]) -> None:
    wdi = _coverage_counts(features, WDI_QUALITY_FIELDS, countries)
    wgi = wgi_coverage(features, countries["iso3"] if not countries.empty and "iso3" in countries else None)
    diagnostics["wdi_quality_coverage"] = wdi
    diagnostics["wgi_quality_coverage"] = wgi
    diagnostics["live_quality_thresholds"] = {
        "wdi_min_coverage_share": WDI_MIN_COVERAGE_SHARE,
        "wgi_min_coverage_share": WGI_MIN_COVERAGE_SHARE,
    }
    critical_warnings = []
    if wdi["missing_fields"] or wdi["min_field_coverage_share"] < WDI_MIN_COVERAGE_SHARE:
        critical_warnings.append("World Bank key WDI coverage is below the live validity threshold.")
    if wgi["min_field_coverage_share"] < WGI_MIN_COVERAGE_SHARE:
        critical_warnings.append("World Bank WGI coverage is below the live validity threshold.")
    diagnostics["critical_quality_warnings"] = critical_warnings
    diagnostics["valid_for_location_analysis"] = not diagnostics.get("source_errors") and not critical_warnings


def build_live_source_manifest(diagnostics: dict[str, Any]) -> pd.DataFrame:
    labels = {
        "world_bank_countries": ("World Bank Countries API", "country metadata", "executed_live"),
        "world_bank_indicators_long": ("World Bank Indicators API", "macro/education/institutional indicators", "executed_live"),
        "world_bank_wgi_excel": ("World Bank WGI 2025 Excel", "official governance workbook", "executed_live"),
        "world_bank_wgi_long": ("World Bank WGI 2025 Excel", "normalized governance long panel", "executed_live"),
        "world_bank_wgi_features": ("World Bank WGI 2025 Excel", "latest governance features", "executed_live"),
        "imf_datamapper_long": ("IMF DataMapper", "macro forecast indicators", "executed_live"),
        "un_wpp2024_age_sex_historical": (WPP_SOURCE_NAME, "single-age-sex official estimates bulk file", "local_official_bulk"),
        "un_wpp2024_age_sex_projection": (WPP_SOURCE_NAME, "single-age-sex medium projection bulk file", "local_official_bulk"),
        "un_wpp2024_demographic_features": (WPP_SOURCE_NAME, "derived model demographic inputs from official bulk", "derived"),
        "live_merged_features": ("MGIMO Branch Ranker", "merged live feature panel before scoring", "derived"),
        "cbr_exchange_rate": ("Central Bank of Russia XML", "USD/RUB exchange rate metadata", "executed_live"),
    }
    rows = []
    for key, raw_file in sorted(diagnostics.get("raw_source_files", {}).items()):
        provider, description, mode = labels.get(key, (key, key, "executed_live"))
        rows.append(
            {
                "source_key": key,
                "provider": provider,
                "description": description,
                "mode": mode,
                "raw_file": raw_file,
            }
        )
    return pd.DataFrame(rows)


def _wpp_paths_from_config(cfg: ProjectConfig) -> tuple[Path, Path]:
    un_wpp_cfg = cfg.get("indicators", "un_wpp", default={})
    return resolve_wpp_paths(
        historical_path=un_wpp_cfg.get("age_sex_historical_path"),
        projection_path=un_wpp_cfg.get("age_sex_projection_path"),
    )


def _drop_legacy_demography_columns(features: pd.DataFrame, target_years: list[int]) -> pd.DataFrame:
    prefixes = (
        "population_total_",
        "pop_15_24_",
        "pop_17_24_",
        "student_pool_",
        "student_pool_growth_",
        "weighted_youth_",
    )
    explicit = {"demography_source", "demography_source_name", "latest_observation_lag_years"}
    legacy_cols = [col for col in features.columns if col in explicit or col.startswith(prefixes)]
    return features.drop(columns=legacy_cols, errors="ignore")


def _attach_wpp_demography(
    features: pd.DataFrame,
    cfg: ProjectConfig,
    diagnostics: dict[str, Any],
    raw_dir: str | Path | None = None,
) -> pd.DataFrame:
    if features.empty or "iso3" not in features:
        raise RuntimeError("Cannot attach mandatory UN WPP 2024 demography without ISO3 feature rows.")
    iso_filter = sorted({str(iso).upper().strip() for iso in features["iso3"].dropna() if str(iso).strip()})
    historical, projection = _wpp_paths_from_config(cfg)
    _record_raw_file(diagnostics, "un_wpp2024_age_sex_historical", historical)
    _record_raw_file(diagnostics, "un_wpp2024_age_sex_projection", projection)
    wpp_features = load_wpp_demographic_features(
        historical,
        projection,
        iso_filter=iso_filter,
        target_years=cfg.target_years,
        base_year=cfg.base_year,
    )
    _write_live_raw_csv(
        wpp_features,
        ensure_dir(raw_dir) if raw_dir is not None else None,
        "un_wpp2024_demographic_features",
        "un_wpp2024_demographic_features.csv",
        diagnostics,
    )
    cleaned = _drop_legacy_demography_columns(features, target_years=cfg.target_years)
    merged = cleaned.merge(wpp_features, on="iso3", how="left")
    missing = sorted(set(iso_filter) - set(merged.loc[merged["demography_source"].eq(WPP_SOURCE_KEY), "iso3"].astype(str)))
    if missing:
        raise RuntimeError(f"Mandatory UN WPP 2024 demography is missing after merge for ISO3: {missing}")
    diagnostics["un_wpp2024_demographic_countries_n"] = int(wpp_features["iso3"].nunique())
    diagnostics["un_wpp2024_source_key"] = WPP_SOURCE_KEY
    return merged


def build_live_features(cfg: ProjectConfig, data_dir: str | Path, raw_dir: str | Path | None = None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Download live API data and produce one feature row per country."""
    diagnostics: dict[str, Any] = {"mode": "live", "source_errors": [], "source_warnings": [], "raw_source_files": {}}
    raw_dir_path = ensure_dir(raw_dir) if raw_dir is not None else None
    frames: list[pd.DataFrame] = []
    countries = pd.DataFrame(columns=["iso3"])

    try:
        countries = fetch_countries()
        _write_live_raw_csv(countries, raw_dir_path, "world_bank_countries", "world_bank_countries.csv", diagnostics)
        diagnostics["world_bank_countries_n"] = len(countries)
    except Exception as exc:  # pragma: no cover - network path
        diagnostics["source_errors"].append({"source": "world_bank_countries", "error": repr(exc), "trace": traceback.format_exc(limit=2)})

    try:
        imf_indicators = cfg.get("indicators", "imf_datamapper", default={})
        if imf_indicators:
            periods = list(range(cfg.base_year, cfg.base_year + 6))
            imf_long = fetch_imf_indicators(imf_indicators, periods=periods)
            _write_live_raw_csv(imf_long, raw_dir_path, "imf_datamapper_long", "imf_datamapper_long.csv", diagnostics)
            imf_features = imf_long_to_features(imf_long, start_year=cfg.base_year, end_year=cfg.base_year + 5)
            frames.append(imf_features)
            diagnostics["imf_indicator_rows_n"] = len(imf_long)
    except Exception as exc:  # pragma: no cover - network path
        diagnostics["source_errors"].append({"source": "imf_datamapper", "error": repr(exc), "trace": traceback.format_exc(limit=2)})

    try:
        wb_indicators = cfg.get("indicators", "world_bank", default={})
        wb_long = fetch_wb_indicators(wb_indicators, start_year=2015, end_year=cfg.base_year)
        _write_live_raw_csv(wb_long, raw_dir_path, "world_bank_indicators_long", "world_bank_indicators_long.csv", diagnostics)
        wb_features = worldbank_long_to_features(wb_long)
        frames.append(wb_features)
        diagnostics["world_bank_indicator_rows_n"] = len(wb_long)
        diagnostics["world_bank_indicator_features_n"] = int(len([c for c in wb_features.columns if c not in {"iso3", "country"} and not c.endswith("_year")]))
    except Exception as exc:  # pragma: no cover - network path
        diagnostics["source_errors"].append({"source": "world_bank_indicators", "error": repr(exc), "trace": traceback.format_exc(limit=2)})

    try:
        wgi_content, wgi_long, wgi_features = fetch_wgi_features()
        _write_live_raw_bytes(wgi_content, raw_dir_path, "world_bank_wgi_excel", "world_bank_wgi_2025.xlsx", diagnostics)
        _write_live_raw_csv(wgi_long, raw_dir_path, "world_bank_wgi_long", "world_bank_wgi_long.csv", diagnostics)
        _write_live_raw_csv(wgi_features, raw_dir_path, "world_bank_wgi_features", "world_bank_wgi_features.csv", diagnostics)
        frames.append(wgi_features)
        diagnostics["world_bank_wgi_rows_n"] = int(len(wgi_long))
        diagnostics["world_bank_wgi_countries_n"] = int(wgi_features["iso3"].nunique()) if not wgi_features.empty else 0
        diagnostics["world_bank_wgi_fields"] = list(WGI_SHEET_TO_FIELD.values())
    except Exception as exc:  # pragma: no cover - network path
        diagnostics["source_errors"].append({"source": "world_bank_wgi_2025", "error": repr(exc), "trace": traceback.format_exc(limit=2)})

    features = merge_feature_sources(*frames)
    if countries is not None and not countries.empty:
        features = countries.merge(features.drop(columns=[c for c in ["country", "region", "income_group"] if c in features], errors="ignore"), on="iso3", how="left")
    _update_live_quality_gates(features, countries, diagnostics)
    _write_live_raw_csv(features, raw_dir_path, "live_merged_features", "live_merged_features.csv", diagnostics)
    return features, diagnostics


def build_demo_features(data_dir: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    features = load_demo_features(data_dir)
    diagnostics = {
        "mode": "demo",
        "note": "Demo fixture is for pipeline verification only. Use --mode snapshot for the bundled global panel or --mode live for API collection.",
        "countries_n": len(features),
    }
    return features, diagnostics


def build_snapshot_features(cfg: ProjectConfig, data_dir: str | Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    features = load_platform_snapshot(data_dir, base_year=cfg.base_year)
    diagnostics = {
        "mode": "snapshot",
        "note": "Offline global panel inherited from mgimo_branch_platform_project; v0.3 recomputes indices, eligibility and finance on top of it.",
        "countries_n": int(len(features)),
        "source_panel": "data/platform_snapshot/country_master_panel.csv",
    }
    return features, diagnostics


def fetch_exchange_rate_required(
    cfg: ProjectConfig,
    explicit_usd_rub: float | None,
    diagnostics: dict[str, Any],
    raw_dir: str | Path | None = None,
) -> float | None:
    raw_dir_path = ensure_dir(raw_dir) if raw_dir is not None else None
    requested_date = dt.date.today()
    metadata: dict[str, Any] = {"requested_date": requested_date.isoformat()}
    if explicit_usd_rub is not None:
        diagnostics["usd_rub_source"] = "explicit_cli_argument"
        diagnostics["usd_rub"] = explicit_usd_rub
        metadata.update({"source": "explicit_cli_argument", "usd_rub": explicit_usd_rub})
        _write_live_raw_json(metadata, raw_dir_path, "cbr_exchange_rate", "cbr_exchange_rate.json", diagnostics)
        return explicit_usd_rub
    try:
        rate = fetch_usd_rub(requested_date)
        diagnostics["usd_rub_source"] = "cbr_xml_daily"
        diagnostics["usd_rub"] = rate
        metadata.update({"source": "cbr_xml_daily", "usd_rub": rate})
        _write_live_raw_json(metadata, raw_dir_path, "cbr_exchange_rate", "cbr_exchange_rate.json", diagnostics)
        return rate
    except Exception as exc:
        diagnostics["usd_rub_source"] = "cbr_xml_unavailable"
        diagnostics["usd_rub_error"] = repr(exc)
        metadata.update(
            {
                "source": diagnostics["usd_rub_source"],
                "error": repr(exc),
            }
        )
        _write_live_raw_json(metadata, raw_dir_path, "cbr_exchange_rate", "cbr_exchange_rate.json", diagnostics)
        raise RuntimeError("USD/RUB rate is required. Provide --usd-rub or make the CBR XML source available.") from exc


def run_pipeline(
    cfg: ProjectConfig,
    data_dir: str | Path,
    output_dir: str | Path,
    mode: str = "snapshot",
    mc_iterations: int = 1000,
    usd_rub: float | None = None,
    input_features: pd.DataFrame | None = None,
    input_diagnostics: dict[str, Any] | None = None,
) -> dict[str, Path]:
    output_dir = ensure_dir(output_dir)
    mode = mode.lower().strip()
    if mode not in {"demo", "snapshot", "live"}:
        raise ValueError("mode must be 'demo', 'snapshot' or 'live'")
    raw_dir = ensure_dir(output_dir / "raw_sources") if mode == "live" else None

    if input_features is not None:
        features = input_features.copy()
        diagnostics = dict(input_diagnostics or {})
        diagnostics.setdefault("mode", "provided_features")
        diagnostics.setdefault("note", "Scored from a provided feature panel; no source collection was executed in this run.")
    elif mode == "live":
        features, diagnostics = build_live_features(cfg, data_dir, raw_dir=raw_dir)
        if features.empty:
            raise RuntimeError("Live data collection produced an empty feature table. Check network/API availability or run --mode snapshot.")
    elif mode == "snapshot":
        features, diagnostics = build_snapshot_features(cfg, data_dir)
    else:
        features, diagnostics = build_demo_features(data_dir)

    if mode != "demo":
        features = _attach_wpp_demography(features, cfg, diagnostics, raw_dir=raw_dir)

    unfriendly = load_unfriendly(data_dir)
    presence = load_existing_presence(data_dir)
    partners = load_partner_universities(data_dir)
    non_sovereign = load_non_sovereign_exclusions(data_dir)

    features = apply_static_flags(features, unfriendly, presence, partners=partners, non_sovereign=non_sovereign)
    features = compute_indices(
        features,
        q_low=float(cfg.get("normalization", "q_low", default=0.05)),
        q_high=float(cfg.get("normalization", "q_high", default=0.95)),
    )
    diagnostics["unfriendly_iso3_n"] = int(unfriendly["iso3"].nunique())
    diagnostics["existing_presence_iso3_n"] = int(presence["iso3"].nunique())
    diagnostics["partner_reference_iso3_n"] = int(partners["iso3"].nunique()) if not partners.empty else 0
    diagnostics["non_sovereign_reference_iso3_n"] = int(non_sovereign["iso3"].nunique()) if not non_sovereign.empty else 0

    usd_rub_val = fetch_exchange_rate_required(cfg, usd_rub, diagnostics, raw_dir=raw_dir)
    financial_full, financial_best = run_financial_model(features, cfg.get("financial", default={}), usd_rub=usd_rub_val)
    features = add_financial_index(features, financial_best)

    features = apply_eligibility(
        features,
        hard_exclude_unfriendly=bool(cfg.get("rules", "hard_exclude_unfriendly", default=True)),
        hard_exclude_existing_branch=bool(cfg.get("rules", "hard_exclude_existing_branch", default=True)),
        hard_exclude_domestic=bool(cfg.get("rules", "hard_exclude_domestic_russia", default=True)),
        hard_exclude_non_sovereign=bool(cfg.get("rules", "hard_exclude_non_sovereign", default=True)),
        min_data_quality=float(cfg.get("rules", "min_data_quality_for_priority", default=0.0)),
    )

    epsilon = float(cfg.get("normalization", "epsilon", default=0.05))
    weights = cfg.weights()
    features = compute_priority(features, weights, epsilon=epsilon)
    robustness = (
        monte_carlo_weight_sensitivity(
            features,
            weights,
            n=int(mc_iterations),
            epsilon=epsilon,
        )
        if mc_iterations > 0
        else pd.DataFrame({"iso3": features["iso3"]})
    )

    explain = make_explainability(
        features,
        component_cols=["I_MARKET", "I_PROGRAM", "I_RUSCOMP", "I_ECO", "I_FIN", "I_FEAS", "I_HRSTRAT"],
    )
    final = features.merge(robustness, on="iso3", how="left").merge(explain, on="iso3", how="left")
    final["recommendation_category"] = final.apply(category_assignment, axis=1)
    final = final.sort_values(["eligible", "PRIORITY"], ascending=[False, False]).reset_index(drop=True)

    priority_cols = [
        "rank_eligible",
        "iso3",
        "country",
        "region",
        "income_group",
        "eligible",
        "exclusion_reason",
        "recommendation_category",
        "PRIORITY",
        "rank_median_mc",
        "rank_q25_mc",
        "rank_q75_mc",
        "p_top5_mc",
        "p_top10_mc",
        "p_top20_mc",
        "I_MARKET",
        "I_PROGRAM",
        "I_DEM",
        "I_ECO",
        "I_RUSCOMP",
        "I_RUSCOMP_GRADED",
        "I_FIN",
        "I_FEAS",
        "I_HRSTRAT",
        "I_PARTNERSHIP",
        "PROGRAM_FIT",
        "recommended_program_profile",
        "I_PROFILE_DIPLO_ANALYTIC",
        "I_PROFILE_ECON_LEGAL",
        "I_PROFILE_DIGITAL_FINANCE",
        "I_PROFILE_ENERGY_LOGISTICS",
        "addressable_market_students_2026",
        "addressable_market_students_2035",
        "addressable_market_students_2050",
        "DATAQ",
        "recommended_format",
        "capex_usd",
        "capex_rub",
        "npv_10y_usd",
        "npv_10y_rub",
        "npv_expected_usd",
        "npv_expected_rub",
        "npv_p10_usd",
        "npv_p90_usd",
        "npv_positive_probability",
        "payback_years",
        "students_year_10",
        "avg_tuition_usd",
        "host_subsidy_share",
        "demand_pool_students",
        "is_unfriendly",
        "is_domestic_russia",
        "is_non_sovereign_or_special",
        "has_existing_mgimo_branch",
        "has_mgimo_pipeline",
        "mgimo_pipeline_status_label",
        "mgimo_pipeline_stage",
        "mgimo_presence_type",
        "partner_universities_mgimo_count",
        "platform_data_coverage_pct",
        "top_strengths",
        "main_weaknesses",
    ]
    public_final = _strict_output_frame(final)
    priority_cols = [c for c in priority_cols if c in public_final.columns]
    ranking = public_final[priority_cols].copy()

    files: dict[str, Path] = {}
    files["ranking"] = write_csv(ranking, output_dir / "country_ranking.csv")

    eligible_mask = ranking["eligible"].astype(bool)
    files["top20_recommended"] = write_csv(
        ranking[eligible_mask].sort_values("rank_eligible").head(20),
        output_dir / "top20_recommended.csv",
    )
    if "has_mgimo_pipeline" in ranking.columns:
        direct_open_mask = eligible_mask & ~ranking["has_mgimo_pipeline"].fillna(False).astype(bool)
    else:
        direct_open_mask = eligible_mask
    files["top20_direct_open"] = write_csv(
        ranking[direct_open_mask].sort_values("rank_eligible").head(20),
        output_dir / "top20_direct_open.csv",
    )
    files["country_scores_full"] = write_csv(public_final, output_dir / "country_scores_full.csv")
    files["financial_model_full"] = write_csv(financial_full, output_dir / "financial_model_full.csv")
    files["financial_model_best"] = write_csv(financial_best, output_dir / "financial_model_best.csv")
    profile_cols = [c for c in PROFILE_COLUMNS if c in public_final.columns]
    if profile_cols:
        profile_long = public_final[["iso3", "country", "eligible", "recommendation_category", "recommended_program_profile", "PRIORITY"] + profile_cols].melt(
            id_vars=["iso3", "country", "eligible", "recommendation_category", "recommended_program_profile", "PRIORITY"],
            value_vars=profile_cols,
            var_name="program_profile",
            value_name="program_profile_score",
        )
        profile_long["program_profile"] = profile_long["program_profile"].str.replace("I_PROFILE_", "", regex=False).str.lower()
        profile_long = profile_long.sort_values(["program_profile", "eligible", "program_profile_score"], ascending=[True, False, False])
        files["program_profile_ranking"] = write_csv(profile_long, output_dir / "program_profile_ranking.csv")
    in_preparation_view = public_final[public_final.get("has_mgimo_pipeline", False).astype(bool)] if "has_mgimo_pipeline" in public_final else pd.DataFrame()
    if not in_preparation_view.empty:
        files["in_preparation_countries"] = write_csv(in_preparation_view, output_dir / "in_preparation_countries.csv")
    excluded = public_final[~public_final["eligible"].astype(bool)].copy()
    if not excluded.empty:
        files["excluded_countries"] = write_csv(excluded[[c for c in ["iso3", "country", "region", "income_group", "exclusion_reason", "is_unfriendly", "is_domestic_russia", "is_non_sovereign_or_special", "has_existing_mgimo_branch"] if c in excluded.columns]], output_dir / "excluded_countries.csv")
    if diagnostics.get("mode") == "live" and diagnostics.get("raw_source_files"):
        manifest = build_live_source_manifest(diagnostics)
        if not manifest.empty:
            files["source_manifest"] = write_csv(manifest, output_dir / "source_manifest.csv")
    elif mode == "snapshot":
        manifest = copy_snapshot_source_manifest(data_dir, output_dir)
        if manifest is not None:
            files["source_manifest"] = manifest
    elif mode == "live":
        manifest = build_live_source_manifest(diagnostics)
        if not manifest.empty:
            files["source_manifest"] = write_csv(manifest, output_dir / "source_manifest.csv")
    files["unfriendly_reference"] = write_csv(unfriendly, output_dir / "unfriendly_reference_copy.csv")
    files["existing_presence_reference"] = write_csv(presence, output_dir / "mgimo_existing_presence_copy.csv")
    if not partners.empty:
        files["partner_universities_reference"] = write_csv(partners, output_dir / "mgimo_partner_universities_copy.csv")
    if not non_sovereign.empty:
        files["non_sovereign_reference"] = write_csv(non_sovereign, output_dir / "non_sovereign_or_special_exclusions_copy.csv")
    diagnostics.pop("scenario", None)
    diagnostics.pop("weights", None)
    diagnostics.update(
        {
            "weights_default": weights,
            "mc_iterations": mc_iterations,
            "eligible_countries_n": int(final["eligible"].sum()),
            "total_countries_n": int(len(final)),
            "model_version": cfg.get("project", "version", default="0.3.0"),
            "created_at": dt.datetime.now().isoformat(timespec="seconds"),
        }
    )
    files["run_metadata"] = write_json(diagnostics, output_dir / "run_metadata.json")
    return files
