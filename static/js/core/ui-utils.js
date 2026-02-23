/**
 * UI Utilities Module
 * Handles tab switching, modal management, theme switching, and UI helpers
 * @module ui-utils
 */

import {
  ELEMENT_IDS as _ELEMENT_IDS,
  CSS_CLASSES,
  TIMEOUTS,
  STORAGE_KEYS as _STORAGE_KEYS,
  DEFAULTS as _DEFAULTS,
} from './constants.js';

/**
 * UI Utilities class providing static methods for common UI operations
 * @class
 */
export class UIUtils {
  /**
   * Show a specific tab and hide others
   *
   * @param {string} tabName - The name of the tab to show (e.g., 'library', 'tracking')
   * @param {Event} [event=null] - The click event that triggered the tab switch
   * @returns {string} The name of the tab that was shown
   *
   * @example
   * UIUtils.showTab('library', event);
   */
  static showTab(tabName, event) {
    if (event) {
      event.preventDefault();
    }

    // Set URL hash
    window.location.hash = tabName;

    // Hide all tabs
    const allTabs = document.querySelectorAll('.tab');
    allTabs.forEach((tab) => tab.classList.remove('active'));

    // Remove active class from all buttons
    const allButtons = document.querySelectorAll('.nav-btn');
    allButtons.forEach((btn) => btn.classList.remove('active'));

    // Show the selected tab
    const selectedTab = document.getElementById(`${tabName}-tab`);
    selectedTab?.classList.add('active');

    // Mark the clicked button as active
    if (event?.target) {
      event.target.classList.add('active');
    } else {
      // Find button by looking at onclick attribute
      const buttons = document.querySelectorAll('.nav-btn');
      buttons.forEach((btn) => {
        const onclick = btn.getAttribute('onclick');
        if (onclick?.includes(`showTab('${tabName}'`)) {
          btn.classList.add('active');
        }
      });
    }

    // Update the main breadcrumb (with sub-tab if applicable)
    if (tabName === 'settings') {
      const savedSettingsTab = localStorage.getItem('curator-settings-tab') || 'providers';
      UIUtils.updateBreadcrumb(tabName, savedSettingsTab);
    } else if (tabName === 'queue') {
      const savedQueueView = localStorage.getItem('lastQueueView') || 'download';
      UIUtils.updateBreadcrumb(tabName, savedQueueView);
    } else {
      UIUtils.updateBreadcrumb(tabName);
    }

    // If switching to settings tab, restore the last active settings sub-tab
    if (tabName === 'settings' && window.restoreSettingsTab) {
      // Use setTimeout to ensure DOM is ready
      setTimeout(() => window.restoreSettingsTab(), 0);
    }

    return tabName;
  }

  /**
   * Update the main-page breadcrumb to reflect the active tab
   *
   * @param {string} tabName - The active tab name (e.g. 'library', 'tracking')
   */
  static updateBreadcrumb(tabName, subTab) {
    const TAB_LABELS = {
      library: 'Library',
      tracking: 'Tracking',
      stacks: 'Stacks',
      tasks: 'Tasks',
      queue: 'Queue',
      settings: 'Settings',
    };

    const SETTINGS_LABELS = {
      providers: 'Providers',
      storage: 'Storage',
      matching: 'Matching',
      tasks: 'Downloads',
      'pdf-ocr': 'PDF/OCR',
      appearance: 'Appearance',
      account: 'Account',
      advanced: 'Advanced',
    };

    const QUEUE_LABELS = {
      download: 'Downloads',
      ocr: 'OCR Processing',
    };

    const bc = document.getElementById('main-breadcrumb');
    if (!bc) return;

    const label = TAB_LABELS[tabName] || tabName;
    let html = '';

    if (tabName === 'library') {
      html = `<span class="current">${label}</span>`;
    } else {
      html =
        `<a href="#library" onclick="showTab('library', event)">Library</a>` +
        ` <span class="separator">/</span>`;

      if (subTab && tabName === 'settings') {
        const subLabel = SETTINGS_LABELS[subTab] || subTab;
        html +=
          ` <a href="#settings" onclick="showTab('settings', event)">${label}</a>` +
          ` <span class="separator">/</span>` +
          ` <span class="current">${subLabel}</span>`;
      } else if (subTab && tabName === 'queue') {
        const subLabel = QUEUE_LABELS[subTab] || subTab;
        html +=
          ` <a href="#queue" onclick="showTab('queue', event)">${label}</a>` +
          ` <span class="separator">/</span>` +
          ` <span class="current">${subLabel}</span>`;
      } else {
        html += ` <span class="current">${label}</span>`;
      }
    }

    bc.innerHTML = html;
  }

