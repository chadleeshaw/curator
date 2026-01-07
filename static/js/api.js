/**
 * API Client Module
 * Provides authenticated fetch wrapper for API calls
 */

import { AuthManager } from './auth.js';

export class APIClient {
  /**
   * Fetch wrapper that automatically includes authentication token
   */
  static async authenticatedFetch(url, options = {}) {
    const token = AuthManager.getToken();

    if (!token) {
      // Redirect to login if no token
      window.location.href = '/login.html';
      return null;
    }

    const headers = options.headers || {};
    headers['Authorization'] = `Bearer ${token}`;

    const response = await fetch(url, {
      ...options,
      headers,
    });

    // Handle 401 Unauthorized - token is invalid or expired
    if (response.status === 401) {
      AuthManager.removeToken();
      window.location.href = '/login.html';
      return null;
    }

    return response;
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
    const token = AuthManager.getToken();
    return fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(data),
    });
  }

  /**
   * Convenience method for PUT requests
   */
  static async put(url, data) {
    const token = AuthManager.getToken();
    return fetch(url, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
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
