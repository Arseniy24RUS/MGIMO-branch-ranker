#!/usr/bin/env python3
"""Scan project-owned files for disallowed data-substitution wording."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUFFIXES = {".html", ".js", ".cjs", ".css", ".json", ".csv", ".md", ".py", ".yaml", ".yml"}
SKIP_DIRS = {
    ".git",
    ".playwright-mcp",
    ".pytest_cache",
    "artifacts",
    "internal_archive",
    "node_modules",
    "playwright-report",
    "reports",
    "test-results",
    "vendor",
    "v2.0 legacy",
}
SKIP_PREFIXES = {
    ("data", "raw"),
    ("docs", "assets", "vendor"),
}
SKIP_FILES = {"package-lock.json"}


def term(*parts: str) -> str:
    return "".join(parts)


DISALLOWED_TERMS = [
    term("place", "holder"),
    term("pro", "xy"),
    term("fall", "back"),
    term("mo", "ck"),
    term("st", "ub"),
    term("fa", "ke"),
    term("temp", "orary"),
    term("sub", "stitute"),
    term("extra", "polated"),
    term("заг", "луш"),
    term("прок", "си"),
    term("врем", "енн"),
    term("фол", "лбек"),
    term("под", "став"),
]

OLD_SAI_BASE = term("A_MOBILITY", "_READINESS")

PATTERNS = [
    (
        "old decision modes",
        re.compile(
            "|".join(
                re.escape(item)
                for item in [
                    term("scenario", "Weights"),
                    term("snapshot", "Countries"),
                    term("base", "line"),
                    term("soft", "_power"),
                    term("comm", "ercial"),
                    term("risk", "_averse"),
                ]
            ),
            re.I,
        ),
    ),
    ("old youth cohort", re.compile(re.escape(term("youth", "17_24")) + r"|" + re.escape(term("17", "-24")), re.I)),
    (
        "old demography chart",
        re.compile(re.escape(term("demography", "TrendChart")) + r"|" + re.escape(term("render", "DemographyTrendChart"))),
    ),
    ("old output names", re.compile(re.escape(term("live", "_final")) + r"|" + re.escape(term("final", "_snapshot")), re.I)),
    ("old SAI mobility key", re.compile(re.escape(OLD_SAI_BASE))),
    (
        "old demographic provenance",
        re.compile(
            re.escape(term("world", "_bank_wpp_linked"))
            + r"|"
            + re.escape(term("model", "_forecast"))
            + r"|"
            + re.escape(term("temp", "orary") + " " + term("sub", "stitute"))
            + r"|"
            + re.escape(term("fall", "back") + " dashboard demography"),
            re.I,
        ),
    ),
    ("disallowed wording", re.compile("|".join(re.escape(item) for item in DISALLOWED_TERMS), re.I)),
]


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if path.name in SKIP_FILES:
        return True
    if any(part in SKIP_DIRS for part in parts):
        return True
    return any(parts[: len(prefix)] == prefix for prefix in SKIP_PREFIXES)


def iter_files() -> list[Path]:
    return [
        path
        for path in ROOT.rglob("*")
        if path.is_file()
        and path.suffix.lower() in SUFFIXES
        and not should_skip(path)
    ]


def main() -> None:
    failures: list[str] = []
    for path in iter_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label, pattern in PATTERNS:
            match = pattern.search(text)
            if match:
                failures.append(f"{label}: {path.relative_to(ROOT)} near {match.group(0)!r}")
    if failures:
        raise SystemExit("strict token scan failed:\n" + "\n".join(failures[:120]))
    print("strict token scan passed")


if __name__ == "__main__":
    main()
