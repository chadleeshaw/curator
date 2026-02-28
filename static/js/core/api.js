/**
 * API Client Module
 * Provides authenticated fetch wrapper for API calls with comprehensive error handling
 * @module api
 */

import { AuthManager } from './auth.js';
import { APIError, NetworkError, AuthenticationError as _AuthenticationError } from './errors.js';

/**
 * API Client class providing authenticated HTTP methods
 * @class
 */
export class APIClient {
  /**
   * Authenticated fetch wrapper that automatically includes authorization token
   * and provides consistent error handling across all API calls
   *
   * @param {string} url - The API endpoint URL to fetch
   * @param {Object} [options={}] - Fetch options (method, headers, body, etc.)
   * @param {string} [options.method='GET'] - HTTP method
   * @param {Object} [options.headers] - Additional headers to include
   * @param {string|Object} [options.body] - Request body
   * @returns {Promise<Response|null>} The fetch response or null if redirected to login
   * @throws {AuthenticationError} When no token is available or token is invalid
   * @throws {APIError} When the server returns a non-OK response
   * @throws {NetworkError} When the network request fails
   *
   * @example
   * // GET request
   * const response = await APIClient.authenticatedFetch('/api/periodicals');
   * const data = await response.json();
   *
   * @example
   * // POST request with JSON body
   * const response = await APIClient.authenticatedFetch('/api/tracking', {
   *   method: 'POST',
   *   headers: { 'Content-Type': 'application/json' },
   *   body: JSON.stringify({ title: 'Magazine' })
   * });
   */
  static async authenticatedFetch(url, options = {}) {
    const token = AuthManager.getToken();

    if (!token) {
      console.warn(`[APIClient] No auth token available for request to ${url}`);
      window.location.href = '/login.html';
      return null;
    }

    const { headers: customHeaders, ...restOptions } = options;
    const method = (options.method || 'GET').toUpperCase();

    // Attach CSRF token for state-changing requests (double-submit cookie pattern).
    const csrfToken = document.cookie
      .split('; ')
      .find((r) => r.startsWith('csrf_token='))
      ?.split('=')[1];

    const headers = {
      ...customHeaders,
      Authorization: `Bearer ${token}`,
      ...(csrfToken && !['GET', 'HEAD', 'OPTIONS'].includes(method)
        ? { 'X-CSRF-Token': csrfToken }
        : {}),
    };

    try {
      const response = await fetch(url, {
        ...restOptions,
        headers,
      });

      if (response.status === 401) {
        console.warn(`[APIClient] Authentication expired for request to ${url}`);
        AuthManager.removeToken();
        window.location.href = '/login.html';
        return null;
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        let errorMessage = errorData.detail ?? errorData.message ?? `HTTP ${response.status}`;
        // Pydantic 422 errors return detail as an array of validation objects
        if (Array.isArray(errorMessage)) {
          errorMessage = errorMessage.map((e) => e.msg || JSON.stringify(e)).join('; ');
        } else if (typeof errorMessage === 'object') {
          errorMessage = JSON.stringify(errorMessage);
        }
        throw new APIError(errorMessage, response.status, url, errorData);
      }

      return response;
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }

      // AbortError means the request was intentionally cancelled — don't treat as a network error
      if (error.name === 'AbortError') {
        throw error;
      }

      // Network or other fetch errors
      console.error(`[APIClient] Request failed for ${url}:`, error);
      throw new NetworkError(`Failed to connect to ${url}: ${error.message}`, url, error);
    }
  }

  /**
   * Perform a GET request to the specified URL
   *
   * @param {string} url - The API endpoint URL
   * @returns {Promise<Response|null>} The fetch response or null if redirected
   * @throws {APIError} When the server returns a non-OK response
   * @throws {NetworkError} When the network request fails
   *
   * @example
   * const response = await APIClient.get('/api/periodicals?page=1');
   * const { periodicals } = await response.json();
   */
  static async get(url, { signal } = {}) {
    return this.authenticatedFetch(url, { signal });
  }

  /**
   * Perform a POST request with JSON body
   *
   * @param {string} url - The API endpoint URL
   * @param {Object} data - The data to send in the request body
   * @returns {Promise<Response|null>} The fetch response or null if redirected
   * @throws {APIError} When the server returns a non-OK response
   * @throws {NetworkError} When the network request fails
   *
   * @example
   * const response = await APIClient.post('/api/tracking', {
   *   title: 'PC Gamer',
   *   language: 'English'
   * });
   * const result = await response.json();
   */
  static async post(url, data, { signal } = {}) {
    return this.authenticatedFetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
      signal,
    });
  }
  /**
   * Perform a PUT request with JSON body
   *
   * @param {string} url - The API endpoint URL
   * @param {Object} data - The data to send in the request body
   * @returns {Promise<Response|null>} The fetch response or null if redirected
   * @throws {APIError} When the server returns a non-OK response
   * @throws {NetworkError} When the network request fails
   *
   * @example
   * const response = await APIClient.put('/api/tracking/123', {
   *   track_all_editions: true
   * });
   */
  static async put(url, data, { signal } = {}) {
    return this.authenticatedFetch(url, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
      signal,
    });
  }
  /**
   * Perform a DELETE request
   *
   * @param {string} url - The API endpoint URL
   * @returns {Promise<Response|null>} The fetch response or null if redirected
   * @throws {APIError} When the server returns a non-OK response
   * @throws {NetworkError} When the network request fails
   *
   * @example
   * const response = await APIClient.delete('/api/tracking/123');
   * const { success } = await response.json();
   */
  static async delete(url, { signal } = {}) {
    return this.authenticatedFetch(url, {
      method: 'DELETE',
      signal,
    });
  }
}

