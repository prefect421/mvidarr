/**
 * MVidarr Playlist Detail Management JavaScript
 * Handles detailed playlist view, video management, and drag-drop reordering
 */

class PlaylistDetailManager {
    constructor() {
        this.playlistId = this.extractPlaylistId();
        this.playlist = null;
        this.videos = [];
        this.selectedVideos = new Set();
        this.availableVideos = [];
        this.selectedAvailableVideos = new Set();
        this.isLoading = false;
        this.canModify = false;
        this.isAdmin = false;
        this.draggedElement = null;
        this.draggedIndex = -1;
        
        this.init();
    }

    extractPlaylistId() {
        const path = window.location.pathname;
        const match = path.match(/\/playlist\/(\d+)/);
        return match ? parseInt(match[1]) : null;
    }

    async init() {
        if (!this.playlistId) {
            this.showError('Invalid playlist ID');
            return;
        }

        try {
            await this.checkUserPermissions();
            await this.loadPlaylist();
            this.initializeEventListeners();
            this.setupDragAndDrop();
            this.setupKeyboardShortcuts();
        } catch (error) {
            console.error('Failed to initialize playlist detail manager:', error);
            this.showError(`Failed to initialize: ${error.message}`);
        }
    }

    async checkUserPermissions() {
        try {
            const response = await fetch('/api/auth/user');
            if (response.ok) {
                const userData = await response.json();
                this.isAdmin = userData.user && userData.user.role === 'admin';
                
                if (this.isAdmin) {
                    const featuredGroup = document.getElementById('editFeaturedGroup');
                    if (featuredGroup) {
                        featuredGroup.style.display = 'block';
                    }
                }
            }
        } catch (error) {
            console.error('Failed to check user permissions:', error);
        }
    }

    async loadPlaylist() {
        if (this.isLoading) return;
        
        this.isLoading = true;
        this.showLoading(true);

        try {
            const response = await fetch(`/api/playlists/${this.playlistId}?include_entries=true&include_user=true&include_video_details=true`);
            
            if (!response.ok) {
                if (response.status === 404) {
                    throw new Error('Playlist not found');
                } else if (response.status === 403) {
                    throw new Error('Access denied to this playlist');
                } else {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }
            }

            const data = await response.json();
            
            if (data.success) {
                this.playlist = data.playlist;
                this.videos = data.playlist.entries || [];
                this.canModify = data.playlist.can_modify || false;

                // Debug logging to see playlist data structure
                console.log('Playlist detail data:', this.playlist);
                console.log('can_modify from API:', data.playlist.can_modify);
                console.log('this.canModify set to:', this.canModify);
                console.log('User data:', this.playlist.user);
                console.log('Owner field:', this.playlist.owner);
                
                this.renderPlaylist();
                this.renderVideos();
                this.updateUI();
            } else {
                throw new Error(data.error || 'Failed to load playlist');
            }
        } catch (error) {
            console.error('Failed to load playlist:', error);
            this.showError(error.message);
        } finally {
            this.isLoading = false;
            this.showLoading(false);
        }
    }

    renderPlaylist() {
        if (!this.playlist) return;

        // Update header
        document.getElementById('playlistTitle').textContent = this.playlist.name;
        
        // Update thumbnail
        const thumbnailContainer = document.getElementById('playlistHeaderThumbnail');
        console.log('Thumbnail debug:', {
            container: thumbnailContainer,
            thumbnailUrl: this.playlist.thumbnail_url,
            playlistData: this.playlist
        });
        
        if (thumbnailContainer && this.playlist.thumbnail_url) {
            console.log('Setting thumbnail image:', this.playlist.thumbnail_url);
            thumbnailContainer.innerHTML = `<img src="${this.escapeHtml(this.playlist.thumbnail_url)}" alt="${this.escapeHtml(this.playlist.name)} thumbnail" 
                                                 onerror="this.parentElement.innerHTML='<div class=\\'playlist-header-icon\\'><iconify-icon icon=\\'tabler:playlist\\' style=\\'font-size: 3rem;\\'></iconify-icon></div>'">`;
        } else if (thumbnailContainer) {
            console.log('Setting default icon - no thumbnail URL or container');
            thumbnailContainer.innerHTML = '<div class="playlist-header-icon"><iconify-icon icon="tabler:playlist" style="font-size: 3rem;"></iconify-icon></div>';
        } else {
            console.log('No thumbnail container found');
        }
        
        const description = document.getElementById('playlistDescription');
        if (this.playlist.description) {
            description.textContent = this.playlist.description;
            description.style.display = 'block';
        } else {
            description.style.display = 'none';
        }
        
        // Update meta information
        const videoCount = this.videos.length;
        document.getElementById('playlistVideoCount').textContent = `${videoCount} video${videoCount !== 1 ? 's' : ''}`;
        document.getElementById('playlistOwner').textContent = this.playlist.user?.username || this.playlist.owner || 'System';
        
        const updatedDate = new Date(this.playlist.updated_at).toLocaleDateString();
        document.getElementById('playlistUpdated').textContent = updatedDate;
        
        // Update badges
        const badgesContainer = document.getElementById('playlistBadges');
        const badges = [];
        
        if (this.playlist.is_featured) {
            badges.push('<span class="playlist-badge featured">Featured</span>');
        }
        if (this.playlist.is_public) {
            badges.push('<span class="playlist-badge public">Public</span>');
        } else {
            badges.push('<span class="playlist-badge private">Private</span>');
        }
        
        badgesContainer.innerHTML = badges.join('');
        
        // Show/hide action buttons based on permissions
        const editBtn = document.getElementById('editPlaylistBtn');
        const editFiltersBtn = document.getElementById('editFiltersBtn');
        const addVideoBtn = document.getElementById('addVideoBtn');
        const addFirstVideoBtn = document.getElementById('addFirstVideoBtn');

        if (this.canModify) {
            if (editBtn) editBtn.style.display = 'block';
            if (addVideoBtn) addVideoBtn.style.display = 'block';
            if (addFirstVideoBtn) addFirstVideoBtn.style.display = 'block';

            // Show "Edit Filters" button only for dynamic playlists
            if (editFiltersBtn) {
                editFiltersBtn.style.display = this.playlist.is_dynamic ? 'block' : 'none';
            }
        } else {
            if (editBtn) editBtn.style.display = 'none';
            if (editFiltersBtn) editFiltersBtn.style.display = 'none';
            if (addVideoBtn) addVideoBtn.style.display = 'none';
            if (addFirstVideoBtn) addFirstVideoBtn.style.display = 'none';
        }
    }

