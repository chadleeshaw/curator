/**
 * EPUB Reader Module
 * Handles loading and displaying EPUB content chapter by chapter
 */

/* global URL, DOMParser, IntersectionObserver */

import { APIClient } from './api.js';
import { mediaWorker, Priority } from './media-worker-manager.js';

class EPUBReader {
  constructor() {
    this.magazineId = null;
    this.metadata = null;
    this.currentChapterIndex = 0;
    this.loading = false;
    this.zoomLevel = 100; // 50-200%
    this.isFullscreen = false;
    this.progressSaveTimer = null;
    this.workerInitialized = false;
    this.chapterCache = new Map(); // Cache for prefetched chapters
  }

  /**
   * Initialize the reader with a magazine ID from URL params
   */
  async init() {
    const urlParams = new URLSearchParams(window.location.search);
    this.magazineId = urlParams.get('id');

    if (!this.magazineId) {
      this.showError('No periodical ID provided');
      return;
    }

    // Initialize media worker
    try {
      await mediaWorker.init();
      this.workerInitialized = true;
      console.log('[EPUBReader] Media worker initialized');
    } catch (error) {
      console.warn('[EPUBReader] Media worker initialization failed:', error);
      this.workerInitialized = false;
    }

    // Setup fullscreen listeners
    this.setupFullscreenListeners();

    // Load metadata and initialize UI
    await this.loadMetadata();

    // Load saved progress
    await this.loadProgress();
  }

  /**
   * Load EPUB metadata including chapter list
   */
  async loadMetadata() {
    try {
      const response = await APIClient.get(`/api/periodicals/${this.magazineId}/epub/metadata`);
      this.metadata = await response.json();

      // Update UI with metadata
      document.getElementById('book-title').textContent = this.metadata.title || 'EPUB Reader';

      // Render chapter list
      this.renderChapterList();

      // Load first chapter by default or from URL
      const urlParams = new URLSearchParams(window.location.search);
      const chapterParam = urlParams.get('chapter');
      const startChapter = chapterParam ? parseInt(chapterParam, 10) : 0;
      await this.loadChapter(startChapter);
    } catch (error) {
      console.error('Failed to load EPUB metadata:', error);
      this.showError('Failed to load EPUB metadata: ' + error.message);
    }
  }

  /**
   * Render the chapter list in the sidebar
   */
  renderChapterList() {
    const chapterList = document.getElementById('chapter-list');

    if (!this.metadata || !this.metadata.chapters || this.metadata.chapters.length === 0) {
      chapterList.innerHTML = '<div class="error">No chapters found</div>';
      return;
    }

    chapterList.innerHTML = this.metadata.chapters
      .map(
        (chapter, index) => `
        <div 
          class="chapter-item ${index === this.currentChapterIndex ? 'active' : ''}" 
          data-index="${index}"
          onclick="epubReader.loadChapter(${index})"
        >
          <span class="chapter-number">${index + 1}.</span>
          ${this.escapeHtml(chapter)}
        </div>
      `
      )
      .join('');
  }

  /**
   * Load and display a specific chapter
   * @param {number} index - Chapter index (0-based)
   */
  async loadChapter(index) {
    if (this.loading) return;
    if (!this.metadata || index < 0 || index >= this.metadata.chapters.length) return;

    this.loading = true;
    this.currentChapterIndex = index;

    // Update UI
    this.updateChapterUI();

    const contentDiv = document.getElementById('chapter-content');
    contentDiv.innerHTML =
      '<div class="loading"><div style="text-align: center"><div class="spinner"></div><div>Loading chapter...</div></div></div>';

    try {
      // Check if chapter is cached
      let html;
      if (this.chapterCache.has(index)) {
        console.log(`Loading chapter ${index + 1} from cache`);
        html = this.chapterCache.get(index);
      } else {
        const response = await APIClient.get(
          `/api/periodicals/${this.magazineId}/epub/chapter/${index}`
        );
        html = await response.text();
        // Cache the chapter
        this.chapterCache.set(index, html);
      }

      // Display chapter content
      contentDiv.innerHTML = `<div class="chapter-content-inner" style="font-size: ${this.zoomLevel}%;">${html}</div>`;

      // Setup lazy loading for images
      this.setupImageLazyLoading(contentDiv);

      // Prefetch next chapters and their images
      this.prefetchNextChapters();

      // Scroll to top
      contentDiv.scrollTop = 0;

      // Update URL without reload
      this.updateURL(index);

      // Save progress
      this.saveProgressDebounced();
    } catch (error) {
      console.error('Failed to load chapter:', error);
      contentDiv.innerHTML = `<div class="error">Failed to load chapter: ${this.escapeHtml(error.message)}</div>`;
    } finally {
      this.loading = false;
    }
  }

