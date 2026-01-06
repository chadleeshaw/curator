/**
 * Main Entry Point
 * Initializes the application and coordinates all modules
 */

import { AuthManager } from './auth.js?v=1767725019';
import { UIUtils } from './ui-utils.js?v=1767725019';
import { library } from './library.js?v=1767725019';
import { tracking } from './tracking.js?v=1767725019';
import { downloads } from './downloads.js?v=1767725019';
import { settings } from './settings.js?v=1767725019';
import { tasks } from './tasks.js?v=1767725019';
import { imports } from './imports.js?v=1767725019';

/**
 * Initialize the application
 */
document.addEventListener('DOMContentLoaded', async () => {
  console.log('[Main] Application initializing...');

  // Check authentication first
  const isAuthenticated = await AuthManager.checkAuthentication();
  if (!isAuthenticated) {
    return;
  }

  // Initialize theme from localStorage
  UIUtils.initTheme();

  // Check if there's a tab in the URL hash
  const hash = window.location.hash.substring(1);
  if (hash && ['library', 'tracking', 'tasks', 'settings'].includes(hash)) {
    // Show the tab from the hash
    const tabName = UIUtils.showTab(hash, null);

    // Load data for specific tabs
    if (tabName === 'library') {
      library.loadPeriodicals();
    } else if (tabName === 'tracking') {
      tracking.loadTrackedPeriodicals();
    } else if (tabName === 'settings') {
      settings.loadSettings();
    } else if (tabName === 'tasks') {
      tasks.loadScheduledTasks();
      downloads.loadDownloadQueue();
      downloads.loadFailedDownloads();
      downloads.startAutoRefresh();
    }
  } else {
    // Default to library tab
    UIUtils.showTab('library', null);
    library.loadPeriodicals();
  }

  // Load initial data for other tabs
  tracking.loadTrackedPeriodicals();
  settings.loadSettings();

  // Close delete modal when clicking outside of it
  const modal = document.getElementById('delete-modal');
  if (modal) {
    modal.addEventListener('click', (event) => {
      if (event.target === modal) {
        library.closeDeleteModal();
      }
    });
  }

  console.log('[Main] Application initialized successfully');
});

// Handle hash changes (when coming from periodical page or navigating)
window.addEventListener('hashchange', () => {
  const hash = window.location.hash.substring(1);
  if (hash) {
    // Stop any running auto-refresh when changing tabs
    downloads.stopAutoRefresh();

    const tabName = UIUtils.showTab(hash, null);

    // Load data for the tab if needed
    if (tabName === 'library') {
      library.loadPeriodicals();
    } else if (tabName === 'tracking') {
      tracking.loadTrackedPeriodicals();
    } else if (tabName === 'settings') {
      settings.loadSettings();
    } else if (tabName === 'tasks') {
      tasks.loadScheduledTasks();
      downloads.loadDownloadQueue();
      downloads.loadFailedDownloads();
    }
  }
});

// Export modules for debugging in console
window.__modules = {
  library,
  tracking,
  downloads,
  settings,
  tasks,
  imports,
  AuthManager,
  UIUtils,
};

console.log('[Main] Modules loaded:', Object.keys(window.__modules));
