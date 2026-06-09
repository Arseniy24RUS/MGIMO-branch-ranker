const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const VISUAL_DIR = path.resolve(__dirname, '..', 'artifacts', 'visual_qa');
const FACTORS = ['I_MARKET', 'I_PROGRAM', 'I_RUSCOMP', 'I_ECO', 'I_FIN', 'I_FEAS', 'I_HRSTRAT'];
const HEADERS = [
  'official_indicator_code',
  'official_indicator_name_ru',
  'provider',
  'official_url',
  'raw_file',
  'source_note',
  'source_name',
  'year',
  'unit',
  'raw_value',
  'normalized_value',
  'within_factor_weight',
  'observation_status',
  'normalization_method'
];

async function loadBranch(page) {
  await page.goto('/#lang=ru');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#loadStatus')).toContainText(/Data loaded|Данные загружены/i);
}

test('all seven factor tabs expose formula inputs, formula and strict evidence table', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await loadBranch(page);
  await expect(page.locator('#factorTabs .factor-tab')).toHaveCount(7);
  for (const factor of FACTORS) {
    await page.locator(`#factorTabs [data-factor="${factor}"]`).click({ force: true });
    await expect(page.locator('#activeFactorChart')).toBeVisible();
    await expect(page.locator('#activeFactorChart .component-workbench')).toBeVisible();
    await expect(page.locator('#activeFactorChart .component-equation')).toBeVisible();
    await expect(page.locator('#factorDetailPanel .method-source-panel')).toBeVisible();
    await expect(page.locator('#activeFactorChart .component-equation')).toContainText(/I[1-7]|×|N\(/i);
    const headers = await page.locator('#factorDetailPanel .factor-input-table thead th').evaluateAll(nodes => nodes.map(node => node.textContent.trim()));
    expect(headers).toEqual(HEADERS);
    await expect(page.locator('#factorDetailPanel .evidence-table-drawer')).toBeVisible();
    await expect(page.locator('#factorDetailPanel [data-factor-csv]')).toBeVisible();
    await page.locator('#factorDetailPanel .evidence-table-drawer summary').click();
    const firstCode = await page.locator('#factorDetailPanel .factor-input-table tbody tr').first().locator('td').first().innerText();
    expect(firstCode).not.toMatch(/^I_/);
  }
  await page.locator('#factorTabs [data-factor="I_FEAS"]').click({ force: true });
  await page.locator('#activeFactorChart .method-equation-token[data-method-input="politicalStability"]').click();
  await expect(page.locator('#factorDetailPanel .method-source-panel')).toContainText('PV.EST');
  await expect(page.locator('#factorDetailPanel .method-source-panel')).toContainText('https://data.worldbank.org/indicator/PV.EST');
  if (testInfo.project.name === 'chromium') {
    fs.mkdirSync(VISUAL_DIR, { recursive: true });
    await page.locator('#factorTabs [data-factor="I_MARKET"]').click();
    await page.locator('#activeFactorChart').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_desktop_factor_market.png'), fullPage: false });
    await page.locator('#factorTabs [data-factor="I_FIN"]').click();
    await page.locator('#activeFactorChart').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_desktop_factor_finance.png'), fullPage: false });
    await page.locator('#factorTabs [data-factor="I_FEAS"]').click();
    await page.locator('#activeFactorChart').scrollIntoViewIfNeeded();
    await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_desktop_factor_feasibility.png'), fullPage: false });
  }
});
