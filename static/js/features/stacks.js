/**
 * Stacks Management Module
 * Handles CRUD operations for stacks and member assignment
 * @module stacks
 */

import { APIClient, APIHelper } from '../core/api.js';
import { UIUtils } from '../core/ui-utils.js';

/**
 * Stacks Manager class for managing stack CRUD and assignment
 * @class
 */
export class StacksManager {
  constructor() {
    /** @type {Array} All stacks loaded from API */
    this.allStacks = [];
    /** @type {boolean} Whether stacks have been loaded */
    this.stacksLoaded = false;
    /** @type {Object|null} Stack currently being edited/assigned */
    this.currentStack = null;
    /** @type {Array} All available items for assignment */
    this.availableItems = [];
    /** @type {Set} IDs selected for adding to stack */
    this.selectedForAdd = new Set();
    /** @type {Function|null} Callback when stacks change (create/update/delete/assign) */
    this.onChangeCallback = null;
    /** @type {Array} Available categories from constants API */
    this.availableCategories = [];
    /** @type {Set} Currently selected categories in the modal */
    this.selectedCategories = new Set();
  }

  /**
   * Register a callback to be called when stacks are modified
   *
   * @param {Function} callback - Function to call on stack changes
   */
  onChange(callback) {
    this.onChangeCallback = callback;
  }

  /**
   * Notify listeners that stacks have changed
   * @private
   */
  async _notifyChange() {
    if (this.onChangeCallback) {
      await this.onChangeCallback();
    }
  }

