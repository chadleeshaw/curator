/**
 * Settings Module
 * Handles application settings and provider configuration
 * 
 * NOTE: This is a working skeleton extracted from script.js settings section
 * Contains core functionality - provider management needs full implementation
 */

import { APIClient } from './api.js';
import { UIUtils } from './ui-utils.js';

export class SettingsManager {
  constructor() {
    this.currentConfig = null;
    this.currentUsername = null;
  }

  /**
   * Load all settings from server
   */
  async loadSettings() {
    try {
      const response = await APIClient.authenticatedFetch('/api/config');
      const data = await response.json();

      this.currentConfig = data;
      this.displaySettings(data);

      // Load user account info
      await this.loadUserAccount();
    } catch (error) {
      console.error('Error loading settings:', error);
    }
  }

  /**
   * Load current user account information
   */
  async loadUserAccount() {
    try {
      const response = await APIClient.authenticatedFetch('/api/auth/user/info');

      if (!response || !response.ok) {
        console.error('[Settings] Failed to load user info, status:', response?.status);
        return;
      }

      const data = await response.json();

      if (data.success) {
        // Store current username for comparison
        this.currentUsername = data.username;

        // Pre-populate username
        const usernameInput = document.getElementById('account-username');
        if (usernameInput) {
          usernameInput.value = data.username;
        }
      }
    } catch (error) {
      console.error('Error loading user account:', error);
    }
  }

  /**
   * Display settings in the UI
   */
  displaySettings(config) {
    // Render search providers
    if (config.config?.search_providers) {
      this.renderSearchProviders(config.config.search_providers);
    }
    
    // Display download client config
    if (config.config?.download_client) {
      this.displayDownloadClient(config.config.download_client);
    }
    
    // Display storage settings
    if (config.config?.storage) {
      this.displayStorageSettings(config.config.storage);
    }
    
    // Display matching settings
    if (config.config?.matching) {
      this.displayMatchingSettings(config.config.matching);
    }
    
    // Display logging settings
    if (config.config?.logging) {
      this.displayLoggingSettings(config.config.logging);
    }
    
    // Display import settings
    if (config.config?.import) {
      this.displayImportSettings(config.config.import);
    }
  }

  /**
   * Render search providers list
   */
  renderSearchProviders(providers) {
    const list = document.getElementById('search-providers-list');
    if (!list) return;
    
    list.innerHTML = '';
    providers.forEach((provider, index) => {
      const div = document.createElement('div');
      div.className = 'provider-block';
      
      div.innerHTML = `
        <h4>${provider.name || 'Provider ' + (index + 1)}</h4>
        <div style="margin: 10px 0;">
          <label style="display: block; margin-bottom: 5px; font-weight: 600; color: var(--text-primary); font-size: 14px;">Name:</label>
          <input type="text" id="search-provider-name-${index}" value="${provider.name || ''}"
                style="width: 100%; padding: 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--input-bg); color: var(--text-primary);">
        </div>
        <div style="margin: 10px 0;">
          <label style="display: block; margin-bottom: 5px; font-weight: 600; color: var(--text-primary); font-size: 14px;">API URL:</label>
          <input type="text" id="search-provider-url-${index}" value="${provider.api_url || ''}"
                style="width: 100%; padding: 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--input-bg); color: var(--text-primary);">
        </div>
        <div style="margin: 10px 0;">
          <label style="display: block; margin-bottom: 5px; font-weight: 600; color: var(--text-primary); font-size: 14px;">API Key:</label>
          <input type="password" id="search-provider-key-${index}" placeholder="${provider.api_key ? '••••••••••••••••' : 'Enter API key'}"
                data-original-key="${provider.api_key || ''}"
                style="width: 100%; padding: 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--input-bg); color: var(--text-primary);">
        </div>
        <div style="margin: 10px 0;">
          <label style="display: flex; align-items: center; gap: 8px;">
            <input type="checkbox" id="search-provider-enabled-${index}" ${provider.enabled ? 'checked' : ''}>
            Enabled
          </label>
        </div>
        <div style="margin-top: 15px; display: flex; gap: 10px;">
          <button onclick="editSearchProvider(${index})" class="btn-primary">Save</button>
          <button onclick="removeSearchProvider(${index})" class="btn-danger">Remove</button>
        </div>
      `;
      
      list.appendChild(div);
    });
  }

  /**
   * Display download client configuration
   */
  displayDownloadClient(clientConfig) {
    const typeSelect = document.getElementById('download-client-type');
    const nameInput = document.getElementById('download-client-name');
    const urlInput = document.getElementById('download-client-url');
    const apiKeyInput = document.getElementById('download-client-apikey');
    
    if (typeSelect) typeSelect.value = clientConfig.type || 'sabnzbd';
    if (nameInput) nameInput.value = clientConfig.name || '';
    if (urlInput) urlInput.value = clientConfig.api_url || '';
    if (apiKeyInput) {
      apiKeyInput.value = '';
      apiKeyInput.setAttribute('data-original-key', clientConfig.api_key || '');
      apiKeyInput.placeholder = clientConfig.api_key ? '••••••••••••••••' : 'Enter API key';
    }
  }

