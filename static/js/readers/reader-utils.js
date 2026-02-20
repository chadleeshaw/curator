/**
 * Shared Reader Utilities
 * Common functionality for PDF, Comic, and EPUB readers
 */

import { APIClient, APIHelper } from '../core/api.js';

/**
 * Fullscreen Manager
 * Handles fullscreen mode with fallback for iOS and other browsers
 */
export class FullscreenManager {
  /**
   * @param {Object} options
   * @param {string} options.logPrefix - Prefix for log messages (e.g., 'PDFReader')
   * @param {Function} options.onEnter - Callback when entering fullscreen
   * @param {Function} options.onExit - Callback when exiting fullscreen
   */
  constructor(options = {}) {
    this.logPrefix = options.logPrefix || 'Reader';
    this.onEnter = options.onEnter || (() => {});
    this.onExit = options.onExit || (() => {});
    this.isFullscreen = false;
    this._toolbarMouseMove = null;
    this._toolbarTouchStart = null;
  }

  /**
   * Setup fullscreen button and change listeners
   */
  setup() {
    const fullscreenBtn = document.getElementById('fullscreen-btn');
    if (fullscreenBtn) {
      fullscreenBtn.removeAttribute('onclick');

      const toggleHandler = (e) => {
        e.preventDefault();
        e.stopPropagation();
        console.log(`[${this.logPrefix}] Fullscreen button clicked/touched`);
        this.toggle();
      };

      fullscreenBtn.addEventListener('click', toggleHandler);
      fullscreenBtn.addEventListener('touchend', toggleHandler);
      fullscreenBtn.style.pointerEvents = 'auto';
      fullscreenBtn.style.touchAction = 'manipulation';

      console.log(`[${this.logPrefix}] Fullscreen button event listeners attached`);
    } else {
      console.warn(`[${this.logPrefix}] Fullscreen button not found in DOM`);
    }

    // Fullscreen change handler
    const handleFullscreenChange = () => {
      this.isFullscreen = !!(
        document.fullscreenElement ||
        document.webkitFullscreenElement ||
        document.mozFullScreenElement ||
        document.msFullscreenElement
      );

      this._updateUI();

      if (this.isFullscreen) {
        this.setupAutoHideToolbar();
        this.onEnter();
      } else {
        this.cleanupAutoHideToolbar();
        this.onExit();
      }
    };

    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);
  }

  /**
   * Toggle fullscreen mode
   */
  toggle() {
    console.log(
      `[${this.logPrefix}] toggleFullscreen called, current isFullscreen:`,
      this.isFullscreen
    );

    const doc = document;
    const docEl = document.documentElement;

    const isNativeFullscreen =
      doc.fullscreenElement ||
      doc.webkitFullscreenElement ||
      doc.mozFullScreenElement ||
      doc.msFullscreenElement;

    // Check if we're in fallback fullscreen mode
    if (this.isFullscreen && !isNativeFullscreen) {
      console.log(`[${this.logPrefix}] Exiting fallback fullscreen`);
      this._enableFallback();
      return;
    }

    if (!isNativeFullscreen && !this.isFullscreen) {
      console.log(`[${this.logPrefix}] Attempting to enter fullscreen`);

      const fullscreenEnabled =
        doc.fullscreenEnabled ||
        doc.webkitFullscreenEnabled ||
        doc.mozFullScreenEnabled ||
        doc.msFullscreenEnabled;

      console.log(`[${this.logPrefix}] Fullscreen API supported:`, fullscreenEnabled);

      if (!fullscreenEnabled) {
        console.log(`[${this.logPrefix}] Fullscreen API not supported, using CSS fallback`);
        this._enableFallback();
        return;
      }

      let result = null;
      try {
        if (docEl.requestFullscreen) {
          result = docEl.requestFullscreen();
        } else if (docEl.webkitRequestFullscreen) {
          result = docEl.webkitRequestFullscreen();
        } else if (docEl.webkitRequestFullScreen) {
          result = docEl.webkitRequestFullScreen();
        } else if (docEl.mozRequestFullScreen) {
          result = docEl.mozRequestFullScreen();
        } else if (docEl.msRequestFullscreen) {
          result = docEl.msRequestFullscreen();
        }
      } catch (err) {
        console.warn(`[${this.logPrefix}] Fullscreen request threw error:`, err);
        this._enableFallback();
        return;
      }

      if (!result) {
        console.log(`[${this.logPrefix}] No fullscreen method available, using CSS fallback`);
        this._enableFallback();
        return;
      }

      if (result && typeof result.then === 'function') {
        result
          .then(() => {
            console.log(`[${this.logPrefix}] Fullscreen request succeeded`);
          })
          .catch((err) => {
            console.warn(`[${this.logPrefix}] Fullscreen request failed:`, err);
            setTimeout(() => {
              if (!this.isFullscreen) {
                this._enableFallback();
              }
            }, 100);
          });
      }
    } else if (isNativeFullscreen) {
      console.log(`[${this.logPrefix}] Exiting native fullscreen`);
      if (doc.exitFullscreen) {
        doc.exitFullscreen();
      } else if (doc.webkitExitFullscreen) {
        doc.webkitExitFullscreen();
      } else if (doc.webkitCancelFullScreen) {
        doc.webkitCancelFullScreen();
      } else if (doc.mozCancelFullScreen) {
        doc.mozCancelFullScreen();
      } else if (doc.msExitFullscreen) {
        doc.msExitFullscreen();
      }
    }
  }

  /**
   * Enable CSS-based fullscreen fallback (for iOS)
   */
  _enableFallback() {
    console.log(
      `[${this.logPrefix}] enableFullscreenFallback called, current state:`,
      this.isFullscreen
    );

    if (this.isFullscreen) {
      console.log(`[${this.logPrefix}] Exiting CSS fallback fullscreen`);
      document.body.classList.remove('fullscreen-fallback');
      this.isFullscreen = false;
      this._updateUI();
      this.cleanupAutoHideToolbar();
      this.onExit();
    } else {
      console.log(`[${this.logPrefix}] Entering CSS fallback fullscreen`);
      document.body.classList.add('fullscreen-fallback');
      this.isFullscreen = true;
      this._updateUI();
      this.setupAutoHideToolbar();
      window.scrollTo(0, 1);
      console.log(`[${this.logPrefix}] Scrolled to hide browser chrome`);
      this.onEnter();
    }
  }

  /**
   * Update UI elements based on fullscreen state
   */
  _updateUI() {
    const btn = document.getElementById('fullscreen-btn');
    const sidebar = document.getElementById('sidebar');

    if (btn) {
      btn.classList.toggle('active', this.isFullscreen);
      btn.title = this.isFullscreen ? 'Exit fullscreen' : 'Fullscreen';
      console.log(
        `[${this.logPrefix}] Button updated to ${this.isFullscreen ? 'active' : 'inactive'}`
      );
    }

    if (sidebar) {
      sidebar.style.display = this.isFullscreen ? 'none' : 'flex';
      console.log(`[${this.logPrefix}] Sidebar ${this.isFullscreen ? 'hidden' : 'shown'}`);
    }
  }

  /**
   * Setup auto-hide toolbar behavior in fullscreen
   */
  setupAutoHideToolbar() {
    const readerHeader = document.querySelector('.reader-header');
    const contentHeader = document.querySelector('.content-header');
    let hideTimer = null;

    if (readerHeader && contentHeader) {
      setTimeout(() => {
        const readerHeaderHeight = readerHeader.offsetHeight;
        contentHeader.style.setProperty('--reader-header-offset', `${readerHeaderHeight - 1}px`);
      }, 50);
    }

    const showToolbars = () => {
      if (readerHeader) readerHeader.classList.add('show-toolbar');
      if (contentHeader) contentHeader.classList.add('show-toolbar');

      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => {
        if (readerHeader) readerHeader.classList.remove('show-toolbar');
        if (contentHeader) contentHeader.classList.remove('show-toolbar');
      }, 3000);
    };

    const hideToolbars = () => {
      clearTimeout(hideTimer);
      if (readerHeader) readerHeader.classList.remove('show-toolbar');
      if (contentHeader) contentHeader.classList.remove('show-toolbar');
    };

    const handleMouseMove = (e) => {
      if (e.clientY >= 50 && e.clientY < 150) {
        showToolbars();
      } else if (e.clientY > 250) {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(hideToolbars, 1000);
      }
    };

    const handleTouchStart = (e) => {
      const touch = e.touches[0];
      if (touch.clientY >= 50 && touch.clientY < 150) {
        showToolbars();
      }
    };

    this._toolbarMouseMove = handleMouseMove;
    this._toolbarTouchStart = handleTouchStart;

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('touchstart', handleTouchStart);

    hideTimer = setTimeout(hideToolbars, 2000);
  }

  /**
   * Cleanup auto-hide toolbar listeners
   */
  cleanupAutoHideToolbar() {
    if (this._toolbarMouseMove) {
      document.removeEventListener('mousemove', this._toolbarMouseMove);
      this._toolbarMouseMove = null;
    }
    if (this._toolbarTouchStart) {
      document.removeEventListener('touchstart', this._toolbarTouchStart);
      this._toolbarTouchStart = null;
    }

    const readerHeader = document.querySelector('.reader-header');
    const contentHeader = document.querySelector('.content-header');
    if (readerHeader) readerHeader.classList.remove('show-toolbar');
    if (contentHeader) contentHeader.classList.remove('show-toolbar');
  }
}