  /**
   * Show a modal by its element ID
   *
   * @param {string} modalId - The ID of the modal element to show
   * @returns {void}
   *
   * @example
   * UIUtils.showModal('edit-tracking-modal');
   */
  static showModal(modalId) {
    const modal = document.getElementById(modalId);
    modal?.classList.remove(CSS_CLASSES.HIDDEN);
  }

  /**
   * Close/hide a modal by its element ID
   *
   * @param {string} modalId - The ID of the modal element to close
   * @returns {void}
   *
   * @example
   * UIUtils.closeModal('edit-tracking-modal');
   */
  static closeModal(modalId) {
    const modal = document.getElementById(modalId);
    modal?.classList.add(CSS_CLASSES.HIDDEN);
  }

  /**
   * Toggle a modal's visibility
   *
   * @param {string} modalId - The ID of the modal element to toggle
   * @returns {void}
   *
   * @example
   * UIUtils.toggleModal('settings-modal');
   */
  static toggleModal(modalId) {
    const modal = document.getElementById(modalId);
    modal?.classList.toggle(CSS_CLASSES.HIDDEN);
  }

  /**
   * Initialize theme from localStorage
   * Applies saved theme preference or defaults to dark mode
   *
   * @returns {void}
   *
   * @example
   * // Call on page load
   * UIUtils.initTheme();
   */
  static initTheme() {
    const savedTheme = localStorage.getItem('curator-theme') ?? 'dark';
    if (savedTheme === 'dark') {
      document.body.classList.add('dark-mode');
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.body.classList.remove('dark-mode');
      document.documentElement.setAttribute('data-theme', 'light');
    }
    const themeSelect = document.getElementById('theme-mode');
    if (themeSelect) {
      themeSelect.value = savedTheme;
    }
  }

  /**
   * Set theme and save to localStorage
   *
   * @param {'dark'|'light'} theme - The theme to apply
   * @returns {void}
   *
   * @example
   * UIUtils.setTheme('dark');
   */
  static setTheme(theme) {
    localStorage.setItem('curator-theme', theme);
    if (theme === 'dark') {
      document.body.classList.add('dark-mode');
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.body.classList.remove('dark-mode');
      document.documentElement.setAttribute('data-theme', 'light');
    }
  }

