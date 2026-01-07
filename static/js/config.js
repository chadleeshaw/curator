/**
 * Frontend Configuration
 * Centralized configuration for the frontend application
 */

export const config = {
  // API configuration
  apiBaseUrl: '/api',

  // Polling intervals (milliseconds)
  downloadStatusPollInterval: 5000, // 5 seconds

  // UI refresh intervals (milliseconds)
  libraryRefreshInterval: 30000, // 30 seconds

  // Cache busting version
  assetsVersion: Date.now().toString(),
};
