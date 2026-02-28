/**
 * Media Worker Module
 * Handles image/media prefetching and caching in a Web Worker for improved performance
 * Supports thumbnails, PDF pages, and comic book pages with prioritized loading
 */

/* global self, DOMException */

/**
 * Cache entry structure
 * @typedef {Object} CacheEntry
 * @property {Blob} blob - The image data
 * @property {string} url - Original URL
 * @property {number} timestamp - When it was cached
 * @property {string} type - Media type (thumbnail, pdf-page, comic-page)
 */

let _authToken = null;

class MediaWorker {
  constructor() {
    this.cache = new Map(); // key -> CacheEntry
    this.loading = new Map(); // key -> Promise
    this.loadQueue = []; // Priority queue for load requests
    this.maxCacheSize = 100; // Max number of cached items
    this.maxCacheSizeMB = 200; // Max cache size in MB
    this.currentCacheSizeMB = 0;
    this.isProcessingQueue = false;
    this.maxConcurrentRequests = 6; // Limit concurrent connections
    this.activeRequests = 0;
    this.pendingQueue = []; // Queue for requests waiting for slots
  }

  /**
   * Generate cache key from URL
   * @param {string} url - The media URL
   * @returns {string} Cache key
   */
  getCacheKey(url) {
    return url;
  }

  /**
   * Estimate blob size in MB
   * @param {Blob} blob - The blob to measure
   * @returns {number} Size in MB
   */
  getBlobSizeMB(blob) {
    return blob.size / (1024 * 1024);
  }

  /**
   * Evict old cache entries to make room for new ones
   * Uses LRU (Least Recently Used) strategy
   */
  evictCache() {
    if (this.cache.size <= this.maxCacheSize && this.currentCacheSizeMB <= this.maxCacheSizeMB) {
      return;
    }

    // Sort by timestamp (oldest first)
    const entries = Array.from(this.cache.entries()).sort(
      (a, b) => a[1].timestamp - b[1].timestamp
    );

    // Remove oldest entries until we're under limits
    while (
      entries.length > 0 &&
      (this.cache.size > this.maxCacheSize * 0.8 ||
        this.currentCacheSizeMB > this.maxCacheSizeMB * 0.8)
    ) {
      const [key, entry] = entries.shift();
      this.currentCacheSizeMB -= this.getBlobSizeMB(entry.blob);
      this.cache.delete(key);
    }
  }

  /**
   * Acquire a connection slot (wait if at max concurrent requests)
   * @returns {Promise<void>}
   */
  async acquireSlot() {
    if (this.activeRequests < this.maxConcurrentRequests) {
      this.activeRequests++;
      return;
    }

    // Wait for a slot to become available
    // Wait for a slot to become available
    return new Promise((resolve, reject) => {
      this.pendingQueue.push({ resolve, reject });
    });

  /**
   * Release a connection slot and process pending queue
   */
    this.activeRequests--;

    // If there are pending requests, give them a slot
    if (this.pendingQueue.length > 0) {
      const { resolve } = this.pendingQueue.shift();
      this.activeRequests++;
      resolve();
    }
  }

  /**
   * Prefetch media with priority
   * @param {Object} data - { url, priority, type }
   * @returns {Promise<Object>} Result object
   */
  async prefetchMedia(data) {
    const { url, type = 'image' } = data;
    const key = this.getCacheKey(url);

    // Check if already cached
    if (this.cache.has(key)) {
      const entry = this.cache.get(key);
      entry.timestamp = Date.now(); // Update access time for LRU
      return { success: true, cached: true, url, type };
    }

    // Check if already loading
    if (this.loading.has(key)) {
      try {
        const result = await this.loading.get(key);
        return result;
      } catch (error) {
        return { success: false, url, error: error.message };
      }
    }

    // Acquire connection slot before fetching
    await this.acquireSlot();

    // Create loading promise
    const loadPromise = this.fetchAndCache(url, type, key);
    this.loading.set(key, loadPromise);

    try {
      const result = await loadPromise;
      return result;
    } finally {
      this.loading.delete(key);
      this.releaseSlot();
    }
  }

  /**
   * Fetch media and add to cache
   * @param {string} url - Media URL
   * @param {string} type - Media type
   * @param {string} key - Cache key
   * @returns {Promise<Object>} Result
   */
  async fetchAndCache(url, type, key) {
    try {
      const response = await fetch(url, {
        headers: _authToken ? { Authorization: `Bearer ${_authToken}` } : {},
      });

      const blob = await response.blob();
      const blobSize = this.getBlobSizeMB(blob);

      // Evict old entries if needed
      this.evictCache();

      // Add to cache
      const entry = {
        blob,
        url,
        timestamp: Date.now(),
        type,
      };

      this.cache.set(key, entry);
      this.currentCacheSizeMB += blobSize;

      return { success: true, url, blob, type };
    } catch (error) {
      return { success: false, url, error: error.message, type };
    }
  }

