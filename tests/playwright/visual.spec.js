// @ts-check
const { test, expect } = require('@playwright/test');

// Credentials from env — set CURATOR_TEST_USER / CURATOR_TEST_PASSWORD before running.
const TEST_USER = process.env.CURATOR_TEST_USER || 'admin';
const TEST_PASSWORD = process.env.CURATOR_TEST_PASSWORD || 'adminadmin';

// Cached JWT token — obtained once and reused across all tests to avoid rate limits.
/** @type {string|null} */ let _authToken = null;

/**
 * Obtain a JWT token via the API (cached — only one login per test run).
 * Handles both first-time setup and existing-user login.
 * @param {import('@playwright/test').APIRequestContext} request
 * @returns {Promise<string>}
 */
async function getToken(request) {
  if (_authToken) return _authToken;

  const modeRes = await request.get('/api/auth/login-mode');
  const mode = await modeRes.json();

  if (mode.mode === 'setup') {
    await request.post('/api/auth/setup', {
      data: { username: TEST_USER, password: TEST_PASSWORD },
    });
  }

  const loginRes = await request.post('/api/auth/login', {
    data: { username: TEST_USER, password: TEST_PASSWORD },
  });
  const loginData = await loginRes.json();

  if (!loginData.token) {
    const hint =
      mode.mode === 'login'
        ? ' Set CURATOR_TEST_USER and CURATOR_TEST_PASSWORD env vars for this instance.'
        : '';
    throw new Error(`Login failed: ${JSON.stringify(loginData)}.${hint}`);
  }

  _authToken = loginData.token;
  return /** @type {string} */ (_authToken);
}

/**
 * Inject the JWT into localStorage so the SPA treats us as authenticated.
 * @param {import('@playwright/test').Page} page
 * @param {import('@playwright/test').APIRequestContext} request
 */
async function login(page, request) {
  const token = await getToken(request);
  await page.goto('/');
  await page.evaluate((t) => localStorage.setItem('auth_token', t), token);
}

/**
 * Navigate to the main page and wait for the SPA modules to initialize.
 * Returns only after window.__modules is populated (UIUtils available).
 * @param {import('@playwright/test').Page} page
 */
async function gotoApp(page) {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  // Wait for ES module init — main.js assigns window.__modules after DOMContentLoaded
  await page.waitForFunction(() => /** @type {any} */ (window).__modules?.UIUtils, { timeout: 5000 });
}

/**
 * Click a top-level nav tab by its label text and wait for its content div.
 * @param {import('@playwright/test').Page} page
 * @param {string} label
 * @param {string} tabId
 */
async function navigateToTab(page, label, tabId) {
  await page.locator(`nav .nav-btn:has(.nav-text:text("${label}"))`).click();
  await page.waitForTimeout(300);
  await expect(page.locator(tabId)).toBeVisible();
}

// ---------------------------------------------------------------------------
// Login Page
// ---------------------------------------------------------------------------
test.describe('Login Page', () => {
  test('renders login form with branding', async ({ page }) => {
    await page.goto('/login.html');
    await page.waitForLoadState('networkidle');

    await expect(page.locator('.login-header h1')).toContainText('Curator');
    await expect(page.locator('.login-header p')).toBeVisible();
    await expect(page.locator('#loginUsername')).toBeVisible();
    await expect(page.locator('#loginPassword')).toBeVisible();
    await expect(page.locator('#loginBtn')).toBeVisible();
    await expect(page.locator('#loginBtn')).toHaveText('Sign In');
  });
});

