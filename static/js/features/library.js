/**
 * Library Module
 * Handles periodical library display, sorting, and deletion
 * @module library
 */

/* global IntersectionObserver */

import { APIClient, APIHelper } from '../core/api.js';
import { UIUtils, SortManager, FilterManager } from '../core/ui-utils.js';
import {
  ELEMENT_IDS as _ELEMENT_IDS,
  STATUS_MESSAGES as _STATUS_MESSAGES,
  CSS_CLASSES as _CSS_CLASSES,
  TIMEOUTS,
} from '../core/constants.js';
import { ValidationError as _ValidationError } from '../core/errors.js';
import { mediaWorker, Priority } from '../readers/media-worker-manager.js';
import { stacks as stacksManager } from './stacks.js';

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
    /** @type {FilterManager} Manager for library filters */
    this.filterManager = new FilterManager('libraryFilters', () => this.applyFiltersAndRender());
    /** @type {Array} All periodicals loaded from API (unfiltered) */
    this.allPeriodicals = [];
    /** @type {boolean} Whether periodicals have been loaded at least once */
    this.periodicalsLoaded = false;
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
    /** @type {Array} All stacks loaded from API */
    this.allStacks = [];


    // Initialize media worker
    this.initMediaWorker();

    // Setup Intersection Observer for smart lazy loading
    this.setupIntersectionObserver();

    // Load categories on initialization
    this.loadCategories();

    // Load saved filter state from localStorage
    const savedFilters = this.filterManager.loadState();
    if (savedFilters) {
      // Restore sort settings
      if (savedFilters.sortField) {
        this.sortManager.field = savedFilters.sortField;
      }
      if (savedFilters.sortOrder) {
        this.sortManager.order = savedFilters.sortOrder;
      }
      // Update UI elements
      this.filterManager.updateUI(
        'library-category-filter',
        'library-language-filter',
        'library-search-input'
      );
      
      // Update sort dropdown
      const sortDropdown = document.getElementById('library-sort-select');
      if (sortDropdown) {
        sortDropdown.value = this.sortManager.field;
      }
      
      this.updateLibrarySortToggleButton();
    }

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
      // FilterManager handles loading from localStorage
      this.filterManager.loadState();
      
      // Update UI elements
      this.filterManager.updateUI(
        'library-category-filter',
        'library-language-filter',
        'library-search-input'
      );

      // Update sort dropdown
      const sortDropdown = document.getElementById('library-sort-select');
      if (sortDropdown) sortDropdown.value = this.sortManager.field;

      // Update sort toggle button
      this.updateLibrarySortToggleButton();

      console.log('[Library] Loaded saved filter state:', {
        category: this.filterManager.categoryFilter,
        language: this.filterManager.languageFilter,
        sortField: this.sortManager.field,
        sortOrder: this.sortManager.order,
      });
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
      // FilterManager handles saving to localStorage
      this.filterManager.saveState();
      
      // Also save sort settings
      const filters = {
        category: this.filterManager.categoryFilter,
        language: this.filterManager.languageFilter,
        sortField: this.sortManager.field,
        sortOrder: this.sortManager.order,
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

    // Store current value before rebuilding
    const currentValue = this.filterManager.categoryFilter || dropdown.value;

    // Temporarily remove the onchange handler to prevent triggering during rebuild
    const originalOnChange = dropdown.onchange;
    dropdown.onchange = null;

    // Keep the "All" option
    dropdown.innerHTML = '<option value="all">All</option>';

    // Add each category as an option
    categories.forEach((category) => {
      const option = document.createElement('option');
      option.value = category;
      option.textContent = category;
      dropdown.appendChild(option);
    });
    
    // Restore saved filter value
    if (currentValue && currentValue !== 'all') {
      dropdown.value = currentValue;
    }

    // Restore the onchange handler
    dropdown.onchange = originalOnChange;
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
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const { field, order } = this.sortManager.getSortParams();
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals?sort_by=${field}&sort_order=${order}&limit=10000`
      );
      return await response.json();
    }, 'Library');

    if (data) {
      // Store all periodicals unfiltered
      this.allPeriodicals = data.periodicals || [];
      this.periodicalsLoaded = true;

      // Load stacks data
      await this.loadStacks();

      // Load unique languages for language filter (independent API call)
      await this.populateLanguageDropdown();

      // Apply filters and render
      this.applyFiltersAndRender();
    }
  }

  /**
   * Load stacks data from API for library display
   *
   * @returns {Promise<void>}
   */
  async loadStacks() {
    try {
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.authenticatedFetch('/api/stacks');
        return await response.json();
      }, 'Library');

      if (data) {
        this.allStacks = data.stacks || [];
      }
    } catch (error) {
      console.warn('[Library] Failed to load stacks:', error);
      this.allStacks = [];
    }
  }

  /**
   * Apply current filters and render the filtered periodicals
   *
   * @returns {void}
   */
  applyFiltersAndRender() {
    const grid = document.getElementById('periodicals-grid');
    if (!grid) return;

    // Don't apply filters if periodicals haven't been loaded yet
    if (!this.periodicalsLoaded) {
      console.log('[Library] No periodicals loaded yet, skipping filter application');
      return;
    }

    grid.innerHTML = '';

    // Build a lookup of stacks by ID (needed before filtering for stack name search)
    const stackLookup = new Map();
    this.allStacks.forEach((s) => stackLookup.set(s.id, s));

    // Use filterManager to apply filters - search matches periodical title or stack name
    const filtered = this.filterManager.applyFilters(this.allPeriodicals, {
      getCategoryFn: (p) => p.metadata?.category || 'Unknown',
      getLanguageFn: (p) => p.language || 'English',
      getTitleFn: (p) => {
        const title = p.title || '';
        if (p.stack_id) {
          const stack = stackLookup.get(p.stack_id);
          if (stack) return `${title}\0${stack.name}`;
        }
        return title;
      },
    });

    // Determine if user is actively searching
    const isSearching = this.filterManager.searchQuery && this.filterManager.searchQuery.trim() !== '';

    // Separate items into stacked and ungrouped
    const stackMap = new Map(); // stack_id -> { stack, items: [] }
    const ungrouped = [];

    if (isSearching) {
      // When searching, show individual items (not grouped into stack cards)
      // so users can see exactly which item matched. Stack badge on each card
      // shows which stack it belongs to via the stackLookup parameter.
      const query = this.filterManager.searchQuery.toLowerCase().trim();

      // Add all filtered items as individual cards
      filtered.forEach((periodical) => ungrouped.push(periodical));

      // Also include members of stacks whose name matches the search
      const filteredIds = new Set(filtered.map((p) => p.id));
      this.allStacks.forEach((stack) => {
        if ((stack.name || '').toLowerCase().includes(query)) {
          const members = this.allPeriodicals.filter((p) => p.stack_id === stack.id && !filteredIds.has(p.id));
          members.forEach((m) => {
            ungrouped.push(m);
            filteredIds.add(m.id);
          });
        }
      });
    } else {
      // Normal browsing: group stacked items into stack cards
      filtered.forEach((periodical) => {
        if (periodical.stack_id && stackLookup.has(periodical.stack_id)) {
          if (!stackMap.has(periodical.stack_id)) {
            stackMap.set(periodical.stack_id, {
              stack: stackLookup.get(periodical.stack_id),
              items: [],
            });
          }
          stackMap.get(periodical.stack_id).items.push(periodical);
        } else {
          ungrouped.push(periodical);
        }
      });
    }

    // Render results
    const totalItems = stackMap.size + ungrouped.length;
    if (totalItems === 0) {
      const filterDesc = this.filterManager.getActiveFilterDescription();
      grid.innerHTML = `<p>No periodicals found${filterDesc}</p>`;
      if (window.updateHeaderStats) {
        window.updateHeaderStats();
      }
      return;
    }

    // Build a unified list of renderable items (stacks + ungrouped) for sorting
    const renderItems = [];

    stackMap.forEach(({ stack, items }) => {
      renderItems.push({ type: 'stack', stack, items });
    });

    ungrouped.forEach((periodical) => {
      renderItems.push({ type: 'periodical', periodical });
    });

    // Sort the unified list so stacks interleave with periodicals
    const sortField = this.sortManager.field;
    const isAsc = this.sortManager.order === 'asc';

    const getSortKey = (item) => {
      if (item.type === 'stack') {
        const s = item.stack;
        const items = item.items;
        if (sortField === 'title') return (s.name || '').toLowerCase();
        if (sortField === 'issue_date') {
          // Use the most recent issue_date across all members
          return items.reduce((max, i) => (i.issue_date > max ? i.issue_date : max), items[0]?.issue_date || '');
        }
        if (sortField === 'created_at') {
          // Use the most recent created_at across all members
          return items.reduce((max, i) => (i.created_at > max ? i.created_at : max), items[0]?.created_at || '');
        }
        if (sortField === 'issue_count') {
          // Sum issue_count across all members
          return items.reduce((sum, i) => sum + (i.issue_count || 0), 0);
        }
        return (s.name || '').toLowerCase();
      }
      const p = item.periodical;
      if (sortField === 'title') return (p.title || '').toLowerCase();
      if (sortField === 'issue_date') return p.issue_date || '';
      if (sortField === 'created_at') return p.created_at || '';
      if (sortField === 'issue_count') return p.issue_count || 0;
      return (p.title || '').toLowerCase();
    };

    renderItems.sort((a, b) => {
      const keyA = getSortKey(a);
      const keyB = getSortKey(b);
      let cmp = 0;
      if (typeof keyA === 'number' && typeof keyB === 'number') {
        cmp = keyA - keyB;
      } else {
        cmp = String(keyA).localeCompare(String(keyB));
      }
      return isAsc ? cmp : -cmp;
    });

    // Render in sorted order
    renderItems.forEach((item) => {
      if (item.type === 'stack') {
        grid.appendChild(this.createStackCard(item.stack, item.items));
      } else {
        grid.appendChild(this.createPeriodicalCard(item.periodical, stackLookup));
      }
    });

    // Update header stats
    if (window.updateHeaderStats) {
      window.updateHeaderStats();
    }

    console.log(
      `[Library] Rendered ${stackMap.size} stacks + ${ungrouped.length} items (${filtered.length} total periodicals)`
    );
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
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.authenticatedFetch('/api/periodicals/languages');
        return await response.json();
      }, 'Library');

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
        dropdown.value = this.filterManager.languageFilter;
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
    // Use FilterManager to handle filter updates
    this.filterManager.setFilter(filterType, value);
    
    // Update dropdown UI
    if (filterType === 'category') {
      const dropdown = document.getElementById('library-category-filter');
      if (dropdown) dropdown.value = value;
    } else if (filterType === 'language') {
      const dropdown = document.getElementById('library-language-filter');
      if (dropdown) dropdown.value = value;
    }
    
    // If periodicals haven't been loaded yet, load them now
    if (!this.periodicalsLoaded) {
      this.loadPeriodicals();
    }
    // Otherwise FilterManager automatically triggers applyFiltersAndRender via callback
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
    // Use FilterManager to handle search updates
    this.filterManager.setSearch(query);
    // FilterManager automatically triggers applyFiltersAndRender via callback
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
    // Use FilterManager to clear filters
    this.filterManager.clearFilters();
    
    // Update UI to reflect cleared state
    this.filterManager.updateUI(
      'library-category-filter',
      'library-language-filter',
      'library-search-input'
    );

    const searchInput = document.getElementById('library-search-input');
    if (searchInput) searchInput.value = '';

    // Save cleared state
    this.saveFilterState();

    // Re-apply filters (will show all)
    this.applyFiltersAndRender();

    console.log('[Library] Cleared all filters');
  }

  /**
   * Create a fanned stack card element for the library grid
   *
   * @param {Object} stack - Stack data from API
   * @param {Array} items - Filtered periodicals belonging to this stack
   * @returns {HTMLElement} The created stack card element
   */
  createStackCard(stack, items) {
    const card = document.createElement('div');
    card.className = 'periodical-card stack-card';

    // Build the fanned cover area
    const cover = document.createElement('div');
    cover.className = 'periodical-cover stack-cover';

    // Use preview covers from the stack data, or fall back to items
    const previewCovers = stack.preview_covers || [];
    const coverIds = previewCovers.map((c) => c.periodical_id).filter(Boolean);

    // If no preview covers, use the items from the filtered set
    if (coverIds.length === 0) {
      items.forEach((item) => {
        if (item.cover_path && coverIds.length < 3) {
          coverIds.push(item.id);
        }
      });
    }

    if (coverIds.length === 0) {
      // No covers at all - show placeholder
      const placeholder = document.createElement('div');
      placeholder.className = 'stack-cover-placeholder';
      placeholder.textContent = '📚';
      cover.appendChild(placeholder);
    } else if (coverIds.length === 1) {
      // Single cover - show full size
      const layer = document.createElement('div');
      layer.className = 'stack-cover-layer layer-single';
      const img = document.createElement('img');
      img.alt = stack.name;
      img.loading = 'lazy';
      img.src = `/api/periodicals/${coverIds[0]}/cover`;
      layer.appendChild(img);
      cover.appendChild(layer);
    } else {
      // Multiple covers - create fanned layers (up to 3)
      const layerClasses = ['layer-back', 'layer-middle', 'layer-front'];
      const displayCovers = coverIds.slice(0, 3);

      // Align layers so the front is always last
      const startIdx = layerClasses.length - displayCovers.length;

      displayCovers.forEach((coverId, idx) => {
        const layerIdx = startIdx + idx;
        if (layerIdx >= layerClasses.length) return;

        const layer = document.createElement('div');
        layer.className = `stack-cover-layer ${layerClasses[layerIdx]}`;
        const img = document.createElement('img');
        img.alt = stack.name;
        img.loading = 'lazy';
        img.src = `/api/periodicals/${coverId}/cover`;
        layer.appendChild(img);
        cover.appendChild(layer);
      });
    }

    card.appendChild(cover);

    // Info section
    const info = document.createElement('div');
    info.className = 'periodical-info';

    const h4 = document.createElement('h4');
    h4.textContent = stack.name;
    info.appendChild(h4);

    if (stack.description) {
      const desc = document.createElement('p');
      desc.textContent = stack.description;
      desc.style.overflow = 'hidden';
      desc.style.textOverflow = 'ellipsis';
      desc.style.whiteSpace = 'nowrap';
      info.appendChild(desc);
    }

    const countP = document.createElement('p');
    countP.textContent = `${stack.member_count} periodical${stack.member_count !== 1 ? 's' : ''}`;
    info.appendChild(countP);

    // Action buttons matching periodical cards
    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'periodical-actions';

    const viewBtn = document.createElement('button');
    viewBtn.className = 'btn-primary';
    viewBtn.textContent = 'Open';
    viewBtn.style.flex = '1';
    viewBtn.style.padding = '8px 14px';
    viewBtn.style.fontSize = '13px';
    viewBtn.style.fontWeight = '600';
    viewBtn.onclick = (e) => {
      e.stopPropagation();
      window.location.href = `/stacks/${stack.slug}`;
    };
    actionsDiv.appendChild(viewBtn);

    // Placeholder to match the delete button width on regular cards
    const spacer = document.createElement('div');
    spacer.className = 'btn-icon';
    spacer.style.visibility = 'hidden';
    actionsDiv.appendChild(spacer);

    info.appendChild(actionsDiv);
    card.appendChild(info);

    // Click navigates to stack detail page
    card.onclick = () => {
      window.location.href = `/stacks/${stack.slug}`;
    };

    return card;
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
   * @param {Map} [stackLookup=null] - Optional map of stack ID to stack data for badge display
   * @returns {HTMLElement} The created card element
   *
   * @example
   * const card = library.createPeriodicalCard({ id: 1, title: 'PC Gamer', issue_date: '2024-01-01' });
   */
  createPeriodicalCard(periodical, stackLookup = null) {
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

    // Language overlay on cover
    if (language && language !== 'English') {
      const langOverlay = document.createElement('span');
      langOverlay.className = 'language-overlay';
      langOverlay.textContent = language;
      cover.appendChild(langOverlay);
    }

    // Stack badge on cover when item belongs to a stack
    if (periodical.stack_id && stackLookup) {
      const stack = stackLookup.get(periodical.stack_id);
      if (stack) {
        const stackBadge = document.createElement('span');
        stackBadge.className = 'stack-badge-overlay';
        stackBadge.textContent = `\u{1F4DA} ${stack.name}`;
        stackBadge.title = `In stack: ${stack.name}`;
        cover.appendChild(stackBadge);
      }
    }

    card.appendChild(cover);

    const info = document.createElement('div');
    info.className = 'periodical-info';

    const h4 = document.createElement('h4');
    h4.textContent = title;
    info.appendChild(h4);

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
      const result = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/periodicals/${this.pendingDeleteId}?delete_files=${deleteFiles}&remove_tracking=${removeTracking}&delete_all_issues=${deleteAllIssues}`,
            { method: 'DELETE' }
          );

          if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail ?? 'Failed to delete periodical');
          }

          return await response.json();
        },
        'Library',
        'import-status'
      );

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
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.get(`/api/periodicals/${magazineId}`);
        return await response.json();
      }, 'Library');

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

// Bind search input event listener directly (more reliable than inline oninput)
const librarySearchInput = document.getElementById('library-search-input');
if (librarySearchInput) {
  librarySearchInput.addEventListener('input', (e) => {
    library.onSearchInput(e.target.value);
  });
}
