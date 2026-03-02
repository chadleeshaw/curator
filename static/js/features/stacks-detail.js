/**
 * Stack Detail Page Module
 * Handles the individual stack view: rendering members, searching, and downloading
 * @module stacks-detail
 */

import { AuthManager } from '../core/auth.js';
import { UIUtils } from '../core/ui-utils.js';
import { APIClient } from '../core/api.js';
import { initScrollCollapse } from '../core/scroll-collapse.js';
import { escapeHtml } from '../readers/reader-utils.js';

/** @type {boolean} Whether a search is in progress */
let isSearching = false;

/** @type {Map<number, {member: Object, availableIssues: Array}>} Search results per member index */
const memberSearchResults = new Map();

/** @type {Array} Tracked members with tracking_id */
let trackedMembers = [];

/** @type {Array} All members data */
let allMembersData = [];

// Sorting state
let currentSortField = localStorage.getItem('stack-sort-field') || 'title';
let sortAscending = localStorage.getItem('stack-sort-order') !== 'desc';

/**
 * Initialize the stack detail page
 * @returns {Promise<void>}
 */
export async function initStackDetail() {
  // Initialize theme
  UIUtils.initTheme();

  // Check authentication
  const isAuthenticated = await AuthManager.checkAuthentication();
  if (!isAuthenticated) {
    window.location.href = '/login.html';
    return;
  }

  // Initialize scroll-collapse behavior
  initScrollCollapse();

  // Wire up global handlers for onclick attributes
  window.goBack = goBack;
  window.searchStack = searchStack;
  window.closeSearchPanel = closeSearchPanel;
  window.downloadMemberIssues = downloadMemberIssues;
  window.downloadAllStackIssues = downloadAllStackIssues;
  window.setStackSort = setStackSort;
  window.toggleStackSortOrder = toggleStackSortOrder;

  // Get data from template
  const container = document.getElementById('stack-container');
  if (!container) return;
  const membersData = JSON.parse(container.dataset.members || '[]');
  allMembersData = membersData;

  // Set initial sort UI state
  if (document.getElementById('stack-sort-select')) {
    document.getElementById('stack-sort-select').value = currentSortField;
    document.getElementById('stack-sort-toggle').textContent = sortAscending ? '↑' : '↓';
    updateStackSubtitle();
  }
  const grid = document.getElementById('stack-periodicals-grid');
  const emptyState = document.getElementById('stack-empty-state');
  const countBadge = document.getElementById('stack-member-count');

  // Update count badge
  countBadge.textContent = `${membersData.length} item${membersData.length !== 1 ? 's' : ''}`;

  // Hide search button if no tracked members
  trackedMembers = membersData.filter((m) => m.type === 'tracking' && m.tracking_id);
  if (trackedMembers.length === 0) {
    document.getElementById('stack-search-btn').classList.add('hidden');
  }

  // Render member cards
  if (membersData.length === 0) {
    grid.classList.add('hidden');
    emptyState.classList.remove('hidden');
  } else {
    renderMembers(membersData, grid);
  }
}

/**
 * Render members with current sort
 * @param {Array} members - Members to render
 * @param {HTMLElement} grid - Grid element to render into
 */
function renderMembers(members, grid) {
  const sortedMembers = sortMembers([...members]);
  grid.innerHTML = '';
  sortedMembers.forEach((item) => {
    grid.appendChild(createMemberCard(item));
  });
}

/**
 * Update subtitle based on current sort field
 */
function updateStackSubtitle() {
  const subtitle = document.getElementById('stack-sort-subtitle');
  if (!subtitle) return;

  const subtitles = {
    title: 'Sorted by Title',
    category: 'Sorted by Category',
    library_count: 'Sorted by Number of Issues',
    latest_issue: 'Sorted by Latest Issue',
  };

  subtitle.textContent = subtitles[currentSortField] || '';
}

/**
 * Sort members based on current sort field and order
 * @param {Array} members - Array of member objects
 * @returns {Array} Sorted members
 */
function sortMembers(members) {
  return members.sort((a, b) => {
    let comparison = 0;

    switch (currentSortField) {
      case 'title':
        comparison = (a.title || '').localeCompare(b.title || '');
        break;
      case 'category':
        comparison = (a.category || '').localeCompare(b.category || '');
        break;
      case 'library_count':
        comparison = (a.library_count || 0) - (b.library_count || 0);
        break;
      case 'latest_issue':
        comparison = new Date(a.latest_issue || 0) - new Date(b.latest_issue || 0);
        break;
    }

    return sortAscending ? comparison : -comparison;
  });
}

/**
 * Set the sort field and re-render
 * @param {string} field - The field to sort by
 */
