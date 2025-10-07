/**
 * Video Virtualization Integration
 * Connects virtualization engine with existing MVidarr video management
 */

class VideoVirtualizationIntegration {
    constructor() {
        this.virtualization = null;
        this.originalLoadVideos = null;
        this.currentVideos = [];
        this.currentPage = 1;
        this.totalPages = 1;
        this.pageSize = 50; // Virtualization can handle many more items efficiently
        this.isInitialized = false;
        this.performanceMonitor = null;
        
        this.init();
    }
    
    init() {
        // Wait for DOM and existing scripts to load
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => this.initializeVirtualization());
        } else {
            this.initializeVirtualization();
        }
    }
    
    initializeVirtualization() {
        // Check if we're on a video page
        if (!this.isVideoPage()) {
            return;
        }
        
        // Find or create video container
        const container = this.setupVideoContainer();
        if (!container) {
            console.warn('Could not setup video container for virtualization');
            return;
        }
        
        // Initialize virtualization
        this.virtualization = new VideoVirtualization({
            itemHeight: this.calculateOptimalItemHeight(),
            bufferSize: 8,
            threshold: 100,
            onVideoSelect: this.handleVideoSelection.bind(this),
            onVideoAction: this.handleVideoAction.bind(this)
        });
        
        // Mount virtualization
        this.virtualization.mount(container, []);
        
        // Hook into existing video loading system
        this.hookIntoVideoLoading();
        
        // Setup performance monitoring
        this.setupPerformanceMonitoring();
        
        // Setup event listeners
        this.setupEventListeners();
        
        // Load initial videos
        this.loadVirtualizedVideos();
        
        this.isInitialized = true;
        console.log('Video virtualization integration initialized');
        
        // Show initialization success notification
        if (window.uiEnhancements) {
            window.uiEnhancements.success(
                'Performance Enhanced',
                'Video list virtualization enabled for improved performance with large datasets'
            );
        }
    }
    
    // ========================================
    // SETUP METHODS
    // ========================================
    
    isVideoPage() {
        return window.location.pathname.includes('/videos') || 
               document.querySelector('.videos-container, .videos-grid') !== null;
    }
    
    setupVideoContainer() {
        // Look for existing video grid
        const existingGrid = document.querySelector('.videos-grid, .video-grid, .videos-container .row');
        
        if (existingGrid) {
            // Create virtualized container
            const virtualContainer = document.createElement('div');
            virtualContainer.className = 'virtualized-video-container';
            virtualContainer.id = 'virtualized-video-grid';
            
            // Style the container
            Object.assign(virtualContainer.style, {
                width: '100%',
                minHeight: '600px',
                background: 'var(--bg-primary)',
                borderRadius: 'var(--radius-lg)',
                padding: 'var(--space-4)',
                marginTop: 'var(--space-4)'
            });
            
            // Insert before existing grid
            existingGrid.parentNode.insertBefore(virtualContainer, existingGrid);
            
            // Hide original grid
            existingGrid.style.display = 'none';
            existingGrid.setAttribute('data-virtualized', 'true');
            
            return virtualContainer;
        }
        
        return null;
    }
    
    calculateOptimalItemHeight() {
        // Base height for video cards
        const baseHeight = 200;
        
        // Adjust based on screen size
        if (window.innerWidth < 768) {
            return baseHeight + 100; // Mobile needs more space for stacked layout
        } else if (window.innerWidth < 1200) {
            return baseHeight + 50; // Tablet adjustment
        }
        
        return baseHeight;
    }
    
    hookIntoVideoLoading() {
        // Store original loadVideos function if it exists
        if (typeof window.loadVideos === 'function') {
            this.originalLoadVideos = window.loadVideos;
            
            // Replace with virtualized version
            window.loadVideos = this.loadVirtualizedVideos.bind(this);
        }
        
        // Hook into pagination if it exists
        if (typeof window.goToPage === 'function') {
            const originalGoToPage = window.goToPage;
            window.goToPage = (page) => {
                this.currentPage = page;
                this.loadVirtualizedVideos();
            };
        }
        
        // Hook into search functionality
        if (typeof window.searchVideos === 'function') {
            const originalSearchVideos = window.searchVideos;
            window.searchVideos = (...args) => {
                // Reset to first page for new search
                this.currentPage = 1;
                this.loadVirtualizedVideos();
            };
        }
    }
    
    setupPerformanceMonitoring() {
        if (!this.virtualization) return;
        
        this.performanceMonitor = {
            renderCount: 0,
            totalRenderTime: 0,
            maxRenderTime: 0,
            lastMetrics: null
        };
        
        // Monitor virtualization renders
        this.virtualization.container.addEventListener('virtualRender', (event) => {
            const metrics = event.detail;
            this.performanceMonitor.renderCount++;
            this.performanceMonitor.totalRenderTime += metrics.renderTime;
            this.performanceMonitor.maxRenderTime = Math.max(this.performanceMonitor.maxRenderTime, metrics.renderTime);
            this.performanceMonitor.lastMetrics = metrics;
            
            // Log performance warnings
            if (metrics.renderTime > 16) { // More than one frame at 60fps
                console.warn(`Slow virtual render: ${metrics.renderTime.toFixed(2)}ms for ${metrics.visibleItems} items`);
            }
        });
        
        // Performance reporting interval
        setInterval(() => {
            if (this.performanceMonitor.renderCount > 0) {
                const avgRenderTime = this.performanceMonitor.totalRenderTime / this.performanceMonitor.renderCount;
                console.log('Virtualization Performance:', {
                    averageRenderTime: avgRenderTime.toFixed(2) + 'ms',
                    maxRenderTime: this.performanceMonitor.maxRenderTime.toFixed(2) + 'ms',
                    totalRenders: this.performanceMonitor.renderCount,
                    currentItems: this.currentVideos.length
                });
            }
        }, 30000); // Every 30 seconds
    }
    
    setupEventListeners() {
        if (!this.virtualization) return;
        
        // Handle bulk actions
        document.addEventListener('videoSelectionChanged', (event) => {
            if (window.videoManagementUI) {
                window.videoManagementUI.updateBulkActions();
            }
        });
        
        // Handle video updates
        document.addEventListener('videoUpdated', (event) => {
            const { videoId, updates } = event.detail;
            this.updateVideoInList(videoId, updates);
        });
        
        // Handle video deletion
        document.addEventListener('videoDeleted', (event) => {
            const { videoId } = event.detail;
            this.removeVideoFromList(videoId);
        });
        
        // Handle new video addition
        document.addEventListener('videoAdded', (event) => {
            const { video } = event.detail;
            this.addVideoToList(video);
        });
        
        // Handle context menu
        this.virtualization.container.addEventListener('videoContextMenu', (event) => {
            this.showVideoContextMenu(event.detail);
        });
        
        // Handle window resize for responsive adjustments
        window.addEventListener('resize', () => {
            if (this.virtualization) {
                const newItemHeight = this.calculateOptimalItemHeight();
                if (newItemHeight !== this.virtualization.itemHeight) {
                    this.virtualization.setItemHeight(newItemHeight);
                }
            }
        });
    }
    
    // ========================================
    // VIDEO LOADING & DATA MANAGEMENT
    // ========================================
    
    async loadVirtualizedVideos() {
        if (!this.virtualization) return;
        
        this.showLoadingState();
        
        try {
            // Build API request
            const params = new URLSearchParams({
                page: this.currentPage,
                page_size: this.pageSize, // Larger page size for virtualization
                ...this.getCurrentFilters()
            });
            
            const response = await fetch(`/api/videos?${params}`);
            const data = await response.json();
            
            if (response.ok) {
                this.currentVideos = data.videos || [];
                this.totalPages = data.total_pages || 1;
                
                // Update virtualization with new data
                this.virtualization.updateItems(this.currentVideos);
                
                // Update pagination UI if it exists
                this.updatePaginationUI(data);
                
                // Show results info
                this.showResultsInfo(data);
                
                console.log(`Loaded ${this.currentVideos.length} videos for virtualization`);
            } else {
                throw new Error(data.error || 'Failed to load videos');
            }
        } catch (error) {
            console.error('Error loading virtualized videos:', error);
            this.showErrorState(error.message);
            
            if (window.uiEnhancements) {
                window.uiEnhancements.error('Loading Error', error.message);
            }
        }
    }
    
    getCurrentFilters() {
        const filters = {};
        
        // Get search term
        const searchInput = document.querySelector('#searchTerm, [name="search"]');
        if (searchInput && searchInput.value.trim()) {
            filters.search = searchInput.value.trim();
        }
        
        // Get artist filter
        const artistSelect = document.querySelector('#artistFilter, [name="artist"]');
        if (artistSelect && artistSelect.value) {
            filters.artist = artistSelect.value;
        }
        
        // Get status filter
        const statusSelect = document.querySelector('#statusFilter, [name="status"]');
        if (statusSelect && statusSelect.value) {
            filters.status = statusSelect.value;
        }
        
        // Get year filter
        const yearInput = document.querySelector('#yearFilter, [name="year"]');
        if (yearInput && yearInput.value) {
            filters.year = yearInput.value;
        }
        
        // Get sort options
        const sortSelect = document.querySelector('#sortBy, [name="sort"]');
        if (sortSelect && sortSelect.value) {
            filters.sort_by = sortSelect.value;
        }
        
        const orderSelect = document.querySelector('#sortOrder, [name="order"]');
        if (orderSelect && orderSelect.value) {
            filters.sort_order = orderSelect.value;
        }
        
        return filters;
    }
    
    updateVideoInList(videoId, updates) {
        const videoIndex = this.currentVideos.findIndex(v => v.id === videoId);
        if (videoIndex !== -1) {
            this.currentVideos[videoIndex] = { ...this.currentVideos[videoIndex], ...updates };
            this.virtualization.updateItem(videoIndex, this.currentVideos[videoIndex]);
        }
    }
    
    removeVideoFromList(videoId) {
        const videoIndex = this.currentVideos.findIndex(v => v.id === videoId);
        if (videoIndex !== -1) {
            this.currentVideos.splice(videoIndex, 1);
            this.virtualization.removeItem(videoIndex);
        }
    }
    
    addVideoToList(video) {
        this.currentVideos.unshift(video); // Add to beginning
        this.virtualization.addItem(video, 0);
    }
    
    // ========================================
    // UI STATE MANAGEMENT
    // ========================================
    
    showLoadingState() {
        if (!this.virtualization || !this.virtualization.container) return;
        
        const loadingElement = document.createElement('div');
        loadingElement.className = 'virtual-loading';
        loadingElement.innerHTML = `
            <div class="loading-spinner">
                <img src="/static/MVidarr.png" alt="MVidarr" class="spinning mvidarr-logo-spinner" style="width: 24px; height: 24px;">
            </div>
            <div>Loading videos...</div>
        `;
        
        this.virtualization.container.innerHTML = '';
        this.virtualization.container.appendChild(loadingElement);
    }
    
    showErrorState(message) {
        if (!this.virtualization || !this.virtualization.container) return;
        
        const errorElement = document.createElement('div');
        errorElement.className = 'virtual-error';
        errorElement.innerHTML = `
            <div style="text-align: center; padding: var(--space-8); color: var(--status-error);">
                <iconify-icon icon="tabler:alert-circle" style="font-size: 3rem; margin-bottom: var(--space-4);"></iconify-icon>
                <h3>Error Loading Videos</h3>
                <p>${message}</p>
                <button class="btn btn-primary" onclick="window.videoVirtualizationIntegration.loadVirtualizedVideos()">
                    Try Again
                </button>
            </div>
        `;
        
        this.virtualization.container.innerHTML = '';
        this.virtualization.container.appendChild(errorElement);
    }
    
    showResultsInfo(data) {
        const resultsInfo = document.querySelector('.search-results-info');
        if (resultsInfo && data.total_count !== undefined) {
            const start = (this.currentPage - 1) * this.pageSize + 1;
            const end = Math.min(start + this.currentVideos.length - 1, data.total_count);
            
            resultsInfo.innerHTML = `
                Showing ${start}-${end} of ${data.total_count} videos
                ${data.filter_applied ? '(filtered)' : ''}
                <span style="margin-left: var(--space-4); color: var(--text-muted);">
                    Virtual rendering enabled for optimal performance
                </span>
            `;
        }
    }
    
    updatePaginationUI(data) {
        // Update page info
        const pageInfo = document.querySelector('.pagination-info');
        if (pageInfo) {
            pageInfo.textContent = `Page ${this.currentPage} of ${this.totalPages}`;
        }
        
        // Update page input
        const pageInput = document.querySelector('.page-input');
        if (pageInput) {
            pageInput.value = this.currentPage;
            pageInput.max = this.totalPages;
        }
        
        // Update navigation buttons
        const prevBtn = document.querySelector('.pagination-btn[onclick*="goToPage"][onclick*="' + (this.currentPage - 1) + '"]');
        const nextBtn = document.querySelector('.pagination-btn[onclick*="goToPage"][onclick*="' + (this.currentPage + 1) + '"]');
        
        if (prevBtn) prevBtn.disabled = this.currentPage <= 1;
        if (nextBtn) nextBtn.disabled = this.currentPage >= this.totalPages;
    }
    
    // ========================================
    // EVENT HANDLERS
    // ========================================
    
    handleVideoSelection(videoId, selected, selectedVideos) {
        // Update bulk actions UI
        if (window.videoManagementUI) {
            if (videoId) {
                // Single video selection
                if (selected) {
                    window.videoManagementUI.selectedVideos.add(videoId);
                } else {
                    window.videoManagementUI.selectedVideos.delete(videoId);
                }
            } else {
                // Bulk selection change
                window.videoManagementUI.selectedVideos = new Set(selectedVideos);
            }
            
            window.videoManagementUI.updateBulkActions();
        }
        
        // Dispatch selection event
        document.dispatchEvent(new CustomEvent('videoSelectionChanged', {
            detail: { selectedVideos: Array.from(selectedVideos) }
        }));
    }
    
    handleVideoAction(action, videoId) {
        // Delegate to existing video management system
        if (window.videoManagementUI) {
            const video = this.currentVideos.find(v => v.id === videoId);
            if (video) {
                const card = this.virtualization.viewport.querySelector(`[data-video-id="${videoId}"]`);
                window.videoManagementUI.executeQuickAction(action, videoId, card);
            }
        }
    }
    
    showVideoContextMenu(detail) {
        const { video, x, y } = detail;
        
        // Create context menu
        const menu = document.createElement('div');
        menu.className = 'context-menu';
        menu.style.cssText = `
            position: fixed;
            top: ${y}px;
            left: ${x}px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-primary);
            border-radius: var(--radius-md);
            padding: var(--space-2);
            z-index: 9999;
            box-shadow: var(--shadow-lg);
            min-width: 150px;
        `;
        
        const actions = [
            { label: 'View Details', action: 'viewVideo', icon: 'tabler:eye' },
            { label: 'Download', action: 'downloadVideo', icon: 'tabler:download' },
            { label: 'Delete', action: 'deleteVideo', icon: 'tabler:trash' }
        ];
        
        actions.forEach(item => {
            const menuItem = document.createElement('button');
            menuItem.className = 'btn btn-ghost btn-sm context-menu-item';
            menuItem.innerHTML = `<iconify-icon icon="${item.icon}"></iconify-icon> ${item.label}`;
            menuItem.onclick = () => {
                this.handleVideoAction(item.action, video.id);
                menu.remove();
            };
            menu.appendChild(menuItem);
        });
        
        document.body.appendChild(menu);
        
        // Remove on click outside
        setTimeout(() => {
            document.addEventListener('click', () => menu.remove(), { once: true });
        }, 100);
    }
    
    // ========================================
    // PUBLIC API
    // ========================================
    
    refresh() {
        this.loadVirtualizedVideos();
    }
    
    selectAll() {
        if (this.virtualization) {
            this.virtualization.selectAll();
        }
    }
    
    clearSelection() {
        if (this.virtualization) {
            this.virtualization.clearSelection();
        }
    }
    
    scrollToVideo(videoId) {
        const index = this.currentVideos.findIndex(v => v.id === videoId);
        if (index !== -1 && this.virtualization) {
            this.virtualization.scrollToIndex(index);
        }
    }
    
    getPerformanceMetrics() {
        const virtualMetrics = this.virtualization ? this.virtualization.getPerformanceMetrics() : {};
        return {
            ...virtualMetrics,
            integration: this.performanceMonitor
        };
    }
    
    destroy() {
        if (this.virtualization) {
            this.virtualization.destroy();
            this.virtualization = null;
        }
        
        // Restore original functions
        if (this.originalLoadVideos) {
            window.loadVideos = this.originalLoadVideos;
        }
        
        // Show original grid
        const originalGrid = document.querySelector('[data-virtualized="true"]');
        if (originalGrid) {
            originalGrid.style.display = '';
            originalGrid.removeAttribute('data-virtualized');
        }
        
        // Remove virtualized container
        const virtualContainer = document.getElementById('virtualized-video-grid');
        if (virtualContainer) {
            virtualContainer.remove();
        }
        
        console.log('Video virtualization integration destroyed');
    }
}

// Initialize integration
window.videoVirtualizationIntegration = new VideoVirtualizationIntegration();

// Export for global access
window.VideoVirtualizationIntegration = VideoVirtualizationIntegration;