/**
 * API Helper class for common API operation patterns
 * Provides utilities for executing API calls with standard error handling and UI updates
 * @class
 */
export class APIHelper {
  /**
   * Execute an API call with automatic error handling and optional status display
   *
   * Handles:
   * - Error logging with context
   * - User-friendly error messages
   * - Status element updates
   * - Error re-throwing for caller handling
   *
   * @param {Function} apiCall - Async function that performs the API call and returns data
   * @param {string} errorContext - Context for error messages (e.g., "Library", "Tracking")
   * @param {string|null} [statusElementId=null] - Optional status element ID to update on error
   * @returns {Promise<any>} The API response data
   * @throws {Error} Re-throws any errors after logging
   *
   * @example
   * // Basic usage with error logging only
   * const data = await APIHelper.executeWithErrorHandling(
   *   async () => {
   *     const response = await APIClient.get('/api/periodicals');
   *     return await response.json();
   *   },
   *   'Library'
   * );
   *
   * @example
   * // With status element updates
   * const data = await APIHelper.executeWithErrorHandling(
   *   async () => {
   *     const response = await APIClient.post('/api/tracking', {...});
   *     return await response.json();
   *   },
   *   'Tracking',
   *   'tracking-status'
   * );
   */
  static async executeWithErrorHandling(apiCall, errorContext, statusElementId = null) {
    try {
      return await apiCall();
    } catch (error) {
      console.error(`[${errorContext}] API operation failed:`, error);

      if (statusElementId) {
        // Import UIUtils dynamically to avoid circular dependencies
        const message = error.toUserMessage ? error.toUserMessage() : error.message;
        const statusElement = document.getElementById(statusElementId);
        if (statusElement) {
          statusElement.textContent = message;
          statusElement.className = 'status-message error';
          statusElement.style.display = 'block';
        }
      }

      throw error;
    }
  }

  /**
   * Execute an API call with loading state management
   *
   * Automatically shows/hides loading indicator and handles errors
   *
   * @param {Function} apiCall - Async function that performs the API call
   * @param {string} errorContext - Context for error messages
   * @param {string} loadingElementId - ID of loading indicator element
   * @param {string|null} [statusElementId=null] - Optional status element for error display
   * @returns {Promise<any>} The API response data
   *
   * @example
   * const data = await APIHelper.executeWithLoading(
   *   async () => {
   *     const response = await APIClient.get('/api/periodicals');
   *     return await response.json();
   *   },
   *   'Library',
   *   'loading-indicator',
   *   'library-status'
   * );
   */
  static async executeWithLoading(apiCall, errorContext, loadingElementId, statusElementId = null) {
    const loadingElement = document.getElementById(loadingElementId);

    try {
      if (loadingElement) {
        loadingElement.style.display = 'block';
      }

      return await this.executeWithErrorHandling(apiCall, errorContext, statusElementId);
    } finally {
      if (loadingElement) {
        loadingElement.style.display = 'none';
      }
    }
  }
}