function setStackSort(field) {
  currentSortField = field;
  localStorage.setItem('stack-sort-field', field);
  updateStackSubtitle();
  const grid = document.getElementById('stack-periodicals-grid');
  grid.style.opacity = '0.5';
  grid.style.transition = 'opacity 0.2s ease';
  setTimeout(() => {
    renderMembers(allMembersData, grid);
    grid.style.opacity = '1';
  }, 100);
}

/**
 * Toggle sort order and re-render
 */
function toggleStackSortOrder() {
  sortAscending = !sortAscending;
  localStorage.setItem('stack-sort-order', sortAscending ? 'asc' : 'desc');
  document.getElementById('stack-sort-toggle').textContent = sortAscending ? '↑' : '↓';
  const grid = document.getElementById('stack-periodicals-grid');
  grid.style.opacity = '0.5';
  grid.style.transition = 'opacity 0.2s ease';
  setTimeout(() => {
    renderMembers(allMembersData, grid);
    grid.style.opacity = '1';
  }, 100);
}

/**
 * Navigate back to the library
 */
function goBack() {
  window.location.href = '/#library';
}

/**
 * Navigate to a periodical's detail page
 * @param {Object} item - The member item
 */
function navigateToItem(item) {
  let url = `/periodicals/${encodeURIComponent(item.title)}`;
  const params = new URLSearchParams();
  if (item.language) params.set('language', item.language);
  // Pass stack name and slug so the periodical breadcrumb can use them without an extra API call
  const stackNameEl = document.getElementById('stack-title');
  if (stackNameEl) params.set('from_stack_name', stackNameEl.textContent.trim());
  const slugMatch = window.location.pathname.match(/^\/stacks\/([^/]+)/);
  if (slugMatch) params.set('from_stack_slug', slugMatch[1]);
  const qs = params.toString();
  if (qs) url += `?${qs}`;
  window.location.href = url;
}

/**
 * Create a card element for a stack member
 * @param {Object} item - The member data
 * @returns {HTMLElement} The card element
 */
function createMemberCard(item) {
  const card = document.createElement('div');
  card.className = 'periodical-card stack-detail-card';
  card.onclick = () => navigateToItem(item);

  const cover = document.createElement('div');
  cover.className = 'periodical-cover';

  if (item.cover_path || item.cover_periodical_id) {
    const img = document.createElement('img');
    img.alt = item.title;
    img.loading = 'lazy';
    const coverId = item.cover_periodical_id || item.id;
    img.src = `/api/periodicals/${coverId}/cover`;
    cover.appendChild(img);
  } else {
    cover.textContent = item.title;
  }

  // Language overlay on cover (non-English only)
  if (item.language && item.language !== 'English') {
    const langOverlay = document.createElement('span');
    langOverlay.className = 'language-overlay';
    langOverlay.textContent = item.language;
    cover.appendChild(langOverlay);
  }

  // Category overlay on cover
  if (item.category) {
    const catOverlay = document.createElement('span');
    catOverlay.className = 'stack-badge-overlay';
    catOverlay.textContent = item.category;
    cover.appendChild(catOverlay);
  }

  card.appendChild(cover);

  const info = document.createElement('div');
  info.className = 'periodical-info';

  const h4 = document.createElement('h4');
  h4.className = 'stack-detail-title';
  h4.textContent = item.title;
  info.appendChild(h4);

  // Subtitle with issue info
  const subtitle = document.createElement('p');
  subtitle.className = 'stack-detail-subtitle';
  if (item.type === 'tracking') {
    const count = item.library_count || 0;
    if (count > 0) {
      subtitle.textContent = `${count} issue${count !== 1 ? 's' : ''}`;
    } else {
      subtitle.textContent = 'Tracking · no issues yet';
    }
  } else if (item.issue_date) {
    const d = new Date(item.issue_date);
    subtitle.textContent = d.toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
    });
  }
  info.appendChild(subtitle);

  // Action buttons matching library card style
  const actionsDiv = document.createElement('div');
  actionsDiv.className = 'periodical-actions';

  const openBtn = document.createElement('button');
  openBtn.className = 'btn-primary card-open-btn';
  openBtn.textContent = 'Open';
  openBtn.setAttribute('aria-label', `Open ${item.title}`);
  openBtn.onclick = (e) => {
    e.stopPropagation();
    navigateToItem(item);
  };
  actionsDiv.appendChild(openBtn);
  info.appendChild(actionsDiv);

  card.appendChild(info);

  return card;
}

/**
 * Search all tracked members in the stack for available issues
 * @returns {Promise<void>}
 */
