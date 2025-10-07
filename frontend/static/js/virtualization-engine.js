/**
 * Virtualization Engine for Large Datasets
 * Efficient rendering of large lists using virtual scrolling
 */

class VirtualizationEngine {
    constructor(options = {}) {
        this.container = null;
        this.items = [];
        this.itemHeight = options.itemHeight || 250; // Default video card height
        this.bufferSize = options.bufferSize || 10; // Items to render outside viewport
        this.scrollContainer = null;
        this.viewportHeight = 0;
        this.scrollTop = 0;
        this.startIndex = 0;
        this.endIndex = 0;
        this.renderFunction = options.renderFunction || this.defaultRenderFunction;
        this.threshold = options.threshold || 100; // Scroll threshold for updates
        this.lastScrollTime = 0;
        this.scrollRAF = null;
        
        // Performance monitoring
        this.renderTime = 0;
        this.totalRenders = 0;
        
        this.init();
    }
    
    init() {
        this.setupScrollListener();
        this.setupResizeListener();
    }
    
    // ========================================
    // INITIALIZATION & SETUP
    // ========================================
    
    mount(container, items = []) {
        this.container = container;
        this.scrollContainer = this.findScrollContainer(container);
        this.items = items;
        
        this.setupVirtualContainer();
        this.updateViewportDimensions();
        this.render();
        
        return this;
    }
    
    findScrollContainer(element) {
        let parent = element.parentElement;
        while (parent) {
            const overflow = window.getComputedStyle(parent).overflow;
            if (overflow === 'auto' || overflow === 'scroll') {
                return parent;
            }
            parent = parent.parentElement;
        }
        return window;
    }
    
    setupVirtualContainer() {
        if (!this.container) return;
        
        // Add virtualization classes
        this.container.classList.add('virtual-list');
        this.container.style.position = 'relative';
        
        // Create virtual spacer for total height
        this.spacer = document.createElement('div');
        this.spacer.className = 'virtual-spacer';
        this.spacer.style.position = 'absolute';
        this.spacer.style.top = '0';
        this.spacer.style.left = '0';
        this.spacer.style.right = '0';
        this.spacer.style.pointerEvents = 'none';
        
        this.container.appendChild(this.spacer);
        
        // Create viewport container
        this.viewport = document.createElement('div');
        this.viewport.className = 'virtual-viewport';
        this.viewport.style.position = 'relative';
        this.viewport.style.zIndex = '1';
        
        this.container.appendChild(this.viewport);
        
        // Update total height
        this.updateTotalHeight();
    }
    
    updateTotalHeight() {
        if (this.spacer) {
            const totalHeight = this.items.length * this.itemHeight;
            this.spacer.style.height = `${totalHeight}px`;
        }
    }
    
    // ========================================
    // SCROLL HANDLING
    // ========================================
    
    setupScrollListener() {
        const handleScroll = () => {
            if (this.scrollRAF) {
                cancelAnimationFrame(this.scrollRAF);
            }
            
            this.scrollRAF = requestAnimationFrame(() => {
                this.updateScrollPosition();
                this.checkRenderUpdate();
            });
        };
        
        if (this.scrollContainer === window) {
            window.addEventListener('scroll', handleScroll, { passive: true });
        } else if (this.scrollContainer) {
            this.scrollContainer.addEventListener('scroll', handleScroll, { passive: true });
        }
    }
    
    setupResizeListener() {
        const handleResize = () => {
            this.updateViewportDimensions();
            this.render();
        };
        
        window.addEventListener('resize', handleResize, { passive: true });
    }
    
    updateScrollPosition() {
        if (this.scrollContainer === window) {
            this.scrollTop = window.pageYOffset || document.documentElement.scrollTop;
        } else if (this.scrollContainer) {
            this.scrollTop = this.scrollContainer.scrollTop;
        }
    }
    
    updateViewportDimensions() {
        if (this.scrollContainer === window) {
            this.viewportHeight = window.innerHeight;
        } else if (this.scrollContainer) {
            this.viewportHeight = this.scrollContainer.clientHeight;
        }
    }
    
    checkRenderUpdate() {
        const containerRect = this.container.getBoundingClientRect();
        const containerTop = this.scrollContainer === window ? 
            containerRect.top + this.scrollTop : 
            containerRect.top - this.scrollContainer.getBoundingClientRect().top + this.scrollTop;
        
        // Calculate visible range
        const visibleStart = Math.max(0, this.scrollTop - containerTop);
        const visibleEnd = visibleStart + this.viewportHeight;
        
        const newStartIndex = Math.max(0, Math.floor(visibleStart / this.itemHeight) - this.bufferSize);
        const newEndIndex = Math.min(this.items.length, Math.ceil(visibleEnd / this.itemHeight) + this.bufferSize);
        
        // Only re-render if range changed significantly
        if (Math.abs(newStartIndex - this.startIndex) > this.threshold / this.itemHeight || 
            Math.abs(newEndIndex - this.endIndex) > this.threshold / this.itemHeight) {
            this.startIndex = newStartIndex;
            this.endIndex = newEndIndex;
            this.render();
        }
    }
    
