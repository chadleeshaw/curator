/**
 * Tracking Module
 * Handles periodical tracking, metadata search, and issue downloads
 *
 * NOTE: This is a working skeleton extracted from script.js lines 620-1650
 * Contains core functionality - may need additional methods added
 */

import { APIClient } from './api.js';
import { UIUtils, SortManager } from './ui-utils.js';

export class TrackingManager {
  constructor() {
    this.sortManager = new SortManager('title', 'asc', () => this.loadTrackedPeriodicals());
    this.currentPeriodicalMetadata = null;
    this.currentEditionsData = null;
    this.selectedEditions = {};
    this.mergeMode = false;
    this.selectedForMerge = new Set();
  }

  /**
   * Search for periodical metadata
   */
  async searchPeriodicalMetadata() {
    const query = document.getElementById('tracking-search-query').value.trim();

    if (!query) {
      UIUtils.showStatus('tracking-status', 'Please enter a periodical title', 'error');
      return;
    }

    const loading = document.getElementById('tracking-search-loading');
    const result = document.getElementById('tracking-search-result');
    const error = document.getElementById('tracking-search-error');

    loading.classList.remove('hidden');
    result.classList.add('hidden');
    error.classList.add('hidden');

    try {
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/search-providers?query=${encodeURIComponent(query)}`,
        { method: 'POST' }
      );
      const data = await response.json();

      if (!response.ok) {
        error.textContent = data.detail || `Error: ${response.status}`;
        error.classList.remove('hidden');
        return;
      }

      if (data.found && data.results && data.results.length > 0) {
        this.displaySearchResultsGrouped(data.results);
        result.classList.remove('hidden');
      } else {
        error.textContent = data.message || 'Periodical not found';
        error.classList.remove('hidden');
      }
    } catch (err) {
      console.error('Search error:', err);
      error.textContent = err.message;
      error.classList.remove('hidden');
    } finally {
      loading.classList.add('hidden');
    }
  }

  /**
   * Display search results grouped by edition
   */
  displaySearchResultsGrouped(results) {
    const container = document.getElementById('tracking-search-result');

    // Extract unique periodical editions and group results
    const uniquePeriodicals = {};

    results.forEach((result) => {
      // Extract clean title from the result title/filename
      let cleanTitle = result.title;

      // Extract periodical name from filename (e.g., "PC.Gamer.US.No.405..." -> "PC Gamer US")
      const match = result.title.match(/^([A-Za-z0-9\.\s]+?)(?:\.No\.|\.Issue\.|\.E|\.201|\.202)/i);
      if (match) {
        cleanTitle = match[1].replace(/\./g, ' ').trim();
      }

      // Normalize title for deduplication
      const normalizedKey = cleanTitle.toLowerCase().replace(/\s+/g, ' ').trim();

      if (!uniquePeriodicals[normalizedKey]) {
        uniquePeriodicals[normalizedKey] = {
          displayTitle: cleanTitle,
          count: 0,
          firstResult: result,
        };
      }
      uniquePeriodicals[normalizedKey].count++;
    });

    // Convert to array and sort by count (most common first)
    const periodicalsList = Object.values(uniquePeriodicals).sort((a, b) => b.count - a.count);

    container.innerHTML = '<h4>Select a Periodical Edition:</h4><div class="search-results"></div>';
    const resultsContainer = container.querySelector('.search-results');

    periodicalsList.forEach((periodical) => {
      const result = periodical.firstResult;
      const publisher = result.metadata?.publisher || '';

      const div = document.createElement('div');
      div.className = 'result-item';
      div.style.padding = '15px';
      div.style.margin = '10px 0';
      div.style.border = '1px solid var(--border-color)';
      div.style.borderRadius = '8px';
      div.style.cursor = 'pointer';
      div.style.background = 'var(--surface)';
      div.style.display = 'flex';
      div.style.justifyContent = 'space-between';
      div.style.alignItems = 'center';

      div.innerHTML = `
        <div class="result-info">
          <h5 style="margin: 0 0 8px 0;">${periodical.displayTitle}</h5>
          <p style="margin: 4px 0; color: var(--text-secondary);">
            <strong>Available Issues:</strong> ${periodical.count}
          </p>
          ${publisher ? `<p style="margin: 4px 0; color: var(--text-secondary);"><strong>Publisher:</strong> ${publisher}</p>` : ''}
        </div>
        <div class="result-select" style="font-size: 24px; color: var(--primary);">→</div>
      `;

      div.onclick = () =>
        this.chooseSearchResult({
          ...result,
          title: periodical.displayTitle, // Override with clean title
          publisher: publisher || '', // Empty string if no publisher metadata
        });

      resultsContainer.appendChild(div);
    });
  }

  /**
   * Display search results for user to select
   */
  displaySearchResults(results) {
    const container = document.getElementById('tracking-search-result');
    container.innerHTML = '<h4>Select a Periodical:</h4>';

    results.forEach((result, _index) => {
      const div = document.createElement('div');
      div.style.padding = '15px';
      div.style.margin = '10px 0';
      div.style.border = '1px solid var(--border-color)';
      div.style.borderRadius = '8px';
      div.style.cursor = 'pointer';
      div.style.background = 'var(--surface)';

      div.innerHTML = `
        <h5>${result.title}</h5>
        <p>${result.publisher || 'Unknown Publisher'}</p>
        <p style="color: var(--text-secondary);">${result.source || ''}</p>
      `;

      div.onclick = () => this.chooseSearchResult(result);
      container.appendChild(div);
    });
  }

  /**
   * User selected a search result
   */
  async chooseSearchResult(result) {
    this.currentPeriodicalMetadata = result;

    // Hide the search results
    document.getElementById('tracking-search-result').classList.add('hidden');

    // Show Step 3 (Save Preferences)
    const saveStep = document.getElementById('save-step');
    const saveInfo = document.getElementById('save-info');

    saveInfo.innerHTML = `
      <div style="padding: 15px; background: var(--surface); border-radius: 8px; border: 1px solid var(--border-color);">
        <h4 style="margin: 0 0 8px 0;">${result.title}</h4>
        <p style="margin: 4px 0; color: var(--text-secondary);">
          <strong>Publisher:</strong> ${result.publisher || 'Unknown'}
        </p>
      </div>
    `;

    saveStep.classList.remove('hidden');

    // Scroll to the save step
    saveStep.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  /**
   * Save tracking preferences
   */
  async saveTrackingPreferences() {
    if (!this.currentPeriodicalMetadata) {
      UIUtils.showStatus('tracking-status', 'No periodical selected', 'error');
      return;
    }

    // Get tracking mode from radio buttons
    const trackingModeElement = document.querySelector('input[name="tracking-mode"]:checked');
    const trackingMode = trackingModeElement ? trackingModeElement.value : 'all';

    // Generate olid from title if not present
    const olid =
      this.currentPeriodicalMetadata.olid ||
      this.currentPeriodicalMetadata.title
        .toLowerCase()
        .replace(/\s+/g, '_')
        .replace(/[^a-z0-9_]/g, '');

    const preferences = {
      olid: olid,
      title: this.currentPeriodicalMetadata.title,
      publisher: this.currentPeriodicalMetadata.publisher || '',
      issn: this.currentPeriodicalMetadata.issn || null,
      first_publish_year: this.currentPeriodicalMetadata.first_publish_year || null,
      track_all_editions: trackingMode === 'all',
      track_new_only: trackingMode === 'new',
      selected_editions: {},
      selected_years: [],
      metadata: this.currentPeriodicalMetadata,
    };

    try {
      const response = await APIClient.post('/api/periodicals/tracking/save', preferences);
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('tracking-status', 'Tracking saved successfully', 'success');

        // Close modal and reload
        this.closeTrackNewPeriodicalModal();
        this.loadTrackedPeriodicals();

        setTimeout(() => {
          UIUtils.hideStatus('tracking-status');
        }, 2000);
      } else {
        UIUtils.showStatus('tracking-status', data.message || 'Error saving tracking', 'error');
      }
    } catch (error) {
      console.error('Error saving tracking:', error);
      UIUtils.showStatus('tracking-status', `Error: ${error.message}`, 'error');
    }
  }

  /**
   * Load tracked periodicals
   */
  async loadTrackedPeriodicals() {
    try {
      const { field, order } = this.sortManager.getSortParams();
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/tracking?sort_by=${field}&sort_order=${order}`
      );
      const data = await response.json();

      const container = document.getElementById('tracked-list');
      container.innerHTML = '';

      const tracked = data.tracked_magazines || data.tracked || [];
      if (tracked.length === 0) {
        container.innerHTML = '<p>No tracked periodicals yet</p>';
        return;
      }

      tracked.forEach((trackingItem) => {
        container.appendChild(this.createTrackedCard(trackingItem));
      });
    } catch (error) {
      console.error('Error loading tracked periodicals:', error);
    }
  }

  /**
   * Create a tracked periodical card
   */
  createTrackedCard(tracked) {
    const card = document.createElement('div');
    card.className = 'tracked-card';
    card.dataset.trackingId = tracked.id;

    // Determine tracking icon and label
    let trackingIcon = '👁️';
    let trackingLabel = 'Watched';
    if (tracked.track_all_editions) {
      trackingIcon = '⬇️';
      trackingLabel = 'All Issues';
    } else if (tracked.track_new_only) {
      trackingIcon = '⬇️';
      trackingLabel = 'New Issues';
    }

    const checkboxHtml = this.mergeMode 
      ? `<input type="checkbox" class="merge-checkbox" data-tracking-id="${tracked.id}" ${this.selectedForMerge.has(tracked.id) ? 'checked' : ''}>` 
      : '';

    card.innerHTML = `
      ${checkboxHtml}
      <div class="tracked-card-info">
        <h5>${tracked.title}</h5>
        <p>Publisher: ${tracked.publisher || 'Unknown'}</p>
        <p>ISSN: ${tracked.issn || 'N/A'}</p>
        <p class="tracking-mode">${trackingIcon} ${trackingLabel}</p>
      </div>
      <div class="tracked-card-buttons">
        <button onclick="editTracking(${tracked.id})" class="btn-small">✏️ Edit</button>
        <button onclick='searchForIssues(${tracked.id}, "${tracked.title.replace(/"/g, '&quot;').replace(/'/g, '&#39;')}")' class="btn-small">🔍 Search Issues</button>
        <button onclick='deleteTracking(${tracked.id}, "${tracked.title.replace(/"/g, '&quot;').replace(/'/g, '&#39;')}")' class="btn-small btn-danger">🗑️ Delete</button>
      </div>
    `;

    // Add event listener for checkbox if in merge mode
    if (this.mergeMode) {
      const checkbox = card.querySelector('.merge-checkbox');
      checkbox.addEventListener('change', (e) => {
        if (e.target.checked) {
          this.selectedForMerge.add(tracked.id);
        } else {
          this.selectedForMerge.delete(tracked.id);
        }
        this.updateMergeButtonState();
      });
    }

    return card;
  }

  /**
   * Set sort field for tracked periodicals
   */
  setSortField(field) {
    this.sortManager.field = field;
    this.sortManager.order = 'asc';

    document.querySelectorAll('.sort-controls .sort-btn').forEach((btn) => {
      btn.classList.remove('active');
    });
    const activeBtn = document.querySelector(`.sort-controls [data-sort="${field}"]`);
    if (activeBtn) {
      activeBtn.classList.add('active');
    }

    this.updateSortToggleButton();
    this.loadTrackedPeriodicals();
  }

  /**
   * Toggle sort order
   */
  toggleSortOrder() {
    this.sortManager.order = this.sortManager.order === 'asc' ? 'desc' : 'asc';
    this.updateSortToggleButton();
    this.loadTrackedPeriodicals();
  }

  /**
   * Update sort toggle button
   */
  updateSortToggleButton() {
    const btn = document.getElementById('tracking-sort-toggle');
    if (btn) {
      btn.textContent = this.sortManager.order === 'asc' ? '↑' : '↓';
    }
  }

  /**
   * Update merge button state based on selection
   */
  updateMergeButtonState() {
    const mergeBtn = document.getElementById('execute-merge-btn');
    if (mergeBtn) {
      mergeBtn.disabled = this.selectedForMerge.size < 2;
      mergeBtn.textContent = `Merge Selected (${this.selectedForMerge.size})`;
    }
  }

  /**
   * Edit tracking details - shows modal with current data
   */
  async editTracking(trackingId) {
    try {
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/tracking/${trackingId}`
      );
      const data = await response.json();

      if (data.success) {
        const t = data.tracking;

        // Populate modal with tracking data
        document.getElementById('edit-tracking-id').value = trackingId;
        document.getElementById('edit-tracking-title').value = t.title || '';
        document.getElementById('edit-tracking-publisher').value = t.publisher || '';
        document.getElementById('edit-tracking-issn').value = t.issn || '';

        // Set tracking mode
        let mode = 'none';
        if (t.track_all_editions) mode = 'all';
        else if (t.track_new_only) mode = 'new';
        document.getElementById('edit-tracking-mode').value = mode;

        // Set delete from client checkbox
        document.getElementById('edit-delete-from-client').checked =
          t.delete_from_client_on_completion || false;

        // Set organization pattern
        document.getElementById('edit-tracking-org-pattern').value = t.organization_pattern || '';

        // Show modal
        document.getElementById('edit-tracking-modal').classList.remove('hidden');
      }
    } catch (err) {
      console.error('Error loading tracking details:', err);
      UIUtils.showStatus('tracking-status', 'Failed to load tracking details', 'error');
    }
  }

  /**
   * Search for issues of a tracked periodical
   */
  async searchForIssues(trackingId, title) {
    try {
      // Show loading spinner
      const issuesContent = document.getElementById('search-issues-content');
      issuesContent.innerHTML = `
        <div style="text-align: center; padding: 60px;">
          <div class="loading-spinner"></div>
          <p style="margin-top: 20px; color: var(--text-secondary);">Searching for issues...</p>
        </div>`;
      document.getElementById('search-issues-modal').classList.remove('hidden');

      // Store tracking_id for later use in downloadIssue
      window.currentTrackingId = trackingId;

      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/search-providers?query=${encodeURIComponent(title)}`,
        { method: 'POST' }
      );
      const data = await response.json();

      if (data.found && data.results.length > 0) {
        // Parse and curate results
        const curatedIssues = this.parseAndCurateIssues(data.results);
        this.displayCuratedIssues(curatedIssues, title);
      } else {
        let errorInfo = '';
        if (data.provider_errors && data.provider_errors.length > 0) {
          errorInfo = `<div style="margin-top: 15px; padding: 10px; background: #ffebee; color: var(--error-color); border-radius: 4px; font-size: 0.9em;"><strong>Provider Errors:</strong><br>${data.provider_errors.join('<br>')}</div>`;
        }
        issuesContent.innerHTML = `<div style="text-align: center; padding: 40px;"><p>No issues found for "${title}"</p>${errorInfo}</div>`;
      }
    } catch (err) {
      console.error('Error searching issues:', err);
      const issuesContent = document.getElementById('search-issues-content');
      issuesContent.innerHTML = `<div style="text-align: center; padding: 40px; color: var(--error-color);"><p>Failed to search for issues</p><p style="font-size: 0.9em; margin-top: 10px;">${err.message}</p></div>`;
    }
  }

  /**
   * Parse and organize issues by year
   */
  parseAndCurateIssues(results) {
    const _issues = [];
    const issueMap = new Map();

    results.forEach((result) => {
      const parsed = this.parseIssueTitle(result.title);
      if (parsed) {
        // If month/issue not found in title, try to extract from publication_date
        if (parsed.month === 0 && result.publication_date) {
          try {
            const pubDate = new Date(result.publication_date);
            if (!isNaN(pubDate.getTime())) {
              parsed.month = pubDate.getMonth() + 1; // getMonth() returns 0-11
            }
          } catch (e) {
            // Ignore date parsing errors
          }
        }

        // Create unique key including season and title to avoid over-deduplication
        // Include the original title hash to ensure different issues don't collide
        const titleHash = result.title.replace(/\s+/g, '-').substring(0, 30);
        const key = `${parsed.year}-${parsed.month}-${parsed.issue}-${parsed.season || ''}-${titleHash}`;

        if (!issueMap.has(key)) {
          // Extract language variant from title if present
          const langMatch = result.title.match(
            /\b(German|Dutch|French|Spanish|Italian|English|DE|NL|FR|ES|IT|EN|USA|UK)\b/i
          );
          const language = langMatch ? langMatch[0] : '';

          issueMap.set(key, {
            ...parsed,
            title: result.title,
            provider: result.provider,
            url: result.url,
            publication_date: result.publication_date,
            already_downloaded: result.already_downloaded || false,
            language: language,
            variants: [result], // Store all variants
          });
        } else {
          // Add to variants if it's a different language edition
          const existing = issueMap.get(key);
          existing.variants.push(result);

          // If already downloaded, mark the combined entry as downloaded
          if (result.already_downloaded) {
            existing.already_downloaded = true;
          }
        }
      }
    });

    // Sort by year desc, month desc, issue desc
    const sortedIssues = Array.from(issueMap.values()).sort((a, b) => {
      if (b.year !== a.year) return b.year - a.year;
      if (b.month !== a.month) return b.month - a.month;
      return b.issue - a.issue;
    });

    // Group by year
    const grouped = {};
    sortedIssues.forEach((issue) => {
      if (!grouped[issue.year]) {
        grouped[issue.year] = [];
      }
      grouped[issue.year].push(issue);
    });

    return grouped;
  }

  /**
   * Parse issue title to extract year, month, issue number, season
   */
  parseIssueTitle(title) {
    let year = null;
    let issue = null;
    let month = null;
    let season = null;

    // First, try to extract season
    const seasonMatch = title.match(/\b(Spring|Summer|Fall|Autumn|Winter)\b/i);
    if (seasonMatch) {
      season = seasonMatch[1].charAt(0).toUpperCase() + seasonMatch[1].slice(1).toLowerCase();
    }

    // Extract year-month pattern (e.g., "2007-11" or "2007 11")
    const yearMonthMatch = title.match(/(\d{4})[\s.-](\d{1,2})(?:\D|$)/);
    if (yearMonthMatch) {
      year = parseInt(yearMonthMatch[1]);
      const num = parseInt(yearMonthMatch[2]);
      if (num >= 1 && num <= 12) {
        month = num;
      }
    }

    // If no year-month found, try other patterns
    if (!year) {
      const patterns = [
        /(?:No\.|Issue|#)\.?(\d+)\.?(\d{4})/, // No.405.2026 or Issue.12.2025
        /(\d{4})[\s.](?:Issue|No\.)?[\s.]?(\d+)/, // 2026 No. 405 or 2026 405
        /Vol\.?(\d+).*?(\d{4})/, // Vol.123 2026
        /(\d{4})/, // Just a year
      ];

      for (const pattern of patterns) {
        const match = title.match(pattern);
        if (match) {
          if (match.length === 2) {
            const num = parseInt(match[1]);
            if (num > 1900 && num < 2100) {
              year = num;
              break;
            }
          } else {
            const num1 = parseInt(match[1]);
            const num2 = parseInt(match[2]);

            if (num2 > 1900 && num2 < 2100) {
              year = num2;
              issue = num1;
            } else if (num1 > 1900 && num1 < 2100) {
              year = num1;
              issue = num2;
            }

            if (year) break;
          }
        }
      }
    }

    // Try to extract month name (only if not already found)
    if (!month) {
      const monthMatch = title.match(
        /\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b/i
      );
      if (monthMatch) {
        const monthNames = [
          'january',
          'february',
          'march',
          'april',
          'may',
          'june',
          'july',
          'august',
          'september',
          'october',
          'november',
          'december',
        ];
        const monthAbbr = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
        const lowerMonth = monthMatch[1].toLowerCase();
        month = monthNames.indexOf(lowerMonth) + 1 || monthAbbr.indexOf(lowerMonth) + 1 || 0;
      }
    }

    if (year) {
      return { year, issue: issue || 0, month: month || 0, season: season || null };
    }

    return null;
  }

  /**
   * Toggle tracking for a single issue
   */
  async toggleIssueTracking(trackingId, editionId, track) {
    try {
      const response = await APIClient.authenticatedFetch(
        `/api/periodicals/tracking/${trackingId}/editions/${editionId}/track?track=${track}`,
        { method: 'POST' }
      );
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus(
          'tracking-status',
          `Issue ${track ? 'marked for' : 'removed from'} tracking (${data.total_selected} total)`,
          'success'
        );
        setTimeout(() => UIUtils.hideStatus('tracking-status'), 2000);
        return true;
      } else {
        throw new Error(data.message || 'Failed to update tracking');
      }
    } catch (error) {
      console.error('Error toggling issue tracking:', error);
      UIUtils.showStatus('tracking-status', `Error: ${error.message}`, 'error');
      return false;
    }
  }

  /**
   * Display curated issues grouped by year
   */
  displayCuratedIssues(groupedByYear, title) {
    const issuesContent = document.getElementById('search-issues-content');

    if (Object.keys(groupedByYear).length === 0) {
      issuesContent.innerHTML = `<div style="text-align: center; padding: 40px;"><p>No issues could be parsed for "${title}"</p></div>`;
      return;
    }

    let html = `<h3>Available Issues for "${title}"</h3><div style="max-height: 70vh; overflow-y: auto;">`;

    const years = Object.keys(groupedByYear).sort((a, b) => b - a);

    years.forEach((year) => {
      const issues = groupedByYear[year];
      html += `<div style="margin-bottom: 20px;">
        <h4 style="color: var(--primary-color); margin-bottom: 10px;">📅 ${year}</h4>
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 10px;">`;

      issues.forEach((issue) => {
        // Create display label based on available information
        let displayLabel;
        
        // Priority 1: Season (if present)
        if (issue.season) {
          displayLabel = issue.season;
        }
        // Priority 2: Month and Issue
        else if (issue.month > 0 && issue.issue > 0) {
          const monthNames = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
          displayLabel = `${monthNames[issue.month]} #${issue.issue}`;
        } 
        // Priority 3: Month only
        else if (issue.month > 0) {
          const monthNames = ['', 'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
          displayLabel = monthNames[issue.month];
        } 
        // Priority 4: Issue number only
        else if (issue.issue > 0) {
          displayLabel = `#${issue.issue}`;
        } 
        // Fallback: Just show year (shouldn't happen often now)
        else {
          displayLabel = `${issue.year}`;
        }

        const isLibraryOnly = !issue.url || issue.url === '';
        const isDownloaded = issue.already_downloaded;

        const backgroundColor = isLibraryOnly ? 'var(--surface)' : 'var(--surface-variant)';
        const borderColor = isLibraryOnly
          ? 'var(--border-color)'
          : isDownloaded
            ? '#4caf50'
            : 'transparent';
        const opacity = isLibraryOnly ? '0.85' : isDownloaded ? '0.7' : '1';
        const textColor = isLibraryOnly ? 'var(--text-secondary)' : 'var(--text-primary)';

        const providerDisplay = isLibraryOnly
          ? ''
          : `<div style="font-size: 10px; color: var(--text-secondary); margin-top: 6px;">${issue.provider}</div>`;
        const statusBadge = isLibraryOnly
          ? '<div style="font-size: 10px; margin-top: 6px; color: var(--text-secondary); font-weight: 600;">📚 In Library</div>'
          : isDownloaded
            ? '<div style="font-size: 10px; margin-top: 6px; color: #4caf50; font-weight: 600;">✓ Have</div>'
            : '';

        // Show language variants badge if multiple editions exist
        const variantsBadge =
          issue.variants && issue.variants.length > 1
            ? `<div style="font-size: 10px; margin-top: 6px; color: var(--primary-color); font-weight: 600;">🌍 ${issue.variants.length} editions</div>`
            : issue.language
              ? `<div style="font-size: 10px; margin-top: 6px; color: var(--text-secondary);">${issue.language}</div>`
              : '';

        let cardHtml = `<div style="
          padding: 12px;
          background: ${backgroundColor};
          border-radius: 5px;
          text-align: center;
          cursor: ${isLibraryOnly ? 'default' : 'pointer'};
          transition: all 0.2s;
          border: 2px solid ${borderColor};
          opacity: ${opacity};
          color: ${textColor};
        "`;

        if (!isLibraryOnly) {
          // Store variants globally for selection
          const issueKey = `${issue.year}-${issue.month}-${issue.issue}`;
          window.issueVariants = window.issueVariants || {};
          window.issueVariants[issueKey] = issue.variants;

          cardHtml += ` onmouseover="this.style.background='var(--primary-color)'; this.style.color='white'; this.style.opacity='1';" onmouseout="this.style.background='var(--surface-variant)'; this.style.color='inherit'; this.style.opacity='${opacity}';" onclick='selectIssueWithVariants("${issueKey}", ${isDownloaded})'`;
        }

        cardHtml += `>
          <div style="font-weight: 600; font-size: 14px;">${displayLabel}</div>
          ${providerDisplay}
          ${statusBadge}
          ${variantsBadge}
        </div>`;

        html += cardHtml;
      });

      html += `</div></div>`;
    });

    html += `</div>`;
    issuesContent.innerHTML = html;
  }

  /**
   * Delete tracking
   */
  async deleteTracking(trackingId, title) {
    // Show confirmation modal with periodical name
    const confirmed = await UIUtils.confirm(
      'Remove Tracking',
      `Are you sure you want to remove "${title}" from tracking?`
    );
    if (!confirmed) return;

    try {
      const response = await APIClient.delete(`/api/periodicals/tracking/${trackingId}`);
      const data = await response.json();

      if (data.success) {
        UIUtils.showStatus('tracking-status', 'Tracking removed', 'success');
        this.loadTrackedPeriodicals();
        setTimeout(() => UIUtils.hideStatus('tracking-status'), 3000);
      } else {
        UIUtils.showStatus('tracking-status', data.message || 'Error removing tracking', 'error');
      }
    } catch (error) {
      console.error('Error deleting tracking:', error);
      UIUtils.showStatus('tracking-status', 'Error removing tracking', 'error');
    }
  }

  /**
   * Reset the tracking workflow
   */
  resetTracking() {
    this.currentPeriodicalMetadata = null;
    document.getElementById('tracking-search-query').value = '';
    document.getElementById('tracking-search-result').classList.add('hidden');
    document.getElementById('tracking-search-error').classList.add('hidden');
    document.getElementById('save-step').classList.add('hidden');
  }

  /**
   * Open track new periodical modal
   */
  openTrackNewPeriodicalModal() {
    this.resetTracking();
    document.getElementById('track-new-periodical-modal').classList.remove('hidden');
  }

  /**
   * Close track new periodical modal
   */
  closeTrackNewPeriodicalModal() {
    document.getElementById('track-new-periodical-modal').classList.add('hidden');
    this.resetTracking();
  }

  /**
   * Update tracking mode (called when radio buttons change)
   */
  updateTrackingMode() {
    // This is just a placeholder - the actual mode is read when saving
    // Could add visual feedback here if needed
  }
}