async function searchStack() {
  if (isSearching) return;
  isSearching = true;
  memberSearchResults.clear();

  const searchBtn = document.getElementById('stack-search-btn');
  const panel = document.getElementById('stack-search-panel');
  const progress = document.getElementById('stack-search-progress');
  const summary = document.getElementById('stack-search-summary');
  const titleEl = document.getElementById('stack-search-title');

  searchBtn.disabled = true;
  searchBtn.innerHTML =
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M8 16H3v5"/></svg> Searching...';
  panel.classList.remove('hidden');
  summary.classList.add('hidden');
  titleEl.textContent = `Searching ${trackedMembers.length} tracked item${trackedMembers.length !== 1 ? 's' : ''}...`;

  // Build progress rows
  progress.innerHTML = trackedMembers
    .map(
      (m, i) => `
    <div class="stack-search-row" id="search-row-${i}">
      <div class="stack-search-row-status" id="search-status-${i}">⏳</div>
      <div class="stack-search-row-title">${escapeHtml(m.title)}${m.language && m.language !== 'English' ? ` <span class="language-badge" style="font-size:9px;padding:1px 6px;margin:0">${escapeHtml(m.language)}</span>` : ''}</div>
      <div class="stack-search-row-actions" id="search-actions-${i}"></div>
      <div class="stack-search-row-result" id="search-result-${i}">Waiting...</div>
    </div>`
    )
    .join('');

  let totalAvailable = 0;
  let totalInLibrary = 0;
  let totalErrors = 0;

  // Search each tracked member sequentially
  for (let i = 0; i < trackedMembers.length; i++) {
    const member = trackedMembers[i];
    const statusEl = document.getElementById(`search-status-${i}`);
    const resultEl = document.getElementById(`search-result-${i}`);
    const actionsEl = document.getElementById(`search-actions-${i}`);
    const rowEl = document.getElementById(`search-row-${i}`);

    statusEl.innerHTML =
      '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>';
    resultEl.textContent = 'Searching...';
    rowEl.classList.add('searching');

    try {
      const params = new URLSearchParams();
      params.append('query', member.title);
      params.append('tracking_id', member.tracking_id);
      if (member.language) params.append('language', member.language);
      if (member.country) params.append('country', member.country);
      if (member.category) params.append('category', member.category);

      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/search-providers?${params.toString()}`,
        { method: 'POST' }
      );
      const data = await response.json();

      rowEl.classList.remove('searching');

      if (data.found && data.results) {
        const inLib = data.results.filter(
          (r) => r.status === 'in_library' || r.already_downloaded
        ).length;
        const availableIssues = data.results.filter(
          (r) => r.status !== 'in_library' && !r.already_downloaded && !r.download_failed
        );
        const available = availableIssues.length;
        totalAvailable += available;
        totalInLibrary += inLib;

        if (available > 0) {
          // Store for bulk download
          memberSearchResults.set(i, {
            member,
            availableIssues: availableIssues
              .map((r) => ({
                title: r.title,
                url: r.url || r.download_url || r.nzb_url || r.link,
                provider: r.provider || 'newsnab',
              }))
              .filter((issue) => issue.url),
          });

          statusEl.innerHTML =
            '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 17V3"/><path d="m6 11 6 6 6-6"/><path d="M19 21H5"/></svg>';
          resultEl.innerHTML = `<strong>${available}</strong> available, ${inLib} in library`;
          actionsEl.innerHTML = `<button class="stack-search-dl-btn" onclick="downloadMemberIssues(${i})" title="Download ${available} issues">⬇ ${available}</button>`;
          rowEl.classList.add('has-results');
        } else {
          statusEl.textContent = '✅';
          resultEl.textContent = `${inLib} in library, nothing new`;
          rowEl.classList.add('complete');
        }
      } else {
        statusEl.textContent = '➖';
        resultEl.textContent = 'No results';
        rowEl.classList.add('complete');
      }
    } catch (err) {
      console.error(`Search error for ${member.title}:`, err);
      statusEl.textContent = '❌';
      resultEl.textContent = 'Error';
      rowEl.classList.remove('searching');
      rowEl.classList.add('error');
      totalErrors++;
    }
  }

  // Show summary
  titleEl.textContent = 'Search Complete';
  summary.classList.remove('hidden');
  let summaryHtml = `<div class="stack-search-stats">`;
  if (totalAvailable > 0) {
    summaryHtml += `<span class="stat stat-available"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 17V3"/><path d="m6 11 6 6 6-6"/><path d="M19 21H5"/></svg> <strong>${totalAvailable}</strong> new issue${totalAvailable !== 1 ? 's' : ''} available</span>`;
  } else {
    summaryHtml += `<span class="stat">✅ All up to date</span>`;
  }
  summaryHtml += `<span class="stat"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H19a1 1 0 0 1 1 1v18a1 1 0 0 1-1 1H6.5a1 1 0 0 1 0-5H20"/></svg> <strong>${totalInLibrary}</strong> already in library</span>`;
  if (totalErrors > 0) {
    summaryHtml += `<span class="stat stat-error">❌ ${totalErrors} error${totalErrors !== 1 ? 's' : ''}</span>`;
  }
  summaryHtml += `</div>`;
  if (totalAvailable > 0) {
    summaryHtml += `<div class="stack-search-actions-bar">`;
    summaryHtml += `<button class="stack-search-dl-all-btn" onclick="downloadAllStackIssues()" id="dl-all-btn">⬇ Download All ${totalAvailable} Issues</button>`;
    summaryHtml += `</div>`;
  }
  summary.innerHTML = summaryHtml;

  searchBtn.disabled = false;
  searchBtn.innerHTML =
    '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg> Search for Issues';
  isSearching = false;
}

/**
 * Download all available issues for a single tracked member
 * @param {number} memberIdx - The index of the member in trackedMembers
 * @returns {Promise<void>}
 */
async function downloadMemberIssues(memberIdx) {
  const entry = memberSearchResults.get(memberIdx);
  if (!entry || entry.availableIssues.length === 0) return;

  const btn = document.querySelector(`#search-actions-${memberIdx} .stack-search-dl-btn`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳';
  }

  try {
    const response = await APIClient.authenticatedFetch('/api/downloads/batch-issues', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        tracking_id: entry.member.tracking_id,
        issues: entry.availableIssues,
      }),
    });
    const data = await response.json();

    const parts = [];
    if (data.submitted > 0) parts.push(`${data.submitted} sent`);
    if (data.queued > 0) parts.push(`${data.queued} queued`);
    if (data.skipped > 0) parts.push(`${data.skipped} skipped`);
    if (data.failed > 0) parts.push(`${data.failed} failed`);

    if (btn) {
      const hasErrors = data.failed > 0;
      btn.textContent = hasErrors ? '⚠️' : '✅';
      btn.title = parts.join(', ');
      btn.classList.add(hasErrors ? 'dl-warning' : 'dl-done');
    }

    // Remove from available set so Download All skips these
    memberSearchResults.delete(memberIdx);
  } catch (err) {
    console.error(`Download error for member ${memberIdx}:`, err);
    if (btn) {
      btn.textContent = '❌';
      btn.title = err.message;
      btn.disabled = false;
    }
  }
}