  /**
   * Display a status message to the user
   *
   * @param {string} elementId - The ID of the status element to update
   * @param {string} message - The message to display
   * @param {'success'|'error'|'warning'|'info'} [type='success'] - The type of status message
   * @returns {void}
   *
   * @example
   * UIUtils.showStatus('tracking-status', 'Saved successfully', 'success');
   * UIUtils.showStatus('tracking-status', 'Please enter a title', 'error');
   */
  static showStatus(elementId, message, type = 'success') {
    const statusDiv = document.getElementById(elementId);
    if (!statusDiv) return;

    statusDiv.classList.remove(CSS_CLASSES.HIDDEN);

    // Apply base status message class and type-specific class
    statusDiv.className = CSS_CLASSES.STATUS_MESSAGE;

    const statusConfig = {
      success: { className: CSS_CLASSES.STATUS_SUCCESS, icon: '\u2713' },
      error: { className: CSS_CLASSES.STATUS_ERROR, icon: '\u2717' },
      warning: { className: CSS_CLASSES.STATUS_WARNING, icon: '' },
      info: { className: CSS_CLASSES.STATUS_INFO, icon: '\u2139' },
    };

    const config = statusConfig[type] ?? statusConfig.info;
    statusDiv.classList.add(config.className);
    statusDiv.textContent = config.icon ? `${config.icon} ${message}` : message;

    // Scroll to the status message so it's visible
    statusDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  /**
   * Hide a status message
   *
   * @param {string} elementId - The ID of the status element to hide
   * @returns {void}
   *
   * @example
   * UIUtils.hideStatus('tracking-status');
   */
  static hideStatus(elementId) {
    const statusDiv = document.getElementById(elementId);
    statusDiv?.classList.add(CSS_CLASSES.HIDDEN);
  }

  /**
   * Convert a string to title case (capitalize first letter of each word)
   *
   * @param {string} str - The string to convert
   * @returns {string} The title-cased string
   *
   * @example
   * UIUtils.toTitleCase('hello world'); // 'Hello World'
   * UIUtils.toTitleCase('nat geo mines'); // 'Nat Geo Mines'
   */
  static toTitleCase(str) {
    if (!str) return '';
    return str
      .toLowerCase()
      .split(' ')
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  }

  /**
   * Show a toast notification (temporary popup message)
   *
   * @param {string} message - The message to display
   * @param {string} type - The type of message ('success', 'error', 'warning', 'info')
   * @param {number} duration - How long to show the toast in milliseconds (default: 3000)
   *
   * @example
   * UIUtils.showToast('Item saved successfully', 'success');
   * UIUtils.showToast('An error occurred', 'error', 5000);
   */
  static showToast(message, type = 'info', duration = 3000) {
    // Check if a modal is currently visible
    const visibleModal = document.querySelector('.modal:not(.hidden)');
    const modalContent = visibleModal?.querySelector('.modal-content');

    // Determine the container parent and container ID
    const containerParent = modalContent || document.body;
    const containerId = modalContent ? 'modal-toast-container' : 'toast-container';

    // Create toast container if it doesn't exist in the appropriate context
    let toastContainer = containerParent.querySelector(`#${containerId}`);
    if (!toastContainer) {
      toastContainer = document.createElement('div');
      toastContainer.id = containerId;
      toastContainer.style.cssText = `
        position: ${modalContent ? 'absolute' : 'fixed'};
        top: 20px;
        right: 20px;
        z-index: 10000;
        display: flex;
        flex-direction: column;
        gap: 10px;
      `;
      containerParent.appendChild(toastContainer);
    }

    // Create toast element
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;

    // Set color based on type
    const colors = {
      success: 'var(--status-completed)',
      error: 'var(--status-failed)',
      warning: 'var(--status-pending)',
      info: 'var(--primary)',
    };
    const bgColor = colors[type] || colors.info;

    toast.style.cssText = `
      background: ${bgColor};
      color: white;
      padding: 12px 20px;
      border-radius: 4px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      min-width: 250px;
      max-width: 400px;
      animation: slide-in-right 0.3s ease-out;
      cursor: pointer;
      font-size: 0.9em;
    `;

    toast.textContent = message;

    // Add click to dismiss
    toast.onclick = () => {
      toast.style.animation = 'slide-out-right 0.3s ease-out';
      setTimeout(() => toast.remove(), 300);
    };

    toastContainer.appendChild(toast);

    // Auto-dismiss after duration
    setTimeout(() => {
      if (toast.parentElement) {
        toast.style.animation = 'slide-out-right 0.3s ease-out';
        setTimeout(() => toast.remove(), 300);
      }
    }, duration);
  }

  /**
   * Show a confirmation modal with Yes/No buttons
   *
   * @param {string} title - The title of the confirmation dialog
   * @param {string} message - The message/question to display (supports HTML)
   * @returns {Promise<boolean>} Resolves to true if user clicked Yes, false otherwise
   *
   * @example
   * const confirmed = await UIUtils.confirm('Delete Item', 'Are you sure?');
   * if (confirmed) {
   *   // User clicked Yes
   * }
   */
  static confirm(title, message) {
    return new Promise((resolve) => {
      const modalHTML = `
        <div id="confirm-modal" class="modal modal-visible">
          <div class="modal-content modal-content-sm">
            <h2>${title}</h2>
            <p class="modal-message">${message}</p>
            <div class="modal-actions">
              <button id="confirm-yes" class="btn-primary flex-1">Yes</button>
              <button id="confirm-no" class="btn-secondary flex-1">No</button>
            </div>
          </div>
        </div>
      `;

      document.getElementById('confirm-modal')?.remove();
      document.body.insertAdjacentHTML('beforeend', modalHTML);

      const modal = document.getElementById('confirm-modal');
      const yesBtn = document.getElementById('confirm-yes');
      const noBtn = document.getElementById('confirm-no');

      const cleanup = () => {
        modal?.remove();
      };

      yesBtn.onclick = () => {
        cleanup();
        resolve(true);
      };

      noBtn.onclick = () => {
        cleanup();
        resolve(false);
      };

      // Close on background click (track mousedown to prevent text selection closing modal)
      let confirmMouseDown = null;
      modal.onmousedown = (e) => {
        confirmMouseDown = e.target;
      };
      modal.onclick = (e) => {
        if (e.target === modal && confirmMouseDown === modal) {
          cleanup();
          resolve(false);
        }
        confirmMouseDown = null;
      };
    });
  }

  /**
   * Show a progress modal for batch operations
   *
   * @param {string} title - The title of the progress modal
   * @param {number} total - The total number of items to process
   * @returns {Object} Controller object with update, complete, error, and close methods
   * @returns {Function} return.update - Update progress (count, status, message)
   * @returns {Function} return.complete - Mark as complete (finalMessage, success)
   * @returns {Function} return.error - Show error state (errorMessage)
   * @returns {Function} return.close - Close the modal
   *
   * @example
   * const progress = UIUtils.showProgressModal('Processing', 10);
   * for (let i = 0; i < 10; i++) {
   *   progress.update(i + 1, 'Processing...', `Item ${i + 1}`);
   *   await processItem(i);
   * }
   * progress.complete('All items processed!', true);
   */
  static showProgressModal(title, total) {
    const modalHTML = `
      <div id="progress-modal" class="modal modal-visible">
        <div class="modal-content modal-content-md">
          <h2>${title}</h2>
          <div class="progress-container">
            <div class="progress-header">
              <span id="progress-status" class="progress-status">Preparing...</span>
              <span id="progress-count" class="progress-count">0/${total}</span>
            </div>
            <div class="progress-bar-container">
              <div id="progress-bar" class="progress-bar"></div>
            </div>
          </div>
          <div id="progress-message" class="progress-message"></div>
          <div id="progress-close-container" class="progress-close-container hidden">
            <button id="progress-close-btn" class="btn-primary btn-full-width">Close</button>
          </div>
        </div>
      </div>
    `;

    document.body.insertAdjacentHTML('beforeend', modalHTML);

    const modal = document.getElementById('progress-modal');
    const progressBar = document.getElementById('progress-bar');
    const progressCount = document.getElementById('progress-count');
    const progressStatus = document.getElementById('progress-status');
    const progressMessage = document.getElementById('progress-message');
    const closeContainer = document.getElementById('progress-close-container');
    const closeBtn = document.getElementById('progress-close-btn');

    let currentCount = 0;

    return {
      /**
       * Update progress display
       * @param {number} count - Current progress count
       * @param {string|null} [status=null] - Status text to display
       * @param {string|null} [message=null] - Additional message to display
       */
      update: (count, status = null, message = null) => {
        currentCount = count;
        const percentage = (count / total) * 100;
        progressBar.style.width = `${percentage}%`;
        progressCount.textContent = `${count}/${total}`;
        if (status) progressStatus.textContent = status;
        if (message) progressMessage.textContent = message;
      },

      /**
       * Mark progress as complete
       * @param {string} finalMessage - Final message to display
       * @param {boolean} [success=true] - Whether the operation was successful
       */
      complete: (finalMessage, success = true) => {
        progressBar.style.width = '100%';
        progressBar.className = success
          ? 'progress-bar progress-bar-success'
          : 'progress-bar progress-bar-error';
        progressStatus.textContent = success ? 'Complete' : 'Finished';
        progressCount.textContent = `${currentCount}/${total}`;
        progressMessage.textContent = finalMessage;
        closeContainer.classList.remove(CSS_CLASSES.HIDDEN);

        closeBtn.onclick = () => {
          modal?.remove();
        };

        // Auto-close after timeout if successful
        if (success) {
          setTimeout(() => {
            modal?.remove();
          }, TIMEOUTS.AUTO_HIDE_STATUS);
        }
      },

      /**
       * Display an error state
       * @param {string} errorMessage - Error message to display
       */
      error: (errorMessage) => {
        progressBar.className = 'progress-bar progress-bar-error';
        progressStatus.textContent = 'Error';
        progressMessage.textContent = errorMessage;
        progressMessage.classList.add(CSS_CLASSES.TEXT_ERROR);
        closeContainer.classList.remove(CSS_CLASSES.HIDDEN);

        closeBtn.onclick = () => {
          modal?.remove();
        };
      },

      /**
       * Close the modal immediately
       */
      close: () => {
        modal?.remove();
      },
    };
  }
}

/**
 * Sort Manager Class
 * Handles sorting state and UI updates for sortable lists
 * @class
 */
export class SortManager {
  /**
   * Create a new SortManager instance
   *
   * @param {string} [defaultField='title'] - The default field to sort by
   * @param {'asc'|'desc'} [defaultOrder='asc'] - The default sort order
   * @param {Function|null} [onChangeCallback=null] - Callback function when sort changes
   *
   * @example
   * const sortManager = new SortManager('title', 'asc', () => loadItems());
   */
  constructor(defaultField = 'title', defaultOrder = 'asc', onChangeCallback = null) {
    /** @type {string} Current sort field */
    this.field = defaultField;
    /** @type {'asc'|'desc'} Current sort order */
    this.order = defaultOrder;
    /** @type {Function|null} Callback when sort changes */
    this.onChange = onChangeCallback;
  }

