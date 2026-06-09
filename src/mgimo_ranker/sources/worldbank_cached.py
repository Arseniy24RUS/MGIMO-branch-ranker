from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import requests

DOWNLOAD_TEMPLATE = "https://api.worldbank.org/v2/en/indicator/{code}?downloadformat=excel"

# Minimal mapping of World Bank Excel indicator codes that can feed the v0.3 model.
# Additional codes can be added to configs/default.yaml; if a file is present in
# data/raw/world_bank, it will be used automatically.
CACHED_WB_LOGICAL_TO_CODE: dict[str, str] = {
    "population_total": "SP.POP.TOTL",
    "population_female_share": "SP.POP.TOTL.FE.ZS",
    "population_male_share": "SP.POP.TOTL.MA.ZS",
    "pop_1519_female_share": "SP.POP.1519.FE.5Y",
    "pop_1519_male_share": "SP.POP.1519.MA.5Y",
    "pop_2024_female_share": "SP.POP.2024.FE.5Y",
    "pop_2024_male_share": "SP.POP.2024.MA.5Y",
    "pop_2529_female_share": "SP.POP.2529.FE.5Y",
    "pop_2529_male_share": "SP.POP.2529.MA.5Y",
    "gdp_pc_ppp_current": "NY.GDP.PCAP.PP.KD",
    "gdp_growth_real": "NY.GDP.MKTP.KD.ZG",
    "trade_percent_gdp": "NE.TRD.GNFS.ZS",
    "services_value_added": "NV.SRV.TOTL.ZS",
    "urban_population_pct": "SP.URB.TOTL.IN.ZS",
    "internet_users": "IT.NET.USER.ZS",
    "tertiary_enrollment_gross": "SE.TER.ENRR",
    "wgi_government_effectiveness": "GE.EST",
    "wgi_rule_of_law": "RL.EST",
    "wgi_regulatory_quality": "RQ.EST",
    "wgi_political_stability": "PV.EST",
    "price_level_index": "PA.NUS.GDP.PLI",
}

CACHED_WB_SOURCE_NOTES: dict[str, dict[str, str]] = {
    "SP.POP.TOTL": {"label": "Population, total", "group": "demography"},
    "SP.POP.TOTL.FE.ZS": {"label": "Population, female (% of total)", "group": "demography"},
    "SP.POP.TOTL.MA.ZS": {"label": "Population, male (% of total)", "group": "demography"},
    "SP.POP.1519.FE.5Y": {"label": "Population ages 15-19, female (% of female population)", "group": "demography"},
    "SP.POP.1519.MA.5Y": {"label": "Population ages 15-19, male (% of male population)", "group": "demography"},
    "SP.POP.2024.FE.5Y": {"label": "Population ages 20-24, female (% of female population)", "group": "demography"},
    "SP.POP.2024.MA.5Y": {"label": "Population ages 20-24, male (% of male population)", "group": "demography"},
    "SP.POP.2529.FE.5Y": {"label": "Population ages 25-29, female (% of female population)", "group": "demography"},
    "SP.POP.2529.MA.5Y": {"label": "Population ages 25-29, male (% of male population)", "group": "demography"},
    "NY.GDP.PCAP.PP.KD": {"label": "GDP per capita, PPP (constant 2021 international $)", "group": "economy"},
    "NY.GDP.MKTP.KD.ZG": {"label": "GDP growth (annual %)", "group": "economy"},
    "NE.TRD.GNFS.ZS": {"label": "Trade (% of GDP)", "group": "economy"},
    "NV.SRV.TOTL.ZS": {"label": "Services, value added (% of GDP)", "group": "economy"},
    "SP.URB.TOTL.IN.ZS": {"label": "Urban population (% of total population)", "group": "readiness"},
    "IT.NET.USER.ZS": {"label": "Individuals using the Internet (% of population)", "group": "readiness"},
    "SE.TER.ENRR": {"label": "School enrollment, tertiary (% gross)", "group": "readiness"},
    "GE.EST": {"label": "Government Effectiveness: Estimate", "group": "operations"},
    "RL.EST": {"label": "Rule of Law: Estimate", "group": "operations"},
    "RQ.EST": {"label": "Regulatory Quality: Estimate", "group": "operations"},
    "PV.EST": {"label": "Political Stability and Absence of Violence/Terrorism: Estimate", "group": "operations"},
    "PA.NUS.GDP.PLI": {"label": "Price level index (GDP)", "group": "finance"},
}


