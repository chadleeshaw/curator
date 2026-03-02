/**
 * @module periodical-actions
 * @description Delete modal, move-issue modal, toggle special edition, and navigation
 * for the periodical detail page.
 */

import { APIClient, APIHelper } from '../core/api.js';
import { CSS_CLASSES, API_LIMITS } from '../core/constants.js';
import { UIUtils } from '../core/ui-utils.js';
import { isSpecialEdition } from './periodical-rendering.js';
import { closeMetadataModal } from './periodical-metadata.js';
import { escapeHtml } from '../readers/reader-utils.js';

// Module-level references to shared state (set via init)
let _state = null;

/**
 * Initialise this module with a reference to the shared state object.
 * Must be called before any other function in this module.
 * @param {Object} state - Shared state: { pendingDeleteId, currentPeriodicalId, currentPeriodicalData }
 */
export function initActions(state) {
  _state = state;
}

// ---------------------------------------------------------------------------
// Delete modal
// ---------------------------------------------------------------------------

/**
 * Open the delete-confirmation modal for a periodical issue.
 * @param {number} periodicalId
 * @param {string} title
 */
export function openDeleteModal(periodicalId, title) {
  _state.pendingDeleteId = periodicalId;

  const modal = document.getElementById('delete-modal');

  const titleElement = document.getElementById('delete-modal-title');
  if (titleElement) {
    titleElement.textContent = `Are you sure you want to delete "${title}"?`;
  }

  // Use class toggle for div-based modal
  if (modal) {
    modal.classList.remove(CSS_CLASSES.HIDDEN);
  }
}

/**
 * Close the delete-confirmation modal.
 */
export function closeDeleteModal() {
  const modal = document.getElementById('delete-modal');

  // Use class toggle for div-based modal
  if (modal) {
    modal.classList.add(CSS_CLASSES.HIDDEN);
  }
  _state.pendingDeleteId = null;
}

// Close modal when clicking outside of it
// Track mousedown target to prevent text selection drag from closing modal
let deleteModalMouseDown = null;
document.addEventListener('mousedown', (event) => {
  deleteModalMouseDown = event.target;
});
document.addEventListener('click', (event) => {
  const modal = document.getElementById('delete-modal');
  if (modal && event.target === modal && deleteModalMouseDown === modal) {
    closeDeleteModal();
  }
  deleteModalMouseDown = null;
});

// ---------------------------------------------------------------------------
// Single issue deletion
// ---------------------------------------------------------------------------

/**
 * Trigger delete flow for an issue (opens modal).
 * @param {number} periodicalId
 * @param {string} title
 */
export function deleteIssue(periodicalId, title) {
  openDeleteModal(periodicalId, title);
}

/**
 * Execute the deletion after user confirms in the modal.
 * @returns {Promise<void>}
 */
