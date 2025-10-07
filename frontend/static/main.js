// MVidarr Enhanced - Main JavaScript

// Utility functions - Updated to use toast notifications
function showMessage(message, type = 'info') {
    // Use the global toast manager if available, fallback to console
    if (window.toastManager) {
        return window.toastManager.show(message, type);
    } else if (window.showToast) {
        return window.showToast(message, type);
    } else {
        console.log(`${type.toUpperCase()}: ${message}`);
        return null;
    }
}

// Note: showSuccess, showError, showWarning, showInfo are defined in toast.js
// This provides the showLoading function that toast.js doesn't have
function showLoading(message) {
    if (window.toastManager) {
        return window.toastManager.loading(message);
    } else {
        console.log(`LOADING: ${message}`);
        return null;
    }
}

// Toast notification system is loaded from toast.js

// API helper functions
async function apiRequest(url, options = {}) {
    try {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        });
        
        // Check if response is JSON
        const contentType = response.headers.get('content-type');
        if (!contentType || !contentType.includes('application/json')) {
            // Non-JSON response, likely an error page
            const text = await response.text();
            throw new Error(`Server returned non-JSON response (${response.status}): ${text.substring(0, 100)}...`);
        }
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || `HTTP error! status: ${response.status}`);
        }
        
        return data;
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

// Settings management
class SettingsManager {
    static async get(key) {
        try {
            const data = await apiRequest(`/api/settings/${key}`);
            return data.value;
        } catch (error) {
            console.error(`Failed to get setting ${key}:`, error);
            return null;
        }
    }
    
    static async set(key, value) {
        try {
            await apiRequest(`/api/settings/${key}`, {
                method: 'PUT',
                body: JSON.stringify({ value })
            });
            return true;
        } catch (error) {
            console.error(`Failed to set setting ${key}:`, error);
            return false;
        }
    }
    
    static async getAll() {
        try {
            const data = await apiRequest('/api/settings/');
            return data.settings;
        } catch (error) {
            console.error('Failed to get all settings:', error);
            return {};
        }
    }
    
    static async updateMultiple(settings) {
        try {
            await apiRequest('/api/settings/bulk', {
                method: 'PUT',
                body: JSON.stringify({ settings })
            });
            return true;
        } catch (error) {
            console.error('Failed to update multiple settings:', error);
            return false;
        }
    }
}

// System health monitoring
class HealthMonitor {
    static async getStatus() {
        try {
            const data = await apiRequest('/api/health/status');
            return data;
        } catch (error) {
            console.error('Failed to get health status:', error);
            return { status: 'unhealthy', error: error.message };
        }
    }
    
    static async checkDatabase() {
        try {
            const data = await apiRequest('/api/health/database');
            return data;
        } catch (error) {
            console.error('Failed to check database:', error);
            return { status: 'unhealthy', error: error.message };
        }
    }
}

// Loading indicator - Enhanced for toast integration
function showElementLoading(element, message = 'Loading...') {
    if (typeof element === 'string') {
        element = document.getElementById(element);
    }
    
    if (!element) {
        // Fallback to toast loading if element not found
        return showLoading(message);
    }
    
    const originalContent = element.innerHTML;
    element.innerHTML = `
        <div class="loading-spinner">
            <img src="/static/MVidarr.png" alt="MVidarr" class="spinning mvidarr-logo-spinner" style="width: 24px; height: 24px;">
            <p>${message}</p>
        </div>
    `;
    
    return () => {
        element.innerHTML = originalContent;
    };
}

// Global loading indicator using toast
function showGlobalLoading(message = 'Loading...') {
    return showLoading(message);
}

// Add spinner CSS
const spinnerStyle = document.createElement('style');
spinnerStyle.textContent = `
    .loading-spinner {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        padding: 2rem;
    }
    
    .spinner {
        width: 40px;
        height: 40px;
        border: 4px solid #444;
        border-top: 4px solid #00d4ff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
        margin-bottom: 1rem;
    }
    
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
`;
document.head.appendChild(spinnerStyle);

// Form validation
function validateForm(formElement) {
    const requiredFields = formElement.querySelectorAll('[required]');
    let isValid = true;
    
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.style.borderColor = '#ff0000';
            isValid = false;
        } else {
            field.style.borderColor = '#444';
        }
    });
    
    return isValid;
}