// Create singleton instance
export const tracking = new TrackingManager();

// Modal management functions
window.closeEditTrackingModal = function () {
  document.getElementById('edit-tracking-modal').classList.add('hidden');
};

window.closeSearchIssuesModal = function () {
  document.getElementById('search-issues-modal').classList.add('hidden');
};

// Save edited tracking
window.saveEditedTracking = async function () {
  const trackingId = document.getElementById('edit-tracking-id').value;
  const title = document.getElementById('edit-tracking-title').value;
  const publisher = document.getElementById('edit-tracking-publisher').value;
  const issn = document.getElementById('edit-tracking-issn').value;
  const mode = document.getElementById('edit-tracking-mode').value;
  const deleteFromClient = document.getElementById('edit-delete-from-client').checked;
  const orgPattern = document.getElementById('edit-tracking-org-pattern').value.trim();

  try {
    const response = await APIClient.put(`/api/periodicals/tracking/${trackingId}`, {
      title,
      publisher,
      issn,
      track_all_editions: mode === 'all',
      track_new_only: mode === 'new',
      delete_from_client_on_completion: deleteFromClient,
      organization_pattern: orgPattern || null, // Send null if empty to use global default
    });

    const result = await response.json();
    if (result.success) {
      window.closeEditTrackingModal();
      tracking.loadTrackedPeriodicals();
      UIUtils.showStatus('tracking-status', 'Tracking updated successfully', 'success');
      setTimeout(() => UIUtils.hideStatus('tracking-status'), 3000);
    } else {
      UIUtils.showStatus('tracking-status', 'Failed to update tracking', 'error');
    }
  } catch (err) {
    console.error('Error updating tracking:', err);
    UIUtils.showStatus('tracking-status', 'Failed to update tracking', 'error');
  }
};

