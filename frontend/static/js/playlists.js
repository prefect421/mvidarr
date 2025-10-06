/**
 * MVidarr Playlist Management JavaScript
 * Comprehensive playlist management functionality
 */

class PlaylistManager {
    constructor() {
        this.playlists = [];
        this.currentPage = 1;
        this.pageSize = 20;
        this.totalPages = 1;
        this.totalCount = 0;
        this.filters = {
            search: '',
            visibility: '',
            owner: '',
            sort: 'updated_desc'
        };
        this.selectedPlaylists = new Set();
        this.isLoading = false;
        this.isAdmin = false;
        
        this.init();
    }

    async init() {
        try {
            await this.checkUserPermissions();
            await this.loadPlaylists();
            this.initializeEventListeners();
            this.setupKeyboardShortcuts();
        } catch (error) {
            console.error('Failed to initialize playlist manager:', error);
            this.showToast('Failed to initialize playlist manager', 'error');
        }
    }

    async checkUserPermissions() {
        try {
            const response = await fetch('/api/auth/user');
            if (response.ok) {
                const userData = await response.json();
                this.isAdmin = userData.user && userData.user.role === 'admin';
                
                // Show featured checkbox for admins
                if (this.isAdmin) {
                    const featuredGroup = document.getElementById('featuredGroup');
                    if (featuredGroup) {
                        featuredGroup.style.display = 'block';
                    }
                }
            }
        } catch (error) {
            console.error('Failed to check user permissions:', error);
        }
    }