export async function confirmDeleteIssue() {
  if (!_state.pendingDeleteId) {
    console.error('No issue selected for deletion');
    return;
  }

  const deleteOption = document.querySelector('input[name="delete-option"]:checked');
  if (!deleteOption) {
    console.error('No delete option selected');
    return;
  }

  const deleteFiles = deleteOption.value === 'delete-files';
  const markAsBad = document.getElementById('mark-as-bad-file')?.checked || false;

  // Count total issues before deletion
  const issueCards = document.querySelectorAll('.issue-card');
  const isLastIssue = issueCards.length === 1;

  try {
    const response = await APIHelper.executeWithErrorHandling(async () => {
      return await APIClient.delete(
        `/api/periodicals/${_state.pendingDeleteId}?delete_files=${deleteFiles}&mark_as_bad=${markAsBad}`
      );
    }, 'Periodical');

    const result = await response.json();

    // Show success message
    UIUtils.showStatus('status-message', result.message, 'success');

    // Close modal
    closeDeleteModal();

    // After a short delay, handle the result
    setTimeout(() => {
      if (isLastIssue) {
        // If this was the last issue, go back to library
        UIUtils.showStatus('status-message', 'Last issue deleted. Returning to library...', 'success');
        setTimeout(() => {
          window.location.href = '/#library';
        }, 1000);
      } else {
        // Reload to show updated issue list
        UIUtils.showStatus('status-message', 'Issue deleted. Refreshing...', 'success');
        setTimeout(() => {
          location.reload();
        }, 1000);
      }
    }, 1500);
  } catch (error) {
    console.error('[Periodical] Error deleting issue:', error);
    const message = error.toUserMessage ? error.toUserMessage() : error.message;
    UIUtils.showStatus('status-message', `Error: ${message}`, 'error');
  }
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------

/**
 * Navigate back — to stack page if coming from one, otherwise to the library.
 */
export function goBack() {
  // If we came from a stack page, go back there
  if (window._stackReturnUrl) {
    window.location.href = window._stackReturnUrl;
    return;
  }
  // Navigate to main page with library hash
  window.location.href = '/#library';
}

/**
 * Detect if navigated from a stack detail page and update the breadcrumb accordingly.
 * Called once during initialisation.
 */
export async function initBreadcrumb() {
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const paramStackName = urlParams.get('from_stack_name');
    const paramStackSlug = urlParams.get('from_stack_slug');

    // Determine the stack slug — prefer URL param, fall back to referrer path
    let stackSlug = paramStackSlug || null;
    let stackReturnPath = stackSlug ? `/stacks/${stackSlug}` : null;

    if (!stackSlug) {
      const ref = document.referrer;
      if (ref) {
        const refUrl = new URL(ref);
        const stackMatch = refUrl.pathname.match(/^\/stacks\/([^/]+)/);
        if (stackMatch) {
          stackSlug = stackMatch[1];
          stackReturnPath = refUrl.pathname;
        }
      }
    }

    if (!stackSlug) return;

    window._stackReturnUrl = stackReturnPath;
    const breadcrumb = document.getElementById('breadcrumb');
    if (!breadcrumb) return;

    const title = document.getElementById('periodical-title')?.textContent || '';

    let stackName = paramStackName;
    if (!stackName) {
      // Fall back: fetch from API (covers direct navigation / bookmarks)
      try {
        const response = await APIClient.get(`/api/stacks/${stackSlug}`);
        const data = await response.json();
        if (data.name) stackName = data.name;
      } catch {
        // Last resort: derive from slug
        stackName = UIUtils.toTitleCase(decodeURIComponent(stackSlug).replace(/-/g, ' '));
      }
    }

    breadcrumb.innerHTML =
      `<a href="/#library">Library</a>` +
      `<span class="separator">/</span>` +
      `<a href="/stacks/${escapeHtml(stackSlug)}">${escapeHtml(stackName)}</a>` +
      `<span class="separator">/</span>` +
      `<span class="current">${escapeHtml(title)}</span>`;
  } catch {
    // Ignore breadcrumb errors
  }
}

// ---------------------------------------------------------------------------
// Move issue modal
// ---------------------------------------------------------------------------

/**
 * Open the move-issue modal and populate the tracking select.
 * @returns {Promise<void>}
 */
export async function openMoveIssueModal() {
  if (!_state.currentPeriodicalId) {
    alert('No magazine selected');
    return;
  }

  const modal = document.getElementById('move-issue-modal');
  const loading = document.getElementById('move-issue-loading');
  const options = document.getElementById('move-issue-options');
  const select = document.getElementById('target-tracking-select');

  modal.classList.remove(CSS_CLASSES.HIDDEN);
  loading.classList.remove(CSS_CLASSES.HIDDEN);
  options.classList.add(CSS_CLASSES.HIDDEN);

  try {
    // Fetch all tracking records
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.get(
        `/api/periodicals/tracking?limit=${API_LIMITS.TRACKING_LIST}`
      );
      return await response.json();
    }, 'Periodical');

    const trackingRecords = data.tracked_periodicals || [];

    // Clear and populate select
    select.innerHTML = '<option value="">Select a tracking record...</option>';

    trackingRecords.forEach((tracking) => {
      // Don't show current tracking as an option
      if (tracking.id === _state.currentPeriodicalData.tracking_id) {
        return;
      }

      const option = document.createElement('option');
      option.value = tracking.id;
      option.textContent = `${tracking.title} (${tracking.category || 'Auto-detect'} - ${tracking.language || 'English'})`;
      select.appendChild(option);
    });

    // Show options
    loading.classList.add(CSS_CLASSES.HIDDEN);
    options.classList.remove(CSS_CLASSES.HIDDEN);

    // Add change listener to enable/disable move button
    select.onchange = function () {
      document.getElementById('confirm-move-btn').disabled = !this.value;
    };
  } catch (error) {
    console.error('[Periodical] Error loading tracking records:', error);
    const message = error.toUserMessage ? error.toUserMessage() : 'Failed to load tracking options';
    alert(message + ': ' + error.message);
    closeMoveIssueModal();
  }
}

