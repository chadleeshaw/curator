/**
 * Tracking Module
 * Handles periodical tracking, metadata search, and issue downloads
 * @module tracking
 */

import { APIClient } from './api.js';
import { UIUtils, SortManager } from './ui-utils.js';
import {
  ELEMENT_IDS,
  STATUS_MESSAGES,
  CSS_CLASSES,
  TIMEOUTS,
  PATTERNS as _PATTERNS,
  BADGE_CONFIGS as _BADGE_CONFIGS,
  NUMBER_TO_MONTH,
  MONTH_NAMES_LOWER,
  MONTH_ABBR_LOWER,
} from './constants.js';

/** @type {string[]} Supported languages loaded from backend */
let SUPPORTED_LANGUAGES = [];
/** @type {Object.<string, string>} ISO country codes to names */
let ISO_COUNTRIES = {};
/** @type {Object.<string, string>} Language to default country mapping */
let LANGUAGE_TO_COUNTRY = {};
/** @type {Object.<string, string[]>} Country code to title indicators */
let COUNTRY_INDICATORS = {};
/** @type {Object.<string, string[]>} Language to title keywords */
let LANGUAGE_KEYWORDS = {};

/**
 * Tracking Manager class for managing periodical tracking operations
 * @class
 */
export class TrackingManager {
  /**
   * Create a new TrackingManager instance
   */
  constructor() {
    /** @type {SortManager} Manager for tracking list sorting */
    this.sortManager = new SortManager('title', 'asc', () => this.loadTrackedPeriodicals());
    /** @type {Object|null} Current periodical metadata from search */
    this.currentPeriodicalMetadata = null;
    /** @type {Object|null} Current editions data */
    this.currentEditionsData = null;
    /** @type {Object.<string, boolean>} Selected editions map */
    this.selectedEditions = {};
    /** @type {boolean} Whether merge mode is active */
    this.mergeMode = false;
    /** @type {Set<number>} IDs selected for merge */
    this.selectedForMerge = new Set();
  }

  /**
   * Initialize the tracking manager
   */
  async init() {
    await this.loadConstants();
    this.populateFormDropdowns();
  }

  /**
   * Load constants from backend API
   *
   * @returns {Promise<void>}
   * @throws {Error} When API request fails
   */
  async loadConstants() {
    try {
      const response = await APIClient.get('/api/constants');
      const data = await response.json();
      if (data.success) {
        SUPPORTED_LANGUAGES = data.languages ?? [];
        ISO_COUNTRIES = data.countries ?? {};
        LANGUAGE_TO_COUNTRY = data.language_to_country ?? {};
        COUNTRY_INDICATORS = data.country_indicators ?? {};
        LANGUAGE_KEYWORDS = data.language_keywords ?? {};
      }
    } catch (error) {
      console.error('[Tracking] Failed to load constants:', error);
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Failed to load form options', 'error');
    }
  }

  /**
   * Populate form dropdowns with constants
   */
  populateFormDropdowns() {
    // Populate language dropdown
    // Populate language dropdowns (new, edit, and search filter)
    const languageSelects = [
      document.getElementById('new-tracking-language'),
      document.getElementById('edit-tracking-language'),
      document.getElementById('search-filter-language'),
    ];
    languageSelects.forEach((languageSelect) => {
      if (languageSelect && SUPPORTED_LANGUAGES.length > 0) {
        // Keep existing options for search filter
        const existingOptions =
          languageSelect.id === 'search-filter-language' ? languageSelect.innerHTML : '';

        languageSelect.innerHTML = existingOptions || '';

        SUPPORTED_LANGUAGES.forEach((lang) => {
          const option = document.createElement('option');
          option.value = lang;
          option.textContent = lang;
          if (lang === 'English' && languageSelect.id !== 'search-filter-language') {
            option.selected = true;
          }
          languageSelect.appendChild(option);
        });
      }
    });

    // Populate country dropdowns (new, edit, and search filter)
    const countrySelects = [
      document.getElementById('new-tracking-country'),
      document.getElementById('edit-tracking-country'),
      document.getElementById('search-filter-country'),
    ];
    countrySelects.forEach((countrySelect) => {
      if (countrySelect && Object.keys(ISO_COUNTRIES).length > 0) {
        // Keep the default option
        const defaultOption = countrySelect.querySelector('option[value=""]');
        const existingDefault = defaultOption ? defaultOption.outerHTML : '';

        countrySelect.innerHTML = existingDefault || '';

        // Get unique countries (removes duplicates like UK/GB)
        const uniqueCountries = new Map();
        Object.entries(ISO_COUNTRIES).forEach(([code, name]) => {
          if (!uniqueCountries.has(name)) {
            uniqueCountries.set(name, code);
          }
        });

        // Sort by country name and add options
        Array.from(uniqueCountries.entries())
          .sort((a, b) => a[0].localeCompare(b[0]))
          .forEach(([name, code]) => {
            const option = document.createElement('option');
            option.value = code;
            option.textContent = `${name} (${code})`;
            if (code === 'US' && countrySelect.id !== 'search-filter-country') {
              option.selected = true;
            }
            countrySelect.appendChild(option);
          });
      }
    });
  }

  /**
   * Search for periodical metadata from providers
   *
   * @returns {Promise<void>}
   * @throws {Error} When API request fails
   */
  async searchPeriodicalMetadata() {
    const query = document.getElementById(ELEMENT_IDS.TRACKING_SEARCH_QUERY)?.value.trim() ?? '';
    const filterLanguage = document.getElementById(ELEMENT_IDS.SEARCH_FILTER_LANGUAGE)?.value ?? '';
    const filterCountry = document.getElementById(ELEMENT_IDS.SEARCH_FILTER_COUNTRY)?.value ?? '';
    const filterCategory = document.getElementById(ELEMENT_IDS.NEW_TRACKING_CATEGORY)?.value ?? '';

    if (!query) {
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, STATUS_MESSAGES.ENTER_TITLE, 'error');
      return;
    }

    const loading = document.getElementById(ELEMENT_IDS.TRACKING_SEARCH_LOADING);
    const result = document.getElementById(ELEMENT_IDS.TRACKING_SEARCH_RESULT);
    const error = document.getElementById(ELEMENT_IDS.TRACKING_SEARCH_ERROR);

    loading.classList.remove(CSS_CLASSES.HIDDEN);
    result.classList.add(CSS_CLASSES.HIDDEN);
    error.classList.add(CSS_CLASSES.HIDDEN);

