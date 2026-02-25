/**
 * @module periodical-bulk-ops
 * @description Bulk selection, bulk move to tracking, bulk regenerate thumbnail/OCR,
 * and bulk delete for the periodical detail page.
 */

import { APIClient, APIHelper } from '../core/api.js';
import { CSS_CLASSES, API_LIMITS } from '../core/constants.js';
import { showNotification } from './periodical-metadata.js';

// Module-level references to shared state (set via init)
let _state = null;
// rerenderFn is the callback used to re-render the issue grid after mode changes
let _rerender = null;

/**
 * Initialise this module with references to shared state and the rerender function.
 * Must be called before any other function in this module.
 * @param {Object} state - Shared state: { bulkSelectMode, selectedIssueIds, ... }
 * @param {Function} rerender - Callback to re-render the issue list
 */
export function initBulkOps(state, rerender) {
  _state = state;
  _rerender = rerender;
}

// ==========================================================================
// Bulk Selection Mode
// ==========================================================================

/**
 * Toggle bulk selection mode on/off
 */
export function toggleBulkSelectMode() {
  _state.bulkSelectMode = !_state.bulkSelectMode;
  _state.selectedIssueIds.clear();

  const container = document.getElementById('issues-container');
  const toggleBtn = document.getElementById('bulk-select-toggle');
  const actionBar = document.getElementById('bulk-action-bar');

  if (_state.bulkSelectMode) {
    container.classList.add('bulk-select-mode');
    toggleBtn.classList.add('active');
    toggleBtn.innerHTML =
      '<span class="bulk-select-icon">☑</span><span class="btn-label"> Selecting...</span>';
    actionBar.classList.remove(CSS_CLASSES.HIDDEN);
  } else {
    container.classList.remove('bulk-select-mode');
    toggleBtn.classList.remove('active');
    toggleBtn.innerHTML =
      '<span class="bulk-select-icon">☑</span><span class="btn-label"> Select</span>';
    actionBar.classList.add(CSS_CLASSES.HIDDEN);
  }

  updateBulkSelectionCount();
  _rerender();
}

/**
 * Toggle selection of an individual issue
 * @param {number} issueId - ID of the issue to toggle
 * @param {HTMLInputElement} checkbox - The checkbox element
 */
export function toggleIssueSelection(issueId, checkbox) {
  if (checkbox.checked) {
    _state.selectedIssueIds.add(issueId);
  } else {
    _state.selectedIssueIds.delete(issueId);
  }

  // Update card selected visual
  const card = checkbox.closest('.issue-card');
  if (card) {
    card.classList.toggle('bulk-selected', checkbox.checked);
  }

  updateBulkSelectionCount();
}

/**
 * Select all visible issues
 */
export function selectAllIssues() {
  const cards = document.querySelectorAll('.issue-card');
  cards.forEach((card) => {
    const id = parseInt(card.dataset.issueId, 10);
    if (id) {
      _state.selectedIssueIds.add(id);
      card.classList.add('bulk-selected');
      const cb = card.querySelector('.bulk-checkbox');
      if (cb) cb.checked = true;
    }
  });
  updateBulkSelectionCount();
}

/**
 * Deselect all issues
 */
export function deselectAllIssues() {
  _state.selectedIssueIds.clear();
  const cards = document.querySelectorAll('.issue-card');
  cards.forEach((card) => {
    card.classList.remove('bulk-selected');
    const cb = card.querySelector('.bulk-checkbox');
    if (cb) cb.checked = false;
  });
  updateBulkSelectionCount();
}

/**
 * Update the selected count display in the action bar
 */
export function updateBulkSelectionCount() {
  const countEl = document.getElementById('bulk-selected-count');
  if (countEl) {
    countEl.textContent = _state.selectedIssueIds.size;
  }
}

/**
 * Get array of selected issue IDs
 * @returns {number[]}
 */
export function getSelectedIds() {
  return Array.from(_state.selectedIssueIds);
}

// ==========================================================================
// Bulk Move to Tracking
// ==========================================================================

/**
 * Open the bulk-move modal and populate the tracking select.
 * @returns {Promise<void>}
 */
