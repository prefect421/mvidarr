/**
 * Enhanced Bulk Operations JavaScript for MVidarr 0.9.7 - Issue #74
 * Progressive enhancement for existing bulk operations UI
 * Adds real-time progress tracking, preview functionality, and improved UX
 */

class BulkOperationsEnhanced {
    constructor() {
        this.currentOperation = null;
        this.progressInterval = null;
        this.isEnhancedMode = true; // Flag to enable enhanced features
        this.init();
    }

    init() {
        console.log('🚀 Initializing Enhanced Bulk Operations');
        this.addProgressContainer();
        this.enhanceExistingButtons();
        this.checkForActiveOperations();
    }

    /**
     * Add progress container to the bulk actions panel
     */
    addProgressContainer() {
        const bulkPanel = document.getElementById('bulkActionsPanel');
        if (!bulkPanel) return;

        const progressHTML = `
            <div id="bulkProgressContainer" class="bulk-progress-container" style="display: none;">
                <div class="progress-header">
                    <h4>🔄 Bulk Operation in Progress</h4>
                    <button onclick="bulkEnhanced.cancelCurrentOperation()" class="btn-cancel">Cancel</button>
                </div>
                <div class="progress-details">
                    <div class="progress-bar-container">
                        <div id="bulkProgressBar" class="progress-bar">
                            <div id="bulkProgressFill" class="progress-fill" style="width: 0%"></div>
                        </div>
                        <span id="bulkProgressText">Starting...</span>
                    </div>
                    <div class="progress-stats">
                        <span id="bulkProgressStats">0 / 0 items processed</span>
                        <span id="bulkProgressTime">Estimated time: calculating...</span>
                    </div>
                    <div id="bulkProgressErrors" class="progress-errors" style="display: none;">
                        <h5>⚠️ Errors:</h5>
                        <ul id="bulkErrorList"></ul>
                    </div>
                </div>
                <div class="progress-actions">
                    <button onclick="bulkEnhanced.undoLastOperation()" id="bulkUndoBtn" class="btn-undo" style="display: none;">
                        Undo Last Operation
                    </button>
                </div>
            </div>
        `;

        const content = bulkPanel.querySelector('.bulk-actions-content');
        if (content) {
            content.insertAdjacentHTML('afterbegin', progressHTML);
        }
    }

    /**
     * Enhance existing bulk operation buttons with progress tracking
     */
    enhanceExistingButtons() {
        // Find all bulk operation buttons and enhance them
        const bulkButtons = document.querySelectorAll('[onclick*="bulkDownload"], [onclick*="bulkDelete"], [onclick*="bulkUpdateStatus"], [onclick*="bulkEdit"]');
        
        bulkButtons.forEach(button => {
            const originalOnclick = button.getAttribute('onclick');
            if (originalOnclick && !originalOnclick.includes('Enhanced')) {
                // Add preview functionality
                button.insertAdjacentHTML('afterend', `
                    <button class="btn-preview" onclick="bulkEnhanced.previewOperation('${originalOnclick}')" title="Preview this operation">
                        👁️ Preview
                    </button>
                `);
            }
        });

        // Add enhanced versions of key functions
        this.addEnhancedFunctions();
    }

