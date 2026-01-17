/**
 * Downloads Module
 * Handles download queue management, failed downloads, and cleanup operations
 * @module downloads
 */

import { APIClient } from './api.js?v=1767733177';
import { UIUtils } from './ui-utils.js?v=1767733177';
import {
  ELEMENT_IDS as _ELEMENT_IDS,
  STATUS_MESSAGES as _STATUS_MESSAGES,
  CSS_CLASSES,
  TIMEOUTS as _TIMEOUTS,
} from './constants.js';

/**
 * @typedef {Object} DownloadItem
 * @property {number} id - Unique identifier
 * @property {number} submission_id - Submission ID
 * @property {string} title - Download title
 * @property {string} magazine - Associated magazine name
 * @property {string} status - Current status (pending, downloading, completed, failed, skipped)
 * @property {number} [attempt_count] - Number of download attempts
 * @property {string} [last_error] - Last error message
 * @property {string} [created_at] - Creation timestamp
 * @property {string} [updated_at] - Last update timestamp
 * @property {boolean} [isBad] - Whether marked as a bad file
 */

/**
 * @typedef {Object} DownloadGroup
 * @property {string} periodical - Periodical name
 * @property {DownloadItem[]} items - Download items in this group
 * @property {number} failedCount - Number of failed downloads
 * @property {number} badCount - Number of bad files
 * @property {number} totalCount - Total count of items
 */

/**
 * Downloads Manager class for managing download queue operations
 * @class
 */
