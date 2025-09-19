// tests/utils/test-helpers.js

/**
 * MVidarr Test Helper Functions
 * Common utilities for E2E testing
 */

/**
 * Login helper function
 * @param {import('@playwright/test').Page} page
 * @param {string} username
 * @param {string} password
 */
async function login(page, username = 'admin', password = 'mvidarr') {
  console.log(`🔐 Logging in as ${username}...`);
  
  // Navigate to login page if not already there
  const currentUrl = page.url();
  if (!currentUrl.includes('/auth/login')) {
    await page.goto('/auth/login');
  }
  
  // Wait for login form to be visible
  await page.waitForSelector('#loginForm', { timeout: 10000 });
  
  // Fill in credentials using MVidarr's actual form IDs
  await page.fill('#username', username);
  await page.fill('#password', password);
  
  // Submit form
  await page.click('button[type="submit"]');
  
  // Wait for either successful navigation or error message
  try {
    // Try to wait for navigation to dashboard
    await page.waitForURL('/', { timeout: 5000 });
  } catch (error) {
    // If navigation fails, check if we're still on login page with error
    const currentUrl = page.url();
    if (currentUrl.includes('/auth/login')) {
      // Check for error messages
      const errorElement = page.locator('.error, .alert-danger, #loginMessage');
      if (await errorElement.isVisible()) {
        const errorText = await errorElement.textContent();
        throw new Error(`Login failed: ${errorText}`);
      }
      // If no error shown, credentials might be wrong
      throw new Error('Login failed: No navigation occurred and no error shown');
    }
    throw error;
  }
  
  console.log('✅ Login successful');
}

/**
 * Logout helper function
 * @param {import('@playwright/test').Page} page
 */
async function logout(page) {
  console.log('🚪 Logging out...');
  
  // Look for logout button in MVidarr's interface
  try {
    // Try different logout selectors that might exist in MVidarr
    const logoutSelectors = [
      'button:has-text("Logout")',
      'a:has-text("Logout")', 
      '.logout-btn',
      '[onclick*="logout"]',
      '#logout-button'
    ];
    
    let logoutElement = null;
    for (const selector of logoutSelectors) {
      const element = page.locator(selector);
      if (await element.count() > 0) {
        logoutElement = element;
        break;
      }
    }
    
    if (logoutElement) {
      await logoutElement.click();
      
      // Wait for redirect to login page
      await page.waitForURL(/\/auth\/login/, { timeout: 10000 });
      console.log('✅ Logout successful');
    } else {
      // Fallback: Clear cookies and navigate to login
      console.log('⚠️ No logout button found, clearing session manually');
      await page.context().clearCookies();
      await page.goto('/auth/login');
      console.log('✅ Session cleared');
    }
  } catch (error) {
    console.log('⚠️ Logout error, clearing session manually:', error.message);
    await page.context().clearCookies();
    await page.goto('/auth/login');
  }
}

/**
 * Wait for loading indicators to disappear
 * @param {import('@playwright/test').Page} page
 */
async function waitForPageLoad(page) {
  // Wait for common loading indicators to disappear
  await page.waitForFunction(() => {
    const loadingElements = document.querySelectorAll('.loading, .spinner, [data-loading]');
    const disabledButtons = Array.from(document.querySelectorAll('.btn:disabled')).filter(btn => 
      btn.textContent && btn.textContent.toLowerCase().includes('loading')
    );
    return loadingElements.length === 0 && disabledButtons.length === 0;
  }, { timeout: 10000 });
}

/**
 * Fill form with data
 * @param {import('@playwright/test').Page} page
 * @param {Object} formData - Object with field names and values
 */
async function fillForm(page, formData) {
  for (const [field, value] of Object.entries(formData)) {
    await page.fill(`[name="${field}"], #${field}`, value);
  }
}

/**
 * Take screenshot with timestamp
 * @param {import('@playwright/test').Page} page
 * @param {string} name
 */
async function takeScreenshot(page, name) {
  const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
  await page.screenshot({ 
    path: `test-results/screenshots/${name}-${timestamp}.png`,
    fullPage: true 
  });
}

/**
 * Wait for API response
 * @param {import('@playwright/test').Page} page
 * @param {string} urlPattern
 * @param {number} timeout
 */
async function waitForApiResponse(page, urlPattern, timeout = 10000) {
  return await page.waitForResponse(
    response => response.url().includes(urlPattern) && response.status() === 200,
    { timeout }
  );
}

/**
 * Check for console errors
 * @param {import('@playwright/test').Page} page
 * @param {Array} allowedErrors - Array of error messages to ignore
 */
function monitorConsoleErrors(page, allowedErrors = []) {
  const errors = [];
  
  page.on('console', msg => {
    if (msg.type() === 'error') {
      const errorText = msg.text();
      if (!allowedErrors.some(allowed => errorText.includes(allowed))) {
        errors.push(errorText);
      }
    }
  });
  
  return errors;
}

/**
 * Mock API response
 * @param {import('@playwright/test').Page} page
 * @param {string} url
 * @param {Object} response
 */
async function mockApiResponse(page, url, response) {
  await page.route(url, route => {
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(response)
    });
  });
}

module.exports = {
  login,
  logout,
  waitForPageLoad,
  fillForm,
  takeScreenshot,
  waitForApiResponse,
  monitorConsoleErrors,
  mockApiResponse
};