def download_indicator_xls(indicator_code: str, dest_path: Path, timeout: int = 120) -> Path:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(DOWNLOAD_TEMPLATE.format(code=indicator_code), timeout=timeout)
    response.raise_for_status()
    dest_path.write_bytes(response.content)
    return dest_path


def read_indicator_xls(path: Path) -> pd.DataFrame:
    try:
        return pd.read_excel(path, sheet_name="Data", header=3, engine="xlrd")
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Reading cached World Bank .xls files requires xlrd. Install project requirements first.") from exc


def read_country_metadata(path: Path) -> pd.DataFrame:
    try:
        meta = pd.read_excel(path, sheet_name="Metadata - Countries", engine="xlrd")
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("Reading cached World Bank .xls files requires xlrd. Install project requirements first.") from exc
    meta = meta.rename(columns={"TableName": "country", "Country Code": "iso3", "Region": "region", "IncomeGroup": "income_group"})
    meta = meta[meta["region"].notna()].copy()
    keep = ["iso3", "country", "region", "income_group", "SpecialNotes"]
    for col in keep:
        if col not in meta:
            meta[col] = pd.NA
    return meta[keep].drop_duplicates("iso3").reset_index(drop=True)


def dedupe_indicator_frame(df: pd.DataFrame) -> pd.DataFrame:
    year_cols = [col for col in df.columns if str(col).isdigit()]
    temp = df.copy()
    temp["_non_null_count"] = temp[year_cols].notna().sum(axis=1)
    temp = temp.sort_values(["Country Code", "_non_null_count"], ascending=[True, False])
    temp = temp.drop_duplicates("Country Code", keep="first")
    return temp.drop(columns=["_non_null_count"])


def build_timeseries_map(files: dict[str, Path], country_codes: Iterable[str]) -> dict[str, pd.DataFrame]:
    ts: dict[str, pd.DataFrame] = {}
    codes = list(country_codes)
    for indicator_code, path in files.items():
        raw = dedupe_indicator_frame(read_indicator_xls(path))
        year_cols = [col for col in raw.columns if str(col).isdigit()]
        mat = raw.set_index("Country Code")[year_cols]
        mat.columns = [int(c) for c in mat.columns]
        mat = mat.apply(pd.to_numeric, errors="coerce")
        ts[indicator_code] = mat.reindex(codes)
    return ts


def latest_value_and_year(frame: pd.DataFrame) -> pd.DataFrame:
    years: list[Any] = []
    vals: list[Any] = []
    for _, row in frame.iterrows():
        clean = row.dropna()
        if clean.empty:
            years.append(pd.NA)
            vals.append(np.nan)
        else:
            years.append(int(clean.index[-1]))
            vals.append(float(clean.iloc[-1]))
    return pd.DataFrame({"latest_year": years, "latest_value": vals}, index=frame.index)


def _cohort_total(
    total_pop: pd.DataFrame,
    female_total_share: pd.DataFrame,
    male_total_share: pd.DataFrame,
    female_age_share: pd.DataFrame,
    male_age_share: pd.DataFrame,
) -> pd.DataFrame:
    # total female/male shares are shares of total population; age shares are shares of corresponding sex population.
    return total_pop * ((female_total_share / 100.0) * (female_age_share / 100.0) + (male_total_share / 100.0) * (male_age_share / 100.0))


def _logical_indicator_map_from_config(cfg: Any | None) -> dict[str, str]:
    mapping = dict(CACHED_WB_LOGICAL_TO_CODE)
    if cfg is not None:
        try:
            configured = cfg.get("indicators", "world_bank", default={})
        except Exception:
            configured = {}
        if isinstance(configured, dict):
            mapping.update({str(k): str(v) for k, v in configured.items()})
    return mapping


def available_indicator_files(raw_dir: str | Path, cfg: Any | None = None) -> dict[str, Path]:
    raw_dir = Path(raw_dir)
    mapping = _logical_indicator_map_from_config(cfg)
    codes = sorted(set(mapping.values()) | {p.stem for p in raw_dir.glob("*.xls")})
    return {code: raw_dir / f"{code}.xls" for code in codes if (raw_dir / f"{code}.xls").exists()}


