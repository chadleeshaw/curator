const {
  DESKTOP_VIEWPORT,
  MOBILE_VIEWPORT,
  MOBILE_UA,
  launch,
  login,
  enableDarkMode,
  clickTab,
  saveScreenshot,
} = require('./helpers');

const { chromium } = require('playwright');

const TABS = ['library', 'track', 'tasks', 'queue', 'settings'];

async function captureDesktop(browser) {
  console.log('\n=== Desktop (1280x1024) ===');
  const context = await browser.newContext({ viewport: DESKTOP_VIEWPORT, colorScheme: 'dark' });
  const page = await context.newPage();

  await login(page);
  await enableDarkMode(page);

  for (const tab of TABS) {
    console.log(`  Tab: ${tab}`);
    await clickTab(page, tab);
    if (tab === 'library') await page.waitForTimeout(3000);
    await saveScreenshot(page, `docs/screenshots/desktop_${tab}.jpg`);
    if (tab === 'settings') {
      await page.screenshot({
        path: 'docs/screenshots/desktop_settings_full.jpg',
        type: 'jpeg',
        quality: 90,
        fullPage: true,
      });
      console.log('  Saved: docs/screenshots/desktop_settings_full.jpg');
    }
  }

  try {
    console.log('  Periodical detail page');
    await page.goto('http://localhost:8000/periodicals/PC%20Magazine?language=English', {
      waitUntil: 'networkidle',
      timeout: 10000,
    });
    await enableDarkMode(page);
    await page.waitForTimeout(1500);
    await saveScreenshot(page, 'docs/screenshots/desktop_periodical.jpg');
  } catch (e) {
    console.warn('  Periodical detail failed:', e.message);
  }

  await context.close();
}

async function captureDesktopLogin(browser) {
  const context = await browser.newContext({ viewport: DESKTOP_VIEWPORT, colorScheme: 'dark' });
  const page = await context.newPage();
  try {
    await page.goto('http://localhost:8000/login.html', {
      waitUntil: 'networkidle',
      timeout: 10000,
    });
    await page.waitForTimeout(500);
    await saveScreenshot(page, 'docs/screenshots/desktop_login.jpg');
  } catch (e) {
    console.warn('  Desktop login page failed:', e.message);
  }
  await context.close();
}

async function captureMobile(browser) {
  console.log('\n=== Mobile (390x844) ===');
  const context = await browser.newContext({
    viewport: MOBILE_VIEWPORT,
    colorScheme: 'dark',
    userAgent: MOBILE_UA,
  });
  const page = await context.newPage();

  await login(page);
  await enableDarkMode(page);

  for (const tab of TABS) {
    console.log(`  Tab: ${tab}`);
    await clickTab(page, tab);
    if (tab === 'library') await page.waitForTimeout(3000);
    await saveScreenshot(page, `docs/screenshots/mobile_${tab}.jpg`);
    if (tab === 'settings') {
      await page.screenshot({
        path: 'docs/screenshots/mobile_settings_full.jpg',
        type: 'jpeg',
        quality: 90,
        fullPage: true,
      });
      console.log('  Saved: docs/screenshots/mobile_settings_full.jpg');
    }
  }

  await context.close();
}

async function captureMobileLogin(browser) {
  const context = await browser.newContext({
    viewport: MOBILE_VIEWPORT,
    colorScheme: 'dark',
    userAgent: MOBILE_UA,
  });
  const page = await context.newPage();
  try {
    await page.goto('http://localhost:8000/login.html', {
      waitUntil: 'networkidle',
      timeout: 10000,
    });
    await page.waitForTimeout(500);
    await saveScreenshot(page, 'docs/screenshots/mobile_login.jpg');
  } catch (e) {
    console.warn('  Mobile login page failed:', e.message);
  }
  await context.close();
}

(async () => {
  const browser = await chromium.launch();
  try {
    await captureDesktop(browser);
    console.log('  Login page');
    await captureDesktopLogin(browser);
    await captureMobile(browser);
    console.log('  Login page');
    await captureMobileLogin(browser);
  } finally {
    await browser.close();
    console.log('\nDone.');
  }
})();
