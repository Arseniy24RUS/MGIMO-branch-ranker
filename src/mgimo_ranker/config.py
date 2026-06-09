from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ProjectConfig:
    raw: dict[str, Any]
    path: Path

    @property
    def base_year(self) -> int:
        return int(self.raw["project"]["base_year"])

    @property
    def target_years(self) -> list[int]:
        return [int(x) for x in self.raw["project"]["target_years"]]

    def weights(self) -> dict[str, float]:
        raw_weights = self.raw["weights"]
        if raw_weights and all(isinstance(v, (int, float)) for v in raw_weights.values()):
            weights = raw_weights
        else:
            weights = raw_weights.get("default")
        if not weights:
            raise KeyError("Config must define a non-empty default weights mapping")
        total = float(sum(weights.values()))
        if total <= 0:
            raise ValueError("Default weights have a non-positive weight sum")
        return {k: float(v) / total for k, v in weights.items()}

    def get(self, *path: str, default: Any = None) -> Any:
        cur: Any = self.raw
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur


def load_config(path: str | Path) -> ProjectConfig:
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return ProjectConfig(raw=raw, path=path)