    renderVideos() {
        const videoList = document.getElementById('videoList');
        const playlistVideos = document.getElementById('playlistVideos');
        const emptyState = document.getElementById('emptyState');
        
        if (this.videos.length === 0) {
            if (playlistVideos) playlistVideos.style.display = 'none';
            if (emptyState) emptyState.style.display = 'block';
            return;
        }

        if (emptyState) emptyState.style.display = 'none';
        if (playlistVideos) playlistVideos.style.display = 'block';
        
        if (!videoList) return;

        videoList.innerHTML = this.videos.map((entry, index) => this.renderVideoItem(entry, index)).join('');
        
        // Add event listeners
        this.videos.forEach((entry, index) => {
            const item = document.getElementById(`video-item-${entry.id}`);
            if (item) {
                const checkbox = item.querySelector('.video-checkbox');
                if (checkbox) {
                    checkbox.addEventListener('change', (e) => {
                        this.handleVideoSelection(entry.id, e.target.checked);
                    });
                }
            }
        });
    }

    renderVideoItem(entry, index) {
        const video = entry.video;
        if (!video) return '';
        
        // Debug logging to see video data structure
        console.log('Rendering video entry:', entry);
        console.log('Video data:', video);
        console.log('Expected fields - artist_name:', video.artist_name, 'quality:', video.quality, 'duration:', video.duration, 'added_at:', entry.added_at);
        
        const isSelected = this.selectedVideos.has(entry.id);
        const thumbnailUrl = video.thumbnail_url || '/static/placeholder-video.png';
        const position = entry.position || index + 1;
        
        return `
            <div class="video-item ${isSelected ? 'selected' : ''}" 
                 id="video-item-${entry.id}" 
                 draggable="${this.canModify ? 'true' : 'false'}"
                 data-entry-id="${entry.id}"
                 data-position="${position}">
                
                <div class="video-item-checkbox">
                    <input type="checkbox" class="video-checkbox" ${isSelected ? 'checked' : ''} 
                           ${this.canModify ? '' : 'disabled'}>
                </div>
                
                ${this.canModify ? `
                    <div class="video-item-drag">
                        <iconify-icon icon="tabler:grip-vertical"></iconify-icon>
                    </div>
                ` : ''}
                
                <div class="video-item-position">${position}</div>
                
                <div class="video-item-thumbnail">
                    <img src="${thumbnailUrl}" alt="Video thumbnail" loading="lazy">
                </div>
                
                <div class="video-item-info">
                    <div class="video-item-title">${this.escapeHtml(video.title || video.name || 'Unknown Title')}</div>
                    <div class="video-item-artist">${this.escapeHtml(video.artist_name || video.artist?.name || 'Unknown Artist')}</div>
                    <div class="video-item-meta">
                        <span>Quality: ${video.quality || video.video_quality || 'N/A'}</span>
                        <span>Duration: ${this.formatDuration(video.duration || video.length || video.duration_seconds)}</span>
                        <span>Added: ${entry.added_at ? new Date(entry.added_at).toLocaleDateString() : entry.created_at ? new Date(entry.created_at).toLocaleDateString() : 'Unknown'}</span>
                    </div>
                </div>
                
                <div class="video-item-actions">
                    <button onclick="playLocalVideo(${video.id})" class="btn btn-primary btn-sm" title="Play video">
                        <iconify-icon icon="tabler:play"></iconify-icon>
                    </button>
                    <button onclick="viewVideoDetail(${video.id})" class="btn btn-secondary btn-sm" title="View details">
                        <iconify-icon icon="tabler:info-circle"></iconify-icon>
                    </button>
                    ${this.canModify ? `
                        <button onclick="removeVideoFromPlaylist(${entry.id})" class="btn btn-danger btn-sm" title="Remove from playlist">
                            <iconify-icon icon="tabler:x"></iconify-icon>
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
    }

