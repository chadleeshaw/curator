// @ts-check
const { test, expect } = require('@playwright/test');
const http = require('http');
const fs = require('fs');
const path = require('path');

const REPO_ROOT = path.resolve(__dirname, '../..');

/**
 * Serve the repo so the fixture can import the real library module.
 * @returns {Promise<{server: import('http').Server, origin: string}>}
 */
function startStaticServer() {
  const server = http.createServer((req, res) => {
    const urlPath = decodeURIComponent(new URL(req.url || '/', 'http://127.0.0.1').pathname);
    const filePath = path.resolve(REPO_ROOT, `.${urlPath}`);
    if (filePath !== REPO_ROOT && !filePath.startsWith(`${REPO_ROOT}${path.sep}`)) {
      res.writeHead(403);
      res.end();
      return;
    }
    fs.readFile(filePath, (err, data) => {
      if (err) {
        res.writeHead(404);
        res.end('not found');
        return;
      }
      const type = filePath.endsWith('.js')
        ? 'text/javascript'
        : filePath.endsWith('.html')
          ? 'text/html'
          : 'application/octet-stream';
      res.writeHead(200, { 'Content-Type': type });
      res.end(data);
    });
  });

  return new Promise((resolve) => {
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      if (!address || typeof address === 'string') {
        throw new Error('static server has no port');
      }
      resolve({ server, origin: `http://127.0.0.1:${address.port}` });
    });
  });
}

const WEEKLY_STACK = {
  id: 1,
  name: 'Weekly Stack',
  slug: 'weekly-stack',
  member_count: 2,
  description: '',
  preview_covers: [],
};

const PERIODICALS = [
  {
    id: 1,
    title: 'Alpha Weekly',
    language: 'French',
    stack_id: 1,
    issue_date: '2024-01-01',
    issue_count: 1,
    metadata: { category: 'Magazines' },
  },
  {
    id: 2,
    title: 'Beta Weekly',
    language: 'English',
    stack_id: 1,
    issue_date: '2024-02-01',
    issue_count: 1,
    metadata: { category: 'Magazines' },
  },
  {
    id: 3,
    title: 'Gamma Solo',
    language: 'French',
    stack_id: null,
    issue_date: '2024-03-01',
    issue_count: 1,
    metadata: { category: 'Magazines' },
  },
  {
    id: 4,
    title: 'Delta Notes',
    language: '',
    stack_id: 1,
    issue_date: '2024-04-01',
    issue_count: 1,
    metadata: { category: 'Magazines' },
  },
];

test.describe('Library language filter', () => {
  /** @type {import('http').Server} */
  let server;
  /** @type {string} */
  let origin;

  test.beforeAll(async () => {
    const started = await startStaticServer();
    server = started.server;
    origin = started.origin;
  });

  test.afterAll(async () => {
    await new Promise((resolve) => server.close(resolve));
  });

  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('auth_token', 'test-token');
    });
    await page.route('**/api/periodicals/languages', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          languages: [
            { language: '', count: 3 },
            { language: '   ', count: 1 },
            { language: 'English', count: 10 },
            { language: 'French', count: 2 },
          ],
        }),
      })
    );
  });

  test('blank language is labeled English and its count is merged', async ({ page }) => {
    await page.goto(`${origin}/tests/playwright/fixtures/library-language.html`);
    await page.waitForFunction(() => window.__library);

    await page.evaluate(() => window.__library.populateLanguageDropdown());

    const options = page.locator('#library-language-filter option');
    await expect(options).toHaveText(['All', 'English (14)', 'French (2)']);
    const values = await options.evaluateAll((nodes) => nodes.map((node) => node.value));
    expect(values).toEqual(['all', 'English', 'French']);
  });

  test('selecting a language shows periodicals instead of the stack', async ({ page }) => {
    await page.goto(`${origin}/tests/playwright/fixtures/library-language.html`);
    await page.waitForFunction(() => window.__library);

    await page.evaluate(
      ({ periodicals, stack }) => {
        const library = window.__library;
        library.periodicalsLoaded = true;
        library.allStacks = [stack];
        library.allPeriodicals = periodicals;
        library.filterManager.languageFilter = 'all';
        library.applyFiltersAndRender();
      },
      { periodicals: PERIODICALS, stack: WEEKLY_STACK }
    );

    await expect(page.locator('#periodicals-grid .stack-card')).toHaveCount(1);
    await expect(page.locator('#periodicals-grid .periodical-card:not(.stack-card)')).toHaveCount(1);
    await expect(page.locator('#periodicals-grid h4')).toHaveText(['Weekly Stack', 'Gamma Solo']);

    await page.evaluate(() => {
      window.__library.filterManager.languageFilter = 'French';
      window.__library.applyFiltersAndRender();
    });

    await expect(page.locator('#periodicals-grid .stack-card')).toHaveCount(0);
    await expect(page.locator('#periodicals-grid h4')).toHaveText(['Alpha Weekly', 'Gamma Solo']);
    await expect(page.locator('#periodicals-grid .stack-badge-overlay')).toHaveCount(1);
    await expect(page.locator('#periodicals-grid .stack-badge-overlay')).toContainText('Weekly Stack');

    await page.evaluate(() => {
      window.__library.filterManager.languageFilter = 'English';
      window.__library.applyFiltersAndRender();
    });

    await expect(page.locator('#periodicals-grid .stack-card')).toHaveCount(0);
    await expect(page.locator('#periodicals-grid h4')).toHaveText(['Beta Weekly', 'Delta Notes']);
    await expect(page.locator('#periodicals-grid')).not.toContainText('No periodicals found');
  });
});
