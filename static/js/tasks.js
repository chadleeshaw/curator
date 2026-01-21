/**
 * Tasks Module
 * Handles scheduled tasks display and execution
 */

import { APIClient } from './api.js';
import { UIUtils } from './ui-utils.js';

export class TasksManager {
  /**
   * Load and populate categories for reorganize dropdown
   */
  async loadCategories() {
    try {
      const response = await APIClient.get('/api/constants/categories');
      const data = await response.json();

      if (data.success && data.categories) {
        this.populateCategoryDropdown(data.categories);
      }
    } catch (error) {
      console.error('[Tasks] Failed to load categories:', error);
      // If loading fails, dropdown will keep the hardcoded defaults
    }
  }

  /**
   * Populate the category dropdown with categories from API
   *
   * @param {string[]} categories - Array of category names
   */
  populateCategoryDropdown(categories) {
    const dropdown = document.getElementById('reorganize-category');
    if (!dropdown) return;

    // Store current selection
    const currentValue = dropdown.value || categories[0];

    // Clear and repopulate
    dropdown.innerHTML = '';

    // Add each category as an option
    categories.forEach((category) => {
      const option = document.createElement('option');
      option.value = category;
      option.textContent = category;
      dropdown.appendChild(option);
    });

    // Restore selection if still valid
    if (categories.includes(currentValue)) {
      dropdown.value = currentValue;
    }
  }

  /**
   * Load and display scheduled tasks
   */
  async loadScheduledTasks() {
    try {
      console.log('[Tasks] Starting loadScheduledTasks...');
      const response = await APIClient.authenticatedFetch('/api/tasks/status');
      const data = await response.json();
      console.log('[Tasks] API Response:', data);
      console.log('[Tasks] Found tasks:', data.tasks?.length || 0);
      data.tasks?.forEach((task, idx) => {
        console.log(`  [${idx}] ${task.id}: last_run=${task.last_run}, status=${task.last_status}`);
      });
      this.displayScheduledTasks(data);
    } catch (error) {
      console.error('[Tasks] Error loading scheduled tasks:', error);
    }
  }

  /**
   * Display scheduled tasks in the UI
   */
  displayScheduledTasks(data) {
    const tasksList = document.getElementById('scheduled-tasks-list');
    console.log('[Tasks] displayScheduledTasks called with:', data);

    if (!data.tasks || data.tasks.length === 0) {
      console.log('[Tasks] No tasks to display');
      tasksList.innerHTML =
        '<p style="color: var(--text-secondary);">No scheduled tasks configured.</p>';
      return;
    }

    console.log('[Tasks] Rendering tasks');

    // Get timezone info
    // eslint-disable-next-line no-undef
    const timezone = data.timezone || Intl.DateTimeFormat().resolvedOptions().timeZone;

    tasksList.innerHTML = data.tasks
      .map((task) => {
        const lastRun = task.last_run ? new Date(task.last_run).toLocaleString() : 'Never';
        const nextRun = task.next_run ? new Date(task.next_run).toLocaleString() : 'Pending';
        console.log(`[Tasks] Rendering task: ${task.name}, lastRun: ${task.last_run}`);

        // Build additional timestamps section if available
        let timestampsHtml = '';
        const hasDetailedTimestamps =
          task.stats &&
          (task.stats.last_client_check ||
            task.stats.last_folder_scan ||
            task.stats.last_process_time);
        if (hasDetailedTimestamps) {
          const stats = task.stats;
          timestampsHtml = `
          <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 0.85em; color: var(--text-secondary); display: grid; gap: 6px;">
            ${stats.last_client_check ? `<div>🕐 Last client check: <strong>${new Date(stats.last_client_check).toLocaleString()}</strong></div>` : ''}
            ${stats.last_folder_scan ? `<div>🕐 Last folder scan: <strong>${new Date(stats.last_folder_scan).toLocaleString()}</strong></div>` : ''}
            ${stats.last_process_time ? `<div>🕐 Last OCR process: <strong>${new Date(stats.last_process_time).toLocaleString()}</strong></div>` : ''}
          </div>
        `;
        }

        return `
        <div style="padding: 20px; background: var(--surface-variant); border-radius: 8px; border: 1px solid var(--border); box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
          <div style="display: flex; justify-content: space-between; align-items: start; gap: 15px; flex-wrap: wrap;">
            <div style="flex: 1; min-width: 300px;">
              <strong style="font-size: 1.1em; color: var(--text-primary);">${task.name}</strong>
              <div style="color: var(--text-secondary); font-size: 0.9em; margin-top: 8px;">
                <div style="margin-bottom: 10px;">${task.description || ''}</div>
                <div style="display: grid; gap: 4px;">
                  <div>⏱️ Interval: ${task.interval}s</div>
                  <div>✓ Last run: ${lastRun}</div>
                  <div>⏭️ Next run: ${nextRun}</div>
                  ${task.last_status ? `<div style="color: ${task.last_status === 'success' ? 'var(--status-completed)' : 'var(--status-failed)'};">Status: ${task.last_status}</div>` : ''}
                </div>
              </div>
              ${timestampsHtml}
            </div>
            <button onclick="runTaskManually('${task.id}')" class="btn-primary" style="flex-shrink: 0;">▶️ Run Now</button>
          </div>
        </div>
      `;
      })
      .join('');

    // Add timezone info at the top with consistent styling
    if (timezone) {
      tasksList.insertAdjacentHTML(
        'afterbegin',
        `
        <div style="padding: 15px 20px; background: var(--surface-variant); border-radius: 8px; border: 1px solid var(--border); margin-bottom: 15px; display: flex; align-items: center; gap: 8px;">
          <span style="font-size: 1.2em;">🌍</span>
          <span style="color: var(--text-secondary);">Timezone:</span>
          <strong style="color: var(--text-primary);">${timezone}</strong>
        </div>
      `
      );
    }
  }

