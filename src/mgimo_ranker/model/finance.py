from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from mgimo_ranker.utils import robust_norm


def estimate_tuition_usd(row: pd.Series, fin_cfg: dict[str, Any], level: str = "ba") -> float:
    ref = float(fin_cfg.get("tuition_reference_usd_ba" if level == "ba" else "tuition_reference_usd_ma", 7000))
    ref_gdp_pc = float(fin_cfg.get("reference_gdp_pc_ppp", 35000))
    gdp_pc = row.get("gdp_pc_ppp_current", np.nan)
    if pd.isna(gdp_pc) or gdp_pc <= 0:
        gdp_pc = ref_gdp_pc
    income_factor = 0.60 + 0.40 * min(2.0, max(0.35, (float(gdp_pc) / ref_gdp_pc) ** 0.35))
    profile_premium = 1.0 + 0.08 * max(0.0, float(row.get("PROGRAM_FIT", 0.5)) - 0.5)
    discount = float(fin_cfg.get("scholarship_discount", 0.15))
    return ref * income_factor * profile_premium * (1.0 - discount)


def purchasing_power_cost_factor(row: pd.Series, fin_cfg: dict[str, Any]) -> float:
    """Local cost multiplier for non-tradable CAPEX/OPEX.

    v0.3 combines the v0.2 income channel with the platform project's World Bank
    price-level index when available. This avoids treating all high-income
    countries as equally costly and makes the financial model closer to the
    country-panel evidence supplied by the second application.
    """
    ref_gdp_pc = float(fin_cfg.get("reference_gdp_pc_ppp", 35000))
    gdp_pc = row.get("gdp_pc_ppp_current", np.nan)
    if pd.isna(gdp_pc) or gdp_pc <= 0:
        income_factor = 1.0
    else:
        income_factor = min(1.55, max(0.50, (float(gdp_pc) / ref_gdp_pc) ** 0.35))
    pli = row.get("price_level_index", np.nan)
    if pd.isna(pli) or pli <= 0:
        return float(income_factor)
    pli_factor = min(1.75, max(0.35, float(pli) / 100.0))
    return min(1.70, max(0.45, 0.55 * income_factor + 0.45 * pli_factor))


def risk_premium(row: pd.Series, fin_cfg: dict[str, Any]) -> float:
    max_prem = float(fin_cfg.get("risk_premium_max", 0.20))
    feas = row.get("I_FEAS", 0.5)
    if pd.isna(feas):
        feas = 0.5
    return max_prem * (1.0 - min(1.0, max(0.0, float(feas))))


def demand_pool(row: pd.Series) -> float:
    """Addressable market for a transnational MGIMO branch.

    Use the computed addressable-market field from the indices module.
    """
    ams = row.get("addressable_market_students_2026", np.nan)
    if pd.notna(ams) and float(ams) > 0:
        return float(ams)
    return math.nan


def capture_ceiling(row: pd.Series, fin_cfg: dict[str, Any]) -> float:
    base = float(fin_cfg.get("base_conversion_rate", 0.00015))
    program_fit = float(row.get("PROGRAM_FIT", 0.5))
    ruscomp = float(row.get("I_RUSCOMP", 1.0))
    partners = min(3.0, float(row.get("partner_universities_mgimo_count", 0) or 0))
    strategic_partners = min(2.0, float(row.get("strategic_partner_universities_count", 0) or 0))
    partner_bonus = float(fin_cfg.get("partner_capture_bonus", 0.08)) * partners
    strategic_bonus = float(fin_cfg.get("strategic_partner_capture_bonus", 0.06)) * strategic_partners
    competition = float(row.get("international_branch_competition", 0) or 0)
    competition_penalty = float(fin_cfg.get("competition_capture_penalty", 0.05)) * min(5.0, competition)
    multiplier = (0.70 + 0.60 * program_fit) * (0.60 + 0.40 * ruscomp) * (1 + partner_bonus + strategic_bonus - competition_penalty)
    return max(0.0, base * multiplier)


