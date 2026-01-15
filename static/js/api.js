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
    const headers = {
      ...customHeaders,
      Authorization: `Bearer ${token}`,
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
        const errorMessage = errorData.detail ?? errorData.message ?? `HTTP ${response.status}`;
        throw new APIError(
          errorMessage,
          response.status,
          url,
          errorData
        );
      }

      return response;
    } catch (error) {
      if (error instanceof APIError) {
        throw error;
      }

      // Network or other fetch errors
      console.error(`[APIClient] Request failed for ${url}:`, error);
      throw new NetworkError(
        `Failed to connect to ${url}: ${error.message}`,
        url,
        error
      );
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
  static async get(url) {
    return this.authenticatedFetch(url);
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
  static async post(url, data) {
    return this.authenticatedFetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
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
  static async put(url, data) {
    return this.authenticatedFetch(url, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
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
  static async delete(url) {
    return this.authenticatedFetch(url, {
      method: 'DELETE',
    });
  }
}
