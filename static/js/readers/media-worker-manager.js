/**
 * Media Worker Manager
 * Main thread interface for the media loading Web Worker
 * Provides async API for prefetching and caching images/media
 */

/* global Worker, URL */

/**
 * Priority levels for media loading (must match worker)
 */
export const Priority = {
  HIGH: 0, // Current page, visible thumbnails
  MEDIUM: 1, // Next/previous pages
  LOW: 2, // Prefetch beyond immediate neighbors
};

/**
 * Manager class for media worker operations
 */
export class MediaWorkerManager {
  constructor() {
    this.worker = null;
    this.messageId = 0;
    this.pendingMessages = new Map();
    this.initialized = false;
    this._objectURLs = new Set();
  }

  /**
   * Initialize the worker
   * @returns {Promise<void>}
   */
  async init() {
    if (this.initialized) return;

    try {
      this.worker = new Worker('/static/js/readers/reader-worker.js');
      this.worker.onmessage = this.handleMessage.bind(this);
      this.worker.onerror = this.handleError.bind(this);
      this.initialized = true;
      const token = localStorage.getItem('auth_token');
      if (token) {
        this.worker.postMessage({ type: 'init', token });
      }
      console.log('[MediaWorker] Initialized successfully');
    } catch (error) {
      console.error('[MediaWorker] Failed to initialize:', error);
      throw error;
    }
  }

  /**
   * Handle messages from worker
   * @param {MessageEvent} event - Worker message event
   */
  handleMessage(event) {
    const { result, id } = event.data;

    if (this.pendingMessages.has(id)) {
      const { resolve } = this.pendingMessages.get(id);
      this.pendingMessages.delete(id);
      resolve(result);
    }
  }

  /**
   * Handle worker errors
   * @param {ErrorEvent} error - Worker error event
   */
  handleError(error) {
    console.error('[MediaWorker] Worker error:', error);
  }

  /**
   * Send message to worker and wait for response
   * @param {string} type - Message type
   * @param {Object} data - Message data
   * @returns {Promise<Object>} Worker response
   */
  sendMessage(type, data = {}) {
    if (!this.initialized) {
      throw new Error('MediaWorker not initialized. Call init() first.');
    }

    return new Promise((resolve, reject) => {
      const id = this.messageId++;
      this.pendingMessages.set(id, { resolve, reject });

      this.worker.postMessage({ type, data, id });

      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.pendingMessages.has(id)) {
          this.pendingMessages.delete(id);
          reject(new Error(`Worker message timeout: ${type}`));
        }
      }, 30000);
    });
  }

  /**
   * Prefetch a single media item
   * @param {string} url - Media URL
   * @param {number} priority - Priority level (default: MEDIUM)
   * @param {string} type - Media type (thumbnail, pdf-page, comic-page)
   * @returns {Promise<Object>} Result
   */
  async prefetch(url, priority = Priority.MEDIUM, type = 'image') {
    try {
      const result = await this.sendMessage('prefetch', { url, priority, type });
      return result;
    } catch (error) {
      console.error(`[MediaWorker] Prefetch failed for ${url}:`, error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Batch prefetch multiple media items
   * @param {Array<{url: string, priority?: number, type?: string}>} urls - URLs to prefetch
   * @returns {Promise<Object>} Results
   */
  async batchPrefetch(urls) {
    try {
      const result = await this.sendMessage('batchPrefetch', { urls });
      return result;
    } catch (error) {
      console.error('[MediaWorker] Batch prefetch failed:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Get cached media (doesn't fetch if not cached)
   * @param {string} url - Media URL
   * @returns {Promise<Object>} Result with blob if cached
   */
  async getCached(url) {
    try {
      const result = await this.sendMessage('getCached', { url });
      return result;
    } catch (error) {
      console.error(`[MediaWorker] Get cached failed for ${url}:`, error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Clear cache (optionally filtered)
   * @param {Object} options - { type?, urlPattern? }
   * @returns {Promise<Object>} Result
   */
  async clearCache(options = {}) {
    try {
      const result = await this.sendMessage('clearCache', options);
      console.log(`[MediaWorker] Cache cleared:`, result);
      return result;
    } catch (error) {
      console.error('[MediaWorker] Clear cache failed:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Get cache statistics
   * @returns {Promise<Object>} Stats
   */
  async getStats() {
    try {
      const result = await this.sendMessage('getStats');
      return result;
    } catch (error) {
      console.error('[MediaWorker] Get stats failed:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Update worker configuration
   * @param {Object} config - { maxCacheSize?, maxCacheSizeMB? }
   * @returns {Promise<Object>} Result
   */
  async updateConfig(config) {
    try {
      const result = await this.sendMessage('updateConfig', config);
      console.log('[MediaWorker] Config updated:', result);
      return result;
    } catch (error) {
      console.error('[MediaWorker] Update config failed:', error);
      return { success: false, error: error.message };
    }
  }

  /**
   * Create object URL from cached blob
   * @param {string} url - Original URL
   * @returns {Promise<string|null>} Object URL or null if not cached
   */
  async getObjectURL(url) {
    const result = await this.getCached(url);
    if (result.cached && result.blob) {
      const objectURL = URL.createObjectURL(result.blob);
      this._objectURLs.add(objectURL);
      return objectURL;
    }
    return null;
  }

  /**
   * Terminate the worker
   */
  terminate() {
    if (this.worker) {
      this.worker.terminate();
      this.worker = null;
      this.initialized = false;
      this.pendingMessages.clear();
      for (const objectURL of this._objectURLs) {
        URL.revokeObjectURL(objectURL);
      }
      this._objectURLs.clear();
      console.log('[MediaWorker] Terminated');
    }
  }
}

// Create and export singleton instance
export const mediaWorker = new MediaWorkerManager();
