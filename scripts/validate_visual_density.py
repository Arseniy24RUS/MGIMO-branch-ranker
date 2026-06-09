#!/usr/bin/env python3
"""Validate Playwright visual-density metrics for the first branch viewport."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VISUAL_DIR = ROOT / "artifacts/visual_qa"
METRICS = VISUAL_DIR / "branch_desktop_ru_overview.metrics.json"
SCREENSHOT = VISUAL_DIR / "branch_desktop_ru_overview.png"


def main() -> None:
    failures: list[str] = []
    if not SCREENSHOT.exists():
        failures.append("branch desktop overview screenshot missing")
    if not METRICS.exists():
        failures.append("branch desktop overview metrics missing")
    if failures:
        raise SystemExit("; ".join(failures))

    data = json.loads(METRICS.read_text(encoding="utf-8"))
    top_row = data.get("topRow") or {}
    map_box = top_row.get("map") or {}
    ranking_box = top_row.get("ranking") or {}
    selected_box = top_row.get("selected") or {}
    if not all([map_box, ranking_box, selected_box]):
        failures.append("top row must include map, ranking and selected country panels")
    else:
        if not (map_box.get("left", 0) < ranking_box.get("left", 0) < selected_box.get("left", 0)):
            failures.append("top row order must be map | ranking | selected country")
        if abs(map_box.get("top", 0) - ranking_box.get("top", 0)) > 12 or abs(map_box.get("top", 0) - selected_box.get("top", 0)) > 12:
            failures.append("map, ranking and selected country panels must share one desktop row")
        for name, box in {"map": map_box, "ranking": ranking_box, "selected": selected_box}.items():
            if box.get("height", 0) < 390:
                failures.append(f"{name} panel too short ({box.get('height')})")

    cards = data.get("executiveCards") or []
    if len(cards) < 4:
        failures.append(f"fewer than four executive cards rendered: {len(cards)}")
    required = {"indexDecompositionChart", "financeChart", "populationYouthChart", "ageSexPyramidChart"}
    seen = {card.get("visualId") for card in cards}
    if not required.issubset(seen):
        failures.append(f"required executive visual cards missing: {sorted(required - seen)}")
    for card in cards:
        if card.get("height", 0) < 340:
            failures.append(f"{card.get('visualId')}: card too short ({card.get('height')})")
        if card.get("visualHeight", 0) < 220:
            failures.append(f"{card.get('visualId')}: chart area too short ({card.get('visualHeight')})")
        if not card.get("hasPlotPixels"):
            failures.append(f"{card.get('visualId')}: chart pixels missing")
        if card.get("isTooNarrow"):
            failures.append(f"{card.get('visualId')}: card too narrow ({card.get('width')})")
    if data.get("largestBlankCardShare", 0) > 0.25:
        failures.append(f"blank visual share too high: {data.get('largestBlankCardShare')}")

    if failures:
        raise SystemExit("visual density validation failed:\n" + "\n".join(failures[:80]))
    print("visual density validation passed")


if __name__ == "__main__":
    main()
