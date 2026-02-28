/**
 * EPUB Reader Module
 * Handles loading and displaying EPUB content chapter by chapter
 */

/* global DOMParser, IntersectionObserver */

import { APIClient, APIHelper } from '../core/api.js';
import { mediaWorker, Priority } from './media-worker-manager.js';
import {
  FullscreenManager,
  ProgressManager,
  escapeHtml,
  goBackToPeriodical,
  setupMobileSidebar,
  setupKeyboardNavigation,
} from './reader-utils.js';

/**
 * Sanitize HTML from EPUB chapters using DOMParser to strip XSS vectors.
 * Removes scripts, inline event handlers, and javascript: URIs before
 * injecting content into the DOM.
 *
 * @param {string} html - Raw HTML string from EPUB chapter
 * @returns {string} Sanitized HTML string safe for innerHTML assignment
 */
function sanitizeEpubHtml(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, 'text/html');

  // Remove dangerous elements entirely
  doc
    .querySelectorAll('script, style, iframe, object, embed, form, meta, link')
    .forEach((el) => el.remove());

  // Strip inline event handler attributes and unsafe URL schemes
  const eventAttrs = [
    'onerror', 'onload', 'onclick', 'onmouseover', 'onfocus', 'onblur',
    'onkeydown', 'onkeyup', 'onkeypress', 'onchange', 'onsubmit', 'onreset',
    'onselect', 'ondblclick', 'onmousedown', 'onmouseup', 'onmousemove',
    'onmouseout', 'onmouseenter', 'onmouseleave', 'oncontextmenu', 'onwheel',
    'ondrag', 'ondragend', 'ondragenter', 'ondragleave', 'ondragover',
    'ondragstart', 'ondrop',
  ];

  doc.querySelectorAll('*').forEach((el) => {
    eventAttrs.forEach((attr) => el.removeAttribute(attr));

    // Remove javascript: URIs from href / src / action
    ['href', 'src', 'action'].forEach((attr) => {
      const val = el.getAttribute(attr);
      if (val && /^\s*javascript:/i.test(val)) el.removeAttribute(attr);
    });

    // Remove data: URIs from non-image src (potential XSS vector)
    const src = el.getAttribute('src');
    if (src && /^\s*data:/i.test(src) && el.tagName !== 'IMG') {
      el.removeAttribute('src');
    }
  });

  // Return sanitized body content (EPUB chapters are body fragments)
  return doc.body ? doc.body.innerHTML : doc.documentElement.innerHTML;
}

const MAX_CHAPTER_CACHE_SIZE = 25;

class EPUBReader {
  constructor() {
    this.periodicalId = null;
    this.metadata = null;
    this.currentChapterIndex = 0;
    this.loading = false;
    this.zoomLevel = 100; // 50-200%
    this.workerInitialized = false;
    this.chapterCache = new Map();

    // Initialize managers
    this.fullscreenManager = new FullscreenManager({
      logPrefix: 'EPUBReader',
    });

    this.progressManager = new ProgressManager({
      logPrefix: 'EPUBReader',
      getPeriodicalId: () => this.periodicalId,
      getProgressData: () => ({
        current_chapter: this.currentChapterIndex,
        total_pages: this.metadata?.chapters?.length || 0,
      }),
      onProgressLoaded: (progress) => {
        if (progress.current_chapter != null) {
          const urlParams = new URLSearchParams(window.location.search);
          if (!urlParams.has('chapter')) {
            this.loadChapter(progress.current_chapter);
          }
        }
      },
    });
  }

  /**
   * Initialize the reader with a magazine ID from URL params
   */
  async init() {
    const urlParams = new URLSearchParams(window.location.search);
    this.periodicalId = urlParams.get('id');

    if (!this.periodicalId) {
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

    // Setup fullscreen
    this.fullscreenManager.setup();

    // Load metadata and initialize UI
    await this.loadMetadata();

    // Load saved progress
    await this.progressManager.load();
  }

  /**
   * Load EPUB metadata including chapter list
   */
  async loadMetadata() {
    try {
      this.metadata = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.get(`/api/periodicals/${this.periodicalId}/epub/metadata`);
        return await response.json();
      }, 'EPUBReader');

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
          ${escapeHtml(chapter)}
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
        html = await APIHelper.executeWithErrorHandling(async () => {
          const response = await APIClient.get(
            `/api/periodicals/${this.periodicalId}/epub/chapter/${index}`
          );
          return await response.text();
        }, 'EPUBReader');
        // Cache the chapter
        this.chapterCache.set(index, html);
        if (this.chapterCache.size > MAX_CHAPTER_CACHE_SIZE) {
          const oldestKey = this.chapterCache.keys().next().value;
          this.chapterCache.delete(oldestKey);
        }
      }
      // Display chapter content
      contentDiv.innerHTML = `<div class="chapter-content-inner" style="font-size: ${this.zoomLevel}%;">${sanitizeEpubHtml(html)}</div>`;

