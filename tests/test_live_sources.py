from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest

from mgimo_ranker.config import load_config
from mgimo_ranker.model.transform import worldbank_long_to_features
from mgimo_ranker.pipeline import run_pipeline
from mgimo_ranker.sources.wgi import WGI_ESTIMATE_COL, WGI_SHEET_TO_FIELD, parse_wgi_excel, wgi_long_to_features
from mgimo_ranker.sources.un_wpp import parse_un_csv
from mgimo_ranker.sources.wpp2024_bulk import (
    WPP_SOURCE_KEY,
    build_age_sex_pyramid_from_panel,
    build_demographic_features_from_panel,
    build_demography_series_from_panel,
)
from mgimo_ranker.utils import latest_by_country


def test_un_csv_parser_accepts_separator_hint_variants():
    compact = "sep=|\nId|Name|Iso3\n4|Afghanistan|AFG\n"
    spaced = "sep =|\nId|Name|Iso3\n8|Albania|ALB\n"

    assert parse_un_csv(compact).loc[0, "Iso3"] == "AFG"
    assert parse_un_csv(spaced).loc[0, "Iso3"] == "ALB"


def test_latest_by_country_uses_latest_non_null_value():
    rows = pd.DataFrame(
        [
            {"iso3": "AAA", "indicator": "gdp_ppp_current", "year": 2024, "value": 100},
            {"iso3": "AAA", "indicator": "gdp_ppp_current", "year": 2026, "value": None},
        ]
    )
    latest = latest_by_country(rows)

    assert latest.iloc[0]["year"] == 2024
    assert latest.iloc[0]["value"] == 100


def test_worldbank_transform_preserves_latest_non_null_indicators_and_years():
    indicators = [f"indicator_{i:02d}" for i in range(17)]
    rows = []
    for indicator in indicators:
        rows.extend(
            [
                {"iso3": "AAA", "country": "Example", "indicator": indicator, "year": 2024, "value": 100},
                {"iso3": "AAA", "country": "Example", "indicator": indicator, "year": 2026, "value": None},
            ]
        )

    features = worldbank_long_to_features(pd.DataFrame(rows))
    row = features.iloc[0]

    for indicator in indicators:
        assert row[indicator] == 100
        assert row[f"{indicator}_year"] == 2024


def test_wgi_parser_builds_latest_governance_features():
    workbook = BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        for sheet in WGI_SHEET_TO_FIELD:
            pd.DataFrame(
                [
                    {"Economy (code)": "AAA", "Economy (name)": "Example", "Year": 2023, WGI_ESTIMATE_COL: 0.1},
                    {"Economy (code)": "AAA", "Economy (name)": "Example", "Year": 2024, WGI_ESTIMATE_COL: 0.2},
                ]
            ).to_excel(writer, sheet_name=sheet, index=False)
    workbook.seek(0)

    long = parse_wgi_excel(workbook)
    features = wgi_long_to_features(long)
    row = features.loc[features["iso3"].eq("AAA")].iloc[0]

    for field in WGI_SHEET_TO_FIELD.values():
        assert row[field] == pytest.approx(0.2)
        assert row[f"{field}_year"] == 2024


def _wpp_panel_for_iso(iso3: str, country: str = "Example") -> pd.DataFrame:
    rows = []
    for year in [2000, 2014, 2023, 2024, 2026, 2030, 2035, 2050]:
        status = "official_estimate" if year <= 2023 else "official_projection"
        year_shift = (year - 2000) * 0.2
        for age in range(0, 101):
            male = 100.0 + age + year_shift
            female = 115.0 + age + year_shift
            rows.append(
                {
                    "iso3": iso3,
                    "country": country,
                    "year": year,
                    "age_start": age,
                    "male": male,
                    "female": female,
                    "total": male + female,
                    "observation_status": status,
                }
            )
    return pd.DataFrame(rows)


def test_wpp_bulk_demographic_features_build_youth_fields_from_single_age_rows():
    panel = _wpp_panel_for_iso("AAA")
    features = build_demographic_features_from_panel(panel, target_years=[2026, 2035, 2050], base_year=2026)
    row = features.loc[features["iso3"].eq("AAA")].iloc[0]
    current = panel[(panel["year"].eq(2024))]
    target_2026 = panel[(panel["year"].eq(2026))]

    assert row["population_total_current"] == pytest.approx(current["total"].sum())
    assert row["pop_15_24_current"] == pytest.approx(current[current["age_start"].between(15, 24)]["total"].sum())
    assert row["pop_15_24_2026"] == pytest.approx(target_2026[target_2026["age_start"].between(15, 24)]["total"].sum())
    assert row["student_pool_2026"] == pytest.approx(
        target_2026[target_2026["age_start"].between(15, 24)]["total"].sum()
        + 0.45 * target_2026[target_2026["age_start"].between(25, 29)]["total"].sum()
    )
    assert row["demography_source"] == WPP_SOURCE_KEY


def test_wpp_demographic_series_uses_official_estimate_and_projection_status():
    series = build_demography_series_from_panel(_wpp_panel_for_iso("AAA"), highlight_years=[2026, 2030])["AAA"]

    assert [row["year"] for row in series["actual"]] == [2000, 2014, 2023]
    assert [row["year"] for row in series["forecast"]] == [2024, 2026, 2030, 2035, 2050]
    assert {row["observation_status"] for row in series["actual"]} == {"official_estimate"}
    assert {row["observation_status"] for row in series["forecast"]} == {"official_projection"}
    assert series["highlightYears"] == [2026, 2030]


