from __future__ import annotations

from io import BytesIO
from zipfile import ZipFile

import pandas as pd
import requests


def fetch_bulk_csv_from_zip(url: str, member_contains: str | None = None) -> pd.DataFrame:  # pragma: no cover - network helper
    """Fetch an ILOSTAT bulk-download ZIP and return the first matching CSV.

    ILOSTAT exposes many datasets through its bulk-download repository. The
    exact dataset URL is intentionally passed by the caller because ILOSTAT
    table codes differ by subject and frequency.
    """
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    with ZipFile(BytesIO(r.content)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if member_contains:
            names = [n for n in names if member_contains.lower() in n.lower()]
        if not names:
            raise ValueError(f"No CSV member found in ILOSTAT ZIP: {url}")
        with zf.open(names[0]) as f:
            return pd.read_csv(f)
