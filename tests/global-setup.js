// tests/global-setup.js
const { chromium } = require('@playwright/test');

/**
 * Global setup for MVidarr Playwright tests
 * Runs once before all tests
 */
async function globalSetup(config) {
  console.log('🚀 Starting MVidarr E2E Test Suite Global Setup');
  
  // Check if MVidarr is running
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  try {
    console.log('🔍 Checking if MVidarr is accessible...');
    await page.goto(config.projects[0].use.baseURL || 'http://localhost:5000', {
      timeout: 30000,
      waitUntil: 'networkidle'
    });
    
    // Check if we can reach the login or dashboard page
    const isAccessible = await page.locator('body').isVisible();
    if (!isAccessible) {
      throw new Error('MVidarr application is not accessible');
    }
    
    console.log('✅ MVidarr is accessible and ready for testing');
    
    // Create test data directory if needed
    console.log('📁 Setting up test environment...');
    
    // You can add more setup logic here like:
    // - Creating test user accounts
    // - Setting up test data
    // - Clearing previous test artifacts
    
    console.log('✅ Global setup completed successfully');
    
  } catch (error) {
    console.error('❌ Global setup failed:', error.message);
    console.error('Please ensure MVidarr is running on http://localhost:5000');
    throw error;
  } finally {
    await browser.close();
  }
}

module.exports = globalSetup;