// Search for publisher metadata (from edit modal)
window.searchPublisherMetadata = async function () {
  const title = document.getElementById('edit-tracking-title').value;
  if (!title) {
    UIUtils.showStatus('tracking-status', 'Please enter a title', 'error');
    return;
  }

  // Show loading modal
  const loadingHTML = `
    <div id="metadata-search-loading" class="modal" style="display: flex;">
      <div class="modal-content" style="max-width: 400px; text-align: center;">
        <div style="padding: 60px 40px;">
          <p style="font-size: 18px; margin-bottom: 20px;">🔍 Searching for metadata...</p>
          <p style="color: var(--text-secondary); margin-bottom: 20px;">Checking Wikipedia and CrossRef</p>
          <div style="display: inline-block; width: 40px; height: 40px; border: 4px solid var(--border-color); border-top-color: var(--primary-color); border-radius: 50%; animation: spin 1s linear infinite;"></div>
        </div>
      </div>
    </div>
  `;

  document.body.insertAdjacentHTML('beforeend', loadingHTML);

  try {
    const response = await APIClient.authenticatedFetch(
      `/api/periodicals/search-metadata?query=${encodeURIComponent(title)}`,
      { method: 'POST' }
    );
    const data = await response.json();

    // Remove loading modal
    const loadingModal = document.getElementById('metadata-search-loading');
    if (loadingModal) {
      loadingModal.remove();
    }

    if (data.found && data.results && data.results.length > 0) {
      // Show results in a modal for user selection
      window.showMetadataSearchResults(data.results, title);
    } else {
      UIUtils.showStatus('tracking-status', 'No metadata found for this title', 'error');
    }
  } catch (err) {
    console.error('Error searching metadata:', err);

    // Remove loading modal
    const loadingModal = document.getElementById('metadata-search-loading');
    if (loadingModal) {
      loadingModal.remove();
    }

    UIUtils.showStatus('tracking-status', 'Failed to search metadata', 'error');
  }
};

