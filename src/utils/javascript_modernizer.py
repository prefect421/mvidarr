"""
JavaScript Modernization System - Issue 130 Template System Migration
Automated modernization of JavaScript files for FastAPI compatibility
"""

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logger import get_logger

logger = get_logger("mvidarr.utils.javascript_modernizer")


class JavaScriptModernizer:
    """Modernize JavaScript files for FastAPI compatibility"""

    def __init__(self):
        self.modernization_patterns = self._load_modernization_patterns()
        self.api_endpoint_mappings = self._load_api_mappings()
        self.modernization_stats = {
            "files_processed": 0,
            "patterns_applied": 0,
            "api_endpoints_updated": 0,
            "errors": [],
        }

    def _load_modernization_patterns(self) -> List[Dict[str, Any]]:
        """Load patterns for JavaScript modernization"""
        return [
            # jQuery to modern JavaScript
            {
                "name": "jquery_document_ready",
                "pattern": r"\$\(document\)\.ready\(function\(\)\s*\{",
                "replacement": 'document.addEventListener("DOMContentLoaded", function() {',
                "description": "Replace jQuery document ready with modern DOMContentLoaded",
            },
            {
                "name": "jquery_ajax_get",
                "pattern": r'\$\.get\(["\']([^"\']+)["\']\s*,\s*function\(([^)]*)\)\s*\{',
                "replacement": r'fetch("\1").then(response => response.json()).then(\2 => {',
                "description": "Replace jQuery $.get with fetch API",
            },
            {
                "name": "jquery_ajax_post",
                "pattern": r'\$\.post\(["\']([^"\']+)["\']\s*,\s*([^,]+)\s*,\s*function\(([^)]*)\)\s*\{',
                "replacement": r'fetch("\1", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(\2)}).then(response => response.json()).then(\3 => {',
                "description": "Replace jQuery $.post with fetch API",
            },
            {
                "name": "jquery_selector",
                "pattern": r'\$\(["\']([#\.][^"\']+)["\']\)',
                "replacement": r'document.querySelector("\1")',
                "description": "Replace jQuery selectors with querySelector",
            },
            {
                "name": "jquery_selector_all",
                "pattern": r'\$\(["\']([^#\.\["][^"\']*?)["\']\)',
                "replacement": r'document.querySelectorAll("\1")',
                "description": "Replace jQuery selectors with querySelectorAll",
            },
            # Callback patterns to async/await
            {
                "name": "callback_to_async",
                "pattern": r"function\s+(\w+)\([^)]*,\s*callback\)\s*\{",
                "replacement": r"async function \1(...args) {",
                "description": "Convert callback functions to async functions",
            },
            {
                "name": "promise_then_to_await",
                "pattern": r"\.then\(([^)]+)\s*=>\s*\{([^}]*)\}\)",
                "replacement": r";\nconst \1 = await previousPromise;\n\2",
                "description": "Convert promise chains to async/await",
            },
            # WebSocket patterns (Socket.IO to native WebSocket)
            {
                "name": "socketio_connect",
                "pattern": r"var\s+socket\s*=\s*io\(\);?",
                "replacement": "const socket = new WebSocket(`ws://${location.host}/ws/${generateClientId()}`);",
                "description": "Replace Socket.IO connection with native WebSocket",
            },
            {
                "name": "socketio_on",
                "pattern": r'socket\.on\(["\']([^"\']+)["\']\s*,\s*function\(([^)]*)\)\s*\{',
                "replacement": r'socket.addEventListener("message", function(event) {\n    const data = JSON.parse(event.data);\n    if (data.type === "\1") {\n        const \2 = data.data;',
                "description": "Replace Socket.IO event listeners with WebSocket message handlers",
            },
            {
                "name": "socketio_emit",
                "pattern": r'socket\.emit\(["\']([^"\']+)["\']\s*,\s*([^)]+)\);?',
                "replacement": r'socket.send(JSON.stringify({type: "\1", data: \2}));',
                "description": "Replace Socket.IO emit with WebSocket send",
            },
            # Modern ES6+ patterns
            {
                "name": "var_to_const",
                "pattern": r"var\s+(\w+)\s*=\s*([^;]+);",
                "replacement": r"const \1 = \2;",
                "description": "Replace var declarations with const",
            },
            {
                "name": "function_to_arrow",
                "pattern": r"function\s*\(([^)]*)\)\s*\{([^}]*)\}",
                "replacement": r"(\1) => {\2}",
                "description": "Convert function expressions to arrow functions",
            },
            {
                "name": "string_concatenation",
                "pattern": r'["\']([^"\']*)["\']\\s*\+\\s*([^+]+)\\s*\+\\s*["\']([^"\']*)["\']',
                "replacement": r"`\1${\2}\3`",
                "description": "Replace string concatenation with template literals",
            },
        ]

    def _load_api_mappings(self) -> Dict[str, str]:
        """Load API endpoint mappings from Flask to FastAPI"""
        return {
            # Frontend API endpoints
            "/api/videos": "/api/videos",
            "/api/artists": "/api/artists",
            "/api/playlists": "/api/playlists",
            "/api/settings": "/api/settings",
            "/api/admin": "/api/admin",
            # Authentication endpoints
            "/auth/login": "/api/auth/login",
            "/auth/logout": "/api/auth/logout",
            "/auth/2fa/setup": "/api/auth/2fa/setup",
            "/auth/2fa/verify": "/api/auth/2fa/verify",
            # Video operations
            "/videos/add": "/api/videos",
            "/videos/update": "/api/videos",
            "/videos/delete": "/api/videos",
            "/videos/search": "/api/search/videos",
            # Artist operations
            "/artists/add": "/api/artists",
            "/artists/update": "/api/artists",
            "/artists/search": "/api/search/artists",
            # Playlist operations
            "/playlists/create": "/api/playlists",
            "/playlists/update": "/api/playlists",
            "/playlists/add_video": "/api/playlists/{playlist_id}/videos",
            # Settings
            "/settings/update": "/api/settings",
            "/settings/get": "/api/settings",
            # Search
            "/search": "/api/search",
            "/search/universal": "/api/search/all",
            # Background jobs
            "/jobs/status": "/api/jobs/status",
            "/jobs/cancel": "/api/jobs/{job_id}/cancel",
            # Admin endpoints
            "/admin/users": "/api/admin/users",
            "/admin/system": "/api/admin/system",
        }

    def modernize_file(self, file_path: str) -> Tuple[bool, List[str]]:
        """Modernize a single JavaScript file"""
        changes = []

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            original_content = content

            # Apply modernization patterns
            for pattern_info in self.modernization_patterns:
                pattern = pattern_info["pattern"]
                replacement = pattern_info["replacement"]
                name = pattern_info["name"]

                matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
                if matches:
                    content = re.sub(
                        pattern, replacement, content, flags=re.MULTILINE | re.DOTALL
                    )
                    changes.append(f"Applied {name}: {len(matches)} replacements")
                    self.modernization_stats["patterns_applied"] += len(matches)

            # Update API endpoints
            api_changes = self._update_api_endpoints(content)
            content = api_changes["content"]
            changes.extend(api_changes["changes"])

            # Add modern JavaScript utilities if needed
            if self._needs_utilities(content):
                utility_code = self._generate_utility_code()
                content = utility_code + "\n\n" + content
                changes.append("Added modern JavaScript utilities")

            # Write modernized content back to file
            if content != original_content:
                # Create backup
                backup_path = f"{file_path}.backup"
                with open(backup_path, "w", encoding="utf-8") as f:
                    f.write(original_content)

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)

                changes.append(f"Backup created: {backup_path}")

            self.modernization_stats["files_processed"] += 1
            return True, changes

        except Exception as e:
            error_msg = f"Error modernizing {file_path}: {str(e)}"
            logger.error(error_msg)
            self.modernization_stats["errors"].append(error_msg)
            return False, [error_msg]

    def _update_api_endpoints(self, content: str) -> Dict[str, Any]:
        """Update API endpoints from Flask to FastAPI"""
        changes = []
        updated_content = content

        for old_endpoint, new_endpoint in self.api_endpoint_mappings.items():
            # Find API calls with the old endpoint
            patterns = [
                f"[\"'{old_endpoint}[\"']",  # Direct string references
                f'url_for\\(["\'][^"\']*{old_endpoint.split("/")[-1]}["\']\\)',  # Flask url_for calls
                f"fetch\\([\"'{old_endpoint}[\"']",  # Fetch calls
                f"\\.get\\([\"'{old_endpoint}[\"']",  # jQuery/axios get calls
                f"\\.post\\([\"'{old_endpoint}[\"']",  # jQuery/axios post calls
            ]

            for pattern in patterns:
                matches = re.findall(pattern, updated_content)
                if matches:
                    updated_content = re.sub(
                        pattern,
                        pattern.replace(old_endpoint, new_endpoint),
                        updated_content,
                    )
                    changes.append(
                        f"Updated API endpoint: {old_endpoint} -> {new_endpoint}"
                    )
                    self.modernization_stats["api_endpoints_updated"] += len(matches)

        return {"content": updated_content, "changes": changes}

    def _needs_utilities(self, content: str) -> bool:
        """Check if content needs modern JavaScript utilities"""
        utility_indicators = [
            "WebSocket",
            "fetch(",
            "async ",
            "await ",
            "generateClientId",
            "showToast",
            "updateLoadingState",
        ]

        return any(indicator in content for indicator in utility_indicators)

    def _generate_utility_code(self) -> str:
        """Generate modern JavaScript utility functions"""
        return """
// Modern JavaScript Utilities for MVidarr FastAPI Integration

// Generate unique client ID for WebSocket connections
function generateClientId() {
    return 'client_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

// Modern fetch wrapper with error handling
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin'
    };
    
    const config = { ...defaultOptions, ...options };
    
    try {
        const response = await fetch(url, config);
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return await response.json();
        }
        
        return await response.text();
    } catch (error) {
        console.error('API request failed:', error);
        throw error;
    }
}

// WebSocket connection manager
class WebSocketManager {
    constructor() {
        this.socket = null;
        this.clientId = generateClientId();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.messageHandlers = new Map();
    }
    
    connect() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/${this.clientId}`;
        
        this.socket = new WebSocket(wsUrl);
        
        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.reconnectAttempts = 0;
            this.onConnectionEstablished();
        };
        
        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        this.socket.onclose = () => {
            console.log('WebSocket disconnected');
            this.attemptReconnect();
        };
        
        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }
    
    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            setTimeout(() => {
                console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
                this.connect();
            }, Math.pow(2, this.reconnectAttempts) * 1000); // Exponential backoff
        }
    }
    
    send(type, data = null) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({ type, data }));
        } else {
            console.error('WebSocket not connected');
        }
    }
    
    subscribe(topic) {
        this.send('subscribe', { topic });
    }
    
    unsubscribe(topic) {
        this.send('unsubscribe', { topic });
    }
    
    onMessage(type, handler) {
        this.messageHandlers.set(type, handler);
    }
    
    handleMessage(data) {
        const handler = this.messageHandlers.get(data.type);
        if (handler) {
            handler(data.data);
        } else {
            console.log('Unhandled message type:', data.type, data);
        }
    }
    
    onConnectionEstablished() {
        // Auto-subscribe to common topics
        this.subscribe('job_updates');
        this.subscribe('notifications_info');
        this.subscribe('notifications_warning');
        this.subscribe('notifications_error');
    }
}

// Global WebSocket instance
const wsManager = new WebSocketManager();

// Toast notification system (compatible with existing toast.js)
function showToast(message, type = 'info', duration = 5000) {
    // Use existing toast system if available, otherwise create simple fallback
    if (typeof window.showToast === 'function') {
        return window.showToast(message, type, duration);
    }
    
    // Fallback implementation
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 12px 20px;
        border-radius: 4px;
        color: white;
        z-index: 10000;
        opacity: 0;
        transition: opacity 0.3s ease;
    `;
    
    // Set background color based on type
    const colors = {
        info: '#3b82f6',
        success: '#10b981',
        warning: '#f59e0b',
        error: '#ef4444'
    };
    toast.style.backgroundColor = colors[type] || colors.info;
    
    document.body.appendChild(toast);
    
    // Animate in
    requestAnimationFrame(() => {
        toast.style.opacity = '1';
    });
    
    // Remove after duration
    setTimeout(() => {
        toast.style.opacity = '0';
        setTimeout(() => {
            if (toast.parentNode) {
                toast.parentNode.removeChild(toast);
            }
        }, 300);
    }, duration);
}

// Loading state management
class LoadingManager {
    constructor() {
        this.activeOperations = new Set();
    }
    
    start(operationId) {
        this.activeOperations.add(operationId);
        this.updateGlobalLoadingState();
    }
    
    stop(operationId) {
        this.activeOperations.delete(operationId);
        this.updateGlobalLoadingState();
    }
    
    updateGlobalLoadingState() {
        const isLoading = this.activeOperations.size > 0;
        document.body.classList.toggle('loading', isLoading);
        
        // Update loading indicators
        const loadingIndicators = document.querySelectorAll('.loading-indicator');
        loadingIndicators.forEach(indicator => {
            indicator.style.display = isLoading ? 'block' : 'none';
        });
    }
}

const loadingManager = new LoadingManager();

// Initialize WebSocket connection when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    wsManager.connect();
    
    // Handle WebSocket messages
    wsManager.onMessage('notification', (data) => {
        showToast(data.message, data.type);
    });
    
    wsManager.onMessage('job_update', (data) => {
        console.log('Job update:', data);
        // Handle job updates (compatible with existing job dashboard)
        if (typeof window.handleJobUpdate === 'function') {
            window.handleJobUpdate(data);
        }
    });
});

// Export utilities for other scripts
window.MVidarr = {
    api: apiRequest,
    ws: wsManager,
    toast: showToast,
    loading: loadingManager,
    utils: {
        generateClientId
    }
};
"""

    def modernize_directory(
        self, directory_path: str, file_patterns: List[str] = None
    ) -> Dict[str, Any]:
        """Modernize all JavaScript files in a directory"""
        if file_patterns is None:
            file_patterns = ["*.js", "*.ts"]

        results = {
            "total_files": 0,
            "processed_files": 0,
            "failed_files": 0,
            "changes_summary": [],
            "errors": [],
        }

        directory = Path(directory_path)

        for pattern in file_patterns:
            for file_path in directory.rglob(pattern):
                results["total_files"] += 1

                success, changes = self.modernize_file(str(file_path))

                if success:
                    results["processed_files"] += 1
                    if changes:
                        results["changes_summary"].append(
                            {
                                "file": str(file_path.relative_to(directory)),
                                "changes": changes,
                            }
                        )
                else:
                    results["failed_files"] += 1
                    results["errors"].extend(changes)

        return results

    def generate_modernization_report(
        self, output_path: str = "javascript_modernization_report.json"
    ):
        """Generate comprehensive modernization report"""
        report = {
            "modernization_stats": self.modernization_stats,
            "patterns_available": [
                {"name": pattern["name"], "description": pattern["description"]}
                for pattern in self.modernization_patterns
            ],
            "api_mappings": self.api_endpoint_mappings,
            "timestamp": "2025-01-08T00:00:00Z",
        }

        with open(output_path, "w") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Modernization report saved to {output_path}")
        return report

    def create_modern_javascript_template(
        self, template_name: str, features: List[str] = None
    ) -> str:
        """Create a modern JavaScript template with specified features"""
        if features is None:
            features = ["api", "websocket", "toast", "loading"]

        template_code = f"""
/**
 * {template_name} - Modern JavaScript Module for MVidarr FastAPI
 * Generated by JavaScript Modernizer
 */

class {template_name.replace('_', '').title()} {{
    constructor() {{
        this.initialized = false;
    }}
    
    async initialize() {{
        if (this.initialized) return;
        
        try {{
"""

        if "websocket" in features:
            template_code += """
            // Subscribe to WebSocket topics
            if (window.MVidarr && window.MVidarr.ws) {
                window.MVidarr.ws.subscribe('relevant_topic');
                window.MVidarr.ws.onMessage('relevant_message', this.handleWebSocketMessage.bind(this));
            }
"""

        if "api" in features:
            template_code += """
            // Initialize API connections
            await this.loadInitialData();
"""

        template_code += """
            this.bindEvents();
            this.initialized = true;
            
        } catch (error) {
            console.error(`Error initializing ${template_name}:`, error);
        }
    }
"""

        if "api" in features:
            template_code += """
    
    async loadInitialData() {
        try {
            if (window.MVidarr && window.MVidarr.loading) {
                window.MVidarr.loading.start('initial_data');
            }
            
            const data = await window.MVidarr.api('/api/relevant-endpoint');
            this.processInitialData(data);
            
        } catch (error) {
            console.error('Error loading initial data:', error);
            if (window.MVidarr && window.MVidarr.toast) {
                window.MVidarr.toast('Failed to load data', 'error');
            }
        } finally {
            if (window.MVidarr && window.MVidarr.loading) {
                window.MVidarr.loading.stop('initial_data');
            }
        }
    }
    
    processInitialData(data) {
        // Process loaded data
        console.log('Initial data loaded:', data);
    }
"""

        if "websocket" in features:
            template_code += """
    
    handleWebSocketMessage(data) {
        console.log('WebSocket message received:', data);
        // Handle real-time updates
    }
"""

        template_code += (
            """
    
    bindEvents() {
        // Bind DOM events using modern event listeners
        document.addEventListener('click', this.handleClick.bind(this));
    }
    
    handleClick(event) {
        // Handle click events with event delegation
        const target = event.target.closest('[data-action]');
        if (!target) return;
        
        const action = target.dataset.action;
        this.handleAction(action, target, event);
    }
    
    async handleAction(action, element, event) {
        try {
            switch (action) {
                case 'example-action':
                    await this.performExampleAction(element);
                    break;
                default:
                    console.warn(`Unknown action: ${action}`);
            }
        } catch (error) {
            console.error(`Error handling action ${action}:`, error);
            if (window.MVidarr && window.MVidarr.toast) {
                window.MVidarr.toast(`Action failed: ${action}`, 'error');
            }
        }
    }
    
    async performExampleAction(element) {
        // Example async action
        console.log('Performing example action');
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', async function() {
    const instance = new """
            + template_name.replace("_", "").title()
            + """();
    await instance.initialize();
});
"""
        )

        return template_code


# Global modernizer instance
javascript_modernizer = JavaScriptModernizer()


def modernize_javascript_files(
    directory: str = "frontend/static", patterns: List[str] = None
) -> Dict[str, Any]:
    """Modernize JavaScript files in the specified directory"""
    return javascript_modernizer.modernize_directory(directory, patterns)


def generate_modern_template(name: str, features: List[str] = None) -> str:
    """Generate a modern JavaScript template"""
    return javascript_modernizer.create_modern_javascript_template(name, features)


def create_modernization_report(output_path: str = None) -> Dict[str, Any]:
    """Create a comprehensive modernization report"""
    return javascript_modernizer.generate_modernization_report(output_path)


if __name__ == "__main__":
    # Run modernization on the frontend directory
    import sys

    directory = sys.argv[1] if len(sys.argv) > 1 else "frontend/static"

    print(f"Modernizing JavaScript files in: {directory}")
    results = modernize_javascript_files(directory)

    print(
        f"Results: {results['processed_files']}/{results['total_files']} files processed"
    )

    if results["errors"]:
        print("Errors encountered:")
        for error in results["errors"]:
            print(f"  - {error}")

    # Generate report
    report = create_modernization_report()
    print(f"Modernization report saved")