def estimate_students(
    row: pd.Series,
    fin_cfg: dict[str, Any],
    fmt_cfg: dict[str, Any],
    year: int,
    capture_multiplier: float = 1.0,
) -> float:
    capacity = float(fmt_cfg["capacity_students"])
    midpoint = float(fmt_cfg.get("capture_midpoint_year", fin_cfg.get("capture_midpoint_year", 3.5)))
    steepness = float(fmt_cfg.get("capture_steepness", fin_cfg.get("capture_steepness", 0.90)))
    s_curve = 1.0 / (1.0 + math.exp(-steepness * (year - midpoint)))
    cap = capture_ceiling(row, fin_cfg) * max(0.0, capture_multiplier)
    expected = demand_pool(row) * cap * s_curve
    min_launch = float(fmt_cfg.get("minimum_launch_students", 0)) if year == 1 else 0.0
    return min(capacity, max(min_launch, expected))


def npv(cashflows: list[float], discount_rate: float, capex: float) -> float:
    val = -capex
    for i, cf in enumerate(cashflows, start=1):
        val += cf / ((1 + discount_rate) ** i)
    return float(val)


def payback_year(cashflows: list[float], capex: float) -> float:
    cum = -capex
    for i, cf in enumerate(cashflows, start=1):
        cum += cf
        if cum >= 0:
            return float(i)
    return math.inf


def capex_for_format(row: pd.Series, fin_cfg: dict[str, Any], fmt_cfg: dict[str, Any]) -> tuple[float, float, float, float]:
    cost_factor = purchasing_power_cost_factor(row, fin_cfg)
    prem = risk_premium(row, fin_cfg)
    if "capex_base_usd" in fmt_cfg:
        base = float(fmt_cfg["capex_base_usd"])
        capex = base * cost_factor * (1 + prem)
        return capex, cost_factor, prem, base
    trad = float(fmt_cfg.get("capex_tradables_usd", 0))
    nontrad = float(fmt_cfg.get("capex_nontradables_base_usd", 0)) * cost_factor
    regulatory = float(fmt_cfg.get("capex_regulatory_usd", 0)) * (1 + prem)
    contingency = float(fin_cfg.get("capex_contingency", 0.10))
    capex = (trad + nontrad + regulatory) * (1 + contingency) * (1 + prem)
    return capex, cost_factor, prem, trad + nontrad + regulatory


def _host_subsidy_share(row: pd.Series, fin_cfg: dict[str, Any], fmt_cfg: dict[str, Any]) -> float:
    base = float(fmt_cfg.get("host_subsidy_share", fin_cfg.get("host_subsidy_share", 0.0)))
    if float(row.get("partner_universities_mgimo_count", 0) or 0) > 0:
        base = max(base, float(fin_cfg.get("partner_host_subsidy_share", 0.08)))
    return min(0.60, max(0.0, base))


def _cashflows_for_format(
    row: pd.Series,
    fin_cfg: dict[str, Any],
    fmt_cfg: dict[str, Any],
    horizon: int,
    tuition_mult: float = 1.0,
    opex_mult: float = 1.0,
    capture_mult: float = 1.0,
    subsidy_share_delta: float = 0.0,
) -> tuple[list[float], float, float, float, float]:
    cost_factor = purchasing_power_cost_factor(row, fin_cfg)
    prem = risk_premium(row, fin_cfg)
    fixed_opex = float(fmt_cfg["fixed_opex_usd"]) * cost_factor * (1 + prem) * opex_mult
    var_opex = float(fmt_cfg["variable_opex_per_student_usd"]) * cost_factor * opex_mult
    tuition_ba = estimate_tuition_usd(row, fin_cfg, "ba") * tuition_mult
    tuition_ma = estimate_tuition_usd(row, fin_cfg, "ma") * tuition_mult
    avg_tuition = 0.70 * tuition_ba + 0.30 * tuition_ma
    collection_rate = float(fin_cfg.get("collection_rate", 0.96))
    base_execed_y10 = float(fmt_cfg.get("execed_revenue_year10_usd", 0))
    subsidy_share = min(0.60, max(0.0, _host_subsidy_share(row, fin_cfg, fmt_cfg) + subsidy_share_delta))
    cashflows: list[float] = []
    students_last = 0.0
    for year in range(1, horizon + 1):
        students = estimate_students(row, fin_cfg, fmt_cfg, year, capture_multiplier=capture_mult)
        students_last = students
        ramp = min(1.0, year / max(1, horizon))
        tuition_revenue = students * avg_tuition * collection_rate
        execed_revenue = base_execed_y10 * ramp
        opex = fixed_opex + students * var_opex
        host_subsidy = subsidy_share * opex
        cashflows.append(tuition_revenue + execed_revenue + host_subsidy - opex)
    return cashflows, students_last, avg_tuition, fixed_opex, var_opex


