/**
 * Constants Module
 * Centralized constants for element IDs, status messages, CSS classes, timeouts, and patterns
 */

// ============================================================================
// Element IDs
// ============================================================================

export const ELEMENT_IDS = {
  // Tracking elements
  TRACKING_STATUS: 'tracking-status',
  TRACKING_SEARCH_LOADING: 'tracking-search-loading',
  TRACKING_SEARCH_RESULT: 'tracking-search-result',
  TRACKING_SEARCH_ERROR: 'tracking-search-error',
  TRACKING_SEARCH_QUERY: 'tracking-search-query',
  SEARCH_ISSUES_CONTENT: 'search-issues-content',
  EDIT_TRACKING_MODAL: 'edit-tracking-modal',
  SEARCH_ISSUES_MODAL: 'search-issues-modal',
  NEW_TRACKING_LANGUAGE: 'new-tracking-language',
  NEW_TRACKING_COUNTRY: 'new-tracking-country',
  NEW_TRACKING_CATEGORY: 'new-tracking-category',
  EDIT_TRACKING_LANGUAGE: 'edit-tracking-language',
  EDIT_TRACKING_COUNTRY: 'edit-tracking-country',
  SEARCH_FILTER_LANGUAGE: 'search-filter-language',
  SEARCH_FILTER_COUNTRY: 'search-filter-country',

  // Downloads elements
  DOWNLOADS_STATUS: 'downloads-status',
  FAILED_DOWNLOADS_CONTAINER: 'failed-downloads-container',
  MANAGE_FAILED_MODAL: 'manage-failed-modal',
  MANAGE_FAILED_MODAL_CONTENT: 'manage-failed-modal-content',
  MANAGE_QUEUE_MODAL: 'manage-queue-modal',
  MANAGE_QUEUE_MODAL_CONTENT: 'manage-queue-modal-content',
  MODAL_QUEUE_STATUS: 'modal-queue-status',
  MODAL_FAILED_STATUS: 'modal-failed-status',
  QUEUE_EMPTY: 'queue-empty',
  QUEUE_TABLE_CONTAINER: 'queue-table-container',
  QUEUE_BODY: 'queue-body',
  QUEUE_STATS: 'queue-stats',
  CLEANUP_PREVIEW: 'cleanup-preview',
  CLEANUP_COUNT: 'cleanup-count',
  CLEANUP_STATUS: 'cleanup-status',
  CLEANUP_HOURS: 'cleanup-hours',

  // Library elements
  LIBRARY_STATUS: 'library-status',
  LIBRARY_CONTENT: 'library-content',
  PERIODICALS_GRID: 'periodicals-grid',
  LIBRARY_SORT_TOGGLE: 'library-sort-toggle',
  DELETE_MODAL: 'delete-modal',
  DELETE_MODAL_TITLE: 'delete-modal-title',
  DELETE_REMOVE_TRACKING: 'delete-remove-tracking',

  // Import elements
  IMPORT_STATUS: 'import-status',
  IMPORT_MESSAGE: 'import-message',
  IMPORT_CATEGORY: 'import-category',
  IMPORT_AUTO_TRACK: 'import-auto-track',
  IMPORT_TRACKING_MODE: 'import-tracking-mode',
  IMPORT_ORGANIZE_PATTERN: 'import-organization-pattern',
  IMPORT_MODAL_ORGANIZE_PATTERN: 'import-modal-organize-pattern',
  IMPORT_ENABLE_TEXT_SCAN: 'import-enable-text-scan',
  IMPORT_ENABLE_OCR: 'import-enable-ocr',

  // Tasks elements
  TASKS_STATUS: 'tasks-status',
  TASKS_TAB: 'tasks-tab',

  // OCR Queue elements
  OCR_QUEUE_STATUS: 'ocr-queue-status',
  OCR_QUEUE_CONTAINER: 'ocr-queue-container',

  // Settings elements
  SETTINGS_STATUS: 'settings-status',
  THEME_MODE: 'theme-mode',
};

// ============================================================================
// Status Messages
// ============================================================================

