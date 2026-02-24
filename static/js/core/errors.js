/**
 * Custom Error Classes Module
 * Domain-specific error types for better error handling and debugging
 */

/**
 * Error thrown when an API request fails
 * @extends Error
 */
export class APIError extends Error {
  /**
   * Create an API error
   * @param {string} message - Error message describing what went wrong
   * @param {number} statusCode - HTTP status code from the response
   * @param {string} endpoint - The API endpoint that was called
   * @param {Object} [response=null] - The raw response data if available
   */
  constructor(message, statusCode, endpoint, response = null) {
    super(message);
    this.name = 'APIError';
    this.statusCode = statusCode;
    this.endpoint = endpoint;
    this.response = response;
    this.timestamp = new Date().toISOString();
  }

  /**
   * Get a user-friendly error message
   * @returns {string} User-friendly message
   */
  toUserMessage() {
    if (this.statusCode === 401) {
      return 'Your session has expired. Please log in again.';
    }
    if (this.statusCode === 403) {
      return 'You do not have permission to perform this action.';
    }
    if (this.statusCode === 404) {
      return 'The requested resource was not found.';
    }
    if (this.statusCode >= 500) {
      return 'A server error occurred. Please try again later.';
    }
    return this.message;
  }
}

/**
 * Error thrown when form or input validation fails
 * @extends Error
 */
export class ValidationError extends Error {
  /**
   * Create a validation error
   * @param {string} message - Error message describing the validation failure
   * @param {string} field - The field name that failed validation
   * @param {*} [value=undefined] - The invalid value that was provided
   * @param {string} [rule=null] - The validation rule that was violated
   */
  constructor(message, field, value = undefined, rule = null) {
    super(message);
    this.name = 'ValidationError';
    this.field = field;
    this.value = value;
    this.rule = rule;
  }

  /**
   * Get a user-friendly error message
   * @returns {string} User-friendly message
   */
  toUserMessage() {
    return this.message;
  }
}

/**
 * Error thrown when a network request fails
 * @extends Error
 */
export class NetworkError extends Error {
  /**
   * Create a network error
   * @param {string} message - Error message
   * @param {string} [url=null] - The URL that failed
   * @param {Error} [originalError=null] - The original error that was caught
   */
  constructor(message, url = null, originalError = null) {
    super(message);
    this.name = 'NetworkError';
    this.url = url;
    this.originalError = originalError;
  }

  /**
   * Get a user-friendly error message
   * @returns {string} User-friendly message
   */
  toUserMessage() {
    return 'Unable to connect to the server. Please check your connection and try again.';
  }
}

/**
 * Error thrown when authentication fails or session expires
 * @extends Error
 */
export class AuthenticationError extends Error {
  /**
   * Create an authentication error
   * @param {string} message - Error message
   * @param {string} [reason='unknown'] - The reason for authentication failure
   */
  constructor(message, reason = 'unknown') {
    super(message);
    this.name = 'AuthenticationError';
    this.reason = reason;
  }

  /**
   * Get a user-friendly error message
   * @returns {string} User-friendly message
   */
  toUserMessage() {
    if (this.reason === 'expired') {
      return 'Your session has expired. Please log in again.';
    }
    if (this.reason === 'invalid') {
      return 'Invalid credentials. Please check your username and password.';
    }
    return 'Authentication failed. Please log in again.';
  }
}
