/**
 * Library Module
 * Handles periodical library display, sorting, and deletion
 * @module library
 */

/* global IntersectionObserver */

import { APIClient } from './api.js';
import { UIUtils, SortManager } from './ui-utils.js';
import {
  ELEMENT_IDS as _ELEMENT_IDS,
  STATUS_MESSAGES as _STATUS_MESSAGES,
  CSS_CLASSES as _CSS_CLASSES,
  TIMEOUTS,
} from './constants.js';
import { ValidationError as _ValidationError } from './errors.js';
import { mediaWorker, Priority } from './media-worker-manager.js';

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
    /** @type {string} Current category filter */
    this.categoryFilter = 'all';
    /** @type {string} Current language filter */
    this.languageFilter = 'all';
    /** @type {string} Current search query */
    this.searchQuery = '';
    /** @type {Array} All periodicals loaded from API (unfiltered) */
    this.allPeriodicals = [];
    /** @type {number|null} ID of periodical pending deletion */
    this.pendingDeleteId = null;
    /** @type {string|null} Title of periodical pending deletion */
    this.pendingDeleteTitle = null;
    /** @type {number|null} Issue count of periodical pending deletion */
    this.pendingDeleteIssueCount = null;
    /** @type {boolean} Whether media worker is initialized */
    this.workerInitialized = false;
    /** @type {IntersectionObserver|null} Observer for lazy loading thumbnails */
    this.thumbnailObserver = null;

    // Initialize media worker
    this.initMediaWorker();

    // Setup Intersection Observer for smart lazy loading
    this.setupIntersectionObserver();

    // Load categories on initialization
    this.loadCategories();

    // Load saved filter state from localStorage
    this.loadFilterState();

    // Setup keyboard shortcuts
    this.setupKeyboardShortcuts();
  }

  /**
   * Setup keyboard shortcuts for library
   *
   * @returns {void}
   */
  setupKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
      // Ctrl+F or Cmd+F to focus search (only on library tab)
      if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
        const libraryTab = document.getElementById('library-tab');
        if (libraryTab && libraryTab.classList.contains('active')) {
          e.preventDefault();
          const searchInput = document.getElementById('library-search-input');
          if (searchInput) {
            searchInput.focus();
            searchInput.select();
          }
        }
      }
    });
  }

  /**
   * Setup Intersection Observer for smart thumbnail loading
   * Loads thumbnails when they're about to enter viewport
   */
  setupIntersectionObserver() {
    if (!('IntersectionObserver' in window)) {
      console.warn(
        '[Library] IntersectionObserver not supported, falling back to standard loading'
      );
      return;
    }

    // Load images when they're within 200px of viewport
    const options = {
      root: null,
      rootMargin: '200px',
      threshold: 0.01,
    };

    this.thumbnailObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const img = entry.target;
          const dataSrc = img.getAttribute('data-src');

          if (dataSrc && !img.src) {
            // Load the image
            img.src = dataSrc;
            img.removeAttribute('data-src');

            // Prefetch with worker if available
            if (this.workerInitialized) {
              mediaWorker.prefetch(dataSrc, Priority.HIGH, 'thumbnail').catch((err) => {
                console.warn('[Library] Worker prefetch failed:', err);
              });
            }
          }

          // Stop observing once loaded
          this.thumbnailObserver.unobserve(img);
        }
      });
    }, options);
  }

  /**
   * Initialize the media worker for background thumbnail loading
   * @returns {Promise<void>}
   */
  async initMediaWorker() {
    try {
      await mediaWorker.init();
      this.workerInitialized = true;
      console.log('[Library] Media worker initialized');
    } catch (error) {
      console.warn(
        '[Library] Media worker initialization failed, falling back to standard loading:',
        error
      );
      this.workerInitialized = false;
    }
  }

  /**
   * Load categories from API and populate dropdown
   *
   * @returns {Promise<void>}
   * @throws {Error} When API request fails
   */
  async loadCategories() {
    try {
      const response = await APIClient.get('/api/constants/categories');
      const data = await response.json();

      if (data.success && data.categories) {
        this.populateCategoryDropdown(data.categories);
      }
    } catch (error) {
      console.error('[Library] Failed to load categories:', error);
      // If loading fails, dropdown will keep the hardcoded defaults
    }
  }

  /**
   * Load saved filter state from localStorage
   *
   * @returns {void}
   */
  loadFilterState() {
    try {
      const saved = localStorage.getItem('libraryFilters');
      if (saved) {
        const filters = JSON.parse(saved);
        this.categoryFilter = filters.category || 'all';
        this.languageFilter = filters.language || 'all';
        // Don't restore search query - it should always start empty
        this.searchQuery = '';

        // Restore sort settings
        if (filters.sortField) {
          this.sortManager.field = filters.sortField;
        }
        if (filters.sortOrder) {
          this.sortManager.order = filters.sortOrder;
        }

        // Update UI elements
        const categoryDropdown = document.getElementById('library-category-filter');
        if (categoryDropdown) categoryDropdown.value = this.categoryFilter;

        const languageDropdown = document.getElementById('library-language-filter');
        if (languageDropdown) languageDropdown.value = this.languageFilter;

        // Update sort dropdown
        const sortDropdown = document.getElementById('library-sort-select');
        if (sortDropdown) sortDropdown.value = this.sortManager.field;

        // Update sort toggle button
        this.updateLibrarySortToggleButton();

        // Ensure search input is empty
        const searchInput = document.getElementById('library-search-input');
        if (searchInput) searchInput.value = '';

        console.log('[Library] Loaded saved filter state:', {
          category: this.categoryFilter,
          language: this.languageFilter,
          sortField: this.sortManager.field,
          sortOrder: this.sortManager.order,
        });
      }
    } catch (error) {
      console.warn('[Library] Failed to load saved filters:', error);
    }
  }

  /**
   * Save current filter state to localStorage
   *
   * @returns {void}
   */
  saveFilterState() {
    try {
      const filters = {
        category: this.categoryFilter,
        language: this.languageFilter,
        sortField: this.sortManager.field,
        sortOrder: this.sortManager.order,
        // Don't save search query - it should always start fresh
      };
      localStorage.setItem('libraryFilters', JSON.stringify(filters));
      console.log('[Library] Saved filter state:', filters);
    } catch (error) {
      console.warn('[Library] Failed to save filters:', error);
    }
  }

  /**
   * Populate the category filter dropdown with categories
   *
   * @param {string[]} categories - Array of category names
   * @returns {void}
   */
  populateCategoryDropdown(categories) {
    const dropdown = document.getElementById('library-category-filter');
    if (!dropdown) return;

    // Keep the "All" option
    dropdown.innerHTML = '<option value="all">All</option>';

    // Add each category as an option
    categories.forEach((category) => {
      const option = document.createElement('option');
      option.value = category;
      option.textContent = category;
      dropdown.appendChild(option);
    });
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

      // Store all periodicals unfiltered
      this.allPeriodicals = data.periodicals || [];

      // Load unique languages for language filter (independent API call)
      await this.populateLanguageDropdown();

      // Apply filters and render
      this.applyFiltersAndRender();
    } catch (error) {
      console.error('[Library] Failed to load periodicals:', error);
    }
  }

  /**
   * Apply current filters and render the filtered periodicals
   *
   * @returns {void}
   */
  applyFiltersAndRender() {
    const grid = document.getElementById('periodicals-grid');
    grid.innerHTML = '';

    let filtered = [...this.allPeriodicals];

    // Apply category filter
    if (this.categoryFilter !== 'all') {
      filtered = filtered.filter((p) => {
        const category = p.metadata?.category || 'Unknown';
        return category === this.categoryFilter;
      });
    }

    // Apply language filter
    if (this.languageFilter !== 'all') {
      filtered = filtered.filter((p) => {
        const language = p.language || 'English';
        return language === this.languageFilter;
      });
    }

    // Apply search query
    if (this.searchQuery.trim()) {
      const query = this.searchQuery.toLowerCase().trim();
      filtered = filtered.filter((p) => {
        const title = (p.title || '').toLowerCase();
        return title.includes(query);
      });
    }

    // Render results
    if (filtered.length === 0) {
      const filterDesc = this.getActiveFilterDescription();
      grid.innerHTML = `<p>No periodicals found${filterDesc}</p>`;
      // Update header stats
      if (window.updateHeaderStats) {
        window.updateHeaderStats();
      }
      return;
    }

    filtered.forEach((periodical) => {
      grid.appendChild(this.createPeriodicalCard(periodical));
    });

    // Update header stats
    if (window.updateHeaderStats) {
      window.updateHeaderStats();
    }

    console.log(
      `[Library] Rendered ${filtered.length} of ${this.allPeriodicals.length} periodicals`
    );
  }

  /**
   * Get a description of currently active filters for display
   *
   * @returns {string} Description of active filters (e.g., " matching 'comics' in Magazines")
   */
  getActiveFilterDescription() {
    const parts = [];

    if (this.searchQuery.trim()) {
      parts.push(`matching '${this.searchQuery}'`);
    }

    if (this.categoryFilter !== 'all') {
      parts.push(`in ${this.categoryFilter}`);
    }

    if (this.languageFilter !== 'all') {
      parts.push(`(${this.languageFilter})`);
    }

    return parts.length > 0 ? ' ' + parts.join(' ') : '';
  }

  /**
   * Populate the language filter dropdown with unique languages from library
   *
   * @returns {Promise<void>}
   */
  async populateLanguageDropdown() {
    const dropdown = document.getElementById('library-language-filter');
    if (!dropdown) return;

    try {
      // Fetch languages with counts from API
      const response = await APIClient.authenticatedFetch('/api/periodicals/languages');
      const data = await response.json();

      if (data.success && data.languages) {
        // Keep the "All" option
        dropdown.innerHTML = '<option value="all">All</option>';

        // Add each language as an option with count
        data.languages.forEach(({ language, count }) => {
          const option = document.createElement('option');
          option.value = language;
          option.textContent = `${language} (${count})`;
          dropdown.appendChild(option);
        });

        // Restore saved selection
        dropdown.value = this.languageFilter;
      } else {
        console.warn('[Library] Failed to load languages from API');
      }
    } catch (error) {
      console.error('[Library] Error loading languages:', error);
      // Fallback: don't populate dropdown on error
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

    // Update dropdown selected value
    const selectElement = document.getElementById('library-sort-select');
    if (selectElement) {
      selectElement.value = field;
    }

    this.updateLibrarySortToggleButton();
    this.saveFilterState();
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
    this.saveFilterState();
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
   * Set a filter for the library
   *
   * @param {string} filterType - The type of filter ('category' or 'language')
   * @param {string} value - The filter value
   * @returns {void}
   *
   * @example
   * library.setLibraryFilter('category', 'Comics');
   * library.setLibraryFilter('language', 'English');
   */
  setLibraryFilter(filterType, value) {
    if (filterType === 'category') {
      this.categoryFilter = value;

      // Update dropdown selection
      const dropdown = document.getElementById('library-category-filter');
      if (dropdown) {
        dropdown.value = value;
      }
    } else if (filterType === 'language') {
      this.languageFilter = value;

      // Update dropdown selection
      const dropdown = document.getElementById('library-language-filter');
      if (dropdown) {
        dropdown.value = value;
      }
    }

    // Save filter state
    this.saveFilterState();

    // Re-apply filters
    this.applyFiltersAndRender();
  }

  /**
   * Handle search input changes
   *
   * @param {string} query - The search query
   * @returns {void}
   *
   * @example
   * library.onSearchInput('national geographic');
   */
  onSearchInput(query) {
    this.searchQuery = query;

    // Save filter state
    this.saveFilterState();

    // Re-apply filters (debounced would be better for performance, but simple for now)
    this.applyFiltersAndRender();
  }

  /**
   * Clear all filters and search
   *
   * @returns {void}
   *
   * @example
   * library.clearFilters();
   */
  clearFilters() {
    this.categoryFilter = 'all';
    this.languageFilter = 'all';
    this.searchQuery = '';

    // Update UI elements
    const categoryDropdown = document.getElementById('library-category-filter');
    if (categoryDropdown) categoryDropdown.value = 'all';

    const languageDropdown = document.getElementById('library-language-filter');
    if (languageDropdown) languageDropdown.value = 'all';

    const searchInput = document.getElementById('library-search-input');
    if (searchInput) searchInput.value = '';

    // Save cleared state
    this.saveFilterState();

    // Re-apply filters (will show all)
    this.applyFiltersAndRender();

    console.log('[Library] Cleared all filters');
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
      img.alt = title;
      img.loading = 'lazy'; // Enable native lazy loading as fallback

      const coverUrl = `/api/periodicals/${id}/cover`;

      // Use Intersection Observer if available, otherwise load immediately
      if (this.thumbnailObserver) {
        // Set data-src for lazy loading
        img.setAttribute('data-src', coverUrl);
        // Add placeholder or low-quality image (optional)
        img.style.backgroundColor = '#2a2a2a';
        // Start observing
        this.thumbnailObserver.observe(img);
      } else {
        // Fallback: load immediately
        img.src = coverUrl;

        // Prefetch with media worker if initialized
        if (this.workerInitialized) {
          mediaWorker.prefetch(coverUrl, Priority.MEDIUM, 'thumbnail').catch((err) => {
            console.warn(`[Library] Worker prefetch failed for ${id}:`, err);
          });
        }
      }

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

      // Check file type and open appropriate reader
      if (data.file_path) {
        const filePath = data.file_path.toLowerCase();
        console.log('[Library] Opening file:', filePath);
        if (filePath.endsWith('.epub')) {
          console.log('[Library] Detected EPUB, opening EPUB reader');
          // Open EPUB reader
          window.open(`/epub-reader?id=${magazineId}`, '_blank');
        } else if (filePath.endsWith('.cbz') || filePath.endsWith('.cbr')) {
          console.log('[Library] Detected comic file, opening comic reader');
          // Open comic reader
          window.open(`/comic-reader?id=${magazineId}`, '_blank');
        } else if (filePath.endsWith('.pdf')) {
          console.log('[Library] Detected PDF, opening PDF reader');
          // Open PDF reader
          window.open(`/pdf-reader?id=${magazineId}`, '_blank');
        } else {
          console.log('[Library] Unknown file type, opening directly');
          // Open file directly
          window.open(`/api/periodicals/${magazineId}/pdf`, '_blank');
        }
      } else {
        console.log('[Library] No file_path, opening directly');
        // Fallback to opening directly
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
window.setLibraryFilter = (filterType, value) => library.setLibraryFilter(filterType, value);
window.onLibrarySearchInput = (query) => library.onSearchInput(query);
window.clearLibraryFilters = () => library.clearFilters();
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
