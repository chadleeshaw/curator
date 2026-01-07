/**
 * API Client Module
 * Provides authenticated fetch wrapper for API calls
 */

import { AuthManager } from './auth.js';

export class APIClient {
  /**
   * Fetch wrapper that automatically includes authentication token and error handling
   */
  static async authenticatedFetch(url, options = {}) {
    const token = AuthManager.getToken();

    if (!token) {
      window.location.href = '/login.html';
      return null;
    }

    const headers = options.headers || {};
    headers['Authorization'] = `Bearer ${token}`;

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      if (response.status === 401) {
        AuthManager.removeToken();
        window.location.href = '/login.html';
        return null;
      }

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}`);
      }

      return response;
    } catch (error) {
      console.error('API request failed:', error);
      throw error;
    }
  }

  /**
   * Convenience method for GET requests
   */
  static async get(url) {
    return this.authenticatedFetch(url);
  }

  /**
   * Convenience method for POST requests
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
   * Convenience method for PUT requests
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
   * Convenience method for DELETE requests
   */
  static async delete(url) {
    return this.authenticatedFetch(url, {
      method: 'DELETE',
    });
  }
}
