/**
 * EPUB Reader Module
 * Handles loading and displaying EPUB content chapter by chapter
 */

/* global URL */

import { APIClient } from './api.js';

class EPUBReader {
  constructor() {
    this.magazineId = null;
    this.metadata = null;
    this.currentChapterIndex = 0;
    this.loading = false;
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

    // Load metadata and initialize UI
    await this.loadMetadata();
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
      const response = await APIClient.get(
        `/api/periodicals/${this.magazineId}/epub/chapter/${index}`
      );
      const html = await response.text();

      // Display chapter content
      contentDiv.innerHTML = `<div class="chapter-content-inner">${html}</div>`;

      // Scroll to top
      contentDiv.scrollTop = 0;

      // Update URL without reload
      this.updateURL(index);
    } catch (error) {
      console.error('Failed to load chapter:', error);
      contentDiv.innerHTML = `<div class="error">Failed to load chapter: ${this.escapeHtml(error.message)}</div>`;
    } finally {
      this.loading = false;
    }
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
  }
});

// Mobile sidebar toggle
window.toggleSidebar = function () {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('mobile-overlay');
  sidebar.classList.toggle('open');
  overlay.classList.toggle('active');
};
