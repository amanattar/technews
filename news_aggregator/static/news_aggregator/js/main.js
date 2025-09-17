// Main JavaScript functionality for TechNews Aggregator

// Global configuration
const APP_CONFIG = {
    apiBaseUrl: '/api',
    refreshInterval: 5 * 60 * 1000, // 5 minutes
    autoRefresh: true
};

// Utility functions
const Utils = {
    // Format date to relative time
    timeAgo: function(date) {
        const now = new Date();
        const diff = now - new Date(date);
        const seconds = Math.floor(diff / 1000);
        const minutes = Math.floor(seconds / 60);
        const hours = Math.floor(minutes / 60);
        const days = Math.floor(hours / 24);
        
        if (days > 0) return `${days} day${days !== 1 ? 's' : ''} ago`;
        if (hours > 0) return `${hours} hour${hours !== 1 ? 's' : ''} ago`;
        if (minutes > 0) return `${minutes} minute${minutes !== 1 ? 's' : ''} ago`;
        return 'Just now';
    },
    
    // Format number with commas
    formatNumber: function(num) {
        return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    },
    
    // Truncate text with ellipsis
    truncateText: function(text, maxLength) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength) + '...';
    },
    
    // Debounce function
    debounce: function(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },
    
    // Show loading spinner
    showLoading: function(element) {
        const spinner = `
            <div class="text-center p-4">
                <div class="spinner-custom mx-auto"></div>
                <div class="mt-2 text-muted">Loading...</div>
            </div>
        `;
        $(element).html(spinner);
    },
    
    // Show error message
    showError: function(element, message = 'An error occurred') {
        const errorHtml = `
            <div class="text-center p-4 text-muted">
                <i class="fas fa-exclamation-triangle fa-2x mb-2"></i>
                <div>${message}</div>
            </div>
        `;
        $(element).html(errorHtml);
    },
    
    // Generate random ID
    generateId: function() {
        return Math.random().toString(36).substr(2, 9);
    },
    
    // Copy text to clipboard
    copyToClipboard: function(text) {
        navigator.clipboard.writeText(text).then(() => {
            this.showToast('Copied to clipboard!', 'success');
        }).catch(() => {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            document.execCommand('copy');
            document.body.removeChild(textArea);
            this.showToast('Copied to clipboard!', 'success');
        });
    },
    
    // Show toast notification
    showToast: function(message, type = 'info', duration = 3000) {
        const toastId = this.generateId();
        const toast = `
            <div id="toast-${toastId}" class="toast align-items-center text-white bg-${type} border-0 position-fixed" 
                 style="top: 20px; right: 20px; z-index: 9999;" role="alert">
                <div class="d-flex">
                    <div class="toast-body">${message}</div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" 
                            onclick="Utils.hideToast('${toastId}')"></button>
                </div>
            </div>
        `;
        
        $('body').append(toast);
        $(`#toast-${toastId}`).addClass('show');
        
        setTimeout(() => {
            this.hideToast(toastId);
        }, duration);
    },
    
    // Hide toast notification
    hideToast: function(toastId) {
        $(`#toast-${toastId}`).removeClass('show');
        setTimeout(() => {
            $(`#toast-${toastId}`).remove();
        }, 300);
    }
};

// API wrapper
const API = {
    // Get CSRF token from cookies
    getCsrfToken: function() {
        return $('[name=csrfmiddlewaretoken]').val() || 
               document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
               $('meta[name=csrf-token]').attr('content');
    },
    
    // Generic GET request
    get: function(endpoint, params = {}) {
        return $.get(`${APP_CONFIG.apiBaseUrl}${endpoint}`, params);
    },
    
    // Generic POST request
    post: function(endpoint, data = {}) {
        return $.ajax({
            url: `${APP_CONFIG.apiBaseUrl}${endpoint}`,
            method: 'POST',
            data: JSON.stringify(data),
            contentType: 'application/json',
            headers: {
                'X-CSRFToken': this.getCsrfToken()
            }
        });
    },
    
    // Generic PUT request
    put: function(endpoint, data = {}) {
        return $.ajax({
            url: `${APP_CONFIG.apiBaseUrl}${endpoint}`,
            method: 'PUT',
            data: JSON.stringify(data),
            contentType: 'application/json',
            headers: {
                'X-CSRFToken': this.getCsrfToken()
            }
        });
    },
    
    // Generic DELETE request
    delete: function(endpoint) {
        return $.ajax({
            url: `${APP_CONFIG.apiBaseUrl}${endpoint}`,
            method: 'DELETE',
            headers: {
                'X-CSRFToken': this.getCsrfToken()
            }
        });
    },
    
    // Download file
    download: function(endpoint, data = {}, filename = 'download') {
        return $.ajax({
            url: `${APP_CONFIG.apiBaseUrl}${endpoint}`,
            method: 'POST',
            data: JSON.stringify(data),
            contentType: 'application/json',
            xhrFields: { responseType: 'blob' },
            success: function(data, status, xhr) {
                const blob = new Blob([data]);
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                
                // Get filename from response header or use default
                const contentDisposition = xhr.getResponseHeader('Content-Disposition');
                if (contentDisposition) {
                    const filenameMatch = contentDisposition.match(/filename="(.+)"/);
                    if (filenameMatch) {
                        filename = filenameMatch[1];
                    }
                }
                
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
            }
        });
    }
};

