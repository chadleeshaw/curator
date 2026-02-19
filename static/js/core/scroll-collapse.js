/**
 * Scroll Collapse Utility
 * Collapses a `.collapsible-header` when the user scrolls down,
 * and re-expands it when scrolled back to the top.
 *
 * Uses hysteresis (different collapse/expand thresholds) and a page-height
 * check to prevent bounce loops when collapsing would shrink the page
 * enough to trigger an immediate re-expand.
 *
 * @module scroll-collapse
 */

const COLLAPSE_AT = 60;
const EXPAND_AT = 10;

/**
 * Initialize scroll-collapse behavior for the current page.
 * Safe to call multiple times; only one listener is attached.
 */
export function initScrollCollapse() {
  let collapsed = false;

  window.addEventListener(
    'scroll',
    () => {
      const y = window.scrollY;
      if (!collapsed && y > COLLAPSE_AT) {
        const hdr = document.querySelector('.collapsible-header');
        const saved = hdr ? hdr.offsetHeight + 40 : 200;
        const remaining = document.documentElement.scrollHeight - saved;
        if (remaining > window.innerHeight + COLLAPSE_AT) {
          collapsed = true;
          document.body.classList.add('header-collapsed');
        }
      } else if (collapsed && y <= EXPAND_AT) {
        collapsed = false;
        document.body.classList.remove('header-collapsed');
      }
    },
    { passive: true }
  );
}
