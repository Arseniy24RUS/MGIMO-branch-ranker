const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const VISUAL_DIR = path.resolve(__dirname, '..', 'artifacts', 'visual_qa');
const SAI_UIS_KEY = 'A_OUTBOUND_MOBILITY_UIS';
const OLD_SAI_BASE = ['A_MOBILITY', '_READINESS'].join('');
const OLD_SAI_KEY = `${OLD_SAI_BASE}_${['PRO', 'XY'].join('')}`;
const OLD_NOTICE_KEY = ['students.uis', 'Pro', 'xyNotice'].join('');

async function loadStudents(page) {
  await page.goto('/students.html');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#loadStatus')).toContainText(/Data loaded|Данные загружены/i);
  await expect(page.locator('#studentMap')).toBeVisible();
}

test('students page keeps independent SAI model, UIS component and modelled arcs', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await loadStudents(page);
  await expect(page.locator('#studentDataMode')).toHaveCount(0);
  await expect(page.locator('.student-kpis')).toHaveCount(0);
  await expect(page.locator('#studentTopNSelect')).toHaveValue('20');
  await expect(page.locator('#studentRankingBody tr')).toHaveCount(20);
  const rankingHeaders = await page.locator('.student-ranking-table thead th').evaluateAll(nodes => nodes.map(node => node.textContent.trim()));
  expect(rankingHeaders).toHaveLength(3);
  expect(rankingHeaders.join('|')).not.toMatch(/Status|Статус/i);
  const firstRank = await page.locator('#studentRankingBody tr[data-iso3]').first().locator('td').first().innerText();
  expect(firstRank.trim()).toBe('1');
  const firstRowStyle = await page.locator('#studentRankingBody tr[data-iso3]').first().evaluate(el => {
    const firstCell = el.querySelector('td');
    const countryButton = el.querySelector('.student-row-button');
    return {
      statusColor: getComputedStyle(el).getPropertyValue('--student-status-color').trim(),
      cellRail: firstCell ? getComputedStyle(firstCell).borderLeftColor : '',
      countryRailWidth: countryButton ? getComputedStyle(countryButton).borderLeftWidth : '',
      countryBackground: countryButton ? getComputedStyle(countryButton).backgroundColor : ''
    };
  });
  expect(firstRowStyle.statusColor).toMatch(/^#|rgb/i);
  expect(firstRowStyle.cellRail).not.toMatch(/rgba\(0,\s*0,\s*0,\s*0\)|transparent/i);
  expect(firstRowStyle.countryRailWidth).toBe('0px');
  expect(firstRowStyle.countryBackground).toBe('rgba(0, 0, 0, 0)');
  await expect(page.locator('#studentObservedNotice')).toHaveCount(0);
  await expect(page.locator('.student-map-note')).toHaveCount(0);
  await expect(page.locator('#studentMapLegend')).toContainText(/модельн|modelled|фактическ|actual/i);
  await expect(page.locator('.student-direction-legend #studentFlowToggle')).toHaveCount(1);
  await expect(page.locator(`[data-i18n="${OLD_NOTICE_KEY}"]`)).toHaveCount(0);
  const state = await page.evaluate(() => ({
    model: window.MGIMO_STUDENTS_STATE?.studentModelMeta?.model_name,
    components: Object.keys(window.MGIMO_STUDENTS_STATE?.rows?.[0]?.components || {}),
    trace: window.MGIMO_STUDENTS_STATE?.rows?.[0]?.componentTrace?.A_OUTBOUND_MOBILITY_UIS || null,
    observed: window.MGIMO_STUDENTS_STATE?.flowRows?.filter(row => row.evidence === 'observed').length,
    modelled: window.MGIMO_STUDENTS_STATE?.flowRows?.filter(row => row.evidence === 'modelled').length
  }));
  expect(state.model).toBe('SAI_MGIMO_V3');
  expect(state.components).toContain(SAI_UIS_KEY);
  expect(state.components).not.toContain(OLD_SAI_BASE);
  expect(state.components).not.toContain(OLD_SAI_KEY);
  expect(state.trace).toBeTruthy();
  for (const key of ['source_key', 'year', 'raw_value', 'normalized_value', 'normalization_method', 'weight', 'observation_status']) {
    expect(state.trace[key], key).not.toBeNull();
    expect(String(state.trace[key]), key).not.toBe('');
  }
  expect(state.observed).toBe(0);
  expect(state.modelled).toBeGreaterThan(20);
  await expect.poll(async () => page.locator('#studentMap path.student-line.modelled').count()).toBeGreaterThan(20);
  await expect(page.locator('#studentTopAfricaPanel')).toBeVisible();
  await expect(page.locator('#studentTopAfricaPanel .gtitle')).toContainText(/Countries|Страны/i);
  await expect(page.locator('#studentPopulationYouthChart')).toBeVisible();
  await expect(page.locator('#studentAgeSexPyramidChart')).toBeVisible();
  const layout = await page.evaluate(() => {
    const rectFor = (selector) => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const box = node.getBoundingClientRect();
      return {
        top: Math.round(box.top),
        left: Math.round(box.left),
        height: Math.round(box.height),
        width: Math.round(box.width)
      };
    };
    const visualCards = Array.from(document.querySelectorAll('.student-visual-grid .visual-card')).map((card) => {
      const visual = card.querySelector('[data-visual-id]');
      const cardBox = card.getBoundingClientRect();
      const visualBox = visual?.getBoundingClientRect();
      const hasPlotPixels = Array.from(visual?.querySelectorAll('svg') || []).some((svg) => {
        const svgBox = svg.getBoundingClientRect();
        return svgBox.width > 40 && svgBox.height > 40 && Boolean(svg.querySelector('path, rect, circle, line, text, polygon'));
      });
      return {
        visualId: visual?.getAttribute('data-visual-id') || '',
        height: Math.round(cardBox.height),
        visualHeight: Math.round(visualBox?.height || 0),
        hasPlotPixels
      };
    });
    return {
      topRow: {
        map: rectFor('.student-map-panel'),
        ranking: rectFor('.student-ranking-card'),
        selected: rectFor('.student-selected-card')
      },
      visualCards
    };
  });
  expect(layout.topRow.map.left).toBeLessThan(layout.topRow.ranking.left);
  expect(layout.topRow.ranking.left).toBeLessThan(layout.topRow.selected.left);
  expect(Math.abs(layout.topRow.map.top - layout.topRow.ranking.top)).toBeLessThanOrEqual(12);
  expect(Math.abs(layout.topRow.map.top - layout.topRow.selected.top)).toBeLessThanOrEqual(12);
  for (const panel of Object.values(layout.topRow)) expect(panel.height).toBeGreaterThanOrEqual(390);
  for (const card of layout.visualCards) {
    expect(card.height).toBeGreaterThanOrEqual(300);
    expect(card.visualHeight).toBeGreaterThanOrEqual(card.visualId === 'studentMobilityChart' ? 205 : 225);
    expect(card.hasPlotPixels).toBeTruthy();
  }
  const youthRange = await page.locator('#studentYouthGrowthScatter').evaluate(el => {
    const plot = el.classList.contains('js-plotly-plot') ? el : el.querySelector('.js-plotly-plot');
    return plot?._fullLayout?.yaxis?.range || plot?.layout?.yaxis?.range || [];
  });
  expect(youthRange.length).toBe(2);
  expect(youthRange[0]).toBeGreaterThanOrEqual(0);
  expect(youthRange[1]).toBeLessThanOrEqual(100);
  expect(youthRange[1] - youthRange[0]).toBeLessThan(100);
  if (testInfo.project.name === 'chromium') {
    fs.mkdirSync(VISUAL_DIR, { recursive: true });
    await page.screenshot({ path: path.join(VISUAL_DIR, 'students_desktop_ru_overview.png'), fullPage: false });
  }
});

