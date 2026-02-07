/**
 * Event Handlers Module
 * Centralized event delegation system to replace global window functions
 *
 * NOTE: This module works ALONGSIDE existing window.* global functions for backward compatibility.
 * The window.* assignments will be removed in a future phase after HTML migration.
 */

import { CSS_CLASSES } from './core/constants.js';

export class EventHandlers {
  /**
   * Initialize all event delegation listeners
   * This sets up centralized event handling for the entire application
   */
  static init() {
    console.log('[EventHandlers] Initializing centralized event delegation...');

    this.initGlobalClickDelegation();
    this.initModalHandlers();
    this.initFormHandlers();

    console.log('[EventHandlers] Event delegation initialized successfully');
  }

  /**
   * Global click event delegation
   * Routes all data-action clicks to appropriate handlers
   */
  static initGlobalClickDelegation() {
    document.addEventListener('click', (e) => {
      const target = e.target.closest('[data-action]');
      if (!target) return;

      const action = target.dataset.action;
      const handlers = this.getActionHandlers();

      const handler = handlers[action];
      if (handler) {
        e.preventDefault();
        handler(e, target);
      } else {
        console.warn(`[EventHandlers] No handler found for action: ${action}`);
      }
    });
  }

  /**
   * Get map of all action handlers
   * @returns {Object} Map of action names to handler functions
   */
  static getActionHandlers() {
    return {
      // Tracking actions
      'close-edit-tracking-modal': () => this.closeEditTrackingModal(),
      'close-search-issues-modal': () => this.closeSearchIssuesModal(),
      'close-lang-variant-modal': () => this.closeLangVariantModal(),
      'close-merge-modal': () => this.closeMergeModal(),
      'close-merge-selection-modal': () => this.closeMergeSelectionModal(),
      'save-edited-tracking': () => this.saveEditedTracking(),
      'open-track-new-modal': () => this.openTrackNewPeriodicalModal(),
      'close-track-new-modal': () => this.closeTrackNewPeriodicalModal(),
      'save-new-tracking': () => this.saveNewTracking(),
      'save-tracking-preferences': () => this.saveTrackingPreferences(),
      'reset-tracking': () => this.resetTracking(),
      'update-tracking-mode': () => this.updateTrackingMode(),
      'open-merge-modal': () => this.openMergeModal(),
      'show-merge-target-selection': () => this.showMergeTargetSelection(),
      'confirm-merge': () => this.confirmMerge(),

      // Downloads actions
      'retry-download': (e, target) => this.retryDownload(target.dataset.id),
      'remove-from-queue': (e, target) => this.removeFromQueue(target.dataset.id),
      'retry-failed-issue': (e, target) => this.retryFailedIssue(target.dataset.id),
      'open-cleanup-modal': () => this.openCleanupModal(),
      'close-cleanup-modal': () => this.closeCleanupModal(),
      'preview-cleanup': () => this.previewCleanup(),
      'execute-cleanup': () => this.executeCleanup(),

      // Library actions
      'close-delete-modal': () => this.closeDeleteModal(),
      'confirm-delete-periodical': () => this.confirmDeletePeriodical(),
      'open-import-modal': () => this.openImportModal(),
      'close-import-modal': () => this.closeImportModal(),

      // Import actions
      'import-from-library': () => this.importFromLibraryDir(),
      'save-import-settings': () => this.saveImportSettings(),
      'start-import-with-options': () => this.startImportWithOptions(),
      'check-and-import-downloads': () => this.checkAndImportDownloads(),

      // Tasks actions
      'run-task-manually': (e, target) => this.runTaskManually(target.dataset.taskId),

      // UI actions
      'show-tab': (e, target) => this.showTab(target.dataset.tabName, e),
      'scroll-to-section': (e, target) => this.scrollToSection(target.dataset.sectionId),
      logout: () => this.logout(),
    };
  }

  /**
   * Modal-specific handlers
   * Handles modal background clicks and close button clicks.
   * Uses mousedown+click tracking to prevent text selection from closing modals.
   */
  static initModalHandlers() {
    // Track where mousedown started to avoid closing on text selection drag
    let modalMouseDownTarget = null;
    document.addEventListener('mousedown', (e) => {
      modalMouseDownTarget = e.target;
    });

    // Close modal only when both mousedown and click land on the modal backdrop
    document.addEventListener('click', (e) => {
      if (e.target.classList.contains('modal') && modalMouseDownTarget === e.target) {
        e.target.classList.add(CSS_CLASSES.HIDDEN);
      }
      modalMouseDownTarget = null;
    });

    // Close button handlers for all modals
    document.querySelectorAll('.modal .close').forEach((closeBtn) => {
      closeBtn.addEventListener('click', (e) => {
        const modal = closeBtn.closest('.modal');
        if (modal) {
          e.preventDefault();
          modal.classList.add(CSS_CLASSES.HIDDEN);
        }
      });
    });
  }

