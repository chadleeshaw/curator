/**
 * @module periodical
 * @description Periodical detail page — thin coordinator that wires together
 * the focused feature modules and exposes their functions to the global scope
 * for HTML onclick handlers.
 */

import { initScrollCollapse } from './core/scroll-collapse.js';

// Feature modules
import {
  loadLanguageDropdown,
  updateSubtitle,
  renderFlatView,
  renderGroupedView,
  createIssueCard,
  openPDF,
} from './features/periodical-rendering.js';

import {
  initMetadata,
  viewMetadata,
  closeMetadataModal,
  enableMetadataEdit,
  cancelMetadataEdit,
  previewCoverUpload,
  clearCoverUpload,
  regenerateThumbnailOcr,
  saveMetadataEdit,
} from './features/periodical-metadata.js';

import {
  initActions,
  closeDeleteModal,
  deleteIssue,
  confirmDeleteIssue,
  goBack,
  initBreadcrumb,
  openMoveIssueModal,
  closeMoveIssueModal,
  confirmMoveIssue,
  toggleSpecialEdition,
} from './features/periodical-actions.js';

import {
  initBulkOps,
  toggleBulkSelectMode,
  toggleIssueSelection,
  selectAllIssues,
  deselectAllIssues,
  openBulkMoveModal,
  closeBulkMoveModal,
  confirmBulkMove,
  openBulkRegenerateModal,
  closeBulkRegenerateModal,
  confirmBulkRegenerate,
  openBulkDeleteModal,
  closeBulkDeleteModal,
  confirmBulkDelete,
} from './features/periodical-bulk-ops.js';

// Initialize scroll-collapse for detail page header
initScrollCollapse();

// ---------------------------------------------------------------------------
// Shared state — single source of truth used across all modules
// ---------------------------------------------------------------------------

// Parse years data and special editions from data attributes
const container = document.getElementById('periodical-container');
const yearsData = container ? JSON.parse(container.getAttribute('data-years') || '[]') : [];
const specialEditionsData = container
  ? JSON.parse(container.getAttribute('data-special-editions') || '[]')
  : [];

/**
 * Shared mutable state object.  Modules receive a reference to this object so
 * they can both read and write the same values without requiring explicit
 * setter functions for every field.
 */
const state = {
  pendingDeleteId: null,
  currentPeriodicalId: null,
  currentPeriodicalData: null,
  bulkSelectMode: false,
  selectedIssueIds: new Set(),
};

// ---------------------------------------------------------------------------
// Sort state (coordinator-owned — rendering helpers receive values as args)
// ---------------------------------------------------------------------------

let currentSortField = localStorage.getItem('periodical-sort-field') || 'issue_date';
let sortAscending = localStorage.getItem('periodical-sort-order') === 'asc'; // Default to desc for issue_date

// Set initial sort UI state
if (document.getElementById('periodical-sort-select')) {
  document.getElementById('periodical-sort-select').value = currentSortField;
  document.getElementById('periodical-sort-toggle').textContent = sortAscending ? '↑' : '↓';
  updateSubtitle(currentSortField, yearsData);
}

// ---------------------------------------------------------------------------
// Initialise modules with shared state
// ---------------------------------------------------------------------------

initMetadata(state);
initActions(state);
initBreadcrumb(); // async — updates breadcrumb once stack name is fetched
initBulkOps(state, rerender);

// ---------------------------------------------------------------------------
// Rendering helpers (coordinator-level, because they close over sort state)
// ---------------------------------------------------------------------------

/**
 * Render all issues using the current sort settings.
 */
function renderIssues() {
  const issuesContainer = document.getElementById('issues-container');

  if (
    (!yearsData || yearsData.length === 0) &&
    (!specialEditionsData || specialEditionsData.length === 0)
  ) {
    issuesContainer.innerHTML = '<div class="no-issues">No issues found for this periodical.</div>';
    return;
  }

  if (currentSortField !== 'issue_date') {
    renderFlatView(
      issuesContainer,
      specialEditionsData,
      yearsData,
      currentSortField,
      sortAscending,
      _createIssueCard
    );
  } else {
    renderGroupedView(
      issuesContainer,
      specialEditionsData,
      yearsData,
      currentSortField,
      sortAscending,
      _createIssueCard
    );
  }
}

/**
 * Thin wrapper that binds the coordinator-level callbacks into createIssueCard.
 * @param {Object} issue
 * @returns {HTMLElement}
 */
function _createIssueCard(issue) {
  return createIssueCard(
    issue,
    state.bulkSelectMode,
    state.selectedIssueIds,
    toggleIssueSelection,
    openPDF,
    viewMetadata,
    deleteIssue
  );
}

/**
 * Re-render the issues with current sort settings (called by sort controls and bulk ops).
 */