  /**
   * Set the sort field while preserving the current sort order
   *
   * @param {string} field - The field to sort by
   * @param {string} buttonSelector - CSS selector for sort buttons to update
   * @returns {void}
   *
   * @example
   * sortManager.setField('date', '.sort-btn');
   */
  setField(field, buttonSelector) {
    this.field = field;
    // Don't reset order - preserve user's asc/desc preference
    this.updateButtons(buttonSelector);
    this.onChange?.();
  }

  /**
   * Toggle sort order between ascending and descending
   *
   * @param {string} toggleBtnId - The ID of the toggle button to update
   * @returns {void}
   *
   * @example
   * sortManager.toggleOrder('sort-toggle-btn');
   */
  toggleOrder(toggleBtnId) {
    this.order = this.order === 'asc' ? 'desc' : 'asc';
    this.updateToggleButton(toggleBtnId);
    this.onChange?.();
  }

  /**
   * Update button states to show active sort field
   *
   * @param {string} selector - CSS selector for sort buttons
   * @returns {void}
   */
  updateButtons(selector) {
    const buttons = document.querySelectorAll(selector);
    buttons.forEach((btn) => {
      if (btn.dataset.field === this.field) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    });
  }

  /**
   * Update toggle button to show current order
   *
   * @param {string} btnId - The ID of the toggle button
   * @returns {void}
   */
  updateToggleButton(btnId) {
    const btn = document.getElementById(btnId);
    if (btn) {
      btn.textContent = this.order === 'asc' ? '\u2191 Ascending' : '\u2193 Descending';
    }
  }

