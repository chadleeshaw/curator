/**
 * Main Entry Point
 * Initializes the application and coordinates all modules
 */

import { AuthManager } from './auth.js?v=1767733177';
import { UIUtils } from './ui-utils.js?v=1767733177';
import { library } from './library.js?v=1767733177';
import { tracking } from './tracking.js?v=1767733177';
import { downloads } from './downloads.js?v=1767733177';
import { ocrQueue } from './ocr-queue.js?v=1767733177';
import { settings } from './settings.js?v=1767733177';
import { tasks } from './tasks.js?v=1767733177';
import { imports } from './imports.js?v=1767733177';
import { EventHandlers } from './event-handlers.js';
import { CSS_CLASSES } from './constants.js';

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
  if (hash && ['library', 'tracking', 'tasks', 'queue', 'settings'].includes(hash)) {
    // Show the tab from the hash
    const tabName = UIUtils.showTab(hash, null);

    // Load data for specific tabs
    if (tabName === 'library') {
      library.loadPeriodicals();
    } else if (tabName === 'tracking') {
      tracking.loadTrackedPeriodicals();
    } else if (tabName === 'settings') {
      settings.loadSettings();
      settings.loadSettingsTab();
    } else if (tabName === 'tasks') {
      tasks.loadScheduledTasks();
    } else if (tabName === 'queue') {
      initQueueSwitcher();
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
  const modal = document.getElementById('delete-modal');
  if (modal) {
    modal.addEventListener('click', (event) => {
      if (event.target === modal) {
        library.closeDeleteModal();
      }
    });

    // Prevent modal content clicks from propagating to modal background
    const modalContent = modal.querySelector('.modal-content');
    if (modalContent) {
      modalContent.addEventListener('click', (event) => {
        event.stopPropagation();
      });
    }
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
    } else if (tabName === 'settings') {
      settings.loadSettings();
      settings.loadSettingsTab();
    } else if (tabName === 'tasks') {
      tasks.loadScheduledTasks();
    } else if (tabName === 'queue') {
      initQueueSwitcher();
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
    downloads.loadDownloadQueue();
    downloads.startAutoRefresh();
  } else if (queueType === 'ocr') {
    ocrQueue.loadQueue();
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
    // Get download queue stats
    const downloadResponse = await fetch('/api/downloads/queue', {
      headers: { Authorization: `Bearer ${AuthManager.getToken()}` },
    });
    const downloadData = await downloadResponse.json();
    const activeDownloads =
      downloadData.queue?.filter((d) => d.status === 'pending' || d.status === 'downloading')
        .length || 0;
    document.getElementById('download-queue-badge').textContent = activeDownloads;

    // Get OCR queue stats
    const ocrResponse = await fetch('/api/ocr/queue/stats', {
      headers: { Authorization: `Bearer ${AuthManager.getToken()}` },
    });
    const ocrData = await ocrResponse.json();
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
    const response = await fetch('/api/periodicals/stats/count', {
      headers: { Authorization: `Bearer ${AuthManager.getToken()}` },
    });
    const data = await response.json();
    document.getElementById('header-periodicals-count').textContent = data.total || 0;
  } catch (error) {
    console.error('[Main] Error updating header stats:', error);
  }
}

// Make functions globally available
window.showQueueView = showQueueView;
window.updateQueueBadges = updateQueueBadges;
window.updateHeaderStats = updateHeaderStats;

// Make module instances globally available for inline event handlers
window.ocrQueue = ocrQueue;
window.downloads = downloads;

// Export modules for debugging in console
window.__modules = {
  library,
  tracking,
  downloads,
  ocrQueue,
  settings,
  tasks,
  imports,
  AuthManager,
  UIUtils,
};

console.log('[Main] Modules loaded:', Object.keys(window.__modules));
