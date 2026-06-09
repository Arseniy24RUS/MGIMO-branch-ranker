#!/usr/bin/env python3
"""Static 10/10 dashboard contract gate.

The gate checks the public dashboard, documentation, payload, archive hygiene,
and available Playwright summary. It is intentionally deterministic so the
autonomous review runner can turn these checks into machine scorecards when
human/subagent reviewers are not configured.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FAIL: list[str] = []
WARN: list[str] = []


def term(*parts: str) -> str:
    return "".join(parts)

BRANCH_VISUAL_IDS = [
    "rankingTable",
    "selectedFactorBars",
    "indexDecompositionChart",
    "financeChart",
    "populationYouthChart",
    "ageSexPyramidChart",
    "programProfileChart",
    "feasibilityRadarChart",
    "activeFactorChart",
    "compareGrid",
]

STUDENT_VISUAL_IDS = [
    "studentSaiDecomposition",
    "studentYouthGrowthScatter",
    "studentMobilityChart",
    "studentRegionTreemap",
    "studentTopAfricaPanel",
    "studentPopulationYouthChart",
    "studentAgeSexPyramidChart",
]

BRANCH_RENDERERS = [
    "renderRanking",
    "renderSelectedFactorBars",
    "renderIndexDecompositionChart",
    "renderFinanceChart",
    "renderPopulationYouthChart",
    "renderAgeSexPyramidChart",
    "renderProgramProfileChart",
    "renderFeasibilityRadarChart",
    "renderActiveFactorChart",
    "renderExecutiveVisuals",
]

STUDENT_RENDERERS = [
    "renderStudentSaiDecomposition",
    "renderYouthGrowthScatter",
    "renderStudentMobilityChart",
    "renderStudentRegionTreemap",
    "renderStudentTopAfricaPanel",
    "renderStudentDemographyCharts",
    "renderStudentVisuals",
]

SAI_UIS_KEY = "A_OUTBOUND_MOBILITY_UIS"
SAI_OLD_MOBILITY_BASE = "A_MOBILITY" + "_READINESS"
SAI_OLD_MOBILITY_KEY = SAI_OLD_MOBILITY_BASE + "_" + "PRO" + "XY"
SAI_TRACE_REQUIRED = {
    "source_key",
    "year",
    "raw_value",
    "normalized_value",
    "normalization_method",
    "weight",
    "observation_status",
}

SAI_REQUIRED_WEIGHTS = {
    "A_YOUTH_OPPORTUNITY": 0.50,
    SAI_UIS_KEY: 0.16,
    "A_LEGAL_PARTNERSHIP_CONTEXT": 0.12,
    "A_PROGRAM_RELEVANCE": 0.08,
    "A_AFFORDABILITY_ACCESS": 0.06,
    "A_DIGITAL_REACH": 0.04,
    "A_DATAQ": 0.04,
}

PUBLIC_SCAN_PATHS = [
    ROOT / "docs/index.html",
    ROOT / "docs/students.html",
    ROOT / "docs/assets/app.js",
    ROOT / "docs/assets/students.js",
    ROOT / "docs/assets/style.css",
    ROOT / "docs/METHODOLOGY.md",
    ROOT / "docs/METHODOLOGY_RU.md",
    ROOT / "docs/DATA_DICTIONARY.md",
    *sorted((ROOT / "docs/locales").glob("*.json")),
]

LEGACY_PATTERNS = {
    "scenario wording": re.compile(r"\bscenario(?:s)?\b|сценар", re.IGNORECASE),
    "legacy decision tokens": re.compile(
        r"\b(?:"
        + "|".join(
            re.escape(item)
            for item in [
                term("base", "line"),
                term("soft", "_power"),
                term("comm", "ercial"),
                term("risk", "_averse"),
            ]
        )
        + r")\b",
        re.IGNORECASE,
    ),
    "old output wording": re.compile(
        r"\b(?:"
        + "|".join(re.escape(item) for item in [term("snap", "shot"), term("live", "_final"), term("final", "_snapshot")])
        + r")\b",
        re.IGNORECASE,
    ),
    "Vietnam separated wording": re.compile(r"Вьетнам\s+не\s+смешива|Vietnam\s+is\s+not\s+mixed", re.IGNORECASE),
    "dead header traces": re.compile(r"\bdataDate\b|decision-strip|executiveDecisionStrip", re.IGNORECASE),
    "old Russian data-quality label": re.compile(r"Качество данных", re.IGNORECASE),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        FAIL.append(message)


def warn(condition: bool, message: str) -> None:
    if not condition:
        WARN.append(message)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_json(path: Path) -> Any:
    return json.loads(read_text(path))


def check_public_text() -> None:
    for path in PUBLIC_SCAN_PATHS:
        require(path.exists(), f"required public file missing: {path.relative_to(ROOT)}")
        if not path.exists():
            continue
        text = read_text(path)
        for label, pattern in LEGACY_PATTERNS.items():
            match = pattern.search(text)
            require(not match, f"{label} remains in {path.relative_to(ROOT)} near {match.group(0)!r}" if match else "")


def check_visual_contract() -> None:
    index_html = read_text(ROOT / "docs/index.html")
    students_html = read_text(ROOT / "docs/students.html")
    app_js = read_text(ROOT / "docs/assets/app.js")
    students_js = read_text(ROOT / "docs/assets/students.js")

    for visual_id in BRANCH_VISUAL_IDS:
        require(f'id="{visual_id}"' in index_html, f"branch visual id missing: {visual_id}")
        require(f'data-visual-id="{visual_id}"' in index_html, f"branch data-visual-id missing: {visual_id}")
    for visual_id in STUDENT_VISUAL_IDS:
        require(f'id="{visual_id}"' in students_html, f"student visual id missing: {visual_id}")
        require(f'data-visual-id="{visual_id}"' in students_html, f"student data-visual-id missing: {visual_id}")

    for renderer in BRANCH_RENDERERS:
        require(re.search(rf"\bfunction\s+{renderer}\b", app_js) is not None, f"branch renderer missing: {renderer}")
    for renderer in STUDENT_RENDERERS:
        require(re.search(rf"\bfunction\s+{renderer}\b", students_js) is not None, f"student renderer missing: {renderer}")

    for html_name, html_text in [("index.html", index_html), ("students.html", students_html)]:
        require("assets/vendor/plotly/plotly.min.js" in html_text, f"local Plotly script missing in {html_name}")
        require("cdn.plot.ly" not in html_text.lower(), f"Plotly CDN referenced in {html_name}")
        require("unpkg.com/leaflet" not in html_text.lower(), f"Leaflet CDN referenced in {html_name}")
        require("cdn.jsdelivr.net/npm/leaflet" not in html_text.lower(), f"Leaflet CDN referenced in {html_name}")

    require((ROOT / "docs/assets/vendor/plotly/plotly.min.js").exists(), "local Plotly asset missing")
    require((ROOT / "docs/assets/vendor/leaflet/leaflet.js").exists(), "local Leaflet asset missing")


def check_payload_contract() -> None:
    payload_path = ROOT / "docs/data/mgimo_dashboard_data.json"
    require(payload_path.exists(), "dashboard payload missing")
    if not payload_path.exists():
        return

    data = load_json(payload_path)
    for key in [
        "countries",
        "factorInputs",
        "demographySeries",
        "ageSexPyramid",
        "studentAttraction",
        "studentFlowsObserved",
        "studentFlowsModelled",
        "weightsDefault",
    ]:
        require(key in data, f"payload key missing: {key}")

    countries = data.get("countries", [])
    vietnam = next((row for row in countries if row.get("iso3") == "VNM"), None)
    require(vietnam is not None, "Vietnam missing from common country list")
    if vietnam:
        status_blob = json.dumps(vietnam, ensure_ascii=False)
        require(vietnam.get("recommendationCategory") == "in_preparation", "Vietnam is not common-ranked as in_preparation")
        require("В подготовке" in status_blob or "in_preparation" in status_blob, "Vietnam in-preparation status label not found")

    student = data.get("studentAttraction", {})
    require(student.get("model", {}).get("name") == "SAI_MGIMO_V3", "student attraction model is not SAI_MGIMO_V3")
    require(len(student.get("byCountry", {})) == 217, "student attraction does not contain 217 model countries")
    eligible_summary = data.get("metadata", {}).get("summary", {}).get("eligibleCountries")
    eligible_rows = sum(1 for row in data.get("countries", []) if row.get("eligible") is True)
    require(eligible_summary == eligible_rows, "practical/eligible universe does not match country rows")
    require(100 <= int(eligible_rows) <= 180, "practical/eligible universe is outside the expected country-list range")
    require("open-data" in str(student.get("model", {}).get("scoreType", "")).lower(), "student index is not marked as open-data")
    weights = student.get("model", {}).get("weights") or {}
    for key, expected in SAI_REQUIRED_WEIGHTS.items():
        require(key in weights, f"SAI weight missing: {key}")
        if key in weights:
            require(abs(float(weights.get(key) or 0) - expected) < 1e-9, f"SAI weight mismatch for {key}: {weights.get(key)}")
    require(SAI_OLD_MOBILITY_BASE not in weights and SAI_OLD_MOBILITY_KEY not in weights, "old SAI mobility component remains in model weights")
    require(student.get("model", {}).get("uisComponentPolicy", {}).get("component") == SAI_UIS_KEY, "UIS component policy missing")
    require(float(weights.get("A_LEGAL_PARTNERSHIP_CONTEXT") or 0) > 0, "SAI legal partnership weight is zero")
    require(float(weights.get("A_PROGRAM_RELEVANCE") or 0) > 0, "SAI program relevance weight is zero")
    require(len(data.get("studentFlowsObserved", {}).get("rows", [])) == 0, "observed student flows should be factual zero rows until a source is added")
    modelled_flows = data.get("studentFlowsModelled", {})
    modelled_rows = modelled_flows.get("rows", [])
    require(len(modelled_rows) >= 20, "modelled attraction potential arrows are missing")
    require(modelled_flows.get("model", {}).get("name") == "SAI_MGIMO_V3", "modelled arrows do not use SAI_MGIMO_V3")
    require(
        modelled_flows.get("model", {}).get("scoreType") == "modelled_attraction_potential_from_open_indicators_not_mgimo_headcount",
        "modelled arrows are not labelled as non-observed MGIMO headcounts",
    )
    for row in modelled_rows[:120]:
        require(row.get("flowType") == "modelled_potential_not_observed_mgimo_students", f"{row.get('originIso3')}: modelled flow type is not explicit")
        require(row.get("modelledPotentialIndex") is not None, f"{row.get('originIso3')}: modelled potential is missing")
        require(row.get("strokeWidth") is not None, f"{row.get('originIso3')}: stroke width is missing")
    for iso3, row in (student.get("byCountry") or {}).items():
        components = row.get("components") or {}
        trace_rows = row.get("componentTrace") or {}
        require(SAI_OLD_MOBILITY_KEY not in components and SAI_OLD_MOBILITY_KEY not in trace_rows, f"{iso3}: old SAI mobility component remains")
        if row.get("saiMgimoV3Score") is not None:
            require(SAI_UIS_KEY in components, f"{iso3}: UIS component missing")
            trace = trace_rows.get(SAI_UIS_KEY) or {}
            missing = [key for key in SAI_TRACE_REQUIRED if trace.get(key) in (None, "")]
            require(not missing, f"{iso3}: UIS trace missing {missing}")
        filters = row.get("hardFilters") or {}
        hard = any(bool(filters.get(key)) for key in ("unfriendly_430r", "domestic_russia", "non_sovereign_or_special"))
        if hard:
            require(row.get("saiMgimoV3Score") is None, f"{iso3}: hard-filtered student country has score")
            require(row.get("rankPracticalStudentRecruitment") is None and row.get("rankReferenceAll") is None, f"{iso3}: hard-filtered student country has rank")

    factor_long_path = ROOT / "docs/data/factor_inputs_long.json"
    require(factor_long_path.exists(), "factor_inputs_long.json missing")
    if factor_long_path.exists():
        factor_rows = load_json(factor_long_path)
        vnm_status_rows = [
            row for row in factor_rows
            if row.get("iso3") == "VNM"
            and row.get("factor_key") == "I_RUSCOMP"
            and str(row.get("input_key", "")).lower() == "inpreparation"
        ]
        require(vnm_status_rows, "Vietnam in-preparation trace row missing")
        for row in vnm_status_rows:
            require(float(row.get("input_weight", 1) or 0) == 0, "Vietnam in-preparation trace has nonzero input weight")
            require("not_scored" in str(row.get("scoring_role", "")).lower() or "reference" in str(row.get("scoring_role", "")).lower(), "Vietnam in-preparation trace is not marked as reference/non-scored")


def check_branch_dictionary() -> None:
    json_path = ROOT / "docs/data/branch_factor_indicator_dictionary_v3.json"
    csv_path = ROOT / "docs/data/branch_factor_indicator_dictionary_v3.csv"
    require(json_path.exists(), "branch factor indicator dictionary JSON missing")
    require(csv_path.exists(), "branch factor indicator dictionary CSV missing")
    if not json_path.exists():
        return
    rows = load_json(json_path)
    require(isinstance(rows, list) and len(rows) >= 7, "branch factor dictionary is empty")
    factors = {row.get("factor_key") for row in rows if isinstance(row, dict)}
    require(factors == {"I_MARKET", "I_PROGRAM", "I_RUSCOMP", "I_ECO", "I_FIN", "I_FEAS", "I_HRSTRAT"}, f"branch dictionary factors mismatch: {sorted(factors)}")
    required = {
        "official_indicator_code",
        "official_indicator_name_ru",
        "source_name",
        "year",
        "unit",
        "normalization_method",
        "observation_status",
        "within_factor_weight",
        "input_key",
        "factor_key",
    }
    for row in rows[:200]:
        missing = [key for key in required if key not in row]
        require(not missing, f"branch dictionary row missing fields {missing}: {row.get('official_indicator_code')}")
        require(not str(row.get("official_indicator_code", "")).startswith("I_"), f"internal pseudo-code remains in dictionary: {row.get('official_indicator_code')}")


def check_archives() -> None:
    bad_tokens = ("node_modules/", ".pytest_cache/", "__pycache__/", term("live", "_final") + "/", term("final", "_snapshot") + "/")
    for archive in ROOT.glob("*.zip"):
        with zipfile.ZipFile(archive) as zf:
            names = [name.replace("\\", "/") for name in zf.namelist()]
        bad = [name for name in names if any(token in name for token in bad_tokens)]
        require(not bad, f"{archive.name} contains forbidden archive entries, first={bad[0] if bad else ''}")


def check_workspace_hygiene() -> None:
    forbidden_dirs = [
        ROOT / ("internal_archive/outputs/" + term("live", "_final")),
        ROOT / ("internal_archive/outputs/" + term("final", "_snapshot")),
        ROOT / ".pytest_cache",
    ]
    forbidden_dirs.extend(ROOT.glob("**/__pycache__"))
    for path in forbidden_dirs:
        require(not path.exists(), f"forbidden cache/output path exists: {path.relative_to(ROOT)}")


def check_playwright_summary() -> None:
    summary_path = ROOT / "test-results/playwright-summary.json"
    if not summary_path.exists():
        require(False, "Playwright JSON summary not found; run e2e for final gate")
        return
    source_paths = [p for p in PUBLIC_SCAN_PATHS if p.exists()]
    source_paths.extend([ROOT / "tests/dashboard.spec.js", ROOT / "playwright.config.js"])
    newest_source = max((p.stat().st_mtime for p in source_paths if p.exists()), default=0)
    if summary_path.stat().st_mtime < newest_source:
        require(False, "Playwright JSON summary is stale; run e2e for final gate")
        return
    summary = load_json(summary_path)
    for error in summary.get("errors", []):
        unexpected_message = error.get("message") if isinstance(error, dict) else str(error)
        unexpected_message = unexpected_message or "<unknown Playwright reporter error>"
        FAIL.append(f"Playwright JSON top-level error: {unexpected_message}")
    unexpected: list[str] = []
    for suite in summary.get("suites", []):
        stack = [suite]
        while stack:
            node = stack.pop()
            stack.extend(node.get("suites", []))
            for spec in node.get("specs", []):
                for test in spec.get("tests", []):
                    status = test.get("status")
                    if status not in {"expected", "skipped"}:
                        result_statuses = ",".join(result.get("status", "?") for result in test.get("results", []))
                        unexpected.append(f"{spec.get('title', '<untitled>')} [{status}; results={result_statuses}]")
    require(not unexpected, "Playwright JSON has unexpected failures: " + "; ".join(unexpected[:8]))


def main() -> None:
    check_public_text()
    check_visual_contract()
    check_payload_contract()
    check_branch_dictionary()
    check_archives()
    check_workspace_hygiene()
    check_playwright_summary()

    for message in WARN:
        print("WARN: " + message)
    if FAIL:
        for message in FAIL:
            if message:
                print("FAIL: " + message)
        raise SystemExit(1)
    print("static dashboard review gate passed")


if __name__ == "__main__":
    main()