    try {
      // Build query parameters
      const params = new URLSearchParams({
        query: query,
      });

      if (filterLanguage) {
        params.append('language', filterLanguage);
      }

      if (filterCountry) {
        params.append('country', filterCountry);
      }

      if (filterCategory) {
        params.append('category', filterCategory);
      }

      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/search-providers?${params.toString()}`,
        { method: 'POST' }
      );
      const data = await response.json();

      if (!response.ok) {
        error.textContent = data.detail || `Error: ${response.status}`;
        error.classList.remove(CSS_CLASSES.HIDDEN);
        return;
      }

      if (data.found && data.results && data.results.length > 0) {
        this.displaySearchResultsGrouped(data.results);
        result.classList.remove(CSS_CLASSES.HIDDEN);
      } else {
        const filterInfo = [];
        if (filterLanguage) filterInfo.push(`Language: ${filterLanguage}`);
        if (filterCountry) filterInfo.push(`Country: ${filterCountry}`);
        if (filterCategory) filterInfo.push(`Category: ${filterCategory}`);
        const filterText = filterInfo.length > 0 ? ` (Filters: ${filterInfo.join(', ')})` : '';
        error.textContent = `${data.message || 'Periodical not found'}${filterText}`;
        error.classList.remove(CSS_CLASSES.HIDDEN);
      }
    } catch (err) {
      console.error('Search error:', err);
      error.textContent = err.message;
      error.classList.remove(CSS_CLASSES.HIDDEN);
    } finally {
      loading.classList.add(CSS_CLASSES.HIDDEN);
    }
  }

  /**
   * Display search results grouped by edition
   */
  displaySearchResultsGrouped(results) {
    const container = document.getElementById(ELEMENT_IDS.TRACKING_SEARCH_RESULT);

    // Extract unique periodical editions and group results
    const uniquePeriodicals = {};

    results.forEach((result) => {
      // Extract clean title from the result title/filename
      let cleanTitle = result.title;

      // Extract periodical name from filename (e.g., "PC.Gamer.US.No.405..." -> "PC Gamer US")
      const match = result.title.match(/^([A-Za-z0-9\.\s]+?)(?:\.No\.|\.Issue\.|\.E|\.201|\.202)/i);
      if (match) {
        cleanTitle = match[1].replace(/\./g, ' ').trim();
      }

      // Normalize title for deduplication
      const normalizedKey = cleanTitle.toLowerCase().replace(/\s+/g, ' ').trim();

      if (!uniquePeriodicals[normalizedKey]) {
        uniquePeriodicals[normalizedKey] = {
          displayTitle: cleanTitle,
          count: 0,
          firstResult: result,
        };
      }
      uniquePeriodicals[normalizedKey].count++;
    });

    // Convert to array and sort by count (most common first)
    const periodicalsList = Object.values(uniquePeriodicals).sort((a, b) => b.count - a.count);

    container.innerHTML = '<h4>Select a Periodical Edition:</h4><div class="search-results"></div>';
    const resultsContainer = container.querySelector('.search-results');

    periodicalsList.forEach((periodical) => {
      const result = periodical.firstResult;
      const publisher = result.metadata?.publisher || '';

      const div = document.createElement('div');
      div.className = CSS_CLASSES.RESULT_ITEM;

      div.innerHTML = `
        <div class="result-info">
          <h5 class="result-title">${periodical.displayTitle}</h5>
          <p class="result-detail">
            <strong>Available Issues:</strong> ${periodical.count}
          </p>
          ${publisher ? `<p class="result-detail"><strong>Publisher:</strong> ${publisher}</p>` : ''}
        </div>
        <div class="result-select">→</div>
      `;

      div.onclick = () =>
        this.chooseSearchResult({
          ...result,
          title: periodical.displayTitle, // Override with clean title
          publisher: publisher || '', // Empty string if no publisher metadata
        });

      resultsContainer.appendChild(div);
    });
  }

  /**
   * Display search results for user to select
   */
  displaySearchResults(results) {
    const container = document.getElementById(ELEMENT_IDS.TRACKING_SEARCH_RESULT);
    container.innerHTML = '<h4>Select a Periodical:</h4>';

    results.forEach((result, _index) => {
      const div = document.createElement('div');
      div.className = CSS_CLASSES.RESULT_ITEM;

      div.innerHTML = `
        <h5 class="result-title">${result.title}</h5>
        <p class="result-publisher">${result.publisher || 'Unknown Publisher'}</p>
        <p class="result-source">${result.source || ''}</p>
      `;

      div.onclick = () => this.chooseSearchResult(result);
      container.appendChild(div);
    });
  }

  /**
   * User selected a search result
   */
  async chooseSearchResult(result) {
    this.currentPeriodicalMetadata = result;

    // Auto-populate the manual form fields with search result data
    const titleInput = document.getElementById('new-tracking-title');
    const categorySelect = document.getElementById('new-tracking-category');
    const languageSelect = document.getElementById('new-tracking-language');
    const countrySelect = document.getElementById('new-tracking-country');

    // Set title
    titleInput.value = result.title;

    // Try to detect category from title or metadata
    const titleLower = result.title.toLowerCase();
    if (titleLower.includes('comic') || titleLower.includes('manga')) {
      categorySelect.value = 'Comics';
    } else if (titleLower.includes('magazine') || titleLower.includes('journal')) {
      categorySelect.value = 'Magazines';
    } else if (result.metadata?.category) {
      categorySelect.value = result.metadata.category;
    } else {
      // Default to auto-detect
      categorySelect.value = '';
    }

    // Set language (from filters or detect from title using centralized keywords)
    const currentFilterLanguage = document.getElementById('search-filter-language')?.value;
    if (currentFilterLanguage && currentFilterLanguage !== '') {
      languageSelect.value = currentFilterLanguage;
    } else {
      // Try to detect from title using centralized LANGUAGE_KEYWORDS
      let detectedLanguage = 'English'; // Default
      for (const [language, keywords] of Object.entries(LANGUAGE_KEYWORDS)) {
        if (keywords.some((keyword) => result.title.includes(keyword))) {
          detectedLanguage = language;
          break;
        }
      }
      languageSelect.value = detectedLanguage;
    }

    // Set country (from filters or detect from title using centralized indicators)
    const currentFilterCountry = document.getElementById('search-filter-country')?.value;
    if (currentFilterCountry && currentFilterCountry !== '') {
      countrySelect.value = currentFilterCountry;
    } else {
      // Try to detect from title using centralized COUNTRY_INDICATORS
      let detectedCountry = '';
      for (const [code, indicators] of Object.entries(COUNTRY_INDICATORS)) {
        if (indicators.some((ind) => result.title.includes(ind))) {
          detectedCountry = code;
          break;
        }
      }

      // If no country detected, try to infer from detected language
      if (!detectedCountry && languageSelect.value && LANGUAGE_TO_COUNTRY[languageSelect.value]) {
        detectedCountry = LANGUAGE_TO_COUNTRY[languageSelect.value];
      }

      countrySelect.value = detectedCountry || 'US'; // Default to US
    }

    // Hide the search results
    document.getElementById(ELEMENT_IDS.TRACKING_SEARCH_RESULT).classList.add(CSS_CLASSES.HIDDEN);

    // Show a success message and scroll to the form
    UIUtils.showStatus(
      ELEMENT_IDS.TRACKING_STATUS,
      `✓ Selected: ${result.title}. Review the fields below and click "Start Tracking".`,
      'success'
    );

    // Scroll to the manual form
    const manualSection = titleInput.closest('div[style*="margin-top: 30px"]');
    if (manualSection) {
      manualSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    // Highlight the title field briefly to draw attention
    titleInput.classList.add(CSS_CLASSES.HIGHLIGHT_SUCCESS);
    setTimeout(() => {
      titleInput.classList.remove(CSS_CLASSES.HIGHLIGHT_SUCCESS);
    }, TIMEOUTS.AUTO_HIDE_SUCCESS);
  }

  /**
   * Save tracking preferences
   */
  async saveTrackingPreferences() {
    if (!this.currentPeriodicalMetadata) {
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'No periodical selected', 'error');
      return;
    }

    // Get tracking mode from radio buttons
    const trackingModeElement = document.querySelector('input[name="tracking-mode"]:checked');
    const trackingMode = trackingModeElement ? trackingModeElement.value : 'all';

    // Generate olid from title if not present
    const olid =
      this.currentPeriodicalMetadata.olid ||
      this.currentPeriodicalMetadata.title
        .toLowerCase()
        .replace(/\s+/g, '_')
        .replace(/[^a-z0-9_]/g, '');

    const preferences = {
      olid: olid,
      title: this.currentPeriodicalMetadata.title,
      publisher: this.currentPeriodicalMetadata.publisher || '',
      issn: this.currentPeriodicalMetadata.issn || null,
      first_publish_year: this.currentPeriodicalMetadata.first_publish_year || null,
      track_all_editions: trackingMode === 'all',
      track_new_only: trackingMode === 'new',
      selected_editions: {},
      selected_years: [],
      metadata: this.currentPeriodicalMetadata,
    };

    try {
      const response = await APIClient.post('/api/periodicals/tracking/save', preferences);
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Tracking saved successfully', 'success');

        // Close modal and reload
        this.closeTrackNewPeriodicalModal();
        this.loadTrackedPeriodicals();

        setTimeout(() => {
          UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS);
        }, 2000);
      } else {
        UIUtils.showStatus(
          ELEMENT_IDS.TRACKING_STATUS,
          data.message || 'Error saving tracking',
          'error'
        );
      }
    } catch (error) {
      console.error('Error saving tracking:', error);
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Load tracked periodicals from the API
   *
   * @returns {Promise<void>}
   * @throws {Error} When API request fails
   */
  async loadTrackedPeriodicals() {
    try {
      const { field, order } = this.sortManager.getSortParams();
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/tracking?sort_by=${field}&sort_order=${order}`
      );
      const data = await response.json();