def _lognormal_mean_one(rng: np.random.Generator, sigma: float, size: int) -> np.ndarray:
    if sigma <= 0:
        return np.ones(size)
    return rng.lognormal(mean=-0.5 * sigma**2, sigma=sigma, size=size)


def simulate_npv_distribution(
    row: pd.Series,
    fin_cfg: dict[str, Any],
    fmt_cfg: dict[str, Any],
    horizon: int,
    discount_rate: float,
    capex: float,
    rng: np.random.Generator,
    n: int,
) -> np.ndarray:
    if n <= 0:
        cashflows, *_ = _cashflows_for_format(row, fin_cfg, fmt_cfg, horizon)
        return np.array([npv(cashflows, discount_rate, capex)])
    tuition_sigma = float(fin_cfg.get("mc_tuition_sigma", 0.08))
    opex_sigma = float(fin_cfg.get("mc_opex_sigma", 0.12))
    capture_sigma = float(fin_cfg.get("mc_capture_sigma", 0.25))
    capex_sigma = float(fin_cfg.get("mc_capex_sigma", 0.10))
    subsidy_sigma = float(fin_cfg.get("mc_subsidy_share_sigma", 0.03))
    vals = np.empty(n, dtype=float)
    tuition_mults = _lognormal_mean_one(rng, tuition_sigma, n)
    opex_mults = _lognormal_mean_one(rng, opex_sigma, n)
    capture_mults = _lognormal_mean_one(rng, capture_sigma, n)
    capex_mults = _lognormal_mean_one(rng, capex_sigma, n)
    subsidy_deltas = rng.normal(0, subsidy_sigma, n) if subsidy_sigma > 0 else np.zeros(n)
    for i in range(n):
        cashflows, *_ = _cashflows_for_format(
            row,
            fin_cfg,
            fmt_cfg,
            horizon,
            tuition_mult=float(tuition_mults[i]),
            opex_mult=float(opex_mults[i]),
            capture_mult=float(capture_mults[i]),
            subsidy_share_delta=float(subsidy_deltas[i]),
        )
        vals[i] = npv(cashflows, discount_rate, capex * float(capex_mults[i]))
    return vals


