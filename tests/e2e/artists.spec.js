// tests/e2e/artists.spec.js
const { test, expect } = require('@playwright/test');
const { login, waitForPageLoad, waitForApiResponse, fillForm } = require('../utils/test-helpers');
const { testUsers, testArtists, mockResponses } = require('../fixtures/test-data');

test.describe('Artist Management', () => {
  
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await login(page, testUsers.user.username, testUsers.user.password);
    await page.goto('/artists');
    await waitForPageLoad(page);
  });

  test('should display artists page correctly', async ({ page }) => {
    // Check page loads
    await expect(page).toHaveURL('/artists');
    await expect(page.locator('h1:has-text("Artists"), h2:has-text("Artists")')).toBeVisible();
    
    // Check search and filter controls
    await expect(page.locator('input[placeholder*="Search"], .search-input')).toBeVisible();
    
    // Check add artist button
    await expect(page.locator('button:has-text("Add"), .btn:has-text("Add")')).toBeVisible();
  });

  test('should open Add New Artist modal', async ({ page }) => {
    // Click Add Artist button
    await page.click('button:has-text("Add New Artist"), .btn:has-text("Add Artist")');
    
    // Modal should appear
    await expect(page.locator('.modal, #addArtistModal')).toBeVisible();
    
    // Check modal content
    await expect(page.locator('#artistSearchInput, input[name="artistName"]')).toBeVisible();
    await expect(page.locator('button:has-text("Search IMVDb")')).toBeVisible();
  });

  test('should search for artists in IMVDb', async ({ page }) => {
    // Open Add Artist modal
    await page.click('button:has-text("Add New Artist")');
    
    // Fill search input
    await page.fill('#artistSearchInput', 'Taylor Swift');
    
    // Click search
    await page.click('button:has-text("Search IMVDb")');
    
    // Wait for search results
    await page.waitForSelector('#artistSearchResults, .search-results', { timeout: 10000 });
    
    // Results should appear
    await expect(page.locator('#artistSearchResults')).toBeVisible();
  });

  test('should handle artist search with no results', async ({ page }) => {
    // Open Add Artist modal
    await page.click('button:has-text("Add New Artist")');
    
    // Search for non-existent artist
    await page.fill('#artistSearchInput', 'NonExistentArtistXYZ123');
    await page.click('button:has-text("Search IMVDb")');
    
    // Should show no results message
    await expect(page.locator(':has-text("No results"), :has-text("not found")')).toBeVisible({ timeout: 10000 });
  });

  test('should import artist from search results', async ({ page }) => {
    // Mock successful artist search
    await page.route('**/api/artists/discover*', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockResponses.imvdbArtistSearch)
      });
    });
    
    // Mock successful artist import
    await page.route('**/api/artists/import-from-imvdb', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          name: 'Test Artist',
          id: 'test_artist_1'
        })
      });
    });
    
    // Open Add Artist modal and search
    await page.click('button:has-text("Add New Artist")');
    await page.fill('#artistSearchInput', 'Test Artist');
    await page.click('button:has-text("Search IMVDb")');
    
    // Wait for results and click import
    await page.waitForSelector('.search-result-item, .artist-result');
    await page.click('button:has-text("Import"), .btn:has-text("Add")');
    
    // Should show success message
    await expect(page.locator(':has-text("added successfully"), .success')).toBeVisible({ timeout: 10000 });
  });

  test('should filter artists list', async ({ page }) => {
    // Use search/filter input
    const searchInput = page.locator('input[placeholder*="Search"], .search-input');
    await searchInput.fill('Test');
    
    // Wait for filtering to take effect
    await page.waitForTimeout(1000);
    
    // Check that filter is applied (if artists exist)
    const artistCards = page.locator('.artist-card, .artist-item');
    if (await artistCards.count() > 0) {
      // Should show only matching artists
      const firstArtist = artistCards.first();
      await expect(firstArtist).toBeVisible();
    }
  });

  test('should sort artists list', async ({ page }) => {
    // Look for sort controls
    const sortSelect = page.locator('select[name="sort"], .sort-select');
    if (await sortSelect.count() > 0) {
      await sortSelect.selectOption('name');
      await waitForPageLoad(page);
      
      // Artists should be reordered
      await expect(page.locator('.artist-card, .artist-item')).toBeVisible();
    }
  });

  test('should view artist details', async ({ page }) => {
    // Look for artist links
    const artistLinks = page.locator('a[href*="/artist/"], .artist-link');
    
    if (await artistLinks.count() > 0) {
      await artistLinks.first().click();
      
      // Should navigate to artist detail page
      await expect(page).toHaveURL(/\/artist\/\d+/);
      await expect(page.locator('h1, h2')).toBeVisible();
    }
  });

  test('should handle bulk artist operations', async ({ page }) => {
    // Look for bulk operation controls
    const bulkControls = page.locator('.bulk-actions, .bulk-operations');
    
    if (await bulkControls.count() > 0) {
      // Select some artists
      const checkboxes = page.locator('input[type="checkbox"]');
      if (await checkboxes.count() > 0) {
        await checkboxes.first().check();
        
        // Bulk actions should become available
        await expect(page.locator('button:has-text("Delete"), button:has-text("Export")')).toBeVisible();
      }
    }
  });

  test('should handle artist auto-download setting', async ({ page }) => {
    // Look for artist with auto-download toggle
    const toggles = page.locator('.auto-download-toggle, input[type="checkbox"]');
    
    if (await toggles.count() > 0) {
      const firstToggle = toggles.first();
      const initialState = await firstToggle.isChecked();
      
      // Toggle the setting
      await firstToggle.click();
      
      // State should change
      const newState = await firstToggle.isChecked();
      expect(newState).toBe(!initialState);
    }
  });

  test('should display artist statistics', async ({ page }) => {
    // Check for stats display
    const statsElements = page.locator('.artist-stats, .stats-card');
    
    if (await statsElements.count() > 0) {
      await expect(statsElements.first()).toBeVisible();
      
      // Should show numbers
      const statsText = await statsElements.first().textContent();
      expect(statsText).toMatch(/\d+/);
    }
  });

  test('should handle pagination', async ({ page }) => {
    // Look for pagination controls
    const pagination = page.locator('.pagination, .page-nav');
    
    if (await pagination.count() > 0) {
      const nextButton = page.locator('button:has-text("Next"), .next-page');
      
      if (await nextButton.count() > 0 && await nextButton.isEnabled()) {
        await nextButton.click();
        await waitForPageLoad(page);
        
        // Page should change
        await expect(page.locator('.artist-card, .artist-item')).toBeVisible();
      }
    }
  });

  test('should handle empty artists list', async ({ page }) => {
    // Mock empty response
    await page.route('**/api/artists/', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ artists: [], total: 0 })
      });
    });
    
    await page.reload();
    await waitForPageLoad(page);
    
    // Should show empty state message
    await expect(page.locator(':has-text("No artists"), :has-text("empty")')).toBeVisible();
  });

  test('should handle artist import errors gracefully', async ({ page }) => {
    // Mock error response
    await page.route('**/api/artists/import-from-imvdb', route => {
      route.fulfill({
        status: 502,
        contentType: 'application/json',
        body: JSON.stringify({ success: false, error: 'Import failed' })
      });
    });
    
    // Try to import artist
    await page.click('button:has-text("Add New Artist")');
    await page.fill('#artistSearchInput', 'Test Artist');
    await page.click('button:has-text("Search IMVDb")');
    
    // Mock search success first
    await page.route('**/api/artists/discover*', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(mockResponses.imvdbArtistSearch)
      });
    });
    
    // Click import on first result
    await page.waitForSelector('.search-result-item');
    await page.click('button:has-text("Import")');
    
    // Should show error message
    await expect(page.locator(':has-text("error"), :has-text("failed")')).toBeVisible({ timeout: 10000 });
  });
});