// ---------------------------------------------------------------------------
// Main Application — Page-level tests for each tab
// ---------------------------------------------------------------------------
test.describe('Main Application', () => {
  test.beforeEach(async ({ page, request }) => {
    await login(page, request);
  });

  test('loads the main page with all navigation tabs', async ({ page }) => {
    await gotoApp(page);

    const nav = page.locator('nav .nav-btn');
    await expect(nav.first()).toBeVisible();

    for (const label of ['Library', 'Track', 'Tasks', 'Queue', 'Settings']) {
      await expect(page.locator(`nav .nav-btn .nav-text:text("${label}")`)).toBeVisible();
    }
  });

  test('library tab loads with content', async ({ page }) => {
    await gotoApp(page);

    await expect(page.locator('#library-tab')).toBeVisible();
    await expect(page.locator('.library-container')).toBeVisible();
  });

  test('tracking tab loads with content', async ({ page }) => {
    await gotoApp(page);
    await navigateToTab(page, 'Track', '#tracking-tab');

    await expect(page.locator('.tracking-container')).toBeVisible();
  });

  test('tasks tab loads with content', async ({ page }) => {
    await gotoApp(page);
    await navigateToTab(page, 'Tasks', '#tasks-tab');

    await expect(page.locator('#tasks-tab .tasks-container')).toBeVisible();
    await expect(page.locator('#tasks-tab .scheduled-tasks-section')).toBeVisible();
  });

  test('queue tab loads with download and OCR sub-tabs', async ({ page }) => {
    await gotoApp(page);
    await navigateToTab(page, 'Queue', '#queue-tab');

    // Both sub-tab buttons present
    await expect(page.locator('#switch-download-queue')).toBeVisible();
    await expect(page.locator('#switch-ocr-queue')).toBeVisible();

    // Download queue visible by default
    await expect(page.locator('#download-queue-view')).toBeVisible();
    await expect(page.locator('#ocr-queue-view')).not.toBeVisible();

    // Switch to OCR
    await page.locator('#switch-ocr-queue').click();
    await page.waitForTimeout(300);
    await expect(page.locator('#ocr-queue-view')).toBeVisible();
    await expect(page.locator('#download-queue-view')).not.toBeVisible();

    // Switch back to Downloads
    await page.locator('#switch-download-queue').click();
    await page.waitForTimeout(300);
    await expect(page.locator('#download-queue-view')).toBeVisible();
  });

  test('settings tab loads with all sub-tabs', async ({ page }) => {
    await gotoApp(page);
    await navigateToTab(page, 'Settings', '#settings-tab');

    await expect(page.locator('.settings-tabs-nav')).toBeVisible();

    const subTabs = [
      'Providers',
      'Storage',
      'Matching',
      'Downloads',
      'PDF/OCR',
      'Appearance',
      'Account',
      'Advanced',
    ];

    for (const label of subTabs) {
      const btn = page.locator(
        `.settings-tabs-nav .settings-tab-btn:has(.nav-text:text("${label}"))`
      );
      await expect(btn).toBeVisible();
    }
  });

  test('settings sub-tabs are clickable and switch content', async ({ page }) => {
    await gotoApp(page);
    await navigateToTab(page, 'Settings', '#settings-tab');

    const subTabs = [
      'Providers',
      'Storage',
      'Matching',
      'Downloads',
      'PDF/OCR',
      'Appearance',
      'Account',
      'Advanced',
    ];

    for (const label of subTabs) {
      const btn = page.locator(
        `.settings-tabs-nav .settings-tab-btn:has(.nav-text:text("${label}"))`
      );
      await btn.click();
      await page.waitForTimeout(300);
      await expect(btn).toHaveClass(/active/);
    }
  });

  test('all nav tabs reveal their content panel', async ({ page }) => {
    await gotoApp(page);

    const tabs = [
      { label: 'Library', id: '#library-tab' },
      { label: 'Track', id: '#tracking-tab' },
      { label: 'Tasks', id: '#tasks-tab' },
      { label: 'Queue', id: '#queue-tab' },
      { label: 'Settings', id: '#settings-tab' },
    ];

    for (const tab of tabs) {
      await navigateToTab(page, tab.label, tab.id);
    }
  });
});

// ---------------------------------------------------------------------------
// Detail Pages (conditional — only run when data exists)
// ---------------------------------------------------------------------------
test.describe('Detail Pages', () => {
  test.beforeEach(async ({ page, request }) => {
    await login(page, request);
  });

  test('periodical detail page loads when library has periodicals', async ({ page }) => {
    await gotoApp(page);

    // Library renders periodical cards via JS — they're divs, not <a> links.
    // Cards with .stack-card are stacks; plain .periodical-card are periodicals.
    const card = page.locator('#periodicals-grid .periodical-card:not(.stack-card)').first();
    const hasCard = await card.isVisible().catch(() => false);
    test.skip(!hasCard, 'No periodicals in library — skipping detail page test');

    await card.click();
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#periodical-container')).toBeVisible();
    await expect(page.locator('#periodical-title')).toBeVisible();
    await expect(page.locator('.breadcrumb')).toBeVisible();
  });

  test('stack detail page loads when stacks exist', async ({ page, request }) => {
    const token = await getToken(request);
    const stacksRes = await request.get('/api/stacks', {
      headers: { Authorization: `Bearer ${token}` },
    });
    const data = await stacksRes.json();
    const stacksList = data.stacks || [];
    test.skip(stacksList.length === 0, 'No stacks — skipping detail page test');

    const slug = stacksList[0].slug;
    await page.goto(`/stacks/${slug}`);
    await page.waitForLoadState('networkidle');

    await expect(page.locator('#stack-container')).toBeVisible();
    await expect(page.locator('#stack-title')).toBeVisible();
    await expect(page.locator('.breadcrumb')).toBeVisible();
  });
});
