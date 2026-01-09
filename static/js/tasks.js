/**
 * Tasks Module
 * Handles scheduled tasks display and execution
 */

import { APIClient } from './api.js';
import { UIUtils } from './ui-utils.js';

export class TasksManager {
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
        const hasDetailedTimestamps = task.stats && (task.stats.last_client_check || task.stats.last_folder_scan);
        if (hasDetailedTimestamps) {
          const stats = task.stats;
          timestampsHtml = `
          <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border); font-size: 0.85em; color: var(--text-secondary); display: grid; gap: 6px;">
            ${stats.last_client_check ? `<div>🕐 Last client check: <strong>${new Date(stats.last_client_check).toLocaleString()}</strong></div>` : ''}
            ${stats.last_folder_scan ? `<div>🕐 Last folder scan: <strong>${new Date(stats.last_folder_scan).toLocaleString()}</strong></div>` : ''}
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
                  ${!hasDetailedTimestamps ? `<div>✓ Last run: ${lastRun}</div>` : ''}
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
      tasksList.insertAdjacentHTML('afterbegin', `
        <div style="padding: 15px 20px; background: var(--surface-variant); border-radius: 8px; border: 1px solid var(--border); margin-bottom: 15px; display: flex; align-items: center; gap: 8px;">
          <span style="font-size: 1.2em;">🌍</span>
          <span style="color: var(--text-secondary);">Timezone:</span>
          <strong style="color: var(--text-primary);">${timezone}</strong>
        </div>
      `);
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
}

// Create singleton instance
export const tasks = new TasksManager();

// Expose functions globally for onclick handlers
window.runTaskManually = (taskId) => tasks.runTaskManually(taskId);
