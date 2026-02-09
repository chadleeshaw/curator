/**
 * Main Entry Point
 * Initializes the application and coordinates all modules
 */

import { AuthManager } from './core/auth.js?v=1767733177';
import { APIClient, APIHelper } from './core/api.js';
import { UIUtils } from './core/ui-utils.js?v=1767733177';
import { library } from './features/library.js?v=1767733177';
import { tracking } from './features/tracking.js?v=1770583068';
import { downloads } from './features/downloads.js?v=1767733177';
import { ocrQueue } from './features/ocr-queue.js?v=1767733177';
import { settings } from './features/settings.js?v=1767733177';
import { tasks } from './features/tasks.js?v=1767733177';
import { imports } from './features/imports.js?v=1767733177';
import { stacks } from './features/stacks.js?v=1770652571';
import { EventHandlers } from './event-handlers.js?v=1767733177';
import { CSS_CLASSES } from './core/constants.js';

/**
 * Initialize the application
 */
document.addEventListener('DOMContentLoaded', async () => {
  console.log('[Main] Application initializing...');

  // Initialize centralized event delegation system
  EventHandlers.init();

  // Check authentication first
  const isAuthenticated = await AuthManager.checkAuthentication();
  if (!isAuthenticated) {
    return;
  }

  // Initialize theme from localStorage
  UIUtils.initTheme();

  // Initialize tracking manager (loads constants from API)
  await tracking.init();

  // Check if there's a tab in the URL hash
  const hash = window.location.hash.substring(1);
  if (hash && ['library', 'tracking', 'stacks', 'tasks', 'queue', 'settings'].includes(hash)) {
    // Show the tab from the hash
    const tabName = UIUtils.showTab(hash, null);

    // Load data for specific tabs
    if (tabName === 'library') {
      library.loadPeriodicals();
    } else if (tabName === 'tracking') {
      tracking.loadTrackedPeriodicals();
    } else if (tabName === 'stacks') {
      stacks.loadStacks();
    } else if (tabName === 'settings') {
      settings.loadSettings();
      settings.loadSettingsTab();
    } else if (tabName === 'tasks') {
      tasks.loadScheduledTasks();
    } else if (tabName === 'queue') {
      initQueueSwitcher();
      // Set download queue filter to 'all' when navigating to queue tab
      downloads.setFilter('all');
      // Restore last active queue view or default to download
      const lastQueueView = localStorage.getItem('lastQueueView') || 'download';
      showQueueView(lastQueueView);
    }
  } else {
    // Default to library tab
    UIUtils.showTab('library', null);
    library.loadPeriodicals();
  }

  // Load initial data for other tabs
  tracking.loadTrackedPeriodicals();
  settings.loadSettings();

  // Load initial header stats
  updateHeaderStats();

  // Close delete modal when clicking outside of it
  // Track mousedown target to prevent text selection drag from closing modal
  const modal = document.getElementById('delete-modal');
  if (modal) {
    let mouseDownTarget = null;
    modal.addEventListener('mousedown', (event) => {
      mouseDownTarget = event.target;
    });
    modal.addEventListener('click', (event) => {
      if (event.target === modal && mouseDownTarget === modal) {
        library.closeDeleteModal();
      }
      mouseDownTarget = null;
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
    ocrQueue.stopAutoRefresh();

    const tabName = UIUtils.showTab(hash, null);

    // Load data for the tab if needed
    if (tabName === 'library') {
      library.loadPeriodicals();
    } else if (tabName === 'tracking') {
      tracking.loadTrackedPeriodicals();
    } else if (tabName === 'stacks') {
      stacks.loadStacks();
    } else if (tabName === 'settings') {
      settings.loadSettings();
      settings.loadSettingsTab();
    } else if (tabName === 'tasks') {
      tasks.loadScheduledTasks();
    } else if (tabName === 'queue') {
      initQueueSwitcher();
      // Set download queue filter to 'all' when navigating to queue tab
      downloads.setFilter('all');
      // Restore last active queue view or default to download
      const lastQueueView = localStorage.getItem('lastQueueView') || 'download';
      showQueueView(lastQueueView);
    }
  }
});

/**
 * Initialize queue switcher buttons
 */
function initQueueSwitcher() {
  const switchButtons = document.querySelectorAll('.queue-switch-btn');
  switchButtons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const queueType = btn.dataset.queue;
      showQueueView(queueType);
    });
  });
}

/**
 * Show specific queue view and hide others
 */
function showQueueView(queueType) {
  // Save current queue view to localStorage
  localStorage.setItem('lastQueueView', queueType);

  // Update breadcrumb with queue sub-view
  UIUtils.updateBreadcrumb('queue', queueType);

  // Update button active states
  document.querySelectorAll('.queue-switch-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.queue === queueType);
  });

  // Show/hide queue views
  document
    .getElementById('download-queue-view')
    ?.classList.toggle(CSS_CLASSES.HIDDEN, queueType !== 'download');
  document
    .getElementById('ocr-queue-view')
    ?.classList.toggle(CSS_CLASSES.HIDDEN, queueType !== 'ocr');

  // Stop all auto-refresh
  downloads.stopAutoRefresh();
  ocrQueue.stopAutoRefresh();

  // Load data and start refresh for active queue
  if (queueType === 'download') {
    downloads.setFilter('all'); // setFilter internally calls loadDownloadQueue()
    downloads.startAutoRefresh();
  } else if (queueType === 'ocr') {
    ocrQueue.setFilter('all'); // setFilter internally calls loadQueue()
    ocrQueue.startAutoRefresh();
  }

  // Update all badge counts
  updateQueueBadges();
}

