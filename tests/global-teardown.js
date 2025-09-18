// tests/global-teardown.js

/**
 * Global teardown for MVidarr Playwright tests
 * Runs once after all tests complete
 */
async function globalTeardown(config) {
  console.log('🧹 Starting MVidarr E2E Test Suite Global Teardown');
  
  try {
    // Clean up test artifacts
    console.log('📁 Cleaning up test artifacts...');
    
    // You can add cleanup logic here like:
    // - Removing test user accounts
    // - Clearing test data
    // - Resetting database state
    // - Cleaning up uploaded files
    
    console.log('✅ Global teardown completed successfully');
    
  } catch (error) {
    console.error('❌ Global teardown failed:', error.message);
    // Don't throw error in teardown to avoid masking test failures
  }
}

module.exports = globalTeardown;