const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const READY_RE = /Data loaded|Данные загружены/i;
const PREPARATION_RE = /in preparation|В подготовке/i;
const VISUAL_DIR = path.resolve(__dirname, '..', 'artifacts', 'visual_qa');
const INDEX_KEYS = ['I_MARKET', 'I_PROGRAM', 'I_RUSCOMP', 'I_ECO', 'I_FIN', 'I_FEAS', 'I_HRSTRAT'];
const SAI_UIS_KEY = 'A_OUTBOUND_MOBILITY_UIS';
const OLD_SAI_BASE = ['A_MOBILITY', '_READINESS'].join('');
const OLD_SAI_KEY = `${OLD_SAI_BASE}_${['PRO', 'XY'].join('')}`;
const EXECUTIVE_COMPARE_CHARTS = [
  '#indexDecompositionChart',
  '#financeChart',
  '#populationYouthChart',
  '#programProfileChart',
  '#feasibilityRadarChart'
];

function term(...parts) {
  return parts.join('');
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

const BAD_VISIBLE_RE = new RegExp(
  `\\b(?:${[
    term('sce', 'nario'),
    term('base', 'line'),
    term('soft', '_power'),
    term('comm', 'ercial'),
    term('risk', '_averse'),
    'undefined',
    'NaN',
    'Infinity',
    '[object Object]'
  ].map(escapeRegExp).join('|')})\\b|сценар|Качество данных`,
  'i'
);
const BAD_PAYLOAD_RE = new RegExp(
  `\\b(?:${[
    term('sce', 'nario'),
    term('base', 'line'),
    term('soft', '_power'),
    term('comm', 'ercial'),
    term('risk', '_averse'),
    term('snap', 'shot'),
    term('live', '_final'),
    term('final', '_snapshot'),
    term('source', '_manifest'),
    term('run', '_metadata')
  ].map(escapeRegExp).join('|')})\\b`,
  'i'
);

const pageErrors = new WeakMap();

function isFiniteNumber(value) {
  return value !== null && value !== '' && Number.isFinite(Number(value));
}

function priorityScore(country, weights, epsilon = 0.05) {
  let acc = 0;
  let weightSum = 0;
  for (const [key, weight] of Object.entries(weights)) {
    const value = country.factorScores?.[key] ?? country[key];
    if (!isFiniteNumber(value)) continue;
    const score = Math.max(0, Math.min(1, Number(value)));
    acc += Number(weight) * Math.log(epsilon + score);
    weightSum += Number(weight);
  }
  return weightSum > 0 ? 100 * Math.exp(acc / weightSum) : null;
}

function collectForbidden(value, prefix = '$', hits = []) {
  if (hits.length > 40) return hits;
  if (Array.isArray(value)) {
    value.forEach((child, index) => collectForbidden(child, `${prefix}[${index}]`, hits));
  } else if (value && typeof value === 'object') {
    Object.entries(value).forEach(([key, child]) => {
      const childPath = `${prefix}.${key}`;
      if (BAD_PAYLOAD_RE.test(key)) hits.push(childPath);
      collectForbidden(child, childPath, hits);
    });
  } else if (typeof value === 'string' && BAD_PAYLOAD_RE.test(value)) {
    hits.push(prefix);
  }
  return hits;
}

async function visibleText(page) {
  return page.locator('body').evaluate(body => {
    const out = [];
    const walker = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const node = walker.currentNode;
      const el = node.parentElement;
      if (!el || ['SCRIPT', 'STYLE', 'NOSCRIPT', 'OPTION'].includes(el.tagName)) continue;
      const style = getComputedStyle(el);
      if (style.display !== 'none' && style.visibility !== 'hidden') {
        const text = node.textContent.trim();
        if (text) out.push(text);
      }
    }
    return out.join('\n');
  });
}

async function expectCleanVisibleText(page) {
  expect(await visibleText(page)).not.toMatch(BAD_VISIBLE_RE);
}

async function plotlyVisibleText(page) {
  return page.locator('.js-plotly-plot').evaluateAll(plots => plots.flatMap(plot =>
    Array.from(plot.querySelectorAll('.gtitle, .xtitle, .ytitle, .legendtext, .xtick text, .ytick text, .angularaxis text, .polarsublayer text'))
      .map(node => (node.textContent || '').trim())
      .filter(Boolean)
  ).join('\n'));
}

async function expectHtmlVisual(page, selector) {
  const visual = page.locator(selector);
  await expect(visual).toBeVisible();
  await expect.poll(async () => visual.evaluate(el => el.childElementCount > 0 && (el.textContent || '').trim().length > 0)).toBe(true);
  const state = await visual.evaluate(el => ({
    text: (el.textContent || '').trim(),
    children: el.childElementCount
  }));
  expect(state.children, selector).toBeGreaterThan(0);
  expect(state.text, selector).not.toMatch(BAD_VISIBLE_RE);
}

