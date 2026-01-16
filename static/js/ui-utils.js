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

    return tabName;
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
    } else {
      document.body.classList.remove('dark-mode');
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

      // Close on background click
      modal.onclick = (e) => {
        if (e.target === modal) {
          cleanup();
          resolve(false);
        }
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
   * Set the sort field and reset order to ascending
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
    this.order = 'asc';
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

// Expose functions globally for onclick handlers
window.showTab = (tabName, event) => UIUtils.showTab(tabName, event);

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
