#!/usr/bin/env python3
"""Download UNESCO UIS outbound mobility ratio records for SAI_MGIMO_V3."""
from __future__ import annotations

import csv
import datetime as dt
import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DATASET = "uis006"
INDICATOR_ID = "MOR.5T8.40510"
INDICATOR_LABEL = "Outbound mobility ratio, all regions, both sexes (UIS estimate) (%)"
BASE_URL = f"https://data.unesco.org/api/explore/v2.1/catalog/datasets/{DATASET}/records"
OUT_CSV = Path("data/education/uis_outbound_mobility.csv")
OUT_MANIFEST = Path("data/education/uis_outbound_mobility_manifest.json")
FIELDS = [
    "iso3",
    "country",
    "regional_group",
    "year",
    "outbound_mobility_ratio_tertiary",
    "source_key",
    "source_name",
    "dataset_id",
    "indicator_id",
    "indicator_label",
    "qualifier",
    "observation_status",
    "retrieved_at",
    "raw_url",
]


def _request_url(limit: int, offset: int) -> str:
    params = urllib.parse.urlencode(
        {
            "where": f'indicator_id="{INDICATOR_ID}"',
            "limit": str(limit),
            "offset": str(offset),
            "timezone": "UTC",
        }
    )
    return f"{BASE_URL}?{params}"


def _fetch_page(limit: int, offset: int) -> dict[str, Any]:
    url = _request_url(limit=limit, offset=offset)
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def _as_text(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value if item is not None)
    return "" if value is None else str(value)


def _extract_records() -> tuple[list[dict[str, Any]], int, str]:
    limit = 100
    offset = 0
    rows: list[dict[str, Any]] = []
    first_url = _request_url(limit=limit, offset=0)
    total_count = 0
    while True:
        page = _fetch_page(limit=limit, offset=offset)
        if offset == 0:
            total_count = int(page.get("total_count") or 0)
        records = page.get("results") or []
        for record in records:
            iso3 = _as_text(record.get("country_id")).strip().upper()
            year = _as_text(record.get("year")).strip()
            value = record.get("value")
            if not iso3 or not year or value is None:
                raise ValueError(f"UIS record lacks required fields at offset {offset}: {record!r}")
            rows.append(record)
        offset += len(records)
        if not records or offset >= total_count:
            break
    return rows, total_count, first_url


def main() -> None:
    retrieved_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat()
    records, total_count, raw_url = _extract_records()
    if not records:
        raise SystemExit("UNESCO UIS returned no outbound mobility records.")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "iso3": _as_text(record.get("country_id")).strip().upper(),
                    "country": _as_text(record.get("country_name_en")).strip(),
                    "regional_group": _as_text(record.get("regional_group")).strip(),
                    "year": _as_text(record.get("year")).strip(),
                    "outbound_mobility_ratio_tertiary": record.get("value"),
                    "source_key": "unesco_uis_uis006_mor_5t8_40510",
                    "source_name": "UNESCO DataHub UIS",
                    "dataset_id": DATASET,
                    "indicator_id": _as_text(record.get("indicator_id")).strip(),
                    "indicator_label": _as_text(record.get("indicator_label_en")).strip(),
                    "qualifier": _as_text(record.get("qualifier")).strip(),
                    "observation_status": "uis_estimate",
                    "retrieved_at": retrieved_at,
                    "raw_url": raw_url,
                }
            )

    manifest = {
        "source_key": "unesco_uis_uis006_mor_5t8_40510",
        "source_name": "UNESCO DataHub UIS",
        "dataset_id": DATASET,
        "indicator_id": INDICATOR_ID,
        "indicator_label": INDICATOR_LABEL,
        "records_returned": len(records),
        "api_total_count": total_count,
        "country_count": len({str(record.get("country_id")).upper() for record in records if record.get("country_id")}),
        "retrieved_at": retrieved_at,
        "raw_url": raw_url,
        "output_csv": OUT_CSV.as_posix(),
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {OUT_CSV} ({len(records)} records)")
    print(f"saved {OUT_MANIFEST}")


if __name__ == "__main__":
    main()