def test_wpp_age_sex_pyramid_highlights_only_15_24_bands():
    panel = _wpp_panel_for_iso("AAA")
    pyramid = build_age_sex_pyramid_from_panel(panel)["AAA"]

    assert pyramid["dataStatus"] == "available"
    assert pyramid["highlightAgeBands"] == ["15-19", "20-24"]
    assert pyramid["actualYears"] == [2023]
    assert pyramid["forecastYears"] == [2024, 2026, 2035, 2050]
    assert pyramid["yearStatuses"]["2023"] == "official_estimate"
    assert pyramid["yearStatuses"]["2024"] == "official_projection"
    year_idx = pyramid["forecastYears"].index(2024)
    band_idx = [pyramid["ageBands"].index("15-19"), pyramid["ageBands"].index("20-24")]
    youth_pyramid = sum(pyramid["forecastMale"][year_idx][i] + pyramid["forecastFemale"][year_idx][i] for i in band_idx)
    youth_panel = panel[panel["year"].eq(2024) & panel["age_start"].between(15, 24)]["total"].sum()
    assert youth_pyramid == pytest.approx(youth_panel)


def test_live_pipeline_writes_raw_source_metadata(monkeypatch, tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "configs" / "default.yaml")
    cfg.raw["financial"]["finance_mc_iterations"] = 0

    countries = pd.DataFrame(
        {
            "iso3": ["IND", "BRA"],
            "iso2": ["IN", "BR"],
            "country": ["India", "Brazil"],
            "region": ["South Asia", "Latin America & Caribbean"],
            "income_group": ["Lower middle income", "Upper middle income"],
        }
    )
    wb_long = pd.DataFrame(
        [
            {"iso3": iso3, "country": country, "indicator": indicator, "year": 2024, "value": value, "source": "world_bank_indicators"}
            for iso3, country in [("IND", "India"), ("BRA", "Brazil")]
            for indicator, value in [
                ("gdp_ppp_current", 1_000_000),
                ("gdp_pc_ppp_current", 12000),
                ("gdp_growth_real", 5),
                ("tertiary_enrollment_gross", 35),
                ("school_enrollment_secondary", 85),
                ("internet_users", 75),
                ("trade_percent_gdp", 45),
                ("services_value_added", 55),
                ("urban_population_pct", 65),
                ("lpi_overall", 3.1),
                ("price_level_index", 55),
            ]
        ]
    )
    imf_long = pd.DataFrame(
        [
            {"iso3": iso3, "indicator": indicator, "year": 2026, "value": value, "source": "imf_datamapper"}
            for iso3 in ["IND", "BRA"]
            for indicator, value in [("real_gdp_growth", 4.5), ("inflation", 4.0), ("unemployment", 7.0)]
        ]
    )
    wpp_features = build_demographic_features_from_panel(
        pd.concat([_wpp_panel_for_iso("IND", "India"), _wpp_panel_for_iso("BRA", "Brazil")], ignore_index=True),
        target_years=cfg.target_years,
        base_year=cfg.base_year,
    )
    wgi_features = pd.DataFrame(
        [
            {
                "iso3": iso3,
                "country": country,
                "wgi_political_stability": 0.1,
                "wgi_government_effectiveness": 0.2,
                "wgi_regulatory_quality": 0.3,
                "wgi_rule_of_law": 0.4,
                "wgi_control_corruption": 0.5,
            }
            for iso3, country in [("IND", "India"), ("BRA", "Brazil")]
        ]
    )
    wgi_long = pd.DataFrame(
        [
            {"iso3": row["iso3"], "country": row["country"], "indicator": field, "year": 2024, "value": row[field], "source": "world_bank_wgi_2025_excel"}
            for _, row in wgi_features.iterrows()
            for field in WGI_SHEET_TO_FIELD.values()
        ]
    )

    monkeypatch.setattr("mgimo_ranker.pipeline.fetch_countries", lambda: countries)
    monkeypatch.setattr("mgimo_ranker.pipeline.fetch_wb_indicators", lambda *args, **kwargs: wb_long)
    monkeypatch.setattr("mgimo_ranker.pipeline.fetch_imf_indicators", lambda *args, **kwargs: imf_long)
    monkeypatch.setattr("mgimo_ranker.pipeline.fetch_wgi_features", lambda *args, **kwargs: (b"sample-xlsx", wgi_long, wgi_features))
    hist = tmp_path / "WPP2024_PopulationBySingleAgeSex_Medium_1950-2023.csv.gz"
    proj = tmp_path / "WPP2024_PopulationBySingleAgeSex_Medium_2024-2100.csv.gz"
    hist.write_bytes(b"")
    proj.write_bytes(b"")
    monkeypatch.setattr("mgimo_ranker.pipeline.resolve_wpp_paths", lambda *args, **kwargs: (hist, proj))
    monkeypatch.setattr("mgimo_ranker.pipeline.load_wpp_demographic_features", lambda *args, **kwargs: wpp_features)

    files = run_pipeline(cfg, root / "data", tmp_path, mode="live", mc_iterations=0, usd_rub=73.3436)
    metadata = json.loads(Path(files["run_metadata"]).read_text(encoding="utf-8"))

    assert metadata["source_errors"] == []
    assert metadata["valid_for_location_analysis"] is True
    assert "source_manifest" in files
    for key in [
        "world_bank_countries",
        "un_wpp2024_age_sex_historical",
        "un_wpp2024_age_sex_projection",
        "un_wpp2024_demographic_features",
        "world_bank_wgi_features",
        "live_merged_features",
        "cbr_exchange_rate",
    ]:
        assert key in metadata["raw_source_files"]
        assert Path(metadata["raw_source_files"][key]).exists()
