/**
 * Downloads Module
 * Handles download queue management and cleanup
 */

import { APIClient } from './api.js';
import { UIUtils } from './ui-utils.js';

export class DownloadsManager {
  constructor() {
    this.refreshInterval = null;
    this.showBadFiles = true;
  }

  /**
   * Load failed downloads and bad files
   */
  async loadFailedDownloads() {
    try {
      const response = await APIClient.authenticatedFetch(
        `/api/downloads/failed?include_bad=${this.showBadFiles}`
      );
      const data = await response.json();
      this.displayFailedDownloads(data);
    } catch (error) {
      console.error('[Downloads] Error loading failed downloads:', error);
      UIUtils.showStatus('downloads-status', 'Error loading failed downloads', 'error');
    }
  }

  /**
   * Display failed downloads and bad files
   */
  displayFailedDownloads(data) {
    const container = document.getElementById('failed-downloads-container');
    if (!container) return;

    let html = '<h3>Failed Downloads</h3>';

    // Bad files section (3+ failures)
    if (data.bad_files && data.bad_files.length > 0) {
      html += `
        <div style="background: var(--surface); border: 2px solid var(--status-failed); border-radius: 8px; padding: 15px; margin-bottom: 20px;">
          <h4 style="color: var(--status-failed); margin-top: 0;">🚫 Bad Files (${data.total_bad}) - Will Not Retry</h4>
          <p style="color: var(--text-secondary); font-size: 0.9em; margin-bottom: 15px;">
            These files have failed 3+ times and will not be attempted again.
          </p>
          <div style="display: flex; flex-direction: column; gap: 10px;">
      `;
      
      data.bad_files.forEach(file => {
        html += `
          <div style="padding: 10px; background: var(--background); border-left: 4px solid var(--status-failed); border-radius: 4px;">
            <div style="display: flex; justify-content: space-between; align-items: start; gap: 10px;">
              <div style="flex: 1;">
                <strong>${file.title}</strong>
                <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">
                  <div>❌ Attempts: ${file.attempt_count}</div>
                  <div>📝 Error: ${file.last_error}</div>
                  <div>🕐 Failed: ${new Date(file.failed_at).toLocaleString()}</div>
                </div>
              </div>
              <button onclick="deleteFailedDownload(${file.id})" class="btn-secondary" style="background: var(--status-failed);">
                🗑️ Remove
              </button>
            </div>
          </div>
        `;
      });
      
      html += '</div></div>';
    }

    // Recent failures section (1-2 attempts)
    if (data.failed_downloads && data.failed_downloads.length > 0) {
      html += `
        <div style="background: var(--surface); border: 1px solid var(--border-color); border-radius: 8px; padding: 15px;">
          <h4 style="margin-top: 0;">⚠️ Recent Failures (${data.total_failed}) - May Retry</h4>
          <div style="display: flex; flex-direction: column; gap: 10px;">
      `;
      
      data.failed_downloads.forEach(file => {
        html += `
          <div style="padding: 10px; background: var(--background); border-left: 4px solid orange; border-radius: 4px;">
            <div style="display: flex; justify-content: space-between; align-items: start; gap: 10px;">
              <div style="flex: 1;">
                <strong>${file.title}</strong>
                <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">
                  <div>🔄 Attempts: ${file.attempt_count}/3</div>
                  <div>📝 Error: ${file.last_error}</div>
                  <div>🕐 Failed: ${new Date(file.failed_at).toLocaleString()}</div>
                </div>
              </div>
              <button onclick="deleteFailedDownload(${file.id})" class="btn-secondary">
                🗑️ Remove
              </button>
            </div>
          </div>
        `;
      });
      
      html += '</div></div>';
    }

    if (data.total_failed === 0 && data.total_bad === 0) {
      html += '<p style="text-align: center; color: var(--text-secondary); padding: 40px;">No failed downloads</p>';
    }

    container.innerHTML = html;
  }

