/**
 * Library Module
 * Handles periodical library display, sorting, and deletion
 */

import { APIClient } from './api.js';
import { UIUtils, SortManager } from './ui-utils.js';

export class LibraryManager {
  constructor() {
    this.sortManager = new SortManager('title', 'asc', () => this.loadPeriodicals());
    this.pendingDeleteId = null;
    this.pendingDeleteTitle = null;
  }

  /**
   * Load and display periodicals from the library
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

      if (data.periodicals.length === 0) {
        grid.innerHTML = '<p>No periodicals in library yet</p>';
        return;
      }

      data.periodicals.forEach((periodical) => {
        grid.appendChild(this.createPeriodicalCard(periodical));
      });
    } catch (error) {
      console.error('Error loading periodicals:', error);
    }
  }

  /**
   * Set the sort field for the library
   */
  setLibrarySortField(field) {
    this.sortManager.field = field;
    this.sortManager.order = 'asc';

    // Update button active states
    document.querySelectorAll('.library-controls .sort-btn').forEach((btn) => {
      btn.classList.remove('active');
    });
    const activeBtn = document.querySelector(`.library-controls [data-lib-sort="${field}"]`);
    if (activeBtn) {
      activeBtn.classList.add('active');
    }

    this.updateLibrarySortToggleButton();
    this.loadPeriodicals();
  }

  /**
   * Toggle the sort order for the library
   */
  toggleLibrarySortOrder() {
    this.sortManager.order = this.sortManager.order === 'asc' ? 'desc' : 'asc';
    this.updateLibrarySortToggleButton();
    this.loadPeriodicals();
  }

  /**
   * Update the library sort toggle button display
   */
  updateLibrarySortToggleButton() {
    const btn = document.getElementById('library-sort-toggle');
    if (btn) {
      btn.textContent = this.sortManager.order === 'asc' ? '↑' : '↓';
      btn.title =
        this.sortManager.order === 'asc'
          ? 'Ascending (click to descend)'
          : 'Descending (click to ascend)';
    }
  }

  /**
   * Create a periodical card element
   */
  createPeriodicalCard(periodical) {
    const card = document.createElement('div');
    card.className = 'periodical-card';

    const cover = document.createElement('div');
    cover.className = 'periodical-cover';

    if (periodical.cover_path) {
      const img = document.createElement('img');
      img.src = `/api/periodicals/${periodical.id}/cover`;
      img.alt = periodical.title;
      cover.appendChild(img);
    } else {
      cover.textContent = periodical.title;
    }

    card.appendChild(cover);

    const info = document.createElement('div');
    info.className = 'periodical-info';

    const h4 = document.createElement('h4');
    h4.textContent = periodical.title;
    info.appendChild(h4);

    // Add language badge if present
    if (periodical.language && periodical.language !== 'English') {
      const langBadge = document.createElement('span');
      langBadge.className = 'language-badge';
      langBadge.textContent = periodical.language;
      info.appendChild(langBadge);
    }

    const dateP = document.createElement('p');
    const dateText = new Date(periodical.issue_date).toLocaleDateString();
    dateP.textContent = `Latest: ${dateText}`;
    info.appendChild(dateP);

    const issueP = document.createElement('p');
    const issueCount = periodical.issue_count || 1;
    const issueText = issueCount === 1 ? '1 issue' : `${issueCount} issues`;
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
      this.viewPeriodical(periodical.title, periodical.language);
    };
    actionsDiv.appendChild(viewBtn);

    // Delete button
    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-icon btn-danger';
    deleteBtn.textContent = '🗑️';
    deleteBtn.title = 'Delete this periodical';
    deleteBtn.onclick = (e) => {
      e.stopPropagation();
      window.deletePeriodical(periodical.id, periodical.title, periodical.issue_count);
    };
    actionsDiv.appendChild(deleteBtn);

    info.appendChild(actionsDiv);
    card.appendChild(info);

