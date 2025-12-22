/**
 * Scheduler Dashboard JavaScript
 * Version: v0.10.1
 * Phase 5: Frontend Integration
 *
 * Handles scheduler dashboard UI interactions and real-time updates
 */

const schedulerDashboard = {
    // Configuration
    refreshInterval: 30000, // 30 seconds
    refreshTimer: null,
    currentFilters: {
        jobType: '',
        status: ''
    },

    /**
     * Initialize the dashboard
     */
    init() {
        console.log('Initializing Scheduler Dashboard');
        this.loadSchedulerStatus();
        this.loadStatistics();
        this.loadSchedules();
        this.loadHealthStatus();
        this.loadRecentJobs();

        // Start auto-refresh
        this.startAutoRefresh();

        // Cleanup on page unload
        window.addEventListener('beforeunload', () => {
            this.stopAutoRefresh();
        });
    },

    /**
     * Start auto-refresh timer
     */
    startAutoRefresh() {
        this.stopAutoRefresh(); // Clear any existing timer
        this.refreshTimer = setInterval(() => {
            this.refreshData();
        }, this.refreshInterval);
        console.log(`Auto-refresh started (every ${this.refreshInterval/1000}s)`);
    },

    /**
     * Stop auto-refresh timer
     */
    stopAutoRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
            console.log('Auto-refresh stopped');
        }
    },

    /**
     * Refresh all dashboard data
     */
    async refreshData() {
        console.log('Refreshing dashboard data...');
        await Promise.all([
            this.loadSchedulerStatus(),
            this.loadStatistics(),
            this.loadSchedules(),
            this.loadHealthStatus(),
            this.loadRecentJobs()
        ]);
    },

    /**
     * Load scheduler status
     */
    async loadSchedulerStatus() {
        try {
            const response = await fetch('/api/v2/scheduler/status');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.displaySchedulerStatus(data);
        } catch (error) {
            console.error('Failed to load scheduler status:', error);
            this.showError('Failed to load scheduler status');
        }
    },

    /**
     * Display scheduler status
     */
    displaySchedulerStatus(data) {
        const statusDisplay = document.getElementById('scheduler-status-display');
        const startBtn = document.getElementById('btn-start-scheduler');
        const stopBtn = document.getElementById('btn-stop-scheduler');

        let statusClass = 'running';
        let statusText = 'Running';
        let statusIcon = 'mdi:check-circle';

        if (data.status === 'stopped') {
            statusClass = 'stopped';
            statusText = 'Stopped';
            statusIcon = 'mdi:stop-circle';
        } else if (!data.celery_connected) {
            statusClass = 'degraded';
            statusText = 'Degraded - Celery Disconnected';
            statusIcon = 'mdi:alert-circle';
        } else if (!data.enabled) {
            statusClass = 'stopped';
            statusText = 'Disabled';
            statusIcon = 'mdi:pause-circle';
        }

        statusDisplay.innerHTML = `
            <div class="status-indicator ${statusClass}">
                <span class="status-dot"></span>
                <iconify-icon icon="${statusIcon}" width="20"></iconify-icon>
                <span>${statusText}</span>
            </div>
        `;

        // Update button states
        if (data.status === 'running') {
            startBtn.disabled = true;
            stopBtn.disabled = false;
        } else {
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
    },

    /**
     * Load statistics
     */
    async loadStatistics() {
        try {
            const response = await fetch('/api/v2/scheduler/status');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.displayStatistics(data.statistics || {});
        } catch (error) {
            console.error('Failed to load statistics:', error);
        }
    },

    /**
     * Display statistics
     */
    displayStatistics(stats) {
        document.getElementById('stat-total-jobs').textContent = stats.total_jobs_24h || 0;
        document.getElementById('stat-completed-jobs').textContent = stats.completed || 0;
        document.getElementById('stat-failed-jobs').textContent = stats.failed || 0;
        document.getElementById('stat-success-rate').textContent =
            (stats.success_rate !== undefined ? stats.success_rate + '%' : '-');
    },

    /**
     * Load active schedules
     */
    async loadSchedules() {
        try {
            const response = await fetch('/api/v2/scheduler/status');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.displaySchedules(data.schedules || {});
        } catch (error) {
            console.error('Failed to load schedules:', error);
        }
    },

    /**
     * Display active schedules
     */
    displaySchedules(schedules) {
        const container = document.getElementById('active-schedules');
        const scheduleEntries = Object.entries(schedules);

        if (scheduleEntries.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <iconify-icon icon="mdi:calendar-blank"></iconify-icon>
                    <p>No active schedules</p>
                </div>
            `;
            return;
        }

        const scheduleItems = scheduleEntries.map(([name, schedule]) => {
            const displayName = name.replace('scheduled-', '').replace(/-/g, ' ').toUpperCase();
            return `
                <div class="schedule-item">
                    <span class="schedule-name">${displayName}</span>
                    <span class="schedule-time">${schedule.schedule || 'N/A'}</span>
                </div>
            `;
        }).join('');

        container.innerHTML = scheduleItems;
    },

    /**
     * Load health status
     */
    async loadHealthStatus() {
        try {
            const response = await fetch('/api/v2/scheduler/health');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.displayHealthStatus(data);
        } catch (error) {
            console.error('Failed to load health status:', error);
        }
    },

    /**
     * Display health status
     */
    displayHealthStatus(health) {
        const container = document.getElementById('health-status');

        const celeryStatus = health.celery_connected ? 'connected' : 'disconnected';
        const celeryText = health.celery_connected ? 'Connected' : 'Disconnected';

        container.innerHTML = `
            <div class="health-item">
                <span class="health-name">Celery Connection</span>
                <span class="health-status ${celeryStatus}">
                    <iconify-icon icon="mdi:${health.celery_connected ? 'check-circle' : 'alert-circle'}" width="16"></iconify-icon>
                    ${celeryText}
                </span>
            </div>
            <div class="health-item">
                <span class="health-name">Scheduler Status</span>
                <span class="health-status ${health.running ? 'connected' : 'disconnected'}">
                    <iconify-icon icon="mdi:${health.running ? 'check-circle' : 'stop-circle'}" width="16"></iconify-icon>
                    ${health.running ? 'Running' : 'Stopped'}
                </span>
            </div>
            <div class="health-item">
                <span class="health-name">Scheduler Enabled</span>
                <span class="health-status ${health.enabled ? 'connected' : 'disconnected'}">
                    <iconify-icon icon="mdi:${health.enabled ? 'check-circle' : 'close-circle'}" width="16"></iconify-icon>
                    ${health.enabled ? 'Enabled' : 'Disabled'}
                </span>
            </div>
        `;
    },

    /**
     * Load recent jobs
     */
    async loadRecentJobs() {
        try {
            const params = new URLSearchParams({
                limit: 10,
                ...(this.currentFilters.jobType && { job_type: this.currentFilters.jobType }),
                ...(this.currentFilters.status && { status: this.currentFilters.status })
            });

            const response = await fetch(`/api/v2/scheduler/jobs?${params}`);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.displayRecentJobs(data.jobs || []);
        } catch (error) {
            console.error('Failed to load recent jobs:', error);
            this.showError('Failed to load recent jobs');
        }
    },

    /**
     * Display recent jobs
     */
    displayRecentJobs(jobs) {
        const container = document.getElementById('recent-jobs-container');

        if (jobs.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <iconify-icon icon="mdi:file-clock-outline"></iconify-icon>
                    <p>No recent jobs found</p>
                </div>
            `;
            return;
        }

        const tableHTML = `
            <table class="recent-jobs-table">
                <thead>
                    <tr>
                        <th>Type</th>
                        <th>Status</th>
                        <th>Artist</th>
                        <th>Started</th>
                        <th>Duration</th>
                    </tr>
                </thead>
                <tbody>
                    ${jobs.map(job => this.createJobRow(job)).join('')}
                </tbody>
            </table>
        `;

        container.innerHTML = tableHTML;
    },

    /**
     * Create job table row
     */
    createJobRow(job) {
        const duration = this.calculateDuration(job.started_at, job.completed_at);
        const artistName = job.artist?.name || (job.artist_id ? `Artist ${job.artist_id}` : 'All Artists');

        return `
            <tr>
                <td>
                    <span class="job-type-badge job-type-${job.job_type}">
                        ${job.job_type.toUpperCase()}
                    </span>
                </td>
                <td>
                    <span class="job-status-badge job-status-${job.status}">
                        ${job.status.toUpperCase()}
                    </span>
                </td>
                <td>${artistName}</td>
                <td>${this.formatDateTime(job.started_at) || '-'}</td>
                <td>${duration}</td>
            </tr>
        `;
    },

    /**
     * Calculate duration between two timestamps
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
     * Format date/time for display
     */
    formatDateTime(dateString) {
        if (!dateString) return null;
        const date = new Date(dateString);
        return date.toLocaleString();
    },

    /**
     * Filter jobs
     */
    filterJobs() {
        this.currentFilters.jobType = document.getElementById('filter-job-type')?.value || '';
        this.currentFilters.status = document.getElementById('filter-job-status')?.value || '';
        this.loadRecentJobs();
    },

    /**
     * Start scheduler
     */
    async startScheduler() {
        if (!confirm('Start the scheduler?')) return;

        try {
            const response = await fetch('/api/v2/scheduler/start', {
                method: 'POST'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.showSuccess(data.message || 'Scheduler started successfully');
            await this.loadSchedulerStatus();
        } catch (error) {
            console.error('Failed to start scheduler:', error);
            this.showError('Failed to start scheduler');
        }
    },

    /**
     * Stop scheduler
     */
    async stopScheduler() {
        if (!confirm('Stop the scheduler? This will not cancel running jobs.')) return;

        try {
            const response = await fetch('/api/v2/scheduler/stop', {
                method: 'POST'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.showSuccess(data.message || 'Scheduler stopped successfully');
            await this.loadSchedulerStatus();
        } catch (error) {
            console.error('Failed to stop scheduler:', error);
            this.showError('Failed to stop scheduler');
        }
    },

    /**
     * Reload settings
     */
    async reloadSettings() {
        try {
            const response = await fetch('/api/v2/scheduler/settings/reload', {
                method: 'POST'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.showSuccess(data.message || 'Settings reloaded successfully');
            await this.refreshData();
        } catch (error) {
            console.error('Failed to reload settings:', error);
            this.showError('Failed to reload settings');
        }
    },

    /**
     * Trigger discovery
     */
    async triggerDiscovery() {
        if (!confirm('Trigger discovery for all monitored artists?')) return;

        try {
            const response = await fetch('/api/v2/scheduler/trigger/discovery', {
                method: 'POST'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.showSuccess(`Discovery triggered (Task ID: ${data.task_id})`);

            // Refresh jobs after a short delay
            setTimeout(() => this.loadRecentJobs(), 2000);
        } catch (error) {
            console.error('Failed to trigger discovery:', error);
            this.showError('Failed to trigger discovery');
        }
    },

    /**
     * Trigger downloads
     */
    async triggerDownloads() {
        if (!confirm('Trigger downloads for all wanted videos?')) return;

        try {
            const response = await fetch('/api/v2/scheduler/trigger/downloads', {
                method: 'POST'
            });

            if (!response.ok) throw new Error(`HTTP ${response.status}`);

            const data = await response.json();
            this.showSuccess(`Downloads triggered (Task ID: ${data.task_id})`);

            // Refresh jobs after a short delay
            setTimeout(() => this.loadRecentJobs(), 2000);
        } catch (error) {
            console.error('Failed to trigger downloads:', error);
            this.showError('Failed to trigger downloads');
        }
    },

    /**
     * Show success notification
     */
    showSuccess(message) {
        // You can integrate with your notification system here
        console.log('Success:', message);
        alert(message); // Simple fallback
    },

    /**
     * Show error notification
     */
    showError(message) {
        // You can integrate with your notification system here
        console.error('Error:', message);
        alert('Error: ' + message); // Simple fallback
    }
};

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = schedulerDashboard;
}