// Global action functions (called from templates)
function refreshNow() {
    Utils.showToast('Starting refresh...', 'info');
    API.post('/sources/scrape_all/')
        .done((data) => {
            Utils.showToast('Refresh completed successfully!', 'success');
            // Trigger a page reload or data refresh if on dashboard
            if (typeof loadDashboardData === 'function') {
                setTimeout(loadDashboardData, 2000);
            }
        })
        .fail((xhr) => {
            const errorMsg = xhr.responseJSON?.message || 'Failed to start refresh';
            Utils.showToast(errorMsg, 'danger');
        });
}

function runScanNow() {
    refreshNow(); // Same as refresh for now
}

function exportCSV() {
    $('#exportModal').modal('show');
}

// Initialize app when document is ready
$(document).ready(function() {
    // Update last update time
    updateLastUpdateTime();
    
    // Setup auto-refresh if enabled
    if (APP_CONFIG.autoRefresh) {
        setInterval(updateLastUpdateTime, APP_CONFIG.refreshInterval);
    }
    
    // Setup global AJAX error handler
    $(document).ajaxError(function(event, xhr, settings, thrownError) {
        if (xhr.status === 403) {
            Utils.showToast('Access denied', 'danger');
        } else if (xhr.status === 404) {
            Utils.showToast('Resource not found', 'warning');
        } else if (xhr.status >= 500) {
            Utils.showToast('Server error occurred', 'danger');
        }
    });
    
    // Setup tooltip initialization
    if (typeof bootstrap !== 'undefined') {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function(tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
    
    // Setup global keyboard shortcuts
    $(document).on('keydown', function(e) {
        // Ctrl/Cmd + R for refresh
        if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
            e.preventDefault();
            refreshNow();
        }
        
        // Ctrl/Cmd + E for export
        if ((e.ctrlKey || e.metaKey) && e.key === 'e') {
            e.preventDefault();
            exportCSV();
        }
        
        // Escape to close modals
        if (e.key === 'Escape') {
            $('.modal.show').modal('hide');
        }
    });
});

function updateLastUpdateTime() {
    const now = new Date();
    $('#last-update span').text(now.toLocaleTimeString());
}

// Priority helpers
const PriorityHelpers = {
    getLabelColor: function(label) {
        const colors = {
            'high': 'danger',
            'medium': 'warning', 
            'low': 'info',
            'minimal': 'secondary'
        };
        return colors[label] || 'secondary';
    },
    
    getLabelIcon: function(label) {
        const icons = {
            'high': 'fas fa-exclamation-triangle',
            'medium': 'fas fa-star',
            'low': 'fas fa-info-circle', 
            'minimal': 'fas fa-circle'
        };
        return icons[label] || 'fas fa-circle';
    },
    
    getLabelText: function(label) {
        const labels = {
            'high': 'High Priority',
            'medium': 'Medium Priority',
            'low': 'Low Priority',
            'minimal': 'Minimal Priority'
        };
        return labels[label] || 'Unknown Priority';
    },
    
    // Legacy score-based methods for backward compatibility
    getScoreColor: function(score) {
        if (score >= 20) return 'danger';
        if (score >= 10) return 'warning';
        if (score >= 5) return 'info';
        return 'secondary';
    },
    
    getScoreLabel: function(score) {
        if (score >= 20) return 'High';
        if (score >= 10) return 'Medium';
        if (score >= 5) return 'Low';
        return 'Minimal';
    },
    
    formatScore: function(score) {
        return parseFloat(score).toFixed(1);
    }
};

// Filter helpers
const FilterHelpers = {
    // Build query string from form
    buildQueryString: function(formSelector) {
        const formData = new FormData(document.querySelector(formSelector));
        const params = new URLSearchParams();
        
        for (let [key, value] of formData.entries()) {
            if (value) {
                params.append(key, value);
            }
        }
        
        return params.toString();
    },
    
    // Apply filters to URL
    updateUrlWithFilters: function(filters) {
        const url = new URL(window.location);
        url.search = new URLSearchParams(filters).toString();
        window.history.replaceState({}, '', url);
    },
    
    // Get filters from URL
    getFiltersFromUrl: function() {
        const params = new URLSearchParams(window.location.search);
        const filters = {};
        
        for (let [key, value] of params.entries()) {
            filters[key] = value;
        }
        
        return filters;
    }
};

// Local storage helpers
const StorageHelpers = {
    // Save user preferences
    savePreferences: function(key, data) {
        try {
            localStorage.setItem(`technews_${key}`, JSON.stringify(data));
        } catch (e) {
            console.warn('Failed to save preferences:', e);
        }
    },
    
    // Load user preferences
    loadPreferences: function(key, defaultValue = {}) {
        try {
            const data = localStorage.getItem(`technews_${key}`);
            return data ? JSON.parse(data) : defaultValue;
        } catch (e) {
            console.warn('Failed to load preferences:', e);
            return defaultValue;
        }
    },
    
    // Clear preferences
    clearPreferences: function(key) {
        try {
            localStorage.removeItem(`technews_${key}`);
        } catch (e) {
            console.warn('Failed to clear preferences:', e);
        }
    }
};

// Export utilities for use in other scripts
window.TechNewsApp = {
    Utils,
    API,
    PriorityHelpers,
    FilterHelpers,
    StorageHelpers,
    APP_CONFIG
};