  /**
   * Batch prefetch multiple media items
   * @param {Object} data - { urls: Array<{url, priority, type}> }
   * @returns {Promise<Object>} Results
   */
  async batchPrefetch(data) {
    const { urls } = data;
    const results = await Promise.allSettled(urls.map((item) => this.prefetchMedia(item)));

    return {
      success: true,
      results: results.map((r, i) => ({
        url: urls[i].url,
        success: r.status === 'fulfilled' && r.value.success,
        cached: r.status === 'fulfilled' ? r.value.cached : false,
        error: r.status === 'rejected' ? r.reason : r.value?.error,
      })),
    };
  }

  /**
   * Get cached media
   * @param {Object} data - { url }
   * @returns {Object} Result with blob if cached
   */
  getCached(data) {
    const { url } = data;
    const key = this.getCacheKey(url);

    if (this.cache.has(key)) {
      const entry = this.cache.get(key);
      entry.timestamp = Date.now(); // Update access time
      return { success: true, cached: true, blob: entry.blob, url };
    }

    return { success: true, cached: false, url };
  }

  /**
   * Clear cache (optionally by type or URL pattern)
   * @param {Object} data - { type?, urlPattern? }
   */
  clearCache(data = {}) {
    const { type, urlPattern } = data;

    if (!type && !urlPattern) {
      // Reject all pending slot-wait promises before clearing
      for (const { reject } of this.pendingQueue) {
        reject(new DOMException('Worker cache cleared', 'AbortError'));
      }
      this.pendingQueue.length = 0;
      // Clear all
      this.cache.clear();
      this.loading.clear();
      this.currentCacheSizeMB = 0;
      return { success: true, cleared: 'all' };
    }

    let cleared = 0;

    // Clear by filter
    for (const [key, entry] of this.cache.entries()) {
      const matchesType = !type || entry.type === type;
      const matchesPattern = !urlPattern || entry.url.includes(urlPattern);

      if (matchesType && matchesPattern) {
        this.currentCacheSizeMB -= this.getBlobSizeMB(entry.blob);
        this.cache.delete(key);
        cleared++;
      }
    }

    return { success: true, cleared };
  }

  /**
   * Get cache statistics
   * @returns {Object} Stats object
   */
  getCacheStats() {
    const typeStats = {};

    for (const entry of this.cache.values()) {
      if (!typeStats[entry.type]) {
        typeStats[entry.type] = 0;
      }
      typeStats[entry.type]++;
    }

    return {
      totalCached: this.cache.size,
      currentlyLoading: this.loading.size,
      cacheSizeMB: Math.round(this.currentCacheSizeMB * 100) / 100,
      maxCacheSizeMB: this.maxCacheSizeMB,
      activeRequests: this.activeRequests,
      pendingRequests: this.pendingQueue.length,
      maxConcurrentRequests: this.maxConcurrentRequests,
      typeStats,
    };
  }

  /**
   * Update cache configuration
   * @param {Object} data - { maxCacheSize?, maxCacheSizeMB?, maxConcurrentRequests? }
   */
  updateConfig(data) {
    if (data.maxCacheSize !== undefined) {
      this.maxCacheSize = data.maxCacheSize;
    }
    if (data.maxCacheSizeMB !== undefined) {
      this.maxCacheSizeMB = data.maxCacheSizeMB;
    }
    if (data.maxConcurrentRequests !== undefined) {
      this.maxConcurrentRequests = data.maxConcurrentRequests;
    }
    this.evictCache(); // Apply new limits
    return {
      success: true,
      config: {
        maxCacheSize: this.maxCacheSize,
        maxCacheSizeMB: this.maxCacheSizeMB,
        maxConcurrentRequests: this.maxConcurrentRequests,
      },
    };
  }
}

const worker = new MediaWorker();

// Handle messages from main thread
self.onmessage = async function (e) {
  const { type, data, id } = e.data;

  try {
    let result;

    switch (type) {
      case 'init':
        _authToken = e.data.token ?? null;
        self.postMessage({ type, result: { success: true }, id });
        return;
      case 'prefetch':
        result = await worker.prefetchMedia(data);
        break;
      case 'batchPrefetch':
        result = await worker.batchPrefetch(data);
        break;
      case 'getCached':
        result = worker.getCached(data);
        break;
      case 'clearCache':
        result = worker.clearCache(data);
        break;
      case 'getStats':
        result = worker.getCacheStats();
        break;
      case 'updateConfig':
        result = worker.updateConfig(data);
        break;
      default:
        result = { success: false, error: `Unknown message type: ${type}` };
    }

    self.postMessage({ type, result, id });
  } catch (error) {
    self.postMessage({ type, result: { success: false, error: error.message }, id });
  }
};