    // ========================================
    // RENDERING
    // ========================================
    
    render() {
        if (!this.viewport || !this.items.length) return;
        
        const startTime = performance.now();
        
        // Clear current viewport
        this.viewport.innerHTML = '';
        
        // Render visible items
        for (let i = this.startIndex; i < this.endIndex; i++) {
            if (i >= this.items.length) break;
            
            const item = this.items[i];
            const element = this.renderItem(item, i);
            
            if (element) {
                // Position element absolutely
                element.style.position = 'absolute';
                element.style.top = `${i * this.itemHeight}px`;
                element.style.left = '0';
                element.style.right = '0';
                element.style.height = `${this.itemHeight}px`;
                
                this.viewport.appendChild(element);
            }
        }
        
        // Update performance metrics
        this.renderTime = performance.now() - startTime;
        this.totalRenders++;
        
        // Dispatch render event
        this.container.dispatchEvent(new CustomEvent('virtualRender', {
            detail: {
                startIndex: this.startIndex,
                endIndex: this.endIndex,
                renderTime: this.renderTime,
                totalItems: this.items.length,
                visibleItems: this.endIndex - this.startIndex
            }
        }));
    }
    
    renderItem(item, index) {
        return this.renderFunction(item, index, this.itemHeight);
    }
    
    defaultRenderFunction(item, index, height) {
        const element = document.createElement('div');
        element.className = 'virtual-item';
        element.style.height = `${height}px`;
        element.style.padding = '10px';
        element.style.borderBottom = '1px solid var(--border-primary)';
        element.textContent = `Item ${index}: ${JSON.stringify(item).slice(0, 50)}...`;
        return element;
    }
    
    // ========================================
    // DATA MANAGEMENT
    // ========================================
    
    updateItems(newItems) {
        this.items = newItems;
        this.updateTotalHeight();
        
        // Reset scroll position if needed
        if (this.scrollTop > this.items.length * this.itemHeight) {
            this.scrollToTop();
        }
        
        this.render();
    }
    
    addItem(item, index = null) {
        if (index === null) {
            this.items.push(item);
        } else {
            this.items.splice(index, 0, item);
        }
        
        this.updateTotalHeight();
        this.render();
    }
    
    removeItem(index) {
        if (index >= 0 && index < this.items.length) {
            this.items.splice(index, 1);
            this.updateTotalHeight();
            this.render();
        }
    }
    
    updateItem(index, newItem) {
        if (index >= 0 && index < this.items.length) {
            this.items[index] = newItem;
            
            // Only re-render if item is currently visible
            if (index >= this.startIndex && index < this.endIndex) {
                this.render();
            }
        }
    }
    
    // ========================================
    // NAVIGATION & UTILITY
    // ========================================
    
    scrollToIndex(index, behavior = 'smooth') {
        if (index < 0 || index >= this.items.length) return;
        
        const targetScrollTop = index * this.itemHeight;
        
        if (this.scrollContainer === window) {
            const containerRect = this.container.getBoundingClientRect();
            const containerTop = containerRect.top + window.pageYOffset;
            
            window.scrollTo({
                top: containerTop + targetScrollTop,
                behavior
            });
        } else if (this.scrollContainer) {
            this.scrollContainer.scrollTo({
                top: targetScrollTop,
                behavior
            });
        }
    }
    
    scrollToTop(behavior = 'smooth') {
        this.scrollToIndex(0, behavior);
    }
    
    scrollToBottom(behavior = 'smooth') {
        this.scrollToIndex(this.items.length - 1, behavior);
    }
    
    getVisibleRange() {
        return {
            start: this.startIndex,
            end: this.endIndex,
            total: this.items.length
        };
    }
    
    getPerformanceMetrics() {
        return {
            totalRenders: this.totalRenders,
            averageRenderTime: this.totalRenders > 0 ? this.renderTime / this.totalRenders : 0,
            lastRenderTime: this.renderTime,
            totalItems: this.items.length,
            itemHeight: this.itemHeight,
            bufferSize: this.bufferSize
        };
    }
    
    // ========================================
    // CONFIGURATION
    // ========================================
    
    setItemHeight(height) {
        this.itemHeight = height;
        this.updateTotalHeight();
        this.render();
    }
    
    setBufferSize(size) {
        this.bufferSize = size;
        this.render();
    }
    
