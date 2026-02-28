/**
 * @module periodical-metadata
 * @description Metadata modal view/edit/save and notifications for the periodical detail page.
 */

/* global FileReader */

import { APIClient, APIHelper } from '../core/api.js';
import { CSS_CLASSES } from '../core/constants.js';
import { getSpecialEditionValue, isSpecialEdition } from './periodical-rendering.js';
import { escapeHtml } from '../readers/reader-utils.js';

// Module-level references to shared state (set via init)
let _state = null;

/**
 * Initialise this module with a reference to the shared state object.
 * Must be called before any other function in this module.
 * @param {Object} state - Shared state: { currentPeriodicalId, currentPeriodicalData, ... }
 */
export function initMetadata(state) {
  _state = state;
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

/**
 * Show a transient notification banner.
 * @param {string} message
 * @param {'success'|'info'|'error'} type
 */
export function showNotification(message, type) {
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

// ---------------------------------------------------------------------------
// Metadata modal – view
// ---------------------------------------------------------------------------

/**
 * Fetch metadata for a periodical and open the modal.
 * @param {number} periodicalId
 * @returns {Promise<void>}
 */
export async function viewMetadata(periodicalId) {
  try {
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.get(`/api/periodicals/${periodicalId}`);
      return await response.json();
    }, 'Periodical');
    displayMetadata(data);
  } catch (error) {
    console.error('[Periodical] Error fetching metadata:', error);
    const message = error.toUserMessage ? error.toUserMessage() : 'Failed to load metadata';
    showNotification(message, 'error');
  }
}

/**
 * Render metadata into the modal and open it.
 * @param {Object} data - Periodical data from the API
 */