async function expectPlotlyVisual(page, selector) {
  const visual = page.locator(selector);
  await expect(visual).toBeVisible();
  await expect.poll(async () => visual.evaluate(el => {
    const plot = el.classList.contains('js-plotly-plot') ? el : el.querySelector('.js-plotly-plot');
    const traceCount = (plot?._fullData?.length || plot?.data?.length || 0);
    const hasSvgPixels = Array.from(el.querySelectorAll('svg')).some(svg => {
      const box = svg.getBoundingClientRect();
      return box.width > 24 && box.height > 24 && Boolean(svg.querySelector('path, rect, circle, text, line, polygon'));
    });
    const hasCanvasPixels = Array.from(el.querySelectorAll('canvas')).some(canvas => canvas.width > 24 && canvas.height > 24);
    return traceCount > 0 && (hasSvgPixels || hasCanvasPixels);
  })).toBe(true);
  const state = await visual.evaluate(el => {
    const plot = el.classList.contains('js-plotly-plot') ? el : el.querySelector('.js-plotly-plot');
    return {
      traceCount: (plot?._fullData?.length || plot?.data?.length || 0),
      text: (el.textContent || '').trim()
    };
  });
  expect(state.traceCount, selector).toBeGreaterThan(0);
  expect(state.text, selector).not.toMatch(BAD_VISIBLE_RE);
}

async function expectBranchVisuals(page) {
  const htmlVisuals = ['#rankingTable', '#selectedFactorBars', '#activeFactorChart'];
  const plotlyVisuals = [
    '#indexDecompositionChart',
    '#financeChart',
    '#populationYouthChart',
    '#ageSexPyramidChart',
    '#programProfileChart',
    '#feasibilityRadarChart'
  ];
  for (const selector of htmlVisuals) await expectHtmlVisual(page, selector);
  for (const selector of plotlyVisuals) await expectPlotlyVisual(page, selector);
  await expect(page.locator('#dataTraceCard')).toHaveCount(0);
  expect(htmlVisuals.length + plotlyVisuals.length).toBeGreaterThanOrEqual(8);
  await expectCleanVisibleText(page);
}

async function expectStudentVisuals(page) {
  const plotlyVisuals = [
    '#studentSaiDecomposition',
    '#studentYouthGrowthScatter',
    '#studentMobilityChart',
    '#studentRegionTreemap',
    '#studentTopAfricaPanel',
    '#studentPopulationYouthChart',
    '#studentAgeSexPyramidChart'
  ];
  for (const selector of plotlyVisuals) await expectPlotlyVisual(page, selector);
  expect(plotlyVisuals.length).toBeGreaterThanOrEqual(7);
  await expectCleanVisibleText(page);
}

async function loadDashboard(page, hash = '') {
  await page.goto(`/${hash}`);
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#loadStatus')).toContainText(READY_RE);
  await expect(page.locator('#map')).toBeVisible();
  expect(pageErrors.get(page) || []).toEqual([]);
}

async function loadStudents(page) {
  await page.goto('/students.html');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#loadStatus')).toContainText(READY_RE);
  await expect(page.locator('#studentsDashboard')).toBeVisible();
  await expect(page.locator('#studentMap')).toBeVisible();
  expect(pageErrors.get(page) || []).toEqual([]);
}

async function dashboardPayload(page) {
  return (await page.request.get('/data/mgimo_dashboard_data.json')).json();
}

async function sliderWeights(page) {
  return page.locator('.weight-slider').evaluateAll(inputs => inputs.map(input => Number(input.value) / 100));
}

async function switchToSlidersAndChange(page) {
  if (!await page.locator('#weightEditorPanel').isVisible()) {
    await page.locator('#weightModeSliders').click();
  }
  const scoreBefore = await page.locator('#kpiComposite').innerText();
  const first = page.locator('.weight-slider').first();
  const current = Number(await first.evaluate(input => input.value));
  const next = String(Math.min(70, current + 12));
  if (await first.isVisible()) {
    await first.fill(next);
    await first.dispatchEvent('input');
    await first.dispatchEvent('change');
  } else {
    await first.evaluate((input, value) => {
      input.value = value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }, next);
  }
  await expect(page).toHaveURL(/weights=/);
  await expect.poll(async () => page.locator('#kpiComposite').innerText()).not.toBe(scoreBefore);
}

async function emitPlotlyClick(page, selector, point = {}) {
  await expectPlotlyVisual(page, selector);
  await page.locator(selector).evaluate((node, eventPoint) => {
    if (typeof node.emit === 'function') {
      node.emit('plotly_click', { points: [eventPoint] });
    }
  }, point);
}

async function plotTraceCount(page, selector) {
  return page.locator(selector).evaluate(el => {
    const plot = el.classList.contains('js-plotly-plot') ? el : el.querySelector('.js-plotly-plot');
    return plot?._fullData?.length || plot?.data?.length || 0;
  });
}

async function executiveTraceCounts(page) {
  const entries = [];
  for (const selector of EXECUTIVE_COMPARE_CHARTS) {
    entries.push([selector, await plotTraceCount(page, selector)]);
  }
  return Object.fromEntries(entries);
}

async function expectNoHorizontalOverflow(page) {
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(2);
}

test.beforeEach(async ({ page }) => {
  const errors = [];
  pageErrors.set(page, errors);
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', error => errors.push(error.message));
});

test.afterEach(async ({ page }) => {
  expect(pageErrors.get(page) || []).toEqual([]);
});

