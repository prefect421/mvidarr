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
async function login(page, username = 'testuser', password = 'testpass') {
  console.log(`🔐 Logging in as ${username}...`);
  
  // Navigate to login page if not already there
  const currentUrl = page.url();
  if (!currentUrl.includes('/auth/login') && !currentUrl.includes('/simple-login')) {
    await page.goto('/auth/login');
  }
  
  // Fill in credentials
  await page.fill('input[name="username"], input[name="email"]', username);
  await page.fill('input[name="password"]', password);
  
  // Submit form
  await page.click('button[type="submit"], .btn-primary');
  
  // Wait for navigation to dashboard
  await page.waitForURL('/', { timeout: 10000 });
  
  console.log('✅ Login successful');
}

/**
 * Logout helper function
 * @param {import('@playwright/test').Page} page
 */
async function logout(page) {
  console.log('🚪 Logging out...');
  
  // Look for logout button or link
  const logoutSelector = 'button:has-text("Logout"), a:has-text("Logout"), [data-action="logout"]';
  await page.click(logoutSelector);
  
  // Wait for redirect to login page
  await page.waitForURL(/\/(auth\/login|simple-login)/, { timeout: 5000 });
  
  console.log('✅ Logout successful');
}

/**
 * Wait for loading indicators to disappear
 * @param {import('@playwright/test').Page} page
 */
async function waitForPageLoad(page) {
  // Wait for common loading indicators to disappear
  await page.waitForFunction(() => {
    const loadingElements = document.querySelectorAll(
      '.loading, .spinner, [data-loading], .btn:disabled:has-text("Loading")'
    );
    return loadingElements.length === 0;
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