    /**
     * Add enhanced versions of bulk operations
     */
    addEnhancedFunctions() {
        // Enhanced bulk download
        window.bulkDownloadEnhanced = async (preview = false) => {
            const selectedIds = this.getSelectedVideoIds();
            if (selectedIds.length === 0) {
                alert('Please select videos to download.');
                return;
            }

            if (preview) {
                return this.previewBulkDownload(selectedIds);
            }

            return this.executeBulkOperation('/api/videos/bulk/download', {
                video_ids: selectedIds,
                preview: false
            }, 'Downloading selected videos...');
        };

        // Enhanced bulk status update
        window.bulkUpdateStatusEnhanced = async (newStatus, preview = false) => {
            const selectedIds = this.getSelectedVideoIds();
            if (selectedIds.length === 0) {
                alert('Please select videos to update.');
                return;
            }

            if (preview) {
                return this.previewStatusUpdate(selectedIds, newStatus);
            }

            return this.executeBulkOperation('/api/videos/bulk/status', {
                video_ids: selectedIds,
                status: newStatus,
                preview: false
            }, `Updating status to ${newStatus}...`);
        };

        // Enhanced bulk edit
        window.bulkEditEnhanced = async (editData, preview = false) => {
            const selectedIds = this.getSelectedVideoIds();
            if (selectedIds.length === 0) {
                alert('Please select videos to edit.');
                return;
            }

            if (preview) {
                return this.previewBulkEdit(selectedIds, editData);
            }

            return this.executeBulkOperation('/api/videos/bulk/edit', {
                video_ids: selectedIds,
                ...editData,
                preview: false
            }, 'Updating video metadata...');
        };

        // Enhanced bulk delete
        window.bulkDeleteEnhanced = async (deleteFiles = false, preview = false) => {
            const selectedIds = this.getSelectedVideoIds();
            if (selectedIds.length === 0) {
                alert('Please select videos to delete.');
                return;
            }

            if (preview) {
                return this.previewBulkDelete(selectedIds, deleteFiles);
            }

            const confirmMsg = deleteFiles 
                ? `This will permanently delete ${selectedIds.length} videos and their files. This cannot be undone. Continue?`
                : `This will remove ${selectedIds.length} videos from the database. Files will be preserved. Continue?`;

            if (!confirm(confirmMsg)) return;

            return this.executeBulkOperation('/api/videos/bulk/delete', {
                video_ids: selectedIds,
                delete_files: deleteFiles,
                preview: false
            }, 'Deleting selected videos...');
        };
    }

