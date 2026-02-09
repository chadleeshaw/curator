/**
 * @module periodical
 * @description Periodical detail page functionality - displays issues, metadata editing,
 * special edition management, and issue organization.
 */

/* global FileReader */

import { APIClient, APIHelper } from './core/api.js';
import { CSS_CLASSES } from './core/constants.js';
import { initScrollCollapse } from './core/scroll-collapse.js';

// Initialize scroll-collapse for detail page header
initScrollCollapse();

// Parse years data and special editions from data attributes
const container = document.getElementById('periodical-container');
const yearsData = container ? JSON.parse(container.getAttribute('data-years') || '[]') : [];
const specialEditionsData = container
  ? JSON.parse(container.getAttribute('data-special-editions') || '[]')
  : [];
let pendingDeleteId = null;
let currentMagazineId = null;
let currentMagazineData = null;

/**
 * Helper function to extract special edition value from data structure.
 * Checks derived_metadata (new location), extra_metadata, and metadata (legacy location).
 *
 * @param {Object} data - The periodical data object
 * @returns {string|null} The special edition name or null
 */
function getSpecialEditionValue(data) {
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
function isSpecialEdition(data) {
  // Only check derived_metadata.is_special_edition (boolean flag)
  // Do NOT fallback to title-based keyword matching
  if (data.derived_metadata?.is_special_edition?.value !== undefined) {
    return Boolean(data.derived_metadata.is_special_edition.value);
  }

  // Default to false - only explicitly marked issues are special editions
  return false;
}

// Delete modal functions
function openDeleteModal(magazineId, title) {
  pendingDeleteId = magazineId;

  const modal = document.getElementById('delete-modal');

  const titleElement = document.getElementById('delete-modal-title');
  if (titleElement) {
    titleElement.textContent = `Are you sure you want to delete "${title}"?`;
  }

  // Use showModal() for dialog element
  if (modal && typeof modal.showModal === 'function') {
    modal.showModal();
  } else {
    modal.classList.remove(CSS_CLASSES.HIDDEN);
  }
}

function closeDeleteModal() {
  const modal = document.getElementById('delete-modal');

  // Use close() for dialog element
  if (modal && typeof modal.close === 'function') {
    modal.close();
  } else {
    modal.classList.add(CSS_CLASSES.HIDDEN);
  }
  pendingDeleteId = null;
}

// Close modal when clicking outside of it
// Track mousedown target to prevent text selection drag from closing modal
let deleteModalMouseDown = null;
document.addEventListener('mousedown', (event) => {
  deleteModalMouseDown = event.target;
});
document.addEventListener('click', (event) => {
  const modal = document.getElementById('delete-modal');
  if (modal && event.target === modal && deleteModalMouseDown === modal) {
    closeDeleteModal();
  }
  deleteModalMouseDown = null;
});

function renderIssues() {
  const container = document.getElementById('issues-container');

  if (
    (!yearsData || yearsData.length === 0) &&
    (!specialEditionsData || specialEditionsData.length === 0)
  ) {
    container.innerHTML = '<div class="no-issues">No issues found for this periodical.</div>';
    return;
  }

  // Title is already set correctly by the backend from MagazineTracking.title
  // No need to extract it from issue titles

  // Render special editions section first, if any exist
  if (specialEditionsData && specialEditionsData.length > 0) {
    const specialSection = document.createElement('div');
    specialSection.className = 'year-section special-edition-section';

    const specialTitle = document.createElement('h2');
    specialTitle.className = 'year-title special-edition-title';
    specialTitle.textContent = '🌟 Special Editions';
    specialSection.appendChild(specialTitle);

    const issuesGrid = document.createElement('div');
    issuesGrid.className = 'issues-grid';

    specialEditionsData.forEach((issue) => {
      const issueCard = createIssueCard(issue);
      issuesGrid.appendChild(issueCard);
    });

    specialSection.appendChild(issuesGrid);
    container.appendChild(specialSection);
  }

  // Render regular year sections
  yearsData.forEach((yearData) => {
    const yearSection = document.createElement('div');
    yearSection.className = 'year-section';

    const yearTitle = document.createElement('h2');
    yearTitle.className = 'year-title';
    yearTitle.textContent = yearData.year;
    yearSection.appendChild(yearTitle);

    const issuesGrid = document.createElement('div');
    issuesGrid.className = 'issues-grid';

    yearData.issues.forEach((issue) => {
      const issueCard = createIssueCard(issue);
      issuesGrid.appendChild(issueCard);
    });

    yearSection.appendChild(issuesGrid);
    container.appendChild(yearSection);
  });
}

// Helper function to create an issue card
function createIssueCard(issue) {
  const issueCard = document.createElement('div');
  issueCard.className = 'issue-card';

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
    specialEditionP.textContent = issue.special_edition_name;
    specialEditionP.title = issue.special_edition_name;
    infoDiv.appendChild(specialEditionP);
  }

  // Create actions container with View, Metadata, and Delete buttons
  const actionsDiv = document.createElement('div');
  actionsDiv.className = 'issue-actions';

  const openButton = document.createElement('button');
  openButton.className = 'open-pdf-btn';
  openButton.textContent = '📖';
  openButton.title = 'Open file';
  openButton.onclick = (e) => {
    e.stopPropagation();
    openPDF(issue.id);
  };
  actionsDiv.appendChild(openButton);

  const metadataButton = document.createElement('button');
  metadataButton.className = 'metadata-btn';
  metadataButton.textContent = 'ℹ️';
  metadataButton.title = 'View metadata';
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

async function openPDF(magazineId) {
  try {
    // Get magazine metadata to check file type
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.get(`/api/periodicals/${magazineId}`);
      return await response.json();
    }, 'Periodical');

    // Check file type and open appropriate reader
    if (data.file_path) {
      const filePath = data.file_path.toLowerCase();
      console.log('[Periodical] Opening file:', filePath);
      if (filePath.endsWith('.epub')) {
        console.log('[Periodical] Detected EPUB, opening EPUB reader');
        // Open EPUB reader in same window
        window.location.href = `/epub-reader?id=${magazineId}`;
      } else if (filePath.endsWith('.cbz') || filePath.endsWith('.cbr')) {
        console.log('[Periodical] Detected comic file, opening comic reader');
        // Open comic reader in same window
        window.location.href = `/comic-reader?id=${magazineId}`;
      } else if (filePath.endsWith('.pdf')) {
        console.log('[Periodical] Detected PDF, opening PDF reader');
        // Open PDF reader in same window
        window.location.href = `/pdf-reader?id=${magazineId}`;
      } else {
        console.log('[Periodical] Unknown file type, opening directly');
        // Open file directly in new tab (for non-reader files)
        window.open(`/api/periodicals/${magazineId}/pdf`, '_blank');
      }
    } else {
      console.log('[Periodical] No file_path, opening directly');
      // Fallback to opening directly in new tab
      window.open(`/api/periodicals/${magazineId}/pdf`, '_blank');
    }
  } catch (error) {
    console.error('[Periodical] Error checking file type:', error);
    // Fallback to opening as PDF in new tab
    window.open(`/api/periodicals/${magazineId}/pdf`, '_blank');
  }
}