    // Make card clickable on cover/title but not buttons
    const coverClickable = () => this.viewPeriodical(periodical.title, periodical.language);
    cover.style.cursor = 'pointer';
    cover.onclick = coverClickable;
    h4.style.cursor = 'pointer';
    h4.onclick = coverClickable;

    return card;
  }

  /**
   * View periodical (navigate to periodical page)
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
   */
  deletePeriodical(periodicalId, title, issueCount = null) {
    console.log(`[Library] Setting pending delete: ID=${periodicalId}, Title=${title}, IssueCount=${issueCount}`);
    this.pendingDeleteId = periodicalId;
    this.pendingDeleteTitle = title;
    this.pendingDeleteIssueCount = issueCount;

    const modal = document.getElementById('delete-modal');
    if (!modal) {
      console.error('Delete modal not found in DOM');
      return;
    }

    const titleElement = document.getElementById('delete-modal-title');
    if (titleElement) {
      if (issueCount && issueCount > 1) {
        titleElement.textContent = `Are you sure you want to delete all ${issueCount} issues of "${title}"?`;
      } else {
        titleElement.textContent = `Are you sure you want to delete "${title}"?`;
      }
    }

    UIUtils.showModal('delete-modal');
  }

  /**
   * Close the delete confirmation modal
   */
  closeDeleteModal() {
    UIUtils.closeModal('delete-modal');
    this.pendingDeleteId = null;
    this.pendingDeleteTitle = null;
    this.pendingDeleteIssueCount = null;
  }

  /**
   * Confirm and execute periodical deletion
   */
  async confirmDeletePeriodical() {
    console.log(`[Library] Confirming delete: pendingDeleteId=${this.pendingDeleteId}, pendingDeleteTitle=${this.pendingDeleteTitle}`);
    if (!this.pendingDeleteId) {
      console.error('No periodical selected for deletion');
      console.error('This usually means the state was cleared. Check if modal is being closed unexpectedly.');
      UIUtils.showStatus('import-status', 'Error: No periodical selected for deletion. Please try again.', 'error');
      this.closeDeleteModal();
      return;
    }

    const deleteOption = document.querySelector('input[name="delete-option"]:checked');
    if (!deleteOption) {
      console.error('No delete option selected');
      return;
    }

    const deleteFiles = deleteOption.value === 'delete-files';
    const removeTracking = document.getElementById('delete-remove-tracking').checked;
    const deleteAllIssues = true; // Always delete all issues when deleting from library page

    try {
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/${this.pendingDeleteId}?delete_files=${deleteFiles}&remove_tracking=${removeTracking}&delete_all_issues=${deleteAllIssues}`,
        { method: 'DELETE' }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to delete periodical');
      }

      const result = await response.json();

      if (result.success) {
        UIUtils.showStatus('import-status', result.message, 'success');
        setTimeout(() => UIUtils.hideStatus('import-status'), 4000);
        this.closeDeleteModal();
        setTimeout(() => this.loadPeriodicals(), 500);
      }
    } catch (error) {
      console.error('Error deleting periodical:', error);
      UIUtils.showStatus('import-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Open PDF in new tab
   */
  viewPDF(magazineId, _title) {
    window.open(`/api/periodicals/${magazineId}/pdf`, '_blank');
  }

  /**
   * Show import options modal
   */
  openImportModal() {
    UIUtils.showModal('import-options-modal');

    // Set up event listeners for tracking options
    const autoTrackCheckbox = document.getElementById('import-auto-track');
    const trackingModeSelect = document.getElementById('import-tracking-mode');

    // Sync tracking mode dropdown with checkbox
    const syncTrackingOptions = () => {
      if (autoTrackCheckbox.checked) {
        trackingModeSelect.disabled = false;
      } else {
        trackingModeSelect.disabled = true;
        trackingModeSelect.value = 'none';
      }
    };

    // Initial sync
    syncTrackingOptions();

    // Add change listener
    autoTrackCheckbox.addEventListener('change', syncTrackingOptions);
  }

  /**
   * Close import options modal
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
