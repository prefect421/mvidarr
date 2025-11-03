/**
 * Example Test File
 * Demonstrates how to write Playwright tests for MVidarr
 *
 * This file shows common patterns and best practices
 */

import { test, expect } from '@playwright/test';
import { login, logout, waitForPageLoad } from './helpers';

/**
 * EXAMPLE 1: Basic Page Test
 * Tests that a page loads and contains expected content
 */
test.describe('Example: Basic Page Tests', () => {
  test('should load the dashboard', async ({ page }) => {
    // Login first (most pages require authentication)
    await login(page);

    // Navigate to the page
    await page.goto('/');

    // Verify the page loaded
    await expect(page).toHaveURL('/');

    // Verify content is visible
    await expect(page.locator('body')).toBeVisible();

    // Verify page title
    await expect(page).toHaveTitle(/MVidarr|Dashboard/i);
  });
});

/**
 * EXAMPLE 2: User Interaction Test
 * Tests clicking buttons and filling forms
 */
test.describe('Example: User Interaction Tests', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('should navigate using links', async ({ page }) => {
    await page.goto('/');

    // Find and click a link (adjust selector to match your actual UI)
    const videosLink = page.locator('a[href="/videos"]').first();

    // Check if link exists before clicking
    if (await videosLink.count() > 0) {
      await videosLink.click();

      // Verify navigation occurred
      await expect(page).toHaveURL('/videos');
    }
  });

  test('should fill and submit a form', async ({ page }) => {
    await page.goto('/some-form-page');

    // Fill form fields
    await page.fill('#field-name', 'Test Value');
    await page.selectOption('#dropdown', 'option-value');
    await page.check('#checkbox');

    // Submit form
    await page.click('button[type="submit"]');

    // Wait for response/redirect
    await page.waitForURL('/success-page');
  });
});

/**
 * EXAMPLE 3: API Test
 * Tests API endpoints directly
 */
test.describe('Example: API Tests', () => {
  test('should call API endpoint', async ({ request }) => {
    // Make GET request
    const response = await request.get('/api/health');

    // Verify response status
    expect(response.ok()).toBeTruthy();
    expect(response.status()).toBe(200);

    // Verify response data
    const data = await response.json();
    expect(data).toHaveProperty('status');
  });

  test('should handle POST request', async ({ request }) => {
    // Make POST request with data
    const response = await request.post('/api/some-endpoint', {
      data: {
        key: 'value',
        number: 123
      }
    });

    // Verify response
    expect([200, 201]).toContain(response.status());

    // Get response data
    const data = await response.json();
    expect(data).toBeTruthy();
  });
});

/**
 * EXAMPLE 4: Test with Setup and Teardown
 * Shows how to prepare and clean up test data
 */
test.describe('Example: Data Management Tests', () => {
  let testVideoId: number;

  test.beforeEach(async ({ request }) => {
    // Create test data before each test
    const response = await request.post('/api/videos', {
      data: {
        title: 'Test Video',
        artist: 'Test Artist'
      }
    });

    const data = await response.json();
    testVideoId = data.id;
  });

  test.afterEach(async ({ request }) => {
    // Clean up test data after each test
    if (testVideoId) {
      await request.delete(`/api/videos/${testVideoId}`);
    }
  });

  test('should work with test data', async ({ page }) => {
    await login(page);

    // Use the test data
    await page.goto(`/videos/${testVideoId}`);

    // Verify it loaded
    await expect(page.locator('h1')).toContainText('Test Video');
  });
});

/**
 * EXAMPLE 5: Testing Error States
 * Tests how the application handles errors
 */
test.describe('Example: Error Handling Tests', () => {
  test('should handle 404 errors', async ({ page }) => {
    await login(page);

    // Try to access non-existent page
    const response = await page.goto('/non-existent-page');

    // Verify 404 response
    expect(response?.status()).toBe(404);
  });

  test('should handle invalid form input', async ({ page }) => {
    await login(page);
    await page.goto('/some-form');

    // Submit form with invalid data
    await page.fill('#email', 'invalid-email');
    await page.click('button[type="submit"]');

    // Verify error message appears
    await expect(page.locator('.error-message')).toBeVisible();
  });
});

/**
 * EXAMPLE 6: Performance Testing
 * Measures page load times and performance
 */
