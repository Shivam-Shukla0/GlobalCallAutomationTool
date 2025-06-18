// Dashboard JavaScript functionality
class CallAutomationDashboard {
    constructor() {
        this.updateInterval = null;
        this.isUpdating = false;
        this.init();
    }

    init() {
        this.startRealTimeUpdates();
        this.setupEventListeners();
        this.setupWebSocket();
    }

    setupEventListeners() {
        // Refresh button
        const refreshBtn = document.getElementById('refresh-logs');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshLogs());
        }

        // Auto-refresh toggle
        const autoRefreshToggle = document.getElementById('auto-refresh');
        if (autoRefreshToggle) {
            autoRefreshToggle.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.startRealTimeUpdates();
                } else {
                    this.stopRealTimeUpdates();
                }
            });
        }

        // Call response buttons
        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('call-response-btn')) {
                const callSid = e.target.dataset.callSid;
                const response = e.target.dataset.response;
                this.handleCallResponse(callSid, response);
            }
        });
    }

    setupWebSocket() {
        // WebSocket setup for real-time updates
        // Note: This would require WebSocket support on the backend
        try {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            
            // For now, we'll use polling instead of WebSocket
            // this.ws = new WebSocket(wsUrl);
            // this.ws.onmessage = (event) => this.handleWebSocketMessage(event);
        } catch (error) {
            console.log('WebSocket not available, using polling');
        }
    }

    startRealTimeUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
        }

        // Update every 5 seconds
        this.updateInterval = setInterval(() => {
            this.updateDashboard();
        }, 5000);

        // Initial update
        this.updateDashboard();
    }

    stopRealTimeUpdates() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    }

    async updateDashboard() {
        if (this.isUpdating) return;
        this.isUpdating = true;

        try {
            // Update queue status
            await this.updateQueueStatus();
            
            // Update recent calls
            await this.updateRecentCalls();
            
        } catch (error) {
            console.error('Error updating dashboard:', error);
        } finally {
            this.isUpdating = false;
        }
    }

    async updateQueueStatus() {
        try {
            const response = await fetch('/api/queue-status');
            const data = await response.json();

            // Update status cards
            this.updateStatusCard('total-calls', data.total_calls);
            this.updateStatusCard('not-called', data.not_called);
            this.updateStatusCard('connected', data.connected);
            this.updateStatusCard('accepted', data.accepted);
            this.updateStatusCard('forwarded', data.forwarded);
            this.updateStatusCard('failed', data.failed);

            // Update automation status
            this.updateAutomationStatus(data.is_running);

        } catch (error) {
            console.error('Error updating queue status:', error);
        }
    }

    async updateRecentCalls() {
        try {
            const response = await fetch('/api/recent-calls?limit=10');
            const calls = await response.json();

            const tableBody = document.getElementById('recent-calls-table');
            if (tableBody) {
                tableBody.innerHTML = this.renderRecentCallsTable(calls);
            }

        } catch (error) {
            console.error('Error updating recent calls:', error);
        }
    }

    updateStatusCard(elementId, value) {
        const element = document.getElementById(elementId);
        if (element) {
            const currentValue = parseInt(element.textContent);
            if (currentValue !== value) {
                element.textContent = value;
                element.parentElement.parentElement.classList.add('status-update');
                setTimeout(() => {
                    element.parentElement.parentElement.classList.remove('status-update');
                }, 1000);
            }
        }
    }

    updateAutomationStatus(isRunning) {
        const statusElement = document.getElementById('automation-status');
        if (statusElement) {
            statusElement.textContent = isRunning ? 'Running' : 'Stopped';
            statusElement.className = `badge bg-${isRunning ? 'success' : 'secondary'}`;
        }

        // Update status indicator
        const indicator = document.querySelector('.status-indicator');
        if (indicator) {
            indicator.className = `status-indicator ${isRunning ? 'running' : 'stopped'}`;
        }
    }

    renderRecentCallsTable(calls) {
        if (!calls || calls.length === 0) {
            return '<tr><td colspan="6" class="text-center text-muted">No call logs available</td></tr>';
        }

        return calls.map(call => `
            <tr>
                <td>${call.phone_number}</td>
                <td>${call.caller_name || '-'}</td>
                <td>
                    <span class="badge call-status-${call.call_status.toLowerCase()}">
                        ${call.call_status}
                    </span>
                </td>
                <td>${call.response || '-'}</td>
                <td>${call.duration ? call.duration + 's' : '-'}</td>
                <td>${this.formatDateTime(call.created_at)}</td>
            </tr>
        `).join('');
    }

    async refreshLogs() {
        const refreshBtn = document.getElementById('refresh-logs');
        if (refreshBtn) {
            const originalHTML = refreshBtn.innerHTML;
            refreshBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Refreshing...';
            refreshBtn.disabled = true;
        }

        try {
            await this.updateDashboard();
        } finally {
            if (refreshBtn) {
                refreshBtn.innerHTML = '<i class="fas fa-sync-alt"></i> Refresh';
                refreshBtn.disabled = false;
            }
        }
    }

    async handleCallResponse(callSid, response) {
        try {
            const result = await fetch('/api/call-response', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    call_id: callSid,
                    response: response
                })
            });

            const data = await result.json();

            if (data.success) {
                this.showToast(`Call marked as ${data.response}`, 'success');
                await this.updateDashboard();
            } else {
                this.showToast('Error: ' + data.error, 'error');
            }

        } catch (error) {
            console.error('Error handling call response:', error);
            this.showToast('Error processing request', 'error');
        }
    }

    showToast(message, type = 'info') {
        // Create toast notification
        const toastContainer = document.getElementById('toast-container') || this.createToastContainer();
        
        const toast = document.createElement('div');
        toast.className = `toast align-items-center text-white bg-${type === 'error' ? 'danger' : type} border-0`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        `;

        toastContainer.appendChild(toast);

        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();

        // Remove toast element after it's hidden
        toast.addEventListener('hidden.bs.toast', () => {
            toast.remove();
        });
    }

    createToastContainer() {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        container.style.zIndex = '1055';
        document.body.appendChild(container);
        return container;
    }

    formatDateTime(dateString) {
        if (!dateString) return '-';
        
        try {
            const date = new Date(dateString);
            return date.toLocaleString();
        } catch (error) {
            return dateString;
        }
    }

    formatDuration(seconds) {
        if (!seconds) return '-';
        
        const minutes = Math.floor(seconds / 60);
        const remainingSeconds = seconds % 60;
        
        if (minutes > 0) {
            return `${minutes}m ${remainingSeconds}s`;
        }
        return `${remainingSeconds}s`;
    }

    // Utility function to handle loading states
    setLoading(element, isLoading) {
        if (isLoading) {
            element.classList.add('loading');
        } else {
            element.classList.remove('loading');
        }
    }

    // Export functionality
    exportToCSV(data, filename) {
        const csv = this.convertToCSV(data);
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
    }

    convertToCSV(data) {
        if (!data || data.length === 0) return '';
        
        const headers = Object.keys(data[0]);
        const csvContent = [
            headers.join(','),
            ...data.map(row => 
                headers.map(header => 
                    JSON.stringify(row[header] || '')
                ).join(',')
            )
        ].join('\n');
        
        return csvContent;
    }
}

// Initialize dashboard when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    window.dashboard = new CallAutomationDashboard();
});

// Handle page visibility changes to pause/resume updates
document.addEventListener('visibilitychange', function() {
    if (window.dashboard) {
        if (document.hidden) {
            window.dashboard.stopRealTimeUpdates();
        } else {
            window.dashboard.startRealTimeUpdates();
        }
    }
});

// Cleanup on page unload
window.addEventListener('beforeunload', function() {
    if (window.dashboard) {
        window.dashboard.stopRealTimeUpdates();
    }
});
