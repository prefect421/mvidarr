/**
 * Scheduled Jobs JavaScript
 * Version: v0.10.1
 * Phase 5: Frontend Integration
 *
 * Handles scheduled jobs monitoring UI interactions
 */

const scheduledJobs = {
    // Configuration
    currentPage: 0,
    limit: 50,
    total: 0,
    filters: {
        status: '',
        job_type: '',
        artist_id: ''
    },

    /**
     * Initialize the page
     */
    init() {
        console.log('Initializing Scheduled Jobs Monitor');
        this.loadJobs();
    },

    /**
     * Apply filters
     */
    applyFilters() {
        this.filters.status = document.getElementById('filter-status')?.value || '';
        this.filters.job_type = document.getElementById('filter-type')?.value || '';
        this.filters.artist_id = document.getElementById('filter-artist')?.value || '';
        this.limit = parseInt(document.getElementById('filter-limit')?.value || '50');

        this.currentPage = 0; // Reset to first page
        this.loadJobs();
    },

    /**
     * Load jobs from API
     */
    async loadJobs() {
        try {
            const params = new URLSearchParams({
                limit: this.limit,
                offset: this.currentPage * this.limit,
                ...(this.filters.status && { status: this.filters.status }),
                ...(this.filters.job_type && { job_type: this.filters.job_type }),
                ...(this.filters.artist_id && { artist_id: this.filters.artist_id })
            });

            const response = await fetch(`/api/v2/jobs/scheduled?${params}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.total = data.total || 0;
            this.displayJobs(data.jobs || []);
            this.updatePagination();
        } catch (error) {
            console.error('Failed to load jobs:', error);
            this.showError('Failed to load jobs');
        }
    },

    /**
     * Display jobs in table
     */
    displayJobs(jobs) {
        const tbody = document.getElementById('jobs-table-body');

        if (jobs.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="8">
                        <div class="empty-state">
                            <iconify-icon icon="mdi:file-clock-outline"></iconify-icon>
                            <p>No jobs found</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = jobs.map(job => this.createJobRow(job)).join('');
    },

    /**
     * Create job table row
     */
    createJobRow(job) {
        const duration = this.calculateDuration(job.started_at, job.completed_at);
        const artistInfo = job.artist?.name || (job.artist_id ? `ID: ${job.artist_id}` : 'All');

        return `
            <tr>
                <td>
                    <span class="job-id">#${job.id}</span>
                </td>
                <td>
                    <span class="job-type-badge job-type-${job.job_type}">
                        ${job.job_type.toUpperCase()}
                    </span>
                </td>
                <td>
                    <span class="job-status-badge job-status-${job.status}">
                        <iconify-icon icon="mdi:${this.getStatusIcon(job.status)}" width="14"></iconify-icon>
                        ${job.status.toUpperCase()}
                    </span>
                </td>
                <td>${artistInfo}</td>
                <td>${this.formatDateTime(job.started_at) || '-'}</td>
                <td>${duration}</td>
                <td>
                    <span style="color: ${job.retry_count > 0 ? '#f59e0b' : 'inherit'};">
                        ${job.retry_count} / ${job.max_retries}
                    </span>
                </td>
                <td>
                    <div class="job-actions">
                        <button class="btn-icon btn-view"
                                onclick="scheduledJobs.viewJobDetails(${job.id})"
                                title="View Details">
                            <iconify-icon icon="mdi:eye" width="18"></iconify-icon>
                        </button>
                        ${job.status === 'failed' ? `
                            <button class="btn-icon btn-retry"
                                    onclick="scheduledJobs.retryJob(${job.id})"
                                    title="Retry Job">
                                <iconify-icon icon="mdi:refresh" width="18"></iconify-icon>
                            </button>
                        ` : ''}
                        ${job.status === 'pending' || job.status === 'running' ? `
                            <button class="btn-icon btn-cancel"
                                    onclick="scheduledJobs.cancelJob(${job.id})"
                                    title="Cancel Job">
                                <iconify-icon icon="mdi:close" width="18"></iconify-icon>
                            </button>
                        ` : ''}
                    </div>
                </td>
            </tr>
        `;
    },

    /**
     * Get status icon
     */
    getStatusIcon(status) {
        const icons = {
            'completed': 'check-circle',
            'failed': 'alert-circle',
            'running': 'loading',
            'pending': 'clock-outline',
            'cancelled': 'close-circle'
        };
        return icons[status] || 'information';
    },

    /**
     * Calculate duration
     */
    calculateDuration(start, end) {
        if (!start) return '-';
        if (!end && start) return 'Running...';

        const startTime = new Date(start);
        const endTime = new Date(end);
        const diffMs = endTime - startTime;
        const diffSecs = Math.floor(diffMs / 1000);

        if (diffSecs < 60) return `${diffSecs}s`;
        const diffMins = Math.floor(diffSecs / 60);
        if (diffMins < 60) return `${diffMins}m ${diffSecs % 60}s`;
        const diffHours = Math.floor(diffMins / 60);
        return `${diffHours}h ${diffMins % 60}m`;
    },

    /**
     * Format date/time
     */
    formatDateTime(dateString) {
        if (!dateString) return null;
        const date = new Date(dateString);
        return date.toLocaleString();
    },

    /**
     * Update pagination controls
     */
    updatePagination() {
        const totalPages = Math.max(1, Math.ceil(this.total / this.limit));
        const currentPageNum = this.currentPage + 1;

        document.getElementById('current-page').textContent = currentPageNum;
        document.getElementById('total-pages').textContent = totalPages;

        document.getElementById('btn-first-page').disabled = this.currentPage === 0;
        document.getElementById('btn-prev-page').disabled = this.currentPage === 0;
        document.getElementById('btn-next-page').disabled = currentPageNum >= totalPages;
        document.getElementById('btn-last-page').disabled = currentPageNum >= totalPages;
    },

    /**
     * Go to specific page
     */
    goToPage(page) {
        this.currentPage = page;
        this.loadJobs();
    },

    /**
     * Go to first page
     */
    firstPage() {
        this.goToPage(0);
    },

    /**
     * Go to previous page
     */
    previousPage() {
        if (this.currentPage > 0) {
            this.goToPage(this.currentPage - 1);
        }
    },

    /**
     * Go to next page
     */
    nextPage() {
        const totalPages = Math.ceil(this.total / this.limit);
        if (this.currentPage < totalPages - 1) {
            this.goToPage(this.currentPage + 1);
        }
    },

    /**
     * Go to last page
     */
    goToLastPage() {
        const lastPage = Math.max(0, Math.ceil(this.total / this.limit) - 1);
        this.goToPage(lastPage);
    },

    /**
     * View job details
     */
    async viewJobDetails(jobId) {
        try {
            const response = await fetch(`/api/v2/jobs/scheduled/${jobId}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const job = await response.json();
            this.showJobDetailsModal(job);
        } catch (error) {
            console.error('Failed to load job details:', error);
            this.showError('Failed to load job details');
        }
    },

    /**
     * Show job details modal
     */
    showJobDetailsModal(job) {
        const modal = document.getElementById('job-details-modal');
        const content = document.getElementById('job-details-content');

        const artistInfo = job.artist ?
            `${job.artist.name} (ID: ${job.artist.id})` :
            (job.artist_id ? `Artist ID: ${job.artist_id}` : 'All Artists');

        const resultSummary = job.result_summary ?
            JSON.stringify(job.result_summary, null, 2) :
            'No result data';

        content.innerHTML = `
            <div class="job-detail-section">
                <h3>
                    <iconify-icon icon="mdi:information-outline"></iconify-icon>
                    Basic Information
                </h3>
                <div class="job-detail-grid">
                    <div class="job-detail-item">
                        <div class="job-detail-label">Job ID</div>
                        <div class="job-detail-value">#${job.id}</div>
                    </div>
                    <div class="job-detail-item">
                        <div class="job-detail-label">Job Type</div>
                        <div class="job-detail-value">
                            <span class="job-type-badge job-type-${job.job_type}">
                                ${job.job_type.toUpperCase()}
                            </span>
                        </div>
                    </div>
                    <div class="job-detail-item">
                        <div class="job-detail-label">Status</div>
                        <div class="job-detail-value">
                            <span class="job-status-badge job-status-${job.status}">
                                ${job.status.toUpperCase()}
                            </span>
                        </div>
                    </div>
                    <div class="job-detail-item">
                        <div class="job-detail-label">Artist</div>
                        <div class="job-detail-value">${artistInfo}</div>
                    </div>
                </div>
            </div>

            <div class="job-detail-section">
                <h3>
                    <iconify-icon icon="mdi:clock-outline"></iconify-icon>
                    Timing
                </h3>
                <div class="job-detail-grid">
                    <div class="job-detail-item">
                        <div class="job-detail-label">Created</div>
                        <div class="job-detail-value">${this.formatDateTime(job.created_at)}</div>
                    </div>
                    <div class="job-detail-item">
                        <div class="job-detail-label">Started</div>
                        <div class="job-detail-value">${this.formatDateTime(job.started_at) || 'Not started'}</div>
                    </div>
                    <div class="job-detail-item">
                        <div class="job-detail-label">Completed</div>
                        <div class="job-detail-value">${this.formatDateTime(job.completed_at) || 'Not completed'}</div>
                    </div>
                    <div class="job-detail-item">
                        <div class="job-detail-label">Duration</div>
                        <div class="job-detail-value">${this.calculateDuration(job.started_at, job.completed_at)}</div>
                    </div>
                </div>
            </div>

            <div class="job-detail-section">
                <h3>
                    <iconify-icon icon="mdi:sync"></iconify-icon>
                    Retry Information
                </h3>
                <div class="job-detail-grid">
                    <div class="job-detail-item">
                        <div class="job-detail-label">Retry Count</div>
                        <div class="job-detail-value">${job.retry_count}</div>
                    </div>
                    <div class="job-detail-item">
                        <div class="job-detail-label">Max Retries</div>
                        <div class="job-detail-value">${job.max_retries}</div>
                    </div>
                    <div class="job-detail-item">
                        <div class="job-detail-label">Celery Task ID</div>
                        <div class="job-detail-value" style="font-family: monospace; font-size: 0.8rem; word-break: break-all;">
                            ${job.celery_task_id || 'N/A'}
                        </div>
                    </div>
                    <div class="job-detail-item">
                        <div class="job-detail-label">Triggered By</div>
                        <div class="job-detail-value">${job.triggered_by || 'system'}</div>
                    </div>
                </div>
            </div>

            ${job.error_message ? `
                <div class="job-detail-section">
                    <h3>
                        <iconify-icon icon="mdi:alert-circle"></iconify-icon>
                        Error Message
                    </h3>
                    <div class="error-box">${job.error_message}</div>
                </div>
            ` : ''}

            ${job.result_summary ? `
                <div class="job-detail-section">
                    <h3>
                        <iconify-icon icon="mdi:file-document-outline"></iconify-icon>
                        Result Summary
                    </h3>
                    <div class="error-box" style="background: var(--bg-secondary); border-color: var(--border-secondary); color: var(--text-primary);">
                        ${resultSummary}
                    </div>
                </div>
            ` : ''}

            <div class="job-detail-section" style="display: flex; gap: 1rem; justify-content: flex-end;">
                ${job.status === 'failed' ? `
                    <button class="btn btn-success" onclick="scheduledJobs.retryJob(${job.id}); scheduledJobs.closeModal();">
                        <iconify-icon icon="mdi:refresh"></iconify-icon>
                        Retry Job
                    </button>
                ` : ''}
                ${job.status === 'pending' || job.status === 'running' ? `
                    <button class="btn btn-danger" onclick="scheduledJobs.cancelJob(${job.id}); scheduledJobs.closeModal();">
                        <iconify-icon icon="mdi:close"></iconify-icon>
                        Cancel Job
                    </button>
                ` : ''}
                <button class="btn btn-primary" onclick="scheduledJobs.closeModal()">
                    Close
                </button>
            </div>
        `;

        modal.classList.add('active');
    },

    /**
     * Close modal
     */
    closeModal() {
        const modal = document.getElementById('job-details-modal');
        modal.classList.remove('active');
    },

    /**
     * Retry job
     */
    async retryJob(jobId) {
        if (!confirm('Retry this failed job?')) return;

        try {
            const response = await fetch(`/api/v2/jobs/scheduled/${jobId}/retry`, {
                method: 'POST'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.showSuccess(`Job retried successfully (New Task ID: ${data.new_task_id})`);

            // Refresh jobs list
            setTimeout(() => this.loadJobs(), 1000);
        } catch (error) {
            console.error('Failed to retry job:', error);
            this.showError('Failed to retry job');
        }
    },

    /**
     * Cancel job
     */
    async cancelJob(jobId) {
        if (!confirm('Cancel this job? This cannot be undone.')) return;

        try {
            const response = await fetch(`/api/v2/jobs/scheduled/${jobId}/cancel`, {
                method: 'POST'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.showSuccess(data.message || 'Job cancelled successfully');

            // Refresh jobs list
            setTimeout(() => this.loadJobs(), 1000);
        } catch (error) {
            console.error('Failed to cancel job:', error);
            this.showError('Failed to cancel job');
        }
    },

    /**
     * Clean up old jobs
     */
    async cleanupOldJobs() {
        const days = prompt('Delete jobs older than how many days?', '30');
        if (!days) return;

        const daysNum = parseInt(days);
        if (isNaN(daysNum) || daysNum < 1) {
            this.showError('Please enter a valid number of days');
            return;
        }

        if (!confirm(`Delete all jobs older than ${daysNum} days?`)) return;

        try {
            const response = await fetch(`/api/v2/jobs/history/cleanup?days=${daysNum}`, {
                method: 'DELETE'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.showSuccess(data.message || `Deleted ${data.deleted} old jobs`);

            // Refresh jobs list
            setTimeout(() => this.loadJobs(), 1000);
        } catch (error) {
            console.error('Failed to cleanup old jobs:', error);
            this.showError('Failed to cleanup old jobs');
        }
    },

    /**
     * Refresh data
     */
    refreshData() {
        this.loadJobs();
    },

    /**
     * Show success message
     */
    showSuccess(message) {
        console.log('Success:', message);
        alert(message);
    },

    /**
     * Show error message
     */
    showError(message) {
        console.error('Error:', message);
        alert('Error: ' + message);
    }
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = scheduledJobs;
}