export const STATUS_MESSAGES = {
  // Tracking messages
  ENTER_TITLE: 'Please enter a periodical title',
  SEARCH_FAILED: 'Failed to search for issues',
  TRACKING_SAVED: 'Tracking saved successfully',
  TRACKING_UPDATED: 'Tracking updated successfully',
  TRACKING_REMOVED: 'Tracking removed',
  TRACKING_LOAD_FAILED: 'Failed to load tracked periodicals',
  FORM_OPTIONS_FAILED: 'Failed to load form options',

  // Downloads messages
  RETRY_SUCCESS: 'Retry initiated successfully',
  RETRY_FAILED: 'Failed to retry download',
  CLEANUP_SUCCESS: 'Cleanup completed successfully',
  CLEANUP_FAILED: 'Cleanup failed',
  DOWNLOAD_REMOVED: 'Failed download removed',
  NO_FAILED_ITEMS: 'No failed items to retry',
  DOWNLOADS_LOAD_FAILED: 'Error loading failed downloads',

  // Library messages
  LIBRARY_LOAD_FAILED: 'Failed to load library',
  DELETE_SUCCESS: 'Issue deleted successfully',
  DELETE_NO_SELECTION: 'Error: No periodical selected for deletion. Please try again.',

  // Import messages
  IMPORT_SUCCESS: 'Import completed successfully',
  IMPORT_FAILED: 'Import failed',
  NO_FILES_TO_IMPORT: 'No files to import',

  // Tasks messages
  TASK_RUNNING: 'Task is running...',
  TASK_ERROR: 'Error running task',

  // OCR Queue messages
  OCR_QUEUE_LOAD_FAILED: 'Error loading OCR queue',

  // Generic messages
  LOADING: 'Loading...',
  ERROR_GENERIC: 'An error occurred',
  SUCCESS_GENERIC: 'Operation completed successfully',
};

// ============================================================================
// CSS Class Names
// ============================================================================

export const CSS_CLASSES = {
  // Visibility
  HIDDEN: 'hidden',
  ACTIVE: 'active',

  // Components
  MODAL: 'modal',
  MODAL_VISIBLE: 'modal-visible',
  TAB: 'tab',
  NAV_BTN: 'nav-btn',

  // Status message types (will be added in Phase 1)
  STATUS_MESSAGE: 'status-message',
  STATUS_SUCCESS: 'status-success',
  STATUS_ERROR: 'status-error',
  STATUS_WARNING: 'status-warning',
  STATUS_INFO: 'status-info',

  // Text color classes
  TEXT_ERROR: 'text-error',

  // Highlight effects
  HIGHLIGHT_SUCCESS: 'highlight-success',

  // Tracking badges (will be added in Phase 1)
  BADGE_DOWNLOAD_ALL: 'badge-download-all',
  BADGE_DOWNLOAD_NEW: 'badge-download-new',
  BADGE_WATCH: 'badge-watch',

  // Issue cards (will be added in Phase 1)
  ISSUE_CARD: 'issue-card',
  ISSUE_CARD_SELECTED: 'issue-card-selected',
  ISSUE_CARD_DOWNLOADED: 'issue-card-downloaded',

  // Result items (will be added in Phase 1)
  RESULT_ITEM: 'result-item',

  // Empty states (will be added in Phase 1)
  EMPTY_STATE: 'empty-state',
  EMPTY_STATE_ICON: 'empty-state-icon',
  EMPTY_STATE_TITLE: 'empty-state-title',
  EMPTY_STATE_SUBTITLE: 'empty-state-subtitle',

  // Stats boxes (will be added in Phase 1)
  STATS_SUMMARY: 'stats-summary',
  STAT_BOX: 'stat-box',
  STAT_BOX_VALUE: 'stat-box-value',
  STAT_BOX_LABEL: 'stat-box-label',
  STAT_BOX_SUBLABEL: 'stat-box-sublabel',

  // Progress bar (will be added in Phase 1)
  PROGRESS_BAR_SUCCESS: 'progress-bar-success',
  PROGRESS_BAR_ERROR: 'progress-bar-error',
};

// ============================================================================
// Timeouts (milliseconds)
// ============================================================================

