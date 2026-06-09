from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from mgimo_ranker.utils import http_get_json

WB_BASE = "https://api.worldbank.org/v2"

AGE_SEX_BANDS: list[dict[str, Any]] = [
    {"code": "0004", "label": "0-4"},
    {"code": "0509", "label": "5-9"},
    {"code": "1014", "label": "10-14"},
    {"code": "1519", "label": "15-19"},
    {"code": "2024", "label": "20-24"},
    {"code": "2529", "label": "25-29"},
    {"code": "3034", "label": "30-34"},
    {"code": "3539", "label": "35-39"},
    {"code": "4044", "label": "40-44"},
    {"code": "4549", "label": "45-49"},
    {"code": "5054", "label": "50-54"},
    {"code": "5559", "label": "55-59"},
    {"code": "6064", "label": "60-64"},
    {"code": "6569", "label": "65-69"},
    {"code": "7074", "label": "70-74"},
    {"code": "7579", "label": "75-79"},
    {"code": "80UP", "label": "80+"},
]
TARGET_AGE_CODES = {"1519", "2024", "2529"}

CORE_DEMOGRAPHIC_INDICATORS: dict[str, str] = {
    "population_total": "SP.POP.TOTL",
    "population_female_share": "SP.POP.TOTL.FE.ZS",
    "population_male_share": "SP.POP.TOTL.MA.ZS",
    "pop_1519_female_share": "SP.POP.1519.FE.5Y",
    "pop_1519_male_share": "SP.POP.1519.MA.5Y",
    "pop_2024_female_share": "SP.POP.2024.FE.5Y",
    "pop_2024_male_share": "SP.POP.2024.MA.5Y",
    "pop_2529_female_share": "SP.POP.2529.FE.5Y",
    "pop_2529_male_share": "SP.POP.2529.MA.5Y",
}

AGE_SEX_INDICATORS: dict[str, str] = {
    f"pop_{band['code'].lower()}_{sex}_share": f"SP.POP.{band['code']}.{suffix}.5Y"
    for band in AGE_SEX_BANDS
    for sex, suffix in [("female", "FE"), ("male", "MA")]
}

WB_DEMOGRAPHIC_INDICATORS: dict[str, str] = {
    **CORE_DEMOGRAPHIC_INDICATORS,
    **AGE_SEX_INDICATORS,
}


def _paginate(endpoint: str, params: dict[str, Any] | None = None, per_page: int = 20000) -> list[dict[str, Any]]:
    params = dict(params or {})
    params.update({"format": "json", "per_page": per_page})
    first = http_get_json(endpoint, params=params)
    if not isinstance(first, list) or len(first) < 2:
        return []
    meta, data = first[0], first[1] or []
    pages = int(meta.get("pages", 1))
    out = list(data)
    for page in range(2, pages + 1):  # pragma: no cover - network path
        params["page"] = page
        chunk = http_get_json(endpoint, params=params)
        if isinstance(chunk, list) and len(chunk) >= 2 and chunk[1]:
            out.extend(chunk[1])
    return out


def fetch_countries() -> pd.DataFrame:
    """Fetch World Bank country metadata and keep sovereign/country entries, not aggregates."""
    rows = _paginate(f"{WB_BASE}/country", per_page=400)
    recs: list[dict[str, Any]] = []
    for r in rows:
        region = (r.get("region") or {}).get("value")
        if not region or region == "Aggregates":
            continue
        iso3 = r.get("id")
        if not iso3 or len(iso3) != 3:
            continue
        recs.append(
            {
                "iso3": iso3,
                "iso2": r.get("iso2Code"),
                "country": r.get("name"),
                "region": region,
                "income_group": (r.get("incomeLevel") or {}).get("value"),
                "lending_type": (r.get("lendingType") or {}).get("value"),
                "capital_city": r.get("capitalCity"),
                "longitude": r.get("longitude"),
                "latitude": r.get("latitude"),
            }
        )
    return pd.DataFrame(recs).sort_values("iso3").reset_index(drop=True)