    /**
     * Execute a bulk operation with progress tracking
     */
    async executeBulkOperation(endpoint, payload, operationName) {
        try {
            this.showProgress(operationName);
            
            const response = await fetch(endpoint, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });

            const result = await response.json();

            if (result.success && result.operation_id) {
                this.currentOperation = result.operation_id;
                this.startProgressTracking();
                return result;
            } else {
                this.hideProgress();
                alert(`Error: ${result.error || 'Operation failed'}`);
                return null;
            }
        } catch (error) {
            console.error('Bulk operation error:', error);
            this.hideProgress();
            alert(`Error: ${error.message}`);
            return null;
        }
    }

    /**
     * Start tracking progress for the current operation
     */
    startProgressTracking() {
        if (!this.currentOperation) return;

        this.progressInterval = setInterval(async () => {
            try {
                const response = await fetch(`/api/bulk-operations/operations/${this.currentOperation}/status`);
                const progress = await response.json();

                this.updateProgressDisplay(progress);

                // Stop tracking if operation is complete
                if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(progress.status)) {
                    clearInterval(this.progressInterval);
                    this.progressInterval = null;
                    
                    setTimeout(() => {
                        this.hideProgress();
                        if (progress.status === 'COMPLETED') {
                            this.showUndoOption();
                            // Refresh the video display
                            if (typeof loadVideos === 'function') {
                                loadVideos();
                            }
                        }
                    }, 2000);
                }
            } catch (error) {
                console.error('Progress tracking error:', error);
            }
        }, 1000); // Update every second
    }

    /**
     * Update the progress display
     */
    updateProgressDisplay(progress) {
        const progressBar = document.getElementById('bulkProgressFill');
        const progressText = document.getElementById('bulkProgressText');
        const progressStats = document.getElementById('bulkProgressStats');
        const progressTime = document.getElementById('bulkProgressTime');

        if (progressBar) {
            progressBar.style.width = `${progress.progress_percentage || 0}%`;
        }

        if (progressText) {
            progressText.textContent = progress.status || 'Processing...';
        }

        if (progressStats) {
            progressStats.textContent = `${progress.processed_items || 0} / ${progress.total_items || 0} items processed`;
        }

        if (progressTime && progress.estimated_completion) {
            const eta = new Date(progress.estimated_completion);
            progressTime.textContent = `Estimated completion: ${eta.toLocaleTimeString()}`;
        }

        // Show errors if any
        if (progress.failed_items > 0) {
            this.showErrors(progress.error_log || []);
        }
    }

    /**
     * Show progress container
     */
    showProgress(operationName) {
        const container = document.getElementById('bulkProgressContainer');
        if (container) {
            container.style.display = 'block';
            const progressText = document.getElementById('bulkProgressText');
            if (progressText) {
                progressText.textContent = operationName;
            }
        }
    }

    /**
     * Hide progress container
     */
    hideProgress() {
        const container = document.getElementById('bulkProgressContainer');
        if (container) {
            container.style.display = 'none';
        }
        this.currentOperation = null;
    }

    /**
     * Show undo option
     */
    showUndoOption() {
        const undoBtn = document.getElementById('bulkUndoBtn');
        if (undoBtn) {
            undoBtn.style.display = 'block';
            setTimeout(() => {
                undoBtn.style.display = 'none';
            }, 30000); // Hide after 30 seconds
        }
    }

    /**
     * Show errors
     */
    showErrors(errors) {
        const errorContainer = document.getElementById('bulkProgressErrors');
        const errorList = document.getElementById('bulkErrorList');
        
        if (errorContainer && errorList && errors.length > 0) {
            errorList.innerHTML = errors.map(error => `<li>${error}</li>`).join('');
            errorContainer.style.display = 'block';
        }
    }

    /**
     * Cancel current operation
     */
    async cancelCurrentOperation() {
        if (!this.currentOperation) return;

        try {
            const response = await fetch(`/api/bulk-operations/operations/${this.currentOperation}/cancel`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                clearInterval(this.progressInterval);
                this.hideProgress();
                alert('Operation cancelled successfully');
            } else {
                alert('Failed to cancel operation');
            }
        } catch (error) {
            console.error('Cancel operation error:', error);
            alert('Error cancelling operation');
        }
    }

    /**
     * Undo last operation
     */
    async undoLastOperation() {
        if (!this.currentOperation) return;

        if (!confirm('Are you sure you want to undo the last operation? This will reverse all changes made.')) {
            return;
        }

        try {
            const response = await fetch(`/api/bulk-operations/operations/${this.currentOperation}/undo`, {
                method: 'POST'
            });
            const result = await response.json();
            
            if (result.success) {
                alert('Operation undone successfully');
                // Refresh the video display
                if (typeof loadVideos === 'function') {
                    loadVideos();
                }
            } else {
                alert('Failed to undo operation');
            }
        } catch (error) {
            console.error('Undo operation error:', error);
            alert('Error undoing operation');
        }
    }

    /**
     * Preview bulk download
     */
    async previewBulkDownload(videoIds) {
        const videoTitles = this.getSelectedVideoTitles();
        const message = `This will start downloading ${videoIds.length} videos:\n\n${videoTitles.slice(0, 10).join('\n')}${videoTitles.length > 10 ? `\n... and ${videoTitles.length - 10} more` : ''}`;
        
        if (confirm(message + '\n\nProceed with download?')) {
            return bulkDownloadEnhanced(false);
        }
    }

    /**
     * Preview status update
     */
    async previewStatusUpdate(videoIds, newStatus) {
        const videoTitles = this.getSelectedVideoTitles();
        const message = `This will update the status of ${videoIds.length} videos to "${newStatus}":\n\n${videoTitles.slice(0, 10).join('\n')}${videoTitles.length > 10 ? `\n... and ${videoTitles.length - 10} more` : ''}`;
        
        if (confirm(message + '\n\nProceed with status update?')) {
            return bulkUpdateStatusEnhanced(newStatus, false);
        }
    }

    /**
     * Preview bulk edit
     */
    async previewBulkEdit(videoIds, editData) {
        const changes = Object.entries(editData).map(([key, value]) => `${key}: "${value}"`).join('\n');
        const message = `This will update ${videoIds.length} videos with the following changes:\n\n${changes}\n\nProceed with edit?`;
        
        if (confirm(message)) {
            return bulkEditEnhanced(editData, false);
        }
    }

    /**
     * Preview bulk delete
     */
    async previewBulkDelete(videoIds, deleteFiles) {
        const videoTitles = this.getSelectedVideoTitles();
        const action = deleteFiles ? 'delete (including files)' : 'remove from database';
        const message = `This will ${action} ${videoIds.length} videos:\n\n${videoTitles.slice(0, 10).join('\n')}${videoTitles.length > 10 ? `\n... and ${videoTitles.length - 10} more` : ''}`;
        
        if (confirm(message + `\n\nProceed with ${action}?`)) {
            return bulkDeleteEnhanced(deleteFiles, false);
        }
    }

    /**
     * Get selected video IDs
     */
    getSelectedVideoIds() {
        const checkboxes = document.querySelectorAll('input[name="video_ids"]:checked');
        return Array.from(checkboxes).map(cb => parseInt(cb.value));
    }

    /**
     * Get selected video titles for preview
     */
    getSelectedVideoTitles() {
        const checkboxes = document.querySelectorAll('input[name="video_ids"]:checked');
        return Array.from(checkboxes).map(cb => {
            const videoCard = cb.closest('.video-card');
            const titleElement = videoCard ? videoCard.querySelector('.video-title') : null;
            return titleElement ? titleElement.textContent.trim() : `Video ${cb.value}`;
        });
    }

    /**
     * Check for any active operations on page load
     */
    async checkForActiveOperations() {
        try {
            const response = await fetch('/api/bulk/bridge/health');
            const health = await response.json();
            
            if (health.active_operations > 0) {
                // Could restore progress tracking for active operations
                console.log(`Found ${health.active_operations} active bulk operations`);
            }
        } catch (error) {
            console.error('Error checking for active operations:', error);
        }
    }

    /**
     * Preview any operation
     */
    previewOperation(originalFunction) {
        const functionName = originalFunction.split('(')[0];
        
        switch (functionName) {
            case 'bulkDownload':
                return this.previewBulkDownload(this.getSelectedVideoIds());
            case 'bulkDelete':
                return this.previewBulkDelete(this.getSelectedVideoIds(), false);
            case 'bulkUpdateStatus':
                const status = originalFunction.match(/'([^']+)'/);
                return this.previewStatusUpdate(this.getSelectedVideoIds(), status ? status[1] : 'WANTED');
            default:
                alert('Preview not available for this operation');
        }
    }
}