    setRenderFunction(fn) {
        this.renderFunction = fn;
        this.render();
    }
    
    // ========================================
    // CLEANUP
    // ========================================
    
    destroy() {
        // Cancel any pending RAF
        if (this.scrollRAF) {
            cancelAnimationFrame(this.scrollRAF);
        }
        
        // Remove event listeners
        if (this.scrollContainer === window) {
            window.removeEventListener('scroll', this.handleScroll);
        } else if (this.scrollContainer) {
            this.scrollContainer.removeEventListener('scroll', this.handleScroll);
        }
        
        window.removeEventListener('resize', this.handleResize);
        
        // Clear container
        if (this.container) {
            this.container.innerHTML = '';
            this.container.classList.remove('virtual-list');
        }
        
        // Reset properties
        this.container = null;
        this.viewport = null;
        this.spacer = null;
        this.items = [];
    }
}

// Video-specific virtualization wrapper
class VideoVirtualization extends VirtualizationEngine {
    constructor(options = {}) {
        super({
            itemHeight: 280, // Standard video card height
            bufferSize: 5,
            threshold: 50,
            ...options
        });
        
        this.selectedVideos = new Set();
        this.onVideoSelect = options.onVideoSelect || (() => {});
        this.onVideoAction = options.onVideoAction || (() => {});
    }
    
    renderItem(video, index, height) {
        const card = document.createElement('div');
        card.className = 'video-card virtual-video-card';
        card.dataset.videoId = video.id;
        card.dataset.index = index;
        
        // Check if selected
        if (this.selectedVideos.has(video.id)) {
            card.classList.add('selected');
        }
        
        card.innerHTML = `
            <div class="video-card-content">
                <div class="video-thumbnail">
                    <img src="${video.thumbnail || '/static/images/default-thumbnail.jpg'}" 
                         alt="${this.escapeHtml(video.title)}"
                         loading="lazy">
                    <div class="video-duration">${this.formatDuration(video.duration)}</div>
                    <div class="video-status-badge status-${video.status.toLowerCase()}">${video.status}</div>
                </div>
                <div class="video-info">
                    <h3 class="video-title" title="${this.escapeHtml(video.title)}">${this.escapeHtml(video.title)}</h3>
                    <p class="video-artist">${this.escapeHtml(video.artist_name)}</p>
                    <div class="video-metadata">
                        <span class="video-year">${video.year || 'Unknown'}</span>
                        <span class="video-quality">${video.quality || 'Unknown'}</span>
                        <span class="video-size">${this.formatFileSize(video.file_size)}</span>
                    </div>
                    <div class="video-dates">
                        <small>Added: ${this.formatDate(video.created_at)}</small>
                        ${video.updated_at !== video.created_at ? 
                            `<small>Updated: ${this.formatDate(video.updated_at)}</small>` : ''}
                    </div>
                </div>
                <div class="video-actions">
                    <button data-video-id="${video.id}" data-action="download" class="btn-icon" title="Download Video">
                        <iconify-icon icon="tabler:download"></iconify-icon>
                    </button>
                    <button data-video-id="${video.id}" data-action="add-to-playlist" class="btn-icon" title="Add to Playlist">
                        <iconify-icon icon="tabler:playlist-add"></iconify-icon>
                    </button>
                    <button data-video-id="${video.id}" data-action="refresh-metadata" class="btn-icon" title="Refresh Metadata">
                        <iconify-icon icon="tabler:refresh"></iconify-icon>
                    </button>
                    <button data-video-id="${video.id}" data-action="delete" class="btn-icon btn-danger" title="Delete Video">
                        <iconify-icon icon="tabler:trash"></iconify-icon>
                    </button>
                    <label class="video-select">
                        <input type="checkbox" ${this.selectedVideos.has(video.id) ? 'checked' : ''}>
                        <span class="checkmark"></span>
                    </label>
                </div>
            </div>
        `;
        
        // Add event listeners
        this.attachVideoCardListeners(card, video);
        
        return card;
    }
    
