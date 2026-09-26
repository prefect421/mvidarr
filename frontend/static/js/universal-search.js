/**
 * Universal Search Component - Optimized for Performance
 * Extracted from base.html for better maintainability and caching
 */

class UniversalSearch {
    constructor() {
        this.searchInput = document.getElementById('universalSearchInput');
        this.searchResults = document.getElementById('universalSearchResults');
        this.clearButton = document.getElementById('universalSearchClear');
        this.loadingElement = document.getElementById('universalSearchLoading');
        this.noResultsElement = document.getElementById('noResultsMessage');
        this.searchMoreSection = document.getElementById('searchMoreSection');
        this.searchMoreButton = document.getElementById('searchMoreButton');
        
        this.videosSection = document.getElementById('videosSection');
        this.artistsSection = document.getElementById('artistsSection');
        this.externalSection = document.getElementById('externalSection');
        
        this.videosResults = document.getElementById('videosResults');
        this.artistsResults = document.getElementById('artistsResults');
        this.externalResults = document.getElementById('externalResults');
        
        this.videosCount = document.getElementById('videosCount');
        this.artistsCount = document.getElementById('artistsCount');
        this.externalCount = document.getElementById('externalCount');
        
        this.searchTimeout = null;
        this.isSearching = false;
        this.currentQuery = '';
        this.cache = new Map(); // Simple result caching
        
        this.init();
    }
    
    init() {
        if (!this.searchInput) return;
        
        // Use passive listeners for better scroll performance
        this.searchInput.addEventListener('input', this.debounceSearch.bind(this), { passive: true });
        this.clearButton.addEventListener('click', this.handleClear.bind(this));
        this.searchMoreButton?.addEventListener('click', this.handleSearchMore.bind(this));
        
        // Efficient event delegation
        document.addEventListener('click', this.handleDocumentClick.bind(this), { passive: true });
        this.searchResults.addEventListener('click', this.handleResultClick.bind(this));
        this.searchInput.addEventListener('focus', this.handleFocus.bind(this), { passive: true });
    }
    
    debounceSearch(e) {
        const query = e.target.value.trim();
        
        if (query.length === 0) {
            this.clearResults();
            this.clearButton.style.display = 'none';
            return;
        }
        
        this.clearButton.style.display = 'block';
        
        if (query.length < 2) {
            this.clearResults();
            return;
        }
        
        // Debounce search with shorter delay for better UX
        clearTimeout(this.searchTimeout);
        this.searchTimeout = setTimeout(() => {
            this.performSearch(query);
        }, 200); // Reduced from 300ms to 200ms
    }
    
    handleClear() {
        this.searchInput.value = '';
        this.clearResults();
        this.clearButton.style.display = 'none';
        this.searchInput.focus();
    }
    
    handleSearchMore() {
        const queryToUse = this.currentQuery || this.searchInput.value.trim();
        
        if (queryToUse) {
            const discoverUrl = `/discover?q=${encodeURIComponent(queryToUse)}`;
            window.location.href = discoverUrl;
        } else {
            window.location.href = '/discover';
        }
    }
    
    handleDocumentClick(e) {
        if (!e.target.closest('.universal-search-container')) {
            this.hideResults();
        }
    }
    
    handleResultClick(e) {
        e.stopPropagation();
    }
    
    handleFocus() {
        if (this.searchInput.value.trim().length >= 2) {
            this.showResults();
        }
    }
    
