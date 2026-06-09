from __future__ import annotations

from typing import Any

import pandas as pd
import requests

UIS_API_BASE = "https://api.uis.unesco.org/api/public"


def fetch_json(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    """Generic UNESCO UIS public API getter.

    UIS indicator identifiers and filters evolve with the Data Browser. For reproducible projects,
    store the exact endpoint and filters in a YAML config or source registry, then call this helper.
    """
    endpoint = endpoint.strip("/")
    url = f"{UIS_API_BASE}/{endpoint}"
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.json()


def json_records_to_frame(payload: Any) -> pd.DataFrame:
    """Best-effort conversion of common UIS JSON shapes to a DataFrame."""
    if isinstance(payload, list):
        return pd.DataFrame(payload)
    if isinstance(payload, dict):
        for key in ["data", "results", "items", "value"]:
            if key in payload and isinstance(payload[key], list):
                return pd.DataFrame(payload[key])
        return pd.json_normalize(payload)
    return pd.DataFrame()