// Show metadata search results modal
window.showMetadataSearchResults = function (results, title) {
  // Create a modal to display search results
  const modalHTML = `
    <div id="metadata-results-modal" class="modal" style="display: flex;">
      <div class="modal-content" style="max-width: 600px; max-height: 70vh; overflow-y: auto;">
        <span class="close" onclick="closeMetadataModal()">&times;</span>
        <h2>Metadata Search Results for "${title}"</h2>
        <p style="color: var(--text-secondary); margin-bottom: 20px;">Click on a result to populate the form:</p>
        <div id="metadata-results-list"></div>
      </div>
    </div>
  `;

  // Remove any existing metadata modal
  const existingModal = document.getElementById('metadata-results-modal');
  if (existingModal) {
    existingModal.remove();
  }

  document.body.insertAdjacentHTML('beforeend', modalHTML);

  const resultsList = document.getElementById('metadata-results-list');

  // Merge results by title, combining publisher and ISSN from different sources
  const mergedResults = window.mergeMetadataResults(results);

  // Display results
  mergedResults.forEach((result) => {
    const resultDiv = document.createElement('div');
    resultDiv.style.cssText = `
      padding: 15px;
      border: 1px solid var(--border-color);
      border-radius: 5px;
      margin-bottom: 10px;
      cursor: pointer;
      transition: background 0.2s;
    `;
    resultDiv.onmouseover = () => (resultDiv.style.background = 'var(--surface-variant)');
    resultDiv.onmouseout = () => (resultDiv.style.background = 'transparent');

    const titleP = document.createElement('p');
    titleP.style.cssText = 'margin: 0 0 8px 0; font-weight: 600; font-size: 15px;';
    titleP.textContent = result.title;
    resultDiv.appendChild(titleP);

    const sourcesP = document.createElement('p');
    sourcesP.style.cssText = 'margin: 0 0 8px 0; font-size: 12px; color: var(--text-secondary);';
    sourcesP.textContent = `Sources: ${result.sources.join(', ')}`;
    resultDiv.appendChild(sourcesP);

    if (result.publisher) {
      const pubP = document.createElement('p');
      pubP.style.cssText = 'margin: 0 0 5px 0; font-size: 13px;';
      pubP.textContent = `Publisher: ${result.publisher}`;
      resultDiv.appendChild(pubP);
    }

    if (result.issn) {
      const issnP = document.createElement('p');
      issnP.style.cssText =
        'margin: 0 0 5px 0; font-size: 13px; font-weight: 500; color: var(--primary-color);';
      issnP.textContent = `ISSN: ${result.issn}`;
      resultDiv.appendChild(issnP);
    }

    if (result.publication_date) {
      const dateP = document.createElement('p');
      dateP.style.cssText = 'margin: 0; font-size: 12px; color: var(--text-tertiary);';
      dateP.textContent = `Date: ${result.publication_date}`;
      resultDiv.appendChild(dateP);
    }

    resultDiv.onclick = () => window.selectMetadataResult(result);
    resultsList.appendChild(resultDiv);
  });
};

