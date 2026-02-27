const { chromium } = require('playwright');

const DESKTOP_VIEWPORT = { width: 1280, height: 1024 };
const MOBILE_VIEWPORT = { width: 390, height: 844 };
const MOBILE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1';

async function launch(viewport, userAgent) {
  const browser = await chromium.launch();
  const contextOptions = { viewport, colorScheme: 'dark' };
  if (userAgent) contextOptions.userAgent = userAgent;
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();
  return { browser, context, page };
}

async function login(page) {
  await page.goto('http://localhost:8000', { waitUntil: 'networkidle', timeout: 15000 });
  if (page.url().includes('login')) {
    await page.fill('input[name="username"]', 'admin');
    await page.fill('input[name="password"]', 'adminadmin');
    await Promise.all([
      page.waitForNavigation({ waitUntil: 'networkidle', timeout: 10000 }).catch(() => {}),
      page.click('button[type="submit"]'),
    ]);
  }
  if (page.url().includes('login')) throw new Error('Login failed');
}

async function enableDarkMode(page) {
  await page.evaluate(() => {
    document.body.classList.add('dark-mode');
    document.documentElement.setAttribute('data-theme', 'dark');
  });
}

async function clickTab(page, tabName) {
  const clicked = await page.evaluate((name) => {
    const btns = Array.from(document.querySelectorAll('.nav-btn, [data-tab]'));
    const btn = btns.find(
      (b) =>
        b.dataset.tab === name ||
        (b.textContent &&
          b.textContent
            .trim()
            .toLowerCase()
            .replace(/[^a-z]/g, '')
            .includes(name))
    );
    if (btn) {
      btn.click();
      return true;
    }
    return false;
  }, tabName);
  if (!clicked) console.warn(`  Warning: could not find tab "${tabName}"`);
  await page.waitForTimeout(1500);
}

async function saveScreenshot(page, filePath) {
  await page.screenshot({ path: filePath, type: 'jpeg', quality: 90 });
  console.log(`  Saved: ${filePath}`);
}

module.exports = {
  DESKTOP_VIEWPORT,
  MOBILE_VIEWPORT,
  MOBILE_UA,
  launch,
  login,
  enableDarkMode,
  clickTab,
  saveScreenshot,
};