// Initialize enhanced bulk operations when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize if we're on a page with bulk operations
    if (document.getElementById('bulkActionsPanel')) {
        window.bulkEnhanced = new BulkOperationsEnhanced();
    }
});

// Expose for global access
window.BulkOperationsEnhanced = BulkOperationsEnhanced;

/**
 * Streamlined Bulk Operations Tab Management - Issue #12
 * Handles the new 2-tab design with Actions and Manage tabs
 */

// Tab switching function for streamlined design
function switchBulkTab(tabName) {
    // Remove active class from all tabs and content
    document.querySelectorAll('.bulk-actions-tabs .tab-button').forEach(btn => {
        btn.classList.remove('active');
        btn.setAttribute('aria-selected', 'false');
    });
    
    document.querySelectorAll('.bulk-tab-content').forEach(content => {
        content.classList.remove('active');
    });
    
    // Activate selected tab
    const tabButton = document.getElementById(tabName + 'TabBtn');
    const tabContent = document.getElementById('bulk' + tabName.charAt(0).toUpperCase() + tabName.slice(1) + 'Tab');
    
    if (tabButton && tabContent) {
        tabButton.classList.add('active');
        tabButton.setAttribute('aria-selected', 'true');
        tabContent.classList.add('active');
    }
}

// Compact bulk action functions for streamlined design
function executeBulkAction(actionType, options = {}) {
    const selectedIds = getSelectedVideoIds();
    if (selectedIds.length === 0) {
        alert('Please select videos to perform this action.');
        return;
    }

    switch (actionType) {
        case 'download':
            if (typeof bulkDownloadEnhanced === 'function') {
                bulkDownloadEnhanced();
            } else {
                bulkDownload();
            }
            break;
            
        case 'delete':
            if (typeof bulkDeleteEnhanced === 'function') {
                bulkDeleteEnhanced(options.deleteFiles || false);
            } else {
                bulkDelete(options.deleteFiles || false);
            }
            break;
            
        case 'status':
            const status = options.status || 'WANTED';
            if (typeof bulkUpdateStatusEnhanced === 'function') {
                bulkUpdateStatusEnhanced(status);
            } else {
                bulkUpdateStatus(status);
            }
            break;
            
        case 'edit':
            performBulkEdit(options);
            break;
            
        case 'organize':
            performBulkOrganize(options);
            break;
            
        case 'quality':
            performQualityCheck(options);
            break;
            
        default:
            console.warn('Unknown bulk action type:', actionType);
    }
}