test('payload v2 has no scenarios and formula matches prepared factor scores', async ({ page }) => {
  await loadDashboard(page);
  const canonicalText = await (await page.request.get('/data/mgimo_dashboard_data.json')).text();
  const aliasText = await (await page.request.get('/data/dashboard_payload.json')).text();
  expect(aliasText).toBe(canonicalText);

  const data = JSON.parse(canonicalText);
  expect(data.schema_version).toBe('2.0.0');
  expect(data).not.toHaveProperty(term('scenario', 'Weights'));
  expect(collectForbidden(data)).toEqual([]);
  for (const key of ['countries', 'factorInputs', 'weightsDefault', 'eligibility', 'demographySeries', 'ageSexPyramid', 'branchMarkers', 'studentAttraction', 'studentFlowsObserved', 'studentFlowsModelled', 'sources', 'methodology', 'metadata']) {
    expect(data).toHaveProperty(key);
  }

  const totalWeight = Object.values(data.weightsDefault).reduce((sum, value) => sum + Number(value), 0);
  expect(totalWeight).toBeCloseTo(1, 10);
  for (const country of data.countries.filter(row => row.eligible).slice(0, 30)) {
    expect(priorityScore(country, data.weightsDefault), country.iso3).toBeCloseTo(Number(country.priorityScore), 6);
  }
});

test('RU and EN shells are clean and scenario-free', async ({ page }) => {
  await loadDashboard(page);
  await expect(page.locator('html')).toHaveAttribute('lang', 'ru');
  await expect(page.locator('#dataDate, .asof, #executiveDecisionStrip, .decision-strip, .scenario-tiles, .scenario-tile, #scenarioDialog, [data-scenario]')).toHaveCount(0);
  await expectCleanVisibleText(page);

  await page.locator('#langEn').click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'en');
  await expectCleanVisibleText(page);
  expect(await visibleText(page)).not.toMatch(/[А-Яа-яЁё]/);
});

test('RU Plotly labels do not expose English UI wording', async ({ page }) => {
  const badRuPlotly = new RegExp(`CAPEX|NPV expected|demand Pool|capture Ceiling|host Subsidy|students Year|avg Tuition|rule of Law|government Effectiveness|political Stability|internet Users|urban Population|Executive|scatter|treemap|${term('pro', 'xy')}|download`, 'i');
  await loadDashboard(page, '#lang=ru');
  await expectBranchVisuals(page);
  expect(await plotlyVisibleText(page)).not.toMatch(badRuPlotly);
  await page.locator('#factorTabs [data-factor="I_FIN"]').click();
  await expectHtmlVisual(page, '#activeFactorChart');
  expect(await plotlyVisibleText(page)).not.toMatch(badRuPlotly);
  await page.locator('#factorTabs [data-factor="I_FEAS"]').click();
  await expectHtmlVisual(page, '#activeFactorChart');
  expect(await plotlyVisibleText(page)).not.toMatch(badRuPlotly);

  await loadStudents(page);
  await expectStudentVisuals(page);
  expect(await plotlyVisibleText(page)).not.toMatch(badRuPlotly);
});

test('Vietnam is visible with in-preparation status and no status bonus wording', async ({ page }) => {
  await loadDashboard(page);
  const row = page.locator('#rankingList tr[data-iso3="VNM"]').first();
  await expect(row).toBeVisible();
  await expect(row).toContainText(PREPARATION_RE);
  const rowText = await row.innerText();
  expect(rowText).not.toMatch(/pipeline|bonus|direct open|hard/i);

  const mapCountry = page.locator('#map path[data-iso3="VNM"]').first();
  await expect(mapCountry).toBeVisible();
  const mapStatus = await mapCountry.evaluate(el => `${el.getAttribute('data-status') || ''} ${el.getAttribute('aria-label') || ''}`);
  expect(mapStatus).toMatch(PREPARATION_RE);

  const data = await dashboardPayload(page);
  const vietnam = data.countries.find(country => country.iso3 === 'VNM');
  expect(vietnam.recommendationCategory).toBe('in_preparation');
  expect(priorityScore(vietnam, data.weightsDefault)).toBeCloseTo(vietnam.priorityScore, 6);
});

test('branch country ranking is one scrollable table on desktop', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name.includes('mobile'), 'desktop scroll contract');
  await loadDashboard(page);
  await expect(page.locator('#visualRanking')).toHaveCount(0);
  await expect(page.locator('#rankingList .compare-toggle')).toHaveCount(0);
  const state = await page.locator('.shortlist-wrap').evaluate(el => ({
    overflowY: getComputedStyle(el).overflowY,
    clientHeight: el.clientHeight,
    scrollHeight: el.scrollHeight,
    rowCount: el.querySelectorAll('#rankingList tr[data-iso3]').length,
    columnCount: document.querySelectorAll('#rankingTable thead th').length
  }));
  expect(state.rowCount).toBeGreaterThan(10);
  expect(state.columnCount).toBe(3);
  expect(state.overflowY).toMatch(/auto|scroll/);
  expect(state.scrollHeight).toBeGreaterThan(state.clientHeight + 120);
});

