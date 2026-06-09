from __future__ import annotations

from typing import Any

import pandas as pd
import requests

# IMF has been migrating DataMapper API versions. The code tries v1 first because it
# remains widely used in examples, then falls back to v2-like base if needed.
BASE_CANDIDATES = [
    "https://www.imf.org/external/datamapper/api/v1",
    "https://www.imf.org/external/datamapper/api/v2",
]


def _get_json(url: str) -> Any:  # pragma: no cover - network path
    r = requests.get(url, timeout=90)
    r.raise_for_status()
    return r.json()


def fetch_indicator(indicator_code: str, periods: list[int] | None = None) -> pd.DataFrame:
    qs = ""
    if periods:
        qs = "?periods=" + ",".join(str(p) for p in periods)
    last_error: Exception | None = None
    payload = None
    for base in BASE_CANDIDATES:  # pragma: no cover - network path
        try:
            payload = _get_json(f"{base}/{indicator_code}{qs}")
            break
        except Exception as exc:
            last_error = exc
    if payload is None:
        raise RuntimeError(f"IMF DataMapper request failed for {indicator_code}: {last_error}")

    # Common DataMapper shape: {"values": {"NGDP_RPCH": {"USA": {"2024": 2.8}}}}
    values = payload.get("values", payload) if isinstance(payload, dict) else {}
    if isinstance(values, dict) and indicator_code in values:
        values = values[indicator_code]
    rows: list[dict[str, Any]] = []
    if isinstance(values, dict):
        for iso3, series in values.items():
            if not isinstance(series, dict) or len(str(iso3)) != 3:
                continue
            for year, value in series.items():
                rows.append(
                    {
                        "iso3": iso3,
                        "indicator": indicator_code,
                        "year": int(year) if str(year).isdigit() else year,
                        "value": value,
                        "source": "imf_datamapper",
                    }
                )
    return pd.DataFrame(rows)


def fetch_indicators(indicators: dict[str, str], periods: list[int]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for logical_name, code in indicators.items():  # pragma: no cover - network path
        df = fetch_indicator(code, periods=periods)
        if not df.empty:
            df["indicator"] = logical_name
            df["indicator_code"] = code
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["iso3", "indicator", "year", "value", "source"])
    return pd.concat(frames, ignore_index=True)
