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
    
    // Check if we hit a login page
    const isLoginPage = await page.url().includes('login');
    if (isLoginPage) {
      console.log('Login page detected, attempting to login...');
      // Looking at main.py/config, the default admin is admin/adminadmin
      await page.fill('input[name="username"]', 'admin');
      await page.fill('input[name="password"]', 'adminadmin');
      
      console.log('Clicking login...');
      await Promise.all([
        page.waitForNavigation({ waitUntil: 'networkidle', timeout: 5000 }).catch(e => console.log('Navigation wait timed out, continuing...')),
        page.click('button[type="submit"]')
      ]);
      
      // Check if we're still on the login page (login failed)
      if (page.url().includes('login')) {
        console.log('Login may have failed, checking for error messages...');
        const errorMsg = await page.$('.error-message');
        if (errorMsg) {
          const text = await errorMsg.textContent();
          console.log(`Login error: ${text}`);
          // Fallback credentials just in case
          console.log('Trying fallback credentials...');
          await page.fill('input[name="username"]', 'admin');
          await page.fill('input[name="password"]', 'admin');
          await Promise.all([
            page.waitForNavigation({ waitUntil: 'networkidle', timeout: 5000 }).catch(e => {}),
            page.click('button[type="submit"]')
          ]);
        }
      }
    }
    
    console.log('Current URL:', page.url());
    
    // If we're at the root/index, we should be good
    if (!page.url().includes('login')) {
      console.log('Waiting for app to render...');
      await page.waitForTimeout(2000);
      
      // Force dark mode just to be absolutely certain (since it relies on class in themes.css)
      await page.evaluate(() => {
        if (!document.body.classList.contains('dark-mode')) {
          document.body.classList.add('dark-mode');
          // Also set theme data attribute if that's what's used
          document.documentElement.setAttribute('data-theme', 'dark');
        }
      });
      
      // Find the library tab button and click it
      const libraryTab = await page.$('.nav-btn[data-tab="library"]');
      if (libraryTab) {
        console.log('Clicking library tab explicitly...');
        await libraryTab.click();
      } else {
        console.log('Could not find library tab button, attempting evaluate click...');
        await page.evaluate(() => {
          const btns = Array.from(document.querySelectorAll('.nav-btn'));
          const libBtn = btns.find(b => b.textContent && b.textContent.toLowerCase().includes('library'));
          if (libBtn) libBtn.click();
        });
      }
      
      // Wait for content (like book covers) to fully load
      console.log('Waiting for library content to render...');
      await page.waitForTimeout(5000);
      
      console.log('Taking screenshot...');
      await page.screenshot({ 
        path: 'docs/screenshots/library.jpg',
        type: 'jpeg',
        quality: 90
      });
      console.log('Screenshot saved to docs/screenshots/library.jpg');
    } else {
      console.error('Still on login page! Cannot take library screenshot.');
      // Take a debug screenshot of the login page
      await page.screenshot({ path: 'debug-login.jpg' });
      console.log('Saved debug-login.jpg to see what went wrong');
    }
  } catch (error) {
    console.error('Failed to take screenshot:', error.message);
  } finally {
    await browser.close();
  }
})();
