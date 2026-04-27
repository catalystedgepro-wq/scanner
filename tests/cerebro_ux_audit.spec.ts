import { expect, test, type TestInfo } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

test.use({ viewport: { width: 1440, height: 900 } });

const SCANNER_URL = process.env.SCANNER_BASE_URL ?? 'https://catalystedgescanner.com';
const HUD_URL = process.env.PLAYWRIGHT_BASE_URL ?? 'http://67.205.148.181';

async function attachJson(testInfo: TestInfo, name: string, payload: unknown) {
  const filePath = testInfo.outputPath(`${name}.json`);
  mkdirSync(dirname(filePath), { recursive: true });
  writeFileSync(filePath, JSON.stringify(payload, null, 2), 'utf8');
  await testInfo.attach(name, {
    path: filePath,
    contentType: 'application/json',
  });
}

async function centerHit(page: Parameters<typeof test>[0]['page']) {
  const viewport = page.viewportSize();
  if (!viewport) {
    throw new Error('Viewport not available');
  }

  return page.evaluate(({ x, y }) => {
    const el = document.elementFromPoint(x, y);
    return {
      tagName: el?.tagName ?? null,
      id: el?.id ?? null,
      ariaLabel: el?.getAttribute?.('aria-label') ?? null,
      className: typeof el?.className === 'string' ? el.className : null,
    };
  }, { x: viewport.width / 2, y: viewport.height / 2 });
}

test.describe('Catalyst Edge Scanner - 4:00 AM Drop-In Test', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(SCANNER_URL);
    await expect(page.locator('.spotlight-label').first()).toContainText(/Primary Target/i, { timeout: 15_000 });
  });

  test('Primary Target is immediately visible without scrolling', async ({ page }, testInfo) => {
    const viewport = page.viewportSize();
    if (!viewport) {
      throw new Error('Viewport not available');
    }

    const primaryTarget = page.locator('.spotlight-label').first();
    const primaryTicker = page.locator('.spotlight-ticker').first();
    const topGapHeading = page.getByRole('heading', { name: /Top Gap Candidates/i });

    await expect(primaryTarget).toBeInViewport();
    await expect(primaryTicker).toBeInViewport();
    await expect(topGapHeading).toBeVisible();

    const [labelBox, tickerBox, gapBox] = await Promise.all([
      primaryTarget.boundingBox(),
      primaryTicker.boundingBox(),
      topGapHeading.boundingBox(),
    ]);

    expect(labelBox).not.toBeNull();
    expect(tickerBox).not.toBeNull();
    expect(gapBox).not.toBeNull();
    expect(labelBox!.y).toBeLessThan(viewport.height * 0.33);
    expect(tickerBox!.y).toBeLessThan(viewport.height * 0.45);

    await attachJson(testInfo, 'scanner-primary-target-visibility', {
      viewport,
      primaryTarget: labelBox,
      primaryTicker: tickerBox,
      topGapHeading: gapBox,
    });
  });

  test('Data Cards are opaque and not destroyed by background animation', async ({ page }, testInfo) => {
    const dataCard = page.locator('.gap-burn-shell.solid-armor-card').first();
    const sparkles = page.locator('.sparkles-core').first();

    await expect(dataCard).toBeVisible();
    await expect(sparkles).toBeVisible();
    await expect(page.locator('.liquid-glass-card')).toHaveCount(0);

    const computed = await dataCard.evaluate((el) => {
      const style = getComputedStyle(el);
      const before = getComputedStyle(el, '::before');
      return {
        backgroundColor: style.backgroundColor,
        backgroundImage: style.backgroundImage,
        borderColor: style.borderColor,
        backdropFilter: style.backdropFilter,
        boxShadow: style.boxShadow,
        beforeBackgroundImage: before.backgroundImage,
      };
    });

    expect(
      computed.backgroundColor !== 'rgba(0, 0, 0, 0)'
      || computed.backgroundImage !== 'none'
      || computed.beforeBackgroundImage !== 'none'
    ).toBeTruthy();
    expect(computed.boxShadow).not.toBe('none');
    expect(computed.borderColor).not.toBe('rgba(0, 0, 0, 0)');

    await attachJson(testInfo, 'scanner-armor-card-style', computed);
  });
});

