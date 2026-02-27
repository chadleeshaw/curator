/**
 * @module periodical-rendering
 * @description Rendering engine for the periodical detail page.
 * Handles language dropdown, sort state, special edition helpers,
 * issue rendering (flat and grouped views), issue card creation,
 * and file viewer (openPDF).
 */

import { APIClient, APIHelper } from '../core/api.js';
import { UIUtils } from '../core/ui-utils.js';

/**
 * Load languages from API and populate the edit-language dropdown
 *
 * @returns {Promise<void>}
 */
export async function loadLanguageDropdown() {
  try {
    const response = await APIClient.get('/api/constants/languages');
    const data = await response.json();
    if (data.success && data.languages) {
      const dropdown = document.getElementById('edit-language');
      if (!dropdown) return;
      const currentValue = dropdown.value;
      dropdown.innerHTML = '';
      const anyOption = document.createElement('option');
      anyOption.value = '';
      anyOption.textContent = 'Any';
      dropdown.appendChild(anyOption);
      data.languages.forEach((lang) => {
        const option = document.createElement('option');
        option.value = lang;
        option.textContent = lang;
        dropdown.appendChild(option);
      });
      // Use `!== undefined` rather than a truthiness check so that an empty string
      // (selecting "Any") is preserved — `if (currentValue)` would skip restoring it.
      if (currentValue !== undefined) {
        dropdown.value = currentValue;
      }
    }
  } catch (error) {
    console.error('[Periodical] Failed to load languages:', error);
  }
}

/**
 * Update subtitle based on current sort field
 * @param {string} currentSortField
 * @param {Array} yearsData
 */
export function updateSubtitle(currentSortField, yearsData) {
  const subtitle = document.getElementById('periodical-subtitle');
  if (!subtitle) return;

  // For issue_date sort, detect if grouped by year or volume
  let issueGroupingLabel = 'Grouped by Publication Date';
  if (currentSortField === 'issue_date' && yearsData.length > 0) {
    // Check if the grouping keys look like years (numeric 4-digit) or volumes
    const firstKey = String(yearsData[0].year);
    const looksLikeYear = /^\d{4}$/.test(firstKey);
    issueGroupingLabel = looksLikeYear ? 'Grouped by Year' : 'Grouped by Volume';
  }

  const subtitles = {
    issue_date: issueGroupingLabel,
    title: 'Sorted by Title',
    volume: 'Sorted by Volume',
    added_date: 'Sorted by Date Added',
  };

  subtitle.textContent = subtitles[currentSortField] || issueGroupingLabel;
}

/**
 * Helper function to extract special edition value from data structure.
 * Checks derived_metadata (new location), extra_metadata, and metadata (legacy location).
 *
 * @param {Object} data - The periodical data object
 * @returns {string|null} The special edition name or null
 */
export function getSpecialEditionValue(data) {
  // Check derived_metadata first (new structure from file scans)
  // Note: Field was renamed from special_edition to special_edition_name
  if (data.derived_metadata?.special_edition_name?.value) {
    return data.derived_metadata.special_edition_name.value;
  }

  // Legacy field name (for backwards compatibility)
  if (data.derived_metadata?.special_edition?.value) {
    return data.derived_metadata.special_edition.value;
  }

  // Check extra_metadata (where backend stores manual toggles)
  if (data.extra_metadata?.special_edition) {
    return data.extra_metadata.special_edition;
  }

  // Fallback to metadata (legacy structure)
  if (data.metadata?.special_edition) {
    return data.metadata.special_edition;
  }

  return null;
}

/**
 * Helper function to check if an issue is marked as a special edition.
 * Only checks the explicit is_special_edition flag in derived_metadata.
 *
 * @param {Object} data - The periodical data object
 * @returns {boolean} True if this is explicitly marked as a special edition
 */