def fetch_indicator(indicator_code: str, start_year: int | None = None, end_year: int | None = None) -> pd.DataFrame:
    params: dict[str, Any] = {}
    if start_year and end_year:
        params["date"] = f"{start_year}:{end_year}"
    rows = _paginate(f"{WB_BASE}/country/all/indicator/{indicator_code}", params=params)
    recs: list[dict[str, Any]] = []
    for r in rows:
        countryiso3 = r.get("countryiso3code")
        if not countryiso3 or len(countryiso3) != 3:
            continue
        recs.append(
            {
                "iso3": countryiso3,
                "country": (r.get("country") or {}).get("value"),
                "indicator": indicator_code,
                "indicator_name": (r.get("indicator") or {}).get("value"),
                "year": int(r["date"]) if str(r.get("date", "")).isdigit() else r.get("date"),
                "value": r.get("value"),
                "source": "world_bank_indicators",
            }
        )
    return pd.DataFrame(recs)


def fetch_indicators(indicators: dict[str, str], start_year: int = 2015, end_year: int = 2050) -> pd.DataFrame:
    frames = []
    for logical_name, code in indicators.items():
        df = fetch_indicator(code, start_year=start_year, end_year=end_year)
        if not df.empty:
            df["indicator"] = logical_name
            df["indicator_code"] = code
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["iso3", "country", "indicator", "year", "value", "source"])
    return pd.concat(frames, ignore_index=True)


def fetch_demographic_indicators(start_year: int = 2000, end_year: int = 2026) -> pd.DataFrame:
    """Disabled: dashboard demography requires official UN WPP age-sex files."""
    raise RuntimeError("Official UN WPP age-sex files are required for demography.")


def _indicator_timeseries(long_df: pd.DataFrame, indicator: str) -> pd.DataFrame:
    df = long_df[long_df["indicator"].eq(indicator)].copy()
    if df.empty:
        return pd.DataFrame()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["iso3", "year"])
    if df.empty:
        return pd.DataFrame()
    df["year"] = df["year"].astype(int)
    wide = df.pivot_table(index="iso3", columns="year", values="value", aggfunc="first")
    wide = wide.apply(pd.to_numeric, errors="coerce")
    wide.columns = [int(c) for c in wide.columns]
    return wide.sort_index(axis=1)


def _required_indicator_series(wb_demo_long: pd.DataFrame, indicators: dict[str, str]) -> dict[str, pd.DataFrame]:
    series = {name: _indicator_timeseries(wb_demo_long, name) for name in indicators}
    missing = [name for name, frame in series.items() if frame.empty]
    if missing:
        raise ValueError(f"Missing required World Bank demographic indicators: {missing}")
    return series


def _latest_value_and_year(frame: pd.DataFrame, base_year: int) -> pd.DataFrame:
    years: list[Any] = []
    vals: list[Any] = []
    for _, row in frame.iterrows():
        clean = pd.to_numeric(row, errors="coerce").dropna()
        clean = clean[[int(c) <= int(base_year) for c in clean.index]]
        if clean.empty:
            years.append(pd.NA)
            vals.append(np.nan)
        else:
            years.append(int(clean.index[-1]))
            vals.append(float(clean.iloc[-1]))
    return pd.DataFrame({"latest_year": years, "latest_value": vals}, index=frame.index)


def _cagr(v0: float, v1: float, years: int) -> float:
    if years <= 0 or pd.isna(v0) or pd.isna(v1) or v0 <= 0 or v1 <= 0:
        return np.nan
    return (v1 / v0) ** (1.0 / years) - 1.0


