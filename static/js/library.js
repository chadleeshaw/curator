/**
 * Library Module
 * Handles periodical library display, sorting, and deletion
 * @module library
 */

import { APIClient } from './api.js';
import { UIUtils, SortManager } from './ui-utils.js';
import {
  ELEMENT_IDS as _ELEMENT_IDS,
  STATUS_MESSAGES as _STATUS_MESSAGES,
  CSS_CLASSES as _CSS_CLASSES,
  TIMEOUTS,
} from './constants.js';
import { ValidationError as _ValidationError } from './errors.js';

/**
 * Library Manager class for managing periodical library operations
 * @class
 */
export class LibraryManager {
  /**
   * Create a new LibraryManager instance
   */
  constructor() {
    /** @type {SortManager} Manager for library sorting */
    this.sortManager = new SortManager('title', 'asc', () => this.loadPeriodicals());
    /** @type {number|null} ID of periodical pending deletion */
    this.pendingDeleteId = null;
    /** @type {string|null} Title of periodical pending deletion */
    this.pendingDeleteTitle = null;
    /** @type {number|null} Issue count of periodical pending deletion */
    this.pendingDeleteIssueCount = null;
  }

  /**
   * Load and display periodicals from the library
   *
   * @returns {Promise<void>}
   * @throws {Error} When API request fails
   *
   * @example
   * await library.loadPeriodicals();
   */
  async loadPeriodicals() {
    try {
      const { field, order } = this.sortManager.getSortParams();
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals?sort_by=${field}&sort_order=${order}`
      );
      const data = await response.json();

      const grid = document.getElementById('periodicals-grid');
      grid.innerHTML = '';

      const { periodicals } = data;
      if (periodicals.length === 0) {
        grid.innerHTML = '<p>No periodicals in library yet</p>';
        // Update header stats
        if (window.updateHeaderStats) {
          window.updateHeaderStats();
        }
        return;
      }

      periodicals.forEach((periodical) => {
        grid.appendChild(this.createPeriodicalCard(periodical));
      });

      // Update header stats
      if (window.updateHeaderStats) {
        window.updateHeaderStats();
      }
    } catch (error) {
      console.error('[Library] Failed to load periodicals:', error);
    }
  }

  /**
   * Set the sort field for the library
   *
   * @param {string} field - The field to sort by (e.g., 'title', 'date')
   * @returns {void}
   *
   * @example
   * library.setLibrarySortField('date');
   */
  setLibrarySortField(field) {
    this.sortManager.field = field;
    this.sortManager.order = 'asc';

    // Update button active states
    document.querySelectorAll('.library-controls .sort-btn').forEach((btn) => {
      btn.classList.remove('active');
    });
    const activeBtn = document.querySelector(`.library-controls [data-lib-sort="${field}"]`);
    activeBtn?.classList.add('active');

    this.updateLibrarySortToggleButton();
    this.loadPeriodicals();
  }

  /**
   * Toggle the sort order for the library
   *
   * @returns {void}
   *
   * @example
   * library.toggleLibrarySortOrder();
   */
  toggleLibrarySortOrder() {
    this.sortManager.order = this.sortManager.order === 'asc' ? 'desc' : 'asc';
    this.updateLibrarySortToggleButton();
    this.loadPeriodicals();
  }

  /**
   * Update the library sort toggle button display
   *
   * @returns {void}
   * @private
   */
  updateLibrarySortToggleButton() {
    const btn = document.getElementById('library-sort-toggle');
    if (btn) {
      btn.textContent = this.sortManager.order === 'asc' ? '\u2191' : '\u2193';
      btn.title =
        this.sortManager.order === 'asc'
          ? 'Ascending (click to descend)'
          : 'Descending (click to ascend)';
    }
  }

  /**
   * Create a periodical card element
   *
   * @param {Object} periodical - The periodical data
   * @param {number} periodical.id - Unique identifier
   * @param {string} periodical.title - Periodical title
   * @param {string} [periodical.cover_path] - Path to cover image
   * @param {string} [periodical.language] - Language of the periodical
   * @param {string} periodical.issue_date - Date of latest issue
   * @param {number} [periodical.issue_count=1] - Number of issues
   * @returns {HTMLElement} The created card element
   *
   * @example
   * const card = library.createPeriodicalCard({ id: 1, title: 'PC Gamer', issue_date: '2024-01-01' });
   */
  createPeriodicalCard(periodical) {
    const { id, title, cover_path, language, issue_date, issue_count = 1 } = periodical;

    const card = document.createElement('div');
    card.className = 'periodical-card';

    const cover = document.createElement('div');
    cover.className = 'periodical-cover';

    if (cover_path) {
      const img = document.createElement('img');
      img.src = `/api/periodicals/${id}/cover`;
      img.alt = title;
      cover.appendChild(img);
    } else {
      cover.textContent = title;
    }

    card.appendChild(cover);

    const info = document.createElement('div');
    info.className = 'periodical-info';

    const h4 = document.createElement('h4');
    h4.textContent = title;
    info.appendChild(h4);

    // Add language badge if present and not English
    if (language && language !== 'English') {
      const langBadge = document.createElement('span');
      langBadge.className = 'language-badge';
      langBadge.textContent = language;
      info.appendChild(langBadge);
    }

    const dateP = document.createElement('p');
    const dateText = new Date(issue_date).toLocaleDateString();
    dateP.textContent = `Latest: ${dateText}`;
    info.appendChild(dateP);

    const issueP = document.createElement('p');
    const issueText = issue_count === 1 ? '1 issue' : `${issue_count} issues`;
    issueP.textContent = issueText;
    info.appendChild(issueP);

    // Add action buttons container
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'periodical-actions';

    // View button
    const viewBtn = document.createElement('button');
    viewBtn.className = 'btn-primary';
    viewBtn.textContent = 'Open';
    viewBtn.style.flex = '1';
    viewBtn.style.padding = '8px 14px';
    viewBtn.style.fontSize = '13px';
    viewBtn.style.fontWeight = '600';
    viewBtn.onclick = (e) => {
      e.stopPropagation();
      e.preventDefault();
      this.viewPeriodical(title, language);
    };
    actionsDiv.appendChild(viewBtn);

    // Delete button
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-icon btn-danger';
    deleteBtn.textContent = '\uD83D\uDDD1\uFE0F';
    deleteBtn.title = 'Delete this periodical';
    deleteBtn.onclick = (e) => {
      e.stopPropagation();
      window.deletePeriodical(id, title, issue_count);
    };
    actionsDiv.appendChild(deleteBtn);

    info.appendChild(actionsDiv);
    card.appendChild(info);

    // Make card clickable on cover/title but not buttons
    const coverClickable = () => this.viewPeriodical(title, language);
    cover.style.cursor = 'pointer';
    cover.onclick = coverClickable;
    h4.style.cursor = 'pointer';
    h4.onclick = coverClickable;

    return card;
  }

  /**
   * Navigate to periodical detail page
   *
   * @param {string} periodicalTitle - The title of the periodical
   * @param {string|null} [language=null] - Optional language filter
   * @returns {void}
   *
   * @example
   * library.viewPeriodical('PC Gamer', 'English');
   */
  viewPeriodical(periodicalTitle, language = null) {
    let url = `/periodicals/${encodeURIComponent(periodicalTitle)}`;
    if (language) {
      url += `?language=${encodeURIComponent(language)}`;
    }
    window.location.href = url;
  }

  /**
   * Show delete confirmation modal for a periodical
   *
   * @param {number} periodicalId - The ID of the periodical to delete
   * @param {string} title - The title of the periodical
   * @param {number|null} [issueCount=null] - Number of issues (for display purposes)
   * @returns {void}
   *
   * @example
   * library.deletePeriodical(123, 'PC Gamer', 5);
   */
  deletePeriodical(periodicalId, title, issueCount = null) {
    console.log(
      `[Library] Setting pending delete: ID=${periodicalId}, Title=${title}, IssueCount=${issueCount}`
    );
    this.pendingDeleteId = periodicalId;
    this.pendingDeleteTitle = title;
    this.pendingDeleteIssueCount = issueCount;

    const modal = document.getElementById('delete-modal');
    if (!modal) {
      console.error('[Library] Delete modal not found in DOM');
      return;
    }

    const titleElement = document.getElementById('delete-modal-title');
    if (titleElement) {
      titleElement.textContent =
        issueCount && issueCount > 1
          ? `Are you sure you want to delete all ${issueCount} issues of "${title}"?`
          : `Are you sure you want to delete "${title}"?`;
    }

    UIUtils.showModal('delete-modal');
  }

  /**
   * Close the delete confirmation modal
   *
   * @returns {void}
   */
  closeDeleteModal() {
    UIUtils.closeModal('delete-modal');
    this.pendingDeleteId = null;
    this.pendingDeleteTitle = null;
    this.pendingDeleteIssueCount = null;
  }

  /**
   * Confirm and execute periodical deletion
   *
   * @returns {Promise<void>}
   * @throws {ValidationError} When no periodical is selected for deletion
   * @throws {Error} When API request fails
   *
   * @example
   * await library.confirmDeletePeriodical();
   */
  async confirmDeletePeriodical() {
    console.log(
      `[Library] Confirming delete: pendingDeleteId=${this.pendingDeleteId}, pendingDeleteTitle=${this.pendingDeleteTitle}`
    );

    if (!this.pendingDeleteId) {
      console.error('[Library] No periodical selected for deletion');
      UIUtils.showStatus(
        'import-status',
        'Error: No periodical selected for deletion. Please try again.',
        'error'
      );
      this.closeDeleteModal();
      return;
    }

    const deleteOption = document.querySelector('input[name="delete-option"]:checked');
    if (!deleteOption) {
      console.error('[Library] No delete option selected');
      return;
    }

    const deleteFiles = deleteOption.value === 'delete-files';
    const removeTracking = document.getElementById('delete-remove-tracking')?.checked ?? false;
    const deleteAllIssues = true; // Always delete all issues when deleting from library page

    try {
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/${this.pendingDeleteId}?delete_files=${deleteFiles}&remove_tracking=${removeTracking}&delete_all_issues=${deleteAllIssues}`,
        { method: 'DELETE' }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail ?? 'Failed to delete periodical');
      }