    attachVideoCardListeners(card, video) {
        const checkbox = card.querySelector('input[type="checkbox"]');
        const actionButtons = card.querySelectorAll('[data-action]');
        
        // Selection handling
        if (checkbox) {
            checkbox.addEventListener('change', (e) => {
                e.stopPropagation();
                const isSelected = e.target.checked;
                
                if (isSelected) {
                    this.selectedVideos.add(video.id);
                    card.classList.add('selected');
                } else {
                    this.selectedVideos.delete(video.id);
                    card.classList.remove('selected');
                }
                
                this.onVideoSelect(video.id, isSelected, this.selectedVideos);
            });
        }
        
        // Action button handling
        actionButtons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                
                const action = button.getAttribute('data-action');
                
                // Handle playlist action specifically
                if (action === 'add-to-playlist') {
                    if (window.addSingleVideoToPlaylist) {
                        window.addSingleVideoToPlaylist(video.id);
                    } else {
                        console.error('addSingleVideoToPlaylist function not found');
                    }
                } else {
                    // Handle other actions through the video action callback
                    this.onVideoAction(action, video.id);
                }
            });
        });
        
        // Card click handling
        card.addEventListener('click', (e) => {
            if (!e.target.closest('.video-select') && !e.target.closest('[data-action]') && !e.target.closest('.btn-icon')) {
                // Toggle selection on card click
                const isSelected = this.selectedVideos.has(video.id);
                if (checkbox) {
                    checkbox.checked = !isSelected;
                    checkbox.dispatchEvent(new Event('change'));
                }
            }
        });
        
        // Keyboard support
        card.setAttribute('tabindex', '0');
        card.setAttribute('role', 'gridcell');
        card.setAttribute('aria-label', `${video.title} by ${video.artist_name}`);
        
        card.addEventListener('keydown', (e) => {
            switch (e.key) {
                case 'Enter':
                case ' ':
                    e.preventDefault();
                    if (checkbox) {
                        checkbox.checked = !checkbox.checked;
                        checkbox.dispatchEvent(new Event('change'));
                    }
                    break;
            }
        });
        
        // Context menu for quick actions
        card.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            this.showVideoContextMenu(e, video);
        });
    }
    
    showVideoContextMenu(event, video) {
        // Dispatch context menu event for integration with existing systems
        this.container.dispatchEvent(new CustomEvent('videoContextMenu', {
            detail: {
                video,
                x: event.clientX,
                y: event.clientY
            }
        }));
    }
    
    // ========================================
    // SELECTION MANAGEMENT
    // ========================================
    
    selectVideo(videoId, selected = true) {
        if (selected) {
            this.selectedVideos.add(videoId);
        } else {
            this.selectedVideos.delete(videoId);
        }
        
        // Update visible cards
        const card = this.viewport.querySelector(`[data-video-id="${videoId}"]`);
        if (card) {
            const checkbox = card.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = selected;
            }
            card.classList.toggle('selected', selected);
        }
        
        this.onVideoSelect(videoId, selected, this.selectedVideos);
    }
    
    selectAll() {
        this.items.forEach(video => {
            this.selectedVideos.add(video.id);
        });
        this.render(); // Re-render to update all checkboxes
        this.onVideoSelect(null, true, this.selectedVideos);
    }
    
    clearSelection() {
        this.selectedVideos.clear();
        this.render(); // Re-render to update all checkboxes
        this.onVideoSelect(null, false, this.selectedVideos);
    }
    
    getSelectedVideos() {
        return Array.from(this.selectedVideos);
    }
    
    // ========================================
    // UTILITY METHODS
    // ========================================
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text || '';
        return div.innerHTML;
    }
    
    formatDuration(seconds) {
        if (!seconds) return 'Unknown';
        const mins = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }
    
    formatFileSize(bytes) {
        if (!bytes) return 'Unknown';
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${sizes[i]}`;
    }
    
    formatDate(dateString) {
        if (!dateString) return 'Unknown';
        return new Date(dateString).toLocaleDateString();
    }
}

// Export for global use
window.VirtualizationEngine = VirtualizationEngine;
window.VideoVirtualization = VideoVirtualization;

// Auto-initialize video virtualization if video grid exists
document.addEventListener('DOMContentLoaded', () => {
    const videoGrid = document.querySelector('.videos-grid, .video-grid');
    if (videoGrid && typeof loadVideos === 'function') {
        // Create enhanced video grid with virtualization
        const enhancedGrid = document.createElement('div');
        enhancedGrid.className = 'virtualized-video-grid';
        enhancedGrid.style.minHeight = '400px';
        
        // Replace existing grid
        videoGrid.parentNode.insertBefore(enhancedGrid, videoGrid);
        videoGrid.style.display = 'none'; // Hide original
        
        // Initialize virtualization
        window.videoVirtualization = new VideoVirtualization({
            onVideoSelect: (videoId, selected, selectedVideos) => {
                // Integrate with existing video management
                if (window.videoManagementUI) {
                    if (selected && videoId) {
                        window.videoManagementUI.selectVideo(videoId, selected);
                    } else if (!videoId) {
                        // Bulk selection change
                        document.dispatchEvent(new CustomEvent('videoSelectionChanged', {
                            detail: { selectedVideos: Array.from(selectedVideos) }
                        }));
                    }
                }
            }
        });
        
        // Mount to enhanced grid
        window.videoVirtualization.mount(enhancedGrid, []);
        
        console.log('Video virtualization initialized for improved performance');
    }
});