/**
 * Close the move-issue modal.
 */
export function closeMoveIssueModal() {
  document.getElementById('move-issue-modal').classList.add(CSS_CLASSES.HIDDEN);
}

/**
 * Execute the move after user confirms in the modal.
 * @returns {Promise<void>}
 */
export async function confirmMoveIssue() {
  const targetTrackingId = document.getElementById('target-tracking-select').value;

  if (!targetTrackingId || !_state.currentPeriodicalId) {
    alert('Please select a tracking record');
    return;
  }

  const confirmBtn = document.getElementById('confirm-move-btn');
  confirmBtn.disabled = true;
  confirmBtn.textContent = 'Moving...';

  try {
    // Count total issues before moving to detect if this is the last one
    const issueCards = document.querySelectorAll('.issue-card');
    const isLastIssue = issueCards.length === 1;

    const response = await APIHelper.executeWithErrorHandling(async () => {
      return await APIClient.post(
        `/api/periodicals/${_state.currentPeriodicalId}/move-to-tracking?target_tracking_id=${targetTrackingId}`
      );
    }, 'Periodical');

    const result = await response.json();

    // Show success message
    UIUtils.showStatus('status-message', result.message, 'success');

    // Close modals
    closeMoveIssueModal();
    closeMetadataModal();

    // If this was the last issue, redirect to library instead of reloading
    if (isLastIssue) {
      UIUtils.showStatus('status-message', 'Last issue moved. Returning to library...', 'success');
      setTimeout(() => {
        window.location.href = '/#library';
      }, 1500);
    } else {
      // Otherwise just reload to show updated list
      setTimeout(() => {
        location.reload();
      }, 1500);
    }
  } catch (error) {
    console.error('[Periodical] Error moving issue:', error);
    const message = error.toUserMessage ? error.toUserMessage() : error.message;
    alert('Failed to move issue: ' + message);
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Move Issue';
  }
}

// ---------------------------------------------------------------------------
// Toggle special edition
// ---------------------------------------------------------------------------

/**
 * Toggle the special-edition flag for the current issue.
 * @returns {Promise<void>}
 */
export async function toggleSpecialEdition() {
  if (!_state.currentPeriodicalId || !_state.currentPeriodicalData) {
    alert('No magazine selected');
    return;
  }

  const isCurrentlySpecial = isSpecialEdition(_state.currentPeriodicalData);

  const toggleBtn = document.getElementById('toggle-special-btn');
  const originalText = toggleBtn.textContent;
  toggleBtn.disabled = true;
  toggleBtn.textContent = 'Updating...';

  try {
    const response = await APIHelper.executeWithErrorHandling(async () => {
      return await APIClient.post(
        `/api/periodicals/${_state.currentPeriodicalId}/toggle-special-edition?is_special=${!isCurrentlySpecial}`
      );
    }, 'Periodical');

    const result = await response.json();

    // Show success message
    UIUtils.showStatus('status-message', result.message, 'success');

    // Close modal
    closeMetadataModal();

    // Reload page after a delay
    setTimeout(() => {
      location.reload();
    }, 1500);
  } catch (error) {
    console.error('[Periodical] Error toggling special edition:', error);
    const message = error.toUserMessage ? error.toUserMessage() : error.message;
    alert('Failed to update special edition status: ' + message);
    toggleBtn.disabled = false;
    toggleBtn.textContent = originalText;
  }
}