      const tracked = data.tracked_magazines ?? data.tracked ?? [];

      // Update statistics
      this.updateTrackingStatistics(tracked);

      const container = document.getElementById('tracked-list');
      container.innerHTML = '';

      if (tracked.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <div class="empty-state-icon">📚</div>
            <h3>No Tracked Periodicals</h3>
            <p>Start tracking magazines, comics, or news publications to automatically monitor and download new issues.</p>
            <button onclick="openTrackNewPeriodicalModal()" class="btn-primary" style="margin-top: 16px;">📌 Track Your First Periodical</button>
          </div>
        `;
        return;
      }

      tracked.forEach((trackingItem) => {
        container.appendChild(this.createTrackedCard(trackingItem));
      });
    } catch (error) {
      console.error('Error loading tracked periodicals:', error);
    }
  }

  /**
   * Update tracking statistics display
   */
  updateTrackingStatistics(tracked) {
    const statsContainer = document.getElementById('tracking-stats');
    if (!statsContainer) return;

    const stats = {
      total: tracked.length,
      watching: tracked.filter((t) => !t.track_all_editions && !t.track_new_only).length,
      trackingNew: tracked.filter((t) => t.track_new_only).length,
      trackingAll: tracked.filter((t) => t.track_all_editions).length,
      totalKnown: tracked.reduce((sum, t) => sum + (t.total_known || 0), 0),
      totalSelected: tracked.reduce((sum, t) => sum + (t.selected_count || 0), 0),
    };

    statsContainer.innerHTML = `
      <div class="stat-card">
        <div class="stat-value">${stats.total}</div>
        <div class="stat-label">Total Tracked</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${stats.trackingAll}</div>
        <div class="stat-label">All Issues</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${stats.trackingNew}</div>
        <div class="stat-label">New Issues</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${stats.watching}</div>
        <div class="stat-label">Watch Only</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${stats.totalKnown}</div>
        <div class="stat-label">Issues Found</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${stats.totalSelected}</div>
        <div class="stat-label">Selected</div>
      </div>
    `;
  }

  /**
   * Create a tracked periodical card element
   *
   * @param {Object} tracked - The tracking data object
   * @param {number} tracked.id - Tracking ID
   * @param {string} tracked.title - Periodical title
   * @param {boolean} [tracked.track_all_editions] - Whether tracking all editions
   * @param {boolean} [tracked.track_new_only] - Whether tracking new issues only
   * @param {number} [tracked.total_known] - Total known issues
   * @param {number} [tracked.selected_count] - Selected issue count
   * @param {number} [tracked.library_count] - Issues in library
   * @param {number} [tracked.failed_count] - Failed download count
   * @param {string} [tracked.country] - Country code
   * @param {string} [tracked.category] - Category
   * @param {string} [tracked.language] - Language
   * @returns {HTMLElement} The created card element
   */
  createTrackedCard(tracked) {
    const {
      id,
      title,
      track_all_editions: trackAll,
      track_new_only: trackNew,
      total_known: totalKnown = 0,
      selected_count: selectedCount = 0,
      library_count: libraryCount = 0,
      failed_count: failedCount = 0,
      country = '',
      category,
      language,
    } = tracked;

    const card = document.createElement('div');
    card.className = 'tracked-card';
    card.dataset.trackingId = id;

    // Determine tracking badge
    let trackingBadge = '';
    if (trackAll) {
      trackingBadge =
        '<span class="tracking-badge badge-download-all">\u2B07\uFE0F All Issues</span>';
    } else if (trackNew) {
      trackingBadge =
        '<span class="tracking-badge badge-download-new">\u2B07\uFE0F New Issues</span>';
    } else {
      trackingBadge =
        '<span class="tracking-badge badge-watch">\uD83D\uDC41\uFE0F Watch Only</span>';
    }

    const countryStats = country ? `<span class="country">\uD83C\uDF0D ${country}</span>` : '';
    const issueStats =
      totalKnown > 0 ? `<span class="issue-count">${totalKnown} issues found</span>` : '';
    const libraryStats = `<span class="library-count">\uD83D\uDCDA ${libraryCount} in library</span>`;
    const selectedStats =
      selectedCount > 0
        ? `<span class="selected-count">\u2022 ${selectedCount} selected</span>`
        : '';
    const failedStats =
      failedCount > 0
        ? `<span class="failed-count" style="color: var(--status-pending); cursor: pointer;" data-tracking-id="${id}" title="Click to view failed downloads">\u26A0\uFE0F ${failedCount} failed</span>`
        : '';

    const checkboxHtml = this.mergeMode
      ? `<input type="checkbox" class="merge-checkbox" data-tracking-id="${id}" ${this.selectedForMerge.has(id) ? 'checked' : ''}>`
      : '';

    card.innerHTML = `
      ${checkboxHtml}
      <div class="tracked-card-main">
        <div class="tracked-card-header">
          <h5>${title}</h5>
          ${trackingBadge}
        </div>
        <div class="tracked-card-meta">
          <span class="meta-item">\uD83D\uDCC1 ${category ?? 'Auto-detect'}</span>
          <span class="meta-item">\uD83C\uDF10 ${language ?? 'English'}</span>
          ${countryStats}
          ${issueStats}
          ${libraryStats}
          ${failedStats}
          ${selectedStats}
        </div>
      </div>
      <div class="tracked-card-buttons">
        <button onclick="editTracking(${id})" class="btn-icon" title="Edit">\u270F\uFE0F</button>
        <button class="btn-icon search-issues-btn" data-tracking-id="${id}" title="Search Issues">\uD83D\uDD0D</button>
        <button class="btn-icon btn-danger delete-tracking-btn" data-tracking-id="${id}" title="Delete">\uD83D\uDDD1\uFE0F</button>
      </div>
    `;

    // Add event listeners for search and delete buttons
    const searchBtn = card.querySelector('.search-issues-btn');
    searchBtn?.addEventListener('click', () =>
      this.searchForIssues(id, title, language, country, category)
    );

    const deleteBtn = card.querySelector('.delete-tracking-btn');
    deleteBtn?.addEventListener('click', () => this.deleteTracking(id, title));

    // Add event listener for failed count to open failed downloads modal
    const failedCountSpan = card.querySelector('.failed-count');
    failedCountSpan?.addEventListener('click', () =>
      this.showFailedDownloadsForTracking(id, title)
    );

    // Add event listener for checkbox if in merge mode
    if (this.mergeMode) {
      const checkbox = card.querySelector('.merge-checkbox');
      checkbox?.addEventListener('change', (e) => {
        if (e.target.checked) {
          this.selectedForMerge.add(id);
        } else {
          this.selectedForMerge.delete(id);
        }
        this.updateMergeButtonState();
      });
    }

    return card;
  }

  /**
   * Show failed downloads modal for a specific tracking ID
   */
  async showFailedDownloadsForTracking(trackingId, periodicalTitle) {
    try {
      // Fetch all failed downloads
      const response = await APIClient.authenticatedFetch('/api/downloads/failed?include_bad=true');
      const data = await response.json();

      // Filter items for this tracking ID
      const failedItems = data.failed_downloads
        .filter((item) => item.tracking_id === trackingId)
        .map((item) => ({
          id: item.id,
          title: item.title,
          attempt_count: item.attempt_count,
          last_error: item.last_error,
          status: 'failed',
          isBad: false,
        }));

      const badItems = data.bad_files
        .filter((item) => item.tracking_id === trackingId)
        .map((item) => ({
          id: item.id,
          title: item.title,
          attempt_count: item.attempt_count,
          last_error: item.last_error,
          status: 'failed',
          isBad: true,
        }));

      const allItems = [...failedItems, ...badItems];

      if (allItems.length === 0) {
        UIUtils.showToast('No failed downloads found', 'info');
        return;
      }

      // Import downloads module and open modal
      const { downloads } = await import('./downloads.js?v=1767733177');
      downloads.openManageFailedModal(periodicalTitle, allItems);
    } catch (error) {
      console.error('[Tracking] Error loading failed downloads:', error);
      UIUtils.showToast('Error loading failed downloads', 'error');
    }
  }

  /**
   * Set sort field for tracked periodicals
   */
  setSortField(field) {
    this.sortManager.field = field;
    this.sortManager.order = 'asc';

    document.querySelectorAll('.sort-controls .sort-btn').forEach((btn) => {
      btn.classList.remove('active');
    });
    const activeBtn = document.querySelector(`.sort-controls [data-sort="${field}"]`);
    if (activeBtn) {
      activeBtn.classList.add('active');
    }

    this.updateSortToggleButton();
    this.loadTrackedPeriodicals();
  }

  /**
   * Toggle sort order
   */
  toggleSortOrder() {
    this.sortManager.order = this.sortManager.order === 'asc' ? 'desc' : 'asc';
    this.updateSortToggleButton();
    this.loadTrackedPeriodicals();
  }

  /**
   * Update sort toggle button
   */
  updateSortToggleButton() {
    const btn = document.getElementById('tracking-sort-toggle');
    if (btn) {
      btn.textContent = this.sortManager.order === 'asc' ? '↑' : '↓';
    }
  }

  /**
   * Update merge button state based on selection
   */
  updateMergeButtonState() {
    const mergeBtn = document.getElementById('execute-merge-btn');
    if (mergeBtn) {
      mergeBtn.disabled = this.selectedForMerge.size < 2;
      mergeBtn.textContent = `Merge Selected (${this.selectedForMerge.size})`;
    }
  }

  /**
   * Edit tracking details - shows modal with current data
   */
  async editTracking(trackingId) {
    try {
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/tracking/${trackingId}`
      );
      const data = await response.json();

