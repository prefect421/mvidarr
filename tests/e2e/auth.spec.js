// tests/e2e/auth.spec.js
const { test, expect } = require('@playwright/test');
const { login, logout, monitorConsoleErrors } = require('../utils/test-helpers');
const { testUsers } = require('../fixtures/test-data');

test.describe('Authentication Flow', () => {
  
  test.beforeEach(async ({ page }) => {
    // Monitor console errors
    const errors = monitorConsoleErrors(page, [
      'Failed to load resource', // Common in dev environments
      'favicon.ico' // Ignore favicon errors
    ]);
    
    // Store errors for later checking
    page.errors = errors;
  });

  test('should display login page', async ({ page }) => {
    await page.goto('/auth/login');
    
    // Check page loads correctly
    await expect(page).toHaveTitle(/MVidarr|Login/);
    
    // Check login form elements exist
    await expect(page.locator('input[name="username"], input[name="email"]')).toBeVisible();
    await expect(page.locator('input[name="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"], .btn-primary')).toBeVisible();
  });

  test('should login with valid credentials', async ({ page }) => {
    await page.goto('/auth/login');
    
    // Fill login form
    await page.fill('input[name="username"], input[name="email"]', testUsers.user.username);
    await page.fill('input[name="password"]', testUsers.user.password);
    
    // Submit form
    await page.click('button[type="submit"], .btn-primary');
    
    // Should redirect to dashboard
    await expect(page).toHaveURL('/');
    
    // Should see dashboard content
    await expect(page.locator('h1, h2, .dashboard-stats')).toBeVisible();
  });

  test('should show error with invalid credentials', async ({ page }) => {
    await page.goto('/auth/login');
    
    // Fill with invalid credentials
    await page.fill('input[name="username"], input[name="email"]', 'invaliduser');
    await page.fill('input[name="password"]', 'wrongpassword');
    
    // Submit form
    await page.click('button[type="submit"], .btn-primary');
    
    // Should show error message
    await expect(page.locator('.error, .alert-danger, .text-danger')).toBeVisible();
    
    // Should stay on login page
    await expect(page).toHaveURL(/\/(auth\/login|simple-login)/);
  });

  test('should logout successfully', async ({ page }) => {
    // First login
    await login(page, testUsers.user.username, testUsers.user.password);
    
    // Verify we're logged in
    await expect(page).toHaveURL('/');
    
    // Logout
    await logout(page);
    
    // Should redirect to login page
    await expect(page).toHaveURL(/\/(auth\/login|simple-login)/);
  });

  test('should redirect unauthenticated users to login', async ({ page }) => {
    // Try to access protected page without login
    await page.goto('/artists');
    
    // Should redirect to login
    await expect(page).toHaveURL(/\/(auth\/login|simple-login)/, { timeout: 10000 });
  });

  test('should handle logout button click', async ({ page }) => {
    // Login first
    await login(page, testUsers.user.username, testUsers.user.password);
    
    // Find and click logout button
    const logoutButton = page.locator('button:has-text("Logout"), a:has-text("Logout"), [data-action="logout"]');
    await expect(logoutButton).toBeVisible();
    await logoutButton.click();
    
    // Should redirect to login page
    await expect(page).toHaveURL(/\/(auth\/login|simple-login)/, { timeout: 10000 });
  });

  test('should preserve redirect URL after login', async ({ page }) => {
    // Try to access a specific page without being logged in
    await page.goto('/settings');
    
    // Should redirect to login with return URL
    await expect(page).toHaveURL(/\/(auth\/login|simple-login)/);
    
    // Login
    await page.fill('input[name="username"], input[name="email"]', testUsers.user.username);
    await page.fill('input[name="password"]', testUsers.user.password);
    await page.click('button[type="submit"], .btn-primary');
    
    // Should redirect to original page or dashboard
    await page.waitForLoadState('networkidle');
    const finalUrl = page.url();
    expect(finalUrl === '/settings' || finalUrl === '/').toBeTruthy();
  });

  test('should handle session timeout', async ({ page }) => {
    // Login
    await login(page, testUsers.user.username, testUsers.user.password);
    
    // Clear all cookies to simulate session timeout
    await page.context().clearCookies();
    
    // Try to access protected resource
    await page.goto('/api/artists/');
    
    // Should get authentication error or redirect
    const response = await page.waitForResponse(/api\/artists/);
    expect(response.status()).toBeGreaterThanOrEqual(401);
  });

  test.afterEach(async ({ page }) => {
    // Check for console errors
    if (page.errors && page.errors.length > 0) {
      console.warn('Console errors detected:', page.errors);
    }
  });
});