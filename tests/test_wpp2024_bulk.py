from __future__ import annotations

import pytest

from mgimo_ranker.sources.wpp2024_bulk import (
    DEFAULT_WPP_HISTORICAL,
    DEFAULT_WPP_PROJECTION,
    build_age_sex_pyramid_from_panel,
    build_demographic_features_from_panel,
    load_wpp_age_sex_panel,
)


pytestmark = pytest.mark.skipif(
    not DEFAULT_WPP_HISTORICAL.exists() or not DEFAULT_WPP_PROJECTION.exists(),
    reason="local UN WPP 2024 bulk files are not present",
)


def test_wpp2024_china_vietnam_aggregates_are_summed_from_single_age_sex_rows():
    panel = load_wpp_age_sex_panel(iso_filter=["CHN", "VNM"])
    features = build_demographic_features_from_panel(panel, target_years=[2026, 2035, 2050], base_year=2026)
    by_iso = features.set_index("iso3")

    for iso3 in ["CHN", "VNM"]:
        for year in [2024, 2026, 2035, 2050]:
            raw = panel[panel["iso3"].eq(iso3) & panel["year"].eq(year)]
            total = raw["total"].sum()
            pop_15_24 = raw[raw["age_start"].between(15, 24)]["total"].sum()
            field_suffix = "current" if year == 2024 else str(year)
            assert by_iso.loc[iso3, f"population_total_{field_suffix}"] == pytest.approx(total)
            assert by_iso.loc[iso3, f"pop_15_24_{field_suffix}"] == pytest.approx(pop_15_24)


def test_wpp2024_pyramid_youth_bands_match_15_24_aggregate():
    panel = load_wpp_age_sex_panel(iso_filter=["CHN", "VNM"])
    pyramids = build_age_sex_pyramid_from_panel(panel)

    for iso3, pyramid in pyramids.items():
        assert pyramid["highlightAgeBands"] == ["15-19", "20-24"]
        assert "25-29" not in pyramid["highlightAgeBands"]
        year_idx = pyramid["forecastYears"].index(2024)
        band_idx = [pyramid["ageBands"].index("15-19"), pyramid["ageBands"].index("20-24")]
        youth_pyramid = sum(pyramid["forecastMale"][year_idx][i] + pyramid["forecastFemale"][year_idx][i] for i in band_idx)
        youth_raw = panel[panel["iso3"].eq(iso3) & panel["year"].eq(2024) & panel["age_start"].between(15, 24)]["total"].sum()
        assert youth_pyramid == pytest.approx(youth_raw)