def ensure_indicator_files(raw_dir: str | Path, cfg: Any | None = None, overwrite: bool = False) -> dict[str, Path]:
    raw_dir = Path(raw_dir)
    mapping = _logical_indicator_map_from_config(cfg)
    out: dict[str, Path] = {}
    for code in sorted(set(mapping.values())):
        path = raw_dir / f"{code}.xls"
        if overwrite or not path.exists():  # pragma: no cover - network path
            download_indicator_xls(code, path)
        if path.exists():
            out[code] = path
    return out


def build_cached_worldbank_features(
    data_dir: str | Path,
    cfg: Any | None = None,
    refresh_downloads: bool = False,
    target_years: list[int] | None = None,
) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    """Build a full country feature table from cached World Bank Excel files.

    Returns (features, diagnostics, source_manifest). The feature names are aligned
    with the v0.2 analytical core, so the same index and financial modules can be
    used for demo, cached and live modes.
    """
    data_dir = Path(data_dir)
    raw_dir = data_dir / "raw" / "world_bank"
    if refresh_downloads:
        files = ensure_indicator_files(raw_dir, cfg=cfg, overwrite=True)
    else:
        files = available_indicator_files(raw_dir, cfg=cfg)
    if not files:
        raise FileNotFoundError(f"No cached World Bank .xls files found in {raw_dir}")

    metadata = read_country_metadata(next(iter(files.values())))
    country_codes = metadata["iso3"].astype(str).tolist()
    ts = build_timeseries_map(files, country_codes)
    features = metadata.rename(columns={"SpecialNotes": "world_bank_special_notes"}).copy()

    logical_to_code = _logical_indicator_map_from_config(cfg)
    latest_year_cols: list[str] = []
    for logical, code in logical_to_code.items():
        if code not in ts:
            continue
        latest = latest_value_and_year(ts[code])
        features[logical] = features["iso3"].map(latest["latest_value"])
        year_col = f"{logical}_year"
        features[year_col] = features["iso3"].map(latest["latest_year"])
        latest_year_cols.append(year_col)

    # Demographic cohorts reconstructed from official World Bank disseminated WPP age-share series.
    required_demo = [
        "SP.POP.TOTL",
        "SP.POP.TOTL.FE.ZS",
        "SP.POP.TOTL.MA.ZS",
        "SP.POP.1519.FE.5Y",
        "SP.POP.1519.MA.5Y",
        "SP.POP.2024.FE.5Y",
        "SP.POP.2024.MA.5Y",
        "SP.POP.2529.FE.5Y",
        "SP.POP.2529.MA.5Y",
    ]
    if all(code in ts for code in required_demo):
        total_pop = ts["SP.POP.TOTL"]
        female_total_share = ts["SP.POP.TOTL.FE.ZS"]
        male_total_share = ts["SP.POP.TOTL.MA.ZS"]
        c1519 = _cohort_total(total_pop, female_total_share, male_total_share, ts["SP.POP.1519.FE.5Y"], ts["SP.POP.1519.MA.5Y"])
        c2024 = _cohort_total(total_pop, female_total_share, male_total_share, ts["SP.POP.2024.FE.5Y"], ts["SP.POP.2024.MA.5Y"])
        c2529 = _cohort_total(total_pop, female_total_share, male_total_share, ts["SP.POP.2529.FE.5Y"], ts["SP.POP.2529.MA.5Y"])
        pop_15_24 = c1519 + c2024
        student_pool = c1519 + c2024 + 0.45 * c2529
        latest_15_24 = latest_value_and_year(pop_15_24)
        features["pop_15_24_current"] = features["iso3"].map(latest_15_24["latest_value"])
        features["pop_15_24_current_year"] = features["iso3"].map(latest_15_24["latest_year"])
        latest_sp = latest_value_and_year(student_pool)
        features["student_pool_current"] = features["iso3"].map(latest_sp["latest_value"])
        features["student_pool_current_year"] = features["iso3"].map(latest_sp["latest_year"])
    else:
        missing = [code for code in required_demo if code not in ts]
        features["cached_demography_missing_codes"] = ";".join(missing)

    # Model-compatible aliases and approximations.
    if "gdp_pc_ppp_current" in features and "population_total" in features:
        features["gdp_ppp_current"] = pd.to_numeric(features["gdp_pc_ppp_current"], errors="coerce") * pd.to_numeric(features["population_total"], errors="coerce")
    if "population_total" in features:
        features["population_total_current"] = features["population_total"]

    if latest_year_cols:
        yrs = features[latest_year_cols].apply(pd.to_numeric, errors="coerce")
        features["latest_observation_year_median"] = yrs.median(axis=1)
        base_year = int(getattr(cfg, "base_year", 2026)) if cfg is not None else 2026
        features["latest_observation_lag_years"] = (base_year - features["latest_observation_year_median"]).clip(lower=0)

    source_manifest = build_source_manifest(files, features, logical_to_code)
    diagnostics = {
        "mode": "cached",
        "world_bank_raw_dir": str(raw_dir),
        "world_bank_indicator_files_n": len(files),
        "world_bank_countries_n": int(features["iso3"].nunique()),
        "demographic_source_note": "Cached World Bank files provide observed inputs only; target-year demographic columns are supplied by the mandatory UN WPP 2024 attach step.",
        "available_indicator_codes": sorted(files),
    }
    return features, diagnostics, source_manifest