      if (data.success) {
        const t = data.tracking;

        // Populate modal with tracking data
        document.getElementById('edit-tracking-id').value = trackingId;
        document.getElementById('edit-tracking-title').value = t.title || '';
        document.getElementById('edit-tracking-category').value = t.category || '';
        document.getElementById('edit-tracking-language').value = t.language || 'English';
        document.getElementById('edit-tracking-country').value = t.country || '';
        document.getElementById('edit-tracking-download-category').value =
          t.download_category || '';

        // Set tracking mode
        let mode = 'none';
        if (t.track_all_editions) mode = 'all';
        else if (t.track_new_only) mode = 'new';
        document.getElementById('edit-tracking-mode').value = mode;

        // Set delete from client checkbox
        document.getElementById('edit-delete-from-client').checked =
          t.delete_from_client_on_completion || false;

        // Set organization pattern
        document.getElementById('edit-tracking-org-pattern').value = t.organization_pattern || '';

        // Show modal
        document
          .getElementById(ELEMENT_IDS.EDIT_TRACKING_MODAL)
          .classList.remove(CSS_CLASSES.HIDDEN);
      }
    } catch (err) {
      console.error('Error loading tracking details:', err);
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Failed to load tracking details', 'error');
    }
  }

  /**
   * Search for issues of a tracked periodical
   */
  async searchForIssues(trackingId, title, language = null, country = null, category = null) {
    try {
      // Show loading spinner
      const issuesContent = document.getElementById('search-issues-content');
      issuesContent.innerHTML = `
        <div style="text-align: center; padding: 60px;">
          <div class="loading-spinner"></div>
          <p style="margin-top: 20px; color: var(--text-secondary);">Searching for issues...</p>
        </div>`;
      document.getElementById(ELEMENT_IDS.SEARCH_ISSUES_MODAL).classList.remove(CSS_CLASSES.HIDDEN);

      // Store tracking_id for later use in downloadIssue
      window.currentTrackingId = trackingId;

      // Build query parameters
      const params = new URLSearchParams();
      params.append('query', title);
      params.append('tracking_id', trackingId);
      if (language) params.append('language', language);
      if (country) params.append('country', country);
      if (category) params.append('category', category);

      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/search-providers?${params.toString()}`,
        { method: 'POST' }
      );
      const data = await response.json();

      if (data.found && data.results.length > 0) {
        // Parse and curate results
        const curatedIssues = this.parseAndCurateIssues(data.results);
        this.displayCuratedIssues(curatedIssues, title);
      } else {
        let errorInfo = '';
        if (data.provider_errors && data.provider_errors.length > 0) {
          errorInfo = `<div style="margin-top: 15px; padding: 10px; background: #ffebee; color: var(--error-color); border-radius: 4px; font-size: 0.9em;"><strong>Provider Errors:</strong><br>${data.provider_errors.join('<br>')}</div>`;
        }
        issuesContent.innerHTML = `<div style="text-align: center; padding: 40px;"><p>No issues found for "${title}"</p>${errorInfo}</div>`;
      }
    } catch (err) {
      console.error('Error searching issues:', err);
      const issuesContent = document.getElementById('search-issues-content');
      issuesContent.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--error-color);"><p>Failed to search for issues</p><p style="font-size: 0.9em; margin-top: 10px;">${err.message}</p></div>`;
    }
  }

  /**
   * Parse and organize issues by year
   */
  parseAndCurateIssues(results) {
    const _issues = [];
    const issueMap = new Map();

    results.forEach((result) => {
      const parsed = this.parseIssueTitle(result.title);
      if (parsed) {
        // If month/issue not found in title, try to extract from publication_date
        if (parsed.month === 0 && result.publication_date) {
          try {
            const pubDate = new Date(result.publication_date);
            if (!isNaN(pubDate.getTime())) {
              parsed.month = pubDate.getMonth() + 1; // getMonth() returns 0-11
            }
          } catch (e) {
            // Ignore date parsing errors
          }
        }

        // Create unique key including season and title to avoid over-deduplication
        // Include the original title hash to ensure different issues don't collide
        const titleHash = result.title.replace(/\s+/g, '-').substring(0, 30);
        const key = `${parsed.year}-${parsed.month}-${parsed.issue}-${parsed.season || ''}-${titleHash}`;

        if (!issueMap.has(key)) {
          // Extract language variant from title if present
          const langMatch = result.title.match(
            /\b(German|Dutch|French|Spanish|Italian|English|DE|NL|FR|ES|IT|EN|USA|UK)\b/i
          );
          const language = langMatch ? langMatch[0] : '';

          issueMap.set(key, {
            ...parsed,
            title: result.title,
            provider: result.provider,
            url: result.url,
            publication_date: result.publication_date,
            already_downloaded: result.already_downloaded || false,
            language: language,
            variants: [result], // Store all variants
          });
        } else {
          // Add to variants if it's a different language edition
          const existing = issueMap.get(key);
          existing.variants.push(result);

          // If already downloaded, mark the combined entry as downloaded
          if (result.already_downloaded) {
            existing.already_downloaded = true;
          }
        }
      }
    });

    // Sort by year desc, month desc, issue desc
    const sortedIssues = Array.from(issueMap.values()).sort((a, b) => {
      if (b.year !== a.year) return b.year - a.year;
      if (b.month !== a.month) return b.month - a.month;
      return b.issue - a.issue;
    });

    // Group by year
    const grouped = {};
    sortedIssues.forEach((issue) => {
      if (!grouped[issue.year]) {
        grouped[issue.year] = [];
      }
      grouped[issue.year].push(issue);
    });

    return grouped;
  }

  /**
   * Parse issue title to extract year, month, issue number, season
   */
  parseIssueTitle(title) {
    let year = null;
    let issue = null;
    let month = null;
    let season = null;

    // First, try to extract season
    const seasonMatch = title.match(/\b(Spring|Summer|Fall|Autumn|Winter)\b/i);
    if (seasonMatch) {
      season = seasonMatch[1].charAt(0).toUpperCase() + seasonMatch[1].slice(1).toLowerCase();
    }

    // Extract year-month pattern (e.g., "2007-11" or "2007 11")
    const yearMonthMatch = title.match(/(\d{4})[\s.-](\d{1,2})(?:\D|$)/);
    if (yearMonthMatch) {
      year = parseInt(yearMonthMatch[1]);
      const num = parseInt(yearMonthMatch[2]);
      if (num >= 1 && num <= 12) {
        month = num;
      }
    }

    // If no year-month found, try other patterns
    if (!year) {
      const patterns = [
        /(?:No\.|Issue|#)\.?(\d+)\.?(\d{4})/, // No.405.2026 or Issue.12.2025
        /(\d{4})[\s.](?:Issue|No\.)?[\s.]?(\d+)/, // 2026 No. 405 or 2026 405
        /Vol\.?(\d+).*?(\d{4})/, // Vol.123 2026
        /(\d{4})/, // Just a year
      ];

      for (const pattern of patterns) {
        const match = title.match(pattern);
        if (match) {
          if (match.length === 2) {
            const num = parseInt(match[1]);
            if (num > 1900 && num < 2100) {
              year = num;
              break;
            }
          } else {
            const num1 = parseInt(match[1]);
            const num2 = parseInt(match[2]);

            if (num2 > 1900 && num2 < 2100) {
              year = num2;
              issue = num1;
            } else if (num1 > 1900 && num1 < 2100) {
              year = num1;
              issue = num2;
            }

            if (year) break;
          }
        }
      }
    }

    // Try to extract month name (only if not already found)
    if (!month) {
      const monthMatch = title.match(
        /\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/i
      );
      if (monthMatch) {
        const lowerMonth = monthMatch[1].toLowerCase();
        month =
          MONTH_NAMES_LOWER.indexOf(lowerMonth) + 1 ||
          MONTH_ABBR_LOWER.indexOf(lowerMonth) + 1 ||
          0;
      }
    }

    if (year) {
      return { year, issue: issue || 0, month: month || 0, season: season || null };
    }

    return null;
  }

  /**
   * Toggle tracking for a single issue
   */
  async toggleIssueTracking(trackingId, editionId, track) {
    try {
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/tracking/${trackingId}/editions/${editionId}/track?track=${track}`,
        { method: 'POST' }
      );
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus(
          'tracking-status',
          `Issue ${track ? 'marked for' : 'removed from'} tracking (${data.total_selected} total)`,
          'success'
        );
        setTimeout(
          () => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS),
          TIMEOUTS.AUTO_HIDE_SUCCESS
        );
        return true;
      } else {
        throw new Error(data.message || 'Failed to update tracking');
      }
    } catch (error) {
      console.error('Error toggling issue tracking:', error);
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `Error: ${error.message}`, 'error');
      return false;
    }
  }

  /**
   * Display curated issues grouped by year
   */
  displayCuratedIssues(groupedByYear, title) {
    const issuesContent = document.getElementById('search-issues-content');

    if (Object.keys(groupedByYear).length === 0) {
      issuesContent.innerHTML = `<div style="text-align: center; padding: 40px;"><p>No issues could be parsed for "${title}"</p></div>`;
      return;
    }

    let html = `<h3>Available Issues for "${title}"</h3><div style="max-height: 70vh; overflow-y: auto;">`;

    const years = Object.keys(groupedByYear).sort((a, b) => b - a);

    years.forEach((year) => {
      const issues = groupedByYear[year];
      html += `<div style="margin-bottom: 20px;">
        <h4 style="color: var(--primary-color); margin-bottom: 10px;">📅 ${year}</h4>
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px;">`;

      issues.forEach((issue) => {
        // Create display label based on available information
        let displayLabel;

        // Priority 1: Season (if present)
        if (issue.season) {
          displayLabel = issue.season;
        }
        // Priority 2: Month and Issue
        else if (issue.month > 0 && issue.issue > 0) {
          displayLabel = `${NUMBER_TO_MONTH[issue.month]} #${issue.issue}`;
        }
        // Priority 3: Month only
        else if (issue.month > 0) {
          displayLabel = NUMBER_TO_MONTH[issue.month];
        }
        // Priority 4: Issue number only
        else if (issue.issue > 0) {
          displayLabel = `#${issue.issue}`;
        }
        // Fallback: Just show year (shouldn't happen often now)
        else {
          displayLabel = `${issue.year}`;
        }

        const isLibraryOnly = !issue.url || issue.url === '';
        const isDownloaded = issue.already_downloaded;
        const hasFailed = issue.download_failed || false;

        const backgroundColor = isLibraryOnly ? 'var(--surface)' : 'var(--surface-variant)';
        const borderColor = isLibraryOnly
          ? 'var(--border-color)'
          : isDownloaded
            ? '#4caf50'
            : hasFailed
              ? '#f44336'
              : 'transparent';
        const opacity = isLibraryOnly ? '0.85' : isDownloaded ? '0.7' : hasFailed ? '0.85' : '1';
        const textColor = isLibraryOnly ? 'var(--text-secondary)' : 'var(--text-primary)';

        const providerDisplay = isLibraryOnly
          ? ''
          : `<div style="font-size: 10px; color: var(--text-secondary); margin-top: 6px;">${issue.provider}</div>`;
        const statusBadge = isLibraryOnly
          ? '<div style="font-size: 10px; margin-top: 6px; color: var(--text-secondary); font-weight: 600;">📚 In Library</div>'
          : isDownloaded
            ? '<div style="font-size: 10px; margin-top: 6px; color: #4caf50; font-weight: 600;">✓ Have</div>'
            : hasFailed
              ? '<div style="font-size: 10px; margin-top: 6px; color: #f44336; font-weight: 600;">✗ Failed</div>'
              : '';

        // Show language variants badge if multiple editions exist
        const variantsBadge =
          issue.variants && issue.variants.length > 1
            ? `<div style="font-size: 10px; margin-top: 6px; color: var(--primary-color); font-weight: 600;">🌍 ${issue.variants.length} editions</div>`
            : issue.language
              ? `<div style="font-size: 10px; margin-top: 6px; color: var(--text-secondary);">${issue.language}</div>`
              : '';

        let cardHtml = `<div style="
          padding: 12px;
          background: ${backgroundColor};
          border-radius: 5px;
          text-align: center;
          cursor: ${isLibraryOnly ? 'default' : 'pointer'};
          transition: all 0.2s;
          border: 2px solid ${borderColor};
          opacity: ${opacity};
          color: ${textColor};
        "`;

        if (!isLibraryOnly) {
          // Store variants globally for selection
          const issueKey = `${issue.year}-${issue.month}-${issue.issue}`;
          window.issueVariants = window.issueVariants || {};
          window.issueVariants[issueKey] = issue.variants;

          cardHtml += ` onclick='selectIssueWithVariants("${issueKey}", ${isDownloaded}, ${hasFailed})'`;
        }

        cardHtml += `>
          <div style="font-weight: 600; font-size: 14px;">${displayLabel}</div>
          ${providerDisplay}
          ${statusBadge}
          ${variantsBadge}
        </div>`;

        html += cardHtml;
      });

      html += `</div></div>`;
    });

    html += `</div>`;
    issuesContent.innerHTML = html;
  }

  /**
   * Delete tracking
   */
  async deleteTracking(trackingId, title) {
    // Show confirmation modal with periodical name
    const confirmed = await UIUtils.confirm(
      'Remove Tracking',
      `Are you sure you want to remove "${title}" from tracking?`
    );
    if (!confirmed) return;

    try {
      const response = await APIClient.delete(`/api/periodicals/tracking/${trackingId}`);
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Tracking removed', 'success');
        this.loadTrackedPeriodicals();
        setTimeout(
          () => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS),
          TIMEOUTS.AUTO_HIDE_STATUS
        );
      } else {
        UIUtils.showStatus(
          ELEMENT_IDS.TRACKING_STATUS,
          data.message || 'Error removing tracking',
          'error'
        );
      }
    } catch (error) {
      console.error('Error deleting tracking:', error);
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Error removing tracking', 'error');
    }
  }

  /**
   * Reset the tracking workflow
   */
  resetTracking() {
    this.currentPeriodicalMetadata = null;
    const titleInput = document.getElementById('new-tracking-title');
    if (titleInput) titleInput.value = '';

    // Clear search query and results
    const searchQuery = document.getElementById('tracking-search-query');
    if (searchQuery) searchQuery.value = '';

    const searchResult = document.getElementById(ELEMENT_IDS.TRACKING_SEARCH_RESULT);
    if (searchResult) searchResult.classList.add(CSS_CLASSES.HIDDEN);

    const searchError = document.getElementById('tracking-search-error');
    if (searchError) searchError.classList.add(CSS_CLASSES.HIDDEN);
  }

  /**
   * Open track new periodical modal
   */
  openTrackNewPeriodicalModal() {
    this.resetTracking();
    document.getElementById('track-new-periodical-modal').classList.remove(CSS_CLASSES.HIDDEN);
  }

  /**
   * Close track new periodical modal
   */
  closeTrackNewPeriodicalModal() {
    document.getElementById('track-new-periodical-modal').classList.add(CSS_CLASSES.HIDDEN);
    this.resetTracking();
  }

  /**
   * Update tracking mode (called when radio buttons change)
   */
  updateTrackingMode() {
    // This is just a placeholder - the actual mode is read when saving
    // Could add visual feedback here if needed
  }
}

