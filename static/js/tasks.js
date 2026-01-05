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
      
      return `
        <div style="padding: 15px; background: var(--surface); border-radius: 8px; border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 15px;">
          <div>
            <strong style="font-size: 1.1em;">${task.name}</strong>
            <div style="color: var(--text-secondary); font-size: 0.9em; margin-top: 5px;">
              <div>⏱️ Interval: ${task.interval}s</div>
              <div>✓ Last run: ${lastRun}</div>
              <div>⏭️ Next run: ${nextRun}</div>
              ${task.last_status ? `<div style="color: ${task.last_status === 'success' ? 'var(--status-completed)' : 'var(--status-failed)'};">Status: ${task.last_status}</div>` : ''}
            </div>
          </div>
          <button onclick="runTaskManually('${task.id}')" class="btn-secondary">▶️ Run Now</button>
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
