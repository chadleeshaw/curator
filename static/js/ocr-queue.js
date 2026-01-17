/**
 * OCR Queue Module
 * Handles OCR job queue management and monitoring
 */

import { APIClient } from './api.js?v=1767733177';
import { UIUtils } from './ui-utils.js?v=1767733177';
import {
  ELEMENT_IDS as _ELEMENT_IDS,
  STATUS_MESSAGES as _STATUS_MESSAGES,
  CSS_CLASSES,
  TIMEOUTS as _TIMEOUTS,
} from './constants.js';

export class OCRQueueManager {
  constructor() {
    this.refreshInterval = null;
    /** @type {number} Maximum OCR retry attempts */
    this.maxRetries = 3; // Default value, will be loaded from API
    /** @type {string} Current filter (all, active, failed, completed) */
    this.currentFilter = 'active';

    // Load constants from API
    this.loadConstants();
  }

  /**
   * Load application constants from the API
   * @returns {Promise<void>}
   */
  async loadConstants() {
    try {
      const response = await APIClient.get('/api/constants');
      const data = await response.json();
      if (data.success && data.max_ocr_retries) {
        this.maxRetries = data.max_ocr_retries;
      }
    } catch (error) {
      console.warn('[OCR Queue] Failed to load constants, using defaults:', error);
    }
  }

  /**
   * Load OCR queue and stats
   */
  async loadQueue() {
    try {
      const [queueResponse, statsResponse] = await Promise.all([
        APIClient.authenticatedFetch('/api/ocr/queue'),
        APIClient.authenticatedFetch('/api/ocr/queue/stats'),
      ]);

      const queueData = await queueResponse.json();
      const statsData = await statsResponse.json();

      // Update badge count
      this.updateBadgeCount(statsData);

      // Display queue
      this.displayQueue(queueData, statsData);
    } catch (error) {
      console.error('[OCR Queue] Error loading queue:', error);
      UIUtils.showStatus('ocr-queue-status', 'Error loading OCR queue', 'error');
    }
  }

  /**
   * Update badge count in switcher button
   */
  updateBadgeCount(stats) {
    const badge = document.getElementById('ocr-queue-badge');
    if (badge) {
      const activeCount = (stats.pending || 0) + (stats.processing || 0);
      badge.textContent = activeCount;
    }
  }