function rerender() {
  const issuesContainer = document.getElementById('issues-container');
  issuesContainer.style.opacity = '0.5';
  issuesContainer.style.transition = 'opacity 0.2s ease';

  setTimeout(() => {
    issuesContainer.innerHTML = '';

    if (currentSortField !== 'issue_date') {
      renderFlatView(
        issuesContainer,
        specialEditionsData,
        yearsData,
        currentSortField,
        sortAscending,
        _createIssueCard
      );
    } else {
      renderGroupedView(
        issuesContainer,
        specialEditionsData,
        yearsData,
        currentSortField,
        sortAscending,
        _createIssueCard
      );
    }

    issuesContainer.style.opacity = '1';
  }, 100);
}

// ---------------------------------------------------------------------------
// Sort controls (exposed globally below)
// ---------------------------------------------------------------------------

/**
 * Set the sort field and re-render
 * @param {string} field - The field to sort by
 */
function setPeriodicalSort(field) {
  currentSortField = field;
  localStorage.setItem('periodical-sort-field', field);
  updateSubtitle(currentSortField, yearsData);
  rerender();
}

/**
 * Toggle sort order and re-render
 */
function togglePeriodicalSortOrder() {
  sortAscending = !sortAscending;
  localStorage.setItem('periodical-sort-order', sortAscending ? 'asc' : 'desc');
  document.getElementById('periodical-sort-toggle').textContent = sortAscending ? '↑' : '↓';
  rerender();
}

// ---------------------------------------------------------------------------
// Global window scope exposure — must remain intact for HTML onclick handlers
// ---------------------------------------------------------------------------

window.setPeriodicalSort = setPeriodicalSort;
window.togglePeriodicalSortOrder = togglePeriodicalSortOrder;
window.toggleBulkSelectMode = toggleBulkSelectMode;

window.goBack = goBack;
window.closeDeleteModal = closeDeleteModal;
window.confirmDeleteIssue = confirmDeleteIssue;
window.closeMetadataModal = closeMetadataModal;
window.enableMetadataEdit = enableMetadataEdit;
window.cancelMetadataEdit = cancelMetadataEdit;
window.saveMetadataEdit = saveMetadataEdit;
window.toggleSpecialEdition = toggleSpecialEdition;
window.openMoveIssueModal = openMoveIssueModal;
window.closeMoveIssueModal = closeMoveIssueModal;
window.confirmMoveIssue = confirmMoveIssue;
window.previewCoverUpload = previewCoverUpload;
window.clearCoverUpload = clearCoverUpload;
window.regenerateThumbnailOcr = regenerateThumbnailOcr;

// Bulk operation functions
window.selectAllIssues = selectAllIssues;
window.deselectAllIssues = deselectAllIssues;
window.openBulkMoveModal = openBulkMoveModal;
window.closeBulkMoveModal = closeBulkMoveModal;
window.confirmBulkMove = confirmBulkMove;
window.openBulkRegenerateModal = openBulkRegenerateModal;
window.closeBulkRegenerateModal = closeBulkRegenerateModal;
window.confirmBulkRegenerate = confirmBulkRegenerate;
window.openBulkDeleteModal = openBulkDeleteModal;
window.closeBulkDeleteModal = closeBulkDeleteModal;
window.confirmBulkDelete = confirmBulkDelete;

// ---------------------------------------------------------------------------
// DOMContentLoaded initialization
// ---------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  // Load dynamic dropdown data
  loadLanguageDropdown();

  // Ensure delete modal is closed on page load
  const deleteModal = document.getElementById('delete-modal');
  if (deleteModal && typeof deleteModal.close === 'function') {
    deleteModal.close();
  }

  try {
    renderIssues();
    // If yearsData is empty or no issues were rendered, show a message
    const issuesContainer = document.getElementById('issues-container');
    if (!issuesContainer || issuesContainer.innerHTML.includes('No issues found')) {
      // Add a back button message if all issues are deleted
      const message = document.createElement('div');
      message.style.textAlign = 'center';
      message.style.padding = '40px';
      message.style.color = 'var(--text-secondary)';
      message.innerHTML = `<p>This periodical has no issues remaining.</p><p><button onclick="goBack()" class="back-button">← ${window._stackReturnUrl ? 'Back to Stack' : 'Back to Library'}</button></p>`;
      const statusDiv = document.getElementById('status-message');
      if (statusDiv && statusDiv.style.display === 'none') {
        // Show helpful message if not already showing deletion success
      }
    }
  } catch (error) {
    console.error('Error rendering issues:', error);
    const errorDiv = document.getElementById('status-message');
    if (errorDiv) {
      errorDiv.className = 'status-error mt-20 p-15 rounded';
      errorDiv.textContent = `Error loading issues: ${error.message}`;
      errorDiv.style.display = 'block';
    }
  }
});
