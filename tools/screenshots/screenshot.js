const {
  DESKTOP_VIEWPORT,
  launch,
  login,
  enableDarkMode,
  clickTab,
  saveScreenshot,
} = require('./helpers');

(async () => {
  const { browser, context, page } = await launch(DESKTOP_VIEWPORT);
  try {
    await login(page);
    await enableDarkMode(page);
    await clickTab(page, 'library');
    await page.waitForTimeout(5000);
    await saveScreenshot(page, 'docs/screenshots/desktop_library.jpg');
  } catch (error) {
    console.error('Failed to take screenshot:', error.message);
    await page.screenshot({ path: 'docs/screenshots/debug-login.jpg' });
  } finally {
    await context.close();
    await browser.close();
  }
})();