// Merge metadata results from different sources
window.mergeMetadataResults = function (results) {
  // Group results by title (case-insensitive)
  const grouped = new Map();

  results.forEach((result) => {
    const titleKey = result.title.toLowerCase().trim();

    if (!grouped.has(titleKey)) {
      grouped.set(titleKey, {
        title: result.title,
        publisher: null,
        issn: null,
        sources: [],
        publication_date: result.publication_date,
        url: result.url,
        raw_metadata: result.raw_metadata || {},
      });
    }

    const merged = grouped.get(titleKey);

    // Combine data from different sources
    if (!merged.publisher && (result.raw_metadata?.publisher || result.metadata?.publisher)) {
      merged.publisher = result.raw_metadata?.publisher || result.metadata?.publisher;
    }

    if (!merged.issn && (result.raw_metadata?.issn || result.metadata?.issn)) {
      merged.issn = result.raw_metadata?.issn || result.metadata?.issn;
    }

    // Track sources
    if (!merged.sources.includes(result.provider)) {
      merged.sources.push(result.provider);
    }
  });

  // Convert to array and sort by number of sources (prefer results with more metadata)
  return Array.from(grouped.values()).sort((a, b) => {
    // Prioritize results with both publisher and ISSN
    const aComplete = (a.publisher ? 1 : 0) + (a.issn ? 1 : 0);
    const bComplete = (b.publisher ? 1 : 0) + (b.issn ? 1 : 0);

    if (aComplete !== bComplete) return bComplete - aComplete;

    // Then prioritize by number of sources
    return b.sources.length - a.sources.length;
  });
};

