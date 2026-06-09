#!/usr/bin/env python3
"""Download official UN WPP 2024 age-sex data through the UN Data Portal API.

The execution environment used to create this patch had no DNS/network access, so
this script is included as the authoritative downloader to be run by Codex App,
GitHub Actions, or a local machine with internet access.

Expected target indicator:
- Population by 5-year age groups and sex, or, preferably, 1-year age groups and sex
  if the API endpoint is used for indicator 47.

The script is intentionally conservative: it stores raw API responses and never
silently replaces official WPP values by modelled values.
"""
from __future__ import annotations
import argparse
import io
import sys
from pathlib import Path
import pandas as pd
import requests

BASE = "https://population.un.org/dataportalapi/api/v1"

def parse_un_csv(content: bytes) -> pd.DataFrame:
    text = content.decode("utf-8-sig", errors="replace")
    if text.startswith("sep=|"):
        text = text.split("\n", 1)[1]
    return pd.read_csv(io.StringIO(text), sep="|")

def fetch_country_location_ids() -> list[str]:
    r = requests.get(f"{BASE}/locations", params={"sort": "id", "format": "csv"}, timeout=120)
    r.raise_for_status()
    df = parse_un_csv(r.content)
    df = df.rename(columns={"Id": "location_id", "Iso3": "iso3", "LocationType": "location_type"})
    if "location_type" in df:
        df = df[df["location_type"].astype(str).str.lower().eq("country")].copy()
    if "iso3" in df:
        df = df[df["iso3"].astype(str).str.fullmatch(r"[A-Z]{3}", na=False)].copy()
    if "location_id" not in df or df.empty:
        raise RuntimeError("UN Data Portal locations response did not provide country location ids")
    return [str(int(value)) for value in pd.to_numeric(df["location_id"], errors="coerce").dropna().unique()]

def download_csv(indicator: int, locations: str, start: int, end: int, out: Path) -> None:
    ids = fetch_country_location_ids() if locations == "all-countries" else [part.strip() for part in locations.split(",") if part.strip()]
    if ids == ["900"]:
        raise RuntimeError("locations=900 is the world aggregate and cannot be used as a replacement for country-level WPP data")
    frames: list[pd.DataFrame] = []
    for i in range(0, len(ids), 35):
        chunk = ",".join(ids[i:i + 35])
        url = f"{BASE}/data/indicators/{indicator}/locations/{chunk}/start/{start}/end/{end}/?format=csv"
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        df = parse_un_csv(r.content)
        if not df.empty:
            frames.append(df)
    if not frames:
        raise RuntimeError("UN Data Portal returned no country-level data")
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.concat(frames, ignore_index=True).to_csv(out, index=False)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--indicator", type=int, default=46, help="UN Data Portal indicator id; verify 46/47 in current API metadata")
    p.add_argument("--locations", default="all-countries", help="Use all country location ids from /locations, or pass comma-separated country location ids")
    p.add_argument("--start", type=int, default=2000)
    p.add_argument("--end", type=int, default=2050)
    p.add_argument("--out", type=Path, default=Path("data/demography/raw_un_wpp2024_age_sex.csv"))
    args = p.parse_args()
    download_csv(args.indicator, args.locations, args.start, args.end, args.out)
    print(f"saved {args.out}")