def _forecast_row(
    row: pd.Series,
    base_year: int,
    target_years: list[int],
    clip: tuple[float, float] = (-0.05, 0.05),
) -> dict[int, float]:
    clean = pd.to_numeric(row, errors="coerce").dropna().sort_index()
    if clean.empty:
        return {int(y): np.nan for y in target_years}
    clean.index = [int(c) for c in clean.index]
    base_candidates = clean[clean.index <= int(base_year)]
    if base_candidates.empty:
        observed_year = int(clean.index[-1])
        observed_value = float(clean.iloc[-1])
    else:
        observed_year = int(base_candidates.index[-1])
        observed_value = float(base_candidates.iloc[-1])
    rates: list[tuple[float, float]] = []
    for window, weight in ((5, 0.5), (10, 0.3), (20, 0.2)):
        prior_year = observed_year - window
        if prior_year in clean.index:
            rate = _cagr(float(clean.loc[prior_year]), observed_value, window)
            if not pd.isna(rate):
                rates.append((rate, weight))
    rate = sum(r * w for r, w in rates) / sum(w for _, w in rates) if rates else 0.0
    rate = float(np.clip(rate, clip[0], clip[1]))
    out: dict[int, float] = {}
    for year in target_years:
        year = int(year)
        if year in clean.index:
            out[year] = float(clean.loc[year])
            continue
        horizon = year - observed_year
        damp = 0.85 if horizon <= 12 else 0.60
        out[year] = observed_value * ((1.0 + rate * damp) ** horizon)
    return out


def _add_forecast_columns(features: pd.DataFrame, series: pd.DataFrame, prefix: str, target_years: list[int], base_year: int) -> None:
    for iso3, row in series.iterrows():
        forecast = _forecast_row(row, base_year=base_year, target_years=target_years)
        for year, value in forecast.items():
            features.loc[features["iso3"].eq(iso3), f"{prefix}_{year}"] = value


def _cohort_total(
    total_pop: pd.DataFrame,
    female_total_share: pd.DataFrame,
    male_total_share: pd.DataFrame,
    female_age_share: pd.DataFrame,
    male_age_share: pd.DataFrame,
) -> pd.DataFrame:
    female = (female_total_share / 100.0) * (female_age_share / 100.0)
    male = (male_total_share / 100.0) * (male_age_share / 100.0)
    return total_pop * (female + male)