/**
 * Update badge counts for all queues
 */
async function updateQueueBadges() {
  try {
    // Get download queue stats (use efficient status endpoint that only counts)
    const downloadData = await APIHelper.executeWithErrorHandling(async () => {
      const downloadResponse = await APIClient.get('/api/downloads/queue/status');
      return await downloadResponse.json();
    }, 'Main');
    const activeDownloads = downloadData.active || 0;
    document.getElementById('download-queue-badge').textContent = activeDownloads;

    // Get OCR queue stats
    const ocrData = await APIHelper.executeWithErrorHandling(async () => {
      const ocrResponse = await APIClient.get('/api/ocr/queue/stats');
      return await ocrResponse.json();
    }, 'Main');
    const activeOcr = (ocrData.pending || 0) + (ocrData.processing || 0);
    document.getElementById('ocr-queue-badge').textContent = activeOcr;
  } catch (error) {
    console.error('[Main] Error updating queue badges:', error);
  }
}

/**
 * Update header stats (periodicals count)
 */
async function updateHeaderStats() {
  try {
    // Get periodicals count from stats endpoint
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.get('/api/periodicals/stats/count');
      return await response.json();
    }, 'Main');
    document.getElementById('header-periodicals-count').textContent = data.total || 0;
  } catch (error) {
    console.error('[Main] Error updating header stats:', error);
  }
}

// Make functions globally available
window.showQueueView = showQueueView;
window.updateQueueBadges = updateQueueBadges;
window.updateHeaderStats = updateHeaderStats;

// Stacks global functions (used by inline onclick handlers in index.html)
window.openCreateStackModal = () => stacks.openCreateStackModal();
window.closeStackCreateModal = () => UIUtils.closeModal('stack-create-modal');
window.closeDeleteStackModal = () => stacks.closeDeleteStackModal();
window.confirmDeleteStack = () => stacks.confirmDeleteStack();
window.closeStackAssignModal = () => UIUtils.closeModal('stack-assign-modal');

// Settings tab switcher
window.showSettingsTab = (tabName, event) => {
  // Remove active class from all settings tab buttons
  const buttons = document.querySelectorAll('.settings-tab-btn');
  buttons.forEach((btn) => btn.classList.remove('active'));

  // Add active class to clicked button
  if (event && event.currentTarget) {
    event.currentTarget.classList.add('active');
  }

  // Hide all settings sub-tabs
  const tabs = document.querySelectorAll('.settings-sub-tab');
  tabs.forEach((tab) => tab.classList.remove('active'));

  // Show the selected settings sub-tab
  const selectedTab = document.getElementById(`settings-${tabName}-tab`);
  if (selectedTab) {
    selectedTab.classList.add('active');
  }

  // Save the current tab to localStorage
  localStorage.setItem('curator-settings-tab', tabName);

  // Update breadcrumb with settings sub-tab
  UIUtils.updateBreadcrumb('settings', tabName);
};

// Restore last active settings tab on page load
window.restoreSettingsTab = () => {
  const savedTab = localStorage.getItem('curator-settings-tab');
  if (savedTab) {
    // Find the button for the saved tab
    const buttons = document.querySelectorAll('.settings-tab-btn');
    buttons.forEach((btn) => {
      const onclick = btn.getAttribute('onclick');
      if (onclick && onclick.includes(`'${savedTab}'`)) {
        btn.click();
      }
    });
  }
};

// Make module instances globally available for inline event handlers
window.ocrQueue = ocrQueue;
window.downloads = downloads;
window.tasks = tasks;

// Global window functions for download queue sort and filter handlers
window.setDownloadSort = function (sort) {
  if (window.downloads) {
    window.downloads.setSort(sort);
  }
};

window.toggleDownloadSortOrder = function () {
  if (window.downloads) {
    window.downloads.toggleSortOrder();
  }
};

window.setDownloadFilter = function (filter) {
  if (window.downloads) {
    window.downloads.setFilter(filter);
  }
};

// Global window functions for OCR queue sort and filter handlers
window.setOCRSort = function (sort) {
  if (window.ocrQueue) {
    window.ocrQueue.setSort(sort);
  }
};

window.toggleOCRSortOrder = function () {
  if (window.ocrQueue) {
    window.ocrQueue.toggleSortOrder();
  }
};

window.setOCRFilter = function (filter) {
  if (window.ocrQueue) {
    window.ocrQueue.setFilter(filter);
  }
};

// Export modules for debugging in console
window.__modules = {
  library,
  tracking,
  downloads,
  ocrQueue,
  settings,
  tasks,
  imports,
  stacks,
  AuthManager,
  UIUtils,
};

console.log('[Main] Modules loaded:', Object.keys(window.__modules));