/**
 * Progress Manager
 * Handles loading and saving reading progress
 */
export class ProgressManager {
  /**
   * @param {Object} options
   * @param {string} options.logPrefix - Prefix for log messages
   * @param {Function} options.getPeriodicalId - Function that returns current magazine ID
   * @param {Function} options.getProgressData - Function that returns progress data to save
   * @param {Function} options.onProgressLoaded - Callback when progress is loaded
   */
  constructor(options = {}) {
    this.logPrefix = options.logPrefix || 'Reader';
    this.getPeriodicalId = options.getPeriodicalId || (() => null);
    this.getProgressData = options.getProgressData || (() => ({}));
    this.onProgressLoaded = options.onProgressLoaded || (() => {});
    this.saveTimer = null;
  }

  /**
   * Load saved reading progress
   */
  async load() {
    const periodicalId = this.getPeriodicalId();
    if (!periodicalId) return null;

    try {
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.get(`/api/periodicals/${periodicalId}/progress`);
        return await response.json();
      }, this.logPrefix);

      if (data.progress) {
        this.onProgressLoaded(data.progress);
      }
      return data.progress;
    } catch (error) {
      console.log('No saved progress found or error loading progress:', error.message);
      return null;
    }
  }

  /**
   * Save progress (debounced)
   */
  saveDebounced() {
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
    }
    this.saveTimer = setTimeout(() => {
      this.save();
    }, 2000);
  }

  /**
   * Save current reading progress
   */
  async save() {
    const periodicalId = this.getPeriodicalId();
    const progressData = this.getProgressData();

    if (!periodicalId || !progressData) return;

    try {
      await APIHelper.executeWithErrorHandling(async () => {
        await APIClient.post(`/api/periodicals/${periodicalId}/progress`, progressData);
      }, this.logPrefix);
      console.log(`Progress saved:`, progressData);
    } catch (error) {
      console.error('Failed to save progress:', error);
    }
  }
}