test('branch candidates use green status treatment in ranking and map', async ({ page }) => {
  await loadDashboard(page);
  const data = await dashboardPayload(page);
  const candidate = data.countries.find(country => country.eligible && country.recommendationCategory === 'A_open_priority');
  expect(candidate?.iso3).toBeTruthy();
  const row = page.locator(`#rankingList tr[data-iso3="${candidate.iso3}"]`).first();
  await expect(row).toBeVisible();
  const colors = await row.evaluate(el => {
    const firstCell = el.querySelector('td');
    const countryButton = el.querySelector('.table-country');
    return {
      rowStatus: getComputedStyle(el).getPropertyValue('--status-color').trim(),
      cellBorder: getComputedStyle(firstCell).borderLeftColor,
      countryBorderWidth: getComputedStyle(countryButton).borderLeftWidth,
      countryBackground: getComputedStyle(countryButton).backgroundColor,
      text: el.innerText
    };
  });
  expect(colors.rowStatus.toLowerCase()).toBe('#397a21');
  expect(colors.cellBorder).toMatch(/57,\s*122,\s*33/);
  expect(colors.countryBorderWidth).toBe('0px');
  expect(colors.countryBackground).toBe('rgba(0, 0, 0, 0)');
  expect(colors.text).not.toMatch(/Кандидат|Candidate|Партнёрский|Partner format/i);
  const mapCandidate = page.locator(`#map path.country-${candidate.iso3}.candidate-country`).first();
  await expect(mapCandidate).toBeVisible();
  await expect(mapCandidate).toHaveAttribute('data-status', 'candidate');
  await expect.poll(async () => page.locator('#map .marker-candidate').count()).toBeGreaterThan(0);
});

test('branch comparison starts empty and multi-select drives charts, map, URL and reset', async ({ page }) => {
  await loadDashboard(page);
  await expect(page.locator('#comparePanel')).not.toHaveClass(/open/);
  await expect(page.locator('#rankingList .compare-toggle')).toHaveCount(0);
  await expect(page.locator('#rankingList .rank-row.compared-row')).toHaveCount(0);
  const initial = await page.evaluate(() => ({
    selected: window.MGIMO_DASHBOARD_STATE?.selectedIso3,
    compared: Array.from(window.MGIMO_DASHBOARD_STATE?.comparisonIso3s || [])
  }));
  expect(initial.selected).toBeTruthy();
  expect(initial.compared).toEqual([]);
  expect(page.url()).not.toContain('compare=');
  const initialCounts = await executiveTraceCounts(page);

  for (const iso3 of ['CHN', 'TUR', 'BRA']) {
    await page.locator(`#rankingList tr[data-iso3="${iso3}"] .table-country`).click();
  }
  await expect.poll(async () => page.evaluate(() => Array.from(window.MGIMO_DASHBOARD_STATE?.comparisonIso3s || []).sort())).toEqual(['BRA', 'CHN', 'TUR']);
  await expect(page.locator('#comparePanel')).toHaveClass(/open/);
  await expect(page.locator('#compareGrid .compare-donut-card')).toHaveCount(3);
  await expect(page.locator('#ageSexPyramidChart .pyramid-compare-item')).toHaveCount(3);
  await expect.poll(async () => page.locator('#populationYouthChart').evaluate(el => {
    const plot = el.classList.contains('js-plotly-plot') ? el : el.querySelector('.js-plotly-plot');
    return (plot?._fullData || plot?.data || []).filter(trace => /15/.test(String(trace.name || ''))).length;
  })).toBeGreaterThanOrEqual(3);
  await expect(page.locator('#rankingList .rank-row.compared-row')).toHaveCount(3);
  for (const iso3 of ['CHN', 'TUR', 'BRA']) {
    await expect(page.locator(`#map path.country-${iso3}.compare-country`).first()).toBeVisible();
    await expect(page.locator(`#rankingList tr[data-iso3="${iso3}"]`)).toHaveClass(/compared-row/);
  }

  await page.locator('#rankingList tr[data-iso3="BRA"] .table-country').click();
  await expect.poll(async () => page.evaluate(() => Array.from(window.MGIMO_DASHBOARD_STATE?.comparisonIso3s || []).sort())).toEqual(['CHN', 'TUR']);
  await expect(page.locator('#rankingList tr[data-iso3="BRA"]')).not.toHaveClass(/compared-row/);
  await expect(page.locator('#rankingList .rank-row.compared-row')).toHaveCount(2);
  await expect(page.locator('#compareGrid .compare-donut-card')).toHaveCount(2);
  await expect(page.locator('#ageSexPyramidChart .pyramid-compare-item')).toHaveCount(2);

  const compareUrl = new URL(page.url());
  expect((compareUrl.hash.match(/compare=([^&]+)/) || [])[1] || '').toMatch(/CHN/);
  const comparedCounts = await executiveTraceCounts(page);
  for (const selector of EXECUTIVE_COMPARE_CHARTS) {
    expect(comparedCounts[selector], selector).toBeGreaterThan(initialCounts[selector]);
  }

  await page.locator('#resetBtn').click();
  await expect.poll(async () => page.evaluate(() => Array.from(window.MGIMO_DASHBOARD_STATE?.comparisonIso3s || []))).toEqual([]);
  await expect(page.locator('#comparePanel')).not.toHaveClass(/open/);
  await expect(page.locator('#rankingList .rank-row.compared-row')).toHaveCount(0);
  expect(page.url()).not.toContain('compare=');

  await loadDashboard(page, '#compare=CHN,TUR');
  await expect.poll(async () => page.evaluate(() => Array.from(window.MGIMO_DASHBOARD_STATE?.comparisonIso3s || []).sort())).toEqual(['CHN', 'TUR']);
  await expect(page.locator('#comparePanel')).toHaveClass(/open/);
  await expect(page.locator('#rankingList .rank-row.compared-row')).toHaveCount(2);
});