    initializeEventListeners() {
        // Search input
        const searchInput = document.getElementById('playlistSearchInput');
        if (searchInput) {
            let debounceTimer;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => {
                    this.filters.search = e.target.value.trim();
                    this.currentPage = 1;
                    this.loadPlaylists();
                }, 300);
            });
        }

        // Filter dropdowns
        ['playlistVisibilityFilter', 'playlistOwnerFilter', 'playlistSortFilter'].forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.addEventListener('change', () => this.handleFilterChange());
            }
        });

        // Select all checkbox
        const selectAllCheckbox = document.getElementById('selectAllPlaylists');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                this.handleSelectAll(e.target.checked);
            });
        }
        
        // Listen for playlist updates from other components
        document.addEventListener('playlistUpdated', (e) => {
            console.log('Playlist updated event received:', e.detail);
            // Refresh playlist counts to show updated information
            this.refreshPlaylistCounts();
        });

        // Also listen for general playlist change events
        document.addEventListener('playlistChanged', (e) => {
            console.log('Playlist changed event received:', e.detail);
            this.refreshPlaylistCounts();
        });
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + N - New playlist
            if ((e.ctrlKey || e.metaKey) && e.key === 'n' && !e.target.matches('input, textarea')) {
                e.preventDefault();
                this.showCreatePlaylistModal();
            }
            
            // Escape - Close modals
            if (e.key === 'Escape') {
                this.closeAllModals();
            }
            
            // Delete - Delete selected playlists
            if (e.key === 'Delete' && this.selectedPlaylists.size > 0 && !e.target.matches('input, textarea')) {
                e.preventDefault();
                this.bulkDeletePlaylists();
            }
        });
    }

    async loadPlaylists() {
        if (this.isLoading) return;
        
        this.isLoading = true;
        this.showLoading(true);

        try {
            const params = new URLSearchParams({
                page: this.currentPage,
                per_page: this.pageSize,
                search: this.filters.search,
                public_only: this.filters.visibility === 'public' ? 'true' : 'false',
                featured: this.filters.visibility === 'featured' ? 'true' : 'false',
                include_count: 'true', // Request fresh video counts
                include_user: 'true' // Request user details
            });

            const response = await fetch(`/api/playlists/?${params}`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();

            if (data.playlists !== undefined) {
                this.playlists = data.playlists || [];
                this.totalCount = data.pagination.total;
                this.totalPages = data.pagination.pages;

                // Debug logging to see playlist data structure
                console.log('Loaded playlists:', this.playlists.length);
                if (this.playlists.length > 0) {
                    console.log('Sample playlist data:', this.playlists[0]);
                }

                this.renderPlaylists();
                this.renderPagination();
                this.updateFilterCounts();

                // Note: Counts are already accurate from the API response
                // No need to refresh separately
            } else {
                throw new Error(data.error || 'Failed to load playlists');
            }
        } catch (error) {
            console.error('Failed to load playlists:', error);
            this.showToast(`Failed to load playlists: ${error.message}`, 'error');
            this.showEmptyState();
        } finally {
            this.isLoading = false;
            this.showLoading(false);
        }
    }

    async refreshPlaylistCounts() {
        console.log('Refreshing playlist counts...'); // Debug logging
        
        // Refresh video counts for all currently loaded playlists
        const promises = this.playlists.map(async (playlist) => {
            try {
                const response = await fetch(`/api/playlists/${playlist.id}?include_entries=true`);
                if (response.ok) {
                    const data = await response.json();
                    if (data.success && data.playlist) {
                        // Update the video count based on actual entries
                        const oldCount = playlist.video_count;
                        playlist.video_count = data.playlist.entries ? data.playlist.entries.length : 0;
                        console.log(`Playlist ${playlist.name} count updated: ${oldCount} → ${playlist.video_count}`); // Debug logging
                    }
                }
            } catch (error) {
                console.error(`Failed to refresh count for playlist ${playlist.id}:`, error);
            }
        });
        
        await Promise.all(promises);
        
        // Re-render the playlists with updated counts
        console.log('Re-rendering playlists with updated counts'); // Debug logging
        this.renderPlaylists();
    }

    renderPlaylists() {
        const grid = document.getElementById('playlistsGrid');
        const emptyState = document.getElementById('playlistsEmptyState');
        
        if (!grid) return;

        if (this.playlists.length === 0) {
            grid.style.display = 'none';
            if (emptyState) emptyState.style.display = 'block';
            return;
        }

        if (emptyState) emptyState.style.display = 'none';
        grid.style.display = 'grid';

        grid.innerHTML = this.playlists.map(playlist => this.renderPlaylistCard(playlist)).join('');
        
        // Add event listeners to cards
        this.playlists.forEach(playlist => {
            const card = document.getElementById(`playlist-${playlist.id}`);
            if (card) {
                card.addEventListener('click', (e) => {
                    if (!e.target.matches('input, button, .btn')) {
                        this.showPlaylistDetail(playlist.id);
                    }
                });

                const checkbox = card.querySelector('.playlist-checkbox');
                if (checkbox) {
                    checkbox.addEventListener('change', (e) => {
                        e.stopPropagation();
                        this.handlePlaylistSelection(playlist.id, e.target.checked);
                    });
                }
            }
        });
    }

    renderPlaylistCard(playlist) {
        const isSelected = this.selectedPlaylists.has(playlist.id);
        const videoCount = playlist.video_count || 0;
        const updatedDate = new Date(playlist.updated_at).toLocaleDateString();
        
        const badges = [];
        if (playlist.is_featured) badges.push('<span class="playlist-badge featured">Featured</span>');
        if (playlist.is_public) badges.push('<span class="playlist-badge public">Public</span>');
        else badges.push('<span class="playlist-badge private">Private</span>');
        
        // Add dynamic playlist badges
        if (playlist.playlist_type === 'DYNAMIC') {
            badges.push('<span class="playlist-badge dynamic">Dynamic</span>');
            if (playlist.auto_update) {
                badges.push('<span class="playlist-badge auto-update">Auto-Update</span>');
            }
        }

        return `
            <div class="playlist-card ${isSelected ? 'selected' : ''}" id="playlist-${playlist.id}">
                <div class="playlist-card-checkbox">
                    <input type="checkbox" class="playlist-checkbox" ${isSelected ? 'checked' : ''} 
                           aria-label="Select playlist ${playlist.name}">
                </div>
                
                ${playlist.thumbnail_url ? 
                    `<div class="playlist-card-thumbnail">
                        <img src="${this.escapeHtml(playlist.thumbnail_url)}" alt="${this.escapeHtml(playlist.name)} thumbnail" 
                             onerror="this.parentElement.innerHTML='<div class=\\'playlist-card-icon\\'><iconify-icon icon=\\'tabler:playlist\\'></iconify-icon></div>'">
                    </div>` : 
                    `<div class="playlist-card-icon">
                        <iconify-icon icon="tabler:playlist"></iconify-icon>
                    </div>`
                }
                
                <h3 class="playlist-card-title">${this.escapeHtml(playlist.name)}</h3>
                
                ${playlist.description ? `<p class="playlist-card-description">${this.escapeHtml(playlist.description)}</p>` : ''}
                
                <div class="playlist-card-meta">
                    <div class="playlist-card-meta-item">
                        <iconify-icon icon="tabler:music"></iconify-icon>
                        <span>${videoCount} video${videoCount !== 1 ? 's' : ''}</span>
                    </div>
                    <div class="playlist-card-meta-item">
                        <iconify-icon icon="tabler:user"></iconify-icon>
                        <span>${this.escapeHtml(playlist.user?.username || playlist.owner || 'System')}</span>
                    </div>
                    <div class="playlist-card-meta-item">
                        <iconify-icon icon="tabler:calendar"></iconify-icon>
                        <span>${updatedDate}</span>
                    </div>
                </div>
                
                <div class="playlist-card-badges">
                    ${badges.join('')}
                </div>
                
                <div class="playlist-card-actions">
                    <button class="btn btn-primary btn-sm" onclick="playlistManager.playPlaylist(${playlist.id})" 
                            title="Play playlist">
                        <iconify-icon icon="tabler:play"></iconify-icon>
                        Play
                    </button>
                    ${playlist.can_modify ? `
                        <button class="btn btn-secondary btn-sm" onclick="playlistManager.editPlaylist(${playlist.id})" 
                                title="Edit playlist">
                            <iconify-icon icon="tabler:edit"></iconify-icon>
                            Edit
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }

    renderPagination() {
        const paginationContainer = document.getElementById('playlistsPagination');
        if (!paginationContainer || this.totalPages <= 1) {
            if (paginationContainer) paginationContainer.style.display = 'none';
            return;
        }

        paginationContainer.style.display = 'block';
        
        const pagination = [];
        
        // Previous button
        pagination.push(`
            <button class="btn btn-secondary btn-sm ${this.currentPage <= 1 ? 'disabled' : ''}" 
                    onclick="playlistManager.goToPage(${this.currentPage - 1})" 
                    ${this.currentPage <= 1 ? 'disabled' : ''}>
                <iconify-icon icon="tabler:chevron-left"></iconify-icon>
                Previous
            </button>
        `);
        
        // Page numbers
        const startPage = Math.max(1, this.currentPage - 2);
        const endPage = Math.min(this.totalPages, this.currentPage + 2);
        
        if (startPage > 1) {
            pagination.push(`<button class="btn btn-ghost btn-sm" onclick="playlistManager.goToPage(1)">1</button>`);
            if (startPage > 2) pagination.push(`<span class="pagination-ellipsis">...</span>`);
        }
        
        for (let i = startPage; i <= endPage; i++) {
            pagination.push(`
                <button class="btn ${i === this.currentPage ? 'btn-primary' : 'btn-ghost'} btn-sm" 
                        onclick="playlistManager.goToPage(${i})">${i}</button>
            `);
        }
        
        if (endPage < this.totalPages) {
            if (endPage < this.totalPages - 1) pagination.push(`<span class="pagination-ellipsis">...</span>`);
            pagination.push(`<button class="btn btn-ghost btn-sm" onclick="playlistManager.goToPage(${this.totalPages})">${this.totalPages}</button>`);
        }
        
        // Next button
        pagination.push(`
            <button class="btn btn-secondary btn-sm ${this.currentPage >= this.totalPages ? 'disabled' : ''}" 
                    onclick="playlistManager.goToPage(${this.currentPage + 1})" 
                    ${this.currentPage >= this.totalPages ? 'disabled' : ''}>
                Next
                <iconify-icon icon="tabler:chevron-right"></iconify-icon>
            </button>
        `);

        paginationContainer.innerHTML = `
            <div class="pagination">
                ${pagination.join('')}
            </div>
            <div class="pagination-info">
                Showing ${((this.currentPage - 1) * this.pageSize) + 1}-${Math.min(this.currentPage * this.pageSize, this.totalCount)} 
                of ${this.totalCount} playlists
            </div>
        `;
    }

    async goToPage(page) {
        if (page < 1 || page > this.totalPages || page === this.currentPage) return;
        this.currentPage = page;
        await this.loadPlaylists();
    }

    handleFilterChange() {
        this.filters.visibility = document.getElementById('playlistVisibilityFilter')?.value || '';
        this.filters.owner = document.getElementById('playlistOwnerFilter')?.value || '';
        this.filters.sort = document.getElementById('playlistSortFilter')?.value || 'updated_desc';
        
        this.currentPage = 1;
        this.loadPlaylists();
    }

    clearPlaylistFilters() {
        this.filters = {
            search: '',
            visibility: '',
            owner: '',
            sort: 'updated_desc'
        };
        
        // Reset UI elements
        const searchInput = document.getElementById('playlistSearchInput');
        if (searchInput) searchInput.value = '';
        
        ['playlistVisibilityFilter', 'playlistOwnerFilter'].forEach(id => {
            const element = document.getElementById(id);
            if (element) element.value = '';
        });
        
        const sortFilter = document.getElementById('playlistSortFilter');
        if (sortFilter) sortFilter.value = 'updated_desc';
        
        this.currentPage = 1;
        this.loadPlaylists();
    }

    updateFilterCounts() {
        const filterCount = document.getElementById('playlistFilterCount');
        if (filterCount) {
            const activeFilters = Object.values(this.filters).filter(f => f && f !== 'updated_desc').length;
            filterCount.textContent = activeFilters > 0 ? `(${activeFilters})` : '';
        }
    }

    handlePlaylistSelection(playlistId, isSelected) {
        if (isSelected) {
            this.selectedPlaylists.add(playlistId);
        } else {
            this.selectedPlaylists.delete(playlistId);
        }
        
        this.updateSelectionUI();
    }

    handleSelectAll(selectAll) {
        this.selectedPlaylists.clear();
        
        if (selectAll) {
            this.playlists.forEach(playlist => {
                this.selectedPlaylists.add(playlist.id);
            });
        }
        
        // Update checkboxes
        document.querySelectorAll('.playlist-checkbox').forEach(checkbox => {
            checkbox.checked = selectAll;
        });
        
        // Update card styles
        document.querySelectorAll('.playlist-card').forEach(card => {
            card.classList.toggle('selected', selectAll);
        });
        
        this.updateSelectionUI();
    }

    updateSelectionUI() {
        const selectedCount = this.selectedPlaylists.size;
        
        // Update count displays
        const countElements = ['selectedCount', 'bulkSelectedCount'];
        countElements.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = selectedCount === 1 ? '1 playlist selected' : `${selectedCount} playlists selected`;
            }
        });
        
        // Update select all checkbox
        const selectAllCheckbox = document.getElementById('selectAllPlaylists');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = selectedCount === this.playlists.length && this.playlists.length > 0;
            selectAllCheckbox.indeterminate = selectedCount > 0 && selectedCount < this.playlists.length;
        }
        
        // Show/hide bulk actions panel
        const bulkActionsPanel = document.getElementById('bulkActionsPanel');
        if (bulkActionsPanel) {
            bulkActionsPanel.style.display = selectedCount > 0 ? 'block' : 'none';
        }
        
        // Update card selection styles
        this.playlists.forEach(playlist => {
            const card = document.getElementById(`playlist-${playlist.id}`);
            if (card) {
                card.classList.toggle('selected', this.selectedPlaylists.has(playlist.id));
            }
        });
    }

    // Modal Management
    showCreatePlaylistModal() {
        this.resetPlaylistForm();
        document.getElementById('playlistModalTitle').textContent = 'Create Playlist';
        document.getElementById('savePlaylistBtn').innerHTML = '<iconify-icon icon="tabler:check"></iconify-icon> Create Playlist';
        this.showModal('playlistModal');
    }

    async editPlaylist(playlistId) {
        try {
            const response = await fetch(`/api/playlists/${playlistId}`);
            if (!response.ok) throw new Error('Failed to load playlist');
            
            const data = await response.json();
            if (!data.success) throw new Error(data.error);
            
            const playlist = data.playlist;
            
            // Populate form
            document.getElementById('playlistId').value = playlist.id;
            document.getElementById('playlistName').value = playlist.name;
            document.getElementById('playlistDescription').value = playlist.description || '';
            document.getElementById('playlistThumbnailUrl').value = playlist.thumbnail_url || '';
            document.getElementById('playlistIsPublic').checked = playlist.is_public;
            document.getElementById('playlistIsFeatured').checked = playlist.is_featured;
            
            // Handle dynamic playlist fields
            document.getElementById('playlistType').value = playlist.playlist_type || 'STATIC';
            this.handlePlaylistTypeChange();
            
            if (playlist.playlist_type === 'DYNAMIC' && playlist.filter_criteria) {
                this.populateDynamicFilters(playlist.filter_criteria);
                document.getElementById('playlistAutoUpdate').checked = playlist.auto_update || true;
            }
            
            document.getElementById('playlistModalTitle').textContent = 'Edit Playlist';
            document.getElementById('savePlaylistBtn').innerHTML = '<iconify-icon icon="tabler:check"></iconify-icon> Save Changes';
            this.showModal('playlistModal');
            
        } catch (error) {
            this.showToast(`Failed to load playlist: ${error.message}`, 'error');
        }
    }

    async savePlaylist(event) {
        event.preventDefault();
        
        const form = document.getElementById('playlistForm');
        const formData = new FormData(form);
        
        const playlistType = document.getElementById('playlistType').value;
        
        const playlistData = {
            name: document.getElementById('playlistName').value.trim(),
            description: document.getElementById('playlistDescription').value.trim(),
            thumbnail_url: document.getElementById('playlistThumbnailUrl').value.trim(),
            is_public: document.getElementById('playlistIsPublic').checked,
            is_featured: document.getElementById('playlistIsFeatured').checked,
            playlist_type: playlistType,
            auto_update: playlistType === 'DYNAMIC' ? document.getElementById('playlistAutoUpdate').checked : true
        };
        
        // Add dynamic playlist filter criteria
        if (playlistType === 'DYNAMIC') {
            const filterCriteria = this.collectFilterCriteria();
            if (Object.keys(filterCriteria).length === 0) {
                this.showToast('Please configure at least one filter for your dynamic playlist', 'error');
                return;
            }
            playlistData.filter_criteria = filterCriteria;
        }
        
        if (!playlistData.name) {
            this.showToast('Playlist name is required', 'error');
            return;
        }
        
        // Validate thumbnail URL if provided
        if (playlistData.thumbnail_url) {
            // Allow local paths (starting with /) or valid URLs
            if (!playlistData.thumbnail_url.startsWith('/')) {
                try {
                    new URL(playlistData.thumbnail_url);
                } catch (error) {
                    this.showToast('Please enter a valid thumbnail URL or local path', 'error');
                    return;
                }
            }
        }
        
        const playlistId = document.getElementById('playlistId').value;
        const isEdit = playlistId && playlistId !== '';
        
        try {
            // Use dynamic playlist endpoint if creating a dynamic playlist
            let url, method;
            if (playlistType === 'DYNAMIC' && !isEdit) {
                url = '/api/playlists/dynamic';
                method = 'POST';
            } else {
                url = isEdit ? `/api/playlists/${playlistId}` : '/api/playlists/';
                method = isEdit ? 'PUT' : 'POST';
            }
            
            const response = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(playlistData)
            });

            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || errorData.detail || `HTTP ${response.status}`);
            }

            const data = await response.json();

            // Dynamic playlist endpoint returns playlist object directly, not {success: true}
            // Regular endpoint returns {success: true, playlist: {...}}
            if (playlistType !== 'DYNAMIC' && !isEdit && !data.success) {
                throw new Error(data.error || 'Failed to create playlist');
            }

            this.showToast(isEdit ? 'Playlist updated successfully' : 'Playlist created successfully', 'success');
            this.closePlaylistModal();
            await this.loadPlaylists();
            
        } catch (error) {
            this.showToast(`Failed to ${isEdit ? 'update' : 'create'} playlist: ${error.message}`, 'error');
        }
    }

    // Dynamic Playlist Methods
    handlePlaylistTypeChange() {
        const playlistType = document.getElementById('playlistType').value;
        const dynamicConfig = document.getElementById('dynamicPlaylistConfig');
        
        if (dynamicConfig) {
            dynamicConfig.style.display = playlistType === 'DYNAMIC' ? 'block' : 'none';
        }
        
        // Clear preview when switching types
        const previewResults = document.getElementById('previewResults');
        if (previewResults) {
            previewResults.style.display = 'none';
        }
    }

    collectFilterCriteria() {
        const criteria = {};
        
        // Collect filter values
        const genres = document.getElementById('filterGenres').value.trim();
        if (genres) {
            criteria.genres = genres.split(',').map(g => g.trim()).filter(g => g);
        }
        
        const artists = document.getElementById('filterArtists').value.trim();
        if (artists) {
            criteria.artists = artists.split(',').map(a => a.trim()).filter(a => a);
        }
        
        const yearMin = document.getElementById('filterYearMin').value;
        const yearMax = document.getElementById('filterYearMax').value;
        if (yearMin || yearMax) {
            criteria.year_range = {};
            if (yearMin) criteria.year_range.min = parseInt(yearMin);
            if (yearMax) criteria.year_range.max = parseInt(yearMax);
        }
        
        const durationMin = document.getElementById('filterDurationMin').value;
        const durationMax = document.getElementById('filterDurationMax').value;
        if (durationMin || durationMax) {
            criteria.duration_range = {};
            if (durationMin) criteria.duration_range.min = parseInt(durationMin) * 60; // Convert to seconds
            if (durationMax) criteria.duration_range.max = parseInt(durationMax) * 60; // Convert to seconds
        }
        
        const quality = Array.from(document.getElementById('filterQuality').selectedOptions)
            .map(option => option.value);
        if (quality.length > 0) {
            criteria.quality = quality;
        }
        
        const status = Array.from(document.getElementById('filterStatus').selectedOptions)
            .map(option => option.value);
        if (status.length > 0) {
            criteria.status = status;
        }
        
        const keywords = document.getElementById('filterKeywords').value.trim();
        if (keywords) {
            criteria.keywords = keywords.split(',').map(k => k.trim()).filter(k => k);
        }
        
        return criteria;
    }

    populateDynamicFilters(filterCriteria) {
        if (!filterCriteria) return;
        
        // Populate genres
        if (filterCriteria.genres) {
            document.getElementById('filterGenres').value = filterCriteria.genres.join(', ');
        }
        
        // Populate artists
        if (filterCriteria.artists) {
            document.getElementById('filterArtists').value = filterCriteria.artists.join(', ');
        }
        
        // Populate year range
        if (filterCriteria.year_range) {
            if (filterCriteria.year_range.min) {
                document.getElementById('filterYearMin').value = filterCriteria.year_range.min;
            }
            if (filterCriteria.year_range.max) {
                document.getElementById('filterYearMax').value = filterCriteria.year_range.max;
            }
        }
        
        // Populate duration range (convert from seconds to minutes)
        if (filterCriteria.duration_range) {
            if (filterCriteria.duration_range.min) {
                document.getElementById('filterDurationMin').value = Math.floor(filterCriteria.duration_range.min / 60);
            }
            if (filterCriteria.duration_range.max) {
                document.getElementById('filterDurationMax').value = Math.floor(filterCriteria.duration_range.max / 60);
            }
        }
        
        // Populate quality
        if (filterCriteria.quality) {
            const qualitySelect = document.getElementById('filterQuality');
            Array.from(qualitySelect.options).forEach(option => {
                option.selected = filterCriteria.quality.includes(option.value);
            });
        }
        
        // Populate status
        if (filterCriteria.status) {
            const statusSelect = document.getElementById('filterStatus');
            Array.from(statusSelect.options).forEach(option => {
                option.selected = filterCriteria.status.includes(option.value);
            });
        }
        
        // Populate keywords
        if (filterCriteria.keywords) {
            document.getElementById('filterKeywords').value = filterCriteria.keywords.join(', ');
        }
    }

    async applyDynamicTemplate() {
        const templateId = document.getElementById('dynamicTemplate').value;
        if (!templateId) return;

        try {
            // Client-side templates (no API call needed)
            const templates = {
                'recent_releases': {
                    name: 'Recent Releases',
                    description: 'Videos released in the last 2 years',
                    filter_criteria: {
                        year_range: { min: new Date().getFullYear() - 2 }
                    }
                },
                'high_quality': {
                    name: 'High Quality Videos',
                    description: '1080p and higher quality videos',
                    filter_criteria: {
                        quality: ['1080p', '1440p', '2160p', '4320p']
                    }
                },
                'completed': {
                    name: 'Completed Downloads',
                    description: 'All successfully downloaded videos',
                    filter_criteria: {
                        status: ['DOWNLOADED', 'READY']
                    }
                },
                'pending': {
                    name: 'Pending Downloads',
                    description: 'Videos queued or downloading',
                    filter_criteria: {
                        status: ['QUEUED', 'DOWNLOADING', 'PENDING']
                    }
                }
            };

            const template = templates[templateId];
            if (!template) throw new Error('Template not found');

            // Apply template to form
            this.populateDynamicFilters(template.filter_criteria);

            // Update playlist name if empty
            const nameInput = document.getElementById('playlistName');
            if (!nameInput.value.trim()) {
                nameInput.value = template.name;
            }

            // Update description if empty
            const descInput = document.getElementById('playlistDescription');
            if (!descInput.value.trim()) {
                descInput.value = template.description;
            }

            this.showToast(`Applied template: ${template.name}`, 'success');

        } catch (error) {
            this.showToast(`Failed to apply template: ${error.message}`, 'error');
        }
    }

    async previewDynamicPlaylist() {
        const filterCriteria = this.collectFilterCriteria();
        
        if (Object.keys(filterCriteria).length === 0) {
            this.showToast('Please configure at least one filter to preview results', 'error');
            return;
        }
        
        try {
            const response = await fetch('/api/playlists/dynamic/preview', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    filter_criteria: filterCriteria,
                    limit: 50
                })
            });
            
            if (!response.ok) throw new Error('Failed to preview playlist');
            
            const data = await response.json();
            if (!data.success) throw new Error(data.error);
            
            this.displayPreviewResults(data.preview);
            
        } catch (error) {
            this.showToast(`Failed to preview playlist: ${error.message}`, 'error');
        }
    }

    displayPreviewResults(previewData) {
        const previewResults = document.getElementById('previewResults');
        const totalMatches = previewData.total_matches || 0;
        const videos = previewData.preview_videos || [];
        
        let html = `
            <div class="preview-stats">
                <div class="preview-stats-item">
                    <iconify-icon icon="tabler:music"></iconify-icon>
                    <span><span class="preview-stats-number">${totalMatches}</span> matching videos</span>
                </div>
                <div class="preview-stats-item">
                    <iconify-icon icon="tabler:eye"></iconify-icon>
                    <span>Showing first <span class="preview-stats-number">${Math.min(videos.length, 50)}</span></span>
                </div>
            </div>
        `;
        
        if (videos.length > 0) {
            html += '<div class="preview-video-list">';
            
            videos.forEach(video => {
                const thumbnailUrl = video.thumbnail_url || '/static/default-thumbnail.jpg';
                html += `
                    <div class="preview-video-item">
                        <img src="${this.escapeHtml(thumbnailUrl)}" alt="Thumbnail" loading="lazy">
                        <div class="preview-video-info">
                            <div class="preview-video-title">${this.escapeHtml(video.title)}</div>
                            <div class="preview-video-meta">
                                ${video.artist ? this.escapeHtml(video.artist) + ' • ' : ''}
                                ${video.year || 'Unknown Year'} • 
                                ${video.quality || 'Unknown Quality'} • 
                                ${video.duration ? this.formatDuration(video.duration) : 'Unknown Duration'}
                            </div>
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
        } else {
            html += '<p>No videos match the current filter criteria. Try adjusting your filters.</p>';
        }
        
        previewResults.innerHTML = html;
        previewResults.style.display = 'block';
    }

    formatDuration(seconds) {
        if (!seconds) return 'Unknown';
        const minutes = Math.floor(seconds / 60);
        const secs = seconds % 60;
        return `${minutes}:${secs.toString().padStart(2, '0')}`;
    }

    async deletePlaylist(playlistId) {
        if (!confirm('Are you sure you want to delete this playlist? This action cannot be undone.')) {
            return;
        }
        
        try {
            const response = await fetch(`/api/playlists/${playlistId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            if (!data.success) throw new Error(data.error);
            
            this.showToast('Playlist deleted successfully', 'success');
            await this.loadPlaylists();
            
        } catch (error) {
            this.showToast(`Failed to delete playlist: ${error.message}`, 'error');
        }
    }

    async bulkDeletePlaylists() {
        if (this.selectedPlaylists.size === 0) return;
        
        const count = this.selectedPlaylists.size;
        if (!confirm(`Are you sure you want to delete ${count} playlist${count !== 1 ? 's' : ''}? This action cannot be undone.`)) {
            return;
        }
        
        try {
            const response = await fetch('/api/playlists/bulk/delete', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    playlist_ids: Array.from(this.selectedPlaylists)
                })
            });
            
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            
            const data = await response.json();
            if (!data.success) throw new Error(data.error);
            
            this.showToast(`${count} playlist${count !== 1 ? 's' : ''} deleted successfully`, 'success');
            this.selectedPlaylists.clear();
            await this.loadPlaylists();
            
        } catch (error) {
            this.showToast(`Failed to delete playlists: ${error.message}`, 'error');
        }
    }

    async playPlaylist(playlistId) {
        // Navigate to MvTV with playlist
        window.location.href = `/mvtv?playlist=${playlistId}`;
    }

    async sharePlaylist(playlistId) {
        try {
            const playlist = this.playlists.find(p => p.id === playlistId);
            if (!playlist) throw new Error('Playlist not found');
            
            const shareUrl = `${window.location.origin}/playlist/${playlistId}`;
            
            if (navigator.share) {
                await navigator.share({
                    title: `${playlist.name} - MVidarr Playlist`,
                    text: playlist.description || `Check out this playlist: ${playlist.name}`,
                    url: shareUrl
                });
            } else {
                await navigator.clipboard.writeText(shareUrl);
                this.showToast('Playlist link copied to clipboard', 'success');
            }
        } catch (error) {
            this.showToast(`Failed to share playlist: ${error.message}`, 'error');
        }
    }

    async showPlaylistDetail(playlistId) {
        try {
            const response = await fetch(`/api/playlists/${playlistId}?include_entries=true`);
            if (!response.ok) throw new Error('Failed to load playlist details');
            
            const data = await response.json();
            if (!data.success) throw new Error(data.error);
            
            const playlist = data.playlist;
            
            // Navigate to playlist detail page or show in modal
            window.location.href = `/playlist/${playlistId}`;
            
        } catch (error) {
            this.showToast(`Failed to load playlist details: ${error.message}`, 'error');
        }
    }

    // Import/Export functionality
    showImportPlaylistModal() {
        this.showModal('importPlaylistModal');
    }

    closeImportPlaylistModal() {
        this.closeModal('importPlaylistModal');
    }

    switchImportTab(tabName, button) {
        // Hide all tab contents
        document.querySelectorAll('.import-tab-content').forEach(tab => {
            tab.classList.remove('active');
        });
        
        // Remove active class from all buttons
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.remove('active');
        });
        
        // Show selected tab content
        const tabContent = document.getElementById(`${tabName}ImportTab`);
        if (tabContent) {
            tabContent.classList.add('active');
        }
        
        // Activate selected button
        if (button) {
            button.classList.add('active');
        }
    }

    async importPlaylistFromUrl() {
        const url = document.getElementById('importUrl').value.trim();
        if (!url) {
            this.showToast('Please enter a URL', 'error');
            return;
        }

        try {
            // Basic URL validation
            new URL(url);
            
            this.showToast('Import functionality coming soon! Currently supported: manual playlist creation.', 'info');
            
            // TODO: Implement actual import from URL
            // This would require backend support for parsing different playlist formats
            
        } catch (error) {
            this.showToast('Please enter a valid URL', 'error');
        }
    }

    async importPlaylistFromFile() {
        const fileInput = document.getElementById('importFile');
        const file = fileInput.files[0];
        
        if (!file) {
            this.showToast('Please select a file', 'error');
            return;
        }

        try {
            const text = await file.text();
            
            if (file.name.endsWith('.json')) {
                await this.importFromJSON(text);
            } else if (file.name.endsWith('.m3u') || file.name.endsWith('.m3u8')) {
                await this.importFromM3U(text);
            } else {
                throw new Error('Unsupported file format. Please use JSON, M3U, or M3U8 files.');
            }
            
        } catch (error) {
            this.showToast(`Failed to import playlist: ${error.message}`, 'error');
        }
    }

    async importFromJSON(jsonText) {
        try {
            const data = JSON.parse(jsonText);
            
            // Validate JSON structure
            if (!data.name) {
                throw new Error('Invalid JSON: missing playlist name');
            }
            
            if (!Array.isArray(data.videos)) {
                throw new Error('Invalid JSON: missing or invalid videos array');
            }

            // Create playlist
            const playlistData = {
                name: data.name,
                description: data.description || '',
                is_public: false
            };

            const response = await fetch('/api/playlists/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(playlistData)
            });

            if (!response.ok) throw new Error('Failed to create playlist');

            const result = await response.json();
            if (!result.success) throw new Error(result.error);

            this.showToast(`Imported playlist "${data.name}" with ${data.videos.length} videos`, 'success');
            this.closeImportPlaylistModal();
            await this.loadPlaylists();

        } catch (error) {
            throw new Error(`JSON import failed: ${error.message}`);
        }
    }

    async importFromM3U(m3uText) {
        try {
            const lines = m3uText.split('\n').map(line => line.trim()).filter(line => line);
            const videos = [];
            let currentTitle = '';

            for (const line of lines) {
                if (line.startsWith('#EXTINF:')) {
                    // Extract title from EXTINF line
                    const titleMatch = line.match(/,(.*)$/);
                    currentTitle = titleMatch ? titleMatch[1] : 'Unknown Title';
                } else if (line.startsWith('http') && !line.startsWith('#')) {
                    // This is a URL
                    videos.push({
                        title: currentTitle || 'Unknown Title',
                        url: line
                    });
                    currentTitle = '';
                }
            }

            if (videos.length === 0) {
                throw new Error('No valid URLs found in M3U file');
            }

            // Create playlist
            const playlistName = `Imported Playlist ${new Date().toLocaleDateString()}`;
            const playlistData = {
                name: playlistName,
                description: `Imported from M3U file with ${videos.length} videos`,
                is_public: false
            };

            const response = await fetch('/api/playlists/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(playlistData)
            });

            if (!response.ok) throw new Error('Failed to create playlist');

            const result = await response.json();
            if (!result.success) throw new Error(result.error);

            this.showToast(`Imported M3U playlist with ${videos.length} videos`, 'success');
            this.closeImportPlaylistModal();
            await this.loadPlaylists();

        } catch (error) {
            throw new Error(`M3U import failed: ${error.message}`);
        }
    }

    async importYouTubePlaylist() {
        const url = document.getElementById('youtubePlaylistUrl').value.trim();
        const makePrivate = document.getElementById('youtubeImportPrivate').checked;
        
        if (!url) {
            this.showToast('Please enter a YouTube playlist URL', 'error');
            return;
        }

        try {
            // Validate YouTube playlist URL
            const urlObj = new URL(url);
            if (!urlObj.hostname.includes('youtube.com') || !urlObj.searchParams.get('list')) {
                throw new Error('Please enter a valid YouTube playlist URL');
            }

            this.showToast('YouTube import functionality coming soon! Use the existing YouTube Playlists page for now.', 'info');
            
            // TODO: Implement actual YouTube playlist import
            // This would integrate with the existing YouTube API functionality
            
        } catch (error) {
            this.showToast(`Invalid YouTube URL: ${error.message}`, 'error');
        }
    }

    async bulkExportPlaylists() {
        if (this.selectedPlaylists.size === 0) return;

        try {
            const playlistsToExport = [];
            
            for (const playlistId of this.selectedPlaylists) {
                const response = await fetch(`/api/playlists/${playlistId}?include_entries=true`);
                if (response.ok) {
                    const data = await response.json();
                    if (data.success) {
                        const playlist = data.playlist;
                        playlistsToExport.push({
                            name: playlist.name,
                            description: playlist.description,
                            is_public: playlist.is_public,
                            videos: playlist.entries.map(entry => ({
                                title: entry.video.title,
                                artist: entry.video.artist?.name,
                                youtube_id: entry.video.youtube_id,
                                position: entry.position
                            }))
                        });
                    }
                }
            }

            if (playlistsToExport.length === 0) {
                throw new Error('No playlists could be exported');
            }

            const exportData = {
                export_date: new Date().toISOString(),
                playlists: playlistsToExport
            };

            const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = `mvidarr_playlists_${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            this.showToast(`Exported ${playlistsToExport.length} playlist${playlistsToExport.length !== 1 ? 's' : ''}`, 'success');

        } catch (error) {
            this.showToast(`Failed to export playlists: ${error.message}`, 'error');
        }
    }

    async bulkToggleVisibility() {
        if (this.selectedPlaylists.size === 0) return;

        try {
            let successCount = 0;
            
            for (const playlistId of this.selectedPlaylists) {
                const playlist = this.playlists.find(p => p.id === playlistId);
                if (!playlist || !playlist.can_modify) continue;

                const response = await fetch(`/api/playlists/${playlistId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        name: playlist.name,
                        description: playlist.description,
                        is_public: !playlist.is_public,
                        is_featured: playlist.is_featured
                    })
                });

                if (response.ok) {
                    const data = await response.json();
                    if (data.success) successCount++;
                }
            }

            if (successCount > 0) {
                this.showToast(`Updated visibility for ${successCount} playlist${successCount !== 1 ? 's' : ''}`, 'success');
                await this.loadPlaylists();
            } else {
                throw new Error('No playlists could be updated');
            }

        } catch (error) {
            this.showToast(`Failed to toggle visibility: ${error.message}`, 'error');
        }
    }

    // UI Helper Methods
    showModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'block';
            document.body.style.overflow = 'hidden';
        }
    }

    closeModal(modalId) {
        const modal = document.getElementById(modalId);
        if (modal) {
            modal.style.display = 'none';
            document.body.style.overflow = '';
        }
    }

    closeAllModals() {
        ['playlistModal', 'importPlaylistModal', 'playlistDetailModal'].forEach(modalId => {
            this.closeModal(modalId);
        });
    }

    closePlaylistModal() {
        this.closeModal('playlistModal');
        this.resetPlaylistForm();
    }

    resetPlaylistForm() {
        const form = document.getElementById('playlistForm');
        if (form) form.reset();
        document.getElementById('playlistId').value = '';
        document.getElementById('playlistThumbnailUrl').value = '';
        
        // Reset playlist type to static
        document.getElementById('playlistType').value = 'STATIC';
        this.handlePlaylistTypeChange();
        
        // Reset dynamic playlist fields
        document.getElementById('dynamicTemplate').value = '';
        document.getElementById('filterGenres').value = '';
        document.getElementById('filterArtists').value = '';
        document.getElementById('filterYearMin').value = '';
        document.getElementById('filterYearMax').value = '';
        document.getElementById('filterDurationMin').value = '';
        document.getElementById('filterDurationMax').value = '';
        document.getElementById('filterKeywords').value = '';
        document.getElementById('playlistAutoUpdate').checked = true;
        
        // Reset multi-select fields
        const qualitySelect = document.getElementById('filterQuality');
        const statusSelect = document.getElementById('filterStatus');
        
        Array.from(qualitySelect.options).forEach(option => option.selected = false);
        Array.from(statusSelect.options).forEach(option => {
            option.selected = option.value === 'DOWNLOADED'; // Default to Downloaded
        });
        
        // Hide preview
        const previewResults = document.getElementById('previewResults');
        if (previewResults) previewResults.style.display = 'none';
        
        // Reset file upload fields
        const fileInput = document.getElementById('playlistThumbnailFile');
        const fileNameInput = document.getElementById('playlistThumbnailFileName');
        const uploadBtn = document.getElementById('uploadThumbnailBtn');
        
        if (fileInput) fileInput.value = '';
        if (fileNameInput) fileNameInput.value = '';
        if (uploadBtn) uploadBtn.disabled = true;
    }

    showLoading(show) {
        const loading = document.getElementById('playlistsLoading');
        if (loading) {
            loading.style.display = show ? 'block' : 'none';
        }
    }

    showEmptyState() {
        const grid = document.getElementById('playlistsGrid');
        const emptyState = document.getElementById('playlistsEmptyState');
        
        if (grid) grid.style.display = 'none';
        if (emptyState) emptyState.style.display = 'block';
    }

    showToast(message, type = 'info') {
        if (typeof window.showToast === 'function') {
            window.showToast(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
            alert(message);
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Global functions for HTML onclick handlers
let playlistManager;

function showCreatePlaylistModal() {
    playlistManager.showCreatePlaylistModal();
}

function closePlaylistModal() {
    playlistManager.closePlaylistModal();
}

function savePlaylist(event) {
    return playlistManager.savePlaylist(event);
}

function toggleSearchPanel() {
    const panel = document.getElementById('playlistSearchPanel');
    const button = document.querySelector('[aria-controls="playlistSearchPanel"]');
    
    if (panel) {
        const isVisible = panel.style.display !== 'none';
        panel.style.display = isVisible ? 'none' : 'block';
        
        if (button) {
            button.setAttribute('aria-expanded', isVisible ? 'false' : 'true');
        }
    }
}

function togglePlaylistAdvancedFilters() {
    const filters = document.getElementById('playlistAdvancedFilters');
    const button = document.getElementById('playlistFiltersToggle');
    
    if (filters) {
        const isVisible = filters.style.display !== 'none';
        filters.style.display = isVisible ? 'none' : 'block';
        
        if (button) {
            button.setAttribute('aria-expanded', isVisible ? 'false' : 'true');
        }
    }
}

function applyPlaylistFilters() {
    playlistManager.handleFilterChange();
}

function clearPlaylistFilters() {
    playlistManager.clearPlaylistFilters();
}

function toggleSelectAll() {
    const checkbox = document.getElementById('selectAllPlaylists');
    if (checkbox) {
        playlistManager.handleSelectAll(checkbox.checked);
    }
}

function toggleBulkActionsPanel() {
    const panel = document.getElementById('bulkActionsPanel');
    const button = document.getElementById('bulkActionsToggle');
    
    if (panel) {
        const isVisible = panel.style.display !== 'none';
        panel.style.display = isVisible ? 'none' : 'block';
        
        if (button) {
            button.setAttribute('aria-expanded', isVisible ? 'false' : 'true');
        }
    }
}

function refreshPlaylists() {
    if (playlistManager) {
        playlistManager.loadPlaylists().then(() => {
            // Also refresh the counts to ensure they're accurate
            playlistManager.refreshPlaylistCounts();
        });
    }
}

// Manual function to test count refresh
function testRefreshCounts() {
    if (playlistManager) {
        console.log('Manual count refresh triggered');
        playlistManager.refreshPlaylistCounts();
    }
}

function bulkDeletePlaylists() {
    playlistManager.bulkDeletePlaylists();
}

function handlePlaylistSearchInput(event) {
    if (event.key === 'Enter') {
        playlistManager.filters.search = event.target.value.trim();
        playlistManager.currentPage = 1;
        playlistManager.loadPlaylists();
    }
}

function showImportPlaylistModal() {
    playlistManager.showImportPlaylistModal();
}

function closeImportPlaylistModal() {
    playlistManager.closeImportPlaylistModal();
}

function switchImportTab(tabName, button) {
    playlistManager.switchImportTab(tabName, button);
}

function importPlaylistFromUrl() {
    playlistManager.importPlaylistFromUrl();
}

function importPlaylistFromFile() {
    playlistManager.importPlaylistFromFile();
}

function importYouTubePlaylist() {
    playlistManager.importYouTubePlaylist();
}

function bulkExportPlaylists() {
    playlistManager.bulkExportPlaylists();
}

function bulkToggleVisibility() {
    playlistManager.bulkToggleVisibility();
}

async function importPlaylistThumbnail() {
    const playlistId = document.getElementById('playlistId').value;
    const thumbnailUrl = document.getElementById('playlistThumbnailUrl').value.trim();
    const importBtn = document.getElementById('importThumbnailBtn');
    
    if (!thumbnailUrl) {
        playlistManager.showToast('Please enter a thumbnail URL first', 'error');
        return;
    }
    
    // If it's already a local thumbnail path, no need to import
    if (thumbnailUrl.startsWith('/thumbnails/')) {
        playlistManager.showToast('This is already a local thumbnail path', 'info');
        return;
    }
    
    // Validate that it's a proper URL
    try {
        new URL(thumbnailUrl);
    } catch (error) {
        playlistManager.showToast('Please enter a valid URL (e.g., https://example.com/image.jpg)', 'error');
        return;
    }
    
    if (!playlistId) {
        playlistManager.showToast('Please save the playlist first before importing thumbnails', 'error');
        return;
    }
    
    try {
        // Show loading state
        const originalContent = importBtn.innerHTML;
        importBtn.innerHTML = '<iconify-icon icon="tabler:loader-2" class="spin"></iconify-icon> Importing...';
        importBtn.disabled = true;
        
        const response = await fetch(`/api/playlists/${playlistId}/thumbnail/upload`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                url: thumbnailUrl
            })
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error);
        }
        
        // Update the thumbnail URL field with the imported path
        if (data.thumbnail_path) {
            document.getElementById('playlistThumbnailUrl').value = data.thumbnail_path;
        }
        
        playlistManager.showToast('Thumbnail imported successfully!', 'success');
        
    } catch (error) {
        console.error('Failed to import thumbnail:', error);
        playlistManager.showToast(`Failed to import thumbnail: ${error.message}`, 'error');
    } finally {
        // Restore button state
        const originalContent = '<iconify-icon icon="tabler:download" aria-hidden="true"></iconify-icon> Import';
        importBtn.innerHTML = originalContent;
        importBtn.disabled = false;
    }
}

