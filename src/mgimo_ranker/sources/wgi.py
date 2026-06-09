from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd
import requests

WGI_2025_XLSX_URL = "https://datacatalogfiles.worldbank.org/ddh-published/0038026/DR0095947/wgidataset_with_sourcedata-2025.xlsx"

WGI_SHEET_TO_FIELD = {
    "pv": "wgi_political_stability",
    "ge": "wgi_government_effectiveness",
    "rq": "wgi_regulatory_quality",
    "rl": "wgi_rule_of_law",
    "cc": "wgi_control_corruption",
}

WGI_ESTIMATE_COL = "Governance estimate (approx. -2.5 to +2.5)"
WGI_SCORE_COL = "Governance score (0-100)"


def fetch_wgi_excel(url: str = WGI_2025_XLSX_URL, timeout: int = 120) -> bytes:  # pragma: no cover - network path
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def parse_wgi_excel(content: bytes | BytesIO) -> pd.DataFrame:
    """Parse official WGI workbook into a normalized long table."""
    excel = pd.ExcelFile(BytesIO(content) if isinstance(content, bytes) else content)
    rows: list[pd.DataFrame] = []
    for sheet, field in WGI_SHEET_TO_FIELD.items():
        if sheet not in excel.sheet_names:
            raise ValueError(f"WGI workbook is missing required sheet '{sheet}'")
        raw = pd.read_excel(excel, sheet_name=sheet)
        required = ["Economy (code)", "Economy (name)", "Year", WGI_ESTIMATE_COL]
        missing = [col for col in required if col not in raw.columns]
        if missing:
            raise ValueError(f"WGI sheet '{sheet}' is missing columns: {missing}")
        frame = pd.DataFrame(
            {
                "iso3": raw["Economy (code)"].astype("string").str.upper(),
                "country": raw["Economy (name)"],
                "indicator": field,
                "year": pd.to_numeric(raw["Year"], errors="coerce"),
                "value": pd.to_numeric(raw[WGI_ESTIMATE_COL], errors="coerce"),
                "wgi_score_0_100": pd.to_numeric(raw.get(WGI_SCORE_COL), errors="coerce") if WGI_SCORE_COL in raw else pd.NA,
                "source": "world_bank_wgi_2025_excel",
            }
        )
        frame = frame.dropna(subset=["iso3", "indicator", "year", "value"])
        rows.append(frame)
    if not rows:
        return pd.DataFrame(columns=["iso3", "country", "indicator", "year", "value", "source"])
    return pd.concat(rows, ignore_index=True)


def wgi_long_to_features(wgi_long: pd.DataFrame) -> pd.DataFrame:
    if wgi_long.empty:
        return pd.DataFrame(columns=["iso3"])
    df = wgi_long.copy()
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["iso3", "indicator", "year", "value"])
    latest = df.sort_values(["iso3", "indicator", "year"]).groupby(["iso3", "indicator"], as_index=False).tail(1)
    values = latest.pivot_table(index="iso3", columns="indicator", values="value", aggfunc="first").reset_index()
    years = latest.pivot_table(index="iso3", columns="indicator", values="year", aggfunc="first").reset_index()
    years = years.rename(columns={c: f"{c}_year" for c in years.columns if c != "iso3"})
    countries = df[["iso3", "country"]].dropna().drop_duplicates("iso3")
    return countries.merge(values, on="iso3", how="right").merge(years, on="iso3", how="left")


def fetch_wgi_features(url: str = WGI_2025_XLSX_URL) -> tuple[bytes, pd.DataFrame, pd.DataFrame]:
    content = fetch_wgi_excel(url=url)
    long = parse_wgi_excel(content)
    features = wgi_long_to_features(long)
    return content, long, features


def wgi_coverage(features: pd.DataFrame, iso3: pd.Series | list[str] | None = None) -> dict[str, Any]:
    fields = list(WGI_SHEET_TO_FIELD.values())
    df = features.copy()
    if iso3 is not None and "iso3" in df:
        keep = pd.Series(iso3).dropna().astype(str).str.upper().unique()
        df = df[df["iso3"].astype(str).str.upper().isin(keep)]
    total = int(df["iso3"].nunique()) if "iso3" in df else 0
    counts = {
        field: int(pd.to_numeric(df[field], errors="coerce").notna().sum()) if field in df else 0
        for field in fields
    }
    min_coverage = min((count / total for count in counts.values()), default=0.0) if total else 0.0
    return {"total_countries": total, "field_non_null_counts": counts, "min_field_coverage_share": float(min_coverage)}