  /**
   * Setup lazy loading for images in chapter content
   * @param {HTMLElement} container - Container with images
   */
  setupImageLazyLoading(container) {
    if (!this.workerInitialized || !('IntersectionObserver' in window)) {
      return; // Fallback to standard loading
    }

    const images = container.querySelectorAll('img');
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const img = entry.target;
            const src = img.src;

            // Prefetch via worker
            if (src) {
              mediaWorker.prefetch(src, Priority.HIGH, 'epub-image').catch((err) => {
                console.warn('[EPUBReader] Image prefetch failed:', err);
              });
            }

            observer.unobserve(img);
          }
        });
      },
      { rootMargin: '200px' }
    );

    images.forEach((img) => observer.observe(img));
  }

  /**
   * Prefetch next 2 chapters in background
   */
  async prefetchNextChapters() {
    if (!this.metadata || !this.workerInitialized) return;

    const chaptersToPrefetch = [];

    // Prefetch next 2 chapters
    for (let i = 1; i <= 2; i++) {
      const nextIndex = this.currentChapterIndex + i;
      if (nextIndex < this.metadata.chapters.length && !this.chapterCache.has(nextIndex)) {
        chaptersToPrefetch.push(nextIndex);
      }
    }

    // Prefetch chapters in background
    chaptersToPrefetch.forEach((chapterIndex) => {
      this.prefetchChapter(chapterIndex);
    });
  }

  /**
   * Prefetch a single chapter
   * @param {number} index - Chapter index to prefetch
   */
  async prefetchChapter(index) {
    if (this.chapterCache.has(index)) return;

    const chapterUrl = `/api/periodicals/${this.magazineId}/epub/chapter/${index}`;

    try {
      // Use worker to prefetch if available
      if (this.workerInitialized) {
        await mediaWorker.prefetch(chapterUrl, Priority.LOW, 'epub-chapter');
      }

      // Also fetch and cache the chapter HTML
      const response = await fetch(chapterUrl);
      if (response.ok) {
        const html = await response.text();
        this.chapterCache.set(index, html);
        console.log(`Prefetched chapter ${index + 1}`);

        // Prefetch images in this chapter
        this.prefetchChapterImages(html);
      }
    } catch (error) {
      console.warn(`Failed to prefetch chapter ${index + 1}:`, error);
    }
  }

  /**
   * Prefetch images from chapter HTML
   * @param {string} html - Chapter HTML content
   */
  prefetchChapterImages(html) {
    if (!this.workerInitialized) return;

    // Parse HTML to find images
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, 'text/html');
    const images = doc.querySelectorAll('img');

    images.forEach((img) => {
      const src = img.src;
      if (src) {
        mediaWorker.prefetch(src, Priority.LOW, 'epub-image').catch((err) => {
          console.warn('[EPUBReader] Image prefetch failed:', err);
        });
      }
    });
  }

  /**
   * Update chapter selection UI (sidebar, title, nav buttons)
   */
  updateChapterUI() {
    // Update sidebar active state
    document.querySelectorAll('.chapter-item').forEach((item, idx) => {
      item.classList.toggle('active', idx === this.currentChapterIndex);
    });

    // Update chapter title display
    const chapterTitle = this.metadata.chapters[this.currentChapterIndex];
    document.getElementById('current-chapter-title').textContent = chapterTitle;

    // Update navigation buttons
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');

    prevBtn.disabled = this.currentChapterIndex === 0;
    nextBtn.disabled = this.currentChapterIndex === this.metadata.chapters.length - 1;
  }

  /**
   * Navigate to previous chapter
   */
  async previousChapter() {
    if (this.currentChapterIndex > 0) {
      await this.loadChapter(this.currentChapterIndex - 1);
    }
  }

  /**
   * Navigate to next chapter
   */
  async nextChapter() {
    if (this.currentChapterIndex < this.metadata.chapters.length - 1) {
      await this.loadChapter(this.currentChapterIndex + 1);
    }
  }

  /**
   * Update URL with current chapter (for bookmarking/sharing)
   * @param {number} chapterIndex
   */
  updateURL(chapterIndex) {
    const url = new URL(window.location);
    url.searchParams.set('chapter', chapterIndex);
    window.history.replaceState({}, '', url);
  }

  /**
   * Show error message
   * @param {string} message
   */
  showError(message) {
    const contentDiv = document.getElementById('chapter-content');
    contentDiv.innerHTML = `<div class="error">${this.escapeHtml(message)}</div>`;

    const chapterList = document.getElementById('chapter-list');
    chapterList.innerHTML = `<div class="error">${this.escapeHtml(message)}</div>`;
  }

  /**
   * Escape HTML to prevent XSS
   * @param {string} text
   * @returns {string}
   */
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Load saved reading progress
   */
  async loadProgress() {
    try {
      const response = await APIClient.get(`/api/periodicals/${this.magazineId}/progress`);
      const data = await response.json();

      if (data.progress && data.progress.current_chapter !== null) {
        // Load the saved chapter (unless URL specifies a different chapter)
        const urlParams = new URLSearchParams(window.location.search);
        if (!urlParams.has('chapter')) {
          await this.loadChapter(data.progress.current_chapter);
        }
      }
    } catch (error) {
      console.log('No saved progress found or error loading progress:', error.message);
    }
  }

  /**
   * Save reading progress (debounced to avoid excessive API calls)
   */
  saveProgressDebounced() {
    // Clear existing timer
    if (this.progressSaveTimer) {
      clearTimeout(this.progressSaveTimer);
    }

    // Set new timer to save after 2 seconds of inactivity
    this.progressSaveTimer = setTimeout(() => {
      this.saveProgress();
    }, 2000);
  }

  /**
   * Save current reading progress to server
   */
  async saveProgress() {
    if (!this.metadata) return;

    try {
      await APIClient.post(`/api/periodicals/${this.magazineId}/progress`, {
        current_chapter: this.currentChapterIndex,
        total_pages: this.metadata.chapters.length,
      });
      console.log(
        `Progress saved: chapter ${this.currentChapterIndex + 1}/${this.metadata.chapters.length}`
      );
    } catch (error) {
      console.error('Failed to save progress:', error);
    }
  }

  /**
   * Adjust zoom level
   * @param {number} delta - Amount to change zoom (+/- 10)
   */
  adjustZoom(delta) {
    this.zoomLevel = Math.max(50, Math.min(200, this.zoomLevel + delta));
    document.getElementById('zoom-level').textContent = `${this.zoomLevel}%`;

    // Apply zoom to current content
    const content = document.querySelector('.chapter-content-inner');
    if (content) {
      content.style.fontSize = `${this.zoomLevel}%`;
    }
  }

  /**
   * Reset zoom to 100%
   */
  resetZoom() {
    this.zoomLevel = 100;
    document.getElementById('zoom-level').textContent = '100%';

    const content = document.querySelector('.chapter-content-inner');
    if (content) {
      content.style.fontSize = '100%';
    }
  }

  /**
   * Navigate back to the periodical detail page
   */
  goBackToPeriodical() {
    if (this.magazineId) {
      window.location.href = `/periodical?id=${this.magazineId}`;
    } else {
      // Fallback to home if no ID available
      window.location.href = '/';
    }
  }

  /**
   * Toggle fullscreen mode
   */
  toggleFullscreen() {
    const doc = document;
    const docEl = document.documentElement;

    const isFullscreen =
      doc.fullscreenElement ||
      doc.webkitFullscreenElement ||
      doc.mozFullScreenElement ||
      doc.msFullscreenElement;

    if (!isFullscreen) {
      // Enter fullscreen
      if (docEl.requestFullscreen) {
        docEl.requestFullscreen();
      } else if (docEl.webkitRequestFullscreen) {
        // Safari/iOS
        docEl.webkitRequestFullscreen();
      } else if (docEl.mozRequestFullScreen) {
        // Firefox
        docEl.mozRequestFullScreen();
      } else if (docEl.msRequestFullscreen) {
        // IE/Edge
        docEl.msRequestFullscreen();
      }
    } else {
      // Exit fullscreen
      if (doc.exitFullscreen) {
        doc.exitFullscreen();
      } else if (doc.webkitExitFullscreen) {
        doc.webkitExitFullscreen();
      } else if (doc.mozCancelFullScreen) {
        doc.mozCancelFullScreen();
      } else if (doc.msExitFullscreen) {
        doc.msExitFullscreen();
      }
    }
  }

  /**
   * Setup fullscreen change listeners
   */
  setupFullscreenListeners() {
    // Fullscreen change handler
    const handleFullscreenChange = () => {
      this.isFullscreen = !!(
        document.fullscreenElement ||
        document.webkitFullscreenElement ||
        document.mozFullScreenElement ||
        document.msFullscreenElement
      );
      const btn = document.getElementById('fullscreen-btn');
      const sidebar = document.getElementById('sidebar');

      if (btn) {
        btn.classList.toggle('active', this.isFullscreen);
        btn.textContent = this.isFullscreen ? '⛶' : '⛶';
        btn.title = this.isFullscreen ? 'Exit fullscreen' : 'Fullscreen';
      }

      // Hide sidebar in fullscreen mode
      if (sidebar) {
        sidebar.style.display = this.isFullscreen ? 'none' : 'flex';
      }

      // Setup auto-hide toolbar in fullscreen
      if (this.isFullscreen) {
        this.setupAutoHideToolbar();
      } else {
        this.cleanupAutoHideToolbar();
      }
    };

    // Listen to all vendor-prefixed fullscreen change events
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);
  }

  /**
   * Setup auto-hide toolbar behavior in fullscreen
   */
  setupAutoHideToolbar() {
    const readerHeader = document.querySelector('.reader-header');
    const contentHeader = document.querySelector('.content-header');
    let hideTimer = null;

    // Calculate proper positioning for content header below reader header
    if (readerHeader && contentHeader) {
      // Wait a tick for fullscreen padding to apply, then measure
      setTimeout(() => {
        // offsetHeight includes padding and border, subtract 1px to overlap the border
        const readerHeaderHeight = readerHeader.offsetHeight;
        contentHeader.style.setProperty('--reader-header-offset', `${readerHeaderHeight - 1}px`);
      }, 50);
    }

    // Function to show toolbars
    const showToolbars = () => {
      if (readerHeader) readerHeader.classList.add('show-toolbar');
      if (contentHeader) contentHeader.classList.add('show-toolbar');

      // Auto-hide after 3 seconds of inactivity
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => {
        if (readerHeader) readerHeader.classList.remove('show-toolbar');
        if (contentHeader) contentHeader.classList.remove('show-toolbar');
      }, 3000);
    };

    // Function to hide toolbars immediately
    const hideToolbars = () => {
      clearTimeout(hideTimer);
      if (readerHeader) readerHeader.classList.remove('show-toolbar');
      if (contentHeader) contentHeader.classList.remove('show-toolbar');
    };

    // Show toolbars when mouse moves near top of screen (but not at very top to avoid browser UI)
    const handleMouseMove = (e) => {
      // Show toolbar when mouse is between 50-150px from top (avoiding browser UI at 0-50px)
      if (e.clientY >= 50 && e.clientY < 150) {
        showToolbars();
      } else if (e.clientY > 250) {
        // Hide if mouse moves away from toolbar area
        clearTimeout(hideTimer);
        hideTimer = setTimeout(hideToolbars, 1000);
      }
    };

    // Show toolbars on touch near top of screen (avoiding very top for browser UI)
    const handleTouchStart = (e) => {
      const touch = e.touches[0];
      // Show toolbar when touch is between 50-150px from top
      if (touch.clientY >= 50 && touch.clientY < 150) {
        showToolbars();
      }
    };

    // Store handlers for cleanup
    this._toolbarMouseMove = handleMouseMove;
    this._toolbarTouchStart = handleTouchStart;

    // Add event listeners
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('touchstart', handleTouchStart);

    // Initially hide toolbars after a delay
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

    // Show toolbars when exiting fullscreen
    const readerHeader = document.querySelector('.reader-header');
    const contentHeader = document.querySelector('.content-header');
    if (readerHeader) readerHeader.classList.remove('show-toolbar');
    if (contentHeader) contentHeader.classList.remove('show-toolbar');
  }
}

// Create global instance
const epubReader = new EPUBReader();
window.epubReader = epubReader;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  epubReader.init();
});

// Handle keyboard navigation
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowLeft') {
    epubReader.previousChapter();
  } else if (e.key === 'ArrowRight') {
    epubReader.nextChapter();
  } else if (e.key === '+' || e.key === '=') {
    e.preventDefault();
    epubReader.adjustZoom(10);
  } else if (e.key === '-' || e.key === '_') {
    e.preventDefault();
    epubReader.adjustZoom(-10);
  } else if (e.key === '0') {
    e.preventDefault();
    epubReader.resetZoom();
  } else if (e.key === 'f' || e.key === 'F') {
    e.preventDefault();
    epubReader.toggleFullscreen();
  }
});

// Mobile sidebar toggle
window.toggleSidebar = function () {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('mobile-overlay');
  sidebar.classList.toggle('open');
  overlay.classList.toggle('active');
};