test('Saudi Arabia age-sex pyramid renders continuous WPP million values', async ({ page }) => {
  await loadDashboard(page);
  await page.locator('#rankingList tr[data-iso3="SAU"] .table-country').click();
  await expect.poll(async () => page.evaluate(() => window.MGIMO_DASHBOARD_STATE?.selectedIso3)).toBe('SAU');
  const mapFocusStyle = await page.locator('#map path.country-SAU').first().evaluate(el => {
    const style = getComputedStyle(el);
    return {
      filter: style.filter,
      outlineStyle: style.outlineStyle
    };
  });
  expect(mapFocusStyle.filter).toBe('none');
  expect(mapFocusStyle.outlineStyle).toBe('none');
  await expectPlotlyVisual(page, '#ageSexPyramidChart');
  const pyramid = await page.locator('#ageSexPyramidChart').evaluate(el => {
    const plot = el.classList.contains('js-plotly-plot') ? el : el.querySelector('.js-plotly-plot');
    const data = plot?._fullData || plot?.data || [];
    const layout = plot?._fullLayout || plot?.layout || {};
    return {
      maleX: data[0]?.x || [],
      femaleX: data[1]?.x || [],
      ticktext: layout.xaxis?.ticktext || [],
      tickBoxes: Array.from(el.querySelectorAll('.xtick text')).map(node => {
        const box = node.getBoundingClientRect();
        return { left: box.left, right: box.right };
      }),
      title: layout.xaxis?.title?.text || ''
    };
  });
  const maleAbs = pyramid.maleX.map(value => Math.abs(Number(value))).filter(Number.isFinite);
  const female = pyramid.femaleX.map(Number).filter(Number.isFinite);
  expect(maleAbs.length).toBe(17);
  expect(female.length).toBe(17);
  expect(Math.max(...maleAbs)).toBeGreaterThan(2.5);
  expect(Math.max(...maleAbs)).toBeLessThan(2.7);
  expect(Math.max(...female)).toBeGreaterThan(1.35);
  expect(Math.max(...female)).toBeLessThan(1.45);
  expect(maleAbs.some(value => Math.abs(value - Math.round(value)) > 0.01)).toBeTruthy();
  expect(female.some(value => Math.abs(value - Math.round(value)) > 0.01)).toBeTruthy();
  expect(new Set(female.map(value => value.toFixed(2))).size).toBeGreaterThan(8);
  expect(pyramid.ticktext.length).toBeLessThanOrEqual(9);
  expect(pyramid.ticktext.every(label => !String(label).trim().startsWith('-'))).toBeTruthy();
  const sortedBoxes = pyramid.tickBoxes.sort((left, right) => left.left - right.left);
  for (let index = 1; index < sortedBoxes.length; index += 1) {
    expect(sortedBoxes[index].left).toBeGreaterThanOrEqual(sortedBoxes[index - 1].right - 1);
  }
  expect(pyramid.title).toMatch(/млн|million/i);
});

test('compact weights, sliders, reset and URL restore update ranking client-side', async ({ page }) => {
  await loadDashboard(page);
  await expect(page.locator('#weightsPanel')).toBeVisible();
  await expect(page.locator('.weight-segment')).toHaveCount(INDEX_KEYS.length);
  await expect(page.locator('#weightModeSliders')).toBeVisible();
  await expect(page.locator('#copyWeightsLink')).toBeHidden();
  await expect(page.locator('#resetWeights')).toBeHidden();
  await expect(page.locator('#weightInputs input')).toHaveCount(0);

  await page.locator('#weightModeSliders').click();
  await expect(page.locator('.weight-slider')).toHaveCount(INDEX_KEYS.length);
  await expect(page.locator('#copyWeightsLink')).toBeVisible();
  await expect(page.locator('#resetWeights')).toBeVisible();
  const defaults = await sliderWeights(page);
  expect(defaults.reduce((sum, value) => sum + value, 0)).toBeCloseTo(1, 1);

  await switchToSlidersAndChange(page);
  await page.locator('#copyWeightsLink').click();
  await expect(page.locator('#copyStatus')).not.toBeEmpty();
  const changedUrl = page.url();
  await page.reload();
  await page.waitForLoadState('networkidle');
  expect(page.url()).toBe(changedUrl);
  await expect(page.locator('#weightModeSliders')).not.toHaveClass(/active/);
  await expect(page.locator('#copyWeightsLink')).toBeHidden();
  await expect(page.locator('#resetWeights')).toBeHidden();

  await page.locator('#weightModeSliders').click();
  await expect(page.locator('.weight-slider')).toHaveCount(INDEX_KEYS.length);

  await page.locator('#resetWeights').click();
  const reset = await sliderWeights(page);
  reset.forEach((value, index) => expect(value).toBeCloseTo(defaults[index], 1));
});

