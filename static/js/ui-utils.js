/**
 * UI Utilities Module
 * Handles tab switching, modal management, theme switching, and UI helpers
 */

import { ELEMENT_IDS, CSS_CLASSES, TIMEOUTS, STORAGE_KEYS, DEFAULTS } from './constants.js';

export class UIUtils {
  /**
   * Show a specific tab and hide others
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
    if (selectedTab) {
      selectedTab.classList.add('active');
    }

    // Mark the clicked button as active
    if (event && event.target) {
      event.target.classList.add('active');
    } else {
      // Find button by looking at onclick attribute
      const buttons = document.querySelectorAll('.nav-btn');
      buttons.forEach((btn) => {
        const onclick = btn.getAttribute('onclick');
        if (onclick && onclick.includes(`showTab('${tabName}'`)) {
          btn.classList.add('active');
        }
      });
    }

    return tabName;
  }

  /**
   * Show a modal by ID
   */
  static showModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.remove('hidden');
    }
  }

  /**
   * Close a modal by ID
   */
  static closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.add('hidden');
    }
  }

  /**
   * Toggle a modal by ID
   */
  static toggleModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
      modal.classList.toggle('hidden');
    }
  }

  /**
   * Initialize theme from localStorage
   */
  static initTheme() {
    const savedTheme = localStorage.getItem('curator-theme') || 'dark';
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
   * Display a status message
   */
  static showStatus(elementId, message, type = 'success') {
    const statusDiv = document.getElementById(elementId);
    if (!statusDiv) return;

    statusDiv.classList.remove(CSS_CLASSES.HIDDEN);

    // Apply base status message class and type-specific class
    statusDiv.className = CSS_CLASSES.STATUS_MESSAGE;

    if (type === 'success') {
      statusDiv.classList.add(CSS_CLASSES.STATUS_SUCCESS);
      statusDiv.textContent = `✓ ${message}`;
    } else if (type === 'error') {
      statusDiv.classList.add(CSS_CLASSES.STATUS_ERROR);
      statusDiv.textContent = `✗ ${message}`;
    } else if (type === 'warning') {
      statusDiv.classList.add(CSS_CLASSES.STATUS_WARNING);
      statusDiv.textContent = message;
    } else if (type === 'info') {
      statusDiv.classList.add(CSS_CLASSES.STATUS_INFO);
      statusDiv.textContent = `ℹ ${message}`;
    }

    // Scroll to the status message so it's visible
    statusDiv.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  /**
   * Hide a status message
   */
  static hideStatus(elementId) {
    const statusDiv = document.getElementById(elementId);
    if (statusDiv) {
      statusDiv.classList.add('hidden');
    }
  }

  /**
   * Show a confirmation modal with Yes/No buttons
   * Returns a Promise that resolves to true/false
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
        if (modal) modal.remove();
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
   * Returns an object with update and close methods
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
      update: (count, status = null, message = null) => {
        currentCount = count;
        const percentage = (count / total) * 100;
        progressBar.style.width = `${percentage}%`;
        progressCount.textContent = `${count}/${total}`;
        if (status) progressStatus.textContent = status;
        if (message) progressMessage.textContent = message;
      },

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
          if (modal) modal.remove();
        };

        // Auto-close after 3 seconds if successful
        if (success) {
          setTimeout(() => {
            if (modal) modal.remove();
          }, TIMEOUTS.AUTO_HIDE_STATUS);
        }
      },

      error: (errorMessage) => {
        progressBar.className = 'progress-bar progress-bar-error';
        progressStatus.textContent = 'Error';
        progressMessage.textContent = errorMessage;
        progressMessage.classList.add(CSS_CLASSES.TEXT_ERROR);
        closeContainer.classList.remove(CSS_CLASSES.HIDDEN);

        closeBtn.onclick = () => {
          if (modal) modal.remove();
        };
      },

      close: () => {
        if (modal) modal.remove();
      }
    };
  }
}

/**
 * Sort Manager Class
 * Handles sorting state and UI updates for sortable lists
 */
export class SortManager {
  constructor(defaultField = 'title', defaultOrder = 'asc', onChangeCallback = null) {
    this.field = defaultField;
    this.order = defaultOrder;
    this.onChange = onChangeCallback;
  }

  /**
   * Set the sort field
   */
  setField(field, buttonSelector) {
    this.field = field;
    this.order = 'asc';
    this.updateButtons(buttonSelector);
    if (this.onChange) {
      this.onChange();
    }
  }

  /**
   * Toggle sort order between asc and desc
   */
  toggleOrder(toggleBtnId) {
    this.order = this.order === 'asc' ? 'desc' : 'asc';
    this.updateToggleButton(toggleBtnId);
    if (this.onChange) {
      this.onChange();
    }
  }

  /**
   * Update button states to show active sort field
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
   */
  updateToggleButton(btnId) {
    const btn = document.getElementById(btnId);
    if (btn) {
      btn.textContent = this.order === 'asc' ? '↑ Ascending' : '↓ Descending';
    }
  }

  /**
   * Get current sort parameters
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
 */
window.scrollToSection = (sectionId) => {
  const section = document.getElementById(sectionId);
  if (section) {
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
};
