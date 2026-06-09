from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_unfriendly(data_dir: str | Path) -> pd.DataFrame:
    path = Path(data_dir) / "reference" / "unfriendly_countries_russia_430r.csv"
    return pd.read_csv(path)


def load_existing_presence(data_dir: str | Path) -> pd.DataFrame:
    path = Path(data_dir) / "reference" / "mgimo_existing_presence.csv"
    return pd.read_csv(path)


def load_partner_universities(data_dir: str | Path) -> pd.DataFrame:
    path = Path(data_dir) / "reference" / "mgimo_partner_universities.csv"
    if not path.exists():
        return pd.DataFrame(columns=["iso3", "partner_count", "strategic_partner_count", "partner_notes", "source_url"])
    return pd.read_csv(path)


def load_non_sovereign_exclusions(data_dir: str | Path) -> pd.DataFrame:
    path = Path(data_dir) / "reference" / "non_sovereign_or_special_exclusions.csv"
    if not path.exists():
        return pd.DataFrame(columns=["iso3", "name", "reason", "hard_exclude"])
    df = pd.read_csv(path)
    # Harmonise possible schemas from the platform project.
    rename = {
        "Country Code": "iso3",
        "Country Name": "name",
        "country_code": "iso3",
        "country_name": "name",
        "eligibility_reason": "reason",
        "exclude_reason": "reason",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "iso3" not in df.columns:
        return pd.DataFrame(columns=["iso3", "name", "reason", "hard_exclude"])
    df["iso3"] = df["iso3"].astype(str).str.upper()
    if "hard_exclude" not in df.columns:
        df["hard_exclude"] = 1
    if "reason" not in df.columns:
        df["reason"] = "non_sovereign_or_special"
    return df


def load_demo_features(data_dir: str | Path) -> pd.DataFrame:
    path = Path(data_dir) / "fixtures" / "demo_country_features.csv"
    return pd.read_csv(path)