export async function openBulkMoveModal() {
  const ids = getSelectedIds();
  if (ids.length === 0) {
    showNotification('No issues selected', 'error');
    return;
  }

  const modal = document.getElementById('bulk-move-modal');
  const loading = document.getElementById('bulk-move-loading');
  const options = document.getElementById('bulk-move-options');
  const select = document.getElementById('bulk-target-tracking-select');
  const countEl = document.getElementById('bulk-move-count');

  countEl.textContent = ids.length;
  modal.classList.remove(CSS_CLASSES.HIDDEN);
  loading.classList.remove(CSS_CLASSES.HIDDEN);
  options.classList.add(CSS_CLASSES.HIDDEN);

  try {
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.get(
        `/api/periodicals/tracking?limit=${API_LIMITS.TRACKING_LIST}`
      );
      return await response.json();
    }, 'Periodical');

    const trackingRecords = data.tracked_periodicals || [];

    select.innerHTML = '<option value="">Select a tracking record...</option>';

    trackingRecords.forEach((tracking) => {
      const option = document.createElement('option');
      option.value = tracking.id;
      option.textContent = `${tracking.title} (${tracking.category || 'Auto-detect'} - ${tracking.language || 'English'})`;
      select.appendChild(option);
    });

    loading.classList.add(CSS_CLASSES.HIDDEN);
    options.classList.remove(CSS_CLASSES.HIDDEN);

    select.onchange = function () {
      document.getElementById('confirm-bulk-move-btn').disabled = !this.value;
    };
  } catch (error) {
    console.error('[Periodical] Error loading tracking records for bulk move:', error);
    const message = error.toUserMessage ? error.toUserMessage() : 'Failed to load tracking options';
    showNotification(message, 'error');
    closeBulkMoveModal();
  }
}

/**
 * Close the bulk-move modal.
 */
export function closeBulkMoveModal() {
  document.getElementById('bulk-move-modal').classList.add(CSS_CLASSES.HIDDEN);
}

/**
 * Execute the bulk move after user confirms in the modal.
 * @returns {Promise<void>}
 */
export async function confirmBulkMove() {
  const targetTrackingId = document.getElementById('bulk-target-tracking-select').value;
  const ids = getSelectedIds();

  if (!targetTrackingId || ids.length === 0) {
    showNotification('Please select a tracking record', 'error');
    return;
  }

  const confirmBtn = document.getElementById('confirm-bulk-move-btn');
  confirmBtn.disabled = true;
  confirmBtn.textContent = 'Moving...';

  try {
    const totalIssues = document.querySelectorAll('.issue-card').length;
    const isMovingAll = ids.length >= totalIssues;

    const response = await APIHelper.executeWithErrorHandling(async () => {
      return await APIClient.post('/api/periodicals/bulk/move-to-tracking', {
        periodical_ids: ids,
        target_tracking_id: parseInt(targetTrackingId, 10),
      });
    }, 'Periodical');

    const result = await response.json();

    const statusDiv = document.getElementById('status-message');
    statusDiv.className = 'status-success mt-20 p-15 rounded';
    statusDiv.textContent = `✓ ${result.message}`;
    statusDiv.style.display = 'block';

    closeBulkMoveModal();
    toggleBulkSelectMode();

    if (isMovingAll) {
      statusDiv.textContent = '✓ All issues moved. Returning to library...';
      setTimeout(() => {
        window.location.href = '/#library';
      }, 1500);
    } else {
      setTimeout(() => {
        location.reload();
      }, 1500);
    }
  } catch (error) {
    console.error('[Periodical] Error in bulk move:', error);
    const message = error.toUserMessage ? error.toUserMessage() : error.message;
    showNotification('Failed to move issues: ' + message, 'error');
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Move Issues';
  }
}

// ==========================================================================
// Bulk Regenerate Thumbnail & OCR
// ==========================================================================

/**
 * Open the bulk-regenerate modal.
 */
export function openBulkRegenerateModal() {
  const ids = getSelectedIds();
  if (ids.length === 0) {
    showNotification('No issues selected', 'error');
    return;
  }

  const countEl = document.getElementById('bulk-regenerate-count');
  countEl.textContent = ids.length;

  const modal = document.getElementById('bulk-regenerate-modal');
  modal.classList.remove(CSS_CLASSES.HIDDEN);
}

