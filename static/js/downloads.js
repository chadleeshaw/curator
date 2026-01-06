/**
 * Downloads Module
 * Handles download queue management and cleanup
 */

import { APIClient } from './api.js?v=1767725875';
import { UIUtils } from './ui-utils.js?v=1767725875';

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
   * Display failed downloads and bad files grouped by periodical
   */
  displayFailedDownloads(data) {
    const container = document.getElementById('failed-downloads-container');
    if (!container) return;

    // Group by periodical name (tracking_id)
    const grouped = this.groupDownloadsByPeriodical(data.failed_downloads, data.bad_files);

    let html = '';

    if (grouped.length === 0) {
      html = '<p style="text-align: center; color: var(--text-secondary); padding: 40px;">No failed downloads</p>';
      container.innerHTML = html;
      return;
    }

    // Display grouped by periodical
    html += '<div style="display: flex; flex-direction: column; gap: 15px;">';

    grouped.forEach((group) => {
      const hasBadFiles = group.badCount > 0;
      const icon = hasBadFiles ? '🚫' : '⚠️';

      html += `
        <div style="background: var(--surface); border-radius: 8px; padding: 12px; cursor: pointer; border-bottom: 2px solid var(--border-color);"
             onclick="downloads.openManageFailedModal('${group.periodical}', ${JSON.stringify(group.items).replace(/"/g, '&quot;')})">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div style="flex: 1;">
              <div style="display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 1.1em;">${icon} ${group.periodical}</span>
                <span style="font-size: 0.9em; color: var(--text-secondary);">${group.totalCount} issues</span>
              </div>
            </div>
            <div style="display: flex; gap: 10px; align-items: center;">
              ${group.failedCount > 0 ? `<span style="background: orange; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.85em;">${group.failedCount} failed</span>` : ''}
              ${hasBadFiles ? `<span style="background: var(--status-failed); color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.85em;">${group.badCount} bad</span>` : ''}
              <span style="font-size: 1.2em; color: var(--text-secondary);">→</span>
            </div>
          </div>
        </div>
      `;
    });

    html += '</div>';
    container.innerHTML = html;
  }

  /**
   * Group downloads by periodical name
   */
  groupDownloadsByPeriodical(failed, bad) {
    const map = new Map();

    // Process failed downloads
    failed.forEach((item) => {
      const key = item.magazine || 'Unknown';
      if (!map.has(key)) {
        map.set(key, { periodical: key, items: [], failedCount: 0, badCount: 0, totalCount: 0 });
      }
      const group = map.get(key);
      group.items.push({ ...item, isBad: false });
      group.failedCount++;
      group.totalCount++;
    });

    // Process bad files
    bad.forEach((item) => {
      const key = item.magazine || 'Unknown';
      if (!map.has(key)) {
        map.set(key, { periodical: key, items: [], failedCount: 0, badCount: 0, totalCount: 0 });
      }
      const group = map.get(key);
      group.items.push({ ...item, isBad: true });
      group.badCount++;
      group.totalCount++;
    });

    return Array.from(map.values()).sort((a, b) => b.totalCount - a.totalCount);
  }

  /**
   * Delete a failed download
   */
  async deleteFailedDownload(submissionId) {
    if (!confirm('Remove this failed download from the database?')) return;

    try {
      const response = await APIClient.authenticatedFetch(`/api/downloads/failed/${submissionId}`, {
        method: 'DELETE',
      });
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
   * Load download queue
   */
  async loadDownloadQueue() {
    try {
      const url = '/api/downloads/queue/all';

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
   * Display queue data grouped by periodical
   */
  displayQueue(data) {
    console.log('[Queue] displayQueue called');
    const emptyDiv = document.getElementById('queue-empty');
    const tableContainer = document.getElementById('queue-table-container');
    const tbody = document.getElementById('queue-body');
    const statsDiv = document.getElementById('queue-stats');

    // Get CSS variable colors
    const colors = {
      pending: getComputedStyle(document.documentElement)
        .getPropertyValue('--status-pending')
        .trim(),
      downloading: getComputedStyle(document.documentElement)
        .getPropertyValue('--status-downloading')
        .trim(),
      completed: getComputedStyle(document.documentElement)
        .getPropertyValue('--status-completed')
        .trim(),
      failed: getComputedStyle(document.documentElement).getPropertyValue('--status-failed').trim(),
      skipped: getComputedStyle(document.documentElement)
        .getPropertyValue('--status-skipped')
        .trim(),
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

    // Group by periodical
    const grouped = this.groupQueueByPeriodical(data.queue);
    
    tbody.innerHTML = '';
    grouped.forEach((group) => {
      // Create periodical header row
      const headerRow = document.createElement('tr');
      headerRow.style.background = 'var(--surface)';
      headerRow.style.cursor = 'pointer';
      headerRow.onclick = () => this.openManageQueueModal(group.periodical, group.items);
      
      const statusCounts = this.getStatusCounts(group.items);
      const statusBadges = Object.entries(statusCounts)
        .filter(([_, count]) => count > 0)
        .map(([status, count]) => {
          const color = this.getStatusColor(status);
          return `<span style="background: ${color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; margin-right: 5px;">${count} ${status}</span>`;
        })
        .join('');

      headerRow.innerHTML = `
        <td colspan="5" style="padding: 12px; font-weight: bold; border-bottom: 2px solid var(--border-color);">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <span style="font-size: 1.1em;">📰 ${group.periodical}</span>
              <span style="margin-left: 15px; font-size: 0.9em; color: var(--text-secondary);">${group.items.length} issues</span>
            </div>
            <div style="display: flex; gap: 10px; align-items: center;">
              ${statusBadges}
              <span style="font-size: 1.2em; color: var(--text-secondary);">→</span>
            </div>
          </div>
        </td>
      `;
      tbody.appendChild(headerRow);
    });
  }

  /**
   * Group queue items by periodical
   */
  groupQueueByPeriodical(queue) {
    const map = new Map();

    queue.forEach((item) => {
      const key = item.magazine || 'Unknown';
      if (!map.has(key)) {
        map.set(key, { periodical: key, items: [] });
      }
      map.get(key).items.push(item);
    });

    return Array.from(map.values()).sort((a, b) => b.items.length - a.items.length);
  }

  /**
   * Get status counts for items
   */
  getStatusCounts(items) {
    const counts = {};
    items.forEach((item) => {
      const status = item.status || 'unknown';
      counts[status] = (counts[status] || 0) + 1;
    });
    return counts;
  }

  /**
   * Get color for status
   */
  getStatusColor(status) {
    const colors = {
      pending: '#6c757d',
      downloading: '#0d6efd',
      processing: '#0dcaf0',
      completed: '#198754',
      failed: '#dc3545',
      paused: '#ffc107',
    };
    return colors[status] || '#6c757d';
  }

  /**
   * Get action buttons for queue item
   */
  getQueueActionButtons(item) {
    let buttons = '';
    
    if (item.status === 'failed') {
      buttons += `<button onclick="downloads.retryDownload(${item.submission_id})" class="btn-secondary" style="padding: 4px 8px; margin-right: 5px;">🔄 Retry</button>`;
    }
    
    if (item.status !== 'completed') {
      buttons += `<button onclick="downloads.deleteQueueItem(${item.submission_id})" class="btn-secondary" style="background: var(--status-failed); padding: 4px 8px;">Remove</button>`;
    }
    
    return buttons || '-';
  }

  /**
   * Open modal to manage queue for a periodical
   */
  openManageQueueModal(periodical, items) {
    // Store current items
    this.currentModalItems = items;
    this.currentModalPeriodical = periodical;
    this.currentModalFilter = 'all';

    this.renderManageQueueModal();
  }

  /**
   * Render the manage queue modal with current filter
   */
  renderManageQueueModal() {
    const items = this.currentModalItems;
    const periodical = this.currentModalPeriodical;
    const filter = this.currentModalFilter || 'all';

    // Filter items based on current filter
    const filteredItems = filter === 'all' ? items : items.filter(item => item.status === filter);

    const statusCounts = this.getStatusCounts(items);
    const statusList = Object.entries(statusCounts)
      .map(([status, count]) => `${count} ${status}`)
      .join(', ');

    let html = `
      <div class="modal-header">
        <h3>Manage Downloads: ${periodical}</h3>
        <p style="color: var(--text-secondary); margin-top: 10px;">${items.length} issues - ${statusList}</p>
        
        <div style="display: flex; gap: 5px; margin-top: 15px; flex-wrap: wrap;">
          <button onclick="downloads.filterModalQueue('all')" class="sort-btn ${filter === 'all' ? 'active' : ''}">All (${items.length})</button>
          <button onclick="downloads.filterModalQueue('pending')" class="sort-btn ${filter === 'pending' ? 'active' : ''}">Pending (${statusCounts.pending || 0})</button>
          <button onclick="downloads.filterModalQueue('downloading')" class="sort-btn ${filter === 'downloading' ? 'active' : ''}">Downloading (${statusCounts.downloading || 0})</button>
          <button onclick="downloads.filterModalQueue('completed')" class="sort-btn ${filter === 'completed' ? 'active' : ''}">Completed (${statusCounts.completed || 0})</button>
          <button onclick="downloads.filterModalQueue('failed')" class="sort-btn ${filter === 'failed' ? 'active' : ''}">Failed (${statusCounts.failed || 0})</button>
          <button onclick="downloads.filterModalQueue('skipped')" class="sort-btn ${filter === 'skipped' ? 'active' : ''}">Skipped (${statusCounts.skipped || 0})</button>
        </div>
      </div>
      
      <div class="modal-body" style="max-height: 400px; overflow-y: auto; margin: 20px 0;">
        <table style="width: 100%; border-collapse: collapse;">
          <thead style="position: sticky; top: 0; background: var(--surface); z-index: 1;">
            <tr>
              <th style="text-align: left; padding: 10px; border-bottom: 2px solid var(--border-color);">Issue</th>
              <th style="text-align: center; padding: 10px; border-bottom: 2px solid var(--border-color);">Status</th>
              <th style="text-align: center; padding: 10px; border-bottom: 2px solid var(--border-color);">Actions</th>
            </tr>
          </thead>
          <tbody>
    `;

    if (filteredItems.length === 0) {
      html += `
        <tr>
          <td colspan="3" style="padding: 40px; text-align: center; color: var(--text-secondary);">
            No ${filter === 'all' ? '' : filter} items found
          </td>
        </tr>
      `;
    } else {
      filteredItems.forEach((item) => {
        const statusColor = this.getStatusColor(item.status);
        html += `
          <tr>
            <td style="padding: 10px; border-bottom: 1px solid var(--border-color);">${item.title}</td>
            <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
              <span style="background: ${statusColor}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 0.85em;">${item.status}</span>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
              ${this.getQueueActionButtons(item)}
            </td>
          </tr>
        `;
      });
    }

    html += `
          </tbody>
        </table>
      </div>
      
      <div class="modal-footer" style="display: flex; gap: 10px; justify-content: space-between; padding-top: 20px; border-top: 1px solid var(--border-color);">
        <div>
          <button onclick="downloads.bulkRetryQueue()" class="btn-secondary">🔄 Retry Failed</button>
          <button onclick="downloads.bulkRemoveQueue()" class="btn-secondary" style="background: var(--status-failed);">🗑️ Remove All</button>
        </div>
        <button onclick="downloads.closeManageQueueModal()" class="save-btn">Close</button>
      </div>
    `;

    const container = document.getElementById('manage-queue-modal-content');
    if (container) {
      container.innerHTML = html;
      document.getElementById('manage-queue-modal').classList.remove('hidden');
    }
  }

  /**
   * Filter items in the manage queue modal
   */
  filterModalQueue(status) {
    this.currentModalFilter = status;
    this.renderManageQueueModal();
  }

  /**
   * Close manage queue modal
   */
  closeManageQueueModal() {
    document.getElementById('manage-queue-modal').classList.add('hidden');
    this.currentModalItems = null;
    this.currentModalPeriodical = null;
    this.currentModalFilter = 'all';
  }
  /**
   * Open modal to manage failed downloads for a periodical
   */
  openManageFailedModal(periodical, items) {
    // Parse items if it's a string
    if (typeof items === 'string') {
      try {
        items = JSON.parse(items.replace(/&quot;/g, '"'));
      } catch (e) {
        console.error('Error parsing items:', e);
        return;
      }
    }

    this.currentModalItems = items;
    this.currentModalPeriodical = periodical;

    const badCount = items.filter((i) => i.isBad).length;
    const failedCount = items.filter((i) => !i.isBad).length;

    let html = `
      <div class="modal-header">
        <h3>Manage Failed Downloads: ${periodical}</h3>
        <p style="color: var(--text-secondary); margin-top: 10px;">${failedCount} recent failures, ${badCount} bad files</p>
      </div>
      
      <div class="modal-body" style="max-height: 400px; overflow-y: auto; margin: 20px 0;">
        <table style="width: 100%; border-collapse: collapse;">
          <thead style="position: sticky; top: 0; background: var(--surface); z-index: 1;">
            <tr>
              <th style="text-align: left; padding: 10px; border-bottom: 2px solid var(--border-color);">Issue</th>
              <th style="text-align: center; padding: 10px; border-bottom: 2px solid var(--border-color);">Attempts</th>
              <th style="text-align: left; padding: 10px; border-bottom: 2px solid var(--border-color);">Error</th>
              <th style="text-align: center; padding: 10px; border-bottom: 2px solid var(--border-color);">Actions</th>
            </tr>
          </thead>
          <tbody>
    `;

    items.forEach((item) => {
      const color = item.isBad ? 'var(--status-failed)' : 'orange';
      html += `
        <tr>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color);">${item.title}</td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
            <span style="background: ${color}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 0.85em;">${item.attempt_count}/3</span>
          </td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); font-size: 0.85em;">${item.last_error || 'Unknown'}</td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
            <button onclick="downloads.deleteFailedDownload(${item.id})" class="btn-secondary" style="background: var(--status-failed); padding: 4px 8px;">Remove</button>
          </td>
        </tr>
      `;
    });

    html += `
          </tbody>
        </table>
      </div>
      
      <div class="modal-footer" style="display: flex; gap: 10px; justify-content: space-between; padding-top: 20px; border-top: 1px solid var(--border-color);">
        <button onclick="downloads.bulkRemoveFailed()" class="btn-secondary" style="background: var(--status-failed);">🗑️ Remove All</button>
        <button onclick="downloads.closeManageFailedModal()" class="save-btn">Close</button>
      </div>
    `;

    const container = document.getElementById('manage-failed-modal-content');
    if (container) {
      container.innerHTML = html;
      document.getElementById('manage-failed-modal').classList.remove('hidden');
    }
  }

  /**
   * Close manage failed modal
   */
  closeManageFailedModal() {
    document.getElementById('manage-failed-modal').classList.add('hidden');
    this.currentModalItems = null;
    this.currentModalPeriodical = null;
  }

  /**
   * Bulk retry failed downloads for current periodical
   */
  async bulkRetryQueue() {
    if (!this.currentModalItems) return;

    const failedItems = this.currentModalItems.filter((item) => item.status === 'failed');
    if (failedItems.length === 0) {
      UIUtils.showStatus('downloads-status', 'No failed items to retry', 'info');
      return;
    }

    if (!confirm(`Retry ${failedItems.length} failed downloads for ${this.currentModalPeriodical}?`))
      return;

    let succeeded = 0;
    for (const item of failedItems) {
      try {
        const response = await APIClient.authenticatedFetch(
          `/api/downloads/queue/retry/${item.submission_id}`,
          { method: 'POST' }
        );
        const data = await response.json();
        if (data.success) succeeded++;
      } catch (e) {
        console.error('Retry failed:', e);
      }
    }

    UIUtils.showStatus('downloads-status', `Retried ${succeeded} of ${failedItems.length} downloads`, 'success');
    this.closeManageQueueModal();
    this.loadDownloadQueue();
  }

  /**
   * Bulk remove all downloads for current periodical
   */
  async bulkRemoveQueue() {
    if (!this.currentModalItems) return;

    if (
      !confirm(
        `Remove ALL ${this.currentModalItems.length} downloads for ${this.currentModalPeriodical}? This cannot be undone.`
      )
    )
      return;

    let succeeded = 0;
    for (const item of this.currentModalItems) {
      try {
        const response = await APIClient.authenticatedFetch(
          `/api/downloads/queue/${item.submission_id}`,
          { method: 'DELETE' }
        );
        const data = await response.json();
        if (data.success) succeeded++;
      } catch (e) {
        console.error('Remove failed:', e);
      }
    }

    UIUtils.showStatus('downloads-status', `Removed ${succeeded} of ${this.currentModalItems.length} downloads`, 'success');
    this.closeManageQueueModal();
    this.loadDownloadQueue();
  }

  /**
   * Bulk remove all failed downloads for current periodical
   */
  async bulkRemoveFailed() {
    if (!this.currentModalItems) return;

    if (
      !confirm(
        `Remove ALL ${this.currentModalItems.length} failed downloads for ${this.currentModalPeriodical}? This cannot be undone.`
      )
    )
      return;

    let succeeded = 0;
    for (const item of this.currentModalItems) {
      try {
        const response = await APIClient.authenticatedFetch(`/api/downloads/failed/${item.id}`, {
          method: 'DELETE',
        });
        const data = await response.json();
        if (data.success) succeeded++;
      } catch (e) {
        console.error('Remove failed:', e);
      }
    }

    UIUtils.showStatus('downloads-status', `Removed ${succeeded} of ${this.currentModalItems.length} failed downloads`, 'success');
    this.closeManageFailedModal();
    this.loadFailedDownloads();
  }

  /**
   * Retry a failed download
   */
  async retryDownload(submissionId) {
    const confirmed = await UIUtils.confirm(
      'Retry Download',
      'Are you sure you want to retry this download?'
    );
    if (!confirmed) return;

    try {
      const response = await APIClient.authenticatedFetch(
        `/api/downloads/queue/retry/${submissionId}`,
        {
          method: 'POST',
        }
      );

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
    const confirmed = await UIUtils.confirm(
      'Remove Item',
      'Are you sure you want to remove this item from the queue? This cannot be undone.'
    );
    if (!confirmed) return;

    try {
      const response = await APIClient.authenticatedFetch(`/api/downloads/queue/${submissionId}`, {
        method: 'DELETE',
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
   * Alias for removeFromQueue (used by action buttons)
   */
  async deleteQueueItem(submissionId) {
    return this.removeFromQueue(submissionId);
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
      data.queue.forEach((item) => {
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
      if (countDiv)
        countDiv.textContent = `${count} item${count !== 1 ? 's' : ''} older than ${hours} hours with status "${status || 'any'}"`;
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
          older_than_hours: hours,
        }),
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

// Expose downloads object and functions globally for onclick handlers
window.downloads = downloads;
window.loadDownloadQueue = () => downloads.loadDownloadQueue();
window.retryDownload = (id) => downloads.retryDownload(id);
window.removeFromQueue = (id) => downloads.removeFromQueue(id);
window.deleteFailedDownload = (id) => downloads.deleteFailedDownload(id);
window.openCleanupModal = () => downloads.openCleanupModal();
window.closeCleanupModal = () => downloads.closeCleanupModal();
window.previewCleanup = () => downloads.previewCleanup();
window.executeCleanup = () => downloads.executeCleanup();