    initializeEventListeners() {
        // Select all checkbox
        const selectAllCheckbox = document.getElementById('selectAllVideos');
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', (e) => {
                this.handleSelectAllVideos(e.target.checked);
            });
        }

        // Sort order dropdown
        const sortOrder = document.getElementById('sortOrder');
        if (sortOrder) {
            sortOrder.addEventListener('change', () => {
                this.applySortOrder();
            });
        }

        // Video search for adding to playlist
        const videoSearchInput = document.getElementById('videoSearchInput');
        if (videoSearchInput) {
            let debounceTimer;
            videoSearchInput.addEventListener('input', (e) => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => {
                    this.searchVideosForPlaylist(e.target.value.trim());
                }, 300);
            });
        }
    }

    setupDragAndDrop() {
        if (!this.canModify) return;

        const videoList = document.getElementById('videoList');
        if (!videoList) return;

        videoList.addEventListener('dragstart', (e) => {
            if (e.target.classList.contains('video-item')) {
                this.draggedElement = e.target;
                this.draggedIndex = Array.from(videoList.children).indexOf(e.target);
                e.target.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
            }
        });

        videoList.addEventListener('dragend', (e) => {
            if (e.target.classList.contains('video-item')) {
                e.target.classList.remove('dragging');
                this.draggedElement = null;
                this.draggedIndex = -1;
                
                // Remove all drag-over classes
                document.querySelectorAll('.drag-over').forEach(el => {
                    el.classList.remove('drag-over');
                });
            }
        });

        videoList.addEventListener('dragover', (e) => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            
            const afterElement = this.getDragAfterElement(videoList, e.clientY);
            const dragging = document.querySelector('.dragging');
            
            if (afterElement == null) {
                videoList.appendChild(dragging);
            } else {
                videoList.insertBefore(dragging, afterElement);
            }
        });

        videoList.addEventListener('drop', (e) => {
            e.preventDefault();
            this.handleVideoDrop();
        });
    }

    getDragAfterElement(container, y) {
        const draggableElements = [...container.querySelectorAll('.video-item:not(.dragging)')];
        
        return draggableElements.reduce((closest, child) => {
            const box = child.getBoundingClientRect();
            const offset = y - box.top - box.height / 2;
            
            if (offset < 0 && offset > closest.offset) {
                return { offset: offset, element: child };
            } else {
                return closest;
            }
        }, { offset: Number.NEGATIVE_INFINITY }).element;
    }

    async handleVideoDrop() {
        if (!this.draggedElement) return;

        const videoList = document.getElementById('videoList');
        const newIndex = Array.from(videoList.children).indexOf(this.draggedElement);
        
        if (newIndex === this.draggedIndex) return; // No change

        try {
            // Create new order array
            const newOrder = [];
            const videoItems = Array.from(videoList.children);
            
            videoItems.forEach((item, index) => {
                const entryId = parseInt(item.dataset.entryId);
                newOrder.push({
                    entry_id: entryId,
                    position: index + 1
                });
            });

            await this.reorderVideos(newOrder);
            
        } catch (error) {
            console.error('Failed to reorder videos:', error);
            this.showToast('Failed to reorder videos', 'error');
            // Reload to restore original order
            await this.loadPlaylist();
        }
    }

    async reorderVideos(newOrder) {
        try {
            const response = await fetch(`/api/playlists/${this.playlistId}/videos/reorder`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ order: newOrder })
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            if (!data.success) throw new Error(data.error);

            this.showToast('Videos reordered successfully', 'success');
            
            // Update local data
            this.videos = this.videos.map(entry => {
                const newOrderItem = newOrder.find(item => item.entry_id === entry.id);
                if (newOrderItem) {
                    entry.position = newOrderItem.position;
                }
                return entry;
            }).sort((a, b) => a.position - b.position);

        } catch (error) {
            throw error;
        }
    }

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Escape - Close modals
            if (e.key === 'Escape') {
                this.closeAllModals();
            }
            
            // Delete - Remove selected videos
            if (e.key === 'Delete' && this.selectedVideos.size > 0 && this.canModify && !e.target.matches('input, textarea')) {
                e.preventDefault();
                this.removeSelectedVideos();
            }
            
            // Ctrl/Cmd + A - Select all videos
            if ((e.ctrlKey || e.metaKey) && e.key === 'a' && !e.target.matches('input, textarea')) {
                e.preventDefault();
                const selectAllCheckbox = document.getElementById('selectAllVideos');
                if (selectAllCheckbox) {
                    selectAllCheckbox.checked = true;
                    this.handleSelectAllVideos(true);
                }
            }
        });
    }

    handleVideoSelection(entryId, isSelected) {
        if (isSelected) {
            this.selectedVideos.add(entryId);
        } else {
            this.selectedVideos.delete(entryId);
        }
        
        this.updateVideoSelectionUI();
    }

    handleSelectAllVideos(selectAll) {
        this.selectedVideos.clear();
        
        if (selectAll) {
            this.videos.forEach(entry => {
                this.selectedVideos.add(entry.id);
            });
        }
        
        // Update checkboxes
        document.querySelectorAll('.video-checkbox').forEach(checkbox => {
            checkbox.checked = selectAll;
        });
        
        // Update item styles
        document.querySelectorAll('.video-item').forEach(item => {
            item.classList.toggle('selected', selectAll);
        });
        
        this.updateVideoSelectionUI();
    }

    updateVideoSelectionUI() {
        const selectedCount = this.selectedVideos.size;
        
        // Update count displays
        const countElements = ['selectedVideoCount', 'selectedVideosCount'];
        countElements.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.textContent = selectedCount === 1 ? '1 video selected' : `${selectedCount} videos selected`;
            }
        });
        
        // Update select all checkbox
        const selectAllCheckbox = document.getElementById('selectAllVideos');
        if (selectAllCheckbox) {
            selectAllCheckbox.checked = selectedCount === this.videos.length && this.videos.length > 0;
            selectAllCheckbox.indeterminate = selectedCount > 0 && selectedCount < this.videos.length;
        }
        
        // Show/hide bulk actions panel
        const videoActionsPanel = document.getElementById('videoActionsPanel');
        if (videoActionsPanel) {
            videoActionsPanel.style.display = selectedCount > 0 ? 'block' : 'none';
        }
        
        // Update item selection styles
        this.videos.forEach(entry => {
            const item = document.getElementById(`video-item-${entry.id}`);
            if (item) {
                item.classList.toggle('selected', this.selectedVideos.has(entry.id));
            }
        });
    }

    async searchVideosForPlaylist(query) {
        if (!query) {
            document.getElementById('availableVideos').innerHTML = '<p style="padding: 1rem; text-align: center; color: var(--text-muted);">Enter a search term to find videos</p>';
            return;
        }

        console.log('Searching for videos with query:', query); // Debug logging

        try {
            // Try multiple possible API endpoints
            let apiUrl = `/api/videos/search?search=${encodeURIComponent(query)}&per_page=50`;
            let response = await fetch(apiUrl);
            
            // If that fails, try the alternative endpoint
            if (!response.ok) {
                console.log('First endpoint failed, trying alternative:', response.status);
                apiUrl = `/api/videos/?q=${encodeURIComponent(query)}&per_page=50`;
                response = await fetch(apiUrl);
            }
            
            // If that also fails, try another alternative
            if (!response.ok) {
                console.log('Second endpoint failed, trying third alternative:', response.status);
                apiUrl = `/api/videos/?search=${encodeURIComponent(query)}&per_page=50`;
                response = await fetch(apiUrl);
            }
            
            console.log('Final API URL used:', apiUrl); // Debug logging
            console.log('Search response status:', response.status); // Debug logging
            
            if (!response.ok) throw new Error(`Failed to search videos: ${response.status} ${response.statusText}`);

            const data = await response.json();
            console.log('Search response data:', data); // Debug logging
            
            if (data.videos) {
                this.availableVideos = data.videos || [];
                console.log('Found videos:', this.availableVideos.length); // Debug logging
                this.renderAvailableVideos();
            } else {
                console.error('Search API returned error:', data.error || 'No videos found');
                this.showToast(`Search failed: ${data.error || 'No videos found'}`, 'error');
            }
        } catch (error) {
            console.error('Failed to search videos:', error);
            this.showToast(`Failed to search videos: ${error.message}`, 'error');
        }
    }

    renderAvailableVideos() {
        const container = document.getElementById('availableVideos');
        if (!container) return;

        if (this.availableVideos.length === 0) {
            container.innerHTML = '<p style="padding: 1rem; text-align: center; color: var(--text-muted);">No videos found</p>';
            return;
        }

        console.log('Rendering available videos, first video structure:', this.availableVideos[0]); // Debug
        console.log('Thumbnail fields check:', {
            thumbnail_url: this.availableVideos[0]?.thumbnail_url,
            thumbnail: this.availableVideos[0]?.thumbnail,
            thumbnail_path: this.availableVideos[0]?.thumbnail_path,
            image_url: this.availableVideos[0]?.image_url
        }); // Debug thumbnails

        container.innerHTML = this.availableVideos.map(video => {
            const isSelected = this.selectedAvailableVideos.has(video.id);
            const isInPlaylist = this.videos.some(entry => entry.video.id === video.id);
            
            return `
                <div class="available-video-item ${isSelected ? 'selected' : ''} ${isInPlaylist ? 'disabled' : ''}"
                     onclick="playlistDetailManager.toggleAvailableVideoSelection(${video.id})">
                    <input type="checkbox" ${isSelected ? 'checked' : ''} ${isInPlaylist ? 'disabled' : ''}>
                    <div class="available-video-thumbnail">
                        <img src="${video.thumbnail_url || video.thumbnail || video.thumbnail_path || video.image_url || '/static/placeholder-video.png'}" alt="Thumbnail">
                    </div>
                    <div class="video-info" style="flex: 1;">
                        <div style="font-weight: 600; margin-bottom: 0.25rem;">${this.escapeHtml(video.title || video.name || 'Unknown Title')}</div>
                        <div style="color: var(--text-secondary); font-size: 0.9rem;">${this.escapeHtml(video.artist?.name || video.artist_name || video.artist || 'Unknown Artist')}</div>
                    </div>
                    ${isInPlaylist ? '<span style="color: var(--text-muted); font-size: 0.8rem;">Already in playlist</span>' : ''}
                </div>
            `;
        }).join('');

        this.updateAddSelectedButton();
    }

    toggleAvailableVideoSelection(videoId) {
        const video = this.availableVideos.find(v => v.id === videoId);
        if (!video) return;
        
        // Don't allow selection if video is already in playlist
        const isInPlaylist = this.videos.some(entry => entry.video.id === video.id);
        if (isInPlaylist) return;

        if (this.selectedAvailableVideos.has(videoId)) {
            this.selectedAvailableVideos.delete(videoId);
        } else {
            this.selectedAvailableVideos.add(videoId);
        }
        
        this.renderAvailableVideos();
    }

    updateAddSelectedButton() {
        const button = document.getElementById('addSelectedBtn');
        if (button) {
            const count = this.selectedAvailableVideos.size;
            button.disabled = count === 0;
            button.innerHTML = `<iconify-icon icon="tabler:plus"></iconify-icon> Add Selected Videos (${count})`;
        }
    }

    async addSelectedVideosToPlaylist() {
        if (this.selectedAvailableVideos.size === 0) return;

        try {
            const videoIds = Array.from(this.selectedAvailableVideos);

            // API expects video_ids as an array
            const response = await fetch(`/api/playlists/${this.playlistId}/videos`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ video_ids: videoIds })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail || `Failed to add videos`);
            }

            this.showToast(`Added ${videoIds.length} video${videoIds.length !== 1 ? 's' : ''} to playlist`, 'success');
            this.selectedAvailableVideos.clear();
            this.closeAddVideoModal();
            await this.loadPlaylist();

        } catch (error) {
            console.error('Failed to add videos:', error);
            this.showToast(`Failed to add videos: ${error.message}`, 'error');
        }
    }

    async removeSelectedVideos() {
        if (this.selectedVideos.size === 0) return;

        const count = this.selectedVideos.size;
        if (!confirm(`Remove ${count} video${count !== 1 ? 's' : ''} from this playlist?`)) {
            return;
        }

        try {
            const entryIds = Array.from(this.selectedVideos);
            
            for (const entryId of entryIds) {
                const response = await fetch(`/api/playlists/${this.playlistId}/videos/${entryId}`, {
                    method: 'DELETE'
                });

                if (!response.ok) throw new Error(`Failed to remove video ${entryId}`);
            }

            this.showToast(`Removed ${count} video${count !== 1 ? 's' : ''} from playlist`, 'success');
            this.selectedVideos.clear();
            await this.loadPlaylist();

        } catch (error) {
            console.error('Failed to remove videos:', error);
            this.showToast(`Failed to remove videos: ${error.message}`, 'error');
        }
    }

    async removeVideoFromPlaylist(entryId) {
        if (!confirm('Remove this video from the playlist?')) {
            return;
        }

        try {
            const response = await fetch(`/api/playlists/${this.playlistId}/videos/${entryId}`, {
                method: 'DELETE'
            });

            if (!response.ok) throw new Error('Failed to remove video');

            const data = await response.json();
            if (!data.success) throw new Error(data.error);

            this.showToast('Video removed from playlist', 'success');
            await this.loadPlaylist();

        } catch (error) {
            console.error('Failed to remove video:', error);
            this.showToast(`Failed to remove video: ${error.message}`, 'error');
        }
    }

    // Playlist actions
    async playPlaylist() {
        if (this.videos.length === 0) {
            this.showToast('Playlist is empty', 'warning');
            return;
        }
        
        window.location.href = `/mvtv?playlist=${this.playlistId}`;
    }

    async shufflePlaylist() {
        if (this.videos.length === 0) {
            this.showToast('Playlist is empty', 'warning');
            return;
        }
        
        window.location.href = `/mvtv?playlist=${this.playlistId}&shuffle=true`;
    }

    showEditPlaylistModal() {
        if (!this.playlist || !this.canModify) return;

        // Populate form with null checks
        const nameField = document.getElementById('editPlaylistName');
        const descriptionField = document.getElementById('editPlaylistDescription');
        const thumbnailUrlField = document.getElementById('editPlaylistThumbnailUrl');
        const publicField = document.getElementById('editPlaylistIsPublic');
        const featuredField = document.getElementById('editPlaylistIsFeatured');
        
        if (nameField) nameField.value = this.playlist.name;
        if (descriptionField) descriptionField.value = this.playlist.description || '';
        if (thumbnailUrlField) thumbnailUrlField.value = this.playlist.thumbnail_url || '';
        if (publicField) publicField.checked = this.playlist.is_public;
        if (featuredField) featuredField.checked = this.playlist.is_featured;
        
        // Reset file upload fields with null checks
        const fileInput = document.getElementById('editPlaylistThumbnailFile');
        const fileNameInput = document.getElementById('editPlaylistThumbnailFileName');
        const uploadBtn = document.getElementById('editUploadThumbnailBtn');
        
        if (fileInput) fileInput.value = '';
        if (fileNameInput) fileNameInput.value = '';
        if (uploadBtn) uploadBtn.disabled = true;

        this.showModal('editPlaylistModal');
    }

    async savePlaylistChanges(event) {
        event.preventDefault();
        
        const nameField = document.getElementById('editPlaylistName');
        const descriptionField = document.getElementById('editPlaylistDescription');
        const thumbnailUrlField = document.getElementById('editPlaylistThumbnailUrl');
        const publicField = document.getElementById('editPlaylistIsPublic');
        const featuredField = document.getElementById('editPlaylistIsFeatured');
        
        const playlistData = {
            name: nameField ? nameField.value.trim() : '',
            description: descriptionField ? descriptionField.value.trim() : '',
            thumbnail_url: thumbnailUrlField ? thumbnailUrlField.value.trim() : '',
            is_public: publicField ? publicField.checked : false,
            is_featured: featuredField ? featuredField.checked : false
        };
        
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
        
        try {
            const response = await fetch(`/api/playlists/${this.playlistId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(playlistData)
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `HTTP ${response.status}`);
            }
            
            const data = await response.json();
            if (!data.success) throw new Error(data.error);
            
            this.showToast('Playlist updated successfully', 'success');
            this.closeEditPlaylistModal();
            await this.loadPlaylist();
            
        } catch (error) {
            this.showToast(`Failed to update playlist: ${error.message}`, 'error');
        }
    }

    showAddVideoModal() {
        if (!this.canModify) return;
        
        this.selectedAvailableVideos.clear();
        document.getElementById('videoSearchInput').value = '';
        document.getElementById('availableVideos').innerHTML = '<p style="padding: 1rem; text-align: center; color: var(--text-muted);">Enter a search term to find videos</p>';
        
        this.showModal('addVideoToPlaylistModal');
    }


    async exportPlaylist() {
        try {
            const exportData = {
                name: this.playlist.name,
                description: this.playlist.description,
                videos: this.videos.map(entry => ({
                    title: entry.video.title,
                    artist: entry.video.artist?.name,
                    youtube_id: entry.video.youtube_id,
                    position: entry.position
                }))
            };

            const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = `${this.playlist.name.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_playlist.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            
            this.showToast('Playlist exported successfully', 'success');
        } catch (error) {
            this.showToast(`Failed to export playlist: ${error.message}`, 'error');
        }
    }

    // UI Helper Methods
    updateUI() {
        const elements = ['playlistHeader', 'secondaryActions'];
        elements.forEach(id => {
            const element = document.getElementById(id);
            if (element) element.style.display = 'block';
        });
    }

    showLoading(show) {
        const loading = document.getElementById('playlistDetailLoading');
        if (loading) {
            loading.style.display = show ? 'block' : 'none';
        }
    }

    showError(message) {
        const errorState = document.getElementById('errorState');
        const errorMessage = document.getElementById('errorMessage');
        
        if (errorState) errorState.style.display = 'block';
        if (errorMessage) errorMessage.textContent = message;
        
        // Hide other elements
        ['playlistDetailLoading', 'playlistHeader', 'playlistVideos', 'emptyState'].forEach(id => {
            const element = document.getElementById(id);
            if (element) element.style.display = 'none';
        });
    }

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
        ['editPlaylistModal', 'addVideoToPlaylistModal'].forEach(modalId => {
            this.closeModal(modalId);
        });
    }

    closeEditPlaylistModal() {
        this.closeModal('editPlaylistModal');
    }

    closeAddVideoModal() {
        this.closeModal('addVideoToPlaylistModal');
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
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    formatDuration(seconds) {
        if (!seconds || seconds === 0 || isNaN(seconds)) return 'N/A';
        
        // Convert to number if it's a string
        const numSeconds = typeof seconds === 'string' ? parseInt(seconds) : seconds;
        if (isNaN(numSeconds) || numSeconds <= 0) return 'N/A';
        
        const minutes = Math.floor(numSeconds / 60);
        const remainingSeconds = numSeconds % 60;
        return `${minutes}:${remainingSeconds.toString().padStart(2, '0')}`;
    }

    applySortOrder() {
        const sortOrder = document.getElementById('sortOrder');
        if (!sortOrder) return;
        
        const sortValue = sortOrder.value;
        console.log('Applying sort order:', sortValue); // Debug
        let sortedVideos = [...this.videos];
        
        switch (sortValue) {
            case 'position':
                sortedVideos.sort((a, b) => (a.position || 0) - (b.position || 0));
                break;
            case 'title':
                sortedVideos.sort((a, b) => (a.video.title || a.video.name || '').localeCompare(b.video.title || b.video.name || ''));
                break;
            case 'title_desc':
                sortedVideos.sort((a, b) => (b.video.title || b.video.name || '').localeCompare(a.video.title || a.video.name || ''));
                break;
            case 'artist':
                sortedVideos.sort((a, b) => (a.video.artist_name || a.video.artist?.name || '').localeCompare(b.video.artist_name || b.video.artist?.name || ''));
                break;
            case 'artist_desc':
                sortedVideos.sort((a, b) => (b.video.artist_name || b.video.artist?.name || '').localeCompare(a.video.artist_name || a.video.artist?.name || ''));
                break;
            case 'date_added':
                sortedVideos.sort((a, b) => new Date(b.added_at || b.created_at) - new Date(a.added_at || a.created_at));
                break;
            case 'date_added_desc':
                sortedVideos.sort((a, b) => new Date(a.added_at || a.created_at) - new Date(b.added_at || b.created_at));
                break;
            case 'duration':
                sortedVideos.sort((a, b) => (b.video.duration || 0) - (a.video.duration || 0));
                break;
            default:
                return; // No sorting needed
        }
        
        this.videos = sortedVideos;
        this.renderVideos();
    }

    async removeDuplicateVideos() {
        if (!this.canModify) {
            this.showToast('You do not have permission to modify this playlist', 'error');
            return;
        }

        try {
            // Find duplicate videos by video ID
            const videoIds = new Map();
            const duplicateEntries = [];
            
            this.videos.forEach(entry => {
                const videoId = entry.video.id;
                if (videoIds.has(videoId)) {
                    // This is a duplicate - mark for removal (keep first occurrence)
                    duplicateEntries.push(entry.id);
                } else {
                    videoIds.set(videoId, entry.id);
                }
            });
            
            if (duplicateEntries.length === 0) {
                this.showToast('No duplicate videos found in this playlist', 'info');
                return;
            }
            
            if (!confirm(`Remove ${duplicateEntries.length} duplicate video${duplicateEntries.length !== 1 ? 's' : ''} from this playlist?`)) {
                return;
            }
            
            // Remove duplicates
            for (const entryId of duplicateEntries) {
                const response = await fetch(`/api/playlists/${this.playlistId}/videos/${entryId}`, {
                    method: 'DELETE'
                });
                
                if (!response.ok) throw new Error(`Failed to remove duplicate ${entryId}`);
            }
            
            this.showToast(`Removed ${duplicateEntries.length} duplicate video${duplicateEntries.length !== 1 ? 's' : ''} from playlist`, 'success');
            await this.loadPlaylist();
            
        } catch (error) {
            console.error('Failed to remove duplicates:', error);
            this.showToast(`Failed to remove duplicates: ${error.message}`, 'error');
        }
    }
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Global functions for HTML onclick handlers
let playlistDetailManager;

function showEditPlaylistModal() {
    playlistDetailManager.showEditPlaylistModal();
}

function closeEditPlaylistModal() {
    playlistDetailManager.closeEditPlaylistModal();
}

function savePlaylistChanges(event) {
    return playlistDetailManager.savePlaylistChanges(event);
}

function showAddVideoModal() {
    playlistDetailManager.showAddVideoModal();
}

function closeAddVideoModal() {
    playlistDetailManager.closeAddVideoModal();
}

function addSelectedVideosToPlaylist() {
    playlistDetailManager.addSelectedVideosToPlaylist();
}

function removeVideoFromPlaylist(entryId) {
    playlistDetailManager.removeVideoFromPlaylist(entryId);
}

function removeSelectedVideos() {
    playlistDetailManager.removeSelectedVideos();
}

function toggleSelectAllVideos() {
    const checkbox = document.getElementById('selectAllVideos');
    if (checkbox) {
        playlistDetailManager.handleSelectAllVideos(checkbox.checked);
    }
}

function toggleVideoActionsPanel() {
    const panel = document.getElementById('videoActionsPanel');
    const button = document.getElementById('videoActionsToggle');
    
    if (panel) {
        const isVisible = panel.style.display !== 'none';
        panel.style.display = isVisible ? 'none' : 'block';
        
        if (button) {
            button.setAttribute('aria-expanded', isVisible ? 'false' : 'true');
        }
    }
}

function playPlaylist() {
    playlistDetailManager.playPlaylist();
}

function shufflePlaylist() {
    playlistDetailManager.shufflePlaylist();
}

function exportPlaylist() {
    playlistDetailManager.exportPlaylist();
}

function refreshPlaylist() {
    playlistDetailManager.loadPlaylist();
}

function sortPlaylist() {
    playlistDetailManager.applySortOrder();
}

function applySortOrder() {
    playlistDetailManager.applySortOrder();
}

function removeDuplicates() {
    playlistDetailManager.removeDuplicateVideos();
}

function playLocalVideo(videoId) {
    if (videoId) {
        // Use the same playback system as the main videos page
        if (typeof playVideoById === 'function') {
            playVideoById(videoId);
        } else {
            // Fallback: redirect to video detail page
            window.location.href = `/video/${videoId}?play=true`;
        }
    }
}

function viewVideoDetail(videoId) {
    window.location.href = `/video/${videoId}`;
}

function searchVideosForPlaylist(event) {
    if (event.key === 'Enter') {
        playlistDetailManager.searchVideosForPlaylist(event.target.value.trim());
    }
}

// Thumbnail upload functions for playlist detail page
async function importPlaylistThumbnailDetail() {
    const playlistId = playlistDetailManager.playlistId;
    const thumbnailUrlField = document.getElementById('editPlaylistThumbnailUrl');
    const importBtn = document.getElementById('editImportThumbnailBtn');
    
    if (!thumbnailUrlField || !importBtn) {
        console.error('Thumbnail elements not found in DOM');
        return;
    }
    
    const thumbnailUrl = thumbnailUrlField.value.trim();
    
    if (!thumbnailUrl) {
        playlistDetailManager.showToast('Please enter a thumbnail URL first', 'error');
        return;
    }
    
    // If it's already a local thumbnail path, no need to import
    if (thumbnailUrl.startsWith('/thumbnails/')) {
        playlistDetailManager.showToast('This is already a local thumbnail path', 'info');
        return;
    }
    
    // Validate that it's a proper URL
    try {
        new URL(thumbnailUrl);
    } catch (error) {
        playlistDetailManager.showToast('Please enter a valid URL (e.g., https://example.com/image.jpg)', 'error');
        return;
    }
    
    if (!playlistId) {
        playlistDetailManager.showToast('Invalid playlist ID', 'error');
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
        if (data.thumbnail_path && thumbnailUrlField) {
            thumbnailUrlField.value = data.thumbnail_path;
        }
        
        // Update the playlist data and re-render
        playlistDetailManager.playlist.thumbnail_url = data.thumbnail_path;
        playlistDetailManager.renderPlaylist();
        
        playlistDetailManager.showToast('Thumbnail imported successfully!', 'success');
        
    } catch (error) {
        console.error('Failed to import thumbnail:', error);
        playlistDetailManager.showToast(`Failed to import thumbnail: ${error.message}`, 'error');
    } finally {
        // Restore button state
        const originalContent = '<iconify-icon icon="tabler:download" aria-hidden="true"></iconify-icon> Import';
        importBtn.innerHTML = originalContent;
        importBtn.disabled = false;
    }
}

function handleDetailThumbnailFileSelect() {
    const fileInput = document.getElementById('editPlaylistThumbnailFile');
    const fileNameInput = document.getElementById('editPlaylistThumbnailFileName');
    const uploadBtn = document.getElementById('editUploadThumbnailBtn');
    
    if (fileInput.files.length > 0) {
        const file = fileInput.files[0];
        
        // Validate file type
        const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/gif'];
        if (!allowedTypes.includes(file.type)) {
            playlistDetailManager.showToast('Please select a valid image file (JPG, PNG, WebP, or GIF)', 'error');
            fileInput.value = '';
            fileNameInput.value = '';
            uploadBtn.disabled = true;
            return;
        }
        
        // Validate file size (10MB limit)
        if (file.size > 10 * 1024 * 1024) {
            playlistDetailManager.showToast('File too large. Maximum size is 10MB.', 'error');
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

async function uploadPlaylistThumbnailDetail() {
    const playlistId = playlistDetailManager.playlistId;
    const fileInput = document.getElementById('editPlaylistThumbnailFile');
    const uploadBtn = document.getElementById('editUploadThumbnailBtn');
    
    if (!fileInput || !uploadBtn) {
        console.error('File upload elements not found in DOM');
        return;
    }
    
    if (!fileInput.files.length) {
        playlistDetailManager.showToast('Please select a file first', 'error');
        return;
    }
    
    if (!playlistId) {
        playlistDetailManager.showToast('Invalid playlist ID', 'error');
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
        const thumbnailUrlField = document.getElementById('editPlaylistThumbnailUrl');
        if (data.thumbnail_path && thumbnailUrlField) {
            thumbnailUrlField.value = data.thumbnail_path;
        }
        
        // Update the playlist data and re-render
        playlistDetailManager.playlist.thumbnail_url = data.thumbnail_path;
        playlistDetailManager.renderPlaylist();
        
        // Clear the file input
        fileInput.value = '';
        const fileNameInput = document.getElementById('editPlaylistThumbnailFileName');
        if (fileNameInput) fileNameInput.value = '';
        
        playlistDetailManager.showToast('Thumbnail uploaded successfully!', 'success');
        
    } catch (error) {
        console.error('Failed to upload thumbnail:', error);
        playlistDetailManager.showToast(`Failed to upload thumbnail: ${error.message}`, 'error');
    } finally {
        // Restore button state
        const originalContent = '<iconify-icon icon="tabler:upload" aria-hidden="true"></iconify-icon> Upload';
        uploadBtn.innerHTML = originalContent;
        uploadBtn.disabled = !fileInput.files.length;
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    playlistDetailManager = new PlaylistDetailManager();
});
// Dynamic Playlist Filter Functions
async function showEditFiltersModal() {
    console.log('showEditFiltersModal called');
    if (!playlistDetailManager || !playlistDetailManager.playlist) {
        console.error('No playlist manager or playlist found');
        return;
    }

    const modal = document.getElementById('editFiltersModal');
    console.log('Modal element:', modal);
    const playlist = playlistDetailManager.playlist;
    console.log('Playlist data:', playlist);

    // Load genres into dropdown
    await loadGenresForFilter();

    // Parse filter criteria - it might be a JSON string or already an object
    let filterCriteria = {};
    console.log('Raw filter_criteria:', playlist.filter_criteria);
    console.log('Type of filter_criteria:', typeof playlist.filter_criteria);

    if (playlist.filter_criteria) {
        if (typeof playlist.filter_criteria === 'string') {
            try {
                filterCriteria = JSON.parse(playlist.filter_criteria);
                console.log('Parsed from JSON string:', filterCriteria);
            } catch (e) {
                console.error('Failed to parse filter_criteria as JSON:', e);
                filterCriteria = {};
            }
        } else if (typeof playlist.filter_criteria === 'object') {
            filterCriteria = playlist.filter_criteria;
            console.log('Already an object:', filterCriteria);
        }
    } else {
        console.log('No filter_criteria present on playlist');
    }
    console.log('Final parsed filter criteria:', filterCriteria);

    // Populate form with existing filter criteria
    // Genres - convert array to single value (take first genre if multiple)
    if (filterCriteria.genres && filterCriteria.genres.length > 0) {
        document.getElementById('filterGenre').value = filterCriteria.genres[0];
    } else {
        document.getElementById('filterGenre').value = '';
    }

    // Artists - convert array to comma-separated string
    if (filterCriteria.artists && filterCriteria.artists.length > 0) {
        document.getElementById('filterArtist').value = filterCriteria.artists.join(', ');
    } else {
        document.getElementById('filterArtist').value = '';
    }

    // Quality - convert array to single value (take first quality if multiple)
    if (filterCriteria.quality && filterCriteria.quality.length > 0) {
        document.getElementById('filterQuality').value = filterCriteria.quality[0];
    } else {
        document.getElementById('filterQuality').value = '';
    }

    // Status - convert array to single value (take first status if multiple)
    if (filterCriteria.status && filterCriteria.status.length > 0) {
        document.getElementById('filterStatus').value = filterCriteria.status[0];
    } else {
        document.getElementById('filterStatus').value = 'DOWNLOADED'; // Default to DOWNLOADED
    }

    // Year range
    if (filterCriteria.year_range) {
        document.getElementById('filterYearFrom').value = filterCriteria.year_range.min || '';
        document.getElementById('filterYearTo').value = filterCriteria.year_range.max || '';
    } else {
        document.getElementById('filterYearFrom').value = '';
        document.getElementById('filterYearTo').value = '';
    }

    // Duration range (convert from seconds to minutes)
    if (filterCriteria.duration_range) {
        if (filterCriteria.duration_range.min) {
            document.getElementById('filterDurationMin').value = Math.floor(filterCriteria.duration_range.min / 60);
        } else {
            document.getElementById('filterDurationMin').value = '';
        }
        if (filterCriteria.duration_range.max) {
            document.getElementById('filterDurationMax').value = Math.floor(filterCriteria.duration_range.max / 60);
        } else {
            document.getElementById('filterDurationMax').value = '';
        }
    } else {
        document.getElementById('filterDurationMin').value = '';
        document.getElementById('filterDurationMax').value = '';
    }

    // Limit (default to 100 if not specified)
    document.getElementById('filterLimit').value = filterCriteria.limit || 100;

    console.log('Setting modal display to block');
    modal.style.display = 'block';
    console.log('Modal display style:', modal.style.display);
}

function closeEditFiltersModal() {
    const modal = document.getElementById('editFiltersModal');
    modal.style.display = 'none';
    document.getElementById('filterPreviewResults').style.display = 'none';
}

async function loadGenresForFilter() {
    try {
        const response = await fetch('/api/genres/');
        const data = await response.json();

        const select = document.getElementById('filterGenre');
        // Clear existing options except "Any Genre"
        select.innerHTML = '<option value="">Any Genre</option>';

        if (data.genres && data.genres.length > 0) {
            data.genres.forEach(genreObj => {
                const option = document.createElement('option');
                option.value = genreObj.genre;
                option.textContent = `${genreObj.genre} (${genreObj.video_count} videos)`;
                select.appendChild(option);
            });
            console.log(`Loaded ${data.genres.length} genres into filter dropdown`);
        }
    } catch (error) {
        console.error('Failed to load genres:', error);
    }
}

async function previewFilters() {
    const filterCriteria = getFilterCriteriaFromForm();
    
    try {
        const response = await fetch('/api/playlists/dynamic/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filter_criteria: filterCriteria,
                limit: 20
            })
        });
        
        const data = await response.json();
        
        const resultsDiv = document.getElementById('filterPreviewResults');
        const countP = document.getElementById('filterPreviewCount');
        const videosDiv = document.getElementById('filterPreviewVideos');
        
        if (data.success) {
            countP.textContent = `Found ${data.total_matches} matching videos (showing first ${data.videos.length})`;

            videosDiv.innerHTML = data.videos.map(video => {
                const duration = video.duration ? playlistDetailManager.formatDuration(video.duration) : 'N/A';
                const quality = video.quality || 'Unknown';
                return `
                    <div style="padding: 0.5rem; border-bottom: 1px solid var(--border-secondary);">
                        <div style="font-weight: 600;">${video.title}</div>
                        <div style="font-size: 0.9rem; color: var(--text-secondary);">
                            ${video.artist_name} • ${duration} • ${quality}
                        </div>
                    </div>
                `;
            }).join('');

            resultsDiv.style.display = 'block';
        } else {
            playlistDetailManager.showToast('Failed to preview filters', 'error');
        }
    } catch (error) {
        console.error('Failed to preview filters:', error);
        playlistDetailManager.showToast(`Failed to preview: ${error.message}`, 'error');
    }
}

async function saveFilterChanges(event) {
    event.preventDefault();
    
    if (!playlistDetailManager || !playlistDetailManager.playlistId) return;
    
    const filterCriteria = getFilterCriteriaFromForm();
    
    try {
        const response = await fetch(`/api/playlists/${playlistDetailManager.playlistId}/filters`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filter_criteria: filterCriteria })
        });
        
        const data = await response.json();
        
        if (data.success) {
            playlistDetailManager.showToast(`Filters updated! Playlist now has ${data.video_count} videos`, 'success');
            closeEditFiltersModal();
            await playlistDetailManager.loadPlaylist();
        } else {
            throw new Error(data.detail || 'Failed to update filters');
        }
    } catch (error) {
        console.error('Failed to save filter changes:', error);
        playlistDetailManager.showToast(`Failed to save filters: ${error.message}`, 'error');
    }
}