  /**
   * Display storage settings
   */
  displayStorageSettings(storageConfig) {
    const dbPath = document.getElementById('storage-db-path');
    const downloadDir = document.getElementById('storage-download-dir');
    const organizeDir = document.getElementById('storage-organize-dir');
    const cacheDir = document.getElementById('storage-cache-dir');
    
    if (dbPath) dbPath.value = storageConfig.db_path || '';
    if (downloadDir) downloadDir.value = storageConfig.download_dir || '';
    if (organizeDir) organizeDir.value = storageConfig.organize_dir || '';
    if (cacheDir) cacheDir.value = storageConfig.cache_dir || '';
  }

  /**
   * Display matching settings
   */
  displayMatchingSettings(matchingConfig) {
    const threshold = document.getElementById('matching-fuzzy-threshold');
    if (threshold) threshold.value = matchingConfig.fuzzy_threshold || 80;
  }

  /**
   * Display logging settings
   */
  displayLoggingSettings(loggingConfig) {
    const level = document.getElementById('logging-level');
    const logFile = document.getElementById('logging-file');
    
    if (level) level.value = loggingConfig.level || 'INFO';
    if (logFile) logFile.value = loggingConfig.log_file || '';
  }

  /**
   * Display import settings
   */
  displayImportSettings(importConfig) {
    const pattern = document.getElementById('import-organize-pattern');
    if (pattern) pattern.value = importConfig.organization_pattern || 'data/{category}/{title}/{year}/';
  }