/**
 * Close the bulk-regenerate modal.
 */
export function closeBulkRegenerateModal() {
  document.getElementById('bulk-regenerate-modal').classList.add(CSS_CLASSES.HIDDEN);
}

/**
 * Execute the bulk regenerate after user confirms in the modal.
 * @returns {Promise<void>}
 */
export async function confirmBulkRegenerate() {
  const ids = getSelectedIds();
  if (ids.length === 0) return;

  const confirmBtn = document.getElementById('confirm-bulk-regenerate-btn');
  confirmBtn.disabled = true;
  confirmBtn.textContent = 'Regenerating...';

  try {
    const response = await APIHelper.executeWithErrorHandling(async () => {
      return await APIClient.post('/api/periodicals/bulk/regenerate-thumbnail-ocr', {
        periodical_ids: ids,
      });
    }, 'Periodical');

    const result = await response.json();

    showNotification(`✅ ${result.message}`, 'success');

    closeBulkRegenerateModal();
    toggleBulkSelectMode();

    setTimeout(() => {
      location.reload();
    }, 1500);
  } catch (error) {
    console.error('[Periodical] Error in bulk regenerate:', error);
    const message = error.toUserMessage ? error.toUserMessage() : error.message;
    showNotification('Failed to regenerate: ' + message, 'error');
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Regenerate';
  }
}

// ==========================================================================
// Bulk Delete
// ==========================================================================

/**
 * Open the bulk-delete modal.
 */
export function openBulkDeleteModal() {
  const ids = getSelectedIds();
  if (ids.length === 0) {
    showNotification('No issues selected', 'error');
    return;
  }

  const countEl = document.getElementById('bulk-delete-count');
  countEl.textContent = ids.length;

  const modal = document.getElementById('bulk-delete-modal');
  modal.classList.remove(CSS_CLASSES.HIDDEN);
}

/**
 * Close the bulk-delete modal.
 */
export function closeBulkDeleteModal() {
  document.getElementById('bulk-delete-modal').classList.add(CSS_CLASSES.HIDDEN);
}

/**
 * Execute the bulk delete after user confirms in the modal.
 * @returns {Promise<void>}
 */
export async function confirmBulkDelete() {
  const ids = getSelectedIds();
  if (ids.length === 0) return;

  const deleteOption = document.querySelector('input[name="bulk-delete-option"]:checked');
  if (!deleteOption) return;

  const deleteFiles = deleteOption.value === 'delete-files';
  const markAsBad = document.getElementById('bulk-mark-as-bad')?.checked || false;

  const totalIssues = document.querySelectorAll('.issue-card').length;
  const isDeletingAll = ids.length >= totalIssues;

  const confirmBtn = document.getElementById('confirm-bulk-delete-btn');
  if (confirmBtn) {
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Deleting...';
  }

  try {
    const response = await APIHelper.executeWithErrorHandling(async () => {
      return await APIClient.post('/api/periodicals/bulk/delete', {
        periodical_ids: ids,
        delete_files: deleteFiles,
        mark_as_bad: markAsBad,
      });
    }, 'Periodical');

    const result = await response.json();

    const statusDiv = document.getElementById('status-message');
    statusDiv.className = 'status-success mt-20 p-15 rounded';
    statusDiv.textContent = `✓ ${result.message}`;
    statusDiv.style.display = 'block';

    closeBulkDeleteModal();
    toggleBulkSelectMode();

    if (isDeletingAll) {
      statusDiv.textContent = '✓ All issues deleted. Returning to library...';
      setTimeout(() => {
        window.location.href = '/#library';
      }, 1500);
    } else {
      setTimeout(() => {
        location.reload();
      }, 1500);
    }
  } catch (error) {
    console.error('[Periodical] Error in bulk delete:', error);
    const message = error.toUserMessage ? error.toUserMessage() : error.message;
    showNotification('Failed to delete issues: ' + message, 'error');
    if (confirmBtn) {
      confirmBtn.disabled = false;
      confirmBtn.textContent = 'Delete Issues';
    }
  }
}