test.describe('Example: Performance Tests', () => {
  test('should load page within acceptable time', async ({ page }) => {
    await login(page);

    const startTime = Date.now();
    await page.goto('/videos');
    await waitForPageLoad(page);
    const loadTime = Date.now() - startTime;

    // Verify load time is under 5 seconds
    expect(loadTime).toBeLessThan(5000);
  });

  test('should measure API response time', async ({ request }) => {
    const startTime = Date.now();
    await request.get('/api/health');
    const responseTime = Date.now() - startTime;

    // Verify response time is under 500ms
    expect(responseTime).toBeLessThan(500);
  });
});

/**
 * EXAMPLE 7: Conditional Testing
 * Tests that adapt based on page state
 */
test.describe('Example: Conditional Tests', () => {
  test('should handle optional elements', async ({ page }) => {
    await login(page);
    await page.goto('/');

    // Check if element exists before interacting
    const optionalButton = page.locator('#optional-button');

    if (await optionalButton.count() > 0) {
      await optionalButton.click();
      // Do something with the button
    } else {
      // Element doesn't exist, that's okay
      console.log('Optional element not found');
    }
  });
});

/**
 * EXAMPLE 8: Waiting Strategies
 * Different ways to wait for elements and actions
 */
test.describe('Example: Waiting Strategies', () => {
  test('should wait for elements', async ({ page }) => {
    await login(page);
    await page.goto('/');

    // Wait for specific element to appear
    await page.waitForSelector('.loading-indicator', { state: 'hidden' });

    // Wait for element to be visible
    await page.waitForSelector('.content', { state: 'visible' });

    // Wait for network to be idle
    await page.waitForLoadState('networkidle');

    // Wait for specific timeout
    await page.waitForTimeout(1000); // Use sparingly!
  });

  test('should wait for navigation', async ({ page }) => {
    await login(page);
    await page.goto('/');

    // Click and wait for navigation
    await Promise.all([
      page.waitForNavigation(),
      page.click('a[href="/videos"]')
    ]);

    await expect(page).toHaveURL('/videos');
  });
});

/**
 * EXAMPLE 9: Screenshot and Debug
 * Taking screenshots and debugging tests
 */
test.describe('Example: Screenshot Tests', () => {
  test('should take screenshot on failure', async ({ page }) => {
    await login(page);
    await page.goto('/');

    try {
      // This might fail
      await expect(page.locator('.non-existent')).toBeVisible();
    } catch (error) {
      // Take screenshot for debugging
      await page.screenshot({ path: 'failure-screenshot.png' });
      throw error;
    }
  });

  test('should take full page screenshot', async ({ page }) => {
    await login(page);
    await page.goto('/videos');

    // Take full page screenshot
    await page.screenshot({
      path: 'videos-page.png',
      fullPage: true
    });
  });
});

/**
 * EXAMPLE 10: Tagging Tests
 * Using tags to organize and filter tests
 */
test.describe('Example: Tagged Tests', () => {
  test('smoke test - critical functionality @smoke', async ({ page }) => {
    // Quick test of critical features
    await login(page);
    await page.goto('/');
    await expect(page.locator('body')).toBeVisible();
  });

  test('regression test - detailed verification @regression', async ({ page }) => {
    // More detailed test for regression testing
    await login(page);
    await page.goto('/videos');

    // Verify multiple elements
    await expect(page.locator('h1')).toBeVisible();
    await expect(page.locator('.video-list')).toBeVisible();
  });

  test('slow test - performance heavy @slow', async ({ page }) => {
    test.slow(); // Mark as slow test (3x timeout)

    await login(page);

    // This test might take longer
    await page.goto('/large-dataset');
    await page.waitForLoadState('networkidle');
  });
});

/*
 * HOW TO RUN THESE EXAMPLES:
 *
 * 1. Run all examples:
 *    npx playwright test tests/example.spec.ts
 *
 * 2. Run specific test:
 *    npx playwright test tests/example.spec.ts -g "should load the dashboard"
 *
 * 3. Run with specific tag:
 *    npx playwright test --grep @smoke
 *
 * 4. Run in headed mode (see browser):
 *    npx playwright test tests/example.spec.ts --headed
 *
 * 5. Run in debug mode:
 *    npx playwright test tests/example.spec.ts --debug
 *
 * 6. Run in UI mode:
 *    npx playwright test tests/example.spec.ts --ui
 */