  /**
   * Delete a failed download
   */
  async deleteFailedDownload(submissionId) {
    if (!confirm('Remove this failed download from the database?')) return;
    
    try {
      const response = await APIClient.authenticatedFetch(
        `/api/downloads/failed/${submissionId}`,
        { method: 'DELETE' }
      );
      const data = await response.json();
      
      if (data.success) {
        UIUtils.showStatus('downloads-status', 'Failed download removed', 'success');
        this.loadFailedDownloads();
      } else {
        throw new Error(data.message || 'Failed to remove');
      }
    } catch (error) {
      console.error('[Downloads] Error deleting failed download:', error);
      UIUtils.showStatus('downloads-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Filter queue by status
   */
  filterQueue(status) {
    // Update active button state
    document.querySelectorAll('.sort-buttons .sort-btn[data-queue-filter]').forEach(btn => {
      btn.classList.remove('active');
    });
    const activeBtn = document.querySelector(`.sort-btn[data-queue-filter="${status}"]`);
    if (activeBtn) {
      activeBtn.classList.add('active');
    }
    
    this.loadDownloadQueue(status);
  }

  /**
   * Load download queue with optional filter
   */
  async loadDownloadQueue(statusFilter = '') {
    try {
      const filter = statusFilter || '';
      const url = filter 
        ? `/api/downloads/queue/all?status=${filter}`
        : '/api/downloads/queue/all';
      
      console.log('[Queue] Fetching from:', url);
      const response = await APIClient.authenticatedFetch(url);
      const data = await response.json();
      
      console.log('[Queue] API Response:', data);
      console.log('[Queue] Items in queue:', data.queue?.length || 0);
      console.log('[Queue] Status counts:', data.status_counts);
      if (data.queue?.length > 0) {
        data.queue.slice(0, 3).forEach((item, idx) => {
          console.log(`  [${idx}] ${item.title}: ${item.status} (${item.magazine})`);
        });
        if (data.queue.length > 3) console.log(`  ... and ${data.queue.length - 3} more`);
      }
      this.displayQueue(data);
    } catch (error) {
      console.error('[Queue] Error loading queue:', error);
    }
  }

  /**
   * Display queue data in table
   */
  displayQueue(data) {
    console.log('[Queue] displayQueue called');
    const emptyDiv = document.getElementById('queue-empty');
    const tableContainer = document.getElementById('queue-table-container');
    const tbody = document.getElementById('queue-body');
    const statsDiv = document.getElementById('queue-stats');
    
    // Get CSS variable colors
    const colors = {
      pending: getComputedStyle(document.documentElement).getPropertyValue('--status-pending').trim(),
      downloading: getComputedStyle(document.documentElement).getPropertyValue('--status-downloading').trim(),
      completed: getComputedStyle(document.documentElement).getPropertyValue('--status-completed').trim(),
      failed: getComputedStyle(document.documentElement).getPropertyValue('--status-failed').trim(),
      skipped: getComputedStyle(document.documentElement).getPropertyValue('--status-skipped').trim()
    };
    
    // Display status counts
    if (data.status_counts) {
      statsDiv.innerHTML = `
        <div style="display: flex; gap: 20px; flex-wrap: wrap;">
          <div><span style="font-weight: bold; color: ${colors.pending};">${data.status_counts.pending || 0}</span> Pending</div>
          <div><span style="font-weight: bold; color: ${colors.downloading};">${data.status_counts.downloading || 0}</span> Downloading</div>
          <div><span style="font-weight: bold; color: ${colors.completed};">${data.status_counts.completed || 0}</span> Completed</div>
          <div><span style="font-weight: bold; color: ${colors.failed};">${data.status_counts.failed || 0}</span> Failed</div>
          <div><span style="font-weight: bold; color: ${colors.skipped};">${data.status_counts.skipped || 0}</span> Skipped</div>
        </div>
      `;
    }
    
    if (data.queue.length === 0) {
      emptyDiv.classList.remove('hidden');
      tableContainer.classList.add('hidden');
      return;
    }
    
    emptyDiv.classList.add('hidden');
    tableContainer.classList.remove('hidden');
    tbody.innerHTML = '';
    
    const tableBorder = getComputedStyle(document.documentElement).getPropertyValue('--table-border').trim();
    const urlText = getComputedStyle(document.documentElement).getPropertyValue('--url-text').trim();
    
    data.queue.forEach((item, _idx) => {
      const row = document.createElement('tr');
      const statusColor = this.getStatusColor(item.status);
      const createdDate = new Date(item.created_at).toLocaleDateString();
      
      const displayTitle = item.title.length > 50 ? item.title.substring(0, 50) + '...' : item.title;
      
      row.innerHTML = `
        <td style="padding: 12px; border-bottom: 1px solid ${tableBorder}; max-width: 400px;">
          <strong title="${item.title}">${displayTitle}</strong>
          ${item.url ? `<br><small style="color: ${urlText};">${item.url.substring(0, 50)}...</small>` : ''}
        </td>
        <td style="padding: 12px; border-bottom: 1px solid ${tableBorder};">${item.magazine}</td>
        <td style="padding: 12px; border-bottom: 1px solid ${tableBorder}; text-align: center;">
          <span style="padding: 4px 12px; background: ${statusColor}; color: white; border-radius: 4px;">${item.status}</span>
          ${item.error ? `<br><small style="color: var(--error-color);">${item.error}</small>` : ''}
        </td>
        <td style="padding: 12px; border-bottom: 1px solid ${tableBorder};">${createdDate}</td>
        <td style="padding: 12px; border-bottom: 1px solid ${tableBorder}; text-align: center;">
          ${this.getQueueActionButtons(item)}
        </td>
      `;
      
      tbody.appendChild(row);
    });
  }

  /**
   * Get status color from CSS variables
   */
  getStatusColor(status) {
    const colors = {
      'completed': getComputedStyle(document.documentElement).getPropertyValue('--status-completed').trim(),
      'downloading': getComputedStyle(document.documentElement).getPropertyValue('--status-downloading').trim(),
      'pending': getComputedStyle(document.documentElement).getPropertyValue('--status-pending').trim(),
      'failed': getComputedStyle(document.documentElement).getPropertyValue('--status-failed').trim(),
      'skipped': getComputedStyle(document.documentElement).getPropertyValue('--status-skipped').trim()
    };
    return colors[status] || '#666';
  }

  /**
   * Get action buttons for queue item
   */
  getQueueActionButtons(item) {
    const pendingColor = getComputedStyle(document.documentElement).getPropertyValue('--status-pending').trim();
    const failedColor = getComputedStyle(document.documentElement).getPropertyValue('--status-failed').trim();
    
    let buttons = '';
    
    if (item.status === 'failed') {
      buttons += `<button onclick="retryDownload(${item.submission_id})" style="padding: 4px 8px; margin: 2px; background: ${pendingColor}; color: white; border: none; border-radius: 3px; cursor: pointer;">Retry</button>`;
    }
    
    buttons += `<button onclick="removeFromQueue(${item.submission_id})" style="padding: 4px 8px; margin: 2px; background: ${failedColor}; color: white; border: none; border-radius: 3px; cursor: pointer;">Remove</button>`;
    
    return buttons;
  }

  /**
   * Retry a failed download
   */
  async retryDownload(submissionId) {
    const confirmed = await UIUtils.confirm('Retry Download', 'Are you sure you want to retry this download?');
    if (!confirmed) return;

    try {
      const response = await APIClient.authenticatedFetch(`/api/downloads/queue/retry/${submissionId}`, {
        method: 'POST'
      });

      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('downloads-status', data.message, 'success');
        setTimeout(() => UIUtils.hideStatus('downloads-status'), 3000);
        this.loadDownloadQueue();
      } else {
        UIUtils.showStatus('downloads-status', data.message || 'Failed to retry', 'error');
      }
    } catch (error) {
      console.error('Error retrying download:', error);
      UIUtils.showStatus('downloads-status', error.message, 'error');
    }
  }

  /**
   * Remove a submission from queue
   */
  async removeFromQueue(submissionId) {
    const confirmed = await UIUtils.confirm('Remove Item', 'Are you sure you want to remove this item from the queue? This cannot be undone.');
    if (!confirmed) return;

    try {
      const response = await APIClient.authenticatedFetch(`/api/downloads/queue/${submissionId}`, {
        method: 'DELETE'
      });

      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('downloads-status', data.message, 'success');
        setTimeout(() => UIUtils.hideStatus('downloads-status'), 3000);
        this.loadDownloadQueue();
      } else {
        UIUtils.showStatus('downloads-status', data.message || 'Failed to remove', 'error');
      }
    } catch (error) {
      console.error('Error removing from queue:', error);
      UIUtils.showStatus('downloads-status', error.message, 'error');
    }
  }

  /**
   * Open cleanup modal
   */
  openCleanupModal() {
    UIUtils.showModal('cleanup-queue-modal');
  }

  /**
   * Close cleanup modal
   */
  closeCleanupModal() {
    UIUtils.closeModal('cleanup-queue-modal');
    const preview = document.getElementById('cleanup-preview');
    if (preview) {
      preview.style.display = 'none';
    }
  }

  /**
   * Preview cleanup (show what will be deleted)
   */
  async previewCleanup() {
    const status = document.getElementById('cleanup-status').value;
    const hours = parseInt(document.getElementById('cleanup-hours').value) || 24;
    
    try {
      const response = await APIClient.authenticatedFetch('/api/downloads/queue/all');
      const data = await response.json();
      
      let count = 0;
      data.queue.forEach(item => {
        const updatedTime = new Date(item.updated_at);
        const nowTime = new Date();
        const hoursDiff = (nowTime - updatedTime) / (1000 * 60 * 60);
        
        if (hoursDiff > hours) {
          if (!status || item.status === status) {
            count++;
          }
        }
      });
      
      const preview = document.getElementById('cleanup-preview');
      const countDiv = document.getElementById('cleanup-count');
      
      if (preview) preview.style.display = 'block';
      if (countDiv) countDiv.textContent = `${count} item${count !== 1 ? 's' : ''} older than ${hours} hours with status "${status || 'any'}"`;
    } catch (error) {
      console.error('Error previewing cleanup:', error);
    }
  }

  /**
   * Execute cleanup
   */
  async executeCleanup() {
    const status = document.getElementById('cleanup-status').value;
    const hours = parseInt(document.getElementById('cleanup-hours').value) || 24;

    try {
      const response = await APIClient.authenticatedFetch('/api/downloads/queue/cleanup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: status || undefined,
          older_than_hours: hours
        })
      });

      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('downloads-status', data.message, 'success');
        setTimeout(() => UIUtils.hideStatus('downloads-status'), 3000);
        this.closeCleanupModal();
        this.loadDownloadQueue();
      } else {
        UIUtils.showStatus('downloads-status', data.message || 'Cleanup failed', 'error');
      }
    } catch (error) {
      console.error('Error executing cleanup:', error);
      UIUtils.showStatus('downloads-status', error.message, 'error');
    }
  }

  /**
   * Start auto-refresh for the tasks tab
   */
  startAutoRefresh() {
    // Clear any existing interval
    this.stopAutoRefresh();
    
    // Auto-refresh every 10 seconds
    this.refreshInterval = setInterval(() => {
      const tasksTab = document.getElementById('tasks-tab');
      if (tasksTab && tasksTab.classList.contains('active')) {
        this.loadDownloadQueue();
      } else {
        this.stopAutoRefresh();
      }
    }, 10000);
  }

  /**
   * Stop auto-refresh
   */
  stopAutoRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }
}

// Create singleton instance
export const downloads = new DownloadsManager();

// Expose functions globally for onclick handlers
window.filterQueue = (status) => downloads.filterQueue(status);
window.retryDownload = (id) => downloads.retryDownload(id);
window.removeFromQueue = (id) => downloads.removeFromQueue(id);
window.deleteFailedDownload = (id) => downloads.deleteFailedDownload(id);
window.openCleanupModal = () => downloads.openCleanupModal();
window.closeCleanupModal = () => downloads.closeCleanupModal();
window.previewCleanup = () => downloads.previewCleanup();
window.executeCleanup = () => downloads.executeCleanup();

