/**
 * Downloads Module
 * Handles download queue management, failed downloads, and cleanup operations
 * @module downloads
 */

import { APIClient, APIHelper } from '../core/api.js?v=1767733177';
import { UIUtils } from '../core/ui-utils.js?v=1767733177';
import {
  ELEMENT_IDS as _ELEMENT_IDS,
  STATUS_MESSAGES as _STATUS_MESSAGES,
  CSS_CLASSES,
  TIMEOUTS as _TIMEOUTS,
} from '../core/constants.js';

/**
 * @typedef {Object} DiscoveredIssue
 * @property {number} id - Unique identifier
 * @property {number} tracking_id - Tracking ID for the periodical
 * @property {string} title - Issue title
 * @property {string} tracking_title - Associated periodical name
 * @property {string} download_status - Current status (discovered, wanted, queued, downloading, completed, failed, permanently_failed, ignored)
 * @property {number} download_attempts - Number of download attempts
 * @property {string} [last_error] - Last error message
 * @property {string} [first_seen] - First discovery timestamp
 * @property {string} [last_seen] - Last seen timestamp
 * @property {number} download_priority - Priority score
 * @property {boolean} [isPermanentlyFailed] - Whether marked as permanently failed
 */

/**
 * @typedef {Object} DownloadGroup
 * @property {string} periodical - Periodical name
 * @property {DiscoveredIssue[]} items - Issues in this group
 * @property {number} failedCount - Number of failed issues
 * @property {number} permanentlyFailedCount - Number of permanently failed issues
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
    /** @type {boolean} Whether to include permanently failed issues in display */
    this.showPermanentlyFailed = true;
    /** @type {number} Maximum download retry attempts */
    this.maxRetries = 3; // Default value, will be loaded from API
    /** @type {DiscoveredIssue[]|null} Current items in modal */
    this.currentModalItems = null;
    /** @type {string|null} Current periodical in modal */
    this.currentModalPeriodical = null;
    /** @type {string} Current filter in modal */
    this.currentModalFilter = 'all';
    /** @type {string} Current filter for queue view (all, queued, pending, downloading, completed, failed, skipped) */
    this.currentFilter = 'all';
    /** @type {string} Current sort field for queue view (title, status, priority, created_at) */
    this.currentSort = 'title';
    /** @type {boolean} Current sort order (true = ascending, false = descending) */
    this.sortAscending = true;

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
      }, 'Downloads');
      if (data.success && data.max_download_retries) {
        this.maxRetries = data.max_download_retries;
      }
    } catch (error) {
      console.warn('[Downloads] Failed to load constants, using defaults:', error);
    }
  }

  /**
   * Load failed and permanently failed issues from the API
   *
   * @returns {Promise<void>}
   * @throws {Error} When API request fails
   *
   * @example
   * await downloads.loadFailedDownloads();
   */
  async loadFailedDownloads() {
    try {
      // Fetch failed and permanently_failed issues
      const statuses = this.showPermanentlyFailed ? 'failed,permanently_failed' : 'failed';
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/discovered-issues?status=${statuses}&limit=500`
          );
          return await response.json();
        },
        'Downloads',
        'downloads-status'
      );
      this.displayFailedDownloads(data);
    } catch (error) {
      // Already logged and displayed by APIHelper
    }
  }

  /**
   * Display failed and permanently failed issues grouped by periodical
   *
   * @param {Object} data - Response data from API
   * @param {DiscoveredIssue[]} data.issues - Array of discovered issues
   * @returns {void}
   */
  displayFailedDownloads(data) {
    const container = document.getElementById('failed-downloads-container');
    if (!container) return;

    const issues = data.issues || [];
    const grouped = this.groupIssuesByPeriodical(issues);

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
    const totalPermanentlyFailed = grouped.reduce((sum, g) => sum + g.permanentlyFailedCount, 0);

    let html = `
      <div class="${CSS_CLASSES.STATS_SUMMARY}">
        <div class="${CSS_CLASSES.STAT_BOX}">
          <div class="${CSS_CLASSES.STAT_BOX_VALUE} stat-box-warning">${totalFailed}</div>
          <div class="${CSS_CLASSES.STAT_BOX_LABEL}">Failed Downloads</div>
          <div class="${CSS_CLASSES.STAT_BOX_SUBLABEL}">Can be retried</div>
        </div>
        <div class="${CSS_CLASSES.STAT_BOX}">
          <div class="${CSS_CLASSES.STAT_BOX_VALUE} stat-box-error">${totalPermanentlyFailed}</div>
          <div class="${CSS_CLASSES.STAT_BOX_LABEL}">Permanently Failed</div>
          <div class="${CSS_CLASSES.STAT_BOX_SUBLABEL}">3+ failures, needs review</div>
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
      const { periodical, permanentlyFailedCount, failedCount, totalCount, items } = group;
      const hasPermanentlyFailed = permanentlyFailedCount > 0;
      const icon = hasPermanentlyFailed ? '\uD83D\uDEAB' : '\u26A0\uFE0F';

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
              ${hasPermanentlyFailed ? `<span class="badge badge-error">${permanentlyFailedCount} Permanently Failed</span>` : ''}
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
   * Group discovered issues by periodical name
   *
   * @param {DiscoveredIssue[]} issues - Array of discovered issues
   * @returns {DownloadGroup[]} Grouped issues sorted by total count
   */
  groupIssuesByPeriodical(issues) {
    const map = new Map();

    issues.forEach((issue) => {
      const key = issue.tracking_title ?? 'Unknown';
      if (!map.has(key)) {
        map.set(key, {
          periodical: key,
          items: [],
          failedCount: 0,
          permanentlyFailedCount: 0,
          totalCount: 0,
        });
      }
      const group = map.get(key);
      const isPermanentlyFailed = issue.download_status === 'permanently_failed';
      group.items.push({ ...issue, isPermanentlyFailed });

      if (isPermanentlyFailed) {
        group.permanentlyFailedCount++;
      } else {
        group.failedCount++;
      }
      group.totalCount++;
    });

    return Array.from(map.values()).sort((a, b) => b.totalCount - a.totalCount);
  }

  /**
   * Retry a failed or permanently failed issue
   *
   * @param {number} issueId - The discovered issue ID to retry
   * @returns {Promise<void>}
   *
   * @example
   * await downloads.retryFailedIssue(123);
   */
  async retryFailedIssue(issueId) {
    const confirmed = await UIUtils.confirm(
      'Retry Download',
      'Reset this issue and attempt to download it again?'
    );
    if (!confirmed) return;

    // Determine which status element to use (modal or base page)
    const failedModal = document.getElementById('manage-failed-modal');
    const statusId =
      failedModal && !failedModal.classList.contains('hidden')
        ? 'modal-failed-status'
        : 'downloads-status';

    try {
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/discovered-issues/${issueId}/retry`,
            {
              method: 'POST',
            }
          );
          return await response.json();
        },
        'Downloads',
        statusId
      );

      if (data.success) {
        UIUtils.showStatus(statusId, 'Issue reset and queued for retry', 'success');
        this.loadFailedDownloads();
      } else {
        throw new Error(data.message ?? 'Failed to retry');
      }
    } catch (error) {
      // Already logged and displayed by APIHelper
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

      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.authenticatedFetch(url);
        return await response.json();
      }, 'Downloads');

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
        <div class="queue-stats-grid">
          <div class="queue-stat-item" title="Waiting for download slot (not yet sent to client)">
            <div class="queue-stat-number" style="color: ${colors.queued};">${queued}</div>
            <div class="queue-stat-label">Queued</div>
            <div class="queue-stat-desc">Waiting for slot</div>
          </div>
          <div class="queue-stat-item" title="Sent to download client, waiting to start">
            <div class="queue-stat-number" style="color: ${colors.pending};">${pending}</div>
            <div class="queue-stat-label">Pending</div>
            <div class="queue-stat-desc">Sent to client</div>
          </div>
          <div class="queue-stat-item" title="Actively downloading">
            <div class="queue-stat-number" style="color: ${colors.downloading};">${downloading}</div>
            <div class="queue-stat-label">DL</div>
            <div class="queue-stat-desc">In progress</div>
          </div>
          <div class="queue-stat-item" title="Successfully downloaded">
            <div class="queue-stat-number" style="color: ${colors.completed};">${completed}</div>
            <div class="queue-stat-label">Done</div>
            <div class="queue-stat-desc">Completed</div>
          </div>
          <div class="queue-stat-item" title="Download failed">
            <div class="queue-stat-number" style="color: ${colors.failed};">${failed}</div>
            <div class="queue-stat-label">Failed</div>
            <div class="queue-stat-desc">Error occurred</div>
          </div>
          <div class="queue-stat-item" title="Skipped">
            <div class="queue-stat-number" style="color: ${colors.skipped};">${skipped}</div>
            <div class="queue-stat-label">Skip</div>
            <div class="queue-stat-desc">Not downloaded</div>
          </div>
        </div>
      `;
    }

    // Filter downloads based on current filter
    let filteredDownloads = data.queue;
    if (this.currentFilter === 'queued') {
      filteredDownloads = data.queue.filter(({ status }) => status === 'queued');
    } else if (this.currentFilter === 'pending') {
      filteredDownloads = data.queue.filter(({ status }) => status === 'pending');
    } else if (this.currentFilter === 'downloading') {
      filteredDownloads = data.queue.filter(({ status }) => status === 'downloading');
    } else if (this.currentFilter === 'failed') {
      filteredDownloads = data.queue.filter(({ status }) => status === 'failed');
    } else if (this.currentFilter === 'completed') {
      filteredDownloads = data.queue.filter(({ status }) => status === 'completed');
    } else if (this.currentFilter === 'skipped') {
      filteredDownloads = data.queue.filter(({ status }) => status === 'skipped');
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
          pending: 'No pending downloads',
          downloading: 'No downloads in progress',
          failed: 'No failed downloads',
          completed: 'No completed downloads',
          skipped: 'No skipped downloads',
        };
        emptyMessage.textContent = messages[this.currentFilter] || 'No downloads in queue';
      }
      return;
    }

    emptyDiv.classList.add(CSS_CLASSES.HIDDEN);
    tableContainer.classList.remove(CSS_CLASSES.HIDDEN);

    // Group by periodical
    const grouped = this.groupQueueByPeriodical(filteredDownloads);

    // Sort items within each group
    grouped.forEach((group) => {
      group.items = this.sortItems(group.items);
    });

    // Sort the groups themselves based on the first item in each group
    if (this.currentSort !== 'title') {
      // For non-title sorts, sort groups by the first item's sort field
      grouped.sort((a, b) => {
        if (a.items.length === 0 || b.items.length === 0) return 0;
        
        const firstA = a.items[0];
        const firstB = b.items[0];
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

    tbody.innerHTML = '';
    grouped.forEach((group) => {
      const { periodical, items } = group;

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
      headerRow.onclick = () => this.openManageQueueModal(periodical, items);

      const statusCounts = this.getStatusCounts(items);
      const statusBadges = Object.entries(statusCounts)
        .filter(([, count]) => count > 0)
        .map(([status, count]) => {
          const color = this.getStatusColor(status);
          return `<span style="background: ${color}; color: white; padding: 2px 8px; border-radius: 12px; font-size: 0.85em; margin-right: 5px;">${count} ${status}</span>`;
        })
        .join('');

      // Check for rate limiting and get longest wait time
      const waitInfo = this.getLongestWaitTime(items);
      const waitTimeNote = waitInfo
        ? `<div style="font-size: 0.8em; color: var(--status-failed); margin-top: 4px; font-weight: 600; display: flex; align-items: center; gap: 5px;">
             <span style="font-size: 1.2em;">⏱️</span>
             <span>Longest wait: ${this.formatWaitTime(waitInfo.waitTime)}</span>
             ${waitInfo.count > 1 ? `<span style="font-size: 0.85em; color: var(--text-secondary); font-weight: normal;">(${waitInfo.count} rate limited)</span>` : ''}
           </div>`
        : '';

      headerRow.innerHTML = `
        <td colspan="2" style="padding: 12px; font-weight: bold;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <span style="font-size: 1.1em;">\uD83D\uDCF0 ${periodical}</span>
              <span style="margin-left: 15px; font-size: 0.9em; color: var(--text-secondary);">${items.length} issues</span>
            </div>
            <div style="display: flex; flex-direction: column; gap: 5px; align-items: flex-end;">
              <div style="display: flex; gap: 10px; align-items: center;">
                ${statusBadges}
                <span style="font-size: 1.2em; color: var(--text-secondary);">\u2192</span>
              </div>
              ${waitTimeNote}
            </div>
          </div>
        </td>
      `;
      tbody.appendChild(headerRow);
    });
  }

  /**
   * Format seconds into human-readable time
   *
   * @param {number} seconds - Time in seconds
   * @returns {string} Formatted time (e.g., "2h 58m", "45m", "30s")
   */
  formatWaitTime(seconds) {
    if (seconds < 60) {
      return `${seconds}s`;
    }
    if (seconds < 3600) {
      const minutes = Math.floor(seconds / 60);
      return `${minutes}m`;
    }
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    if (minutes === 0) {
      return `${hours}h`;
    }
    return `${hours}h ${minutes}m`;
  }

  /**
   * Extract wait time in seconds from extra_status message
   *
   * @param {string} extraStatus - The extra_status field (e.g., "Provider rate limit: waiting 178s (~0.0h)")
   * @returns {number|null} Wait time in seconds, or null if not found
   */
  parseWaitTime(extraStatus) {
    if (!extraStatus) return null;
    // Match patterns like "waiting 178s" or "waiting 178 seconds"
    const match = extraStatus.match(/waiting (\d+)s/);
    return match ? parseInt(match[1], 10) : null;
  }

  /**
   * Get longest wait time from a list of items
   *
   * @param {DownloadItem[]} items - Array of download items
   * @returns {{waitTime: number, count: number}|null} Longest wait time info or null
   */
  getLongestWaitTime(items) {
    const rateLimitedItems = items.filter((item) => item.extra_status);
    if (rateLimitedItems.length === 0) return null;

    let maxWaitTime = 0;
    rateLimitedItems.forEach((item) => {
      const waitTime = this.parseWaitTime(item.extra_status);
      if (waitTime && waitTime > maxWaitTime) {
        maxWaitTime = waitTime;
      }
    });

    return maxWaitTime > 0 ? { waitTime: maxWaitTime, count: rateLimitedItems.length } : null;
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

    // Get wait time info for the modal header
    const waitInfo = this.getLongestWaitTime(items);
    const waitTimeAlert = waitInfo
      ? `<div style="background: var(--surface-variant); padding: 10px; border-radius: 6px; margin-top: 10px; border-left: 3px solid var(--status-failed);">
           <div style="display: flex; align-items: center; gap: 8px;">
             <span style="font-size: 1.3em;">⏱️</span>
             <div>
               <div style="font-weight: 600; color: var(--status-failed);">Rate Limited</div>
               <div style="font-size: 0.85em; color: var(--text-secondary);">
                 ${waitInfo.count} issue${waitInfo.count !== 1 ? 's' : ''} waiting - longest: ${this.formatWaitTime(waitInfo.waitTime)}
               </div>
             </div>
           </div>
         </div>`
      : '';

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
            error,
          } = item;
          const statusColor = this.getStatusColor(status);

          // Add clarity if title equals magazine name
          let displayTitle = title;
          if (title === magazine || title === periodical) {
            const date = createdAt ? new Date(createdAt).toLocaleDateString() : '';
            displayTitle = `${title} <span style="color: var(--text-secondary); font-size: 0.85em;">(#${submissionId}${date ? ' - ' + date : ''})</span>`;
          }

          // Build status info with error or extra_status
          let statusInfo = `<span style="background: ${statusColor}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 0.85em;">${status}</span>`;

          // Show error message for failed items
          if (status === 'failed' && error) {
            statusInfo += `<div style="font-size: 0.75em; color: var(--status-failed); margin-top: 4px; font-style: italic;">❌ ${error}</div>`;
          }
          // Show extra_status for rate limiting or other info
          else if (item.extra_status) {
            statusInfo += `<div style="font-size: 0.75em; color: var(--text-secondary); margin-top: 4px; font-style: italic;">⏱️ ${item.extra_status}</div>`;
          }

          return `
          <tr>
            <td style="padding: 10px; border-bottom: 1px solid var(--border-color);">${displayTitle}</td>
            <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
              ${statusInfo}
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
        ${waitTimeAlert}
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
   * @param {DiscoveredIssue[]|string} items - Array of items or JSON string
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

    const permanentlyFailedCount = items.filter((i) => i.isPermanentlyFailed).length;
    const failedCount = items.filter((i) => !i.isPermanentlyFailed).length;

    const tableRows = items
      .map((item) => {
        const {
          id,
          title,
          max_retries: itemMaxRetries,
          last_error: lastError,
          isPermanentlyFailed,
        } = item;
        const attemptCount = item.download_attempts || item.attempt_count || item.attempts || 0;
        const color = isPermanentlyFailed ? 'var(--status-failed)' : 'orange';
        // Use per-issue max_retries if available, otherwise fall back to global
        // maxRetries means "max retries allowed" so total attempts = maxRetries + 1
        const maxRetries = itemMaxRetries !== undefined ? itemMaxRetries : this.maxRetries;
        const maxAttempts = maxRetries + 1;

        return `
        <tr>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color);">${title}</td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
            <span style="background: ${color}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 0.85em;">${attemptCount}/${maxAttempts}</span>
          </td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); font-size: 0.85em;">${lastError ?? 'Unknown'}</td>
          <td style="padding: 10px; border-bottom: 1px solid var(--border-color); text-align: center;">
            <button onclick="downloads.retryFailedIssue(${id})" class="btn-primary" style="padding: 4px 8px;">Retry</button>
          </td>
        </tr>
      `;
      })
      .join('');

    const html = `
      <div class="modal-header">
        <h3>Manage Failed Downloads: ${periodical}</h3>
        <p style="color: var(--text-secondary); margin-top: 10px;">${failedCount} recent failures, ${permanentlyFailedCount} permanently failed</p>
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
        <button onclick="downloads.bulkRetryFailed()" class="btn-primary">\u27F3 Retry All</button>
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

    const failedItems = this.currentModalItems.filter(
      ({ download_status }) =>
        download_status === 'failed' || download_status === 'permanently_failed'
    );
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
        const data = await APIHelper.executeWithErrorHandling(async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/downloads/queue/retry/${submissionId}`,
            { method: 'POST' }
          );
          return await response.json();
        }, 'Downloads');
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
        const data = await APIHelper.executeWithErrorHandling(async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/downloads/queue/${submissionId}`,
            { method: 'DELETE' }
          );
          return await response.json();
        }, 'Downloads');
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
   * Bulk retry all failed issues for current periodical
   *
   * @returns {Promise<void>}
   */
  async bulkRetryFailed() {
    if (!this.currentModalItems) return;

    const confirmed = await UIUtils.confirm(
      'Retry All Failed',
      `Retry ALL ${this.currentModalItems.length} failed issues for ${this.currentModalPeriodical}?`
    );
    if (!confirmed) return;

    const progress = UIUtils.showProgressModal(
      'Retrying Failed Issues',
      this.currentModalItems.length
    );
    let succeeded = 0;
    let failed = 0;

    for (let i = 0; i < this.currentModalItems.length; i++) {
      const { id, title } = this.currentModalItems[i];
      try {
        progress.update(i + 1, 'Retrying...', `Processing: ${title ?? 'Unknown'}`);
        const data = await APIHelper.executeWithErrorHandling(async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/discovered-issues/${id}/retry`,
            {
              method: 'POST',
            }
          );
          return await response.json();
        }, 'Downloads');
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
        ? `Retried ${succeeded} of ${this.currentModalItems.length} issues (${failed} failed)`
        : `Successfully retried all ${succeeded} issues`;
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
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/downloads/queue/retry/${submissionId}`,
            { method: 'POST' }
          );
          return await response.json();
        },
        'Downloads',
        statusId
      );

      if (data.success) {
        UIUtils.showStatus(statusId, data.message, 'success');
        setTimeout(() => UIUtils.hideStatus(statusId), 3000);
        this.loadDownloadQueue();
      } else {
        UIUtils.showStatus(statusId, data.message ?? 'Failed to retry', 'error');
      }
    } catch (error) {
      // Already logged by APIHelper
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
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/downloads/queue/${submissionId}`,
            {
              method: 'DELETE',
            }
          );
          return await response.json();
        },
        'Downloads',
        statusId
      );

      if (data.success) {
        UIUtils.showStatus(statusId, data.message, 'success');
        setTimeout(() => UIUtils.hideStatus(statusId), 3000);
        this.loadDownloadQueue();
      } else {
        UIUtils.showStatus(statusId, data.message ?? 'Failed to remove', 'error');
      }
    } catch (error) {
      // Already logged by APIHelper
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
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.authenticatedFetch('/api/downloads/queue/all');
        return await response.json();
      }, 'Downloads');

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
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch('/api/downloads/queue/cleanup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              status: status || undefined,
              older_than_hours: hours,
            }),
          });
          return await response.json();
        },
        'Downloads',
        'downloads-status'
      );

      if (data.success) {
        UIUtils.showStatus('downloads-status', data.message, 'success');
        setTimeout(() => UIUtils.hideStatus('downloads-status'), 3000);
        this.closeCleanupModal();
        this.loadDownloadQueue();
      } else {
        UIUtils.showStatus('downloads-status', data.message ?? 'Cleanup failed', 'error');
      }
    } catch (error) {
      // Already logged by APIHelper
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

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch('/api/downloads/queue/pending', {
            method: 'DELETE',
          });
          return await response.json();
        },
        'Downloads',
        'downloads-status'
      );

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
      // Already logged by APIHelper
    }
  }

  /**
   * Set the current filter for the download queue
   *
   * @param {string} filter - Filter type (all, queued, pending, downloading, completed, failed, skipped)
   * @returns {void}
   */
  setFilter(filter) {
    this.currentFilter = filter;

    // Save to localStorage in combined settings object
    try {
      const saved = localStorage.getItem('downloadQueueSettings');
      const settings = saved ? JSON.parse(saved) : {};
      settings.filter = { status: filter };
      localStorage.setItem('downloadQueueSettings', JSON.stringify(settings));
    } catch (error) {
      console.warn('[Downloads] Failed to save filter:', error);
    }

    // Update dropdown
    const dropdown = document.getElementById('download-status-filter');
    if (dropdown) {
      dropdown.value = filter;
    }

    // Update button states (for backward compatibility with old buttons)
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
   * Load filter preference from localStorage
   * @returns {void}
   */
  loadFilterPreference() {
    try {
      const saved = localStorage.getItem('downloadQueueSettings');
      if (saved) {
        const settings = JSON.parse(saved);
        this.currentFilter = settings.filter?.status || 'all';
      }
    } catch (error) {
      console.warn('[Downloads] Failed to parse filter preference:', error);
    }
    // Update dropdown on page load
    setTimeout(() => {
      const dropdown = document.getElementById('download-status-filter');
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
      const saved = localStorage.getItem('downloadQueueSettings');
      if (saved) {
        const settings = JSON.parse(saved);
        this.currentSort = settings.sort?.field || 'title';
        this.sortAscending = settings.sort?.ascending !== undefined ? settings.sort.ascending : true;
      }
    } catch (error) {
      console.warn('[Downloads] Failed to parse sort preference:', error);
    }
    // Update dropdown and button on page load
    setTimeout(() => {
      const dropdown = document.getElementById('download-sort-select');
      if (dropdown) {
        dropdown.value = this.currentSort;
      }
      const toggleBtn = document.getElementById('download-sort-toggle');
      if (toggleBtn) {
        toggleBtn.textContent = this.sortAscending ? '↑' : '↓';
      }
    }, 100);
  }

  /**
   * Set the current sort for the download queue
   *
   * @param {string} sort - Sort type (title, status, priority, created_at)
   * @returns {void}
   */
  setSort(sort) {
    this.currentSort = sort;
    // Save to localStorage in combined settings object
    try {
      const saved = localStorage.getItem('downloadQueueSettings');
      const settings = saved ? JSON.parse(saved) : {};
      settings.sort = {
        field: sort,
        ascending: this.sortAscending
      };
      localStorage.setItem('downloadQueueSettings', JSON.stringify(settings));
    } catch (error) {
      console.warn('[Downloads] Failed to save sort:', error);
    }
    // Reload queue with new sort
    this.loadDownloadQueue();
  }

  /**
   * Toggle sort order for the download queue
   * @returns {void}
   */
  toggleSortOrder() {
    this.sortAscending = !this.sortAscending;
    // Save to localStorage in combined settings object
    try {
      const saved = localStorage.getItem('downloadQueueSettings');
      const settings = saved ? JSON.parse(saved) : {};
      settings.sort = {
        field: this.currentSort,
        ascending: this.sortAscending
      };
      localStorage.setItem('downloadQueueSettings', JSON.stringify(settings));
    } catch (error) {
      console.warn('[Downloads] Failed to save sort order:', error);
    }
    // Update button
    const toggleBtn = document.getElementById('download-sort-toggle');
    if (toggleBtn) {
      toggleBtn.textContent = this.sortAscending ? '↑' : '↓';
    }
    // Reload queue with new sort order
    this.loadDownloadQueue();
  }

  /**
   * Sort items based on current sort settings
   * @param {Array} items - Array of download items
   * @returns {Array} Sorted array of items
   */
  sortItems(items) {
    const sorted = [...items]; // Create a copy to avoid mutating original

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
          // Note: downloads may not have priority, default to 0
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

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch('/api/downloads/queue/queued', {
            method: 'DELETE',
          });
          return await response.json();
        },
        'Downloads',
        'downloads-status'
      );

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
   * Clear downloads by status
   *
   * @param {string} status - Status to clear (all, queued, pending, downloading, completed, failed, skipped)
   * @returns {Promise<void>}
   */
  async clearByStatus(status) {
    try {
      // Map status labels to values
      const statusMap = {
        all: 'all',
        queued: 'queued',
        pending: 'pending',
        downloading: 'downloading',
        completed: 'completed',
        failed: 'failed',
        skipped: 'skipped',
      };

      const actualStatus = statusMap[status.toLowerCase()] || status;

      // Confirm before clearing
      const confirmed = await UIUtils.confirm(
        `Clear ${actualStatus.charAt(0).toUpperCase() + actualStatus.slice(1)} Downloads`,
        `Are you sure you want to clear ${actualStatus === 'all' ? 'all' : 'all ' + actualStatus} downloads? This cannot be undone.`
      );

      if (!confirmed) {
        return;
      }

      UIUtils.showStatus('downloads-status', `🗑️ Clearing ${actualStatus} downloads...`, 'info');

      const endpoint = `/api/downloads/queue/${actualStatus}`;
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(endpoint, {
            method: 'DELETE',
          });
          return await response.json();
        },
        'Downloads',
        'downloads-status'
      );

      if (data.success) {
        UIUtils.showStatus('downloads-status', data.message, 'success');
        setTimeout(() => {
          this.loadDownloadQueue();
        }, 1500);
      }
    } catch (error) {
      // Already logged by APIHelper
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

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch('/api/downloads/queue/failed', {
            method: 'DELETE',
          });
          return await response.json();
        },
        'Downloads',
        'downloads-status'
      );

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
      // Already logged by APIHelper
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
window.retryFailedIssue = (id) => downloads.retryFailedIssue(id);
window.openCleanupModal = () => downloads.openCleanupModal();
window.closeCleanupModal = () => downloads.closeCleanupModal();
window.previewCleanup = () => downloads.previewCleanup();
window.executeCleanup = () => downloads.executeCleanup();
window.clearPendingDownloads = () => downloads.clearPendingDownloads();