/**
 * Download all available issues across all tracked members in the stack
 * @returns {Promise<void>}
 */
async function downloadAllStackIssues() {
  const dlAllBtn = document.getElementById('dl-all-btn');
  if (dlAllBtn) {
    dlAllBtn.disabled = true;
    dlAllBtn.textContent = '⏳ Downloading...';
  }

  let totalSubmitted = 0;
  let totalQueued = 0;
  let totalSkipped = 0;
  let totalFailed = 0;

  // Iterate over remaining members with results
  const entries = [...memberSearchResults.entries()];
  for (const [idx, entry] of entries) {
    const btn = document.querySelector(`#search-actions-${idx} .stack-search-dl-btn`);
    if (btn) {
      btn.disabled = true;
      btn.textContent = '⏳';
    }

    try {
      const response = await APIClient.authenticatedFetch('/api/downloads/batch-issues', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tracking_id: entry.member.tracking_id,
          issues: entry.availableIssues,
        }),
      });
      const data = await response.json();

      totalSubmitted += data.submitted || 0;
      totalQueued += data.queued || 0;
      totalSkipped += data.skipped || 0;
      totalFailed += data.failed || 0;

      if (btn) {
        const hasErrors = data.failed > 0;
        btn.textContent = hasErrors ? '⚠️' : '✅';
        btn.classList.add(hasErrors ? 'dl-warning' : 'dl-done');
      }

      memberSearchResults.delete(idx);
    } catch (err) {
      console.error(`Download error for ${entry.member.title}:`, err);
      totalFailed += entry.availableIssues.length;
      if (btn) {
        btn.textContent = '❌';
        btn.disabled = false;
      }
    }
  }

  // Update the Download All button with results
  if (dlAllBtn) {
    const parts = [];
    if (totalSubmitted > 0) parts.push(`${totalSubmitted} sent`);
    if (totalQueued > 0) parts.push(`${totalQueued} queued`);
    if (totalSkipped > 0) parts.push(`${totalSkipped} skipped`);
    if (totalFailed > 0) parts.push(`${totalFailed} failed`);
    const hasErrors = totalFailed > 0;
    dlAllBtn.textContent = `${hasErrors ? '⚠️' : '✅'} ${parts.join(', ')}`;
    dlAllBtn.classList.add(hasErrors ? 'dl-warning' : 'dl-done');
  }
}

/**
 * Close the search progress panel
 */
function closeSearchPanel() {
  document.getElementById('stack-search-panel').classList.add('hidden');
}
