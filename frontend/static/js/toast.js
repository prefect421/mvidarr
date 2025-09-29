/**
 * Toast Notification System for MVidarr Enhanced
 * Replaces all popup alerts and error messages with modern toast notifications
 */

class ToastManager {
    constructor() {
        this.toasts = [];
        this.maxToasts = 5;
        this.defaultDuration = 5000; // 5 seconds
        this.init();
    }

    init() {
        // Create toast container if it doesn't exist
        if (!document.getElementById('toast-container')) {
            this.createToastContainer();
        }
    }

    createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }

    /**
     * Show a toast notification
     * @param {string} message - The message to display
     * @param {string} type - Toast type: 'success', 'error', 'warning', 'info'
     * @param {number} duration - Duration in milliseconds (0 = no auto-dismiss)
     * @param {Object} options - Additional options
     */
    show(message, type = 'info', duration = null, options = {}) {
        const toastDuration = duration !== null ? duration : this.defaultDuration;
        
        const toast = {
            id: this.generateId(),
            message,
            type,
            duration: toastDuration,
            timestamp: Date.now(),
            ...options
        };

        // Remove oldest toast if we've reached the limit
        if (this.toasts.length >= this.maxToasts) {
            this.removeToast(this.toasts[0].id);
        }

        this.toasts.push(toast);
        this.renderToast(toast);

        // Auto-dismiss if duration is set
        if (toastDuration > 0) {
            setTimeout(() => {
                this.removeToast(toast.id);
            }, toastDuration);
        }

        return toast.id;
    }

    /**
     * Show success toast
     */
    success(message, duration = null, options = {}) {
        return this.show(message, 'success', duration, options);
    }

    /**
     * Show error toast
     */
    error(message, duration = 8000, options = {}) {
        return this.show(message, 'error', duration, options);
    }

    /**
     * Show warning toast
     */
    warning(message, duration = 6000, options = {}) {
        return this.show(message, 'warning', duration, options);
    }

    /**
     * Show info toast
     */
    info(message, duration = null, options = {}) {
        return this.show(message, 'info', duration, options);
    }

    /**
     * Show loading toast (doesn't auto-dismiss)
     */
    loading(message, options = {}) {
        return this.show(message, 'loading', 0, options);
    }

    /**
     * Update an existing toast
     */
    update(toastId, message, type = null) {
        const toast = this.toasts.find(t => t.id === toastId);
        if (toast) {
            toast.message = message;
            if (type) toast.type = type;
            
            const element = document.getElementById(`toast-${toastId}`);
            if (element) {
                const messageEl = element.querySelector('.toast-message');
                const iconEl = element.querySelector('.toast-icon');
                
                if (messageEl) messageEl.textContent = message;
                if (type && iconEl) {
                    element.className = `toast toast-${type}`;
                    iconEl.innerHTML = this.getIcon(type);
                }
            }
        }
    }

    /**
     * Remove a specific toast
     */
    removeToast(toastId) {
        const toastIndex = this.toasts.findIndex(t => t.id === toastId);
        if (toastIndex !== -1) {
            this.toasts.splice(toastIndex, 1);
        }

        const element = document.getElementById(`toast-${toastId}`);
        if (element) {
            element.classList.add('toast-removing');
            setTimeout(() => {
                if (element.parentNode) {
                    element.parentNode.removeChild(element);
                }
            }, 300);
        }
    }

    /**
     * Clear all toasts
     */
    clear() {
        this.toasts.forEach(toast => {
            this.removeToast(toast.id);
        });
        this.toasts = [];
    }

    /**
     * Render a toast element
     */
    renderToast(toast) {
        const container = document.getElementById('toast-container');
        if (!container) return;

        const toastElement = document.createElement('div');
        toastElement.id = `toast-${toast.id}`;
        toastElement.className = `toast toast-${toast.type}`;
        
        const progressBar = toast.duration > 0 ? 
            `<div class="toast-progress">
                <div class="toast-progress-bar" style="animation-duration: ${toast.duration}ms;"></div>
            </div>` : '';

        toastElement.innerHTML = `
            <div class="toast-content">
                <div class="toast-icon">${this.getIcon(toast.type)}</div>
                <div class="toast-message">${this.escapeHtml(toast.message)}</div>
                <button class="toast-close" onclick="toastManager.removeToast('${toast.id}')" aria-label="Close notification">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                </button>
            </div>
            ${progressBar}
        `;

        // Add click handler for action button if provided
        if (toast.action) {
            const actionButton = document.createElement('button');
            actionButton.className = 'toast-action';
            actionButton.textContent = toast.action.label;
            actionButton.onclick = () => {
                toast.action.callback();
                this.removeToast(toast.id);
            };
            toastElement.querySelector('.toast-content').appendChild(actionButton);
        }

        container.appendChild(toastElement);

        // Trigger animation
        setTimeout(() => {
            toastElement.classList.add('toast-show');
        }, 10);
    }

    /**
     * Get icon for toast type
     */
    getIcon(type) {
        const icons = {
            success: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="20,6 9,17 4,12"></polyline>
            </svg>`,
            error: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="15" y1="9" x2="9" y2="15"></line>
                <line x1="9" y1="9" x2="15" y2="15"></line>
            </svg>`,
            warning: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path>
                <line x1="12" y1="9" x2="12" y2="13"></line>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
            </svg>`,
            info: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"></circle>
                <line x1="12" y1="16" x2="12" y2="12"></line>
                <line x1="12" y1="8" x2="12.01" y2="8"></line>
            </svg>`,
            loading: `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="toast-spinner">
                <path d="M21 12a9 9 0 11-6.219-8.56"/>
            </svg>`
        };
        return icons[type] || icons.info;
    }

    /**
     * Generate unique ID
     */
    generateId() {
        return 'toast_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, function(m) { return map[m]; });
    }
}

// Create global toast manager instance
const toastManager = new ToastManager();

// Global convenience functions
window.showToast = (message, type, duration, options) => toastManager.show(message, type, duration, options);
window.showSuccess = (message, duration, options) => toastManager.success(message, duration, options);
window.showError = (message, duration, options) => toastManager.error(message, duration, options);
window.showWarning = (message, duration, options) => toastManager.warning(message, duration, options);
window.showInfo = (message, duration, options) => toastManager.info(message, duration, options);
window.showLoading = (message, options) => toastManager.loading(message, options);

// Additional aliases for legacy compatibility
window.showSuccessMessage = (message, duration, options) => toastManager.success(message, duration, options);
window.showErrorMessage = (message, duration, options) => toastManager.error(message, duration, options);
window.showWarningMessage = (message, duration, options) => toastManager.warning(message, duration, options);
window.showInfoMessage = (message, duration, options) => toastManager.info(message, duration, options);

// Toast notification aliases
window.showSuccessToast = (message, duration, options) => toastManager.success(message, duration, options);
window.showErrorToast = (message, duration, options) => toastManager.error(message, duration, options);
window.showWarningToast = (message, duration, options) => toastManager.warning(message, duration, options);
window.showInfoToast = (message, duration, options) => toastManager.info(message, duration, options);

// Utility function to replace common alert/confirm patterns
window.toastConfirm = (message, onConfirm, onCancel = null) => {
    return toastManager.show(message, 'warning', 0, {
        action: {
            label: 'Confirm',
            callback: onConfirm
        }
    });
};

// Override console methods to also show toasts for errors
const originalConsoleError = console.error;
console.error = function(...args) {
    originalConsoleError.apply(console, args);
    if (args.length > 0 && typeof args[0] === 'string') {
        toastManager.error(args[0]);
    }
};

// Export for modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { ToastManager, toastManager };
}