      // Setup lazy loading for images
      this.setupImageLazyLoading(contentDiv);

      // Prefetch next chapters and their images
      this.prefetchNextChapters();

      // Scroll to top
      contentDiv.scrollTop = 0;

      // Update URL without reload
      this.updateURL(index);

      // Save progress
      this.progressManager.saveDebounced();
    } catch (error) {
      console.error('Failed to load chapter:', error);
      contentDiv.innerHTML = `<div class="error">Failed to load chapter: ${escapeHtml(error.message)}</div>`;
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
      return;
    }

    // Disconnect any previous observer to avoid memory leaks
    if (this.imageObserver) {
      this.imageObserver.disconnect();
    }

    const images = container.querySelectorAll('img');
    this.imageObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const img = entry.target;
            const src = img.src;

            if (src) {
              mediaWorker.prefetch(src, Priority.HIGH, 'epub-image').catch((err) => {
                console.warn('[EPUBReader] Image prefetch failed:', err);
              });
            }

            this.imageObserver.unobserve(img);
          }
        });
      },
      { rootMargin: '200px' }
    );

    images.forEach((img) => this.imageObserver.observe(img));
  }

  /**
   * Prefetch next 2 chapters in background
   */
  async prefetchNextChapters() {
    if (!this.metadata || !this.workerInitialized) return;

    const chaptersToPrefetch = [];

    for (let i = 1; i <= 2; i++) {
      const nextIndex = this.currentChapterIndex + i;
      if (nextIndex < this.metadata.chapters.length && !this.chapterCache.has(nextIndex)) {
        chaptersToPrefetch.push(nextIndex);
      }
    }

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

    const chapterUrl = `/api/periodicals/${this.periodicalId}/epub/chapter/${index}`;

    try {
      if (this.workerInitialized) {
        await mediaWorker.prefetch(chapterUrl, Priority.LOW, 'epub-chapter');
      }

      const response = await fetch(chapterUrl);
      if (response.ok) {
        const html = await response.text();
        this.chapterCache.set(index, html);
        if (this.chapterCache.size > MAX_CHAPTER_CACHE_SIZE) {
          const oldestKey = this.chapterCache.keys().next().value;
          this.chapterCache.delete(oldestKey);
        }
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
    document.querySelectorAll('.chapter-item').forEach((item, idx) => {
      item.classList.toggle('active', idx === this.currentChapterIndex);
    });

    const chapterTitle = this.metadata.chapters[this.currentChapterIndex];
    document.getElementById('current-chapter-title').textContent = chapterTitle;

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
    contentDiv.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;

    const chapterList = document.getElementById('chapter-list');
    chapterList.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
  }

  /**
   * Adjust zoom level
   * @param {number} delta - Amount to change zoom (+/- 10)
   */
  adjustZoom(delta) {
    this.zoomLevel = Math.max(50, Math.min(200, this.zoomLevel + delta));
    document.getElementById('zoom-level').textContent = `${this.zoomLevel}%`;

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
    goBackToPeriodical(this.periodicalId);
  }

  /**
   * Toggle fullscreen mode
   */
  toggleFullscreen() {
    this.fullscreenManager.toggle();
  }
}

// Create global instance
const epubReader = new EPUBReader();
window.epubReader = epubReader;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  epubReader.init();
});

// Setup keyboard navigation
setupKeyboardNavigation({
  previousItem: () => epubReader.previousChapter(),
  nextItem: () => epubReader.nextChapter(),
  adjustZoom: (delta) => epubReader.adjustZoom(delta),
  resetZoom: () => epubReader.resetZoom(),
  toggleFullscreen: () => epubReader.toggleFullscreen(),
});

// Setup mobile sidebar toggle
setupMobileSidebar();
