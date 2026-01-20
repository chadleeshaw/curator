/**
 * Reader Worker Module
 * Handles image prefetching and caching in a Web Worker
 */

/* global self */

class ReaderWorker {
  constructor() {
    this.cache = new Map();
    this.loading = new Set();
  }

  /**
   * Prefetch an image
   * @param {Object} data - { url, index }
   */
  async prefetchImage(data) {
    const { url, index } = data;

    // Skip if already cached or loading
    if (this.cache.has(index) || this.loading.has(index)) {
      return { success: true, cached: true };
    }

    this.loading.add(index);

    try {
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const blob = await response.blob();
      this.cache.set(index, blob);
      this.loading.delete(index);

      return { success: true, index, blob };
    } catch (error) {
      this.loading.delete(index);
      return { success: false, index, error: error.message };
    }
  }

  /**
   * Clear cache
   */
  clearCache() {
    this.cache.clear();
    this.loading.clear();
    return { success: true };
  }

  /**
   * Get cache stats
   */
  getCacheStats() {
    return {
      cached: this.cache.size,
      loading: this.loading.size,
    };
  }
}

const worker = new ReaderWorker();

// Handle messages from main thread
self.onmessage = async function (e) {
  const { type, data } = e.data;

  try {
    let result;

    switch (type) {
      case 'prefetch':
        result = await worker.prefetchImage(data);
        break;
      case 'clearCache':
        result = worker.clearCache();
        break;
      case 'getStats':
        result = worker.getCacheStats();
        break;
      default:
        result = { success: false, error: `Unknown message type: ${type}` };
    }

    self.postMessage({ type, result });
  } catch (error) {
    self.postMessage({ type, result: { success: false, error: error.message } });
  }
};