    async performSearch(query) {
        if (this.isSearching) return;
        
        // Check cache first
        if (this.cache.has(query)) {
            this.displayResults(this.cache.get(query));
            return;
        }
        
        this.isSearching = true;
        this.currentQuery = query;
        this.showLoading();
        
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 second timeout
            
            const response = await fetch(
                `/api/videos/universal-search?q=${encodeURIComponent(query)}`,
                { signal: controller.signal }
            );
            
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`Search failed: ${response.statusText}`);
            }
            
            const data = await response.json();
            
            // Cache results for 5 minutes
            this.cache.set(query, data);
            setTimeout(() => this.cache.delete(query), 300000);
            
            this.displayResults(data);
            
        } catch (error) {
            if (error.name === 'AbortError') {
                this.showError('Search timed out. Please try again.');
            } else {
                console.error('Search error:', error);
                this.showError('Search failed. Please try again.');
            }
        } finally {
            this.isSearching = false;
            this.hideLoading();
        }
    }
    
    displayResults(data) {
        this.clearSections();
        
        if (data.total === 0) {
            this.showNoResults();
            this.showSearchMore();
            return;
        }
        
        // Use requestAnimationFrame for smooth rendering
        requestAnimationFrame(() => {
            if (data.videos && data.videos.length > 0) {
                this.displayVideos(data.videos);
            }
            
            if (data.artists && data.artists.length > 0) {
                this.displayArtists(data.artists);
            }
            
            if (data.external && data.external.length > 0) {
                this.displayExternal(data.external);
            }
            
            this.showSearchMore();
            this.showResults();
        });
    }
    
    displayVideos(videos) {
        this.videosCount.textContent = videos.length;
        
        // Use DocumentFragment for efficient DOM manipulation
        const fragment = document.createDocumentFragment();
        
        videos.forEach(video => {
            const item = this.createResultItem(
                'tabler:video',
                video.title,
                `${video.artist}${video.year ? ` • ${video.year}` : ''}`,
                'View',
                () => window.location.href = video.url
            );
            fragment.appendChild(item);
        });
        
        this.videosResults.innerHTML = '';
        this.videosResults.appendChild(fragment);
        this.videosSection.style.display = 'block';
    }
    
    displayArtists(artists) {
        this.artistsCount.textContent = artists.length;
        
        const fragment = document.createDocumentFragment();
        
        artists.forEach(artist => {
            const item = this.createResultItem(
                'tabler:user',
                artist.name,
                `${artist.video_count} video${artist.video_count !== 1 ? 's' : ''}`,
                'View',
                () => window.location.href = artist.url
            );
            fragment.appendChild(item);
        });
        
        this.artistsResults.innerHTML = '';
        this.artistsResults.appendChild(fragment);
        this.artistsSection.style.display = 'block';
    }
    
    displayExternal(external) {
        this.externalCount.textContent = external.length;
        
        const fragment = document.createDocumentFragment();
        
        external.forEach(result => {
            const sourceIcon = result.source === 'YouTube' ? 'tabler:brand-youtube' : 'tabler:world';
            const item = this.createResultItem(
                sourceIcon,
                result.title,
                `${result.artist} • ${result.source}`,
                'Add',
                null,
                (e) => {
                    e.stopPropagation();
                    this.addToLibrary(result);
                }
            );
            fragment.appendChild(item);
        });
        
        this.externalResults.innerHTML = '';
        this.externalResults.appendChild(fragment);
        this.externalSection.style.display = 'block';
    }
    
    createResultItem(icon, title, subtitle, actionText, clickHandler, actionHandler) {
        const item = document.createElement('div');
        item.className = 'universal-search-result-item';
        
        item.innerHTML = `
            <iconify-icon icon="${icon}" class="universal-search-result-icon"></iconify-icon>
            <div class="universal-search-result-content">
                <div class="universal-search-result-title">${this.escapeHtml(title)}</div>
                <div class="universal-search-result-subtitle">${this.escapeHtml(subtitle)}</div>
            </div>
            <button class="universal-search-result-action">${actionText}</button>
        `;
        
        if (clickHandler) {
            item.addEventListener('click', clickHandler);
        }
        
        if (actionHandler) {
            const button = item.querySelector('.universal-search-result-action');
            button.addEventListener('click', actionHandler);
        }
        
        return item;
    }
    
    async addToLibrary(result) {
        try {
            const source = result.source;
            const videoId = result.video_id;
            const title = result.title;
            const artist = result.artist;
            const url = result.source === 'YouTube' ? `https://youtube.com/watch?v=${videoId}` : '';
            
            // Use existing function if available
            if (typeof addVideoToLibrary === 'function') {
                await addVideoToLibrary(source, videoId, title, artist, url);
            } else {
                // Fallback to direct API call
                const endpoint = '/api/videos/import-from-youtube';

                const payload = {
                    youtube_id: videoId,
                    url: url,
                    title: title,
                    artist: artist,
                    auto_download: true
                };

                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                if (response.ok) {
                    this.showToast('Video added to library successfully!', 'success');
                } else {
                    const error = await response.text();
                    this.showToast(`Failed to add video: ${error}`, 'error');
                }
            }
            
            this.hideResults();
            
        } catch (error) {
            console.error('Add to library error:', error);
            this.showToast('Failed to add video to library', 'error');
        }
    }
    
    showToast(message, type) {
        if (typeof showToast === 'function') {
            showToast(message, type);
        } else {
            console.log(`${type.toUpperCase()}: ${message}`);
        }
    }
    
    // UI State Management
    showLoading() {
        this.loadingElement.style.display = 'flex';
        this.showResults();
    }
    
    hideLoading() {
        this.loadingElement.style.display = 'none';
    }
    
    showResults() {
        this.searchResults.style.display = 'block';
    }
    
    hideResults() {
        this.searchResults.style.display = 'none';
    }
    
    clearResults() {
        this.hideResults();
        this.clearSections();
    }
    
    clearSections() {
        const sections = [this.videosSection, this.artistsSection, this.externalSection, this.noResultsElement, this.searchMoreSection];
        sections.forEach(section => {
            if (section) section.style.display = 'none';
        });
        this.hideLoading();
    }
    
    showNoResults() {
        this.noResultsElement.style.display = 'flex';
        this.showResults();
    }
    
    showError(message) {
        this.showToast(message, 'error');
        this.hideResults();
    }
    
    showSearchMore() {
        if (this.searchMoreSection && this.currentQuery) {
            this.searchMoreSection.style.display = 'block';
        }
    }
    
    escapeHtml(unsafe) {
        const div = document.createElement('div');
        div.textContent = unsafe;
        return div.innerHTML;
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        if (document.getElementById('universalSearchInput')) {
            window.universalSearch = new UniversalSearch();
        }
    });
} else {
    if (document.getElementById('universalSearchInput')) {
        window.universalSearch = new UniversalSearch();
    }
}