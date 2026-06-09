import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SAI_UIS_KEY = "A_OUTBOUND_MOBILITY_UIS"


def term(*parts: str) -> str:
    return "".join(parts)

def test_student_attraction_v3_uses_open_data_scores_without_manual_region_bonus():
    df = pd.read_csv(ROOT / "docs/data/student_attraction_v3.csv")
    scored = df[df["rank_practical_student_recruitment"].notna()]
    assert len(scored) > 100
    assert scored["score_source_policy"].eq("open_api_factual_only").all()
    required = [
        "pop_15_24_latest",
        "pop_15_24_growth_10y_pct",
        "uis_outbound_mobility_ratio",
        "uis_outbound_mobility_year",
        "uis_source_key",
        "uis_observation_status",
        "internet_users_pct",
        "gdp_pc_ppp_current",
    ]
    assert scored[required].notna().all().all()


def test_student_modelled_potential_flows_are_separated_from_observed_data():
    flows = pd.read_csv(ROOT / "docs/data/student_flows_modelled_v3.csv")
    assert len(flows) > 20
    assert {"origin_iso3", "destination_city", "flow_type", "modelled_potential_index", "stroke_width", "source", "year"}.issubset(flows.columns)
    assert flows["flow_type"].eq("modelled_potential_not_observed_mgimo_students").all()
    payload = json.loads((ROOT / "docs/data/mgimo_dashboard_data.json").read_text(encoding="utf-8"))
    assert payload["studentFlowsModelled"]["model"]["name"] == "SAI_MGIMO_V3"
    assert payload["studentFlowsModelled"]["coverage"]["status"] == "modelled_potential_not_observed"
    assert len(payload["studentFlowsModelled"]["rows"]) == len(flows)
    assert "financial_model_recommended_format_student_ramp" not in json.dumps(payload["studentFlowsModelled"], ensure_ascii=False)
    assert term("deprecated_", "fall", "back", "_financial_model_not_student_attraction") not in json.dumps(payload["studentFlowsModelled"], ensure_ascii=False)
    assert payload["studentFlowsObserved"]["coverage"]["status"] == "not_available_country_level_mgimo"


def test_hard_filter_countries_have_no_practical_student_rank():
    df = pd.read_csv(ROOT / "docs/data/student_attraction_v3.csv")
    hard = df[df[["is_unfriendly_430r", "is_domestic_russia", "is_non_sovereign_or_special"]].astype(bool).any(axis=1)]
    assert hard["rank_practical_student_recruitment"].isna().all()
    assert hard["rank_reference_all"].isna().all()
    assert hard["SAI_MGIMO_V3_SCORE"].isna().all()


def test_no_legacy_decision_modes_in_methodology():
    text = "\n".join(p.read_text(encoding="utf-8") for p in [ROOT / "docs/MGIMO_THIRD_GEN_SYSTEM_SPEC_RU.md", ROOT / "docs/METHODOLOGY_STUDENT_ATTRACTION_RU.md"])
    for banned in [term("soft", "_power"), term("risk", "_averse"), term("comm", "ercial"), term("final", "_snapshot"), term("live", "_final")]:
        assert banned not in text


def test_student_attraction_has_no_branch_rank_substitution_contract():
    payload = json.loads((ROOT / "docs/data/mgimo_dashboard_data.json").read_text(encoding="utf-8"))
    serialized = json.dumps(payload["studentAttraction"], ensure_ascii=False)
    assert term("fall", "back", "_from_prepared_inputs") not in serialized
    assert "top20ByDefaultPriority" not in serialized
    assert "attractionScore" not in serialized
    for iso3, row in list(payload["studentAttraction"]["byCountry"].items())[:20]:
        assert row["model"] == "SAI_MGIMO_V3", iso3
        assert row["componentTrace"]
        assert SAI_UIS_KEY in row["componentTrace"]
        assert row["componentTrace"][SAI_UIS_KEY]["source_key"] == "unesco_uis_uis006_mor_5t8_40510"
        for trace in row["componentTrace"].values():
            assert trace["source_key"]
            assert trace["year"]
            assert trace["raw_value"] is not None
            assert trace["normalized_value"] is not None
            assert trace["normalization_method"]
            assert trace["weight"] is not None
            assert trace["observation_status"]
