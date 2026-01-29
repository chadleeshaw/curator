/**
 * Page Reader Module
 * Unified reader for page-based content (PDF, CBZ, CBR)
 * Handles loading and displaying content page by page with spread mode support
 */

/* global URL, Image */

import { APIClient, APIHelper } from './api.js';
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
 * Configuration for different content types
 */
const READER_CONFIGS = {
  pdf: {
    apiPrefix: 'pdf',
    displayName: 'PDF',
    logPrefix: 'PDFReader',
  },
  comic: {
    apiPrefix: 'comic',
    displayName: 'Comic',
    logPrefix: 'ComicReader',
  },
};

/**
 * Unified page-based content reader
 */
export class PageReader {
  /**
   * @param {string} contentType - 'pdf' or 'comic'
   */
  constructor(contentType = 'pdf') {
    const config = READER_CONFIGS[contentType] || READER_CONFIGS.pdf;
    this.contentType = contentType;
    this.apiPrefix = config.apiPrefix;
    this.displayName = config.displayName;
    this.logPrefix = config.logPrefix;

    this.magazineId = null;
    this.metadata = null;
    this.currentPageIndex = 0;
    this.loading = false;
    // Mobile portrait: fit-width, Desktop/landscape: fit-height
    this.fitMode =
      window.innerWidth <= 768 && window.innerHeight > window.innerWidth
        ? 'fit-width'
        : 'fit-height';
    this.zoomLevel = 100; // 50-400%
    // Default to spread mode on desktop or landscape orientation
    this.spreadMode = window.innerWidth > 768 || window.innerWidth > window.innerHeight;
    this.coverPageIndex = 0; // Index of the cover page (default 0)
    this.prefetchCache = new Map(); // Cache for prefetched images
    this.workerInitialized = false; // Media worker status

    // Initialize managers
    this.fullscreenManager = new FullscreenManager({
      logPrefix: this.logPrefix,
    });

    this.progressManager = new ProgressManager({
      logPrefix: this.logPrefix,
      getMagazineId: () => this.magazineId,
      getProgressData: () => ({
        current_page: this.currentPageIndex,
        total_pages: this.metadata?.pages?.length || 0,
      }),
      onProgressLoaded: (progress) => {
        if (progress.current_page !== null) {
          const urlParams = new URLSearchParams(window.location.search);
          if (!urlParams.has('page')) {
            this.loadPage(progress.current_page);
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
    this.magazineId = urlParams.get('id');

    if (!this.magazineId) {
      this.showError('No periodical ID provided');
      return;
    }

    // Initialize media worker
    try {
      await mediaWorker.init();
      this.workerInitialized = true;
      console.log(`[${this.logPrefix}] Media worker initialized`);
    } catch (error) {
      console.warn(`[${this.logPrefix}] Media worker initialization failed:`, error);
      this.workerInitialized = false;
    }

    // Setup fullscreen
    this.fullscreenManager.setup();

    // Setup orientation change listener
    this.setupOrientationListener();

    // Setup pinch-to-zoom gesture
    this.setupPinchZoom();

    // Setup swipe gestures for navigation
    this.setupSwipeGestures();

    // Load metadata and initialize UI
    await this.loadMetadata();

    // Load saved progress
    await this.progressManager.load();
  }

  /**
   * Get the API endpoint for a specific action
   * @param {string} action - e.g., 'metadata', 'page/0', 'page/0/thumbnail'
   * @returns {string} Full API endpoint
   */
  getEndpoint(action) {
    return `/api/periodicals/${this.magazineId}/${this.apiPrefix}/${action}`;
  }

  /**
   * Load content metadata including page list
   */
  async loadMetadata() {
    try {
      this.metadata = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.get(this.getEndpoint('metadata'));
        return await response.json();
      }, this.logPrefix);

      // Store cover page index from metadata (defaults to 0)
      this.coverPageIndex = this.metadata.cover_page || 0;

      // Update UI with metadata
      const titleElement = document.getElementById('pdf-title');
      if (titleElement) {
        titleElement.textContent = this.metadata.title || `${this.displayName} Reader`;
      }

      // Update spread button to reflect default state
      const spreadBtn = document.getElementById('spread-btn');
      if (spreadBtn) {
        spreadBtn.classList.toggle('active', this.spreadMode);
        spreadBtn.textContent = this.spreadMode ? '📖' : '📄';
        spreadBtn.title = this.spreadMode ? 'Single page mode (S)' : 'Two-page spread mode (S)';
      }

      // Update fit mode buttons to reflect default state
      document.querySelectorAll('.fit-btn[data-mode]').forEach((btn) => {
        btn.classList.toggle('active', btn.dataset.mode === this.fitMode);
      });

      // Render page list
      this.renderPageList();

      // Load first page by default or from URL
      const urlParams = new URLSearchParams(window.location.search);
      const pageParam = urlParams.get('page');
      const startPage = pageParam ? parseInt(pageParam, 10) : 0;
      await this.loadPage(startPage);
    } catch (error) {
      console.error(`Failed to load ${this.apiPrefix} metadata:`, error);
      this.showError(`Failed to load ${this.apiPrefix} metadata: ` + error.message);
    }
  }

  /**
   * Render the page list in the sidebar
   */
  renderPageList() {
    const pageList = document.getElementById('page-list');

    if (!this.metadata || !this.metadata.pages || this.metadata.pages.length === 0) {
      pageList.innerHTML = '<div class="error">No pages found</div>';
      return;
    }

    // Use a data attribute to store the reader reference name for onclick
    const readerName = this.contentType === 'comic' ? 'comicReader' : 'pdfReader';

    pageList.innerHTML = this.metadata.pages
      .map(
        (page, index) => `
        <div
          class="page-item ${index === this.currentPageIndex ? 'active' : ''}"
          data-index="${index}"
          onclick="${readerName}.loadPage(${index})"
        >
          <img
            src="${this.getEndpoint(`page/${index}/thumbnail`)}"
            alt="Page ${index + 1}"
            class="page-thumbnail"
            loading="lazy"
          />
          <span class="page-number">Page ${index + 1}</span>
        </div>
      `
      )
      .join('');
  }

  /**
   * Load and display a specific page
   * @param {number} index - Page index (0-based)
   */
  async loadPage(index) {
    if (this.loading) return;
    if (!this.metadata || index < 0 || index >= this.metadata.pages.length) return;

    this.loading = true;
    this.currentPageIndex = index;

    // Update UI
    this.updatePageUI();

    const contentDiv = document.getElementById('page-content');

    // Check if page(s) are already cached - skip loading spinner if so
    const isCached =
      this.spreadMode && index !== this.coverPageIndex && index < this.metadata.pages.length - 1
        ? this.prefetchCache.has(index) && this.prefetchCache.has(index + 1)
        : this.prefetchCache.has(index);

    if (!isCached) {
      contentDiv.innerHTML =
        '<div class="loading"><div style="text-align: center"><div class="spinner"></div></div></div>';
    }

    try {
      if (
        this.spreadMode &&
        index !== this.coverPageIndex &&
        index < this.metadata.pages.length - 1
      ) {
        await this.loadSpreadPages(index);
      } else {
        await this.loadSinglePage(index);
      }

      this.progressManager.saveDebounced();
      this.prefetchNextPages();
    } catch (error) {
      console.error('Failed to load page:', error);
      contentDiv.innerHTML = `<div class="error">Failed to load page: ${escapeHtml(error.message)}</div>`;
      this.loading = false;
    }
  }

  /**
   * Load a single page
   * @param {number} index - Page index
   */
  async loadSinglePage(index) {
    const contentDiv = document.getElementById('page-content');
    const imageUrl = this.getEndpoint(`page/${index}`);
    const img = new Image();

    return new Promise((resolve, reject) => {
      img.onload = () => {
        const scale = this.zoomLevel / 100;
        const transformStyle =
          scale !== 1 ? `transform: scale(${scale}); transform-origin: center;` : '';

        contentDiv.innerHTML = `
          <div class="page-image-container ${this.fitMode}">
            <img src="${imageUrl}" alt="Page ${index + 1}" class="page-image" id="page-image" style="${transformStyle}" />
          </div>
        `;

        contentDiv.scrollTop = 0;
        this.updateURL(index);
        this.loading = false;
        resolve();
      };

      img.onerror = () => {
        contentDiv.innerHTML = `<div class="error">Failed to load page image</div>`;
        this.loading = false;
        reject(new Error('Failed to load image'));
      };

      img.src = imageUrl;
    });
  }

  /**
   * Load two pages side by side (spread mode)
   * @param {number} index - Starting page index
   */
  async loadSpreadPages(index) {
    const contentDiv = document.getElementById('page-content');
    const imageUrl1 = this.getEndpoint(`page/${index}`);
    const imageUrl2 = this.getEndpoint(`page/${index + 1}`);

    const img1 = new Image();
    const img2 = new Image();

    return new Promise((resolve, reject) => {
      let loaded = 0;
      const checkBothLoaded = () => {
        loaded++;
        if (loaded === 2) {
          contentDiv.innerHTML = `
            <div class="page-spread-container ${this.fitMode}">
              <img src="${imageUrl1}" alt="Page ${index + 1}" class="spread-image" />
              <img src="${imageUrl2}" alt="Page ${index + 2}" class="spread-image" />
            </div>
          `;

          const images = contentDiv.querySelectorAll('.spread-image');
          const scale = this.zoomLevel / 100;
          images.forEach((img) => {
            if (scale !== 1) {
              img.style.transform = `scale(${scale})`;
              img.style.transformOrigin = 'center';
            }
          });

          contentDiv.scrollTop = 0;
          this.updateURL(index);
          this.loading = false;
          resolve();
        }
      };

      img1.onload = checkBothLoaded;
      img2.onload = checkBothLoaded;

      img1.onerror = img2.onerror = () => {
        contentDiv.innerHTML = `<div class="error">Failed to load page images</div>`;
        this.loading = false;
        reject(new Error('Failed to load images'));
      };

      img1.src = imageUrl1;
      img2.src = imageUrl2;
    });
  }

  /**
   * Prefetch pages ahead of current position
   */
  prefetchNextPages() {
    if (!this.metadata || !this.metadata.pages) return;

    const pagesToPrefetch = [];

    if (this.spreadMode) {
      if (this.currentPageIndex === this.coverPageIndex) {
        const firstContent = this.coverPageIndex + 1;
        for (let i = 0; i < 4 && firstContent + i < this.metadata.pages.length; i++) {
          pagesToPrefetch.push(firstContent + i);
        }
      } else {
        for (let i = 2; i <= 5; i++) {
          const nextPage = this.currentPageIndex + i;
          if (nextPage < this.metadata.pages.length) {
            pagesToPrefetch.push(nextPage);
          }
        }
      }
    } else {
      for (let i = 1; i <= 3; i++) {
        const nextPage = this.currentPageIndex + i;
        if (nextPage < this.metadata.pages.length) {
          pagesToPrefetch.push(nextPage);
        }
      }
    }

    if (this.workerInitialized && pagesToPrefetch.length > 1) {
      const urls = pagesToPrefetch
        .filter((idx) => !this.prefetchCache.has(idx))
        .map((idx) => ({
          url: this.getEndpoint(`page/${idx}`),
          priority: Priority.LOW,
          type: `${this.apiPrefix}-page`,
        }));

      if (urls.length > 0) {
        mediaWorker
          .batchPrefetch(urls)
          .then((result) => {
            if (result.success) {
              result.results.forEach((res, i) => {
                if (res.success) {
                  console.log(`Batch prefetched page ${pagesToPrefetch[i] + 1}`);
                }
              });
            }
          })
          .catch(() => {
            pagesToPrefetch.forEach((pageIndex) => this.prefetchPage(pageIndex));
          });
      }
    } else {
      pagesToPrefetch.forEach((pageIndex) => this.prefetchPage(pageIndex));
    }
  }

  /**
   * Prefetch a single page image
   * @param {number} index - Page index to prefetch
   */
  prefetchPage(index) {
    if (this.prefetchCache.has(index)) return;

    const imageUrl = this.getEndpoint(`page/${index}`);

    if (this.workerInitialized) {
      mediaWorker
        .prefetch(imageUrl, Priority.LOW, `${this.apiPrefix}-page`)
        .then((result) => {
          if (result.success && result.blob) {
            const objectUrl = URL.createObjectURL(result.blob);
            const img = new Image();
            img.src = objectUrl;
            img.onload = () => {
              this.prefetchCache.set(index, img);
              console.log(`Prefetched page ${index + 1} via worker`);
            };
          }
        })
        .catch((err) => {
          console.warn(`Failed to prefetch page ${index + 1} via worker:`, err);
        });
    } else {
      const img = new Image();
      img.onload = () => {
        this.prefetchCache.set(index, img);
        console.log(`Prefetched page ${index + 1}`);
      };
      img.onerror = () => {
        console.warn(`Failed to prefetch page ${index + 1}`);
      };
      img.src = imageUrl;
    }
  }

  /**
   * Update page selection UI (sidebar, title, nav buttons)
   */
  updatePageUI() {
    document.querySelectorAll('.page-item').forEach((item, idx) => {
      item.classList.toggle('active', idx === this.currentPageIndex);
    });

    const activeItem = document.querySelector('.page-item.active');
    if (activeItem) {
      activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    const currentPageTitle = document.getElementById('current-page-title');
    if (currentPageTitle) {
      currentPageTitle.textContent = `Page ${this.currentPageIndex + 1} of ${this.metadata.pages.length}`;
    }

    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');

    if (prevBtn) prevBtn.disabled = this.currentPageIndex === 0;
    if (nextBtn) nextBtn.disabled = this.currentPageIndex === this.metadata.pages.length - 1;
  }

  /**
   * Navigate to previous page
   */
  async previousPage() {
    if (this.currentPageIndex > 0) {
      let targetPage;
      if (this.spreadMode) {
        const firstContentPage = this.coverPageIndex + 1;
        if (this.currentPageIndex === firstContentPage) {
          targetPage = this.coverPageIndex;
        } else {
          targetPage = Math.max(firstContentPage, this.currentPageIndex - 2);
        }
      } else {
        targetPage = this.currentPageIndex - 1;
      }
      await this.loadPage(targetPage);
    }
  }

  /**
   * Navigate to next page
   */
  async nextPage() {
    if (this.currentPageIndex < this.metadata.pages.length - 1) {
      let targetPage;
      if (this.spreadMode) {
        if (this.currentPageIndex === this.coverPageIndex) {
          targetPage = this.coverPageIndex + 1;
        } else {
          targetPage = Math.min(this.metadata.pages.length - 1, this.currentPageIndex + 2);
        }
      } else {
        targetPage = this.currentPageIndex + 1;
      }
      await this.loadPage(targetPage);
    }
  }

  /**
   * Change image fit mode
   * @param {string} mode - fit-width, fit-height, or original
   */
  setFitMode(mode) {
    this.fitMode = mode;

    const singleContainer = document.querySelector('.page-image-container');
    const spreadContainer = document.querySelector('.page-spread-container');

    if (singleContainer) {
      singleContainer.className = `page-image-container ${mode}`;
    }
    if (spreadContainer) {
      spreadContainer.className = `page-spread-container ${mode}`;
    }

    document.querySelectorAll('.fit-btn').forEach((btn) => {
      btn.classList.toggle('active', btn.dataset.mode === mode);
    });
  }

  /**
   * Update URL with current page (for bookmarking/sharing)
   * @param {number} pageIndex
   */
  updateURL(pageIndex) {
    const url = new URL(window.location);
    url.searchParams.set('page', pageIndex);
    window.history.replaceState({}, '', url);
  }

  /**
   * Show error message
   * @param {string} message
   */
  showError(message) {
    const contentDiv = document.getElementById('page-content');
    if (contentDiv) {
      contentDiv.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
    }

    const pageList = document.getElementById('page-list');
    if (pageList) {
      pageList.innerHTML = `<div class="error">${escapeHtml(message)}</div>`;
    }
  }

  /**
   * Adjust zoom level
   * @param {number} delta - Amount to change zoom (+/- 10)
   */
  adjustZoom(delta) {
    this.zoomLevel = Math.max(50, Math.min(400, this.zoomLevel + delta));
    const zoomDisplay = document.getElementById('zoom-level');
    if (zoomDisplay) {
      zoomDisplay.textContent = `${this.zoomLevel}%`;
    }

    const images = document.querySelectorAll('.page-image, .spread-image');
    const scale = this.zoomLevel / 100;
    images.forEach((img) => {
      img.style.transform = `scale(${scale})`;
      img.style.transformOrigin = 'center';
    });

    const containers = document.querySelectorAll('.page-image-container, .page-spread-container');
    containers.forEach((container) => {
      container.style.overflow = scale > 1 ? 'auto' : '';
    });
  }

  /**
   * Reset zoom to 100%
   */
  resetZoom() {
    this.zoomLevel = 100;
    const zoomDisplay = document.getElementById('zoom-level');
    if (zoomDisplay) {
      zoomDisplay.textContent = '100%';
    }

    const images = document.querySelectorAll('.page-image, .spread-image');
    images.forEach((img) => {
      img.style.transform = 'scale(1)';
    });

    const containers = document.querySelectorAll('.page-image-container, .page-spread-container');
    containers.forEach((container) => {
      container.style.overflow = '';
    });
  }

  /**
   * Toggle two-page spread mode
   */
  async toggleSpreadMode() {
    this.spreadMode = !this.spreadMode;
    const btn = document.getElementById('spread-btn');
    if (btn) {
      btn.classList.toggle('active', this.spreadMode);
      btn.textContent = this.spreadMode ? '📖' : '📄';
      btn.title = this.spreadMode ? 'Single page mode' : 'Two-page spread mode';
    }
    await this.loadPage(this.currentPageIndex);
  }

  /**
   * Navigate back to the periodical detail page
   */
  goBackToPeriodical() {
    goBackToPeriodical(this.magazineId);
  }

  /**
   * Toggle fullscreen mode
   */
  toggleFullscreen() {
    this.fullscreenManager.toggle();
  }

  /**
   * Setup orientation change listener to auto-adjust spread mode and fit mode
   */
  setupOrientationListener() {
    const handleOrientationChange = async () => {
      const isPortrait = window.innerHeight > window.innerWidth;
      const isMobile = window.innerWidth <= 768;
      const shouldBeSpread = window.innerWidth > 768 || !isPortrait;
      const shouldBeFitMode = isMobile && isPortrait ? 'fit-width' : 'fit-height';

      let needsReload = false;

      if (shouldBeSpread !== this.spreadMode) {
        this.spreadMode = shouldBeSpread;
        needsReload = true;

        const spreadBtn = document.getElementById('spread-btn');
        if (spreadBtn) {
          spreadBtn.classList.toggle('active', this.spreadMode);
          spreadBtn.textContent = this.spreadMode ? '📖' : '📄';
          spreadBtn.title = this.spreadMode ? 'Single page mode (S)' : 'Two-page spread mode (S)';
        }
      }

      if (shouldBeFitMode !== this.fitMode) {
        this.fitMode = shouldBeFitMode;
        needsReload = true;

        document.querySelectorAll('.fit-btn[data-mode]').forEach((btn) => {
          btn.classList.toggle('active', btn.dataset.mode === this.fitMode);
        });
      }

      if (needsReload) {
        await this.loadPage(this.currentPageIndex);
      }
    };

    window.addEventListener('orientationchange', handleOrientationChange);

    let resizeTimer = null;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(handleOrientationChange, 300);
    });
  }

  /**
   * Setup pinch-to-zoom gesture support for mobile
   */
  setupPinchZoom() {
    const contentDiv = document.getElementById('page-content');
    if (!contentDiv) return;

    let initialDistance = 0;
    let initialZoom = 100;

    const getDistance = (touches) => {
      const dx = touches[0].clientX - touches[1].clientX;
      const dy = touches[0].clientY - touches[1].clientY;
      return Math.sqrt(dx * dx + dy * dy);
    };

    const handleTouchStart = (e) => {
      if (e.touches.length === 2) {
        e.preventDefault();
        initialDistance = getDistance(e.touches);
        initialZoom = this.zoomLevel;
      }
    };

    const handleTouchMove = (e) => {
      if (e.touches.length === 2) {
        e.preventDefault();
        const currentDistance = getDistance(e.touches);
        const scale = currentDistance / initialDistance;
        const newZoom = Math.round(initialZoom * scale);

        this.zoomLevel = Math.max(50, Math.min(400, newZoom));
        const zoomDisplay = document.getElementById('zoom-level');
        if (zoomDisplay) {
          zoomDisplay.textContent = `${this.zoomLevel}%`;
        }

        const images = document.querySelectorAll('.page-image, .spread-image');
        const zoomScale = this.zoomLevel / 100;
        images.forEach((img) => {
          img.style.transform = `scale(${zoomScale})`;
          img.style.transformOrigin = 'center';
        });

        const containers = document.querySelectorAll(
          '.page-image-container, .page-spread-container'
        );
        containers.forEach((container) => {
          container.style.overflow = zoomScale > 1 ? 'auto' : '';
        });
      }
    };

    const handleTouchEnd = (e) => {
      if (e.touches.length < 2) {
        initialDistance = 0;
        initialZoom = 100;
      }
    };

    contentDiv.addEventListener('touchstart', handleTouchStart, { passive: false });
    contentDiv.addEventListener('touchmove', handleTouchMove, { passive: false });
    contentDiv.addEventListener('touchend', handleTouchEnd);
  }

  /**
   * Setup swipe gestures for page navigation
   */
  setupSwipeGestures() {
    const contentDiv = document.getElementById('page-content');
    if (!contentDiv) return;

    let touchStartX = 0;
    let touchStartY = 0;
    let touchEndX = 0;
    let touchEndY = 0;

    const handleSwipeStart = (e) => {
      if (e.touches.length === 1) {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
      }
    };

    const handleSwipeMove = (e) => {
      if (e.touches.length === 1) {
        touchEndX = e.touches[0].clientX;
        touchEndY = e.touches[0].clientY;
      }
    };

    const handleSwipeEnd = () => {
      const deltaX = touchEndX - touchStartX;
      const deltaY = touchEndY - touchStartY;
      const minSwipeDistance = 50;

      if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > minSwipeDistance) {
        if (deltaX > 0) {
          this.previousPage();
        } else {
          this.nextPage();
        }
      }

      touchStartX = 0;
      touchStartY = 0;
      touchEndX = 0;
      touchEndY = 0;
    };

    contentDiv.addEventListener('touchstart', handleSwipeStart, { passive: true });
    contentDiv.addEventListener('touchmove', handleSwipeMove, { passive: true });
    contentDiv.addEventListener('touchend', handleSwipeEnd);
  }
}

// Re-export utilities for wrapper modules
export { setupKeyboardNavigation, setupMobileSidebar };