export function isSpecialEdition(data) {
  // Only check derived_metadata.is_special_edition (boolean flag)
  // Do NOT fallback to title-based keyword matching
  if (data.derived_metadata?.is_special_edition?.value !== undefined) {
    return Boolean(data.derived_metadata.is_special_edition.value);
  }

  // Default to false - only explicitly marked issues are special editions
  return false;
}

/**
 * Helper function to get volume number from periodical metadata
 * @param {Object} data - The periodical data object
 * @returns {number} The volume number or 0 if not found
 */
export function getVolumeNumber(data) {
  // Check derived_metadata first (new structure)
  const derivedVolume = data.derived_metadata?.volume?.value;
  if (derivedVolume !== undefined && derivedVolume !== null) {
    return parseInt(derivedVolume, 10) || 0;
  }

  // Check metadata (legacy structure)
  const metadataVolume = data.metadata?.volume;
  if (metadataVolume !== undefined && metadataVolume !== null) {
    return parseInt(metadataVolume, 10) || 0;
  }

  return 0;
}

/**
 * Sort issues based on current sort field and order
 * @param {Array} issues - Array of issue objects
 * @param {string} currentSortField
 * @param {boolean} sortAscending
 * @returns {Array} Sorted issues
 */
export function sortIssues(issues, currentSortField, sortAscending) {
  return issues.sort((a, b) => {
    let comparison = 0;

    switch (currentSortField) {
      case 'issue_date':
        // Primary sort by issue_date
        comparison = new Date(a.issue_date || 0) - new Date(b.issue_date || 0);

        // If both have invalid/missing dates (epoch 0), fallback to volume number
        if (comparison === 0 && (!a.issue_date || !b.issue_date)) {
          const volumeA = getVolumeNumber(a);
          const volumeB = getVolumeNumber(b);
          comparison = volumeA - volumeB;
        }
        break;
      case 'title':
        comparison = (a.special_edition_name || a.title || '').localeCompare(
          b.special_edition_name || b.title || ''
        );
        break;
      case 'volume':
        comparison = getVolumeNumber(a) - getVolumeNumber(b);
        break;
      case 'added_date':
        comparison = new Date(a.created_at || 0) - new Date(b.created_at || 0);
        break;
    }

    return sortAscending ? comparison : -comparison;
  });
}

/**
 * Render issues in a flat view (no year grouping)
 * @param {HTMLElement} container - Container element
 * @param {Array} specialEditionsData
 * @param {Array} yearsData
 * @param {string} currentSortField
 * @param {boolean} sortAscending
 * @param {Function} createIssueCard
 */
export function renderFlatView(
  container,
  specialEditionsData,
  yearsData,
  currentSortField,
  sortAscending,
  createIssueCard
) {
  // Collect all issues
  const allIssues = [];

  if (specialEditionsData && specialEditionsData.length > 0) {
    allIssues.push(...specialEditionsData);
  }

  yearsData.forEach((yearData) => {
    allIssues.push(...yearData.issues);
  });

  // Sort all issues together
  const sortedIssues = sortIssues(allIssues, currentSortField, sortAscending);

  // Create single grid
  const issuesGrid = document.createElement('div');
  issuesGrid.className = 'issues-grid';
  issuesGrid.style.marginTop = '20px';

  sortedIssues.forEach((issue) => {
    const issueCard = createIssueCard(issue);
    issuesGrid.appendChild(issueCard);
  });

  container.appendChild(issuesGrid);
}

/**
 * Render issues grouped by year
 * @param {HTMLElement} container - Container element
 * @param {Array} specialEditionsData
 * @param {Array} yearsData
 * @param {string} currentSortField
 * @param {boolean} sortAscending
 * @param {Function} createIssueCard
 */
