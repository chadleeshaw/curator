/**
 * OCR Queue Module
 * Handles OCR job queue management and monitoring
 */

import { APIClient, APIHelper } from '../core/api.js?v=1767733177';
import { UIUtils } from '../core/ui-utils.js?v=1767733177';
import {
  ELEMENT_IDS as _ELEMENT_IDS,
  STATUS_MESSAGES as _STATUS_MESSAGES,
  CSS_CLASSES,
  TIMEOUTS as _TIMEOUTS,
} from '../core/constants.js';

export class OCRQueueManager {
  constructor() {
    this.refreshInterval = null;
    /** @type {number} Maximum OCR retry attempts */
    this.maxRetries = 3; // Default value, will be loaded from API
    /** @type {string} Current filter (all, active, pending, processing, completed, failed) */
    this.currentFilter = 'all';
    /** @type {string} Current sort field (title, status, priority, created_at) */
    this.currentSort = 'title';
    /** @type {boolean} Current sort order (true = ascending, false = descending) */
    this.sortAscending = true;
    /** @type {string|null} Current periodical in modal */
    this.currentModalPeriodical = null;
    /** @type {Array|null} Current jobs in modal */
    this.currentModalJobs = null;
    /** @type {string} Current filter in modal */
    this.currentModalFilter = 'all';
    /** @type {string} Current sort field in modal */
    this.currentModalSort = 'date';
    /** @type {boolean} Current sort order in modal */
    this.currentModalSortAsc = false;

    // Load preferences from localStorage
    this.loadSortPreference();
    this.loadFilterPreference();

    // Load constants from API
    this.loadConstants();
  }

  /**
   * Load application constants from the API
   * @returns {Promise<void>}
   */
  async loadConstants() {
    try {
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.get('/api/constants');
        return await response.json();
      }, 'OCRQueue');
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
      const [queueData, statsData] = await APIHelper.executeWithErrorHandling(
        async () => {
          const [queueResponse, statsResponse] = await Promise.all([
            APIClient.authenticatedFetch('/api/ocr/queue'),
            APIClient.authenticatedFetch('/api/ocr/queue/stats'),
          ]);

          return [await queueResponse.json(), await statsResponse.json()];
        },
        'OCRQueue',
        'ocr-queue-status'
      );

      // Update badge count
      this.updateBadgeCount(statsData);