  /**
   * Get current sort parameters
   *
   * @returns {{field: string, order: string}} Object containing field and order
   *
   * @example
   * const { field, order } = sortManager.getSortParams();
   */
  getSortParams() {
    return {
      field: this.field,
      order: this.order,
    };
  }
}

/**
 * Filter Manager class for managing filter state and persistence
 * @class
 */
export class FilterManager {
  /**
   * Create a new FilterManager instance
   *
   * @param {string} storageKey - The localStorage key for persisting filters
   * @param {Function} onFilterChange - Callback function when filters change
   */
  constructor(storageKey, onFilterChange) {
    /** @type {string} localStorage key */
    this.storageKey = storageKey;
    /** @type {Function} Callback when filters change */
    this.onFilterChange = onFilterChange;
    /** @type {string} Current category filter */
    this.categoryFilter = 'all';
    /** @type {string} Current language filter */
    this.languageFilter = 'all';
    /** @type {string} Current search query */
    this.searchQuery = '';
  }

  /**
   * Load saved filter state from localStorage
   *
   * @returns {Object} The loaded filter state
   */
  loadState() {
    try {
      const saved = localStorage.getItem(this.storageKey);
      if (saved) {
        const filters = JSON.parse(saved);
        this.categoryFilter = filters.category || 'all';
        this.languageFilter = filters.language || 'all';
        // Don't restore search query - it should always start empty
        this.searchQuery = '';
        return filters;
      }
    } catch (error) {
      console.warn(`[FilterManager] Failed to load saved filters from ${this.storageKey}:`, error);
    }
    return null;
  }