// Bulk edit function for the streamlined design
function performBulkEdit(options = {}) {
    const selectedIds = getSelectedVideoIds();
    if (selectedIds.length === 0) {
        alert('Please select videos to edit.');
        return;
    }

    const editData = {};
    
    // Get values from the bulk edit form
    const artistSelect = document.getElementById('bulkEditArtist');
    const albumInput = document.getElementById('bulkEditAlbum');
    const genreInput = document.getElementById('bulkEditGenre');
    
    if (artistSelect && artistSelect.value) {
        editData.artist_id = artistSelect.value;
    }
    
    if (albumInput && albumInput.value.trim()) {
        editData.album = albumInput.value.trim();
    }
    
    if (genreInput && genreInput.value.trim()) {
        editData.genre = genreInput.value.trim();
    }
    
    if (Object.keys(editData).length === 0) {
        alert('Please specify at least one field to edit.');
        return;
    }

    if (typeof bulkEditEnhanced === 'function') {
        bulkEditEnhanced(editData);
    } else {
        // Fallback to basic bulk edit
        console.log('Performing bulk edit with data:', editData);
        // Implementation would depend on existing bulk edit functionality
    }
}

// Bulk organize function
function performBulkOrganize(options = {}) {
    const selectedIds = getSelectedVideoIds();
    if (selectedIds.length === 0) {
        alert('Please select videos to organize.');
        return;
    }

    const action = options.action || 'move';
    let confirmMessage = '';
    
    switch (action) {
        case 'move':
            confirmMessage = `Move ${selectedIds.length} videos to organized folders?`;
            break;
        case 'rename':
            confirmMessage = `Rename ${selectedIds.length} video files using metadata?`;
            break;
        case 'clean':
            confirmMessage = `Clean metadata for ${selectedIds.length} videos?`;
            break;
    }
    
    if (confirm(confirmMessage)) {
        // Implementation would depend on existing organize functionality
        console.log(`Performing bulk organize: ${action} for ${selectedIds.length} videos`);
    }
}

// Quality check function
function performQualityCheck(options = {}) {
    const selectedIds = getSelectedVideoIds();
    if (selectedIds.length === 0) {
        alert('Please select videos for quality check.');
        return;
    }

    const checkType = options.type || 'integrity';
    console.log(`Performing quality check: ${checkType} for ${selectedIds.length} videos`);
    
    // Implementation would depend on existing quality check functionality
}

// Helper function to get selected video IDs (fallback if not available from enhanced class)
function getSelectedVideoIds() {
    if (window.bulkEnhanced && typeof window.bulkEnhanced.getSelectedVideoIds === 'function') {
        return window.bulkEnhanced.getSelectedVideoIds();
    }
    
    // Fallback implementation
    const checkboxes = document.querySelectorAll('input[name="video_ids"]:checked');
    return Array.from(checkboxes).map(cb => parseInt(cb.value));
}

// Initialize tab functionality on page load
document.addEventListener('DOMContentLoaded', function() {
    // Set up tab accessibility
    const tabButtons = document.querySelectorAll('.bulk-actions-tabs .tab-button');
    tabButtons.forEach(button => {
        button.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                button.click();
            }
        });
    });
    
    // Initialize first tab as active if none are active
    const activeTab = document.querySelector('.bulk-actions-tabs .tab-button.active');
    if (!activeTab && tabButtons.length > 0) {
        switchBulkTab('actions');
    }
});