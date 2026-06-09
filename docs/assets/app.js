(() => {
  'use strict';

  const DATA_URL = 'data/mgimo_dashboard_data.json';
  const FACTOR_TRACE_URL = 'data/factor_inputs_long.json';
  const BRANCH_DICTIONARY_URL = 'data/branch_factor_indicator_dictionary_v3.json';
  const FACTOR_LINEAGE_URL = 'data/branch_factor_source_lineage.json';
  const GEO_URL = 'data/world_admin_boundaries_ru_claimed_update_2026.geojson';
  const LOCALE_URLS = { ru: 'locales/ru.json', en: 'locales/en.json' };
  const INDEX_KEYS = ['I_MARKET', 'I_PROGRAM', 'I_RUSCOMP', 'I_ECO', 'I_FIN', 'I_FEAS', 'I_HRSTRAT'];
  const MAP_METRICS = ['priority', ...INDEX_KEYS];
  const FACTOR_INPUT_KEYS = {
    I_MARKET: 'market',
    I_PROGRAM: 'program',
    I_RUSCOMP: 'russiaCompatibility',
    I_ECO: 'economy',
    I_FIN: 'finance',
    I_FEAS: 'feasibility',
    I_HRSTRAT: 'strategicHr'
  };
  const FACTOR_INPUT_META = {
    market: { source: 'un_wpp2024_population_by_single_age_sex', observation: 'official_or_reference' },
    program: { source: 'live_merged_features', observation: 'modelled' },
    russiaCompatibility: { source: 'mgimo_presence', observation: 'official_or_reference' },
    economy: { source: 'world_bank_indicators_long', observation: 'official_or_reference' },
    finance: { source: 'live_merged_features', observation: 'modelled' },
    feasibility: { source: 'world_bank_wgi_long', observation: 'official_or_reference' },
    strategicHr: { source: 'live_merged_features', observation: 'modelled' }
  };
  const DEFAULT_SELECTED_ISO = 'CHN';
  const SCORE_EPSILON = 0.05;
  const MAP_ISO_FIELDS = ['iso_a3', 'adm0_a3', 'wb_a3', 'adm0_iso', 'sov_a3', 'gu_a3'];
  const BLUE_SCALE = ['#f4ead2', '#dfe8f3', '#c4d7ec', '#9fbee0', '#6f98cb', '#3f73b6', '#073f8f'];
  const STATUS_COLORS = {
    in_preparation: '#dfaa00',
    presence: '#041d49',
    candidate: '#397a21',
    partner_model: '#3d68d6',
    unfriendly: '#8c95a3',
    domestic: '#9aa4b3',
    special_territory: '#9aa4b3',
    excluded: '#9aa4b3',
    monitoring: '#9aa4b3'
  };

  const state = {
    lang: ['ru', 'en'].includes(localStorage.getItem('mgimo_lang')) ? localStorage.getItem('mgimo_lang') : 'ru',
    metric: localStorage.getItem('mgimo_metric') || 'priority',
    category: localStorage.getItem('mgimo_category') || 'all',
    region: localStorage.getItem('mgimo_region') || 'all',
    weightMode: 'line',
    weightEditorOpen: false,
    weights: null,
    weightsDefault: null,
    activeFactorKey: localStorage.getItem('mgimo_active_factor') || INDEX_KEYS[0],
    activeMethodInputKey: localStorage.getItem('mgimo_active_method_input') || '',
    selectedIso3: null,
    comparisonIso3s: new Set(),
    data: null,
    geo: null,
    i18n: {},
    map: null,
    countryLayer: null,
    markerLayer: null,
    layoutRefreshFrame: null,
    countryByIso: new Map(),
    geoNameByIso: new Map(),
    factorByIso: new Map(),
    factorTraceRows: [],
    factorTraceByIso: new Map(),
    branchDictionaryRows: [],
    branchDictionaryByKey: new Map(),
    factorSourceLineageRows: [],
    factorSourceLineageByKey: new Map(),
    rankByIso: new Map(),
    countryLayersByIso: new Map()
  };

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const clean = (v) => {
    if (v === null || v === undefined || v === '') return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const bool = (v) => v === true || v === 1 || v === '1' || String(v).toLowerCase() === 'true';
  const clamp = (x, min, max) => Math.max(min, Math.min(max, x));
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
    const n = clean(value);
    if (n === null) return t('noData');
    return n.toLocaleString(state.lang === 'ru' ? 'ru-RU' : 'en-US', { maximumFractionDigits: digits });
  }

  function fmtScore(value, digits = 1) {
    return fmt(value, digits);
  }

  function fmtPct(value, digits = 0) {
    const n = clean(value);
    if (n === null) return t('noData');
    return `${fmt(n * 100, digits)}%`;
  }

  function fmtMoney(value) {
    const n = clean(value);
    if (n === null) return t('noData');
    const abs = Math.abs(n);
    const sign = n < 0 ? '-' : '';
    if (abs >= 1_000_000_000) return `${sign}$${fmt(abs / 1_000_000_000, 1)}B`;
    if (abs >= 1_000_000) return `${sign}$${fmt(abs / 1_000_000, 1)}M`;
    if (abs >= 1_000) return `${sign}$${fmt(abs / 1_000, 1)}K`;
    return `${sign}$${fmt(abs, 0)}`;
  }

  function isoFlag(iso2) {
    const code = String(iso2 || '').trim().toUpperCase();
    if (!/^[A-Z]{2}$/.test(code)) return '';
    return Array.from(code).map((ch) => String.fromCodePoint(127397 + ch.charCodeAt(0))).join('');
  }

  function flagHtml(iso2, className = 'inline-flag') {
    const code = String(iso2 || '').trim().toLowerCase();
    if (!/^[a-z]{2}$/.test(code)) return `<span class="${className} flag-empty" aria-hidden="true"></span>`;
    return `<span class="${className} flag-image" aria-hidden="true"><img src="assets/vendor/flags/4x3/${code}.svg" alt="" loading="lazy" onerror="this.hidden=true;this.nextElementSibling.hidden=false;"><span class="flag-native-mark" hidden>${isoFlag(code)}</span></span>`;
  }

  function countryName(country) {
    const geo = state.geoNameByIso.get(country?.iso3) || {};
    if (state.lang === 'ru') return country?.nameRu || country?.country_ru || geo.ru || country?.name || country?.country || country?.country_en || country?.iso3 || '-';
    return country?.nameEn || country?.country_en || geo.en || country?.name || country?.country || country?.country_ru || country?.iso3 || '-';
  }

  function normalizeRegion(region) {
    return String(region || '')
      .replace('Middle East, North Africa, Afghanistan & Pakistan', 'Middle East & North Africa')
      .replace('Middle East, North Africa, Afghanistan and Pakistan', 'Middle East & North Africa');
  }

  function i18nMap(type, value) {
    if (!value) return '-';
    const normalized = type === 'region' ? normalizeRegion(value) : String(value);
    const key = `${type}.${normalized}`;
    const label = t(key);
    return label === key ? normalized.replaceAll('_', ' ') : label;
  }

  function metricLabel(metric = state.metric) {
    const label = t(`metric.${metric}`);
    return label === `metric.${metric}` ? metric : label;
  }

  function factorTitle(key) {
    const factor = (state.data?.methodology?.factors || []).find((row) => row.code === key);
    if (factor?.label) return metricLabel(key) === key ? factor.label : metricLabel(key);
    const sample = state.data?.methodology?.factor_titles?.[key];
    if (sample) return sample[state.lang] || sample.en || key;
    return metricLabel(key);
  }

  function defaultWeights() {
    const weights = state.data?.weightsDefault || state.data?.weights || {};
    const total = INDEX_KEYS.reduce((sum, key) => sum + Math.max(0, clean(weights[key]) ?? 0), 0);
    if (total <= 0) return Object.fromEntries(INDEX_KEYS.map((key) => [key, 1 / INDEX_KEYS.length]));
    return Object.fromEntries(INDEX_KEYS.map((key) => [key, Math.max(0, clean(weights[key]) ?? 0) / total]));
  }

  function normalizeWeights(weights) {
    const raw = INDEX_KEYS.map((key) => Math.max(0, clean(weights?.[key]) ?? 0));
    const total = raw.reduce((sum, value) => sum + value, 0);
    if (total <= 0) return defaultWeights();
    return Object.fromEntries(INDEX_KEYS.map((key, index) => [key, raw[index] / total]));
  }

  function activeWeights() {
    if (!state.weights) state.weights = defaultWeights();
    state.weights = normalizeWeights(state.weights);
    return state.weights;
  }

  function encodedWeights() {
    return INDEX_KEYS.map((key) => Math.round((activeWeights()[key] || 0) * 1000)).join('.');
  }

  function decodedWeights(value) {
    const parts = String(value || '').split(/[.;:_-]/).map((part) => clean(part)).filter((part) => part !== null);
    if (parts.length !== INDEX_KEYS.length) return null;
    return normalizeWeights(Object.fromEntries(INDEX_KEYS.map((key, index) => [key, parts[index] / 1000])));
  }

  function priority(country, weights = activeWeights()) {
    if (!country || !bool(country.eligible)) return 0;
    const acc = INDEX_KEYS.reduce((sum, key) => {
      const score = clamp(factorScore(country, key), 0, 1);
      return sum + (weights[key] || 0) * Math.log(SCORE_EPSILON + score);
    }, 0);
    return 100 * Math.exp(acc);
  }

  function factorScore(country, key) {
    return clean(country?.factorScores?.[key] ?? country?.[key]) ?? 0;
  }

  function countryFactorInputs(country) {
    return state.data?.factorInputs?.[country?.iso3] || {};
  }

  function eligibilityInfo(country) {
    return state.data?.eligibility?.byCountry?.[country?.iso3] || {};
  }

  function statusCode(country) {
    const flags = eligibilityInfo(country).flags || {};
    const factorFlags = countryFactorInputs(country).russiaCompatibility || {};
    const rec = country?.recommendationCategory || country?.recommendation_category;
    if (rec === 'in_preparation' || bool(country?.has_mgimo_pipeline) || bool(factorFlags.inPreparation)) return 'in_preparation';
    if (bool(flags.existingMgimoBranch) || bool(factorFlags.hasExistingMgimoBranch) || bool(country?.has_existing_mgimo_branch)) return 'presence';
    if (bool(flags.unfriendly) || bool(factorFlags.isUnfriendly) || bool(country?.is_unfriendly)) return 'unfriendly';
    if (bool(flags.domesticRussia) || bool(factorFlags.isDomesticRussia) || bool(country?.is_domestic_russia)) return 'domestic';
    if (bool(flags.nonSovereignOrSpecial) || bool(factorFlags.isNonSovereignOrSpecial) || bool(country?.is_non_sovereign_or_special)) return 'special_territory';
    if (rec === 'A_open_priority') return 'candidate';
    if (rec === 'B_strategic_with_subsidy') return 'partner_model';
    if (rec === 'D_excluded' || !bool(country?.eligible)) return 'excluded';
    return String(country?.status_code || 'monitoring');
  }

  function statusLabel(country) {
    const key = `status.${statusCode(country)}`;
    const label = t(key);
    return label === key ? (state.lang === 'ru' ? country?.status_ru : country?.status_en) || statusCode(country) : label;
  }

  function rowClass(country) {
    const code = statusCode(country);
    const neutral = code === 'in_preparation' ? ' neutral' : '';
    return `row-${code.replace(/_/g, '-')}${neutral}`;
  }

  function categoryMatches(country) {
    const code = statusCode(country);
    if (state.category === 'all') return true;
    if (state.category === 'eligible') return bool(country.eligible);
    if (state.category === 'in_preparation') return code === 'in_preparation';
    if (state.category === 'presence') return code === 'presence';
    if (state.category === 'unfriendly') return code === 'unfriendly';
    return true;
  }

  function visibleCountries() {
    const query = ($('#searchInput')?.value || '').trim().toLowerCase();
    return rankedCountries().filter((country) => {
      const regionOk = state.region === 'all' || normalizeRegion(country.region) === state.region;
      const categoryOk = categoryMatches(country);
      const searchOk = !query || [countryName(country), country.name, country.country, country.iso3, country.iso2].join(' ').toLowerCase().includes(query);
      return regionOk && categoryOk && searchOk;
    });
  }

  function rankedCountries() {
    const weights = activeWeights();
    return (state.data?.countries || [])
      .map((country) => ({ ...country, currentPriority: priority(country, weights) }))
      .sort((left, right) => right.currentPriority - left.currentPriority || countryName(left).localeCompare(countryName(right)));
  }

  function refreshRanks() {
    state.rankByIso.clear();
    let rank = 1;
    rankedCountries().forEach((country) => {
      if (bool(country.eligible)) {
        state.rankByIso.set(country.iso3, rank);
        rank += 1;
      }
    });
  }

  function selectedCountry() {
    if (!state.countryByIso.has(state.selectedIso3)) {
      state.selectedIso3 = state.countryByIso.has(DEFAULT_SELECTED_ISO) ? DEFAULT_SELECTED_ISO : rankedCountries()[0]?.iso3;
    }
    return state.countryByIso.get(state.selectedIso3);
  }

  function parseComparisonIso3s(value) {
    const list = String(value || '')
      .split(',')
      .map((iso3) => iso3.trim().toUpperCase())
      .filter((iso3) => /^[A-Z0-9]{3}$/.test(iso3) && state.countryByIso.has(iso3));
    return new Set(list);
  }

  function comparisonCountries() {
    return Array.from(state.comparisonIso3s)
      .filter((iso3) => state.countryByIso.has(iso3))
      .map((iso3) => state.countryByIso.get(iso3));
  }

  function chartCountries() {
    const focus = selectedCountry();
    const compared = comparisonCountries();
    return compared.length ? compared : [focus].filter(Boolean);
  }

  function comparisonParam() {
    return Array.from(state.comparisonIso3s)
      .filter((iso3) => state.countryByIso.has(iso3))
      .join(',');
  }

  function countryVisualColor(country) {
    return colorFor(mapMetricValue(country));
  }

  function statusVisualColor(country) {
    return STATUS_COLORS[statusCode(country)] || STATUS_COLORS.monitoring;
  }

  function chartColor(country, index = 0) {
    const colors = ['#1f5faa', '#e0aa24', '#2e8b57', '#9b5de5', '#d65f5f', '#008b8b'];
    return index === 0 ? colors[0] : colors[index % colors.length];
  }

  function tableStatusLabel(country) {
    const code = statusCode(country);
    if (['candidate', 'partner_model', 'monitoring', 'not_recommended'].includes(code)) return '';
    return statusLabel(country);
  }

  function toggleComparison(iso3) {
    const normalized = String(iso3 || '').trim().toUpperCase();
    if (!state.countryByIso.has(normalized)) return;
    if (state.comparisonIso3s.has(normalized)) {
      state.comparisonIso3s.delete(normalized);
      if (state.selectedIso3 === normalized && state.comparisonIso3s.size) {
        state.selectedIso3 = Array.from(state.comparisonIso3s)[0];
      } else if (!state.comparisonIso3s.size) {
        state.selectedIso3 = normalized;
      }
    } else {
      state.comparisonIso3s.add(normalized);
      state.selectedIso3 = normalized;
    }
    saveAndRender();
  }

  async function loadLocales() {
    const pairs = await Promise.all(Object.entries(LOCALE_URLS).map(async ([lang, url]) => {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`${url}: ${response.status}`);
      return [lang, await response.json()];
    }));
    state.i18n = Object.fromEntries(pairs);
  }

  function applyI18n() {
    document.documentElement.lang = state.lang;
    document.title = t('appTitle');
    $$('[data-i18n]').forEach((node) => {
      node.textContent = t(node.dataset.i18n);
    });
    const loadStatus = $('#loadStatus');
    if (loadStatus?.classList.contains('ready')) loadStatus.textContent = t('statusReady');
    if (loadStatus?.classList.contains('error')) loadStatus.textContent = t('statusError');
    $$('[data-i18n-aria-label]').forEach((node) => {
      node.setAttribute('aria-label', t(node.dataset.i18nAriaLabel));
    });
    $('#langRu')?.classList.toggle('active', state.lang === 'ru');
    $('#langEn')?.classList.toggle('active', state.lang === 'en');
  }

  function buildIndexes() {
    state.countryByIso.clear();
    state.factorByIso.clear();
    buildFactorTraceIndex();
    buildBranchDictionaryIndex();
    buildFactorSourceLineageIndex();
    (state.data?.countries || []).forEach((country) => state.countryByIso.set(country.iso3, country));
    (state.data?.countries || []).forEach((country) => {
      const groups = new Map();
      INDEX_KEYS.forEach((key) => groups.set(key, factorInputGroup(country, key)));
      state.factorByIso.set(country.iso3, groups);
    });
    state.weightsDefault = defaultWeights();
    state.weights = state.weights || state.weightsDefault;
  }

  function buildFactorTraceIndex() {
    state.factorTraceByIso.clear();
    (state.factorTraceRows || []).forEach((row) => {
      const iso3 = String(row.iso3 || '').toUpperCase();
      const factorKey = String(row.factor_key || '');
      if (!iso3 || !factorKey) return;
      const key = `${iso3}|${factorKey}`;
      if (!state.factorTraceByIso.has(key)) state.factorTraceByIso.set(key, []);
      state.factorTraceByIso.get(key).push(row);
    });
  }

  function buildBranchDictionaryIndex() {
    state.branchDictionaryByKey.clear();
    (state.branchDictionaryRows || []).forEach((row) => {
      const factorKey = String(row.factor_key || row.factorCode || '').trim();
      const inputKey = String(row.input_key || row.indicator_key || '').trim();
      if (!factorKey || !inputKey) return;
      state.branchDictionaryByKey.set(`${factorKey}|${inputKey}`, row);
    });
  }

  function buildFactorSourceLineageIndex() {
    state.factorSourceLineageByKey.clear();
    (state.factorSourceLineageRows || []).forEach((row) => {
      const iso3 = String(row.iso3 || '').toUpperCase();
      const factorKey = String(row.factor_key || '').trim();
      const inputKey = String(row.input_key || '').trim();
      if (!iso3 || !factorKey || !inputKey) return;
      state.factorSourceLineageByKey.set(`${iso3}|${factorKey}|${inputKey}`, row);
    });
  }

  function branchIndicatorMeta(factorKey, inputKey) {
    return state.branchDictionaryByKey.get(`${factorKey}|${inputKey}`) || {};
  }

  function localizedDictionaryName(row, defaultName) {
    if (!row) return defaultName;
    if (state.lang === 'ru') return row.official_indicator_name_ru || row.official_name_ru || row.name_ru || row.official_indicator_name_en || row.official_name_en || defaultName;
    return row.official_indicator_name_en || row.official_name_en || row.name_en || row.official_indicator_name_ru || row.official_name_ru || defaultName;
  }

  function factorLineage(country, factorKey, inputKey) {
    const key = `${String(country?.iso3 || '').toUpperCase()}|${factorKey}|${inputKey}`;
    return state.factorSourceLineageByKey.get(key) || null;
  }

  function factorInputGroup(country, factorKey) {
    const groupKey = FACTOR_INPUT_KEYS[factorKey];
    const traceRows = state.factorTraceByIso.get(`${String(country?.iso3 || '').toUpperCase()}|${factorKey}`) || [];
    if (traceRows.length) {
      const factor = (state.data?.methodology?.factors || []).find((row) => row.code === factorKey) || {};
      return {
        iso3: country.iso3,
        factor_key: factorKey,
        title_en: factor.label || factorKey,
        title_ru: factorKey,
        factor_score: factorScore(country, factorKey),
        inputs: traceRows.map((row) => ({
          key: row.input_key,
          raw_value: row.raw_value,
          normalized_value: row.normalized_value,
          unit: inferInputUnit(row.input_key, row.raw_value),
          year: row.year,
          source_key: row.source_key || '',
          observation_status: row.observation_status || 'modelled',
          normalization_method: row.normalization_method || '',
          input_weight: clean(row.input_weight),
          factor_weight: activeWeights()[factorKey],
          scoring_role: row.scoring_role || '',
          weight_note: row.weight_note || ''
        }))
      };
    }
    return {
      iso3: country.iso3,
      factor_key: factorKey,
      title_en: factorTitle(factorKey),
      title_ru: factorKey,
      factor_score: factorScore(country, factorKey),
      inputs: []
    };
  }

  function inputLabel(key) {
    const labels = {
      addressableMarketStudents2026: { ru: 'Адресуемый пул студентов, 2026', en: 'Addressable student pool, 2026' },
      addressableMarketStudents2035: { ru: 'Адресуемый пул студентов, 2035', en: 'Addressable student pool, 2035' },
      addressableMarketStudents2050: { ru: 'Адресуемый пул студентов, 2050', en: 'Addressable student pool, 2050' },
      affordabilityFactor: { ru: 'Ценовая доступность', en: 'Affordability factor' },
      amsGrowth2026_2035: { ru: 'Рост адресуемого пула 2026-2035', en: 'Addressable pool growth 2026-2035' },
      amsGrowth2026_2050: { ru: 'Рост адресуемого пула 2026-2050', en: 'Addressable pool growth 2026-2050' },
      avgTuitionUsd: { ru: 'Средняя стоимость обучения', en: 'Average tuition' },
      capexUsd: { ru: 'Первичные затраты', en: 'CAPEX' },
      captureCeiling: { ru: 'Предельный охват', en: 'Capture ceiling' },
      controlCorruption: { ru: 'Контроль коррупции', en: 'Control of corruption' },
      demandPoolStudents: { ru: 'Потенциальный пул студентов', en: 'Demand pool' },
      digitalFinanceProfileScore: { ru: 'Цифровые финансы и бизнес-информатика', en: 'Digital finance and business informatics' },
      economicLegalProfileScore: { ru: 'Экономико-правовой профиль', en: 'Economic and legal profile' },
      educationHubScore: { ru: 'Позиция образовательного центра', en: 'Education hub score' },
      educationScore: { ru: 'Образовательный контекст', en: 'Education score' },
      energyLogisticsProfileScore: { ru: 'Энергетика и логистика', en: 'Energy and logistics profile' },
      fieldFitFactor: { ru: 'Соответствие профиля', en: 'Field fit factor' },
      gdpGrowthReal: { ru: 'Реальный рост ВВП', en: 'Real GDP growth' },
      gdpPcPppCurrent: { ru: 'ВВП на душу по ППС', en: 'GDP per capita PPP' },
      gdpPppCurrent: { ru: 'ВВП по ППС', en: 'GDP PPP' },
      governmentEffectiveness: { ru: 'Эффективность государства', en: 'Government effectiveness' },
      hasExistingMgimoBranch: { ru: 'Действующее присутствие МГИМО', en: 'Existing MGIMO branch' },
      hostSubsidyShare: { ru: 'Доля субсидирования принимающей стороны', en: 'Host subsidy share' },
      inPreparation: { ru: 'Проект в подготовке', en: 'In preparation' },
      inflationCpi: { ru: 'Инфляция', en: 'Inflation' },
      internetUsersPct: { ru: 'Пользователи интернета', en: 'Internet users' },
      isDomesticRussia: { ru: 'Россия', en: 'Russia' },
      isNonSovereignOrSpecial: { ru: 'Особая территория', en: 'Special territory' },
      isUnfriendly: { ru: 'Недружественная страна', en: 'Unfriendly country' },
      logisticsPerformanceIndex: { ru: 'Индекс логистики', en: 'Logistics performance' },
      npvExpectedUsd: { ru: 'Ожидаемая приведенная стоимость', en: 'Expected NPV' },
      npvPositiveProbability: { ru: 'Вероятность положительной приведенной стоимости', en: 'Positive NPV probability' },
      partnerUniversitiesMgimoCount: { ru: 'Партнерские университеты МГИМО', en: 'MGIMO partner universities' },
      politicalStability: { ru: 'Политическая стабильность', en: 'Political stability' },
      populationTotalCurrent: { ru: 'Население', en: 'Population' },
      priceLevelIndex: { ru: 'Индекс уровня цен', en: 'Price level index' },
      'profiles.digital_finance_business_informatics': { ru: 'Цифровые финансы и бизнес-информатика', en: 'Digital finance and business informatics' },
      'profiles.diplomatic_analytic': { ru: 'Дипломатико-аналитический профиль', en: 'Diplomatic and analytic profile' },
      'profiles.economic_legal': { ru: 'Экономико-правовой профиль', en: 'Economic and legal profile' },
      'profiles.energy_logistics': { ru: 'Энергетика и логистика', en: 'Energy and logistics' },
      programFit: { ru: 'Соответствие программ', en: 'Program fit' },
      recommendedFormat: { ru: 'Рекомендуемый формат', en: 'Recommended format' },
      recommendedProfile: { ru: 'Рекомендуемый профиль', en: 'Recommended profile' },
      regulatoryQuality: { ru: 'Качество регулирования', en: 'Regulatory quality' },
      ruleOfLaw: { ru: 'Верховенство права', en: 'Rule of law' },
      sectorDepthScore: { ru: 'Глубина отраслевого спроса', en: 'Sector depth score' },
      servicesValueAdded: { ru: 'Доля услуг в экономике', en: 'Services value added' },
      strategicHrFit: { ru: 'Стратегическое кадровое соответствие', en: 'Strategic talent fit' },
      strategicPartnerUniversitiesCount: { ru: 'Стратегические партнерские университеты', en: 'Strategic partner universities' },
      studentPool2026: { ru: 'Студенческий пул, 2026', en: 'Student pool, 2026' },
      studentsYear1: { ru: 'Студенты в 1-й год', en: 'Students year 1' },
      studentsYear10: { ru: 'Студенты в 10-й год', en: 'Students year 10' },
      tertiaryEnrollmentGross: { ru: 'Охват высшим образованием', en: 'Tertiary enrollment' },
      tradePercentGdp: { ru: 'Открытость торговли', en: 'Trade openness' },
      unemployment: { ru: 'Безработица', en: 'Unemployment' },
      youth15_24_2026: { ru: 'Молодежь 15–24, 2026', en: 'Youth 15–24, 2026' },
      urbanPopulationPct: { ru: 'Городское население', en: 'Urban population' }
    };
    if (labels[key]?.[state.lang]) return labels[key][state.lang];
    const label = t(`field.${key}`);
    return label === `field.${key}` ? String(key).replaceAll('.', ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replaceAll('_', ' ') : label;
  }

  function compactInputLabel(key) {
    const labels = {
      politicalStability: { ru: 'Полит.<br>стабильность', en: 'Political<br>stability' },
      governmentEffectiveness: { ru: 'Эффективность<br>гос-ва', en: 'Government<br>effectiveness' },
      regulatoryQuality: { ru: 'Регулирование', en: 'Regulatory<br>quality' },
      ruleOfLaw: { ru: 'Право', en: 'Rule<br>of law' },
      logisticsPerformanceIndex: { ru: 'Логистика', en: 'Logistics' },
      internetUsersPct: { ru: 'Интернет', en: 'Internet<br>users' },
      urbanPopulationPct: { ru: 'Городское<br>население', en: 'Urban<br>population' }
    };
    return labels[key]?.[state.lang] || labels[key]?.en || inputLabel(key);
  }

  function compactProgramLabel(key) {
    const labels = {
      diplomatic_analytic: { ru: 'Дипломатико-<br>аналитический', en: 'Diplomatic<br>analytic' },
      economic_legal: { ru: 'Экономико-<br>правовой', en: 'Economic<br>legal' },
      digital_finance_business_informatics: { ru: 'Цифровые финансы<br>и бизнес-информатика', en: 'Digital finance<br>and BI' },
      energy_logistics: { ru: 'Энергетика<br>и логистика', en: 'Energy<br>logistics' }
    };
    return labels[key]?.[state.lang] || labels[key]?.en || i18nMap('programProfile', key);
  }

  function factorMethodText(factorKey) {
    const label = t(`factorMethod.${factorKey}`);
    return label === `factorMethod.${factorKey}` ? factorKey : label;
  }

  function inferInputUnit(key, value) {
    if (typeof value === 'boolean') return 'flag';
    if (/usd|npv|capex|tuition/i.test(key)) return 'USD';
    if (/share|pct|probability|enrollment|inflation|unemployment|growth|users|populationPct|percent/i.test(key)) return '%';
    if (/score|factor|fit|profiles\./i.test(key) && clean(value) !== null && Math.abs(clean(value)) <= 1) return '0-1';
    if (/population|students|pool|market/i.test(key)) return 'people';
    return '';
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

  function applyHashState() {
    const params = new URLSearchParams(location.hash.replace(/^#/, ''));
    if (['ru', 'en'].includes(params.get('lang'))) state.lang = params.get('lang');
    if (MAP_METRICS.includes(params.get('map'))) state.metric = params.get('map');
    const explicitIso = params.get('iso');
    if (explicitIso && state.countryByIso.has(explicitIso)) state.selectedIso3 = explicitIso;
    if (params.has('compare')) state.comparisonIso3s = parseComparisonIso3s(params.get('compare'));
    if (!explicitIso && state.comparisonIso3s.size) state.selectedIso3 = Array.from(state.comparisonIso3s)[0];
    if (params.get('region')) state.region = params.get('region');
    if (params.get('category')) state.category = params.get('category');
    const decoded = decodedWeights(params.get('weights'));
    if (decoded) state.weights = decoded;
    if (INDEX_KEYS.includes(params.get('factor'))) state.activeFactorKey = params.get('factor');
  }

  function writeHash() {
    const params = new URLSearchParams();
    params.set('iso', state.selectedIso3 || DEFAULT_SELECTED_ISO);
    params.set('lang', state.lang);
    params.set('map', state.metric);
    params.set('category', state.category);
    params.set('region', state.region);
    const compare = comparisonParam();
    if (compare) params.set('compare', compare);
    params.set('weights', encodedWeights());
    params.set('factor', state.activeFactorKey);
    history.replaceState(null, '', `#${params.toString()}`);
  }

  function saveControlState() {
    localStorage.setItem('mgimo_lang', state.lang);
    localStorage.setItem('mgimo_metric', state.metric);
    localStorage.setItem('mgimo_category', state.category);
    localStorage.setItem('mgimo_region', state.region);
    localStorage.removeItem('mgimo_weight_mode');
    localStorage.setItem('mgimo_weights', encodedWeights());
    localStorage.setItem('mgimo_active_factor', state.activeFactorKey);
    if (state.activeMethodInputKey) localStorage.setItem('mgimo_active_method_input', state.activeMethodInputKey);
    else localStorage.removeItem('mgimo_active_method_input');
    localStorage.removeItem('mgimo_compare_iso3');
    const compare = comparisonParam();
    if (compare) localStorage.setItem('mgimo_comparison_iso3s', compare);
    else localStorage.removeItem('mgimo_comparison_iso3s');
  }

  function populateMetricSelect() {
    const select = $('#metricSelect');
    if (!select) return;
    select.innerHTML = MAP_METRICS.map((metric) => `<option value="${metric}">${escapeHtml(metricLabel(metric))}</option>`).join('');
    select.value = state.metric;
  }

  function populateRegionSelect() {
    const select = $('#regionSelect');
    if (!select) return;
    const regions = Array.from(new Set((state.data?.countries || []).map((c) => normalizeRegion(c.region)).filter(Boolean))).sort();
    select.innerHTML = [`<option value="all">${escapeHtml(t('region.all'))}</option>`, ...regions.map((region) => `<option value="${escapeHtml(region)}">${escapeHtml(i18nMap('region', region))}</option>`)].join('');
    select.value = state.region;
  }

  function renderHeader() {
    const countries = state.data.countries || [];
    $('#headerTotalCountries').textContent = fmt(countries.length, 0);
    $('#headerEligibleCountries').textContent = fmt(countries.filter((country) => bool(country.eligible)).length, 0);
    $('#headerDirectShortlist').textContent = fmt(rankedCountries().filter((country) => bool(country.eligible) && statusCode(country) === 'candidate').length, 0);
    $('#headerPartnerFormats').textContent = fmt(rankedCountries().filter((country) => statusCode(country) === 'partner_model').length, 0);
    $('#headerPipelineCountries').textContent = fmt(rankedCountries().filter((country) => statusCode(country) === 'in_preparation').length, 0);
  }

  function setWeight(key, value, balanceOthers = true) {
    const current = activeWeights();
    const nextValue = clamp(value, 0.01, 0.90);
    const otherKeys = INDEX_KEYS.filter((item) => item !== key);
    const remaining = 1 - nextValue;
    const otherTotal = otherKeys.reduce((sum, item) => sum + (current[item] || 0), 0);
    const next = { ...current, [key]: nextValue };
    if (balanceOthers) {
      otherKeys.forEach((item) => {
        next[item] = otherTotal > 0 ? (current[item] / otherTotal) * remaining : remaining / otherKeys.length;
      });
    }
    state.weights = normalizeWeights(next);
    saveAndRender();
  }

  function adjustBoundary(index, newBoundaryPct) {
    const current = activeWeights();
    const leftKeys = INDEX_KEYS.slice(0, index + 1);
    const rightKeys = INDEX_KEYS.slice(index + 1);
    const leftMin = leftKeys.length * 0.01;
    const rightMin = rightKeys.length * 0.01;
    const leftTotal = clamp(newBoundaryPct / 100, leftMin, 1 - rightMin);
    const oldLeftTotal = leftKeys.reduce((sum, key) => sum + current[key], 0);
    const oldRightTotal = rightKeys.reduce((sum, key) => sum + current[key], 0);
    const next = {};
    leftKeys.forEach((key) => { next[key] = oldLeftTotal > 0 ? current[key] / oldLeftTotal * leftTotal : leftTotal / leftKeys.length; });
    rightKeys.forEach((key) => { next[key] = oldRightTotal > 0 ? current[key] / oldRightTotal * (1 - leftTotal) : (1 - leftTotal) / rightKeys.length; });
    state.weights = normalizeWeights(next);
    saveAndRender();
  }

  function renderWeights() {
    const weights = activeWeights();
    const editorOpen = Boolean(state.weightEditorOpen);
    state.weightEditorOpen = editorOpen;
    const lineButton = $('#weightModeLine');
    const slidersButton = $('#weightModeSliders');
    lineButton?.classList.toggle('active', !editorOpen);
    slidersButton?.classList.toggle('active', editorOpen);
    $('#weightLinePanel').hidden = false;
    if ($('#weightEditorPanel')) $('#weightEditorPanel').hidden = !editorOpen;
    if ($('#weightEditorBackdrop')) $('#weightEditorBackdrop').hidden = !editorOpen;

    const track = $('#weightLineTrack');
    if (track) {
      let cumulative = 0;
      const segments = INDEX_KEYS.map((key, index) => {
        const width = weights[key] * 100;
        const segment = `<div class="weight-segment factor-${index}" style="width:${width}%"><span>${escapeHtml(factorTitle(key))}</span><strong>${fmt(width, 0)}%</strong></div>`;
        cumulative += width;
        const handle = index < INDEX_KEYS.length - 1 ? `<button class="weight-boundary" type="button" data-index="${index}" style="left:${cumulative}%"><span class="visually-hidden">${escapeHtml(t('moveBoundary'))}</span></button>` : '';
        return segment + handle;
      }).join('');
      track.innerHTML = `<div class="weight-line-bar">${segments}</div>`;
      $$('.weight-boundary').forEach((handle) => {
        handle.addEventListener('pointerdown', (event) => {
          event.preventDefault();
          const rect = track.getBoundingClientRect();
          const index = Number(handle.dataset.index);
          const move = (moveEvent) => {
            const pct = clamp((moveEvent.clientX - rect.left) / rect.width * 100, 1, 99);
            adjustBoundary(index, pct);
          };
          const up = () => {
            document.removeEventListener('pointermove', move);
            document.removeEventListener('pointerup', up);
          };
          document.addEventListener('pointermove', move);
          document.addEventListener('pointerup', up);
        });
      });
    }

    const sliders = $('#weightSliderPanel');
    if (sliders) {
      sliders.innerHTML = INDEX_KEYS.map((key, index) => `
        <label class="weight-slider-row">
          <span><i class="factor-swatch factor-${index}"></i>${escapeHtml(factorTitle(key))}</span>
          <input class="weight-slider" type="range" min="1" max="70" step="1" value="${Math.round(weights[key] * 100)}" data-key="${key}">
          <input class="weight-percent-input" type="number" min="1" max="70" step="1" value="${Math.round(weights[key] * 100)}" data-key="${key}">
        </label>`).join('');
      sliders.querySelectorAll('[data-key]').forEach((input) => {
        input.addEventListener('input', (event) => setWeight(event.target.dataset.key, Number(event.target.value) / 100));
      });
    }

    const inputs = $('#weightInputs');
    if (inputs) {
      inputs.hidden = !editorOpen;
      inputs.innerHTML = editorOpen ? INDEX_KEYS.map((key, index) => `
        <label>
          <span><i class="factor-swatch factor-${index}"></i>${escapeHtml(factorTitle(key))}</span>
          <input type="number" min="1" max="70" step="1" value="${Math.round(weights[key] * 100)}" data-key="${key}">
        </label>`).join('') : '';
      inputs.querySelectorAll('input').forEach((input) => {
        input.addEventListener('change', (event) => setWeight(event.target.dataset.key, Number(event.target.value) / 100));
      });
    }
  }

  function mapMetricValue(country) {
    if (!country) return null;
    if (state.metric === 'priority') return country.currentPriority ?? priority(country);
    const value = factorScore(country, state.metric);
    return value === null ? null : value * 100;
  }

  function colorFor(value) {
    const n = clean(value);
    if (n === null) return '#eef3f8';
    const index = clamp(Math.floor((clamp(n, 0, 100) / 100) * BLUE_SCALE.length), 0, BLUE_SCALE.length - 1);
    return BLUE_SCALE[index];
  }

  function featureIso(feature) {
    const props = feature.properties || {};
    const iso = MAP_ISO_FIELDS.map((field) => props[field]).find((value) => value && value !== '-99');
    return iso ? String(iso).toUpperCase() : null;
  }

  function ensureHatchPattern() {
    const svg = $('#map svg');
    if (!svg || svg.querySelector('#unfriendlyHatch')) return;
    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    defs.innerHTML = '<pattern id="unfriendlyHatch" patternUnits="userSpaceOnUse" width="8" height="8"><rect width="8" height="8" fill="#e3e7ee"></rect><path d="M-2 8 L8 -2 M0 10 L10 0" stroke="#8c95a3" stroke-width="1.2" opacity="0.55"></path></pattern>';
    svg.prepend(defs);
  }

  function styleFeature(feature) {
    const iso = featureIso(feature);
    const country = iso ? state.countryByIso.get(iso) : null;
    const filtered = country && !visibleCountries().some((row) => row.iso3 === iso);
    const selected = country?.iso3 === state.selectedIso3;
    const compare = country ? state.comparisonIso3s.has(country.iso3) : false;
    const code = statusCode(country);
    const unfriendly = code === 'unfriendly';
    const domestic = code === 'domestic';
    const candidate = code === 'candidate';
    const emphasized = selected || compare;
    return {
      color: emphasized || candidate ? statusVisualColor(country) : '#ffffff',
      weight: emphasized ? 1.7 : candidate ? 1.15 : 0.55,
      opacity: 0.95,
      fillColor: unfriendly ? 'url(#unfriendlyHatch)' : colorFor(mapMetricValue(country)),
      fillOpacity: filtered ? 0.22 : domestic ? 0.62 : 0.88,
      className: [
        iso ? `country-${iso}` : '',
        code === 'in_preparation' ? 'neutral' : '',
        unfriendly ? 'unfriendly-country' : '',
        domestic ? 'domestic-country' : '',
        candidate ? 'candidate-country' : '',
        selected ? 'selected-country' : '',
        compare ? 'compare-country' : '',
        filtered ? 'filtered-out' : ''
      ].join(' ')
    };
  }

  function syncCountryPathClass(layer) {
    const element = layer.getElement();
    if (!element) return;
    Array.from(element.classList).forEach((className) => {
      if (
        /^country-[A-Z0-9]{3}$/.test(className)
        || ['neutral', 'unfriendly-country', 'domestic-country', 'candidate-country', 'selected-country', 'compare-country', 'filtered-out'].includes(className)
      ) {
        element.classList.remove(className);
      }
    });
    styleFeature(layer.feature).className
      .split(/\s+/)
      .filter(Boolean)
      .forEach((className) => element.classList.add(className));
  }

  function mapTooltipHtml(country) {
    if (!country) return '';
    const factualStatus = tableStatusLabel(country);
    const bars = INDEX_KEYS.map((key, index) => {
      const value = clamp(factorScore(country, key) * 100, 0, 100);
      return `<span><i class="factor-${index}" style="width:${value}%"></i></span>`;
    }).join('');
    const rank = state.rankByIso.get(country.iso3);
    return `
      <div class="branch-map-tooltip">
        <strong>${escapeHtml(countryName(country))}</strong>
        ${factualStatus ? `<em>${escapeHtml(factualStatus)}</em>` : ''}
        <span>${escapeHtml(t('rank'))}: ${escapeHtml(rank || t('notRanked'))} / ${escapeHtml(t('kpiCompositeShort'))}: ${fmtScore(priority(country), 1)}</span>
        <div class="tooltip-factor-bars">${bars}</div>
      </div>
    `;
  }

  function initMap() {
    state.map = L.map('map', { worldCopyJump: true, zoomControl: true, attributionControl: false }).setView([21, 35], 2);
    state.markerLayer = L.layerGroup().addTo(state.map);
    state.countryLayer = L.geoJSON(state.geo, {
      style: styleFeature,
      onEachFeature: (feature, layer) => {
        const iso = featureIso(feature);
        if (!iso) return;
        state.countryLayersByIso.set(iso, layer);
        layer.on('click', () => selectCountry(iso));
        layer.bindTooltip(() => {
          const country = state.countryByIso.get(iso);
          return country ? mapTooltipHtml(country) : iso;
        }, { sticky: true });
      }
    }).addTo(state.map);
    ensureHatchPattern();
  }

  function queueLayoutRefresh() {
    if (state.layoutRefreshFrame) cancelAnimationFrame(state.layoutRefreshFrame);
    state.layoutRefreshFrame = requestAnimationFrame(() => {
      state.layoutRefreshFrame = null;
      state.map?.invalidateSize();
      if (window.Plotly?.Plots?.resize) {
        $$('.js-plotly-plot').forEach((node) => window.Plotly.Plots.resize(node));
      }
    });
  }

  function svgIcon(type) {
    const icons = {
      presence: '<path d="M5 18h14M7 18V8l5-3 5 3v10M9 18v-6m3 6v-6m3 6v-6" />',
      preparation: '<circle cx="12" cy="12" r="3.2" /><path d="M12 4v2.2M12 17.8V20M4 12h2.2M17.8 12H20M6.3 6.3l1.6 1.6M16.1 16.1l1.6 1.6M17.7 6.3l-1.6 1.6M7.9 16.1l-1.6 1.6" />',
      partner: '<path d="M7 12l3-3 3 3 3-3 3 3-6 6-3-3-3 3-4-4 4-4" />',
      candidate: '<path d="M12 4l2.1 5.1 5.5.5-4.2 3.6 1.3 5.4-4.7-2.9-4.7 2.9 1.3-5.4-4.2-3.6 5.5-.5L12 4z" />',
      dot: '<circle cx="12" cy="12" r="5" />'
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true">${icons[type] || icons.dot}</svg>`;
  }

  function markerType(marker) {
    const type = String(marker.icon || marker.status_code || marker.presenceType || '').toLowerCase();
    if (type.includes('building') || type.includes('headquarters') || type.includes('campus') || (type.includes('branch') && !type.includes('preparation'))) return 'presence';
    if (type.includes('tool') || type.includes('preparation')) return 'preparation';
    if (type.includes('handshake') || type.includes('platform') || type.includes('partner')) return 'partner';
    if (type.includes('star') || type.includes('candidate')) return 'candidate';
    return 'dot';
  }

  function countryCoordinates(country) {
    const coords = country?.coordinates || {};
    const lat = clean(coords.lat ?? coords.latitude ?? country?.lat ?? country?.latitude);
    const lon = clean(coords.lon ?? coords.lng ?? coords.longitude ?? country?.lon ?? country?.longitude);
    if (lat === null || lon === null) return null;
    return { lat, lon };
  }

  function candidateCountryMarkers() {
    return rankedCountries()
      .filter((country) => bool(country.eligible) && statusCode(country) === 'candidate')
      .slice(0, 20)
      .map((country) => {
        const coords = countryCoordinates(country);
        if (!coords) return null;
        return {
          iso3: country.iso3,
          lat: coords.lat,
          lon: coords.lon,
          status_code: 'candidate',
          icon: 'candidate',
          marker_scope: 'country_candidate'
        };
      })
      .filter(Boolean);
  }

  function flatBranchMarkers() {
    const raw = state.data?.branchMarkers || [];
    const rows = Array.isArray(raw)
      ? [...raw]
      : [
        ...(raw.existing || []).map((row) => ({ ...row, status_code: 'presence', icon: 'building' })),
        ...(raw.inPreparation || []).map((row) => ({ ...row, status_code: 'in_preparation', icon: 'tooling' })),
        ...(raw.platforms || []).map((row) => ({ ...row, status_code: 'partner_model', icon: 'handshake' }))
      ];
    return [...rows, ...candidateCountryMarkers()];
  }

  function renderMarkers() {
    if (!state.markerLayer) return;
    state.markerLayer.clearLayers();
    flatBranchMarkers().forEach((marker) => {
      const country = state.countryByIso.get(marker.iso3);
      if (!country || !categoryMatches(country)) return;
      if (clean(marker.lat) === null || clean(marker.lon) === null) return;
      const type = markerType(marker);
      const icon = L.divIcon({
        className: `map-marker marker-${type}`,
        html: svgIcon(type),
        iconSize: [24, 24],
        iconAnchor: [12, 12]
      });
      L.marker([marker.lat, marker.lon], { icon, title: countryName(country) })
        .on('click', () => selectCountry(marker.iso3))
        .bindTooltip(`${countryName(country)}<br>${statusLabel(country)}`)
        .addTo(state.markerLayer);
    });
  }

  function renderMapLayer() {
    if (!state.countryLayer) return;
    state.countryLayer.setStyle(styleFeature);
    state.countryLayer.eachLayer((layer) => {
      const iso = featureIso(layer.feature);
      const country = iso ? state.countryByIso.get(iso) : null;
      if (iso && layer.getElement()) {
        syncCountryPathClass(layer);
        layer.getElement().setAttribute('data-iso3', iso);
        if (country) {
          layer.getElement().setAttribute('data-status', statusCode(country) === 'in_preparation' ? 'neutral' : statusCode(country));
          const factualStatus = tableStatusLabel(country);
          layer.getElement().setAttribute('aria-label', factualStatus ? `${countryName(country)} ${factualStatus}` : countryName(country));
        }
      }
    });
    ensureHatchPattern();
  }

  function renderMap() {
    renderMapLayer();
    renderMarkers();
    $('#mapHeading').textContent = metricLabel(state.metric);
    $('#mapLegend').textContent = t('mapLegendText', { metric: metricLabel(state.metric) });
  }

  function plotConfig() {
    return { displayModeBar: false, responsive: true };
  }

  function baseLayout(extra = {}) {
    return {
      autosize: true,
      margin: { l: 42, r: 18, t: 12, b: 36 },
      paper_bgcolor: 'rgba(0,0,0,0)',
      plot_bgcolor: 'rgba(0,0,0,0)',
      font: { family: 'Inter, Segoe UI, Arial, sans-serif', size: 11, color: '#17233a' },
      hoverlabel: { bgcolor: '#ffffff', bordercolor: '#cfd6e1', font: { color: '#17233a' } },
      legend: { orientation: 'h', x: 0, y: -0.2, xanchor: 'left', yanchor: 'top', font: { size: 10 } },
      ...extra
    };
  }

  function visualEmpty(selector, message) {
    const node = $(selector);
    if (!node) return;
    if (window.Plotly?.purge) window.Plotly.purge(node);
    node.innerHTML = `<div class="visual-empty">${escapeHtml(message || t('noData'))}</div>`;
  }

  function canPlot(selector) {
    return Boolean(window.Plotly && $(selector));
  }

  function factorGroup(country, key) {
    return state.factorByIso.get(country?.iso3)?.get(key) || factorInputGroup(country, key);
  }

  function factorTraceText(country, key) {
    const group = factorGroup(country, key);
    const input = (group?.inputs || []).find((row) => clean(row.input_weight) > 0) || (group?.inputs || [])[0] || {};
    const parts = [
      `${t('source')}: ${sourceLabel(input.source_key)}`,
      `${t('year')}: ${input.year || t('noData')}`,
      `${t('rawValue')}: ${formatInputValue(input.raw_value, input.unit)}`,
      `${t('normalizedValue')}: ${formatInputValue(input.normalized_value, '0-1')}`,
      `${t('weight')}: ${fmtPct(input.input_weight ?? 0, 0)}`,
      `${t('observationStatus')}: ${observationLabel(input.observation_status)}`
    ];
    return parts.join('<br>');
  }

  function indexContributionRows(country) {
    const weights = activeWeights();
    const eps = state.data?.methodology?.normalization?.epsilon ?? SCORE_EPSILON;
    return INDEX_KEYS.map((key, index) => {
      const score = clamp(factorScore(country, key), 0, 1);
      const weight = weights[key] || 0;
      return {
        key,
        index,
        title: factorTitle(key),
        score,
        weight,
        contribution: score * weight * 100,
        geom: weight * Math.log(eps + score),
        trace: factorTraceText(country, key)
      };
    });
  }

  function methodText(ru, en) {
    return state.lang === 'ru' ? ru : en;
  }

  function factorIndex(key) {
    const index = INDEX_KEYS.indexOf(key);
    return index >= 0 ? index : 0;
  }

  function factorSymbol(key) {
    return `I${factorIndex(key) + 1}`;
  }

  function factorStyleAttr(key) {
    return `--factor-color:var(--factor-${factorIndex(key)})`;
  }

  function mathNumber(value, digits = 2) {
    const n = clean(value);
    if (n === null) return t('noData');
    return n.toLocaleString(state.lang === 'ru' ? 'ru-RU' : 'en-US', {
      minimumFractionDigits: 0,
      maximumFractionDigits: digits
    });
  }

  function evidenceMeta(factorKey, input) {
    const meta = branchIndicatorMeta(factorKey, input.key);
    const unit = meta.unit || input.unit || '';
    return {
      indicatorCode: meta.official_indicator_code || meta.indicator_code || meta.input_key || input.key || 'not_applicable_modelled_component',
      officialName: localizedDictionaryName(meta, inputLabel(input.key)),
      unit,
      sourceName: meta.source_name || sourceLabel(input.source_key),
      withinWeight: meta.within_factor_weight ?? input.input_weight
    };
  }

  function lineageMeta(country, factorKey, input) {
    const line = factorLineage(country, factorKey, input?.key);
    const meta = evidenceMeta(factorKey, input || {});
    return {
      ...line,
      official_indicator_code: line?.official_indicator_code || meta.indicatorCode,
      official_indicator_name_en: line?.official_indicator_name_en || meta.officialName,
      official_indicator_name_ru: line?.official_indicator_name_ru || meta.officialName,
      provider: line?.provider || meta.sourceName,
      source_name: line?.source_name || meta.sourceName,
      source_note: line?.source_note || '',
      official_url: line?.official_url || '',
      raw_file: line?.raw_file || '',
      source_manifest_code: line?.source_manifest_code || '',
      latest_observed_year_in_run: line?.latest_observed_year_in_run || '',
      year: line?.year ?? input?.year,
      unit: line?.unit || meta.unit || input?.unit || '',
      raw_value: line?.raw_value ?? input?.raw_value,
      normalized_value: line?.normalized_value ?? input?.normalized_value,
      normalization_method: line?.normalization_method || input?.normalization_method || '',
      within_factor_weight: line?.within_factor_weight ?? meta.withinWeight,
      factor_weight: line?.factor_weight ?? input?.factor_weight,
      scoring_role: line?.scoring_role || input?.scoring_role || '',
      observation_status: line?.observation_status || input?.observation_status || ''
    };
  }

  function lineageTitle(line) {
    if (!line) return t('noData');
    return state.lang === 'ru'
      ? line.official_indicator_name_ru || line.official_indicator_name_en || line.input_key || t('noData')
      : line.official_indicator_name_en || line.official_indicator_name_ru || line.input_key || t('noData');
  }

  function formulaInputLabel(factorKey, input) {
    const meta = evidenceMeta(factorKey, input);
    const code = meta.indicatorCode || input?.key || '';
    if (code && code !== 'not_applicable_modelled_component') return code;
    return input?.key || meta.officialName || '';
  }

  function renderFormulaInputButton(group, input, index, options = {}) {
    const selected = input.key === state.activeMethodInputKey;
    const role = String(input.scoring_role || '').toLowerCase();
    const code = formulaInputLabel(group.factor_key, input);
    const normalized = clean(input.normalized_value);
    const weight = clean(input.input_weight);
    const prefix = role.includes('multiplicative_gate')
      ? '×'
      : weight !== null && weight < 0
        ? '−'
        : options.isFirst
          ? ''
          : '+';
    const absWeight = weight === null ? null : Math.abs(weight);
    const weightText = role.includes('multiplicative_gate') || absWeight === null
      ? ''
      : `${mathNumber(absWeight, 2)} × `;
    const valueText = role.includes('multiplicative_gate')
      ? `G(${escapeHtml(code)})`
      : `N(${escapeHtml(code)})`;
    return `
      <button class="method-equation-token ${selected ? 'active' : ''}" type="button" data-method-factor="${escapeHtml(group.factor_key)}" data-method-input="${escapeHtml(input.key)}" style="${factorStyleAttr(group.factor_key)}" title="${escapeHtml(inputLabel(input.key))}">
        <span class="math-token-label">${escapeHtml(inputLabel(input.key))}</span>
        <span class="math-token-body">
          ${prefix ? `<span class="math-sign">${escapeHtml(prefix)}</span>` : ''}
          <span class="math-term">${escapeHtml(weightText)}${valueText}</span>
        </span>
        ${normalized !== null ? `<small>${escapeHtml(mathNumber(normalized * 100, 1))}</small>` : ''}
      </button>`;
  }

  function renderComponentEquation(group) {
    const inputs = componentFormulaInputs(group);
    const formulaInputs = inputs.length ? inputs : directFormulaInputs(group);
    const terms = formulaInputs.map((input, index) => renderFormulaInputButton(group, input, index, { isFirst: index === 0, short: true })).join('');
    return `
      <div class="math-equation index-equation component-equation" aria-label="${escapeHtml(t('formula'))}">
        <span class="math-result" style="${factorStyleAttr(group.factor_key)}">${escapeHtml(factorSymbol(group.factor_key))}</span>
        <span class="math-eq">=</span>
        <span class="component-equation-terms">${terms || `<span>${escapeHtml(t('noData'))}</span>`}</span>
      </div>`;
  }

  function renderMethodInputStrip(group) {
    const inputs = componentFormulaInputs(group);
    const formulaInputs = inputs.length ? inputs : directFormulaInputs(group);
    return `
      <div class="method-input-strip">
        ${formulaInputs.map((input, index) => {
          const meta = evidenceMeta(group.factor_key, input);
          const selected = input.key === state.activeMethodInputKey;
          return `
            <button class="method-input-line ${selected ? 'active' : ''}" type="button" data-method-factor="${escapeHtml(group.factor_key)}" data-method-input="${escapeHtml(input.key)}" style="${factorStyleAttr(group.factor_key)}">
              <code>${escapeHtml(formulaInputLabel(group.factor_key, input))}</code>
              <span>${escapeHtml(meta.officialName)}</span>
              <strong>${escapeHtml(fmtPct(meta.withinWeight, 0))}</strong>
            </button>`;
        }).join('')}
      </div>`;
  }

  function displayFactorFormulaText(factorKey) {
    let text = factorMethodText(factorKey);
    if (state.lang === 'ru') {
      text = text
        .replaceAll('evidence table', 'паспорте данных')
        .replaceAll('не получают отдельный бонус', 'не учитываются как отдельное слагаемое');
    }
    return text;
  }

  function directFormulaInputs(group) {
    return (group?.inputs || []).filter((input) => {
      const role = String(input.scoring_role || '').toLowerCase();
      const weight = clean(input.input_weight);
      return role.includes('direct_factor_formula_component') && weight !== null && weight > 0;
    });
  }

  function componentFormulaInputs(group) {
    return (group?.inputs || []).filter((input) => {
      const role = String(input.scoring_role || '').toLowerCase();
      return role.includes('direct_factor_formula_component') || role.includes('direct_penalty') || role.includes('multiplicative_gate');
    });
  }

  function methodRoleInputs(group) {
    return (group?.inputs || []).filter((input) => {
      const role = String(input.scoring_role || '').toLowerCase();
      return role && !role.includes('direct_factor_formula_component');
    });
  }

  function ensureActiveMethodInput(group) {
    const inputs = componentFormulaInputs(group);
    const allInputs = inputs.length ? inputs : group?.inputs || [];
    if (!allInputs.length) {
      state.activeMethodInputKey = '';
      return null;
    }
    if (!allInputs.some((input) => input.key === state.activeMethodInputKey)) {
      state.activeMethodInputKey = allInputs[0].key;
    }
    return allInputs.find((input) => input.key === state.activeMethodInputKey) || allInputs[0];
  }

  function formulaCountryRows() {
    return chartCountries();
  }

  function bindMethodFactorButtons(root = document) {
    root.querySelectorAll('[data-method-factor]').forEach((button) => {
      button.addEventListener('click', () => {
        const key = button.dataset.methodFactor;
        if (!INDEX_KEYS.includes(key)) return;
        state.activeFactorKey = key;
        ensureActiveMethodInput(factorGroup(selectedCountry(), key));
        saveControlState();
        renderFactorTabs();
        renderExecutiveVisuals();
        renderMethodology();
        writeHash();
      });
    });
  }

  function bindMethodInputButtons(root = document) {
    root.querySelectorAll('[data-method-input]').forEach((button) => {
      button.addEventListener('click', () => {
        const inputKey = button.dataset.methodInput;
        const factorKey = button.dataset.methodFactor || state.activeFactorKey;
        if (!inputKey) return;
        state.activeFactorKey = factorKey;
        state.activeMethodInputKey = inputKey;
        saveControlState();
        renderFactorTabs();
        renderExecutiveVisuals();
        renderMethodology();
        writeHash();
      });
    });
  }

  function renderIndexEquation() {
    const eps = state.data?.methodology?.normalization?.epsilon ?? SCORE_EPSILON;
    const terms = INDEX_KEYS.map((key, index) => `
      <button class="math-factor-token ${key === state.activeFactorKey ? 'active' : ''}" type="button" data-method-factor="${escapeHtml(key)}" style="${factorStyleAttr(key)}" title="${escapeHtml(factorTitle(key))}">
        <span class="math-token-label">${escapeHtml(factorTitle(key))}</span>
        <span class="math-token-body">
          <span>w<sub>${index + 1}</sub></span>
          <span class="math-weight-value">${escapeHtml(fmtPct(activeWeights()[key], 0))}</span>
          <span>ln(${mathNumber(eps, 2)} + ${escapeHtml(factorSymbol(key))})</span>
        </span>
      </button>`).join('<span class="math-plus">+</span>');
    return `
      <div class="math-equation index-equation" aria-label="${escapeHtml(t('formulaTitle'))}">
        <span class="math-result">${escapeHtml(methodText('Индекс', 'Index'))}</span>
        <span class="math-eq">=</span>
        <span class="math-scale">100</span>
        <span class="math-op">×</span>
        <span class="math-exp">exp</span>
        <span class="math-paren">(</span>
        <span class="math-sigma">Σ</span>
        <span class="math-token-row">${terms}</span>
        <span class="math-paren">)</span>
      </div>`;
  }

  function renderCountryEquation(country) {
    const terms = indexContributionRows(country).map((row) => `
      <button class="index-term ${row.key === state.activeFactorKey ? 'active' : ''}" type="button" data-method-factor="${escapeHtml(row.key)}" style="${factorStyleAttr(row.key)}" title="${escapeHtml(row.trace.replaceAll('<br>', ' | '))}">
        <em class="index-term-label">${escapeHtml(factorTitle(row.key))}</em>
        <span>${escapeHtml(factorSymbol(row.key))}</span>
        <strong>${mathNumber(row.weight, 3)} × ln(${mathNumber(SCORE_EPSILON + row.score, 3)})</strong>
        <small>${mathNumber(row.score * 100, 1)}</small>
      </button>`).join('');
    return `
      <article class="country-equation-row" style="--country-color:${escapeHtml(countryVisualColor(country))}">
        <div class="country-equation-head">
          <span>${flagHtml(country.iso2)} ${escapeHtml(countryName(country))}</span>
          <strong>${fmtScore(priority(country), 1)}</strong>
        </div>
        <div class="country-equation-terms">${terms}</div>
      </article>`;
  }

  function renderSelectedFactorBars() {
    const country = selectedCountry();
    const node = $('#selectedFactorBars');
    if (!country || !node) return;
    const rows = indexContributionRows(country);
    node.innerHTML = rows.map((row) => `
      <button class="selected-factor-row" type="button" data-factor="${escapeHtml(row.key)}" title="${escapeHtml(row.trace.replaceAll('<br>', ' | '))}">
        <span><i class="factor-swatch factor-${row.index}"></i>${escapeHtml(row.title)}</span>
        <strong>${fmtScore(row.score * 100, 1)}</strong>
        <em>
          <i style="width:${clamp(row.score * 100, 0, 100)}%"></i>
        </em>
      </button>
    `).join('');
    node.querySelectorAll('[data-factor]').forEach((button) => {
      button.addEventListener('click', () => {
        state.activeFactorKey = button.dataset.factor;
        saveControlState();
        renderFactorTabs();
        renderExecutiveVisuals();
        renderMethodology();
        writeHash();
      });
    });

    const sorted = [...rows].sort((a, b) => b.score - a.score);
    const strengths = sorted.slice(0, 2).map((row) => row.title).join(', ');
    const risks = sorted.slice(-2).reverse().map((row) => row.title).join(', ');
    const insightNode = $('#selectedInsightList');
    if (insightNode) {
      insightNode.innerHTML = `
        <div><span>${escapeHtml(t('strengthsLabel'))}</span><strong>${escapeHtml(strengths || t('noData'))}</strong></div>
        <div><span>${escapeHtml(t('risksLabel'))}</span><strong>${escapeHtml(risks || t('noData'))}</strong></div>
      `;
    }
  }

  function renderIndexDecompositionChart(country) {
    if (!canPlot('#indexDecompositionChart')) return;
    const node = $('#indexDecompositionChart');
    const makeTrace = (itemCountry, index) => {
      const items = indexContributionRows(itemCountry);
      return {
      type: 'bar',
      orientation: 'h',
      name: countryName(itemCountry),
      y: items.map((row) => row.title),
      x: items.map((row) => row.contribution),
      customdata: items.map((row) => row.key),
      marker: { color: chartColor(itemCountry, index) },
      hovertext: items.map((row) => `${countryName(itemCountry)}<br>${row.title}<br>${t('score')}: ${fmtScore(row.score * 100, 1)}<br>${t('weight')}: ${fmtPct(row.weight, 0)}<br>${t('indexContributionLabel')}: ${fmtScore(row.contribution, 2)}<br>${state.lang === 'ru' ? 'геометрический член' : 'geom'}: ${fmt(row.geom, 4)}<br>${row.trace}`),
      hoverinfo: 'text'
      };
    };
    Plotly.react(node, chartCountries().map(makeTrace), baseLayout({
      barmode: 'group',
      margin: { l: 144, r: 12, t: 6, b: 52 },
      xaxis: { automargin: true },
      yaxis: { automargin: true, tickfont: { size: 10 } },
      legend: { orientation: 'h', x: 0, y: -0.18, font: { size: 10 } }
    }), plotConfig());
    node.on('plotly_click', (event) => {
      const key = event?.points?.[0]?.customdata;
      if (INDEX_KEYS.includes(key)) {
        state.activeFactorKey = key;
        saveControlState();
        renderFactorTabs();
        renderExecutiveVisuals();
        renderMethodology();
        writeHash();
      }
    });
  }

  function renderFinanceChart(country) {
    if (!canPlot('#financeChart')) return;
    const node = $('#financeChart');
    const makeRow = (itemCountry, itemFin) => ({
      country: itemCountry,
      name: countryName(itemCountry),
      p10: clean(itemFin?.npvP10Usd),
      expected: clean(itemFin?.npvExpectedUsd),
      p90: clean(itemFin?.npvP90Usd),
      capex: clean(itemFin?.capexUsd),
      opex: clean(itemFin?.opexUsd ?? itemFin?.annualOpexUsd ?? itemFin?.averageTuitionUsd),
      probability: clean(itemFin?.npvPositiveProbability),
      payback: clean(itemFin?.paybackYears)
    });
    const rows = chartCountries().map((itemCountry) => makeRow(itemCountry, itemCountry?.finance || {})).filter((row) => row.expected !== null);
    const selectedRow = rows[0];
    const kpiNode = $('#financeKpis');
    if (kpiNode) {
      kpiNode.innerHTML = selectedRow ? [
        [state.lang === 'ru' ? 'CAPEX' : 'CAPEX', fmtMoney(selectedRow.capex)],
        [state.lang === 'ru' ? 'OPEX / tuition' : 'OPEX / tuition', fmtMoney(selectedRow.opex)],
        [state.lang === 'ru' ? 'P(NPV>0)' : 'P(NPV>0)', fmtPct(selectedRow.probability, 0)],
        [state.lang === 'ru' ? 'Окупаемость' : 'Payback', selectedRow.payback === null ? t('noData') : `${fmt(selectedRow.payback, 1)} ${state.lang === 'ru' ? 'лет' : 'y'}`]
      ].map(([label, value]) => `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`).join('') : '';
    }
    if (!rows.length) {
      visualEmpty('#financeChart', t('noData'));
      return;
    }
    const traceText = `${t('source')}: financial_model_best.csv<br>${t('observationStatus')}: ${observationLabel('modelled')}<br>${t('year')}: ${state.data?.metadata?.baseYear || 2026}`;
    const rangedRows = rows.filter((row) => row.p10 !== null && row.p90 !== null);
    const rangeTraces = rangedRows.map((row, index) => ({
      type: 'scatter',
      mode: 'lines',
      name: row.name,
      x: [row.p10, row.p90],
      y: [row.name, row.name],
      line: { color: chartColor(row.country, index), width: index === 0 ? 8 : 6 },
      hovertemplate: `${row.name}<br>NPV P10: ${fmtMoney(row.p10)}<br>${state.lang === 'ru' ? 'Ожидаемая NPV' : 'Expected NPV'}: ${fmtMoney(row.expected)}<br>NPV P90: ${fmtMoney(row.p90)}<br>${state.lang === 'ru' ? 'Первичные затраты' : 'CAPEX'}: ${fmtMoney(row.capex)}<br>${traceText}<extra></extra>`,
      showlegend: false
    }));
    const expectedTrace = {
      type: 'scatter',
      mode: 'markers',
      name: state.lang === 'ru' ? 'Ожидаемая NPV' : 'Expected NPV',
      x: rows.map((row) => row.expected),
      y: rows.map((row) => row.name),
      marker: { color: rows.map((row, index) => chartColor(row.country, index)), size: 10, symbol: 'diamond' },
      customdata: rows.map((row) => [fmtMoney(row.capex), fmtPct(row.probability, 0)]),
      hovertemplate: `%{y}<br>${state.lang === 'ru' ? 'Ожидаемая NPV' : 'Expected NPV'}: %{x:$,.0f}<br>${state.lang === 'ru' ? 'Первичные затраты' : 'CAPEX'}: %{customdata[0]}<br>${state.lang === 'ru' ? 'Вероятность положительной NPV' : 'Positive NPV probability'}: %{customdata[1]}<br>${traceText}<extra></extra>`
    };
    Plotly.react(node, [...rangeTraces, expectedTrace], baseLayout({
      margin: { l: 106, r: 16, t: 8, b: 34 },
      xaxis: { tickprefix: '$', separatethousands: true, automargin: true, zeroline: true },
      yaxis: { automargin: true, tickfont: { size: 10 } },
      annotations: rangedRows.length ? [] : [{
        text: state.lang === 'ru' ? 'Интервал P10-P90 не загружен' : 'P10-P90 interval not loaded',
        xref: 'paper',
        yref: 'paper',
        x: 0,
        y: 1.08,
        showarrow: false,
        font: { size: 10, color: '#5d6778' },
        align: 'left'
      }],
      legend: { orientation: 'h', x: 0, y: -0.18, font: { size: 10 } }
    }), plotConfig());
    node.on('plotly_click', () => selectCountry(country.iso3));
  }

  function demographySourceLabel(series) {
    const source = `${series?.source || ''} ${series?.forecastSource || ''}`.toLowerCase();
    if (/un wpp|world population prospects/.test(source)) {
      return state.lang === 'ru' ? 'UN WPP 2024' : 'UN WPP 2024';
    }
    return t('sourceNotLoaded');
  }

  function demographyActualLabel() {
    return t('wppEstimate');
  }

  function demographyActualShortLabel() {
    return state.lang === 'ru' ? 'оценка' : 'estimate';
  }

  function demographyStatusLabel(status) {
    if (status === 'official_estimate') return t('wppEstimate');
    if (status === 'official_projection') return t('wppProjection');
    return status || t('sourceNotLoaded');
  }

  function demographyForecastLabel(series) {
    const source = `${series?.source || ''} ${series?.forecastSource || ''}`.toLowerCase();
    if (/un wpp|world population prospects/.test(source)) return t('wppProjection');
    return t('sourceNotLoaded');
  }

  function demographyForecastShortLabel() {
    return state.lang === 'ru' ? 'прогноз' : 'projection';
  }

  function renderPopulationYouthChart(country) {
    if (!canPlot('#populationYouthChart')) return;
    const seriesRows = chartCountries()
      .map((itemCountry, index) => ({
        country: itemCountry,
        index,
        series: state.data?.demographySeries?.[itemCountry?.iso3]
      }))
      .filter((row) => row.series?.actual?.length || row.series?.forecast?.length);
    if (!seriesRows.length) {
      visualEmpty('#populationYouthChart', t('noData'));
      return;
    }
    const youthLabel = state.lang === 'ru' ? '15–24' : '15–24';
    const currentYear = state.data?.metadata?.baseYear || 2026;
    const totalTrace = (rows, name, color, dash, itemSeries, opacity = 1, fill = false, showlegend = true) => ({
      type: 'scatter',
      mode: 'lines',
      name,
      legendgroup: name,
      showlegend,
      x: rows.map((row) => row.year),
      y: rows.map((row) => clean(row.population_total)),
      line: { color, dash, width: 2.4 },
      fill: fill ? 'tozeroy' : 'none',
      fillcolor: `rgba(31,95,170,${0.08 * opacity})`,
      opacity,
      customdata: rows.map((row) => [demographySourceLabel(itemSeries), demographyStatusLabel(row.observation_status)]),
      hovertemplate: `${name}<br>${t('year')}: %{x}<br>${t('value')}: %{y:,.0f}<br>${t('source')}: %{customdata[0]}<br>${t('status')}: %{customdata[1]}<extra></extra>`
    });
    const youthTrace = (rows, name, color, itemSeries, opacity = 1, showlegend = true) => ({
      type: 'bar',
      name,
      legendgroup: name,
      showlegend,
      x: rows.map((row) => row.year),
      y: rows.map((row) => clean(row.pop_15_24)),
      marker: { color },
      opacity,
      customdata: rows.map((row) => [demographySourceLabel(itemSeries), demographyStatusLabel(row.observation_status)]),
      hovertemplate: `${name}<br>${t('year')}: %{x}<br>${t('value')}: %{y:,.0f}<br>${t('source')}: %{customdata[0]}<br>${t('status')}: %{customdata[1]}<extra></extra>`
    });
    const traces = [];
    seriesRows.forEach(({ country: itemCountry, index, series }) => {
      const color = chartColor(itemCountry, index);
      const totalName = `${countryName(itemCountry)}: ${t('populationTotalShort')}`;
      const youthName = `${countryName(itemCountry)}: ${youthLabel}`;
      if (series?.actual?.length) {
        traces.push(totalTrace(series.actual, totalName, color, 'solid', series, index === 0 ? 1 : 0.7, index === 0, true));
        traces.push(youthTrace(series.actual, youthName, color, series, index === 0 ? 0.58 : 0.42, true));
      }
      if (series?.forecast?.length) {
        traces.push(totalTrace(series.forecast, totalName, color, 'dot', series, index === 0 ? 0.72 : 0.48, false, !series?.actual?.length));
        traces.push(youthTrace(series.forecast, youthName, color, series, index === 0 ? 0.26 : 0.18, !series?.actual?.length));
      }
    });
    Plotly.react($('#populationYouthChart'), traces, baseLayout({
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
      annotations: [2026, 2035, 2050].map((year) => ({
        x: year,
        y: 1.02,
        xref: 'x',
        yref: 'paper',
        text: String(year),
        showarrow: false,
        font: { size: 9, color: '#5d6778' }
      })),
      legend: { orientation: 'h', x: 0.02, y: -0.24, font: { size: 9 } }
    }), plotConfig());
  }

  function renderSingleAgeSexPyramidChart(country) {
    if (!canPlot('#ageSexPyramidChart')) return;
    const pyramid = state.data?.ageSexPyramid?.[country?.iso3];
    if (!pyramid?.ageBands?.length) {
      visualEmpty('#ageSexPyramidChart', t('noData'));
      return;
    }
    const year = 2026;
    const idx = (pyramid.forecastYears || []).indexOf(year);
    if (idx < 0) {
      visualEmpty('#ageSexPyramidChart', t('noData'));
      return;
    }
    const male = pyramid.forecastMale?.[idx];
    const female = pyramid.forecastFemale?.[idx];
    if (!male?.length || !female?.length) {
      visualEmpty('#ageSexPyramidChart', t('noData'));
      return;
    }
    const bands = pyramid.ageBands;
    const youthBands = new Set(['15-19', '20-24']);
    const maleColors = bands.map((band) => youthBands.has(band) ? '#0b3f86' : '#8fb3d9');
    const femaleColors = bands.map((band) => youthBands.has(band) ? '#e0aa24' : '#e8cc70');
    const statusLabel = demographyStatusLabel(pyramid.yearStatuses?.[String(year)] || 'official_projection');
    const toMillions = (value) => {
      const n = clean(value);
      return n === null ? 0 : n / 1_000_000;
    };
    const maleMillions = male.map((value) => -toMillions(value));
    const femaleMillions = female.map((value) => toMillions(value));
    const maxAbs = Math.max(
      0.01,
      ...maleMillions.map((value) => Math.abs(value)),
      ...femaleMillions.map((value) => Math.abs(value))
    );
    const axis = nicePyramidAxis(maxAbs);
    Plotly.react($('#ageSexPyramidChart'), [
      { type: 'bar', orientation: 'h', name: t('maleLabel'), y: bands, x: maleMillions, marker: { color: maleColors }, hovertemplate: `${t('maleLabel')}<br>%{y}: %{customdata[0]:,.0f}<br>${state.lang === 'ru' ? 'млн человек' : 'million people'}: %{customdata[2]:.2f}<br>${t('year')}: ${year}<br>${t('source')}: ${demographySourceLabel(pyramid)}<br>${t('status')}: %{customdata[1]}<extra></extra>`, customdata: male.map((value) => [value, statusLabel, toMillions(value)]) },
      { type: 'bar', orientation: 'h', name: t('femaleLabel'), y: bands, x: femaleMillions, marker: { color: femaleColors }, hovertemplate: `${t('femaleLabel')}<br>%{y}: %{customdata[0]:,.0f}<br>${state.lang === 'ru' ? 'млн человек' : 'million people'}: %{customdata[2]:.2f}<br>${t('year')}: ${year}<br>${t('source')}: ${demographySourceLabel(pyramid)}<br>${t('status')}: %{customdata[1]}<extra></extra>`, customdata: female.map((value) => [value, statusLabel, toMillions(value)]) }
    ], baseLayout({
      barmode: 'relative',
      margin: { l: 54, r: 12, t: 2, b: 86 },
      xaxis: {
        range: [-axis.axisMax, axis.axisMax],
        tickmode: 'array',
        tickvals: axis.tickVals,
        ticktext: axis.tickText,
        tickangle: 0,
        title: state.lang === 'ru' ? 'млн человек' : 'million people',
        zeroline: true,
        automargin: true
      },
      yaxis: { automargin: true, tickfont: { size: 10 } },
      legend: { orientation: 'h', x: 0.5, xanchor: 'center', y: -0.36, yanchor: 'top', font: { size: 10 } },
      annotations: [{ text: t('youthCohortNote'), xref: 'paper', yref: 'paper', x: 0.5, y: -0.2, showarrow: false, font: { size: 10, color: '#5d6778' } }]
    }), plotConfig());
  }

  function ageSexPyramidRecord(country) {
    const pyramid = state.data?.ageSexPyramid?.[country?.iso3];
    if (!pyramid?.ageBands?.length) return null;
    const year = 2026;
    const idx = (pyramid.forecastYears || []).indexOf(year);
    if (idx < 0) return null;
    const male = pyramid.forecastMale?.[idx];
    const female = pyramid.forecastFemale?.[idx];
    if (!male?.length || !female?.length) return null;
    const toMillions = (value) => {
      const n = clean(value);
      return n === null ? 0 : n / 1_000_000;
    };
    const maleMillions = male.map((value) => -toMillions(value));
    const femaleMillions = female.map((value) => toMillions(value));
    const maxAbs = Math.max(
      0.01,
      ...maleMillions.map((value) => Math.abs(value)),
      ...femaleMillions.map((value) => Math.abs(value))
    );
    return {
      country,
      pyramid,
      year,
      bands: pyramid.ageBands,
      male,
      female,
      maleMillions,
      femaleMillions,
      maxAbs,
      statusLabel: demographyStatusLabel(pyramid.yearStatuses?.[String(year)] || 'official_projection'),
      toMillions
    };
  }

  function nicePyramidAxis(maxValue) {
    const safeMaxAbs = Math.max(0.01, clean(maxValue) ?? 0);
    const targetStep = safeMaxAbs / 2;
    const exponent = Math.floor(Math.log10(targetStep || 1));
    const magnitude = 10 ** exponent;
    const fraction = targetStep / magnitude;
    const niceFraction = fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 5 ? 5 : 10;
    const halfStep = niceFraction * magnitude;
    const axisMax = halfStep * 2;
    const tickVals = [-axisMax, -halfStep, 0, halfStep, axisMax].map((value) => Number(value.toFixed(3)));
    const tickDigits = halfStep < 0.1 ? 2 : halfStep < 1 ? 1 : 0;
    const tickText = tickVals.map((value) => Math.abs(value).toLocaleString(
      state.lang === 'ru' ? 'ru-RU' : 'en-US',
      { maximumFractionDigits: tickDigits }
    ));
    return { axisMax, tickVals, tickText };
  }

  function renderAgeSexPyramidPlot(node, record, axis, compact = false) {
    const youthBands = new Set(['15-19', '20-24']);
    const maleColors = record.bands.map((band) => youthBands.has(band) ? '#0b3f86' : '#8fb3d9');
    const femaleColors = record.bands.map((band) => youthBands.has(band) ? '#e0aa24' : '#e8cc70');
    const unitLabel = state.lang === 'ru' ? 'млн человек' : 'million people';
    Plotly.react(node, [
      {
        type: 'bar',
        orientation: 'h',
        name: t('maleLabel'),
        y: record.bands,
        x: record.maleMillions,
        marker: { color: maleColors },
        showlegend: !compact,
        hovertemplate: `${countryName(record.country)}<br>${t('maleLabel')}<br>%{y}: %{customdata[0]:,.0f}<br>${unitLabel}: %{customdata[2]:.2f}<br>${t('year')}: ${record.year}<br>${t('source')}: ${demographySourceLabel(record.pyramid)}<br>${t('status')}: %{customdata[1]}<extra></extra>`,
        customdata: record.male.map((value) => [value, record.statusLabel, record.toMillions(value)])
      },
      {
        type: 'bar',
        orientation: 'h',
        name: t('femaleLabel'),
        y: record.bands,
        x: record.femaleMillions,
        marker: { color: femaleColors },
        showlegend: !compact,
        hovertemplate: `${countryName(record.country)}<br>${t('femaleLabel')}<br>%{y}: %{customdata[0]:,.0f}<br>${unitLabel}: %{customdata[2]:.2f}<br>${t('year')}: ${record.year}<br>${t('source')}: ${demographySourceLabel(record.pyramid)}<br>${t('status')}: %{customdata[1]}<extra></extra>`,
        customdata: record.female.map((value) => [value, record.statusLabel, record.toMillions(value)])
      }
    ], baseLayout({
      barmode: 'relative',
      margin: compact ? { l: 42, r: 8, t: 2, b: 48 } : { l: 54, r: 12, t: 2, b: 76 },
      xaxis: {
        range: [-axis.axisMax, axis.axisMax],
        tickmode: 'array',
        tickvals: axis.tickVals,
        ticktext: axis.tickText,
        tickangle: 0,
        title: compact ? '' : unitLabel,
        zeroline: true,
        automargin: true,
        tickfont: { size: compact ? 9 : 10 }
      },
      yaxis: { automargin: true, tickfont: { size: compact ? 8 : 10 } },
      legend: { orientation: 'h', x: 0.5, xanchor: 'center', y: -0.28, yanchor: 'top', font: { size: 10 } },
      annotations: compact ? [] : [{ text: t('youthCohortNote'), xref: 'paper', yref: 'paper', x: 0.5, y: -0.18, showarrow: false, font: { size: 10, color: '#5d6778' } }]
    }), plotConfig());
  }

  function renderAgeSexPyramidChart() {
    if (!canPlot('#ageSexPyramidChart')) return;
    const node = $('#ageSexPyramidChart');
    const records = chartCountries().slice(0, 4).map(ageSexPyramidRecord).filter(Boolean);
    if (!records.length) {
      visualEmpty('#ageSexPyramidChart', t('noData'));
      return;
    }
    if (records.length === 1) {
      if (window.Plotly?.purge) window.Plotly.purge(node);
      node.classList.remove('pyramid-compare-grid');
      node.innerHTML = '';
      renderAgeSexPyramidPlot(node, records[0], nicePyramidAxis(records[0].maxAbs), false);
      return;
    }
    if (window.Plotly?.purge) window.Plotly.purge(node);
    node.classList.add('pyramid-compare-grid');
    node.innerHTML = records.map((record, index) => `
      <section class="pyramid-compare-item" data-iso3="${escapeHtml(record.country.iso3)}">
        <h4>${flagHtml(record.country.iso2)} ${escapeHtml(countryName(record.country))}</h4>
        <div id="ageSexPyramidMini${index}" class="pyramid-compare-plot"></div>
      </section>
    `).join('');
    records.forEach((record, index) => renderAgeSexPyramidPlot($(`#ageSexPyramidMini${index}`), record, nicePyramidAxis(record.maxAbs), true));
  }

  function renderProgramProfileChart(country) {
    if (!canPlot('#programProfileChart')) return;
    const countries = chartCountries();
    const keys = Array.from(new Set(countries.flatMap((itemCountry) => Object.keys(itemCountry?.program?.profileScores || {}))));
    if (!keys.length) {
      visualEmpty('#programProfileChart', t('noData'));
      return;
    }
    const traces = countries.map((itemCountry, index) => {
      const scores = itemCountry?.program?.profileScores || {};
      const recommended = itemCountry?.program?.recommendedProfile || itemCountry?.recommended_program_profile;
      return {
      type: 'bar',
      orientation: 'h',
      name: countryName(itemCountry),
      y: keys.map((key) => compactProgramLabel(key)),
      x: keys.map((key) => clean(scores[key]) * 100),
      marker: { color: keys.map((key) => key === recommended && index === 0 ? '#e0aa24' : chartColor(itemCountry, index)) },
      customdata: keys.map((key) => i18nMap('programProfile', key)),
      hovertemplate: `${countryName(itemCountry)}<br>%{customdata}<br>${t('score')}: %{x:.1f}<br>${t('source')}: program_profile_ranking.csv<br>${t('year')}: ${state.data?.metadata?.baseYear || 2026}<extra></extra>`
      };
    });
    Plotly.react($('#programProfileChart'), traces, baseLayout({
      barmode: 'group',
      margin: { l: 118, r: 12, t: 6, b: 34 },
      xaxis: { range: [0, 100], automargin: true },
      yaxis: { automargin: true, tickfont: { size: 9 } },
      legend: { orientation: 'h', x: 0, y: -0.2, font: { size: 9 } }
    }), plotConfig());
    $('#programProfileChart').on('plotly_click', () => selectCountry(country.iso3));
  }

  function regionAverageNormalized(country, groupKey, keys) {
    const peers = (state.data?.countries || []).filter((row) => normalizeRegion(row.region) === normalizeRegion(country.region));
    return keys.map((key) => {
      const values = peers.map((row) => clean(state.data?.factorInputs?.[row.iso3]?.[groupKey]?.__normalized?.[key])).filter((value) => value !== null);
      return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
    });
  }

  function renderFeasibilityRadarChart(country) {
    if (!canPlot('#feasibilityRadarChart')) return;
    const keys = ['politicalStability', 'governmentEffectiveness', 'regulatoryQuality', 'ruleOfLaw', 'logisticsPerformanceIndex', 'internetUsersPct', 'urbanPopulationPct'];
    const labels = keys.map((key) => compactInputLabel(key));
    const traces = chartCountries().map((itemCountry, index) => {
      const normalized = state.data?.factorInputs?.[itemCountry?.iso3]?.feasibility?.__normalized || {};
      const values = keys.map((key) => clean(normalized[key]) ?? 0);
      return {
        type: 'bar',
        orientation: 'h',
        x: values.map((value) => value * 100),
        y: labels,
        name: countryName(itemCountry),
        marker: { color: chartColor(itemCountry, index) },
        hovertemplate: `%{y}<br>${t('normalizedValue')}: %{x:.1f}<br>${factorTraceText(itemCountry, 'I_FEAS')}<extra></extra>`
      };
    });
    Plotly.react($('#feasibilityRadarChart'), traces, baseLayout({
      barmode: 'group',
      margin: { l: 120, r: 12, t: 6, b: 34 },
      xaxis: { range: [0, 100], automargin: true },
      yaxis: { automargin: true, tickfont: { size: 9 } },
      legend: { orientation: 'h', x: 0, y: -0.2, font: { size: 9 } }
    }), plotConfig());
  }

  function renderDataTraceCard(country) {
    const node = null;
    if (!node) return;
    const allInputs = INDEX_KEYS.flatMap((key) => factorGroup(country, key)?.inputs || []);
    const directInputs = allInputs.filter((input) => String(input.scoring_role || '').includes('direct_factor_formula_component'));
    const traceable = allInputs.filter((input) => input.raw_value !== null && input.raw_value !== undefined && input.raw_value !== '' || input.normalized_value !== null && input.normalized_value !== undefined && input.normalized_value !== '');
    const coverage = allInputs.length ? traceable.length / allInputs.length : null;
    const observed = allInputs.filter((input) => /official|observed|reference/i.test(String(input.observation_status || ''))).length;
    const modelled = allInputs.filter((input) => /model/i.test(String(input.observation_status || ''))).length;
    const years = allInputs.map((input) => clean(input.year)).filter((year) => year !== null);
    const oldestYear = years.length ? Math.min(...years) : null;
    node.innerHTML = `
      <dl>
        <div><dt>${escapeHtml(t('country'))}</dt><dd>${escapeHtml(countryName(country))}</dd></div>
        <div><dt>${escapeHtml(state.lang === 'ru' ? 'Покрытие' : 'Coverage')}</dt><dd>${escapeHtml(coverage === null ? t('noData') : fmtPct(coverage, 0))}</dd></div>
        <div><dt>${escapeHtml(state.lang === 'ru' ? 'Observed' : 'Observed')}</dt><dd>${escapeHtml(fmt(observed, 0))}</dd></div>
        <div><dt>${escapeHtml(state.lang === 'ru' ? 'Modelled' : 'Modelled')}</dt><dd>${escapeHtml(fmt(modelled, 0))}</dd></div>
        <div><dt>${escapeHtml(state.lang === 'ru' ? 'Старый год' : 'Oldest year')}</dt><dd>${escapeHtml(oldestYear || t('noData'))}</dd></div>
        <div><dt>${escapeHtml(state.lang === 'ru' ? 'Прямые входы' : 'Direct inputs')}</dt><dd>${escapeHtml(`${directInputs.length}/${allInputs.length}`)}</dd></div>
      </dl>
      <button class="trace-open-button" type="button" data-open-evidence>${escapeHtml(state.lang === 'ru' ? 'Открыть доказательную таблицу' : 'Open evidence table')}</button>
    `;
    node.querySelector('[data-open-evidence]')?.addEventListener('click', () => {
      $('#factorTabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  function renderActiveFactorChart() {
    const country = selectedCountry();
    const node = $('#activeFactorChart');
    if (!country || !node) return;
    const group = factorGroup(country, state.activeFactorKey);
    const inputs = directFormulaInputs(group);
    ensureActiveMethodInput(group);
    if (!inputs.length) {
      node.innerHTML = `<div class="factor-empty">${escapeHtml(t('noDirectInputs'))}</div>`;
      return;
    }
    const activeWeight = activeWeights()[group.factor_key] || 0;
    const countries = formulaCountryRows();
    const countryRows = countries.map((itemCountry) => {
      const score = factorScore(itemCountry, group.factor_key);
      return `
        <article class="component-country-row" style="${factorStyleAttr(group.factor_key)}">
          <span>${flagHtml(itemCountry.iso2)} ${escapeHtml(countryName(itemCountry))}</span>
          <strong>${fmtScore(score * 100, 1)}</strong>
          <em>${escapeHtml(methodText('вклад', 'contribution'))}: ${fmtScore(score * activeWeight * 100, 2)}</em>
          <i><b style="width:${clamp(score * 100, 0, 100)}%"></b></i>
          <small>${escapeHtml(factorTraceText(itemCountry, group.factor_key).replaceAll('<br>', ' | '))}</small>
        </article>`;
    }).join('');
    node.innerHTML = `
      <section class="component-workbench" style="${factorStyleAttr(group.factor_key)}">
        <div class="component-workbench-head">
          <div>
            <span>${escapeHtml(methodText('Активный компонент', 'Active component'))}</span>
            <h3>${escapeHtml(factorSymbol(group.factor_key))} · ${escapeHtml(factorTitle(group.factor_key))}</h3>
            ${renderComponentEquation(group)}
          </div>
          <dl>
            <div><dt>${escapeHtml(t('weight'))}</dt><dd>${escapeHtml(fmtPct(activeWeight, 0))}</dd></div>
            <div><dt>${escapeHtml(t('score'))}</dt><dd>${fmtScore((clean(group.factor_score) || 0) * 100, 1)}</dd></div>
          </dl>
        </div>
        <div class="component-country-list">${countryRows}</div>
        ${renderMethodInputStrip(group)}
      </section>`;
    bindMethodInputButtons(node);
  }

  function renderExecutiveVisuals() {
    const country = selectedCountry();
    if (!country) return;
    $('#visualTraceNote').textContent = `${countryName(country)} / ${factorTitle(state.activeFactorKey)}`;
    renderSelectedFactorBars();
    renderIndexDecompositionChart(country);
    renderFinanceChart(country);
    renderPopulationYouthChart(country);
    renderAgeSexPyramidChart(country);
    renderProgramProfileChart(country);
    renderFeasibilityRadarChart(country);
    renderActiveFactorChart();
  }

  function renderSelected() {
    const country = selectedCountry();
    if (!country) return;
    const rank = state.rankByIso.get(country.iso3);
    $('#selectedFlag').innerHTML = flagHtml(country.iso2, 'country-flag-image');
    $('#selectedTitle').textContent = countryName(country);
    $('#kpiComposite').textContent = fmtScore(priority(country), 1);
    $('#kpiCompositeRank').textContent = rank ? t('rankOf', { rank, total: state.rankByIso.size }) : t('notRanked');
    $('#kpiMarket').textContent = fmtScore(factorScore(country, 'I_MARKET') * 100, 1);
    $('#kpiFit').textContent = fmtScore(factorScore(country, 'I_PROGRAM') * 100, 1);
    $('#kpiOperations').textContent = fmtScore(factorScore(country, 'I_FEAS') * 100, 1);
    $('#kpiFinance').textContent = fmtScore(factorScore(country, 'I_FIN') * 100, 1);
    const factualStatus = tableStatusLabel(country);
    $('#selectedBadges').innerHTML = [
      factualStatus ? `<span class="badge badge-${escapeHtml(statusCode(country))}">${escapeHtml(factualStatus)}</span>` : '',
      `<span class="badge">${escapeHtml(i18nMap('region', country.region))}</span>`,
      bool(country.eligible) ? `<span class="badge">${escapeHtml(t('eligible'))}</span>` : `<span class="badge">${escapeHtml(t('excluded'))}</span>`
    ].filter(Boolean).join('');
    $('#decisionSummary').textContent = decisionText(country);
    $('#countryDetailScore').textContent = `${fmtScore(priority(country), 1)} / 100`;
  }

  function decisionText(country) {
    const code = statusCode(country);
    const rec = country?.recommendation_category || country?.recommendationCategory;
    if (code === 'in_preparation') return t('decisionPreparationText');
    if (code === 'presence') return t('decisionPresenceText');
    if (code === 'unfriendly' || code === 'domestic' || code === 'special_territory' || !bool(country.eligible)) return t('decisionExcludedText');
    if (rec === 'A_open_priority') return t('decisionOpenText');
    if (rec === 'B_strategic_with_subsidy') return t('decisionPartnerText');
    return t('decisionMonitorText');
  }

  function renderRanking() {
    const rows = visibleCountries().slice(0, clean($('#topN')?.value) || 30);
    $('#rankingList').innerHTML = rows.length ? rows.map((country) => {
      const rank = state.rankByIso.get(country.iso3) || '';
      const compared = state.comparisonIso3s.has(country.iso3);
      const active = country.iso3 === state.selectedIso3;
      const rowClassNames = `${rowClass(country)}${active ? ' active-row' : ''}${compared ? ' compared-row' : ''}`.trim();
      const status = tableStatusLabel(country);
      return `<tr data-iso3="${escapeHtml(country.iso3)}" class="rank-row ${rowClassNames}" style="--country-color:${escapeHtml(countryVisualColor(country))};--status-color:${escapeHtml(statusVisualColor(country))}" aria-selected="${active || compared}">
        <td>${escapeHtml(rank || '-')}</td>
        <td><button type="button" class="table-country" data-iso3="${escapeHtml(country.iso3)}" aria-pressed="${active || compared}">${flagHtml(country.iso2)}<span>${escapeHtml(countryName(country))}${status ? `<em>${escapeHtml(status)}</em>` : ''}</span></button></td>
        <td>${fmtScore(priority(country), 1)}</td>
      </tr>`;
    }).join('') : `<tr><td colspan="3" class="empty-state">${escapeHtml(t('emptyRanking'))}</td></tr>`;
    $$('#rankingList .rank-row').forEach((row) => row.addEventListener('click', () => toggleComparison(row.dataset.iso3)));
  }

  function renderCompare() {
    const panel = $('#comparePanel');
    const grid = $('#compareGrid');
    const countries = comparisonCountries().slice(0, 4);
    if (!panel || !grid) return;
    if (!countries.length) {
      panel.classList.remove('open');
      grid.innerHTML = '';
      return;
    }
    panel.classList.add('open');
    const leaderScore = Math.max(...countries.map((itemCountry) => priority(itemCountry)));
    const leaderCountry = countries.find((itemCountry) => Math.abs(priority(itemCountry) - leaderScore) < 0.001) || countries[0];
    const scores = countries.map((itemCountry) => priority(itemCountry));
    const spread = Math.max(...scores) - Math.min(...scores);
    const summary = `
      <div class="compare-summary">
        <div><span>${escapeHtml(methodText('выбрано', 'selected'))}</span><strong>${escapeHtml(String(state.comparisonIso3s.size))}</strong></div>
        <div><span>${escapeHtml(methodText('лидер', 'leader'))}</span><strong>${flagHtml(leaderCountry.iso2)} ${escapeHtml(countryName(leaderCountry))}</strong></div>
        <div><span>${escapeHtml(methodText('разброс', 'spread'))}</span><strong>${escapeHtml(fmtScore(spread, 1))}</strong></div>
      </div>`;
    grid.innerHTML = summary + countries.map((itemCountry) => {
      const rows = indexContributionRows(itemCountry);
      const rawValues = rows.map((row) => Math.max(0, clean(row.contribution) ?? 0));
      const rawTotal = rawValues.reduce((sum, value) => sum + value, 0);
      const values = rawTotal > 0 ? rawValues : rows.map((row) => Math.max(0, clean(row.weight) ?? 0));
      const total = values.reduce((sum, value) => sum + value, 0) || rows.length || 1;
      let cursor = 0;
      const gradient = rows.map((row, index) => {
        const span = values[index] / total * 360;
        const start = cursor;
        cursor += span;
        return `var(--factor-${row.index}) ${start.toFixed(2)}deg ${cursor.toFixed(2)}deg`;
      }).join(', ');
      const factorBars = rows.map((row) => `
        <div class="compare-factor-row" style="${factorStyleAttr(row.key)}" title="${escapeHtml(`${row.title}: ${fmtScore(row.score * 100, 1)} / ${t('indexContributionLabel')}: ${fmtScore(row.contribution, 2)}`)}">
          <span>${escapeHtml(factorSymbol(row.key))}</span>
          <i><b style="width:${clamp(row.score * 100, 0, 100)}%"></b></i>
          <strong>${escapeHtml(fmtScore(row.score * 100, 0))}</strong>
        </div>`).join('');
      const strongest = [...rows].sort((left, right) => right.score - left.score)[0];
      const weakest = [...rows].sort((left, right) => left.score - right.score)[0];
      const score = priority(itemCountry);
      const delta = score - leaderScore;
      const deltaText = Math.abs(delta) < 0.05 ? '0.0' : `${delta > 0 ? '+' : ''}${fmtScore(delta, 1)}`;
      const deltaClass = delta < -0.05 ? 'negative' : 'positive';
      const rank = state.rankByIso.get(itemCountry.iso3);
      return `
        <article class="compare-profile-card compare-donut-card" data-iso3="${escapeHtml(itemCountry.iso3)}" style="--country-color:${escapeHtml(countryVisualColor(itemCountry))};--status-color:${escapeHtml(statusVisualColor(itemCountry))}">
          <div class="compare-donut" style="background: conic-gradient(${gradient})">
            <span><strong>${fmtScore(score, 1)}</strong><em>${escapeHtml(t('kpiCompositeShort'))}</em></span>
          </div>
          <div class="compare-card-main">
            <h4>${flagHtml(itemCountry.iso2)} <span>${escapeHtml(countryName(itemCountry))}</span></h4>
            <div class="compare-metrics">
              <div><span>${escapeHtml(t('rank'))}</span><strong>${escapeHtml(rank ? `#${rank}` : t('notRanked'))}</strong></div>
              <div><span>${escapeHtml(methodText('к лидеру', 'vs leader'))}</span><strong class="${deltaClass}">${escapeHtml(deltaText)}</strong></div>
              <div><span>${escapeHtml(methodText('лучший I', 'best I'))}</span><strong>${escapeHtml(strongest ? factorSymbol(strongest.key) : '-')}</strong></div>
            </div>
          </div>
          <div class="compare-factor-bars">${factorBars}</div>
          <div class="compare-insight-line" style="${weakest ? factorStyleAttr(weakest.key) : ''}">
            <span>${escapeHtml(methodText('Слабее всего', 'Weakest'))}: <strong>${escapeHtml(weakest ? `${factorSymbol(weakest.key)} · ${weakest.title}` : t('noData'))}</strong></span>
            <span>${escapeHtml(methodText('Сильнее всего', 'Strongest'))}: ${escapeHtml(strongest ? factorSymbol(strongest.key) : '-')}</span>
          </div>
        </article>`;
    }).join('');
  }

  function renderFactorTabs() {
    const country = selectedCountry();
    const groupMap = state.factorByIso.get(country?.iso3) || new Map();
    const groups = INDEX_KEYS.map((key) => groupMap.get(key)).filter(Boolean);
    if (!groups.some((group) => group.factor_key === state.activeFactorKey)) state.activeFactorKey = groups[0]?.factor_key || INDEX_KEYS[0];
    $('#factorTabs').innerHTML = groups.map((group) => {
      const active = group.factor_key === state.activeFactorKey;
      const title = factorTitle(group.factor_key);
      const index = factorIndex(group.factor_key);
      const weight = activeWeights()[group.factor_key] || 0;
      const score = clean(group.factor_score) || 0;
      return `<button class="factor-tab ${active ? 'active' : ''}" type="button" role="tab" aria-selected="${active}" aria-label="${escapeHtml(title)}" title="${escapeHtml(title)}" data-factor="${escapeHtml(group.factor_key)}" style="${factorStyleAttr(group.factor_key)}">
        <span><i class="factor-swatch factor-${index}"></i>${escapeHtml(factorSymbol(group.factor_key))}</span>
        <small>${escapeHtml(fmtPct(weight, 0))} · ${escapeHtml(fmtScore(score * 100, 1))}</small>
      </button>`;
    }).join('');
    $$('#factorTabs [data-factor]').forEach((button) => button.addEventListener('click', () => {
      state.activeFactorKey = button.dataset.factor;
      ensureActiveMethodInput(factorGroup(selectedCountry(), state.activeFactorKey));
      saveControlState();
      renderFactorTabs();
      renderExecutiveVisuals();
      renderMethodology();
      writeHash();
    }));
    renderFactorDetail(groups.find((group) => group.factor_key === state.activeFactorKey));
  }

  function renderFactorDetailWorkbench(group) {
    const panel = $('#factorDetailPanel');
    if (!panel) return;
    if (!group) {
      panel.innerHTML = '';
      return;
    }
    const title = factorTitle(group.factor_key);
    const country = selectedCountry();
    const countries = formulaCountryRows();
    const activeInput = ensureActiveMethodInput(group);
    const activeLine = activeInput ? lineageMeta(country, group.factor_key, activeInput) : null;
    const roleInputs = methodRoleInputs(group).filter((input) => !componentFormulaInputs(group).some((item) => item.key === input.key));
    const activeWeight = activeWeights()[group.factor_key] || 0;
    const rows = (group.inputs || []).map((input) => {
      const line = lineageMeta(country, group.factor_key, input);
      return `
      <tr>
        <td><code>${escapeHtml(line.official_indicator_code || t('noData'))}</code></td>
        <td>${escapeHtml(lineageTitle(line))}</td>
        <td>${escapeHtml(line.provider || t('noData'))}</td>
        <td>${line.official_url ? `<a href="${escapeHtml(line.official_url)}" target="_blank" rel="noopener">${escapeHtml(line.official_url)}</a>` : escapeHtml(t('noData'))}</td>
        <td>${escapeHtml(line.raw_file || t('noData'))}</td>
        <td>${escapeHtml(line.source_note || t('noData'))}</td>
        <td>${escapeHtml(line.source_name || t('noData'))}</td>
        <td>${escapeHtml(line.year || t('noData'))}</td>
        <td>${escapeHtml(line.unit || t('noData'))}</td>
        <td>${escapeHtml(formatInputValue(line.raw_value, line.unit || input.unit))}</td>
        <td>${escapeHtml(formatInputValue(line.normalized_value, '0-1'))}</td>
        <td title="${escapeHtml(line.weight_note || line.scoring_role || '')}">${escapeHtml(fmtPct(line.within_factor_weight, 0))}</td>
        <td>${escapeHtml(observationLabel(line.observation_status))}</td>
        <td>${escapeHtml(line.normalization_method || t('noData'))}</td>
      </tr>`;
    }).join('');
    const countryInputRows = countries.map((itemCountry) => {
      const itemGroup = factorGroup(itemCountry, group.factor_key);
      const itemInput = (itemGroup?.inputs || []).find((input) => input.key === state.activeMethodInputKey) || activeInput;
      const line = itemInput ? lineageMeta(itemCountry, group.factor_key, itemInput) : null;
      const normalized = clean(line?.normalized_value);
      const weight = clean(line?.within_factor_weight);
      const contribution = normalized !== null && weight !== null ? normalized * weight * 100 : null;
      return `
        <article class="method-country-calc" style="--country-color:${escapeHtml(countryVisualColor(itemCountry))};${factorStyleAttr(group.factor_key)}">
          <span>${flagHtml(itemCountry.iso2)} ${escapeHtml(countryName(itemCountry))}</span>
          <strong>${escapeHtml(normalized === null ? t('noData') : fmtScore(normalized * 100, 1))}</strong>
          <small>${escapeHtml(fmtPct(weight, 0))} × ${escapeHtml(normalized === null ? t('noData') : mathNumber(normalized, 3))}${contribution === null ? '' : ` = ${escapeHtml(fmtScore(contribution, 2))}`}</small>
        </article>`;
    }).join('');
    const sourceFields = activeLine ? [
      [state.lang === 'ru' ? 'Код индикатора' : 'Indicator code', `<code>${escapeHtml(activeLine.official_indicator_code || t('noData'))}</code>`],
      [state.lang === 'ru' ? 'Название' : 'Name', escapeHtml(lineageTitle(activeLine))],
      [state.lang === 'ru' ? 'Official name EN' : 'Official name EN', escapeHtml(activeLine.official_indicator_name_en || t('noData'))],
      [state.lang === 'ru' ? 'База / провайдер' : 'Database / provider', escapeHtml(activeLine.provider || t('noData'))],
      [state.lang === 'ru' ? 'URL источника' : 'Source URL', activeLine.official_url ? `<a href="${escapeHtml(activeLine.official_url)}" target="_blank" rel="noopener">${escapeHtml(activeLine.official_url)}</a>` : escapeHtml(t('noData'))],
      [t('year'), escapeHtml(activeLine.year || t('noData'))],
      [t('rawValue'), escapeHtml(formatInputValue(activeLine.raw_value, activeLine.unit))],
      [t('normalizedValue'), escapeHtml(formatInputValue(activeLine.normalized_value, '0-1'))],
      [t('weight'), escapeHtml(fmtPct(activeLine.within_factor_weight, 0))],
      [t('observationStatus'), escapeHtml(observationLabel(activeLine.observation_status))],
      [state.lang === 'ru' ? 'Метод нормировки' : 'Normalization', escapeHtml(activeLine.normalization_method || t('noData'))],
      [state.lang === 'ru' ? 'Файл данных' : 'Raw file', escapeHtml(activeLine.raw_file || t('noData'))],
      [state.lang === 'ru' ? 'Запись manifest' : 'Manifest code', escapeHtml(activeLine.source_manifest_code || t('noData'))],
      [state.lang === 'ru' ? 'Примечание источника' : 'Source note', escapeHtml(activeLine.source_note || t('noData'))]
    ] : [];
    const roleCards = roleInputs.map((input) => {
      const line = lineageMeta(country, group.factor_key, input);
      return `
        <article class="method-role-card compact-role" style="${factorStyleAttr(group.factor_key)}">
          <span>${escapeHtml(lineageTitle(line))}</span>
          <strong>${escapeHtml(line.scoring_role || line.weight_note || t('observationStatus'))}</strong>
          <small>${escapeHtml(t('rawValue'))}: ${escapeHtml(formatInputValue(line.raw_value, line.unit || input.unit))} · ${escapeHtml(t('source'))}: ${escapeHtml(line.provider || line.source_name || t('noData'))}</small>
        </article>`;
    }).join('');
    panel.innerHTML = `
      <div class="factor-detail-summary" style="${factorStyleAttr(group.factor_key)}">
        <div class="factor-detail-title">
          <h3>${escapeHtml(factorSymbol(group.factor_key))} · ${escapeHtml(title)}</h3>
          <span>${escapeHtml(methodText('значение компонента', 'component value'))}: ${fmtScore((clean(group.factor_score) || 0) * 100, 1)}</span>
        </div>
        <dl>
          <div><dt>${escapeHtml(t('score'))}</dt><dd>${fmtScore((clean(group.factor_score) || 0) * 100, 1)}</dd></div>
          <div><dt>${escapeHtml(t('weight'))}</dt><dd>${fmtPct(activeWeight, 0)}</dd></div>
          <div><dt>${escapeHtml(methodText('Элемент формулы', 'Formula element'))}</dt><dd>${escapeHtml(activeInput ? formulaInputLabel(group.factor_key, activeInput) : t('noData'))}</dd></div>
        </dl>
        <section class="method-source-panel">
          <div class="method-source-head">
            <span>${escapeHtml(methodText('Источник выбранного элемента', 'Selected element source'))}</span>
            ${activeLine?.official_url ? `<a href="${escapeHtml(activeLine.official_url)}" target="_blank" rel="noopener">${escapeHtml(state.lang === 'ru' ? 'Открыть источник' : 'Open source')}</a>` : ''}
          </div>
          ${renderMethodInputStrip(group)}
          <div class="source-drilldown">
            <article class="source-level formula-node">
              <strong>${escapeHtml(methodText('1. Элемент формулы', '1. Formula element'))}</strong>
              <p><code>${escapeHtml(activeInput ? formulaInputLabel(group.factor_key, activeInput) : t('noData'))}</code> · ${escapeHtml(activeLine ? lineageTitle(activeLine) : t('noData'))}</p>
            </article>
            <article class="source-level calculation-node">
              <strong>${escapeHtml(methodText('2. Расчет по выбранным странам', '2. Selected-country calculation'))}</strong>
              <div class="method-country-calc-grid">${countryInputRows}</div>
            </article>
            <article class="source-level source-node">
              <strong>${escapeHtml(methodText('3. Нижний уровень источника', '3. Source record'))}</strong>
              <dl>${sourceFields.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${value}</dd></div>`).join('')}</dl>
            </article>
          </div>
        </section>
        ${roleCards ? `<div class="method-role-grid">${roleCards}</div>` : ''}
        <button class="secondary-download factor-csv-button" type="button" data-factor-csv="${escapeHtml(group.factor_key)}">${escapeHtml(state.lang === 'ru' ? 'CSV по фактору' : 'Factor CSV')}</button>
      </div>
      <details class="evidence-table-drawer">
        <summary>${escapeHtml(methodText('Паспорт данных', 'Data passport'))}</summary>
        <table class="mini-table factor-input-table">
          <thead><tr><th>official_indicator_code</th><th>${escapeHtml(state.lang === 'ru' ? 'official_indicator_name_ru' : 'official_indicator_name_en')}</th><th>provider</th><th>official_url</th><th>raw_file</th><th>source_note</th><th>source_name</th><th>year</th><th>unit</th><th>raw_value</th><th>normalized_value</th><th>within_factor_weight</th><th>observation_status</th><th>normalization_method</th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </details>`;
    panel.querySelector('[data-factor-csv]')?.addEventListener('click', () => downloadFactorCsv(group));
    bindMethodInputButtons(panel);
  }

  function renderFactorDetail(group) {
    renderFactorDetailWorkbench(group);
    return;
    if (!group) {
      $('#factorDetailPanel').innerHTML = '';
      return;
    }
    const title = factorTitle(group.factor_key);
    const formula = factorMethodText(group.factor_key);
    const rows = (group.inputs || []).map((input) => {
      const meta = branchIndicatorMeta(group.factor_key, input.key);
      const indicatorCode = meta.official_indicator_code || meta.indicator_code || meta.input_key || input.key || 'not_applicable_modelled_component';
      const officialName = localizedDictionaryName(meta, inputLabel(input.key));
      const unit = meta.unit || input.unit || '';
      const sourceName = meta.source_name || sourceLabel(input.source_key);
      const withinWeight = meta.within_factor_weight ?? input.input_weight;
      return `
      <tr>
        <td><code>${escapeHtml(indicatorCode)}</code></td>
        <td>${escapeHtml(officialName)}</td>
        <td>${escapeHtml(sourceName)}</td>
        <td>${escapeHtml(input.year || t('noData'))}</td>
        <td>${escapeHtml(unit || t('noData'))}</td>
        <td>${escapeHtml(formatInputValue(input.raw_value, unit || input.unit))}</td>
        <td>${escapeHtml(formatInputValue(input.normalized_value, '0-1'))}</td>
        <td title="${escapeHtml(input.weight_note || input.scoring_role || '')}">${escapeHtml(fmtPct(withinWeight, 0))}</td>
        <td>${escapeHtml(observationLabel(input.observation_status))}</td>
        <td>${escapeHtml(input.normalization_method || t('noData'))}</td>
      </tr>`;
    }).join('');
    $('#factorDetailPanel').innerHTML = `
      <div class="factor-detail-summary">
        <h3>${escapeHtml(title)}</h3>
        <details class="methodology-accordion" open><summary>${escapeHtml(t('formula'))}</summary><p>${escapeHtml(formula)}</p></details>
        <p class="factor-explanation">${escapeHtml(state.lang === 'ru' ? 'График выше показывает только прямые входы формулы; контекстные и справочные строки раскрываются ниже для трассировки источников.' : 'The chart above shows only direct formula inputs; contextual rows remain in the evidence table for lineage.')}</p>
        <dl>
          <div><dt>${escapeHtml(t('score'))}</dt><dd>${fmtScore((clean(group.factor_score) || 0) * 100, 1)}</dd></div>
          <div><dt>${escapeHtml(t('weight'))}</dt><dd>${fmtPct(activeWeights()[group.factor_key], 0)}</dd></div>
          <div><dt>${escapeHtml(t('formula'))}</dt><dd>${escapeHtml(methodologyFormula())}</dd></div>
        </dl>
        <button class="secondary-download factor-csv-button" type="button" data-factor-csv="${escapeHtml(group.factor_key)}">${escapeHtml(state.lang === 'ru' ? 'CSV по фактору' : 'Factor CSV')}</button>
      </div>
      <table class="mini-table factor-input-table">
        <thead><tr><th>official_indicator_code</th><th>official_indicator_name_ru</th><th>source_name</th><th>year</th><th>unit</th><th>raw_value</th><th>normalized_value</th><th>within_factor_weight</th><th>observation_status</th><th>normalization_method</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
    $('#factorDetailPanel [data-factor-csv]')?.addEventListener('click', () => downloadFactorCsv(group));
  }

  function sourceLabel(key) {
    const source = (state.data.sources || []).find((row) => row.source_key === key || row.source_id === key || row.id === key);
    if (!source) return key || '-';
    return state.lang === 'ru' ? source.provider_ru || source.provider || source.provider_en || key : source.provider_en || source.provider || source.provider_ru || key;
  }

  function observationLabel(value) {
    const key = `observation.${value || 'modelled'}`;
    const label = t(key);
    return label === key ? value || '-' : label;
  }

  function formatInputValue(value, unit) {
    if (value && typeof value === 'object') {
      return Object.entries(value).map(([key, item]) => `${i18nMap('programProfile', key)}: ${formatInputValue(item, '0-1')}`).join('; ');
    }
    if (typeof value === 'string') {
      if (value.includes('_')) return i18nMap(value.includes('branch') ? 'format' : 'programProfile', value);
      return value;
    }
    if (typeof value === 'boolean') return value ? t('yes') : t('no');
    const n = clean(value);
    if (n === null) return t('noData');
    if (unit === 'USD') return fmtMoney(n);
    if (unit === '%') return `${fmt(n, 1)}%`;
    if (unit === '0-1') return fmtScore(n * 100, 1);
    if (unit === 'flag') return n ? t('yes') : t('no');
    if (unit === 'people' || unit === 'students') return fmt(n, 0);
    return fmt(n, 2);
  }

  function renderMethodology() {
    const node = $('#methodologyText');
    if (!node) return;
    const countries = formulaCountryRows();
    const countryRows = countries.map(renderCountryEquation).join('');
    node.innerHTML = `
      <section class="index-formula-workbench">
        <div class="workbench-formula-head">
          <div>
            <span>${escapeHtml(methodText('Методика расчета', 'Calculation method'))}</span>
            <h3>${escapeHtml(t('formulaTitle'))}</h3>
          </div>
          <strong>${escapeHtml(methodText('ε', 'epsilon'))} = ${escapeHtml(mathNumber(state.data?.methodology?.normalization?.epsilon ?? SCORE_EPSILON, 2))}</strong>
        </div>
        ${renderIndexEquation()}
        <div class="country-equation-list">${countryRows}</div>
      </section>`;
    bindMethodFactorButtons(node);
    const sourcePassport = $('#sourcePassport');
    if (sourcePassport) {
      sourcePassport.innerHTML = (state.data.sources || []).slice(0, 8).map((source) => `
        <article class="source-pill">
          <strong>${escapeHtml(state.lang === 'ru' ? source.provider_ru || source.provider || source.provider_en : source.provider_en || source.provider || source.provider_ru)}</strong>
          <span>${escapeHtml(state.lang === 'ru' ? source.used_for_ru || source.usedFor || source.used_for_en || source.description : source.used_for_en || source.usedFor || source.used_for_ru || source.description)}</span>
        </article>`).join('');
    }
    const downloads = [
      ['factor_inputs_long.csv', t('downloadFactorInputs')],
      ['factor_inputs_long.json', t('downloadFactorInputsJson')],
      ['student_attraction.csv', t('downloadStudentAttraction')]
    ];
    const downloadPanel = $('#downloadPanel');
    if (downloadPanel) {
      downloadPanel.innerHTML = `<tbody>${downloads.map(([file, label]) => `
        <tr><th>${escapeHtml(label)}</th><td><a class="download-icon" href="data/${file}" download="MGIMO_${file}" aria-label="${escapeHtml(t('downloadFile', { name: label }))}">DL</a></td></tr>`).join('')}</tbody>`;
    }
  }

  function methodologyFormula() {
    const eps = state.data?.methodology?.normalization?.epsilon ?? SCORE_EPSILON;
    return state.lang === 'ru'
      ? `Индекс = 100 × exp(Σ w_i × ln(${eps} + I_i)); веса суммируются до 100%, каждая вкладка использует подготовленный фактор I_i.`
      : `Index = 100 × exp(Σ w_i × ln(${eps} + I_i)); weights sum to 100%, and each tab uses the prepared factor I_i.`;
  }

  function renderAll() {
    refreshRanks();
    applyI18n();
    $$('.category-chip').forEach((chip) => chip.classList.toggle('active', chip.dataset.category === state.category));
    populateMetricSelect();
    populateRegionSelect();
    renderHeader();
    renderWeights();
    renderMap();
    renderSelected();
    renderRanking();
    renderCompare();
    renderFactorTabs();
    renderExecutiveVisuals();
    renderMethodology();
    writeHash();
    queueLayoutRefresh();
  }

  function saveAndRender() {
    saveControlState();
    renderAll();
  }

  function selectCountry(iso3) {
    if (!iso3 || !state.countryByIso.has(iso3)) return;
    state.selectedIso3 = iso3;
    saveAndRender();
  }

  function resetControls() {
    state.metric = 'priority';
    state.category = 'all';
    state.region = 'all';
    state.weightMode = 'line';
    state.weightEditorOpen = false;
    state.weights = { ...state.weightsDefault };
    state.comparisonIso3s.clear();
    localStorage.removeItem('mgimo_comparison_iso3s');
    localStorage.removeItem('mgimo_compare_iso3');
    $('#searchInput').value = '';
    $('#topN').value = '30';
    saveAndRender();
  }

  function restoreHashState() {
    if (!state.data) return;
    applyHashState();
    if (!state.selectedIso3) {
      state.selectedIso3 = state.countryByIso.has(DEFAULT_SELECTED_ISO) ? DEFAULT_SELECTED_ISO : rankedCountries()[0]?.iso3;
    }
    renderAll();
  }

  function downloadBlob(content, filename, type) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function csvEscape(value) {
    const text = String(value ?? '');
    return /[",\n;]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  }

  function downloadRanking() {
    const header = ['rank', 'iso3', 'country', 'status', 'priority', ...INDEX_KEYS];
    const rows = visibleCountries().map((country) => [
      state.rankByIso.get(country.iso3) || '',
      country.iso3,
      countryName(country),
      statusLabel(country),
      fmtScore(priority(country), 2),
      ...INDEX_KEYS.map((key) => fmtScore(factorScore(country, key) * 100, 2))
    ]);
    downloadBlob([header.join(','), ...rows.map((row) => row.map(csvEscape).join(','))].join('\n'), `MGIMO_country_priorities_${state.lang}.csv`, 'text/csv;charset=utf-8');
  }

  function downloadFactorCsv(group) {
    if (!group) return;
    const country = selectedCountry();
    const header = ['official_indicator_code', 'official_indicator_name_ru', 'provider', 'official_url', 'raw_file', 'source_note', 'source_name', 'year', 'unit', 'raw_value', 'normalized_value', 'within_factor_weight', 'observation_status', 'normalization_method'];
    const rows = (group.inputs || []).map((input) => {
      const line = lineageMeta(country, group.factor_key, input);
      return [
        line.official_indicator_code || '',
        line.official_indicator_name_ru || lineageTitle(line),
        line.provider || '',
        line.official_url || '',
        line.raw_file || '',
        line.source_note || '',
        line.source_name || '',
        line.year || '',
        line.unit || '',
        formatInputValue(line.raw_value, line.unit || input.unit),
        formatInputValue(line.normalized_value, '0-1'),
        fmtPct(line.within_factor_weight, 0),
        observationLabel(line.observation_status),
        line.normalization_method || ''
      ];
    });
    downloadBlob([header.join(','), ...rows.map((row) => row.map(csvEscape).join(','))].join('\n'), `${group.iso3}_${group.factor_key}_evidence_${state.lang}.csv`, 'text/csv;charset=utf-8');
  }

  function downloadCountryJson() {
    const country = selectedCountry();
    const payload = {
      country: countryName(country),
      iso3: country.iso3,
      status: statusLabel(country),
      priority: priority(country),
      weights: activeWeights(),
      factors: Object.fromEntries(INDEX_KEYS.map((key) => [factorTitle(key), factorScore(country, key)]))
    };
    downloadBlob(JSON.stringify(payload, null, 2), `${country.iso3}_country_summary_${state.lang}.json`, 'application/json;charset=utf-8');
  }

  async function copyLink(event) {
    writeHash();
    const statusNode = event?.currentTarget?.id === 'copyViewLink' ? $('#copyViewStatus') : $('#copyStatus');
    try {
      await navigator.clipboard.writeText(location.href);
      if (statusNode) statusNode.textContent = t('copyDone');
    } catch {
      if (statusNode) statusNode.textContent = location.href;
    }
  }

  function wireControls() {
    $('#metricSelect').addEventListener('change', (event) => { state.metric = event.target.value; saveAndRender(); });
    $('#regionSelect').addEventListener('change', (event) => { state.region = event.target.value; saveAndRender(); });
    $('#searchInput').addEventListener('input', () => renderAll());
    $('#topN').addEventListener('change', () => {
      renderRanking();
    });
    $('#langRu').addEventListener('click', () => { state.lang = 'ru'; saveAndRender(); });
    $('#langEn').addEventListener('click', () => { state.lang = 'en'; saveAndRender(); });
    $$('.category-chip').forEach((chip) => chip.addEventListener('click', () => {
      state.category = chip.dataset.category;
      $$('.category-chip').forEach((item) => item.classList.toggle('active', item === chip));
      saveAndRender();
    }));
    $$('#weightsPanel [data-weight-mode]').forEach((button) => button.addEventListener('click', () => {
      state.weightMode = 'line';
      state.weightEditorOpen = button.dataset.weightMode === 'sliders';
      saveAndRender();
    }));
    $('#closeWeights')?.addEventListener('click', () => {
      state.weightMode = 'line';
      state.weightEditorOpen = false;
      saveAndRender();
    });
    $('#weightEditorBackdrop')?.addEventListener('click', () => {
      state.weightMode = 'line';
      state.weightEditorOpen = false;
      saveAndRender();
    });
    $('#resetWeights').addEventListener('click', () => {
      state.weights = { ...state.weightsDefault };
      saveAndRender();
    });
    $('#resetBtn').addEventListener('click', resetControls);
    $('#downloadRanking').addEventListener('click', downloadRanking);
    $('#downloadCountryJson').addEventListener('click', downloadCountryJson);
    $('#copyViewLink')?.addEventListener('click', copyLink);
    $('#copyWeightsLink')?.addEventListener('click', copyLink);
  }

  async function init() {
    try {
      await loadLocales();
      const [data, geo, factorTraceRows, branchDictionaryRows, factorSourceLineageRows] = await Promise.all([
        fetch(DATA_URL).then((response) => {
          if (!response.ok) throw new Error(`${DATA_URL}: ${response.status}`);
          return response.json();
        }),
        fetch(GEO_URL).then((response) => {
          if (!response.ok) throw new Error(`${GEO_URL}: ${response.status}`);
          return response.json();
        }),
        fetch(FACTOR_TRACE_URL).then((response) => {
          if (!response.ok) throw new Error(`${FACTOR_TRACE_URL}: ${response.status}`);
          return response.json();
        }),
        fetch(BRANCH_DICTIONARY_URL).then((response) => {
          if (!response.ok) return [];
          return response.json();
        }),
        fetch(FACTOR_LINEAGE_URL).then((response) => {
          if (!response.ok) throw new Error(`${FACTOR_LINEAGE_URL}: ${response.status}`);
          return response.json();
        })
      ]);
      state.data = data;
      state.geo = geo;
      state.factorTraceRows = Array.isArray(factorTraceRows) ? factorTraceRows : [];
      state.branchDictionaryRows = Array.isArray(branchDictionaryRows) ? branchDictionaryRows : [];
      state.factorSourceLineageRows = Array.isArray(factorSourceLineageRows) ? factorSourceLineageRows : [];
      buildGeoNameIndex();
      buildIndexes();
      state.comparisonIso3s = parseComparisonIso3s(localStorage.getItem('mgimo_comparison_iso3s'));
      state.weights = decodedWeights(localStorage.getItem('mgimo_weights')) || state.weights;
      applyHashState();
      if (!state.selectedIso3) state.selectedIso3 = state.countryByIso.has(DEFAULT_SELECTED_ISO) ? DEFAULT_SELECTED_ISO : rankedCountries()[0]?.iso3;
      initMap();
      wireControls();
      window.addEventListener('resize', queueLayoutRefresh);
      window.addEventListener('hashchange', restoreHashState);
      renderAll();
      $('#loadStatus').textContent = t('statusReady');
      $('#loadStatus').classList.add('ready');
      window.MGIMO_DASHBOARD_STATE = state;
    } catch (error) {
      console.error(error);
      $('#loadStatus').textContent = t('statusError');
      $('#loadStatus').classList.add('error');
    }
  }

  document.addEventListener('DOMContentLoaded', init);
})();
