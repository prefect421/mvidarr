/**
 * Background Jobs UI Integration
 * Real-time job progress tracking with WebSocket integration
 */

class BackgroundJobManager {
    constructor() {
        this.socket = null;
        this.activeJobs = new Map();
        this.jobCallbacks = new Map();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;
        
        this.init();
    }
    
    init() {
        this.connectWebSocket();
        this.createJobProgressContainer();
        this.setupGlobalEventListeners();
    }
    
    // ========================================
    // WEBSOCKET CONNECTION
    // ========================================
    
    connectWebSocket() {
        try {
            // Use FastAPI WebSocket for real-time job progress
            // Auto-detect protocol: use wss:// for https://, ws:// for http://
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/jobs`;
            this.socket = new WebSocket(wsUrl);
            this.setupWebSocketListeners();
        } catch (error) {
            console.error('Failed to connect WebSocket:', error);
            this.setupPollingFallback();
        }
    }
    
    setupWebSocketListeners() {
        this.socket.onopen = () => {
            this.reconnectAttempts = 0;
            this.showConnectionStatus('connected');
        };

        this.socket.onclose = () => {
            this.showConnectionStatus('disconnected');
            this.attemptReconnection();
        };
        
        this.socket.onerror = (error) => {
            console.error('📡 WebSocket error:', error);
            this.showError('WebSocket connection error');
        };
        
        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleWebSocketMessage(data);
            } catch (e) {
                console.error('Failed to process WebSocket message:', e.message);
                console.error('Raw message data:', event.data);
                console.error('Error details:', e);
            }
        };
    }
    
    attemptReconnection() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            const delay = this.reconnectDelay * this.reconnectAttempts;

            setTimeout(() => {
                this.connectWebSocket();
            }, delay);
        } else {
            console.warn('📡 Max reconnection attempts reached, switching to polling');
            this.setupPollingFallback();
        }
    }
    
    setupPollingFallback() {
        // Poll every 5 seconds for active jobs
        this.pollingInterval = setInterval(() => {
            this.activeJobs.forEach((jobData, jobId) => {
                if (jobData.status !== 'completed' && jobData.status !== 'failed') {
                    this.pollJobStatus(jobId);
                }
            });
        }, 5000);
    }
    
    async pollJobStatus(jobId) {
        try {
            const response = await fetch(`/api/jobs/${jobId}`, {
                credentials: 'include'
            });
            
            if (response.ok) {
                const data = await response.json();
                this.handleJobStatus(data);
            }
        } catch (error) {
            console.error('Error polling job status:', error);
        }
    }
    
    // ========================================
    // JOB MANAGEMENT
    // ========================================
    
    async startJob(jobType, payload, options = {}) {
        try {
            const jobData = {
                type: jobType,
                priority: options.priority || 'normal',
                payload: payload
            };
            
            // Add optional parameters
            if (options.max_retries !== undefined) {
                jobData.max_retries = options.max_retries;
            }
            
            let response;
            
            // Use specific endpoints for certain job types until generic jobs API is fully working
            if (jobType === 'metadata_enrichment' && payload.artist_id) {
                // Use the existing metadata enrichment endpoint
                response = await fetch(`/api/metadata-enrichment/enrich/artist/${payload.artist_id}`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify({
                        force_refresh: payload.force_refresh || true,
                        enrich_videos: payload.enrich_videos || true
                    })
                });
            } else if (jobType === 'auto_match' && payload.artist_id) {
                // Use the auto-match endpoint
                response = await fetch(`/api/metadata-enrichment/auto-match/${payload.artist_id}`, {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include'
                });
            } else {
                // Use generic jobs API for other job types
                response = await fetch('/api/jobs/enqueue', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'include',
                    body: JSON.stringify(jobData)
                });
            }
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to start job');
            }
            
            const result = await response.json();
            const jobId = result.job_id;

            // Handle fast-completing jobs like auto-match
            if (jobType === 'auto_match' && result.result) {
                // Auto-match completes immediately, simulate job completion
                // Track job locally with completed status
                this.activeJobs.set(jobId, {
                    id: jobId,
                    type: jobType,
                    status: 'completed',
                    progress: 100,
                    message: result.result.completion_message || 'Auto-match completed',
                    startTime: Date.now(),
                    result: result.result
                });
                
                // Show progress UI briefly
                this.showJobProgress(jobId, options);
                
                // Call completion callback with longer delay to show the job
                if (options.onComplete) {
                    setTimeout(() => {
                        options.onComplete(null, result.result);
                        // Keep job visible for a bit longer before removing
                        setTimeout(() => {
                            this.removeJob(jobId);
                        }, 3000);
                    }, 2000); // Show completed state for 2 seconds
                }
                
                return jobId;
            }

            // Standard job handling for other job types
            // Subscribe to job updates
            this.subscribeToJob(jobId);
            
            // Track job locally
            this.activeJobs.set(jobId, {
                id: jobId,
                type: jobType,
                status: 'queued',
                progress: 0,
                message: 'Job queued...',
                startTime: Date.now()
            });
            
            // Show initial progress UI
            this.showJobProgress(jobId, options);
            
            // Store callback if provided
            if (options.onComplete) {
                this.jobCallbacks.set(jobId, options.onComplete);
            }

            return jobId;
            
        } catch (error) {
            console.error('Failed to start job:', error);
            this.showError(`Failed to start job: ${error.message}`);
            throw error;
        }
    }
    
    subscribeToJob(jobId) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'subscribe_job',
                job_id: jobId
            }));
        } else {
            console.warn(`📡 Cannot subscribe to job ${jobId} - WebSocket not ready. State: ${this.socket ? this.socket.readyState : 'null'}`);
        }
    }
    
    unsubscribeFromJob(jobId) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                type: 'unsubscribe_job',
                job_id: jobId
            }));
        }
    }
    
    handleWebSocketMessage(data) {
        try {
            switch (data.type) {
                case 'connected':
                    break;
                case 'job_update':
                    this.handleJobUpdate(data);
                    break;
                case 'job_status':
                    this.handleJobStatus(data);
                    break;
            case 'subscription_response':
                break;
            case 'unsubscription_response':
                break;
            case 'active_jobs':
                break;
            case 'status':
                break;
            case 'heartbeat':
                break;
            case 'error':
                console.error('📡 WebSocket error:', data.message);
                this.showError('WebSocket error: ' + data.message);
                break;
            default:
                break;
        }
        } catch (e) {
            console.error('❌ Error in handleWebSocketMessage:', e.message);
            console.error('❌ Message data:', data);
            console.error('❌ Full error:', e);
        }
    }
    
    cancelJob(jobId) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            fetch(`/api/jobs/${jobId}/cancel`, {
                method: 'POST',
                credentials: 'include'
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    this.handleJobCancellation(jobId);
                } else {
                    console.error('Failed to cancel job:', data.error);
                    this.showError(data.error);
                }
            })
            .catch(error => {
                console.error('Error cancelling job:', error);
                this.showError('Failed to cancel job');
            });
        }
    }
    
    // ========================================
    // EVENT HANDLERS
    // ========================================
    
    handleJobUpdate(data) {
        const jobId = data.job_id || data.data?.job_id;
        if (!jobId) return;

        const jobData = data.data || data;

        // Update local job tracking
        if (this.activeJobs.has(jobId)) {
            const existingData = this.activeJobs.get(jobId);
            const updatedData = { ...existingData, ...jobData };
            this.activeJobs.set(jobId, updatedData);
        } else {
            // If job not found in local tracking, create with default type
            const jobWithDefaults = {
                id: jobId,
                type: jobData.type || 'unknown_job', // Default type if not provided
                ...jobData
            };
            this.activeJobs.set(jobId, jobWithDefaults);
        }
        
        // Update UI based on job status (WebSocket format)
        const status = jobData.status;
        
        if (status === 'completed' || status === 'success' || status === 'SUCCESS') {
            this.handleJobCompletion(jobId, jobData);
        } else if (status === 'failed' || status === 'failure' || status === 'FAILURE') {
            this.handleJobFailure(jobId, jobData);
        } else if (status === 'processing' || status === 'progress') {
            // Update progress UI
            this.updateJobProgressUI(jobId, jobData);
        } else {
            // Default: update progress UI for any other status
            this.updateJobProgressUI(jobId, jobData);
        }
    }
    
    handleJobStatus(data) {
        const jobId = data.job_id;
        if (!jobId) return;
        
        // Update local tracking
        this.activeJobs.set(jobId, data);
        
        // Update UI
        this.updateJobProgressUI(jobId, data);
        
        // Handle completion
        if (data.status === 'completed' || data.status === 'SUCCESS') {
            this.handleJobCompletion(jobId, data);
        } else if (data.status === 'failed' || data.status === 'FAILURE') {
            this.handleJobFailure(jobId, data);
        }
    }
    
    handleJobCompletion(jobId, data) {
        // Update final progress
        this.updateJobProgressUI(jobId, {
            ...data,
            progress: 100,
            status: 'completed'
        });
        
        // Call completion callback if exists
        const callback = this.jobCallbacks.get(jobId);
        if (callback) {
            callback(null, data);
            this.jobCallbacks.delete(jobId);
        }
        
        // Auto-hide progress after delay
        setTimeout(() => {
            this.hideJobProgress(jobId);
        }, 3000);
        
        // Show success notification
        this.showSuccess(`Job completed successfully: ${data.message || 'Task finished'}`);
        
        // Clean up subscription
        this.unsubscribeFromJob(jobId);
        
        // Remove from active jobs after delay
        setTimeout(() => {
            this.activeJobs.delete(jobId);
        }, 10000);
    }
    
    handleJobFailure(jobId, data) {
        console.error(`❌ Job ${jobId} failed:`, data);
        
        // Update UI to show failure
        this.updateJobProgressUI(jobId, {
            ...data,
            status: 'failed'
        });
        
        // Call completion callback with error
        const callback = this.jobCallbacks.get(jobId);
        if (callback) {
            callback(new Error(data.error_message || 'Job failed'), data);
            this.jobCallbacks.delete(jobId);
        }
        
        // Show error notification
        this.showError(`Job failed: ${data.error_message || 'Unknown error'}`);
        
        // Clean up subscription
        this.unsubscribeFromJob(jobId);
        
        // Remove from active jobs after delay
        setTimeout(() => {
            this.activeJobs.delete(jobId);
        }, 30000);
    }
    
    handleJobCancellation(jobId) {
        // Update UI
        this.updateJobProgressUI(jobId, {
            status: 'cancelled',
            message: 'Job was cancelled'
        });
        
        // Call callback with cancellation
        const callback = this.jobCallbacks.get(jobId);
        if (callback) {
            callback(new Error('Job was cancelled'), null);
            this.jobCallbacks.delete(jobId);
        }
        
        // Hide progress
        setTimeout(() => {
            this.hideJobProgress(jobId);
            this.activeJobs.delete(jobId);
        }, 2000);
    }
    
    // ========================================
    // UI COMPONENTS
    // ========================================
    
    createJobProgressContainer() {
        // Create container for job progress indicators
        if (!document.getElementById('job-progress-container')) {
            const container = document.createElement('div');
            container.id = 'job-progress-container';
            container.className = 'job-progress-container';
            container.innerHTML = `
                <div class="job-progress-header">
                    <h4><iconify-icon icon="tabler:activity"></iconify-icon> Background Jobs</h4>
                    <button class="btn-minimize" onclick="backgroundJobs.toggleContainer()">
                        <iconify-icon icon="tabler:chevron-down"></iconify-icon>
                    </button>
                </div>
                <div class="job-progress-list" id="job-progress-list">
                </div>
            `;
            
            // Position container
            Object.assign(container.style, {
                position: 'fixed',
                bottom: '20px',
                right: '20px',
                width: '400px',
                maxWidth: '90vw',
                background: 'var(--bg-secondary, #2a2a2a)',
                border: '1px solid var(--border-secondary, #444)',
                borderRadius: '12px',
                boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)',
                zIndex: '9999',
                display: 'none'
            });
            
            document.body.appendChild(container);
        }
    }
    
    showJobProgress(jobId, options = {}) {
        const container = document.getElementById('job-progress-container');
        const list = document.getElementById('job-progress-list');

        if (!container || !list) {
            console.error(`📊 Missing job progress elements! Container: ${!!container}, List: ${!!list}`);
            return;
        }

        // Show container
        container.style.display = 'block';

        // Create progress item
        const jobData = this.activeJobs.get(jobId) || {};
        
        const progressItem = document.createElement('div');
        progressItem.id = `job-${jobId}`;
        progressItem.className = 'job-progress-item';
        
        this.updateJobProgressItem(progressItem, jobId, jobData);

        list.appendChild(progressItem);
    }
    
    updateJobProgressUI(jobId, data) {
        const progressItem = document.getElementById(`job-${jobId}`);
        if (progressItem) {
            this.updateJobProgressItem(progressItem, jobId, data);
        }
        
        // Enhanced toast notifications for major status changes
        this.updateJobToastNotification(jobId, data);
    }
    
    updateJobToastNotification(jobId, data) {
        const jobData = this.activeJobs.get(jobId);
        if (!jobData) return;
        
        const previousStatus = jobData.lastNotifiedStatus;
        const currentStatus = data.status;
        const progress = data.progress || 0;
        
        // Only show notifications for significant status changes
        if (previousStatus !== currentStatus) {
            const jobTypeDisplay = this.getJobTypeDisplay(jobData.type);
            
            switch (currentStatus) {
                case 'processing':
                    if (window.toastManager) {
                        window.toastManager.show(`${jobTypeDisplay} started`, 'info', {
                            duration: 3000,
                            icon: 'tabler:loader-2'
                        });
                    }
                    break;
                    
                case 'completed':
                    if (window.toastManager) {
                        window.toastManager.show(`${jobTypeDisplay} completed successfully`, 'success', {
                            duration: 5000,
                            icon: 'tabler:check-circle'
                        });
                    }
                    break;
                    
                case 'failed':
                    if (window.toastManager) {
                        const errorMsg = data.error_message || 'Job failed';
                        window.toastManager.show(`${jobTypeDisplay} failed: ${errorMsg}`, 'error', {
                            duration: 8000,
                            icon: 'tabler:x-circle'
                        });
                    }
                    break;
            }
            
            // Update the last notified status
            jobData.lastNotifiedStatus = currentStatus;
            this.activeJobs.set(jobId, jobData);
        }
        
        // Show progress milestones (25%, 50%, 75%)
        const lastProgress = jobData.lastNotifiedProgress || 0;
        if (progress > 0 && Math.floor(progress / 25) > Math.floor(lastProgress / 25)) {
            const milestone = Math.floor(progress / 25) * 25;
            if (milestone > 0 && milestone < 100) {
                if (window.toastManager) {
                    window.toastManager.show(`${this.getJobTypeDisplay(jobData.type)} ${milestone}% complete`, 'info', {
                        duration: 2000,
                        icon: 'tabler:progress'
                    });
                }
            }
            jobData.lastNotifiedProgress = progress;
            this.activeJobs.set(jobId, jobData);
        }
    }
    
    updateJobProgressItem(element, jobId, data) {
        const progress = data.progress || 0;
        const message = data.message || 'Processing...';
        const status = data.status || 'queued';
        
        // Status indicators
        const statusIcons = {
            queued: 'tabler:clock',
            processing: 'tabler:loader-2',
            completed: 'tabler:check-circle',
            failed: 'tabler:x-circle',
            cancelled: 'tabler:ban'
        };
        
        const statusColors = {
            queued: '#f59e0b',
            processing: '#3b82f6',
            completed: '#10b981',
            failed: '#ef4444',
            cancelled: '#6b7280'
        };
        
        element.innerHTML = `
            <div class="job-header">
                <div class="job-info">
                    <iconify-icon icon="${statusIcons[status]}" 
                                 style="color: ${statusColors[status]}"
                                 ${status === 'processing' ? 'class="spin"' : ''}></iconify-icon>
                    <span class="job-title">${this.getJobTypeDisplay(data.type)}</span>
                </div>
                <div class="job-actions">
                    ${status === 'processing' || status === 'queued' ? 
                        `<button class="btn-cancel" onclick="backgroundJobs.cancelJob('${jobId}')" title="Cancel Job">
                            <iconify-icon icon="tabler:x"></iconify-icon>
                         </button>` : ''
                    }
                    <button class="btn-close" onclick="backgroundJobs.hideJobProgress('${jobId}')" title="Hide">
                        <iconify-icon icon="tabler:x"></iconify-icon>
                    </button>
                </div>
            </div>
            <div class="job-progress">
                <div class="progress-bar">
                    <div class="progress-fill" style="width: ${progress}%; background-color: ${statusColors[status]}"></div>
                </div>
                <div class="progress-info">
                    <span class="progress-message">${message}</span>
                    <span class="progress-percentage">${progress}%</span>
                </div>
            </div>
            ${data.error_message ? `<div class="job-error">${data.error_message}</div>` : ''}
        `;
    }
    
    hideJobProgress(jobId) {
        const progressItem = document.getElementById(`job-${jobId}`);
        if (progressItem) {
            progressItem.remove();
        }
        
        // Hide container if no active jobs
        const list = document.getElementById('job-progress-list');
        if (list && list.children.length === 0) {
            const container = document.getElementById('job-progress-container');
            if (container) {
                container.style.display = 'none';
            }
        }
    }
    
    toggleContainer() {
        const container = document.getElementById('job-progress-container');
        const list = document.getElementById('job-progress-list');
        const btn = container.querySelector('.btn-minimize iconify-icon');
        
        if (list.style.display === 'none') {
            list.style.display = 'block';
            btn.setAttribute('icon', 'tabler:chevron-down');
        } else {
            list.style.display = 'none';
            btn.setAttribute('icon', 'tabler:chevron-up');
        }
    }
    
    // ========================================
    // UTILITY FUNCTIONS
    // ========================================
    
    getJobTypeDisplay(type) {
        const displayNames = {
            metadata_enrichment: 'Metadata Enrichment',
            video_download: 'Video Download',
            bulk_video_download: 'Bulk Video Download',
            bulk_artist_import: 'Bulk Import',
            thumbnail_generation: 'Thumbnail Generation',
            playlist_sync: 'Playlist Sync',
            bulk_video_delete: 'Bulk Delete',
            database_cleanup: 'Database Cleanup',
            // Video quality operations
            video_quality_analyze: 'Quality Analysis',
            video_quality_upgrade: 'Quality Upgrade',
            video_quality_bulk_upgrade: 'Bulk Quality Upgrade',
            video_quality_check_all: 'Quality Check All',
            // Video indexing operations
            video_index_all: 'Index All Videos',
            video_index_single: 'Index Video',
            // Video organization operations
            video_organize_all: 'Organize All Videos',
            video_organize_single: 'Organize Video',
            video_reorganize_existing: 'Reorganize Videos',
            // Scheduler operations
            scheduled_download: 'Scheduled Download',
            scheduled_discovery: 'Scheduled Discovery'
        };
        
        if (!type) {
            return 'Background Job';
        }
        
        return displayNames[type] || type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
    
    showConnectionStatus(status) {
        // Show connection status in UI (could be a small indicator)
    }
    
    showSuccess(message) {
        // Use existing notification system if available
        if (typeof window.uiEnhancements !== 'undefined' && window.uiEnhancements.showNotification) {
            window.uiEnhancements.showNotification({
                type: 'success',
                title: 'Job Complete',
                message: message
            });
        } else if (typeof showSuccess === 'function') {
            showSuccess(message);
        }
    }
    
    showError(message) {
        // Use existing notification system if available
        if (typeof window.uiEnhancements !== 'undefined' && window.uiEnhancements.showNotification) {
            window.uiEnhancements.showNotification({
                type: 'error',
                title: 'Job Failed',
                message: message
            });
        } else if (typeof showError === 'function') {
            showError(message);
        } else {
            console.error('❌ ' + message);
        }
    }
    
    showInfo(message) {
        if (typeof window.uiEnhancements !== 'undefined' && window.uiEnhancements.showNotification) {
            window.uiEnhancements.showNotification({
                type: 'info',
                title: 'Job Update',
                message: message
            });
        } else if (typeof showInfo === 'function') {
            showInfo(message);
        } else {
            console.log('ℹ️ ' + message);
        }
    }
    
    setupGlobalEventListeners() {
        // Clean up on page unload
        window.addEventListener('beforeunload', () => {
            if (this.pollingInterval) {
                clearInterval(this.pollingInterval);
            }
        });
    }
    
    // ========================================
    // PUBLIC API
    // ========================================
    
    // Start a metadata enrichment job
    async startMetadataEnrichment(artistId, options = {}) {
        return this.startJob('metadata_enrichment', {
            artist_id: artistId,
            force_refresh: options.force_refresh || false,
            enrich_videos: options.enrich_videos !== false
        }, options);
    }
    
    // Start an auto-match job
    async startAutoMatch(artistId, options = {}) {
        return this.startJob('auto_match', {
            artist_id: artistId
        }, options);
    }
    
    // Start a video download job
    async startVideoDownload(videoId, options = {}) {
        return this.startJob('video_download', {
            video_id: videoId,
            quality: options.quality || 'best'
        }, options);
    }
    
    // Get current job status
    getJobStatus(jobId) {
        return this.activeJobs.get(jobId);
    }
    
    // Get all active jobs
    getActiveJobs() {
        return Array.from(this.activeJobs.values());
    }
    
    // Remove a job from tracking and UI
    removeJob(jobId) {
        console.log(`🗑️ Removing job ${jobId}`);
        
        // Remove from active jobs
        this.activeJobs.delete(jobId);
        
        // Remove job callbacks
        this.jobCallbacks.delete(jobId);
        
        // Remove from UI
        const progressItem = document.getElementById(`job-${jobId}`);
        if (progressItem) {
            progressItem.remove();
            console.log(`🗑️ Removed job ${jobId} from UI`);
        }
        
        // Hide container if no jobs left
        const list = document.getElementById('job-progress-list');
        const container = document.getElementById('job-progress-container');
        if (list && container && list.children.length === 0) {
            container.style.display = 'none';
            console.log('📦 Job container hidden - no active jobs');
        }
    }
}

// CSS Styles for job progress UI
const jobProgressStyles = `
<style>
.job-progress-container {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

.job-progress-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: var(--bg-tertiary, #333);
    border-radius: 12px 12px 0 0;
    border-bottom: 1px solid var(--border-secondary, #444);
}

.job-progress-header h4 {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--text-primary, #fff);
}

.btn-minimize {
    background: none;
    border: none;
    color: var(--text-secondary, #ccc);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    transition: all 0.2s ease;
}

.btn-minimize:hover {
    background: var(--bg-hover, #444);
    color: var(--text-primary, #fff);
}

.job-progress-item {
    padding: 16px;
    border-bottom: 1px solid var(--border-secondary, #444);
}

.job-progress-item:last-child {
    border-bottom: none;
    border-radius: 0 0 12px 12px;
}

.job-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 12px;
}

.job-info {
    display: flex;
    align-items: center;
    gap: 8px;
}

.job-title {
    font-weight: 600;
    color: var(--text-primary, #fff);
    font-size: 13px;
}

.job-actions {
    display: flex;
    gap: 4px;
}

.btn-cancel, .btn-close {
    background: none;
    border: none;
    color: var(--text-secondary, #ccc);
    cursor: pointer;
    padding: 4px;
    border-radius: 4px;
    transition: all 0.2s ease;
    font-size: 12px;
}

.btn-cancel:hover {
    background: var(--danger-bg, #ef4444);
    color: white;
}

.btn-close:hover {
    background: var(--bg-hover, #444);
    color: var(--text-primary, #fff);
}

.job-progress {
    margin-top: 8px;
}

.progress-bar {
    height: 6px;
    background: var(--bg-tertiary, #333);
    border-radius: 3px;
    overflow: hidden;
    margin-bottom: 8px;
}

.progress-fill {
    height: 100%;
    background: var(--accent-color, #3b82f6);
    transition: width 0.3s ease;
    border-radius: 3px;
}

.progress-info {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
}

.progress-message {
    color: var(--text-secondary, #ccc);
    flex: 1;
    margin-right: 8px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.progress-percentage {
    color: var(--text-primary, #fff);
    font-weight: 600;
    min-width: 35px;
    text-align: right;
}

.job-error {
    margin-top: 8px;
    padding: 8px;
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    border-radius: 4px;
    color: #fca5a5;
    font-size: 12px;
}

.spin {
    animation: spin 1s linear infinite;
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

/* Dark theme adjustments */
[data-theme="dark"] .job-progress-container {
    --bg-secondary: #1e1e1e;
    --bg-tertiary: #2a2a2a;
    --border-secondary: #333;
    --text-primary: #fff;
    --text-secondary: #ccc;
    --bg-hover: #333;
}

/* Light theme adjustments */
[data-theme="light"] .job-progress-container {
    --bg-secondary: #ffffff;
    --bg-tertiary: #f5f5f5;
    --border-secondary: #e0e0e0;
    --text-primary: #000;
    --text-secondary: #666;
    --bg-hover: #f0f0f0;
}
</style>`;

// Initialize the job manager
window.backgroundJobs = new BackgroundJobManager();

// Add styles to document
document.head.insertAdjacentHTML('beforeend', jobProgressStyles);

console.log('🚀 Background Jobs UI System loaded successfully');