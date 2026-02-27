const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1280, height: 1024 },
    colorScheme: 'dark'
  });
  
  const page = await context.newPage();
  
  try {
    console.log('Navigating to local app...');
    await page.goto('http://localhost:8000', { waitUntil: 'networkidle', timeout: 10000 });
    
    // Login
    if (page.url().includes('login')) {
      await page.fill('input[name="username"]', 'admin');
      await page.fill('input[name="password"]', 'adminadmin');
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle', timeout: 5000 }).catch(() => {}),
        page.click('button[type="submit"]')
      ]);
    }
    
    // Ensure dark mode
    await page.evaluate(() => {
      document.body.classList.add('dark-mode');
      document.documentElement.setAttribute('data-theme', 'dark');
    });
    
    // Click Settings tab
    console.log('Clicking settings...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.nav-btn'));
      const btn = btns.find(b => b.textContent && b.textContent.toLowerCase().includes('settings'));
      if (btn) btn.click();
    });
    
    await page.waitForTimeout(2000);
    
    console.log('Taking settings screenshot...');
    await page.screenshot({ path: 'settings.jpg', type: 'jpeg', quality: 90 });
    
    // Click Library tab
    console.log('Clicking library...');
    await page.evaluate(() => {
      const btns = Array.from(document.querySelectorAll('.nav-btn'));
      const btn = btns.find(b => b.textContent && b.textContent.toLowerCase().includes('library'));
      if (btn) btn.click();
    });
    
    await page.waitForTimeout(2000);
    
    console.log('Taking library screenshot...');
    await page.screenshot({ path: 'library.jpg', type: 'jpeg', quality: 90 });

  } catch (error) {
    console.error('Error:', error.message);
  } finally {
    await browser.close();
  }
})();