test('country factor panel exposes exactly seven factor tabs with formula, source, year and status', async ({ page }) => {
  await loadDashboard(page);
  await expect(page.locator('#factorTabs .factor-tab')).toHaveCount(7);
  for (const key of INDEX_KEYS) {
    await expect(page.locator(`#factorTabs [data-factor="${key}"]`)).toBeVisible();
  }
  const panel = page.locator('#factorDetailPanel');
  await expect(page.locator('#methodologyText .index-equation')).toBeVisible();
  await expect(page.locator('#activeFactorChart .component-workbench')).toBeVisible();
  await expect(page.locator('#activeFactorChart .component-equation')).toBeVisible();
  await expect(panel.locator('.method-source-panel')).toBeVisible();
  for (const header of [
    /official_indicator_code/i,
    /official_indicator_name_ru/i,
    /provider/i,
    /official_url/i,
    /raw_file/i,
    /source_note/i,
    /source_name/i,
    /year/i,
    /unit/i,
    /raw_value/i,
    /normalized_value/i,
    /within_factor_weight/i,
    /observation_status/i,
    /normalization_method/i
  ]) {
    await expect(panel.locator('.factor-input-table thead')).toContainText(header);
  }
  for (const key of INDEX_KEYS) {
    await page.locator(`#factorTabs [data-factor="${key}"]`).click();
    await expect(page.locator('#activeFactorChart .component-workbench')).toContainText(new RegExp(key === 'I_MARKET' ? 'I1' : 'I[1-7]'));
    await expect(panel.locator('.method-source-panel')).toBeVisible();
    await panel.locator('.evidence-table-drawer summary').click();
    await expect(panel.locator('.factor-input-table tbody tr').first()).toBeVisible();
    const cells = await panel.locator('.factor-input-table tbody tr').first().locator('th,td').count();
    expect(cells).toBe(14);
  }
  await expect(panel).toContainText(/World Bank|MGIMO|Источник|Source|Официальный|Modelled|Модель/i);
});

test('methodology workbench updates formula weights and country calculation rows', async ({ page }) => {
  await loadDashboard(page);
  await expect(page.locator('#methodologyText .math-factor-token')).toHaveCount(INDEX_KEYS.length);
  const firstTokenStyle = await page.locator('#methodologyText .math-factor-token').first().evaluate((node) => {
    const style = window.getComputedStyle(node);
    return { background: style.backgroundColor, borderTopWidth: style.borderTopWidth };
  });
  expect(firstTokenStyle.background).toBe('rgba(0, 0, 0, 0)');
  expect(firstTokenStyle.borderTopWidth).toBe('0px');
  await expect(page.locator('#methodologyText .country-equation-row')).toHaveCount(1);
  const firstWeightBefore = await page.locator('#methodologyText .math-factor-token').first().innerText();

  await switchToSlidersAndChange(page);
  await expect.poll(async () => page.locator('#methodologyText .math-factor-token').first().innerText()).not.toBe(firstWeightBefore);
  await page.locator('#closeWeights').click();

  for (const iso3 of ['CHN', 'TUR', 'BRA']) {
    await page.locator(`#rankingList tr[data-iso3="${iso3}"] .table-country`).click();
  }
  await expect(page.locator('#methodologyText .country-equation-row')).toHaveCount(3);
  await expect(page.locator('#activeFactorChart .component-country-row')).toHaveCount(3);
  await page.locator('#methodologyText .math-factor-token[data-method-factor="I_FIN"]').click();
  await expect.poll(async () => page.evaluate(() => window.MGIMO_DASHBOARD_STATE?.activeFactorKey)).toBe('I_FIN');
  await expect(page.locator('#factorTabs [data-factor="I_FIN"]')).toHaveClass(/active/);
  await expect(page.locator('#factorDetailPanel .method-source-panel')).toContainText(/Источник|Source|World Bank|MGIMO/i);
});

test('methodology source drilldown reaches concrete WGI indicator record', async ({ page }) => {
  await loadDashboard(page);
  await page.locator('#factorTabs [data-factor="I_FEAS"]').click();
  await page.locator('#activeFactorChart .method-equation-token[data-method-input="politicalStability"]').click();
  const panel = page.locator('#factorDetailPanel .method-source-panel');
  await expect.poll(async () => page.evaluate(() => window.MGIMO_DASHBOARD_STATE?.activeMethodInputKey)).toBe('politicalStability');
  await expect(panel).toContainText('PV.EST');
  await expect(panel).toContainText('World Bank');
  await expect(panel).toContainText('Political Stability and Absence of Violence/Terrorism: Estimate');
  await expect(panel).toContainText('https://data.worldbank.org/indicator/PV.EST');
  await expect(panel).toContainText(/2023|Исходное значение|Raw value|Нормированное значение|Normalized value/i);
  await expect(panel).not.toContainText(/crime|police/i);
});