/**
 * Escape HTML to prevent XSS
 * @param {string} text
 * @returns {string}
 */
export function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

/**
 * Navigate back to the periodical detail page
 * @param {string|number} periodicalId
 */
export function goBackToPeriodical(periodicalId) {
  if (periodicalId) {
    window.location.href = `/periodical?id=${periodicalId}`;
  } else {
    window.location.href = '/';
  }
}

/**
 * Setup mobile sidebar toggle
 */
export function setupMobileSidebar() {
  window.toggleSidebar = function () {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('mobile-overlay');
    if (sidebar) sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('active');
  };
}

/**
 * Setup keyboard navigation for a reader
 * @param {Object} handlers - Object with handler functions
 * @param {Function} handlers.previousItem - Go to previous page/chapter
 * @param {Function} handlers.nextItem - Go to next page/chapter
 * @param {Function} handlers.adjustZoom - Adjust zoom level
 * @param {Function} handlers.resetZoom - Reset zoom to 100%
 * @param {Function} handlers.toggleFullscreen - Toggle fullscreen mode
 * @param {Function} handlers.toggleSpreadMode - Toggle spread mode (optional, for page readers)
 */
export function setupKeyboardNavigation(handlers) {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft' && handlers.previousItem) {
      e.preventDefault();
      handlers.previousItem();
    } else if (e.key === 'ArrowRight' && handlers.nextItem) {
      e.preventDefault();
      handlers.nextItem();
    } else if ((e.key === '+' || e.key === '=') && handlers.adjustZoom) {
      e.preventDefault();
      handlers.adjustZoom(10);
    } else if ((e.key === '-' || e.key === '_') && handlers.adjustZoom) {
      e.preventDefault();
      handlers.adjustZoom(-10);
    } else if (e.key === '0' && handlers.resetZoom) {
      e.preventDefault();
      handlers.resetZoom();
    } else if ((e.key === 'f' || e.key === 'F') && handlers.toggleFullscreen) {
      e.preventDefault();
      handlers.toggleFullscreen();
    } else if ((e.key === 's' || e.key === 'S') && handlers.toggleSpreadMode) {
      e.preventDefault();
      handlers.toggleSpreadMode();
    }
  });
}