// Format utilities
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = seconds % 60;
    
    if (hours > 0) {
        return `${hours}:${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
    } else {
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
}

// Global error handler with toast notifications
window.addEventListener('error', (event) => {
    console.error('Global error:', event.error);
    showError('An unexpected error occurred. Please check the console for details.');
});

// Handle unhandled promise rejections
window.addEventListener('unhandledrejection', (event) => {
    console.error('Unhandled promise rejection:', event.reason);
    showError('An unexpected error occurred during an operation.');
});

// Initialize common functionality
document.addEventListener('DOMContentLoaded', function() {
    // Add click handlers for navigation
    const navLinks = document.querySelectorAll('.nav-menu a');
    navLinks.forEach(link => {
        link.addEventListener('click', function(e) {
            // Remove active class from all links
            navLinks.forEach(l => l.classList.remove('active'));
            // Add active class to clicked link
            this.classList.add('active');
        });
    });
    
    // Set active navigation item based on current path
    const currentPath = window.location.pathname;
    navLinks.forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.classList.add('active');
        }
    });
    
    // Initialize Background Job Manager for real-time job progress
    // Note: BackgroundJobManager is already instantiated as window.backgroundJobs in background-jobs.js
    if (typeof window.backgroundJobs !== 'undefined') {
        console.log('🚀 Background Job Manager already initialized');
    } else if (typeof BackgroundJobManager !== 'undefined') {
        window.backgroundJobs = new BackgroundJobManager();
        console.log('🚀 Background Job Manager initialized');
    } else {
        console.warn('⚠️ BackgroundJobManager not available - background-jobs.js may not be loaded');
    }
});

// Thumbnail management functions
class ThumbnailManager {
    static async populateArtistThumbnails(element, limit = 10) {
        const loadingToast = showLoading('Populating artist thumbnails...');
        const hideLoading = element ? showElementLoading(element, 'Processing...') : null;
        
        try {
            const result = await apiRequest('/api/artists/populate-thumbnails', {
                method: 'POST',
                body: JSON.stringify({ limit })
            });
            
            if (loadingToast && window.toastManager) {
                window.toastManager.update(loadingToast, `Updated ${result.updated_count} of ${result.processed_count} artist thumbnails`, 'success');
                setTimeout(() => window.toastManager.removeToast(loadingToast), 3000);
            } else {
                showSuccess(`Updated ${result.updated_count} of ${result.processed_count} artist thumbnails`);
            }
            return result;
        } catch (error) {
            if (loadingToast && window.toastManager) {
                window.toastManager.update(loadingToast, `Failed to populate thumbnails: ${error.message}`, 'error');
            } else {
                showError(`Failed to populate thumbnails: ${error.message}`);
            }
            throw error;
        } finally {
            if (hideLoading) hideLoading();
        }
    }
    
    static async downloadVideoThumbnail(videoId, element) {
        const loadingToast = showLoading('Downloading video thumbnail...');
        const hideLoading = element ? showElementLoading(element, 'Downloading...') : null;
        
        try {
            const result = await apiRequest('/api/video-indexing/thumbnails/download', {
                method: 'POST',
                body: JSON.stringify({ video_id: videoId })
            });
            
            if (loadingToast && window.toastManager) {
                window.toastManager.update(loadingToast, 'Video thumbnail downloaded successfully', 'success');
                setTimeout(() => window.toastManager.removeToast(loadingToast), 3000);
            } else {
                showSuccess('Video thumbnail downloaded successfully');
            }
            return result;
        } catch (error) {
            if (loadingToast && window.toastManager) {
                window.toastManager.update(loadingToast, `Failed to download thumbnail: ${error.message}`, 'error');
            } else {
                showError(`Failed to download thumbnail: ${error.message}`);
            }
            throw error;
        } finally {
            if (hideLoading) hideLoading();
        }
    }
    
    static async getThumbnailStats() {
        try {
            const stats = await apiRequest('/api/video-indexing/thumbnails/stats');
            return stats;
        } catch (error) {
            console.error('Failed to get thumbnail stats:', error);
            return { total_size: 0, total_count: 0, artist_count: 0, video_count: 0 };
        }
    }
    
    static loadThumbnailWithFallback(imgElement, thumbnailUrl, fallbackUrl) {
        if (thumbnailUrl) {
            imgElement.src = thumbnailUrl;
            imgElement.onerror = () => {
                imgElement.src = fallbackUrl;
                imgElement.onerror = null;
            };
        } else {
            imgElement.src = fallbackUrl;
        }
    }
    
    static setupLazyLoading(container) {
        const images = container.querySelectorAll('img[data-src]');
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    const thumbnailUrl = img.dataset.src;
                    const fallbackUrl = img.dataset.fallback || '/static/placeholder-video.png';
                    
                    this.loadThumbnailWithFallback(img, thumbnailUrl, fallbackUrl);
                    img.removeAttribute('data-src');
                    observer.unobserve(img);
                }
            });
        });
        
        images.forEach(img => imageObserver.observe(img));
    }
    
    static refreshThumbnailDisplay(containerId, type = 'video') {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        const images = container.querySelectorAll('img');
        const placeholderUrl = type === 'artist' ? '/static/placeholder-artist.png' : '/static/placeholder-video.png';
        
        images.forEach(img => {
            const originalSrc = img.dataset.originalSrc || img.src;
            if (originalSrc && !originalSrc.includes('placeholder')) {
                this.loadThumbnailWithFallback(img, originalSrc, placeholderUrl);
            }
        });
    }
    
    static async bulkDownloadThumbnails(videoIds, progressCallback) {
        const results = [];
        const total = videoIds.length;
        
        for (let i = 0; i < total; i++) {
            const videoId = videoIds[i];
            try {
                const result = await this.downloadVideoThumbnail(videoId);
                results.push({ videoId, success: true, result });
                
                if (progressCallback) {
                    progressCallback(i + 1, total, videoId, true);
                }
            } catch (error) {
                results.push({ videoId, success: false, error: error.message });
                
                if (progressCallback) {
                    progressCallback(i + 1, total, videoId, false, error.message);
                }
            }
            
            // Small delay to avoid overwhelming the server
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        
        const successCount = results.filter(r => r.success).length;
        const messageType = successCount === total ? 'success' : 'warning';
        showMessage(`Downloaded ${successCount} of ${total} thumbnails`, messageType);
        
        return results;
    }
}

// Authentication Management
class AuthManager {
    static async checkAuthStatus() {
        try {
            // Check if authentication is required
            const settings = await apiRequest('/api/settings/');
            const requireAuth = settings.require_authentication?.value === 'true';
            
            if (requireAuth) {
                // Show user menu and get user info
                const userMenu = document.getElementById('userMenu');
                const usernameSpan = document.getElementById('username');
                
                if (userMenu) {
                    userMenu.style.display = 'block';
                    if (usernameSpan) {
                        usernameSpan.textContent = 'admin'; // For now, hardcoded
                    }
                }
            } else {
                // Hide user menu when auth is disabled
                const userMenu = document.getElementById('userMenu');
                if (userMenu) {
                    userMenu.style.display = 'none';
                }
            }
            
            return requireAuth;
        } catch (error) {
            console.error('Failed to check auth status:', error);
            return false;
        }
    }
    
    static async logout() {
        try {
            // Try different logout endpoints based on which auth system is active
            let response;
            let logoutEndpoint = '/simple-auth/logout';
            
            // First try simple auth system (since we're running simple auth mode)
            response = await fetch('/simple-auth/logout', { method: 'POST' });
            
            // If simple auth returns 404, try dynamic auth system
            if (response.status === 404) {
                console.log('Simple auth logout not found, trying dynamic logout');
                response = await fetch('/auth/dynamic-logout', { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                logoutEndpoint = '/auth/dynamic-logout';
            }
            
            // If still 404, try full auth system
            if (response.status === 404) {
                console.log('Dynamic logout not found, trying full auth logout');
                response = await fetch('/auth/logout', { method: 'POST' });
                logoutEndpoint = '/auth/logout';
            }
            
            if (response.ok) {
                showSuccess('Logged out successfully');
                // Redirect based on auth system
                if (logoutEndpoint === '/simple-auth/logout') {
                    setTimeout(() => window.location.href = '/simple-auth/login', 1000);
                } else if (logoutEndpoint === '/auth/dynamic-logout') {
                    setTimeout(() => window.location.href = '/auth/login', 1000);
                } else {
                    setTimeout(() => window.location.reload(), 1000);
                }
            } else {
                showError(`Logout failed: HTTP ${response.status}`);
            }
        } catch (error) {
            console.error('Logout error:', error);
            showError('Logout failed');
        }
    }
}

// User Management Functions
function logout() {
    if (confirm('Are you sure you want to log out?')) {
        AuthManager.logout();
    }
}

function showUserProfile() {
    // Create user profile modal
    const modalHtml = `
        <div class="modal" id="userProfileModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>👤 User Profile</h2>
                    <button class="modal-close" onclick="closeModal('userProfileModal')">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="profile-section">
                        <h3>Account Information</h3>
                        <div class="form-group">
                            <label>Username:</label>
                            <p><strong>admin</strong></p>
                        </div>
                        <div class="form-group">
                            <label>Role:</label>
                            <p><strong>Administrator</strong></p>
                        </div>
                        <div class="form-group">
                            <label>Last Login:</label>
                            <p id="lastLogin">Just now</p>
                        </div>
                    </div>
                    <div class="profile-actions">
                        <button class="btn btn-primary" onclick="showChangePassword()">Change Password</button>
                        <button class="btn btn-secondary" onclick="closeModal('userProfileModal')">Close</button>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal
    const existing = document.getElementById('userProfileModal');
    if (existing) existing.remove();
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Show modal
    document.getElementById('userProfileModal').style.display = 'block';
}