def derive_demographic_features(wb_demo_long: pd.DataFrame, target_years: list[int], base_year: int = 2026) -> pd.DataFrame:
    """Derive youth-population model inputs from World Bank age-share time series."""
    raise RuntimeError("Official UN WPP age-sex files are required for demography.")
    if wb_demo_long.empty:
        return pd.DataFrame(columns=["iso3"])
    series = _required_indicator_series(wb_demo_long, CORE_DEMOGRAPHIC_INDICATORS)

    total_pop = series["population_total"]
    female_total_share = series["population_female_share"]
    male_total_share = series["population_male_share"]
    c1519 = _cohort_total(total_pop, female_total_share, male_total_share, series["pop_1519_female_share"], series["pop_1519_male_share"])
    c2024 = _cohort_total(total_pop, female_total_share, male_total_share, series["pop_2024_female_share"], series["pop_2024_male_share"])
    c2529 = _cohort_total(total_pop, female_total_share, male_total_share, series["pop_2529_female_share"], series["pop_2529_male_share"])
    pop_15_24 = c1519 + c2024
    student_pool = c1519 + c2024 + 0.45 * c2529

    features = pd.DataFrame({"iso3": sorted(set(total_pop.index) | set(pop_15_24.index))})
    countries = wb_demo_long[["iso3", "country"]].dropna().drop_duplicates("iso3")
    features = features.merge(countries, on="iso3", how="left")

    latest_total = _latest_value_and_year(total_pop, base_year=base_year)
    latest_15_24 = _latest_value_and_year(pop_15_24, base_year=base_year)
    latest_student_pool = _latest_value_and_year(student_pool, base_year=base_year)
    features["population_total_current"] = features["iso3"].map(latest_total["latest_value"])
    features["population_total_current_year"] = features["iso3"].map(latest_total["latest_year"])
    features["pop_15_24_current"] = features["iso3"].map(latest_15_24["latest_value"])
    features["pop_15_24_current_year"] = features["iso3"].map(latest_15_24["latest_year"])
    features["student_pool_current"] = features["iso3"].map(latest_student_pool["latest_value"])
    features["student_pool_current_year"] = features["iso3"].map(latest_student_pool["latest_year"])

    _add_forecast_columns(features, total_pop, "population_total", target_years, base_year=base_year)
    _add_forecast_columns(features, pop_15_24, "pop_15_24", target_years, base_year=base_year)
    _add_forecast_columns(features, student_pool, "student_pool", target_years, base_year=base_year)
    for year in target_years:
        pop_col = f"pop_15_24_{int(year)}"
        if pop_col in features:
            features[f"pop_17_24_{int(year)}"] = pd.to_numeric(features[pop_col], errors="coerce") * 0.82

    if {"student_pool_2026", "student_pool_2035"}.issubset(features.columns):
        features["student_pool_growth_2026_2035_pct"] = (
            features["student_pool_2035"] / pd.to_numeric(features["student_pool_2026"], errors="coerce").replace(0, np.nan) - 1.0
        ) * 100.0
    if {"student_pool_2026", "student_pool_2050"}.issubset(features.columns):
        features["student_pool_growth_2026_2050_pct"] = (
            features["student_pool_2050"] / pd.to_numeric(features["student_pool_2026"], errors="coerce").replace(0, np.nan) - 1.0
        ) * 100.0

    year_cols = ["population_total_current_year", "pop_15_24_current_year", "student_pool_current_year"]
    features["latest_observation_lag_years"] = (base_year - features[year_cols].apply(pd.to_numeric, errors="coerce").median(axis=1)).clip(lower=0)
    features["demography_source"] = "world_bank_demography_disabled"
    return features


