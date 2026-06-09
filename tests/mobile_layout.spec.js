const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const VISUAL_DIR = path.resolve(__dirname, '..', 'artifacts', 'visual_qa');

async function noOverflow(page) {
  await expect.poll(async () => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(2);
}

test('branch and students mobile layouts keep controls usable without horizontal overflow', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 360, height: 900 });
  await page.goto('/#lang=ru');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#loadStatus')).toContainText(/Data loaded|Данные загружены/i);
  await noOverflow(page);
  await page.locator('#weightModeSliders').click();
  await expect(page.locator('#weightEditorPanel')).toBeVisible();
  await expect(page.locator('#weightSliderPanel .weight-slider').first()).toBeVisible();
  await noOverflow(page);
  if (testInfo.project.name === 'chromium') {
    fs.mkdirSync(VISUAL_DIR, { recursive: true });
    await page.screenshot({ path: path.join(VISUAL_DIR, 'branch_mobile_ru_overview.png'), fullPage: false });
  }

  await page.goto('/students.html');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#loadStatus')).toContainText(/Data loaded|Данные загружены/i);
  await noOverflow(page);
  await expect(page.locator('#studentRankingBody tr')).toHaveCount(20);
  if (testInfo.project.name === 'chromium') {
    fs.mkdirSync(VISUAL_DIR, { recursive: true });
    await page.screenshot({ path: path.join(VISUAL_DIR, 'students_mobile_ru_overview.png'), fullPage: false });
  }
});