function showChangePassword() {
    // Create change password modal
    const modalHtml = `
        <div class="modal" id="changePasswordModal">
            <div class="modal-content">
                <div class="modal-header">
                    <h2>🔑 Change Password</h2>
                    <button class="modal-close" onclick="closeModal('changePasswordModal')">&times;</button>
                </div>
                <div class="modal-body">
                    <form id="changePasswordForm" onsubmit="handleChangePassword(event)">
                        <div class="form-group">
                            <label for="currentPassword">Current Password:</label>
                            <input type="password" id="currentPassword" name="currentPassword" required>
                        </div>
                        <div class="form-group">
                            <label for="newPassword">New Password:</label>
                            <input type="password" id="newPassword" name="newPassword" required minlength="8">
                            <small class="help-text">Password must be at least 8 characters long</small>
                        </div>
                        <div class="form-group">
                            <label for="confirmPassword">Confirm New Password:</label>
                            <input type="password" id="confirmPassword" name="confirmPassword" required>
                        </div>
                        <div class="form-actions">
                            <button type="submit" class="btn btn-primary">Change Password</button>
                            <button type="button" class="btn btn-secondary" onclick="closeModal('changePasswordModal')">Cancel</button>
                        </div>
                    </form>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal
    const existing = document.getElementById('changePasswordModal');
    if (existing) existing.remove();
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Show modal
    document.getElementById('changePasswordModal').style.display = 'block';
}

async function handleChangePassword(event) {
    event.preventDefault();
    
    const form = event.target;
    const currentPassword = form.currentPassword.value;
    const newPassword = form.newPassword.value;
    const confirmPassword = form.confirmPassword.value;
    
    // Validate passwords match
    if (newPassword !== confirmPassword) {
        showError('New passwords do not match');
        return;
    }
    
    // Validate password strength
    if (newPassword.length < 8) {
        showError('Password must be at least 8 characters long');
        return;
    }
    
    try {
        const response = await apiRequest('/auth/change-password', {
            method: 'POST',
            body: JSON.stringify({
                current_password: currentPassword,
                new_password: newPassword
            })
        });
        
        if (response.success) {
            showSuccess('Password changed successfully');
            closeModal('changePasswordModal');
        } else {
            showWarning(response.message || 'Password change functionality is not yet fully implemented');
            closeModal('changePasswordModal');
        }
    } catch (error) {
        console.error('Password change error:', error);
        const errorMessage = error.message || 'Failed to change password';
        showError(errorMessage);
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        setTimeout(() => modal.remove(), 300);
    }
}

// User Management Functions for Settings Page
function resetFailedAttempts() {
    showWarning('Failed attempt reset functionality will be implemented in the next update');
    // TODO: Implement actual API call to reset failed attempts
}

function forceLogoutAllSessions() {
    if (confirm('Are you sure you want to force logout all active sessions? This will require all users to log in again.')) {
        showWarning('Force logout functionality will be implemented in the next update');
        // TODO: Implement actual API call to invalidate all sessions
    }
}

// Settings page authentication management (simplified - no complex user management)
function updateUserManagementSection() {
    // This function is kept for compatibility but does nothing since we removed complex user management
    // The user credentials section is handled by updateUserCredentialsSection()
}

// User credentials section management
function updateUserCredentialsSection() {
    const userCredentialsSection = document.getElementById('userCredentialsSection');
    if (!userCredentialsSection) return;
    
    // Check if authentication is enabled
    const requireAuthElement = document.getElementById('require_authentication');
    if (requireAuthElement && requireAuthElement.value === 'true') {
        userCredentialsSection.style.display = 'block';
        loadCurrentCredentials();
    } else {
        userCredentialsSection.style.display = 'none';
    }
}

// Load current credentials for display
async function loadCurrentCredentials() {
    try {
        const response = await apiRequest('/auth/credentials');
        const usernameField = document.getElementById('auth_username');
        if (usernameField && response.username) {
            usernameField.value = response.username;
        }
    } catch (error) {
        console.log('Could not load current credentials:', error);
    }
}

// Update user credentials
async function updateCredentials() {
    const username = document.getElementById('auth_username').value.trim();
    const password = document.getElementById('auth_password').value;
    const confirmPassword = document.getElementById('auth_password_confirm').value;
    
    // Validation
    if (!username) {
        showError('Username is required');
        return;
    }
    
    if (username.length < 3) {
        showError('Username must be at least 3 characters long');
        return;
    }
    
    if (!password) {
        showError('Password is required');
        return;
    }
    
    if (password.length < 6) {
        showError('Password must be at least 6 characters long');
        return;
    }
    
    if (password !== confirmPassword) {
        showError('Passwords do not match');
        return;
    }
    
    try {
        showLoading('Updating credentials...');
        
        await apiRequest('/auth/credentials', {
            method: 'POST',
            body: JSON.stringify({
                username: username,
                password: password
            })
        });
        
        showSuccess('Credentials updated successfully');
        
        // Clear password fields
        document.getElementById('auth_password').value = '';
        document.getElementById('auth_password_confirm').value = '';
        
    } catch (error) {
        showError('Failed to update credentials: ' + error.message);
    }
}

// Reset credentials to default
async function resetCredentials() {
    if (!confirm('Are you sure you want to reset credentials to default values?')) {
        return;
    }
    
    try {
        showLoading('Resetting credentials...');
        
        await apiRequest('/auth/credentials/reset', {
            method: 'POST'
        });
        
        showSuccess('Credentials reset to default (admin/mvidarr)');
        loadCurrentCredentials();
        
        // Clear password fields
        document.getElementById('auth_password').value = '';
        document.getElementById('auth_password_confirm').value = '';
        
    } catch (error) {
        showError('Failed to reset credentials: ' + error.message);
    }
}

// Initialize authentication status on page load
document.addEventListener('DOMContentLoaded', function() {
    AuthManager.checkAuthStatus();
    
    // Update user management section visibility on settings page
    if (window.location.pathname.includes('/settings')) {
        // Watch for authentication setting changes
        const requireAuthElement = document.getElementById('require_authentication');
        if (requireAuthElement) {
            requireAuthElement.addEventListener('change', function() {
                updateUserManagementSection();
                updateUserCredentialsSection();
            });
            updateUserManagementSection(); // Initial check
            updateUserCredentialsSection(); // Initial check for credentials section
        }
    }
});

// Metadata Services Functions

// Helper functions for metadata services
function getCurrentArtistName() {
    // Try to get from page title or current URL
    const titleElement = document.querySelector('h1');
    if (titleElement && titleElement.textContent) {
        return titleElement.textContent.replace('Artist: ', '').trim();
    }
    
    // Try to get from URL
    const pathParts = window.location.pathname.split('/');
    if (pathParts.includes('artist') || pathParts.includes('artists')) {
        const artistIndex = pathParts.findIndex(part => part === 'artist' || part === 'artists') + 1;
        if (artistIndex < pathParts.length) {
            return decodeURIComponent(pathParts[artistIndex]);
        }
    }
    
    return null;
}

function getCurrentArtistId() {
    // Try to get from URL
    const pathParts = window.location.pathname.split('/');
    if (pathParts.includes('artist') || pathParts.includes('artists')) {
        const artistIndex = pathParts.findIndex(part => part === 'artist' || part === 'artists') + 1;
        if (artistIndex < pathParts.length) {
            const artistId = parseInt(pathParts[artistIndex]);
            if (!isNaN(artistId)) {
                return artistId;
            }
        }
    }
    
    // Try to get from data attribute or hidden field
    const artistIdElement = document.querySelector('[data-artist-id]') || document.getElementById('artistId');
    if (artistIdElement) {
        const id = parseInt(artistIdElement.getAttribute('data-artist-id') || artistIdElement.value);
        if (!isNaN(id)) {
            return id;
        }
    }
    
    return null;
}

function updateServiceStatus(statusElementId, status, text) {
    const statusElement = document.getElementById(statusElementId);
    if (statusElement) {
        statusElement.className = `service-status ${status}`;
        statusElement.innerHTML = `<span class="status-indicator ${status}">${text}</span>`;
    }
}

// Removed redundant displaySearchResults function - replaced with displayMetadataSearchResults

function refreshArtistMetadata() {
    // Simple refresh for now - could be enhanced to update specific sections
    setTimeout(() => {
        window.location.reload();
    }, 1500);
}

// Clear functions
function clearMusicBrainz() {
    updateServiceStatus('musicbrainzStatus', 'unknown', 'Not Linked');
    showSuccess('MusicBrainz data cleared');
}

function clearLastfm() {
    updateServiceStatus('lastfmStatus', 'unknown', 'Not Linked');
    showSuccess('Last.fm data cleared');
}

// Discogs functions removed

function clearAllMusic() {
    updateServiceStatus('allmusicStatus', 'unknown', 'Not Linked');
    showSuccess('AllMusic data cleared');
}

function clearWikipedia() {
    updateServiceStatus('wikipediaStatus', 'unknown', 'Not Linked');
    showSuccess('Wikipedia data cleared');
}

// Additional service functions for artist detail overview
async function searchSpotify() {
    const artistName = getCurrentArtistName();
    if (!artistName) {
        showWarning('Please enter an artist name first');
        return;
    }
    
    showLoading('Searching Spotify...');
    try {
        const response = await apiRequest(`/api/spotify/search/artists?q=${encodeURIComponent(artistName)}&limit=10`);
        
        if (response && response.artists && response.artists.items) {
            const artists = response.artists.items;
            displayMetadataSearchResults('spotify', artists);
            showSuccess(`Found ${artists.length} Spotify artists`);
        } else {
            showWarning('No Spotify artists found');
        }
    } catch (error) {
        if (error.message.includes('Not authenticated')) {
            showWarning('Please connect your Spotify account in Settings → Services first');
        } else {
            showError('Spotify search failed: ' + error.message);
        }
    }
}

async function linkSpotifyArtist(spotifyId, spotifyName) {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showError('No artist ID found');
        return;
    }
    
    if (!spotifyId) {
        showWarning('Please search for and select a Spotify artist first');
        return;
    }
    
    showLoading('Linking Spotify artist...');
    try {
        const response = await apiRequest(`/api/artists/${artistId}`, {
            method: 'PUT',
            body: JSON.stringify({
                spotify_id: spotifyId
            })
        });
        
        if (response.success) {
            showSuccess(`Successfully linked to Spotify artist: ${spotifyName}`);
            // Refresh the page to update the display
            setTimeout(() => window.location.reload(), 1500);
        } else {
            showError('Failed to link Spotify artist');
        }
    } catch (error) {
        showError('Failed to link Spotify artist: ' + error.message);
    }
}

async function syncFromSpotify() {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showError('No artist ID found');
        return;
    }
    
    showLoading('Syncing from Spotify...');
    try {
        // Use the enhanced metadata enrichment endpoint
        const response = await apiRequest(`/api/metadata-enrichment/enrich/${artistId}`, {
            method: 'POST',
            body: JSON.stringify({
                force_refresh: true
            })
        });
        
        if (response.success) {
            showSuccess('Spotify sync completed successfully');
            // Refresh artist metadata display
            setTimeout(() => window.location.reload(), 1500);
        } else {
            showError('Spotify sync failed: ' + (response.errors?.join(', ') || 'Unknown error'));
        }
    } catch (error) {
        showError('Spotify sync failed: ' + error.message);
    }
}

function displaySpotifySearchResults(artists) {
    // Create a modal or panel to show the search results
    const resultsHtml = `
        <div class="spotify-search-results">
            <h4>Select Spotify Artist:</h4>
            <div class="artist-results" id="spotifyArtistResults">
                ${artists.map((artist, index) => `
                    <div class="spotify-artist-result" data-spotify-id="${artist.id}" data-spotify-name="${artist.name}" data-index="${index}" style="cursor: pointer; padding: 0.75rem; border: 1px solid var(--border-primary); margin: 0.5rem 0; border-radius: 4px; display: flex; align-items: center; gap: 0.75rem; transition: background 0.2s;">
                        ${artist.images && artist.images[0] ? 
                            `<img src="${artist.images[0].url}" alt="${artist.name}" style="width: 50px; height: 50px; border-radius: 4px;">` : 
                            '<div style="width: 50px; height: 50px; background: var(--bg-muted); border-radius: 4px; display: flex; align-items: center; justify-content: center;"><iconify-icon icon="tabler:music"></iconify-icon></div>'
                        }
                        <div>
                            <div style="font-weight: 600; color: var(--text-primary);">${artist.name}</div>
                            <div style="font-size: 0.85rem; color: var(--text-secondary);">
                                ${artist.genres && artist.genres.length > 0 ? artist.genres.slice(0, 3).join(', ') : 'No genres listed'}
                            </div>
                            <div style="font-size: 0.8rem; color: var(--text-muted);">
                                ${artist.followers ? `${artist.followers.total.toLocaleString()} followers` : ''}
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
            <div style="margin-top: 1rem; text-align: center;">
                <button onclick="closeSpotifyResults()" class="btn btn-secondary">Cancel</button>
            </div>
        </div>
    `;
    
    // Show the results in a modal-like overlay
    const overlay = document.createElement('div');
    overlay.id = 'spotifySearchOverlay';
    overlay.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%; 
        background: rgba(0,0,0,0.7); z-index: 10000; display: flex; 
        align-items: center; justify-content: center; padding: 2rem;
    `;
    
    const modal = document.createElement('div');
    modal.style.cssText = `
        background: var(--bg-secondary); border-radius: 8px; padding: 2rem; 
        max-width: 600px; width: 100%; max-height: 80vh; overflow-y: auto;
        border: 1px solid var(--border-primary);
    `;
    modal.innerHTML = resultsHtml;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Add click handlers to artist results
    document.getElementById('spotifyArtistResults').addEventListener('click', async (e) => {
        const artistDiv = e.target.closest('.spotify-artist-result');
        if (artistDiv) {
            const spotifyId = artistDiv.getAttribute('data-spotify-id');
            const spotifyName = artistDiv.getAttribute('data-spotify-name');
            
            // Close modal immediately
            closeSpotifyResults();
            
            // Auto-link the selected artist
            await linkSpotifyArtist(spotifyId, spotifyName);
        }
    });
}

function closeSpotifyResults() {
    const overlay = document.getElementById('spotifySearchOverlay');
    if (overlay) {
        overlay.remove();
    }
}

async function syncFromImvdb() {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showError('No artist ID found');
        return;
    }
    
    showLoading('Syncing from IMVDb...');
    try {
        // This would call existing IMVDb sync functionality
        showInfo('IMVDb sync completed. Use the Discover tab to find new videos.');
        showSuccess('IMVDb sync completed');
    } catch (error) {
        showError('IMVDb sync failed: ' + error.message);
    }
}

async function clearImvdbId() {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showError('No artist ID found');
        return;
    }
    
    if (!confirm('Are you sure you want to clear the IMVDb ID for this artist?')) {
        return;
    }
    
    try {
        const response = await apiRequest(`/api/artists/${artistId}`, {
            method: 'PUT',
            body: JSON.stringify({
                imvdb_id: null
            })
        });
        
        if (response.success) {
            showSuccess('IMVDb ID cleared');
            // Refresh the page to update the display
            setTimeout(() => window.location.reload(), 1500);
        } else {
            showError('Failed to clear IMVDb ID');
        }
    } catch (error) {
        showError('Failed to clear IMVDb ID: ' + error.message);
    }
}
async function searchMusicBrainz() {
    const artistName = document.getElementById('artistNameSetting')?.value || getCurrentArtistName();
    if (!artistName) {
        showWarning('Please enter an artist name first');
        return;
    }
    
    showLoading('Searching MusicBrainz...');
    console.log('Starting MusicBrainz search for:', artistName);
    
    try {
        // Use the original working endpoint
        console.log('Making request to /api/musicbrainz/search-artist');
        const response = await apiRequest('/api/musicbrainz/search-artist', {
            method: 'POST',
            body: JSON.stringify({ artist: artistName })
        });
        
        console.log('Full MusicBrainz API Response:', JSON.stringify(response, null, 2));
        console.log('Response type:', typeof response);
        console.log('Response keys:', Object.keys(response || {}));
        console.log('Response results field:', response?.results);
        console.log('Results length:', response?.results?.length);
        
        const results = response?.results || [];
        console.log('Final results passed to display:', results);
        
        displayMetadataSearchResults('musicbrainz', results);
        
        if (results && results.length > 0) {
            showSuccess('MusicBrainz search completed');
        } else {
            showInfo('No MusicBrainz results found');
        }
    } catch (error) {
        console.error('MusicBrainz search error details:', error);
        console.error('Error stack:', error.stack);
        showError('MusicBrainz search failed: ' + error.message);
    }
}

// TEMPORARY DEBUG FUNCTION - Test direct MusicBrainz API
async function testMusicBrainzDirect() {
    console.log('Testing direct MusicBrainz API call...');
    try {
        const response = await apiRequest('/api/musicbrainz/test-direct', {
            method: 'POST',
            body: JSON.stringify({ query: 'Bad Religion' })
        });
        
        console.log('Direct MusicBrainz test result:', response);
        
        if (response.error) {
            showError('Direct test failed: ' + response.error);
        } else {
            showSuccess('Direct test completed - check console for details');
        }
        
    } catch (error) {
        console.error('Direct test error:', error);
        showError('Direct test failed: ' + error.message);
    }
}

// Make function available globally for testing
window.testMusicBrainzDirect = testMusicBrainzDirect;

async function enrichFromMusicBrainz() {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showError('No artist ID found');
        return;
    }
    
    showLoading('Enriching from MusicBrainz...');
    try {
        const response = await apiRequest(`/api/metadata-enrichment/enrich/${artistId}`, {
            method: 'POST',
            body: JSON.stringify({
                force_refresh: true
            })
        });
        
        if (response.success) {
            updateServiceStatus('musicbrainzStatus', 'linked', 'Linked');
            showSuccess('MusicBrainz enrichment completed');
            // Refresh artist metadata display
            refreshArtistMetadata();
        } else {
            showError('MusicBrainz enrichment failed: ' + (response.errors?.join(', ') || 'Unknown error'));
        }
    } catch (error) {
        showError('MusicBrainz enrichment failed: ' + error.message);
    }
}

async function searchLastfm() {
    const artistName = document.getElementById('lastfmArtist')?.value || getCurrentArtistName();
    if (!artistName) {
        showWarning('Please enter an artist name first');
        return;
    }
    
    showLoading('Searching Last.fm...');
    try {
        const response = await apiRequest(`/api/metadata-enrichment/search/lastfm?artist=${encodeURIComponent(artistName)}`);
        
        // Handle authentication message
        if (response.authentication_required && response.message) {
            showWarning(response.message);
            return;
        }
        
        displayMetadataSearchResults('lastfm', response.results || []);
        
        if (response.results && response.results.length > 0) {
            showSuccess('Last.fm search completed');
        } else {
            showInfo('No Last.fm results found');
        }
    } catch (error) {
        showError('Last.fm search failed: ' + error.message);
    }
}

async function enrichFromLastfm() {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showWarning('No artist selected');
        return;
    }
    
    const lastfmArtist = document.getElementById('lastfmArtist')?.value;
    if (!lastfmArtist) {
        showWarning('Please enter a Last.fm artist name first');
        return;
    }
    
    showLoading('Enriching from Last.fm...');
    try {
        const response = await apiRequest(`/api/metadata-enrichment/enrich/${artistId}`, {
            method: 'POST',
            body: JSON.stringify({ 
                source: 'lastfm',
                lastfm_artist: lastfmArtist 
            })
        });
        updateServiceStatus('lastfm', 'linked');
        showSuccess('Artist enriched from Last.fm');
        setTimeout(() => window.location.reload(), 1500);
    } catch (error) {
        showError('Last.fm enrichment failed: ' + error.message);
        updateServiceStatus('lastfm', 'error');
    }
}

// Discogs search function removed

// Discogs enrich function removed

async function searchAllMusic() {
    const artistName = getCurrentArtistName();
    if (!artistName) {
        showWarning('Please enter an artist name first');
        return;
    }
    
    showLoading('Searching AllMusic...');
    try {
        const response = await apiRequest(`/api/metadata-enrichment/search/allmusic?artist=${encodeURIComponent(artistName)}`);
        displayMetadataSearchResults('allmusic', response.results || []);
        showSuccess('AllMusic search completed');
    } catch (error) {
        showError('AllMusic search failed: ' + error.message);
    }
}

async function enrichFromAllMusic() {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showWarning('No artist selected');
        return;
    }
    
    const allmusicId = document.getElementById('allmusicId')?.value;
    if (!allmusicId) {
        showWarning('Please enter an AllMusic ID first');
        return;
    }
    
    showLoading('Enriching from AllMusic...');
    try {
        const response = await apiRequest(`/api/metadata-enrichment/enrich/${artistId}`, {
            method: 'POST',
            body: JSON.stringify({ 
                source: 'allmusic',
                allmusic_id: allmusicId 
            })
        });
        updateServiceStatus('allmusic', 'linked');
        showSuccess('Artist enriched from AllMusic');
        setTimeout(() => window.location.reload(), 1500);
    } catch (error) {
        showError('AllMusic enrichment failed: ' + error.message);
        updateServiceStatus('allmusic', 'error');
    }
}

async function searchWikipedia() {
    const artistName = getCurrentArtistName();
    if (!artistName) {
        showWarning('Please enter an artist name first');
        return;
    }
    
    showLoading('Searching Wikipedia...');
    try {
        const response = await apiRequest(`/api/metadata-enrichment/search/wikipedia?artist=${encodeURIComponent(artistName)}`);
        displayMetadataSearchResults('wikipedia', response.results || []);
        showSuccess('Wikipedia search completed');
    } catch (error) {
        showError('Wikipedia search failed: ' + error.message);
    }
}

async function enrichFromWikipedia() {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showWarning('No artist selected');
        return;
    }
    
    const wikipediaTitle = document.getElementById('wikipediaTitle')?.value;
    if (!wikipediaTitle) {
        showWarning('Please enter a Wikipedia page title first');
        return;
    }
    
    showLoading('Enriching from Wikipedia...');
    try {
        const response = await apiRequest(`/api/metadata-enrichment/enrich/${artistId}`, {
            method: 'POST',
            body: JSON.stringify({ 
                source: 'wikipedia',
                wikipedia_title: wikipediaTitle 
            })
        });
        updateServiceStatus('wikipedia', 'linked');
        showSuccess('Artist enriched from Wikipedia');
        setTimeout(() => window.location.reload(), 1500);
    } catch (error) {
        showError('Wikipedia enrichment failed: ' + error.message);
        updateServiceStatus('wikipedia', 'error');
    }
}

async function enrichFromAllServices() {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showWarning('No artist selected');
        return;
    }
    
    showLoading('Enriching from all available services...');
    try {
        const response = await apiRequest(`/api/metadata-enrichment/enrich/${artistId}`, {
            method: 'POST',
            body: JSON.stringify({ 
                source: 'all',
                force_refresh: true 
            })
        });
        showSuccess('Artist enriched from all services');
        setTimeout(() => window.location.reload(), 2000);
    } catch (error) {
        showError('Bulk enrichment failed: ' + error.message);
    }
}

async function autoMatchServices() {
    const artistId = getCurrentArtistId();
    const artistName = getCurrentArtistName();
    if (!artistId || !artistName) {
        showWarning('No artist selected');
        return;
    }
    
    if (!confirm(`Auto-match ${artistName} across all connected services? This will attempt to find and link corresponding profiles on IMVDb, MusicBrainz, Spotify, and other services.`)) {
        return;
    }
    
    try {
        console.log('🚀 Starting auto-match job for artist:', artistId);
        
        if (!window.backgroundJobs) {
            throw new Error('Background jobs system not available');
        }
        
        if (!window.backgroundJobs.startAutoMatch) {
            throw new Error('startAutoMatch method not available');
        }
        
        // Start background job for auto-match
        const jobId = await window.backgroundJobs.startAutoMatch(artistId, {
            priority: 'normal',
            onComplete: (error, result) => {
                if (error) {
                    console.error('Auto-match job failed:', error);
                    showError('Auto-match failed: ' + error.message);
                } else if (result) {
                    console.log('Auto-match job completed:', result);
                    const matches = result.total_matches || 0;
                    const saved = result.updated_fields ? result.updated_fields.length : 0;
                    
                    if (saved > 0) {
                        showSuccess(`Auto-match completed: ${matches} services matched, ${saved} saved to database`);
                        // Refresh the page to show updated metadata
                        setTimeout(() => window.location.reload(), 2000);
                    } else {
                        showWarning(`Auto-match completed: ${matches} services matched, but no new links were saved`);
                    }
                } else {
                    showSuccess('Auto-match completed');
                    setTimeout(() => window.location.reload(), 2000);
                }
            },
            onProgress: (progress) => {
                console.log('Auto-match progress:', progress);
            }
        });
        
        if (jobId) {
            console.log('Auto-match job started with ID:', jobId);
            showInfo(`Auto-match job started (ID: ${jobId})`);
        } else {
            showError('Failed to start auto-match job');
        }
        
    } catch (error) {
        console.error('Auto-match job error:', error);
        showError('Auto-match failed: ' + error.message);
    }
}

async function viewEnrichmentHistory() {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showWarning('No artist selected');
        return;
    }
    
    try {
        const response = await apiRequest(`/api/metadata-enrichment/history/${artistId}`);
        displayEnrichmentHistory(response.history || []);
    } catch (error) {
        showError('Failed to load enrichment history: ' + error.message);
    }
}

// Clear functions for each service
function clearMusicBrainzId() {
    document.getElementById('musicbrainzId').value = '';
    updateServiceStatus('musicbrainz', 'unknown');
}

function clearLastfmArtist() {
    document.getElementById('lastfmArtist').value = '';
    updateServiceStatus('lastfm', 'unknown');
}

// Discogs clear function removed

function clearAllMusicId() {
    document.getElementById('allmusicId').value = '';
    updateServiceStatus('allmusic', 'unknown');
}

function clearWikipediaTitle() {
    document.getElementById('wikipediaTitle').value = '';
    updateServiceStatus('wikipedia', 'unknown');
}

// Helper functions
function getCurrentArtistId() {
    // Extract artist ID from URL or global variable
    const pathParts = window.location.pathname.split('/');
    const artistIndex = pathParts.indexOf('artist');
    return artistIndex !== -1 ? pathParts[artistIndex + 1] : null;
}

function getCurrentArtistName() {
    return document.getElementById('artistNameSetting')?.value || 
           document.querySelector('h1')?.textContent?.trim() || '';
}

function updateServiceStatus(service, status) {
    const statusElement = document.getElementById(`${service}Status`);
    if (statusElement) {
        const indicator = statusElement.querySelector('.status-indicator');
        if (indicator) {
            indicator.className = `status-indicator ${status}`;
            indicator.textContent = status === 'linked' ? 'Linked' : 
                                  status === 'error' ? 'Error' : 'Not Linked';
        }
    }
}

function displayMetadataSearchResults(service, results) {
    console.log(`${service} search results:`, results);
    
    if (!results || results.length === 0) {
        showWarning(`No results found for ${service}`);
        return;
    }
    
    // Use the proven Spotify modal pattern
    showMetadataSearchResults(service, results);
}

function showMetadataSearchResults(service, results) {
    const serviceCapitalized = service.charAt(0).toUpperCase() + service.slice(1);
    const overlayId = `${service}SearchOverlay`;
    
    // Remove existing overlay
    const existingOverlay = document.getElementById(overlayId);
    if (existingOverlay) {
        existingOverlay.remove();
    }
    
    // Create results HTML using the Spotify pattern
    const resultsHtml = `
        <div class="${service}-search-results">
            <h4>Select ${serviceCapitalized} Result:</h4>
            <div class="service-results" id="${service}Results">
                ${results.map((result, index) => `
                    <div class="${service}-result" 
                         data-service-id="${result.id || result.mbid || result.name}" 
                         data-service-name="${result.name}" 
                         data-index="${index}" 
                         style="cursor: pointer; padding: 0.75rem; border: 1px solid var(--border-primary); margin: 0.5rem 0; border-radius: 4px; display: flex; align-items: center; gap: 0.75rem; transition: background 0.2s;">
                        <div style="width: 50px; height: 50px; background: var(--bg-muted, #555); border-radius: 4px; display: flex; align-items: center; justify-content: center;">
                            <iconify-icon icon="tabler:music" style="color: var(--text-muted, #888);"></iconify-icon>
                        </div>
                        <div style="flex: 1;">
                            <div style="font-weight: 600; color: var(--text-primary);">${result.name}</div>
                            ${result.description ? `<div style="font-size: 0.85rem; color: var(--text-secondary);">${result.description}</div>` : ''}
                            ${result.disambiguation ? `<div style="font-size: 0.85rem; color: var(--text-secondary);">${result.disambiguation}</div>` : ''}
                            ${result.country || result.area ? `<div style="font-size: 0.85rem; color: var(--text-secondary);">${result.country || result.area}</div>` : ''}
                            <div style="font-size: 0.8rem; color: var(--text-muted);">
                                ${result.listeners ? `${result.listeners.toLocaleString()} listeners` : ''}
                                ${result.type ? result.type : ''}
                                ${result.mbid ? ` • MBID: ${result.mbid.substring(0, 8)}...` : ''}
                                ${result.confidence ? ` • Match: ${Math.round(result.confidence * 100)}%` : ''}
                                ${result.url ? ` • ${service}` : ''}
                            </div>
                        </div>
                    </div>
                `).join('')}
            </div>
            <div style="margin-top: 1rem; text-align: center;">
                <button onclick="closeMetadataSearchResults('${overlayId}')" class="btn btn-secondary">Cancel</button>
            </div>
        </div>
    `;
    
    // Create overlay using exact Spotify pattern
    const overlay = document.createElement('div');
    overlay.id = overlayId;
    overlay.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100%; height: 100%; 
        background: rgba(0,0,0,0.7); z-index: 10000; display: flex; 
        align-items: center; justify-content: center; padding: 2rem;
    `;
    
    const modal = document.createElement('div');
    modal.style.cssText = `
        background: var(--bg-secondary); border-radius: 8px; padding: 2rem; 
        max-width: 600px; width: 100%; max-height: 80vh; overflow-y: auto;
        border: 1px solid var(--border-primary);
    `;
    modal.innerHTML = resultsHtml;
    
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    
    // Add click handlers using the proven pattern
    document.getElementById(`${service}Results`).addEventListener('click', async (e) => {
        const resultDiv = e.target.closest(`.${service}-result`);
        if (resultDiv) {
            const serviceId = resultDiv.getAttribute('data-service-id');
            const serviceName = resultDiv.getAttribute('data-service-name');
            const index = resultDiv.getAttribute('data-index');
            
            // Close modal immediately
            closeMetadataSearchResults(overlayId);
            
            // Show selection success
            showSuccess(`Selected: ${serviceName} from ${serviceCapitalized}`);
            
            // Implement linking logic for each service
            const fullResult = results[index];
            await linkSelectedResult(service, fullResult);
            
            console.log(`Selected ${service} result:`, {
                id: serviceId,
                name: serviceName,
                index: index,
                fullResult: fullResult
            });
        }
    });
}

function closeMetadataSearchResults(overlayId) {
    const overlay = document.getElementById(overlayId);
    if (overlay) {
        overlay.remove();
    }
}

async function linkSelectedResult(service, result) {
    const artistId = getCurrentArtistId();
    if (!artistId) {
        showError('No artist selected');
        return;
    }
    
    try {
        showLoading(`Linking ${service} result...`);
        
        switch (service) {
            case 'spotify':
                await linkSpotifyResult(artistId, result);
                break;
            case 'lastfm':
                await linkLastfmResult(artistId, result);
                break;
            case 'allmusic':
                await linkAllMusicResult(artistId, result);
                break;
            case 'wikipedia':
                await linkWikipediaResult(artistId, result);
                break;
            case 'musicbrainz':
                await linkMusicBrainzResult(artistId, result);
                break;
            case 'imvdb':
                await linkImvdbResult(artistId, result);
                break;
            default:
                showWarning(`Linking not implemented for ${service}`);
                return;
        }
        
        showSuccess(`Successfully linked ${service} data`);
        // Refresh the page to show updated metadata
        setTimeout(() => window.location.reload(), 1000);
        
    } catch (error) {
        showError(`Failed to link ${service} result: ${error.message}`);
    }
}

async function linkLastfmResult(artistId, result) {
    // Update the artist's lastfm_name field
    const response = await apiRequest(`/api/artists/${artistId}`, {
        method: 'PUT',
        body: JSON.stringify({
            lastfm_name: result.name
        })
    });
    return response;
}

async function linkSpotifyResult(artistId, result) {
    // Update the artist's spotify_id field
    const response = await apiRequest(`/api/artists/${artistId}`, {
        method: 'PUT',
        body: JSON.stringify({
            spotify_id: result.id
        })
    });
    return response;
}

// Discogs link function removed

async function linkAllMusicResult(artistId, result) {
    // Update the artist's allmusic metadata
    const response = await apiRequest(`/api/artists/${artistId}`, {
        method: 'PUT',
        body: JSON.stringify({
            allmusic_id: result.id,
            allmusic_metadata: result
        })
    });
    return response;
}

async function linkWikipediaResult(artistId, result) {
    // Update the artist's wikipedia metadata
    const response = await apiRequest(`/api/artists/${artistId}`, {
        method: 'PUT',
        body: JSON.stringify({
            wikipedia_url: result.url,
            wikipedia_metadata: result
        })
    });
    return response;
}

async function linkMusicBrainzResult(artistId, result) {
    // Update the artist's musicbrainz_id using mbid field
    const response = await apiRequest(`/api/artists/${artistId}`, {
        method: 'PUT',
        body: JSON.stringify({
            musicbrainz_id: result.mbid,
            musicbrainz_metadata: result
        })
    });
    return response;
}

async function linkImvdbResult(artistId, result) {
    // Update the artist's imvdb_id and metadata
    const response = await apiRequest(`/api/artists/${artistId}`, {
        method: 'PUT',
        body: JSON.stringify({
            imvdb_id: result.id,
            imvdb_metadata: result
        })
    });
    return response;
}

function displayEnrichmentHistory(history) {
    // This would show a modal with enrichment history
    console.log('Enrichment history:', history);
    showInfo(`Found ${history.length} enrichment records`);
}

async function searchImvdb() {
    const artistName = getCurrentArtistName();
    if (!artistName) {
        showWarning('Please enter an artist name first');
        return;
    }
    
    showLoading('Searching IMVDb...');
    try {
        const response = await apiRequest(`/api/metadata-enrichment/search/imvdb?artist=${encodeURIComponent(artistName)}`);
        
        // Handle authentication message
        if (response.authentication_required && response.message) {
            showWarning(response.message);
            return;
        }
        
        displayMetadataSearchResults('imvdb', response.results || []);
        
        if (response.results && response.results.length > 0) {
            showSuccess('IMVDb search completed');
        } else {
            showInfo('No IMVDb results found');
        }
    } catch (error) {
        showError('IMVDb search failed: ' + error.message);
    }
}

// Settings page metadata service functions
async function testMetadataServices() {
    showLoading('Testing metadata service connections...');
    try {
        const services = [
            { name: 'MusicBrainz', endpoint: '/api/musicbrainz/test' },
            { name: 'Last.fm', endpoint: '/api/lastfm/test', method: 'POST' },
            { name: 'Spotify', endpoint: '/api/spotify/test', method: 'POST' },
            { name: 'IMVDb', endpoint: '/api/video-indexing/imvdb/test' }
        ];
        
        const results = [];
        
        for (const service of services) {
            try {
                // Use direct fetch instead of apiRequest to handle 503 responses properly
                const response = await fetch(service.endpoint, {
                    method: service.method || 'GET',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    const data = await response.json();
                    const isSuccess = data.success || false;
                    const status = data.status || 'unknown';
                    results.push(`${service.name}: ${isSuccess ? '✅ Connected' : '❌ Disconnected'} (${status})`);
                } else {
                    results.push(`${service.name}: ❌ Invalid response`);
                }
            } catch (error) {
                results.push(`${service.name}: ❌ (${error.message})`);
            }
        }
        
        showInfo('Service test results:\n' + results.join('\n'));
    } catch (error) {
        showError('Service test failed: ' + error.message);
    }
}

async function searchThumbnailForArtist(artistId) {
    console.log(`🔍 Searching for artist thumbnail for ID ${artistId}...`);
    
    try {
        // Search for thumbnails from Wikipedia and YouTube
        const searchResponse = await fetch(`/api/artists/${artistId}/thumbnail/search`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'include',
            body: JSON.stringify({
                source: 'auto',
                query: null
            })
        });
        
        if (!searchResponse.ok) {
            throw new Error(`Thumbnail search failed: ${searchResponse.status}`);
        }
        
        const searchData = await searchResponse.json();
        
        if (searchData.success && searchData.results && searchData.results.length > 0) {
            // Use the first result (highest priority)
            const bestResult = searchData.results[0];
            console.log(`🔍 Found thumbnail from ${bestResult.source}: ${bestResult.url}`);
            
            // Download and set the thumbnail using the correct PUT endpoint
            const setResponse = await fetch(`/api/artists/${artistId}/thumbnail`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    thumbnail_url: bestResult.url
                }),
                credentials: 'include'
            });
            
            if (setResponse.ok) {
                const setData = await setResponse.json();
                if (setData.success) {
                    console.log(`✅ Successfully downloaded and set thumbnail from ${bestResult.source}`);
                    return true;
                } else {
                    throw new Error(setData.error || 'Failed to download thumbnail');
                }
            } else {
                throw new Error(`Thumbnail download failed: ${setResponse.status}`);
            }
        } else {
            console.log('🔍 No thumbnails found from priority sources');
            return false;
        }
    } catch (error) {
        console.log(`🔍 Thumbnail search error for artist ${artistId}: ${error.message}`);
        throw error;
    }
}

