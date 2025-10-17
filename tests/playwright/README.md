# MVidarr Playwright E2E Tests

Comprehensive end-to-end testing suite for MVidarr using Playwright. Tests all frontend pages, API endpoints, and authentication flows.

## 📋 Test Coverage

### Authentication Tests (`auth.spec.ts`)
- ✅ Login/logout flows
- ✅ Session management
- ✅ Protected page access
- ✅ Admin authentication
- ✅ 2FA setup and verification
- ✅ Invalid credential handling
- ✅ Concurrent login attempts

### Page Navigation Tests (`pages.spec.ts`)
- ✅ All public pages (login, health, manifest)
- ✅ Main application pages (dashboard, videos, artists, playlists)
- ✅ Service integration pages (YouTube, Spotify, Last.fm, Lidarr)
- ✅ Admin pages (dashboard, users, user management)
- ✅ API proxy endpoints
- ✅ Development endpoints
- ✅ Page performance checks
- ✅ Page accessibility (titles)
- ✅ Navigation flows (links, back/forward buttons)

### API Endpoint Tests (`api.spec.ts`)
- ✅ Health and status APIs
- ✅ Videos API (CRUD, search, pagination)
- ✅ Artists API (CRUD, search, related videos)
- ✅ Playlists API (CRUD, playlist videos)
- ✅ Jobs API (list, analytics, queue stats)
- ✅ Metadata enrichment API
- ✅ Analytics API (dashboard, health, trending)
- ✅ Settings API
- ✅ Admin API (users, audit logs, system status)
- ✅ Advanced search API
- ✅ Service integration APIs (Spotify, Last.fm, YouTube, Lidarr)
- ✅ Bulk operations APIs
- ✅ Image processing APIs
- ✅ Genres API
- ✅ Music recommendations API
- ✅ API Gateway management
- ✅ Error handling (404, 405, malformed requests)
- ✅ Rate limiting
- ✅ Content type validation

## 🚀 Setup

### Prerequisites
- Node.js 18+ installed
- MVidarr application running on port 5000 (or set `MVIDARR_BASE_URL` environment variable)
- Valid admin credentials (default: admin/mvidarr)

### Installation

```bash
cd tests/playwright
npm install
npx playwright install
```

### Configuration