test('branch executive visuals render and react to country and weight interactions', async ({ page }) => {
  await loadDashboard(page);
  await expectBranchVisuals(page);

  await page.locator('#map path[data-iso3="CHN"]').click({ force: true });
  await expect.poll(async () => page.evaluate(() => window.MGIMO_DASHBOARD_STATE?.selectedIso3)).toBe('CHN');
  await expectBranchVisuals(page);

  await page.locator('#rankingList tr[data-iso3="VNM"] .table-country').click();
  await expect.poll(async () => page.evaluate(() => window.MGIMO_DASHBOARD_STATE?.selectedIso3)).toBe('VNM');
  await expectBranchVisuals(page);

  await emitPlotlyClick(page, '#indexDecompositionChart', { customdata: 'I_FIN' });
  await expect.poll(async () => page.evaluate(() => window.MGIMO_DASHBOARD_STATE?.activeFactorKey)).toBe('I_FIN');
  await expect.poll(async () => page.evaluate(() => window.MGIMO_DASHBOARD_STATE?.selectedIso3)).toBe('VNM');
  await emitPlotlyClick(page, '#financeChart', {});
  await expect.poll(async () => page.evaluate(() => window.MGIMO_DASHBOARD_STATE?.selectedIso3)).toBe('VNM');
  await emitPlotlyClick(page, '#programProfileChart', {});
  await expect.poll(async () => page.evaluate(() => window.MGIMO_DASHBOARD_STATE?.selectedIso3)).toBe('VNM');

  const rankingBefore = await page.locator('#rankingList').innerText();
  await switchToSlidersAndChange(page);
  await expect.poll(async () => page.locator('#rankingList').innerText()).not.toBe(rankingBefore);
  await expectBranchVisuals(page);
});

test('students page uses open-data index and separates factual flows from modelled potential arrows', async ({ page }) => {
  await loadStudents(page);
  await expectCleanVisibleText(page);
  await expect(page.locator('#studentModeSelect')).toHaveValue('practical');
  await expect(page.locator('#studentEvidenceSelect')).toHaveCount(0);
  await expect(page.locator('#studentObservedNotice')).toHaveCount(0);
  await expect(page.locator('.student-map-note')).toHaveCount(0);
  await expect(page.locator('#studentDataMode')).toHaveCount(0);
  await expect(page.locator('#studentTopNSelect')).toHaveValue('20');
  await expect(page.locator('#studentFlowToggle')).toBeChecked();
  await expect(page.locator('.student-direction-legend #studentFlowToggle')).toHaveCount(1);
  await expect.poll(async () => page.evaluate(() => {
    const state = window.MGIMO_STUDENTS_STATE;
    const leader = state?.rows?.find(row => row.sai !== null && row.sai !== undefined && !row.hardFiltered)?.iso3;
    return state?.selectedIso3 === leader;
  })).toBeTruthy();
  const state = await page.evaluate((uisKey) => ({
    flows: window.MGIMO_STUDENTS_STATE?.flowRows?.length || 0,
    observed: window.MGIMO_STUDENTS_STATE?.flowRows?.filter(row => row.evidence === 'observed').length || 0,
    modelled: window.MGIMO_STUDENTS_STATE?.flowRows?.filter(row => row.evidence === 'modelled').length || 0,
    model: window.MGIMO_STUDENTS_STATE?.studentModelMeta?.model_name || null,
    components: Object.keys(window.MGIMO_STUDENTS_STATE?.rows?.[0]?.components || {}),
    trace: window.MGIMO_STUDENTS_STATE?.rows?.[0]?.componentTrace?.[uisKey] || null,
    componentTrace: Object.keys(window.MGIMO_STUDENTS_STATE?.rows?.[0]?.componentTrace || {}).length,
    scored: window.MGIMO_STUDENTS_STATE?.rows?.filter(row => row.sai !== null && row.sai !== undefined && !row.hardFiltered).length || 0,
    hardWithScore: window.MGIMO_STUDENTS_STATE?.rows?.filter(row => row.hardFiltered && row.sai !== null && row.sai !== undefined).length || 0,
    hasRussia: Boolean(window.MGIMO_STUDENTS_STATE?.rowByIso?.has?.('RUS')),
    russiaStatus: window.MGIMO_STUDENTS_STATE?.rowByIso?.get?.('RUS')?.status || null
  }), SAI_UIS_KEY);
  expect(state.flows).toBeGreaterThan(20);
  expect(state.observed).toBe(0);
  expect(state.modelled).toBeGreaterThan(20);
  expect(state.model).toBe('SAI_MGIMO_V3');
  expect(state.components).toContain(SAI_UIS_KEY);
  expect(state.components).not.toContain(OLD_SAI_BASE);
  expect(state.components).not.toContain(OLD_SAI_KEY);
  expect(state.trace).toBeTruthy();
  for (const key of ['source_key', 'year', 'raw_value', 'normalized_value', 'normalization_method', 'weight', 'observation_status']) {
    expect(state.trace[key], key).not.toBeNull();
    expect(String(state.trace[key]), key).not.toBe('');
  }
  expect(state.componentTrace).toBeGreaterThan(0);
  expect(state.scored).toBeGreaterThan(100);
  expect(state.hardWithScore).toBe(0);
  expect(state.hasRussia).toBeTruthy();
  expect(state.russiaStatus).toBe('domestic_excluded');
  await expect(page.locator('#studentRankingBody tr')).toHaveCount(20);

  await expect(page.locator('#studentMap path.student-line.observed')).toHaveCount(0);
  await expect.poll(async () => page.locator('#studentMap path.student-line.modelled').count()).toBeGreaterThan(20);
  await expect(page.locator('#studentMapLegend')).toContainText(/модельн|modelled|фактическ|actual/i);
  await page.locator('#studentFlowToggle').uncheck();
  await expect(page.locator('#studentMap path.student-line.modelled')).toHaveCount(0);
  await page.locator('#studentFlowToggle').check();
  await expect.poll(async () => page.locator('#studentMap path.student-line.modelled').count()).toBeGreaterThan(20);

  const referencePath = page.locator('#studentMap path.student-country-DEU').first();
  await expect(referencePath).toBeVisible();
  const fill = await referencePath.evaluate(el => el.getAttribute('fill') || getComputedStyle(el).fill);
  expect(fill).toMatch(/studentReferenceHatch|url/i);
  const russiaPath = page.locator('#studentMap path.student-country-RUS').first();
  await expect(russiaPath).toBeVisible();
  const russiaState = await russiaPath.evaluate(el => ({
    fill: el.getAttribute('fill') || getComputedStyle(el).fill,
    className: el.getAttribute('class') || ''
  }));
  expect(russiaState.fill).not.toMatch(/studentReferenceHatch|url/i);
  expect(russiaState.className).toMatch(/student-domestic-country/);
  await expect(page.locator('#studentSelectedWarning')).toContainText(/фактическ|справочно|открыт|индекс|fact|reference|open/i);
  await page.locator('#studentModeSelect').selectOption('reference');
  await expect.poll(async () => page.locator('#studentRankingBody tr').count()).toBeGreaterThan(0);
});

