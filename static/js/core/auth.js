/**
 * Authentication Module
 * Handles token management, authentication state, and user sessions
 * @module auth
 */

/**
 * Authentication Manager class providing static methods for auth operations
 * @class
 */
export class AuthManager {
  /** @private */
  static TOKEN_KEY = 'auth_token';

  /**
   * Get the current authentication token from localStorage
   *
   * @returns {string|null} The stored authentication token or null if not found
   *
   * @example
   * const token = AuthManager.getToken();
   * if (token) {
   *   // User is authenticated
   * }
   */
  static getToken() {
    return localStorage.getItem(this.TOKEN_KEY);
  }

  /**
   * Store an authentication token in localStorage
   *
   * @param {string} token - The JWT token to store
   * @returns {void}
   *
   * @example
   * AuthManager.setToken('eyJhbGciOiJIUzI1NiIs...');
   */
  static setToken(token) {
    localStorage.setItem(this.TOKEN_KEY, token);
  }

  /**
   * Remove the authentication token from localStorage (logout)
   *
   * @returns {void}
   *
   * @example
   * AuthManager.removeToken();
   * // User is now logged out
   */
  static removeToken() {
    localStorage.removeItem(this.TOKEN_KEY);
  }

  /**
   * Check if the user is currently authenticated
   * Redirects to login page if no token is present
   *
   * @returns {Promise<boolean>} True if authenticated, false otherwise
   *
   * @example
   * const isAuth = await AuthManager.checkAuthentication();
   * if (!isAuth) {
   *   // User was redirected to login
   * }
   */
  static async checkAuthentication() {
    const token = this.getToken();

    if (!token) {
      window.location.href = '/login.html';
      return false;
    }

    return true;
  }

  /**
   * Log out the current user with confirmation dialog
   * Removes the token and redirects to the login page
   *
   * @returns {Promise<void>}
   *
   * @example
   * // Called from logout button
   * await AuthManager.logout();
   */
  static async logout() {
    const { UIUtils } = await import('./ui-utils.js');
    const confirmed = await UIUtils.confirm('Logout', 'Are you sure you want to logout?');
    if (confirmed) {
      this.removeToken();
      window.location.href = '/login.html';
    }
  }

  /**
   * Check if a token exists without redirecting
   *
   * @returns {boolean} True if a token exists, false otherwise
   *
   * @example
   * if (AuthManager.hasToken()) {
   *   showAuthenticatedContent();
   * }
   */
  static hasToken() {
    return this.getToken() !== null;
  }
}

// Expose logout globally for onclick handlers
window.logout = () => AuthManager.logout();
