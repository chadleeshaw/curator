/**
 * Tracking Module
 * Handles periodical tracking, metadata search, and issue downloads
 * @module tracking
 */

import { APIClient, APIHelper } from '../core/api.js';
import { UIUtils, SortManager, FilterManager } from '../core/ui-utils.js';
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
  API_LIMITS,
} from '../core/constants.js';
import { escapeHtml } from '../readers/reader-utils.js';
import { stacks } from './stacks.js';

/** @type {string[]} Supported languages loaded from backend */
let SUPPORTED_LANGUAGES = [];
/** @type {string[]} Content categories loaded from backend */
let CATEGORIES = [];
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
    this.sortManager = new SortManager('title', 'asc', () => this.applyFiltersAndRender());
    /** @type {FilterManager} Manager for tracking filters */
    this.filterManager = new FilterManager('trackingFilters', () => this.applyFiltersAndRender());
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
    /** @type {Array} All tracked periodicals loaded from API (unfiltered) */
    this.allTracked = [];
    /** @type {boolean} Whether periodicals have been loaded at least once */
    this.periodicalsLoaded = false;
    /** @type {string} Current source filter for search results ('all', 'newsnab', 'internet_archive', 'rss') */
    this.sourceFilter = 'all';
    /** @type {Object|null} Last curated issues for re-rendering with filters */
    this.lastCuratedIssues = null;
    /** @type {string|null} Last search title for re-rendering */
    this.lastSearchTitle = null;
    /** @type {Map} Stack search results for bulk download */
    this.stackSearchResults = new Map();
    /** @type {Array} All stacks loaded from API (includes empty stacks) */
    this.allStacks = [];
  }

  /**
   * Initialize the tracking manager
   */
  async init() {
    await this.loadConstants();
    this.populateFormDropdowns();
    this.loadCategories();
    this.loadFilterState();
  }

  /**
   * Load constants from backend API
   *
   * @returns {Promise<void>}
   * @throws {Error} When API request fails
   */
  async loadConstants() {
    try {
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.get('/api/constants');
          return await response.json();
        },
        'Tracking',
        ELEMENT_IDS.TRACKING_STATUS
      );
      if (data.success) {
        SUPPORTED_LANGUAGES = data.languages ?? [];
        CATEGORIES = data.categories ?? [];
        ISO_COUNTRIES = data.countries ?? {};
        LANGUAGE_TO_COUNTRY = data.language_to_country ?? {};
        COUNTRY_INDICATORS = data.country_indicators ?? {};
        LANGUAGE_KEYWORDS = data.language_keywords ?? {};
      }
    } catch (error) {
      // Already logged and displayed by APIHelper
    }
  }

  /**
   * Load categories from constants and populate all category dropdowns
   *
   * @returns {void}
   */
  loadCategories() {
    if (CATEGORIES.length === 0) return;

    // Populate the filter dropdown
    const filterDropdown = document.getElementById('tracking-category-filter');
    if (filterDropdown) {
      filterDropdown.innerHTML = '<option value="all">All</option>';
      CATEGORIES.forEach((category) => {
        const option = document.createElement('option');
        option.value = category;
        option.textContent = category;
        filterDropdown.appendChild(option);
      });
      if (this.filterManager.categoryFilter) {
        filterDropdown.value = this.filterManager.categoryFilter;
      }
    }

    // Populate form category dropdowns (edit, new, import)
    const formDropdowns = [
      { id: 'edit-tracking-category', defaultLabel: 'Auto-detect from title', defaultValue: '' },
      { id: 'new-tracking-category', defaultLabel: 'Auto-detect from title', defaultValue: '' },
      { id: 'import-category', defaultLabel: 'Auto-detect from title', defaultValue: 'auto' },
    ];

    formDropdowns.forEach(({ id, defaultLabel, defaultValue }) => {
      const dropdown = document.getElementById(id);
      if (!dropdown) return;

      const currentValue = dropdown.value;
      dropdown.innerHTML = '';

      // Add default option
      const defaultOption = document.createElement('option');
      defaultOption.value = defaultValue;
      defaultOption.textContent = defaultLabel;
      dropdown.appendChild(defaultOption);

      // Add each category
      CATEGORIES.forEach((category) => {
        const option = document.createElement('option');
        option.value = category;
        option.textContent = category;
        dropdown.appendChild(option);
      });

      // Restore previous value if valid
      if (currentValue) {
        dropdown.value = currentValue;
      }
    });
  }

  /**
   * Load saved filter state from localStorage
   *
   * @returns {void}
   */
  loadFilterState() {
    try {
      // FilterManager handles loading from localStorage
      this.filterManager.loadState();

      // Update UI elements
      this.filterManager.updateUI(
        'tracking-category-filter',
        'tracking-language-filter',
        'tracking-search-input'
      );

      // Update sort dropdown
      const sortDropdown = document.getElementById('tracking-sort-select');
      if (sortDropdown) sortDropdown.value = this.sortManager.field;

      // Update sort toggle button
      this.updateTrackingSortToggleButton();

      console.log('[Tracking] Loaded saved filter state:', {
        category: this.filterManager.categoryFilter,
        language: this.filterManager.languageFilter,
        sortField: this.sortManager.field,
        sortOrder: this.sortManager.order,
      });
    } catch (error) {
      console.warn('[Tracking] Failed to load saved filters:', error);
    }
  }

  /**
   * Save current filter state to localStorage
   *
   * @returns {void}
   */
  saveFilterState() {
    try {
      // FilterManager handles saving to localStorage
      this.filterManager.saveState();

      // Also save sort settings
      const filters = {
        category: this.filterManager.categoryFilter,
        language: this.filterManager.languageFilter,
        sortField: this.sortManager.field,
        sortOrder: this.sortManager.order,
      };
      localStorage.setItem('trackingFilters', JSON.stringify(filters));
    } catch (error) {
      console.warn('[Tracking] Failed to save filters:', error);
    }
  }

  /**
   * Update the sort toggle button display
   */
  updateTrackingSortToggleButton() {
    const button = document.getElementById('tracking-sort-toggle');
    if (button) {
      button.textContent = this.sortManager.order === 'asc' ? '↑' : '↓';
      button.title = `Sort ${this.sortManager.order === 'asc' ? 'descending' : 'ascending'}`;
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
          if (lang === 'English') {
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
      // For Internet Archive items, use the full title as-is (each item is unique)
      // and get file count from metadata
      const isInternetArchive = result.provider?.toLowerCase() === 'internet_archive';

      // Extract clean title from the result title/filename
      let cleanTitle = result.title;

      if (!isInternetArchive) {
        // Extract periodical name from filename (e.g., "PC.Gamer.US.No.405..." -> "PC Gamer US")
        const match = result.title.match(
          /^([A-Za-z0-9\.\s]+?)(?:\.No\.|\.Issue\.|\.E|\.201|\.202)/i
        );
        if (match) {
          cleanTitle = match[1].replace(/\./g, ' ').trim();
        }
      }

      // Normalize title for deduplication (for non-IA items)
      // For IA items, use identifier to keep them separate
      const normalizedKey = isInternetArchive
        ? result.metadata?.identifier || result.title
        : cleanTitle.toLowerCase().replace(/\s+/g, ' ').trim();

      if (!uniquePeriodicals[normalizedKey]) {
        // Get file count from IA metadata if available
        const iaItemCount = result.metadata?.item_count;
        // Check if this is a collection archive (bundles of multiple issues)
        const isCollection = result.metadata?.is_collection || false;

        uniquePeriodicals[normalizedKey] = {
          displayTitle: cleanTitle,
          count: iaItemCount || 0,
          firstResult: result,
          isInternetArchive: isInternetArchive,
          hasItemCount: iaItemCount != null && iaItemCount > 0,
          isCollection: isCollection,
        };
      }
      // Only increment count for non-IA items (grouping search results)
      if (!isInternetArchive) {
        uniquePeriodicals[normalizedKey].count++;
      }
    });

    // Convert to array and sort: collections first, then by count (most common first)
    const periodicalsList = Object.values(uniquePeriodicals).sort((a, b) => {
      // Collections always come first
      if (a.isCollection && !b.isCollection) return -1;
      if (!a.isCollection && b.isCollection) return 1;
      // Then sort by count
      return b.count - a.count;
    });

    container.innerHTML = '<h4>Select a Periodical Edition:</h4><div class="search-results"></div>';
    const resultsContainer = container.querySelector('.search-results');

    periodicalsList.forEach((periodical) => {
      const result = periodical.firstResult;
      const publisher = result.metadata?.publisher || '';

      const div = document.createElement('div');
      div.className = CSS_CLASSES.RESULT_ITEM;

      // For IA items, show file count or indicate it needs to be fetched
      let countDisplay;
      if (periodical.isInternetArchive) {
        if (periodical.hasItemCount) {
          countDisplay = `<strong>Files:</strong> ${periodical.count}`;
        } else {
          countDisplay =
            '<strong>Files:</strong> <span class="ia-file-count" data-identifier="' +
            (result.metadata?.identifier || '') +
            '">Loading...</span>';
        }
      } else {
        countDisplay = `<strong>Available Issues:</strong> ${periodical.count}`;
      }

      // Show provider badge for IA items
      const providerBadge = periodical.isInternetArchive
        ? '<span class="provider-badge ia-badge">🏛️ Internet Archive</span>'
        : '';

      // Show collection badge for collection archives
      const collectionBadge = periodical.isCollection
        ? '<span class="provider-badge collection-badge">📦 Collection</span>'
        : '';

      div.innerHTML = `
        <div class="result-info">
          <h5 class="result-title">${periodical.displayTitle}</h5>
          ${collectionBadge}${providerBadge}
          <p class="result-detail">${countDisplay}</p>
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

    // Fetch file counts for IA items that don't have them
    this.fetchIAFileCounts();
  }

  /**
   * Fetch file counts for Internet Archive items that are missing them
   */
  async fetchIAFileCounts() {
    const fileCountElements = document.querySelectorAll('.ia-file-count');
    if (fileCountElements.length === 0) return;

    for (const element of fileCountElements) {
      const identifier = element.dataset.identifier;
      if (!identifier) {
        element.textContent = '1+';
        continue;
      }

      try {
        // Fetch metadata from IA to get file count
        const response = await fetch(`https://archive.org/metadata/${identifier}`);
        if (response.ok) {
          const metadata = await response.json();
          const files = metadata.files || [];
          // Count PDF files (Text PDF, Image Container PDF, etc.)
          const pdfCount = files.filter(
            (f) => f.format && (f.format.toLowerCase().includes('pdf') || f.format === 'Text PDF')
          ).length;
          element.textContent = pdfCount > 0 ? pdfCount : '1+';
        } else {
          element.textContent = '1+';
        }
      } catch {
        element.textContent = '1+';
      }
    }
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
      `Selected: ${result.title}. Review the fields below and click "Start Tracking".`,
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
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/periodicals/tracking/save', preferences);
          return await response.json();
        },
        'Tracking',
        ELEMENT_IDS.TRACKING_STATUS
      );

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
      // Already logged by APIHelper
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
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.authenticatedFetch(
          `/api/periodicals/tracking?sort_by=${field}&sort_order=${order}&limit=${API_LIMITS.TRACKING_LIST}`
        );
        return await response.json();
      }, 'Tracking');

      const tracked = data.tracked_magazines ?? data.tracked ?? [];

      // Store all tracked periodicals unfiltered
      this.allTracked = tracked;
      this.periodicalsLoaded = true;

      // Fetch all stacks so empty stacks still appear in the UI
      try {
        const stacksData = await APIHelper.executeWithErrorHandling(async () => {
          const resp = await APIClient.authenticatedFetch('/api/stacks');
          return await resp.json();
        }, 'Stacks');
        this.allStacks = stacksData.stacks ?? [];
      } catch {
        this.allStacks = [];
      }

      // Load unique languages for language filter
      await this.populateLanguageDropdown();

      // Apply filters and render
      this.applyFiltersAndRender();
    } catch (error) {
      console.error('Error loading tracked periodicals:', error);
    }
  }

  /**
   * Apply current filters and render the filtered tracking list
   *
   * @returns {void}
   */
  applyFiltersAndRender() {
    const container = document.getElementById('tracked-list');
    if (!container) return;

    // Don't apply filters if periodicals haven't been loaded yet
    if (!this.periodicalsLoaded) {
      console.log('[Tracking] No periodicals loaded yet, skipping filter application');
      return;
    }

    container.innerHTML = '';

    // Use filterManager to apply filters
    const filtered = this.filterManager.applyFilters(this.allTracked, {
      getCategoryFn: (t) => t.category || 'Unknown',
      getLanguageFn: (t) => t.language || 'English',
      getTitleFn: (t) => t.title || '',
    });

    // Update statistics with filtered results
    this.updateTrackingStatistics(filtered);

    // Render results
    if (filtered.length === 0) {
      const filterDesc = this.filterManager.getActiveFilterDescription();
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📚</div>
          <h3>No Tracked Periodicals Found</h3>
          <p>No periodicals found${filterDesc}.</p>
          ${
            !this.filterManager.hasActiveFilters()
              ? '<button onclick="openTrackNewPeriodicalModal()" class="btn-primary" style="margin-top: 16px;">📌 Track Your First Periodical</button>'
              : '<button onclick="clearTrackingFilters()" class="btn-secondary" style="margin-top: 16px;">✕ Clear Filters</button>'
          }
        </div>
      `;
      return;
    }

    // Group items by stack while tracking first-seen position for sort interleaving
    const stackGroups = new Map(); // stack_id -> { name, slug, items: [], firstIndex }
    const ungrouped = []; // { trackingItem, index }

    filtered.forEach((trackingItem, index) => {
      if (trackingItem.stack_id && trackingItem.stack_name) {
        if (!stackGroups.has(trackingItem.stack_id)) {
          stackGroups.set(trackingItem.stack_id, {
            name: trackingItem.stack_name,
            slug: trackingItem.stack_slug,
            description: trackingItem.stack_description || '',
            categories: trackingItem.stack_categories || [],
            items: [],
            firstIndex: index,
          });
        }
        stackGroups.get(trackingItem.stack_id).items.push(trackingItem);
      } else {
        ungrouped.push({ trackingItem, index });
      }
    });

    // Inject empty stacks that have no members in the filtered tracking list
    for (const stack of this.allStacks) {
      if (!stackGroups.has(stack.id)) {
        stackGroups.set(stack.id, {
          name: stack.name,
          slug: stack.slug,
          description: stack.description || '',
          categories: stack.categories || [],
          items: [],
          firstIndex: -1,
        });
      }
    }

    // Build a unified render list so stacks interleave with ungrouped items
    // based on the server-side sort order (position of first member)
    const renderItems = [];

    stackGroups.forEach((group, stackId) => {
      renderItems.push({ type: 'stack', stackId, group, sortIndex: group.firstIndex });
    });

    ungrouped.forEach(({ trackingItem, index }) => {
      renderItems.push({ type: 'item', trackingItem, sortIndex: index });
    });

    // Sort: stacks at top only when sorting by title, otherwise interleave by sort order
    const stacksOnTop = this.sortManager.field === 'title';
    renderItems.sort((a, b) => {
      if (stacksOnTop && a.type !== b.type) return a.type === 'stack' ? -1 : 1;
      return a.sortIndex - b.sortIndex;
    });

    // Render in unified sorted order
    renderItems.forEach((entry) => {
      if (entry.type === 'stack') {
        const { stackId, group } = entry;
        const { name, slug, description, categories, items } = group;

        const groupEl = document.createElement('div');
        groupEl.className = 'stack-group';

        // Collapsible header
        const header = document.createElement('div');
        header.className = 'stack-group-header';

        // Check localStorage for collapsed state (default: collapsed)
        const collapseKey = `stack-collapse-${stackId}`;
        const isExpanded = localStorage.getItem(collapseKey) === 'expanded';
        if (isExpanded) header.classList.add('expanded');

        const totalIssues = items.reduce((sum, item) => sum + (item.library_count || 0), 0);
        const totalFailed = items.reduce((sum, item) => sum + (item.failed_count || 0), 0);

        const failedHtml =
          totalFailed > 0
            ? `<span class="stack-stat-failed">\u26a0\ufe0f ${totalFailed} failed</span>`
            : '';

        const descHtml = description
          ? `<span class="stack-group-desc"> — ${description}</span>`
          : '';

        const categoryBadges = (categories || [])
          .map((c) => `<span class="stack-category-badge">${c}</span>`)
          .join('');

        header.innerHTML = `
          <button class="stack-toggle-btn" aria-label="Toggle stack">
            <span class="stack-toggle-icon">${isExpanded ? '\u2212' : '+'}</span>
          </button>
          <div class="stack-group-info">
            <div class="stack-group-title-row">
              <span class="stack-group-name">${name}</span>${descHtml}
              ${categoryBadges ? `<span class="stack-category-badges">${categoryBadges}</span>` : ''}
            </div>
            <div class="stack-group-meta">
              <span class="meta-item">\ud83d\udcc1 ${items.length} periodical${items.length !== 1 ? 's' : ''}</span>
              <span class="meta-item">\ud83d\udcda ${totalIssues} issue${totalIssues !== 1 ? 's' : ''}</span>
              ${failedHtml}
            </div>
          </div>
          <div class="tracked-card-buttons">
            <button class="btn-icon stack-edit-btn" title="Edit stack">\u270f\ufe0f</button>
            <button class="btn-icon stack-assign-btn" title="Manage members">\ud83d\udccb</button>
            <button class="btn-icon stack-search-btn" title="Search for issues">\ud83d\udd0d</button>
            <button class="btn-icon btn-danger stack-delete-btn" title="Delete stack">\ud83d\uddd1\ufe0f</button>
          </div>
        `;

        // Header click toggles collapse (but not on action buttons)
        header.onclick = (e) => {
          if (e.target.closest('.tracked-card-buttons')) return;
          if (e.target.closest('.stack-toggle-btn')) {
            header.classList.toggle('expanded');
            const nowExpanded = header.classList.contains('expanded');
            header.querySelector('.stack-toggle-icon').textContent = nowExpanded ? '\u2212' : '+';
            localStorage.setItem(collapseKey, nowExpanded ? 'expanded' : 'collapsed');
            return;
          }
          header.classList.toggle('expanded');
          const nowExpanded = header.classList.contains('expanded');
          header.querySelector('.stack-toggle-icon').textContent = nowExpanded ? '\u2212' : '+';
          localStorage.setItem(collapseKey, nowExpanded ? 'expanded' : 'collapsed');
        };

        // Action button click handlers
        const stackData = {
          id: stackId,
          name,
          slug,
          description,
          categories,
          member_count: items.length,
        };

        header.querySelector('.stack-edit-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          stacks.openEditStackModal(stackData);
        });

        header.querySelector('.stack-assign-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          stacks.openAssignModal(stackData);
        });

        header.querySelector('.stack-search-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          this.searchStackItems(name, items);
        });

        header.querySelector('.stack-delete-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          stacks.openDeleteStackModal(stackData);
        });

        groupEl.appendChild(header);

        // Items container
        const itemsContainer = document.createElement('div');
        itemsContainer.className = 'stack-group-items';
        items.forEach((trackingItem) => {
          itemsContainer.appendChild(this.createTrackedCard(trackingItem));
        });
        groupEl.appendChild(itemsContainer);

        container.appendChild(groupEl);
      } else {
        container.appendChild(this.createTrackedCard(entry.trackingItem));
      }
    });

    console.log(
      `[Tracking] Rendered ${stackGroups.size} stack groups + ${ungrouped.length} ungrouped (${filtered.length} total)`
    );
  }

  /**
   * Populate the language filter dropdown with unique languages from tracked periodicals
   *
   * @returns {Promise<void>}
   */
  async populateLanguageDropdown() {
    const dropdown = document.getElementById('tracking-language-filter');
    if (!dropdown) return;

    // Get unique languages from tracked periodicals
    const languages = [...new Set(this.allTracked.map((t) => t.language || 'English'))].sort();

    // Keep the "All" option
    dropdown.innerHTML = '<option value="all">All</option>';

    // Add each language as an option
    languages.forEach((lang) => {
      const option = document.createElement('option');
      option.value = lang;
      option.textContent = lang;
      dropdown.appendChild(option);
    });

    // Restore saved filter value
    if (this.filterManager.languageFilter && this.filterManager.languageFilter !== 'all') {
      dropdown.value = this.filterManager.languageFilter;
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
        ? `<span class="failed-count" style="color: var(--text-secondary); cursor: pointer;" data-tracking-id="${id}" title="Click to view failed downloads">\u26A0\uFE0F ${failedCount} failed</span>`
        : '';

    const checkboxHtml = this.mergeMode
      ? `<input type="checkbox" class="merge-checkbox" data-tracking-id="${id}" ${this.selectedForMerge.has(id) ? 'checked' : ''}>`
      : '';

    card.innerHTML = `
      ${checkboxHtml}
      <div class="tracked-card-main">
        <div class="tracked-card-header">
          <h5>${escapeHtml(title)}</h5>
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
      // Try to fetch from new Issue Discovery system first
      const discoveryData = await APIHelper.executeWithErrorHandling(async () => {
        const discoveryResponse = await APIClient.authenticatedFetch(
          `/api/discovered-issues?tracking_id=${trackingId}&status=failed,permanently_failed&limit=500`
        );
        return await discoveryResponse.json();
      }, 'Tracking');

      let issues = (discoveryData.issues || []).map((issue) => ({
        id: issue.id,
        title: issue.title,
        download_attempts: issue.attempt_count, // DiscoveredIssue uses attempt_count
        max_retries: issue.max_retries, // Also get max_retries for accurate display
        last_error: issue.last_error,
        download_status: issue.download_status,
        isPermanentlyFailed: issue.download_status === 'permanently_failed',
      }));

      // If no issues found in new system, try legacy download submissions
      if (issues.length === 0) {
        const submissionData = await APIHelper.executeWithErrorHandling(async () => {
          const submissionResponse = await APIClient.authenticatedFetch(
            `/api/downloads/queue/all?status=failed`
          );
          return await submissionResponse.json();
        }, 'Tracking');

        // Filter by tracking ID and map to expected format
        const failedSubmissions = (submissionData.queue || []).filter(
          (item) => item.tracking_id === trackingId && item.status === 'failed'
        );

        issues = failedSubmissions.map((submission) => ({
          id: submission.submission_id,
          title: submission.title,
          download_attempts: submission.attempts || 0,
          max_retries: 1, // Legacy submissions use default max_retries
          last_error: submission.error || 'Unknown error',
          download_status: 'failed',
          isPermanentlyFailed: false,
          isLegacy: true, // Mark as legacy submission
        }));
      }

      if (issues.length === 0) {
        UIUtils.showToast('No failed downloads found', 'info');
        return;
      }

      // Import downloads module and open modal
      const { downloads } = await import('./downloads.js?v=1767733177');
      downloads.openManageFailedModal(periodicalTitle, issues);
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
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/periodicals/tracking/${trackingId}`
          );
          return await response.json();
        },
        'Tracking',
        ELEMENT_IDS.TRACKING_STATUS
      );

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
        document.getElementById('edit-tracking-search-aliases').value = t.search_aliases || '';

        // Set tracking mode
        let mode = 'none';
        if (t.track_all_editions) mode = 'all';
        else if (t.track_new_only) mode = 'new';
        document.getElementById('edit-tracking-mode').value = mode;

        // Set delete from client checkbox (inverted: checked = keep history, unchecked = auto-remove)
        document.getElementById('edit-delete-from-client').checked =
          !t.delete_from_client_on_completion;

        // Set organization pattern dropdown
        const patternSelect = document.getElementById('edit-tracking-pattern-select');
        const patternCustom = document.getElementById('edit-tracking-pattern-custom');
        const orgPattern = t.organization_pattern || '';

        // Map of pattern templates to their keys
        const patternMap = {
          '{category}/{title}/{year}/': 'default',
          '{category}/{title}/Vol{volume}/': 'volume',
          '{category}/{title}/': 'flat',
          '{category}/{title}/Vol{volume}/{year}/': 'volume_year',
          '{category}/{title}/Issues {issue_range}/': 'issue',
        };

        const matchedKey = patternMap[orgPattern];

        if (patternSelect) {
          if (!orgPattern) {
            // No pattern set - use global default
            patternSelect.value = '';
            if (patternCustom) patternCustom.classList.add('hidden');
          } else if (matchedKey) {
            // Known pattern - select it from dropdown
            patternSelect.value = matchedKey;
            if (patternCustom) patternCustom.classList.add('hidden');
          } else {
            // Custom pattern - show custom input
            patternSelect.value = 'custom';
            if (patternCustom) {
              patternCustom.value = orgPattern;
              patternCustom.classList.remove('hidden');
            }
          }
        }

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
   * Search all items in a stack sequentially, showing progress in the search modal
   */
  async searchStackItems(stackName, items) {
    const issuesContent = document.getElementById('search-issues-content');
    document.getElementById(ELEMENT_IDS.SEARCH_ISSUES_MODAL).classList.remove(CSS_CLASSES.HIDDEN);

    // Reset download state for this search session
    this.stackSearchResults = new Map();

    // Build progress UI
    issuesContent.innerHTML = `
      <div class="search-summary">
        <h3>Searching stack: "${stackName}"</h3>
        <p style="color: var(--text-secondary); margin-top: 4px;">Searching ${items.length} tracked item${items.length !== 1 ? 's' : ''}...</p>
      </div>
      <div id="stack-search-rows" style="max-height: 70vh; overflow-y: auto;"></div>
      <div id="stack-search-done" class="hidden" style="margin-top: 16px;"></div>`;

    const rowsContainer = document.getElementById('stack-search-rows');
    items.forEach((item, i) => {
      const row = document.createElement('div');
      row.className = 'stack-search-row';
      row.id = `stack-sr-${i}`;
      row.innerHTML = `
        <div class="stack-search-row-status" id="stack-sr-status-${i}">\u23f3</div>
        <div class="stack-search-row-title">${item.title}${item.language && item.language !== 'English' ? ` <span class="language-badge" style="font-size:9px;padding:1px 6px;margin:0">${item.language}</span>` : ''}</div>
        <div class="stack-search-row-actions" id="stack-sr-actions-${i}"></div>
        <div class="stack-search-row-result" id="stack-sr-result-${i}">Waiting...</div>`;
      rowsContainer.appendChild(row);
    });

    let totalAvailable = 0;
    let totalInLibrary = 0;
    let totalErrors = 0;

    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      const statusEl = document.getElementById(`stack-sr-status-${i}`);
      const resultEl = document.getElementById(`stack-sr-result-${i}`);
      const actionsEl = document.getElementById(`stack-sr-actions-${i}`);
      const rowEl = document.getElementById(`stack-sr-${i}`);

      statusEl.textContent = '\ud83d\udd04';
      resultEl.textContent = 'Searching...';
      rowEl.classList.add('searching');

      try {
        const params = new URLSearchParams();
        params.append('query', item.title);
        params.append('tracking_id', item.id);
        if (item.language) params.append('language', item.language);
        if (item.country) params.append('country', item.country);
        if (item.category) params.append('category', item.category);

        const response = await APIClient.authenticatedFetch(
          `/api/periodicals/search-providers?${params.toString()}`,
          { method: 'POST' }
        );
        const data = await response.json();
        rowEl.classList.remove('searching');

        if (data.found && data.results) {
          const inLib = data.results.filter(
            (r) => r.status === 'in_library' || r.already_downloaded
          ).length;
          const availableIssues = data.results.filter(
            (r) => r.status !== 'in_library' && !r.already_downloaded && !r.download_failed
          );
          const available = availableIssues.length;
          totalAvailable += available;
          totalInLibrary += inLib;

          if (available > 0) {
            // Store for bulk download
            this.stackSearchResults.set(i, {
              trackingId: item.id,
              availableIssues: availableIssues
                .map((r) => ({
                  title: r.title,
                  url: r.url || r.download_url || r.nzb_url || r.link,
                  provider: r.provider || 'newsnab',
                }))
                .filter((issue) => issue.url),
            });

            statusEl.textContent = '\ud83d\udce5';
            resultEl.innerHTML = `<strong>${available}</strong> available, ${inLib} in library`;
            actionsEl.innerHTML = `<button class="stack-search-dl-btn" onclick="downloadStackSearchMember(${i})" title="Download ${available} issues">\u2b07 ${available}</button>`;
            rowEl.classList.add('has-results');
          } else {
            statusEl.textContent = '\u2705';
            resultEl.textContent = `${inLib} in library, nothing new`;
            rowEl.classList.add('complete');
          }
        } else {
          statusEl.textContent = '\u2796';
          resultEl.textContent = 'No results';
          rowEl.classList.add('complete');
        }
      } catch (err) {
        console.error(`Stack search error for ${item.title}:`, err);
        statusEl.textContent = '\u274c';
        resultEl.textContent = 'Error';
        rowEl.classList.remove('searching');
        rowEl.classList.add('error');
        totalErrors++;
      }
    }

    // Show summary
    const doneEl = document.getElementById('stack-search-done');
    doneEl.classList.remove(CSS_CLASSES.HIDDEN);
    let summaryHtml =
      '<div class="stack-search-stats" style="display:flex;gap:16px;flex-wrap:wrap;font-size:14px;color:var(--text-secondary);">';
    if (totalAvailable > 0) {
      summaryHtml += `<span style="color:#22c55e;">\ud83d\udce5 <strong>${totalAvailable}</strong> new issue${totalAvailable !== 1 ? 's' : ''} available</span>`;
    } else {
      summaryHtml += '<span>\u2705 All up to date</span>';
    }
    summaryHtml += `<span>\ud83d\udcda <strong>${totalInLibrary}</strong> already in library</span>`;
    if (totalErrors > 0) {
      summaryHtml += `<span style="color:var(--error-color);">\u274c ${totalErrors} error${totalErrors !== 1 ? 's' : ''}</span>`;
    }
    summaryHtml += '</div>';
    if (totalAvailable > 0) {
      summaryHtml += `<div style="margin-top:10px;"><button class="stack-search-dl-all-btn" onclick="downloadAllStackSearchIssues()" id="stack-sr-dl-all">\u2b07 Download All ${totalAvailable} Issues</button></div>`;
    }
    doneEl.innerHTML = summaryHtml;
  }

  /**
   * Download available issues for a single member from stack search results
   *
   * @param {number} memberIdx - Index of the member in the search results
   * @returns {Promise<void>}
   */
  async downloadStackSearchMember(memberIdx) {
    const entry = this.stackSearchResults.get(memberIdx);
    if (!entry || entry.availableIssues.length === 0) return;

    const btn = document.querySelector(`#stack-sr-actions-${memberIdx} .stack-search-dl-btn`);
    if (btn) {
      btn.disabled = true;
      btn.textContent = '\u23f3';
    }

    try {
      const response = await APIClient.authenticatedFetch('/api/downloads/batch-issues', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tracking_id: entry.trackingId,
          issues: entry.availableIssues,
        }),
      });
      const data = await response.json();

      const parts = [];
      if (data.submitted > 0) parts.push(`${data.submitted} sent`);
      if (data.queued > 0) parts.push(`${data.queued} queued`);
      if (data.skipped > 0) parts.push(`${data.skipped} skipped`);
      if (data.failed > 0) parts.push(`${data.failed} failed`);

      if (btn) {
        const hasErrors = data.failed > 0;
        btn.textContent = hasErrors ? '\u26a0\ufe0f' : '\u2705';
        btn.title = parts.join(', ');
        btn.classList.add(hasErrors ? 'dl-warning' : 'dl-done');
      }

      this.stackSearchResults.delete(memberIdx);
    } catch (err) {
      console.error(`Download error for stack member ${memberIdx}:`, err);
      if (btn) {
        btn.textContent = '\u274c';
        btn.title = err.message;
        btn.disabled = false;
      }
    }
  }

  /**
   * Download all available issues across all members from stack search results
   *
   * @returns {Promise<void>}
   */
  async downloadAllStackSearchIssues() {
    const dlAllBtn = document.getElementById('stack-sr-dl-all');
    if (dlAllBtn) {
      dlAllBtn.disabled = true;
      dlAllBtn.textContent = '\u23f3 Downloading...';
    }

    let totalSubmitted = 0;
    let totalQueued = 0;
    let totalSkipped = 0;
    let totalFailed = 0;

    const entries = [...this.stackSearchResults.entries()];
    for (const [idx, entry] of entries) {
      const btn = document.querySelector(`#stack-sr-actions-${idx} .stack-search-dl-btn`);
      if (btn) {
        btn.disabled = true;
        btn.textContent = '\u23f3';
      }

      try {
        const response = await APIClient.authenticatedFetch('/api/downloads/batch-issues', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tracking_id: entry.trackingId,
            issues: entry.availableIssues,
          }),
        });
        const data = await response.json();

        totalSubmitted += data.submitted || 0;
        totalQueued += data.queued || 0;
        totalSkipped += data.skipped || 0;
        totalFailed += data.failed || 0;

        if (btn) {
          const hasErrors = data.failed > 0;
          btn.textContent = hasErrors ? '\u26a0\ufe0f' : '\u2705';
          btn.classList.add(hasErrors ? 'dl-warning' : 'dl-done');
        }

        this.stackSearchResults.delete(idx);
      } catch (err) {
        console.error(`Download error for stack member:`, err);
        totalFailed += entry.availableIssues.length;
        if (btn) {
          btn.textContent = '\u274c';
          btn.disabled = false;
        }
      }
    }

    if (dlAllBtn) {
      const parts = [];
      if (totalSubmitted > 0) parts.push(`${totalSubmitted} sent`);
      if (totalQueued > 0) parts.push(`${totalQueued} queued`);
      if (totalSkipped > 0) parts.push(`${totalSkipped} skipped`);
      if (totalFailed > 0) parts.push(`${totalFailed} failed`);

      const hasErrors = totalFailed > 0;
      dlAllBtn.textContent = hasErrors
        ? `\u26a0\ufe0f ${parts.join(', ')}`
        : `\u2705 ${parts.join(', ')}`;
      dlAllBtn.classList.add(hasErrors ? 'dl-warning' : 'dl-done');
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

      const response = await APIHelper.executeWithErrorHandling(async () => {
        return await APIClient.authenticatedFetch(
          `/api/periodicals/search-providers?${params.toString()}`,
          { method: 'POST' }
        );
      }, 'Tracking');
      const data = await response.json();

      if (data.found && data.results.length > 0) {
        // Parse and curate results first to get deduplicated issues
        const curatedIssues = this.parseAndCurateIssues(data.results);

        // Calculate accurate counts from deduplicated issues
        let libraryCount = 0;
        let availableCount = 0;
        let totalCount = 0;

        Object.values(curatedIssues).forEach((yearGroup) => {
          yearGroup.forEach((issue) => {
            totalCount++;
            if (issue.status === 'in_library') {
              libraryCount++;
            } else if (issue.status === 'available') {
              availableCount++;
            }
          });
        });

        // Store summary stats for display
        this.libraryCount = libraryCount;
        this.availableCount = availableCount;
        this.totalCount = totalCount;
        this.fromCache = data.from_cache || false;
        this.cacheAgeDays = data.cache_age_days || 0;

        // Store for re-rendering with filters
        this.lastCuratedIssues = curatedIssues;
        this.lastSearchTitle = title;
        this.sourceFilter = 'all';

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
   * Parse and organize issues by year.
   *
   * Uses backend-provided ``parsed_title`` when available (preferred) so that
   * title-parsing logic lives in one place (Python parsers).  Falls back to
   * the local ``parseIssueTitle()`` for results that lack the field.
   */
  parseAndCurateIssues(results) {
    const _issues = [];
    const issueMap = new Map();

    results.forEach((result) => {
      // Prefer backend-parsed metadata; fall back to local parsing
      let parsed = result.parsed_title
        ? {
            year: result.parsed_title.year ?? 0,
            month: result.parsed_title.month ?? 0,
            issue: result.parsed_title.issue ?? 0,
            volume: result.parsed_title.volume ?? 0,
            season: result.parsed_title.season ?? null,
            isCollection: result.parsed_title.is_collection ?? false,
            size: result.parsed_title.size ?? 0,
            files: result.parsed_title.files ?? 0,
          }
        : this.parseIssueTitle(result.title);

      if (!parsed) {
        console.warn('[Tracking] Could not parse title:', result.title);
      }
      if (parsed) {
        // Use volume from raw_metadata (backend parser) if title parsing missed it
        if (!parsed.volume && result.raw_metadata && result.raw_metadata.volume) {
          parsed.volume = result.raw_metadata.volume;
        }

        // If month/issue not found in title, try to extract from publication_date
        // (but NOT for collections — they group under year 0)
        if (parsed.month === 0 && !parsed.isCollection && result.publication_date) {
          try {
            const pubDate = new Date(result.publication_date);
            if (!isNaN(pubDate.getTime())) {
              parsed.month = pubDate.getMonth() + 1; // getMonth() returns 0-11
            }
          } catch (e) {
            // Ignore date parsing errors
          }
        }

        // Create unique key based on year, month, issue, season, and volume.
        // When month is known (> 0), exclude issue from the key — for monthly magazines the
        // cumulative issue number (e.g. "#8") is cosmetic and should not prevent deduplication
        // of library items and provider results that refer to the same calendar issue.
        const vol = parsed.volume || 0;
        const issueKey = (parsed.month > 0) ? 0 : (parsed.issue || 0);
        const key = `${parsed.year}-${parsed.month}-${issueKey}-${parsed.season || ''}-v${vol}`;

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
            download_failed: result.download_failed || false,
            status: result.status || 'available',
            status_badge: result.status_badge || '📥 Available',
            language: language,
            variants: [result], // Store all variants
          });
        } else {
          // Add download variant if it's a different language version
          const existing = issueMap.get(key);
          existing.variants.push(result);

          // Preserve library status - if any variant is in library, mark as in library
          if (result.status === 'in_library') {
            existing.status = 'in_library';
            existing.status_badge = '📚 In Library';
            existing.already_downloaded = true;
          }

          // If already downloaded, mark the combined entry as downloaded
          if (result.already_downloaded) {
            existing.already_downloaded = true;
          }

          // If any variant failed, mark as failed (unless already in library)
          if (result.download_failed && existing.status !== 'in_library') {
            existing.download_failed = true;
          }
        }
      }
    });

    // Sort by year desc, volume desc, month desc, issue desc
    const sortedIssues = Array.from(issueMap.values()).sort((a, b) => {
      if (b.year !== a.year) return b.year - a.year;
      if ((b.volume || 0) !== (a.volume || 0)) return (b.volume || 0) - (a.volume || 0);
      if (b.month !== a.month) return b.month - a.month;
      return b.issue - a.issue;
    });

    // Group by year (volume-only items go under year 0)
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
   * Format provider name as a styled badge
   * @param {string} provider - Provider type/name
   * @returns {string} HTML for provider badge
   */
  formatProviderBadge(provider) {
    if (!provider) return '';

    const providerLower = provider.toLowerCase();

    // Provider-specific styling
    const providerStyles = {
      internet_archive: {
        icon: '🏛️',
        label: 'Internet Archive',
        color: '#428bca',
        bgColor: '#e8f4fc',
      },
      newsnab: {
        icon: '📰',
        label: 'Newsnab',
        color: '#5cb85c',
        bgColor: '#e8f5e9',
      },
      rss: {
        icon: '📡',
        label: 'RSS',
        color: '#f0ad4e',
        bgColor: '#fff8e1',
      },
    };

    const style = providerStyles[providerLower] || {
      icon: '🔗',
      label: provider,
      color: '#6c757d',
      bgColor: '#f5f5f5',
    };

    return `<span style="
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      background: ${style.bgColor};
      color: ${style.color};
      font-weight: 500;
      font-size: 9px;
    ">${style.icon} ${style.label}</span>`;
  }

  /**
   * Parse issue title to extract year, month, issue number, season
   */
  parseIssueTitle(title) {
    let year = null;
    let issue = null;
    let month = null;
    let season = null;
    let volume = null;

    // First, try to extract season
    const seasonMatch = title.match(/\b(Spring|Summer|Fall|Autumn|Winter)\b/i);
    if (seasonMatch) {
      season = seasonMatch[1].charAt(0).toUpperCase() + seasonMatch[1].slice(1).toLowerCase();
    }

    // Extract year-month pattern (e.g., "2007-11" or "2007 11")
    // But NOT "2600" which is the magazine title
    const yearMonthMatch = title.match(/(?<!2)(\d{4})[\s.-](\d{1,2})(?:\D|$)/);
    if (yearMonthMatch) {
      const potentialYear = parseInt(yearMonthMatch[1]);
      if (potentialYear >= 1900 && potentialYear <= 2100) {
        year = potentialYear;
        const num = parseInt(yearMonthMatch[2]);
        if (num >= 1 && num <= 12) {
          month = num;
        }
      }
    }

    // If no year-month found, try other patterns
    if (!year) {
      const patterns = [
        /(?:No\.|Issue|#)\.?\s?(\d+)[\s.].*?(\d{4})/, // No.405 2026 or No.01.2015
        /(\d{4})[\s.](?:Issue|No\.)?[\s.]?(\d+)/, // 2026 No. 405 or 2026 405
        /Vol\.?\s?(\d+).*?(\d{4})/, // Vol. 123 2026
        /[.-](\d{4})(?:[.-]|$)/, // Year after dash or dot (e.g., -2014 or .2015)
        /(?:^|\s)(\d{4})(?:\s|$)/, // Just a year (with word boundaries)
      ];

      for (const pattern of patterns) {
        const match = title.match(pattern);
        if (match) {
          if (match.length === 2) {
            const num = parseInt(match[1]);
            // Skip 2600 (magazine title) when looking for years
            if (num >= 1900 && num <= 2100 && num !== 2600) {
              year = num;
              break;
            }
          } else if (match.length >= 3) {
            const num1 = parseInt(match[1]);
            const num2 = parseInt(match[2]);

            // Determine which is year and which is issue
            if (num2 >= 1900 && num2 <= 2100 && num2 !== 2600) {
              year = num2;
              issue = num1;
            } else if (num1 >= 1900 && num1 <= 2100 && num1 !== 2600) {
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

    // Try to extract volume number
    const volExtract = title.match(/\b(?:vol\.?|volume|v)[\s]*(\d+)\b/i);
    if (volExtract) {
      volume = parseInt(volExtract[1]);
    }

    if (year) {
      return {
        year,
        issue: issue || 0,
        month: month || 0,
        season: season || null,
        volume: volume || 0,
      };
    }

    // Fallback: Handle volume-only titles (e.g., "Magazine v12", "Title Vol.5")
    if (!year) {
      const volMatch = title.match(/\b(?:vol\.?|volume|v)[\s]*(\d+)\b/i);
      if (volMatch) {
        volume = parseInt(volMatch[1]);
        // Also try to extract issue number
        const issueMatch = title.match(/(?:issue|no\.?|#)\s*(\d+)/i);
        if (issueMatch) {
          issue = parseInt(issueMatch[1]);
        }
        return { year: 0, issue: issue || 0, month: 0, season: null, volume };
      }

      // Try to extract number from set/collection/pack
      const setMatch = title.match(/(?:Set|Collection|Pack|Part)[\s._-]*(\d+)/i);
      if (setMatch) {
        const setNumber = parseInt(setMatch[1]);
        return { year: 0, issue: setNumber, month: 0, season: null, isCollection: true, volume: 0 };
      }

      // Handle collections without numbers (e.g., "Full Collection", "Complete Collection")
      const collectionMatch = title.match(/\b(Full|Complete|Entire)\s+(Collection|Archive|Run)\b/i);
      if (collectionMatch) {
        return { year: 0, issue: 0, month: 0, season: null, isCollection: true, volume: 0 };
      }
    }

    return null;
  }

  /**
   * Toggle tracking for a single issue
   */
  async toggleIssueTracking(trackingId, editionId, track) {
    try {
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/periodicals/tracking/${trackingId}/editions/${editionId}/track?track=${track}`,
            { method: 'POST' }
          );
          return await response.json();
        },
        'Tracking',
        ELEMENT_IDS.TRACKING_STATUS
      );

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

    // Add search summary header
    let cacheInfo = '';
    if (this.fromCache) {
      cacheInfo = ` <span style="font-size: 0.85em; color: var(--text-secondary);">(cached ${this.cacheAgeDays}d ago)</span>`;
    }

    // Store available issues for bulk download
    this.availableIssues = [];

    // Collect unique providers from available items for filter buttons
    const allProviders = new Set();
    Object.values(groupedByYear).forEach((yearGroup) => {
      yearGroup.forEach((issue) => {
        if (issue.status !== 'in_library' && issue.variants) {
          issue.variants.forEach((v) => {
            if (v.provider && v.provider !== 'Library') {
              allProviders.add(v.provider.toLowerCase());
            }
          });
        }
      });
    });

    // Provider display config
    const providerLabels = {
      newsnab: { icon: '📰', label: 'Newsnab' },
      internet_archive: { icon: '🏛️', label: 'Internet Archive' },
      rss: { icon: '📡', label: 'RSS' },
    };

    // Build source filter buttons (only show if more than one provider)
    let sourceFilterHtml = '';
    if (allProviders.size > 1) {
      const filterBtns = [
        `<button onclick="filterSearchBySource('all')" class="sort-btn${this.sourceFilter === 'all' ? ' active' : ''}">All</button>`,
      ];
      allProviders.forEach((provider) => {
        const cfg = providerLabels[provider] || { icon: '🔗', label: provider };
        filterBtns.push(
          `<button onclick="filterSearchBySource('${provider}')" class="sort-btn${this.sourceFilter === provider ? ' active' : ''}">${cfg.icon} ${cfg.label}</button>`
        );
      });
      sourceFilterHtml = `
        <div style="display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; align-items: center;">
          <span style="font-size: 0.85em; color: var(--text-secondary); margin-right: 4px;">Source:</span>
          ${filterBtns.join('')}
        </div>`;
    }

    // Calculate filtered counts
    let filteredLibraryCount = 0;
    let filteredAvailableCount = 0;
    let filteredTotalCount = 0;

    Object.values(groupedByYear).forEach((yearGroup) => {
      yearGroup.forEach((issue) => {
        // Check if issue passes the source filter
        const passesFilter =
          this.sourceFilter === 'all' || this.issueMatchesSourceFilter(issue, this.sourceFilter);
        if (!passesFilter) return;

        filteredTotalCount++;
        if (issue.status === 'in_library') {
          filteredLibraryCount++;
        } else if (issue.status === 'available') {
          filteredAvailableCount++;
        }
      });
    });

    let html = `
      <div class="search-summary">
        <h3>Search Results for "${title}"${cacheInfo}</h3>
        <div class="summary-stats">
          <span class="stat">📚 <strong>${filteredLibraryCount}</strong> in library</span>
          <span class="stat${filteredAvailableCount > 0 ? ' clickable-stat' : ''}" ${filteredAvailableCount > 0 ? 'onclick="downloadAllAvailable()" title="Click to download all available issues"' : ''}>📥 <strong>${filteredAvailableCount}</strong> available</span>
          <span class="stat">🎯 <strong>${filteredTotalCount}</strong> total</span>
        </div>
        ${sourceFilterHtml}
      </div>
      <div style="max-height: 70vh; overflow-y: auto;">`;

    const years = Object.keys(groupedByYear).sort((a, b) => b - a);

    years.forEach((year) => {
      const allIssues = groupedByYear[year];

      // Filter issues by source
      const issues =
        this.sourceFilter === 'all'
          ? allIssues
          : allIssues.filter((issue) => this.issueMatchesSourceFilter(issue, this.sourceFilter));

      if (issues.length === 0) return; // Skip empty year groups after filtering

      // Display label for year groups
      let yearLabel;
      if (year === '0') {
        const hasVolumes = issues.some((i) => i.volume > 0 && !i.isCollection);
        const hasCollections = issues.some((i) => i.isCollection);
        if (hasVolumes && hasCollections) yearLabel = '📦 Volumes & Collections';
        else if (hasVolumes) yearLabel = '📦 Volumes';
        else yearLabel = '📦 Collections';
      } else {
        yearLabel = `📅 ${year}`;
      }
      html += `<div style="margin-bottom: 20px;">
        <h4 style="color: var(--primary-color); margin-bottom: 10px;">${yearLabel}</h4>
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px;">`;

      issues.forEach((issue) => {
        // Create display label based on available information
        let displayLabel;

        // Priority 0: Collection/Set (if isCollection flag is set)
        if (issue.isCollection && issue.issue > 0) {
          displayLabel = `Set #${issue.issue}`;
        } else if (issue.isCollection) {
          displayLabel = 'Collection';
        }
        // Priority 1: Season (if present)
        else if (issue.season) {
          displayLabel = issue.season;
        }
        // Priority 2: Volume with issue (e.g., "Vol 5 #12")
        else if (issue.volume > 0 && issue.issue > 0) {
          displayLabel = `Vol ${issue.volume} #${issue.issue}`;
        }
        // Priority 3: Volume with month (e.g., "Vol 5 Jan")
        else if (issue.volume > 0 && issue.month > 0) {
          displayLabel = `Vol ${issue.volume} ${NUMBER_TO_MONTH[issue.month]}`;
        }
        // Priority 4: Volume only (e.g., "Vol 12")
        else if (issue.volume > 0) {
          displayLabel = `Vol ${issue.volume}`;
        }
        // Priority 5: Month and Issue
        else if (issue.month > 0 && issue.issue > 0) {
          displayLabel = `${NUMBER_TO_MONTH[issue.month]} #${issue.issue}`;
        }
        // Priority 6: Month only
        else if (issue.month > 0) {
          displayLabel = NUMBER_TO_MONTH[issue.month];
        }
        // Priority 7: Issue number only
        else if (issue.issue > 0) {
          displayLabel = `#${issue.issue}`;
        }
        // Fallback: Just show year
        else {
          displayLabel = `${issue.year}`;
        }

        // Determine status from API response
        const status = issue.status || 'available'; // 'in_library', 'available', 'failed'
        const isLibraryItem = status === 'in_library';
        const hasFailed = status === 'failed';

        // Calculate age of newest NZB for availability indication
        // Skip age badge for Internet Archive items (they're permanently archived, age doesn't affect availability)
        let newestAge = '';
        let ageColorClass = '';
        if (!isLibraryItem && issue.variants && issue.variants.length > 0) {
          // Check if all variants are from Internet Archive - skip age badge if so
          const allFromInternetArchive = issue.variants.every(
            (v) => v.provider && v.provider.toLowerCase() === 'internet_archive'
          );

          if (!allFromInternetArchive) {
            // Find the newest publication_date among non-IA variants
            const variantsWithDates = issue.variants.filter(
              (v) => v.publication_date && v.provider?.toLowerCase() !== 'internet_archive'
            );
            if (variantsWithDates.length > 0) {
              const newestVariant = variantsWithDates.reduce((newest, v) => {
                const vDate = new Date(v.publication_date);
                const nDate = new Date(newest.publication_date);
                return vDate > nDate ? v : newest;
              });
              newestAge = formatRelativeAge(newestVariant.publication_date);

              // Color code by age: green < 7 days, yellow 7-30 days, orange 30-90 days, red > 90 days
              const ageDate = new Date(newestVariant.publication_date);
              const ageDays = Math.floor((new Date() - ageDate) / (1000 * 60 * 60 * 24));
              if (ageDays <= 7) {
                ageColorClass = 'age-fresh'; // Green - excellent retention
              } else if (ageDays <= 30) {
                ageColorClass = 'age-good'; // Yellow-green - good retention
              } else if (ageDays <= 90) {
                ageColorClass = 'age-moderate'; // Orange - moderate retention
              } else {
                ageColorClass = 'age-old'; // Red - may have retention issues
              }
            }
          }
        }

        // Status-based styling with color-coded left borders
        let backgroundColor, borderColor, opacity, textColor, statusIcon, statusText;

        if (isLibraryItem) {
          backgroundColor = '#d4edda';
          borderColor = '#28a745';
          opacity = '0.95';
          textColor = '#155724';
          statusIcon = '📚';
          statusText = 'In Library';
        } else if (hasFailed) {
          backgroundColor = '#fff3cd';
          borderColor = '#ffc107';
          opacity = '0.9';
          textColor = '#856404';
          statusIcon = '⚠️';
          statusText = 'Failed';
        } else {
          backgroundColor = '#d1ecf1';
          borderColor = '#17a2b8';
          opacity = '1';
          textColor = '#0c5460';
          statusIcon = '📥';
          statusText = 'Available';
        }

        let providerDisplay = '';
        if (isLibraryItem) {
          // Show provider badges for non-library sources only
          const providers = [
            ...new Set(
              (issue.variants || [])
                .map((v) => v.provider)
                .filter(Boolean)
                .map((p) => p.toLowerCase())
                .filter((p) => p !== 'library')
            ),
          ];
          if (providers.length > 0) {
            providerDisplay = `<div style="font-size: 10px; margin-top: 6px;">${providers.map((p) => this.formatProviderBadge(p)).join(' ')}</div>`;
          }
        } else {
          providerDisplay = `<div style="font-size: 10px; margin-top: 6px;">${this.formatProviderBadge(issue.provider)}</div>`;
        }

        // Filter variants by source when a filter is active
        const filteredVariants =
          this.sourceFilter !== 'all' && issue.variants
            ? issue.variants.filter(
                (v) => v.provider && v.provider.toLowerCase() === this.sourceFilter
              )
            : issue.variants || [];
        const displayVariants =
          filteredVariants.length > 0 ? filteredVariants : issue.variants || [];

        // Show language variants badge if multiple variants exist
        // For library items, only count downloadable (provider) variants
        const providerVariantCount = isLibraryItem
          ? displayVariants.filter(
              (v) => v.status !== 'in_library' && v.from_provider !== false && v.url
            ).length
          : displayVariants.length;
        const hasMultipleVariants = isLibraryItem
          ? providerVariantCount > 0
          : displayVariants.length > 1;
        const variantsBadge = hasMultipleVariants
          ? `<div style="font-size: 10px; margin-top: 6px; color: var(--primary-color); font-weight: 600;">📥 ${providerVariantCount} variant${providerVariantCount !== 1 ? 's' : ''}</div>`
          : isLibraryItem
            ? ''
            : issue.language
              ? `<div style="font-size: 10px; margin-top: 6px; color: var(--text-secondary);">${issue.language}</div>`
              : '';

        // Age badge for available/failed issues (not library items)
        const ageBadge =
          newestAge && !isLibraryItem
            ? `<div class="issue-age-badge ${ageColorClass}" title="NZB posted ${newestAge} ago - newer is better for Usenet retention">⏱️ ${newestAge}</div>`
            : '';

        // Size badge — show file size (and file count for collections)
        let sizeBadge = '';
        const sizeStr = formatFileSize(issue.size);
        if (sizeStr) {
          const filesStr = issue.files > 1 ? ` · ${issue.files} files` : '';
          sizeBadge = `<div style="font-size: 10px; margin-top: 4px; color: var(--text-secondary);" title="Download size">💾 ${sizeStr}${filesStr}</div>`;
        }

        let cardHtml = `<div style="
          padding: 12px;
          background: ${backgroundColor};
          border-radius: 8px;
          text-align: center;
          cursor: pointer;
          transition: all 0.2s;
          border-left: 4px solid ${borderColor};
          opacity: ${opacity};
          color: ${textColor};
          box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        "`;

        // Store variants globally for click handlers
        const issueKey = `${issue.year}-${issue.month}-${issue.issue}`;
        window.issueVariants = window.issueVariants || {};
        window.issueVariants[issueKey] = displayVariants;

        if (isLibraryItem) {
          // Library items: show detail modal with original title and replacement options
          cardHtml += ` onclick='showLibraryItemDetail("${issueKey}")'`;
        } else if (displayVariants.length > 0) {
          cardHtml += ` onclick='selectIssueWithVariants("${issueKey}", ${issue.already_downloaded || false}, ${issue.download_failed || false})'`;

          // Store available issues for bulk download
          if (status === 'available' && displayVariants.length > 0) {
            let candidates = displayVariants.filter((v) => !v.download_failed);
            if (candidates.length === 0) candidates = displayVariants;

            this.availableIssues.push({
              title: candidates[0].title,
              url: candidates[0].url,
              provider: candidates[0].provider,
            });
          }
        }

        cardHtml += `>
          <div class="status-badge-inline" style="
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 10px;
            font-weight: 600;
            margin-bottom: 6px;
            background: rgba(255,255,255,0.7);
          ">${statusIcon} ${statusText}</div>
          <div style="font-weight: 600; font-size: 14px;">${displayLabel}</div>
          ${sizeBadge}
          ${ageBadge}
          ${providerDisplay}
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
   * Check if an issue matches the given source filter.
   * Library items always pass (they show regardless of source filter).
   * Available/failed items pass if any variant matches the provider.
   *
   * @param {Object} issue - Curated issue object
   * @param {string} source - Provider key (e.g., 'newsnab', 'internet_archive')
   * @returns {boolean} Whether the issue should be shown
   */
  issueMatchesSourceFilter(issue, source) {
    if (!issue.variants || issue.variants.length === 0) return false;
    return issue.variants.some((v) => v.provider && v.provider.toLowerCase() === source);
  }

  /**
   * Apply source filter and re-render search results
   *
   * @param {string} source - Provider key or 'all'
   */
  filterSearchBySource(source) {
    this.sourceFilter = source;
    if (this.lastCuratedIssues && this.lastSearchTitle) {
      this.displayCuratedIssues(this.lastCuratedIssues, this.lastSearchTitle);
    }
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
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.delete(`/api/periodicals/tracking/${trackingId}`);
          return await response.json();
        },
        'Tracking',
        ELEMENT_IDS.TRACKING_STATUS
      );

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
      // Already logged by APIHelper
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

    const stackSelect = document.getElementById('new-tracking-stack');
    if (stackSelect) stackSelect.value = '';
  }

  /**
   * Open track new periodical modal
   */
  async openTrackNewPeriodicalModal() {
    this.resetTracking();
    document.getElementById('track-new-periodical-modal').classList.remove(CSS_CLASSES.HIDDEN);
    this.loadStacksDropdown();
  }

  /**
   * Load available stacks into the new tracking modal dropdown
   */
  async loadStacksDropdown() {
    const select = document.getElementById('new-tracking-stack');
    if (!select) return;
    select.innerHTML = '<option value="">No stack</option>';
    try {
      const response = await APIClient.authenticatedFetch('/api/stacks');
      const data = await response.json();
      const stacks = data.stacks || [];
      if (stacks.length) {
        stacks.forEach((stack) => {
          const option = document.createElement('option');
          option.value = stack.slug;
          option.textContent = stack.name;
          select.appendChild(option);
        });
      }
    } catch (err) {
      console.error('Failed to load stacks for dropdown:', err);
    }
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
  const keepHistory = document.getElementById('edit-delete-from-client').checked;
  const searchAliases = document.getElementById('edit-tracking-search-aliases').value.trim();

  // Get organization pattern from dropdown or custom input
  const patternSelect = document.getElementById('edit-tracking-pattern-select');
  const patternCustom = document.getElementById('edit-tracking-pattern-custom');
  let organizationPattern = null;

  if (patternSelect && patternSelect.value) {
    if (patternSelect.value === 'custom' && patternCustom) {
      organizationPattern = patternCustom.value.trim() || null;
    } else if (patternSelect.value !== '') {
      // Map pattern keys to their templates
      const patternTemplates = {
        default: '{category}/{title}/{year}/',
        volume: '{category}/{title}/Vol{volume}/',
        flat: '{category}/{title}/',
        volume_year: '{category}/{title}/Vol{volume}/{year}/',
        issue: '{category}/{title}/Issues {issue_range}/',
      };
      organizationPattern = patternTemplates[patternSelect.value] || null;
    }
  }

  try {
    const result = await APIHelper.executeWithErrorHandling(
      async () => {
        const response = await APIClient.put(`/api/periodicals/tracking/${trackingId}`, {
          title,
          category,
          language,
          country,
          download_category: downloadCategory || null,
          track_all_editions: mode === 'all',
          track_new_only: mode === 'new',
          delete_from_client_on_completion: !keepHistory, // Inverted: checked = keep, unchecked = auto-remove
          organization_pattern: organizationPattern, // Send null if empty to use global default
          search_aliases: searchAliases || null, // Comma-separated alternative search names
        });
        return await response.json();
      },
      'Tracking',
      ELEMENT_IDS.TRACKING_STATUS
    );

    if (result.success) {
      window.closeEditTrackingModal();
      tracking.loadTrackedPeriodicals();

      // If pattern changed, prompt user to reorganize
      if (result.pattern_changed && result.files_affected > 0) {
        const confirmed = await UIUtils.confirm(
          'Reorganize Files?',
          `Organization pattern changed. Would you like to reorganize ${result.files_affected} existing file(s) to match the new pattern?\n\nNew files will use the new pattern automatically.`
        );

        if (confirmed) {
          // Trigger reorganization for this tracking ID
          await reorganizeTrackingFiles(trackingId, title);
        } else {
          UIUtils.showStatus(
            ELEMENT_IDS.TRACKING_STATUS,
            'Tracking updated. New downloads will use the new pattern.',
            'success'
          );
          setTimeout(
            () => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS),
            TIMEOUTS.AUTO_HIDE_STATUS
          );
        }
      } else {
        UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Tracking updated successfully', 'success');
        setTimeout(
          () => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS),
          TIMEOUTS.AUTO_HIDE_STATUS
        );
      }
    } else {
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Failed to update tracking', 'error');
    }
  } catch (err) {
    console.error('Error updating tracking:', err);
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Failed to update tracking', 'error');
  }
};

/**
 * Format a date as relative age (e.g., "2 days", "3 weeks", "1 month")
 * @param {string|Date} date - The date to format
 * @returns {string} Relative age string or empty if invalid
 */
function formatRelativeAge(date) {
  if (!date) return '';
  try {
    const uploadDate = new Date(date);
    if (isNaN(uploadDate.getTime())) return '';

    const now = new Date();
    const diffMs = now - uploadDate;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays < 0) return 'future';
    if (diffDays === 0) return 'today';
    if (diffDays === 1) return '1 day';
    if (diffDays < 7) return `${diffDays} days`;
    if (diffDays < 14) return '1 week';
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks`;
    if (diffDays < 60) return '1 month';
    if (diffDays < 365) return `${Math.floor(diffDays / 30)} months`;
    if (diffDays < 730) return '1 year';
    return `${Math.floor(diffDays / 365)} years`;
  } catch {
    return '';
  }
}

/**
 * Format a file size in bytes to a human-readable string (KB, MB, GB).
 *
 * @param {number} bytes - Size in bytes
 * @returns {string} Formatted size or empty string if 0/falsy
 */
function formatFileSize(bytes) {
  if (!bytes || bytes <= 0) return '';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let size = bytes;
  while (size >= 1024 && i < units.length - 1) {
    size /= 1024;
    i++;
  }
  return `${size < 10 ? size.toFixed(1) : Math.round(size)} ${units[i]}`;
}

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

  // Sort variants by publication_date (newest first) for better Usenet availability
  const sortedVariants = [...variants].sort((a, b) => {
    const dateA = a.publication_date ? new Date(a.publication_date) : new Date(0);
    const dateB = b.publication_date ? new Date(b.publication_date) : new Date(0);
    return dateB - dateA; // Newest first
  });

  // Multiple variants - show selection modal
  const hasLibraryItem = alreadyDownloaded || sortedVariants.some((v) => v.already_downloaded);
  const modalDescription = hasLibraryItem
    ? 'Your downloaded variant is marked below. You can re-download from a different NZB source if needed:'
    : 'Multiple NZB variants available for this issue (sorted by age, newest first):';

  const modalHTML = `
    <div id="language-variant-modal" class="modal" style="display: flex;">
      <div class="modal-content" style="max-width: 500px;">
        <span class="close" onclick="closeLangVariantModal()">&times;</span>
        <h2>Select NZB Source</h2>
        <p style="color: var(--text-secondary); margin-bottom: 20px;">${modalDescription}</p>
        <div id="variant-options" style="display: flex; flex-direction: column; gap: 10px;"></div>
      </div>
    </div>
  `;

  document.body.insertAdjacentHTML('beforeend', modalHTML);

  const optionsDiv = document.getElementById('variant-options');
  sortedVariants.forEach((variant, index) => {
    const isDownloaded = variant.already_downloaded || alreadyDownloaded;
    const downloadFailed = variant.download_failed || hasFailed || false;

    // Build status badges
    let statusBadges = '';
    if (isDownloaded) {
      statusBadges += ' <span class="variant-in-library">✓ In Library</span>';
    } else if (downloadFailed) {
      statusBadges += ' <span class="variant-failed">✗ Failed</span>';
    }

    // Add age badge if we have publication_date
    const age = formatRelativeAge(variant.publication_date);
    const ageBadge = age ? `<span class="variant-age">${age} old</span>` : '';

    // Size badge from raw_metadata or parsed_title
    const variantSize =
      (variant.raw_metadata && variant.raw_metadata.size) ||
      (variant.parsed_title && variant.parsed_title.size) ||
      0;
    const variantSizeStr = formatFileSize(variantSize);
    const sizeBadge = variantSizeStr
      ? `<span class="variant-age" style="background: var(--surface-variant);">💾 ${variantSizeStr}</span>`
      : '';

    // Provider info
    const providerInfo = variant.provider
      ? `<span class="variant-provider">${variant.provider}</span>`
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
      <div class="variant-label">
        <span class="variant-number">#${index + 1}</span>
        ${ageBadge}
        ${sizeBadge}
        ${providerInfo}
        ${statusBadges}
      </div>
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

/**
 * Show detail modal for a library item with original import info and replacement options
 *
 * @param {string} issueKey - The issue key (year-month-issue)
 */
window.showLibraryItemDetail = function (issueKey) {
  const variants = window.issueVariants[issueKey];
  if (!variants || variants.length === 0) return;

  // Separate library copies from downloadable provider variants
  const libraryCopies = variants.filter(
    (v) => v.status === 'in_library' || v.from_provider === false
  );
  const downloadableVariants = variants.filter(
    (v) => v.status !== 'in_library' && v.from_provider !== false && v.url
  );

  // Build detail section for each library copy
  let detailHtml = '';
  libraryCopies.forEach((copy, index) => {
    const metadata = copy.metadata || {};
    const importedFrom = metadata.imported_from || 'Unknown';
    const importDate = metadata.import_date
      ? new Date(metadata.import_date).toLocaleDateString()
      : '';
    const filePath = copy.file_path || '';
    const fileName = filePath ? filePath.split('/').pop() : '';

    // Add separator between copies
    if (index > 0) {
      detailHtml += `<div style="border-top: 1px solid var(--border-color); margin: 12px 0;"></div>`;
    }

    // Copy header if multiple
    if (libraryCopies.length > 1) {
      detailHtml += `
      <div style="font-size: 0.8em; color: var(--primary-color); font-weight: 600; margin-bottom: 8px;">Copy ${index + 1}</div>`;
    }

    detailHtml += `
    <div style="margin-bottom: 16px;">
      <div style="font-size: 0.85em; color: var(--text-secondary); margin-bottom: 4px;">Original Filename</div>
      <div style="padding: 10px 12px; background: var(--surface-variant); border-radius: 6px; font-family: monospace; font-size: 0.9em; word-break: break-all;">${importedFrom}</div>
    </div>`;

    if (filePath) {
      detailHtml += `
      <div style="margin-bottom: 16px;">
        <div style="font-size: 0.85em; color: var(--text-secondary); margin-bottom: 4px;">Current Path</div>
        <div style="padding: 10px 12px; background: var(--surface-variant); border-radius: 6px; font-family: monospace; font-size: 0.85em; word-break: break-all;">${filePath}</div>
      </div>`;
    }

    if (importDate) {
      detailHtml += `
      <div style="margin-bottom: 8px;">
        <div style="font-size: 0.85em; color: var(--text-secondary); margin-bottom: 4px;">Imported</div>
        <div style="font-size: 0.9em;">${importDate}</div>
      </div>`;
    }

    // Delete button for each copy
    const copyId = copy.library_item_id;
    if (copyId) {
      detailHtml += `
      <div style="margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
        <button class="save-btn btn-cancel" style="font-size: 0.8em; padding: 4px 12px;"
          onclick="moveLibraryCopy(${copyId}, '${issueKey}')">📦 Move to Tracking</button>
        <button class="save-btn btn-delete" style="font-size: 0.8em; padding: 4px 12px;"
          onclick="deleteLibraryCopy(${copyId}, '${issueKey}')">🗑️ Remove from Library</button>
      </div>`;
    }
  });

  // Build replacement options if available
  let replacementHtml = '';
  if (downloadableVariants.length > 0) {
    const sorted = [...downloadableVariants].sort((a, b) => {
      const dateA = a.publication_date ? new Date(a.publication_date) : new Date(0);
      const dateB = b.publication_date ? new Date(b.publication_date) : new Date(0);
      return dateB - dateA;
    });

    replacementHtml = `
    <div style="border-top: 1px solid var(--border-color); padding-top: 16px; margin-top: 8px;">
      <div style="font-size: 0.85em; color: var(--text-secondary); margin-bottom: 10px;">
        Replace with a different version (${sorted.length} available):
      </div>
      <div id="library-replacement-options" style="display: flex; flex-direction: column; gap: 8px;"></div>
    </div>`;
  } else {
    replacementHtml = `
    <div style="border-top: 1px solid var(--border-color); padding-top: 12px; margin-top: 8px;">
      <div style="font-size: 0.85em; color: var(--text-secondary); font-style: italic;">No replacement downloads available from providers.</div>
    </div>`;
  }

  const modalHTML = `
    <div id="library-detail-modal" class="modal" style="display: flex;">
      <div class="modal-content" style="max-width: 550px;">
        <span class="close" onclick="closeLibraryDetailModal()">&times;</span>
        <h2 style="margin-bottom: 16px;">📚 Library Item</h2>
        ${detailHtml}
        ${replacementHtml}
      </div>
    </div>
  `;

  document.body.insertAdjacentHTML('beforeend', modalHTML);

  // Click outside to close (with text-selection protection)
  const modal = document.getElementById('library-detail-modal');
  let mouseDownOnBackdrop = false;
  modal.addEventListener('mousedown', (e) => {
    mouseDownOnBackdrop = e.target === modal;
  });
  modal.addEventListener('click', (e) => {
    if (e.target === modal && mouseDownOnBackdrop) {
      window.closeLibraryDetailModal();
    }
    mouseDownOnBackdrop = false;
  });

  // Add replacement option buttons
  if (downloadableVariants.length > 0) {
    const optionsDiv = document.getElementById('library-replacement-options');
    const sorted = [...downloadableVariants].sort((a, b) => {
      const dateA = a.publication_date ? new Date(a.publication_date) : new Date(0);
      const dateB = b.publication_date ? new Date(b.publication_date) : new Date(0);
      return dateB - dateA;
    });

    sorted.forEach((variant, index) => {
      const age = formatRelativeAge(variant.publication_date);
      const ageBadge = age ? `<span class="variant-age">${age} old</span>` : '';
      const providerInfo = variant.provider
        ? `<span class="variant-provider">${variant.provider}</span>`
        : '';

      const btn = document.createElement('button');
      btn.className = 'btn-variant btn-variant-new';
      btn.innerHTML = `
        <div class="variant-label">
          <span class="variant-number">#${index + 1}</span>
          ${ageBadge}
          ${providerInfo}
        </div>
        <div class="variant-title">${variant.title}</div>
      `;
      btn.onclick = () => {
        window.closeLibraryDetailModal();
        window.selectIssue(variant.title, variant.provider, variant.url, true, false);
      };
      optionsDiv.appendChild(btn);
    });
  }
};

window.closeLibraryDetailModal = function () {
  const modal = document.getElementById('library-detail-modal');
  if (modal) modal.remove();
};

/**
 * Delete a library copy from the database with confirmation
 *
 * @param {number} periodicalId - The periodical database ID
 * @param {string} issueKey - The issue key to refresh the modal after deletion
 */
window.deleteLibraryCopy = async function (periodicalId, issueKey) {
  const confirmed = await UIUtils.confirm(
    'Remove from Library',
    '<p>Remove this copy from your library?</p>' +
      '<p style="color: var(--text-secondary); font-size: 0.9em;">The file will be kept on disk but the database record will be removed.</p>'
  );

  if (!confirmed) return;

  try {
    const response = await APIClient.authenticatedFetch(
      `/api/periodicals/${periodicalId}?delete_files=false&remove_tracking=false&delete_all_issues=false`,
      { method: 'DELETE' }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail ?? 'Failed to remove');
    }

    const result = await response.json();
    UIUtils.showStatus(
      ELEMENT_IDS.TRACKING_STATUS,
      result.message || 'Removed from library',
      'success'
    );
    setTimeout(() => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS), 5000);

    // Close modal and refresh search results
    window.closeLibraryDetailModal();
    if (window.trackingManager) {
      window.trackingManager.searchPeriodicalMetadata();
    }
  } catch (error) {
    console.error('[Library] Failed to delete copy:', error);
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `Error: ${error.message}`, 'error');
  }
};

/**
 * Move a library copy to a different tracking record
 *
 * @param {number} periodicalId - The periodical database ID
 * @param {string} issueKey - The issue key to refresh after move
 */
window.moveLibraryCopy = async function (periodicalId, issueKey) {
  // Close the library detail modal first to avoid z-index issues
  window.closeLibraryDetailModal();

  try {
    // Fetch all tracking records
    const response = await APIClient.get(`/api/periodicals/tracking?limit=${API_LIMITS.TRACKING_LIST}`);
    const data = await response.json();
    const trackingRecords = data.tracked_magazines || [];

    if (trackingRecords.length === 0) {
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'No tracking records found', 'error');
      return;
    }

    // Build options HTML
    const optionsHtml = trackingRecords
      .sort((a, b) => a.title.localeCompare(b.title))
      .map(
        (t) =>
          `<option value="${t.id}">${t.title} (${t.category || 'Auto-detect'} - ${t.language || 'English'})</option>`
      )
      .join('');

    const modalHTML = `
      <div id="move-library-copy-modal" class="modal" style="display: flex;">
        <div class="modal-content" style="max-width: 500px;">
          <span class="close" onclick="closeMoveLibraryCopyModal()">&times;</span>
          <h2 style="margin-bottom: 16px;">📦 Move to Tracking</h2>
          <p style="color: var(--text-secondary); margin-bottom: 12px; font-size: 0.9em;">
            Select the tracking record to move this issue to. The file will be renamed and reorganized automatically.
          </p>
          <select id="move-copy-target-tracking" class="w-full" style="margin-bottom: 16px;">
            <option value="">Select a tracking record...</option>
            ${optionsHtml}
          </select>
          <div style="display: flex; gap: 10px; justify-content: flex-end;">
            <button class="save-btn btn-cancel" onclick="closeMoveLibraryCopyModal()">Cancel</button>
            <button id="confirm-move-copy-btn" class="save-btn btn-primary" disabled
              onclick="confirmMoveLibraryCopy(${periodicalId}, '${issueKey}')">Move</button>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);

    // Enable/disable button based on selection
    document.getElementById('move-copy-target-tracking').onchange = function () {
      document.getElementById('confirm-move-copy-btn').disabled = !this.value;
    };

    // Click outside to close
    const modal = document.getElementById('move-library-copy-modal');
    let mouseDownOnBackdrop = false;
    modal.addEventListener('mousedown', (e) => {
      mouseDownOnBackdrop = e.target === modal;
    });
    modal.addEventListener('click', (e) => {
      if (e.target === modal && mouseDownOnBackdrop) {
        window.closeMoveLibraryCopyModal();
      }
      mouseDownOnBackdrop = false;
    });
  } catch (error) {
    console.error('[Library] Failed to load tracking records:', error);
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `Error: ${error.message}`, 'error');
  }
};

window.closeMoveLibraryCopyModal = function () {
  const modal = document.getElementById('move-library-copy-modal');
  if (modal) modal.remove();
};

/**
 * Confirm moving a library copy to the selected tracking record
 *
 * @param {number} periodicalId - The periodical database ID
 * @param {string} issueKey - The issue key to refresh after move
 */
window.confirmMoveLibraryCopy = async function (periodicalId, issueKey) {
  const targetId = document.getElementById('move-copy-target-tracking')?.value;
  if (!targetId) return;

  const btn = document.getElementById('confirm-move-copy-btn');
  btn.disabled = true;
  btn.textContent = 'Moving...';

  try {
    const response = await APIClient.post(
      `/api/periodicals/${periodicalId}/move-to-tracking?target_tracking_id=${targetId}`
    );
    const result = await response.json();

    UIUtils.showStatus(
      ELEMENT_IDS.TRACKING_STATUS,
      result.message || 'Issue moved successfully',
      'success'
    );
    setTimeout(() => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS), 5000);

    window.closeMoveLibraryCopyModal();

    // Refresh search results
    if (window.trackingManager) {
      window.trackingManager.searchPeriodicalMetadata();
    }
  } catch (error) {
    console.error('[Library] Failed to move copy:', error);
    btn.disabled = false;
    btn.textContent = 'Move';
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `Error: ${error.message}`, 'error');
  }
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
    const data = await APIHelper.executeWithErrorHandling(
      async () => {
        const response = await APIClient.get(`/api/periodicals/tracking?limit=${API_LIMITS.TRACKING_LIST}`);
        return await response.json();
      },
      'Tracking',
      ELEMENT_IDS.TRACKING_STATUS
    );

    const items = data.tracked_magazines || [];

    console.log('Merge modal check:', {
      itemsLength: items.length,
      shouldShowWarning: items.length < 2,
    });

    if (items.length < 2) {
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
  const data = await APIHelper.executeWithErrorHandling(
    async () => {
      const response = await APIClient.get(`/api/periodicals/tracking?limit=${API_LIMITS.TRACKING_LIST}`);
      return await response.json();
    },
    'Tracking',
    ELEMENT_IDS.TRACKING_STATUS
  );
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
    const data = await APIHelper.executeWithErrorHandling(
      async () => {
        const response = await APIClient.post(`/api/periodicals/tracking/${targetId}/merge`, {
          source_ids: sourceIds,
        });
        return await response.json();
      },
      'Tracking',
      ELEMENT_IDS.TRACKING_STATUS
    );

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
  } catch (error) {
    console.error('Merge error:', error);
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `✗ ${error.message}`, 'error');
  }
};

// Filter search results by source provider
window.filterSearchBySource = function (source) {
  const tracking = window.trackingManager;
  if (tracking) {
    tracking.filterSearchBySource(source);
  }
};

// Download all available issues
window.downloadAllAvailable = async function () {
  try {
    const trackingId = window.currentTrackingId;
    if (!trackingId) {
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Error: No tracking ID available', 'error');
      return;
    }

    const tracking = window.trackingManager;
    if (!tracking || !tracking.availableIssues || tracking.availableIssues.length === 0) {
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'No available issues to download', 'info');
      return;
    }

    const count = tracking.availableIssues.length;
    const sourceNote =
      tracking.sourceFilter && tracking.sourceFilter !== 'all'
        ? ` from <strong>${tracking.sourceFilter === 'internet_archive' ? 'Internet Archive' : tracking.sourceFilter.charAt(0).toUpperCase() + tracking.sourceFilter.slice(1)}</strong>`
        : '';
    const confirmed = await UIUtils.confirm(
      'Download All Available Issues',
      `Are you sure you want to download all <strong>${count}</strong> available issues${sourceNote}?`
    );
    if (!confirmed) return;

    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `Downloading ${count} issues...`, 'info');

    try {
      // Use batch endpoint to submit all issues in a single request
      const response = await APIClient.post('/api/downloads/batch-issues', {
        tracking_id: trackingId,
        issues: tracking.availableIssues.map((issue) => ({
          title: issue.title,
          url: issue.url,
          provider: issue.provider,
        })),
      });
      const data = await response.json();

      const parts = [];
      if (data.submitted > 0) parts.push(`${data.submitted} submitted`);
      if (data.queued > 0) parts.push(`${data.queued} queued`);
      if (data.skipped > 0) parts.push(`${data.skipped} skipped`);
      if (data.failed > 0) parts.push(`${data.failed} failed`);
      const message = parts.join(', ') || 'No issues to download';

      const hasErrors = data.failed > 0;
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, message, hasErrors ? 'warning' : 'success');
    } catch (err) {
      console.error('Batch download error:', err);
      UIUtils.showStatus(
        ELEMENT_IDS.TRACKING_STATUS,
        `Error: ${err.toUserMessage ? err.toUserMessage() : err.message}`,
        'error'
      );
    }

    setTimeout(() => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS), TIMEOUTS.AUTO_HIDE_LONG);
  } catch (err) {
    console.error('Bulk download error:', err);
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, `Error: ${err.message}`, 'error');
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

    const data = await APIHelper.executeWithErrorHandling(
      async () => {
        const response = await APIClient.post('/api/downloads/single-issue', {
          tracking_id: trackingId,
          title: title,
          url: url,
          provider: provider,
        });
        return await response.json();
      },
      'Tracking',
      ELEMENT_IDS.TRACKING_STATUS
    );

    // Handle different submission statuses
    let message;
    if (data.status === 'queued') {
      message = 'Download queued (will be submitted when slot available)';
    } else if (data.job_id) {
      message = `Download submitted! Job ID: ${data.job_id}`;
    } else {
      message = `Download ${data.status}`;
    }

    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, message, 'success');
    setTimeout(() => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS), TIMEOUTS.AUTO_HIDE_LONG);
    // Keep search modal open so user can continue browsing
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

  // Get organization pattern from dropdown or custom input
  const patternSelect = document.getElementById('new-tracking-pattern-select');
  const patternCustom = document.getElementById('new-tracking-pattern-custom');
  let organizationPattern = null;

  if (patternSelect && patternSelect.value) {
    if (patternSelect.value === 'custom' && patternCustom) {
      organizationPattern = patternCustom.value.trim() || null;
    } else if (patternSelect.value !== '') {
      // Map pattern keys to their templates
      const patternTemplates = {
        default: '{category}/{title}/{year}/',
        volume: '{category}/{title}/Vol{volume}/',
        flat: '{category}/{title}/',
        volume_year: '{category}/{title}/Vol{volume}/{year}/',
        issue: '{category}/{title}/Issues {issue_range}/',
      };
      organizationPattern = patternTemplates[patternSelect.value] || null;
    }
  }

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

    const data = await APIHelper.executeWithErrorHandling(
      async () => {
        const response = await APIClient.post(`/api/periodicals/track?${params.toString()}`, {});
        return await response.json();
      },
      'Tracking',
      ELEMENT_IDS.TRACKING_STATUS
    );

    if (data.success) {
      // Now update with the tracking mode, download category, country, and organization pattern
      const updateData = {
        track_all_editions: trackingMode === 'all',
        track_new_only: trackingMode === 'new',
        country: country || null,
      };
      if (downloadCategory) {
        updateData.download_category = downloadCategory;
      }
      if (organizationPattern) {
        updateData.organization_pattern = organizationPattern;
      }
      await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.put(
            `/api/periodicals/tracking/${data.tracking_id}`,
            updateData
          );
          return await response.json();
        },
        'Tracking',
        ELEMENT_IDS.TRACKING_STATUS
      );

      // Add to stack if one was selected
      const selectedStack = document.getElementById('new-tracking-stack')?.value;
      if (selectedStack) {
        try {
          await APIClient.authenticatedFetch(`/api/stacks/${selectedStack}/members`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tracking_ids: [data.tracking_id] }),
          });
        } catch (stackErr) {
          console.error('Failed to add to stack:', stackErr);
        }
      }

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

/**
 * Reorganize files for a tracking record to match its organization pattern
 *
 * @param {number} trackingId - Tracking record ID
 * @param {string} _title - Periodical title (unused but kept for API consistency)
 * @returns {Promise<void>}
 */
async function reorganizeTrackingFiles(trackingId, _title) {
  try {
    UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, 'Reorganizing files...', 'info');

    const result = await APIHelper.executeWithErrorHandling(
      async () => {
        const response = await APIClient.post(
          `/api/periodicals/tracking/${trackingId}/reorganize`,
          {}
        );
        return await response.json();
      },
      'Tracking',
      ELEMENT_IDS.TRACKING_STATUS
    );

    if (result.success) {
      UIUtils.showStatus(ELEMENT_IDS.TRACKING_STATUS, result.message, 'success');
      tracking.loadTrackedPeriodicals(); // Reload to reflect changes
      setTimeout(() => UIUtils.hideStatus(ELEMENT_IDS.TRACKING_STATUS), TIMEOUTS.AUTO_HIDE_SUCCESS);
    } else {
      UIUtils.showStatus(
        ELEMENT_IDS.TRACKING_STATUS,
        `Reorganization failed: ${result.message || 'Unknown error'}`,
        'error'
      );
    }
  } catch (error) {
    console.error('[Tracking] Error reorganizing files:', error);
    UIUtils.showStatus(
      ELEMENT_IDS.TRACKING_STATUS,
      `Error reorganizing files: ${error.message}`,
      'error'
    );
  }
}

// ============================================================================
// Global Function Exports for HTML Event Handlers
// ============================================================================

/**
 * Set tracking filter (category or language)
 * @param {string} type - Filter type ('category' or 'language')
 * @param {string} value - Filter value
 */
window.setTrackingFilter = function (type, value) {
  if (tracking && tracking.filterManager) {
    tracking.filterManager.setFilter(type, value);

    // Update dropdown UI
    if (type === 'category') {
      const dropdown = document.getElementById('tracking-category-filter');
      if (dropdown) dropdown.value = value;
    } else if (type === 'language') {
      const dropdown = document.getElementById('tracking-language-filter');
      if (dropdown) dropdown.value = value;
    }

    // If periodicals haven't been loaded yet, load them now
    if (!tracking.periodicalsLoaded) {
      tracking.loadTrackedPeriodicals();
    }
  }
};

/**
 * Set tracking sort field
 * @param {string} field - Sort field name
 */
window.setTrackingSortField = function (field) {
  if (tracking && tracking.sortManager) {
    tracking.sortManager.setField(field);
  }
};

/**
 * Toggle tracking sort order
 */
window.toggleTrackingSortOrder = function () {
  if (tracking) {
    tracking.toggleSortOrder();
  }
};

/**
 * Handle tracking search input
 * @param {string} query - Search query
 */
window.onTrackingSearchInput = function (query) {
  if (tracking && tracking.filterManager) {
    tracking.filterManager.setSearch(query);
  }
};

/**
 * Clear all tracking filters
 */
window.clearTrackingFilters = function () {
  if (tracking && tracking.filterManager) {
    tracking.filterManager.clearFilters();
    // Update UI to reflect cleared state
    tracking.filterManager.updateUI(
      'tracking-category-filter',
      'tracking-language-filter',
      'tracking-search-input'
    );
  }
};

window.downloadStackSearchMember = (idx) => tracking.downloadStackSearchMember(idx);
window.downloadAllStackSearchIssues = () => tracking.downloadAllStackSearchIssues();
