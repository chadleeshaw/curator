/**
 * PDF Reader Module
 * Thin wrapper around PageReader for PDF content
 */

import { PageReader, setupKeyboardNavigation, setupMobileSidebar } from './page-reader.js';

// Create PDF reader instance
const pdfReader = new PageReader('pdf');
window.pdfReader = pdfReader;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  pdfReader.init();
});

// Setup keyboard navigation
setupKeyboardNavigation(pdfReader);

// Setup mobile sidebar toggle
setupMobileSidebar();
