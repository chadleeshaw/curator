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
      tasksList.innerHTML = '<p style="color: var(--text-secondary);">No scheduled tasks configured.</p>';
      return;
    }
    
    console.log('[Tasks] Rendering tasks');
    tasksList.innerHTML = data.tasks.map(task => {
      const lastRun = task.last_run ? new Date(task.last_run).toLocaleString() : 'Never';
      const nextRun = task.next_run ? new Date(task.next_run).toLocaleString() : 'Pending';
      console.log(`[Tasks] Rendering task: ${task.name}, lastRun: ${task.last_run}`);
      
      // Build statistics section if available
      let statsHtml = '';
      if (task.stats) {
        const stats = task.stats;
        statsHtml = `
          <div style="margin-top: 10px; padding: 10px; background: var(--background); border-radius: 6px; border: 1px solid var(--border-color);">
            <div style="font-weight: 600; margin-bottom: 8px; color: var(--primary-color);">📊 Statistics</div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; font-size: 0.85em;">
              <div>🔄 Total runs: <strong>${stats.total_runs || 0}</strong></div>
              ${stats.client_downloads_processed !== undefined ? `<div>✅ Client processed: <strong>${stats.client_downloads_processed}</strong></div>` : ''}
              ${stats.client_downloads_failed !== undefined && stats.client_downloads_failed > 0 ? `<div style="color: var(--status-failed);">❌ Client failed: <strong>${stats.client_downloads_failed}</strong></div>` : ''}
              ${stats.folder_files_imported !== undefined ? `<div>📁 Folder imported: <strong>${stats.folder_files_imported}</strong></div>` : ''}
              ${stats.bad_files_detected !== undefined && stats.bad_files_detected > 0 ? `<div style="color: var(--status-failed); font-weight: 600;">🚫 Bad files: <strong>${stats.bad_files_detected}</strong></div>` : ''}
            </div>
            ${stats.last_client_check || stats.last_folder_scan ? `
              <div style="margin-top: 8px; font-size: 0.8em; color: var(--text-secondary);">
                ${stats.last_client_check ? `<div>Last client check: ${new Date(stats.last_client_check).toLocaleString()}</div>` : ''}
                ${stats.last_folder_scan ? `<div>Last folder scan: ${new Date(stats.last_folder_scan).toLocaleString()}</div>` : ''}
              </div>
            ` : ''}
          </div>
        `;
      }
      
      return `
        <div style="padding: 15px; background: var(--surface); border-radius: 8px; border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: start; flex-wrap: wrap; gap: 15px;">
          <div style="flex: 1; min-width: 300px;">
            <strong style="font-size: 1.1em;">${task.name}</strong>
            <div style="color: var(--text-secondary); font-size: 0.9em; margin-top: 5px;">
              <div>${task.description || ''}</div>
              <div style="margin-top: 8px;">
                <div>⏱️ Interval: ${task.interval}s</div>
                <div>✓ Last run: ${lastRun}</div>
                <div>⏭️ Next run: ${nextRun}</div>
                ${task.last_status ? `<div style="color: ${task.last_status === 'success' ? 'var(--status-completed)' : 'var(--status-failed)'};">Status: ${task.last_status}</div>` : ''}
              </div>
            </div>
            ${statsHtml}
          </div>
          <button onclick="runTaskManually('${task.id}')" class="btn-secondary" style="flex-shrink: 0;">▶️ Run Now</button>
        </div>
      `;
    }).join('');
  }

  /**
   * Run a task manually
   */
  async runTaskManually(taskId) {
    try {
      const response = await APIClient.authenticatedFetch(`/api/tasks/run/${taskId}`, { method: 'POST' });
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('tasks-status', `Task "${data.task_name}" started successfully`, 'success');
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