// View metadata - opens the metadata modal
async function viewMetadata(magazineId) {
  try {
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.get(`/api/periodicals/${magazineId}`);
      return await response.json();
    }, 'Periodical');
    displayMetadata(data);
  } catch (error) {
    console.error('[Periodical] Error fetching metadata:', error);
    const message = error.toUserMessage ? error.toUserMessage() : 'Failed to load metadata';
    showNotification(message, 'error');
  }
}

function displayMetadata(data) {
  const metadataBody = document.getElementById('metadata-body');
  metadataBody.innerHTML = '';

  // Store current magazine data globally
  currentMagazineId = data.id;
  currentMagazineData = data;

  // Update special edition button text based on current status
  const isSpecial = isSpecialEdition(data);
  const toggleBtn = document.getElementById('toggle-special-btn');
  if (toggleBtn) {
    if (isSpecial) {
      toggleBtn.textContent = '⭐ Unmark Special Edition';
      toggleBtn.title = 'Remove special edition status';
    } else {
      toggleBtn.textContent = '⭐ Mark as Special Edition';
      toggleBtn.title = 'Mark this issue as a special edition';
    }
  }

  // Helper function to create metadata item
  function addMetadataItem(label, value) {
    if (value === null || value === undefined || value === '') return;

    const item = document.createElement('div');
    item.className = 'metadata-item';

    const labelDiv = document.createElement('div');
    labelDiv.className = 'metadata-label';
    labelDiv.textContent = label;

    const valueDiv = document.createElement('div');
    valueDiv.className = 'metadata-value';

    // Check if value looks like JSON (starts with { or [)
    const valueStr = String(value);
    if ((valueStr.startsWith('{') || valueStr.startsWith('[')) && valueStr.includes('\n')) {
      // Display as formatted JSON in a pre tag
      const pre = document.createElement('pre');
      pre.style.margin = '0';
      pre.style.fontSize = '11px';
      pre.style.lineHeight = '1.4';
      pre.style.padding = '8px';
      pre.style.background = 'var(--background)';
      pre.style.border = '1px solid var(--border-color)';
      pre.style.borderRadius = '3px';
      pre.style.overflow = 'auto';
      pre.style.maxHeight = '200px';
      pre.style.fontFamily = 'monospace';
      pre.textContent = valueStr;
      valueDiv.appendChild(pre);
    } else {
      // Display as plain text
      valueDiv.textContent = valueStr;
    }

    item.appendChild(labelDiv);
    item.appendChild(valueDiv);
    metadataBody.appendChild(item);
  }

  // Section 1: Database Fields (from Periodical model)
  const dbSection = document.createElement('div');
  dbSection.style.marginBottom = '20px';
  dbSection.innerHTML =
    '<h4 style="margin: 0 0 10px 0; color: var(--primary-color);">💾 Database Fields</h4>';
  metadataBody.appendChild(dbSection);

  // Display all database fields dynamically (excluding JSON columns which are shown separately)
  const dbFields = {
    id: 'ID',
    title: 'Title',
    language: 'Language',
    category: 'Category',
    issue_date: 'Issue Date',
    file_path: 'File Path',
    cover_path: 'Cover Path',
    content_hash: 'Content Hash',
    tracking_id: 'Tracking ID',
    created_at: 'Created At',
    updated_at: 'Updated At',
  };

  for (const [field, label] of Object.entries(dbFields)) {
    if (data[field] !== null && data[field] !== undefined) {
      let value = data[field];

      // Format dates nicely
      if (field === 'issue_date' && value) {
        // Issue date: just show the date, no time
        value = value.split('T')[0]; // "2000-05-01"
      } else if ((field === 'created_at' || field === 'updated_at') && value) {
        // Created/Updated: show datetime without microseconds
        value = value.split('.')[0].replace('T', ' '); // "2026-01-17 05:43:47"
      }

      addMetadataItem(label, value);
    }
  }

  // Section 2: Derived Metadata (final merged with source attribution)
  if (data.derived_metadata && Object.keys(data.derived_metadata).length > 0) {
    const derivedSection = document.createElement('div');
    derivedSection.style.marginTop = '20px';
    derivedSection.innerHTML =
      '<h4 style="margin: 0 0 10px 0; color: var(--primary-color);">📊 Derived Metadata (Merged from Scans)</h4>';
    metadataBody.appendChild(derivedSection);

    // Display all derived metadata fields dynamically
    const skipFields = ['_merge_config']; // Internal fields to skip

    for (const [fieldName, fieldData] of Object.entries(data.derived_metadata)) {
      if (skipFields.includes(fieldName)) continue;

      if (typeof fieldData === 'object' && fieldData !== null && 'value' in fieldData) {
        const value = fieldData.value;
        const source = fieldData.source;
        const confidence = fieldData.confidence;

        if (value === null || value === undefined) continue;

        const item = document.createElement('div');
        item.className = 'metadata-item';

        const labelDiv = document.createElement('div');
        labelDiv.className = 'metadata-label';
        // Convert field_name to Field Name
        labelDiv.textContent = fieldName
          .replace(/_/g, ' ')
          .replace(/\b\w/g, (l) => l.toUpperCase());

        const valueDiv = document.createElement('div');
        valueDiv.className = 'metadata-value';

        // Show value with source badge
        const sourceBadge =
          {
            file_scan: '📁 File',
            text_scan: '📄 Text',
            ocr_scan: '🔍 OCR',
          }[source] || source;

        const confBadge =
          typeof confidence === 'number' ? ` (${(confidence * 100).toFixed(0)}%)` : '';
        valueDiv.innerHTML = `${value} <span style="font-size: 0.85em; color: var(--text-secondary); margin-left: 8px;">${sourceBadge}${confBadge}</span>`;

        item.appendChild(labelDiv);
        item.appendChild(valueDiv);
        metadataBody.appendChild(item);
      }
    }
  }

  // Note: parsed_metadata sections (file_scan, text_scan, ocr_scan) are only shown
  // in the collapsible "Full Metadata JSON" section below for cleaner display

  // Create collapsible full metadata section
  const metadataSection = document.createElement('div');
  metadataSection.style.marginTop = '20px';
  metadataSection.style.borderTop = '2px solid var(--border-color)';
  metadataSection.style.paddingTop = '20px';

  const toggleHeader = document.createElement('div');
  toggleHeader.style.cursor = 'pointer';
  toggleHeader.style.display = 'flex';
  toggleHeader.style.alignItems = 'center';
  toggleHeader.style.gap = '10px';
  toggleHeader.style.padding = '10px';
  toggleHeader.style.background = 'var(--surface-variant)';
  toggleHeader.style.borderRadius = '5px';
  toggleHeader.style.marginBottom = '10px';

  const toggleIcon = document.createElement('span');
  toggleIcon.textContent = '▶';
  toggleIcon.style.transition = 'transform 0.2s';

  const toggleLabel = document.createElement('strong');
  toggleLabel.textContent = 'Full Metadata JSON';

  toggleHeader.appendChild(toggleIcon);
  toggleHeader.appendChild(toggleLabel);

  const metadataContent = document.createElement('div');
  metadataContent.style.display = 'none';
  metadataContent.style.maxHeight = '400px';
  metadataContent.style.overflow = 'auto';
  metadataContent.style.background = 'var(--background)';
  metadataContent.style.border = '1px solid var(--border-color)';
  metadataContent.style.borderRadius = '5px';
  metadataContent.style.padding = '15px';

  const pre = document.createElement('pre');
  pre.style.margin = '0';
  pre.style.fontSize = '12px';
  pre.style.lineHeight = '1.5';
  pre.style.color = 'var(--text-primary)';
  pre.style.fontFamily = 'monospace';

  // Create organized JSON structure showing all fields from Periodical model
  const fullData = {
    // Database fields
    id: data.id,
    title: data.title,
    language: data.language,
    category: data.category,
    issue_date: data.issue_date,
    file_path: data.file_path,
    cover_path: data.cover_path,
    content_hash: data.content_hash,
    tracking_id: data.tracking_id,
    created_at: data.created_at,
    updated_at: data.updated_at,

    // Metadata columns (new structure)
    parsed_metadata: data.parsed_metadata || null,
    derived_metadata: data.derived_metadata || null,
    extra_metadata: data.extra_metadata || null,
  };

  pre.textContent = JSON.stringify(fullData, null, 2);

  metadataContent.appendChild(pre);

  toggleHeader.onclick = () => {
    if (metadataContent.style.display === 'none') {
      metadataContent.style.display = 'block';
      toggleIcon.style.transform = 'rotate(90deg)';
    } else {
      metadataContent.style.display = 'none';
      toggleIcon.style.transform = 'rotate(0deg)';
    }
  };

  metadataSection.appendChild(toggleHeader);
  metadataSection.appendChild(metadataContent);
  metadataBody.appendChild(metadataSection);

  // Show the modal
  document.getElementById('metadata-modal').classList.add('show');
}

