/**
 * Authentication Module
 * Handles token management and authentication state
 */

export class AuthManager {
  /**
   * Get authentication token from localStorage
   */
  static getToken() {
    return localStorage.getItem('auth_token');
  }

  /**
   * Set authentication token in localStorage
   */
  static setToken(token) {
    localStorage.setItem('auth_token', token);
  }

  /**
   * Remove authentication token from localStorage
   */
  static removeToken() {
    localStorage.removeItem('auth_token');
  }

  /**
   * Check if user is authenticated, redirect to login if not
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
   * Logout user by removing token and redirecting to login
   */
  static async logout() {
    const { UIUtils } = await import('./ui-utils.js');
    const confirmed = await UIUtils.confirm('Logout', 'Are you sure you want to logout?');
    if (confirmed) {
      this.removeToken();
      window.location.href = '/login.html';
    }
  }
}

// Expose logout globally for onclick handlers
window.logout = () => AuthManager.logout();