// Select a metadata result and populate form
window.selectMetadataResult = function (result) {
  // Populate the form fields with the selected result
  if (result.title) {
    document.getElementById('edit-tracking-title').value = result.title;
  }

  if (result.publisher) {
    document.getElementById('edit-tracking-publisher').value = result.publisher;
  }

  if (result.issn) {
    document.getElementById('edit-tracking-issn').value = result.issn;
  }

  window.closeMetadataModal();
};

// Close metadata results modal
window.closeMetadataModal = function () {
  const modal = document.getElementById('metadata-results-modal');
  if (modal) {
    modal.remove();
  }
};

// Select and download issue with language variant selection
window.selectIssueWithVariants = function (issueKey, alreadyDownloaded) {
  const variants = window.issueVariants[issueKey];

  if (!variants || variants.length === 0) {
    UIUtils.showStatus('tracking-status', 'No variants available', 'error');
    return;
  }

  // If only one variant, download directly
  if (variants.length === 1) {
    const variant = variants[0];
    window.selectIssue(
      variant.title,
      variant.provider,
      variant.url,
      variant.already_downloaded || alreadyDownloaded
    );
    return;
  }

  // Multiple variants - show selection modal
  const modalHTML = `
    <div id="language-variant-modal" class="modal" style="display: flex;">
      <div class="modal-content" style="max-width: 500px;">
        <span class="close" onclick="closeLangVariantModal()">&times;</span>
        <h2>Select Language Edition</h2>
        <p style="color: var(--text-secondary); margin-bottom: 20px;">Multiple language editions available:</p>
        <div id="variant-options" style="display: flex; flex-direction: column; gap: 10px;"></div>
      </div>
    </div>
  `;

  document.body.insertAdjacentHTML('beforeend', modalHTML);

  const optionsDiv = document.getElementById('variant-options');
  variants.forEach((variant, index) => {
    // Detect language
    const langMatch = variant.title.match(
      /\b(German|Dutch|French|Spanish|Italian|English|DE|NL|FR|ES|IT|EN|USA|UK)\b/i
    );
    const lang = langMatch ? langMatch[0].toUpperCase() : '';

    // Detect special editions (Traveler, Kids, etc.)
    const editionMatch = variant.title.match(
      /\b(Traveler|Traveller|Kids|Junior|Special|History|Science)\b/i
    );
    const edition = editionMatch ? editionMatch[0] : '';

    // Build display label
    let displayLabel = lang || `Edition ${index + 1}`;
    if (edition) {
      displayLabel = lang ? `${lang} - ${edition}` : edition;
    }

    const isDownloaded = variant.already_downloaded || alreadyDownloaded;
    const downloaded = isDownloaded ? ' <span style="color: #4caf50;">✓ In Library</span>' : '';

    const btn = document.createElement('button');
    // Different styling for re-download vs new download
    if (isDownloaded) {
      btn.className = 'btn-secondary';
      btn.style.cssText =
        'width: 100%; text-align: left; padding: 15px; background: #4caf50; color: white; border: 2px solid #45a049;';
    } else {
      btn.className = 'btn-primary';
      btn.style.cssText = 'width: 100%; text-align: left; padding: 15px;';
    }
    btn.innerHTML = `
      <div style="font-weight: 600; font-size: 16px;">${displayLabel}${downloaded}</div>
      <div style="font-size: 11px; margin-top: 6px; opacity: 0.8; word-break: break-all;">${variant.title}</div>
    `;
    btn.onclick = () => {
      window.closeLangVariantModal();
      window.selectIssue(variant.title, variant.provider, variant.url, isDownloaded);
    };
    optionsDiv.appendChild(btn);
  });
};