  /**
   * Load all stacks from API and render the management list
   *
   * @returns {Promise<void>}
   */
  async loadStacks() {
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.authenticatedFetch('/api/stacks');
      return await response.json();
    }, 'Stacks');

    if (data) {
      this.allStacks = data.stacks || [];
      this.stacksLoaded = true;
      this.renderStacksList();
    }
  }

  /**
   * Render the stacks management list in the Stacks tab
   *
   * @returns {void}
   */
  renderStacksList() {
    const container = document.getElementById('stacks-list');
    if (!container) return;

    container.innerHTML = '';

    if (this.allStacks.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📚</div>
          <h3>No Stacks Yet</h3>
          <p>Create your first stack to group related periodicals together.</p>
          <button onclick="openCreateStackModal()" class="btn-primary" style="margin-top: 16px">
            ➕ Create Stack
          </button>
        </div>
      `;
      return;
    }

    this.allStacks.forEach((stack) => {
      container.appendChild(this.createStackManagementCard(stack));
    });
  }

  /**
   * Create a management card for a stack
   *
   * @param {Object} stack - Stack data
   * @returns {HTMLElement}
   */
  createStackManagementCard(stack) {
    const card = document.createElement('div');
    card.className = 'stack-management-card';
    card.dataset.stackId = stack.id;

    const info = document.createElement('div');
    info.className = 'stack-management-info';

    const h4 = document.createElement('h4');
    h4.textContent = `📚 ${stack.name}`;
    info.appendChild(h4);

    if (stack.description) {
      const desc = document.createElement('p');
      desc.textContent = stack.description;
      info.appendChild(desc);
    }

    const meta = document.createElement('div');
    meta.className = 'stack-management-meta';
    meta.innerHTML = `
      <span>${stack.member_count} item${stack.member_count !== 1 ? 's' : ''}</span>
      <span>Created ${new Date(stack.created_at).toLocaleDateString()}</span>
    `;
    info.appendChild(meta);

    card.appendChild(info);

    const actions = document.createElement('div');
    actions.className = 'stack-management-actions';

    const viewBtn = document.createElement('button');
    viewBtn.className = 'btn-icon';
    viewBtn.title = 'View Stack';
    viewBtn.textContent = '👁️';
    viewBtn.onclick = () => {
      window.location.href = `/stacks/${stack.slug}`;
    };
    actions.appendChild(viewBtn);

    const assignBtn = document.createElement('button');
    assignBtn.className = 'btn-icon';
    assignBtn.title = 'Manage Members';
    assignBtn.textContent = '📋';
    assignBtn.onclick = () => this.openAssignModal(stack);
    actions.appendChild(assignBtn);

    const editBtn = document.createElement('button');
    editBtn.className = 'btn-icon';
    editBtn.title = 'Edit';
    editBtn.textContent = '✏️';
    editBtn.onclick = () => this.openEditStackModal(stack);
    actions.appendChild(editBtn);

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'btn-icon btn-danger';
    deleteBtn.title = 'Delete';
    deleteBtn.textContent = '🗑️';
    deleteBtn.onclick = () => this.openDeleteStackModal(stack);
    actions.appendChild(deleteBtn);

    card.appendChild(actions);
    return card;
  }

  /**
   * Load available categories from constants API and render pill toggles
   *
   * @param {Array} preselected - Categories to pre-select
   */
  async _loadCategoryPills(preselected = []) {
    const container = document.getElementById('stack-categories-container');
    if (!container) return;

    // Load categories from API if not cached
    if (this.availableCategories.length === 0) {
      try {
        const response = await APIClient.get('/api/constants/categories');
        const data = await response.json();
        this.availableCategories = data.categories || [];
      } catch {
        this.availableCategories = [];
      }
    }

    this.selectedCategories = new Set(preselected);

    container.innerHTML = this.availableCategories
      .map((cat) => {
        const selected = this.selectedCategories.has(cat) ? ' selected' : '';
        return `<button type="button" class="stack-category-pill${selected}" data-category="${cat}">${cat}</button>`;
      })
      .join('');

    // Attach click handlers
    container.querySelectorAll('.stack-category-pill').forEach((pill) => {
      pill.addEventListener('click', () => {
        const cat = pill.dataset.category;
        if (this.selectedCategories.has(cat)) {
          this.selectedCategories.delete(cat);
          pill.classList.remove('selected');
        } else {
          this.selectedCategories.add(cat);
          pill.classList.add('selected');
        }
      });
    });
  }

  /**
   * Open modal to create a new stack
   */
  openCreateStackModal() {
    const nameInput = document.getElementById('stack-name-input');
    const descInput = document.getElementById('stack-desc-input');
    if (nameInput) nameInput.value = '';
    if (descInput) descInput.value = '';

    const modalTitle = document.getElementById('stack-modal-title');
    if (modalTitle) modalTitle.textContent = '➕ Create New Stack';

    const saveBtn = document.getElementById('stack-modal-save-btn');
    if (saveBtn) {
      saveBtn.textContent = 'Create';
      saveBtn.onclick = () => this.createStack();
    }

    this._loadCategoryPills([]);
    UIUtils.showModal('stack-create-modal');
  }

  /**
   * Open modal to edit an existing stack
   *
   * @param {Object} stack - Stack data
   */
  openEditStackModal(stack) {
    this.currentStack = stack;

    const nameInput = document.getElementById('stack-name-input');
    const descInput = document.getElementById('stack-desc-input');
    if (nameInput) nameInput.value = stack.name;
    if (descInput) descInput.value = stack.description || '';

    const modalTitle = document.getElementById('stack-modal-title');
    if (modalTitle) modalTitle.textContent = '✏️ Edit Stack';

    const saveBtn = document.getElementById('stack-modal-save-btn');
    if (saveBtn) {
      saveBtn.textContent = 'Save';
      saveBtn.onclick = () => this.updateStack();
    }

    this._loadCategoryPills(stack.categories || []);
    UIUtils.showModal('stack-create-modal');
  }

  /**
   * Create a new stack via API
   */
  async createStack() {
    const name = document.getElementById('stack-name-input')?.value?.trim();
    const description = document.getElementById('stack-desc-input')?.value?.trim();
    const categories = [...this.selectedCategories];

    if (!name) {
      UIUtils.showToast('Please enter a stack name', 'error');
      return;
    }

    const body = { name };
    if (description) body.description = description;
    if (categories.length > 0) body.categories = categories;

    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.authenticatedFetch('/api/stacks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      return await response.json();
    }, 'Stacks');

    if (data) {
      UIUtils.closeModal('stack-create-modal');
      UIUtils.showToast(`Stack "${name}" created`, 'success');
      await this.loadStacks();
      await this._notifyChange();
    }
  }

  /**
   * Update an existing stack via API
   */
  async updateStack() {
    if (!this.currentStack) return;

    const name = document.getElementById('stack-name-input')?.value?.trim();
    const description = document.getElementById('stack-desc-input')?.value?.trim();
    const categories = [...this.selectedCategories];

    if (!name) {
      UIUtils.showToast('Please enter a stack name', 'error');
      return;
    }

    const body = { name, description: description || '', categories };

    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.authenticatedFetch(
        `/api/stacks/${this.currentStack.slug}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      );
      return await response.json();
    }, 'Stacks');

    if (data) {
      UIUtils.closeModal('stack-create-modal');
      UIUtils.showToast(`Stack "${name}" updated`, 'success');
      this.currentStack = null;
      await this.loadStacks();
      await this._notifyChange();
    }
  }

  /**
   * Open delete confirmation modal
   *
   * @param {Object} stack - Stack to delete
   */
  openDeleteStackModal(stack) {
    this.currentStack = stack;
    const titleEl = document.getElementById('delete-stack-name');
    if (titleEl) titleEl.textContent = stack.name;
    const countEl = document.getElementById('delete-stack-count');
    if (countEl)
      countEl.textContent = `${stack.member_count} item${stack.member_count !== 1 ? 's' : ''} will be ungrouped (not deleted).`;
    UIUtils.showModal('stack-delete-modal');
  }

  /**
   * Close delete confirmation modal
   */
  closeDeleteStackModal() {
    UIUtils.closeModal('stack-delete-modal');
    this.currentStack = null;
  }

  /**
   * Confirm and execute stack deletion
   */
  async confirmDeleteStack() {
    if (!this.currentStack) return;

    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.authenticatedFetch(
        `/api/stacks/${this.currentStack.slug}`,
        { method: 'DELETE' }
      );
      return await response.json();
    }, 'Stacks');

    if (data) {
      UIUtils.closeModal('stack-delete-modal');
      UIUtils.showToast(`Stack "${this.currentStack.name}" deleted`, 'success');
      this.currentStack = null;
      await this.loadStacks();
      await this._notifyChange();
    }
  }

  /**
   * Open the member assignment modal for a stack
   *
   * @param {Object} stack - Stack to manage members for
   */
  async openAssignModal(stack) {
    this.currentStack = stack;
    this.selectedForAdd = new Set();

    const titleEl = document.getElementById('assign-stack-name');
    if (titleEl) titleEl.textContent = stack.name;

    // Load full stack details with current members
    const stackData = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.authenticatedFetch(`/api/stacks/${stack.slug}`);
      return await response.json();
    }, 'Stacks');

    // Load all tracking items
    const trackingData = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.authenticatedFetch(
        '/api/periodicals/tracking?limit=1000'
      );
      return await response.json();
    }, 'Stacks');

    // Load library periodicals (to find untracked items)
    const libraryData = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.authenticatedFetch('/api/periodicals?limit=1000');
      return await response.json();
    }, 'Stacks');

    if (!stackData || !trackingData) return;

    const currentMembers = stackData.stack?.members || [];
    const allTracked = trackingData.tracked_magazines || [];
    const allPeriodicals = libraryData?.periodicals || [];

    // Get IDs already in this stack
    const memberTrackingIds = new Set(
      currentMembers
        .filter((m) => m.periodical_tracking_id)
        .map((m) => m.periodical_tracking_id)
    );
    const memberPeriodicalIds = new Set(
      currentMembers
        .filter((m) => m.periodical_id)
        .map((m) => m.periodical_id)
    );

    // Render current members
    const membersContainer = document.getElementById('stack-current-members');
    if (membersContainer) {
      membersContainer.innerHTML = '';
      if (currentMembers.length === 0) {
        membersContainer.innerHTML =
          '<p style="padding: 12px; color: var(--text-secondary)">No members yet</p>';
      } else {
        currentMembers.forEach((member) => {
          const item = document.createElement('div');
          item.className = 'stack-assignment-item';
          item.style.display = 'flex';
          item.style.justifyContent = 'space-between';
          item.style.alignItems = 'center';
          item.innerHTML = `
            <span>${member.title || 'Unknown'} <small style="color: var(--text-secondary)">(${member.type})</small></span>
            <button class="btn-sm btn-danger-text" title="Remove">✕</button>
          `;
          const removeBtn = item.querySelector('button');
          removeBtn.onclick = async () => {
            await this.removeMember(stack.slug, member.id);
            await this.openAssignModal(stack); // Refresh
          };
          membersContainer.appendChild(item);
        });
      }
    }

    // Build available items list: tracked items + untracked library periodicals
    const availableContainer = document.getElementById('stack-available-items');
    if (availableContainer) {
      availableContainer.innerHTML = '';
      const availableItems = [];

      // Add tracked items that aren't in any stack
      allTracked.forEach((t) => {
        if (!t.stack_id && !memberTrackingIds.has(t.id)) {
          availableItems.push({
            id: t.id,
            title: t.title,
            label: t.category || 'Tracked',
            type: 'tracking',
          });
        }
      });

      // Add untracked library periodicals that aren't in any stack
      const trackedPeriodicalIds = new Set(allTracked.map((t) => t.id));
      allPeriodicals.forEach((p) => {
        // Only include if not tracked (no tracking_id) and not already in a stack
        if (!p.tracking_id && !p.stack_id && !memberPeriodicalIds.has(p.id)) {
          availableItems.push({
            id: p.id,
            title: p.title,
            label: `${p.issue_count || 1} issue${(p.issue_count || 1) !== 1 ? 's' : ''} · Library`,
            type: 'periodical',
          });
        }
      });

      if (availableItems.length === 0) {
        availableContainer.innerHTML =
          '<p style="padding: 12px; color: var(--text-secondary)">No unassigned items available</p>';
      } else {
        availableItems.sort((a, b) => a.title.localeCompare(b.title));
        availableItems.forEach((item) => {
          const el = document.createElement('div');
          el.className = 'stack-assignment-item';
          el.style.display = 'flex';
          el.style.justifyContent = 'space-between';
          el.style.alignItems = 'center';
          el.innerHTML = `
            <span>${item.title} <small style="color: var(--text-secondary)">(${item.label})</small></span>
            <button class="btn-primary" style="padding: 4px 12px; font-size: 12px">Add</button>
          `;
          const addBtn = el.querySelector('button');
          addBtn.onclick = async () => {
            await this.addMember(stack.slug, item.id, item.type);
            await this.openAssignModal(stack); // Refresh
          };
          availableContainer.appendChild(el);
        });
      }
    }

    UIUtils.showModal('stack-assign-modal');
  }

  /**
   * Add a tracking item or periodical to a stack
   *
   * @param {string} slug - Stack slug
   * @param {number} id - Tracking ID or Periodical ID to add
   * @param {string} [type='tracking'] - 'tracking' or 'periodical'
   */
  async addMember(slug, id, type = 'tracking') {
    const payload =
      type === 'periodical' ? { periodical_ids: [id] } : { tracking_ids: [id] };

    await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.authenticatedFetch(`/api/stacks/${slug}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      return await response.json();
    }, 'Stacks');
  }

  /**
   * Remove a member from a stack
   *
   * @param {string} slug - Stack slug
   * @param {number} membershipId - Membership ID to remove
   */
  async removeMember(slug, membershipId) {
    await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.authenticatedFetch(
        `/api/stacks/${slug}/members/${membershipId}`,
        { method: 'DELETE' }
      );
      return await response.json();
    }, 'Stacks');
  }

  /**
   * Get all stacks (cached or freshly loaded)
   *
   * @returns {Promise<Array>}
   */
  async getStacks() {
    if (!this.stacksLoaded) {
      await this.loadStacks();
    }
    return this.allStacks;
  }
}

export const stacks = new StacksManager();
