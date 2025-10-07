/**
 * MVidarr Core JavaScript - Optimized for Performance
 * Extracted from base.html for better caching and loading
 */

// Core application functionality
class MVidarrCore {
    constructor() {
        this.currentTheme = window.currentTheme || 'default';
        this.init();
    }

    init() {
        this.initializeThemeSystem();
        this.initializeSidebar();
        this.initializeAuthentication();
        this.loadVersionInfo();
    }

    // Theme Management System
    async loadSavedTheme() {
        try {
            const response = await fetch('/api/themes/current');
            if (response.ok) {
                const data = await response.json();
                if (data && data.current_theme) {
                    this.currentTheme = data.current_theme;
                    await this.loadThemeVariables(data.current_theme);
                } else {
                    this.applyCurrentTheme();
                }
            } else {
                this.applyCurrentTheme();
            }
        } catch (error) {
            console.log('Current theme not found, using default');
            this.applyCurrentTheme();
        }
    }

    async loadThemeVariables(themeId) {
        try {
            // List of built-in theme names
            const builtInThemes = ['cyber', 'vaporwave', 'tardis', 'punk_77', 'mtv', 'lcars'];
            
            let response;
            
            if (builtInThemes.includes(themeId)) {
                // Handle built-in theme
                response = await fetch(`/api/themes/built-in/${themeId}/extract`, {
                    method: 'POST'
                });
            } else {
                // Handle custom theme
                response = await fetch(`/api/themes/${themeId}`);
            }
            
            if (response.ok) {
                const themeData = await response.json();
                
                // Handle different response formats
                let cssVariables;
                if (themeData.theme_data) {
                    cssVariables = themeData.theme_data; // Custom theme format
                } else if (themeData.variables) {
                    cssVariables = themeData.variables; // Built-in theme format
                } else {
                    cssVariables = themeData; // Direct format
                }
                
                if (cssVariables) {
                    Object.entries(cssVariables).forEach(([cssVar, value]) => {
                        document.documentElement.style.setProperty(cssVar, value);
                    });
                }
            } else if (!builtInThemes.includes(themeId)) {
                // If custom theme failed, try as built-in theme
                response = await fetch(`/api/themes/built-in/${themeId}/extract`, {
                    method: 'POST'
                });
                
                if (response.ok) {
                    const extractData = await response.json();
                    if (extractData.variables) {
                        Object.entries(extractData.variables).forEach(([cssVar, value]) => {
                            document.documentElement.style.setProperty(cssVar, value);
                        });
                    }
                }
            }
            
            this.applyCurrentTheme();
            
        } catch (error) {
            console.error('Failed to load theme variables:', error);
            this.applyCurrentTheme();
        }
    }

    initializeThemeSystem() {
        this.loadSavedTheme();
    }

    applyCurrentTheme() {
        document.documentElement.setAttribute('data-theme', this.currentTheme);
        
        if (typeof updateThemePreviewMode === 'function') {
            updateThemePreviewMode();
        }
    }

    // Authentication Management
    async checkUserAuthentication() {
        try {
            const response = await fetch('/auth/check');
            const data = await response.json();
            
            if (data.authenticated && data.user) {
                this.showUserMenu(data.user);
            } else {
                this.hideUserMenu();
            }
        } catch (error) {
            console.error('Error checking authentication:', error);
            this.hideUserMenu();
        }
    }

    showUserMenu(user) {
        const userMenu = document.getElementById('userMenu');
        const username = document.getElementById('username');
        
        if (userMenu && username) {
            userMenu.style.display = 'block';
            username.textContent = user.username;
        }
    }

    hideUserMenu() {
        const elements = ['userMenu', 'userManagementSidebarItem'];
        elements.forEach(id => {
            const element = document.getElementById(id);
            if (element) element.style.display = 'none';
        });
    }

    initializeAuthentication() {
        setTimeout(() => this.checkUserAuthentication(), 100);
    }

    // Sidebar Management
    initializeSidebar() {
        const sidebar = document.getElementById('sidebar');
        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        
        if (!sidebar || !sidebarToggle || !sidebarOverlay) {
            console.warn('Sidebar elements not found');
            return;
        }
        
        sidebarToggle.addEventListener('click', () => this.toggleSidebar());
        sidebarOverlay.addEventListener('click', () => this.closeSidebar());
        
        this.handleResponsiveSidebar();
        window.addEventListener('resize', () => this.handleResponsiveSidebar());
        
        this.setActiveNavItem();
    }