window.closeLangVariantModal = function () {
  const modal = document.getElementById('language-variant-modal');
  if (modal) modal.remove();
};

// Select and download issue
window.selectIssue = async function (title, provider, url, alreadyDownloaded) {
  const isLibraryOnly = !url || url === '';

  if (isLibraryOnly) {
    UIUtils.showStatus('tracking-status', 'This issue is already in your library', 'success');
    setTimeout(() => UIUtils.hideStatus('tracking-status'), 3000);
    return;
  }

  // Build confirmation message with filename
  let confirmMessage = `<p><strong>File:</strong> ${title}</p><p><strong>Provider:</strong> ${provider}</p>`;
  if (alreadyDownloaded) {
    confirmMessage +=
      '<p style="color: #ff9800; margin-top: 10px;">⚠️ You already have this issue in your library.</p><p>Re-download it anyway?</p>';
  } else {
    confirmMessage += '<p style="margin-top: 10px;">Download this issue?</p>';
  }

  const shouldDownload = await UIUtils.confirm('Download Issue', confirmMessage);
  if (shouldDownload) {
    window.downloadIssue(title, url, provider);
  }
};

/**
 * Open modal to select tracking records to merge
 */
window.openMergeModal = async function() {
  const tracking = window.trackingManager;
  if (!tracking) return;

  try {
    const response = await APIClient.get('/api/periodicals/tracking?limit=1000');
    const data = await response.json();
    
    if (!response.ok || !data.items || data.items.length < 2) {
      alert('You need at least 2 tracked periodicals to merge');
      return;
    }

    const modal = document.createElement('div');
    modal.className = 'modal';
    modal.id = 'merge-selection-modal';
    
    const trackingOptions = data.items.map(item => `
      <div class="merge-select-item">
        <input type="checkbox" id="merge-check-${item.id}" value="${item.id}" class="merge-selection-checkbox">
        <label for="merge-check-${item.id}">
          <strong>${item.title}</strong><br>
          <span style="font-size: 12px; color: var(--text-secondary);">Publisher: ${item.publisher || 'Unknown'} | ISSN: ${item.issn || 'N/A'}</span>
        </label>
      </div>
    `).join('');

    modal.innerHTML = `
      <div class="modal-content" style="max-width: 600px;">
        <h3>🔀 Merge Tracking Records</h3>
        <p style="color: var(--text-secondary); margin-bottom: 20px;">Select 2 or more tracking records to merge. You'll choose which one to keep in the next step.</p>
        <div id="merge-selection-list" style="max-height: 400px; overflow-y: auto; margin-bottom: 20px;">
          ${trackingOptions}
        </div>
        <div style="display: flex; gap: 10px; justify-content: flex-end;">
          <button onclick="window.closeMergeSelectionModal()" class="btn-secondary">Cancel</button>
          <button id="continue-merge-btn" onclick="window.showMergeTargetSelection()" class="btn-primary" disabled>Continue</button>
        </div>
      </div>
    `;
    
    document.body.appendChild(modal);
    modal.style.display = 'flex';

    // Add change listeners to checkboxes
    const checkboxes = modal.querySelectorAll('.merge-selection-checkbox');
    checkboxes.forEach(cb => {
      cb.addEventListener('change', () => {
        const checkedCount = modal.querySelectorAll('.merge-selection-checkbox:checked').length;
        document.getElementById('continue-merge-btn').disabled = checkedCount < 2;
      });
    });
  } catch (error) {
    console.error('Error loading tracking records:', error);
    alert('Failed to load tracking records');
  }
};

