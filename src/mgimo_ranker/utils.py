from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import requests


def ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def read_csv(path: str | Path, **kwargs: Any) -> pd.DataFrame:
    return pd.read_csv(path, **kwargs)


def write_csv(df: pd.DataFrame, path: str | Path, index: bool = False) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    df.to_csv(path, index=index, encoding="utf-8-sig")
    return path


def write_json(obj: Any, path: str | Path) -> Path:
    path = Path(path)
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    return path


def http_get_json(url: str, params: dict[str, Any] | None = None, timeout: int = 60, retries: int = 3) -> Any:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # pragma: no cover - network path
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch JSON from {url}: {last_exc}")


def http_get_text(url: str, params: dict[str, Any] | None = None, timeout: int = 60, retries: int = 3) -> str:
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            # CBR and some legacy Russian sources may set non-UTF encodings. requests guesses reasonably.
            return r.text
        except Exception as exc:  # pragma: no cover - network path
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch text from {url}: {last_exc}")


def robust_norm(series: pd.Series, q_low: float = 0.05, q_high: float = 0.95, positive: bool = True) -> pd.Series:
    """Robust [0, 1] normalization with quantile clipping."""
    s = pd.to_numeric(series, errors="coerce").astype(float)
    if s.notna().sum() == 0:
        out = pd.Series(np.nan, index=s.index, dtype=float)
        return out
    lo = s.quantile(q_low)
    hi = s.quantile(q_high)
    if math.isclose(float(hi), float(lo), rel_tol=0, abs_tol=1e-12):
        out = pd.Series(0.5, index=s.index, dtype=float)
    else:
        out = ((s - lo) / (hi - lo)).clip(0, 1)
    if not positive:
        out = 1 - out
    return out


def safe_log1p(series: pd.Series | np.ndarray | Iterable[float]) -> pd.Series:
    s = pd.Series(series, dtype=float)
    return np.log1p(s.clip(lower=0))


def weighted_mean(row: pd.Series, weights: dict[str, float]) -> float:
    vals = []
    wts = []
    for col, weight in weights.items():
        val = row.get(col, np.nan)
        if pd.notna(val):
            vals.append(float(val))
            wts.append(float(weight))
    if not vals or sum(wts) <= 0:
        return np.nan
    return float(np.average(vals, weights=wts))


def geometric_score(df: pd.DataFrame, weights: dict[str, float], epsilon: float = 0.05) -> pd.Series:
    scores = []
    for _, row in df.iterrows():
        acc = 0.0
        weight_sum = 0.0
        for col, weight in weights.items():
            val = row.get(col, np.nan)
            if pd.notna(val):
                val = min(1.0, max(0.0, float(val)))
                acc += weight * math.log(epsilon + val)
                weight_sum += weight
        if weight_sum <= 0:
            scores.append(np.nan)
        else:
            scores.append(100 * math.exp(acc / weight_sum))
    return pd.Series(scores, index=df.index)


def latest_by_country(long_df: pd.DataFrame, value_col: str = "value", year_col: str = "year") -> pd.DataFrame:
    if long_df.empty:
        return long_df.copy()
    df = long_df.copy()
    df[year_col] = pd.to_numeric(df[year_col], errors="coerce")
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    df = df.dropna(subset=["iso3", "indicator", year_col, value_col])
    df = df.sort_values(["iso3", "indicator", year_col])
    return df.groupby(["iso3", "indicator"], as_index=False).tail(1)

