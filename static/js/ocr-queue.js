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

    // Group jobs by periodical (tracking_title)
    const grouped = this.groupJobsByPeriodical(filteredJobs);

    // Build grouped table rows
    tbody.innerHTML = '';
    grouped.forEach((group) => {
      const { periodical, jobs } = group;

      // Create periodical header row
      const headerRow = document.createElement('tr');
      headerRow.style.background = 'var(--surface)';
      headerRow.style.cursor = 'pointer';
      headerRow.style.borderBottom = '2px solid var(--border-color)';
      headerRow.onclick = () => this.openPeriodicalModal(periodical, jobs);

      const statusCounts = this.getJobStatusCounts(jobs);
      const statusBadges = Object.entries(statusCounts)
        .filter(([, count]) => count > 0)
        .map(([status, count]) => {
          const color = this.getStatusColor(status);
          return `<span style="background: ${color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; margin-right: 5px;">${count} ${status}</span>`;
        })
        .join('');

      headerRow.innerHTML = `
        <td colspan="3" style="padding: 12px; font-weight: bold;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <span style="font-size: 1.1em;">📋 ${periodical}</span>
              <span style="margin-left: 15px; font-size: 0.9em; color: var(--text-secondary);">${jobs.length} issue${jobs.length !== 1 ? 's' : ''}</span>
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
   * Group OCR jobs by periodical (tracking_title)
   * @param {Array} jobs - Array of OCR job objects
   * @returns {Array} Array of {periodical, jobs} objects
   */
  groupJobsByPeriodical(jobs) {
    const map = new Map();

    jobs.forEach((job) => {
      const key = job.tracking_title || job.magazine_title || 'Unknown';
      if (!map.has(key)) {
        map.set(key, { periodical: key, jobs: [] });
      }
      map.get(key).jobs.push(job);
    });

    // Convert to array and sort by periodical name
    return Array.from(map.values()).sort((a, b) => a.periodical.localeCompare(b.periodical));
  }

  /**
   * Get status counts for a group of jobs
   * @param {Array} jobs - Array of job objects
   * @returns {Object} Status counts
   */
  getJobStatusCounts(jobs) {
    const counts = {
      pending: 0,
      processing: 0,
      completed: 0,
      failed: 0,
    };

    jobs.forEach((job) => {
      if (counts.hasOwnProperty(job.status)) {
        counts[job.status]++;
      }
    });

    return counts;
  }

  /**
   * Get color for status badge
   * @param {string} status - Job status
   * @returns {string} CSS color variable
   */
  getStatusColor(status) {
    const colors = {
      pending: 'var(--status-pending)',
      processing: 'var(--status-downloading)',
      completed: 'var(--status-completed)',
      failed: 'var(--status-failed)',
    };
    return colors[status] || 'var(--text-secondary)';
  }

  /**
   * Open modal showing all issues for a periodical
   * @param {string} periodical - Periodical name
   * @param {Array} jobs - Array of job objects for this periodical
   */
  openPeriodicalModal(periodical, jobs) {
    // Build status summary
    const statusCounts = this.getJobStatusCounts(jobs);
    const statusList = Object.entries(statusCounts)
      .filter(([, count]) => count > 0)
      .map(([status, count]) => `${count} ${status}`)
      .join(', ');

    // Build table rows for jobs
    const tableRows = jobs
      .map((job) => {
        const statusColor = this.getStatusColor(job.status);
        const issueInfo =
          `${job.magazine_issue || 'Unknown Issue'} ${job.magazine_year ? `(${job.magazine_year})` : ''}`.trim();

        return `
        <tr style="cursor: pointer;" onclick="ocrQueue.showJobDetails(${job.id})">
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color);">
            <div style="font-weight: 600;">${job.magazine_title}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 2px;">${issueInfo}</div>
          </td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
            <span style="background: ${statusColor}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 0.85em;">${job.status}</span>
            ${job.status === 'completed' && job.processing_time_seconds ? `<div style="font-size: 0.75em; color: var(--text-secondary); margin-top: 4px;">${job.processing_time_seconds}s</div>` : ''}
            ${job.status === 'failed' && job.attempt_count ? `<div style="font-size: 0.75em; color: var(--text-secondary); margin-top: 4px;">Attempt ${job.attempt_count}/${this.maxRetries}</div>` : ''}
          </td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
            ${this.getPriorityBadge(job.priority)}
          </td>
        </tr>
      `;
      })
      .join('');

    const html = `
      <div class="modal-header">
        <h3>OCR Queue: ${periodical}</h3>
        <p style="color: var(--text-secondary); margin-top: 10px;">${jobs.length} issue${jobs.length !== 1 ? 's' : ''} - ${statusList}</p>
      </div>
      <div class="modal-body" style="max-height: 400px; overflow-y: auto; margin: 20px 0;">
        <table style="width: 100%; border-collapse: collapse;">
          <thead style="position: sticky; top: 0; background: var(--surface); z-index: 1;">
            <tr>
              <th style="text-align: left; padding: 10px; border-bottom: 2px solid var(--border-color);">Issue</th>
              <th style="text-align: center; padding: 10px; border-bottom: 2px solid var(--border-color);">Status</th>
              <th style="text-align: center; padding: 10px; border-bottom: 2px solid var(--border-color);">Priority</th>
            </tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>
      <div class="modal-footer" style="display: flex; gap: 10px; justify-content: flex-end; padding-top: 20px; border-top: 1px solid var(--border-color);">
        <button onclick="ocrQueue.closePeriodicalModal()" class="btn-secondary">Close</button>
      </div>
    `;

    const container = document.getElementById('ocr-periodical-modal-content');
    if (container) {
      container.innerHTML = html;
      document.getElementById('ocr-periodical-modal')?.classList.remove(CSS_CLASSES.HIDDEN);
    }
  }

  /**
   * Close periodical modal
   * @returns {void}
   */
  closePeriodicalModal() {
    document.getElementById('ocr-periodical-modal')?.classList.add(CSS_CLASSES.HIDDEN);
  }

  /**
   * Show detailed information for a specific OCR job
   * @param {number} jobId - OCR job ID
   */
  async showJobDetails(jobId) {
    try {
      const response = await APIClient.authenticatedFetch('/api/ocr/queue');
      const data = await response.json();
      const job = data.jobs.find((j) => j.id === jobId);

      if (!job) {
        UIUtils.showToast('Job not found', 'error');
        return;
      }

      // Format metadata for display
      let metadataHtml = '<p style="color: var(--text-secondary);">No OCR metadata available</p>';
      if (job.ocr_metadata) {
        metadataHtml = `<pre style="background: var(--surface-variant); padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 0.85em; max-height: 400px; overflow-y: auto;">${JSON.stringify(job.ocr_metadata, null, 2)}</pre>`;
      }

      // Format error if present
      let errorHtml = '';
      if (job.last_error) {
        errorHtml = `
          <div style="margin-top: 20px;">
            <h4 style="color: var(--status-failed); margin-bottom: 10px;">❌ Error Details</h4>
            <pre style="background: var(--surface-variant); padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 0.85em; color: var(--text-secondary);">${job.last_error}</pre>
          </div>
        `;
      }

      const html = `
        <div class="modal-header">
          <h3>OCR Job Details</h3>
          <p style="font-weight: 600; margin-top: 10px;">${job.magazine_title}</p>
          <p style="color: var(--text-secondary); font-size: 0.9em;">${job.magazine_issue || 'Unknown Issue'} ${job.magazine_year ? `(${job.magazine_year})` : ''}</p>
        </div>
        <div class="modal-body" style="max-height: 500px; overflow-y: auto; margin: 20px 0;">
          <div style="display: grid; grid-template-columns: auto 1fr; gap: 10px 20px; margin-bottom: 20px;">
            <strong>Status:</strong>
            <span>${job.status}</span>
            <strong>Priority:</strong>
            <span>${this.getPriorityBadge(job.priority)}</span>
            <strong>Language:</strong>
            <span>${job.language || 'N/A'}</span>
            <strong>Attempts:</strong>
            <span>${job.attempt_count}/${this.maxRetries}</span>
            ${job.processing_time_seconds ? `<strong>Processing Time:</strong><span>${job.processing_time_seconds}s</span>` : ''}
            ${job.created_at ? `<strong>Created:</strong><span>${new Date(job.created_at).toLocaleString()}</span>` : ''}
            ${job.completed_at ? `<strong>Completed:</strong><span>${new Date(job.completed_at).toLocaleString()}</span>` : ''}
          </div>

          <h4 style="margin-bottom: 10px;">📄 Extracted Metadata</h4>
          ${metadataHtml}

          ${errorHtml}
        </div>
        <div class="modal-footer" style="display: flex; gap: 10px; justify-content: flex-end; padding-top: 20px; border-top: 1px solid var(--border-color);">
          ${job.status === 'failed' ? `<button onclick="ocrQueue.retryJob(${job.id}); ocrQueue.closeJobDetailsModal();" class="btn-primary">🔄 Retry</button>` : ''}
          <button onclick="ocrQueue.closeJobDetailsModal()" class="btn-secondary">Close</button>
        </div>
      `;

      const container = document.getElementById('ocr-job-details-modal-content');
      if (container) {
        container.innerHTML = html;
        document.getElementById('ocr-job-details-modal')?.classList.remove(CSS_CLASSES.HIDDEN);
      }
    } catch (error) {
      console.error('[OCR Queue] Error loading job details:', error);
      UIUtils.showToast('Failed to load job details', 'error');
    }
  }

  /**
   * Close job details modal
   * @returns {void}
   */
  closeJobDetailsModal() {
    document.getElementById('ocr-job-details-modal')?.classList.add(CSS_CLASSES.HIDDEN);
  }

  /**
   * Show detailed information for a specific OCR job
   * @param {number} jobId - OCR job ID
   */
  async showJobDetails(jobId) {
    try {
      const response = await APIClient.authenticatedFetch('/api/ocr/queue');
      const data = await response.json();
      const job = data.jobs.find((j) => j.id === jobId);

      if (!job) {
        UIUtils.showToast('Job not found', 'error');
        return;
      }

      const modal = UIUtils.createModal();

      // Format metadata for display
      let metadataHtml = '<p style="color: var(--text-secondary);">No OCR metadata available</p>';
      if (job.ocr_metadata) {
        metadataHtml = `<pre style="background: var(--surface-variant); padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 0.85em; max-height: 400px; overflow-y: auto;">${JSON.stringify(job.ocr_metadata, null, 2)}</pre>`;
      }

      // Format error if present
      let errorHtml = '';
      if (job.last_error) {
        errorHtml = `
          <div style="margin-top: 20px;">
            <h4 style="color: var(--status-failed); margin-bottom: 10px;">❌ Error Details</h4>
            <pre style="background: var(--surface-variant); padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 0.85em; color: var(--text-secondary);">${job.last_error}</pre>
          </div>
        `;
      }

      const html = `
        <div class="modal-header">
          <h3>OCR Job Details</h3>
          <p style="font-weight: 600; margin-top: 10px;">${job.magazine_title}</p>
          <p style="color: var(--text-secondary); font-size: 0.9em;">${job.magazine_issue || 'Unknown Issue'} ${job.magazine_year ? `(${job.magazine_year})` : ''}</p>
        </div>
        <div class="modal-body" style="max-height: 500px; overflow-y: auto; margin: 20px 0;">
          <div style="display: grid; grid-template-columns: auto 1fr; gap: 10px 20px; margin-bottom: 20px;">
            <strong>Status:</strong>
            <span>${job.status}</span>
            <strong>Priority:</strong>
            <span>${this.getPriorityBadge(job.priority)}</span>
            <strong>Language:</strong>
            <span>${job.language || 'N/A'}</span>
            <strong>Attempts:</strong>
            <span>${job.attempt_count}/${this.maxRetries}</span>
            ${job.processing_time_seconds ? `<strong>Processing Time:</strong><span>${job.processing_time_seconds}s</span>` : ''}
            ${job.created_at ? `<strong>Created:</strong><span>${new Date(job.created_at).toLocaleString()}</span>` : ''}
            ${job.completed_at ? `<strong>Completed:</strong><span>${new Date(job.completed_at).toLocaleString()}</span>` : ''}
          </div>

          <h4 style="margin-bottom: 10px;">📄 Extracted Metadata</h4>
          ${metadataHtml}

          ${errorHtml}
        </div>
        <div class="modal-footer" style="display: flex; gap: 10px; justify-content: flex-end; padding-top: 20px; border-top: 1px solid var(--border-color);">
          ${job.status === 'failed' ? `<button onclick="ocrQueue.retryJob(${job.id}); UIUtils.closeModal();" class="btn-primary">🔄 Retry</button>` : ''}
          <button onclick="UIUtils.closeModal()" class="btn-secondary">Close</button>
        </div>
      `;

      modal.innerHTML = html;
    } catch (error) {
      console.error('[OCR Queue] Error loading job details:', error);
      UIUtils.showToast('Failed to load job details', 'error');
    }
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
