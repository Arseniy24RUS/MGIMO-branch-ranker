const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const VISUAL_DIR = path.resolve(__dirname, '..', 'artifacts', 'visual_qa');

async function loadBranch(page) {
  await page.goto('/#lang=ru');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#loadStatus')).toContainText(/Data loaded|Данные загружены/i);
  await expect(page.locator('#map')).toBeVisible();
}

test('branch desktop first viewport has map, ranking, selected country and readable executive visuals', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'chromium', 'canonical visual density is captured once');
  fs.mkdirSync(VISUAL_DIR, { recursive: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await loadBranch(page);
  await expect(page.locator('#indexDecompositionChart')).toBeVisible();
  await expect(page.locator('#financeChart')).toBeVisible();
  await expect(page.locator('#populationYouthChart')).toBeVisible();
  await expect(page.locator('#dataTraceCard')).toHaveCount(0);

  const metrics = await page.evaluate(() => {
    const rectFor = (selector) => {
      const node = document.querySelector(selector);
      if (!node) return null;
      const box = node.getBoundingClientRect();
      return {
        top: Math.round(box.top),
        left: Math.round(box.left),
        right: Math.round(box.right),
        bottom: Math.round(box.bottom),
        width: Math.round(box.width),
        height: Math.round(box.height)
      };
    };
    const visualCards = Array.from(document.querySelectorAll('.executive-visuals-panel .visual-card')).filter((card) => {
      const style = getComputedStyle(card);
      const box = card.getBoundingClientRect();
      return style.display !== 'none' && box.width > 0 && box.height > 0;
    }).map((card) => {
      const box = card.getBoundingClientRect();
      const visual = card.querySelector('[data-visual-id]');
      const visualBox = visual?.getBoundingClientRect();
      const visualId = visual?.getAttribute('data-visual-id') || '';
      const svgPixels = Array.from(visual?.querySelectorAll('svg') || []).some((svg) => {
        const svgBox = svg.getBoundingClientRect();
        return svgBox.width > 40 && svgBox.height > 40 && Boolean(svg.querySelector('path, rect, circle, line, text, polygon'));
      });
      const canvasPixels = Array.from(visual?.querySelectorAll('canvas') || []).some((canvas) => canvas.width > 40 && canvas.height > 40);
      const hasPlotPixels = Boolean(svgPixels || canvasPixels);
      const text = (visual?.textContent || '').trim();
      return {
        visualId,
        top: Math.round(box.top),
        bottom: Math.round(box.bottom),
        width: Math.round(box.width),
        height: Math.round(box.height),
        visualHeight: Math.round(visualBox?.height || 0),
        hasPlotPixels,
        hasTextPixels: text.length > 12,
        isTooNarrow: box.width < 220,
        blankShare: text.length > 8 || hasPlotPixels ? 0 : 1
      };
    });
    return {
      viewport: { width: innerWidth, height: innerHeight },
      topRow: {
        controls: rectFor('.branch-control-bar'),
        map: rectFor('.map-panel'),
        ranking: rectFor('.shortlist-card'),
        selected: rectFor('#selectedCard')
      },
      executiveCards: visualCards,
      largestBlankCardShare: Math.max(0, ...visualCards.map((card) => card.blankShare))
    };
  });
  fs.writeFileSync(path.join(VISUAL_DIR, 'branch_desktop_ru_overview.metrics.json'), JSON.stringify(metrics, null, 2));
  await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_desktop_ru_overview.png'), fullPage: false });
  expect(metrics.topRow.map.left).toBeLessThan(metrics.topRow.ranking.left);
  expect(metrics.topRow.ranking.left).toBeLessThan(metrics.topRow.selected.left);
  expect(metrics.topRow.controls.bottom).toBeLessThanOrEqual(metrics.topRow.map.top + 4);
  expect(Math.abs(metrics.topRow.map.top - metrics.topRow.ranking.top)).toBeLessThanOrEqual(12);
  expect(Math.abs(metrics.topRow.map.top - metrics.topRow.selected.top)).toBeLessThanOrEqual(12);
  expect(metrics.topRow.map.height).toBeGreaterThanOrEqual(390);
  expect(metrics.topRow.ranking.height).toBeGreaterThanOrEqual(390);
  expect(metrics.topRow.selected.height).toBeGreaterThanOrEqual(390);
  expect(metrics.executiveCards.map((card) => card.visualId)).toEqual(expect.arrayContaining([
    'indexDecompositionChart',
    'financeChart',
    'populationYouthChart',
    'ageSexPyramidChart'
  ]));
  const requiredCards = metrics.executiveCards.filter((card) => ['indexDecompositionChart', 'financeChart', 'populationYouthChart', 'ageSexPyramidChart'].includes(card.visualId));
  expect(requiredCards.length).toBeGreaterThanOrEqual(4);
  for (const card of requiredCards) {
    expect(card.height).toBeGreaterThanOrEqual(340);
    expect(card.visualHeight).toBeGreaterThanOrEqual(card.visualId === 'financeChart' ? 220 : 250);
    expect(card.hasPlotPixels).toBeTruthy();
  }
});
