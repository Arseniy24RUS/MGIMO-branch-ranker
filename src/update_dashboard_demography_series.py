from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mgimo_ranker.sources.wpp2024_bulk import load_wpp_demography_payload_blocks  # noqa: E402


def main() -> int:
    canonical = ROOT / "docs" / "data" / "mgimo_dashboard_data.json"
    alias = ROOT / "docs" / "data" / "dashboard_payload.json"
    data = json.loads(canonical.read_text(encoding="utf-8"))
    iso_keep = sorted({row.get("iso3") for row in data.get("countries", []) if row.get("iso3")})
    series, pyramid, meta = load_wpp_demography_payload_blocks(iso_filter=iso_keep)
    data["demographySeries"] = series
    data["ageSexPyramid"] = pyramid
    data.setdefault("metadata", {}).setdefault("summary", {})["demography"] = meta
    text = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    canonical.write_text(text, encoding="utf-8")
    alias.write_text(text, encoding="utf-8")
    print(f"updated WPP demographySeries for {len(series)} countries")
    print(f"updated WPP ageSexPyramid for {len(pyramid)} countries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
