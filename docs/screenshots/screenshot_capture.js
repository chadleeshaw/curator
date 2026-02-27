const { chromium } = require('playwright');

const DESKTOP_VIEWPORT = { width: 1280, height: 1024 };
const MOBILE_VIEWPORT = { width: 390, height: 844 };
const MOBILE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1';

const TABS = ['library', 'track', 'tasks', 'queue', 'settings'];

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

async function shot(page, filePath) {
  await page.screenshot({ path: filePath, type: 'jpeg', quality: 90 });
  console.log(`  Saved: ${filePath}`);
}

(async () => {
  const browser = await chromium.launch();

  // ── Desktop ───────────────────────────────────────────────────────────────
  console.log('\n=== Desktop (1280×1024) ===');
  {
    const context = await browser.newContext({ viewport: DESKTOP_VIEWPORT, colorScheme: 'dark' });
    const page = await context.newPage();
    await login(page);
    await enableDarkMode(page);

    for (const tab of TABS) {
      console.log(`  Tab: ${tab}`);
      await clickTab(page, tab);
      if (tab === 'library') await page.waitForTimeout(3000);
      await shot(page, `screenshots/desktop_${tab}.jpg`);
    }

    // Periodical detail page
    console.log('  Periodical detail page');
    try {
      await page.goto('http://localhost:8000/periodicals/PC%20Magazine?language=English', {
        waitUntil: 'networkidle',
        timeout: 10000,
      });
      await enableDarkMode(page);
      await page.waitForTimeout(1500);
      await shot(page, 'screenshots/desktop_periodical.jpg');
    } catch (e) {
      console.warn('  Periodical detail failed:', e.message);
    }

    await context.close();
  }

  // Desktop login (unauthenticated context)
  console.log('  Login page');
  try {
    const ctx = await browser.newContext({ viewport: DESKTOP_VIEWPORT, colorScheme: 'dark' });
    const pg = await ctx.newPage();
    await pg.goto('http://localhost:8000/login.html', { waitUntil: 'networkidle', timeout: 10000 });
    await pg.waitForTimeout(500);
    await shot(pg, 'screenshots/desktop_login.jpg');
    await ctx.close();
  } catch (e) {
    console.warn('  Login page failed:', e.message);
  }

  // ── Mobile ────────────────────────────────────────────────────────────────
  console.log('\n=== Mobile (390×844) ===');
  {
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
      await shot(page, `screenshots/mobile_${tab}.jpg`);
      // Extra full-page shot for settings to see provider buttons
      if (tab === 'settings') {
        await page.screenshot({
          path: 'screenshots/mobile_settings_full.jpg',
          type: 'jpeg',
          quality: 90,
          fullPage: true,
        });
        console.log('  Saved: screenshots/mobile_settings_full.jpg');
      }
    }

    await context.close();
  }

  // Mobile login
  console.log('  Login page');
  try {
    const ctx = await browser.newContext({
      viewport: MOBILE_VIEWPORT,
      colorScheme: 'dark',
      userAgent: MOBILE_UA,
    });
    const pg = await ctx.newPage();
    await pg.goto('http://localhost:8000/login.html', { waitUntil: 'networkidle', timeout: 10000 });
    await pg.waitForTimeout(500);
    await shot(pg, 'screenshots/mobile_login.jpg');
    await ctx.close();
  } catch (e) {
    console.warn('  Mobile login failed:', e.message);
  }

  await browser.close();
  console.log('\nDone.');
})();