  /**
   * Save current filter state to localStorage
   *
   * @returns {void}
   */
  saveState() {
    try {
      const filters = {
        category: this.categoryFilter,
        language: this.languageFilter,
        // Don't save search query - it should always start fresh
      };
      localStorage.setItem(this.storageKey, JSON.stringify(filters));
    } catch (error) {
      console.warn(`[FilterManager] Failed to save filters to ${this.storageKey}:`, error);
    }
  }

  /**
   * Set a filter value and trigger callback
   *
   * @param {string} filterType - The type of filter ('category' or 'language')
   * @param {string} value - The filter value
   * @returns {void}
   */
  setFilter(filterType, value) {
    if (filterType === 'category') {
      this.categoryFilter = value;
    } else if (filterType === 'language') {
      this.languageFilter = value;
    }
    this.saveState();
    if (this.onFilterChange) {
      this.onFilterChange();
    }
  }

  /**
   * Set search query and trigger callback
   *
   * @param {string} query - The search query
   * @returns {void}
   */
  setSearch(query) {
    this.searchQuery = query;
    // Don't save search query to localStorage
    if (this.onFilterChange) {
      this.onFilterChange();
    }
  }

  /**
   * Clear all filters and trigger callback
   *
   * @returns {void}
   */
  clearFilters() {
    this.categoryFilter = 'all';
    this.languageFilter = 'all';
    this.searchQuery = '';
    this.saveState();
    if (this.onFilterChange) {
      this.onFilterChange();
    }
  }

  /**
   * Populate a category dropdown with options
   *
   * @param {string} dropdownId - The ID of the select element
   * @param {string[]} categories - Array of category names
   * @returns {void}
   */
  populateCategoryDropdown(dropdownId, categories) {
    const dropdown = document.getElementById(dropdownId);
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

    // Restore saved value
    if (this.categoryFilter) {
      dropdown.value = this.categoryFilter;
    }
  }

  /**
   * Populate a language dropdown with options
   *
   * @param {string} dropdownId - The ID of the select element
   * @param {string[]} languages - Array of language names
   * @returns {void}
   */
  populateLanguageDropdown(dropdownId, languages) {
    const dropdown = document.getElementById(dropdownId);
    if (!dropdown) return;

    // Keep the "All" option
    dropdown.innerHTML = '<option value="all">All</option>';

    // Add each language as an option
    languages.forEach((lang) => {
      const option = document.createElement('option');
      option.value = lang;
      option.textContent = lang;
      dropdown.appendChild(option);
    });

    // Restore saved value
    if (this.languageFilter) {
      dropdown.value = this.languageFilter;
    }
  }

