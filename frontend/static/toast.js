/**
 * Toast Notification System for MVidarr Enhanced
 */

class ToastManager {
    constructor() {
        this.container = null;
        this.toasts = new Map();
        this.init();
    }

    init() {
        // Create toast container if it doesn't exist
        this.container = document.querySelector('.toast-container');
        if (!this.container) {
            this.container = document.createElement('div');
            this.container.className = 'toast-container';
            document.body.appendChild(this.container);
        }
    }

    show(message, options = {}) {
        const {
            type = 'info',
            title = null,
            duration = 5000,
            closable = true,
            icon = null
        } = options;

        const toastId = this.generateId();
        const toast = this.createToast(toastId, message, { type, title, closable, icon });
        
        this.container.appendChild(toast);
        this.toasts.set(toastId, toast);

        // Trigger animation
        setTimeout(() => {
            toast.classList.add('show');
        }, 10);

        // Auto-remove after duration
        if (duration > 0) {
            setTimeout(() => {
                this.remove(toastId);
            }, duration);
        }

        return toastId;
    }

    createToast(id, message, options) {
        const { type, title, closable, icon } = options;
        
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.dataset.toastId = id;

        const iconElement = this.getIcon(type, icon);
        const closeButton = closable ? '<button class="toast-close" onclick="toastManager.remove(\'' + id + '\')">&times;</button>' : '';

        toast.innerHTML = `
            <div class="toast-icon">${iconElement}</div>
            <div class="toast-content">
                ${title ? `<div class="toast-title">${sanitizeMessageHtml(title)}</div>` : ''}
                <div class="toast-message">${sanitizeMessageHtml(message)}</div>
            </div>
            ${closeButton}
        `;

        return toast;
    }

    getIcon(type, customIcon) {
        if (customIcon) return customIcon;
        
        const icons = {
            success: '✓',
            error: '✕',
            warning: '⚠',
            info: 'ℹ'
        };
        
        return icons[type] || icons.info;
    }

    remove(toastId) {
        const toast = this.toasts.get(toastId);
        if (!toast) return;

        toast.classList.remove('show');
        
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
            this.toasts.delete(toastId);
        }, 300);
    }

    removeAll() {
        this.toasts.forEach((_, id) => this.remove(id));
    }

    generateId() {
        return 'toast_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
    }

    // Convenience methods
    success(message, options = {}) {
        return this.show(message, { ...options, type: 'success' });
    }

    error(message, options = {}) {
        return this.show(message, { ...options, type: 'error' });
    }

    warning(message, options = {}) {
        return this.show(message, { ...options, type: 'warning' });
    }

    info(message, options = {}) {
        return this.show(message, { ...options, type: 'info' });
    }
}

// Create global instance
const toastManager = new ToastManager();

// Convenience functions for global access
function showToast(message, options = {}) {
    return toastManager.show(message, options);
}

function showSuccessToast(message, options = {}) {
    return toastManager.success(message, options);
}

function showErrorToast(message, options = {}) {
    return toastManager.error(message, options);
}

function showWarningToast(message, options = {}) {
    return toastManager.warning(message, options);
}

function showInfoToast(message, options = {}) {
    return toastManager.info(message, options);
}