/**
 * Close merge selection modal
 */
window.closeMergeSelectionModal = function() {
  const modal = document.getElementById('merge-selection-modal');
  if (modal) modal.remove();
};

/**
 * Show target selection after initial selection
 */
window.showMergeTargetSelection = async function() {
  const selectionModal = document.getElementById('merge-selection-modal');
  const checkboxes = selectionModal.querySelectorAll('.merge-selection-checkbox:checked');
  const selectedIds = Array.from(checkboxes).map(cb => parseInt(cb.value));
  
  if (selectedIds.length < 2) {
    alert('Please select at least 2 tracking records');
    return;
  }

  // Get the tracking data for selected items
  const response = await APIClient.get('/api/periodicals/tracking?limit=1000');
  const data = await response.json();
  const selectedItems = data.items.filter(item => selectedIds.includes(item.id));
  
  // Close selection modal
  window.closeMergeSelectionModal();
  
  // Show target modal
  const modal = document.createElement('div');
  modal.className = 'modal';
  modal.id = 'merge-target-modal';
  
  const options = selectedItems.map(item => 
    `<option value="${item.id}">${item.title} (${item.publisher || 'Unknown'})</option>`
  ).join('');
  
  modal.innerHTML = `
    <div class="modal-content">
      <h3>Select Target Tracking Record</h3>
      <p>Choose which tracking record to keep. All magazines and downloads from other selected records will be moved to this one.</p>
      <select id="merge-target-select" style="width: 100%; padding: 8px; margin: 16px 0;">
        ${options}
      </select>
      <input type="hidden" id="merge-source-ids" value="${selectedIds.join(',')}">
      <div style="margin-top: 20px; display: flex; gap: 10px; justify-content: flex-end;">
        <button onclick="window.closeMergeModal()" class="btn-secondary">Cancel</button>
        <button onclick="window.confirmMerge()" class="btn-primary">Merge</button>
      </div>
    </div>
  `;
  
  document.body.appendChild(modal);
  modal.style.display = 'flex';
};

/**
 * Close merge target selection modal
 */
window.closeMergeModal = function() {
  const modal = document.getElementById('merge-target-modal');
  if (modal) {
    modal.remove();
  }
};

/**
 * Confirm and execute the merge
 */
window.confirmMerge = async function() {
  const targetId = parseInt(document.getElementById('merge-target-select').value);
  const sourceIdsStr = document.getElementById('merge-source-ids').value;
  const allSelectedIds = sourceIdsStr.split(',').map(id => parseInt(id));
  const sourceIds = allSelectedIds.filter(id => id !== targetId);
  
  if (!targetId || sourceIds.length === 0) {
    alert('Invalid selection');
    return;
  }
  
  if (!confirm(`Merge ${sourceIds.length} tracking record(s) into the selected target? This cannot be undone.`)) {
    return;
  }
  
  try {
    const response = await APIClient.post(`/api/periodicals/tracking/${targetId}/merge`, {
      source_ids: sourceIds
    });
    
    const data = await response.json();
    
    if (response.ok) {
      UIUtils.showStatus('tracking-status', 
        `✓ ${data.message}. Moved ${data.magazines_moved} magazines and ${data.submissions_moved} downloads.`, 
        'success');
      window.closeMergeModal();
      const tracking = window.trackingManager;
      if (tracking) {
        tracking.loadTrackedPeriodicals();
      }
    } else {
      throw new Error(data.detail || 'Merge failed');
    }
  } catch (error) {
    console.error('Merge error:', error);
    UIUtils.showStatus('tracking-status', `✗ ${error.message}`, 'error');
  }
};

// Download a single issue
window.downloadIssue = async function (title, url, provider) {
  try {
    const trackingId = window.currentTrackingId;
    if (!trackingId) {
      UIUtils.showStatus('tracking-status', 'Error: No tracking ID available', 'error');
      return;
    }

    const response = await APIClient.post('/api/downloads/single-issue', {
      tracking_id: trackingId,
      title: title,
      url: url,
      provider: provider,
    });

    const data = await response.json();

    if (response.ok) {
      UIUtils.showStatus('tracking-status', `✓ Download queued! Job ID: ${data.job_id}`, 'success');
      setTimeout(() => UIUtils.hideStatus('tracking-status'), 5000);
      window.closeSearchIssuesModal();
    } else {
      UIUtils.showStatus('tracking-status', data.detail || 'Failed to queue download', 'error');
    }
  } catch (err) {
    console.error('Download error:', err);
    UIUtils.showStatus('tracking-status', `Error: ${err.message}`, 'error');
  }
};

// Expose functions globally for onclick handlers
window.openTrackNewPeriodicalModal = () => tracking.openTrackNewPeriodicalModal();
window.closeTrackNewPeriodicalModal = () => tracking.closeTrackNewPeriodicalModal();
window.searchPeriodicalMetadata = () => tracking.searchPeriodicalMetadata();
window.saveTrackingPreferences = () => tracking.saveTrackingPreferences();
window.resetTracking = () => tracking.resetTracking();
window.updateTrackingMode = () => tracking.updateTrackingMode();
window.setSortField = (field) => tracking.setSortField(field);
window.toggleSortOrder = () => tracking.toggleSortOrder();
window.editTracking = (id) => tracking.editTracking(id);
window.searchForIssues = (id, title) => tracking.searchForIssues(id, title);
window.deleteTracking = (id, title) => tracking.deleteTracking(id, title);
