/**
 * Playwright Configuration for MVidarr E2E Testing
 * Tests all frontend pages and API endpoints
 */

import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',

  // Run tests in parallel
  fullyParallel: true,

  // Fail the build on CI if you accidentally left test.only in the source code
  forbidOnly: !!process.env.CI,

  // Retry on CI only
  retries: process.env.CI ? 2 : 0,

  // Opt out of parallel tests on CI
  workers: process.env.CI ? 1 : undefined,

  // Reporter to use
  reporter: [
    ['html', { outputFolder: 'playwright-report' }],
    ['json', { outputFile: 'playwright-results.json' }],
    ['list']
  ],

  // Shared settings for all projects
  use: {
    // Base URL for the application
    baseURL: process.env.MVIDARR_BASE_URL || 'http://localhost:5000',

    // Collect trace when retrying the failed test
    trace: 'on-first-retry',

    // Screenshot on failure
    screenshot: 'only-on-failure',

    // Video on failure
    video: 'retain-on-failure',

    // Maximum time for test
    actionTimeout: 15000,
  },

  // Configure projects for major browsers
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },

    {
      name: 'firefox',
      use: { ...devices['Desktop Firefox'] },
    },

    {
      name: 'webkit',
      use: { ...devices['Desktop Safari'] },
    },

    // Mobile browsers
    {
      name: 'Mobile Chrome',
      use: { ...devices['Pixel 5'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 12'] },
    },
  ],

  // Run local dev server before starting the tests
  // Note: Assumes MVidarr is already running or set MVIDARR_BASE_URL
  // To run server automatically, uncomment and adjust path to venv:
  // webServer: process.env.CI ? undefined : {
  //   command: 'cd ../../ && source venv/bin/activate && python3 fastapi_app.py',
  //   url: 'http://localhost:5000',
  //   reuseExistingServer: !process.env.CI,
  //   timeout: 120 * 1000, // 2 minutes
  // },
});