test('students executive visuals render and ranking/map clicks update selected country', async ({ page }) => {
  await loadStudents(page);
  await expectStudentVisuals(page);

  const initial = await page.evaluate(() => window.MGIMO_STUDENTS_STATE?.selectedIso3);
  await page.locator('#studentRankingBody [data-iso3]').nth(1).click();
  await expect.poll(async () => page.evaluate(() => window.MGIMO_STUDENTS_STATE?.selectedIso3)).not.toBe(initial);
  await expectStudentVisuals(page);

  const beforeMapClick = await page.evaluate(() => window.MGIMO_STUDENTS_STATE?.selectedIso3);
  await page.locator('#studentMap path.student-country-DEU').first().click({ force: true });
  await expect.poll(async () => page.evaluate(() => window.MGIMO_STUDENTS_STATE?.selectedIso3)).not.toBe(beforeMapClick);
  const studentMapFocusStyle = await page.locator('#studentMap path.student-country-DEU').first().evaluate(el => {
    const style = getComputedStyle(el);
    return {
      filter: style.filter,
      outlineStyle: style.outlineStyle
    };
  });
  expect(studentMapFocusStyle.filter).toBe('none');
  expect(studentMapFocusStyle.outlineStyle).toBe('none');
  await expect(page.locator('#studentSelectedSai')).toContainText(/Нет данных|No data|-|[0-9]/);
});

test('mobile layouts have no horizontal overflow in branch and student views', async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 900 });
  await loadDashboard(page);
  await expectNoHorizontalOverflow(page);
  await expect(page.locator('#weightInputs')).not.toBeVisible();
  await page.locator('#weightModeSliders').click();
  await expect(page.locator('#weightSliderPanel .weight-slider').first()).toBeVisible();
  await page.locator('#closeWeights').click();
  await expect(page.locator('#weightEditorPanel')).toBeHidden();
  await page.locator('#langEn').click();
  await expectNoHorizontalOverflow(page);

  await loadStudents(page);
  await expectNoHorizontalOverflow(page);
  await page.locator('#langEn').click();
  await expectNoHorizontalOverflow(page);
});

test('visual QA screenshots are produced', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'chromium', 'canonical visual screenshots are captured once in Chromium');
  fs.mkdirSync(VISUAL_DIR, { recursive: true });
  for (const file of fs.readdirSync(VISUAL_DIR)) {
    if (file.endsWith('.png')) fs.rmSync(path.join(VISUAL_DIR, file), { force: true });
  }

  await page.setViewportSize({ width: 1440, height: 1000 });
  await loadDashboard(page, '#lang=ru');
  await expectBranchVisuals(page);
  await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_desktop_ru_overview.png'), fullPage: false });
  await page.locator('#indexDecompositionChart').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_desktop_ru_visuals.png'), fullPage: false });
  await page.locator('#factorTabs [data-factor="I_MARKET"]').click();
  await page.locator('#activeFactorChart').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_desktop_factor_market.png'), fullPage: false });
  await page.locator('#factorTabs [data-factor="I_FIN"]').click();
  await page.locator('#activeFactorChart').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_desktop_factor_finance.png'), fullPage: false });
  await page.locator('#factorTabs [data-factor="I_FEAS"]').click();
  await page.locator('#activeFactorChart').scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_desktop_factor_feasibility.png'), fullPage: false });
  await loadStudents(page);
  await expectStudentVisuals(page);
  await page.screenshot({ path: path.join(VISUAL_DIR, 'students_desktop_ru_overview.png'), fullPage: false });

  await page.setViewportSize({ width: 360, height: 900 });
  await loadDashboard(page, '#lang=ru');
  await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_mobile_ru_overview.png'), fullPage: false });
  await loadStudents(page);
  await page.screenshot({ path: path.join(VISUAL_DIR, 'students_mobile_ru_overview.png'), fullPage: false });
});
