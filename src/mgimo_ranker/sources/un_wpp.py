from __future__ import annotations

from io import StringIO
import time
from typing import Iterable

import pandas as pd
import requests

WPP_BASE = "https://population.un.org/dataportalapi/api/v1"


def _auth_headers(token: str | None = None) -> dict[str, str] | None:
    if not token:
        return None
    token = token.strip()
    if not token:
        return None
    value = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    return {"Authorization": value}


def parse_un_csv(text: str) -> pd.DataFrame:
    """Parse UN Data Portal CSV, including its optional separator hint line."""
    lines = text.splitlines()
    first = lines[0].strip().lower().replace(" ", "") if lines else ""
    skip = 1 if first.startswith("sep=") else 0
    return pd.read_csv(StringIO(text), sep="|", skiprows=skip)


def _read_un_csv(url: str, token: str | None = None, params: dict[str, str | int | bool] | None = None) -> pd.DataFrame:
    r = requests.get(url, params=params, headers=_auth_headers(token), timeout=90)
    r.raise_for_status()
    return parse_un_csv(r.text)


def fetch_locations(token: str | None = None) -> pd.DataFrame:
    df = _read_un_csv(f"{WPP_BASE}/locations", token=token, params={"sort": "id", "format": "csv"})
    df = df.rename(columns={"Id": "location_id", "Name": "location", "Iso3": "iso3", "Iso2": "iso2"})
    if "iso3" not in df:
        raise ValueError(f"UN WPP locations response did not contain Iso3/iso3. Columns: {list(df.columns)}")
    if "LocationType" in df:
        df = df[df["LocationType"].eq("Country")].copy()
    df = df[df["iso3"].notna() & df["iso3"].astype(str).str.len().eq(3)].copy()
    return df[["location_id", "location", "iso3", "iso2", "Longitude", "Latitude"]].drop_duplicates("iso3")


def fetch_population_by_age_sex(
    location_ids: Iterable[int | str],
    start_year: int,
    end_year: int,
    indicator_id: int = 46,
    batch_size: int = 35,
    token: str | None = None,
    page_size: int = 100,
    sleep_seconds: float = 2.1,
) -> pd.DataFrame:
    """Fetch WPP population by 5-year age groups and sex.

    The UN Data Portal endpoint follows the documented pattern:
    /data/indicators/{id}/locations/{comma-separated location ids}/start/{year}/end/{year}/?format=csv
    """
    if not token:
        raise RuntimeError("UN_DATAPORTAL_TOKEN is required for UN WPP data endpoints.")
    ids = [str(x) for x in location_ids]
    frames: list[pd.DataFrame] = []
    for i in range(0, len(ids), batch_size):  # pragma: no cover - network path
        chunk = ",".join(ids[i : i + batch_size])
        url = f"{WPP_BASE}/data/indicators/{indicator_id}/locations/{chunk}/start/{start_year}/end/{end_year}"
        page_number = 1
        while True:
            df = _read_un_csv(
                url,
                token=token,
                params={"format": "csv", "pageNumber": page_number, "pageSize": page_size},
            )
            if df.empty:
                break
            frames.append(df)
            if len(df) < page_size:
                break
            page_number += 1
            time.sleep(sleep_seconds)
        if i + batch_size < len(ids):
            time.sleep(sleep_seconds)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def derive_youth_population(wpp_df: pd.DataFrame, years: list[int], age_min: int = 15, age_max: int = 24) -> pd.DataFrame:
    if wpp_df.empty:
        return pd.DataFrame(columns=["iso3"])
    df = wpp_df.copy()
    rename = {"Iso3": "iso3", "Location": "country", "TimeLabel": "year", "Value": "value"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    for col in ["year", "AgeStart", "AgeEnd", "value"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "Variant" in df:
        # Prefer median/medium projection if present.
        mask = df["Variant"].astype(str).str.contains("Median|Medium", case=False, na=False)
        if mask.any():
            df = df[mask].copy()
    if "Sex" in df:
        mask = df["Sex"].astype(str).str.contains("Both|Total|All", case=False, na=False)
        if mask.any():
            df = df[mask].copy()
    df = df[df["year"].isin(years)].copy()
    if "AgeStart" in df and "AgeEnd" in df:
        df = df[(df["AgeStart"] >= age_min) & (df["AgeEnd"] <= age_max)].copy()
    grouped = df.groupby(["iso3", "year"], as_index=False)["value"].sum()
    # WPP population values are commonly in thousands for population indicators.
    grouped["value"] = grouped["value"] * 1000
    wide = grouped.pivot(index="iso3", columns="year", values="value").reset_index()
    wide.columns = ["iso3" if c == "iso3" else f"pop_15_24_{int(c)}" for c in wide.columns]
    return wide


def fetch_youth_population(
    target_years: list[int],
    indicator_id: int = 46,
    age_min: int = 15,
    age_max: int = 24,
    token: str | None = None,
) -> pd.DataFrame:
    if not token:
        raise RuntimeError("UN_DATAPORTAL_TOKEN is required for UN WPP data endpoints.")
    locations = fetch_locations(token=token)
    raw = fetch_population_by_age_sex(
        locations["location_id"].tolist(),
        start_year=min(target_years),
        end_year=max(target_years),
        indicator_id=indicator_id,
        token=token,
    )
    return derive_youth_population(raw, years=target_years, age_min=age_min, age_max=age_max)