def build_source_manifest(files: dict[str, Path], features: pd.DataFrame, logical_to_code: dict[str, str] | None = None) -> pd.DataFrame:
    logical_to_code = logical_to_code or CACHED_WB_LOGICAL_TO_CODE
    code_to_logicals: dict[str, list[str]] = {}
    for logical, code in logical_to_code.items():
        code_to_logicals.setdefault(code, []).append(logical)
    rows: list[dict[str, Any]] = []
    for code, path in sorted(files.items()):
        meta = CACHED_WB_SOURCE_NOTES.get(code, {"label": code, "group": "world_bank"})
        logicals = code_to_logicals.get(code, [])
        latest_year = pd.NA
        year_cols = [f"{logical}_year" for logical in logicals if f"{logical}_year" in features.columns]
        if year_cols:
            vals = features[year_cols].apply(pd.to_numeric, errors="coerce").max(axis=1)
            if vals.notna().any():
                latest_year = int(vals.max())
        rows.append(
            {
                "provider": "World Bank Indicators API / cached Excel",
                "indicator_code": code,
                "logical_fields": ";".join(logicals),
                "indicator_label": meta["label"],
                "indicator_group": meta["group"],
                "official_url": f"https://data.worldbank.org/indicator/{code}",
                "raw_file": str(path.name),
                "latest_observed_year_in_run": latest_year,
                "mode": "executed_cached",
            }
        )
    rows.extend(
        [
            {
                "provider": "UN Population Division / WPP",
                "indicator_code": pd.NA,
                "logical_fields": "pop_15_24_2026;pop_15_24_2035;pop_15_24_2050",
                "indicator_label": "Official WPP projections are the required demographic source for target-year age cohorts",
                "indicator_group": "demography_extension",
                "official_url": "https://population.un.org/dataportalapi/index.html",
                "raw_file": pd.NA,
                "latest_observed_year_in_run": pd.NA,
                "mode": "implemented_live_optional",
            },
            {
                "provider": "IMF DataMapper",
                "indicator_code": "NGDP_RPCH;PCPIPCH;LUR",
                "logical_fields": "gdp_growth_real;inflation_cpi;unemployment",
                "indicator_label": "Macro forecast layer for live/extended runs",
                "indicator_group": "macro_extension",
                "official_url": "https://www.imf.org/external/datamapper/api/help",
                "raw_file": pd.NA,
                "latest_observed_year_in_run": pd.NA,
                "mode": "implemented_live_optional",
            },
            {
                "provider": "World Bank WGI",
                "indicator_code": "PV.EST;GE.EST;RQ.EST;RL.EST;CC.EST",
                "logical_fields": "I_FEAS components",
                "indicator_label": "Governance indicators; use 2025 revised WGI scale when refreshing source files",
                "indicator_group": "operations",
                "official_url": "https://www.worldbank.org/en/publication/worldwide-governance-indicators",
                "raw_file": pd.NA,
                "latest_observed_year_in_run": pd.NA,
                "mode": "source_guidance",
            },
        ]
    )
    return pd.DataFrame(rows)