export function renderGroupedView(
  container,
  specialEditionsData,
  yearsData,
  currentSortField,
  sortAscending,
  createIssueCard
) {
  // Render special editions section with golden highlight
  if (specialEditionsData && specialEditionsData.length > 0) {
    const specialSection = document.createElement('div');
    specialSection.className = 'year-section special-edition-section';

    const specialTitle = document.createElement('h2');
    specialTitle.className = 'year-title special-edition-title';
    specialTitle.textContent = 'Special Editions';
    specialSection.appendChild(specialTitle);

    const issuesGrid = document.createElement('div');
    issuesGrid.className = 'issues-grid';

    const sortedSpecials = sortIssues([...specialEditionsData], currentSortField, sortAscending);
    sortedSpecials.forEach((issue) => {
      const issueCard = createIssueCard(issue);
      issuesGrid.appendChild(issueCard);
    });

    specialSection.appendChild(issuesGrid);
    container.appendChild(specialSection);
  }

  // Sort years based on current sort order
  const sortedYearsData = [...yearsData].sort((a, b) => {
    const yearA = String(a.year);
    const yearB = String(b.year);
    const comparison = yearA.localeCompare(yearB, undefined, { numeric: true });
    return sortAscending ? comparison : -comparison;
  });

  // Re-render regular year sections
  sortedYearsData.forEach((yearData) => {
    const sortedIssues = sortIssues([...yearData.issues], currentSortField, sortAscending);

    const yearSection = document.createElement('div');
    yearSection.className = 'year-section';

    const yearTitle = document.createElement('h2');
    yearTitle.className = 'year-title';
    yearTitle.textContent = yearData.year;
    yearSection.appendChild(yearTitle);

    const issuesGrid = document.createElement('div');
    issuesGrid.className = 'issues-grid';

    sortedIssues.forEach((issue) => {
      const issueCard = createIssueCard(issue);
      issuesGrid.appendChild(issueCard);
    });

    yearSection.appendChild(issuesGrid);
    container.appendChild(yearSection);
  });
}

/**
 * Create an issue card DOM element
 * @param {Object} issue - Issue data object
 * @param {boolean} bulkSelectMode - Whether bulk select mode is active
 * @param {Set} selectedIssueIds - Set of currently selected issue IDs
 * @param {Function} toggleIssueSelection - Callback for toggling selection
 * @param {Function} openPDF - Callback to open PDF
 * @param {Function} viewMetadata - Callback to view metadata
 * @param {Function} deleteIssue - Callback to delete issue
 * @returns {HTMLElement}
 */