  /**
   * Save provider settings
   */
  async saveProviderSettings() {
    try {
      const response = await APIClient.post('/api/config', this.currentConfig);
      const data = await response.json();
      
      if (data.success) {
        UIUtils.showStatus('settings-status', 'Settings saved successfully', 'success');
        setTimeout(() => UIUtils.hideStatus('settings-status'), 3000);
      } else {
        UIUtils.showStatus('settings-status', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving settings:', error);
      UIUtils.showStatus('settings-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Save download client settings
   */
  async saveDownloadClientSettings() {
    const type = document.getElementById('download-client-type')?.value;
    const url = document.getElementById('download-client-url')?.value;
    const apiKeyInput = document.getElementById('download-client-apikey');
    const apiKey = apiKeyInput?.value || apiKeyInput?.getAttribute('data-original-key') || '';
    
    const downloadClientConfig = {
      type,
      api_url: url,
      api_key: apiKey
    };
    
    try {
      const response = await APIClient.post('/api/config', {
        download_client: downloadClientConfig
      });
      const data = await response.json();
      
      if (data.success) {
        UIUtils.showStatus('settings-status', 'Download client settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('settings-status'), 3000);
      } else {
        UIUtils.showStatus('settings-status', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving download client settings:', error);
      UIUtils.showStatus('settings-status', `Error: ${error.message}`, 'error');
    }
  }

  async editSearchProvider(index) {
    try {
      const name = document.getElementById(`search-provider-name-${index}`).value;
      const url = document.getElementById(`search-provider-url-${index}`).value;
      const keyInput = document.getElementById(`search-provider-key-${index}`);
      const key = keyInput.value || keyInput.getAttribute('data-original-key');
      const enabled = document.getElementById(`search-provider-enabled-${index}`).checked;
      
      if (!name || !url || !key) {
        UIUtils.showStatus('settings-status', 'Please fill in all provider fields', 'error');
        return;
      }
      
      // Get current config
      const response = await APIClient.get('/api/config');
      const data = await response.json();
      const config = data.config;
      
      // Update the provider
      config.search_providers[index] = {
        type: config.search_providers[index].type,
        name: name,
        api_url: url,
        api_key: key,
        enabled: enabled
      };
      
      // Save config
      const saveResponse = await APIClient.post('/api/config', { search_providers: config.search_providers });
      const saveData = await saveResponse.json();
      
      if (saveData.success) {
        UIUtils.showStatus('settings-status', 'Search provider updated successfully', 'success');
        setTimeout(() => this.loadSettings(), 1500);
      } else {
        UIUtils.showStatus('settings-status', saveData.message || 'Failed to update provider', 'error');
      }
    } catch (error) {
      console.error('Failed to update search provider:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  async removeSearchProvider(index) {
    const confirmed = await UIUtils.confirm('Remove Provider', 'Are you sure you want to remove this search provider?');
    if (!confirmed) {
      return;
    }

    try {
      // Get current config
      const response = await APIClient.get('/api/config');
      const data = await response.json();
      const config = data.config;

      // Remove provider
      config.search_providers.splice(index, 1);

      // Save config
      const saveResponse = await APIClient.post('/api/config', { search_providers: config.search_providers });
      const saveData = await saveResponse.json();

      if (saveData.success) {
        UIUtils.showStatus('settings-status', 'Search provider removed successfully', 'success');
        setTimeout(() => this.loadSettings(), 1500);
      } else {
        UIUtils.showStatus('settings-status', saveData.message || 'Failed to remove provider', 'error');
      }
    } catch (error) {
      console.error('Failed to remove search provider:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Add new search provider - opens modal
   */
  addSearchProvider() {
    const modal = document.getElementById('add-provider-modal');
    const form = document.getElementById('add-provider-form');
    
    // Reset form
    form.reset();
    
    // Set up form submission
    form.onsubmit = (e) => this.submitAddProvider(e);
    
    // Show modal
    modal.classList.remove('hidden');
  }

  /**
   * Close add provider modal
   */
  closeAddProviderModal() {
    const modal = document.getElementById('add-provider-modal');
    modal.classList.add('hidden');
  }

  /**
   * Submit add provider form
   */
  async submitAddProvider(event) {
    event.preventDefault();
    
    try {
      const type = document.getElementById('new-provider-type').value;
      const name = document.getElementById('new-provider-name').value;
      const apiUrl = document.getElementById('new-provider-url').value;
      const apiKey = document.getElementById('new-provider-key').value;
      const enabled = document.getElementById('new-provider-enabled').checked;

      const newProvider = {
        type,
        name,
        api_url: apiUrl,
        api_key: apiKey,
        enabled
      };

      // Get current config
      const response = await APIClient.get('/api/config');
      const data = await response.json();
      const config = data.config;
      
      // Add new provider
      config.search_providers.push(newProvider);
      
      // Save config
      const saveResponse = await APIClient.post('/api/config', { search_providers: config.search_providers });
      const saveData = await saveResponse.json();
      
      if (saveData.success) {
        UIUtils.showStatus('settings-status', 'Search provider added successfully', 'success');
        this.closeAddProviderModal();
        setTimeout(() => this.loadSettings(), 1500);
      } else {
        UIUtils.showStatus('settings-status', saveData.message || 'Failed to add provider', 'error');
      }
    } catch (error) {
      console.error('Failed to add search provider:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save storage settings
   */
  async saveStorageSettings() {
    try {
      const dbPath = document.getElementById('storage-db-path')?.value;
      const downloadDir = document.getElementById('storage-download-dir')?.value;
      const organizeDir = document.getElementById('storage-organize-dir')?.value;
      const cacheDir = document.getElementById('storage-cache-dir')?.value;
      
      const storageConfig = {
        db_path: dbPath,
        download_dir: downloadDir,
        organize_dir: organizeDir,
        cache_dir: cacheDir
      };
      
      const response = await APIClient.post('/api/config', { storage: storageConfig });
      const data = await response.json();
      
      if (data.success) {
        UIUtils.showStatus('settings-status', 'Storage settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('settings-status'), 3000);
      } else {
        UIUtils.showStatus('settings-status', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving storage settings:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save matching settings
   */
  async saveMatchingSettings() {
    try {
      const threshold = document.getElementById('matching-fuzzy-threshold')?.value;
      
      const matchingConfig = {
        fuzzy_threshold: parseInt(threshold) || 80
      };
      
      const response = await APIClient.post('/api/config', { matching: matchingConfig });
      const data = await response.json();
      
      if (data.success) {
        UIUtils.showStatus('settings-status', 'Matching settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('settings-status'), 3000);
      } else {
        UIUtils.showStatus('settings-status', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving matching settings:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save logging settings
   */
  async saveLoggingSettings() {
    try {
      const level = document.getElementById('logging-level')?.value;
      const logFile = document.getElementById('logging-file')?.value;
      
      const loggingConfig = {
        level: level || 'INFO',
        log_file: logFile
      };
      
      const response = await APIClient.post('/api/config', { logging: loggingConfig });
      const data = await response.json();
      
      if (data.success) {
        UIUtils.showStatus('settings-status', 'Logging settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('settings-status'), 3000);
      } else {
        UIUtils.showStatus('settings-status', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving logging settings:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save theme settings
   */
  async saveThemeSettings() {
    try {
      const mode = document.getElementById('theme-mode')?.value;

      // Apply theme immediately using UIUtils
      UIUtils.setTheme(mode);

      UIUtils.showStatus('settings-status', 'Theme settings saved', 'success');
      setTimeout(() => UIUtils.hideStatus('settings-status'), 3000);
    } catch (error) {
      console.error('Error saving theme settings:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save account settings (username and/or password)
   */
  async saveAccountSettings() {
    try {
      const username = document.getElementById('account-username')?.value.trim();
      const currentPassword = document.getElementById('account-current-password')?.value;
      const newPassword = document.getElementById('account-new-password')?.value;
      const confirmPassword = document.getElementById('account-confirm-password')?.value;

      // Validation
      if (!currentPassword) {
        UIUtils.showStatus('settings-status', 'Current password is required', 'error');
        return;
      }

      // Check if username has actually changed
      const usernameChanged = username && username !== this.currentUsername;

      if (!usernameChanged && !newPassword) {
        UIUtils.showStatus('settings-status', 'No changes to save', 'info');
        return;
      }

      // If changing password, validate new password
      if (newPassword) {
        if (newPassword.length < 6) {
          UIUtils.showStatus('settings-status', 'New password must be at least 6 characters', 'error');
          return;
        }

        if (newPassword !== confirmPassword) {
          UIUtils.showStatus('settings-status', 'New passwords do not match', 'error');
          return;
        }
      }

      const payload = {
        current_password: currentPassword
      };

      // Only include username if it changed
      if (usernameChanged) {
        payload.username = username;
      }

      if (newPassword) {
        payload.new_password = newPassword;
      }

      const response = await APIClient.post('/api/auth/user/update', payload);
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('settings-status', 'Account settings updated successfully', 'success');

        // Update stored username if it changed
        if (usernameChanged) {
          this.currentUsername = username;
        }

        // Clear password fields
        document.getElementById('account-current-password').value = '';
        document.getElementById('account-new-password').value = '';
        document.getElementById('account-confirm-password').value = '';

        setTimeout(() => UIUtils.hideStatus('settings-status'), 3000);
      } else {
        UIUtils.showStatus('settings-status', data.message || 'Error updating account', 'error');
      }
    } catch (error) {
      console.error('Error saving account settings:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Restart the application
   */
  async restartApplication() {
    const modal = document.getElementById('restart-modal');
    modal.classList.remove('hidden');
  }

  /**
   * Close restart modal
   */
  closeRestartModal() {
    const modal = document.getElementById('restart-modal');
    modal.classList.add('hidden');
  }

  /**
   * Confirm and execute the restart
   */
  async confirmRestartApplication() {
    this.closeRestartModal();

    try {
      UIUtils.showStatus('settings-status', 'Restarting application...', 'info');
      
      const response = await APIClient.authenticatedFetch('/api/config/restart', {
        method: 'POST'
      });

      if (response.ok) {
        UIUtils.showStatus('settings-status', 'Application is restarting. Page will reload in a few seconds...', 'success');
        
        // Wait a bit then start polling for server availability
        setTimeout(() => {
          this.waitForServerRestart();
        }, 3000);
      } else {
        throw new Error('Failed to restart application');
      }
    } catch (error) {
      console.error('Error restarting application:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Poll server until it's back online, then reload the page
   */
  async waitForServerRestart() {
    const maxAttempts = 30;
    let attempts = 0;

    const checkServer = async () => {
      try {
        const response = await fetch('/api/config');
        if (response.ok) {
          UIUtils.showStatus('settings-status', 'Application restarted successfully. Reloading...', 'success');
          setTimeout(() => window.location.reload(), 1000);
          return;
        }
      } catch (error) {
        // Server not ready yet
      }

      attempts++;
      if (attempts < maxAttempts) {
        setTimeout(checkServer, 2000);
      } else {
        UIUtils.showStatus('settings-status', 'Restart taking longer than expected. Please refresh manually.', 'warning');
      }
    };

    checkServer();
  }
}

// Create singleton instance
export const settings = new SettingsManager();

// Expose functions globally for onclick handlers
window.saveProviderSettings = () => settings.saveProviderSettings();
window.saveDownloadClientSettings = () => settings.saveDownloadClientSettings();
window.editSearchProvider = (index) => settings.editSearchProvider(index);
window.removeSearchProvider = (index) => settings.removeSearchProvider(index);
window.addSearchProvider = () => settings.addSearchProvider();
window.closeAddProviderModal = () => settings.closeAddProviderModal();
window.saveStorageSettings = () => settings.saveStorageSettings();
window.saveMatchingSettings = () => settings.saveMatchingSettings();
window.saveLoggingSettings = () => settings.saveLoggingSettings();
window.saveThemeSettings = () => settings.saveThemeSettings();
window.saveAccountSettings = () => settings.saveAccountSettings();
window.restartApplication = () => settings.restartApplication();
window.confirmRestartApplication = () => settings.confirmRestartApplication();
window.closeRestartModal = () => settings.closeRestartModal();