// Create singleton instance
export const tracking = new TrackingManager();

// Expose tracking manager globally
window.trackingManager = tracking;

// Modal management functions
window.closeEditTrackingModal = function () {
  document.getElementById(ELEMENT_IDS.EDIT_TRACKING_MODAL).classList.add(CSS_CLASSES.HIDDEN);
};

window.closeSearchIssuesModal = function () {
  document.getElementById(ELEMENT_IDS.SEARCH_ISSUES_MODAL).classList.add(CSS_CLASSES.HIDDEN);
};

// Save edited tracking
window.saveEditedTracking = async function () {
  const trackingId = document.getElementById('edit-tracking-id').value;
  const title = document.getElementById('edit-tracking-title').value;
  const category = document.getElementById('edit-tracking-category').value;
  const language = document.getElementById('edit-tracking-language').value;
  const downloadCategory = document.getElementById('edit-tracking-download-category').value.trim();
  const country = document.getElementById('edit-tracking-country').value;
  const mode = document.getElementById('edit-tracking-mode').value;
  const deleteFromClient = document.getElementById('edit-delete-from-client').checked;
  const orgPattern = document.getElementById('edit-tracking-org-pattern').value.trim();

  try {
    const response = await APIClient.put(`/api/periodicals/tracking/${trackingId}`, {
      title,
      category,
      language,
      country,
      download_category: downloadCategory || null,
      track_all_editions: mode === 'all',
      track_new_only: mode === 'new',
      delete_from_client_on_completion: deleteFromClient,
      organization_pattern: orgPattern || null, // Send null if empty to use global default
    });

    const result = await response.json();
    if (result.success) {
      window.closeEditTrackingModal();
      tracking.loadTrackedPeriodicals();
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Tracking updated successfully', 'success');
      setTimeout(() => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS), TIMEOUTS.AUTO_HIDE_STATUS);
    } else {
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Failed to update tracking', 'error');
    }
  } catch (err) {
    console.error('Error updating tracking:', err);
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Failed to update tracking', 'error');
  }
};