export function createIssueCard(
  issue,
  bulkSelectMode,
  selectedIssueIds,
  toggleIssueSelection,
  openPDF,
  viewMetadata,
  deleteIssue
) {
  const issueCard = document.createElement('div');
  issueCard.className = 'issue-card';
  issueCard.dataset.issueId = issue.id;

  // Bulk select checkbox (hidden by default, shown in bulk mode)
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.className = 'bulk-checkbox';
  checkbox.checked = selectedIssueIds.has(issue.id);
  checkbox.onclick = (e) => {
    e.stopPropagation();
    toggleIssueSelection(issue.id, checkbox);
  };
  issueCard.appendChild(checkbox);

  // In bulk mode, clicking the card toggles selection
  if (bulkSelectMode) {
    issueCard.classList.toggle('bulk-selected', selectedIssueIds.has(issue.id));
    issueCard.addEventListener('click', (e) => {
      if (!bulkSelectMode) return;
      // Don't toggle if clicking an action button
      if (e.target.closest('.issue-actions button')) return;
      checkbox.checked = !checkbox.checked;
      toggleIssueSelection(issue.id, checkbox);
    });
  }

  const coverDiv = document.createElement('div');
  coverDiv.className = 'issue-cover';

  if (issue.cover_url) {
    const img = document.createElement('img');
    img.src = issue.cover_url;
    img.alt = issue.title;
    img.onerror = function () {
      this.style.display = 'none';
      coverDiv.innerHTML = '<div class="issue-cover-placeholder">Cover Not Available</div>';
    };
    coverDiv.appendChild(img);
  } else {
    coverDiv.innerHTML = '<div class="issue-cover-placeholder">No Cover Available</div>';
  }

  issueCard.appendChild(coverDiv);

  const infoDiv = document.createElement('div');
  infoDiv.className = 'issue-info';

  const dateP = document.createElement('p');
  dateP.className = 'issue-date';
  dateP.textContent = issue.issue_date
    ? new Date(issue.issue_date).toLocaleDateString()
    : 'Unknown Date';
  infoDiv.appendChild(dateP);

  // Add special edition name if available
  if (issue.special_edition_name) {
    const specialEditionP = document.createElement('p');
    specialEditionP.className = 'issue-title';
    const titleCased = UIUtils.toTitleCase(issue.special_edition_name);
    specialEditionP.textContent = titleCased;
    specialEditionP.title = titleCased;
    infoDiv.appendChild(specialEditionP);
  }

  // Create actions container with View, Metadata, and Delete buttons
  const actionsDiv = document.createElement('div');
  actionsDiv.className = 'issue-actions';

  const openButton = document.createElement('button');
  openButton.className = 'open-pdf-btn';
  openButton.title = 'Open file';
  openButton.innerHTML = '📖 <span class="btn-text">Open</span>';
  openButton.onclick = (e) => {
    e.stopPropagation();
    openPDF(issue.id);
  };
  actionsDiv.appendChild(openButton);

  const metadataButton = document.createElement('button');
  metadataButton.className = 'metadata-btn';
  metadataButton.title = 'View metadata';
  metadataButton.innerHTML = 'ℹ️';
  metadataButton.onclick = (e) => {
    e.stopPropagation();
    viewMetadata(issue.id);
  };
  actionsDiv.appendChild(metadataButton);

  const deleteButton = document.createElement('button');
  deleteButton.className = 'delete-issue-btn';
  deleteButton.textContent = '🗑️';
  deleteButton.title = 'Delete this issue';
  deleteButton.onclick = (e) => {
    e.stopPropagation();
    deleteIssue(issue.id, issue.title);
  };
  actionsDiv.appendChild(deleteButton);

  infoDiv.appendChild(actionsDiv);
  issueCard.appendChild(infoDiv);

  return issueCard;
}

/**
 * Open the appropriate file viewer for a periodical
 * @param {number} periodicalId
 * @returns {Promise<void>}
 */
export async function openPDF(periodicalId) {
  try {
    // Get magazine metadata to check file type
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.get(`/api/periodicals/${periodicalId}`);
      return await response.json();
    }, 'Periodical');

    // Check file type and open appropriate reader
    if (data.file_path) {
      const filePath = data.file_path.toLowerCase();
      console.log('[Periodical] Opening file:', filePath);
      if (filePath.endsWith('.epub')) {
        console.log('[Periodical] Detected EPUB, opening EPUB reader');
        // Open EPUB reader in same window
        window.location.href = `/epub-reader?id=${periodicalId}`;
      } else if (filePath.endsWith('.cbz') || filePath.endsWith('.cbr')) {
        console.log('[Periodical] Detected comic file, opening comic reader');
        // Open comic reader in same window
        window.location.href = `/comic-reader?id=${periodicalId}`;
      } else if (filePath.endsWith('.pdf')) {
        console.log('[Periodical] Detected PDF, opening PDF reader');
        // Open PDF reader in same window
        window.location.href = `/pdf-reader?id=${periodicalId}`;
      } else {
        console.log('[Periodical] Unknown file type, opening directly');
        // Open file directly in new tab (for non-reader files)
        window.open(`/api/periodicals/${periodicalId}/pdf`, '_blank');
      }
    } else {
      console.log('[Periodical] No file_path, opening directly');
      // Fallback to opening directly in new tab
      window.open(`/api/periodicals/${periodicalId}/pdf`, '_blank');
    }
  } catch (error) {
    console.error('[Periodical] Error checking file type:', error);
    // Fallback to opening as PDF in new tab
    window.open(`/api/periodicals/${periodicalId}/pdf`, '_blank');
  }
}
