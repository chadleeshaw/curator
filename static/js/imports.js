/**
 * Imports Module
 * Handles file import from downloads folder and organized data directory
 */

import { APIClient } from './api.js';
import { UIUtils } from './ui-utils.js';
import { library } from './library.js';

export class ImportsManager {
  /**
   * Import files from organized data directory - show modal for options
   */
  async importFromOrganizeDir() {
    // Show modal with options
    library.openImportModal();
  }

  /**
   * Save import settings
   */
  async saveImportSettings() {
    const pattern = document.getElementById('import-organize-pattern').value || 'data/{category}/{title}/{year}/';
    const messageDiv = document.getElementById('import-message');
    
    try {
      const response = await fetch('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          import: {
            organization_pattern: pattern
          }
        })
      });
      
      const _result = await response.json();
      
      messageDiv.textContent = '✓ Organization pattern saved';
      messageDiv.style.background = '#e8f5e9';
      messageDiv.style.color = '#2e7d32';
      messageDiv.style.borderColor = '#4caf50';
      messageDiv.classList.remove('hidden');
      
      setTimeout(() => {
        messageDiv.classList.add('hidden');
      }, 3000);
    } catch {
      messageDiv.textContent = '✗ Error saving settings';
      messageDiv.style.background = '#ffebee';
      messageDiv.style.color = '#c62828';
      messageDiv.style.borderColor = '#f44336';
      messageDiv.classList.remove('hidden');
    }
  }

  /**
   * Start import with user-specified options
   */
  async startImportWithOptions() {
    const _category = document.getElementById('import-category').value;
    const autoTrack = document.getElementById('import-auto-track').checked;
    const trackingMode = document.getElementById('import-tracking-mode').value;
    const organizationPattern = document.getElementById('import-modal-organize-pattern').value;

    try {
      const statusDiv = document.getElementById('import-status');
      
      // Show importing status
      statusDiv.textContent = '📁 Importing from data directory...';
      statusDiv.style.background = 'var(--surface-variant)';
      statusDiv.style.color = 'var(--text-primary)';
      statusDiv.classList.remove('hidden');
      
      // Close modal
      library.closeImportModal();
      
      // Import from organize directory
      const response = await APIClient.authenticatedFetch('/api/import/from-organize-dir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          auto_track: autoTrack && trackingMode !== 'none',
          tracking_mode: trackingMode,
          organization_pattern: organizationPattern || null,
        }),
      });

      const result = await response.json();

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
      const statusResponse = await APIClient.authenticatedFetch('/api/import/status');
      const statusData = await statusResponse.json();

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
      statusDiv.classList.remove('hidden');

      // Start import
      const response = await APIClient.authenticatedFetch('/api/import/process', {
        method: 'POST',
      });

      const result = await response.json();

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
window.importFromOrganizeDir = () => imports.importFromOrganizeDir();
window.saveImportSettings = () => imports.saveImportSettings();
window.startImportWithOptions = () => imports.startImportWithOptions();
window.checkAndImportDownloads = () => imports.checkAndImportDownloads();