// Select and download issue with language variant selection
window.selectIssueWithVariants = function (issueKey, alreadyDownloaded, hasFailed) {
  const variants = window.issueVariants[issueKey];

  if (!variants || variants.length === 0) {
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'No variants available', 'error');
    return;
  }

  // If only one variant, download directly
  if (variants.length === 1) {
    const variant = variants[0];
    window.selectIssue(
      variant.title,
      variant.provider,
      variant.url,
      variant.already_downloaded || alreadyDownloaded,
      variant.download_failed || hasFailed
    );
    return;
  }

  // Multiple variants - show selection modal
  const modalHTML = `
    <div id="language-variant-modal" class="modal" style="display: flex;">
      <div class="modal-content" style="max-width: 500px;">
        <span class="close" onclick="closeLangVariantModal()">&times;</span>
        <h2>Select Language Edition</h2>
        <p style="color: var(--text-secondary); margin-bottom: 20px;">Multiple language editions available:</p>
        <div id="variant-options" style="display: flex; flex-direction: column; gap: 10px;"></div>
      </div>
    </div>
  `;

  document.body.insertAdjacentHTML('beforeend', modalHTML);

  const optionsDiv = document.getElementById('variant-options');
  variants.forEach((variant, index) => {
    // Detect language using centralized constants
    let detectedLang = '';
    let detectedCountry = '';

    if (window.appConstants?.language_keywords) {
      for (const [lang, keywords] of Object.entries(window.appConstants.language_keywords)) {
        if (keywords.some((kw) => variant.title.toLowerCase().includes(kw.toLowerCase()))) {
          detectedLang = lang;
          break;
        }
      }
    }

    if (window.appConstants?.country_indicators) {
      for (const [country, indicators] of Object.entries(window.appConstants.country_indicators)) {
        if (indicators.some((ind) => variant.title.toLowerCase().includes(ind.toLowerCase()))) {
          detectedCountry = country;
          break;
        }
      }
    }

    // Detect special editions (Traveler, Kids, etc.)
    const editionMatch = variant.title.match(
      /\b(Traveler|Traveller|Kids|Junior|Special|History|Science)\b/i
    );
    const edition = editionMatch ? editionMatch[0] : '';

    // Build display label
    let displayLabel = detectedCountry || detectedLang || `Edition ${index + 1}`;
    if (edition) {
      displayLabel =
        displayLabel !== `Edition ${index + 1}` ? `${displayLabel} - ${edition}` : edition;
    }

    const isDownloaded = variant.already_downloaded || alreadyDownloaded;
    const downloadFailed = variant.download_failed || hasFailed || false;
    const statusBadge = isDownloaded
      ? ' <span class="variant-in-library">✓ In Library</span>'
      : downloadFailed
        ? ' <span class="variant-failed">✗ Failed</span>'
        : '';

    const btn = document.createElement('button');
    // Different styling for re-download vs new download vs failed
    if (isDownloaded) {
      btn.className = 'btn-variant btn-variant-downloaded';
    } else if (downloadFailed) {
      btn.className = 'btn-variant btn-variant-failed';
    } else {
      btn.className = 'btn-variant btn-variant-new';
    }
    btn.innerHTML = `
      <div class="variant-label">${displayLabel}${statusBadge}</div>
      <div class="variant-title">${variant.title}</div>
    `;
    btn.onclick = () => {
      window.closeLangVariantModal();
      window.selectIssue(
        variant.title,
        variant.provider,
        variant.url,
        isDownloaded,
        downloadFailed
      );
    };
    optionsDiv.appendChild(btn);
  });
};