    toggleSidebar() {
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        
        if (window.innerWidth <= 768) {
            // Mobile: Toggle visibility
            if (sidebar.classList.contains('mobile-hidden')) {
                sidebar.classList.remove('mobile-hidden');
                sidebarOverlay.classList.add('active');
            } else {
                sidebar.classList.add('mobile-hidden');
                sidebarOverlay.classList.remove('active');
            }
        } else {
            // Desktop: Toggle collapse
            sidebar.classList.toggle('collapsed');
            localStorage.setItem('sidebar-collapsed', sidebar.classList.contains('collapsed'));
        }
    }

    closeSidebar() {
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        
        if (window.innerWidth <= 768) {
            sidebar.classList.add('mobile-hidden');
            sidebarOverlay.classList.remove('active');
        }
    }

    handleResponsiveSidebar() {
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        
        if (window.innerWidth <= 768) {
            sidebar.classList.add('mobile-hidden');
            sidebar.classList.remove('collapsed');
            sidebarOverlay.classList.remove('active');
        } else {
            sidebar.classList.remove('mobile-hidden');
            sidebarOverlay.classList.remove('active');
            
            const isCollapsed = localStorage.getItem('sidebar-collapsed') === 'true';
            sidebar.classList.toggle('collapsed', isCollapsed);
        }
    }

    setActiveNavItem() {
        const currentPath = window.location.pathname;
        const sidebarItems = document.querySelectorAll('.sidebar-item');
        
        sidebarItems.forEach(item => {
            item.classList.remove('active');
            
            const href = item.getAttribute('href');
            if (href && href !== '#') {
                const isActive = currentPath === href || 
                    (currentPath === '/' && href.includes('index')) ||
                    (currentPath.includes('/artists') && href.includes('artists')) ||
                    (currentPath.includes('/videos') && href.includes('videos')) ||
                    (currentPath.includes('/mvtv') && href.includes('mvtv')) ||
                    (currentPath.includes('/settings') && href.includes('settings'));
                
                if (isActive) {
                    item.classList.add('active');
                }
            }
        });
    }

    // Version Information
    async loadVersionInfo() {
        try {
            const response = await fetch('/api/health/version');
            const data = await response.json();
            
            const versionElement = document.getElementById('versionInfo');
            if (versionElement) {
                const version = data.version || 'unknown';
                const commit = data.git_commit || 'unknown';
                versionElement.textContent = `v${version} (${commit})`;
            }
        } catch (error) {
            console.warn('Failed to load version info:', error);
            const versionElement = document.getElementById('versionInfo');
            if (versionElement) {
                versionElement.textContent = 'v1.0.0';
            }
        }
    }

    // Utility Functions
    goToUserCredentials() {
        window.location.href = '/settings';
        
        setTimeout(() => {
            const userCredentialsSection = document.getElementById('userCredentialsSection');
            if (userCredentialsSection) {
                if (userCredentialsSection.style.display === 'none') {
                    userCredentialsSection.style.display = 'block';
                }
                userCredentialsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        }, 500);
    }

    async logout() {
        if (!confirm('Are you sure you want to logout?')) return;
        
        try {
            // Try different logout endpoints based on which auth system is active
            let logoutEndpoint = '/simple-auth/logout';
            let response;
            
            // First try simple auth logout (since we're running simple auth mode)
            response = await fetch('/simple-auth/logout', { 
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
            });
            
            // If simple auth returns 404, try dynamic logout
            if (response.status === 404) {
                console.log('Simple auth logout not found, trying dynamic logout');
                response = await fetch('/auth/dynamic-logout', { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                });
                logoutEndpoint = '/auth/dynamic-logout';
            }
            
            // If still 404, try full auth system
            if (response.status === 404) {
                console.log('Dynamic logout not found, trying full auth logout');
                response = await fetch('/auth/logout', { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                });
                logoutEndpoint = '/auth/logout';
            }
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status} from ${logoutEndpoint}`);
            }
            
            const data = await response.json();
            
            if (data.success) {
                this.hideUserMenu();
                // Redirect based on auth system
                if (logoutEndpoint === '/simple-auth/logout') {
                    window.location.href = '/simple-auth/login';
                } else if (logoutEndpoint === '/auth/dynamic-logout') {
                    window.location.href = '/auth/login';
                } else {
                    window.location.href = '/';
                }
            } else {
                console.error('Logout failed:', data);
                alert('Logout failed: ' + (data.error || data.message || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error during logout:', error);
            alert('Logout failed: ' + error.message);
        }
    }
}

// Global functions for backward compatibility
window.goToUserCredentials = function() {
    window.mvidarrCore?.goToUserCredentials();
};

window.logout = function() {
    window.mvidarrCore?.logout();
};

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.mvidarrCore = new MVidarrCore();
    });
} else {
    window.mvidarrCore = new MVidarrCore();
}