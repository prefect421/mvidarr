// tests/e2e/dashboard.spec.js
const { test, expect } = require('@playwright/test');
const { login, waitForPageLoad, waitForApiResponse } = require('../utils/test-helpers');
const { testUsers, mockResponses } = require('../fixtures/test-data');

test.describe('Dashboard Functionality', () => {
  
  test.beforeEach(async ({ page }) => {
    // Login before each test
    await login(page, testUsers.user.username, testUsers.user.password);
    await waitForPageLoad(page);
  });

  test('should display dashboard stats correctly', async ({ page }) => {
    await page.goto('/');
    
    // Wait for stats to load
    await waitForPageLoad(page);
    
    // Check that stats cards are visible
    await expect(page.locator('.dashboard-stats')).toBeVisible();
    
    // Check individual stat cards
    const statsCards = page.locator('.stat-card');
    await expect(statsCards).toHaveCount(4); // Assuming 4 stat cards
    
    // Check for artists count
    await expect(page.locator('#artists-count')).toBeVisible();
    
    // Stats should contain numbers
    const artistsCount = await page.locator('#artists-count').textContent();
    expect(artistsCount).toMatch(/^\d+$/);
  });

  test('should load download queue', async ({ page }) => {
    await page.goto('/');
    
    // Check download queue section
    await expect(page.locator('.downloads-section')).toBeVisible();
    await expect(page.locator('h2:has-text("Download Queue")')).toBeVisible();
    
    // Check queue actions
    await expect(page.locator('button:has-text("Clear Stuck Downloads")')).toBeVisible();
    await expect(page.locator('button:has-text("Force Clear All")')).toBeVisible();
    
    // Download queue list should be present
    await expect(page.locator('#download-queue-list')).toBeVisible();
  });

  test('should open Add New Artist modal', async ({ page }) => {
    await page.goto('/');
    
    // Click Add New Artist button
    await page.click('button:has-text("Add New Artist"), .btn:has-text("Add Artist")');
    
    // Modal should appear
    await expect(page.locator('.modal, #addArtistModal')).toBeVisible();
    
    // Check modal content
    await expect(page.locator('input[name="artistName"], #artistSearchInput')).toBeVisible();
    await expect(page.locator('button:has-text("Search"), .btn:has-text("Search")')).toBeVisible();
  });

  test('should open Add Video modal', async ({ page }) => {
    await page.goto('/');
    
    // Click Add Video button
    await page.click('button:has-text("Add Video"), .btn:has-text("Add Video")');
    
    // Modal should appear
    await expect(page.locator('.modal, #addVideoModal')).toBeVisible();
    
    // Check modal tabs and content
    await expect(page.locator('#songTitleInput')).toBeVisible();
    await expect(page.locator('#artistNameInput')).toBeVisible();
    await expect(page.locator('button:has-text("Search Videos")')).toBeVisible();
  });

  test('should search for videos in Add Video modal', async ({ page }) => {
    await page.goto('/');
    
    // Open Add Video modal
    await page.click('button:has-text("Add Video")');
    
    // Fill search form
    await page.fill('#songTitleInput', 'Bad Blood');
    await page.fill('#artistNameInput', 'Taylor Swift');
    
    // Click search
    await page.click('button:has-text("Search Videos")');
    
    // Wait for search results
    await waitForApiResponse(page, 'search-videos');
    
    // Results should appear
    await expect(page.locator('#videoSearchResults')).toBeVisible();
  });

  test('should handle clear stuck downloads', async ({ page }) => {
    await page.goto('/');
    
    // Click clear stuck downloads button
    await page.click('button:has-text("Clear Stuck Downloads")');
    
    // Should show confirmation or success message
    await page.waitForSelector('.toast, .alert, .notification', { timeout: 5000 });
  });

  test('should handle force clear all downloads', async ({ page }) => {
    await page.goto('/');
    
    // Click force clear all button
    await page.click('button:has-text("Force Clear All")');
    
    // Should show confirmation dialog
    await expect(page.locator('.toast, .alert, .notification')).toBeVisible({ timeout: 5000 });
  });

  test('should display download history', async ({ page }) => {
    await page.goto('/');
    
    // Check download history section
    await expect(page.locator('h2:has-text("Download History")')).toBeVisible();
    await expect(page.locator('#download-history-list')).toBeVisible();
    
    // History should load
    await waitForPageLoad(page);
  });

  test('should handle navigation to artists page', async ({ page }) => {
    await page.goto('/');
    
    // Click link to artists page
    const artistsLink = page.locator('a:has-text("Artists"), .nav-link:has-text("Artists")');
    await artistsLink.click();
    
    // Should navigate to artists page
    await expect(page).toHaveURL('/artists');
    await expect(page.locator('h1:has-text("Artists"), h2:has-text("Artists")')).toBeVisible();
  });

  test('should handle navigation to videos page', async ({ page }) => {
    await page.goto('/');
    
    // Click link to videos page
    const videosLink = page.locator('a:has-text("Videos"), .nav-link:has-text("Videos")');
    if (await videosLink.count() > 0) {
      await videosLink.click();
      await expect(page).toHaveURL('/videos');
    }
  });

  test('should display system status information', async ({ page }) => {
    await page.goto('/');
    
    // Check for system status or health indicators
    const statusElements = page.locator('.system-status, .health-check, .status-indicator');
    
    // If status indicators exist, they should be visible
    if (await statusElements.count() > 0) {
      await expect(statusElements.first()).toBeVisible();
    }
  });

  test('should handle responsive design on mobile', async ({ page, isMobile }) => {
    if (!isMobile) {
      // Set mobile viewport
      await page.setViewportSize({ width: 375, height: 667 });
    }
    
    await page.goto('/');
    
    // Dashboard should still be functional on mobile
    await expect(page.locator('.dashboard-stats')).toBeVisible();
    
    // Navigation might be collapsed on mobile
    const nav = page.locator('.navbar, .navigation');
    await expect(nav).toBeVisible();
  });

  test('should refresh data when needed', async ({ page }) => {
    await page.goto('/');
    
    // Initial load
    await waitForPageLoad(page);
    
    // Get initial stats
    const initialArtistsCount = await page.locator('#artists-count').textContent();
    
    // Refresh page
    await page.reload();
    await waitForPageLoad(page);
    
    // Stats should load again
    await expect(page.locator('#artists-count')).toBeVisible();
    const refreshedArtistsCount = await page.locator('#artists-count').textContent();
    
    // Count should be consistent (or updated if data changed)
    expect(refreshedArtistsCount).toBeDefined();
  });
});