from __future__ import annotations

import pandas as pd


def _safe_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in cols:
        if col not in out.columns:
            out[col] = pd.NA
    return out[cols]


def apply_static_flags(
    features: pd.DataFrame,
    unfriendly: pd.DataFrame,
    presence: pd.DataFrame,
    partners: pd.DataFrame | None = None,
    non_sovereign: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Attach legal, MGIMO-presence, territorial and partner-university flags.

    v0.3 keeps the official unfriendly list as a hard normative filter, but also
    imports the platform project's sovereign-country screen and preserves all
    excluded cases in diagnostic output.
    """
    df = features.copy()
    df["iso3"] = df["iso3"].astype(str).str.upper()
    df = df.drop(
        columns=[
            c
            for c in [
                "is_unfriendly",
                "has_existing_mgimo_branch",
                "has_mgimo_presence",
                "has_mgimo_pipeline",
                "mgimo_presence_type",
                "mgimo_pipeline_status",
                "mgimo_pipeline_status_label",
                "mgimo_pipeline_stage",
                "mgimo_planned_program_profile",
                "mgimo_presence_city",
                "mgimo_presence_notes",
            ]
            if c in df.columns
        ],
        errors="ignore",
    )

    unf = unfriendly.copy()
    unf["iso3"] = unf["iso3"].astype(str).str.upper()
    unf = _safe_cols(unf, ["iso3", "entry_type", "group_label", "source_basis", "hard_exclude"])
    unf_cols = unf.drop_duplicates("iso3").rename(
        columns={
            "entry_type": "unfriendly_entry_type",
            "group_label": "unfriendly_group_label",
            "source_basis": "unfriendly_source_basis",
            "hard_exclude": "unfriendly_hard_exclude",
        }
    )
    df = df.merge(unf_cols, on="iso3", how="left")
    df["is_unfriendly"] = pd.to_numeric(df["unfriendly_hard_exclude"], errors="coerce").fillna(0).astype(int).eq(1)

    prs = presence.copy()
    prs["iso3"] = prs["iso3"].astype(str).str.upper()
    prs = _safe_cols(
        prs,
        [
            "iso3",
            "presence_type",
            "exclude_from_new_branch_ranking",
            "pipeline_status",
            "pipeline_stage",
            "planned_program_profile",
            "city",
            "latitude",
            "longitude",
            "coordinate_source",
            "notes",
        ],
    )
    prs_cols = prs.drop_duplicates("iso3").rename(
        columns={
            "presence_type": "mgimo_presence_type",
            "exclude_from_new_branch_ranking": "has_existing_mgimo_branch",
            "pipeline_status": "mgimo_pipeline_status",
            "pipeline_stage": "mgimo_pipeline_stage",
            "planned_program_profile": "mgimo_planned_program_profile",
            "city": "mgimo_presence_city",
            "latitude": "mgimo_presence_latitude",
            "longitude": "mgimo_presence_longitude",
            "coordinate_source": "mgimo_presence_coordinate_source",
            "notes": "mgimo_presence_notes",
        }
    )
    df = df.merge(prs_cols, on="iso3", how="left")
    df["has_existing_mgimo_branch"] = pd.to_numeric(df["has_existing_mgimo_branch"], errors="coerce").fillna(0).astype(int).eq(1)
    df["has_mgimo_presence"] = df["mgimo_presence_type"].notna()
    df["has_mgimo_pipeline"] = pd.to_numeric(df["mgimo_pipeline_status"], errors="coerce").fillna(0).astype(int).eq(1)
    df["mgimo_pipeline_status_label"] = pd.NA
    df.loc[df["has_mgimo_pipeline"], "mgimo_pipeline_status_label"] = "В подготовке"

    if non_sovereign is not None and not non_sovereign.empty:
        ns = non_sovereign.copy()
        rename = {"country_code": "iso3", "Country Code": "iso3", "country_name": "name", "Country Name": "name", "exclude_reason": "reason"}
        ns = ns.rename(columns={k: v for k, v in rename.items() if k in ns.columns})
        ns["iso3"] = ns["iso3"].astype(str).str.upper()
        ns = _safe_cols(ns, ["iso3", "name", "reason", "hard_exclude"])
        ns["hard_exclude"] = pd.to_numeric(ns["hard_exclude"], errors="coerce").fillna(1).astype(int)
        ns_cols = ns.drop_duplicates("iso3").rename(columns={"name": "non_sovereign_name", "reason": "non_sovereign_reason", "hard_exclude": "non_sovereign_hard_exclude"})
        df = df.merge(ns_cols, on="iso3", how="left")
    if "non_sovereign_hard_exclude" not in df:
        df["non_sovereign_hard_exclude"] = 0
    df["is_non_sovereign_or_special"] = pd.to_numeric(df["non_sovereign_hard_exclude"], errors="coerce").fillna(0).astype(int).eq(1)
    df["is_domestic_russia"] = df["iso3"].eq("RUS")

    if partners is not None and not partners.empty:
        pts = partners.copy()
        pts["iso3"] = pts["iso3"].astype(str).str.upper()
        pts = _safe_cols(pts, ["iso3", "partner_count", "strategic_partner_count", "partner_notes"])
        pts["partner_count"] = pd.to_numeric(pts["partner_count"], errors="coerce").fillna(0)
        pts["strategic_partner_count"] = pd.to_numeric(pts["strategic_partner_count"], errors="coerce").fillna(0)
        pts = pts.groupby("iso3", as_index=False).agg(
            partner_universities_mgimo_count=("partner_count", "max"),
            strategic_partner_universities_count=("strategic_partner_count", "max"),
            partner_notes=("partner_notes", lambda x: "; ".join(str(v) for v in x.dropna().unique()[:3])),
        )
        df = df.merge(pts, on="iso3", how="left")
    if "partner_universities_mgimo_count" not in df:
        df["partner_universities_mgimo_count"] = 0
    if "strategic_partner_universities_count" not in df:
        df["strategic_partner_universities_count"] = 0
    df["partner_universities_mgimo_count"] = pd.to_numeric(df["partner_universities_mgimo_count"], errors="coerce").fillna(0)
    df["strategic_partner_universities_count"] = pd.to_numeric(df["strategic_partner_universities_count"], errors="coerce").fillna(0)
    return df


def apply_eligibility(
    df: pd.DataFrame,
    hard_exclude_unfriendly: bool = True,
    hard_exclude_existing_branch: bool = True,
    hard_exclude_domestic: bool = True,
    hard_exclude_non_sovereign: bool = True,
    min_data_quality: float = 0.0,
) -> pd.DataFrame:
    out = df.copy()
    out["eligible"] = True
    reasons = []
    for _, row in out.iterrows():
        r: list[str] = []
        if hard_exclude_unfriendly and bool(row.get("is_unfriendly", False)):
            r.append("unfriendly_country_hard_exclusion")
        if hard_exclude_existing_branch and bool(row.get("has_existing_mgimo_branch", False)):
            r.append("existing_mgimo_branch_hard_exclusion")
        if hard_exclude_domestic and bool(row.get("is_domestic_russia", False)):
            r.append("domestic_russia_hard_exclusion")
        if hard_exclude_non_sovereign and bool(row.get("is_non_sovereign_or_special", False)):
            r.append("non_sovereign_or_special_hard_exclusion")
        dq = row.get("DATAQ", 1.0)
        if pd.notna(dq) and float(dq) < min_data_quality:
            r.append("low_data_quality")
        reasons.append(";".join(r))
    out["exclusion_reason"] = reasons
    out.loc[out["exclusion_reason"].ne(""), "eligible"] = False
    return out