def derive_demographic_series(
    wb_demo_long: pd.DataFrame,
    actual_start_year: int = 2000,
    base_year: int = 2026,
    forecast_end_year: int = 2050,
    highlight_years: list[int] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build annual public demography series for the static dashboard payload."""
    raise RuntimeError("Official UN WPP age-sex files are required for demography.")
    if wb_demo_long.empty:
        return {}
    series = _required_indicator_series(wb_demo_long, CORE_DEMOGRAPHIC_INDICATORS)

    total_pop = series["population_total"]
    female_total_share = series["population_female_share"]
    male_total_share = series["population_male_share"]
    c1519 = _cohort_total(total_pop, female_total_share, male_total_share, series["pop_1519_female_share"], series["pop_1519_male_share"])
    c2024 = _cohort_total(total_pop, female_total_share, male_total_share, series["pop_2024_female_share"], series["pop_2024_male_share"])
    c2529 = _cohort_total(total_pop, female_total_share, male_total_share, series["pop_2529_female_share"], series["pop_2529_male_share"])
    pop_15_24 = c1519 + c2024
    student_pool = pop_15_24 + 0.45 * c2529

    forecast_years = list(range(int(base_year), int(forecast_end_year) + 1))
    highlights = highlight_years or [base_year, 2035, forecast_end_year]
    source = "world_bank_demography_disabled"
    forecast_source = "disabled_world_bank_demography_projection"

    def value_at(frame: pd.DataFrame, iso3: str, year: int) -> float | None:
        if iso3 not in frame.index or year not in frame.columns:
            return None
        value = pd.to_numeric(pd.Series([frame.loc[iso3, year]]), errors="coerce").iloc[0]
        if pd.isna(value):
            return None
        return float(value)

    def row(year: int, iso3: str, forecast_cache: dict[str, dict[int, float]] | None = None) -> dict[str, Any] | None:
        if forecast_cache:
            total = forecast_cache["population_total"].get(year)
            youth = forecast_cache["pop_15_24"].get(year)
            pool = forecast_cache["student_pool"].get(year)
        else:
            total = value_at(total_pop, iso3, year)
            youth = value_at(pop_15_24, iso3, year)
            pool = value_at(student_pool, iso3, year)
        if all(pd.isna(v) if v is not None else True for v in (total, youth, pool)):
            return None
        return {
            "year": int(year),
            "population_total": None if total is None or pd.isna(total) else float(total),
            "pop_15_24": None if youth is None or pd.isna(youth) else float(youth),
            "student_pool": None if pool is None or pd.isna(pool) else float(pool),
        }

    out: dict[str, dict[str, Any]] = {}
    iso3_values = sorted(set(total_pop.index) | set(pop_15_24.index) | set(student_pool.index))
    for iso3 in iso3_values:
        years = sorted(
            y
            for y in set(total_pop.columns) | set(pop_15_24.columns) | set(student_pool.columns)
            if int(y) >= int(actual_start_year) and int(y) < int(base_year)
        )
        actual = [item for item in (row(int(year), iso3) for year in years) if item]
        if not actual:
            continue
        forecast_cache = {
            "population_total": _forecast_row(
                total_pop.loc[iso3] if iso3 in total_pop.index else pd.Series(dtype=float),
                base_year=base_year,
                target_years=forecast_years,
            ),
            "pop_15_24": _forecast_row(
                pop_15_24.loc[iso3] if iso3 in pop_15_24.index else pd.Series(dtype=float),
                base_year=base_year,
                target_years=forecast_years,
            ),
            "student_pool": _forecast_row(
                student_pool.loc[iso3] if iso3 in student_pool.index else pd.Series(dtype=float),
                base_year=base_year,
                target_years=forecast_years,
            ),
        }
        forecast = [item for item in (row(year, iso3, forecast_cache) for year in forecast_years) if item]
        out[iso3] = {
            "actual": actual,
            "forecast": forecast,
            "source": source,
            "forecastSource": forecast_source,
            "highlightYears": [int(year) for year in highlights],
        }
    return out


def derive_age_sex_pyramid(
    wb_demo_long: pd.DataFrame,
    actual_start_year: int = 2000,
    base_year: int = 2026,
    forecast_end_year: int = 2050,
    target_age_codes: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Disabled: dashboard demography requires official UN WPP age-sex files."""
    raise RuntimeError("Official UN WPP age-sex files are required for demography.")
    if wb_demo_long.empty:
        return {}
    required = {
        "population_total": CORE_DEMOGRAPHIC_INDICATORS["population_total"],
        "population_female_share": CORE_DEMOGRAPHIC_INDICATORS["population_female_share"],
        "population_male_share": CORE_DEMOGRAPHIC_INDICATORS["population_male_share"],
    }
    base_series = _required_indicator_series(wb_demo_long, required)
    age_series = {name: _indicator_timeseries(wb_demo_long, name) for name in AGE_SEX_INDICATORS}

    total_pop = base_series["population_total"]
    female_total_share = base_series["population_female_share"]
    male_total_share = base_series["population_male_share"]
    target_age_codes = target_age_codes or TARGET_AGE_CODES
    target_labels = {band["label"] for band in AGE_SEX_BANDS if band["code"] in target_age_codes}
    forecast_years = list(range(int(base_year), int(forecast_end_year) + 1))
    source = "world_bank_demography_disabled"
    forecast_source = "disabled_world_bank_demography_projection"

    def frame_value(frame: pd.DataFrame, iso3: str, year: int) -> float | None:
        if iso3 not in frame.index or year not in frame.columns:
            return None
        value = pd.to_numeric(pd.Series([frame.loc[iso3, year]]), errors="coerce").iloc[0]
        if pd.isna(value):
            return None
        return float(value)

    def count_for(
        iso3: str,
        year: int,
        sex: str,
        band_code: str,
        cache: dict[str, dict[int, float]] | None = None,
    ) -> float | None:
        pop = cache["population_total"].get(year) if cache else frame_value(total_pop, iso3, year)
        sex_share_key = "population_female_share" if sex == "female" else "population_male_share"
        age_share_key = f"pop_{band_code.lower()}_{sex}_share"
        sex_share = cache[sex_share_key].get(year) if cache else frame_value(base_series[sex_share_key], iso3, year)
        age_share = cache[age_share_key].get(year) if cache else frame_value(age_series.get(age_share_key, pd.DataFrame()), iso3, year)
        if pop is None or sex_share is None or age_share is None:
            return None
        if any(pd.isna(v) for v in [pop, sex_share, age_share]):
            return None
        return float(pop) * (float(sex_share) / 100.0) * (float(age_share) / 100.0)

    def rows_for_years(
        iso3: str,
        years: list[int],
        cache: dict[str, dict[int, float]] | None = None,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for year in years:
            for band in AGE_SEX_BANDS:
                male = count_for(iso3, year, "male", str(band["code"]), cache=cache)
                female = count_for(iso3, year, "female", str(band["code"]), cache=cache)
                if male is None and female is None:
                    continue
                rows.append(
                    {
                        "year": int(year),
                        "ageBand": str(band["label"]),
                        "male": None if male is None else float(male),
                        "female": None if female is None else float(female),
                        "targetGroup": bool(str(band["code"]) in target_age_codes),
                    }
                )
        return rows

    iso3_values = sorted(set(total_pop.index) | {iso3 for frame in age_series.values() for iso3 in frame.index})
    all_actual_years = sorted(
        int(y)
        for y in set(total_pop.columns)
        if int(y) >= int(actual_start_year) and int(y) < int(base_year)
    )
    out: dict[str, dict[str, Any]] = {}
    for iso3 in iso3_values:
        actual = rows_for_years(iso3, all_actual_years)
        forecast_cache: dict[str, dict[int, float]] = {
            "population_total": _forecast_row(
                total_pop.loc[iso3] if iso3 in total_pop.index else pd.Series(dtype=float),
                base_year=base_year,
                target_years=forecast_years,
            ),
            "population_female_share": _forecast_row(
                female_total_share.loc[iso3] if iso3 in female_total_share.index else pd.Series(dtype=float),
                base_year=base_year,
                target_years=forecast_years,
                clip=(-0.01, 0.01),
            ),
            "population_male_share": _forecast_row(
                male_total_share.loc[iso3] if iso3 in male_total_share.index else pd.Series(dtype=float),
                base_year=base_year,
                target_years=forecast_years,
                clip=(-0.01, 0.01),
            ),
        }
        for band in AGE_SEX_BANDS:
            for sex in ["female", "male"]:
                key = f"pop_{str(band['code']).lower()}_{sex}_share"
                frame = age_series.get(key, pd.DataFrame())
                forecast_cache[key] = _forecast_row(
                    frame.loc[iso3] if iso3 in frame.index else pd.Series(dtype=float),
                    base_year=base_year,
                    target_years=forecast_years,
                    clip=(-0.03, 0.03),
                )
        forecast = rows_for_years(iso3, forecast_years, cache=forecast_cache)
        available_years = sorted({row["year"] for row in actual + forecast})
        actual_bands = {row["ageBand"] for row in actual}
        missing_bands = [band["label"] for band in AGE_SEX_BANDS if band["label"] not in actual_bands]
        out[iso3] = {
            "actual": actual,
            "forecast": forecast,
            "availableYears": available_years,
            "highlightAgeBands": sorted(target_labels, key=lambda label: [band["label"] for band in AGE_SEX_BANDS].index(label)),
            "source": source,
            "forecastSource": forecast_source,
            "dataStatus": "available" if actual and not missing_bands else ("partial" if actual else "missing"),
            "missingAgeBands": missing_bands,
        }
    return out