function closeMetadataModal() {
  document.getElementById('metadata-modal').classList.remove('show');
  // Reset to view mode when closing
  cancelMetadataEdit();
}

// eslint-disable-next-line no-unused-vars -- Called from HTML onclick handlers
function enableMetadataEdit() {
  if (!currentMagazineData) return;

  // Hide view, show edit form
  document.getElementById('metadata-body').classList.add(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-edit-form').classList.remove(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-view-buttons').classList.add(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-edit-buttons').classList.remove(CSS_CLASSES.HIDDEN);

  // Check if this issue is linked to tracking
  const hasTracking =
    currentMagazineData.tracking_id !== null && currentMagazineData.tracking_id !== undefined;

  // Populate form fields
  const languageField = document.getElementById('edit-language');
  languageField.value = currentMagazineData.language || 'English';

  // Disable language if controlled by tracking
  const languageContainer = document.getElementById('edit-language-container');
  if (hasTracking) {
    languageField.disabled = true;
    languageContainer.title = 'Language is controlled by the tracking record';
    languageContainer.style.opacity = '0.6';
  } else {
    languageField.disabled = false;
    languageContainer.title = '';
    languageContainer.style.opacity = '1';
  }

  // Year field
  document.getElementById('edit-year').value =
    (currentMagazineData.metadata && currentMagazineData.metadata.year) || '';

  // Month field
  document.getElementById('edit-month').value =
    (currentMagazineData.metadata && currentMagazineData.metadata.month) || '';

  // Country field
  const countryField = document.getElementById('edit-country');
  countryField.value = (currentMagazineData.metadata && currentMagazineData.metadata.country) || '';

  // Disable country if controlled by tracking
  const countryContainer = document.getElementById('edit-country-container');
  if (hasTracking) {
    countryField.disabled = true;
    countryContainer.title = 'Country is controlled by the tracking record';
    countryContainer.style.opacity = '0.6';
  } else {
    countryField.disabled = false;
    countryContainer.title = '';
    countryContainer.style.opacity = '1';
  }

  // Issue-specific fields (always editable)
  document.getElementById('edit-issue-number').value =
    (currentMagazineData.metadata && currentMagazineData.metadata.issue_number) || '';
  document.getElementById('edit-volume').value =
    (currentMagazineData.metadata && currentMagazineData.metadata.volume) || '';

  // Always show special edition field in edit mode
  const specialField = document.getElementById('special-edition-name-field');
  const specialEditionValue = getSpecialEditionValue(currentMagazineData);
  const isSpecial = isSpecialEdition(currentMagazineData);
  specialField.classList.remove(CSS_CLASSES.HIDDEN);
  document.getElementById('edit-special-edition').value = specialEditionValue || '';

  // Update the label to indicate if it's currently marked as special edition
  const specialLabel = specialField.querySelector('label');
  if (isSpecial) {
    specialLabel.textContent = 'Special Edition Name ⭐';
  } else {
    specialLabel.textContent = 'Special Edition Name';
  }

  // Cover page field
  document.getElementById('edit-cover-page').value =
    (currentMagazineData.metadata && currentMagazineData.metadata.cover_page) || '1';
}

function cancelMetadataEdit() {
  // Show view, hide edit form
  document.getElementById('metadata-body').classList.remove(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-edit-form').classList.add(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-view-buttons').classList.remove(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-edit-buttons').classList.add(CSS_CLASSES.HIDDEN);
  // Clear any cover upload preview
  clearCoverUpload();
}

// eslint-disable-next-line no-unused-vars -- Called from HTML onclick handlers
function previewCoverUpload(input) {
  const preview = document.getElementById('cover-upload-preview');
  const previewImg = document.getElementById('cover-preview-img');

  if (input.files && input.files[0]) {
    const reader = new FileReader();
    reader.onload = function (e) {
      previewImg.src = e.target.result;
      preview.classList.remove(CSS_CLASSES.HIDDEN);
    };
    reader.readAsDataURL(input.files[0]);
  } else {
    preview.classList.add(CSS_CLASSES.HIDDEN);
    previewImg.src = '';
  }
}

// eslint-disable-next-line no-unused-vars -- Called from HTML onclick handlers
function clearCoverUpload() {
  const fileInput = document.getElementById('edit-cover-file');
  const preview = document.getElementById('cover-upload-preview');
  const previewImg = document.getElementById('cover-preview-img');

  if (fileInput) fileInput.value = '';
  if (preview) preview.classList.add(CSS_CLASSES.HIDDEN);
  if (previewImg) previewImg.src = '';
}

async function uploadCoverImage(magazineId) {
  const fileInput = document.getElementById('edit-cover-file');
  if (!fileInput || !fileInput.files || !fileInput.files[0]) {
    return false; // No file to upload
  }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  showNotification('🖼️ Uploading cover image...', 'info');

  const response = await fetch(`/api/periodicals/${magazineId}/upload-cover`, {
    method: 'POST',
    body: formData,
    headers: {
      Authorization: `Bearer ${localStorage.getItem('auth_token')}`,
    },
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to upload cover');
  }

  return true; // Successfully uploaded
}

// eslint-disable-next-line no-unused-vars -- Called from HTML onclick handlers
async function saveMetadataEdit() {
  if (!currentMagazineId) return;

  // Check if this issue is linked to tracking
  const hasTracking =
    currentMagazineData.tracking_id !== null && currentMagazineData.tracking_id !== undefined;

  const updates = {
    year: document.getElementById('edit-year').value || null,
    month: document.getElementById('edit-month').value || null,
    issue_number: document.getElementById('edit-issue-number').value || null,
    volume: document.getElementById('edit-volume').value || null,
  };

  // Only include tracking-controlled fields if issue is NOT linked to tracking
  if (!hasTracking) {
    updates.language = document.getElementById('edit-language').value;
    updates.country = document.getElementById('edit-country').value || null;
  }

  // Include special edition name if it's a special edition
  const specialEditionName = document.getElementById('edit-special-edition').value;
  updates.special_edition = specialEditionName || null;

  // Include cover page number
  const coverPage = document.getElementById('edit-cover-page').value;
  updates.cover_page = coverPage ? parseInt(coverPage) : 1;

  // Check if cover page number has changed
  const currentCoverPage = currentMagazineData.metadata?.cover_page || 1;
  const shouldRegenerateCover = coverPage && parseInt(coverPage) !== currentCoverPage;

  // Check if a custom cover image was selected
  const coverFileInput = document.getElementById('edit-cover-file');
  const hasCustomCover = coverFileInput && coverFileInput.files && coverFileInput.files[0];

  try {
    await APIHelper.executeWithErrorHandling(async () => {
      await APIClient.put(`/api/periodicals/${currentMagazineId}`, updates);
    }, 'Periodical');

    // Handle cover: custom upload takes priority over page number regeneration
    if (hasCustomCover) {
      await uploadCoverImage(currentMagazineId);
    } else if (shouldRegenerateCover) {
      showNotification('🔄 Regenerating cover from page ' + coverPage, 'info');
      await APIHelper.executeWithErrorHandling(async () => {
        await APIClient.post(`/api/periodicals/${currentMagazineId}/regenerate-cover`, {
          page_number: parseInt(coverPage),
        });
      }, 'Periodical');
    }

    await viewMetadata(currentMagazineId);

    // Clear the file input
    clearCoverUpload();

    // Show success message
    showNotification('✅ Metadata updated successfully', 'success');

    // Refresh the page to show updated data
    setTimeout(() => window.location.reload(), 1000);
  } catch (error) {
    console.error('[Periodical] Error updating metadata:', error);
    const message = error.toUserMessage ? error.toUserMessage() : 'Failed to update metadata';
    showNotification('❌ ' + message, 'error');
  }
}

function showNotification(message, type) {
  const notification = document.createElement('div');
  notification.textContent = message;
  notification.style.position = 'fixed';
  notification.style.top = '20px';
  notification.style.right = '20px';
  notification.style.padding = '15px 20px';
  notification.style.borderRadius = '5px';
  notification.style.zIndex = '10000';
  notification.style.fontWeight = '600';
  notification.style.boxShadow = '0 4px 6px rgba(0,0,0,0.1)';

  if (type === 'success') {
    notification.style.background = '#10b981';
    notification.style.color = 'white';
  } else if (type === 'info') {
    notification.style.background = '#8b5cf6';
    notification.style.color = 'white';
  } else {
    notification.style.background = '#ef4444';
    notification.style.color = 'white';
  }

  document.body.appendChild(notification);

  setTimeout(() => {
    notification.remove();
  }, 3000);
}

// Close metadata modal when clicking outside
// Track mousedown target to prevent text selection drag from closing modal
let metadataModalMouseDown = null;
document.addEventListener('mousedown', (event) => {
  metadataModalMouseDown = event.target;
});
document.addEventListener('click', (event) => {
  const modal = document.getElementById('metadata-modal');
  if (event.target === modal && metadataModalMouseDown === modal) {
    closeMetadataModal();
  }
  metadataModalMouseDown = null;
});

// Delete an issue - opens the modal
function deleteIssue(magazineId, title) {
  openDeleteModal(magazineId, title);
}

// Confirm delete from modal
// eslint-disable-next-line no-unused-vars -- Called from HTML onclick handlers
async function confirmDeleteIssue() {
  if (!pendingDeleteId) {
    console.error('No issue selected for deletion');
    return;
  }

  const deleteOption = document.querySelector('input[name="delete-option"]:checked');
  if (!deleteOption) {
    console.error('No delete option selected');
    return;
  }

  const deleteFiles = deleteOption.value === 'delete-files';
  const markAsBad = document.getElementById('mark-as-bad-file')?.checked || false;

  // Count total issues before deletion
  const issueCards = document.querySelectorAll('.issue-card');
  const isLastIssue = issueCards.length === 1;

  try {
    const response = await APIHelper.executeWithErrorHandling(async () => {
      return await APIClient.delete(
        `/api/periodicals/${pendingDeleteId}?delete_files=${deleteFiles}&mark_as_bad=${markAsBad}`
      );
    }, 'Periodical');

    const result = await response.json();

    // Show success message
    const statusDiv = document.getElementById('status-message');
    statusDiv.className = 'status-success mt-20 p-15 rounded';
    statusDiv.textContent = `✓ ${result.message}`;
    statusDiv.style.display = 'block';

    // Close modal
    closeDeleteModal();

    // After a short delay, handle the result
    setTimeout(() => {
      if (isLastIssue) {
        // If this was the last issue, go back to library
        statusDiv.textContent = '✓ Last issue deleted. Returning to library...';
        setTimeout(() => {
          window.location.href = '/#library';
        }, 1000);
      } else {
        // Reload to show updated issue list
        statusDiv.textContent = '✓ Issue deleted. Refreshing...';
        setTimeout(() => {
          location.reload();
        }, 1000);
      }
    }, 1500);
  } catch (error) {
    console.error('[Periodical] Error deleting issue:', error);
    const statusDiv = document.getElementById('status-message');
    statusDiv.className = 'status-error mt-20 p-15 rounded';
    const message = error.toUserMessage ? error.toUserMessage() : error.message;
    statusDiv.textContent = `✗ Error: ${message}`;
    statusDiv.style.display = 'block';
  }
}

// eslint-disable-next-line no-unused-vars -- Called from HTML onclick handlers
function goBack() {
  // If we came from a stack page, go back there
  if (window._stackReturnUrl) {
    window.location.href = window._stackReturnUrl;
    return;
  }
  // Navigate to main page with library hash
  window.location.href = '/#library';
}

// Detect if navigated from a stack detail page and update breadcrumb
(function initBreadcrumb() {
  try {
    const ref = document.referrer;
    if (ref) {
      const refUrl = new URL(ref);
      const stackMatch = refUrl.pathname.match(/^\/stacks\/([^/]+)/);
      if (stackMatch) {
        window._stackReturnUrl = refUrl.pathname;
        const breadcrumb = document.getElementById('breadcrumb');
        if (breadcrumb) {
          const stackSlug = stackMatch[1];
          const title = document.getElementById('periodical-title')?.textContent || '';
          breadcrumb.innerHTML =
            `<a href="/#library">Library</a>` +
            `<span class="separator">/</span>` +
            `<a href="/#stacks">Stacks</a>` +
            `<span class="separator">/</span>` +
            `<a href="/stacks/${stackSlug}">${decodeURIComponent(stackSlug).replace(/-/g, ' ')}</a>` +
            `<span class="separator">/</span>` +
            `<span class="current">${title}</span>`;
        }
      }
    }
  } catch {
    // Ignore referrer parsing errors
  }
})();

// Move issue modal functions
// eslint-disable-next-line no-unused-vars -- Called from HTML onclick handlers
async function openMoveIssueModal() {
  if (!currentMagazineId) {
    alert('No magazine selected');
    return;
  }

  const modal = document.getElementById('move-issue-modal');
  const loading = document.getElementById('move-issue-loading');
  const options = document.getElementById('move-issue-options');
  const select = document.getElementById('target-tracking-select');

  modal.classList.remove(CSS_CLASSES.HIDDEN);
  loading.classList.remove(CSS_CLASSES.HIDDEN);
  options.classList.add(CSS_CLASSES.HIDDEN);

  try {
    // Fetch all tracking records
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.get('/api/periodicals/tracking?limit=1000');
      return await response.json();
    }, 'Periodical');

    const trackingRecords = data.tracked_magazines || [];

    // Clear and populate select
    select.innerHTML = '<option value="">Select a tracking record...</option>';

    trackingRecords.forEach((tracking) => {
      // Don't show current tracking as an option
      if (tracking.id === currentMagazineData.tracking_id) {
        return;
      }

      const option = document.createElement('option');
      option.value = tracking.id;
      option.textContent = `${tracking.title} (${tracking.category || 'Auto-detect'} - ${tracking.language || 'English'})`;
      select.appendChild(option);
    });

    // Show options
    loading.classList.add(CSS_CLASSES.HIDDEN);
    options.classList.remove(CSS_CLASSES.HIDDEN);

    // Add change listener to enable/disable move button
    select.onchange = function () {
      document.getElementById('confirm-move-btn').disabled = !this.value;
    };
  } catch (error) {
    console.error('[Periodical] Error loading tracking records:', error);
    const message = error.toUserMessage ? error.toUserMessage() : 'Failed to load tracking options';
    alert(message + ': ' + error.message);
    closeMoveIssueModal();
  }
}

function closeMoveIssueModal() {
  document.getElementById('move-issue-modal').classList.add(CSS_CLASSES.HIDDEN);
}

// eslint-disable-next-line no-unused-vars -- Called from HTML onclick handlers
async function confirmMoveIssue() {
  const targetTrackingId = document.getElementById('target-tracking-select').value;

  if (!targetTrackingId || !currentMagazineId) {
    alert('Please select a tracking record');
    return;
  }

  const confirmBtn = document.getElementById('confirm-move-btn');
  confirmBtn.disabled = true;
  confirmBtn.textContent = 'Moving...';

  try {
    // Count total issues before moving to detect if this is the last one
    const issueCards = document.querySelectorAll('.issue-card');
    const isLastIssue = issueCards.length === 1;

    const response = await APIHelper.executeWithErrorHandling(async () => {
      return await APIClient.post(
        `/api/periodicals/${currentMagazineId}/move-to-tracking?target_tracking_id=${targetTrackingId}`
      );
    }, 'Periodical');

    const result = await response.json();

    // Show success message
    const statusDiv = document.getElementById('status-message');
    statusDiv.className = 'status-success mt-20 p-15 rounded';
    statusDiv.textContent = `✓ ${result.message}`;
    statusDiv.style.display = 'block';

    // Close modals
    closeMoveIssueModal();
    closeMetadataModal();

    // If this was the last issue, redirect to library instead of reloading
    if (isLastIssue) {
      statusDiv.textContent = '✓ Last issue moved. Returning to library...';
      setTimeout(() => {
        window.location.href = '/#library';
      }, 1500);
    } else {
      // Otherwise just reload to show updated list
      setTimeout(() => {
        location.reload();
      }, 1500);
    }
  } catch (error) {
    console.error('[Periodical] Error moving issue:', error);
    const message = error.toUserMessage ? error.toUserMessage() : error.message;
    alert('Failed to move issue: ' + message);
    confirmBtn.disabled = false;
    confirmBtn.textContent = 'Move Issue';
  }
}

// Toggle special edition status
// eslint-disable-next-line no-unused-vars -- Called from HTML onclick handlers
async function toggleSpecialEdition() {
  if (!currentMagazineId || !currentMagazineData) {
    alert('No magazine selected');
    return;
  }

  const isCurrentlySpecial = isSpecialEdition(currentMagazineData);

  const toggleBtn = document.getElementById('toggle-special-btn');
  const originalText = toggleBtn.textContent;
  toggleBtn.disabled = true;
  toggleBtn.textContent = 'Updating...';

  try {
    const response = await APIHelper.executeWithErrorHandling(async () => {
      return await APIClient.post(
        `/api/periodicals/${currentMagazineId}/toggle-special-edition?is_special=${!isCurrentlySpecial}`
      );
    }, 'Periodical');

    const result = await response.json();

    // Show success message
    const statusDiv = document.getElementById('status-message');
    statusDiv.className = 'status-success mt-20 p-15 rounded';
    statusDiv.textContent = `✓ ${result.message}`;
    statusDiv.style.display = 'block';

    // Close modal
    closeMetadataModal();

    // Reload page after a delay
    setTimeout(() => {
      location.reload();
    }, 1500);
  } catch (error) {
    console.error('[Periodical] Error toggling special edition:', error);
    const message = error.toUserMessage ? error.toUserMessage() : error.message;
    alert('Failed to update special edition status: ' + message);
    toggleBtn.disabled = false;
    toggleBtn.textContent = originalText;
  }
}

// Expose functions to global scope for HTML onclick handlers
// Must be done immediately so they're available when HTML loads
window.goBack = goBack;
window.closeDeleteModal = closeDeleteModal;
window.confirmDeleteIssue = confirmDeleteIssue;
window.closeMetadataModal = closeMetadataModal;
window.enableMetadataEdit = enableMetadataEdit;
window.cancelMetadataEdit = cancelMetadataEdit;
window.saveMetadataEdit = saveMetadataEdit;
window.toggleSpecialEdition = toggleSpecialEdition;
window.openMoveIssueModal = openMoveIssueModal;
window.closeMoveIssueModal = closeMoveIssueModal;
window.confirmMoveIssue = confirmMoveIssue;
window.previewCoverUpload = previewCoverUpload;
window.clearCoverUpload = clearCoverUpload;

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
  // Ensure delete modal is closed on page load
  const deleteModal = document.getElementById('delete-modal');
  if (deleteModal && typeof deleteModal.close === 'function') {
    deleteModal.close();
  }

  try {
    renderIssues();
    // If yearsData is empty or no issues were rendered, show a message
    const issuesContainer = document.getElementById('issues-container');
    if (!issuesContainer || issuesContainer.innerHTML.includes('No issues found')) {
      // Add a back button message if all issues are deleted
      const message = document.createElement('div');
      message.style.textAlign = 'center';
      message.style.padding = '40px';
      message.style.color = 'var(--text-secondary)';
      message.innerHTML =
        `<p>This periodical has no issues remaining.</p><p><button onclick="goBack()" class="back-button">← ${window._stackReturnUrl ? 'Back to Stack' : 'Back to Library'}</button></p>`;
      const statusDiv = document.getElementById('status-message');
      if (statusDiv && statusDiv.style.display === 'none') {
        // Show helpful message if not already showing deletion success
      }
    }
  } catch (error) {
    console.error('Error rendering issues:', error);
    const errorDiv = document.getElementById('status-message');
    if (errorDiv) {
      errorDiv.className = 'status-error mt-20 p-15 rounded';
      errorDiv.textContent = `Error loading issues: ${error.message}`;
      errorDiv.style.display = 'block';
    }
  }
});
