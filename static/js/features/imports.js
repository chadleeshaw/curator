/**
 * Imports Module
 * Handles file import from downloads folder and organized data directory
 */

import { APIClient, APIHelper } from '../core/api.js';
import { UIUtils } from '../core/ui-utils.js';
import { library } from './library.js';
import { CSS_CLASSES } from '../core/constants.js';

export class ImportsManager {
  /**
   * Import files from organized data directory - show modal for options
   */
  async importFromLibraryDir() {
    // Show modal with options
    library.openImportModal();
  }

  /**
   * Save import settings
   */
  async saveImportSettings() {
    const pattern =
      document.getElementById('import-organization-pattern').value || '{category}/{title}/{year}/';
    const enableTextScan = document.getElementById('import-enable-text-scan')?.checked ?? true;
    const enableOcr = document.getElementById('import-enable-ocr')?.checked ?? true;
    const messageDiv = document.getElementById('import-message');

    try {
      await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config', {
            import: {
              organization_pattern: pattern,
              enable_text_scan: enableTextScan,
              enable_ocr: enableOcr,
            },
          });
          return await response.json();
        },
        'Imports',
        'import-message'
      );

      messageDiv.textContent = '✓ Organization pattern saved';
      messageDiv.style.background = '#e8f5e9';
      messageDiv.style.color = '#2e7d32';
      messageDiv.style.borderColor = '#4caf50';
      messageDiv.classList.remove(CSS_CLASSES.HIDDEN);

      setTimeout(() => {
        messageDiv.classList.add(CSS_CLASSES.HIDDEN);
      }, 3000);
    } catch {
      messageDiv.textContent = '✗ Error saving settings';
      messageDiv.style.background = '#ffebee';
      messageDiv.style.color = '#c62828';
      messageDiv.style.borderColor = '#f44336';
      messageDiv.classList.remove(CSS_CLASSES.HIDDEN);
    }
  }

  /**
   * Start import with user-specified options
   */
  async startImportWithOptions() {
    const _category = document.getElementById('import-category').value;
    const autoTrack = document.getElementById('import-auto-track').checked;
    const trackingMode = document.getElementById('import-tracking-mode').value;

    const statusDiv = document.getElementById('import-status');

    // Show importing status
    statusDiv.textContent = '📁 Importing from data directory...';
    statusDiv.style.background = 'var(--surface-variant)';
    statusDiv.style.color = 'var(--text-primary)';
    statusDiv.classList.remove(CSS_CLASSES.HIDDEN);

    // Close modal
    library.closeImportModal();

    try {
      const result = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch('/api/import/from-library-dir', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              auto_track: autoTrack && trackingMode !== 'none',
              tracking_mode: trackingMode,
            }),
          });
          return await response.json();
        },
        'Imports',
        'import-status'
      );

      if (result.success) {
        UIUtils.showStatus('import-status', result.message, 'success');

        // Reload periodicals after a delay
        setTimeout(() => {
          library.loadPeriodicals();
          UIUtils.hideStatus('import-status');
        }, 3000);
      } else {
        UIUtils.showStatus('import-status', result.message || 'Import failed', 'error');
      }
    } catch (error) {
      console.error('Error starting import:', error);
      UIUtils.showStatus('import-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Check status and import downloads
   */
  async checkAndImportDownloads() {
    try {
      // First check status
      const statusData = await APIHelper.executeWithErrorHandling(
        async () => {
          const statusResponse = await APIClient.authenticatedFetch('/api/import/status');
          return await statusResponse.json();
        },
        'Imports',
        'import-status'
      );

      const statusDiv = document.getElementById('import-status');

      if (!statusData.ready) {
        UIUtils.showStatus('import-status', `No files to import. ${statusData.message}`, 'info');
        setTimeout(() => UIUtils.hideStatus('import-status'), 5000);
        return;
      }

      // Show importing status
      statusDiv.style.background = '#e3f2fd';
      statusDiv.style.color = '#1565c0';
      statusDiv.style.borderColor = '#2196f3';
      statusDiv.textContent = `⏳ Importing ${statusData.files} periodicals(s)...`;
      statusDiv.classList.remove(CSS_CLASSES.HIDDEN);

      // Start import
      const result = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch('/api/import/process', {
            method: 'POST',
          });
          return await response.json();
        },
        'Imports',
        'import-status'
      );

      if (result.status === 'processing') {
        UIUtils.showStatus('import-status', result.message, 'success');

        // Reload periodicals after a delay
        setTimeout(() => {
          library.loadPeriodicals();
          UIUtils.hideStatus('import-status');
        }, 3000);
      }
    } catch (error) {
      console.error('Error importing files:', error);
      UIUtils.showStatus('import-status', `Error: ${error.message}`, 'error');
    }
  }
}

// Create singleton instance
export const imports = new ImportsManager();

// Expose functions globally for onclick handlers
window.importFromLibraryDir = () => imports.importFromLibraryDir();
// Note: saveImportSettings is now only in settings.js to avoid naming conflict
window.startImportWithOptions = () => imports.startImportWithOptions();
window.checkAndImportDownloads = () => imports.checkAndImportDownloads();
