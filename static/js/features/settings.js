/**
 * Settings Module
 * Handles application settings and provider configuration
 *
 * NOTE: This is a working skeleton extracted from script.js settings section
 * Contains core functionality - provider management needs full implementation
 */

import { APIClient, APIHelper } from '../core/api.js';
import { UIUtils } from '../core/ui-utils.js';
import {
  ELEMENT_IDS as _ELEMENT_IDS,
  STATUS_MESSAGES as _STATUS_MESSAGES,
  CSS_CLASSES,
  TIMEOUTS,
} from '../core/constants.js';

export class SettingsManager {
  constructor() {
    this.currentConfig = null;
    this.currentUsername = null;
    this.initSortable();
  }

  /**
   * Escape HTML to prevent XSS and attribute issues
   */
  escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  /**
   * Initialize drag-and-drop for sortable lists
   */
  initSortable() {
    // Defer initialization until DOM is ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => this.setupSortable());
    } else {
      this.setupSortable();
    }
  }

  /**
   * Setup sortable functionality for metadata source priority
   */
  setupSortable() {
    const list = document.getElementById('metadata-source-priority-list');
    if (!list) return;

    let draggedElement = null;

    // Add drag event listeners to all sortable items
    const items = list.querySelectorAll('.sortable-item');
    items.forEach((item) => {
      item.addEventListener('dragstart', (e) => {
        draggedElement = item;
        item.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
      });

      item.addEventListener('dragend', () => {
        item.classList.remove('dragging');
        draggedElement = null;
        // Update priority badges after reordering
        this.updatePriorityBadges();
      });

      item.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';

        if (draggedElement && draggedElement !== item) {
          const rect = item.getBoundingClientRect();
          const midpoint = rect.top + rect.height / 2;
          const insertBefore = e.clientY < midpoint;

          if (insertBefore) {
            list.insertBefore(draggedElement, item);
          } else {
            list.insertBefore(draggedElement, item.nextSibling);
          }
        }
      });

      item.addEventListener('dragenter', (e) => {
        e.preventDefault();
        if (draggedElement !== item) {
          item.classList.add('drag-over');
        }
      });

      item.addEventListener('dragleave', () => {
        item.classList.remove('drag-over');
      });

      item.addEventListener('drop', (e) => {
        e.preventDefault();
        item.classList.remove('drag-over');
      });
    });
  }

  /**
   * Update priority badges to reflect current order
   */
  updatePriorityBadges() {
    const list = document.getElementById('metadata-source-priority-list');
    if (!list) return;

    const items = list.querySelectorAll('.sortable-item');
    items.forEach((item, index) => {
      const badge = item.querySelector('.priority-badge');
      if (badge) {
        badge.textContent = `Priority ${index + 1}`;
      }
    });
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
   * Load settings specific to the settings tab being displayed
   */
  async loadSettingsTab() {
    await this.loadAPIToken();
    await this.loadCacheStats();
    // Load categories for reorganize dropdown
    if (window.tasks) {
      await window.tasks.loadCategories();
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
        // Handle case where username might be an object (extract string value)
        let username = data.username;

        // If username is somehow an object, try to extract the actual username
        if (typeof username === 'object' && username !== null) {
          console.warn('Username is an object:', username);
          // Try common property names
          username =
            username.username || username.name || username.value || JSON.stringify(username);
        } else if (typeof username !== 'string') {
          username = String(username || '');
        }

        this.currentUsername = username;

        // Pre-populate username
        const usernameInput = document.getElementById('account-username');
        if (usernameInput) {
          usernameInput.value = username;
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

    // Display metadata settings
    if (config.config?.metadata) {
      this.displayMetadataSettings(config.config.metadata);
    }

    // Display logging settings
    if (config.config?.logging) {
      this.displayLoggingSettings(config.config.logging);
    }

    // Display import settings
    if (config.config?.import) {
      this.displayImportSettings(config.config.import);
    }

    // Display downloads settings
    if (config.config?.downloads) {
      this.displayDownloadsSettings(config.config.downloads);
    }

    // Display tasks settings
    if (config.config?.tasks) {
      this.displayTasksSettings(config.config.tasks);
    }

    // Display PDF settings
    if (config.config?.pdf) {
      this.displayPDFSettings(config.config.pdf);
    }

    // Display OCR settings
    if (config.config?.ocr) {
      this.displayOCRSettings(config.config.ocr);
    }

    // Display cache settings
    if (config.config?.cache) {
      this.displayCacheSettings(config.config.cache);
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
        <h4>${this.escapeHtml(provider.name || 'Provider ' + (index + 1))}</h4>
        <div style="margin: 10px 0;">
          <label style="display: block; margin-bottom: 5px; font-weight: 600; color: var(--text-primary); font-size: 14px;">Name:</label>
          <input type="text" id="search-provider-name-${index}" value="${this.escapeHtml(provider.name || '')}"
                style="width: 100%; padding: 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--input-bg); color: var(--text-primary);">
        </div>
        <div style="margin: 10px 0;">
          <label style="display: block; margin-bottom: 5px; font-weight: 600; color: var(--text-primary); font-size: 14px;">API URL:</label>
          <input type="text" id="search-provider-url-${index}" value="${this.escapeHtml(provider.api_url || '')}"
                style="width: 100%; padding: 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--input-bg); color: var(--text-primary);">
        </div>
        <div style="margin: 10px 0;">
          <label style="display: block; margin-bottom: 5px; font-weight: 600; color: var(--text-primary); font-size: 14px;">API Key:</label>
          <input type="password" id="search-provider-key-${index}" placeholder="${provider.api_key ? '••••••••••••••••' : 'Enter API key'}"
                data-original-key="${this.escapeHtml(provider.api_key || '')}"
                style="width: 100%; padding: 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--input-bg); color: var(--text-primary);">
        </div>
        <div style="margin: 10px 0;">
          <label style="display: block; margin-bottom: 5px; font-weight: 600; color: var(--text-primary); font-size: 14px;">
            Categories <span style="font-weight: 400; color: var(--text-secondary); font-size: 12px;">(Newsnab only, comma-separated, e.g., 7000,7010,7030)</span>:
          </label>
          <input type="text" id="search-provider-categories-${index}" value="${this.escapeHtml(provider.categories || '')}"
                placeholder="7000,7010,7020,7030"
                style="width: 100%; padding: 8px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--input-bg); color: var(--text-primary);">
        </div>
        <div style="margin: 10px 0;">
          <label style="display: flex; align-items: center; gap: 8px;">
            <input type="checkbox" id="search-provider-enabled-${index}" ${provider.enabled ? 'checked' : ''}>
            Enabled
          </label>
        </div>
        <div style="margin-top: 15px; display: flex; gap: 10px;">
          <button onclick="testProviderConnection(${index})" class="btn-secondary">Test Connection</button>
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
    const libraryDir = document.getElementById('storage-library-dir');
    const cacheDir = document.getElementById('storage-cache-dir');

    if (dbPath) dbPath.value = storageConfig.db_path || '';
    if (downloadDir) downloadDir.value = storageConfig.download_dir || '';
    if (libraryDir) libraryDir.value = storageConfig.library_dir || '';
    if (cacheDir) cacheDir.value = storageConfig.cache_dir || '';
  }

  /**
   * Display matching settings
   */
  displayMatchingSettings(matchingConfig) {
    const threshold = document.getElementById('matching-fuzzy-threshold');
    const duplicateThreshold = document.getElementById('matching-duplicate-threshold');

    if (threshold) threshold.value = matchingConfig.fuzzy_threshold || 80;
    if (duplicateThreshold) {
      duplicateThreshold.value = matchingConfig.duplicate_date_threshold_days || 5;
    }
  }

  /**
   * Display metadata aggregation settings
   */
  displayMetadataSettings(metadataConfig) {
    // Confidence thresholds
    const ocrConfidence = document.getElementById('metadata-confidence-ocr');
    const textScanConfidence = document.getElementById('metadata-confidence-text-scan');
    const filenameConfidence = document.getElementById('metadata-confidence-filename');

    if (ocrConfidence) {
      ocrConfidence.value = metadataConfig.confidence_thresholds?.ocr || 70;
    }
    if (textScanConfidence) {
      textScanConfidence.value = metadataConfig.confidence_thresholds?.text_scan || 50;
    }
    if (filenameConfidence) {
      filenameConfidence.value = metadataConfig.confidence_thresholds?.filename || 0;
    }

    // Field overrides
    const yearField = document.getElementById('metadata-field-year');
    const monthField = document.getElementById('metadata-field-month');
    const issueNumberField = document.getElementById('metadata-field-issue-number');
    const volumeField = document.getElementById('metadata-field-volume');

    if (yearField) {
      yearField.value = metadataConfig.field_overrides?.year?.ocr || 80;
    }
    if (monthField) {
      monthField.value = metadataConfig.field_overrides?.month?.ocr || 60;
    }
    if (issueNumberField) {
      issueNumberField.value = metadataConfig.field_overrides?.issue_number?.ocr || 75;
    }
    if (volumeField) {
      volumeField.value = metadataConfig.field_overrides?.volume?.ocr || 75;
    }

    // Source priority - reorder list items based on config
    if (metadataConfig.source_priority) {
      this.reorderSourcePriority(metadataConfig.source_priority);
    }
  }

  /**
   * Reorder source priority list based on config array
   */
  reorderSourcePriority(priorityArray) {
    const list = document.getElementById('metadata-source-priority-list');
    if (!list) return;

    // Get all items as a map
    const items = Array.from(list.querySelectorAll('.sortable-item'));
    const itemMap = {};
    items.forEach((item) => {
      const value = item.getAttribute('data-value');
      itemMap[value] = item;
    });

    // Clear the list
    list.innerHTML = '';

    // Re-add items in priority order
    priorityArray.forEach((source) => {
      if (itemMap[source]) {
        list.appendChild(itemMap[source]);
      }
    });

    // Update priority badges
    this.updatePriorityBadges();
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
    const patternSelect = document.getElementById('import-organization-pattern-select');
    const patternCustom = document.getElementById('import-organization-pattern-custom');
    const enableTextScan = document.getElementById('import-enable-text-scan');
    const enableOcr = document.getElementById('import-enable-ocr');
    const autoCleanupDownloads = document.getElementById('import-auto-cleanup-downloads');
    const autoCleanupLibrary = document.getElementById('import-auto-cleanup-library');

    // Map of pattern templates to their keys
    const patternMap = {
      '{category}/{title}/{year}/': 'default',
      '{category}/{title}/{year}/': 'default',
      '{category}/{title}/Vol{volume}/': 'volume',
      '{category}/{title}/': 'flat',
      '{category}/{title}/Vol{volume}/{year}/': 'volume_year',
      '{category}/{title}/Issues {issue_range}/': 'issue',
    };

    const configPattern = importConfig.organization_pattern || '{category}/{title}/{year}/';
    const matchedKey = patternMap[configPattern];

    if (patternSelect) {
      if (matchedKey) {
        // Known pattern - select it from dropdown
        patternSelect.value = matchedKey;
        if (patternCustom) patternCustom.classList.add('hidden');
      } else {
        // Custom pattern - show custom input
        patternSelect.value = 'custom';
        if (patternCustom) {
          patternCustom.value = configPattern;
          patternCustom.classList.remove('hidden');
        }
      }
    }

    if (enableTextScan) enableTextScan.checked = importConfig.enable_text_scan ?? true;
    if (enableOcr) enableOcr.checked = importConfig.enable_ocr ?? true;

    // Auto-cleanup settings
    const autoCleanupConfig = importConfig.auto_cleanup || {};
    if (autoCleanupDownloads) {
      autoCleanupDownloads.checked = autoCleanupConfig.enable_downloads ?? true;
    }
    if (autoCleanupLibrary) {
      autoCleanupLibrary.checked = autoCleanupConfig.enable_library ?? true;
    }
  }

  /**
   * Display download settings
   */
  displayDownloadsSettings(downloadsConfig) {
    const maxRetries = document.getElementById('downloads-max-retries');
    const maxConcurrent = document.getElementById('downloads-max-concurrent');

    if (maxRetries) maxRetries.value = downloadsConfig.max_retries || 1;
    if (maxConcurrent) maxConcurrent.value = downloadsConfig.max_concurrent || 10;
  }

  /**
   * Display tasks settings
   */
  displayTasksSettings(tasksConfig) {
    const autoDownloadInterval = document.getElementById('tasks-auto-download-interval');
    const downloadMonitorInterval = document.getElementById('tasks-download-monitor-interval');
    const cleanupCoversInterval = document.getElementById('tasks-cleanup-covers-interval');
    const ocrProcessorInterval = document.getElementById('tasks-ocr-processor-interval');
    const maxPeriodicalsPerSearch = document.getElementById('tasks-max-periodicals-per-search');
    const rapidSearchInterval = document.getElementById('tasks-rapid-search-interval');
    const normalSearchInterval = document.getElementById('tasks-normal-search-interval');
    const slowSearchInterval = document.getElementById('tasks-slow-search-interval');
    const verySlowSearchInterval = document.getElementById('tasks-very-slow-search-interval');
    const ocrWorkerCount = document.getElementById('ocr-worker-count');
    const ocrBatchSize = document.getElementById('ocr-batch-size');

    if (autoDownloadInterval)
      autoDownloadInterval.value = tasksConfig.auto_download_interval || 1800;
    if (downloadMonitorInterval)
      downloadMonitorInterval.value = tasksConfig.download_monitor_interval || 30;
    if (cleanupCoversInterval)
      cleanupCoversInterval.value = tasksConfig.cleanup_covers_interval || 86400;
    if (ocrProcessorInterval) ocrProcessorInterval.value = tasksConfig.ocr_processor_interval || 10;
    if (maxPeriodicalsPerSearch)
      maxPeriodicalsPerSearch.value = tasksConfig.max_periodicals_per_search || 2;
    if (rapidSearchInterval) rapidSearchInterval.value = tasksConfig.rapid_search_interval || 1;
    if (normalSearchInterval) normalSearchInterval.value = tasksConfig.normal_search_interval || 6;
    if (slowSearchInterval) slowSearchInterval.value = tasksConfig.slow_search_interval || 24;
    if (verySlowSearchInterval)
      verySlowSearchInterval.value = tasksConfig.very_slow_search_interval || 168;
    if (ocrWorkerCount) ocrWorkerCount.value = tasksConfig.ocr_max_workers || 1;
    if (ocrBatchSize) ocrBatchSize.value = tasksConfig.ocr_batch_size || 5;
  }

  /**
   * Display PDF settings
   */
  displayPDFSettings(pdfConfig) {
    const coverDpiLow = document.getElementById('pdf-cover-dpi-low');
    const coverDpiHigh = document.getElementById('pdf-cover-dpi-high');
    const coverQualityLow = document.getElementById('pdf-cover-quality-low');
    const coverQualityHigh = document.getElementById('pdf-cover-quality-high');

    if (coverDpiLow) coverDpiLow.value = pdfConfig.cover_dpi_low || 60;
    if (coverDpiHigh) coverDpiHigh.value = pdfConfig.cover_dpi_high || 200;
    if (coverQualityLow) coverQualityLow.value = pdfConfig.cover_quality_low || 50;
    if (coverQualityHigh) coverQualityHigh.value = pdfConfig.cover_quality_high || 85;
  }

  /**
   * Display OCR settings
   */
  displayOCRSettings(ocrConfig) {
    const resizeWidth = document.getElementById('ocr-resize-width');
    const contrastEnhance = document.getElementById('ocr-contrast-enhance');
    const denoiseH = document.getElementById('ocr-denoise-h');
    const sharpenKernel = document.getElementById('ocr-sharpen-kernel');

    if (resizeWidth) resizeWidth.value = ocrConfig.resize_width || 1200;
    if (contrastEnhance) contrastEnhance.value = ocrConfig.contrast_enhance || 1.5;
    if (denoiseH) denoiseH.value = ocrConfig.denoise_h || 10;
    if (sharpenKernel) sharpenKernel.value = ocrConfig.sharpen_kernel || 5;
  }

  /**
   * Save provider settings
   */
  async saveProviderSettings() {
    try {
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config', this.currentConfig);
          return await response.json();
        },
        'Settings',
        'settings-status'
      );

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
    const apiKey = apiKeyInput?.value; // Only use the actual input value

    const downloadClientConfig = {
      type,
      api_url: url,
    };

    // Only include api_key if user entered a new one
    if (apiKey) {
      downloadClientConfig.api_key = apiKey;
    } else if (this.currentConfig?.config?.download_client?.api_key) {
      // Preserve existing key from cached config
      downloadClientConfig.api_key = this.currentConfig.config.download_client.api_key;
    }

    try {
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config', {
            download_client: downloadClientConfig,
          });
          return await response.json();
        },
        'Settings',
        'settings-status'
      );

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

  /**
   * Test connection to download client
   */
  async testDownloadClientConnection() {
    try {
      const type = document.getElementById('download-client-type')?.value;
      const url = document.getElementById('download-client-url')?.value;
      const apiKeyInput = document.getElementById('download-client-apikey');
      const apiKey = apiKeyInput?.value || apiKeyInput?.dataset.originalKey;

      if (!url) {
        UIUtils.showStatus('settings-status', 'Please enter an API URL', 'error');
        return;
      }

      if (!apiKey) {
        UIUtils.showStatus('settings-status', 'Please enter an API key', 'error');
        return;
      }

      // Show testing status
      UIUtils.showStatus('settings-status', `Testing connection to ${type}...`, 'info');

      // Build the test payload
      const testPayload = {
        type,
        api_url: url,
        api_key: apiKey,
      };

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config/test-download-client', testPayload);
          return await response.json();
        },
        'Settings',
        'settings-status'
      );

      if (data.success) {
        const versionInfo = data.version ? ` (v${data.version})` : '';
        UIUtils.showStatus('settings-status', `Connection successful!${versionInfo}`, 'success');
        setTimeout(() => UIUtils.hideStatus('settings-status'), 5000);
      } else {
        UIUtils.showStatus('settings-status', data.message || 'Connection test failed', 'error');
      }
    } catch (error) {
      console.error('Failed to test download client connection:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Test connection to a search provider
   */
  async testProviderConnection(index) {
    try {
      const name = document.getElementById(`search-provider-name-${index}`).value;
      const url = document.getElementById(`search-provider-url-${index}`).value;
      const keyInput = document.getElementById(`search-provider-key-${index}`);
      const key = keyInput.value || keyInput.dataset.originalKey;

      if (!url) {
        UIUtils.showStatus('settings-status', 'Please enter an API URL', 'error');
        return;
      }

      if (!key) {
        UIUtils.showStatus('settings-status', 'Please enter an API key', 'error');
        return;
      }

      // Show testing status
      UIUtils.showStatus(
        'settings-status',
        `Testing connection to ${name || 'provider'}...`,
        'info'
      );

      // Build the test payload
      const testPayload = {
        type: 'newsnab', // Currently only newsnab is supported
        api_url: url,
        api_key: key,
      };

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config/test-provider', testPayload);
          return await response.json();
        },
        'Settings',
        'settings-status'
      );

      if (data.success) {
        const serverInfo = data.server_info
          ? ` (${data.server_info.title || 'Unknown'} v${data.server_info.version || 'Unknown'})`
          : '';
        UIUtils.showStatus('settings-status', `Connection successful!${serverInfo}`, 'success');
        setTimeout(() => UIUtils.hideStatus('settings-status'), 5000);
      } else {
        UIUtils.showStatus('settings-status', data.message || 'Connection test failed', 'error');
      }
    } catch (error) {
      console.error('Failed to test provider connection:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  async editSearchProvider(index) {
    try {
      const name = document.getElementById(`search-provider-name-${index}`).value;
      const url = document.getElementById(`search-provider-url-${index}`).value;
      const keyInput = document.getElementById(`search-provider-key-${index}`);
      const key = keyInput.value; // Only use the actual input value, not data-original-key
      const categories = document.getElementById(`search-provider-categories-${index}`).value;
      const enabled = document.getElementById(`search-provider-enabled-${index}`).checked;

      if (!name || !url) {
        UIUtils.showStatus('settings-status', 'Please fill in provider name and URL', 'error');
        return;
      }

      // Build the provider update - only include api_key if it was actually entered
      const providerUpdate = {
        type: this.currentConfig.config.search_providers[index].type,
        name: name,
        api_url: url,
        enabled: enabled,
      };

      // Add categories if provided (optional field)
      if (categories) {
        providerUpdate.categories = categories;
      }

      // Only include api_key if user entered a new one
      if (key) {
        providerUpdate.api_key = key;
      } else {
        // If no new key entered, preserve the existing one from our cached config
        providerUpdate.api_key = this.currentConfig.config.search_providers[index].api_key;
      }

      // Clone the current providers array and update the specific provider
      const updatedProviders = JSON.parse(
        JSON.stringify(this.currentConfig.config.search_providers)
      );
      updatedProviders[index] = providerUpdate;

      // Save config
      const saveData = await APIHelper.executeWithErrorHandling(
        async () => {
          const saveResponse = await APIClient.post('/api/config', {
            search_providers: updatedProviders,
          });
          return await saveResponse.json();
        },
        'Settings',
        'settings-status'
      );

      if (saveData.success) {
        UIUtils.showStatus('settings-status', 'Search provider updated successfully', 'success');
        setTimeout(() => this.loadSettings(), 1500);
      } else {
        UIUtils.showStatus(
          'settings-status',
          saveData.message || 'Failed to update provider',
          'error'
        );
      }
    } catch (error) {
      console.error('Failed to update search provider:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }
  }

  async removeSearchProvider(index) {
    const confirmed = await UIUtils.confirm(
      'Remove Provider',
      'Are you sure you want to remove this search provider?'
    );
    if (!confirmed) {
      return;
    }

    try {
      // Clone the current providers array and remove the provider
      const updatedProviders = JSON.parse(
        JSON.stringify(this.currentConfig.config.search_providers)
      );
      updatedProviders.splice(index, 1);

      // Save config
      const saveData = await APIHelper.executeWithErrorHandling(
        async () => {
          const saveResponse = await APIClient.post('/api/config', {
            search_providers: updatedProviders,
          });
          return await saveResponse.json();
        },
        'Settings',
        'settings-status'
      );

      if (saveData.success) {
        UIUtils.showStatus('settings-status', 'Search provider removed successfully', 'success');
        setTimeout(() => this.loadSettings(), 1500);
      } else {
        UIUtils.showStatus(
          'settings-status',
          saveData.message || 'Failed to remove provider',
          'error'
        );
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

    // Remove any existing submit handlers
    const newForm = form.cloneNode(true);
    form.parentNode.replaceChild(newForm, form);

    // Set up form submission with proper binding
    newForm.addEventListener('submit', (e) => {
      e.preventDefault();
      this.submitAddProvider(e);
      return false;
    });

    // Show modal
    modal.classList.remove(CSS_CLASSES.HIDDEN);
  }

  /**
   * Close add provider modal
   */
  closeAddProviderModal() {
    const modal = document.getElementById('add-provider-modal');
    modal.classList.add(CSS_CLASSES.HIDDEN);
  }

  /**
   * Submit add provider form
   */
  async submitAddProvider(event) {
    if (event) {
      event.preventDefault();
    }

    try {
      const type = document.getElementById('new-provider-type').value;
      const name = document.getElementById('new-provider-name').value;
      const apiUrl = document.getElementById('new-provider-url').value;
      const apiKey = document.getElementById('new-provider-key').value;
      const categories = document.getElementById('new-provider-categories').value;
      const enabled = document.getElementById('new-provider-enabled').checked;

      const newProvider = {
        type,
        name,
        api_url: apiUrl,
        api_key: apiKey,
        enabled,
      };

      // Add categories if provided (optional field)
      if (categories) {
        newProvider.categories = categories;
      }

      // Clone current providers array and add new provider
      const updatedProviders = JSON.parse(
        JSON.stringify(this.currentConfig.config.search_providers)
      );
      updatedProviders.push(newProvider);

      // Save config
      const saveData = await APIHelper.executeWithErrorHandling(
        async () => {
          const saveResponse = await APIClient.post('/api/config', {
            search_providers: updatedProviders,
          });
          return await saveResponse.json();
        },
        'Settings',
        'settings-status'
      );

      if (saveData.success) {
        UIUtils.showStatus('settings-status', 'Search provider added successfully', 'success');
        this.closeAddProviderModal();
        // Reload settings after a short delay
        setTimeout(() => this.loadSettings(), 500);
      } else {
        UIUtils.showStatus(
          'settings-status',
          saveData.message || 'Failed to add provider',
          'error'
        );
      }
    } catch (error) {
      console.error('Failed to add search provider:', error);
      UIUtils.showStatus('settings-status', 'Error: ' + error.message, 'error');
    }

    return false;
  }

  /**
   * Save storage settings
   */
  async saveStorageSettings() {
    try {
      const dbPath = document.getElementById('storage-db-path')?.value;
      const downloadDir = document.getElementById('storage-download-dir')?.value;
      const libraryDir = document.getElementById('storage-library-dir')?.value;
      const cacheDir = document.getElementById('storage-cache-dir')?.value;

      const storageConfig = {
        db_path: dbPath,
        download_dir: downloadDir,
        library_dir: libraryDir,
        cache_dir: cacheDir,
      };

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config', { storage: storageConfig });
          return await response.json();
        },
        'Settings',
        'settings-status'
      );

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
      const duplicateThreshold = document.getElementById('matching-duplicate-threshold')?.value;

      const matchingConfig = {
        fuzzy_threshold: parseInt(threshold) || 80,
        duplicate_date_threshold_days: parseInt(duplicateThreshold) || 5,
      };

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config', { matching: matchingConfig });
          return await response.json();
        },
        'Settings',
        'matching-message'
      );

      if (data.success) {
        UIUtils.showStatus('matching-message', 'Matching settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('matching-message'), 3000);
      } else {
        UIUtils.showStatus('matching-message', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving matching settings:', error);
      UIUtils.showStatus('matching-message', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save metadata aggregation settings
   */
  async saveMetadataSettings() {
    try {
      const ocrConfidence = document.getElementById('metadata-confidence-ocr')?.value;
      const textScanConfidence = document.getElementById('metadata-confidence-text-scan')?.value;
      const filenameConfidence = document.getElementById('metadata-confidence-filename')?.value;

      const yearField = document.getElementById('metadata-field-year')?.value;
      const monthField = document.getElementById('metadata-field-month')?.value;
      const issueNumberField = document.getElementById('metadata-field-issue-number')?.value;
      const volumeField = document.getElementById('metadata-field-volume')?.value;

      // Get source priority from sortable list
      const sourcePriority = this.getSourcePriorityOrder();

      const metadataConfig = {
        source_priority: sourcePriority,
        confidence_thresholds: {
          ocr: parseInt(ocrConfidence) || 70,
          text_scan: parseInt(textScanConfidence) || 50,
          filename: parseInt(filenameConfidence) || 0,
        },
        field_overrides: {
          year: { ocr: parseInt(yearField) || 80 },
          month: { ocr: parseInt(monthField) || 60 },
          issue_number: { ocr: parseInt(issueNumberField) || 75 },
          volume: { ocr: parseInt(volumeField) || 75 },
        },
      };

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config/save', { metadata: metadataConfig });
          return await response.json();
        },
        'Settings',
        'metadata-message'
      );

      if (data.success) {
        await this.loadSettings();
        UIUtils.showStatus('metadata-message', 'Metadata settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('metadata-message'), 3000);
      } else {
        UIUtils.showStatus('metadata-message', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving metadata settings:', error);
      UIUtils.showStatus('metadata-message', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Get current source priority order from sortable list
   */
  getSourcePriorityOrder() {
    const list = document.getElementById('metadata-source-priority-list');
    if (!list) {
      return ['ocr', 'text_scan', 'filename']; // Default order
    }

    const items = list.querySelectorAll('.sortable-item');
    return Array.from(items).map((item) => item.getAttribute('data-value'));
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
        log_file: logFile,
      };

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config/save', { logging: loggingConfig });
          return await response.json();
        },
        'Settings',
        'settings-status'
      );

      if (data.success) {
        await this.loadSettings();
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
   * Save import settings (enable_text_scan, enable_ocr, auto_cleanup)
   */
  async saveImportSettings() {
    try {
      // Get pattern from dropdown or custom input
      const patternSelect = document.getElementById('import-organization-pattern-select');
      const patternCustom = document.getElementById('import-organization-pattern-custom');
      const enableTextScan = document.getElementById('import-enable-text-scan')?.checked;
      const enableOcr = document.getElementById('import-enable-ocr')?.checked;
      const autoCleanupDownloads = document.getElementById('import-auto-cleanup-downloads')?.checked;
      const autoCleanupLibrary = document.getElementById('import-auto-cleanup-library')?.checked;

      // Map pattern keys to their templates
      const patternTemplates = {
        default: '{category}/{title}/{year}/',
        volume: '{category}/{title}/Vol{volume}/',
        flat: '{category}/{title}/',
        volume_year: '{category}/{title}/Vol{volume}/{year}/',
        issue: '{category}/{title}/Issues {issue_range}/',
      };

      let pattern;
      if (patternSelect && patternSelect.value === 'custom' && patternCustom) {
        pattern = patternCustom.value || '{category}/{title}/{year}/';
      } else if (patternSelect) {
        pattern = patternTemplates[patternSelect.value] || '{category}/{title}/{year}/';
      } else {
        pattern = '{category}/{title}/{year}/';
      }

      const importConfig = {
        organization_pattern: pattern,
        enable_text_scan: enableTextScan ?? true,
        enable_ocr: enableOcr ?? true,
        auto_cleanup: {
          enable_downloads: autoCleanupDownloads ?? true,
          enable_library: autoCleanupLibrary ?? true,
        },
      };

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config/save', { import: importConfig });
          return await response.json();
        },
        'Settings',
        'import-message'
      );

      if (data.success) {
        await this.loadSettings();
        UIUtils.showStatus('import-message', 'Import settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('import-message'), 3000);
      } else {
        UIUtils.showStatus('import-message', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving import settings:', error);
      UIUtils.showStatus('import-message', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save theme settings
   */
  async saveThemeSettings() {
    try {
      const mode = document.getElementById('theme-mode')?.value;

      if (!mode) {
        UIUtils.showStatus('theme-message', 'Please select a theme', 'error');
        return;
      }

      // Apply theme immediately using UIUtils
      UIUtils.setTheme(mode);

      UIUtils.showStatus('theme-message', `Theme changed to ${mode} mode`, 'success');
      setTimeout(() => UIUtils.hideStatus('theme-message'), 3000);
    } catch (error) {
      console.error('Error saving theme settings:', error);
      UIUtils.showStatus('theme-message', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save downloads settings
   */
  async saveDownloadsSettings() {
    try {
      const maxRetries = document.getElementById('downloads-max-retries')?.value;
      const maxConcurrent = document.getElementById('downloads-max-concurrent')?.value;

      const downloadsConfig = {
        max_retries: parseInt(maxRetries) || 1,
        max_concurrent: parseInt(maxConcurrent) || 10,
      };

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config', { downloads: downloadsConfig });
          return await response.json();
        },
        'Settings',
        'downloads-message'
      );

      if (data.success) {
        UIUtils.showStatus('downloads-message', 'Downloads settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('downloads-message'), 3000);
      } else {
        UIUtils.showStatus('downloads-message', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving downloads settings:', error);
      UIUtils.showStatus('downloads-message', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save tasks settings (background task intervals)
   */
  async saveTasksSettings() {
    try {
      const autoDownloadInterval = document.getElementById('tasks-auto-download-interval')?.value;
      const downloadMonitorInterval = document.getElementById(
        'tasks-download-monitor-interval'
      )?.value;
      const cleanupCoversInterval = document.getElementById('tasks-cleanup-covers-interval')?.value;
      const ocrProcessorInterval = document.getElementById('tasks-ocr-processor-interval')?.value;

      const tasksConfig = {
        auto_download_interval: parseInt(autoDownloadInterval) || 1800,
        download_monitor_interval: parseInt(downloadMonitorInterval) || 30,
        cleanup_covers_interval: parseInt(cleanupCoversInterval) || 86400,
        ocr_processor_interval: parseInt(ocrProcessorInterval) || 10,
      };

      // Preserve other task settings that aren't in this form section
      if (this.currentConfig?.config?.tasks) {
        const current = this.currentConfig.config.tasks;
        tasksConfig.max_periodicals_per_search =
          current.max_periodicals_per_search !== undefined ? current.max_periodicals_per_search : 2;
        tasksConfig.rapid_search_interval =
          current.rapid_search_interval !== undefined ? current.rapid_search_interval : 1;
        tasksConfig.normal_search_interval =
          current.normal_search_interval !== undefined ? current.normal_search_interval : 6;
        tasksConfig.slow_search_interval =
          current.slow_search_interval !== undefined ? current.slow_search_interval : 24;
        tasksConfig.very_slow_search_interval =
          current.very_slow_search_interval !== undefined ? current.very_slow_search_interval : 168;
      }

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config', { tasks: tasksConfig });
          return await response.json();
        },
        'Settings',
        'tasks-message'
      );

      if (data.success) {
        UIUtils.showStatus('tasks-message', 'Task settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('tasks-message'), 3000);
      } else {
        UIUtils.showStatus('tasks-message', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving tasks settings:', error);
      UIUtils.showStatus('tasks-message', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save discovery settings (adaptive search scheduling)
   */
  async saveDiscoverySettings() {
    try {
      const maxPeriodicalsPerSearch = document.getElementById(
        'tasks-max-periodicals-per-search'
      )?.value;
      const rapidSearchInterval = document.getElementById('tasks-rapid-search-interval')?.value;
      const normalSearchInterval = document.getElementById('tasks-normal-search-interval')?.value;
      const slowSearchInterval = document.getElementById('tasks-slow-search-interval')?.value;
      const verySlowSearchInterval = document.getElementById(
        'tasks-very-slow-search-interval'
      )?.value;

      const tasksConfig = {
        max_periodicals_per_search: parseInt(maxPeriodicalsPerSearch) || 2,
        rapid_search_interval: parseFloat(rapidSearchInterval) || 1,
        normal_search_interval: parseFloat(normalSearchInterval) || 6,
        slow_search_interval: parseFloat(slowSearchInterval) || 24,
        very_slow_search_interval: parseFloat(verySlowSearchInterval) || 168,
      };

      // Preserve other task settings that aren't in this form section
      if (this.currentConfig?.config?.tasks) {
        const current = this.currentConfig.config.tasks;
        tasksConfig.auto_download_interval =
          current.auto_download_interval !== undefined ? current.auto_download_interval : 1800;
        tasksConfig.download_monitor_interval =
          current.download_monitor_interval !== undefined ? current.download_monitor_interval : 30;
        tasksConfig.cleanup_covers_interval =
          current.cleanup_covers_interval !== undefined ? current.cleanup_covers_interval : 86400;
        tasksConfig.ocr_processor_interval =
          current.ocr_processor_interval !== undefined ? current.ocr_processor_interval : 10;
      }

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config', { tasks: tasksConfig });
          return await response.json();
        },
        'Settings',
        'discovery-message'
      );

      if (data.success) {
        UIUtils.showStatus('discovery-message', 'Discovery settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('discovery-message'), 3000);
      } else {
        UIUtils.showStatus('discovery-message', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving discovery settings:', error);
      UIUtils.showStatus('discovery-message', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save PDF settings
   */
  async savePDFSettings() {
    try {
      const coverDpiLow = document.getElementById('pdf-cover-dpi-low')?.value;
      const coverDpiHigh = document.getElementById('pdf-cover-dpi-high')?.value;
      const coverQualityLow = document.getElementById('pdf-cover-quality-low')?.value;
      const coverQualityHigh = document.getElementById('pdf-cover-quality-high')?.value;

      const pdfConfig = {
        cover_dpi_low: parseInt(coverDpiLow) || 60,
        cover_dpi_high: parseInt(coverDpiHigh) || 200,
        cover_quality_low: parseInt(coverQualityLow) || 50,
        cover_quality_high: parseInt(coverQualityHigh) || 85,
      };

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config/save', { pdf: pdfConfig });
          return await response.json();
        },
        'Settings',
        'pdf-message'
      );

      if (data.success) {
        await this.loadSettings();
        UIUtils.showStatus('pdf-message', 'PDF settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('pdf-message'), 3000);
      } else {
        UIUtils.showStatus('pdf-message', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving PDF settings:', error);
      UIUtils.showStatus('pdf-message', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save OCR settings
   */
  async saveOCRSettings() {
    try {
      const resizeWidth = document.getElementById('ocr-resize-width')?.value;
      const contrastEnhance = document.getElementById('ocr-contrast-enhance')?.value;
      const denoiseH = document.getElementById('ocr-denoise-h')?.value;
      const sharpenKernel = document.getElementById('ocr-sharpen-kernel')?.value;

      const ocrConfig = {
        resize_width: parseInt(resizeWidth) || 1200,
        contrast_enhance: parseFloat(contrastEnhance) || 1.5,
        denoise_h: parseInt(denoiseH) || 10,
        sharpen_kernel: parseInt(sharpenKernel) || 5,
      };

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config/save', { ocr: ocrConfig });
          return await response.json();
        },
        'Settings',
        'ocr-message'
      );

      if (data.success) {
        await this.loadSettings();
        UIUtils.showStatus('ocr-message', 'OCR settings saved', 'success');
        setTimeout(() => UIUtils.hideStatus('ocr-message'), 3000);
      } else {
        UIUtils.showStatus('ocr-message', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving OCR settings:', error);
      UIUtils.showStatus('ocr-message', 'Error: ' + error.message, 'error');
    }
  }

  /**
   * Save OCR worker settings (worker count and batch size)
   */
  async saveOCRWorkerSettings() {
    try {
      const workerCount = document.getElementById('ocr-worker-count')?.value;
      const batchSize = document.getElementById('ocr-batch-size')?.value;

      const tasksConfig = {
        ocr_max_workers: parseInt(workerCount) || 1,
        ocr_batch_size: parseInt(batchSize) || 5,
      };

      // Save config without restarting
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/config/save', { tasks: tasksConfig });
          return await response.json();
        },
        'Settings',
        'ocr-worker-message'
      );

      if (data.success) {
        // Reload settings to show updated values in UI
        await this.loadSettings();

        UIUtils.showStatus(
          'ocr-worker-message',
          'OCR worker settings saved. Restart required for changes to take effect.',
          'success'
        );
        setTimeout(() => UIUtils.hideStatus('ocr-worker-message'), 5000);
      } else {
        UIUtils.showStatus('ocr-worker-message', data.message || 'Error saving settings', 'error');
      }
    } catch (error) {
      console.error('Error saving OCR worker settings:', error);
      UIUtils.showStatus('ocr-worker-message', 'Error: ' + error.message, 'error');
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
          UIUtils.showStatus(
            'settings-status',
            'New password must be at least 6 characters',
            'error'
          );
          return;
        }

        if (newPassword !== confirmPassword) {
          UIUtils.showStatus('settings-status', 'New passwords do not match', 'error');
          return;
        }
      }

      const payload = {
        current_password: currentPassword,
      };

      // Only include username if it changed
      if (usernameChanged) {
        payload.username = username;
      }

      if (newPassword) {
        payload.new_password = newPassword;
      }

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/auth/user/update', payload);
          return await response.json();
        },
        'Settings',
        'settings-status'
      );

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
    modal.classList.remove(CSS_CLASSES.HIDDEN);
  }

  /**
   * Close restart modal
   */
  closeRestartModal() {
    const modal = document.getElementById('restart-modal');
    modal.classList.add(CSS_CLASSES.HIDDEN);
  }

  /**
   * Confirm and execute the restart
   */
  async confirmRestartApplication() {
    this.closeRestartModal();

    try {
      UIUtils.showStatus('settings-status', 'Restarting application...', 'info');

      const response = await APIClient.authenticatedFetch('/api/config/restart', {
        method: 'POST',
      });

      if (response.ok) {
        UIUtils.showStatus(
          'settings-status',
          'Application is restarting. Page will reload in a few seconds...',
          'success'
        );

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
          UIUtils.showStatus(
            'settings-status',
            'Application restarted successfully. Reloading...',
            'success'
          );
          setTimeout(() => window.location.reload(), 1000);
          return;
        }
      } catch {
        // Server not ready yet
      }

      attempts++;
      if (attempts < maxAttempts) {
        setTimeout(checkServer, TIMEOUTS.AUTO_HIDE_SUCCESS);
      } else {
        UIUtils.showStatus(
          'settings-status',
          'Restart taking longer than expected. Please refresh manually.',
          'warning'
        );
      }
    };

    checkServer();
  }

  /**
   * Load and display the current API token
   */
  async loadAPIToken() {
    try {
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.get('/api/auth/api-token');
        return await response.json();
      }, 'Settings');

      const tokenDisplay = document.getElementById('api-token-display');
      if (tokenDisplay && data.api_token) {
        tokenDisplay.value = data.api_token;
        tokenDisplay.type = 'password'; // Start as hidden
      }
    } catch (error) {
      console.error('Error loading API token:', error);
    }
  }

  /**
   * Toggle API token visibility (show/hide)
   */
  toggleAPITokenVisibility() {
    const tokenDisplay = document.getElementById('api-token-display');
    const toggleBtn = document.getElementById('api-token-toggle-btn');

    if (tokenDisplay.type === 'password') {
      tokenDisplay.type = 'text';
      toggleBtn.textContent = '🙈';
      toggleBtn.title = 'Hide token';
    } else {
      tokenDisplay.type = 'password';
      toggleBtn.textContent = '👁️';
      toggleBtn.title = 'Show token';
    }
  }

  /**
   * Copy API token to clipboard
   */
  async copyAPIToken() {
    const tokenDisplay = document.getElementById('api-token-display');
    if (tokenDisplay.value) {
      try {
        await navigator.clipboard.writeText(tokenDisplay.value);
        UIUtils.showStatus('api-token-message', 'API token copied to clipboard!', 'success');
        setTimeout(() => {
          document.getElementById('api-token-message').classList.add(CSS_CLASSES.HIDDEN);
        }, 3000);
      } catch (error) {
        UIUtils.showStatus('api-token-message', 'Failed to copy token', 'error');
      }
    }
  }

  /**
   * Regenerate a new API token
   */
  async regenerateAPIToken() {
    const confirmed = await UIUtils.confirm(
      'Regenerate API Token',
      'Are you sure you want to regenerate your API token? This will invalidate the old token.'
    );
    if (!confirmed) return;

    try {
      const result = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.post('/api/auth/api-token/regenerate', {});
          return await response.json();
        },
        'Settings',
        'api-token-message'
      );

      if (result.success) {
        const tokenDisplay = document.getElementById('api-token-display');
        tokenDisplay.value = result.api_token;
        tokenDisplay.type = 'password';
        UIUtils.showStatus('api-token-message', 'API token regenerated successfully!', 'success');
        setTimeout(() => {
          document.getElementById('api-token-message').classList.add(CSS_CLASSES.HIDDEN);
        }, 3000);
      } else {
        UIUtils.showStatus(
          'api-token-message',
          result.message || 'Failed to regenerate token',
          'error'
        );
      }
    } catch (error) {
      console.error('Error regenerating API token:', error);
      UIUtils.showStatus('api-token-message', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Open purge database confirmation modal
   */
  openPurgeModal() {
    // Reset checkbox
    const checkbox = document.getElementById('purge-confirm-checkbox');
    const confirmBtn = document.getElementById('purge-confirm-btn');

    if (checkbox) {
      checkbox.checked = false;
      checkbox.onchange = () => {
        if (confirmBtn) {
          confirmBtn.disabled = !checkbox.checked;
        }
      };
    }

    if (confirmBtn) {
      confirmBtn.disabled = true;
    }

    UIUtils.showModal('purge-database-modal');
  }

  /**
   * Close purge database modal
   */
  closePurgeModal() {
    UIUtils.closeModal('purge-database-modal');
  }

  /**
   * Confirm and execute database purge
   */
  async confirmPurgeDatabase() {
    const checkbox = document.getElementById('purge-confirm-checkbox');

    if (!checkbox || !checkbox.checked) {
      UIUtils.showStatus('settings-status', 'Please confirm you understand this action', 'error');
      return;
    }

    try {
      UIUtils.showStatus('settings-status', 'Purging database...', 'info');

      const response = await APIClient.authenticatedFetch('/api/purge-database', {
        method: 'POST',
      });

      const result = await response.json();

      if (result.success) {
        this.closePurgeModal();
        UIUtils.showStatus('settings-status', result.message, 'success');

        // Reload the page after a delay to show empty library
        setTimeout(() => {
          window.location.reload();
        }, 3000);
      } else {
        UIUtils.showStatus('settings-status', result.message || 'Purge failed', 'error');
      }
    } catch (error) {
      console.error('Error purging database:', error);
      UIUtils.showStatus('settings-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Load and display cache statistics
   */
  async loadCacheStats() {
    try {
      // Load old-style search result cache stats
      const response = await APIClient.authenticatedFetch('/api/cache/stats');
      const stats = await response.json();

      const statsText = document.getElementById('cache-stats-text');
      if (statsText && stats.total_entries) {
        const entryText = stats.total_entries === 1 ? 'entry' : 'entries';
        const queryText = stats.unique_queries === 1 ? 'query' : 'queries';
        statsText.textContent = `Currently ${stats.total_entries} ${entryText} from ${stats.unique_queries} ${queryText}.`;
      }

      // Load provider cache stats for display
      const providerCacheResponse = await APIClient.authenticatedFetch('/api/indexer-cache/status');
      const providerStats = await providerCacheResponse.json();

      // Update cache stats display
      this.displayCacheStats(providerStats);
    } catch (error) {
      console.warn('Error loading cache stats:', error);
    }
  }

  /**
   * Display cache statistics in the UI
   */
  displayCacheStats(stats) {
    const totalReleases = document.getElementById('cache-total-releases');
    const lastSync = document.getElementById('cache-last-sync');

    if (totalReleases) {
      totalReleases.textContent = stats.total_entries?.toLocaleString() || '0';
    }
    if (lastSync) {
      if (stats.last_sync) {
        const date = new Date(stats.last_sync);
        lastSync.textContent = date.toLocaleString();
      } else {
        lastSync.textContent = 'Never';
      }
    }
  }

  /**
   * Display cache settings in the UI
   */
  displayCacheSettings(cacheConfig) {
    const cacheEnabled = document.getElementById('cache-enabled');
    const cacheRetention = document.getElementById('cache-retention');
    const cacheSyncInterval = document.getElementById('cache-sync-interval');

    if (cacheEnabled) {
      cacheEnabled.checked = cacheConfig?.enabled ?? true;
    }
    if (cacheRetention) {
      cacheRetention.value = cacheConfig?.retention_days || 90;
    }
    if (cacheSyncInterval) {
      const intervalMinutes = cacheConfig?.sync?.interval_seconds
        ? Math.round(cacheConfig.sync.interval_seconds / 60)
        : 30;
      cacheSyncInterval.value = intervalMinutes;
    }
  }

  /**
   * Save cache settings
   */
  async saveCacheSettings() {
    try {
      UIUtils.showStatus('settings-status', 'Saving cache settings...', 'info');

      const cacheEnabled = document.getElementById('cache-enabled')?.checked;
      const cacheRetention = parseInt(document.getElementById('cache-retention')?.value || '90');
      const cacheSyncInterval = parseInt(
        document.getElementById('cache-sync-interval')?.value || '30'
      );

      const payload = {
        cache: {
          enabled: cacheEnabled,
          retention_days: cacheRetention,
          sync: {
            interval_seconds: cacheSyncInterval * 60,
            initial_sync_limit: this.currentConfig?.config?.cache?.sync?.initial_sync_limit || 100,
            incremental_sync_limit:
              this.currentConfig?.config?.cache?.sync?.incremental_sync_limit || 100,
          },
        },
      };

      const response = await APIClient.authenticatedFetch('/api/config', {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('settings-status', 'Cache settings saved successfully!', 'success');
        await this.loadSettings();
      } else {
        UIUtils.showStatus(
          'settings-status',
          data.message || 'Failed to save cache settings',
          'error'
        );
      }
    } catch (error) {
      console.error('Error saving cache settings:', error);
      UIUtils.showStatus('settings-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Open purge cache confirmation modal
   */
  openPurgeCacheModal() {
    UIUtils.showModal('purge-cache-modal');
  }

  /**
   * Close purge cache modal
   */
  closePurgeCacheModal() {
    UIUtils.closeModal('purge-cache-modal');
  }

  /**
   * Confirm and execute cache purge
   */
  async confirmPurgeCache() {
    try {
      UIUtils.showStatus('settings-status', 'Purging cache...', 'info');

      const response = await APIClient.authenticatedFetch('/api/purge-cache', {
        method: 'POST',
      });

      const result = await response.json();

      if (result.success) {
        this.closePurgeCacheModal();
        UIUtils.showStatus('settings-status', result.message, 'success');
        // Reload cache stats
        this.loadCacheStats();
      } else {
        UIUtils.showStatus('settings-status', result.message || 'Cache purge failed', 'error');
      }
    } catch (error) {
      console.error('Error purging cache:', error);
      UIUtils.showStatus('settings-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Handle organization pattern dropdown change
   * Shows/hides custom input field based on selection
   *
   * @param {string} context - Either 'import' or 'reorganize'
   */
  handlePatternSelectChange(context) {
    const selectId =
      context === 'import' ? 'import-organization-pattern-select' : 'reorganization-pattern-select';
    const customInputId =
      context === 'import' ? 'import-organization-pattern-custom' : 'reorganization-pattern-custom';

    const selectElement = document.getElementById(selectId);
    const customInput = document.getElementById(customInputId);

    if (!selectElement || !customInput) return;

    if (selectElement.value === 'custom') {
      customInput.classList.remove('hidden');
      customInput.focus();
    } else {
      customInput.classList.add('hidden');
    }
  }
}

// Create singleton instance
export const settings = new SettingsManager();

// Expose functions globally for onclick handlers
window.saveProviderSettings = () => settings.saveProviderSettings();
window.saveDownloadClientSettings = () => settings.saveDownloadClientSettings();
window.testProviderConnection = (index) => settings.testProviderConnection(index);
window.testDownloadClientConnection = () => settings.testDownloadClientConnection();
window.editSearchProvider = (index) => settings.editSearchProvider(index);
window.removeSearchProvider = (index) => settings.removeSearchProvider(index);
window.addSearchProvider = () => settings.addSearchProvider();
window.closeAddProviderModal = () => settings.closeAddProviderModal();
window.saveStorageSettings = () => settings.saveStorageSettings();
window.saveMatchingSettings = () => settings.saveMatchingSettings();
window.saveMetadataSettings = () => settings.saveMetadataSettings();
window.saveLoggingSettings = () => settings.saveLoggingSettings();
window.saveThemeSettings = () => settings.saveThemeSettings();
window.saveAccountSettings = () => settings.saveAccountSettings();
window.restartApplication = () => settings.restartApplication();
window.confirmRestartApplication = () => settings.confirmRestartApplication();
window.closeRestartModal = () => settings.closeRestartModal();
window.openPurgeModal = () => settings.openPurgeModal();
window.closePurgeModal = () => settings.closePurgeModal();
window.confirmPurgeDatabase = () => settings.confirmPurgeDatabase();
window.loadSettingsTab = () => settings.loadSettingsTab();
window.toggleAPITokenVisibility = () => settings.toggleAPITokenVisibility();
window.copyAPIToken = () => settings.copyAPIToken();
window.regenerateAPIToken = () => settings.regenerateAPIToken();
window.openPurgeCacheModal = () => settings.openPurgeCacheModal();
window.closePurgeCacheModal = () => settings.closePurgeCacheModal();
window.confirmPurgeCache = () => settings.confirmPurgeCache();
window.saveDownloadsSettings = () => settings.saveDownloadsSettings();
window.saveTasksSettings = () => settings.saveTasksSettings();
window.saveDiscoverySettings = () => settings.saveDiscoverySettings();
window.savePDFSettings = () => settings.savePDFSettings();
window.saveOCRSettings = () => settings.saveOCRSettings();
window.saveOCRWorkerSettings = () => settings.saveOCRWorkerSettings();
window.saveImportSettings = () => settings.saveImportSettings();
window.handlePatternSelectChange = (context) => settings.handlePatternSelectChange(context);
window.saveCacheSettings = () => settings.saveCacheSettings();
window.loadCacheStats = () => settings.loadCacheStats();