function handleThumbnailFileSelect() {
    const fileInput = document.getElementById('playlistThumbnailFile');
    const fileNameInput = document.getElementById('playlistThumbnailFileName');
    const uploadBtn = document.getElementById('uploadThumbnailBtn');
    
    if (fileInput.files.length > 0) {
        const file = fileInput.files[0];
        
        // Validate file type
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'];
        if (!allowedTypes.includes(file.type)) {
            playlistManager.showToast('Please select a valid image file (JPG, PNG, WebP, or GIF)', 'error');
            fileInput.value = '';
            fileNameInput.value = '';
            uploadBtn.disabled = true;
            return;
        }
        
        // Validate file size (10MB limit)
        if (file.size > 10 * 1024 * 1024) {
            playlistManager.showToast('File too large. Maximum size is 10MB.', 'error');
            fileInput.value = '';
            fileNameInput.value = '';
            uploadBtn.disabled = true;
            return;
        }
        
        fileNameInput.value = file.name;
        uploadBtn.disabled = false;
    } else {
        fileNameInput.value = '';
        uploadBtn.disabled = true;
    }
}

async function uploadPlaylistThumbnail() {
    const playlistId = document.getElementById('playlistId').value;
    const fileInput = document.getElementById('playlistThumbnailFile');
    const uploadBtn = document.getElementById('uploadThumbnailBtn');
    
    if (!fileInput.files.length) {
        playlistManager.showToast('Please select a file first', 'error');
        return;
    }
    
    if (!playlistId) {
        playlistManager.showToast('Please save the playlist first before uploading thumbnails', 'error');
        return;
    }
    
    const file = fileInput.files[0];
    
    try {
        // Show loading state
        const originalContent = uploadBtn.innerHTML;
        uploadBtn.innerHTML = '<iconify-icon icon="tabler:loader-2" class="spin"></iconify-icon> Uploading...';
        uploadBtn.disabled = true;
        
        // Create FormData for file upload
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`/api/playlists/${playlistId}/thumbnail/file`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `HTTP ${response.status}`);
        }
        
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error);
        }
        
        // Update the thumbnail URL field with the uploaded path
        if (data.thumbnail_path) {
            document.getElementById('playlistThumbnailUrl').value = data.thumbnail_path;
        }
        
        // Clear the file input
        fileInput.value = '';
        document.getElementById('playlistThumbnailFileName').value = '';
        
        playlistManager.showToast('Thumbnail uploaded successfully!', 'success');
        
    } catch (error) {
        console.error('Failed to upload thumbnail:', error);
        playlistManager.showToast(`Failed to upload thumbnail: ${error.message}`, 'error');
    } finally {
        // Restore button state
        const originalContent = '<iconify-icon icon="tabler:upload" aria-hidden="true"></iconify-icon> Upload';
        uploadBtn.innerHTML = originalContent;
        uploadBtn.disabled = !fileInput.files.length;
    }
}

// Dynamic Playlist Global Functions
function handlePlaylistTypeChange() {
    if (playlistManager) {
        playlistManager.handlePlaylistTypeChange();
    }
}

function applyDynamicTemplate() {
    if (playlistManager) {
        playlistManager.applyDynamicTemplate();
    }
}

function previewDynamicPlaylist() {
    if (playlistManager) {
        playlistManager.previewDynamicPlaylist();
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    playlistManager = new PlaylistManager();
});