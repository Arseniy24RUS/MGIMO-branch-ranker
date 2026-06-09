from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd
import requests

OECD_SDMX_BASE = "https://sdmx.oecd.org/public/rest"


def fetch_dataflows(agency: str = "all") -> pd.DataFrame:
    """Fetch OECD SDMX dataflow catalogue.

    This is a generic adapter. For production use, select a specific dataset in OECD Data Explorer,
    copy the Developer API query, and pass the resource path to ``fetch_sdmx_csv``.
    """
    url = f"{OECD_SDMX_BASE}/dataflow/{agency}/all/all"
    headers = {"Accept": "application/vnd.sdmx.structure+json;version=1.0"}
    r = requests.get(url, headers=headers, timeout=90)
    r.raise_for_status()
    payload = r.json()
    flows = payload.get("data", {}).get("dataflows", []) or payload.get("dataflows", [])
    rows: list[dict[str, Any]] = []
    if isinstance(flows, dict):
        flows = flows.values()
    for flow in flows:
        fid = flow.get("id") or flow.get("urn")
        name = flow.get("name", {})
        if isinstance(name, dict):
            name = name.get("en") or next(iter(name.values()), None)
        rows.append({"dataflow_id": fid, "name": name, "raw": flow})
    return pd.DataFrame(rows)


def fetch_sdmx_csv(resource_path: str, params: dict[str, Any] | None = None) -> pd.DataFrame:
    """Fetch a CSV response from an OECD SDMX REST resource path.

    Example resource path copied from OECD Data Explorer may look like:
    ``/data/OECD.SDD.NAD,DSD_NAMAIN10@DF_TABLE1/.A...``.
    """
    path = resource_path if resource_path.startswith("/") else f"/{resource_path}"
    url = f"{OECD_SDMX_BASE}{path}"
    headers = {"Accept": "text/csv"}
    r = requests.get(url, params=params, headers=headers, timeout=120)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text))
