/**
 * Comic Reader Module
 * Handles loading and displaying CBZ/CBR content page by page
 */

/* global URL, Image */

import { APIClient } from './api.js';
import { mediaWorker, Priority } from './media-worker-manager.js';

class ComicReader {
  constructor() {
    this.magazineId = null;
    this.metadata = null;
    this.currentPageIndex = 0;
    this.loading = false;
    // Mobile portrait: fit-width, Desktop/landscape: fit-height
    this.fitMode =
      window.innerWidth <= 768 && window.innerHeight > window.innerWidth
        ? 'fit-width'
        : 'fit-height';
    this.zoomLevel = 100; // 50-200%
    // Default to spread mode on desktop or landscape orientation
    this.spreadMode = window.innerWidth > 768 || window.innerWidth > window.innerHeight;
    this.isFullscreen = false;
    this.progressSaveTimer = null;
    this.coverPageIndex = 0; // Index of the cover page (default 0)
    this.prefetchCache = new Map(); // Cache for prefetched images
    this.touchStartDistance = 0; // For pinch-to-zoom gesture
    this.initialZoomLevel = 100; // Store initial zoom at gesture start
    this.workerInitialized = false; // Media worker status
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
      console.log('[ComicReader] Media worker initialized');
    } catch (error) {
      console.warn('[ComicReader] Media worker initialization failed:', error);
      this.workerInitialized = false;
    }

    // Setup fullscreen listeners
    this.setupFullscreenListeners();

    // Setup orientation change listener
    this.setupOrientationListener();

    // Setup pinch-to-zoom gesture
    this.setupPinchZoom();

    // Setup swipe gestures for navigation
    this.setupSwipeGestures();

    // Load metadata and initialize UI
    await this.loadMetadata();

