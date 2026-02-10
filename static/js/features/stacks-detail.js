/**
 * Stack Detail Page Module
 * Handles the individual stack view: rendering members, searching, and downloading
 * @module stacks-detail
 */

import { AuthManager } from '../core/auth.js';
import { UIUtils } from '../core/ui-utils.js';
import { APIClient } from '../core/api.js';
import { initScrollCollapse } from '../core/scroll-collapse.js';

/** @type {boolean} Whether a search is in progress */
let isSearching = false;

/** @type {Map<number, {member: Object, availableIssues: Array}>} Search results per member index */
const memberSearchResults = new Map();

/** @type {Array} Tracked members with tracking_id */
let trackedMembers = [];

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

  // Get data from template
  const container = document.getElementById('stack-container');
  const membersData = JSON.parse(container.dataset.members || '[]');
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
    membersData.forEach((item) => {
      grid.appendChild(createMemberCard(item));
    });
  }
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
  if (item.language) {
    url += `?language=${encodeURIComponent(item.language)}`;
  }
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
  card.appendChild(cover);

  const info = document.createElement('div');
  info.className = 'periodical-info';

  const h4 = document.createElement('h4');
  h4.className = 'stack-detail-title';
  h4.textContent = item.title;
  info.appendChild(h4);

  // Badges row
  const badgesRow = document.createElement('div');
  badgesRow.className = 'stack-detail-badges';

  if (item.category) {
    const catBadge = document.createElement('span');
    catBadge.className = 'stack-detail-category-badge';
    catBadge.textContent = item.category;
    badgesRow.appendChild(catBadge);
  }

  if (item.language && item.language !== 'English') {
    const langBadge = document.createElement('span');
    langBadge.className = 'language-badge';
    langBadge.textContent = item.language;
    badgesRow.appendChild(langBadge);
  }

  if (badgesRow.children.length > 0) {
    info.appendChild(badgesRow);
  }

  // Subtitle with issue info
  const subtitle = document.createElement('p');
  subtitle.className = 'stack-detail-subtitle';
  if (item.type === 'tracking') {
    const count = item.library_count || 0;
    if (count > 0) {
      subtitle.textContent = `${count} issue${count !== 1 ? 's' : ''} in library`;
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
  searchBtn.textContent = '⏳ Searching...';
  panel.classList.remove('hidden');
  summary.classList.add('hidden');
  titleEl.textContent = `Searching ${trackedMembers.length} tracked item${trackedMembers.length !== 1 ? 's' : ''}...`;

  // Build progress rows
  progress.innerHTML = trackedMembers
    .map(
      (m, i) => `
    <div class="stack-search-row" id="search-row-${i}">
      <div class="stack-search-row-status" id="search-status-${i}">⏳</div>
      <div class="stack-search-row-title">${m.title}${m.language && m.language !== 'English' ? ` <span class="language-badge" style="font-size:9px;padding:1px 6px;margin:0">${m.language}</span>` : ''}</div>
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

    statusEl.textContent = '🔄';
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
          (r) =>
            r.status !== 'in_library' &&
            !r.already_downloaded &&
            !r.download_failed
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

          statusEl.textContent = '📥';
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
    summaryHtml += `<span class="stat stat-available">📥 <strong>${totalAvailable}</strong> new issue${totalAvailable !== 1 ? 's' : ''} available</span>`;
  } else {
    summaryHtml += `<span class="stat">✅ All up to date</span>`;
  }
  summaryHtml += `<span class="stat">📚 <strong>${totalInLibrary}</strong> already in library</span>`;
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
  searchBtn.textContent = '🔍 Search for Issues';
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