  /**
   * Display queue data
   */
  displayQueue(queueData, statsData) {
    const emptyDiv = document.getElementById('ocr-queue-empty');
    const tableContainer = document.getElementById('ocr-queue-table-container');
    const tbody = document.getElementById('ocr-queue-body');
    const statsDiv = document.getElementById('ocr-queue-stats');

    // Get CSS variable colors
    const colors = {
      pending: getComputedStyle(document.documentElement)
        .getPropertyValue('--status-pending')
        .trim(),
      processing: getComputedStyle(document.documentElement)
        .getPropertyValue('--status-downloading')
        .trim(),
      completed: getComputedStyle(document.documentElement)
        .getPropertyValue('--status-completed')
        .trim(),
      failed: getComputedStyle(document.documentElement).getPropertyValue('--status-failed').trim(),
    };

    // Display stats
    if (statsData) {
      statsDiv.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 15px;">
          <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div class="ocr-stat-number" style="font-size: 1.5em; font-weight: bold; color: ${colors.pending};">${statsData.pending || 0}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">Pending</div>
          </div>
          <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div class="ocr-stat-number" style="font-size: 1.5em; font-weight: bold; color: ${colors.processing};">${statsData.processing || 0}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">Processing</div>
          </div>
          <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div class="ocr-stat-number" style="font-size: 1.5em; font-weight: bold; color: ${colors.completed};">${statsData.completed || 0}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">Completed</div>
          </div>
          <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div class="ocr-stat-number" style="font-size: 1.5em; font-weight: bold; color: ${colors.failed};">${statsData.failed || 0}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">Failed</div>
          </div>
        </div>
      `;
    }

    // Filter jobs based on current filter
    let filteredJobs = queueData.jobs;
    if (this.currentFilter === 'active') {
      filteredJobs = queueData.jobs.filter(
        (job) => job.status === 'pending' || job.status === 'processing'
      );
    } else if (this.currentFilter === 'failed') {
      filteredJobs = queueData.jobs.filter((job) => job.status === 'failed');
    } else if (this.currentFilter === 'completed') {
      filteredJobs = queueData.jobs.filter((job) => job.status === 'completed');
    }
    // 'all' filter shows everything

    if (filteredJobs.length === 0) {
      emptyDiv.classList.remove(CSS_CLASSES.HIDDEN);
      tableContainer.classList.add(CSS_CLASSES.HIDDEN);

      // Update empty message based on filter
      const emptyMessage = emptyDiv.querySelector('p:first-of-type');
      if (emptyMessage) {
        const messages = {
          all: 'No OCR jobs in queue',
          active: 'No active OCR jobs',
          failed: 'No failed OCR jobs',
          completed: 'No completed OCR jobs',
        };
        emptyMessage.textContent = messages[this.currentFilter] || 'No OCR jobs in queue';
      }
      return;
    }

    emptyDiv.classList.add(CSS_CLASSES.HIDDEN);
    tableContainer.classList.remove(CSS_CLASSES.HIDDEN);

    // Build table rows
    tbody.innerHTML = '';
    filteredJobs.forEach((job) => {
      const row = document.createElement('tr');
      row.style.borderBottom = '1px solid var(--border)';

      // Periodical title
      const titleCell = document.createElement('td');
      titleCell.style.padding = '12px';
      titleCell.innerHTML = `
        <div style="font-weight: 600;">${job.magazine_title || 'Unknown'}</div>
        <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 2px;">
          ${job.magazine_issue ? `Issue ${job.magazine_issue}` : ''} ${job.magazine_year ? `(${job.magazine_year})` : ''}
        </div>
      `;
      row.appendChild(titleCell);

      // Status with additional info
      const statusCell = document.createElement('td');
      statusCell.style.padding = '12px';
      statusCell.style.textAlign = 'center';

      let statusContent = this.getStatusBadge(job.status);

      // Add additional context based on status (but not for processing since badge already says it)
      if (job.status === 'failed' && job.attempt_count) {
        statusContent += `<div style="font-size: 0.8em; color: var(--text-secondary); margin-top: 4px;">Attempt ${job.attempt_count}/${this.maxRetries}</div>`;
      } else if (job.status === 'completed' && job.processing_time_seconds) {
        statusContent += `<div style="font-size: 0.8em; color: var(--text-secondary); margin-top: 4px;">${job.processing_time_seconds}s</div>`;
      }

      statusCell.innerHTML = statusContent;
      row.appendChild(statusCell);

      // Priority
      const priorityCell = document.createElement('td');
      priorityCell.style.padding = '12px';
      priorityCell.style.textAlign = 'center';
      priorityCell.innerHTML = this.getPriorityBadge(job.priority);
      row.appendChild(priorityCell);

      // Actions
      const actionsCell = document.createElement('td');
      actionsCell.style.padding = '12px';
      actionsCell.style.textAlign = 'right';

      // Retry button for failed jobs
      if (job.status === 'failed') {
        const retryBtn = document.createElement('button');
        retryBtn.className = 'action-btn';
        retryBtn.textContent = '🔄 Retry';
        retryBtn.title = 'Retry this job';
        retryBtn.style.cssText =
          'background: var(--primary); color: white; padding: 6px 12px; border-radius: 4px; border: none; cursor: pointer; margin-right: 5px;';
        retryBtn.addEventListener('click', () => this.retryJob(job.id));
        actionsCell.appendChild(retryBtn);
      }

      // Delete button for all jobs
      const deleteTitle =
        job.status === 'processing' ? 'Cancel OCR processing' : 'Remove from queue';
      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'action-btn';
      deleteBtn.textContent = '🗑️';
      deleteBtn.title = deleteTitle;
      deleteBtn.style.cssText =
        'background: var(--surface-variant); color: var(--status-failed); padding: 6px 12px; border-radius: 4px; border: 1px solid var(--border); cursor: pointer;';
      deleteBtn.addEventListener('click', () => this.deleteJob(job.id, job.magazine_title));

      // Also add info button if there's an error
      if (job.last_error) {
        const infoBtn = document.createElement('button');
        infoBtn.className = 'action-btn';
        infoBtn.textContent = 'ℹ️ Info';
        infoBtn.title = 'View error details';
        infoBtn.style.cssText =
          'background: var(--surface-variant); padding: 6px 12px; border-radius: 4px; border: 1px solid var(--border); cursor: pointer; margin-right: 5px;';
        infoBtn.addEventListener('click', () => this.showError(job.magazine_title, job.last_error));
        actionsCell.appendChild(infoBtn);
      }

      actionsCell.appendChild(deleteBtn);
      row.appendChild(actionsCell);

      tbody.appendChild(row);
    });
  }

  /**
   * Get status badge HTML
   */
  getStatusBadge(status) {
    const badges = {
      pending:
        '<span style="background: var(--status-pending); color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.85em;">⏱️ Pending</span>',
      processing:
        '<span style="background: var(--status-downloading); color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.85em;">⚡ Processing</span>',
      completed:
        '<span style="background: var(--status-completed); color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.85em;">✅ Done</span>',
      failed:
        '<span style="background: var(--status-failed); color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.85em;">❌ Failed</span>',
    };
    return badges[status] || status;
  }

  /**
   * Get priority badge HTML
   */
  getPriorityBadge(priority) {
    if (priority >= 10) {
      return '<span style="color: var(--status-failed); font-weight: bold;">🔥 High</span>';
    } else if (priority >= 5) {
      return '<span style="color: var(--text-primary);">⚡ Normal</span>';
    } else {
      return '<span style="color: var(--text-secondary);">💤 Low</span>';
    }
  }

  /**
   * Retry a failed OCR job
   */
  async retryJob(jobId) {
    try {
      const response = await APIClient.authenticatedFetch(`/api/ocr/retry/${jobId}`, {
        method: 'POST',
      });

      if (response.ok) {
        UIUtils.showToast('OCR job queued for retry', 'success');
        await this.loadQueue();
      } else {
        const error = await response.json();
        UIUtils.showToast(error.detail || 'Failed to retry job', 'error');
      }
    } catch (error) {
      console.error('[OCR Queue] Error retrying job:', error);
      UIUtils.showToast('Error retrying job', 'error');
    }
  }

  /**
   * Show confirmation modal for deleting a job
   */
  showDeleteConfirmation(jobId, jobTitle) {
    const modal = document.createElement('div');
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0,0,0,0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10000;
    `;

    const modalContent = document.createElement('div');
    modalContent.style.cssText =
      'background: var(--surface); border-radius: 8px; padding: 24px; max-width: 500px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.3);';

    modalContent.innerHTML = `
      <h3 style="margin: 0 0 16px 0; color: var(--text-primary);">⚠️ Remove OCR Job</h3>
      <p style="margin: 0 0 12px 0; color: var(--text-secondary);">Are you sure you want to remove this OCR job from the queue?</p>
      <p style="margin: 0 0 20px 0; color: var(--text-primary); font-weight: 600;">${jobTitle}</p>
      <div style="display: flex; gap: 10px; justify-content: flex-end;"></div>
    `;

    const buttonContainer = modalContent.querySelector('div[style*="display: flex"]');

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    cancelBtn.style.cssText =
      'background: var(--surface-variant); color: var(--text-primary); padding: 8px 16px; border-radius: 4px; border: 1px solid var(--border); cursor: pointer;';
    cancelBtn.addEventListener('click', () => modal.remove());

    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = 'Delete';
    deleteBtn.style.cssText =
      'background: var(--status-failed); color: white; padding: 8px 16px; border-radius: 4px; border: none; cursor: pointer;';
    deleteBtn.addEventListener('click', () => {
      this.confirmDelete(jobId);
      modal.remove();
    });

    buttonContainer.appendChild(cancelBtn);
    buttonContainer.appendChild(deleteBtn);
    modal.appendChild(modalContent);

    modal.addEventListener('click', (e) => {
      if (e.target === modal) modal.remove();
    });

    document.body.appendChild(modal);
  }

  /**
   * Confirm and execute delete
   */
  async confirmDelete(jobId) {
    try {
      const response = await APIClient.authenticatedFetch(`/api/ocr/queue/${jobId}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        UIUtils.showToast('OCR job removed', 'success');
        await this.loadQueue();
      } else {
        const error = await response.json();
        UIUtils.showToast(error.detail || 'Failed to delete job', 'error');
      }
    } catch (error) {
      console.error('[OCR Queue] Error deleting job:', error);
      UIUtils.showToast('Error deleting job', 'error');
    }
  }

  /**
   * Delete an OCR job (shows confirmation modal)
   */
  deleteJob(jobId, jobTitle = 'Unknown Job') {
    this.showDeleteConfirmation(jobId, jobTitle);
  }

  /**
   * Show error details modal
   */
  showError(title, errorMessage) {
    const modal = document.createElement('div');
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0,0,0,0.5);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10000;
    `;

    modal.innerHTML = `
      <div style="background: var(--surface); border-radius: 8px; padding: 24px; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto; box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
        <h3 style="margin: 0 0 16px 0; color: var(--status-failed);">❌ OCR Error Details</h3>
        <p style="font-weight: 600; margin-bottom: 12px;">${title}</p>
        <pre style="background: var(--surface-variant); padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 0.9em; color: var(--text-secondary);">${errorMessage}</pre>
        <button
          id="close-error-modal"
          style="margin-top: 16px; background: var(--primary); color: white; padding: 8px 16px; border-radius: 4px; border: none; cursor: pointer; float: right;">
          Close
        </button>
      </div>
    `;

    // Add click handler for close button
    const closeBtn = modal.querySelector('#close-error-modal');
    closeBtn.addEventListener('click', () => modal.remove());

    // Close modal when clicking outside
    modal.onclick = (e) => {
      if (e.target === modal) modal.remove();
    };

    document.body.appendChild(modal);
  }

  /**
   * Start auto-refresh
   */
  startAutoRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
    }
    // Refresh every 5 seconds
    this.refreshInterval = setInterval(() => this.loadQueue(), 5000);
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

  /**
   * Set filter and reload queue
   * @param {string} filter - Filter type (all, active, failed, completed)
   */
  setFilter(filter) {
    this.currentFilter = filter;

    // Update button states
    document.querySelectorAll('.filter-btn').forEach((btn) => {
      btn.classList.remove('active');
    });
    const activeBtn = document.getElementById(`ocr-filter-${filter}`);
    if (activeBtn) {
      activeBtn.classList.add('active');
    }

    // Reload queue with new filter
    this.loadQueue();
  }

  /**
   * Clear all failed OCR jobs
   */
  async clearFailedJobs() {
    try {
      // Show confirmation modal
      const modal = document.createElement('div');
      modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 10000;
      `;

      const modalContent = document.createElement('div');
      modalContent.style.cssText =
        'background: var(--surface); border-radius: 8px; padding: 24px; max-width: 500px; width: 90%; box-shadow: 0 4px 20px rgba(0,0,0,0.3);';

      modalContent.innerHTML = `
        <h3 style="margin: 0 0 16px 0; color: var(--text-primary);">⚠️ Clear All Failed Jobs</h3>
        <p style="margin: 0 0 12px 0; color: var(--text-secondary);">Are you sure you want to remove all failed OCR jobs from the queue?</p>
        <p style="margin: 0 0 20px 0; color: var(--status-failed); font-weight: 600;">This action cannot be undone.</p>
        <div style="display: flex; gap: 10px; justify-content: flex-end;"></div>
      `;

      const buttonContainer = modalContent.querySelector('div[style*="display: flex"]');

      const cancelBtn = document.createElement('button');
      cancelBtn.textContent = 'Cancel';
      cancelBtn.style.cssText =
        'background: var(--surface-variant); color: var(--text-primary); padding: 8px 16px; border-radius: 4px; border: 1px solid var(--border); cursor: pointer;';
      cancelBtn.addEventListener('click', () => modal.remove());

      const deleteBtn = document.createElement('button');
      deleteBtn.textContent = 'Clear All Failed';
      deleteBtn.style.cssText =
        'background: var(--status-failed); color: white; padding: 8px 16px; border-radius: 4px; border: none; cursor: pointer;';
      deleteBtn.addEventListener('click', async () => {
        modal.remove();
        await this.executeClearFailedJobs();
      });

      buttonContainer.appendChild(cancelBtn);
      buttonContainer.appendChild(deleteBtn);
      modal.appendChild(modalContent);

      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
      });

      document.body.appendChild(modal);
    } catch (error) {
      console.error('[OCR Queue] Error showing clear failed modal:', error);
    }
  }

  /**
   * Execute bulk delete of failed jobs
   */
  async executeClearFailedJobs() {
    try {
      const response = await APIClient.authenticatedFetch('/api/ocr/queue/failed', {
        method: 'DELETE',
      });

      if (response.ok) {
        const result = await response.json();
        UIUtils.showToast(`Cleared ${result.count || 0} failed OCR jobs`, 'success');
        await this.loadQueue();
      } else {
        const error = await response.json();
        UIUtils.showToast(error.detail || 'Failed to clear jobs', 'error');
      }
    } catch (error) {
      console.error('[OCR Queue] Error clearing failed jobs:', error);
      UIUtils.showToast('Error clearing failed jobs', 'error');
    }
  }
}

// Export singleton instance
export const ocrQueue = new OCRQueueManager();

// Expose to window for HTML onclick handlers
window.ocrQueue = ocrQueue;
