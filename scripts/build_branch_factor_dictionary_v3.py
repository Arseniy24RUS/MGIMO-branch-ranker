#!/usr/bin/env python3
"""Build the public branch factor indicator dictionary from curated mappings."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
IN_JSON = ROOT / "docs/data/factor_inputs_long.json"
OUT_JSON = ROOT / "docs/data/branch_factor_indicator_dictionary_v3.json"
OUT_CSV = ROOT / "docs/data/branch_factor_indicator_dictionary_v3.csv"

MODELLED = "not_applicable_modelled_component"

FACTOR_NAMES = {
    "I_MARKET": ("Market attractiveness", "Привлекательность рынка"),
    "I_PROGRAM": ("Program-industry relevance", "Программно-отраслевая релевантность"),
    "I_RUSCOMP": ("Legal-partnership context", "Нормативно-партнёрский контекст"),
    "I_ECO": ("Economic context", "Экономический контекст"),
    "I_FIN": ("Financial feasibility", "Финансовая реализуемость"),
    "I_FEAS": ("Operational feasibility", "Операционная реализуемость"),
    "I_HRSTRAT": ("Strategic talent fit", "Стратегический кадровый эффект"),
}

SOURCE_NAMES = {
    "un_wpp2024_population_by_single_age_sex": "UN World Population Prospects 2024",
    "world_bank_indicators_long": "World Bank World Development Indicators",
    "world_bank_wgi_long": "World Bank WGI, LPI and WDI operational indicators",
    "mgimo_presence": "MGIMO partner registry and Government of Russia Order No. 430-r",
    "live_merged_features": "MGIMO Branch Ranker derived model output",
}

OFFICIAL_MAP: dict[str, tuple[str, str, str]] = {
    "populationTotalCurrent": ("UN_WPP2024.POP.TOTAL.BOTH_SEXES", "Численность населения, всего", "UN WPP 2024 PopulationBySingleAgeSex aggregate"),
    "youth15_24_2026": ("UN_WPP2024.POP.15_24.BOTH_SEXES", "Население 15-24 лет, оба пола", "UN WPP 2024 PopulationBySingleAgeSex aggregate"),
    "tertiaryEnrollmentGross": ("SE.TER.ENRR", "Валовой охват высшим образованием", "World Bank WDI tertiary gross enrollment"),
    "gdpPppCurrent": ("NY.GDP.MKTP.PP.CD", "ВВП по ППС, текущие международные доллары", "World Bank WDI GDP PPP"),
    "gdpPcPppCurrent": ("NY.GDP.PCAP.PP.CD", "ВВП на душу населения по ППС", "World Bank WDI GDP per capita PPP"),
    "gdpGrowthReal": ("NY.GDP.MKTP.KD.ZG", "Рост ВВП, годовой процент", "World Bank WDI real GDP growth"),
    "inflationCpi": ("FP.CPI.TOTL.ZG", "Инфляция потребительских цен", "World Bank WDI CPI inflation"),
    "unemployment": ("SL.UEM.TOTL.ZS", "Безработица, всего", "World Bank WDI unemployment"),
    "tradePercentGdp": ("NE.TRD.GNFS.ZS", "Торговля товарами и услугами, процент ВВП", "World Bank WDI trade share"),
    "servicesValueAdded": ("NV.SRV.TOTL.ZS", "Добавленная стоимость услуг, процент ВВП", "World Bank WDI services share"),
    "priceLevelIndex": ("PA.NUS.PPPC.RF", "Коэффициент пересчёта ППС к рыночному обменному курсу", "World Bank WDI price level ratio"),
    "politicalStability": ("PV.EST", "Политическая стабильность и отсутствие насилия/терроризма", "World Bank Worldwide Governance Indicators"),
    "governmentEffectiveness": ("GE.EST", "Эффективность государственного управления", "World Bank Worldwide Governance Indicators"),
    "regulatoryQuality": ("RQ.EST", "Качество регулирования", "World Bank Worldwide Governance Indicators"),
    "ruleOfLaw": ("RL.EST", "Верховенство права", "World Bank Worldwide Governance Indicators"),
    "controlCorruption": ("CC.EST", "Контроль коррупции", "World Bank Worldwide Governance Indicators"),
    "logisticsPerformanceIndex": ("LP.LPI.OVRL.XQ", "Индекс эффективности логистики", "World Bank Logistics Performance Index"),
    "internetUsersPct": ("IT.NET.USER.ZS", "Пользователи интернета, процент населения", "World Bank WDI internet users"),
    "urbanPopulationPct": ("SP.URB.TOTL.IN.ZS", "Городское население, процент населения", "World Bank WDI urban population share"),
    "partnerUniversitiesMgimoCount": ("MGIMO_PARTNER_UNIVERSITIES.COUNT", "Партнёрские университеты МГИМО", "MGIMO partner registry"),
    "strategicPartnerUniversitiesCount": ("MGIMO_STRATEGIC_PARTNERS.COUNT", "Стратегические партнёрские университеты", "MGIMO partner registry"),
    "hasExistingMgimoBranch": ("MGIMO_BRANCH_PRESENCE.FLAG", "Действующее присутствие МГИМО", "MGIMO public presence reference"),
    "inPreparation": ("MGIMO_PIPELINE_STATUS.FLAG", "Проект в подготовке", "MGIMO management status, zero score weight"),
    "isUnfriendly": ("RU_GOV_ORDER_430R.UNFRIENDLY_COUNTRY_FLAG", "Недружественная страна по распоряжению Правительства РФ N 430-р", "Government of Russia Order No. 430-r"),
    "isDomesticRussia": ("ISO3166.RUS.DOMESTIC_FLAG", "Россия как внутренняя юрисдикция", "ISO 3166 country reference"),
    "isNonSovereignOrSpecial": ("ISO3166.SPECIAL_TERRITORY_FLAG", "Особая или несамостоятельная территория", "ISO 3166 / map boundary reference"),
}

MODELLED_NAMES_RU = {
    "addressableMarketStudents2026": "Адресуемый пул студентов, 2026",
    "addressableMarketStudents2035": "Адресуемый пул студентов, 2035",
    "addressableMarketStudents2050": "Адресуемый пул студентов, 2050",
    "affordabilityFactor": "Ценовая доступность",
    "amsGrowth2026_2035": "Рост адресуемого пула 2026-2035",
    "amsGrowth2026_2050": "Рост адресуемого пула 2026-2050",
    "avgTuitionUsd": "Средняя стоимость обучения",
    "capexUsd": "Первичные затраты",
    "captureCeiling": "Предельный охват",
    "demandPoolStudents": "Потенциальный пул студентов",
    "digitalFinanceProfileScore": "Цифровые финансы и бизнес-информатика",
    "economicLegalProfileScore": "Экономико-правовой профиль",
    "educationHubScore": "Позиция образовательного центра",
    "educationScore": "Образовательный контекст",
    "energyLogisticsProfileScore": "Энергетика и логистика",
    "fieldFitFactor": "Отраслевая релевантность",
    "hostSubsidyShare": "Доля субсидирования принимающей стороны",
    "nationalPriorityDiplomacy": "Национальный приоритет дипломатии",
    "nationalPriorityEnergy": "Национальный приоритет энергетики",
    "nationalPriorityLogistics": "Национальный приоритет логистики",
    "npvExpectedUsd": "Ожидаемая приведённая стоимость",
    "npvPositiveProbability": "Вероятность положительной приведённой стоимости",
    "programFit": "Соответствие программ",
    "recommendedFormat": "Рекомендуемый формат",
    "recommendedProfile": "Рекомендуемый профиль",
    "sectorDepthScore": "Глубина отраслевого спроса",
    "strategicHrFit": "Стратегическое кадровое соответствие",
    "studentPool2026": "Студенческий пул, 2026",
    "studentsYear1": "Студенты в первый год",
    "studentsYear10": "Студенты в десятый год",
}


def english_name(input_key: str) -> str:
    text = input_key.replace("profiles.", "profile ")
    text = text.replace("_", " ")
    out: list[str] = []
    for char in text:
        if out and char.isupper() and out[-1].islower():
            out.append(" ")
        out.append(char)
    return "".join(out).strip().capitalize()


def modelled_name_ru(input_key: str) -> str:
    if input_key.startswith("profiles."):
        suffix = input_key.split(".", 1)[1].replace("_", " ")
        return f"Профиль программы: {suffix}"
    return MODELLED_NAMES_RU.get(input_key, english_name(input_key))


def unit_for(input_key: str, raw_value: Any) -> str:
    key = input_key.lower()
    if isinstance(raw_value, bool):
        return "flag"
    if any(token in key for token in ("usd", "npv", "capex", "tuition")):
        return "USD"
    if "gdp" in key:
        return "international USD" if "current" in key or "ppp" in key else "%"
    if "logisticsperformanceindex" in key:
        return "score"
    if any(token in key for token in ("share", "pct", "probability", "enrollment", "inflation", "unemployment", "growth", "users", "percent")):
        return "%"
    if any(token in key for token in ("score", "factor", "fit", "profile", "stability", "quality", "law", "corruption", "effectiveness")):
        return "0-1"
    if any(token in key for token in ("population", "students", "pool", "market", "youth")):
        return "people"
    if "count" in key:
        return "count"
    return ""


def official_meta(input_key: str) -> tuple[str, str, str]:
    if input_key in OFFICIAL_MAP:
        return OFFICIAL_MAP[input_key]
    return (
        MODELLED,
        modelled_name_ru(input_key),
        "Derived/modelled component; see evidence rows for official source inputs and normalization.",
    )


def main() -> int:
    rows = json.loads(IN_JSON.read_text(encoding="utf-8"))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        factor_key = str(row.get("factor_key") or "")
        input_key = str(row.get("input_key") or "")
        if not factor_key or not input_key:
            continue
        grouped[(factor_key, input_key)].append(row)

    out_rows: list[dict[str, Any]] = []
    for (factor_key, input_key), items in sorted(grouped.items()):
        first = sorted(items, key=lambda row: (str(row.get("country") or ""), str(row.get("iso3") or "")))[0]
        years = [row.get("year") for row in items if row.get("year") not in (None, "")]
        source_keys = sorted({str(row.get("source_key") or "") for row in items if row.get("source_key")})
        observations = sorted({str(row.get("observation_status") or "") for row in items if row.get("observation_status")})
        code, official_name_ru, note = official_meta(input_key)
        factor_name_en, factor_name_ru = FACTOR_NAMES.get(factor_key, (factor_key, factor_key))
        source_name = "; ".join(SOURCE_NAMES.get(key, key) for key in source_keys)
        out_rows.append({
            "model": "BRANCH_INDEX_MGIMO_V3",
            "factor_key": factor_key,
            "factor_name_en": factor_name_en,
            "factor_name_ru": factor_name_ru,
            "input_key": input_key,
            "official_indicator_code": code,
            "official_indicator_name_en": english_name(input_key),
            "official_indicator_name_ru": official_name_ru,
            "source_name": source_name,
            "year": max(years) if years else "",
            "unit": unit_for(input_key, first.get("raw_value")),
            "normalization_method": first.get("normalization_method") or "",
            "observation_status": ";".join(observations),
            "within_factor_weight": first.get("input_weight"),
            "factor_weight": first.get("factor_weight"),
            "scoring_role": first.get("scoring_role") or "",
            "notes": note,
        })

    OUT_JSON.write_text(json.dumps(out_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        writer.writeheader()
        writer.writerows(out_rows)
    print(f"saved {OUT_JSON}")
    print(f"saved {OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