      // Display queue
      this.displayQueue(queueData, statsData);
    } catch (error) {
      // Already logged and displayed by APIHelper
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
        <div class="queue-stats-grid">
          <div class="queue-stat-item" title="Waiting to be processed">
            <div class="queue-stat-number" style="color: ${colors.pending};">${statsData.pending || 0}</div>
            <div class="queue-stat-label">Pending</div>
          </div>
          <div class="queue-stat-item" title="Currently processing">
            <div class="queue-stat-number" style="color: ${colors.processing};">${statsData.processing || 0}</div>
            <div class="queue-stat-label">Active</div>
          </div>
          <div class="queue-stat-item" title="Successfully completed">
            <div class="queue-stat-number" style="color: ${colors.completed};">${statsData.completed || 0}</div>
            <div class="queue-stat-label">Completed</div>
          </div>
          <div class="queue-stat-item" title="Failed">
            <div class="queue-stat-number" style="color: ${colors.failed};">${statsData.failed || 0}</div>
            <div class="queue-stat-label">Failed</div>
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
    } else if (this.currentFilter === 'pending') {
      filteredJobs = queueData.jobs.filter((job) => job.status === 'pending');
    } else if (this.currentFilter === 'processing') {
      filteredJobs = queueData.jobs.filter((job) => job.status === 'processing');
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

    // Sort jobs within each group
    grouped.forEach((group) => {
      group.jobs = this.sortJobs(group.jobs);
    });

    // Sort the groups themselves based on the first item in each group
    if (this.currentSort !== 'title') {
      // For non-title sorts, sort groups by the first item's sort field
      grouped.sort((a, b) => {
        if (a.jobs.length === 0 || b.jobs.length === 0) return 0;
        
        const firstA = a.jobs[0];
        const firstB = b.jobs[0];
        let comparison = 0;

        switch (this.currentSort) {
          case 'status':
            comparison = (firstA.status || '').localeCompare(firstB.status || '');
            break;
          case 'priority':
            comparison = (firstA.priority || 0) - (firstB.priority || 0);
            break;
          case 'created_at':
            comparison = new Date(firstA.created_at || 0) - new Date(firstB.created_at || 0);
            break;
        }

        return this.sortAscending ? comparison : -comparison;
      });
    } else {
      // For title sort, sort groups alphabetically by periodical name
      grouped.sort((a, b) => {
        const comparison = a.periodical.localeCompare(b.periodical);
        return this.sortAscending ? comparison : -comparison;
      });
    }

    // Build grouped table rows
    tbody.innerHTML = '';
    grouped.forEach((group) => {
      const { periodical, jobs } = group;

      // Create periodical header row
      const headerRow = document.createElement('tr');
      headerRow.style.background = 'var(--surface)';
      headerRow.style.cursor = 'pointer';
      headerRow.style.borderTop = '1px solid var(--border-color)';
      headerRow.style.borderBottom = '1px solid var(--border-color)';
      headerRow.style.transition = 'background 0.2s ease';
      headerRow.onmouseover = () => {
        headerRow.style.background = 'var(--surface-variant)';
      };
      headerRow.onmouseout = () => {
        headerRow.style.background = 'var(--surface)';
      };
      headerRow.onclick = () => this.openPeriodicalModal(periodical, jobs);

      const statusCounts = this.getJobStatusCounts(jobs);

      // Build status indicators for the Status column (active states)
      const processingJobs = jobs.filter(j => j.status === 'processing');
      let statusIndicators = '';
      if (processingJobs.length > 0) {
        statusIndicators += `<span style="background: var(--status-downloading); color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; white-space: nowrap;">⚡ ${processingJobs.length} processing</span>`;
      }

      // Build uniform summary bubbles (fixed order, always shown)
      const summaryStatuses = ['pending', 'processing', 'completed', 'failed'];
      const summaryBubbles = summaryStatuses.map(status => {
        const count = statusCounts[status] || 0;
        const color = this.getStatusColor(status);
        const padded = String(count).padStart(2, '0');
        return `<span class="status-bubble" data-status="${status}" style="background: ${color}; color: white; min-width: 26px; display: inline-block; text-align: center; padding: 2px 6px; border-radius: 10px; font-size: 0.8em; cursor: pointer; font-weight: 600; font-variant-numeric: tabular-nums; opacity: ${count === 0 ? '0.3' : '1'};" title="${count} ${status}">${padded}</span>`;
      }).join('');

      headerRow.innerHTML = `
        <td style="padding: 12px; font-weight: bold;">
          <div>
            <span style="font-size: 1.1em;">📋 ${periodical}</span>
            <span style="margin-left: 15px; font-size: 0.9em; color: var(--text-secondary);">${jobs.length} issue${jobs.length !== 1 ? 's' : ''}</span>
          </div>
          <div class="mobile-summary" style="display: none; margin-top: 6px;">
            <div style="display: inline-flex; gap: 4px; align-items: center;">
              ${summaryBubbles}
              <span style="font-size: 1.2em; color: var(--text-secondary); margin-left: 4px;">→</span>
            </div>
          </div>
        </td>
        <td class="queue-status-col" style="padding: 12px; text-align: center; white-space: nowrap;">
          ${statusIndicators}
        </td>
        <td class="queue-summary-col" style="padding: 12px; text-align: right; white-space: nowrap;">
          <div style="display: inline-flex; gap: 4px; align-items: center;">
            ${summaryBubbles}
            <span style="font-size: 1.2em; color: var(--text-secondary); margin-left: 4px;">→</span>
          </div>
        </td>
      `;

      // Add click handlers for individual status bubbles
      headerRow.querySelectorAll('.status-bubble').forEach(bubble => {
        bubble.addEventListener('click', (e) => {
          e.stopPropagation();
          this.openPeriodicalModal(periodical, jobs, bubble.dataset.status);
        });
      });

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
  openPeriodicalModal(periodical, jobs, filter = 'all') {
    this.currentModalPeriodical = periodical;
    this.currentModalJobs = jobs;
    this.currentModalFilter = filter;
    this.renderPeriodicalModal();
  }

  /**
   * Render the periodical modal with current filter and sort
   * @returns {void}
   */
  renderPeriodicalModal() {
    const { currentModalJobs: jobs, currentModalPeriodical: periodical, currentModalFilter: filter } = this;
    if (!jobs || !periodical) return;

    // Build status summary
    const statusCounts = this.getJobStatusCounts(jobs);
    const statusList = Object.entries(statusCounts)
      .filter(([, count]) => count > 0)
      .map(([status, count]) => `${count} ${status}`)
      .join(', ');

    // Filter items
    let filteredJobs;
    if (filter === 'all') {
      filteredJobs = jobs;
    } else if (filter === 'active') {
      filteredJobs = jobs.filter(j => j.status === 'pending' || j.status === 'processing');
    } else {
      filteredJobs = jobs.filter(j => j.status === filter);
    }

    // Filter buttons
    const activeCount = (statusCounts.pending ?? 0) + (statusCounts.processing ?? 0);
    const filterButtons = ['all', 'active', 'completed', 'failed']
      .map((f) => {
        let count;
        if (f === 'all') count = jobs.length;
        else if (f === 'active') count = activeCount;
        else count = statusCounts[f] ?? 0;
        const selected = filter === f ? 'active' : '';
        return `<button onclick="ocrQueue.filterOcrModal('${f}')" class="sort-btn ${selected}">${f.charAt(0).toUpperCase() + f.slice(1)} (${count})</button>`;
      })
      .join('\n');

    // Sort
    const sortField = this.currentModalSort;
    const sortAsc = this.currentModalSortAsc;
    const sorted = [...filteredJobs].sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case 'title':
          cmp = (a.magazine_title || '').localeCompare(b.magazine_title || '');
          break;
        case 'status':
          cmp = (a.status || '').localeCompare(b.status || '');
          break;
        case 'date':
        default:
          cmp = new Date(a.completed_at || a.created_at || 0) - new Date(b.completed_at || b.created_at || 0);
          break;
      }
      return sortAsc ? cmp : -cmp;
    });

    // Build table rows
    let tableRows = '';
    if (sorted.length === 0) {
      tableRows = `<tr><td colspan="5" style="padding: 40px; text-align: center; color: var(--text-secondary);">No ${filter === 'all' ? '' : filter} items found</td></tr>`;
    } else {
      tableRows = sorted
        .map((job) => {
          const statusColor = this.getStatusColor(job.status);
          const issueInfo = `${job.magazine_issue || 'Unknown Issue'} ${job.magazine_year ? `(${job.magazine_year})` : ''}`.trim();

          // Format relative time
          const timestamp = job.completed_at || job.created_at;
          let timeAgo = '';
          if (timestamp) {
            const diff = Date.now() - new Date(timestamp).getTime();
            const mins = Math.floor(diff / 60000);
            const hours = Math.floor(diff / 3600000);
            const days = Math.floor(diff / 86400000);
            if (mins < 1) timeAgo = 'just now';
            else if (mins < 60) timeAgo = `${mins}m ago`;
            else if (hours < 24) timeAgo = `${hours}h ago`;
            else timeAgo = `${days}d ago`;
          }

          return `
          <tr style="background: var(--surface-variant); border-radius: 6px;">
            <td style="padding: 14px; border-bottom: 1px solid var(--border-color);">
              <div style="font-weight: 600;">${job.magazine_title}</div>
              <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 2px;">${issueInfo}</div>
            </td>
            <td style="padding: 14px; border-bottom: 1px solid var(--border-color); text-align: center; white-space: nowrap;">
              <span style="background: ${statusColor}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 0.85em;">${job.status}</span>
              ${job.status === 'completed' && job.processing_time_seconds ? `<div style="font-size: 0.75em; color: var(--text-secondary); margin-top: 4px;">${job.processing_time_seconds}s</div>` : ''}
              ${job.status === 'failed' && job.attempt_count ? `<div style="font-size: 0.75em; color: var(--text-secondary); margin-top: 4px;">Attempt ${job.attempt_count}/${this.maxRetries}</div>` : ''}
            </td>
            <td style="padding: 14px; border-bottom: 1px solid var(--border-color); text-align: center; white-space: nowrap; font-size: 0.8em; color: var(--text-secondary);">
              ${timeAgo}
            </td>
            <td style="padding: 14px; border-bottom: 1px solid var(--border-color); text-align: right; white-space: nowrap;">
              <div style="display: inline-flex; gap: 6px; align-items: center;">
                <button onclick="event.stopPropagation(); ocrQueue.showJobDetails(${job.id})" style="padding: 5px 10px; font-size: 0.8em; border: 1px solid var(--border-color); background: var(--surface); color: var(--text-secondary); border-radius: 6px; cursor: pointer;" title="View metadata">Details</button>
                ${job.status === 'failed' ? `<button onclick="event.stopPropagation(); ocrQueue.retryJob(${job.id})" style="padding: 5px 10px; font-size: 0.8em; border: 1px solid var(--status-downloading); background: transparent; color: var(--status-downloading); border-radius: 6px; cursor: pointer;" title="Retry OCR">Retry</button>` : ''}
                <button onclick="event.stopPropagation(); ocrQueue.deleteJob(${job.id})" style="padding: 5px 10px; font-size: 0.8em; border: 1px solid var(--status-failed); background: transparent; color: var(--status-failed); border-radius: 6px; cursor: pointer;" title="Remove job">Delete</button>
              </div>
            </td>
          </tr>
        `;
        })
        .join('');
    }

    const html = `
      <div class="modal-header">
        <h3>OCR Queue: ${periodical}</h3>
        <p style="color: var(--text-secondary); margin-top: 10px;">${jobs.length} issue${jobs.length !== 1 ? 's' : ''} - ${statusList}</p>
        <div style="display: flex; gap: 8px; margin-top: 15px; flex-wrap: wrap;">
          ${filterButtons}
        </div>
      </div>
      <div class="modal-body" style="max-height: 60vh; overflow-y: auto; margin: 20px 0;">
        <table style="width: 100%; border-collapse: separate; border-spacing: 0 4px;">
          <thead style="position: sticky; top: 0; background: var(--surface); z-index: 1;">
            <tr>
              <th onclick="ocrQueue.sortOcrModal('title')" style="text-align: left; padding: 12px 14px; border-bottom: 2px solid var(--border-color); cursor: pointer; user-select: none;">Issue ${this.currentModalSort === 'title' ? (this.currentModalSortAsc ? '↑' : '↓') : ''}</th>
              <th onclick="ocrQueue.sortOcrModal('status')" style="text-align: center; padding: 12px 14px; border-bottom: 2px solid var(--border-color); cursor: pointer; user-select: none;">Status ${this.currentModalSort === 'status' ? (this.currentModalSortAsc ? '↑' : '↓') : ''}</th>
              <th onclick="ocrQueue.sortOcrModal('date')" style="text-align: center; padding: 12px 14px; border-bottom: 2px solid var(--border-color); min-width: 80px; cursor: pointer; user-select: none;">Date ${this.currentModalSort === 'date' ? (this.currentModalSortAsc ? '↑' : '↓') : ''}</th>
              <th style="text-align: center; padding: 12px 14px; border-bottom: 2px solid var(--border-color); min-width: 80px;">Actions</th>
            </tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>
      <div id="ocr-modal-status" class="hidden" style="padding: 10px 15px; border-radius: 6px; margin-bottom: 10px; font-size: 0.9em;"></div>
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
    this.currentModalJobs = null;
    this.currentModalPeriodical = null;
    this.currentModalFilter = 'all';
  }

  /**
   * Show error info for a failed OCR job in the modal status bar
   * @param {string} message - The error message to display
   */
  showJobInfo(message) {
    const decoded = message.replace(/&#39;/g, "'").replace(/&quot;/g, '"');
    const statusEl = document.getElementById('ocr-modal-status');
    if (statusEl && !statusEl.classList.contains('hidden') && statusEl.textContent.includes(decoded)) {
      UIUtils.hideStatus('ocr-modal-status');
      return;
    }
    UIUtils.showStatus('ocr-modal-status', decoded, 'error');
  }

  /**
   * Filter OCR modal by status
   * @param {string} status - Status to filter by
   */
  filterOcrModal(status) {
    this.currentModalFilter = status;
    this.renderPeriodicalModal();
  }

  /**
   * Sort OCR modal by column
   * @param {string} field - Field to sort by ('title', 'status', 'date')
   */
  sortOcrModal(field) {
    if (this.currentModalSort === field) {
      this.currentModalSortAsc = !this.currentModalSortAsc;
    } else {
      this.currentModalSort = field;
      this.currentModalSortAsc = field === 'title';
    }
    this.renderPeriodicalModal();
  }

  /**
   * Show detailed information for a specific OCR job
   * @param {number} jobId - OCR job ID
   */
  async showJobDetails(jobId) {
    try {
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.authenticatedFetch('/api/ocr/queue');
        return await response.json();
      }, 'OCRQueue');
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
      const response = await APIHelper.executeWithErrorHandling(async () => {
        return await APIClient.authenticatedFetch(`/api/ocr/retry/${jobId}`, {
          method: 'POST',
        });
      }, 'OCRQueue');

      if (response.ok) {
        UIUtils.showToast('OCR job queued for retry', 'success');
        await this.loadQueue();
      } else {
        const error = await response.json();
        UIUtils.showToast(error.detail || 'Failed to retry job', 'error');
      }
    } catch (error) {
      // Already logged by APIHelper
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
      const response = await APIHelper.executeWithErrorHandling(async () => {
        return await APIClient.authenticatedFetch(`/api/ocr/queue/${jobId}`, {
          method: 'DELETE',
        });
      }, 'OCRQueue');

      if (response.ok) {
        UIUtils.showToast('OCR job removed', 'success');
        // Close the periodical modal if open
        this.closePeriodicalModal();
        // Reload the queue
        await this.loadQueue();
      } else {
        const error = await response.json();
        UIUtils.showToast(error.detail || 'Failed to delete job', 'error');
      }
    } catch (error) {
      // Already logged by APIHelper
    }
  }

  /**
   * Delete an OCR job (shows confirmation modal)
   * Fetches job details to show title in confirmation
   */
  async deleteJob(jobId) {
    try {
      // Fetch job details to get the title
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.authenticatedFetch('/api/ocr/queue');
        return await response.json();
      }, 'OCRQueue');
      const job = data.jobs.find((j) => j.id === jobId);

      if (!job) {
        UIUtils.showToast('Job not found', 'error');
        return;
      }

      const jobTitle = `${job.magazine_title} - ${job.magazine_issue || 'Unknown Issue'}`;
      this.showDeleteConfirmation(jobId, jobTitle);
    } catch (error) {
      console.error('[OCR Queue] Error fetching job for delete:', error);
      // Fallback to showing confirmation without title
      this.showDeleteConfirmation(jobId, 'Unknown Job');
    }
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
   * Sort jobs based on current sort settings
   * @param {Array} jobs - Array of job objects
   * @returns {Array} Sorted array of jobs
   */
  sortJobs(jobs) {
    const sorted = [...jobs]; // Create a copy to avoid mutating original

    sorted.sort((a, b) => {
      let comparison = 0;

      switch (this.currentSort) {
        case 'title':
          comparison = (a.title || '').localeCompare(b.title || '');
          break;
        case 'status':
          comparison = (a.status || '').localeCompare(b.status || '');
          break;
        case 'priority':
          comparison = (a.priority || 0) - (b.priority || 0);
          break;
        case 'created_at':
          comparison = new Date(a.created_at || 0) - new Date(b.created_at || 0);
          break;
        default:
          comparison = 0;
      }

      // Apply ascending/descending order
      return this.sortAscending ? comparison : -comparison;
    });

    return sorted;
  }

  /**
   * Set filter and reload queue
   * @param {string} filter - Filter type (all, active, pending, processing, completed, failed)
   */
  setFilter(filter) {
    this.currentFilter = filter;

    // Save to localStorage in combined settings object
    try {
      const saved = localStorage.getItem('ocrQueueSettings');
      const settings = saved ? JSON.parse(saved) : {};
      settings.filter = { status: filter };
      localStorage.setItem('ocrQueueSettings', JSON.stringify(settings));
    } catch (error) {
      console.warn('[OCR Queue] Failed to save filter:', error);
    }

    // Update dropdown
    const dropdown = document.getElementById('ocr-status-filter');
    if (dropdown) {
      dropdown.value = filter;
    }

    // Update button states (for backward compatibility with old buttons)
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
   * Load filter preference from localStorage
   * @returns {void}
   */
  loadFilterPreference() {
    try {
      const saved = localStorage.getItem('ocrQueueSettings');
      if (saved) {
        const settings = JSON.parse(saved);
        this.currentFilter = settings.filter?.status || 'all';
      }
    } catch (error) {
      console.warn('[OCR Queue] Failed to parse filter preference:', error);
    }
    // Update dropdown on page load
    setTimeout(() => {
      const dropdown = document.getElementById('ocr-status-filter');
      if (dropdown) {
        dropdown.value = this.currentFilter;
      }
    }, 100);
  }

  /**
   * Load sort preference from localStorage
   * @returns {void}
   */
  loadSortPreference() {
    try {
      const saved = localStorage.getItem('ocrQueueSettings');
      if (saved) {
        const settings = JSON.parse(saved);
        this.currentSort = settings.sort?.field || 'title';
        this.sortAscending = settings.sort?.ascending !== undefined ? settings.sort.ascending : true;
      }
    } catch (error) {
      console.warn('[OCR Queue] Failed to parse sort preference:', error);
    }
    // Update dropdown and button on page load
    setTimeout(() => {
      const dropdown = document.getElementById('ocr-sort-select');
      if (dropdown) {
        dropdown.value = this.currentSort;
      }
      const toggleBtn = document.getElementById('ocr-sort-toggle');
      if (toggleBtn) {
        toggleBtn.textContent = this.sortAscending ? '↑' : '↓';
      }
    }, 100);
  }

  /**
   * Set the current sort for the OCR queue
   *
   * @param {string} sort - Sort type (title, status, priority, created_at)
   * @returns {void}
   */
  setSort(sort) {
    this.currentSort = sort;
    // Save to localStorage in combined settings object
    try {
      const saved = localStorage.getItem('ocrQueueSettings');
      const settings = saved ? JSON.parse(saved) : {};
      settings.sort = {
        field: sort,
        ascending: this.sortAscending
      };
      localStorage.setItem('ocrQueueSettings', JSON.stringify(settings));
    } catch (error) {
      console.warn('[OCR Queue] Failed to save sort:', error);
    }
    // Reload queue with new sort
    this.loadQueue();
  }

  /**
   * Toggle sort order for the OCR queue
   * @returns {void}
   */
  toggleSortOrder() {
    this.sortAscending = !this.sortAscending;
    // Save to localStorage in combined settings object
    try {
      const saved = localStorage.getItem('ocrQueueSettings');
      const settings = saved ? JSON.parse(saved) : {};
      settings.sort = {
        field: this.currentSort,
        ascending: this.sortAscending
      };
      localStorage.setItem('ocrQueueSettings', JSON.stringify(settings));
    } catch (error) {
      console.warn('[OCR Queue] Failed to save sort order:', error);
    }
    // Update button
    const toggleBtn = document.getElementById('ocr-sort-toggle');
    if (toggleBtn) {
      toggleBtn.textContent = this.sortAscending ? '↑' : '↓';
    }
    // Reload queue with new sort order
    this.loadQueue();
  }

  /**
   * Clear OCR jobs by status
   *
   * @param {string} status - Status to clear (all, pending, processing, completed, failed)
   * @returns {Promise<void>}
   */
  async clearByStatus(status) {
    try {
      // Map status labels to values
      const statusMap = {
        all: 'all',
        pending: 'pending',
        processing: 'processing',
        active: 'processing', // Handle 'active' label mapping to 'processing'
        completed: 'completed',
        done: 'completed', // Handle 'done' label mapping to 'completed'
        failed: 'failed',
      };

      const actualStatus = statusMap[status.toLowerCase()] || status;

      // Confirm before clearing
      const confirmed = await UIUtils.confirm(
        `Clear ${actualStatus.charAt(0).toUpperCase() + actualStatus.slice(1)} OCR Jobs`,
        `Are you sure you want to clear ${actualStatus === 'all' ? 'all' : 'all ' + actualStatus} OCR jobs? This cannot be undone.`
      );

      if (!confirmed) {
        return;
      }

      UIUtils.showStatus('ocr-queue-status', `🗑️ Clearing ${actualStatus} OCR jobs...`, 'info');

      const endpoint = `/api/ocr/queue/${actualStatus}`;
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(endpoint, {
            method: 'DELETE',
          });
          return await response.json();
        },
        'OCRQueue',
        'ocr-queue-status'
      );

      if (data) {
        UIUtils.showToast(`Cleared ${data.count || 0} OCR jobs`, 'success');
        await this.loadQueue();
      }
    } catch (error) {
      // Already logged by APIHelper
    }
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
      const response = await APIHelper.executeWithErrorHandling(async () => {
        return await APIClient.authenticatedFetch('/api/ocr/queue/failed', {
          method: 'DELETE',
        });
      }, 'OCRQueue');

      if (response.ok) {
        const result = await response.json();
        UIUtils.showToast(`Cleared ${result.count || 0} failed OCR jobs`, 'success');
        await this.loadQueue();
      } else {
        const error = await response.json();
        UIUtils.showToast(error.detail || 'Failed to clear jobs', 'error');
      }
    } catch (error) {
      // Already logged by APIHelper
    }
  }
}

// Export singleton instance
export const ocrQueue = new OCRQueueManager();

// Expose to window for HTML onclick handlers
window.ocrQueue = ocrQueue;