Edit `playwright.config.ts` to customize:
- Base URL (default: http://localhost:5000)
- Test timeout
- Browser configurations
- Report settings

Environment variables:
```bash
export MVIDARR_BASE_URL=http://localhost:5000  # Override base URL
export CI=true                                  # Enable CI mode
```

## 🧪 Running Tests

### Run all tests
```bash
npm test
```

### Run tests in headed mode (see browser)
```bash
npm run test:headed
```

### Run tests in debug mode
```bash
npm run test:debug
```

### Run tests in UI mode (interactive)
```bash
npm run test:ui
```

### Run specific browser
```bash
npm run test:chromium
npm run test:firefox
npm run test:webkit
```

### Run mobile tests
```bash
npm run test:mobile
```

### Run specific test suite
```bash
npm run test:auth      # Authentication tests only
npm run test:pages     # Page navigation tests only
npm run test:api       # API endpoint tests only
```

### Run tests with tags
```bash
npm run test:smoke       # Smoke tests only
npm run test:regression  # Regression tests only
```

### Generate test code
```bash
npm run codegen
```

## 📊 Viewing Results

### View HTML report
```bash
npm run report
```

The HTML report includes:
- Test results summary
- Failed test screenshots
- Test execution videos
- Detailed trace logs

Reports are saved in `playwright-report/` directory.

## 📁 Test Structure

```
tests/playwright/
├── playwright.config.ts    # Playwright configuration
├── package.json           # NPM dependencies and scripts
├── README.md             # This file
└── tests/
    ├── auth.spec.ts      # Authentication tests
    ├── pages.spec.ts     # Page navigation tests
    └── api.spec.ts       # API endpoint tests
```

## 🔧 Test Configuration

### Browsers Tested
- ✅ Chromium (Desktop Chrome)
- ✅ Firefox (Desktop)
- ✅ WebKit (Desktop Safari)
- ✅ Mobile Chrome (Pixel 5)
- ✅ Mobile Safari (iPhone 12)

### Test Timeouts
- Action timeout: 15 seconds
- Navigation timeout: 30 seconds
- Test timeout: 60 seconds

### Retries
- CI mode: 2 retries
- Local mode: 0 retries

### Artifacts
- Screenshots: On failure only
- Videos: On failure only
- Traces: On first retry

## 📝 Writing New Tests

### Basic test structure
```typescript
import { test, expect } from '@playwright/test';

test('my test', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveTitle(/MVidarr/);
});
```

### Authentication helper
```typescript
import { Page } from '@playwright/test';

async function login(page: Page) {
  await page.goto('/auth/login');
  await page.fill('#username', 'admin');
  await page.fill('#password', 'mvidarr');
  await page.click('button[type="submit"]');
  await page.waitForURL('/');
}

test('protected page', async ({ page }) => {
  await login(page);
  await page.goto('/settings');
  await expect(page).toHaveURL('/settings');
});
```

### API testing
```typescript
test('API endpoint', async ({ request }) => {
  const response = await request.get('/api/health');
  expect(response.ok()).toBeTruthy();

  const data = await response.json();
  expect(data).toHaveProperty('status');
});
```

## 🐛 Debugging Tests

### Debug specific test
```bash
npx playwright test tests/auth.spec.ts --debug
```

### Run with trace viewer
```bash
npx playwright test --trace on
npx playwright show-trace trace.zip
```

### Run with browser console logs
```bash
PWDEBUG=console npx playwright test
```

### Take screenshot during test
```typescript
await page.screenshot({ path: 'screenshot.png' });
```

## 🔄 Continuous Integration

### GitHub Actions Example
```yaml
name: Playwright Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-node@v3
        with:
          node-version: 18
      - name: Install dependencies
        run: |
          cd tests/playwright
          npm ci
          npx playwright install --with-deps
      - name: Run tests
        run: |
          cd tests/playwright
          npm test
        env:
          CI: true
      - uses: actions/upload-artifact@v3
        if: always()
        with:
          name: playwright-report
          path: tests/playwright/playwright-report/
          retention-days: 30
```

## 📈 Test Metrics

### Current Test Coverage
- **Total Tests**: 100+
- **Authentication Tests**: 15
- **Page Tests**: 50+
- **API Tests**: 40+

### Success Criteria
- All tests pass on Chromium
- 95%+ pass rate on Firefox and WebKit
- Page load times < 5 seconds
- API response times < 500ms
- Zero critical accessibility issues

## 🤝 Contributing

### Adding New Tests
1. Create new test file in `tests/` directory
2. Follow existing test patterns
3. Include proper test descriptions
4. Add tags for smoke/regression testing
5. Update this README with new test coverage

### Test Guidelines
- ✅ Use descriptive test names
- ✅ Keep tests independent and isolated
- ✅ Use proper selectors (prefer data-testid)
- ✅ Add comments for complex logic
- ✅ Handle async operations properly
- ✅ Clean up test data after tests
- ✅ Use beforeEach/afterEach hooks appropriately

## 📚 Resources

- [Playwright Documentation](https://playwright.dev)
- [Playwright Best Practices](https://playwright.dev/docs/best-practices)
- [Playwright API Reference](https://playwright.dev/docs/api/class-playwright)
- [MVidarr Documentation](../../README.md)

## 🆘 Troubleshooting

### Tests timing out
- Increase timeout in playwright.config.ts
- Check if MVidarr is running on correct port
- Verify network connectivity

### Authentication failures
- Verify credentials (default: admin/mvidarr)
- Check if user accounts exist in database
- Review session configuration

### Browser not launching
```bash
npx playwright install --with-deps
```

### Port conflicts
```bash
export MVIDARR_BASE_URL=http://localhost:5001  # Use different port
```

### Database issues
- Ensure test database is properly seeded
- Check database connection in MVidarr config
- Review migration status

## 📞 Support

For issues or questions:
- Open an issue on GitHub
- Check MVidarr documentation
- Review Playwright troubleshooting guide

---

**Last Updated**: 2025-10-16
**Test Suite Version**: 1.0.0
**MVidarr Version**: 0.9.9