    // Load saved progress
    await this.loadProgress();
  }

  /**
   * Load comic metadata including page list
   */
  async loadMetadata() {
    try {
      const response = await APIClient.get(`/api/periodicals/${this.magazineId}/comic/metadata`);
      this.metadata = await response.json();

      // Store cover page index from metadata (defaults to 0)
      this.coverPageIndex = this.metadata.cover_page || 0;

      // Update UI with metadata
      document.getElementById('comic-title').textContent = this.metadata.title || 'Comic Reader';

      // Update spread button to reflect default state
      const spreadBtn = document.getElementById('spread-btn');
      spreadBtn.classList.toggle('active', this.spreadMode);
      spreadBtn.textContent = this.spreadMode ? '📖' : '📄';
      spreadBtn.title = this.spreadMode ? 'Single page mode (S)' : 'Two-page spread mode (S)';

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
      console.error('Failed to load comic metadata:', error);
      this.showError('Failed to load comic metadata: ' + error.message);
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

    pageList.innerHTML = this.metadata.pages
      .map(
        (page, index) => `
        <div 
          class="page-item ${index === this.currentPageIndex ? 'active' : ''}" 
          data-index="${index}"
          onclick="comicReader.loadPage(${index})"
        >
          <img 
            src="/api/periodicals/${this.magazineId}/comic/page/${index}/thumbnail" 
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
      // Only show loading spinner for uncached pages
      contentDiv.innerHTML =
        '<div class="loading"><div style="text-align: center"><div class="spinner"></div></div></div>';
    }

    try {
      // In spread mode: cover page is always single, then pair pages after cover (cover+1 & cover+2, etc.)
      if (
        this.spreadMode &&
        index !== this.coverPageIndex &&
        index < this.metadata.pages.length - 1
      ) {
        // Load two pages side by side
        await this.loadSpreadPages(index);
      } else {
        // Load single page
        await this.loadSinglePage(index);
      }

      // Save progress after page loads
      this.saveProgressDebounced();

      // Prefetch next pages for smoother navigation
      this.prefetchNextPages();
    } catch (error) {
      console.error('Failed to load page:', error);
      contentDiv.innerHTML = `<div class="error">Failed to load page: ${this.escapeHtml(error.message)}</div>`;
      this.loading = false;
    }
  }

  /**
   * Load a single page
   * @param {number} index - Page index
   */
  async loadSinglePage(index) {
    const contentDiv = document.getElementById('page-content');
    const imageUrl = `/api/periodicals/${this.magazineId}/comic/page/${index}`;
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

        // Scroll to top
        contentDiv.scrollTop = 0;

        // Update URL without reload
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
    const imageUrl1 = `/api/periodicals/${this.magazineId}/comic/page/${index}`;
    const imageUrl2 = `/api/periodicals/${this.magazineId}/comic/page/${index + 1}`;

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

          // Apply zoom after images are loaded using CSS transform
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
      // In spread mode, prefetch next 2 spreads (4 pages total for smoother navigation)
      if (this.currentPageIndex === this.coverPageIndex) {
        // After cover, prefetch first content spread
        const firstContent = this.coverPageIndex + 1;
        if (firstContent < this.metadata.pages.length) {
          pagesToPrefetch.push(firstContent);
        }
        if (firstContent + 1 < this.metadata.pages.length) {
          pagesToPrefetch.push(firstContent + 1);
        }
        // Also prefetch next spread
        if (firstContent + 2 < this.metadata.pages.length) {
          pagesToPrefetch.push(firstContent + 2);
        }
        if (firstContent + 3 < this.metadata.pages.length) {
          pagesToPrefetch.push(firstContent + 3);
        }
      } else {
        // Prefetch next 2 spreads (4 pages)
        for (let i = 2; i <= 5; i++) {
          const nextPage = this.currentPageIndex + i;
          if (nextPage < this.metadata.pages.length) {
            pagesToPrefetch.push(nextPage);
          }
        }
      }
    } else {
      // In single page mode, prefetch next 3 pages
      for (let i = 1; i <= 3; i++) {
        const nextPage = this.currentPageIndex + i;
        if (nextPage < this.metadata.pages.length) {
          pagesToPrefetch.push(nextPage);
        }
      }
    }

    // Use batch prefetch if worker available for better performance
    if (this.workerInitialized && pagesToPrefetch.length > 1) {
      const urls = pagesToPrefetch
        .filter((idx) => !this.prefetchCache.has(idx))
        .map((idx) => ({
          url: `/api/periodicals/${this.magazineId}/comic/page/${idx}`,
          priority: Priority.LOW,
          type: 'comic-page',
        }));

      if (urls.length > 0) {
        mediaWorker
          .batchPrefetch(urls)
          .then((result) => {
            if (result.success) {
              result.results.forEach((res, i) => {
                if (res.success) {
                  const pageIndex = pagesToPrefetch[i];
                  console.log(`Batch prefetched page ${pageIndex + 1}`);
                }
              });
            }
          })
          .catch((err) => {
            console.warn('Batch prefetch failed, falling back to individual:', err);
            // Fallback to individual prefetch
            pagesToPrefetch.forEach((pageIndex) => {
              this.prefetchPage(pageIndex);
            });
          });
      }
    } else {
      // Fallback to individual prefetch
      pagesToPrefetch.forEach((pageIndex) => {
        this.prefetchPage(pageIndex);
      });
    }
  }

  /**
   * Prefetch a single page image
   * @param {number} index - Page index to prefetch
   */
  prefetchPage(index) {
    // Skip if already cached
    if (this.prefetchCache.has(index)) return;

    const imageUrl = `/api/periodicals/${this.magazineId}/comic/page/${index}`;

    // Use media worker if available
    if (this.workerInitialized) {
      mediaWorker
        .prefetch(imageUrl, Priority.LOW, 'comic-page')
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
      // Fallback to standard prefetch
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
    // Update sidebar active state
    document.querySelectorAll('.page-item').forEach((item, idx) => {
      item.classList.toggle('active', idx === this.currentPageIndex);
    });

    // Scroll active page into view in sidebar
    const activeItem = document.querySelector('.page-item.active');
    if (activeItem) {
      activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // Update page title display
    document.getElementById('current-page-title').textContent =
      `Page ${this.currentPageIndex + 1} of ${this.metadata.pages.length}`;

    // Update navigation buttons
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');

    prevBtn.disabled = this.currentPageIndex === 0;
    nextBtn.disabled = this.currentPageIndex === this.metadata.pages.length - 1;
  }

  /**
   * Navigate to previous page
   */
  async previousPage() {
    if (this.currentPageIndex > 0) {
      let targetPage;
      if (this.spreadMode) {
        // In spread mode: Navigate by 2 pages, except when going to/from cover
        const firstContentPage = this.coverPageIndex + 1;
        if (this.currentPageIndex === firstContentPage) {
          targetPage = this.coverPageIndex; // Go to cover
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
        // In spread mode: Navigate by 2 pages, except when going from cover
        if (this.currentPageIndex === this.coverPageIndex) {
          targetPage = this.coverPageIndex + 1; // From cover to first content page
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

    // Update container class for both single and spread mode
    const singleContainer = document.querySelector('.page-image-container');
    const spreadContainer = document.querySelector('.page-spread-container');

    if (singleContainer) {
      singleContainer.className = `page-image-container ${mode}`;
    }
    if (spreadContainer) {
      spreadContainer.className = `page-spread-container ${mode}`;
    }

    // Update button states
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
    contentDiv.innerHTML = `<div class="error">${this.escapeHtml(message)}</div>`;

    const pageList = document.getElementById('page-list');
    pageList.innerHTML = `<div class="error">${this.escapeHtml(message)}</div>`;
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

      if (data.progress && data.progress.current_page !== null) {
        // Load the saved page (unless URL specifies a different page)
        const urlParams = new URLSearchParams(window.location.search);
        if (!urlParams.has('page')) {
          await this.loadPage(data.progress.current_page);
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
        current_page: this.currentPageIndex,
        total_pages: this.metadata.pages.length,
      });
      console.log(
        `Progress saved: page ${this.currentPageIndex + 1}/${this.metadata.pages.length}`
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

    // Apply zoom using CSS transform scale for compatibility with fit modes
    const images = document.querySelectorAll('.page-image, .spread-image');
    const scale = this.zoomLevel / 100;
    images.forEach((img) => {
      img.style.transform = `scale(${scale})`;
      img.style.transformOrigin = 'center';
    });

    // Adjust container to accommodate scaled content
    const containers = document.querySelectorAll('.page-image-container, .page-spread-container');
    containers.forEach((container) => {
      if (scale > 1) {
        container.style.overflow = 'auto';
      } else {
        container.style.overflow = '';
      }
    });
  }

  /**
   * Reset zoom to 100%
   */
  resetZoom() {
    this.zoomLevel = 100;
    document.getElementById('zoom-level').textContent = '100%';

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
    btn.classList.toggle('active', this.spreadMode);
    btn.textContent = this.spreadMode ? '📖' : '📄';
    btn.title = this.spreadMode ? 'Single page mode' : 'Two-page spread mode';

    // Reload current page with new mode
    await this.loadPage(this.currentPageIndex);
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
      const enterFullscreen = () => {
        if (docEl.requestFullscreen) {
          return docEl.requestFullscreen();
        } else if (docEl.webkitRequestFullscreen) {
          // Safari/older Chrome
          return docEl.webkitRequestFullscreen();
        } else if (docEl.webkitEnterFullscreen) {
          // iOS Safari (video only)
          return docEl.webkitEnterFullscreen();
        } else if (docEl.mozRequestFullScreen) {
          // Firefox
          return docEl.mozRequestFullScreen();
        } else if (docEl.msRequestFullscreen) {
          // IE/Edge
          return docEl.msRequestFullscreen();
        }
        return null;
      };

      const result = enterFullscreen();

      // iOS fallback: If fullscreen API is not available or fails
      if (!result) {
        console.warn('[ComicReader] Fullscreen API not available, using CSS fallback');
        this.enableFullscreenFallback();
      } else if (result && result.catch) {
        // Handle promise rejection (e.g., on iOS where it might not be supported)
        result.catch((err) => {
          console.warn('[ComicReader] Fullscreen request failed, using CSS fallback:', err);
          this.enableFullscreenFallback();
        });
      }
    } else {
      // Exit fullscreen
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
   * Enable CSS-based fullscreen fallback for browsers that don't support Fullscreen API
   * (particularly iOS Safari/Chrome)
   */
  enableFullscreenFallback() {
    if (this.isFullscreen) {
      // Exit fallback fullscreen
      document.body.classList.remove('fullscreen-fallback');
      this.isFullscreen = false;

      const btn = document.getElementById('fullscreen-btn');
      const sidebar = document.getElementById('sidebar');

      if (btn) {
        btn.classList.remove('active');
        btn.title = 'Fullscreen';
      }

      if (sidebar) {
        sidebar.style.display = 'flex';
      }

      this.cleanupAutoHideToolbar();
    } else {
      // Enter fallback fullscreen
      document.body.classList.add('fullscreen-fallback');
      this.isFullscreen = true;

      const btn = document.getElementById('fullscreen-btn');
      const sidebar = document.getElementById('sidebar');

      if (btn) {
        btn.classList.add('active');
        btn.title = 'Exit fullscreen';
      }

      if (sidebar) {
        sidebar.style.display = 'none';
      }

      this.setupAutoHideToolbar();

      // Scroll to hide browser chrome on iOS
      window.scrollTo(0, 1);
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
   * Setup orientation change listener to auto-adjust spread mode and fit mode
   */
  setupOrientationListener() {
    const handleOrientationChange = async () => {
      const isPortrait = window.innerHeight > window.innerWidth;
      const isMobile = window.innerWidth <= 768;

      // Determine if spread mode should be enabled based on screen dimensions
      const shouldBeSpread = window.innerWidth > 768 || !isPortrait;

      // Determine fit mode: mobile portrait = fit-width, else = fit-height
      const shouldBeFitMode = isMobile && isPortrait ? 'fit-width' : 'fit-height';

      let needsReload = false;

      // Update spread mode if changed
      if (shouldBeSpread !== this.spreadMode) {
        this.spreadMode = shouldBeSpread;
        needsReload = true;

        // Update spread button UI
        const spreadBtn = document.getElementById('spread-btn');
        if (spreadBtn) {
          spreadBtn.classList.toggle('active', this.spreadMode);
          spreadBtn.textContent = this.spreadMode ? '📖' : '📄';
          spreadBtn.title = this.spreadMode ? 'Single page mode (S)' : 'Two-page spread mode (S)';
        }
      }

      // Update fit mode if changed
      if (shouldBeFitMode !== this.fitMode) {
        this.fitMode = shouldBeFitMode;
        needsReload = true;

        // Update fit mode button UI
        document.querySelectorAll('.fit-btn[data-mode]').forEach((btn) => {
          btn.classList.toggle('active', btn.dataset.mode === this.fitMode);
        });
      }

      // Reload current page with new mode if anything changed
      if (needsReload) {
        await this.loadPage(this.currentPageIndex);
      }
    };

    // Listen for orientation changes
    window.addEventListener('orientationchange', handleOrientationChange);

    // Also listen for resize events (covers more cases)
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

        // Apply zoom constraints (50-200%)
        this.zoomLevel = Math.max(50, Math.min(200, newZoom));
        document.getElementById('zoom-level').textContent = `${this.zoomLevel}%`;

        // Apply zoom using CSS transform
        const images = document.querySelectorAll('.page-image, .spread-image');
        const zoomScale = this.zoomLevel / 100;
        images.forEach((img) => {
          img.style.transform = `scale(${zoomScale})`;
          img.style.transformOrigin = 'center';
        });

        // Adjust container to accommodate scaled content
        const containers = document.querySelectorAll(
          '.page-image-container, .page-spread-container'
        );
        containers.forEach((container) => {
          if (zoomScale > 1) {
            container.style.overflow = 'auto';
          } else {
            container.style.overflow = '';
          }
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
      // Only track single-finger swipes (ignore pinch-to-zoom)
      if (e.touches.length === 1) {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
      }
    };

    const handleSwipeMove = (e) => {
      // Only track single-finger swipes
      if (e.touches.length === 1) {
        touchEndX = e.touches[0].clientX;
        touchEndY = e.touches[0].clientY;
      }
    };

    const handleSwipeEnd = () => {
      // Calculate swipe distance and direction
      const deltaX = touchEndX - touchStartX;
      const deltaY = touchEndY - touchStartY;

      // Minimum swipe distance (in pixels)
      const minSwipeDistance = 50;

      // Check if horizontal swipe is greater than vertical (to avoid interfering with scroll)
      if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > minSwipeDistance) {
        if (deltaX > 0) {
          // Swipe right - go to previous page
          this.previousPage();
        } else {
          // Swipe left - go to next page
          this.nextPage();
        }
      }

      // Reset values
      touchStartX = 0;
      touchStartY = 0;
      touchEndX = 0;
      touchEndY = 0;
    };

    contentDiv.addEventListener('touchstart', handleSwipeStart, { passive: true });
    contentDiv.addEventListener('touchmove', handleSwipeMove, { passive: true });
    contentDiv.addEventListener('touchend', handleSwipeEnd);
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
const comicReader = new ComicReader();
window.comicReader = comicReader;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  comicReader.init();
});

// Handle keyboard navigation
document.addEventListener('keydown', (e) => {
  if (e.key === 'ArrowLeft') {
    comicReader.previousPage();
  } else if (e.key === 'ArrowRight') {
    comicReader.nextPage();
  } else if (e.key === '+' || e.key === '=') {
    e.preventDefault();
    comicReader.adjustZoom(10);
  } else if (e.key === '-' || e.key === '_') {
    e.preventDefault();
    comicReader.adjustZoom(-10);
  } else if (e.key === '0') {
    e.preventDefault();
    comicReader.resetZoom();
  } else if (e.key === 'f' || e.key === 'F') {
    e.preventDefault();
    comicReader.toggleFullscreen();
  } else if (e.key === 's' || e.key === 'S') {
    e.preventDefault();
    comicReader.toggleSpreadMode();
  }
});

// Mobile sidebar toggle
window.toggleSidebar = function () {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('mobile-overlay');
  sidebar.classList.toggle('open');
  overlay.classList.toggle('active');
};
