from __future__ import annotations

import pandas as pd

from mgimo_ranker.utils import latest_by_country


def worldbank_long_to_features(wb_long: pd.DataFrame) -> pd.DataFrame:
    """Convert World Bank long panel to one latest-value row per country."""
    if wb_long.empty:
        return pd.DataFrame(columns=["iso3"])
    latest = latest_by_country(wb_long, value_col="value", year_col="year")
    if latest.empty:
        return pd.DataFrame(columns=["iso3"])
    wide = latest.pivot_table(index="iso3", columns="indicator", values="value", aggfunc="first").reset_index()
    years = latest.pivot_table(index="iso3", columns="indicator", values="year", aggfunc="first").reset_index()
    years = years.rename(columns={c: f"{c}_year" for c in years.columns if c != "iso3"})
    country_cols = ["iso3", "country"]
    countries = wb_long[country_cols].dropna().drop_duplicates("iso3") if "country" in wb_long else pd.DataFrame({"iso3": []})
    out = countries.merge(wide, on="iso3", how="right").merge(years, on="iso3", how="left")
    return out


def merge_feature_sources(*frames: pd.DataFrame) -> pd.DataFrame:
    base = None
    for frame in frames:
        if frame is None or frame.empty:
            continue
        if "iso3" not in frame:
            continue
        frame = frame.drop_duplicates("iso3")
        if base is None:
            base = frame.copy()
        else:
            base = base.merge(frame, on="iso3", how="outer", suffixes=("", "_src"))
            # Consolidate duplicate country-like columns if they appear.
            for col in list(base.columns):
                if col.endswith("_src"):
                    root = col[:-4]
                    if root in base.columns:
                        base[root] = base[root].combine_first(base[col])
                        base = base.drop(columns=[col])
    return base if base is not None else pd.DataFrame(columns=["iso3"])


def imf_long_to_features(imf_long: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    """Convert IMF DataMapper panel to country features.

    For forecast variables, the model uses the average over the configured
    decision horizon rather than the last available historical observation.
    """
    if imf_long.empty:
        return pd.DataFrame(columns=["iso3"])
    df = imf_long.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df[df["year"].between(start_year, end_year, inclusive="both")].copy()
    if df.empty:
        return pd.DataFrame(columns=["iso3"])
    avg = df.groupby(["iso3", "indicator"], as_index=False)["value"].mean()
    wide = avg.pivot_table(index="iso3", columns="indicator", values="value", aggfunc="first").reset_index()
    rename = {
        "real_gdp_growth": "gdp_growth_real",
        "inflation": "inflation_cpi",
        "unemployment": "unemployment",
    }
    return wide.rename(columns={k: v for k, v in rename.items() if k in wide.columns})