window.closeLangVariantModal = function () {
  const modal = document.getElementById('language-variant-modal');
  if (modal) modal.remove();
};

// Select and download issue
window.selectIssue = async function (title, provider, url, alreadyDownloaded, downloadFailed) {
  const isLibraryOnly = !url || url === '';

  if (isLibraryOnly) {
    UIUtils.showStatus(
      ELEMENT_IDS.TRACKING_STATUS,
      'This issue is already in your library',
      'success'
    );
    setTimeout(() => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS), 3000);
    return;
  }

  // Build confirmation message with filename
  let confirmMessage = `<p><strong>File:</strong> ${title}</p><p><strong>Provider:</strong> ${provider}</p>`;
  if (alreadyDownloaded) {
    confirmMessage +=
      '<p style="color: #ff9800; margin-top: 10px;">⚠️ You already have this issue in your library.</p><p>Re-download it anyway?</p>';
  } else if (downloadFailed) {
    confirmMessage +=
      '<p style="color: #f44336; margin-top: 10px;">⚠️ This download failed previously.</p><p>The file may be corrupt or unavailable. Try again anyway?</p>';
  } else {
    confirmMessage += '<p style="margin-top: 10px;">Download this issue?</p>';
  }

  const shouldDownload = await UIUtils.confirm('Download Issue', confirmMessage);
  if (shouldDownload) {
    window.downloadIssue(title, url, provider);
  }
};

/**
 * Open modal to select tracking records to merge
 */
