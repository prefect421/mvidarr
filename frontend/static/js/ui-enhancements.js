/**
 * UI/UX Enhancement Package - JavaScript Components
 * Enhanced user interface components and interactions
 */

class UIEnhancements {
    constructor() {
        this.notificationContainer = null;
        this.modalStack = [];
        this.tooltips = new Map();
        
        this.init();
    }
    
    init() {
        this.createNotificationContainer();
        this.setupGlobalEventListeners();
        this.enhanceExistingElements();
        this.setupAccessibilityFeatures();
        this.initializeFormEnhancements();
    }
    
    // ========================================
    // NOTIFICATION SYSTEM
    // ========================================
    
    createNotificationContainer() {
        this.notificationContainer = document.createElement('div');
        this.notificationContainer.id = 'notification-container';
        this.notificationContainer.className = 'notification-container';
        this.notificationContainer.setAttribute('aria-live', 'polite');
        this.notificationContainer.setAttribute('aria-atomic', 'true');
        
        // Styles for notification container
        Object.assign(this.notificationContainer.style, {
            position: 'fixed',
            top: '1rem',
            right: '1rem',
            zIndex: '9999',
            maxWidth: '400px',
            pointerEvents: 'none'
        });
        
        document.body.appendChild(this.notificationContainer);
    }
    
    showNotification(options) {
        const {
            type = 'info',
            title,
            message,
            duration = 5000,
            actions = [],
            persistent = false
        } = options;
        
        const notification = this.createNotificationElement(type, title, message, actions, persistent);
        
        this.notificationContainer.appendChild(notification);
        
        // Animate in
        requestAnimationFrame(() => {
            notification.style.transform = 'translateX(0)';
            notification.style.opacity = '1';
        });
        
        // Auto-remove after duration (unless persistent)
        if (!persistent && duration > 0) {
            setTimeout(() => {
                this.removeNotification(notification);
            }, duration);
        }
        
        return notification;
    }
    
    createNotificationElement(type, title, message, actions, persistent) {
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.setAttribute('role', 'alert');
        
        // Base styles
        Object.assign(notification.style, {
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-primary)',
            borderRadius: 'var(--radius-lg)',
            padding: 'var(--space-4)',
            marginBottom: 'var(--space-3)',
            boxShadow: 'var(--shadow-lg)',
            transform: 'translateX(100%)',
            opacity: '0',
            transition: 'all 0.3s ease-out',
            pointerEvents: 'all',
            minWidth: '300px'
        });
        
        // Type-specific styling
        const typeStyles = {
            success: { borderLeftColor: 'var(--status-success)', borderLeftWidth: '4px' },
            warning: { borderLeftColor: 'var(--status-warning)', borderLeftWidth: '4px' },
            error: { borderLeftColor: 'var(--status-error)', borderLeftWidth: '4px' },
            info: { borderLeftColor: 'var(--status-info)', borderLeftWidth: '4px' }
        };
        
        Object.assign(notification.style, typeStyles[type] || typeStyles.info);
        
        // Icon
        const iconMap = {
            success: '✅',
            warning: '⚠️',
            error: '❌',
            info: 'ℹ️'
        };
        
        const html = `
            <div style="display: flex; align-items: flex-start; gap: var(--space-3);">
                <div style="font-size: 1.25rem; flex-shrink: 0;">
                    ${iconMap[type] || iconMap.info}
                </div>
                <div style="flex: 1; min-width: 0;">
                    ${title ? `<div style="font-weight: 600; margin-bottom: var(--space-1); color: var(--text-primary);">${this.escapeHtml(title)}</div>` : ''}
                    <div style="color: var(--text-secondary); font-size: var(--font-size-sm); line-height: var(--line-height-normal);">
                        ${this.escapeHtml(message)}
                    </div>
                    ${actions.length > 0 ? this.createNotificationActions(actions) : ''}
                </div>
                ${!persistent ? `
                    <button class="notification-close" aria-label="Close notification" style="
                        background: none;
                        border: none;
                        color: var(--text-muted);
                        cursor: pointer;
                        padding: var(--space-1);
                        border-radius: var(--radius-md);
                        flex-shrink: 0;
                        font-size: 1.25rem;
                        line-height: 1;
                        transition: all 0.15s ease;
                    ">×</button>
                ` : ''}
            </div>
        `;
        