// Confirmation dialog function
function toastConfirm(message, onConfirm, onCancel = null, options = {}) {
    const {
        confirmText = 'Confirm',
        cancelText = 'Cancel',
        type = 'warning',
        title = 'Confirmation Required'
    } = options;

    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.className = 'toast-confirm-overlay';
    overlay.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
        backdrop-filter: blur(3px);
        padding: 20px;
        box-sizing: border-box;
    `;

    // Create confirmation dialog
    const dialog = document.createElement('div');
    dialog.className = 'toast-confirm-dialog';
    dialog.style.cssText = `
        background: #2a2a2a;
        border: 1px solid #444;
        border-radius: 12px;
        padding: 2rem;
        width: 450px;
        max-width: 90vw;
        margin: 0 auto;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
        animation: confirmSlideIn 0.3s ease-out;
        position: relative;
    `;

    // Add animation keyframes
    if (!document.querySelector('#toast-confirm-styles')) {
        const style = document.createElement('style');
        style.id = 'toast-confirm-styles';
        style.textContent = `
            @keyframes confirmSlideIn {
                from {
                    transform: scale(0.9) translateY(-20px);
                    opacity: 0;
                }
                to {
                    transform: scale(1) translateY(0);
                    opacity: 1;
                }
            }
            
            .toast-confirm-dialog {
                box-sizing: border-box;
            }
            
            @media (max-width: 768px) {
                .toast-confirm-dialog {
                    width: 100% !important;
                    margin: 0 !important;
                    max-width: calc(100vw - 40px) !important;
                    padding: 1.5rem !important;
                }
                
                .confirm-actions {
                    flex-direction: column !important;
                    gap: 8px !important;
                }
                
                .confirm-actions button {
                    width: 100% !important;
                    justify-content: center !important;
                }
            }
        `;
        document.head.appendChild(style);
    }

    dialog.innerHTML = `
        <div class="confirm-header" style="margin-bottom: 1.5rem;">
            <h3 style="color: #fff; margin: 0; font-size: 1.2rem;">${sanitizeMessageHtml(title)}</h3>
        </div>
        <div class="confirm-message" style="margin-bottom: 2rem; color: #ccc; line-height: 1.5;">
            ${sanitizeMessageHtml(message)}
        </div>
        <div class="confirm-actions" style="display: flex; gap: 12px; justify-content: flex-end; align-items: center; margin-top: 1rem;">
            <button class="confirm-cancel" style="
                padding: 0.75rem 1.5rem;
                border: 1px solid #555;
                background: #333;
                color: #ccc;
                border-radius: 6px;
                cursor: pointer;
                transition: all 0.3s ease;
                font-size: 14px;
                min-width: 80px;
            ">${sanitizeMessageHtml(cancelText)}</button>
            <button class="confirm-ok" style="
                padding: 0.75rem 1.5rem;
                border: none;
                background: ${type === 'danger' ? '#dc3545' : '#00d4ff'};
                color: white;
                border-radius: 6px;
                cursor: pointer;
                font-weight: 600;
                transition: all 0.3s ease;
                font-size: 14px;
                min-width: 80px;
            ">${sanitizeMessageHtml(confirmText)}</button>
        </div>
    `;

    // Add hover effects
    const cancelBtn = dialog.querySelector('.confirm-cancel');
    const confirmBtn = dialog.querySelector('.confirm-ok');

    cancelBtn.addEventListener('mouseenter', () => {
        cancelBtn.style.background = '#444';
        cancelBtn.style.borderColor = '#666';
    });
    cancelBtn.addEventListener('mouseleave', () => {
        cancelBtn.style.background = '#333';
        cancelBtn.style.borderColor = '#555';
    });

    confirmBtn.addEventListener('mouseenter', () => {
        confirmBtn.style.transform = 'translateY(-1px)';
        confirmBtn.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.3)';
    });
    confirmBtn.addEventListener('mouseleave', () => {
        confirmBtn.style.transform = 'translateY(0)';
        confirmBtn.style.boxShadow = 'none';
    });

    // Event handlers
    const cleanup = () => {
        if (overlay && overlay.parentNode === document.body) {
            document.body.removeChild(overlay);
        }
        document.removeEventListener('keydown', handleEscape);
    };

    cancelBtn.addEventListener('click', () => {
        cleanup();
        if (onCancel) onCancel();
    });

    confirmBtn.addEventListener('click', () => {
        cleanup();
        if (onConfirm) onConfirm();
    });

    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) {
            cleanup();
            if (onCancel) onCancel();
        }
    });

    // Handle Escape key
    const handleEscape = (e) => {
        if (e.key === 'Escape') {
            cleanup();
            if (onCancel) onCancel();
        }
    };
    document.addEventListener('keydown', handleEscape);

    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    // Focus the confirm button
    setTimeout(() => confirmBtn.focus(), 100);
}

// Short aliases for convenience
function showSuccess(message, options = {}) {
    return toastManager.success(message, options);
}

function showError(message, options = {}) {
    return toastManager.error(message, options);
}

function showWarning(message, options = {}) {
    return toastManager.warning(message, options);
}

function showInfo(message, options = {}) {
    return toastManager.info(message, options);
}