  /**
   * Form submission handlers
   * Prevents default form submission and routes to JS handlers
   */
  static initFormHandlers() {
    document.querySelectorAll('form[data-handler]').forEach((form) => {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        const handlerName = form.dataset.handler;
        const handler = this[handlerName];
        if (handler && typeof handler === 'function') {
          handler.call(this, form);
        } else {
          console.warn(`[EventHandlers] No form handler found: ${handlerName}`);
        }
      });
    });
  }

  // ============================================================================
  // Tracking Handlers
  // ============================================================================

  static closeEditTrackingModal() {
    const modal = document.getElementById('edit-tracking-modal');
    if (modal) modal.classList.add(CSS_CLASSES.HIDDEN);
  }

  static closeSearchIssuesModal() {
    const modal = document.getElementById('search-issues-modal');
    if (modal) modal.classList.add(CSS_CLASSES.HIDDEN);
  }

  static closeLangVariantModal() {
    const modal = document.getElementById('lang-variant-modal');
    if (modal) modal.classList.add(CSS_CLASSES.HIDDEN);
  }

  static closeMergeModal() {
    const modal = document.getElementById('merge-modal');
    if (modal) modal.classList.add(CSS_CLASSES.HIDDEN);
  }

  static closeMergeSelectionModal() {
    const modal = document.getElementById('merge-selection-modal');
    if (modal) modal.classList.add(CSS_CLASSES.HIDDEN);
  }

  static async saveEditedTracking() {
    if (window.trackingManager) {
      await window.trackingManager.saveEditedTracking();
    }
  }

  static openTrackNewPeriodicalModal() {
    if (window.trackingManager) {
      window.trackingManager.openTrackNewPeriodicalModal();
    }
  }

  static closeTrackNewPeriodicalModal() {
    if (window.trackingManager) {
      window.trackingManager.closeTrackNewPeriodicalModal();
    }
  }

  static async saveNewTracking() {
    if (window.saveNewTracking) {
      await window.saveNewTracking();
    }
  }

  static saveTrackingPreferences() {
    if (window.trackingManager) {
      window.trackingManager.saveTrackingPreferences();
    }
  }

  static resetTracking() {
    if (window.trackingManager) {
      window.trackingManager.resetTracking();
    }
  }

  static updateTrackingMode() {
    if (window.trackingManager) {
      window.trackingManager.updateTrackingMode();
    }
  }

  static async openMergeModal() {
    if (window.openMergeModal) {
      await window.openMergeModal();
    }
  }

  static async showMergeTargetSelection() {
    if (window.showMergeTargetSelection) {
      await window.showMergeTargetSelection();
    }
  }

  static async confirmMerge() {
    if (window.confirmMerge) {
      await window.confirmMerge();
    }
  }

  // ============================================================================
  // Downloads Handlers
  // ============================================================================

  static retryDownload(downloadId) {
    if (window.retryDownload) {
      window.retryDownload(downloadId);
    }
  }

  static removeFromQueue(downloadId) {
    if (window.removeFromQueue) {
      window.removeFromQueue(downloadId);
    }
  }

  static retryFailedIssue(issueId) {
    if (window.retryFailedIssue) {
      window.retryFailedIssue(issueId);
    }
  }

  static openCleanupModal() {
    if (window.openCleanupModal) {
      window.openCleanupModal();
    }
  }

  static closeCleanupModal() {
    if (window.closeCleanupModal) {
      window.closeCleanupModal();
    }
  }

  static previewCleanup() {
    if (window.previewCleanup) {
      window.previewCleanup();
    }
  }

  static executeCleanup() {
    if (window.executeCleanup) {
      window.executeCleanup();
    }
  }

  // ============================================================================
  // Library Handlers
  // ============================================================================

  static closeDeleteModal() {
    if (window.closeDeleteModal) {
      window.closeDeleteModal();
    }
  }

  static confirmDeletePeriodical() {
    if (window.confirmDeletePeriodical) {
      window.confirmDeletePeriodical();
    }
  }

  static openImportModal() {
    if (window.openImportModal) {
      window.openImportModal();
    }
  }

  static closeImportModal() {
    if (window.closeImportModal) {
      window.closeImportModal();
    }
  }

  // ============================================================================
  // Import Handlers
  // ============================================================================

  static importFromLibraryDir() {
    if (window.importFromLibraryDir) {
      window.importFromLibraryDir();
    }
  }

  static saveImportSettings() {
    if (window.saveImportSettings) {
      window.saveImportSettings();
    }
  }

  static startImportWithOptions() {
    if (window.startImportWithOptions) {
      window.startImportWithOptions();
    }
  }

  static checkAndImportDownloads() {
    if (window.checkAndImportDownloads) {
      window.checkAndImportDownloads();
    }
  }

  // ============================================================================
  // Tasks Handlers
  // ============================================================================

  static runTaskManually(taskId) {
    if (window.runTaskManually) {
      window.runTaskManually(taskId);
    }
  }

  // ============================================================================
  // UI Handlers
  // ============================================================================

  static showTab(tabName, event) {
    if (window.showTab) {
      window.showTab(tabName, event);
    }
  }

  static scrollToSection(sectionId) {
    if (window.scrollToSection) {
      window.scrollToSection(sectionId);
    }
  }

  static logout() {
    if (window.logout) {
      window.logout();
    }
  }
}
