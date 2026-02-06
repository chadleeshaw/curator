/**
 * Tasks Module
 * Handles scheduled tasks display and execution
 */

import { APIClient, APIHelper } from '../core/api.js';
import { UIUtils } from '../core/ui-utils.js';

export class TasksManager {
  /**
   * Load and populate categories for reorganize dropdown
   */
  async loadCategories() {
    try {
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.get('/api/constants/categories');
        return await response.json();
      }, 'Tasks');

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
      const data = await APIHelper.executeWithErrorHandling(async () => {
        const response = await APIClient.authenticatedFetch('/api/tasks/status');
        return await response.json();
      }, 'Tasks');
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
        const isEnabled = task.enabled !== false;
        const disabledStyle = isEnabled ? '' : 'opacity: 0.5;';
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
            <div style="flex: 1; min-width: 300px; ${disabledStyle}">
              <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                <strong style="font-size: 1.1em; color: var(--text-primary);">${task.name}</strong>
                <label class="task-toggle" title="${isEnabled ? 'Disable' : 'Enable'} ${task.name}">
                  <input type="checkbox" ${isEnabled ? 'checked' : ''} onchange="toggleTask('${task.id}')">
                  <span class="task-toggle-slider"></span>
                </label>
                ${!isEnabled ? '<span style="font-size: 0.8em; color: var(--text-hint); font-style: italic;">Disabled</span>' : ''}
              </div>
              <div style="color: var(--text-secondary); font-size: 0.9em;">
                <div style="margin-bottom: 10px;">${task.description || ''}</div>
                <div style="display: grid; gap: 4px;">
                  <div>⏱️ Interval: ${task.interval}s</div>
                  <div>✓ Last run: ${lastRun}</div>
                  <div>⏭️ Next run: ${isEnabled ? nextRun : 'Disabled'}</div>
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
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(`/api/tasks/run/${taskId}`, {
            method: 'POST',
          });
          return await response.json();
        },
        'Tasks',
        'tasks-status'
      );

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

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/import/reorganize?${params.toString()}`,
            {
              method: 'POST',
            }
          );
          return await response.json();
        },
        'Tasks',
        'reorganize-status'
      );

      // Debug logging
      console.log('[Preview] API Response:', data);
      console.log('[Preview] Changes array:', data.changes);
      console.log('[Preview] Changes length:', data.changes?.length || 0);
      console.log('[Preview] Changes is array?:', Array.isArray(data.changes));

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

      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(
            `/api/import/reorganize?${params.toString()}`,
            {
              method: 'POST',
            }
          );
          return await response.json();
        },
        'Tasks',
        'reorganize-status'
      );

      if (data.success) {
        this.displayReorganizeResults(data, false);
        UIUtils.showStatus(
          'reorganize-status',
          `Reorganized ${data.files_reorganized} file(s) successfully`,
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
   * Display reorganization results with detailed changes
   */
  displayReorganizeResults(data, isPreview) {
    const resultsDiv = document.getElementById('reorganize-results');

    // Debug logging
    console.log('[Display] Received data:', data);
    console.log('[Display] data.changes:', data.changes);
    console.log('[Display] Changes is array?:', Array.isArray(data.changes));
    console.log('[Display] Number of changes:', data.changes?.length || 0);

    if (data.changes && data.changes.length > 0) {
      console.log('[Display] First change:', data.changes[0]);
    }

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

    // Display detailed changes if available
    if (data.changes && Array.isArray(data.changes) && data.changes.length > 0) {
      console.log('[Display] Rendering changes list with', data.changes.length, 'items');
      html += `
        <div style="margin-top: 20px;">
          <h5 style="margin: 0 0 10px 0; color: var(--text-primary); font-size: 1em;">
            📁 ${isPreview ? 'Folder Changes Preview' : 'Completed Changes'} (${data.changes.length})
          </h5>
          <div style="max-height: 400px; overflow-y: auto; border: 1px solid var(--border); border-radius: 4px;">
            ${data.changes
              .slice(0, 50)
              .map(
                (change) => `
              <div style="padding: 10px; border-bottom: 1px solid var(--border-subtle); font-size: 0.9em;">
                <div style="display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px;">
                  ${change.title_changed ? '<span title="Title updated">🏷️</span>' : '<span title="Title unchanged">📄</span>'}
                  <div style="flex: 1;">
                    <div style="color: var(--text-primary); font-weight: 500; margin-bottom: 4px;">
                      ${change.title_changed ? `${this.escapeHtml(change.old_title)} → ${this.escapeHtml(change.new_title)}` : this.escapeHtml(change.new_title)}
                    </div>
                    <div style="font-family: monospace; font-size: 0.85em; color: var(--text-secondary);">
                      <div title="Old folder" style="color: var(--status-failed); margin-bottom: 2px;">
                        ❌ ${this.escapeHtml(change.old_folder)}/
                      </div>
                      <div title="New folder" style="color: var(--status-completed);">
                        ✅ ${this.escapeHtml(change.new_folder)}/
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            `
              )
              .join('')}
            ${
              data.changes.length > 50
                ? `
              <div style="padding: 10px; text-align: center; color: var(--text-hint); font-style: italic;">
                ... and ${data.changes.length - 50} more change(s)
              </div>
            `
                : ''
            }
          </div>
          <div style="margin-top: 8px; font-size: 0.85em; color: var(--text-hint);">
            💡 Legend: 🏷️ = Title updated (country added), 📄 = Title unchanged
          </div>
        </div>
      `;
    } else {
      console.log('[Display] No changes to display - data.changes:', data.changes);
      // Show a message if there are files to reorganize but no detailed changes
      if (data.files_reorganized > 0) {
        html += `
          <div style="margin-top: 20px; padding: 10px; background: var(--background-secondary); border: 1px solid var(--border); border-radius: 4px; color: var(--text-hint);">
            ℹ️ Detailed changes list not available
          </div>
        `;
      }
    }

    if (data.errors && data.errors.length > 0) {
      html += `
        <div style="margin-top: 15px; padding: 10px; background: var(--status-failed-bg); border: 1px solid var(--status-failed); border-radius: 4px;">
          <strong style="color: var(--status-failed);">⚠️ Errors (${data.errors.length}):</strong>
          <ul style="margin: 8px 0 0 20px; color: var(--text-secondary); font-size: 0.9em;">
            ${data.errors
              .slice(0, 5)
              .map((err) => `<li>${this.escapeHtml(err)}</li>`)
              .join('')}
            ${data.errors.length > 5 ? `<li><em>... and ${data.errors.length - 5} more</em></li>` : ''}
          </ul>
        </div>
      `;
    }

    html += '</div>';

    resultsDiv.innerHTML = html;
  }

  /**
   * Toggle a task's enabled/disabled state
   */
  async toggleTask(taskId) {
    try {
      const data = await APIHelper.executeWithErrorHandling(
        async () => {
          const response = await APIClient.authenticatedFetch(`/api/tasks/${taskId}/toggle`, {
            method: 'POST',
          });
          return await response.json();
        },
        'Tasks',
        'tasks-status'
      );

      if (data.success) {
        const state = data.enabled ? 'enabled' : 'disabled';
        UIUtils.showStatus('tasks-status', `Task ${state}`, 'success');
        setTimeout(() => UIUtils.hideStatus('tasks-status'), 3000);
        this.loadScheduledTasks();
      } else {
        UIUtils.showStatus('tasks-status', data.message || 'Failed to toggle task', 'error');
        this.loadScheduledTasks(); // Reload to reset checkbox state
      }
    } catch (error) {
      console.error('Error toggling task:', error);
      UIUtils.showStatus('tasks-status', 'Error toggling task', 'error');
      this.loadScheduledTasks(); // Reload to reset checkbox state
    }
  }

  /**
   * Escape HTML to prevent XSS
   */
  escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}

// Create singleton instance
export const tasks = new TasksManager();

// Expose functions globally for onclick handlers
window.runTaskManually = (taskId) => tasks.runTaskManually(taskId);
window.toggleTask = (taskId) => tasks.toggleTask(taskId);
window.runReorganizePreview = () => tasks.runReorganizePreview();
window.runReorganize = () => tasks.runReorganize();
