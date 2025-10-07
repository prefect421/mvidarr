# MVidarr E2E Testing with Playwright

This directory contains comprehensive end-to-end tests for the MVidarr music video management system using Playwright.

## Overview

The test suite covers all critical user workflows and functionality:

- ✅ **Authentication** - Login, logout, session management
- ✅ **Dashboard** - Stats, downloads, navigation  
- ✅ **Artist Management** - Add, search, import, bulk operations
- 🔄 **Video Management** - Search, import, playlist (TODO)
- 🔄 **API Validation** - Endpoint testing (TODO)
- 🔄 **UI Interactions** - Navigation, modals, forms (TODO)

## Setup

### Prerequisites
- MVidarr service running on `http://localhost:5000`
- Node.js installed
- Test user account configured

### Installation
```bash
npm install
npm run test:install  # Install Playwright browsers
```

## Running Tests

### All Tests
```bash
npm test                 # Run all tests headless
npm run test:headed      # Run with browser UI
npm run test:debug       # Debug mode with DevTools
```

### Specific Test Suites
```bash
npm run test:auth        # Authentication tests only
npm run test:dashboard   # Dashboard functionality tests
npm run test:artists     # Artist management tests
npm run test:videos      # Video management tests
npm run test:navigation  # Navigation and UI tests
npm run test:api         # API endpoint validation tests
npm run test:fixes       # 0.9.8 bug fixes validation
npm run test:core        # Core functionality (auth, dashboard, artists)
npm run test:extended    # Extended functionality (videos, navigation, API)
```

### View Results
```bash
npm run test:report      # Open HTML test report
```

## Test Structure

```
tests/
├── e2e/                 # End-to-end test specs
│   ├── auth.spec.js     # Authentication flow tests
│   ├── dashboard.spec.js # Dashboard functionality tests
│   ├── artists.spec.js  # Artist management tests
│   ├── video-management.spec.js # Video search, import, playlist tests
│   ├── navigation-ui.spec.js # Navigation and UI interaction tests
│   ├── api-validation.spec.js # API endpoint validation tests
│   └── fixes-0.9.8.spec.js # 0.9.8 bug fixes validation tests
├── fixtures/            # Test data and mocks
│   └── test-data.js     # Test users, artists, videos, mock API responses
├── utils/               # Helper functions
│   └── test-helpers.js  # Login, navigation, form filling utilities
├── global-setup.js     # Global test setup
├── global-teardown.js  # Global test cleanup
└── README.md           # This file
```

## Test Configuration

Tests are configured via `playwright.config.js` with:

- **Multi-browser support**: Chrome, Firefox, Safari, Mobile
- **Automatic screenshots** on failure
- **Video recording** for failed tests
- **Trace collection** for debugging
- **HTML, JSON, and JUnit reports**

## Test Data

Test data is managed in `fixtures/test-data.js`:

```javascript
// Test users
testUsers.user = { username: 'testuser', password: 'testpass' }

// Test artists  
testArtists.taylorSwift = { name: 'Taylor Swift', imvdb_id: 'test_taylor_swift' }

// Mock API responses for isolated testing
mockResponses.imvdbArtistSearch = { success: true, results: [...] }
```

## Helper Functions

Common test operations are abstracted in `utils/test-helpers.js`:

```javascript
await login(page, username, password)    // Authenticate user
await logout(page)                       // Sign out user  
await waitForPageLoad(page)             // Wait for loading
await fillForm(page, formData)          // Fill form fields
await waitForApiResponse(page, pattern) // Wait for API calls
```

## Writing New Tests

### Basic Test Structure
```javascript
const { test, expect } = require('@playwright/test');
const { login } = require('../utils/test-helpers');

test.describe('Feature Name', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('should do something', async ({ page }) => {
    await page.goto('/feature');
    await expect(page.locator('h1')).toHaveText('Expected Title');
  });
});
```

### Best Practices
- **Use descriptive test names** that explain the expected behavior
- **Set up test data** in beforeEach hooks
- **Use page object patterns** for complex UI interactions  
- **Mock external APIs** to ensure test reliability
- **Test error scenarios** as well as happy paths
- **Keep tests independent** - no dependencies between tests

## Debugging Tests

### Debug Mode
```bash
npm run test:debug
```
This opens tests in debug mode with:
- Browser DevTools
- Step-through debugging
- Console logging
- Network inspection

### Screenshots and Videos
Failed tests automatically capture:
- Screenshots: `test-results/screenshots/`
- Videos: `test-results/videos/`  
- Traces: `test-results/traces/`

### Console Logging
Tests monitor console errors and warnings automatically. Check test output for JavaScript errors.

## CI/CD Integration

Tests are designed for CI/CD pipelines:

- **Parallel execution** across multiple workers
- **Retry logic** for flaky tests
- **Multiple report formats** (HTML, JSON, JUnit)
- **Docker-friendly** configuration

### GitHub Actions Example
```yaml
- name: Run E2E Tests
  run: |
    npm ci
    npm run test:install
    npm test
- name: Upload Test Results
  uses: actions/upload-artifact@v3
  with:
    name: playwright-report
    path: playwright-report/
```

## Test Coverage

Current coverage includes:

### ✅ Implemented
- **Authentication flows** (8 tests)
- **Dashboard functionality** (12 tests) 
- **Artist management** (12 tests)
- **Video management** (6 tests)
- **Navigation and UI** (6 tests)
- **API endpoint validation** (10 tests)
- **0.9.8 Bug fixes validation** (8 tests)

### 🔄 Planned
- Settings and configuration tests
- Performance and load tests
- Mobile-specific UI tests
- Error handling and edge cases
- Integration with external services

## Troubleshooting

### Common Issues

**Tests fail with authentication errors**
- Ensure test user account exists
- Check session timeout settings
- Verify credentials in test-data.js

**Browser launch fails**
- Run `npm run test:install` to install browsers
- Check system dependencies
- Verify Playwright installation

**Tests timeout waiting for elements**
- Increase timeout values in playwright.config.js
- Check if MVidarr service is running
- Verify element selectors are correct

**Network errors in tests**
- Ensure MVidarr is accessible on localhost:5000
- Check firewall and port configuration
- Verify API endpoints are responding

For more help, check the [Playwright documentation](https://playwright.dev/docs/intro) or review test output logs.