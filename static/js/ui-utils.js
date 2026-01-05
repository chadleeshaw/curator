/**
 * UI Utilities Module
 * Handles tab switching, modal management, theme switching, and UI helpers
 */

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
    const savedTheme = localStorage.getItem('curator-theme') || 'light';
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

    statusDiv.classList.remove('hidden');
    
    // Style based on type
    if (type === 'success') {
      statusDiv.style.background = '#e8f5e9';
      statusDiv.style.color = '#2e7d32';
      statusDiv.style.borderColor = '#4caf50';
      statusDiv.textContent = `✓ ${message}`;
    } else if (type === 'error') {
      statusDiv.style.background = '#ffebee';
      statusDiv.style.color = '#c62828';
      statusDiv.style.borderColor = '#f44336';
      statusDiv.textContent = `✗ ${message}`;
    } else if (type === 'info') {
      statusDiv.style.background = '#e3f2fd';
      statusDiv.style.color = '#1565c0';
      statusDiv.style.borderColor = '#2196f3';
      statusDiv.textContent = `ℹ ${message}`;
    }
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
        <div id="confirm-modal" class="modal" style="display: flex;">
          <div class="modal-content" style="max-width: 450px;">
            <h2>${title}</h2>
            <p style="color: var(--text-secondary); margin: 20px 0;">${message}</p>
            <div style="display: flex; gap: 10px; margin-top: 30px;">
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
      order: this.order
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