def run_financial_model(features: pd.DataFrame, fin_cfg: dict[str, Any], usd_rub: float | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    horizon = int(fin_cfg.get("horizon_years", 10))
    discount_rate = float(fin_cfg.get("discount_rate", 0.11))
    formats = fin_cfg.get("formats", {})
    mc_n = int(fin_cfg.get("finance_mc_iterations", 100))
    rng = np.random.default_rng(int(fin_cfg.get("finance_mc_seed", 42)))
    for _, row in features.iterrows():
        for fmt, fmt_cfg in formats.items():
            capex, cost_factor, prem, capex_base_for_diag = capex_for_format(row, fin_cfg, fmt_cfg)
            cashflows, students_last, avg_tuition, fixed_opex, var_opex = _cashflows_for_format(row, fin_cfg, fmt_cfg, horizon)
            val = npv(cashflows, discount_rate, capex)
            pby = payback_year(cashflows, capex)
            margin_y10 = cashflows[-1] / (students_last * avg_tuition) if students_last > 0 and avg_tuition > 0 else np.nan
            breakeven_students = fixed_opex / max(1.0, avg_tuition * float(fin_cfg.get("collection_rate", 0.96)) - var_opex)
            sims = simulate_npv_distribution(row, fin_cfg, fmt_cfg, horizon, discount_rate, capex, rng, mc_n)
            rows.append(
                {
                    "iso3": row["iso3"],
                    "country": row.get("country"),
                    "format": fmt,
                    "capacity_students": fmt_cfg["capacity_students"],
                    "capex_usd": capex,
                    "capex_base_usd_for_diag": capex_base_for_diag,
                    "cost_factor": cost_factor,
                    "risk_premium": prem,
                    "capex_rub": capex * usd_rub if usd_rub else np.nan,
                    "avg_tuition_usd": avg_tuition,
                    "students_year_1": estimate_students(row, fin_cfg, fmt_cfg, 1),
                    "students_year_10": students_last,
                    "capture_ceiling": capture_ceiling(row, fin_cfg),
                    "demand_pool_students": demand_pool(row),
                    "host_subsidy_share": _host_subsidy_share(row, fin_cfg, fmt_cfg),
                    "annual_revenue_year_10_usd": students_last * avg_tuition * float(fin_cfg.get("collection_rate", 0.96)) + float(fmt_cfg.get("execed_revenue_year10_usd", 0)),
                    "annual_opex_year_10_usd": fixed_opex + students_last * var_opex,
                    "cashflow_year_10_usd": cashflows[-1],
                    "npv_10y_usd": val,
                    "npv_10y_rub": val * usd_rub if usd_rub else np.nan,
                    "npv_expected_usd": float(np.mean(sims)),
                    "npv_expected_rub": float(np.mean(sims)) * usd_rub if usd_rub else np.nan,
                    "npv_p10_usd": float(np.quantile(sims, 0.10)),
                    "npv_p90_usd": float(np.quantile(sims, 0.90)),
                    "npv_positive_probability": float(np.mean(sims > 0)),
                    "payback_years": pby,
                    "margin_year_10": margin_y10,
                    "breakeven_students": breakeven_students,
                    "discount_rate": discount_rate,
                }
            )
    financial = pd.DataFrame(rows)
    if financial.empty:
        best = pd.DataFrame(columns=["iso3"])
    else:
        sort_df = financial.copy()
        sort_df["payback_sort"] = sort_df["payback_years"].replace(math.inf, 999)
        best = (
            sort_df.sort_values(
                ["iso3", "npv_positive_probability", "npv_expected_usd", "npv_10y_usd", "payback_sort"],
                ascending=[True, False, False, False, True],
            )
            .groupby("iso3", as_index=False)
            .head(1)
        )
        best = best.drop(columns=["payback_sort"])
        best = best.rename(columns={"format": "recommended_format"})
    return financial, best


def add_financial_index(features: pd.DataFrame, best_financial: pd.DataFrame) -> pd.DataFrame:
    df = features.merge(best_financial, on=["iso3"], how="left", suffixes=("", "_fin"))
    if "npv_10y_usd" not in df:
        df["I_FIN"] = 0.5
        return df
    if "npv_expected_usd" in df and "npv_positive_probability" in df:
        df["N_expected_npv"] = robust_norm(df["npv_expected_usd"], positive=True)
        df["I_FIN"] = (0.70 * df["npv_positive_probability"].fillna(0.0) + 0.30 * df["N_expected_npv"].fillna(0.5)).clip(0, 1)
        return df
    df["N_npv"] = robust_norm(df["npv_10y_usd"], positive=True)
    df["N_margin"] = robust_norm(df["margin_year_10"], positive=True)
    payback = df["payback_years"].replace(math.inf, np.nan)
    df["N_payback"] = robust_norm(payback, positive=False).fillna(0.0)
    df["N_capex"] = robust_norm(df["capex_usd"], positive=False)
    df["I_FIN"] = (
        0.45 * df["N_npv"].fillna(0.5)
        + 0.25 * df["N_margin"].fillna(0.5)
        + 0.20 * df["N_payback"].fillna(0.0)
        + 0.10 * df["N_capex"].fillna(0.5)
    ).clip(0, 1)
    return df