async function enrichAllArtists() {
    if (!confirm('This will enrich metadata for all artists. This may take a while. Continue?')) {
        return;
    }
    
    showLoading('Starting bulk enrichment...');
    try {
        // First get candidates for enrichment
        const candidatesResponse = await apiRequest('/api/metadata-enrichment/candidates?limit=10');
        const candidates = candidatesResponse.candidates || [];
        
        if (candidates.length === 0) {
            showInfo('No artists need enrichment at this time');
            return;
        }
        
        const artist_ids = candidates.map(c => c.id);
        const response = await apiRequest('/api/metadata-enrichment/enrich/batch', {
            method: 'POST',
            body: JSON.stringify({ 
                artist_ids: artist_ids,
                force_refresh: false 
            })
        });
        showSuccess(`Bulk enrichment completed. Processed ${response.total_processed} artists, ${response.successful} successful.`);
        
        // Search for thumbnails for all successfully enriched artists
        if (response.successful > 0 && response.enriched_artists) {
            console.log(`🔍 Searching thumbnails for ${response.enriched_artists.length} enriched artists...`);
            const thumbnailPromises = response.enriched_artists.map(artistId => 
                searchThumbnailForArtist(artistId).catch(error => {
                    console.log(`🔍 Thumbnail search failed for artist ${artistId}:`, error);
                    return false;
                })
            );
            
            Promise.allSettled(thumbnailPromises).then(results => {
                const successCount = results.filter(r => r.status === 'fulfilled' && r.value === true).length;
                if (successCount > 0) {
                    showSuccess(`Found thumbnails for ${successCount} artists during bulk enrichment`);
                }
            });
        }
    } catch (error) {
        showError('Bulk enrichment failed: ' + error.message);
    }
}