export function displayMetadata(data) {
  const metadataBody = document.getElementById('metadata-body');
  metadataBody.innerHTML = '';

  // Store current magazine data in shared state
  _state.currentPeriodicalId = data.id;
  _state.currentPeriodicalData = data;

  // Update special edition button text based on current status
  const isSpecial = isSpecialEdition(data);
  const toggleBtn = document.getElementById('toggle-special-btn');
  if (toggleBtn) {
    const starSvg =
      '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>';
    if (isSpecial) {
      toggleBtn.innerHTML = `${starSvg} Unmark Special Edition`;
      toggleBtn.title = 'Remove special edition status';
    } else {
      toggleBtn.innerHTML = `${starSvg} Mark as Special Edition`;
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
    '<h4 style="margin: 0 0 10px 0; color: var(--primary-color);">Database Fields</h4>';
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
      '<h4 style="margin: 0 0 10px 0; color: var(--primary-color);">Derived Metadata (Merged from Scans)</h4>';
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
            file_scan: 'File',
            text_scan: 'Text',
            ocr_scan: 'OCR',
          }[source] || source;

        const confBadge =
          typeof confidence === 'number' ? ` (${(confidence * 100).toFixed(0)}%)` : '';
        valueDiv.innerHTML = `${escapeHtml(String(value))} <span style="font-size: 0.85em; color: var(--text-secondary); margin-left: 8px;">${sourceBadge}${confBadge}</span>`;

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

/**
 * Close the metadata modal and reset to view mode.
 */
export function closeMetadataModal() {
  document.getElementById('metadata-modal').classList.remove('show');
  // Reset to view mode when closing
  cancelMetadataEdit();
}

// ---------------------------------------------------------------------------
// Metadata modal – edit
// ---------------------------------------------------------------------------

/**
 * Switch the metadata modal into edit mode.
 */
export function enableMetadataEdit() {
  if (!_state.currentPeriodicalData) return;

  // Hide view, show edit form
  document.getElementById('metadata-body').classList.add(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-edit-form').classList.remove(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-view-buttons').classList.add(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-edit-buttons').classList.remove(CSS_CLASSES.HIDDEN);

  // Check if this issue is linked to tracking
  const hasTracking =
    _state.currentPeriodicalData.tracking_id !== null &&
    _state.currentPeriodicalData.tracking_id !== undefined;

  // Populate form fields
  const languageField = document.getElementById('edit-language');
  languageField.value = _state.currentPeriodicalData.language || '';

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

  // Year field - read from derived_metadata first, fall back to extra_metadata
  document.getElementById('edit-year').value =
    _state.currentPeriodicalData.derived_metadata?.year?.value ??
    _state.currentPeriodicalData.metadata?.year ??
    '';

  // Month field - read month_name from derived_metadata first, fall back to extra_metadata
  document.getElementById('edit-month').value =
    _state.currentPeriodicalData.derived_metadata?.month_name?.value ??
    _state.currentPeriodicalData.metadata?.month ??
    '';

  // Country field - read from derived_metadata first, fall back to extra_metadata
  const countryField = document.getElementById('edit-country');
  countryField.value =
    _state.currentPeriodicalData.derived_metadata?.country?.value ??
    _state.currentPeriodicalData.metadata?.country ??
    '';

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
  // Read from derived_metadata first (structured format), fall back to extra_metadata (legacy)
  document.getElementById('edit-issue-number').value =
    _state.currentPeriodicalData.derived_metadata?.issue_number?.value ??
    _state.currentPeriodicalData.metadata?.issue_number ??
    '';
  document.getElementById('edit-volume').value =
    _state.currentPeriodicalData.derived_metadata?.volume?.value ??
    _state.currentPeriodicalData.metadata?.volume ??
    '';

  // Always show special edition field in edit mode
  const specialField = document.getElementById('special-edition-name-field');
  const specialEditionValue = getSpecialEditionValue(_state.currentPeriodicalData);
  const isSpecial = isSpecialEdition(_state.currentPeriodicalData);
  specialField.classList.remove(CSS_CLASSES.HIDDEN);
  document.getElementById('edit-special-edition').value = specialEditionValue || '';

  // Update the label to indicate if it's currently marked as special edition
  const specialLabel = specialField.querySelector('label');
  if (isSpecial) {
    specialLabel.textContent = 'Special Edition Name';
  } else {
    specialLabel.textContent = 'Special Edition Name';
  }

  // Cover page field
  document.getElementById('edit-cover-page').value =
    (_state.currentPeriodicalData.metadata && _state.currentPeriodicalData.metadata.cover_page) ||
    '1';
}

/**
 * Cancel edit mode and return to view mode.
 */
export function cancelMetadataEdit() {
  // Show view, hide edit form
  document.getElementById('metadata-body').classList.remove(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-edit-form').classList.add(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-view-buttons').classList.remove(CSS_CLASSES.HIDDEN);
  document.getElementById('metadata-edit-buttons').classList.add(CSS_CLASSES.HIDDEN);
  // Clear any cover upload preview
  clearCoverUpload();
}

/**
 * Preview a selected cover image file.
 * @param {HTMLInputElement} input
 */
export function previewCoverUpload(input) {
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

/**
 * Clear the cover upload preview and file input.
 */
export function clearCoverUpload() {
  const fileInput = document.getElementById('edit-cover-file');
  const preview = document.getElementById('cover-upload-preview');
  const previewImg = document.getElementById('cover-preview-img');

  if (fileInput) fileInput.value = '';
  if (preview) preview.classList.add(CSS_CLASSES.HIDDEN);
  if (previewImg) previewImg.src = '';
}

/**
 * Regenerate thumbnail and queue OCR for the current periodical.
 * @returns {Promise<void>}
 */
export async function regenerateThumbnailOcr() {
  if (!_state.currentPeriodicalId) return;

  showNotification('Regenerating thumbnail and queuing OCR...', 'info');

  try {
    const data = await APIHelper.executeWithErrorHandling(async () => {
      const response = await APIClient.post(
        `/api/periodicals/${_state.currentPeriodicalId}/regenerate-thumbnail-ocr`
      );
      return await response.json();
    }, 'Periodical');

    if (data.skipped) {
      showNotification(data.message, 'info');
      return;
    }

    const ocrNote = data.ocr_queued
      ? 'OCR job queued — metadata will update when processing completes.'
      : data.ocr_message || 'OCR was not queued.';

    showNotification(`Thumbnail regenerated. ${ocrNote}`, 'success');

    // Refresh the metadata modal and page to show updated cover
    await viewMetadata(_state.currentPeriodicalId);
    setTimeout(() => window.location.reload(), 1500);
  } catch (error) {
    console.error('[Periodical] Error regenerating thumbnail/OCR:', error);
    const message = error.toUserMessage
      ? error.toUserMessage()
      : 'Failed to regenerate thumbnail. You can upload a cover manually via Edit Metadata.';
    showNotification(message, 'error');
  }
}

/**
 * Upload a cover image for a periodical.
 * @param {number} periodicalId
 * @returns {Promise<boolean>} True if successfully uploaded, false if no file selected
 */
async function uploadCoverImage(periodicalId) {
  const fileInput = document.getElementById('edit-cover-file');
  if (!fileInput || !fileInput.files || !fileInput.files[0]) {
    return false; // No file to upload
  }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  showNotification('Uploading cover image...', 'info');

  const response = await APIClient.authenticatedFetch(
    `/api/periodicals/${periodicalId}/upload-cover`,
    {
      method: 'POST',
      body: formData,
    }
  );

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to upload cover');
  }

  return true; // Successfully uploaded
}

/**
 * Save the metadata edit form.
 * @returns {Promise<void>}
 */
export async function saveMetadataEdit() {
  if (!_state.currentPeriodicalId) return;

  // Check if this issue is linked to tracking
  const hasTracking =
    _state.currentPeriodicalData.tracking_id !== null &&
    _state.currentPeriodicalData.tracking_id !== undefined;

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
  const currentCoverPage = _state.currentPeriodicalData.metadata?.cover_page || 1;
  const shouldRegenerateCover = coverPage && parseInt(coverPage) !== currentCoverPage;

  // Check if a custom cover image was selected
  const coverFileInput = document.getElementById('edit-cover-file');
  const hasCustomCover = coverFileInput && coverFileInput.files && coverFileInput.files[0];

  try {
    await APIHelper.executeWithErrorHandling(async () => {
      await APIClient.put(`/api/periodicals/${_state.currentPeriodicalId}`, updates);
    }, 'Periodical');

    // Handle cover: custom upload takes priority over page number regeneration
    if (hasCustomCover) {
      await uploadCoverImage(_state.currentPeriodicalId);
    } else if (shouldRegenerateCover) {
      showNotification('Regenerating cover from page ' + coverPage, 'info');
      await APIHelper.executeWithErrorHandling(async () => {
        await APIClient.post(`/api/periodicals/${_state.currentPeriodicalId}/regenerate-cover`, {
          page_number: parseInt(coverPage),
        });
      }, 'Periodical');
    }

    await viewMetadata(_state.currentPeriodicalId);

    // Clear the file input
    clearCoverUpload();

    // Show success message
    showNotification('Metadata updated successfully', 'success');

    // Refresh the page to show updated data
    setTimeout(() => window.location.reload(), 1000);
  } catch (error) {
    console.error('[Periodical] Error updating metadata:', error);
    const message = error.toUserMessage ? error.toUserMessage() : 'Failed to update metadata';
    showNotification('Error: ' + message, 'error');
  }
}

// ---------------------------------------------------------------------------
// Close metadata modal on outside-click
// ---------------------------------------------------------------------------

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
