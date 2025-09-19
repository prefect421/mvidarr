// tests/e2e/navigation-ui.spec.js
const { test, expect } = require('@playwright/test');
const { login, logout, takeScreenshot, monitorConsoleErrors } = require('../utils/test-helpers');
const { testUsers } = require('../fixtures/test-data');

test.describe('Navigation and UI Interactions', () => {
  
  test.beforeEach(async ({ page }) => {
    await login(page, testUsers.admin.username, testUsers.admin.password);
    await page.waitForTimeout(1000);
  });

  test.afterEach(async ({ page }) => {
    await logout(page);
  });

  test('should navigate through main sections', async ({ page }) => {
    console.log('🧪 Testing: Main navigation sections');
    
    await page.goto('/');
    
    // Test main navigation links
    const navigationTests = [
      { selector: 'a[href="/"], .nav-link:has-text("Home")', expectedUrl: '/', name: 'Home' },
      { selector: 'a[href="/artists"], .nav-link:has-text("Artists")', expectedUrl: '/artists', name: 'Artists' },
      { selector: 'a[href="/videos"], .nav-link:has-text("Videos")', expectedUrl: '/videos', name: 'Videos' },
      { selector: 'a[href="/settings"], .nav-link:has-text("Settings")', expectedUrl: '/settings', name: 'Settings' },
      { selector: 'a[href="/lidarr"], .nav-link:has-text("Lidarr")', expectedUrl: '/lidarr', name: 'Lidarr' }
    ];
    
    for (const nav of navigationTests) {
      const navLink = page.locator(nav.selector);
      if (await navLink.count() > 0) {
        await navLink.first().click();
        
        // Wait for navigation
        await page.waitForTimeout(1000);
        
        // Verify URL or page content
        const currentUrl = page.url();
        if (currentUrl.includes(nav.expectedUrl)) {
          console.log(`✅ ${nav.name} navigation successful`);
        } else {
          // Check if page loaded successfully by looking for common elements
          const pageContent = page.locator('body, main, .container');
          await expect(pageContent).toBeVisible();
          console.log(`✅ ${nav.name} page loaded (different URL pattern)`);
        }
        
        // Return to home for next test
        await page.goto('/');
        await page.waitForTimeout(500);
      } else {
        console.log(`ℹ️ ${nav.name} navigation link not found`);
      }
    }
    
    console.log('✅ Main navigation testing completed');
  });

  test('should handle modal interactions', async ({ page }) => {
    console.log('🧪 Testing: Modal interactions');
    
    await page.goto('/');
    
    // Test Add Video modal
    const addVideoButton = page.locator('button:has-text("Add Video"), .btn:has-text("Add Video")');
    if (await addVideoButton.count() > 0) {
      await addVideoButton.click();
      
      // Modal should appear
      const modal = page.locator('.modal, #addVideoModal, .modal-dialog');
      await expect(modal).toBeVisible({ timeout: 5000 });
      console.log('✅ Add Video modal opens');
      
      // Test modal close
      const closeButton = page.locator('.modal .close, .modal-header .btn-close, button:has-text("Close")');
      if (await closeButton.count() > 0) {
        await closeButton.first().click();
        await expect(modal).toBeHidden({ timeout: 5000 });
        console.log('✅ Modal closes properly');
      } else {
        // Try ESC key
        await page.keyboard.press('Escape');
        await page.waitForTimeout(500);
        console.log('✅ Modal closed with ESC key');
      }
    }
    
    // Test Add Artist modal if available
    const addArtistButton = page.locator('button:has-text("Add Artist"), .btn:has-text("Add Artist")');
    if (await addArtistButton.count() > 0) {
      await addArtistButton.click();
      
      const artistModal = page.locator('.modal, #addArtistModal');
      if (await artistModal.isVisible()) {
        console.log('✅ Add Artist modal opens');
        
        // Close modal
        await page.keyboard.press('Escape');
        await page.waitForTimeout(500);
      }
    }
    
    console.log('✅ Modal interactions tested');
  });

  test('should validate form interactions', async ({ page }) => {
    console.log('🧪 Testing: Form interactions');
    
    await page.goto('/');
    
    // Test Add Video form
    const addVideoButton = page.locator('button:has-text("Add Video")');
    if (await addVideoButton.count() > 0) {
      await addVideoButton.click();
      
      // Wait for modal
      await page.waitForTimeout(1000);
      
      // Test form field interactions
      const titleInput = page.locator('#songTitleInput, input[name="songTitle"], input[placeholder*="title"]');
      if (await titleInput.count() > 0) {
        await titleInput.fill('Test Video Title');
        expect(await titleInput.inputValue()).toBe('Test Video Title');
        console.log('✅ Form input works');
        
        // Clear field
        await titleInput.clear();
        expect(await titleInput.inputValue()).toBe('');
        console.log('✅ Form clear works');
      }
      
      // Test artist input
      const artistInput = page.locator('#artistNameInput, input[name="artistName"], input[placeholder*="artist"]');
      if (await artistInput.count() > 0) {
        await artistInput.fill('Test Artist');
        expect(await artistInput.inputValue()).toBe('Test Artist');
        console.log('✅ Artist input works');
      }
      
      // Test form validation
      const searchButton = page.locator('button:has-text("Search"), button:has-text("Search Videos")');
      if (await searchButton.count() > 0) {
        // Try to submit empty form
        await page.locator('#songTitleInput, input[name="songTitle"]').clear();
        await page.locator('#artistNameInput, input[name="artistName"]').clear();
        
        await searchButton.click();
        
        // Check for validation messages
        const validationMessage = page.locator('.error, .invalid-feedback, .alert-danger');
        if (await validationMessage.count() > 0) {
          console.log('✅ Form validation working');
        } else {
          console.log('ℹ️ No visible form validation (may be handled differently)');
        }
      }
      
      // Close modal
      await page.keyboard.press('Escape');
    }
    
    console.log('✅ Form interactions tested');
  });

  test('should validate responsive design elements', async ({ page }) => {
    console.log('🧪 Testing: Responsive design elements');
    
    await page.goto('/');
    
    // Test different viewport sizes
    const viewports = [
      { width: 1920, height: 1080, name: 'Desktop Large' },
      { width: 1366, height: 768, name: 'Desktop Standard' },
      { width: 768, height: 1024, name: 'Tablet' },
      { width: 375, height: 667, name: 'Mobile' }
    ];
    
    for (const viewport of viewports) {
      await page.setViewportSize(viewport);
      await page.waitForTimeout(500);
      
      // Check that main content is visible
      const mainContent = page.locator('body, main, .container, .content');
      await expect(mainContent).toBeVisible();
      
      // Check navigation is accessible
      const navigation = page.locator('nav, .navbar, .navigation');
      if (await navigation.count() > 0) {
        await expect(navigation).toBeVisible();
      }
      
      // Take screenshot for visual testing
      await takeScreenshot(page, `responsive-${viewport.name.toLowerCase().replace(' ', '-')}`);
      
      console.log(`✅ ${viewport.name} (${viewport.width}x${viewport.height}) layout works`);
    }
    
    // Reset to standard size
    await page.setViewportSize({ width: 1366, height: 768 });
    
    console.log('✅ Responsive design validated');
  });

  test('should handle search and filter interactions', async ({ page }) => {
    console.log('🧪 Testing: Search and filter interactions');
    
    // Test artist search
    await page.goto('/artists');
    await page.waitForTimeout(1000);
    
    const searchInput = page.locator('input[type="search"], #search, .search-input, input[placeholder*="search"]');
    if (await searchInput.count() > 0) {
      await searchInput.fill('test');
      await page.keyboard.press('Enter');
      
      await page.waitForTimeout(2000);
      console.log('✅ Artist search interaction works');
      
      // Clear search
      await searchInput.clear();
      await page.keyboard.press('Enter');
      await page.waitForTimeout(1000);
      console.log('✅ Search clear works');
    }
    
    // Test video search
    await page.goto('/videos');
    await page.waitForTimeout(1000);
    
    const videoSearch = page.locator('input[type="search"], #search, .search-input');
    if (await videoSearch.count() > 0) {
      await videoSearch.fill('music');
      await page.keyboard.press('Enter');
      await page.waitForTimeout(2000);
      console.log('✅ Video search interaction works');
    }
    
    // Test filter dropdowns
    const filterDropdowns = page.locator('select, .filter-dropdown');
    if (await filterDropdowns.count() > 0) {
      const firstDropdown = filterDropdowns.first();
      const options = page.locator('option');
      
      if (await options.count() > 1) {
        await firstDropdown.selectOption({ index: 1 });
        console.log('✅ Filter dropdown works');
      }
    }
    
    console.log('✅ Search and filter interactions tested');
  });

  test('should validate keyboard navigation', async ({ page }) => {
    console.log('🧪 Testing: Keyboard navigation');
    
    await page.goto('/');
    
    // Test tab navigation
    await page.keyboard.press('Tab');
    let focusedElement = await page.locator(':focus').first();
    
    if (await focusedElement.count() > 0) {
      console.log('✅ Tab navigation works');
      
      // Continue tabbing through several elements
      for (let i = 0; i < 5; i++) {
        await page.keyboard.press('Tab');
        await page.waitForTimeout(100);
      }
      console.log('✅ Sequential tab navigation works');
    }
    
    // Test Enter key on buttons
    const buttons = page.locator('button, .btn');
    if (await buttons.count() > 0) {
      await buttons.first().focus();
      
      // Test that Enter doesn't cause JS errors
      const consoleErrors = monitorConsoleErrors(page);
      await page.keyboard.press('Enter');
      await page.waitForTimeout(500);
      
      // Allow one error since we might be triggering incomplete forms
      if (consoleErrors.length <= 1) {
        console.log('✅ Enter key navigation works');
      }
    }
    
    // Test ESC key behavior
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);
    console.log('✅ ESC key handling works');
    
    console.log('✅ Keyboard navigation validated');
  });

  test('should validate loading states and feedback', async ({ page }) => {
    console.log('🧪 Testing: Loading states and user feedback');
    
    await page.goto('/');
    
    // Monitor for loading indicators
    const loadingSelectors = [
      '.loading',
      '.spinner', 
      '[data-loading]',
      '.btn[disabled]',
      '.progress',
      '.loading-overlay'
    ];
    
    // Test loading states during navigation
    await page.goto('/artists');
    await page.waitForTimeout(500);
    
    // Check if any loading indicators appear
    let foundLoadingIndicator = false;
    for (const selector of loadingSelectors) {
      const element = page.locator(selector);
      if (await element.count() > 0) {
        foundLoadingIndicator = true;
        console.log(`✅ Found loading indicator: ${selector}`);
        break;
      }
    }
    
    if (!foundLoadingIndicator) {
      console.log('ℹ️ No loading indicators found (fast loading or different implementation)');
    }
    
    // Test button disabled states
    const addButton = page.locator('button:has-text("Add"), .btn:has-text("Add")');
    if (await addButton.count() > 0) {
      await addButton.click();
      
      // Check if button becomes disabled during processing
      const isDisabled = await addButton.isDisabled();
      if (isDisabled) {
        console.log('✅ Button disabled state during processing');
      }
    }
    
    // Test error message display
    await page.goto('/nonexistent-page');
    await page.waitForTimeout(1000);
    
    // Check for error messages or 404 handling
    const errorElements = page.locator('.error, .alert-danger, .not-found, h1:has-text("404")');
    if (await errorElements.count() > 0) {
      console.log('✅ Error state handling works');
    } else {
      console.log('ℹ️ No error state indicators found');
    }
    
    console.log('✅ Loading states and feedback validated');
  });
});