      const result = await response.json();

      if (result.success) {
        UIUtils.showStatus('import-status', result.message, 'success');
        setTimeout(() => UIUtils.hideStatus('import-status'), TIMEOUTS.AUTO_HIDE_STATUS);
        this.closeDeleteModal();
        setTimeout(() => this.loadPeriodicals(), TIMEOUTS.IMPORT_RELOAD_DELAY);
      }
    } catch (error) {
      console.error('[Library] Failed to delete periodical:', error);
      UIUtils.showStatus('import-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * View a magazine's PDF/EPUB file
   *
   * @param {number} magazineId - The ID of the magazine
   * @param {string} _title - The title (unused, for logging)
   * @returns {Promise<void>}
   *
   * @example
   * library.viewPDF(123, 'PC Gamer Issue 1');
   */
  async viewPDF(magazineId, _title) {
    try {
      // Get magazine metadata to check file type
      const response = await APIClient.get(`/api/periodicals/${magazineId}`);
      const data = await response.json();

      // Check if the file is an EPUB
      if (data.file_path && data.file_path.toLowerCase().endsWith('.epub')) {
        // Open EPUB reader
        window.open(`/epub-reader?id=${magazineId}`, '_blank');
      } else {
        // Open PDF normally
        window.open(`/api/periodicals/${magazineId}/pdf`, '_blank');
      }
    } catch (error) {
      console.error('[Library] Error checking file type:', error);
      // Fallback to opening as PDF
      window.open(`/api/periodicals/${magazineId}/pdf`, '_blank');
    }
  }

  /**
   * Show import options modal
   *
   * @returns {void}
   *
   * @example
   * library.openImportModal();
   */
  openImportModal() {
    UIUtils.showModal('import-options-modal');

    // Set up event listeners for tracking options
    const autoTrackCheckbox = document.getElementById('import-auto-track');
    const trackingModeSelect = document.getElementById('import-tracking-mode');

    // Sync tracking mode dropdown with checkbox
    const syncTrackingOptions = () => {
      if (autoTrackCheckbox?.checked) {
        trackingModeSelect.disabled = false;
      } else if (trackingModeSelect) {
        trackingModeSelect.disabled = true;
        trackingModeSelect.value = 'none';
      }
    };

    // Initial sync
    syncTrackingOptions();

    // Add change listener
    autoTrackCheckbox?.addEventListener('change', syncTrackingOptions);
  }

  /**
   * Close import options modal
   *
   * @returns {void}
   */
  closeImportModal() {
    UIUtils.closeModal('import-options-modal');
  }
}

// Create singleton instance
export const library = new LibraryManager();

console.log('[Library] LibraryManager singleton created:', library);

// Expose functions globally for onclick handlers
window.setLibrarySortField = (field) => library.setLibrarySortField(field);
window.toggleLibrarySortOrder = () => library.toggleLibrarySortOrder();
window.deletePeriodical = (id, title, issueCount) => {
  console.log('[Library] window.deletePeriodical called with:', id, title, issueCount);
  return library.deletePeriodical(id, title, issueCount);
};
window.closeDeleteModal = () => library.closeDeleteModal();
window.confirmDeletePeriodical = () => {
  console.log('[Library] window.confirmDeletePeriodical called');
  return library.confirmDeletePeriodical();
};
window.openImportModal = () => library.openImportModal();
window.closeImportModal = () => library.closeImportModal();

console.log('[Library] Window functions registered');