export const TIMEOUTS = {
  // Status message auto-hide timeouts
  AUTO_HIDE_STATUS: 3000, // Standard status message auto-hide
  AUTO_HIDE_SUCCESS: 2000, // Success message auto-hide (faster)
  AUTO_HIDE_LONG: 5000, // Long status message auto-hide
  AUTO_HIDE_IMPORT: 4000, // Import status message auto-hide

  // Polling and refresh intervals
  POLLING_INTERVAL: 5000, // Standard polling interval
  LONG_POLLING: 10000, // Long polling interval (OCR queue)

  // Debounce timeouts
  DEBOUNCE_SHORT: 300, // Short debounce
  DEBOUNCE_LONG: 500, // Long debounce

  // Reload timeouts
  RELOAD_DELAY: 1000, // Delay before page reload
  IMPORT_RELOAD_DELAY: 500, // Delay before reloading after import
};

// ============================================================================
// Regex Patterns
// ============================================================================

export const PATTERNS = {
  // Date patterns
  YEAR_MONTH: /\((\d{4})[-–](\d{2})\)/,
  YEAR_STANDALONE: /\((\d{4})\)/,
  YEAR_RANGE: /(\d{4})-(\d{4})/,

  // Issue patterns
  ISSUE_NUMBER: /#(\d+)/,
  ISSUE_PREFIX: /No\.?\s*(\d+)/i,

  // Month patterns
  MONTH_NAME:
    /(January|February|March|April|May|June|July|August|September|October|November|December)/i,
  MONTH_ABBR: /(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)/i,

  // Season patterns
  SEASON: /(Spring|Summer|Fall|Autumn|Winter)/i,

  // Volume patterns
  VOLUME: /Vol\.?\s*(\d+)/i,
};

// ============================================================================
// Month Names
// ============================================================================

export const NUMBER_TO_MONTH = {
  1: 'January',
  2: 'February',
  3: 'March',
  4: 'April',
  5: 'May',
  6: 'June',
  7: 'July',
  8: 'August',
  9: 'September',
  10: 'October',
  11: 'November',
  12: 'December',
};

/**
 * Full month names (lowercase) for lookup
 */
export const MONTH_NAMES_LOWER = [
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

/**
 * Month abbreviations (lowercase) for lookup
 */
export const MONTH_ABBR_LOWER = [
  'jan',
  'feb',
  'mar',
  'apr',
  'may',
  'jun',
  'jul',
  'aug',
  'sep',
  'oct',
  'nov',
  'dec',
];

// ============================================================================
// Badge Configurations
// ============================================================================

export const BADGE_CONFIGS = {
  ALL_ISSUES: {
    icon: '⬇️',
    text: 'All Issues',
    class: 'badge-download-all',
  },
  NEW_ISSUES: {
    icon: '⬇️',
    text: 'New Issues',
    class: 'badge-download-new',
  },
  WATCH_ONLY: {
    icon: '👁️',
    text: 'Watch Only',
    class: 'badge-watch',
  },
};

// ============================================================================
// HTTP Status Codes
// ============================================================================

export const HTTP_STATUS = {
  OK: 200,
  CREATED: 201,
  BAD_REQUEST: 400,
  UNAUTHORIZED: 401,
  FORBIDDEN: 403,
  NOT_FOUND: 404,
  INTERNAL_SERVER_ERROR: 500,
};

// ============================================================================
// Local Storage Keys
// ============================================================================

export const STORAGE_KEYS = {
  THEME: 'curator-theme',
  AUTH_TOKEN: 'auth_token',
};

// ============================================================================
// API Query Limits
// ============================================================================

export const API_LIMITS = {
  TRACKING_LIST: 1000, // Max tracked periodicals to fetch
  PERIODICAL_LIST: 10000, // Max library periodicals to fetch
};

// ============================================================================
// Default Values
// ============================================================================

export const DEFAULTS = {
  THEME: 'dark',
  ORGANIZATION_PATTERN: '{category}/{title}/{year}/',
  CLEANUP_HOURS: 24,
  ENABLE_TEXT_SCAN: true,
  ENABLE_OCR: true,
};

// ============================================================================
// Date Constants
// ============================================================================

export const DATE_CONSTANTS = {
  UNKNOWN_ISSUE_DATE_YEAR: 1900, // Sentinel year for periodicals without detectable dates
};