test.describe('Cerebro HUD - Ghost Mode & Invisible Cloak Test', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(`${HUD_URL}/#hud`);
    await page.locator('canvas').first().waitFor({ state: 'attached', timeout: 30_000 });
    await expect(page.getByLabel(/tactical controls/i)).toBeVisible({ timeout: 45_000 });
    await expect(page.getByLabel(/command rail/i)).toBeVisible({ timeout: 45_000 });
    await expect(page.getByLabel(/telemetry/i)).toBeVisible({ timeout: 45_000 });
  });

  test('3D Topology is not blocked by invisible cloaks (Center Click Test)', async ({ page }, testInfo) => {
    const viewport = page.viewportSize();
    if (!viewport) {
      throw new Error('Viewport not available');
    }

    // Sidebars start open — the command rail handle must be to the right of center
    const rightHandle = page.getByLabel(/command rail/i);
    const beforeBox = await rightHandle.boundingBox();
    const beforeHit = await centerHit(page);

    await page.mouse.click(viewport.width / 2, viewport.height / 2);
    await page.waitForTimeout(300);

    const afterBox = await rightHandle.boundingBox();
    const afterHit = await centerHit(page);

    expect(beforeBox).not.toBeNull();
    expect(afterBox).not.toBeNull();
    // Rail handle must be to the right of viewport center (not blocking the 3D canvas)
    expect(afterBox!.x).toBeGreaterThan(viewport.width / 2);
    expect(String(beforeHit.ariaLabel ?? '')).not.toMatch(/command rail/i);
    expect(String(afterHit.ariaLabel ?? '')).not.toMatch(/command rail/i);

    await attachJson(testInfo, 'hud-center-click-cloak-check', {
      viewport,
      rightHandleBefore: beforeBox,
      rightHandleAfter: afterBox,
      centerHitBefore: beforeHit,
      centerHitAfter: afterHit,
    });
  });

  test('Right sidebar toggle stays flush and fully clears the canvas when closed', async ({ page }, testInfo) => {
    const viewport = page.viewportSize();
    if (!viewport) {
      throw new Error('Viewport not available');
    }

    // Sidebar starts OPEN — verify open state first
    const openHandle = page.getByLabel('Hide command rail');
    await expect(page.getByText('Command / Search')).toBeVisible();
    const openBox = await openHandle.boundingBox();
    expect(openBox).not.toBeNull();
    expect(openBox!.x).toBeLessThan(viewport.width - 100);

    // Close it
    await openHandle.click();
    await page.waitForTimeout(700);

    const closedHandle = page.getByLabel('Show command rail');
    const closedBox = await closedHandle.boundingBox();
    expect(closedBox).not.toBeNull();
    expect(closedBox!.x).toBeGreaterThanOrEqual(viewport.width - 40);

    // Reopen — should return to original open state
    await closedHandle.click();
    await page.waitForTimeout(700);

    const resetBox = await page.getByLabel('Hide command rail').boundingBox();
    expect(resetBox).not.toBeNull();
    expect(resetBox!.x).toBeLessThan(viewport.width - 100);

    await attachJson(testInfo, 'hud-right-rail-toggle', {
      viewport,
      openBox,
      closedBox,
      resetBox,
    });
  });

  test('Ghost mode handles collapse the left rail and top telemetry, then restore them', async ({ page }, testInfo) => {
    // Sidebars start OPEN — verify open state
    const leftOpenHandle = page.getByLabel('Hide tactical controls');
    const topOpenHandle = page.getByLabel('Hide telemetry');

    await expect(page.getByText('Gravity Filter')).toBeVisible();
    await expect(page.getByText('Visible Universe')).toBeVisible();

    const leftOpenBox = await leftOpenHandle.boundingBox();
    const topOpenBox = await topOpenHandle.boundingBox();

    expect(leftOpenBox).not.toBeNull();
    expect(topOpenBox).not.toBeNull();

    // Close both
    await leftOpenHandle.click();
    await page.waitForTimeout(700);

    await topOpenHandle.click();
    await page.waitForTimeout(700);

    const leftClosedHandle = page.getByLabel('Show tactical controls');
    const topClosedHandle = page.getByLabel('Show telemetry');

    const leftClosedBox = await leftClosedHandle.boundingBox();
    const topClosedBox = await topClosedHandle.boundingBox();

    expect(leftClosedBox).not.toBeNull();
    expect(topClosedBox).not.toBeNull();
    // Closed handle should be far left of where open handle was
    expect(leftClosedBox!.x).toBeLessThan(leftOpenBox!.x - 120);
    // Closed handle should be far above where open handle was
    expect(topClosedBox!.y).toBeLessThan(topOpenBox!.y - 80);

    // Reopen both
    await leftClosedHandle.click();
    await topClosedHandle.click();
    await page.waitForTimeout(700);

    const leftResetBox = await page.getByLabel('Hide tactical controls').boundingBox();
    const topResetBox = await page.getByLabel('Hide telemetry').boundingBox();

    expect(leftResetBox).not.toBeNull();
    expect(topResetBox).not.toBeNull();
    // Should be back near original open position
    expect(leftResetBox!.x).toBeGreaterThanOrEqual(leftOpenBox!.x - 12);
    expect(topResetBox!.y).toBeGreaterThanOrEqual(topOpenBox!.y - 12);

    await attachJson(testInfo, 'hud-ghost-mode-handles', {
      leftOpenBox,
      leftClosedBox,
      leftResetBox,
      topOpenBox,
      topClosedBox,
      topResetBox,
    });
  });
});