function getFilterCriteriaFromForm() {
    const criteria = {};

    // Genre - convert single selection to array for consistency with create form
    const genre = document.getElementById('filterGenre').value;
    if (genre) {
        criteria.genres = [genre];
    }

    // Artist - convert comma-separated string to array
    const artist = document.getElementById('filterArtist').value.trim();
    if (artist) {
        criteria.artists = artist.split(',').map(a => a.trim()).filter(a => a);
    }

    // Quality - convert single selection to array for consistency with create form
    const quality = document.getElementById('filterQuality').value;
    if (quality) {
        criteria.quality = [quality];
    }

    // Status - convert single selection to array for consistency with create form
    const status = document.getElementById('filterStatus').value;
    if (status) {
        criteria.status = [status];
    }

    // Year range - use min/max structure
    const yearFrom = document.getElementById('filterYearFrom').value;
    const yearTo = document.getElementById('filterYearTo').value;
    if (yearFrom || yearTo) {
        criteria.year_range = {};
        if (yearFrom) criteria.year_range.min = parseInt(yearFrom);
        if (yearTo) criteria.year_range.max = parseInt(yearTo);
    }

    // Duration range - convert from minutes to seconds
    const durationMin = document.getElementById('filterDurationMin').value;
    const durationMax = document.getElementById('filterDurationMax').value;
    if (durationMin || durationMax) {
        criteria.duration_range = {};
        if (durationMin) criteria.duration_range.min = parseInt(durationMin) * 60; // Convert to seconds
        if (durationMax) criteria.duration_range.max = parseInt(durationMax) * 60; // Convert to seconds
    }

    // Limit
    const limit = document.getElementById('filterLimit').value;
    if (limit) {
        criteria.limit = parseInt(limit);
    }

    console.log('Filter criteria from form:', criteria);
    return criteria;
}
