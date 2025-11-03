/**
 * Test Helper Functions
 * Shared utilities and helpers for Playwright tests
 */

import { Page, APIRequestContext, expect } from '@playwright/test';

/**
 * Authentication Helpers
 */

export interface LoginCredentials {
  username: string;
  password: string;
}

export const DEFAULT_CREDENTIALS: LoginCredentials = {
  username: 'admin',
  password: 'mvidarr'
};

/**
 * Login to MVidarr via the web interface
 */
export async function login(
  page: Page,
  credentials: LoginCredentials = DEFAULT_CREDENTIALS
): Promise<void> {
  await page.goto('/auth/login');
  await page.fill('#username', credentials.username);
  await page.fill('#password', credentials.password);
  await page.click('button[type="submit"]');

  // Wait for redirect to dashboard
  await page.waitForURL('/', { timeout: 10000 });
}

/**
 * Logout from MVidarr
 */
export async function logout(page: Page): Promise<void> {
  await page.goto('/auth/logout');
  await page.waitForURL('/auth/login');
}

/**
 * Get authenticated API context with session cookie
 */
export async function getAuthenticatedAPIContext(
  request: APIRequestContext,
  credentials: LoginCredentials = DEFAULT_CREDENTIALS
): Promise<string> {
  const response = await request.post('/test-login', {
    data: credentials
  });

  const cookies = response.headers()['set-cookie'];
  return cookies || '';
}

/**
 * Check if user is authenticated
 */
export async function isAuthenticated(page: Page): Promise<boolean> {
  const url = page.url();

  if (url.includes('/auth/login')) {
    return false;
  }

  // Try to access protected page
  const response = await page.goto('/settings');

  if (response) {
    return response.status() === 200;
  }

  return false;
}

/**
 * Navigation Helpers
 */

/**
 * Navigate to page and wait for load
 */
export async function navigateToPage(
  page: Page,
  path: string,
  options?: { waitForSelector?: string; timeout?: number }
): Promise<void> {
  await page.goto(path);

  if (options?.waitForSelector) {
    await page.waitForSelector(options.waitForSelector, {
      timeout: options.timeout || 5000
    });
  } else {
    await page.waitForLoadState('networkidle');
  }
}

/**
 * Wait for page to be fully loaded
 */
export async function waitForPageLoad(page: Page): Promise<void> {
  await page.waitForLoadState('networkidle');
  await page.waitForLoadState('domcontentloaded');
}

/**
 * Data Helpers
 */

/**
 * Generate random test data
 */
export function generateTestData(type: 'video' | 'artist' | 'playlist'): any {
  const timestamp = Date.now();

  switch (type) {
    case 'video':
      return {
        title: `Test Video ${timestamp}`,
        artist: `Test Artist ${timestamp}`,
        youtube_id: `test_${timestamp}`,
        description: `Test video created at ${timestamp}`
      };

    case 'artist':
      return {
        name: `Test Artist ${timestamp}`,
        imvdb_id: `test_${timestamp}`,
        description: `Test artist created at ${timestamp}`
      };

    case 'playlist':
      return {
        name: `Test Playlist ${timestamp}`,
        description: `Test playlist created at ${timestamp}`,
        is_public: true
      };

    default:
      return {};
  }
}

/**
 * Clean up test data
 */
export async function cleanupTestData(
  request: APIRequestContext,
  type: 'video' | 'artist' | 'playlist',
  ids: number[]
): Promise<void> {
  const endpoints = {
    video: '/api/videos',
    artist: '/api/artists',
    playlist: '/api/playlists'
  };

  const endpoint = endpoints[type];

  for (const id of ids) {
    try {
      await request.delete(`${endpoint}/${id}`);
    } catch (e) {
      // Ignore errors during cleanup
      console.log(`Failed to cleanup ${type} ${id}: ${e}`);
    }
  }
}

/**
 * API Helpers
 */

/**
 * Check API health
 */
export async function checkAPIHealth(
  request: APIRequestContext
): Promise<boolean> {
  try {
    const response = await request.get('/api/health');
    return response.ok();
  } catch (e) {
    return false;
  }
}

/**
 * Wait for API to be ready
 */
export async function waitForAPIReady(
  request: APIRequestContext,
  maxAttempts: number = 30,
  delayMs: number = 1000
): Promise<void> {
  for (let i = 0; i < maxAttempts; i++) {
    if (await checkAPIHealth(request)) {
      return;
    }

    await new Promise(resolve => setTimeout(resolve, delayMs));
  }

  throw new Error('API did not become ready in time');
}

/**
 * Make authenticated API request
 */
export async function authenticatedRequest(
  request: APIRequestContext,
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH',
  endpoint: string,
  options?: {
    data?: any;
    params?: Record<string, string>;
    headers?: Record<string, string>;
  }
) {
  const url = new URL(endpoint, 'http://localhost:5000');

  if (options?.params) {
    Object.entries(options.params).forEach(([key, value]) => {
      url.searchParams.append(key, value);
    });
  }

  const requestOptions: any = {
    headers: options?.headers || {}
  };

  if (options?.data) {
    requestOptions.data = options.data;
  }

  switch (method) {
    case 'GET':
      return request.get(url.toString(), requestOptions);
    case 'POST':
      return request.post(url.toString(), requestOptions);
    case 'PUT':
      return request.put(url.toString(), requestOptions);
    case 'DELETE':
      return request.delete(url.toString(), requestOptions);
    case 'PATCH':
      return request.patch(url.toString(), requestOptions);
  }
}

/**
 * UI Helpers
 */

