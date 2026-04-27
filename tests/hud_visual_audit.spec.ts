import { test, expect } from '@playwright/test'

const HUD_URL = 'http://67.205.148.181/#hud'
const viewport = { width: 1440, height: 900 }

test.use({ viewport })
test.setTimeout(90_000)

test.describe('HUD Visual Audit — What Users See', () => {

  test('1. Initial load — all panels open, graph visible', async ({ page }) => {
    await page.goto(HUD_URL, { waitUntil: 'networkidle' })
    await page.locator('canvas').first().waitFor({ state: 'attached', timeout: 30_000 })
    await page.waitForTimeout(4000) // let graph settle
    await page.screenshot({ path: 'output/playwright/hud-audit-01-initial-load.png', fullPage: false })
  })

  test('2. Click a node — does it center between panels?', async ({ page }) => {
    await page.goto(HUD_URL, { waitUntil: 'networkidle' })
    await page.locator('canvas').first().waitFor({ state: 'attached', timeout: 30_000 })
    await page.waitForTimeout(3000)

    // Screenshot before click
    await page.screenshot({ path: 'output/playwright/hud-audit-02a-before-click.png', fullPage: false })

    // Click center of visible area (between panels)
    // Left sidebar = 320, Right sidebar = 384, Top nav = 96
    const visibleCenterX = 320 + ((viewport.width - 320 - 384) / 2)
    const visibleCenterY = 96 + ((viewport.height - 96 - 16) / 2)
    await page.mouse.click(visibleCenterX, visibleCenterY)
    await page.waitForTimeout(2000)
    await page.screenshot({ path: 'output/playwright/hud-audit-02b-after-click.png', fullPage: false })
  })

  test('3. Scanner handoff — ticker from URL centers correctly', async ({ page }) => {
    // Simulate scanner handoff with a known ticker
    await page.goto('http://67.205.148.181/#hud?ticker=AAPL&source=scanner', { waitUntil: 'networkidle' })
    await page.locator('canvas').first().waitFor({ state: 'attached', timeout: 30_000 })
    await page.waitForTimeout(5000) // allow camera flight to complete
    await page.screenshot({ path: 'output/playwright/hud-audit-03-scanner-handoff.png', fullPage: false })
  })

  test('4. Command search — type ticker, verify centering', async ({ page }) => {
    await page.goto(HUD_URL, { waitUntil: 'networkidle' })
    await page.locator('canvas').first().waitFor({ state: 'attached', timeout: 30_000 })
    await page.waitForTimeout(3000)

    // Find the search input in the right command rail
    const searchInput = page.locator('input[placeholder*="earch"], input[placeholder*="icker"], input[placeholder*="ommand"]').first()
    if (await searchInput.isVisible({ timeout: 3000 }).catch(() => false)) {
      await searchInput.fill('MSFT')
      await searchInput.press('Enter')
      await page.waitForTimeout(3000)
    }
    await page.screenshot({ path: 'output/playwright/hud-audit-04-command-search.png', fullPage: false })
  })

  test('5. All panels visible — no overlap or cut-off', async ({ page }) => {
    await page.goto(HUD_URL, { waitUntil: 'networkidle' })
    await page.locator('canvas').first().waitFor({ state: 'attached', timeout: 30_000 })
    await page.waitForTimeout(3000)

    // Check left sidebar content is visible
    const leftPanel = page.getByLabel(/tactical controls/i)
    const rightPanel = page.getByLabel(/command rail/i)
    const topPanel = page.getByLabel(/telemetry/i)

    await expect(leftPanel).toBeVisible({ timeout: 5000 })
    await expect(rightPanel).toBeVisible({ timeout: 5000 })
    await expect(topPanel).toBeVisible({ timeout: 5000 })

    // Take panel-focused screenshots
    const leftBox = await leftPanel.boundingBox()
    const rightBox = await rightPanel.boundingBox()

    await page.screenshot({ path: 'output/playwright/hud-audit-05-panels-visible.png', fullPage: false })

    // Verify panels don't overlap the canvas center
    if (leftBox && rightBox) {
      // Left panel right edge should be < visible center
      const visibleCenterX = 320 + ((viewport.width - 320 - 384) / 2)
      expect(leftBox.x + leftBox.width).toBeLessThan(visibleCenterX)
    }
  })

  test('6. Close all panels — ghost mode canvas', async ({ page }) => {
    await page.goto(HUD_URL, { waitUntil: 'networkidle' })
    await page.locator('canvas').first().waitFor({ state: 'attached', timeout: 30_000 })
    await page.waitForTimeout(2000)

    // Close all three panels
    const hideLeft = page.getByLabel('Hide tactical controls')
    const hideRight = page.getByLabel('Hide command rail')
    const hideTop = page.getByLabel('Hide telemetry')

    if (await hideLeft.isVisible({ timeout: 2000 }).catch(() => false)) await hideLeft.click()
    await page.waitForTimeout(600)
    if (await hideRight.isVisible({ timeout: 2000 }).catch(() => false)) await hideRight.click()
    await page.waitForTimeout(600)
    if (await hideTop.isVisible({ timeout: 2000 }).catch(() => false)) await hideTop.click()
    await page.waitForTimeout(1000)

    await page.screenshot({ path: 'output/playwright/hud-audit-06-ghost-mode.png', fullPage: false })
  })

  test('7. Scanner handoff MSFT — verify centering with different ticker', async ({ page }) => {
    await page.goto('http://67.205.148.181/#hud?ticker=MSFT&source=scanner', { waitUntil: 'networkidle' })
    await page.locator('canvas').first().waitFor({ state: 'attached', timeout: 30_000 })
    await page.waitForTimeout(5000)
    await page.screenshot({ path: 'output/playwright/hud-audit-07-msft-handoff.png', fullPage: false })
  })

  test('8. Scanner handoff NVDA — large-cap centering', async ({ page }) => {
    await page.goto('http://67.205.148.181/#hud?ticker=NVDA&source=scanner', { waitUntil: 'networkidle' })
    await page.locator('canvas').first().waitFor({ state: 'attached', timeout: 30_000 })
    await page.waitForTimeout(5000)
    await page.screenshot({ path: 'output/playwright/hud-audit-08-nvda-handoff.png', fullPage: false })
  })

  test('9. Mobile viewport — 375x812 (iPhone)', async ({ browser }) => {
    const context = await browser.newContext({ viewport: { width: 375, height: 812 } })
    const page = await context.newPage()
    await page.goto(HUD_URL, { waitUntil: 'networkidle' })
    await page.locator('canvas').first().waitFor({ state: 'attached', timeout: 30_000 })
    await page.waitForTimeout(3000)
    await page.screenshot({ path: 'output/playwright/hud-audit-07-mobile.png', fullPage: false })
    await context.close()
  })
})