window.openMergeModal = async function () {
  const tracking = window.trackingManager;
  if (!tracking) return;

  try {
    const response = await APIClient.get('/api/periodicals/tracking?limit=1000');
    const data = await response.json();

    const items = data.tracked_magazines || [];

    console.log('Merge modal check:', {
      responseOk: response.ok,
      itemsLength: items.length,
      shouldShowWarning: !response.ok || items.length < 2,
    });

    if (!response.ok || items.length < 2) {
      console.log('Showing warning status');
      UIUtils.showStatus(
        ELEMENT_IDS.TRACKING_STATUS,
        '⚠️ You need at least 2 tracked periodicals to merge',
        'warning'
      );
      return;
    }

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.id = 'merge-selection-modal';

    const trackingOptions = items
      .map(
        (item) => `
      <div class="merge-select-item">
        <input type="checkbox" id="merge-check-${item.id}" value="${item.id}" class="merge-selection-checkbox">
        <label for="merge-check-${item.id}">
          <strong>${item.title}</strong><br>
          <span style="font-size: 12px; color: var(--text-secondary);">Language: ${item.language || 'Unknown'} | Country: ${item.country || 'N/A'}</span>
        </label>
      </div>
    `
      )
      .join('');

    modal.innerHTML = `
      <div class="modal-content" style="max-width: 600px;">
        <h3>🔀 Merge Tracking Records</h3>
        <p style="color: var(--text-secondary); margin-bottom: 20px;">Select 2 or more tracking records to merge. You'll choose which one to keep in the next step.</p>
        <div id="merge-selection-list" style="max-height: 400px; overflow-y: auto; margin-bottom: 20px;">
          ${trackingOptions}
        </div>
        <div style="display: flex; gap: 10px; justify-content: flex-end;">
          <button onclick="window.closeMergeSelectionModal()" class="btn-secondary">Cancel</button>
          <button id="continue-merge-btn" onclick="window.showMergeTargetSelection()" class="btn-primary" disabled>Continue</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.style.display = 'flex';

    // Add change listeners to checkboxes
    const checkboxes = modal.querySelectorAll('.merge-selection-checkbox');
    checkboxes.forEach((cb) => {
      cb.addEventListener('change', () => {
        const checkedCount = modal.querySelectorAll('.merge-selection-checkbox:checked').length;
        document.getElementById('continue-merge-btn').disabled = checkedCount < 2;
      });
    });
  } catch (error) {
    console.error('Error loading tracking records:', error);
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, '✗ Failed to load tracking records', 'error');
  }
};

/**
 * Close merge selection modal
 */
window.closeMergeSelectionModal = function () {
  const modal = document.getElementById('merge-selection-modal');
  if (modal) modal.remove();
};

/**
 * Show target selection after initial selection
 */
window.showMergeTargetSelection = async function () {
  const selectionModal = document.getElementById('merge-selection-modal');
  const checkboxes = selectionModal.querySelectorAll('.merge-selection-checkbox:checked');
  const selectedIds = Array.from(checkboxes).map((cb) => parseInt(cb.value));

  if (selectedIds.length < 2) {
    UIUtils.showStatus(
      ELEMENT_IDS.TRACKING_STATUS,
      '⚠️ Please select at least 2 tracking records',
      'warning'
    );
    return;
  }

  // Get the tracking data for selected items
  const response = await APIClient.get('/api/periodicals/tracking?limit=1000');
  const data = await response.json();
  const selectedItems = (data.tracked_magazines || []).filter((item) =>
    selectedIds.includes(item.id)
  );

  // Close selection modal
  window.closeMergeSelectionModal();

  // Show target modal
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'merge-target-modal';

  const options = selectedItems
    .map(
      (item) =>
        `<option value="${item.id}">${item.title} (${item.language || 'Unknown'} - ${item.country || 'N/A'})</option>`
    )
    .join('');

  modal.innerHTML = `
    <div class="modal-content">
      <h3>Select Target Tracking Record</h3>
      <p>Choose which tracking record to keep. All magazines and downloads from other selected records will be moved to this one.</p>
      <select id="merge-target-select" style="width: 100%; padding: 8px; margin: 16px 0;">
        ${options}
      </select>
      <input type="hidden" id="merge-source-ids" value="${selectedIds.join(',')}">
      <div style="margin-top: 20px; display: flex; gap: 10px; justify-content: flex-end;">
        <button onclick="window.closeMergeModal()" class="btn-secondary">Cancel</button>
        <button onclick="window.confirmMerge()" class="btn-primary">Merge</button>
      </div>
    </div>
  `;

  document.body.appendChild(modal);
  modal.classList.add(CSS_CLASSES.MODAL_VISIBLE);
};

/**
 * Close merge target selection modal
 */
window.closeMergeModal = function () {
  const modal = document.getElementById('merge-target-modal');
  if (modal) {
    modal.remove();
  }
};

/**
 * Confirm and execute the merge
 */
window.confirmMerge = async function () {
  const targetId = parseInt(document.getElementById('merge-target-select').value);
  const sourceIdsStr = document.getElementById('merge-source-ids').value;
  const allSelectedIds = sourceIdsStr.split(',').map((id) => parseInt(id));
  const sourceIds = allSelectedIds.filter((id) => id !== targetId);

  if (!targetId || sourceIds.length === 0) {
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, '⚠️ Invalid selection', 'warning');
    return;
  }

  try {
    const response = await APIClient.post(`/api/periodicals/tracking/${targetId}/merge`, {
      source_ids: sourceIds,
    });

    const data = await response.json();

    if (response.ok) {
      const filesMsg =
        data.files_reorganized > 0 ? `, reorganized ${data.files_reorganized} files` : '';
      UIUtils.showStatus(
        ELEMENT_IDS.TRACKING_STATUS,
        `${data.message}. Moved ${data.magazines_moved} magazines and ${data.submissions_moved} downloads${filesMsg}.`,
        'success'
      );
      window.closeMergeModal();
      const tracking = window.trackingManager;
      if (tracking) {
        tracking.loadTrackedPeriodicals();
      }
    } else {
      throw new Error(data.detail || 'Merge failed');
    }
  } catch (error) {
    console.error('Merge error:', error);
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `✗ ${error.message}`, 'error');
  }
};

// Download a single issue
window.downloadIssue = async function (title, url, provider) {
  try {
    const trackingId = window.currentTrackingId;
    if (!trackingId) {
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Error: No tracking ID available', 'error');
      return;
    }

    const response = await APIClient.post('/api/downloads/single-issue', {
      tracking_id: trackingId,
      title: title,
      url: url,
      provider: provider,
    });

    const data = await response.json();

    if (response.ok) {
      // Handle different submission statuses
      let message;
      if (data.status === 'queued') {
        message = '✓ Download queued (will be submitted when slot available)';
      } else if (data.job_id) {
        message = `✓ Download submitted! Job ID: ${data.job_id}`;
      } else {
        message = `✓ Download ${data.status}`;
      }

      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, message, 'success');
      setTimeout(() => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS), TIMEOUTS.AUTO_HIDE_LONG);
      window.closeSearchIssuesModal();
    } else {
      UIUtils.showStatus(
        ELEMENT_IDS.TRACKING_STATUS,
        data.detail || 'Failed to queue download',
        'error'
      );
    }
  } catch (err) {
    console.error('Download error:', err);
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `Error: ${err.message}`, 'error');
  }
};

// Expose functions globally for onclick handlers
window.openTrackNewPeriodicalModal = () => tracking.openTrackNewPeriodicalModal();
window.closeTrackNewPeriodicalModal = () => tracking.closeTrackNewPeriodicalModal();
window.saveNewTracking = async () => {
  const title = document.getElementById('new-tracking-title').value.trim();
  const category = document.getElementById('new-tracking-category').value;
  const language = document.getElementById('new-tracking-language').value || 'English';
  const country = document.getElementById('new-tracking-country').value;
  const downloadCategory = document.getElementById('new-tracking-download-category').value.trim();

  if (!title) {
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Please enter a title', 'error');
    return;
  }

  const trackingMode = document.getElementById('new-tracking-mode').value || 'all';

  try {
    // Build query string for the POST request
    const params = new URLSearchParams({
      title: title,
      language: language,
    });
    if (category) {
      params.append('category', category);
    }
    if (country) {
      params.append('country', country);
    }

    const response = await APIClient.post(`/api/periodicals/track?${params.toString()}`, {});

    const data = await response.json();

    if (data.success) {
      // Now update with the tracking mode, download category, and country
      const updateData = {
        track_all_editions: trackingMode === 'all',
        track_new_only: trackingMode === 'new',
        country: country || null,
      };
      if (downloadCategory) {
        updateData.download_category = downloadCategory;
      }
      await APIClient.put(`/api/periodicals/tracking/${data.tracking_id}`, updateData);

      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Tracking started successfully', 'success');
      tracking.closeTrackNewPeriodicalModal();
      tracking.loadTrackedPeriodicals();
      setTimeout(() => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS), TIMEOUTS.AUTO_HIDE_SUCCESS);
    } else {
      UIUtils.showStatus(
        ELEMENT_IDS.TRACKING_STATUS,
        data.message || 'Failed to start tracking',
        'error'
      );
    }
  } catch (error) {
    console.error('Error starting tracking:', error);
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `Error: ${error.message}`, 'error');
  }
};
window.saveTrackingPreferences = () => tracking.saveTrackingPreferences();
window.resetTracking = () => tracking.resetTracking();
window.updateTrackingMode = () => tracking.updateTrackingMode();
window.setSortField = (field) => tracking.setSortField(field);
window.toggleSortOrder = () => tracking.toggleSortOrder();
window.editTracking = (id) => tracking.editTracking(id);
window.searchForIssues = (id, title, language, country, category) =>
  tracking.searchForIssues(id, title, language, country, category);
window.deleteTracking = (id, title) => tracking.deleteTracking(id, title);