export class DownloadsManager {
  /**
   * Create a new DownloadsManager instance
   */
  constructor() {
    /** @type {number|null} Auto-refresh interval ID */
    this.refreshInterval = null;
    /** @type {boolean} Whether to include bad files in display */
    this.showBadFiles = true;
    /** @type {number} Maximum download retry attempts */
    this.maxRetries = 3; // Default value, will be loaded from API
    /** @type {DownloadItem[]|null} Current items in modal */
    this.currentModalItems = null;
    /** @type {string|null} Current periodical in modal */
    this.currentModalPeriodical = null;
    /** @type {string} Current filter in modal */
    this.currentModalFilter = 'all';
    /** @type {string} Current filter for queue view (all, active, failed, completed) */
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
      if (data.success && data.max_download_retries) {
        this.maxRetries = data.max_download_retries;
      }
    } catch (error) {
      console.warn('[Downloads] Failed to load constants, using defaults:', error);
    }
  }

  /**
   * Load failed downloads and bad files from the API
   *
   * @returns {Promise<void>}
   * @throws {Error} When API request fails
   *
   * @example
   * await downloads.loadFailedDownloads();
   */
  async loadFailedDownloads() {
    try {
      const response = await APIClient.authenticatedFetch(
        `/api/downloads/failed?include_bad=${this.showBadFiles}`
      );
      const data = await response.json();
      this.displayFailedDownloads(data);
    } catch (error) {
      console.error('[Downloads] Failed to load failed downloads:', error);
      UIUtils.showStatus('downloads-status', 'Error loading failed downloads', 'error');
    }
  }

  /**
   * Display failed downloads and bad files grouped by periodical
   *
   * @param {Object} data - Response data from API
   * @param {DownloadItem[]} data.failed_downloads - Array of failed downloads
   * @param {DownloadItem[]} data.bad_files - Array of bad files
   * @returns {void}
   */
  displayFailedDownloads(data) {
    const container = document.getElementById('failed-downloads-container');
    if (!container) return;

    const { failed_downloads: failedDownloads, bad_files: badFiles } = data;
    const grouped = this.groupDownloadsByPeriodical(failedDownloads, badFiles);

    if (grouped.length === 0) {
      container.innerHTML = `
        <div class="${CSS_CLASSES.EMPTY_STATE}">
          <div class="${CSS_CLASSES.EMPTY_STATE_ICON}">\u2705</div>
          <p class="${CSS_CLASSES.EMPTY_STATE_TITLE}">No failed downloads</p>
          <p class="${CSS_CLASSES.EMPTY_STATE_SUBTITLE}">All downloads completed successfully</p>
        </div>
      `;
      return;
    }

    // Calculate totals
    const totalFailed = grouped.reduce((sum, g) => sum + g.failedCount, 0);
    const totalBad = grouped.reduce((sum, g) => sum + g.badCount, 0);

    let html = `
      <div class="${CSS_CLASSES.STATS_SUMMARY}">
        <div class="${CSS_CLASSES.STAT_BOX}">
          <div class="${CSS_CLASSES.STAT_BOX_VALUE} stat-box-warning">${totalFailed}</div>
          <div class="${CSS_CLASSES.STAT_BOX_LABEL}">Failed Downloads</div>
          <div class="${CSS_CLASSES.STAT_BOX_SUBLABEL}">Can be retried</div>
        </div>
        <div class="${CSS_CLASSES.STAT_BOX}">
          <div class="${CSS_CLASSES.STAT_BOX_VALUE} stat-box-error">${totalBad}</div>
          <div class="${CSS_CLASSES.STAT_BOX_LABEL}">Bad Files</div>
          <div class="${CSS_CLASSES.STAT_BOX_SUBLABEL}">3+ failures, marked as bad</div>
        </div>
        <div class="${CSS_CLASSES.STAT_BOX}">
          <div class="${CSS_CLASSES.STAT_BOX_VALUE} stat-box-primary">${grouped.length}</div>
          <div class="${CSS_CLASSES.STAT_BOX_LABEL}">Affected Periodicals</div>
          <div class="${CSS_CLASSES.STAT_BOX_SUBLABEL}">Click below to manage</div>
        </div>
      </div>
      <div class="periodical-groups">
    `;

    grouped.forEach((group) => {
      const { periodical, badCount, failedCount, totalCount, items } = group;
      const hasBadFiles = badCount > 0;
      const icon = hasBadFiles ? '\uD83D\uDEAB' : '\u26A0\uFE0F';

      html += `
        <div class="periodical-group-card"
             onclick="downloads.openManageFailedModal('${periodical}', ${JSON.stringify(items).replace(/"/g, '&quot;')})">
          <div class="periodical-group-content">
            <div class="periodical-group-info">
              <div class="periodical-group-header">
                <span class="periodical-group-icon">${icon}</span>
                <span class="periodical-group-title">${periodical}</span>
              </div>
              <div class="periodical-group-subtitle">
                ${totalCount} issue${totalCount !== 1 ? 's' : ''} need${totalCount === 1 ? 's' : ''} attention
              </div>
            </div>
            <div class="periodical-group-badges">
              ${failedCount > 0 ? `<span class="badge badge-warning">${failedCount} Failed</span>` : ''}
              ${hasBadFiles ? `<span class="badge badge-error">${badCount} Bad</span>` : ''}
              <span class="periodical-group-arrow">\u2192</span>
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
   *
   * @param {DownloadItem[]} failed - Array of failed downloads
   * @param {DownloadItem[]} bad - Array of bad files
   * @returns {DownloadGroup[]} Grouped downloads sorted by total count
   */
  groupDownloadsByPeriodical(failed, bad) {
    const map = new Map();

    // Process failed downloads
    failed.forEach((item) => {
      const key = item.magazine ?? 'Unknown';
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
      const key = item.magazine ?? 'Unknown';
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
   * Delete a failed download from the database
   *
   * @param {number} submissionId - The submission ID to delete
   * @returns {Promise<void>}
   *
   * @example
   * await downloads.deleteFailedDownload(123);
   */
  async deleteFailedDownload(submissionId) {
    const confirmed = await UIUtils.confirm(
      'Remove Download',
      'Remove this failed download from the database?'
    );
    if (!confirmed) return;

    // Determine which status element to use (modal or base page)
    const failedModal = document.getElementById('manage-failed-modal');
    const statusId =
      failedModal && !failedModal.classList.contains('hidden')
        ? 'modal-failed-status'
        : 'downloads-status';

    try {
      const response = await APIClient.authenticatedFetch(`/api/downloads/failed/${submissionId}`, {
        method: 'DELETE',
      });
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus(statusId, 'Failed download removed', 'success');
        this.loadFailedDownloads();
      } else {
        throw new Error(data.message ?? 'Failed to remove');
      }
    } catch (error) {
      console.error('[Downloads] Failed to delete failed download:', error);
      UIUtils.showStatus(statusId, `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Load the download queue from the API
   *
   * @returns {Promise<void>}
   *
   * @example
   * await downloads.loadDownloadQueue();
   */
  async loadDownloadQueue() {
    try {
      const url = '/api/downloads/queue/all';
      console.log('[Queue] Fetching from:', url);

      const response = await APIClient.authenticatedFetch(url);
      const data = await response.json();

      console.log('[Queue] API Response:', data);
      console.log('[Queue] Items in queue:', data.queue?.length ?? 0);
      console.log('[Queue] Status counts:', data.status_counts);

      if (data.queue?.length > 0) {
        data.queue.slice(0, 3).forEach((item, idx) => {
          console.log(`  [${idx}] ${item.title}: ${item.status} (${item.magazine})`);
        });
        if (data.queue.length > 3) console.log(`  ... and ${data.queue.length - 3} more`);
      }

      this.displayQueue(data);
    } catch (error) {
      console.error('[Queue] Failed to load queue:', error);
    }
  }

  /**
   * Display queue data grouped by periodical
   *
   * @param {Object} data - Queue data from API
   * @param {DownloadItem[]} data.queue - Array of queue items
   * @param {Object} data.status_counts - Status counts object
   * @returns {void}
   */
  displayQueue(data) {
    console.log('[Queue] displayQueue called');

    const emptyDiv = document.getElementById('queue-empty');
    const tableContainer = document.getElementById('queue-table-container');
    const tbody = document.getElementById('queue-body');
    const statsDiv = document.getElementById('queue-stats');

    // Get CSS variable colors
    const root = document.documentElement;
    const getColor = (name) => getComputedStyle(root).getPropertyValue(name).trim();

    const colors = {
      queued: getColor('--status-queued') || getColor('--status-pending'),
      pending: getColor('--status-pending'),
      downloading: getColor('--status-downloading'),
      completed: getColor('--status-completed'),
      failed: getColor('--status-failed'),
      skipped: getColor('--status-skipped'),
    };

    // Display status counts
    const { status_counts: statusCounts } = data;
    if (statusCounts) {
      const {
        queued = 0,
        pending = 0,
        downloading = 0,
        completed = 0,
        failed = 0,
        skipped = 0,
      } = statusCounts;

      statsDiv.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 15px;">
          <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div class="queue-stat-number" style="font-size: 1.5em; font-weight: bold; color: ${colors.queued};">${queued}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">Queued</div>
          </div>
          <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div class="queue-stat-number" style="font-size: 1.5em; font-weight: bold; color: ${colors.pending};">${pending}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">Pending</div>
          </div>
          <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div class="queue-stat-number" style="font-size: 1.5em; font-weight: bold; color: ${colors.downloading};">${downloading}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">Downloading</div>
          </div>
          <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div class="queue-stat-number" style="font-size: 1.5em; font-weight: bold; color: ${colors.completed};">${completed}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">Completed</div>
          </div>
          <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div class="queue-stat-number" style="font-size: 1.5em; font-weight: bold; color: ${colors.failed};">${failed}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">Failed</div>
          </div>
          <div style="background: var(--surface); padding: 15px; border-radius: 8px; border: 1px solid var(--border); text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
            <div class="queue-stat-number" style="font-size: 1.5em; font-weight: bold; color: ${colors.skipped};">${skipped}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary); margin-top: 5px;">Skipped</div>
          </div>
        </div>
      `;
    }

    // Filter downloads based on current filter
    let filteredDownloads = data.queue;
    if (this.currentFilter === 'queued') {
      filteredDownloads = data.queue.filter(({ status }) => status === 'queued');
    } else if (this.currentFilter === 'active') {
      filteredDownloads = data.queue.filter(
        ({ status }) => status === 'pending' || status === 'downloading'
      );
    } else if (this.currentFilter === 'failed') {
      filteredDownloads = data.queue.filter(({ status }) => status === 'failed');
    } else if (this.currentFilter === 'completed') {
      filteredDownloads = data.queue.filter(({ status }) => status === 'completed');
    }
    // 'all' filter shows everything

    if (filteredDownloads.length === 0) {
      emptyDiv.classList.remove(CSS_CLASSES.HIDDEN);
      tableContainer.classList.add(CSS_CLASSES.HIDDEN);

      // Update empty message based on filter
      const emptyMessage = emptyDiv.querySelector('p:first-of-type');
      if (emptyMessage) {
        const messages = {
          all: 'No downloads in queue',
          queued: 'No queued downloads',
          active: 'No active downloads',
          failed: 'No failed downloads',
          completed: 'No completed downloads',
        };
        emptyMessage.textContent = messages[this.currentFilter] || 'No downloads in queue';
      }
      return;
    }

    emptyDiv.classList.add(CSS_CLASSES.HIDDEN);
    tableContainer.classList.remove(CSS_CLASSES.HIDDEN);

    // Group by periodical
    const grouped = this.groupQueueByPeriodical(filteredDownloads);

    tbody.innerHTML = '';
    grouped.forEach((group) => {
      const { periodical, items } = group;

      // Create periodical header row
      const headerRow = document.createElement('tr');
      headerRow.style.background = 'var(--surface)';
      headerRow.style.cursor = 'pointer';
      headerRow.onclick = () => this.openManageQueueModal(periodical, items);

      const statusCounts = this.getStatusCounts(items);
      const statusBadges = Object.entries(statusCounts)
        .filter(([, count]) => count > 0)
        .map(([status, count]) => {
          const color = this.getStatusColor(status);
          return `<span style="background: ${color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; margin-right: 5px;">${count} ${status}</span>`;
        })
        .join('');

      headerRow.innerHTML = `
        <td colspan="5" style="padding: 12px; font-weight: bold; border-bottom: 2px solid var(--border-color);">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <span style="font-size: 1.1em;">\uD83D\uDCF0 ${periodical}</span>
              <span style="margin-left: 15px; font-size: 0.9em; color: var(--text-secondary);">${items.length} issues</span>
            </div>
            <div style="display: flex; gap: 10px; align-items: center;">
              ${statusBadges}
              <span style="font-size: 1.2em; color: var(--text-secondary);">\u2192</span>
            </div>
          </div>
        </td>
      `;
      tbody.appendChild(headerRow);
    });
  }

  /**
   * Group queue items by periodical
   *
   * @param {DownloadItem[]} queue - Array of queue items
   * @returns {DownloadGroup[]} Grouped queue items
   */
  groupQueueByPeriodical(queue) {
    const map = new Map();

    queue.forEach((item) => {
      const key = item.magazine ?? 'Unknown';
      if (!map.has(key)) {
        map.set(key, { periodical: key, items: [] });
      }
      map.get(key).items.push(item);
    });

    return Array.from(map.values()).sort((a, b) => b.items.length - a.items.length);
  }

  /**
   * Get status counts for an array of items
   *
   * @param {DownloadItem[]} items - Array of download items
   * @returns {Object.<string, number>} Object with status counts
   */
  getStatusCounts(items) {
    return items.reduce((counts, { status = 'unknown' }) => {
      counts[status] = (counts[status] ?? 0) + 1;
      return counts;
    }, {});
  }

  /**
   * Get color for a given status
   *
   * @param {string} status - The status string
   * @returns {string} CSS color value
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
    return colors[status] ?? '#6c757d';
  }

  /**
   * Get action buttons HTML for a queue item
   *
   * @param {DownloadItem} item - The download item
   * @returns {string} HTML string of action buttons
   */
  getQueueActionButtons(item) {
    const { status, submission_id: submissionId } = item;
    let buttons = '';

    if (status === 'failed') {
      buttons += `<button onclick="downloads.retryDownload(${submissionId})" class="btn-secondary" style="padding: 4px 8px; margin-right: 5px;">\uD83D\uDD04 Retry</button>`;
    }

    if (status !== 'completed') {
      buttons += `<button onclick="downloads.deleteQueueItem(${submissionId})" class="btn-secondary" style="background: var(--status-failed); padding: 4px 8px;">Remove</button>`;
    }

    return buttons || '-';
  }

  /**
   * Open modal to manage queue for a periodical
   *
   * @param {string} periodical - The periodical name
   * @param {DownloadItem[]} items - Array of download items
   * @returns {void}
   */
  openManageQueueModal(periodical, items) {
    this.currentModalItems = items;
    this.currentModalPeriodical = periodical;
    this.currentModalFilter = 'all';

    this.renderManageQueueModal();
  }

  /**
   * Render the manage queue modal with current filter
   *
   * @returns {void}
   * @private
   */
  renderManageQueueModal() {
    const {
      currentModalItems: items,
      currentModalPeriodical: periodical,
      currentModalFilter: filter = 'all',
    } = this;

    // Filter items based on current filter
    const filteredItems =
      filter === 'all' ? items : items.filter(({ status }) => status === filter);

    const statusCounts = this.getStatusCounts(items);
    const statusList = Object.entries(statusCounts)
      .map(([status, count]) => `${count} ${status}`)
      .join(', ');

    const filterButtons = ['all', 'pending', 'downloading', 'completed', 'failed', 'skipped']
      .map((f) => {
        const count = f === 'all' ? items.length : (statusCounts[f] ?? 0);
        const active = filter === f ? 'active' : '';
        return `<button onclick="downloads.filterModalQueue('${f}')" class="sort-btn ${active}">${f.charAt(0).toUpperCase() + f.slice(1)} (${count})</button>`;
      })
      .join('\n');

    let tableRows = '';
    if (filteredItems.length === 0) {
      tableRows = `
        <tr>
          <td colspan="3" style="padding: 40px; text-align: center; color: var(--text-secondary);">
            No ${filter === 'all' ? '' : filter} items found
          </td>
        </tr>
      `;
    } else {
      tableRows = filteredItems
        .map((item) => {
          const {
            title,
            magazine,
            submission_id: submissionId,
            created_at: createdAt,
            status,
          } = item;
          const statusColor = this.getStatusColor(status);

          // Add clarity if title equals magazine name
          let displayTitle = title;
          if (title === magazine || title === periodical) {
            const date = createdAt ? new Date(createdAt).toLocaleDateString() : '';
            displayTitle = `${title} <span style="color: var(--text-secondary); font-size: 0.85em;">(#${submissionId}${date ? ' - ' + date : ''})</span>`;
          }

          return `
          <tr>
            <td style="padding: 10px; border-bottom: 1px solid var(--border-color);">${displayTitle}</td>
            <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
              <span style="background: ${statusColor}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 0.85em;">${status}</span>
            </td>
            <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
              ${this.getQueueActionButtons(item)}
            </td>
          </tr>
        `;
        })
        .join('');
    }

    const html = `
      <div class="modal-header">
        <h3>Manage Downloads: ${periodical}</h3>
        <p style="color: var(--text-secondary); margin-top: 10px;">${items.length} issues - ${statusList}</p>
        <div id="modal-queue-status" class="hidden" style="margin-top: 10px;"></div>
        <div style="display: flex; gap: 5px; margin-top: 15px; flex-wrap: wrap;">
          ${filterButtons}
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
          <tbody>${tableRows}</tbody>
        </table>
      </div>
      <div class="modal-footer" style="display: flex; gap: 10px; justify-content: space-between; padding-top: 20px; border-top: 1px solid var(--border-color);">
        <div>
          <button onclick="downloads.bulkRetryQueue()" class="btn-secondary">\uD83D\uDD04 Retry Failed</button>
          <button onclick="downloads.bulkRemoveQueue()" class="btn-secondary" style="background: var(--status-failed);">\uD83D\uDDD1\uFE0F Remove All</button>
        </div>
        <button onclick="downloads.closeManageQueueModal()" class="save-btn">Close</button>
      </div>
    `;

    const container = document.getElementById('manage-queue-modal-content');
    if (container) {
      container.innerHTML = html;
      document.getElementById('manage-queue-modal')?.classList.remove(CSS_CLASSES.HIDDEN);
    }
  }

  /**
   * Filter items in the manage queue modal
   *
   * @param {string} status - The status to filter by ('all' or a specific status)
   * @returns {void}
   */
  filterModalQueue(status) {
    this.currentModalFilter = status;
    this.renderManageQueueModal();
  }

  /**
   * Close manage queue modal
   *
   * @returns {void}
   */
  closeManageQueueModal() {
    document.getElementById('manage-queue-modal')?.classList.add(CSS_CLASSES.HIDDEN);
    this.currentModalItems = null;
    this.currentModalPeriodical = null;
    this.currentModalFilter = 'all';
  }

  /**
   * Open modal to manage failed downloads for a periodical
   *
   * @param {string} periodical - The periodical name
   * @param {DownloadItem[]|string} items - Array of items or JSON string
   * @returns {void}
   */
  openManageFailedModal(periodical, items) {
    // Parse items if it's a string
    if (typeof items === 'string') {
      try {
        items = JSON.parse(items.replace(/&quot;/g, '"'));
      } catch (e) {
        console.error('[Downloads] Error parsing items:', e);
        return;
      }
    }

    this.currentModalItems = items;
    this.currentModalPeriodical = periodical;

    const badCount = items.filter((i) => i.isBad).length;
    const failedCount = items.filter((i) => !i.isBad).length;

    const tableRows = items
      .map((item) => {
        const { id, title, attempt_count: attemptCount, last_error: lastError, isBad } = item;
        const color = isBad ? 'var(--status-failed)' : 'orange';
        // maxRetries means "max retries allowed" so total attempts = maxRetries + 1
        const maxAttempts = this.maxRetries + 1;

        return `
        <tr>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color);">${title}</td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
            <span style="background: ${color}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 0.85em;">${attemptCount}/${maxAttempts}</span>
          </td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); font-size: 0.85em;">${lastError ?? 'Unknown'}</td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
            <button onclick="downloads.deleteFailedDownload(${id})" class="btn-secondary" style="background: var(--status-failed); padding: 4px 8px;">Remove</button>
          </td>
        </tr>
      `;
      })
      .join('');

    const html = `
      <div class="modal-header">
        <h3>Manage Failed Downloads: ${periodical}</h3>
        <p style="color: var(--text-secondary); margin-top: 10px;">${failedCount} recent failures, ${badCount} bad files</p>
        <div id="modal-failed-status" class="hidden" style="margin-top: 10px;"></div>
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
          <tbody>${tableRows}</tbody>
        </table>
      </div>
      <div class="modal-footer" style="display: flex; gap: 10px; justify-content: space-between; padding-top: 20px; border-top: 1px solid var(--border-color);">
        <button onclick="downloads.bulkRemoveFailed()" class="btn-secondary" style="background: var(--status-failed);">\uD83D\uDDD1\uFE0F Remove All</button>
        <button onclick="downloads.closeManageFailedModal()" class="save-btn">Close</button>
      </div>
    `;

    const container = document.getElementById('manage-failed-modal-content');
    if (container) {
      container.innerHTML = html;
      document.getElementById('manage-failed-modal')?.classList.remove(CSS_CLASSES.HIDDEN);
    }
  }

  /**
   * Close manage failed modal
   *
   * @returns {void}
   */
  closeManageFailedModal() {
    document.getElementById('manage-failed-modal')?.classList.add(CSS_CLASSES.HIDDEN);
    this.currentModalItems = null;
    this.currentModalPeriodical = null;
  }

  /**
   * Bulk retry failed downloads for current periodical
   *
   * @returns {Promise<void>}
   */
  async bulkRetryQueue() {
    if (!this.currentModalItems) return;

    const failedItems = this.currentModalItems.filter(({ status }) => status === 'failed');
    if (failedItems.length === 0) {
      UIUtils.showStatus('modal-queue-status', 'No failed items to retry', 'info');
      return;
    }

    const confirmed = await UIUtils.confirm(
      'Retry Downloads',
      `Retry ${failedItems.length} failed downloads for ${this.currentModalPeriodical}?`
    );
    if (!confirmed) return;

    const progress = UIUtils.showProgressModal('Retrying Downloads', failedItems.length);
    let succeeded = 0;
    let failed = 0;

    for (let i = 0; i < failedItems.length; i++) {
      const { submission_id: submissionId, issue } = failedItems[i];
      try {
        progress.update(i + 1, 'Retrying...', `Processing: ${issue ?? 'Unknown'}`);
        const response = await APIClient.authenticatedFetch(
          `/api/downloads/queue/retry/${submissionId}`,
          { method: 'POST' }
        );
        const data = await response.json();
        if (data.success) {
          succeeded++;
        } else {
          failed++;
        }
      } catch (e) {
        console.error('[Downloads] Retry failed:', e);
        failed++;
      }
    }

    const message =
      failed > 0
        ? `Retried ${succeeded} of ${failedItems.length} downloads (${failed} failed)`
        : `Successfully retried all ${succeeded} downloads`;
    progress.complete(message, failed === 0);

    UIUtils.showStatus('modal-queue-status', message, failed === 0 ? 'success' : 'warning');
    setTimeout(() => {
      this.closeManageQueueModal();
      this.loadDownloadQueue();
    }, 2000);
  }

  /**
   * Bulk remove all downloads for current periodical
   *
   * @returns {Promise<void>}
   */
  async bulkRemoveQueue() {
    if (!this.currentModalItems) return;

    const confirmed = await UIUtils.confirm(
      'Remove All Downloads',
      `Remove ALL ${this.currentModalItems.length} downloads for ${this.currentModalPeriodical}? This cannot be undone.`
    );
    if (!confirmed) return;

    const progress = UIUtils.showProgressModal('Removing Downloads', this.currentModalItems.length);
    let succeeded = 0;
    let failed = 0;

    for (let i = 0; i < this.currentModalItems.length; i++) {
      const { submission_id: submissionId, issue } = this.currentModalItems[i];
      try {
        progress.update(i + 1, 'Deleting...', `Processing: ${issue ?? 'Unknown'}`);
        const response = await APIClient.authenticatedFetch(
          `/api/downloads/queue/${submissionId}`,
          { method: 'DELETE' }
        );
        const data = await response.json();
        if (data.success) {
          succeeded++;
        } else {
          failed++;
        }
      } catch (e) {
        console.error('[Downloads] Remove failed:', e);
        failed++;
      }
    }

    const message =
      failed > 0
        ? `Removed ${succeeded} of ${this.currentModalItems.length} downloads (${failed} failed)`
        : `Successfully removed all ${succeeded} downloads`;
    progress.complete(message, failed === 0);

    UIUtils.showStatus('modal-queue-status', message, failed === 0 ? 'success' : 'warning');
    setTimeout(() => {
      this.closeManageQueueModal();
      this.loadDownloadQueue();
    }, 2000);
  }

  /**
   * Bulk remove all failed downloads for current periodical
   *
   * @returns {Promise<void>}
   */
  async bulkRemoveFailed() {
    if (!this.currentModalItems) return;

    const confirmed = await UIUtils.confirm(
      'Remove All Failed',
      `Remove ALL ${this.currentModalItems.length} failed downloads for ${this.currentModalPeriodical}? This cannot be undone.`
    );
    if (!confirmed) return;

    const progress = UIUtils.showProgressModal(
      'Removing Failed Downloads',
      this.currentModalItems.length
    );
    let succeeded = 0;
    let failed = 0;

    for (let i = 0; i < this.currentModalItems.length; i++) {
      const { id, issue } = this.currentModalItems[i];
      try {
        progress.update(i + 1, 'Deleting...', `Processing: ${issue ?? 'Unknown'}`);
        const response = await APIClient.authenticatedFetch(`/api/downloads/failed/${id}`, {
          method: 'DELETE',
        });
        const data = await response.json();
        if (data.success) {
          succeeded++;
        } else {
          failed++;
        }
      } catch (e) {
        console.error('[Downloads] Remove failed:', e);
        failed++;
      }
    }

    const message =
      failed > 0
        ? `Removed ${succeeded} of ${this.currentModalItems.length} failed downloads (${failed} failed)`
        : `Successfully removed all ${succeeded} failed downloads`;
    progress.complete(message, failed === 0);

    UIUtils.showStatus('modal-failed-status', message, failed === 0 ? 'success' : 'warning');
    setTimeout(() => {
      this.closeManageFailedModal();
      this.loadFailedDownloads();
    }, 2000);
  }

  /**
   * Retry a failed download
   *
   * @param {number} submissionId - The submission ID to retry
   * @returns {Promise<void>}
   */
  async retryDownload(submissionId) {
    const confirmed = await UIUtils.confirm(
      'Retry Download',
      'Are you sure you want to retry this download?'
    );
    if (!confirmed) return;

    // Determine which status element to use
    const queueModal = document.getElementById('manage-queue-modal');
    const failedModal = document.getElementById('manage-failed-modal');

    let statusId = 'downloads-status';
    if (queueModal && !queueModal.classList.contains('hidden')) {
      statusId = 'modal-queue-status';
    } else if (failedModal && !failedModal.classList.contains('hidden')) {
      statusId = 'modal-failed-status';
    }

    try {
      const response = await APIClient.authenticatedFetch(
        `/api/downloads/queue/retry/${submissionId}`,
        { method: 'POST' }
      );
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus(statusId, data.message, 'success');
        setTimeout(() => UIUtils.hideStatus(statusId), 3000);
        this.loadDownloadQueue();
      } else {
        UIUtils.showStatus(statusId, data.message ?? 'Failed to retry', 'error');
      }
    } catch (error) {
      console.error('[Downloads] Error retrying download:', error);
      UIUtils.showStatus(statusId, error.message, 'error');
    }
  }

  /**
   * Remove a submission from queue
   *
   * @param {number} submissionId - The submission ID to remove
   * @returns {Promise<void>}
   */
  async removeFromQueue(submissionId) {
    const confirmed = await UIUtils.confirm(
      'Remove Item',
      'Are you sure you want to remove this item from the queue? This cannot be undone.'
    );
    if (!confirmed) return;

    // Determine which status element to use
    const queueModal = document.getElementById('manage-queue-modal');
    const failedModal = document.getElementById('manage-failed-modal');

    let statusId = 'downloads-status';
    if (queueModal && !queueModal.classList.contains('hidden')) {
      statusId = 'modal-queue-status';
    } else if (failedModal && !failedModal.classList.contains('hidden')) {
      statusId = 'modal-failed-status';
    }

    try {
      const response = await APIClient.authenticatedFetch(`/api/downloads/queue/${submissionId}`, {
        method: 'DELETE',
      });
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus(statusId, data.message, 'success');
        setTimeout(() => UIUtils.hideStatus(statusId), 3000);
        this.loadDownloadQueue();
      } else {
        UIUtils.showStatus(statusId, data.message ?? 'Failed to remove', 'error');
      }
    } catch (error) {
      console.error('[Downloads] Error removing from queue:', error);
      UIUtils.showStatus(statusId, error.message, 'error');
    }
  }

  /**
   * Alias for removeFromQueue (used by action buttons)
   *
   * @param {number} submissionId - The submission ID to delete
   * @returns {Promise<void>}
   */
  async deleteQueueItem(submissionId) {
    return this.removeFromQueue(submissionId);
  }

  /**
   * Open cleanup modal
   *
   * @returns {void}
   */
  openCleanupModal() {
    UIUtils.showModal('cleanup-queue-modal');
  }

  /**
   * Close cleanup modal
   *
   * @returns {void}
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
   *
   * @returns {Promise<void>}
   */
  async previewCleanup() {
    const statusSelect = document.getElementById('cleanup-status');
    const hoursInput = document.getElementById('cleanup-hours');

    const status = statusSelect?.value ?? '';
    const hours = parseInt(hoursInput?.value, 10) || 24;

    try {
      const response = await APIClient.authenticatedFetch('/api/downloads/queue/all');
      const data = await response.json();

      const now = new Date();
      const count = data.queue.filter((item) => {
        const updatedTime = new Date(item.updated_at);
        const hoursDiff = (now - updatedTime) / (1000 * 60 * 60);

        if (hoursDiff > hours) {
          return !status || item.status === status;
        }
        return false;
      }).length;

      const preview = document.getElementById('cleanup-preview');
      const countDiv = document.getElementById('cleanup-count');

      if (preview) preview.style.display = 'block';
      if (countDiv) {
        countDiv.textContent = `${count} item${count !== 1 ? 's' : ''} older than ${hours} hours with status "${status || 'any'}"`;
      }
    } catch (error) {
      console.error('[Downloads] Error previewing cleanup:', error);
    }
  }

  /**
   * Execute cleanup
   *
   * @returns {Promise<void>}
   */
  async executeCleanup() {
    const statusSelect = document.getElementById('cleanup-status');
    const hoursInput = document.getElementById('cleanup-hours');

    const status = statusSelect?.value ?? '';
    const hours = parseInt(hoursInput?.value, 10) || 24;

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
        UIUtils.showStatus('downloads-status', data.message ?? 'Cleanup failed', 'error');
      }
    } catch (error) {
      console.error('[Downloads] Error executing cleanup:', error);
      UIUtils.showStatus('downloads-status', error.message, 'error');
    }
  }

  /**
   * Start auto-refresh for the tasks tab
   *
   * @returns {void}
   */
  startAutoRefresh() {
    this.stopAutoRefresh();

    this.refreshInterval = setInterval(() => {
      const tasksTab = document.getElementById('tasks-tab');
      if (tasksTab?.classList.contains('active')) {
        this.loadDownloadQueue();
      } else {
        this.stopAutoRefresh();
      }
    }, 5000);
  }

  /**
   * Stop auto-refresh
   *
   * @returns {void}
   */
  stopAutoRefresh() {
    if (this.refreshInterval) {
      clearInterval(this.refreshInterval);
      this.refreshInterval = null;
    }
  }

  /**
   * Clear all pending downloads from the queue
   *
   * @returns {Promise<void>}
   */
  async clearPendingDownloads() {
    try {
      // Confirm before clearing
      const confirmed = await UIUtils.confirm(
        'Clear Pending Downloads',
        'Are you sure you want to clear all pending downloads? This cannot be undone.'
      );

      if (!confirmed) {
        return;
      }

      UIUtils.showStatus('downloads-status', '🗑️ Clearing pending downloads...', 'info');

      const response = await APIClient.authenticatedFetch('/api/downloads/queue/pending', {
        method: 'DELETE',
      });

      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('downloads-status', data.message, 'success');
        setTimeout(() => {
          UIUtils.hideStatus('downloads-status');
          this.loadDownloadQueue(); // Refresh the queue
        }, 2000);
      } else {
        UIUtils.showStatus('downloads-status', data.message || 'Failed to clear pending', 'error');
      }
    } catch (error) {
      console.error('[Downloads] Error clearing pending downloads:', error);
      UIUtils.showStatus('downloads-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Set the current filter for the download queue
   *
   * @param {string} filter - Filter type (all, active, failed, completed)
   * @returns {void}
   */
  setFilter(filter) {
    this.currentFilter = filter;

    // Update button states
    document.querySelectorAll('#download-queue-view .filter-btn').forEach((btn) => {
      btn.classList.remove('active');
    });
    const activeBtn = document.getElementById(`download-filter-${filter}`);
    if (activeBtn) {
      activeBtn.classList.add('active');
    }

    // Reload queue with new filter
    this.loadDownloadQueue();
  }

  /**
   * Clear all queued downloads from the queue
   *
   * @returns {Promise<void>}
   */
  async clearQueuedDownloads() {
    try {
      // Confirm before clearing
      const confirmed = await UIUtils.confirm(
        'Clear Queued Downloads',
        'Are you sure you want to clear all queued downloads? This cannot be undone.'
      );

      if (!confirmed) {
        return;
      }

      UIUtils.showStatus('downloads-status', '🗑️ Clearing queued downloads...', 'info');

      const response = await APIClient.authenticatedFetch('/api/downloads/queue/queued', {
        method: 'DELETE',
      });

      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('downloads-status', data.message, 'success');
        setTimeout(() => {
          UIUtils.hideStatus('downloads-status');
          this.loadDownloadQueue(); // Refresh the queue
        }, 2000);
      } else {
        throw new Error(data.message ?? 'Failed to clear queued downloads');
      }
    } catch (error) {
      console.error('[Downloads] Failed to clear queued downloads:', error);
      UIUtils.showStatus('downloads-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Clear all failed downloads from the queue
   *
   * @returns {Promise<void>}
   */
  async clearFailedDownloads() {
    try {
      // Confirm before clearing
      const confirmed = await UIUtils.confirm(
        'Clear Failed Downloads',
        'Are you sure you want to clear all failed downloads? This cannot be undone.'
      );

      if (!confirmed) {
        return;
      }

      UIUtils.showStatus('downloads-status', '🗑️ Clearing failed downloads...', 'info');

      const response = await APIClient.authenticatedFetch('/api/downloads/queue/failed', {
        method: 'DELETE',
      });

      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('downloads-status', data.message, 'success');
        setTimeout(() => {
          UIUtils.hideStatus('downloads-status');
          this.loadDownloadQueue(); // Refresh the queue
        }, 2000);
      } else {
        UIUtils.showStatus(
          'downloads-status',
          data.message || 'Failed to clear failed downloads',
          'error'
        );
      }
    } catch (error) {
      console.error('[Downloads] Error clearing failed downloads:', error);
      UIUtils.showStatus('downloads-status', `Error: ${error.message}`, 'error');
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
window.clearPendingDownloads = () => downloads.clearPendingDownloads();
