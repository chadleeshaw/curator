/**
 * Comic Reader Module
 * Thin wrapper around PageReader for CBZ/CBR content
 */

import { PageReader, setupKeyboardNavigation, setupMobileSidebar } from './page-reader.js';

// Create Comic reader instance
const comicReader = new PageReader('comic');
window.comicReader = comicReader;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  comicReader.init();
});

// Setup keyboard navigation
setupKeyboardNavigation({
  previousItem: () => comicReader.previousPage(),
  nextItem: () => comicReader.nextPage(),
  adjustZoom: (delta) => comicReader.adjustZoom(delta),
  resetZoom: () => comicReader.resetZoom(),
  toggleFullscreen: () => comicReader.toggleFullscreen(),
  toggleSpreadMode: () => comicReader.toggleSpreadMode(),
});

// Setup mobile sidebar toggle
setupMobileSidebar();