/**
 * Fill form field with retry
 */
export async function fillField(
  page: Page,
  selector: string,
  value: string,
  maxRetries: number = 3
): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      await page.fill(selector, value);
      return;
    } catch (e) {
      if (i === maxRetries - 1) throw e;
      await page.waitForTimeout(500);
    }
  }
}

/**
 * Click element with retry
 */
export async function clickElement(
  page: Page,
  selector: string,
  maxRetries: number = 3
): Promise<void> {
  for (let i = 0; i < maxRetries; i++) {
    try {
      await page.click(selector);
      return;
    } catch (e) {
      if (i === maxRetries - 1) throw e;
      await page.waitForTimeout(500);
    }
  }
}

/**
 * Wait for element to be visible
 */
export async function waitForElement(
  page: Page,
  selector: string,
  timeout: number = 5000
): Promise<void> {
  await page.waitForSelector(selector, {
    state: 'visible',
    timeout
  });
}

/**
 * Get element text
 */
export async function getElementText(
  page: Page,
  selector: string
): Promise<string> {
  await waitForElement(page, selector);
  return page.textContent(selector) || '';
}

/**
 * Check if element exists
 */
export async function elementExists(
  page: Page,
  selector: string
): Promise<boolean> {
  try {
    await page.waitForSelector(selector, { timeout: 1000 });
    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Screenshot Helpers
 */

/**
 * Take full page screenshot
 */
export async function takeFullScreenshot(
  page: Page,
  filename: string
): Promise<void> {
  await page.screenshot({
    path: filename,
    fullPage: true
  });
}

/**
 * Take element screenshot
 */
export async function takeElementScreenshot(
  page: Page,
  selector: string,
  filename: string
): Promise<void> {
  const element = await page.locator(selector);
  await element.screenshot({ path: filename });
}

/**
 * Wait Helpers
 */

/**
 * Wait for network to be idle
 */
export async function waitForNetworkIdle(
  page: Page,
  timeout: number = 5000
): Promise<void> {
  await page.waitForLoadState('networkidle', { timeout });
}

/**
 * Wait for specific time
 */
export async function wait(ms: number): Promise<void> {
  await new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Wait for condition to be true
 */
export async function waitForCondition(
  condition: () => Promise<boolean>,
  timeout: number = 5000,
  interval: number = 100
): Promise<void> {
  const startTime = Date.now();

  while (Date.now() - startTime < timeout) {
    if (await condition()) {
      return;
    }

    await wait(interval);
  }

  throw new Error('Condition not met within timeout');
}

/**
 * Assertion Helpers
 */

/**
 * Assert page has loaded successfully
 */
export async function assertPageLoaded(page: Page): Promise<void> {
  await expect(page.locator('body')).toBeVisible();
  await expect(page).not.toHaveURL(/\/auth\/login/);
}

/**
 * Assert API response is successful
 */
export async function assertAPISuccess(response: any): Promise<void> {
  expect(response.ok()).toBeTruthy();
  expect(response.status()).toBeGreaterThanOrEqual(200);
  expect(response.status()).toBeLessThan(300);
}

/**
 * Assert element contains text
 */
export async function assertElementContainsText(
  page: Page,
  selector: string,
  text: string
): Promise<void> {
  const element = page.locator(selector);
  await expect(element).toContainText(text);
}

/**
 * Performance Helpers
 */

/**
 * Measure page load time
 */
export async function measurePageLoadTime(
  page: Page,
  url: string
): Promise<number> {
  const startTime = Date.now();
  await page.goto(url);
  await page.waitForLoadState('networkidle');
  return Date.now() - startTime;
}

/**
 * Get performance metrics
 */
export async function getPerformanceMetrics(page: Page): Promise<any> {
  return page.evaluate(() => {
    const perfData = window.performance.timing;
    const pageLoadTime = perfData.loadEventEnd - perfData.navigationStart;
    const connectTime = perfData.responseEnd - perfData.requestStart;
    const renderTime = perfData.domComplete - perfData.domLoading;

    return {
      pageLoadTime,
      connectTime,
      renderTime,
      navigationStart: perfData.navigationStart,
      loadEventEnd: perfData.loadEventEnd
    };
  });
}

/**
 * Test Data Management
 */

/**
 * Create test video
 */
export async function createTestVideo(
  request: APIRequestContext,
  data?: Partial<any>
): Promise<number> {
  const videoData = {
    ...generateTestData('video'),
    ...data
  };

  const response = await request.post('/api/videos', {
    data: videoData
  });

  const result = await response.json();
  return result.id;
}

/**
 * Create test artist
 */
export async function createTestArtist(
  request: APIRequestContext,
  data?: Partial<any>
): Promise<number> {
  const artistData = {
    ...generateTestData('artist'),
    ...data
  };

  const response = await request.post('/api/artists', {
    data: artistData
  });

  const result = await response.json();
  return result.id;
}

/**
 * Create test playlist
 */
export async function createTestPlaylist(
  request: APIRequestContext,
  data?: Partial<any>
): Promise<number> {
  const playlistData = {
    ...generateTestData('playlist'),
    ...data
  };

  const response = await request.post('/api/playlists', {
    data: playlistData
  });

  const result = await response.json();
  return result.id;
}

/**
 * Utility Functions
 */

/**
 * Generate random string
 */
export function randomString(length: number = 10): string {
  const chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  let result = '';

  for (let i = 0; i < length; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }

  return result;
}

/**
 * Generate random number
 */
export function randomNumber(min: number = 0, max: number = 1000): number {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/**
 * Sleep for specified duration
 */
export function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}