test('students regions treemap drives countries chart and country selection highlight', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await loadStudents(page);
  await expect(page.locator('#studentTopAfricaPanel .gtitle')).toContainText(/Countries|Страны/i);

  const targetRegion = await page.evaluate(() => {
    const state = window.MGIMO_STUDENTS_STATE;
    const selectedRegion = state?.rowByIso?.get?.(state?.selectedIso3)?.region || null;
    const regions = Array.from(new Set((state?.rows || [])
      .filter(row => Number.isFinite(Number(row.sai)) && !row.hardFiltered && row.region)
      .map(row => row.region)));
    return regions.find(region => region !== selectedRegion) || regions[0] || null;
  });
  expect(targetRegion).toBeTruthy();

  await page.locator('#studentRegionTreemap').evaluate((el, region) => {
    const custom = (el._fullData?.[0]?.customdata || []).find(row => row[0] === region);
    if (!custom) throw new Error(`Region not found in treemap: ${region}`);
    el.emit('plotly_treemapclick', { points: [{ customdata: custom }] });
  }, targetRegion);

  await expect.poll(async () => page.evaluate(() => window.MGIMO_STUDENTS_STATE?.visualRegion)).toBe(targetRegion);
  const countriesPanel = await page.locator('#studentTopAfricaPanel').evaluate(el => {
    const plot = el.classList.contains('js-plotly-plot') ? el : el.querySelector('.js-plotly-plot');
    const customdata = plot?._fullData?.[0]?.customdata || [];
    const state = window.MGIMO_STUDENTS_STATE;
    return customdata.map(row => {
      const iso3 = row[0];
      return {
        iso3,
        region: state?.rowByIso?.get?.(iso3)?.region || null
      };
    });
  });
  expect(countriesPanel.length).toBeGreaterThan(0);
  expect(new Set(countriesPanel.map(row => row.region))).toEqual(new Set([targetRegion]));

  const clickedIso = countriesPanel[0].iso3;
  await page.locator('#studentTopAfricaPanel').evaluate((el, iso3) => {
    const custom = (el._fullData?.[0]?.customdata || []).find(row => row[0] === iso3);
    if (!custom) throw new Error(`Country not found in countries chart: ${iso3}`);
    el.emit('plotly_click', { points: [{ customdata: custom }] });
  }, clickedIso);

  await expect.poll(async () => page.evaluate(() => window.MGIMO_STUDENTS_STATE?.selectedIso3)).toBe(clickedIso);
  await expect.poll(async () => page.evaluate(() => window.MGIMO_STUDENTS_STATE?.visualRegion)).toBe(targetRegion);
  const highlightState = await page.locator('#studentTopAfricaPanel').evaluate((el, iso3) => {
    const plot = el.classList.contains('js-plotly-plot') ? el : el.querySelector('.js-plotly-plot');
    const trace = plot?._fullData?.[0] || {};
    const index = (trace.customdata || []).findIndex(row => row[0] === iso3);
    return {
      color: Array.isArray(trace.marker?.color) ? trace.marker.color[index] : trace.marker?.color,
      title: plot?._fullLayout?.title?.text || ''
    };
  }, clickedIso);
  expect(highlightState.color).toBe('#e0aa24');
  expect(highlightState.title).toMatch(/Countries|Страны/i);
});