        notification.innerHTML = html;
        
        // Close button event
        const closeBtn = notification.querySelector('.notification-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.removeNotification(notification));
            closeBtn.addEventListener('mouseenter', () => {
                closeBtn.style.color = 'var(--text-primary)';
                closeBtn.style.background = 'var(--bg-tertiary)';
            });
            closeBtn.addEventListener('mouseleave', () => {
                closeBtn.style.color = 'var(--text-muted)';
                closeBtn.style.background = 'none';
            });
        }
        
        return notification;
    }
    
    createNotificationActions(actions) {
        const actionsHtml = actions.map(action => {
            const btnClass = action.type === 'primary' ? 'btn-primary' : 'btn-ghost';
            return `
                <button 
                    class="btn btn-sm ${btnClass}" 
                    onclick="${action.onClick}"
                    style="margin-top: var(--space-2); margin-right: var(--space-2);"
                >
                    ${this.escapeHtml(action.label)}
                </button>
            `;
        }).join('');
        
        return `<div style="margin-top: var(--space-3);">${actionsHtml}</div>`;
    }
    
    removeNotification(notification) {
        notification.style.transform = 'translateX(100%)';
        notification.style.opacity = '0';
        
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }
    
    // ========================================
    // ENHANCED LOADING STATES
    // ========================================
    
    showLoadingOverlay(element, message = 'Loading...') {
        const overlay = document.createElement('div');
        overlay.className = 'loading-overlay';
        overlay.setAttribute('aria-label', message);
        
        Object.assign(overlay.style, {
            position: 'absolute',
            top: '0',
            left: '0',
            right: '0',
            bottom: '0',
            background: 'rgba(0, 0, 0, 0.5)',
            backdropFilter: 'blur(2px)',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 'var(--space-4)',
            zIndex: '999',
            borderRadius: 'inherit'
        });
        
        overlay.innerHTML = `
            <div class="loading-spinner loading-spinner-lg">
                <img src="/static/MVidarr.png" alt="MVidarr" class="spinning mvidarr-logo-spinner" style="width: 48px; height: 48px;">
            </div>
            <div style="color: white; font-size: var(--font-size-sm); font-weight: 500;">
                ${this.escapeHtml(message)}
            </div>
        `;
        
        // Ensure parent has position relative
        const parentPosition = window.getComputedStyle(element).position;
        if (parentPosition === 'static') {
            element.style.position = 'relative';
        }
        
        element.appendChild(overlay);
        return overlay;
    }
    
    hideLoadingOverlay(element) {
        const overlay = element.querySelector('.loading-overlay');
        if (overlay) {
            overlay.style.opacity = '0';
            setTimeout(() => {
                if (overlay.parentNode) {
                    overlay.parentNode.removeChild(overlay);
                }
            }, 200);
        }
    }
    
    setButtonLoading(button, loading = true, originalText = null) {
        if (loading) {
            if (!button.dataset.originalText) {
                button.dataset.originalText = button.textContent;
            }
            button.classList.add('btn-loading');
            button.disabled = true;
        } else {
            button.classList.remove('btn-loading');
            button.disabled = false;
            if (button.dataset.originalText) {
                button.textContent = button.dataset.originalText;
                delete button.dataset.originalText;
            }
        }
    }
    
    // ========================================
    // ENHANCED MODAL SYSTEM
    // ========================================
    
    showModal(options) {
        const {
            title,
            content,
            size = 'md',
            closable = true,
            actions = [],
            onClose
        } = options;
        
        const modal = this.createModalElement(title, content, size, closable, actions);
        
        document.body.appendChild(modal);
        this.modalStack.push({ modal, onClose });
        
        // Focus management
        const focusableElements = modal.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length > 0) {
            focusableElements[0].focus();
        }
        
        // Prevent body scrolling
        document.body.style.overflow = 'hidden';
        
        return modal;
    }
    
    createModalElement(title, content, size, closable, actions) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');
        if (title) {
            modal.setAttribute('aria-labelledby', 'modal-title');
        }
        
        const sizeClasses = {
            sm: 'max-width: 400px;',
            md: 'max-width: 600px;',
            lg: 'max-width: 800px;',
            xl: 'max-width: 1000px;',
            full: 'width: 90vw; height: 90vh;'
        };
        
        modal.innerHTML = `
            <div class="modal-container" style="${sizeClasses[size] || sizeClasses.md}">
                ${title ? `
                    <div class="modal-header">
                        <h2 id="modal-title" class="modal-title">${this.escapeHtml(title)}</h2>
                        ${closable ? `
                            <button class="modal-close" aria-label="Close modal">
                                <iconify-icon icon="tabler:x"></iconify-icon>
                            </button>
                        ` : ''}
                    </div>
                ` : ''}
                <div class="modal-body">${content}</div>
                ${actions.length > 0 ? `
                    <div class="modal-footer">
                        ${actions.map(action => `
                            <button class="btn ${action.type || 'btn-secondary'}" onclick="${action.onClick}">
                                ${this.escapeHtml(action.label)}
                            </button>
                        `).join('')}
                    </div>
                ` : ''}
            </div>
        `;
        
        // Close event handlers
        if (closable) {
            const closeBtn = modal.querySelector('.modal-close');
            if (closeBtn) {
                closeBtn.addEventListener('click', () => this.closeModal(modal));
            }
            
            // Close on overlay click
            modal.addEventListener('click', (e) => {
                if (e.target === modal) {
                    this.closeModal(modal);
                }
            });
            
            // Close on Escape key
            const handleEscape = (e) => {
                if (e.key === 'Escape') {
                    this.closeModal(modal);
                    document.removeEventListener('keydown', handleEscape);
                }
            };
            document.addEventListener('keydown', handleEscape);
        }
        
        return modal;
    }
    
    closeModal(modal) {
        const modalIndex = this.modalStack.findIndex(item => item.modal === modal);
        if (modalIndex !== -1) {
            const { onClose } = this.modalStack[modalIndex];
            this.modalStack.splice(modalIndex, 1);
            
            if (onClose) {
                onClose();
            }
        }
        
        modal.style.opacity = '0';
        setTimeout(() => {
            if (modal.parentNode) {
                modal.parentNode.removeChild(modal);
            }
        }, 200);
        
        // Restore body scrolling if no more modals
        if (this.modalStack.length === 0) {
            document.body.style.overflow = '';
        }
    }
    
    // ========================================
    // FORM ENHANCEMENTS
    // ========================================
    
    initializeFormEnhancements() {
        // Enhance all forms
        document.querySelectorAll('form').forEach(form => {
            this.enhanceForm(form);
        });
        
        // Auto-enhance new forms
        const observer = new MutationObserver(mutations => {
            mutations.forEach(mutation => {
                mutation.addedNodes.forEach(node => {
                    if (node.nodeType === Node.ELEMENT_NODE) {
                        if (node.tagName === 'FORM') {
                            this.enhanceForm(node);
                        }
                        node.querySelectorAll?.('form').forEach(form => {
                            this.enhanceForm(form);
                        });
                    }
                });
            });
        });
        
        observer.observe(document.body, { childList: true, subtree: true });
    }
    
    enhanceForm(form) {
        // Add form validation
        this.addFormValidation(form);
        
        // Add loading states to submit buttons
        this.enhanceSubmitButtons(form);
        
        // Add input enhancements
        this.enhanceInputs(form);
    }
    
    addFormValidation(form) {
        const inputs = form.querySelectorAll('input, select, textarea');
        
        inputs.forEach(input => {
            input.addEventListener('blur', () => {
                this.validateInput(input);
            });
            
            input.addEventListener('input', () => {
                // Clear error state on input
                this.clearInputError(input);
            });
        });
        
        form.addEventListener('submit', (e) => {
            let hasErrors = false;
            
            inputs.forEach(input => {
                if (!this.validateInput(input)) {
                    hasErrors = true;
                }
            });
            
            if (hasErrors) {
                e.preventDefault();
                this.showNotification({
                    type: 'error',
                    title: 'Form Validation Error',
                    message: 'Please correct the errors and try again.'
                });
            }
        });
    }
    
    validateInput(input) {
        const value = input.value.trim();
        let isValid = true;
        let errorMessage = '';
        
        // Required validation
        if (input.required && !value) {
            isValid = false;
            errorMessage = 'This field is required.';
        }
        
        // Type-specific validation
        if (value && input.type === 'email') {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            if (!emailRegex.test(value)) {
                isValid = false;
                errorMessage = 'Please enter a valid email address.';
            }
        }
        
        if (value && input.type === 'url') {
            try {
                new URL(value);
            } catch {
                isValid = false;
                errorMessage = 'Please enter a valid URL.';
            }
        }
        
        // Min/max length validation
        if (value && input.minLength && value.length < input.minLength) {
            isValid = false;
            errorMessage = `Minimum ${input.minLength} characters required.`;
        }
        
        if (value && input.maxLength && value.length > input.maxLength) {
            isValid = false;
            errorMessage = `Maximum ${input.maxLength} characters allowed.`;
        }
        
        // Update UI
        if (isValid) {
            this.clearInputError(input);
        } else {
            this.showInputError(input, errorMessage);
        }
        
        return isValid;
    }
    
    showInputError(input, message) {
        input.classList.add('error');
        
        let errorElement = input.parentNode.querySelector('.form-error');
        if (!errorElement) {
            errorElement = document.createElement('div');
            errorElement.className = 'form-error';
            input.parentNode.appendChild(errorElement);
        }
        
        errorElement.textContent = message;
        errorElement.setAttribute('role', 'alert');
    }
    
    clearInputError(input) {
        input.classList.remove('error');
        
        const errorElement = input.parentNode.querySelector('.form-error');
        if (errorElement) {
            errorElement.remove();
        }
    }
    
    enhanceSubmitButtons(form) {
        const submitButtons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
        
        form.addEventListener('submit', () => {
            submitButtons.forEach(button => {
                this.setButtonLoading(button, true);
            });
            
            // Reset loading state after 5 seconds as fallback
            setTimeout(() => {
                submitButtons.forEach(button => {
                    this.setButtonLoading(button, false);
                });
            }, 5000);
        });
    }
    
    enhanceInputs(form) {
        const inputs = form.querySelectorAll('input, select, textarea');
        
        inputs.forEach(input => {
            // Add floating labels
            if (!input.parentNode.querySelector('label') && input.placeholder) {
                this.addFloatingLabel(input);
            }
            
            // Add clear button to text inputs
            if (input.type === 'text' || input.type === 'email' || input.type === 'url') {
                this.addClearButton(input);
            }
        });
    }
    
    addFloatingLabel(input) {
        const wrapper = document.createElement('div');
        wrapper.className = 'input-wrapper';
        wrapper.style.position = 'relative';
        
        const label = document.createElement('label');
        label.textContent = input.placeholder;
        label.className = 'floating-label';
        
        Object.assign(label.style, {
            position: 'absolute',
            left: '1rem',
            top: '50%',
            transform: 'translateY(-50%)',
            color: 'var(--text-muted)',
            fontSize: 'var(--font-size-base)',
            pointerEvents: 'none',
            transition: 'all 0.2s ease',
            background: 'var(--bg-primary)',
            padding: '0 0.25rem'
        });
        
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);
        wrapper.appendChild(label);
        
        const updateLabel = () => {
            const hasValue = input.value.trim() !== '';
            const isFocused = document.activeElement === input;
            
            if (hasValue || isFocused) {
                Object.assign(label.style, {
                    top: '0',
                    fontSize: 'var(--font-size-sm)',
                    color: 'var(--text-primary)'
                });
            } else {
                Object.assign(label.style, {
                    top: '50%',
                    fontSize: 'var(--font-size-base)',
                    color: 'var(--text-muted)'
                });
            }
        };
        
        input.addEventListener('focus', updateLabel);
        input.addEventListener('blur', updateLabel);
        input.addEventListener('input', updateLabel);
        
        // Initial state
        updateLabel();
    }
    
    addClearButton(input) {
        if (input.parentNode.querySelector('.input-clear')) return;
        
        const clearBtn = document.createElement('button');
        clearBtn.type = 'button';
        clearBtn.className = 'input-clear';
        clearBtn.innerHTML = '×';
        clearBtn.setAttribute('aria-label', 'Clear input');
        
        Object.assign(clearBtn.style, {
            position: 'absolute',
            right: '0.75rem',
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'none',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            fontSize: '1.25rem',
            lineHeight: '1',
            padding: '0.25rem',
            borderRadius: 'var(--radius-sm)',
            opacity: '0',
            transition: 'all 0.2s ease'
        });
        
        // Ensure parent has position relative
        if (window.getComputedStyle(input.parentNode).position === 'static') {
            input.parentNode.style.position = 'relative';
        }
        
        input.parentNode.appendChild(clearBtn);
        
        const updateClearButton = () => {
            clearBtn.style.opacity = input.value ? '1' : '0';
        };
        
        input.addEventListener('input', updateClearButton);
        clearBtn.addEventListener('click', () => {
            input.value = '';
            input.focus();
            updateClearButton();
        });
        
        clearBtn.addEventListener('mouseenter', () => {
            clearBtn.style.color = 'var(--text-primary)';
            clearBtn.style.background = 'var(--bg-tertiary)';
        });
        
        clearBtn.addEventListener('mouseleave', () => {
            clearBtn.style.color = 'var(--text-muted)';
            clearBtn.style.background = 'none';
        });
        
        updateClearButton();
    }
    
    // ========================================
    // ACCESSIBILITY ENHANCEMENTS
    // ========================================
    
    setupAccessibilityFeatures() {
        // Add skip links
        this.addSkipLinks();
        
        // Enhance focus management
        this.enhanceFocusManagement();
        
        // Add keyboard navigation
        this.setupKeyboardNavigation();
        
        // Add ARIA labels where missing
        this.addAriaLabels();
    }
    
    addSkipLinks() {
        const skipLink = document.createElement('a');
        skipLink.href = '#main-content';
        skipLink.className = 'skip-link';
        skipLink.textContent = 'Skip to main content';
        
        document.body.insertBefore(skipLink, document.body.firstChild);
        
        // Ensure main content has proper ID
        const mainContent = document.querySelector('.main-content, main, #main-content');
        if (mainContent && !mainContent.id) {
            mainContent.id = 'main-content';
        }
    }
    
    enhanceFocusManagement() {
        // Add focus indicators
        const style = document.createElement('style');
        style.textContent = `
            .focus-visible:focus-visible {
                outline: 2px solid var(--status-info);
                outline-offset: 2px;
            }
        `;
        document.head.appendChild(style);
        
        // Add focus-visible class to elements
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                document.body.classList.add('using-keyboard');
            }
        });
        
        document.addEventListener('mousedown', () => {
            document.body.classList.remove('using-keyboard');
        });
    }
    
    setupKeyboardNavigation() {
        // Escape key to close modals
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && this.modalStack.length > 0) {
                const topModal = this.modalStack[this.modalStack.length - 1];
                this.closeModal(topModal.modal);
            }
        });
        
        // Arrow key navigation for lists
        document.addEventListener('keydown', (e) => {
            const focusedElement = document.activeElement;
            if (!focusedElement) return;
            
            const list = focusedElement.closest('[role="listbox"], [role="menu"], .video-grid, .artist-grid');
            if (!list) return;
            
            const items = list.querySelectorAll('[role="option"], [role="menuitem"], .video-card, .artist-card');
            const currentIndex = Array.from(items).indexOf(focusedElement);
            
            if (currentIndex === -1) return;
            
            let nextIndex;
            if (e.key === 'ArrowDown') {
                nextIndex = Math.min(currentIndex + 1, items.length - 1);
            } else if (e.key === 'ArrowUp') {
                nextIndex = Math.max(currentIndex - 1, 0);
            } else {
                return;
            }
            
            e.preventDefault();
            items[nextIndex].focus();
        });
    }
    
    addAriaLabels() {
        // Add labels to buttons without text
        document.querySelectorAll('button:not([aria-label])').forEach(button => {
            const iconElement = button.querySelector('iconify-icon, i, svg');
            if (iconElement && !button.textContent.trim()) {
                const icon = iconElement.getAttribute('icon') || iconElement.className;
                if (icon) {
                    button.setAttribute('aria-label', this.getAriaLabelFromIcon(icon));
                }
            }
        });
        
        // Add labels to form inputs without labels
        document.querySelectorAll('input:not([aria-label]):not([id])').forEach(input => {
            if (input.placeholder && !input.parentNode.querySelector('label')) {
                input.setAttribute('aria-label', input.placeholder);
            }
        });
    }
    
    getAriaLabelFromIcon(iconName) {
        const iconLabels = {
            'search': 'Search',
            'close': 'Close',
            'menu': 'Menu',
            'user': 'User',
            'settings': 'Settings',
            'delete': 'Delete',
            'download': 'Download',
            'play': 'Play',
            'pause': 'Pause',
            'refresh': 'Refresh'
        };
        
        for (const [key, label] of Object.entries(iconLabels)) {
            if (iconName.includes(key)) {
                return label;
            }
        }
        
        return 'Button';
    }
    
    // ========================================
    // UTILITY METHODS
    // ========================================
    
    setupGlobalEventListeners() {
        // Global error handling
        window.addEventListener('error', (e) => {
            console.error('Global error:', e.error);
            this.showNotification({
                type: 'error',
                title: 'Application Error',
                message: 'An unexpected error occurred. Please refresh the page if problems persist.'
            });
        });
        
        // Handle network status changes
        window.addEventListener('online', () => {
            this.showNotification({
                type: 'success',
                title: 'Connection Restored',
                message: 'You are back online.',
                duration: 3000
            });
        });
        
        window.addEventListener('offline', () => {
            this.showNotification({
                type: 'warning',
                title: 'Connection Lost',
                message: 'You are currently offline. Some features may not work.',
                persistent: true
            });
        });
    }
    
    enhanceExistingElements() {
        // Enhance existing buttons
        document.querySelectorAll('.btn:not(.enhanced)').forEach(button => {
            button.classList.add('enhanced');
            
            // Add ripple effect
            button.addEventListener('click', this.createRippleEffect.bind(this));
        });
        
        // Enhance existing forms
        document.querySelectorAll('form:not(.enhanced)').forEach(form => {
            form.classList.add('enhanced');
            this.enhanceForm(form);
        });
    }
    
    createRippleEffect(e) {
        const button = e.currentTarget;
        const rect = button.getBoundingClientRect();
        const ripple = document.createElement('span');
        
        const size = Math.max(rect.width, rect.height);
        const x = e.clientX - rect.left - size / 2;
        const y = e.clientY - rect.top - size / 2;
        
        Object.assign(ripple.style, {
            position: 'absolute',
            width: `${size}px`,
            height: `${size}px`,
            left: `${x}px`,
            top: `${y}px`,
            borderRadius: '50%',
            background: 'rgba(255, 255, 255, 0.5)',
            transform: 'scale(0)',
            animation: 'ripple 0.6s linear',
            pointerEvents: 'none'
        });
        
        button.style.position = 'relative';
        button.style.overflow = 'hidden';
        button.appendChild(ripple);
        
        setTimeout(() => {
            ripple.remove();
        }, 600);
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    // ========================================
    // PUBLIC API
    // ========================================
    
    // Notification shortcuts
    success(title, message, options = {}) {
        return this.showNotification({ type: 'success', title, message, ...options });
    }
    
    error(title, message, options = {}) {
        return this.showNotification({ type: 'error', title, message, ...options });
    }
    
    warning(title, message, options = {}) {
        return this.showNotification({ type: 'warning', title, message, ...options });
    }
    
    info(title, message, options = {}) {
        return this.showNotification({ type: 'info', title, message, ...options });
    }
    
    // Modal shortcuts
    confirm(title, message, onConfirm, onCancel) {
        return this.showModal({
            title,
            content: `<p>${this.escapeHtml(message)}</p>`,
            actions: [
                { label: 'Cancel', type: 'btn-secondary', onClick: `window.uiEnhancements.closeCurrentModal(); ${onCancel || ''}` },
                { label: 'Confirm', type: 'btn-primary', onClick: `window.uiEnhancements.closeCurrentModal(); ${onConfirm || ''}` }
            ]
        });
    }
    
    closeCurrentModal() {
        if (this.modalStack.length > 0) {
            const topModal = this.modalStack[this.modalStack.length - 1];
            this.closeModal(topModal.modal);
        }
    }
}

// Add ripple animation styles
const rippleStyles = document.createElement('style');
rippleStyles.textContent = `
    @keyframes ripple {
        to {
            transform: scale(4);
            opacity: 0;
        }
    }
`;
document.head.appendChild(rippleStyles);

// Initialize UI enhancements
const uiEnhancements = new UIEnhancements();

// Export for global access
window.uiEnhancements = uiEnhancements;

// Backward compatibility with existing toast system
window.showToast = function(message, type = 'info', title = null) {
    return uiEnhancements.showNotification({
        type,
        title,
        message
    });
};