  /**
   * Run a task manually
   */
  async runTaskManually(taskId) {
    try {
      const response = await APIClient.authenticatedFetch(`/api/tasks/run/${taskId}`, {
        method: 'POST',
      });
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus(
          'tasks-status',
          `Task "${data.task_name}" started successfully`,
          'success'
        );
        setTimeout(() => UIUtils.hideStatus('tasks-status'), 3000);
        this.loadScheduledTasks();
      } else {
        UIUtils.showStatus('tasks-status', data.message, 'error');
      }
    } catch (error) {
      console.error('Error running task:', error);
      UIUtils.showStatus('tasks-status', 'Error running task', 'error');
    }
  }

  /**
   * Run reorganization preview (dry run)
   */
  async runReorganizePreview() {
    const category = document.getElementById('reorganize-category').value;
    const patternSelect = document.getElementById('reorganization-pattern-select');
    const patternCustom = document.getElementById('reorganization-pattern-custom');

    // Get pattern from dropdown or custom input
    let pattern = null;
    if (patternSelect && patternSelect.value) {
      if (patternSelect.value === 'custom' && patternCustom) {
        pattern = patternCustom.value || null;
      } else if (patternSelect.value !== '') {
        // Map pattern keys to their templates
        const patternTemplates = {
          default: '{category}/{title}/{year}/',
          volume: '{category}/{title}/Vol{volume}/',
          flat: '{category}/{title}/',
          volume_year: '{category}/{title}/Vol{volume}/{year}/',
          issue: '{category}/{title}/Issues {issue_range}/',
        };
        pattern = patternTemplates[patternSelect.value] || null;
      }
    }

    try {
      UIUtils.showStatus('reorganize-status', '🔍 Analyzing files...', 'info');
      document.getElementById('reorganize-results').innerHTML = '';

      const params = new URLSearchParams({
        category,
        dry_run: 'true',
      });

      if (pattern) {
        params.append('pattern', pattern);
      }

      const response = await APIClient.authenticatedFetch(
        `/api/import/reorganize?${params.toString()}`,
        {
          method: 'POST',
        }
      );

      const data = await response.json();

      if (data.success) {
        this.displayReorganizeResults(data, true);
        UIUtils.showStatus(
          'reorganize-status',
          `Preview complete: ${data.files_reorganized} file(s) would be reorganized`,
          'success'
        );
      } else {
        UIUtils.showStatus('reorganize-status', data.error || 'Preview failed', 'error');
      }
    } catch (error) {
      console.error('Error running reorganize preview:', error);
      UIUtils.showStatus('reorganize-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Run actual reorganization
   */
  async runReorganize() {
    const category = document.getElementById('reorganize-category').value;
    const patternSelect = document.getElementById('reorganization-pattern-select');
    const patternCustom = document.getElementById('reorganization-pattern-custom');

    // Get pattern from dropdown or custom input
    let pattern = null;
    if (patternSelect && patternSelect.value) {
      if (patternSelect.value === 'custom' && patternCustom) {
        pattern = patternCustom.value || null;
      } else if (patternSelect.value !== '') {
        // Map pattern keys to their templates
        const patternTemplates = {
          default: '{category}/{title}/{year}/',
          volume: '{category}/{title}/Vol{volume}/',
          flat: '{category}/{title}/',
          volume_year: '{category}/{title}/Vol{volume}/{year}/',
          issue: '{category}/{title}/Issues {issue_range}/',
        };
        pattern = patternTemplates[patternSelect.value] || null;
      }
    }

    // Confirm before running
    const filesReorganized = document.getElementById('reorganize-results').textContent;
    const confirmMsg = filesReorganized
      ? 'Are you sure you want to reorganize these files? This will move files and delete old directories.'
      : 'Are you sure you want to reorganize files? Run Preview first to see what will change.';

    const confirmed = await UIUtils.confirm('Reorganize Files', confirmMsg);

    if (!confirmed) {
      return;
    }

    try {
      UIUtils.showStatus('reorganize-status', '📁 Reorganizing files...', 'info');
      document.getElementById('reorganize-results').innerHTML = '';

      const params = new URLSearchParams({
        category,
        dry_run: 'false',
      });

      if (pattern) {
        params.append('pattern', pattern);
      }

      const response = await APIClient.authenticatedFetch(
        `/api/import/reorganize?${params.toString()}`,
        {
          method: 'POST',
        }
      );

      const data = await response.json();

      if (data.success) {
        this.displayReorganizeResults(data, false);
        UIUtils.showStatus(
          'reorganize-status',
          `✓ Reorganized ${data.files_reorganized} file(s) successfully`,
          'success'
        );
      } else {
        UIUtils.showStatus('reorganize-status', data.error || 'Reorganization failed', 'error');
      }
    } catch (error) {
      console.error('Error running reorganize:', error);
      UIUtils.showStatus('reorganize-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Display reorganization results
   */
  displayReorganizeResults(data, isPreview) {
    const resultsDiv = document.getElementById('reorganize-results');

    const statusLabel = isPreview ? 'Would be reorganized' : 'Reorganized';
    const skippedLabel = isPreview ? 'Would be skipped' : 'Skipped';

    let html = `
      <div style="padding: 15px; background: var(--background); border: 1px solid var(--border); border-radius: 6px;">
        <h4 style="margin-top: 0; color: var(--text-primary);">${isPreview ? '🔍 Preview' : '✓ Completed'}</h4>
        <div style="display: grid; gap: 8px; font-size: 0.95em;">
          <div><strong>Category:</strong> ${data.category}</div>
          <div><strong>Pattern:</strong> ${data.pattern}</div>
          <div><strong>Files found:</strong> ${data.files_found}</div>
          <div style="color: ${data.files_reorganized > 0 ? 'var(--status-completed)' : 'var(--text-secondary)'};">
            <strong>${statusLabel}:</strong> ${data.files_reorganized}
          </div>
          <div><strong>${skippedLabel}:</strong> ${data.files_skipped}</div>
        </div>
    `;

    if (data.errors && data.errors.length > 0) {
      html += `
        <div style="margin-top: 15px; padding: 10px; background: var(--status-failed-bg); border: 1px solid var(--status-failed); border-radius: 4px;">
          <strong style="color: var(--status-failed);">⚠️ Errors (${data.errors.length}):</strong>
          <ul style="margin: 8px 0 0 20px; color: var(--text-secondary); font-size: 0.9em;">
            ${data.errors
              .slice(0, 5)
              .map((err) => `<li>${err}</li>`)
              .join('')}
            ${data.errors.length > 5 ? `<li><em>... and ${data.errors.length - 5} more</em></li>` : ''}
          </ul>
        </div>
      `;
    }

    html += '</div>';

    resultsDiv.innerHTML = html;
  }
}

// Create singleton instance
export const tasks = new TasksManager();

// Expose functions globally for onclick handlers
window.runTaskManually = (taskId) => tasks.runTaskManually(taskId);
window.runReorganizePreview = () => tasks.runReorganizePreview();
window.runReorganize = () => tasks.runReorganize();
