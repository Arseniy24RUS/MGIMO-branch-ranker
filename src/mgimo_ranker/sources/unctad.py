from __future__ import annotations

from io import StringIO
from typing import Any

import pandas as pd
import requests


def fetch_csv(url: str, params: dict[str, Any] | None = None, sep: str = ",") -> pd.DataFrame:  # pragma: no cover - network helper
    """Generic CSV helper for UNCTAD Data Hub exports.

    UNCTAD tables and Data Hub export links vary by dataset. The platform uses
    this helper for explicit, versioned UNCTAD CSV export URLs stored in config
    or a source registry.
    """
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text), sep=sep)