  /**
   * Update UI elements with current filter state
   *
   * @param {string} categoryDropdownId - The ID of the category select element
   * @param {string} languageDropdownId - The ID of the language select element
   * @param {string} searchInputId - The ID of the search input element
   * @returns {void}
   */
  updateUI(categoryDropdownId, languageDropdownId, searchInputId) {
    const categoryDropdown = document.getElementById(categoryDropdownId);
    if (categoryDropdown) categoryDropdown.value = this.categoryFilter;

    const languageDropdown = document.getElementById(languageDropdownId);
    if (languageDropdown) languageDropdown.value = this.languageFilter;

    const searchInput = document.getElementById(searchInputId);
    if (searchInput) searchInput.value = this.searchQuery || '';
  }

  /**
   * Apply filters to an array of items
   *
   * @param {Array} items - The items to filter
   * @param {Object} options - Filter options
   * @param {Function} options.getCategoryFn - Function to extract category from an item
   * @param {Function} options.getLanguageFn - Function to extract language from an item
   * @param {Function} options.getTitleFn - Function to extract title from an item
   * @returns {Array} The filtered items
   */
  applyFilters(items, { getCategoryFn, getLanguageFn, getTitleFn }) {
    let filtered = [...items];

    // Apply category filter
    if (this.categoryFilter !== 'all') {
      filtered = filtered.filter((item) => getCategoryFn(item) === this.categoryFilter);
    }

    // Apply language filter
    if (this.languageFilter !== 'all') {
      filtered = filtered.filter((item) => getLanguageFn(item) === this.languageFilter);
    }

    // Apply search query
    if (this.searchQuery.trim()) {
      const query = this.searchQuery.toLowerCase().trim();
      filtered = filtered.filter((item) => {
        const title = getTitleFn(item).toLowerCase();
        return title.includes(query);
      });
    }

    return filtered;
  }

  /**
   * Get a description of currently active filters
   *
   * @returns {string} Description of active filters
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
   * Check if any filters are active
   *
   * @returns {boolean} True if any filter is active
   */
  hasActiveFilters() {
    return (
      this.categoryFilter !== 'all' ||
      this.languageFilter !== 'all' ||
      this.searchQuery.trim() !== ''
    );
  }
}

// Expose functions globally for onclick handlers
window.showTab = (tabName, event) => UIUtils.showTab(tabName, event);

/* ---------- Scroll-collapse header ---------- */
(function initHeaderCollapse() {
  const COLLAPSE_AT = 80; // collapse when scrolled past this
  const EXPAND_AT = 10; // only expand when nearly at top
  let collapsed = false;

  const onScroll = () => {
    const y = window.scrollY;

    if (!collapsed && y > COLLAPSE_AT) {
      // Only collapse if the page is tall enough to stay scrollable
      // without the header (~250px for header + nav)
      const headerHeight = document.querySelector('header')?.offsetHeight || 0;
      const navHeight = document.querySelector('nav:not(.breadcrumb)')?.offsetHeight || 0;
      const savedSpace = headerHeight + navHeight + 40; // margins
      const remainingHeight = document.documentElement.scrollHeight - savedSpace;

      if (remainingHeight > window.innerHeight + COLLAPSE_AT) {
        collapsed = true;
        document.body.classList.add('header-collapsed');
      }
    } else if (collapsed && y <= EXPAND_AT) {
      collapsed = false;
      document.body.classList.remove('header-collapsed');
    }
  };

  window.addEventListener('scroll', onScroll, { passive: true });
})();

/**
 * Scroll to a specific section within the settings page
 *
 * @param {string} sectionId - The ID of the section to scroll to
 * @returns {void}
 */
window.scrollToSection = (sectionId) => {
  const section = document.getElementById(sectionId);
  section?.scrollIntoView({ behavior: 'smooth', block: 'start' });
};
