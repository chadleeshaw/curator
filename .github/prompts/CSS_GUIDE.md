# CSS Guide: Modern, Performant, and Stylish Web Pages

A comprehensive guide to writing excellent CSS for contemporary web applications.

## Table of Contents
- [Core Principles](#core-principles)
- [Performance](#performance)
- [Modern Layout](#modern-layout)
- [Responsive Design](#responsive-design)
- [Typography](#typography)
- [Colors and Theming](#colors-and-theming)
- [Animations and Transitions](#animations-and-transitions)
- [Best Practices](#best-practices)
- [Common Patterns](#common-patterns)

---

## Core Principles

### 1. Use CSS Custom Properties (Variables)
Custom properties enable dynamic theming and reduce code duplication.

```css
:root {
  /* Colors */
  --color-primary: #3b82f6;
  --color-secondary: #8b5cf6;
  --color-success: #10b981;
  --color-error: #ef4444;
  --color-warning: #f59e0b;
  
  /* Typography */
  --font-sans: system-ui, -apple-system, sans-serif;
  --font-mono: 'Monaco', 'Courier New', monospace;
  --font-size-base: 16px;
  --font-size-sm: 0.875rem;
  --font-size-lg: 1.125rem;
  --line-height-base: 1.5;
  
  /* Spacing */
  --space-xs: 0.25rem;
  --space-sm: 0.5rem;
  --space-md: 1rem;
  --space-lg: 1.5rem;
  --space-xl: 2rem;
  --space-2xl: 3rem;
  
  /* Shadows */
  --shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  --shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1);
  --shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1);
  
  /* Border radius */
  --radius-sm: 0.25rem;
  --radius-md: 0.5rem;
  --radius-lg: 1rem;
  --radius-full: 9999px;
  
  /* Transitions */
  --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-base: 250ms cubic-bezier(0.4, 0, 0.2, 1);
  --transition-slow: 350ms cubic-bezier(0.4, 0, 0.2, 1);
}
```

### 2. Mobile-First Approach
Design for mobile devices first, then enhance for larger screens.

```css
/* Mobile first (default) */
.container {
  padding: var(--space-md);
}

/* Tablet and up */
@media (min-width: 768px) {
  .container {
    padding: var(--space-lg);
  }
}

/* Desktop and up */
@media (min-width: 1024px) {
  .container {
    padding: var(--space-xl);
  }
}
```

### 3. Logical Properties
Use logical properties for better internationalization (RTL/LTR support).

```css
/* Instead of margin-left/right */
.element {
  margin-inline-start: var(--space-md);
  margin-inline-end: var(--space-md);
  padding-block: var(--space-sm);
  border-inline-start: 2px solid var(--color-primary);
}
```

---

## Performance

### 1. Minimize Repaints and Reflows
Avoid properties that trigger layout recalculations.

```css
/* ❌ BAD - Triggers layout */
.animated {
  animation: slide 300ms;
}

@keyframes slide {
  from { left: 0; }
  to { left: 100px; }
}

/* ✅ GOOD - Uses compositor */
.animated {
  animation: slide 300ms;
  will-change: transform;
}

@keyframes slide {
  from { transform: translateX(0); }
  to { transform: translateX(100px); }
}
```

### 2. Use `contain` Property
Help the browser optimize rendering.

```css
.card {
  contain: layout style paint;
  /* Or use: contain: content; for most cases */
}

.isolated-component {
  contain: strict; /* Most restrictive, best performance */
}
```

### 3. Optimize Selectors
Keep selectors simple and avoid deep nesting.

```css
/* ❌ BAD - Overly specific and slow */
div.container > ul.list > li.item > a.link:hover {
  color: blue;
}

/* ✅ GOOD - Simple and fast */
.link:hover {
  color: blue;
}
```

### 4. Load Critical CSS Inline
Inline critical above-the-fold CSS, defer the rest.

```html
<!-- Inline critical CSS -->
<style>
  /* Critical styles for above-the-fold content */
  body { margin: 0; font-family: var(--font-sans); }
  .header { /* ... */ }
</style>

<!-- Defer non-critical CSS -->
<link rel="preload" href="styles.css" as="style" onload="this.onload=null;this.rel='stylesheet'">
<noscript><link rel="stylesheet" href="styles.css"></noscript>
```

### 5. Use `content-visibility`
Dramatically improve rendering performance for long pages.

```css
.article-section {
  content-visibility: auto;
  contain-intrinsic-size: 0 500px; /* Estimated height */
}
```

---

## Modern Layout

### 1. CSS Grid for Two-Dimensional Layouts
Grid excels at complex layouts with rows and columns.

```css
/* Responsive grid without media queries */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: var(--space-lg);
}

/* Named grid areas */
.layout {
  display: grid;
  grid-template-areas:
    "header header header"
    "sidebar main aside"
    "footer footer footer";
  grid-template-columns: 200px 1fr 200px;
  grid-template-rows: auto 1fr auto;
  min-height: 100vh;
}

.header { grid-area: header; }
.sidebar { grid-area: sidebar; }
.main { grid-area: main; }
.aside { grid-area: aside; }
.footer { grid-area: footer; }
```

### 2. Flexbox for One-Dimensional Layouts
Perfect for navigation bars, card layouts, and centering.

```css
/* Center content perfectly */
.center {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 100vh;
}

/* Navigation bar */
.nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-md);
}

/* Equal-width columns */
.columns {
  display: flex;
  gap: var(--space-md);
}

.columns > * {
  flex: 1;
}
```

### 3. Container Queries
Style elements based on their container size (modern browsers).

```css
.card-container {
  container-type: inline-size;
  container-name: card;
}

.card {
  display: grid;
}

/* When container is > 400px */
@container card (min-width: 400px) {
  .card {
    grid-template-columns: 150px 1fr;
  }
}
```

### 4. Subgrid
Align nested grid items with parent grid.

```css
.parent-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-md);
}

.nested-grid {
  display: grid;
  grid-column: span 3;
  grid-template-columns: subgrid; /* Inherit parent columns */
}
```

---

## Responsive Design

### 1. Fluid Typography
Scale typography smoothly across screen sizes.

```css
:root {
  /* Using clamp() for fluid typography */
  --font-size-sm: clamp(0.75rem, 0.7rem + 0.25vw, 0.875rem);
  --font-size-base: clamp(1rem, 0.9rem + 0.5vw, 1.125rem);
  --font-size-lg: clamp(1.25rem, 1.1rem + 0.75vw, 1.5rem);
  --font-size-xl: clamp(1.5rem, 1.3rem + 1vw, 2rem);
  --font-size-2xl: clamp(2rem, 1.5rem + 2vw, 3rem);
}

h1 { font-size: var(--font-size-2xl); }
h2 { font-size: var(--font-size-xl); }
h3 { font-size: var(--font-size-lg); }
p { font-size: var(--font-size-base); }
```

### 2. Fluid Spacing
Use clamp() for responsive spacing.

```css
.section {
  padding-block: clamp(2rem, 5vw, 5rem);
  padding-inline: clamp(1rem, 5vw, 3rem);
}
```

### 3. Responsive Images

```css
img {
  max-width: 100%;
  height: auto;
  display: block;
}

/* Modern aspect ratio */
.image-container {
  aspect-ratio: 16 / 9;
  overflow: hidden;
}

.image-container img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center;
}
```

### 4. Breakpoint Variables

```css
:root {
  --breakpoint-sm: 640px;
  --breakpoint-md: 768px;
  --breakpoint-lg: 1024px;
  --breakpoint-xl: 1280px;
  --breakpoint-2xl: 1536px;
}
```

---

## Typography

### 1. System Font Stack
Fast-loading, native fonts for each platform.

```css
:root {
  --font-sans: system-ui, -apple-system, BlinkMacSystemFont, 
               'Segoe UI', 'Roboto', 'Oxygen', 'Ubuntu', 
               'Cantarell', 'Helvetica Neue', sans-serif;
  
  --font-serif: 'Georgia', 'Cambria', 'Times New Roman', 
                'Times', serif;
  
  --font-mono: 'Monaco', 'Menlo', 'Consolas', 
               'Courier New', monospace;
}

body {
  font-family: var(--font-sans);
}
```

### 2. Typographic Scale

```css
:root {
  /* Modular scale (1.250 - Major Third) */
  --font-size-xs: 0.64rem;
  --font-size-sm: 0.8rem;
  --font-size-base: 1rem;
  --font-size-lg: 1.25rem;
  --font-size-xl: 1.563rem;
  --font-size-2xl: 1.953rem;
  --font-size-3xl: 2.441rem;
  --font-size-4xl: 3.052rem;
}
```

### 3. Better Text Rendering

```css
body {
  font-family: var(--font-sans);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

/* Prevent text overflow */
.text-content {
  overflow-wrap: break-word;
  word-wrap: break-word;
  hyphens: auto;
}

/* Limit line length for readability */
.prose {
  max-width: 65ch; /* 65 characters */
}
```

### 4. Text Truncation

```css
/* Single line truncate */
.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Multi-line truncate (3 lines) */
.line-clamp-3 {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}
```

---

## Colors and Theming

### 1. Color System

```css
:root {
  /* Primary colors */
  --color-primary-50: #eff6ff;
  --color-primary-100: #dbeafe;
  --color-primary-200: #bfdbfe;
  --color-primary-500: #3b82f6;
  --color-primary-600: #2563eb;
  --color-primary-900: #1e3a8a;
  
  /* Semantic colors */
  --color-text-primary: #1f2937;
  --color-text-secondary: #6b7280;
  --color-text-muted: #9ca3af;
  --color-bg-primary: #ffffff;
  --color-bg-secondary: #f9fafb;
  --color-border: #e5e7eb;
}

/* Dark mode */
@media (prefers-color-scheme: dark) {
  :root {
    --color-text-primary: #f9fafb;
    --color-text-secondary: #d1d5db;
    --color-text-muted: #9ca3af;
    --color-bg-primary: #111827;
    --color-bg-secondary: #1f2937;
    --color-border: #374151;
  }
}

/* Manual dark mode toggle */
[data-theme="dark"] {
  --color-text-primary: #f9fafb;
  --color-text-secondary: #d1d5db;
  --color-bg-primary: #111827;
  /* ... */
}
```

### 2. Color Contrast

```css
/* Ensure proper contrast ratios (WCAG AA: 4.5:1 for normal text) */
.button-primary {
  background-color: var(--color-primary-600);
  color: white; /* High contrast */
}

/* Use semi-transparent colors for overlays */
.overlay {
  background-color: rgb(0 0 0 / 0.5);
}

/* Modern color syntax */
.element {
  color: rgb(59 130 246);
  background: rgb(59 130 246 / 0.1); /* 10% opacity */
}
```

### 3. Gradients

```css
/* Linear gradients */
.gradient-1 {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

/* Radial gradients */
.gradient-2 {
  background: radial-gradient(circle at top right, #667eea, #764ba2);
}

/* Mesh gradient effect */
.gradient-mesh {
  background: 
    radial-gradient(at 40% 20%, #667eea 0, transparent 50%),
    radial-gradient(at 80% 0%, #764ba2 0, transparent 50%),
    radial-gradient(at 0% 50%, #f093fb 0, transparent 50%),
    radial-gradient(at 80% 50%, #4facfe 0, transparent 50%);
  background-color: #ffffff;
}
```

---

## Animations and Transitions

### 1. Smooth Transitions

```css
/* Default transition for interactive elements */
.button, .link, .card {
  transition: all var(--transition-base);
}

/* Specific properties for better performance */
.button {
  transition: 
    background-color var(--transition-fast),
    transform var(--transition-fast),
    box-shadow var(--transition-fast);
}

.button:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-lg);
}
```

### 2. Keyframe Animations

```css
/* Fade in */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.fade-in {
  animation: fadeIn var(--transition-base) ease-out;
}

/* Loading spinner */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.spinner {
  animation: spin 1s linear infinite;
}

/* Pulse animation */
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.pulse {
  animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}
```

### 3. Reduced Motion

```css
/* Respect user preferences */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

### 4. View Transitions API (Modern Browsers)

```css
/* Smooth page transitions */
@view-transition {
  navigation: auto;
}

/* Customize transitions */
::view-transition-old(root),
::view-transition-new(root) {
  animation-duration: 0.3s;
}
```

---

## Best Practices

### 1. CSS Reset/Normalize

```css
/* Modern CSS reset */
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html {
  -webkit-text-size-adjust: 100%;
  line-height: 1.5;
}

body {
  min-height: 100vh;
  text-rendering: optimizeLegibility;
}

img,
picture,
video,
canvas,
svg {
  display: block;
  max-width: 100%;
}

input,
button,
textarea,
select {
  font: inherit;
}

p,
h1,
h2,
h3,
h4,
h5,
h6 {
  overflow-wrap: break-word;
}
```

### 2. Utility Classes

```css
/* Spacing utilities */
.m-0 { margin: 0; }
.m-auto { margin: auto; }
.mt-1 { margin-top: var(--space-xs); }
.mb-2 { margin-bottom: var(--space-sm); }

/* Display utilities */
.hidden { display: none; }
.block { display: block; }
.flex { display: flex; }
.grid { display: grid; }

/* Text utilities */
.text-center { text-align: center; }
.text-left { text-align: left; }
.font-bold { font-weight: 700; }

/* Screen reader only */
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

### 3. Focus Styles

```css
/* Remove default outline, add custom focus */
*:focus {
  outline: none;
}

*:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

/* Better focus for interactive elements */
button:focus-visible,
a:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}
```

### 4. Print Styles

```css
@media print {
  /* Optimize for printing */
  *,
  *::before,
  *::after {
    background: transparent !important;
    color: #000 !important;
    box-shadow: none !important;
    text-shadow: none !important;
  }
  
  a,
  a:visited {
    text-decoration: underline;
  }
  
  /* Show URLs for links */
  a[href]::after {
    content: " (" attr(href) ")";
  }
  
  /* Hide non-essential elements */
  nav,
  .no-print {
    display: none !important;
  }
  
  /* Page breaks */
  h2,
  h3 {
    page-break-after: avoid;
  }
}
```

---

## Common Patterns

### 1. Card Component

```css
.card {
  background: var(--color-bg-primary);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-lg);
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
}

.card:hover {
  box-shadow: var(--shadow-md);
  transform: translateY(-2px);
}

.card-header {
  font-size: var(--font-size-lg);
  font-weight: 600;
  margin-bottom: var(--space-md);
  color: var(--color-text-primary);
}

.card-body {
  color: var(--color-text-secondary);
  line-height: var(--line-height-base);
}
```

### 2. Button Styles

```css
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-lg);
  border: none;
  border-radius: var(--radius-md);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--transition-fast);
  text-decoration: none;
}

.btn-primary {
  background: var(--color-primary-600);
  color: white;
}

.btn-primary:hover {
  background: var(--color-primary-700);
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}

.btn-primary:active {
  transform: translateY(0);
}

.btn-outline {
  background: transparent;
  border: 2px solid var(--color-primary-600);
  color: var(--color-primary-600);
}

.btn-outline:hover {
  background: var(--color-primary-600);
  color: white;
}

/* Loading state */
.btn[disabled] {
  opacity: 0.6;
  cursor: not-allowed;
  pointer-events: none;
}
```

### 3. Navigation Bar

```css
.navbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-md) var(--space-lg);
  background: var(--color-bg-primary);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  z-index: 100;
  backdrop-filter: blur(10px);
  background: rgb(255 255 255 / 0.8);
}

.nav-links {
  display: flex;
  gap: var(--space-lg);
  list-style: none;
}

.nav-link {
  color: var(--color-text-secondary);
  text-decoration: none;
  font-weight: 500;
  transition: color var(--transition-fast);
  position: relative;
}

.nav-link:hover,
.nav-link.active {
  color: var(--color-primary-600);
}

/* Animated underline */
.nav-link::after {
  content: '';
  position: absolute;
  bottom: -4px;
  left: 0;
  width: 0;
  height: 2px;
  background: var(--color-primary-600);
  transition: width var(--transition-base);
}

.nav-link:hover::after,
.nav-link.active::after {
  width: 100%;
}
```

### 4. Modal/Dialog

```css
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgb(0 0 0 / 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: var(--space-lg);
}

.modal {
  background: var(--color-bg-primary);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  max-width: 500px;
  width: 100%;
  max-height: 90vh;
  overflow: auto;
  animation: modalSlideIn var(--transition-base);
}

@keyframes modalSlideIn {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.modal-header {
  padding: var(--space-lg);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.modal-body {
  padding: var(--space-lg);
}

.modal-footer {
  padding: var(--space-lg);
  border-top: 1px solid var(--color-border);
  display: flex;
  gap: var(--space-md);
  justify-content: flex-end;
}
```

### 5. Form Styles

```css
.form-group {
  margin-bottom: var(--space-lg);
}

.form-label {
  display: block;
  margin-bottom: var(--space-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.form-input {
  width: 100%;
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  font-size: var(--font-size-base);
  transition: all var(--transition-fast);
  background: var(--color-bg-primary);
  color: var(--color-text-primary);
}

.form-input:focus {
  outline: none;
  border-color: var(--color-primary-600);
  box-shadow: 0 0 0 3px rgb(59 130 246 / 0.1);
}

.form-input::placeholder {
  color: var(--color-text-muted);
}

.form-error {
  color: var(--color-error);
  font-size: var(--font-size-sm);
  margin-top: var(--space-xs);
}

.form-input.error {
  border-color: var(--color-error);
}
```

### 6. Loading Skeleton

```css
.skeleton {
  background: linear-gradient(
    90deg,
    var(--color-bg-secondary) 0%,
    var(--color-border) 50%,
    var(--color-bg-secondary) 100%
  );
  background-size: 200% 100%;
  animation: skeleton-loading 1.5s ease-in-out infinite;
  border-radius: var(--radius-md);
}

@keyframes skeleton-loading {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

.skeleton-text {
  height: 1rem;
  margin-bottom: var(--space-sm);
}

.skeleton-circle {
  width: 48px;
  height: 48px;
  border-radius: 50%;
}
```

### 7. Tooltip

```css
.tooltip-container {
  position: relative;
  display: inline-block;
}

.tooltip {
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%) translateY(-8px);
  padding: var(--space-sm) var(--space-md);
  background: var(--color-text-primary);
  color: var(--color-bg-primary);
  border-radius: var(--radius-md);
  font-size: var(--font-size-sm);
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity var(--transition-fast);
  z-index: 1000;
}

.tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 4px solid transparent;
  border-top-color: var(--color-text-primary);
}

.tooltip-container:hover .tooltip {
  opacity: 1;
}
```

---

## Quick Reference Checklist

✅ **Performance**
- Use `transform` and `opacity` for animations
- Implement `content-visibility` for long pages
- Minimize selector complexity
- Use `will-change` sparingly

✅ **Accessibility**
- Provide focus styles with `:focus-visible`
- Maintain color contrast ratios (4.5:1 minimum)
- Respect `prefers-reduced-motion`
- Use semantic HTML with appropriate CSS

✅ **Modern Features**
- CSS Grid for complex layouts
- Flexbox for simple layouts
- CSS Custom Properties for theming
- `clamp()` for fluid sizing
- Logical properties for internationalization

✅ **Responsive Design**
- Mobile-first approach
- Fluid typography and spacing
- Container queries where supported
- Responsive images with `aspect-ratio`

✅ **Code Quality**
- Consistent naming conventions (BEM, SMACSS, or utility-first)
- Organize with variables and modular structure
- Comment complex calculations and hacks
- Use CSS reset/normalize

---

## Additional Resources

- [MDN CSS Documentation](https://developer.mozilla.org/en-US/docs/Web/CSS)
- [Can I Use](https://caniuse.com/) - Browser compatibility
- [CSS Tricks](https://css-tricks.com/) - Guides and tutorials
- [Modern CSS Solutions](https://moderncss.dev/)
- [Web.dev CSS](https://web.dev/learn/css/)

---

**Remember**: Modern CSS is powerful and constantly evolving. Always test across browsers, prioritize performance and accessibility, and keep learning new features as they become available.
