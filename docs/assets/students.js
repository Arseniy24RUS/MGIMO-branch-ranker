(() => {
  'use strict';

  const DATA_URL = 'data/mgimo_dashboard_data.json';
  const STUDENT_FLOWS_OBSERVED_URL = 'data/student_flows_observed.csv';
  const STUDENT_MODEL_META_URL = 'data/student_model_v3_metadata.json';
  const GEO_URL = 'data/world_admin_boundaries_ru_claimed_update_2026.geojson';
  const LOCALE_URLS = { ru: 'locales/ru.json', en: 'locales/en.json' };
  const MOSCOW = { lat: 55.7558, lon: 37.6176, label: 'Moscow' };
  const STUDENT_UI_VERSION = '20260608-exec-sai-v3-uis';
  const USE_STORED_UI_STATE = localStorage.getItem('mgimo_students_ui_version') === STUDENT_UI_VERSION;
  const DEFAULT_SELECTED_ISO = '';
  const DEFAULT_TOP_N = '20';
  const SAI_V3_WEIGHTS = {
    A_YOUTH_OPPORTUNITY: 0.50,
    A_OUTBOUND_MOBILITY_UIS: 0.16,
    A_LEGAL_PARTNERSHIP_CONTEXT: 0.12,
    A_PROGRAM_RELEVANCE: 0.08,
    A_AFFORDABILITY_ACCESS: 0.06,
    A_DIGITAL_REACH: 0.04,
    A_DATAQ: 0.04
  };
  const STUDENT_STATUS_COLORS = {
    candidate: '#397a21',
    practical_priority_pool: '#397a21',
    in_preparation: '#dfaa00',
    in_preparation_but_ranked: '#dfaa00',
    presence: '#041d49',
    partner_model: '#3d68d6',
    domestic: '#9aa4b3',
    domestic_excluded: '#9aa4b3',
    excluded: '#9aa4b3',
    reference_only: '#9aa4b3',
    special_territory: '#9aa4b3',
    special_territory_reference_only: '#9aa4b3',
    unfriendly: '#8c95a3',
    unfriendly_reference_only: '#8c95a3',
    not_recommended: '#9aa4b3',
    monitoring: '#9aa4b3'
  };
  const MAP_ISO_FIELDS = ['iso_a3', 'adm0_a3', 'wb_a3', 'adm0_iso', 'sov_a3', 'gu_a3'];
  const LANGUAGE_ISO = {
    ru: ['ARM', 'AZE', 'BLR', 'GEO', 'KAZ', 'KGZ', 'MDA', 'TJK', 'TKM', 'UKR', 'UZB'],
    zh: ['CHN', 'HKG', 'MAC', 'TWN', 'SGP'],
    ar: ['ARE', 'BHR', 'DZA', 'EGY', 'IRQ', 'JOR', 'KWT', 'LBN', 'LBY', 'MAR', 'OMN', 'PSE', 'QAT', 'SAU', 'SDN', 'SYR', 'TUN', 'YEM'],
    es: ['ARG', 'BOL', 'CHL', 'COL', 'CRI', 'CUB', 'DOM', 'ECU', 'ESP', 'GTM', 'HND', 'MEX', 'NIC', 'PAN', 'PER', 'PRY', 'SLV', 'URY', 'VEN'],
    pt: ['AGO', 'BRA', 'CPV', 'GNB', 'MOZ', 'PRT', 'STP'],
    fr: ['BEL', 'BEN', 'BFA', 'BDI', 'CAF', 'CAN', 'CHE', 'CIV', 'CMR', 'COD', 'COG', 'DJI', 'FRA', 'GAB', 'GIN', 'HTI', 'LUX', 'MDG', 'MLI', 'MRT', 'NER', 'RWA', 'SEN', 'TCD', 'TGO']
  };

  const state = {
    lang: ['ru', 'en'].includes(localStorage.getItem('mgimo_students_lang') || localStorage.getItem('mgimo_lang'))
      ? (localStorage.getItem('mgimo_students_lang') || localStorage.getItem('mgimo_lang'))
      : 'ru',
    mode: USE_STORED_UI_STATE ? (localStorage.getItem('mgimo_students_mode') || 'practical') : 'practical',
    region: USE_STORED_UI_STATE ? (localStorage.getItem('mgimo_students_region') || 'all') : 'all',
    status: USE_STORED_UI_STATE ? (localStorage.getItem('mgimo_students_status') || 'all') : 'all',
    topN: USE_STORED_UI_STATE ? (localStorage.getItem('mgimo_students_top_n') || DEFAULT_TOP_N) : DEFAULT_TOP_N,
    program: USE_STORED_UI_STATE ? (localStorage.getItem('mgimo_students_program') || 'all') : 'all',
    language: USE_STORED_UI_STATE ? (localStorage.getItem('mgimo_students_language') || 'all') : 'all',
    selectedIso3: USE_STORED_UI_STATE ? (localStorage.getItem('mgimo_students_selected_iso3') || DEFAULT_SELECTED_ISO) : DEFAULT_SELECTED_ISO,
    visualRegion: null,
    activeStudentFactorKey: 'A_YOUTH_OPPORTUNITY',
    activeStudentMethodInputKey: 'A_YOUTH_OPPORTUNITY',
    showDirectionArcs: USE_STORED_UI_STATE ? localStorage.getItem('mgimo_students_show_direction_arcs') !== 'false' : true,
    i18n: window.MGIMO_I18N || {},
    payload: null,
    observedFlowRows: [],
    studentModelMeta: null,
    geo: null,
    rows: [],
    flowRows: [],
    countryByIso: new Map(),
    rowByIso: new Map(),
    geoNameByIso: new Map(),
    map: null,
    countryLayer: null,
    flowLayer: null,
    pointLayer: null,
    selectedLayer: null,
    usingPayloadAttraction: false,
    usingObservedFlows: false
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const clean = (value) => {
    if (value === undefined || value === null || value === '') return null;
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
  };
  const bool = (value) => value === true || value === 1 || value === '1' || String(value).toLowerCase() === 'true';
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

  function t(key, params = {}) {
    let value = state.i18n?.[state.lang]?.[key] ?? state.i18n?.en?.[key] ?? key;
    if (typeof value !== 'string') return value;
    Object.entries(params).forEach(([name, replacement]) => {
      value = value.replaceAll(`{${name}}`, replacement);
    });
    return value;
  }

  function fmt(value, digits = 1) {
    const number = clean(value);
    if (number === null) return t('noData');
    return number.toLocaleString(state.lang === 'ru' ? 'ru-RU' : 'en-US', { maximumFractionDigits: digits });
  }

  function fmtInt(value) {
    return fmt(value, 0);
  }

  function fmtScore(value) {
    return fmt(value, 1);
  }

  function fmtPct(value, digits = 0) {
    const number = clean(value);
    if (number === null) return t('noData');
    return `${fmt(number * 100, digits)}%`;
  }

  function isoFlag(iso2) {
    const code = String(iso2 || '').trim().toUpperCase();
    return /^[A-Z]{2}$/.test(code) ? code : '';
    if (code.length !== 2 || !/^[A-Z]{2}$/.test(code)) return '•';
    return code.replace(/./g, (char) => String.fromCodePoint(127397 + char.charCodeAt()));
  }

  function flagHtml(iso2, className = 'inline-flag') {
    const code = String(iso2 || '').trim().toUpperCase();
    if (code.length !== 2 || !/^[A-Z]{2}$/.test(code)) {
      return `<span class="${className} flag-empty" aria-hidden="true"></span>`;
    }
    const src = `assets/vendor/flags/4x3/${code.toLowerCase()}.svg`;
    return `<span class="${className} flag-image" aria-hidden="true"><img src="${src}" alt="" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false;"><span class="flag-native-mark" hidden>${isoFlag(code)}</span></span>`;
  }

  function normalizeRegion(region) {
    return String(region || '')
      .trim()
      .replace('Middle East, North Africa, Afghanistan & Pakistan', 'Middle East & North Africa')
      .replace('Middle East, North Africa, Afghanistan and Pakistan', 'Middle East & North Africa');
  }

  function i18nMap(type, value) {
    if (!value) return '-';
    const normalized = type === 'region' ? normalizeRegion(value) : String(value).trim();
    return t(`${type}.${normalized}`);
  }

  function programLabel(value) {
    const normalized = String(value || '').trim();
    return t(`programProfile.${normalized}`);
  }

  function languageLabel(value) {
    return t(`students.language.${value || 'en'}`);
  }

  function statusClass(country) {
    if (!country) return 'candidate';
    if (country.status_code) return country.status_code;
    const rec = country.recommendation_category || country.recommendationCategory;
    if (rec === 'in_preparation' || country.branchStatus || bool(country.has_mgimo_pipeline)) return 'in_preparation';
    if (bool(country.has_existing_mgimo_branch)) return 'presence';
    if (!bool(country.eligible) || country.exclusion_reason) return 'excluded';
    if (rec === 'A_open_priority') return 'candidate';
    if (rec === 'B_strategic_with_subsidy') return 'partner_model';
    return 'monitoring';
  }

  function statusLabelFromKey(key) {
    const label = t(`students.status.${key}`);
    return label === `students.status.${key}` ? String(key || '').replaceAll('_', ' ') : label;
  }

  function statusLabel(country) {
    return statusLabelFromKey(statusClass(country));
  }

  function studentStatusColor(row) {
    return STUDENT_STATUS_COLORS[row?.status]
      || STUDENT_STATUS_COLORS[statusClass(row?.country)]
      || STUDENT_STATUS_COLORS.monitoring;
  }

  function countryName(country) {
    const geoNames = state.geoNameByIso.get(country?.iso3) || {};
    if (state.lang === 'ru') return geoNames.ru || country?.country_ru || country?.nameRu || country?.country || country?.name || country?.country_en || country?.iso3 || '-';
    return country?.country_en || country?.nameEn || geoNames.en || country?.country || country?.name || country?.country_ru || country?.iso3 || '-';
  }

  function fieldValue(row, names) {
    for (const name of names) {
      if (row && row[name] !== undefined && row[name] !== null && row[name] !== '') return row[name];
    }
    return null;
  }

  function numberField(row, names) {
    return clean(fieldValue(row, names));
  }

  function normalize01(value, missingValue = null) {
    const number = clean(value);
    if (number === null) return missingValue;
    if (number > 1) return clamp(number / 100, 0, 1);
    return clamp(number, 0, 1);
  }

  function normalizeIndex100(value, missingValue = null) {
    const number = clean(value);
    if (number === null) return missingValue;
    return clamp(number <= 1 ? number * 100 : number, 0, 100);
  }

  function inferLanguage(country) {
    const iso3 = String(country?.iso3 || '').toUpperCase();
    const found = Object.entries(LANGUAGE_ISO).find(([, isoList]) => isoList.includes(iso3));
    if (found) return found[0];
    const region = normalizeRegion(country?.region);
    if (region === 'Latin America & Caribbean') return iso3 === 'BRA' ? 'pt' : 'es';
    if (region === 'Middle East & North Africa') return 'ar';
    if (region === 'Sub-Saharan Africa') return 'fr';
    return 'en';
  }

  function sourceList(value) {
    if (!value) return [];
    if (Array.isArray(value)) return value.map(String).filter(Boolean);
    if (typeof value === 'object') return Object.values(value).flat().map(String).filter(Boolean);
    return String(value).split(/[;|]/).map((part) => part.trim()).filter(Boolean);
  }

  function parseCsv(text) {
    const input = String(text || '').replace(/^\uFEFF/, '');
    const rows = [];
    let row = [];
    let field = '';
    let quoted = false;
    for (let i = 0; i < input.length; i += 1) {
      const ch = input[i];
      const next = input[i + 1];
      if (quoted) {
        if (ch === '"' && next === '"') {
          field += '"';
          i += 1;
        } else if (ch === '"') {
          quoted = false;
        } else {
          field += ch;
        }
      } else if (ch === '"') {
        quoted = true;
      } else if (ch === ',') {
        row.push(field);
        field = '';
      } else if (ch === '\n') {
        row.push(field);
        rows.push(row);
        row = [];
        field = '';
      } else if (ch !== '\r') {
        field += ch;
      }
    }
    if (field || row.length) {
      row.push(field);
      rows.push(row);
    }
    const headers = (rows.shift() || []).map((header) => header.trim());
    if (!headers.length) return [];
    return rows
      .filter((cells) => cells.some((cell) => String(cell || '').trim()))
      .map((cells) => Object.fromEntries(headers.map((header, index) => [header, cells[index] ?? ''])));
  }

  async function fetchOptionalText(url) {
    try {
      const response = await fetch(url);
      if (!response.ok) return '';
      return response.text();
    } catch {
      return '';
    }
  }

  async function fetchOptionalJson(url) {
    try {
      const response = await fetch(url);
      if (!response.ok) return null;
      return response.json();
    } catch {
      return null;
    }
  }

  function normalizeCountry(raw, payload) {
    const factorScores = raw?.factorScores || {};
    const coords = raw?.coordinates || {};
    const program = raw?.program || {};
    const demography = raw?.demography || {};
    const inputs = payload?.factorInputs?.[raw?.iso3] || {};
    const tertiaryGross = clean(inputs.market?.tertiaryEnrollmentGross);
    const internetPct = clean(inputs.feasibility?.internetUsersPct);
    return {
      ...raw,
      __factorInputs: inputs,
      country: raw?.country || raw?.name,
      country_en: raw?.country_en || raw?.name,
      latitude: clean(raw?.latitude) ?? clean(coords.lat),
      longitude: clean(raw?.longitude) ?? clean(coords.lon),
      recommendation_category: raw?.recommendation_category || raw?.recommendationCategory,
      exclusion_reason: raw?.exclusion_reason || raw?.eligibilityReason,
      status_code: raw?.status_code || (raw?.recommendationCategory === 'in_preparation' || raw?.branchStatus ? 'in_preparation' : null),
      recommended_program_profile: raw?.recommended_program_profile || program.recommendedProfile,
      PROGRAM_FIT: clean(raw?.PROGRAM_FIT) ?? clean(program.fitScore),
      I_MARKET: clean(raw?.I_MARKET) ?? clean(factorScores.I_MARKET),
      I_PROGRAM: clean(raw?.I_PROGRAM) ?? clean(factorScores.I_PROGRAM),
      I_RUSCOMP: clean(raw?.I_RUSCOMP) ?? clean(factorScores.I_RUSCOMP),
      I_ECO: clean(raw?.I_ECO) ?? clean(factorScores.I_ECO),
      I_FIN: clean(raw?.I_FIN) ?? clean(factorScores.I_FIN),
      I_FEAS: clean(raw?.I_FEAS) ?? clean(factorScores.I_FEAS),
      I_HRSTRAT: clean(raw?.I_HRSTRAT) ?? clean(factorScores.I_HRSTRAT),
      addressable_market_students_2026: clean(raw?.addressable_market_students_2026) ?? clean(demography.addressableMarketStudents2026),
      student_pool_2026: clean(raw?.student_pool_2026) ?? clean(demography.studentPool2026),
      student_pool_2035: clean(raw?.student_pool_2035) ?? clean(demography.studentPool2035),
      student_pool_growth_2026_2035_pct: clean(raw?.student_pool_growth_2026_2035_pct),
      N_education: clean(raw?.N_education) ?? (tertiaryGross === null ? null : normalize01(tertiaryGross / 100, null)),
      N_internet: clean(raw?.N_internet) ?? (internetPct === null ? null : normalize01(internetPct / 100, null)),
      AFFORDABILITY_FACTOR: clean(raw?.AFFORDABILITY_FACTOR) ?? clean(inputs.market?.affordabilityFactor)
    };
  }

  function attractionMapFromPayload(payload) {
    const map = new Map();
    const modelName = payload?.studentAttraction?.model?.name || payload?.studentAttractionV3?.model?.name;
    if (modelName !== 'SAI_MGIMO_V3') return map;
    const byCountry = payload?.studentAttractionV3?.byCountry || payload?.studentAttraction?.byCountry || {};
    Object.entries(byCountry).forEach(([iso3, row]) => {
      if (!iso3) return;
      map.set(String(iso3).toUpperCase(), row);
    });
    return map;
  }

  function normalizeStudentStatus(value, hardFiltered) {
    const raw = String(value || '').trim();
    if (raw) return raw;
    return hardFiltered ? 'reference_only' : 'practical_priority_pool';
  }

  function normalizedHardStatus(attraction, country, hardFiltered) {
    const inputs = country?.__factorInputs?.russiaCompatibility || {};
    if (bool(attraction?.is_domestic_russia) || bool(inputs.isDomesticRussia)) return 'domestic_excluded';
    if (bool(attraction?.is_non_sovereign_or_special) || bool(inputs.isNonSovereignOrSpecial)) return 'special_territory_reference_only';
    if (bool(attraction?.is_unfriendly_430r) || bool(inputs.isUnfriendly)) return 'unfriendly_reference_only';
    return normalizeStudentStatus(fieldValue(attraction, ['student_recruitment_status', 'status', 'student_status']), hardFiltered);
  }

  function isHardFiltered(attraction, country) {
    const inputs = country?.__factorInputs?.russiaCompatibility || {};
    return bool(attraction?.is_unfriendly_430r)
      || bool(attraction?.is_domestic_russia)
      || bool(attraction?.is_non_sovereign_or_special)
      || bool(inputs.isUnfriendly)
      || bool(inputs.isDomesticRussia)
      || bool(inputs.isNonSovereignOrSpecial);
  }

  function v3ComponentValue(attraction, key) {
    return clean(attraction?.[key])
      ?? clean(attraction?.components?.[key])
      ?? clean(attraction?.componentTrace?.[key]?.normalized_value);
  }

  function v3Components(attraction) {
    return Object.fromEntries(Object.keys(SAI_V3_WEIGHTS).map((key) => [
      key,
      normalize01(v3ComponentValue(attraction, key), null)
    ]));
  }

  function v3ComponentTrace(attraction, hasScore) {
    const trace = attraction?.componentTrace || {};
    const out = {};
    Object.keys(SAI_V3_WEIGHTS).forEach((key) => {
      if (trace[key]) out[key] = trace[key];
      else if (hasScore) throw new Error(`SAI_MGIMO_V3 component trace is missing for ${key}`);
    });
    return out;
  }

  function buildStudentRows(payload) {
    const attractionRows = attractionMapFromPayload(payload);
    state.usingPayloadAttraction = attractionRows.size > 0;
    if (!attractionRows.size) {
      throw new Error('SAI_MGIMO_V3 data are required before the student dashboard can render.');
    }

    const rows = (payload.countries || []).map((country) => normalizeCountry(country, payload))
      .filter((country) => country.iso3)
      .map((country) => {
        const attraction = attractionRows.get(country.iso3);
        if (!attraction) return null;
        const hardFiltered = isHardFiltered(attraction, country);
        const rawSai = numberField(attraction, ['SAI_MGIMO_V3_SCORE', 'saiMgimoV3Score', 'sai', 'SAI', 'student_attraction_index', 'studentAttractionIndex']);
        const status = normalizedHardStatus(attraction, country, hardFiltered);
        return {
          iso3: country.iso3,
          iso2: country.iso2,
          country,
          label: countryName(country),
          region: normalizeRegion(country.region),
          status,
          hardFiltered,
          practicalRank: clean(fieldValue(attraction, ['rank_practical_student_recruitment'])),
          referenceRank: clean(fieldValue(attraction, ['rank_reference_all'])),
          program: String(fieldValue(attraction, ['program', 'recommended_program_profile']) || country.recommended_program_profile || 'digital_finance_business_informatics'),
          language: String(fieldValue(attraction, ['language', 'language_track']) || inferLanguage(country)),
          sai: normalizeIndex100(rawSai, null),
          components: v3Components(attraction),
          componentTrace: v3ComponentTrace(attraction, clean(rawSai) !== null),
          inputs: attraction.inputs || {
            pop_15_24_latest: numberField(attraction, ['pop_15_24_latest']),
            pop_15_24_latest_year: numberField(attraction, ['pop_15_24_latest_year']),
            pop_15_24_growth_10y_pct: numberField(attraction, ['pop_15_24_growth_10y_pct']),
            student_pool_latest: numberField(attraction, ['student_pool_latest']),
            uis_outbound_mobility_ratio: numberField(attraction, ['uis_outbound_mobility_ratio']),
            uis_outbound_mobility_year: numberField(attraction, ['uis_outbound_mobility_year']),
            internet_users_pct: numberField(attraction, ['internet_users_pct']),
            gdp_pc_ppp_current: numberField(attraction, ['gdp_pc_ppp_current']),
            score_source_policy: fieldValue(attraction, ['score_source_policy'])
          },
          payloadSource: [t('students.sourceSaiV3')],
          sourceMode: 'payload',
          dueDiligenceWarnings: String(fieldValue(attraction, ['due_diligence_warnings']) || '')
        };
      })
      .filter(Boolean)
      .sort((left, right) => {
        const leftRank = clean(left.referenceRank) ?? Number.POSITIVE_INFINITY;
        const rightRank = clean(right.referenceRank) ?? Number.POSITIVE_INFINITY;
        return leftRank - rightRank || (clean(right.sai) ?? -1) - (clean(left.sai) ?? -1) || countryName(left.country).localeCompare(countryName(right.country));
      });

    rows.forEach((row, index) => {
      row.rank = index + 1;
    });
    return rows;
  }

  function flowFromPayload(row, evidence) {
    const iso3 = String(fieldValue(row, ['iso3', 'country_iso3', 'origin_iso3', 'from_iso3', 'ISO3']) || '').toUpperCase();
    const student = state.rowByIso.get(iso3);
    const country = student?.country || state.countryByIso.get(iso3);
    if (!iso3 || !country || !student) return null;
    const count = numberField(row, ['students', 'student_count', 'count', 'observed_students', 'observedCount']);
    return {
      iso3,
      evidence: 'observed',
      student,
      country,
      lat: numberField(row, ['latitude', 'lat', 'origin_lat']) ?? clean(country.latitude),
      lon: numberField(row, ['longitude', 'lon', 'lng', 'origin_lon', 'origin_lng']) ?? clean(country.longitude),
      observedCount: count,
      sources: sourceList(fieldValue(row, ['sources', 'source', 'student_sources'])),
      trace: row.trace || {
        source_key: 'student_flows_observed.csv',
        year: fieldValue(row, ['year']),
        raw_value: count,
        normalized_value: count,
        normalization_method: 'observed_student_count',
        weight: 1,
        score_type: 'observed_fact'
      },
      payloadRow: row
    };
  }

  function modelledFlowFromPayload(row) {
    const iso3 = String(fieldValue(row, ['originIso3', 'origin_iso3', 'iso3']) || '').toUpperCase();
    const student = state.rowByIso.get(iso3);
    const country = student?.country || state.countryByIso.get(iso3);
    if (!iso3 || !country || !student) return null;
    const potential = numberField(row, ['modelledPotentialIndex', 'modelled_potential_index', 'potential']);
    return {
      iso3,
      evidence: 'modelled',
      student,
      country,
      lat: numberField(row, ['originLat', 'origin_lat', 'latitude', 'lat']) ?? clean(country.latitude),
      lon: numberField(row, ['originLon', 'origin_lon', 'longitude', 'lon', 'lng']) ?? clean(country.longitude),
      destinationLat: numberField(row, ['destinationLat', 'destination_lat']) ?? MOSCOW.lat,
      destinationLon: numberField(row, ['destinationLon', 'destination_lon']) ?? MOSCOW.lon,
      potentialIndex: potential,
      strokeWidth: numberField(row, ['strokeWidth', 'stroke_width']),
      sources: sourceList(fieldValue(row, ['sources', 'source'])) || [t('students.sourceSaiV3')],
      trace: row.trace || {
        source_key: 'student_flows_modelled_v3.csv',
        year: fieldValue(row, ['year']) || 'latest open indicators',
        raw_value: potential,
        normalized_value: potential === null ? null : potential / 100,
        normalization_method: 'modelled_attraction_potential_from_open_indicators',
        weight: 1,
        score_type: 'modelled_potential_not_observed_student_headcount'
      },
      payloadRow: row
    };
  }

  function buildFlowRows(payload) {
    const observedRows = state.observedFlowRows.map((row) => flowFromPayload(row, 'observed')).filter(Boolean);
    const modelledRows = (payload?.studentFlowsModelled?.rows || []).map(modelledFlowFromPayload).filter(Boolean);
    state.usingObservedFlows = observedRows.length > 0;

    return [...observedRows, ...modelledRows].filter((row) => clean(row.lat) !== null && clean(row.lon) !== null);
  }

  function filteredBaseRows() {
    return state.rows.filter((row) => {
      const hasScore = clean(row.sai) !== null;
      const modeOk = state.mode === 'reference' || (!row.hardFiltered && hasScore);
      const statusOk = state.status === 'all' || row.status === state.status;
      const regionOk = state.region === 'all' || row.region === state.region;
      const programOk = state.program === 'all' || row.program === state.program;
      const languageOk = state.language === 'all' || row.language === state.language;
      return modeOk && statusOk && regionOk && programOk && languageOk;
    });
  }

  function visibleRows() {
    const rankKey = state.mode === 'reference' ? 'referenceRank' : 'practicalRank';
    const rows = filteredBaseRows().sort((left, right) => {
      const lr = clean(left[rankKey]) ?? Number.POSITIVE_INFINITY;
      const rr = clean(right[rankKey]) ?? Number.POSITIVE_INFINITY;
      return lr - rr || (clean(right.sai) ?? -1) - (clean(left.sai) ?? -1) || left.rank - right.rank;
    });
    if (state.topN === 'all') return rows;
    return rows.slice(0, clean(state.topN) || Number(DEFAULT_TOP_N));
  }

  function visibleFlows() {
    const visibleIso = new Set(visibleRows().map((row) => row.iso3));
    return state.flowRows
      .filter((flow) => visibleIso.has(flow.iso3))
      .filter((flow) => flow.evidence === 'observed' || state.showDirectionArcs)
      .sort((left, right) => (clean(right.student.sai) ?? -1) - (clean(left.student.sai) ?? -1));
  }

  function scoredRows() {
    return state.rows.filter((row) => clean(row.sai) !== null && !row.hardFiltered);
  }

  function leaderRow() {
    return [...scoredRows()].sort((left, right) => {
      const lr = clean(left.practicalRank) ?? Number.POSITIVE_INFINITY;
      const rr = clean(right.practicalRank) ?? Number.POSITIVE_INFINITY;
      return lr - rr || (clean(right.sai) ?? -1) - (clean(left.sai) ?? -1) || countryName(left.country).localeCompare(countryName(right.country));
    })[0] || null;
  }

  function selectedRow() {
    if (!state.rowByIso.has(state.selectedIso3)) {
      state.selectedIso3 = visibleRows()[0]?.iso3 || leaderRow()?.iso3 || state.rows[0]?.iso3 || null;
    }
    return state.rowByIso.get(state.selectedIso3) || null;
  }

  function selectedVisualRegion() {
    return state.visualRegion || normalizeRegion(selectedRow()?.region) || null;
  }

  function rowsForVisualRegion() {
    const rows = filteredBaseRows().filter((row) => clean(row.sai) !== null);
    const region = selectedVisualRegion();
    if (region) {
      const regionalRows = rows.filter((row) => normalizeRegion(row.region) === region);
      if (regionalRows.length) return { rows: regionalRows, region };
    }
    return { rows, region: null };
  }

  function selectedFlow() {
    return state.flowRows.find((row) => row.iso3 === state.selectedIso3 && row.evidence === 'observed')
      || state.flowRows.find((row) => row.iso3 === state.selectedIso3 && row.evidence === 'modelled')
      || null;
  }

  function flowSources(flow) {
    if (!flow) return [];
    return flow.sources || [];
  }

  function applyI18n() {
    document.documentElement.lang = state.lang;
    document.title = t('students.appTitle');
    const meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute('content', t('students.subtitle'));
    $$('[data-i18n]').forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });
    $$('[data-i18n-aria-label]').forEach((node) => {
      node.setAttribute('aria-label', t(node.dataset.i18nAriaLabel));
    });
    $('#langRu')?.classList.toggle('active', state.lang === 'ru');
    $('#langEn')?.classList.toggle('active', state.lang === 'en');
  }

  async function loadLocales() {
    const loaded = await Promise.all(Object.entries(LOCALE_URLS).map(async ([lang, url]) => {
      try {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`${url}: ${response.status}`);
        return [lang, await response.json()];
      } catch {
        return [lang, state.i18n[lang] || {}];
      }
    }));
    loaded.forEach(([lang, dict]) => {
      state.i18n[lang] = { ...(state.i18n[lang] || {}), ...dict };
    });
  }

  function saveState() {
    localStorage.setItem('mgimo_students_ui_version', STUDENT_UI_VERSION);
    localStorage.setItem('mgimo_students_lang', state.lang);
    localStorage.setItem('mgimo_lang', state.lang);
    localStorage.setItem('mgimo_students_mode', state.mode);
    localStorage.setItem('mgimo_students_region', state.region);
    localStorage.setItem('mgimo_students_status', state.status);
    localStorage.setItem('mgimo_students_top_n', state.topN);
    localStorage.setItem('mgimo_students_program', state.program);
    localStorage.setItem('mgimo_students_language', state.language);
    localStorage.setItem('mgimo_students_show_direction_arcs', state.showDirectionArcs ? 'true' : 'false');
    if (state.selectedIso3) localStorage.setItem('mgimo_students_selected_iso3', state.selectedIso3);
  }

  function option(value, label, selectedValue) {
    return `<option value="${escapeHtml(value)}"${value === selectedValue ? ' selected' : ''}>${escapeHtml(label)}</option>`;
  }

  function populateSelects() {
    if (!['practical', 'reference'].includes(state.mode)) state.mode = 'practical';
    $('#studentModeSelect').value = state.mode;

    const regions = Array.from(new Set(state.rows.map((row) => row.region))).filter(Boolean).sort();
    $('#studentRegionSelect').innerHTML = [
      option('all', t('region.all'), state.region),
      ...regions.map((region) => option(region, i18nMap('region', region), state.region))
    ].join('');

    const statuses = Array.from(new Set(state.rows.map((row) => row.status))).filter(Boolean).sort();
    $('#studentStatusSelect').innerHTML = [
      option('all', t('category.all'), state.status),
      ...statuses.map((status) => option(status, statusLabelFromKey(status), state.status))
    ].join('');

    const programs = Array.from(new Set(state.rows.map((row) => row.program))).filter(Boolean).sort();
    $('#studentProgramSelect').innerHTML = [
      option('all', t('category.all'), state.program),
      ...programs.map((program) => option(program, programLabel(program), state.program))
    ].join('');

    const languages = Array.from(new Set(state.rows.map((row) => row.language))).filter(Boolean).sort();
    $('#studentLanguageSelect').innerHTML = [
      option('all', t('category.all'), state.language),
      ...languages.map((language) => option(language, languageLabel(language), state.language))
    ].join('');

    $('#studentTopNSelect').value = state.topN;
    $('#studentFlowToggle').checked = state.showDirectionArcs;
    const observedNotice = $('#studentObservedNotice');
    if (observedNotice) observedNotice.hidden = state.usingObservedFlows;
  }

  function updateHeader() {
    const dataMode = $('#studentDataMode');
    if (dataMode) dataMode.textContent = 'SAI_MGIMO_V3';
  }

  function buildGeoNameIndex() {
    state.geoNameByIso.clear();
    (state.geo?.features || []).forEach((feature) => {
      const props = feature.properties || {};
      const iso = MAP_ISO_FIELDS.map((field) => props[field]).find((value) => value && value !== '-99');
      if (!iso) return;
      state.geoNameByIso.set(String(iso).toUpperCase(), {
        ru: props.name_ru || props.NAME_RU || props.admin || props.name,
        en: props.name_en || props.NAME_EN || props.ADMIN || props.name
      });
    });
  }

  function featureIso(feature) {
    const props = feature?.properties || {};
    const iso = MAP_ISO_FIELDS.map((field) => props[field]).find((value) => value && value !== '-99');
    return iso ? String(iso).toUpperCase() : null;
  }

  function studentColorFor(value) {
    const number = clean(value);
    if (number === null) return '#eef3f8';
    const scale = ['#f4ead2', '#dfe8f3', '#c4d7ec', '#9fbee0', '#6f98cb', '#3f73b6', '#073f8f'];
    const index = clamp(Math.floor((clamp(number, 0, 100) / 100) * scale.length), 0, scale.length - 1);
    return scale[index];
  }

  function ensureStudentHatchPattern() {
    const svg = $('#studentMap svg');
    if (!svg || svg.querySelector('#studentReferenceHatch')) return;
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = '<pattern id="studentReferenceHatch" patternUnits="userSpaceOnUse" width="8" height="8"><rect width="8" height="8" fill="#e3e7ee"></rect><path d="M-2 8 L8 -2 M0 10 L10 0" stroke="#8c95a3" stroke-width="1.2" opacity="0.6"></path></pattern>';
    svg.prepend(defs);
  }

  function isDomesticRow(row) {
    return row?.status === 'domestic' || row?.status === 'domestic_excluded' || row?.iso3 === 'RUS';
  }

  function isHatchedReferenceRow(row) {
    return Boolean(row?.hardFiltered && !isDomesticRow(row));
  }

  function studentFeatureStyle(feature) {
    const iso = featureIso(feature);
    const row = iso ? state.rowByIso.get(iso) : null;
    const inFilteredSet = row && filteredBaseRows().some((item) => item.iso3 === iso);
    const hard = isHatchedReferenceRow(row);
    const domestic = isDomesticRow(row);
    const selected = row?.iso3 === state.selectedIso3;
    return {
      color: selected ? studentStatusColor(row) : '#ffffff',
      weight: selected ? 1.8 : 0.55,
      opacity: 0.96,
      fillColor: hard ? 'url(#studentReferenceHatch)' : (domestic ? studentColorFor(row?.country?.priorityScore) : studentColorFor(row?.sai)),
      fillOpacity: row ? (domestic ? 0.62 : (inFilteredSet ? 0.88 : 0.26)) : 0.20,
      className: [
        iso ? `student-country-${iso}` : '',
        hard ? 'student-reference-country' : '',
        domestic ? 'student-domestic-country' : '',
        selected ? 'selected-country' : '',
        inFilteredSet ? '' : 'filtered-out'
      ].join(' ')
    };
  }

  function studentCountryTooltip(row, iso) {
    if (!row) return escapeHtml(iso || '');
    return `
      <div class="student-flow-tooltip">
        <strong>${escapeHtml(countryName(row.country))}</strong>
        <span>${escapeHtml(t('students.saiShort'))}: ${fmtScore(row.sai)}</span>
        <span>${escapeHtml(t('status'))}: ${escapeHtml(statusLabelFromKey(row.status))}</span>
        <small>${escapeHtml(row.hardFiltered ? t('students.referenceOnlyWarning') : t('students.sourceSaiV3'))}</small>
      </div>
    `;
  }

  function initMap() {
    state.map = L.map('studentMap', {
      zoomControl: true,
      attributionControl: false,
      worldCopyJump: true
    }).setView([32, 48], 2);
    state.map.createPane('studentCountries');
    state.map.getPane('studentCountries').style.zIndex = 220;
    state.map.createPane('studentFlows');
    state.map.getPane('studentFlows').style.zIndex = 420;
    state.map.createPane('studentPoints');
    state.map.getPane('studentPoints').style.zIndex = 520;

    if (state.geo?.features?.length) {
      state.countryLayer = L.geoJSON(state.geo, {
        pane: 'studentCountries',
        interactive: true,
        style: studentFeatureStyle,
        onEachFeature: (feature, layer) => {
          const iso = featureIso(feature);
          if (!iso) return;
          layer.on('click', () => selectCountry(iso));
          layer.bindTooltip(() => studentCountryTooltip(state.rowByIso.get(iso), iso), { sticky: true });
        }
      }).addTo(state.map);
      ensureStudentHatchPattern();
    }

    state.flowLayer = L.layerGroup().addTo(state.map);
    state.pointLayer = L.layerGroup().addTo(state.map);
    L.circleMarker([MOSCOW.lat, MOSCOW.lon], {
      pane: 'studentPoints',
      radius: 6,
      color: '#04224d',
      weight: 2,
      fillColor: '#e0aa24',
      fillOpacity: 1
    }).bindTooltip(t('students.moscowTooltip')).addTo(state.pointLayer);
    setTimeout(() => {
      state.map?.invalidateSize();
      state.countryLayer?.redraw?.();
      state.countryLayer?.setStyle(studentFeatureStyle);
    }, 80);
  }

  function curvePoints(fromLat, fromLon, toLat, toLon) {
    const lat1 = clean(fromLat);
    const lon1 = clean(fromLon);
    if (lat1 === null || lon1 === null) return [];
    const points = [];
    const midLat = (lat1 + toLat) / 2;
    const midLon = (lon1 + toLon) / 2;
    const dx = toLon - lon1;
    const dy = toLat - lat1;
    const distance = Math.sqrt(dx * dx + dy * dy);
    const bend = clamp(distance / 10, 8, 22);
    const normalLat = dx === 0 && dy === 0 ? 0 : -dx / Math.max(distance, 1);
    const normalLon = dy === 0 && dx === 0 ? 0 : dy / Math.max(distance, 1);
    const control = [midLat + normalLat * bend, midLon + normalLon * bend];
    for (let i = 0; i <= 32; i += 1) {
      const tValue = i / 32;
      const inv = 1 - tValue;
      const lat = inv * inv * lat1 + 2 * inv * tValue * control[0] + tValue * tValue * toLat;
      const lon = inv * inv * lon1 + 2 * inv * tValue * control[1] + tValue * tValue * toLon;
      points.push([lat, lon]);
    }
    return points;
  }

  function flowTooltip(flow) {
    const isModelled = flow?.evidence === 'modelled';
    const label = isModelled ? t('students.evidenceModelled') : t('students.evidenceObserved');
    const source = flowSources(flow)[0] || (isModelled ? t('students.sourceSaiV3') : t('students.sourceObservedPayload'));
    const value = isModelled
      ? t('students.tooltipModelledPotential', { value: fmtScore(flow.potentialIndex) })
      : t('students.tooltipObservedCount', { count: fmtInt(flow.observedCount) });
    return `
      <div class="student-flow-tooltip">
        <strong>${escapeHtml(countryName(flow.country))}</strong>
        <span>${escapeHtml(t('students.saiShort'))}: ${fmtScore(flow.student.sai)}</span>
        <span>${escapeHtml(label)}: ${escapeHtml(value)}</span>
        ${isModelled ? `<span>${escapeHtml(t('students.notMgimoStudents'))}</span>` : ''}
        <small>${escapeHtml(source)}</small>
      </div>
    `;
  }

  function directionTooltip(row) {
    return `
      <div class="student-flow-tooltip">
        <strong>${escapeHtml(countryName(row.country))}</strong>
        <span>${escapeHtml(t('students.saiShort'))}: ${fmtScore(row.sai)}</span>
        <span>${escapeHtml(t('students.directionArc'))}</span>
        <small>${escapeHtml(t('students.sourceSaiV3'))}</small>
      </div>
    `;
  }

  function arrowHeadPoints(points) {
    if (!points || points.length < 3) return null;
    const tipIndex = Math.max(2, Math.min(points.length - 2, Math.floor(points.length * 0.72)));
    const tip = points[tipIndex];
    const prev = points[tipIndex - 2];
    const dx = tip[1] - prev[1];
    const dy = tip[0] - prev[0];
    const length = Math.sqrt(dx * dx + dy * dy) || 1;
    const ux = dx / length;
    const uy = dy / length;
    const size = clamp(length * 1.8, 1.1, 2.4);
    const backLat = tip[0] - uy * size;
    const backLon = tip[1] - ux * size;
    const perpLat = -ux * size * 0.55;
    const perpLon = uy * size * 0.55;
    return [
      [backLat + perpLat, backLon + perpLon],
      tip,
      [backLat - perpLat, backLon - perpLon]
    ];
  }

  function plotConfig() {
    return { displayModeBar: false, responsive: true };
  }

  function baseLayout(extra = {}) {
    return {
      autosize: true,
      margin: { l: 44, r: 18, t: 12, b: 36 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'Inter, Segoe UI, Arial, sans-serif', size: 11, color: '#17233a' },
      hoverlabel: { bgcolor: '#ffffff', bordercolor: '#cfd6e1', font: { color: '#17233a' } },
      legend: { orientation: 'h', x: 0, y: -0.2, xanchor: 'left', yanchor: 'top', font: { size: 10 } },
      ...extra
    };
  }

  function compactStudentComponentLabel(key) {
    const labels = {
      A_YOUTH_OPPORTUNITY: { ru: 'Молодёжная<br>возможность', en: 'Youth<br>opportunity' },
      A_OUTBOUND_MOBILITY_UIS: { ru: 'UIS<br>мобильность', en: 'UIS<br>mobility' },
      A_LEGAL_PARTNERSHIP_CONTEXT: { ru: 'Право и<br>партнёры', en: 'Legal and<br>partners' },
      A_PROGRAM_RELEVANCE: { ru: 'Программная<br>релевантность', en: 'Program<br>relevance' },
      A_AFFORDABILITY_ACCESS: { ru: 'Доступность', en: 'Affordability' },
      A_DIGITAL_REACH: { ru: 'Цифровой<br>охват', en: 'Digital<br>reach' },
      A_DATAQ: { ru: 'Надёжность<br>данных', en: 'Data<br>reliability' }
    };
    return labels[key]?.[state.lang] || labels[key]?.en || studentComponentLabels()[key] || key;
  }

  function canPlot(selector) {
    return Boolean(window.Plotly && $(selector));
  }

  function visualEmpty(selector, message) {
    const node = $(selector);
    if (!node) return;
    if (window.Plotly?.purge) window.Plotly.purge(node);
    node.innerHTML = `<div class="visual-empty">${escapeHtml(message || t('noData'))}</div>`;
  }

  function componentTraceText(row, key) {
    const trace = row?.componentTrace?.[key] || {};
    const raw = clean(trace.raw_value);
    const normalized = clean(trace.normalized_value);
    return [
      `${t('source')}: ${trace.source_key || ''}`,
      `${t('year')}: ${trace.year ?? ''}`,
      `${t('rawValue')}: ${raw === null ? studentMethodValue(trace.raw_value, 3) : fmtScore(raw * 100)}`,
      `${t('normalizedValue')}: ${normalized === null ? t('noData') : fmtScore(normalized * 100)}`,
      `${t('weight')}: ${fmtPct(trace.weight ?? SAI_V3_WEIGHTS[key])}`,
      `${t('normalizationMethod')}: ${trace.normalization_method || ''}`
    ].join('<br>');
  }

  function studentMethodText(ru, en) {
    return state.lang === 'ru' ? ru : en;
  }

  function studentFactorKeys() {
    return Object.keys(SAI_V3_WEIGHTS);
  }

  function studentFactorIndex(key) {
    return Math.max(0, studentFactorKeys().indexOf(key));
  }

  function studentFactorSymbol(key) {
    return `I${studentFactorIndex(key) + 1}`;
  }

  function studentFactorStyleAttr(key) {
    return `--factor-color:var(--factor-${studentFactorIndex(key)});`;
  }

  function studentTrace(row, key) {
    return row?.componentTrace?.[key] || {};
  }

  function studentTraceRawEntries(trace, key) {
    const raw = trace?.raw_value;
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      return Object.entries(raw).map(([entryKey, value]) => ({ key: entryKey, value }));
    }
    return [{ key, value: raw }];
  }

  function studentMethodValue(value, digits = 3) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return Object.entries(value).map(([key, item]) => `${key}: ${studentMethodValue(item, digits)}`).join('; ');
    }
    if (typeof value === 'boolean') return value ? t('yes') : t('no');
    const number = clean(value);
    if (number === null) return value === undefined || value === null || value === '' ? t('noData') : String(value);
    return fmt(number, digits);
  }

  function studentEvidenceFieldValue(label, value) {
    if (value === undefined || value === null || value === '') return '';
    if (label === 'year') return String(value);
    if (label === 'weight') {
      const number = clean(value);
      return number === null ? String(value) : fmt(number, 4);
    }
    if (['component_key', 'input_key', 'source_key', 'normalization_method', 'observation_status', 'score_type'].includes(label)) {
      return String(value);
    }
    return studentMethodValue(value, 4);
  }

  function ensureStudentMethodSelection(row) {
    const keys = studentFactorKeys();
    if (!keys.includes(state.activeStudentFactorKey)) state.activeStudentFactorKey = keys[0];
    const trace = studentTrace(row, state.activeStudentFactorKey);
    const entries = studentTraceRawEntries(trace, state.activeStudentFactorKey);
    if (!entries.some((entry) => entry.key === state.activeStudentMethodInputKey)) {
      state.activeStudentMethodInputKey = entries[0]?.key || state.activeStudentFactorKey;
    }
  }

  function renderStudentIndexEquation(row) {
    const labels = studentComponentLabels();
    const terms = studentFactorKeys().map((key, index) => {
      const active = key === state.activeStudentFactorKey;
      return `
        <button class="math-factor-token ${active ? 'active' : ''}" type="button" data-student-factor="${escapeHtml(key)}" style="${studentFactorStyleAttr(key)}" title="${escapeHtml(labels[key] || key)}">
          <span class="math-token-label">${escapeHtml(labels[key] || key)}</span>
          <span class="math-token-body">
            <span>w<sub>${index + 1}</sub></span>
            <span class="math-weight-value">${escapeHtml(fmtPct(SAI_V3_WEIGHTS[key], 0))}</span>
            <span>× ${escapeHtml(studentFactorSymbol(key))}</span>
          </span>
        </button>`;
    }).join('<span class="math-plus">+</span>');
    return `
      <div class="math-equation index-equation student-sai-equation" aria-label="SAI_MGIMO_V3">
        <span class="math-result">SAI</span>
        <span class="math-eq">=</span>
        <span class="math-scale">100</span>
        <span class="math-op">×</span>
        <span class="math-sigma">Σ</span>
        <span class="math-token-row">${terms}</span>
      </div>
      ${row ? renderStudentCountryEquation(row) : ''}`;
  }

  function renderStudentCountryEquation(row) {
    const labels = studentComponentLabels();
    const terms = studentFactorKeys().map((key) => {
      const value = clean(row.components?.[key]) ?? clean(studentTrace(row, key).normalized_value) ?? 0;
      const weight = SAI_V3_WEIGHTS[key] ?? 0;
      const contribution = value * weight * 100;
      return `
        <button class="index-term ${key === state.activeStudentFactorKey ? 'active' : ''}" type="button" data-student-factor="${escapeHtml(key)}" style="${studentFactorStyleAttr(key)}" title="${escapeHtml(labels[key] || key)}">
          <em class="index-term-label">${escapeHtml(labels[key] || key)}</em>
          <span>${escapeHtml(studentFactorSymbol(key))}</span>
          <strong>${escapeHtml(`${fmt(weight, 2)} × ${fmt(value, 3)} = ${fmtScore(contribution)}`)}</strong>
          <small>${escapeHtml(fmtScore(value * 100))}</small>
        </button>`;
    }).join('');
    return `
      <article class="country-equation-row student-country-equation-row" style="--country-color:${escapeHtml(studentStatusColor(row))}">
        <div class="country-equation-head">
          <span>${flagHtml(row.iso2)} ${escapeHtml(countryName(row.country))}</span>
          <strong>${escapeHtml(fmtScore(row.sai))}</strong>
        </div>
        <div class="country-equation-terms">${terms}</div>
      </article>`;
  }

  function renderStudentMethodologyText() {
    const node = $('#studentMethodologyText');
    if (!node) return;
    const row = selectedRow();
    ensureStudentMethodSelection(row);
    node.innerHTML = `
      <section class="index-formula-workbench student-index-formula-workbench">
        <div class="workbench-formula-head">
          <div>
            <span>${escapeHtml(studentMethodText('Методика привлечения студентов', 'Student attraction method'))}</span>
            <h3>SAI_MGIMO_V3</h3>
          </div>
          <strong>${escapeHtml(studentMethodText('линейная сумма открытых индикаторов', 'linear open-indicator sum'))}</strong>
        </div>
        ${renderStudentIndexEquation(row)}
      </section>`;
  }

  function renderStudentFactorTabs() {
    const row = selectedRow();
    const node = $('#studentFactorTabs');
    if (!node || !row) return;
    ensureStudentMethodSelection(row);
    const labels = studentComponentLabels();
    node.innerHTML = studentFactorKeys().map((key) => {
      const value = clean(row.components?.[key]) ?? clean(studentTrace(row, key).normalized_value) ?? 0;
      const active = key === state.activeStudentFactorKey;
      return `
        <button class="factor-tab ${active ? 'active' : ''}" type="button" role="tab" aria-selected="${active}" aria-label="${escapeHtml(labels[key] || key)}" title="${escapeHtml(labels[key] || key)}" data-student-factor="${escapeHtml(key)}" style="${studentFactorStyleAttr(key)}">
          <span><i class="factor-swatch factor-${studentFactorIndex(key)}"></i>${escapeHtml(studentFactorSymbol(key))}</span>
          <small>${escapeHtml(fmtPct(SAI_V3_WEIGHTS[key], 0))} · ${escapeHtml(fmtScore(value * 100))}</small>
        </button>`;
    }).join('');
    node.querySelectorAll('[data-student-factor]').forEach((button) => button.addEventListener('click', () => {
      state.activeStudentFactorKey = button.dataset.studentFactor;
      ensureStudentMethodSelection(selectedRow());
      renderStudentMethodology();
    }));
  }

  function renderStudentComponentEquation(row, key) {
    const trace = studentTrace(row, key);
    const entries = studentTraceRawEntries(trace, key);
    const method = trace.normalization_method || '';
    const terms = entries.map((entry, index) => `
      <button class="method-equation-token ${entry.key === state.activeStudentMethodInputKey ? 'active' : ''}" type="button" data-student-factor="${escapeHtml(key)}" data-student-input="${escapeHtml(entry.key)}" style="${studentFactorStyleAttr(key)}" title="${escapeHtml(entry.key)}">
        <span class="math-token-label">${escapeHtml(entry.key)}</span>
        <span class="math-token-body">
          ${index ? '<span class="math-sign">+</span>' : ''}
          <span class="math-term">${escapeHtml(studentMethodValue(entry.value, 2))}</span>
        </span>
      </button>`).join('');
    return `
      <div class="math-equation index-equation component-equation student-component-equation" aria-label="${escapeHtml(key)}">
        <span class="math-result" style="${studentFactorStyleAttr(key)}">${escapeHtml(studentFactorSymbol(key))}</span>
        <span class="math-eq">=</span>
        <span class="component-equation-terms">${terms}</span>
      </div>
      <p class="student-normalization-formula" style="${studentFactorStyleAttr(key)}">${escapeHtml(method)}</p>`;
  }

  function renderStudentMethodInputStrip(row, key) {
    const trace = studentTrace(row, key);
    const entries = studentTraceRawEntries(trace, key);
    return `
      <div class="method-input-strip">
        ${entries.map((entry) => `
          <button class="method-input-line ${entry.key === state.activeStudentMethodInputKey ? 'active' : ''}" type="button" data-student-factor="${escapeHtml(key)}" data-student-input="${escapeHtml(entry.key)}" style="${studentFactorStyleAttr(key)}">
            <code>${escapeHtml(entry.key)}</code>
            <span>${escapeHtml(trace.source_key || t('noData'))}</span>
            <strong>${escapeHtml(studentMethodValue(entry.value, 2))}</strong>
          </button>`).join('')}
      </div>`;
  }

  function renderStudentActiveFactorChart() {
    const row = selectedRow();
    const node = $('#studentActiveFactorChart');
    if (!node || !row) return;
    ensureStudentMethodSelection(row);
    const key = state.activeStudentFactorKey;
    const labels = studentComponentLabels();
    const trace = studentTrace(row, key);
    const value = clean(row.components?.[key]) ?? clean(trace.normalized_value) ?? 0;
    const weight = trace.weight ?? SAI_V3_WEIGHTS[key];
    const contribution = value * (clean(weight) ?? 0) * 100;
    node.innerHTML = `
      <section class="component-workbench student-component-workbench" style="${studentFactorStyleAttr(key)}">
        <div class="component-workbench-head">
          <div>
            <span>${escapeHtml(studentMethodText('Активный компонент', 'Active component'))}</span>
            <h3>${escapeHtml(studentFactorSymbol(key))} · ${escapeHtml(labels[key] || key)}</h3>
            ${renderStudentComponentEquation(row, key)}
          </div>
          <dl>
            <div><dt>${escapeHtml(t('weight'))}</dt><dd>${escapeHtml(fmtPct(weight, 0))}</dd></div>
            <div><dt>${escapeHtml(t('score'))}</dt><dd>${escapeHtml(fmtScore(value * 100))}</dd></div>
          </dl>
        </div>
        <div class="component-country-list">
          <article class="component-country-row" style="${studentFactorStyleAttr(key)}">
            <span>${flagHtml(row.iso2)} ${escapeHtml(countryName(row.country))}</span>
            <strong>${escapeHtml(fmtScore(value * 100))}</strong>
            <em>${escapeHtml(studentMethodText('вклад', 'contribution'))}: ${escapeHtml(fmtScore(contribution))}</em>
            <i><b style="width:${clamp(value * 100, 0, 100)}%"></b></i>
            <small>${escapeHtml(`${trace.source_key || t('noData')} | ${t('year')}: ${trace.year || t('noData')} | ${t('observationStatus')}: ${trace.observation_status || t('noData')}`)}</small>
          </article>
        </div>
        ${renderStudentMethodInputStrip(row, key)}
      </section>`;
    bindStudentMethodButtons(node);
  }

  function renderStudentFactorDetailPanel() {
    const row = selectedRow();
    const panel = $('#studentFactorDetailPanel');
    if (!panel || !row) return;
    ensureStudentMethodSelection(row);
    const key = state.activeStudentFactorKey;
    const trace = studentTrace(row, key);
    const entries = studentTraceRawEntries(trace, key);
    const activeEntry = entries.find((entry) => entry.key === state.activeStudentMethodInputKey) || entries[0];
    const normalized = clean(trace.normalized_value);
    const sourceFields = [
      ['component_key', key],
      ['input_key', activeEntry?.key || key],
      ['source_key', trace.source_key || ''],
      ['year', trace.year ?? ''],
      ['raw_value', activeEntry ? studentMethodValue(activeEntry.value, 3) : studentMethodValue(trace.raw_value, 3)],
      ['normalized_value', normalized === null ? '' : studentMethodValue(normalized, 4)],
      ['normalization_method', trace.normalization_method || ''],
      ['weight', trace.weight ?? SAI_V3_WEIGHTS[key]],
      ['observation_status', trace.observation_status || ''],
      ['score_type', trace.score_type || '']
    ];
    const passportRows = studentFactorKeys().map((itemKey) => {
      const itemTrace = studentTrace(row, itemKey);
      return `
        <tr>
          <td><code>${escapeHtml(itemKey)}</code></td>
          <td>${escapeHtml(studentComponentLabels()[itemKey] || itemKey)}</td>
          <td>${escapeHtml(itemTrace.source_key || '')}</td>
          <td>${escapeHtml(itemTrace.year ?? '')}</td>
          <td>${escapeHtml(studentMethodValue(itemTrace.raw_value, 3))}</td>
          <td>${escapeHtml(studentMethodValue(itemTrace.normalized_value, 4))}</td>
          <td>${escapeHtml(itemTrace.normalization_method || '')}</td>
          <td>${escapeHtml(fmtPct(itemTrace.weight ?? SAI_V3_WEIGHTS[itemKey], 0))}</td>
          <td>${escapeHtml(itemTrace.observation_status || '')}</td>
          <td>${escapeHtml(itemTrace.score_type || '')}</td>
        </tr>`;
    }).join('');
    panel.innerHTML = `
      <div class="factor-detail-summary student-factor-detail-summary" style="${studentFactorStyleAttr(key)}">
        <section class="method-source-panel">
          <div class="method-source-head">
            <span>${escapeHtml(studentMethodText('Источник выбранного элемента', 'Selected element source'))}</span>
          </div>
          <div class="source-drilldown">
            <article class="source-level formula-node">
              <strong>${escapeHtml(studentMethodText('1. Элемент формулы', '1. Formula element'))}</strong>
              <p><code>${escapeHtml(activeEntry?.key || key)}</code> · ${escapeHtml(studentComponentLabels()[key] || key)}</p>
            </article>
            <article class="source-level calculation-node">
              <strong>${escapeHtml(studentMethodText('2. Расчет для страны', '2. Selected-country calculation'))}</strong>
              <div class="method-country-calc-grid">
                <article class="method-country-calc" style="--country-color:${escapeHtml(studentStatusColor(row))};${studentFactorStyleAttr(key)}">
                  <span>${flagHtml(row.iso2)} ${escapeHtml(countryName(row.country))}</span>
                  <strong>${escapeHtml(fmtScore((normalized ?? 0) * 100))}</strong>
                  <small>${escapeHtml(fmtPct(trace.weight ?? SAI_V3_WEIGHTS[key], 0))} × ${escapeHtml(normalized === null ? t('noData') : fmt(normalized, 3))}</small>
                </article>
              </div>
            </article>
            <article class="source-level source-node">
              <strong>${escapeHtml(studentMethodText('3. Источник показателя', '3. Indicator source'))}</strong>
              <dl>${sourceFields.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(studentEvidenceFieldValue(label, value))}</dd></div>`).join('')}</dl>
            </article>
          </div>
        </section>
      </div>
      <details class="evidence-table-drawer">
        <summary>${escapeHtml(studentMethodText('Паспорт данных', 'Data passport'))}</summary>
        <table class="mini-table factor-input-table student-method-passport">
          <thead><tr><th>component_key</th><th>component_name</th><th>source_key</th><th>year</th><th>raw_value</th><th>normalized_value</th><th>normalization_method</th><th>weight</th><th>observation_status</th><th>score_type</th></tr></thead>
          <tbody>${passportRows}</tbody>
        </table>
      </details>`;
    bindStudentMethodButtons(panel);
  }

  function bindStudentMethodButtons(root) {
    root.querySelectorAll('[data-student-factor]').forEach((button) => button.addEventListener('click', () => {
      state.activeStudentFactorKey = button.dataset.studentFactor;
      if (button.dataset.studentInput) state.activeStudentMethodInputKey = button.dataset.studentInput;
      ensureStudentMethodSelection(selectedRow());
      renderStudentMethodology();
    }));
  }

  function renderStudentMethodology() {
    const row = selectedRow();
    if (!row) return;
    const scoreNode = $('#studentCountryDetailScore');
    if (scoreNode) scoreNode.textContent = `${fmtScore(row.sai)} / 100`;
    ensureStudentMethodSelection(row);
    renderStudentMethodologyText();
    renderStudentFactorTabs();
    renderStudentActiveFactorChart();
    renderStudentFactorDetailPanel();
    bindStudentMethodButtons($('#studentMethodologyText') || document);
  }

  function renderStudentSaiDecomposition() {
    const row = selectedRow();
    if (!row || !canPlot('#studentSaiDecomposition')) return;
    if (clean(row.sai) === null) {
      visualEmpty('#studentSaiDecomposition', t('students.notRankedReason'));
      return;
    }
    const labels = studentComponentLabels();
    const entries = Object.entries(SAI_V3_WEIGHTS);
    Plotly.react($('#studentSaiDecomposition'), [{
      type: 'bar',
      orientation: 'h',
      y: entries.map(([key]) => compactStudentComponentLabel(key)),
      x: entries.map(([key, weight]) => (row.components[key] ?? 0) * weight * 100),
      marker: { color: entries.map(([key]) => key === 'A_YOUTH_OPPORTUNITY' ? '#e0aa24' : '#1f5faa') },
      customdata: entries.map(([key, weight]) => [
        labels[key],
        fmtScore((row.components[key] ?? 0) * 100),
        fmtPct(weight),
        componentTraceText(row, key)
      ]),
      hovertemplate: `%{customdata[0]}<br>${t('score')}: %{customdata[1]}<br>${t('weight')}: %{customdata[2]}<br>%{customdata[3]}<extra></extra>`
    }], baseLayout({
      margin: { l: 118, r: 12, t: 6, b: 42 },
      xaxis: { range: [0, 55], automargin: true },
      yaxis: { automargin: true, tickfont: { size: 10 } }
    }), plotConfig());
  }

  function growthPct(row) {
    return clean(row?.inputs?.pop_15_24_growth_10y_pct);
  }

  function saiAxisRange(values) {
    const nums = values.map(clean).filter((value) => value !== null);
    if (!nums.length) return [20, 80];
    const min = Math.min(...nums);
    const max = Math.max(...nums);
    if (min >= 20 && max <= 80) return [20, 80];
    const span = Math.max(max - min, 1);
    let low = Math.max(0, Math.floor(min - Math.max(8, span * 0.15)));
    let high = Math.min(100, Math.ceil(max + Math.max(8, span * 0.15)));
    if (high - low < 20) {
      const mid = (low + high) / 2;
      low = Math.max(0, Math.floor(mid - 10));
      high = Math.min(100, Math.ceil(mid + 10));
      if (high - low < 20) {
        if (low === 0) high = 20;
        else low = high - 20;
      }
    }
    return [low, high];
  }

  function renderYouthGrowthScatter() {
    if (!canPlot('#studentYouthGrowthScatter')) return;
    const rows = filteredBaseRows();
    const data = rows.map((row) => ({
      row,
      x: growthPct(row),
      y: row.sai,
      size: clean(row.inputs?.pop_15_24_latest) ?? clean(row.country?.demography?.youth15_24Current) ?? 1
    })).filter((item) => clean(item.x) !== null && clean(item.y) !== null);
    if (!data.length) {
      visualEmpty('#studentYouthGrowthScatter', t('noData'));
      return;
    }
    const maxSize = Math.max(...data.map((item) => item.size), 1);
    Plotly.react($('#studentYouthGrowthScatter'), [{
      type: 'scatter',
      mode: 'markers',
      x: data.map((item) => item.x),
      y: data.map((item) => item.y),
      text: data.map((item) => countryName(item.row.country)),
      customdata: data.map((item) => [item.row.iso3, fmtInt(item.size), item.row.region]),
      marker: {
        size: data.map((item) => 8 + Math.sqrt(item.size / maxSize) * 26),
        color: data.map((item) => item.row.iso3 === state.selectedIso3 ? '#e0aa24' : '#1f5faa'),
        opacity: 0.72,
        line: { color: '#ffffff', width: 1 }
      },
      hovertemplate: `%{text}<br>${t('students.saiShort')}: %{y:.1f}<br>${t('students.youthGrowth10y')}: %{x:.1f}%<br>${t('students.youthLatest')}: %{customdata[1]}<br>${t('region')}: %{customdata[2]}<br>${t('source')}: demographySeries / student_attraction_v3.csv<extra></extra>`
    }], baseLayout({
      margin: { l: 48, r: 12, t: 6, b: 58 },
      xaxis: { title: t('students.youthGrowth10y'), zeroline: true, automargin: true },
      yaxis: { title: t('students.saiShort'), range: saiAxisRange(data.map((item) => item.y)), automargin: true }
    }), plotConfig());
    $('#studentYouthGrowthScatter').on('plotly_click', (event) => {
      const iso = event?.points?.[0]?.customdata?.[0];
      if (iso) selectCountry(iso);
    });
  }

  function renderStudentMobilityChart() {
    const row = selectedRow();
    if (!row || !canPlot('#studentMobilityChart')) return;
    if (clean(row.sai) === null) {
      visualEmpty('#studentMobilityChart', t('students.notRankedReason'));
      return;
    }
    const keys = ['A_OUTBOUND_MOBILITY_UIS', 'A_DIGITAL_REACH', 'A_AFFORDABILITY_ACCESS', 'A_LEGAL_PARTNERSHIP_CONTEXT'];
    const labels = studentComponentLabels();
    Plotly.react($('#studentMobilityChart'), [{
      type: 'bar',
      x: keys.map((key) => compactStudentComponentLabel(key)),
      y: keys.map((key) => (row.components[key] ?? 0) * 100),
      marker: { color: ['#1f5faa', '#75a7d8', '#e0aa24', '#2c7a3f'] },
      customdata: keys.map((key) => [labels[key], componentTraceText(row, key)]),
      hovertemplate: `%{customdata[0]}<br>${t('normalizedValue')}: %{y:.1f}<br>%{customdata[1]}<extra></extra>`
    }], baseLayout({
      margin: { l: 46, r: 12, t: 6, b: 70 },
      yaxis: { range: [0, 100], automargin: true },
      xaxis: { tickangle: 0, automargin: true, tickfont: { size: 10 } }
    }), plotConfig());
  }

  function renderStudentRegionTreemap() {
    if (!canPlot('#studentRegionTreemap')) return;
    const rows = filteredBaseRows().filter((row) => clean(row.sai) !== null);
    const byRegion = new Map();
    rows.forEach((row) => {
      const key = row.region || t('noData');
      if (!byRegion.has(key)) byRegion.set(key, []);
      byRegion.get(key).push(row);
    });
    const labels = [];
    const parents = [];
    const values = [];
    const custom = [];
    const colors = [];
    const activeRegion = selectedVisualRegion();
    byRegion.forEach((items, region) => {
      labels.push(i18nMap('region', region));
      parents.push('');
      values.push(items.reduce((sum, row) => sum + row.sai, 0));
      const top = [...items].sort((a, b) => b.sai - a.sai)[0];
      custom.push([region, top?.iso3 || '', `${countryName(top?.country)} ${fmtScore(top?.sai)}`, items.length]);
      colors.push(region === activeRegion ? '#e0aa24' : '#1f5faa');
    });
    const node = $('#studentRegionTreemap');
    Plotly.react(node, [{
      type: 'treemap',
      labels,
      parents,
      values,
      customdata: custom,
      marker: {
        colors,
        line: {
          color: custom.map((row) => row[0] === activeRegion ? '#dfaa00' : '#ffffff'),
          width: custom.map((row) => row[0] === activeRegion ? 3 : 1)
        }
      },
      hovertemplate: `%{label}<br>${t('students.regionSaiSum')}: %{value:.1f}<br>${t('students.topSai')}: %{customdata[2]}<br>${t('students.totalCountries')}: %{customdata[3]}<extra></extra>`
    }], baseLayout({ margin: { l: 4, r: 4, t: 4, b: 4 } }), plotConfig());
    node.removeAllListeners?.('plotly_treemapclick');
    node.on('plotly_treemapclick', (event) => {
      const region = event?.points?.[0]?.customdata?.[0];
      if (!region) return false;
      state.visualRegion = region;
      renderStudentRegionTreemap();
      renderStudentCountriesPanel();
      return false;
    });
  }

  function renderStudentCountriesPanel() {
    if (!canPlot('#studentTopAfricaPanel')) return;
    const regionRows = rowsForVisualRegion();
    const rows = regionRows.rows
      .filter((row) => clean(row.sai) !== null)
      .sort((a, b) => b.sai - a.sai)
      .slice(0, 10)
      .reverse();
    if (!rows.length) {
      visualEmpty('#studentTopAfricaPanel', t('noData'));
      return;
    }
    Plotly.react($('#studentTopAfricaPanel'), [{
      type: 'bar',
      orientation: 'h',
      y: rows.map((row) => countryName(row.country)),
      x: rows.map((row) => row.sai),
      customdata: rows.map((row) => [row.iso3, row.status, row.components.A_YOUTH_OPPORTUNITY]),
      marker: { color: rows.map((row) => row.iso3 === state.selectedIso3 ? '#e0aa24' : '#1f5faa') },
      hovertemplate: `%{y}<br>${t('students.saiShort')}: %{x:.1f}<br>${t('status')}: %{customdata[1]}<br>${t('students.componentYouthOpportunity')}: %{customdata[2]:.2f}<br>${t('source')}: student_attraction_v3.csv<extra></extra>`
    }], baseLayout({
      title: {
        text: regionRows.region ? `${t('students.topCountriesTitle')}: ${i18nMap('region', regionRows.region)}` : t('students.topCountriesTitle'),
        x: 0,
        xanchor: 'left',
        font: { size: 11, color: '#17233a' }
      },
      margin: { l: 128, r: 12, t: 28, b: 42 },
      xaxis: { range: [0, 100], automargin: true },
      yaxis: { automargin: true, tickfont: { size: 10 } }
    }), plotConfig());
    $('#studentTopAfricaPanel').removeAllListeners?.('plotly_click');
    $('#studentTopAfricaPanel').on('plotly_click', (event) => {
      const iso = event?.points?.[0]?.customdata?.[0];
      if (iso) selectCountry(iso);
    });
  }

  function renderStudentTopAfricaPanel() {
    renderStudentCountriesPanel();
  }

  function studentDemographySourceLabel(series) {
    const source = `${series?.source || ''} ${series?.forecastSource || ''}`.toLowerCase();
    if (/un wpp|world population prospects/.test(source)) return 'UN WPP 2024';
    return t('noData');
  }

  function studentDemographyStatusLabel(status) {
    if (status === 'official_estimate') return t('wppEstimate');
    if (status === 'official_projection') return t('wppProjection');
    return status || t('noData');
  }

  function renderStudentPopulationYouthChart() {
    if (!canPlot('#studentPopulationYouthChart')) return;
    const row = selectedRow();
    const country = row?.country;
    const series = state.payload?.demographySeries?.[row?.iso3];
    if (!country || !series || (!series.actual?.length && !series.forecast?.length)) {
      visualEmpty('#studentPopulationYouthChart', t('noData'));
      return;
    }
    const youthLabel = '15-24';
    const currentYear = state.payload?.metadata?.baseYear || 2026;
    const traceData = (rows, key) => rows.map((item) => clean(item[key]));
    const custom = (rows) => rows.map((item) => [studentDemographySourceLabel(series), studentDemographyStatusLabel(item.observation_status)]);
    const traces = [];
    const totalName = `${countryName(country)}: ${t('populationTotalShort')}`;
    const youthName = `${countryName(country)}: ${youthLabel}`;
    if (series.actual?.length) {
      traces.push({
        type: 'scatter',
        mode: 'lines',
        name: totalName,
        legendgroup: totalName,
        x: series.actual.map((item) => item.year),
        y: traceData(series.actual, 'population_total'),
        line: { color: '#1f5faa', width: 2.4 },
        fill: 'tozeroy',
        fillcolor: 'rgba(31,95,170,.08)',
        customdata: custom(series.actual),
        hovertemplate: `${totalName}<br>${t('year')}: %{x}<br>${t('value')}: %{y:,.0f}<br>${t('source')}: %{customdata[0]}<br>${t('status')}: %{customdata[1]}<extra></extra>`
      });
      traces.push({
        type: 'bar',
        name: youthName,
        legendgroup: youthName,
        x: series.actual.map((item) => item.year),
        y: traceData(series.actual, 'pop_15_24'),
        marker: { color: '#1f5faa' },
        opacity: 0.58,
        customdata: custom(series.actual),
        hovertemplate: `${youthName}<br>${t('year')}: %{x}<br>${t('value')}: %{y:,.0f}<br>${t('source')}: %{customdata[0]}<br>${t('status')}: %{customdata[1]}<extra></extra>`
      });
    }
    if (series.forecast?.length) {
      traces.push({
        type: 'scatter',
        mode: 'lines',
        name: totalName,
        legendgroup: totalName,
        showlegend: !series.actual?.length,
        x: series.forecast.map((item) => item.year),
        y: traceData(series.forecast, 'population_total'),
        line: { color: '#1f5faa', width: 2.2, dash: 'dot' },
        opacity: 0.72,
        customdata: custom(series.forecast),
        hovertemplate: `${totalName}<br>${t('year')}: %{x}<br>${t('value')}: %{y:,.0f}<br>${t('source')}: %{customdata[0]}<br>${t('status')}: %{customdata[1]}<extra></extra>`
      });
      traces.push({
        type: 'bar',
        name: youthName,
        legendgroup: youthName,
        showlegend: !series.actual?.length,
        x: series.forecast.map((item) => item.year),
        y: traceData(series.forecast, 'pop_15_24'),
        marker: { color: '#1f5faa' },
        opacity: 0.24,
        customdata: custom(series.forecast),
        hovertemplate: `${youthName}<br>${t('year')}: %{x}<br>${t('value')}: %{y:,.0f}<br>${t('source')}: %{customdata[0]}<br>${t('status')}: %{customdata[1]}<extra></extra>`
      });
    }
    Plotly.react($('#studentPopulationYouthChart'), traces, baseLayout({
      barmode: 'overlay',
      margin: { l: 62, r: 12, t: 6, b: 54 },
      yaxis: { separatethousands: true, automargin: true },
      xaxis: { tickmode: 'array', tickvals: [2000, 2026, 2035, 2050], automargin: true },
      shapes: [{
        type: 'line',
        x0: currentYear,
        x1: currentYear,
        y0: 0,
        y1: 1,
        xref: 'x',
        yref: 'paper',
        line: { color: '#17233a', width: 1, dash: 'dash' }
      }],
      legend: { orientation: 'h', x: 0.02, y: -0.24, font: { size: 9 } }
    }), plotConfig());
  }

  function studentAgeSexPyramidRecord() {
    const row = selectedRow();
    const country = row?.country;
    const pyramid = state.payload?.ageSexPyramid?.[row?.iso3];
    if (!country || !pyramid?.ageBands?.length) return null;
    const year = 2026;
    const idx = (pyramid.forecastYears || []).indexOf(year);
    if (idx < 0) return null;
    const male = pyramid.forecastMale?.[idx];
    const female = pyramid.forecastFemale?.[idx];
    if (!male?.length || !female?.length) return null;
    const toMillions = (value) => {
      const number = clean(value);
      return number === null ? 0 : number / 1_000_000;
    };
    const maleMillions = male.map((value) => -toMillions(value));
    const femaleMillions = female.map((value) => toMillions(value));
    const maxAbs = Math.max(0.01, ...maleMillions.map((value) => Math.abs(value)), ...femaleMillions.map((value) => Math.abs(value)));
    const targetStep = maxAbs / 2;
    const exponent = Math.floor(Math.log10(targetStep || 1));
    const magnitude = 10 ** exponent;
    const fraction = targetStep / magnitude;
    const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
    const halfStep = niceFraction * magnitude;
    const axisMax = halfStep * 2;
    const tickVals = [-axisMax, -halfStep, 0, halfStep, axisMax].map((value) => Number(value.toFixed(3)));
    const tickDigits = halfStep < 0.1 ? 2 : halfStep < 1 ? 1 : 0;
    const tickText = tickVals.map((value) => Math.abs(value).toLocaleString(state.lang === 'ru' ? 'ru-RU' : 'en-US', { maximumFractionDigits: tickDigits }));
    return { country, pyramid, year, male, female, maleMillions, femaleMillions, bands: pyramid.ageBands, toMillions, axisMax, tickVals, tickText };
  }

  function renderStudentAgeSexPyramidChart() {
    if (!canPlot('#studentAgeSexPyramidChart')) return;
    const record = studentAgeSexPyramidRecord();
    if (!record) {
      visualEmpty('#studentAgeSexPyramidChart', t('noData'));
      return;
    }
    const youthBands = new Set(['15-19', '20-24']);
    const unitLabel = state.lang === 'ru' ? 'млн человек' : 'million people';
    const statusLabel = studentDemographyStatusLabel(record.pyramid.yearStatuses?.[String(record.year)] || 'official_projection');
    Plotly.react($('#studentAgeSexPyramidChart'), [
      {
        type: 'bar',
        orientation: 'h',
        name: t('maleLabel'),
        y: record.bands,
        x: record.maleMillions,
        marker: { color: record.bands.map((band) => youthBands.has(band) ? '#0b3f86' : '#8fb3d9') },
        hovertemplate: `${countryName(record.country)}<br>${t('maleLabel')}<br>%{y}: %{customdata[0]:,.0f}<br>${unitLabel}: %{customdata[2]:.2f}<br>${t('year')}: ${record.year}<br>${t('source')}: ${studentDemographySourceLabel(record.pyramid)}<br>${t('status')}: %{customdata[1]}<extra></extra>`,
        customdata: record.male.map((value) => [value, statusLabel, record.toMillions(value)])
      },
      {
        type: 'bar',
        orientation: 'h',
        name: t('femaleLabel'),
        y: record.bands,
        x: record.femaleMillions,
        marker: { color: record.bands.map((band) => youthBands.has(band) ? '#e0aa24' : '#e8cc70') },
        hovertemplate: `${countryName(record.country)}<br>${t('femaleLabel')}<br>%{y}: %{customdata[0]:,.0f}<br>${unitLabel}: %{customdata[2]:.2f}<br>${t('year')}: ${record.year}<br>${t('source')}: ${studentDemographySourceLabel(record.pyramid)}<br>${t('status')}: %{customdata[1]}<extra></extra>`,
        customdata: record.female.map((value) => [value, statusLabel, record.toMillions(value)])
      }
    ], baseLayout({
      barmode: 'relative',
      margin: { l: 54, r: 12, t: 2, b: 76 },
      xaxis: {
        range: [-record.axisMax, record.axisMax],
        tickmode: 'array',
        tickvals: record.tickVals,
        ticktext: record.tickText,
        title: unitLabel,
        zeroline: true,
        automargin: true
      },
      yaxis: { automargin: true, tickfont: { size: 10 } },
      legend: { orientation: 'h', x: 0.5, xanchor: 'center', y: -0.28, yanchor: 'top', font: { size: 10 } }
    }), plotConfig());
  }

  function renderStudentDemographyCharts() {
    const row = selectedRow();
    const note = $('#studentDemographyTraceNote');
    if (note && row) note.textContent = `${countryName(row.country)} / UN WPP 2024`;
    renderStudentPopulationYouthChart();
    renderStudentAgeSexPyramidChart();
  }

  function renderStudentVisuals() {
    const row = selectedRow();
    if (!row) return;
    const note = $('#studentVisualTraceNote');
    if (note) {
      note.textContent = `${countryName(row.country)} / ${t('students.dataModePayload')}`;
    }
    renderStudentSaiDecomposition();
    renderYouthGrowthScatter();
    renderStudentMobilityChart();
    renderStudentRegionTreemap();
    renderStudentTopAfricaPanel();
    renderStudentDemographyCharts();
  }

  function renderMap() {
    if (!state.map) return;
    ensureStudentHatchPattern();
    state.map.invalidateSize();
    state.countryLayer?.setStyle(studentFeatureStyle);
    state.flowLayer.clearLayers();
    state.pointLayer.clearLayers();
    L.circleMarker([MOSCOW.lat, MOSCOW.lon], {
      pane: 'studentPoints',
      radius: 6,
      color: '#04224d',
      weight: 2,
      fillColor: '#e0aa24',
      fillOpacity: 1
    }).bindTooltip(t('students.moscowTooltip')).addTo(state.pointLayer);

    const flows = visibleFlows();
    flows.forEach((flow) => {
      const points = curvePoints(flow.lat, flow.lon, flow.destinationLat ?? MOSCOW.lat, flow.destinationLon ?? MOSCOW.lon);
      if (!points.length) return;
      const isModelled = flow.evidence === 'modelled';
      const selected = state.selectedIso3 === flow.iso3;
      const width = isModelled
        ? clamp(clean(flow.strokeWidth) ?? (0.75 + (clean(flow.potentialIndex) ?? 40) / 100 * 2.0), 0.7, 3.1)
        : clamp(Math.sqrt(clean(flow.observedCount) || 1) / 3, 2.2, 7);
      const style = isModelled
        ? { color: selected ? '#d99a14' : '#0b3f86', weight: selected ? width + 0.7 : width, opacity: selected ? 0.62 : 0.26, dashArray: '6 7' }
        : { color: '#0b3f86', weight: width, opacity: 0.88 };
      const className = isModelled ? 'student-line modelled' : 'student-line observed';
      const line = L.polyline(points, { ...style, pane: 'studentFlows', className })
        .bindTooltip(flowTooltip(flow), { sticky: true, direction: 'auto', opacity: 0.96 })
        .on('click', () => selectCountry(flow.iso3));
      line.addTo(state.flowLayer);

      if (isModelled) {
        const arrow = arrowHeadPoints(points);
        if (arrow) {
          L.polyline(arrow, {
            ...style,
            pane: 'studentFlows',
            weight: style.weight + 0.35,
            opacity: selected ? 0.72 : 0.34,
            className: 'student-line modelled modelled-arrow'
          }).bindTooltip(flowTooltip(flow), { sticky: true, direction: 'auto', opacity: 0.96 })
            .on('click', () => selectCountry(flow.iso3))
            .addTo(state.flowLayer);
        }
      }

      const marker = L.circleMarker([flow.lat, flow.lon], {
        pane: 'studentPoints',
        radius: state.selectedIso3 === flow.iso3 ? 5.5 : 4,
        color: state.selectedIso3 === flow.iso3 ? '#e0aa24' : '#fff',
        weight: state.selectedIso3 === flow.iso3 ? 2.2 : 1.2,
        fillColor: isModelled ? '#e0aa24' : '#0b3f86',
        fillOpacity: isModelled ? 0.72 : 0.95
      }).bindTooltip(flowTooltip(flow), { sticky: true, direction: 'top', opacity: 0.96 })
        .on('click', () => selectCountry(flow.iso3));
      marker.addTo(state.pointLayer);
    });

    const selected = selectedFlow();
    const selectedCountryRow = selectedRow();
    const selectedLat = clean(selected?.lat) ?? clean(selectedCountryRow?.country?.latitude);
    const selectedLon = clean(selected?.lon) ?? clean(selectedCountryRow?.country?.longitude);
    if (selectedLat !== null && selectedLon !== null) {
      const selectedMarker = L.circleMarker([selectedLat, selectedLon], {
        pane: 'studentPoints',
        radius: 8,
        color: '#e0aa24',
        weight: 2.4,
        fillColor: '#04224d',
        fillOpacity: 0.9
      }).bindTooltip(
        selected ? flowTooltip(selected) : studentCountryTooltip(selectedCountryRow, selectedCountryRow?.iso3),
        { sticky: true, direction: 'top', opacity: 0.96 }
      );
      selectedMarker.addTo(state.pointLayer);
    }

    const modelledCount = flows.filter((flow) => flow.evidence === 'modelled').length;
    const observedCount = flows.filter((flow) => flow.evidence === 'observed').length;
    $('#studentMapLegend').textContent = t('students.mapLegendText', {
      count: fmtInt(modelledCount),
      observed: fmtInt(observedCount)
    });
    $('#studentMapStatus').textContent = state.showDirectionArcs
      ? t('students.directionStatus', { count: fmtInt(modelledCount) })
      : t('students.directionHidden');
  }

  function renderRanking() {
    const rows = visibleRows();
    $('#studentRankingBody').innerHTML = rows.length
      ? rows.map((row, index) => {
        return `
          <tr data-iso3="${escapeHtml(row.iso3)}" data-status="${escapeHtml(row.status)}" class="${row.iso3 === state.selectedIso3 ? 'active' : ''}" style="--student-status-color:${escapeHtml(studentStatusColor(row))}">
            <td>${index + 1}</td>
            <td>
              <button class="student-row-button" type="button">
                ${flagHtml(row.iso2)}
                <span>${escapeHtml(countryName(row.country))}</span>
              </button>
            </td>
            <td>${fmtScore(row.sai)}</td>
          </tr>
        `;
      }).join('')
      : `<tr><td colspan="3" class="empty-cell">${t('students.emptyRows')}</td></tr>`;

    $$('#studentRankingBody [data-iso3]').forEach((node) => {
      node.addEventListener('click', () => selectCountry(node.dataset.iso3));
    });
  }

  function renderSelected() {
    const row = selectedRow();
    if (!row) return;
    const flow = selectedFlow();
    $('#studentSelectedFlag').innerHTML = flagHtml(row.iso2, 'country-flag-image');
    $('#studentSelectedCountry').textContent = countryName(row.country);
    $('#studentSelectedMeta').textContent = [i18nMap('region', row.region), statusLabelFromKey(row.status)].filter(Boolean).join(' / ');
    $('#studentSelectedSai').textContent = fmtScore(row.sai);
    $('#studentSelectedProgram').textContent = programLabel(row.program);
    $('#studentSelectedLanguage').textContent = languageLabel(row.language);
    $('#studentSelectedEvidence').textContent = flow?.evidence === 'observed'
      ? t('students.evidenceObserved')
      : flow?.evidence === 'modelled'
        ? t('students.evidenceModelled')
        : t('students.noObservedShort');
    $('#studentSelectedPotential').textContent = flow?.evidence === 'observed'
      ? t('students.observedStudentsValue', { count: fmtInt(flow.observedCount) })
      : flow?.evidence === 'modelled'
        ? t('students.modelledPotentialValue', { value: fmtScore(flow.potentialIndex) })
      : fmtInt(row.inputs?.pop_15_24_latest ?? row.country?.demography?.youth15_24Current);
    $('#studentSelectedWarning').textContent = row.hardFiltered
      ? `${t('students.referenceOnlyWarning')} ${row.dueDiligenceWarnings || ''}`.trim()
      : flow?.evidence === 'observed'
        ? t('students.observedWarning')
        : t('students.modelledWarning');
    $('#studentSelectedBadges').innerHTML = [
      `<span class="badge badge-${escapeHtml(row.status)}">${escapeHtml(statusLabelFromKey(row.status))}</span>`,
      `<span class="badge">${escapeHtml(i18nMap('region', row.region))}</span>`,
      `<span class="badge">${escapeHtml(t('students.dataModePayload'))}</span>`,
      row.hardFiltered ? `<span class="badge badge-reference-only">${escapeHtml(t('students.modeReference'))}</span>` : ''
    ].join('');
  }

  function studentComponentLabels() {
    return {
      A_YOUTH_OPPORTUNITY: t('students.componentYouthOpportunity'),
      A_OUTBOUND_MOBILITY_UIS: t('students.componentOutboundMobilityUis'),
      A_LEGAL_PARTNERSHIP_CONTEXT: t('students.componentLegalPartnership'),
      A_PROGRAM_RELEVANCE: t('students.componentProgramRelevance'),
      A_AFFORDABILITY_ACCESS: t('students.componentAffordabilityAccess'),
      A_DIGITAL_REACH: t('students.componentDigitalReach'),
      A_DATAQ: t('students.componentDataQ')
    };
  }

  function renderAll() {
    applyI18n();
    populateSelects();
    updateHeader();
    renderMap();
    renderRanking();
    renderSelected();
    renderStudentMethodology();
    renderStudentVisuals();
    if (state.payload) {
      $('#loadStatus').textContent = t('statusReady');
      $('#loadStatus').classList.add('ready');
    }
  }

  function selectCountry(iso3) {
    if (!iso3 || !state.rowByIso.has(iso3)) return;
    state.selectedIso3 = iso3;
    state.visualRegion = normalizeRegion(state.rowByIso.get(iso3)?.region) || state.visualRegion;
    saveState();
    renderRanking();
    renderSelected();
    renderStudentMethodology();
    renderStudentVisuals();
    renderMap();
  }

  function resetFilters() {
    state.mode = 'practical';
    state.region = 'all';
    state.status = 'all';
    state.topN = DEFAULT_TOP_N;
    state.program = 'all';
    state.language = 'all';
    state.showDirectionArcs = true;
    state.selectedIso3 = leaderRow()?.iso3 || state.selectedIso3;
    state.visualRegion = null;
    saveState();
    renderAll();
  }

  function handleControl(id, key) {
    $(id).addEventListener('change', (event) => {
      state[key] = event.target.value;
      if (key === 'region') state.visualRegion = state.region === 'all' ? null : normalizeRegion(state.region);
      const rows = visibleRows();
      if (!rows.some((row) => row.iso3 === state.selectedIso3)) {
        state.selectedIso3 = rows[0]?.iso3 || state.rows[0]?.iso3 || state.selectedIso3;
      }
      saveState();
      renderAll();
    });
  }

  function bindEvents() {
    $('#langRu').addEventListener('click', () => {
      state.lang = 'ru';
      saveState();
      renderAll();
    });
    $('#langEn').addEventListener('click', () => {
      state.lang = 'en';
      saveState();
      renderAll();
    });
    handleControl('#studentRegionSelect', 'region');
    handleControl('#studentModeSelect', 'mode');
    handleControl('#studentStatusSelect', 'status');
    handleControl('#studentTopNSelect', 'topN');
    handleControl('#studentProgramSelect', 'program');
    handleControl('#studentLanguageSelect', 'language');
    $('#studentFlowToggle').addEventListener('change', (event) => {
      state.showDirectionArcs = event.target.checked;
      saveState();
      renderMap();
    });
    $('#studentResetBtn').addEventListener('click', resetFilters);
    $('#studentDownloadBtn').addEventListener('click', downloadCsv);
  }

  function downloadCsv() {
    const headers = ['rank', 'iso3', 'country', 'region', 'status', 'program', 'language', 'student_index', 'pop_15_24_latest', 'source_policy'];
    const lines = [headers.join(',')];
    visibleRows().forEach((row, index) => {
      const values = [
        clean(state.mode === 'reference' ? row.referenceRank : row.practicalRank) ?? '',
        row.iso3,
        countryName(row.country),
        i18nMap('region', row.region),
        statusLabelFromKey(row.status),
        programLabel(row.program),
        languageLabel(row.language),
        fmtScore(row.sai),
        fmtInt(row.inputs?.pop_15_24_latest),
        row.inputs?.score_source_policy || 'open_api_factual_only'
      ];
      lines.push(values.map((value) => `"${String(value ?? '').replaceAll('"', '""')}"`).join(','));
    });
    const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'mgimo_student_attraction_index.csv';
    link.click();
    URL.revokeObjectURL(url);
  }

  async function init() {
    try {
      await loadLocales();
      applyI18n();
      const [payload, geo, observedFlowsCsv, modelMeta] = await Promise.all([
        fetch(DATA_URL).then((response) => {
          if (!response.ok) throw new Error(`${DATA_URL}: ${response.status}`);
          return response.json();
        }),
        fetch(GEO_URL).then((response) => {
          if (!response.ok) throw new Error(`${GEO_URL}: ${response.status}`);
          return response.json();
        }).catch(() => null),
        fetchOptionalText(STUDENT_FLOWS_OBSERVED_URL),
        fetchOptionalJson(STUDENT_MODEL_META_URL)
      ]);
      state.observedFlowRows = parseCsv(observedFlowsCsv);
      state.studentModelMeta = modelMeta;
      payload.countries = (payload.countries || []).map((country) => normalizeCountry(country, payload));
      state.payload = payload;
      state.geo = geo;
      (payload.countries || []).forEach((country) => state.countryByIso.set(country.iso3, country));
      buildGeoNameIndex();
      state.rows = buildStudentRows(payload);
      state.rows.forEach((row) => state.rowByIso.set(row.iso3, row));
      state.flowRows = buildFlowRows(payload);
      if (!state.rowByIso.has(state.selectedIso3) || state.rowByIso.get(state.selectedIso3)?.hardFiltered || clean(state.rowByIso.get(state.selectedIso3)?.sai) === null) {
        state.selectedIso3 = leaderRow()?.iso3 || state.rows[0]?.iso3 || null;
      }
      populateSelects();
      initMap();
      bindEvents();
      renderAll();
      $('#loadStatus').textContent = t('statusReady');
      $('#loadStatus').classList.add('ready');
      window.MGIMO_STUDENTS_STATE = state;
    } catch (error) {
      console.error(error);
      $('#loadStatus').textContent = t('statusError');
      $('#studentMapStatus').textContent = error.message;
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