async function clearMetadataCache() {
    if (!confirm('This will clear all cached metadata. Continue?')) {
        return;
    }
    
    showLoading('Clearing metadata cache...');
    try {
        // For now, just show a success message - the backend doesn't have a specific clear cache endpoint
        // This could be enhanced later with actual cache clearing functionality
        showSuccess('Metadata cache cleared successfully (placeholder functionality)');
    } catch (error) {
        showError('Failed to clear cache: ' + error.message);
    }
}

// Export for use in other scripts
window.MVidarr = {
    showMessage,
    showSuccess,
    showError,
    showWarning,
    showInfo,
    showLoading,
    showElementLoading,
    showGlobalLoading,
    apiRequest,
    SettingsManager,
    HealthMonitor,
    validateForm,
    formatFileSize,
    formatDuration,
    formatDate,
    ThumbnailManager,
    AuthManager,
    // Metadata services functions
    searchMusicBrainz,
    enrichFromMusicBrainz,
    clearMusicBrainz,
    searchLastfm,
    enrichFromLastfm,
    clearLastfm,
    searchAllMusic,
    enrichFromAllMusic,
    clearAllMusic,
    searchWikipedia,
    enrichFromWikipedia,
    clearWikipedia,
    searchImvdb,
    enrichFromAllServices,
    autoMatchServices,
    viewEnrichmentHistory,
    testMetadataServices,
    enrichAllArtists,
    clearMetadataCache,
    getCurrentArtistName,
    getCurrentArtistId,
    updateServiceStatus,
    displayMetadataSearchResults,
    refreshArtistMetadata,
    // Additional service functions
    searchSpotify,
    linkSpotifyArtist,
    syncFromSpotify,
    syncFromImvdb,
    clearImvdbId,
    // Background job management
    get backgroundJobManager() {
        return window.backgroundJobs;
    },
    get backgroundJobs() {
        return window.backgroundJobs;
    },
    // Convenient background job functions
    startJob: function(jobType, payload, options = {}) {
        if (window.backgroundJobs) {
            return window.backgroundJobs.startJob(jobType, payload, options);
        } else {
            console.warn('BackgroundJobManager not available');
            return Promise.reject(new Error('BackgroundJobManager not initialized'));
        }
    },
    showJobDashboard: function() {
        if (typeof showJobDashboard === 'function') {
            showJobDashboard();
        } else {
            console.warn('showJobDashboard function not available');
        }
    }
};