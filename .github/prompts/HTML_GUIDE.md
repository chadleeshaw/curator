# HTML Guide: Modern, Performant, and Accessible Web Pages

A comprehensive guide to writing excellent HTML for contemporary web applications.

## Table of Contents
- [Document Structure](#document-structure)
- [Semantic HTML](#semantic-html)
- [Accessibility](#accessibility)
- [Performance](#performance)
- [SEO Best Practices](#seo-best-practices)
- [Forms and Validation](#forms-and-validation)
- [Media Elements](#media-elements)
- [Meta Tags](#meta-tags)
- [Modern HTML Features](#modern-html-features)
- [Common Patterns](#common-patterns)

---

## Document Structure

### 1. Modern HTML5 Boilerplate

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="A concise description of your page (150-160 characters)">
  <meta name="theme-color" content="#3b82f6">
  
  <title>Page Title - Site Name</title>
  
  <!-- Preconnect to external domains -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://cdn.example.com">
  
  <!-- Critical CSS inline or preload -->
  <link rel="preload" href="/styles/critical.css" as="style">
  <link rel="stylesheet" href="/styles/critical.css">
  
  <!-- Defer non-critical CSS -->
  <link rel="preload" href="/styles/main.css" as="style" 
        onload="this.onload=null;this.rel='stylesheet'">
  <noscript><link rel="stylesheet" href="/styles/main.css"></noscript>
  
  <!-- Favicon -->
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="icon" type="image/png" href="/favicon.png">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">
  
  <!-- Open Graph for social sharing -->
  <meta property="og:title" content="Page Title">
  <meta property="og:description" content="Page description">
  <meta property="og:image" content="https://example.com/image.jpg">
  <meta property="og:url" content="https://example.com/page">
  <meta property="og:type" content="website">
  
  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Page Title">
  <meta name="twitter:description" content="Page description">
  <meta name="twitter:image" content="https://example.com/image.jpg">
</head>
<body>
  <!-- Content here -->
  
  <!-- Scripts at end of body for better performance -->
  <script src="/js/main.js" defer></script>
</body>
</html>
```

### 2. Semantic Document Outline

```html
<!DOCTYPE html>
<html lang="en">
<body>
  <!-- Skip to main content link for accessibility -->
  <a href="#main-content" class="skip-link">Skip to main content</a>
  
  <header role="banner">
    <nav role="navigation" aria-label="Main navigation">
      <!-- Primary navigation -->
    </nav>
  </header>
  
  <main id="main-content" role="main">
    <article>
      <header>
        <h1>Article Title</h1>
        <p>By <span itemprop="author">Author Name</span></p>
        <time datetime="2026-01-13">January 13, 2026</time>
      </header>
      
      <section>
        <!-- Article content -->
      </section>
      
      <footer>
        <!-- Article metadata, tags, etc. -->
      </footer>
    </article>
    
    <aside role="complementary" aria-label="Related content">
      <!-- Sidebar content -->
    </aside>
  </main>
  
  <footer role="contentinfo">
    <!-- Site footer -->
  </footer>
</body>
</html>
```

---

## Semantic HTML

### 1. Use Semantic Elements

```html
<!-- ❌ BAD - Non-semantic markup -->
<div class="header">
  <div class="nav">
    <div class="nav-item">Home</div>
  </div>
</div>
<div class="content">
  <div class="post">
    <div class="title">Title</div>
    <div class="text">Content...</div>
  </div>
</div>

<!-- ✅ GOOD - Semantic markup -->
<header>
  <nav>
    <a href="/">Home</a>
  </nav>
</header>
<main>
  <article>
    <h1>Title</h1>
    <p>Content...</p>
  </article>
</main>
```

### 2. Semantic Elements Reference

```html
<!-- Page structure -->
<header>Site or section header</header>
<nav>Navigation links</nav>
<main>Primary content (one per page)</main>
<article>Self-contained content</article>
<section>Thematic grouping of content</section>
<aside>Tangentially related content</aside>
<footer>Footer for page or section</footer>

<!-- Content grouping -->
<figure>
  <img src="diagram.png" alt="System architecture diagram">
  <figcaption>Figure 1: System Architecture</figcaption>
</figure>

<details>
  <summary>Click to expand</summary>
  <p>Hidden content revealed on click</p>
</details>

<blockquote cite="https://source.com">
  <p>A quotation from another source</p>
  <footer>— <cite>Source Name</cite></footer>
</blockquote>

<!-- Text-level semantics -->
<mark>Highlighted text</mark>
<strong>Strong importance</strong>
<em>Emphasis</em>
<code>Inline code</code>
<kbd>Keyboard input</kbd>
<samp>Sample output</samp>
<var>Variable</var>
<abbr title="HyperText Markup Language">HTML</abbr>
<time datetime="2026-01-13">January 13, 2026</time>
```

### 3. Heading Hierarchy

```html
<!-- ✅ GOOD - Proper heading hierarchy -->
<h1>Page Title (Only one H1 per page)</h1>
  <h2>Section 1</h2>
    <h3>Subsection 1.1</h3>
    <h3>Subsection 1.2</h3>
  <h2>Section 2</h2>
    <h3>Subsection 2.1</h3>

<!-- ❌ BAD - Skipping levels -->
<h1>Page Title</h1>
  <h3>Section (skipped h2)</h3>
  <h5>Subsection (skipped h4)</h5>
```

---

## Accessibility

### 1. ARIA Attributes

```html
<!-- Landmark roles (redundant with HTML5 semantic elements, but helpful) -->
<header role="banner">
<nav role="navigation" aria-label="Primary">
<main role="main">
<aside role="complementary">
<footer role="contentinfo">

<!-- Interactive elements -->
<button aria-label="Close dialog" aria-pressed="false">
  <svg aria-hidden="true"><!-- Icon --></svg>
</button>

<button aria-expanded="false" aria-controls="dropdown-menu">
  Menu
</button>
<div id="dropdown-menu" hidden>
  <!-- Menu items -->
</div>

<!-- Live regions for dynamic content -->
<div role="alert" aria-live="assertive">
  Error: Please fill in all required fields
</div>

<div aria-live="polite" aria-atomic="true">
  Loading... 45% complete
</div>

<!-- Tab interface -->
<div role="tablist" aria-label="Content sections">
  <button role="tab" aria-selected="true" aria-controls="panel-1" id="tab-1">
    Tab 1
  </button>
  <button role="tab" aria-selected="false" aria-controls="panel-2" id="tab-2">
    Tab 2
  </button>
</div>
<div role="tabpanel" id="panel-1" aria-labelledby="tab-1">
  Panel 1 content
</div>
<div role="tabpanel" id="panel-2" aria-labelledby="tab-2" hidden>
  Panel 2 content
</div>
```

### 2. Form Accessibility

```html
<!-- Always associate labels with inputs -->
<label for="email">Email address</label>
<input type="email" id="email" name="email" 
       required 
       aria-describedby="email-hint"
       aria-invalid="false">
<span id="email-hint" class="hint">We'll never share your email</span>
<span id="email-error" class="error" role="alert" hidden>
  Please enter a valid email address
</span>

<!-- Fieldset for radio groups -->
<fieldset>
  <legend>Choose your subscription</legend>
  <label>
    <input type="radio" name="plan" value="free" checked>
    Free
  </label>
  <label>
    <input type="radio" name="plan" value="premium">
    Premium
  </label>
</fieldset>

<!-- Required fields -->
<label for="name">
  Name <abbr title="required" aria-label="required">*</abbr>
</label>
<input type="text" id="name" name="name" required aria-required="true">
```

### 3. Image Accessibility

```html
<!-- Decorative images -->
<img src="decoration.png" alt="" role="presentation">

<!-- Informative images -->
<img src="chart.png" alt="Sales increased 45% in Q4 2025">

<!-- Complex images -->
<figure>
  <img src="complex-diagram.png" alt="Network topology diagram" 
       aria-describedby="diagram-description">
  <figcaption id="diagram-description">
    Detailed description: The diagram shows three servers connected 
    to a load balancer, which connects to...
  </figcaption>
</figure>

<!-- Icons with text -->
<button>
  <svg aria-hidden="true" focusable="false"><!-- Icon --></svg>
  <span>Delete</span>
</button>

<!-- Icons without text -->
<button aria-label="Delete item">
  <svg aria-hidden="true" focusable="false"><!-- Icon --></svg>
</button>
```

### 4. Keyboard Navigation

```html
<!-- Ensure proper tab order -->
<nav>
  <a href="/" tabindex="0">Home</a>
  <a href="/about" tabindex="0">About</a>
  <a href="/contact" tabindex="0">Contact</a>
</nav>

<!-- Skip links for keyboard users -->
<a href="#main-content" class="skip-link">Skip to main content</a>

<!-- Custom interactive elements need tabindex -->
<div role="button" tabindex="0" 
     onkeydown="if(event.key==='Enter'||event.key===' ')handleClick(event)">
  Custom Button
</div>

<!-- Dialog/modal focus management -->
<dialog id="modal" aria-labelledby="modal-title" aria-modal="true">
  <h2 id="modal-title">Modal Title</h2>
  <button autofocus>Primary Action</button>
  <button>Cancel</button>
</dialog>
```

---

## Performance

### 1. Resource Loading Optimization

```html
<head>
  <!-- DNS prefetch for external domains -->
  <link rel="dns-prefetch" href="https://fonts.googleapis.com">
  
  <!-- Preconnect to establish early connections -->
  <link rel="preconnect" href="https://api.example.com">
  <link rel="preconnect" href="https://cdn.example.com" crossorigin>
  
  <!-- Preload critical resources -->
  <link rel="preload" href="/fonts/main.woff2" as="font" 
        type="font/woff2" crossorigin>
  <link rel="preload" href="/hero-image.jpg" as="image">
  <link rel="preload" href="/critical.css" as="style">
  <link rel="preload" href="/main.js" as="script">
  
  <!-- Prefetch resources for next page -->
  <link rel="prefetch" href="/next-page.html">
  <link rel="prefetch" href="/next-page-image.jpg">
  
  <!-- Prerender next likely page -->
  <link rel="prerender" href="/next-page.html">
</head>
```

### 2. Script Loading Strategies

```html
<!-- Defer: Download in parallel, execute after HTML parsing -->
<script src="/app.js" defer></script>

<!-- Async: Download in parallel, execute immediately when ready -->
<script src="/analytics.js" async></script>

<!-- Module scripts (deferred by default) -->
<script type="module" src="/app.mjs"></script>

<!-- Inline critical JavaScript -->
<script>
  // Critical functionality that must run immediately
  document.documentElement.classList.remove('no-js');
</script>

<!-- Dynamic import for code splitting -->
<script type="module">
  // Load heavy feature only when needed
  button.addEventListener('click', async () => {
    const { feature } = await import('./feature.js');
    feature();
  });
</script>
```

### 3. Image Optimization

```html
<!-- Responsive images with srcset -->
<img src="image-800w.jpg"
     srcset="image-400w.jpg 400w,
             image-800w.jpg 800w,
             image-1200w.jpg 1200w"
     sizes="(max-width: 600px) 400px,
            (max-width: 1000px) 800px,
            1200px"
     alt="Responsive image"
     loading="lazy"
     decoding="async">

<!-- Art direction with picture element -->
<picture>
  <source media="(min-width: 1024px)" srcset="hero-desktop.jpg">
  <source media="(min-width: 768px)" srcset="hero-tablet.jpg">
  <img src="hero-mobile.jpg" alt="Hero image">
</picture>

<!-- Modern image formats with fallback -->
<picture>
  <source srcset="image.avif" type="image/avif">
  <source srcset="image.webp" type="image/webp">
  <img src="image.jpg" alt="Image with modern format fallback">
</picture>

<!-- Native lazy loading -->
<img src="below-fold.jpg" alt="Below fold image" loading="lazy">

<!-- Eager loading for above-fold images -->
<img src="hero.jpg" alt="Hero image" loading="eager" fetchpriority="high">

<!-- Aspect ratio to prevent layout shift -->
<img src="image.jpg" alt="Image" width="800" height="600" loading="lazy">
```

### 4. Video Optimization

```html
<!-- Video with multiple sources and lazy loading -->
<video width="1920" height="1080" 
       controls 
       preload="metadata"
       poster="thumbnail.jpg">
  <source src="video.webm" type="video/webm">
  <source src="video.mp4" type="video/mp4">
  <track kind="captions" src="captions-en.vtt" srclang="en" label="English">
  <track kind="subtitles" src="subtitles-es.vtt" srclang="es" label="Español">
  Your browser doesn't support video.
</video>

<!-- Background video (autoplay, muted, no controls) -->
<video autoplay muted loop playsinline 
       poster="poster.jpg"
       aria-label="Background video">
  <source src="background.webm" type="video/webm">
  <source src="background.mp4" type="video/mp4">
</video>

<!-- Lazy load video -->
<video controls preload="none" poster="poster.jpg">
  <source data-src="video.mp4" type="video/mp4">
</video>
```

---

## Forms and Validation

### 1. Modern Form Elements

```html
<form action="/submit" method="POST" novalidate>
  <!-- Text inputs -->
  <label for="name">Name</label>
  <input type="text" id="name" name="name" 
         required 
         minlength="2" 
         maxlength="50"
         autocomplete="name"
         placeholder="John Doe">
  
  <!-- Email with validation -->
  <label for="email">Email</label>
  <input type="email" id="email" name="email" 
         required 
         autocomplete="email"
         pattern="[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$">
  
  <!-- Phone number -->
  <label for="phone">Phone</label>
  <input type="tel" id="phone" name="phone" 
         autocomplete="tel"
         pattern="[0-9]{3}-[0-9]{3}-[0-9]{4}"
         placeholder="555-555-5555">
  
  <!-- URL -->
  <label for="website">Website</label>
  <input type="url" id="website" name="website"
         placeholder="https://example.com">
  
  <!-- Number with constraints -->
  <label for="quantity">Quantity</label>
  <input type="number" id="quantity" name="quantity"
         min="1" max="100" step="1" value="1">
  
  <!-- Date inputs -->
  <label for="birthdate">Birth Date</label>
  <input type="date" id="birthdate" name="birthdate"
         min="1900-01-01" max="2026-01-13">
  
  <!-- Time input -->
  <label for="appointment">Appointment Time</label>
  <input type="time" id="appointment" name="appointment">
  
  <!-- Color picker -->
  <label for="color">Favorite Color</label>
  <input type="color" id="color" name="color" value="#3b82f6">
  
  <!-- Range slider -->
  <label for="volume">Volume</label>
  <input type="range" id="volume" name="volume"
         min="0" max="100" value="50">
  <output for="volume">50</output>
  
  <!-- Select dropdown -->
  <label for="country">Country</label>
  <select id="country" name="country" required>
    <option value="">Choose a country</option>
    <option value="us">United States</option>
    <option value="uk">United Kingdom</option>
    <option value="ca">Canada</option>
  </select>
  
  <!-- Datalist for autocomplete -->
  <label for="browser">Browser</label>
  <input list="browsers" id="browser" name="browser">
  <datalist id="browsers">
    <option value="Chrome">
    <option value="Firefox">
    <option value="Safari">
    <option value="Edge">
  </datalist>
  
  <!-- Textarea -->
  <label for="message">Message</label>
  <textarea id="message" name="message" 
            rows="4" 
            maxlength="500"
            placeholder="Enter your message..."></textarea>
  
  <!-- Checkbox -->
  <label>
    <input type="checkbox" name="subscribe" value="yes">
    Subscribe to newsletter
  </label>
  
  <!-- Checkbox with required -->
  <label>
    <input type="checkbox" name="terms" required>
    I agree to the <a href="/terms">terms and conditions</a>
  </label>
  
  <!-- Radio buttons -->
  <fieldset>
    <legend>Shipping Method</legend>
    <label>
      <input type="radio" name="shipping" value="standard" checked>
      Standard (5-7 days)
    </label>
    <label>
      <input type="radio" name="shipping" value="express">
      Express (2-3 days)
    </label>
  </fieldset>
  
  <!-- File upload -->
  <label for="avatar">Profile Picture</label>
  <input type="file" id="avatar" name="avatar"
         accept="image/png, image/jpeg"
         capture="user">
  
  <!-- Multiple file upload -->
  <label for="documents">Upload Documents</label>
  <input type="file" id="documents" name="documents"
         multiple
         accept=".pdf,.doc,.docx">
  
  <!-- Submit and reset buttons -->
  <button type="submit">Submit</button>
  <button type="reset">Reset</button>
</form>
```

### 2. Form Validation

```html
<!-- HTML5 validation attributes -->
<form>
  <!-- Required field -->
  <input type="text" required>
  
  <!-- Pattern matching -->
  <input type="text" pattern="[A-Za-z]{3,}" 
         title="At least 3 letters">
  
  <!-- Length constraints -->
  <input type="text" minlength="8" maxlength="20">
  
  <!-- Number constraints -->
  <input type="number" min="0" max="100" step="5">
  
  <!-- Custom validation message -->
  <input type="email" id="email" required
         oninvalid="this.setCustomValidity('Please enter a valid email')"
         oninput="this.setCustomValidity('')">
</form>

<!-- Validation with aria attributes -->
<label for="username">Username</label>
<input type="text" 
       id="username" 
       name="username"
       required
       aria-required="true"
       aria-invalid="false"
       aria-describedby="username-error">
<span id="username-error" role="alert" hidden>
  Username must be at least 3 characters
</span>
```

### 3. Accessible Form Groups

```html
<!-- Form with proper structure -->
<form aria-labelledby="form-title">
  <h2 id="form-title">Contact Form</h2>
  
  <fieldset>
    <legend>Personal Information</legend>
    
    <div class="form-group">
      <label for="first-name">
        First Name <abbr title="required">*</abbr>
      </label>
      <input type="text" id="first-name" name="firstName" required>
    </div>
    
    <div class="form-group">
      <label for="last-name">
        Last Name <abbr title="required">*</abbr>
      </label>
      <input type="text" id="last-name" name="lastName" required>
    </div>
  </fieldset>
  
  <fieldset>
    <legend>Contact Details</legend>
    
    <div class="form-group">
      <label for="email-contact">Email</label>
      <input type="email" id="email-contact" name="email" required>
    </div>
  </fieldset>
  
  <button type="submit">Send Message</button>
</form>
```

---

## Media Elements

### 1. Audio Elements

```html
<!-- Basic audio player -->
<audio controls preload="metadata">
  <source src="audio.mp3" type="audio/mpeg">
  <source src="audio.ogg" type="audio/ogg">
  Your browser doesn't support audio playback.
</audio>

<!-- Audio with track -->
<audio controls>
  <source src="podcast.mp3" type="audio/mpeg">
  <track kind="captions" src="captions.vtt" srclang="en" label="English">
</audio>
```

### 2. Iframe Best Practices

```html
<!-- Responsive iframe wrapper -->
<div style="position: relative; padding-bottom: 56.25%; height: 0;">
  <iframe 
    src="https://www.youtube.com/embed/VIDEO_ID"
    title="Video title"
    style="position: absolute; top: 0; left: 0; width: 100%; height: 100%;"
    frameborder="0"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
    allowfullscreen
    loading="lazy">
  </iframe>
</div>

<!-- Sandbox iframe for security -->
<iframe src="untrusted-content.html"
        sandbox="allow-scripts allow-same-origin"
        title="Sandboxed content">
</iframe>
```

### 3. SVG Integration

```html
<!-- Inline SVG (can be styled with CSS) -->
<svg width="100" height="100" viewBox="0 0 100 100" 
     role="img" aria-label="Circle icon">
  <circle cx="50" cy="50" r="40" fill="#3b82f6"/>
</svg>

<!-- SVG as image -->
<img src="icon.svg" alt="Icon description" width="24" height="24">

<!-- SVG sprite technique -->
<svg style="display: none;">
  <defs>
    <symbol id="icon-heart" viewBox="0 0 24 24">
      <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
    </symbol>
  </defs>
</svg>

<!-- Use the sprite -->
<svg width="24" height="24" aria-label="Like">
  <use href="#icon-heart"/>
</svg>
```

---

## Meta Tags

### 1. Essential Meta Tags

```html
<head>
  <!-- Character encoding -->
  <meta charset="UTF-8">
  
  <!-- Viewport for responsive design -->
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  
  <!-- IE compatibility -->
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  
  <!-- Page description -->
  <meta name="description" content="Page description (150-160 characters)">
  
  <!-- Keywords (less important now) -->
  <meta name="keywords" content="keyword1, keyword2, keyword3">
  
  <!-- Author -->
  <meta name="author" content="Author Name">
  
  <!-- Theme color for mobile browsers -->
  <meta name="theme-color" content="#3b82f6">
  <meta name="theme-color" content="#1e3a8a" media="(prefers-color-scheme: dark)">
  
  <!-- Disable automatic detection of possible phone numbers -->
  <meta name="format-detection" content="telephone=no">
  
  <!-- Security headers -->
  <meta http-equiv="Content-Security-Policy" 
        content="default-src 'self'; script-src 'self' 'unsafe-inline';">
  
  <!-- Referrer policy -->
  <meta name="referrer" content="no-referrer-when-downgrade">
</head>
```

### 2. Progressive Web App (PWA) Meta Tags

```html
<head>
  <!-- Web app manifest -->
  <link rel="manifest" href="/manifest.json">
  
  <!-- Apple-specific -->
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <meta name="apple-mobile-web-app-title" content="App Name">
  <link rel="apple-touch-icon" href="/icons/icon-192.png">
  
  <!-- Microsoft-specific -->
  <meta name="msapplication-TileColor" content="#3b82f6">
  <meta name="msapplication-TileImage" content="/icons/icon-144.png">
  <meta name="msapplication-config" content="/browserconfig.xml">
  
  <!-- Theme colors -->
  <meta name="theme-color" content="#3b82f6">
</head>
```

---

## Modern HTML Features

### 1. Dialog Element

```html
<!-- Native modal dialog -->
<dialog id="dialog" aria-labelledby="dialog-title">
  <form method="dialog">
    <h2 id="dialog-title">Dialog Title</h2>
    <p>Dialog content goes here.</p>
    <button value="cancel">Cancel</button>
    <button value="confirm" autofocus>Confirm</button>
  </form>
</dialog>

<button onclick="document.getElementById('dialog').showModal()">
  Open Dialog
</button>

<script>
  const dialog = document.getElementById('dialog');
  dialog.addEventListener('close', () => {
    console.log('Dialog closed with:', dialog.returnValue);
  });
</script>
```

### 2. Details and Summary

```html
<!-- Collapsible content -->
<details>
  <summary>Click to expand</summary>
  <p>This content is hidden by default and revealed when clicked.</p>
</details>

<!-- Multiple details (accordion) -->
<details name="accordion">
  <summary>Section 1</summary>
  <p>Content for section 1</p>
</details>
<details name="accordion">
  <summary>Section 2</summary>
  <p>Content for section 2</p>
</details>
```

### 3. Template Element

```html
<!-- Define a template -->
<template id="card-template">
  <div class="card">
    <h3 class="card-title"></h3>
    <p class="card-description"></p>
    <button class="card-action">Learn More</button>
  </div>
</template>

<script>
  // Clone and use the template
  const template = document.getElementById('card-template');
  const clone = template.content.cloneNode(true);
  clone.querySelector('.card-title').textContent = 'Card Title';
  clone.querySelector('.card-description').textContent = 'Description';
  document.body.appendChild(clone);
</script>
```

### 4. Progress and Meter

```html
<!-- Progress indicator -->
<label for="file-progress">Upload progress:</label>
<progress id="file-progress" max="100" value="70">70%</progress>

<!-- Meter for scalar measurement -->
<label for="fuel">Fuel level:</label>
<meter id="fuel" 
       min="0" max="100" 
       low="25" high="75" optimum="80" 
       value="60">
  60%
</meter>
```

### 5. Data Attributes

```html
<!-- Store custom data -->
<article data-post-id="123" 
         data-author="john-doe" 
         data-category="technology"
         data-published="2026-01-13">
  Article content
</article>

<script>
  const article = document.querySelector('article');
  console.log(article.dataset.postId); // "123"
  console.log(article.dataset.author); // "john-doe"
</script>
```

---

## Common Patterns

### 1. Navigation Component

```html
<nav aria-label="Main navigation">
  <ul role="list">
    <li><a href="/" aria-current="page">Home</a></li>
    <li><a href="/about">About</a></li>
    <li><a href="/services">Services</a></li>
    <li>
      <button aria-expanded="false" aria-controls="products-menu">
        Products
      </button>
      <ul id="products-menu" hidden>
        <li><a href="/products/web">Web</a></li>
        <li><a href="/products/mobile">Mobile</a></li>
      </ul>
    </li>
    <li><a href="/contact">Contact</a></li>
  </ul>
</nav>
```

### 2. Card Component

```html
<article class="card">
  <img src="image.jpg" alt="Card image" loading="lazy" width="400" height="300">
  <div class="card-content">
    <h3>Card Title</h3>
    <p>Card description goes here with a brief summary.</p>
    <div class="card-meta">
      <time datetime="2026-01-13">Jan 13, 2026</time>
      <span>By John Doe</span>
    </div>
    <a href="/article" class="card-link">
      Read more
      <span class="sr-only">about Card Title</span>
    </a>
  </div>
</article>
```

### 3. Hero Section

```html
<section class="hero" role="region" aria-labelledby="hero-title">
  <div class="hero-content">
    <h1 id="hero-title">Welcome to Our Site</h1>
    <p>Discover amazing products and services</p>
    <div class="hero-actions">
      <a href="/get-started" class="btn btn-primary">Get Started</a>
      <a href="/learn-more" class="btn btn-secondary">Learn More</a>
    </div>
  </div>
  <picture class="hero-image">
    <source media="(min-width: 1024px)" srcset="hero-large.jpg">
    <source media="(min-width: 768px)" srcset="hero-medium.jpg">
    <img src="hero-small.jpg" alt="" loading="eager" fetchpriority="high">
  </picture>
</section>
```

### 4. Breadcrumb Navigation

```html
<nav aria-label="Breadcrumb">
  <ol itemscope itemtype="https://schema.org/BreadcrumbList">
    <li itemprop="itemListElement" itemscope 
        itemtype="https://schema.org/ListItem">
      <a itemprop="item" href="/">
        <span itemprop="name">Home</span>
      </a>
      <meta itemprop="position" content="1" />
    </li>
    <li itemprop="itemListElement" itemscope 
        itemtype="https://schema.org/ListItem">
      <a itemprop="item" href="/category">
        <span itemprop="name">Category</span>
      </a>
      <meta itemprop="position" content="2" />
    </li>
    <li itemprop="itemListElement" itemscope 
        itemtype="https://schema.org/ListItem">
      <span itemprop="name" aria-current="page">Current Page</span>
      <meta itemprop="position" content="3" />
    </li>
  </ol>
</nav>
```

### 5. Pagination

```html
<nav aria-label="Pagination">
  <ul class="pagination">
    <li>
      <a href="?page=1" aria-label="Go to first page">
        First
      </a>
    </li>
    <li>
      <a href="?page=3" rel="prev" aria-label="Go to previous page">
        Previous
      </a>
    </li>
    <li>
      <a href="?page=3">3</a>
    </li>
    <li>
      <span aria-current="page" aria-label="Current page, page 4">4</span>
    </li>
    <li>
      <a href="?page=5">5</a>
    </li>
    <li>
      <a href="?page=5" rel="next" aria-label="Go to next page">
        Next
      </a>
    </li>
    <li>
      <a href="?page=10" aria-label="Go to last page">
        Last
      </a>
    </li>
  </ul>
</nav>
```

### 6. Alert/Notification

```html
<!-- Success alert -->
<div role="alert" aria-live="polite" class="alert alert-success">
  <svg aria-hidden="true" focusable="false"><!-- Success icon --></svg>
  <p>Your changes have been saved successfully!</p>
  <button aria-label="Close alert">×</button>
</div>

<!-- Error alert -->
<div role="alert" aria-live="assertive" class="alert alert-error">
  <svg aria-hidden="true" focusable="false"><!-- Error icon --></svg>
  <p>An error occurred. Please try again.</p>
  <button aria-label="Close alert">×</button>
</div>

<!-- Info alert -->
<div role="status" aria-live="polite" class="alert alert-info">
  <svg aria-hidden="true" focusable="false"><!-- Info icon --></svg>
  <p>New features are now available.</p>
  <button aria-label="Dismiss">×</button>
</div>
```

---

## Best Practices Checklist

✅ **Document Structure**
- Use semantic HTML5 elements
- One `<main>` element per page
- One `<h1>` element per page
- Logical heading hierarchy without skipping levels

✅ **Accessibility**
- Provide alt text for all images (or alt="" for decorative)
- Associate all labels with form inputs
- Use ARIA attributes appropriately
- Ensure keyboard navigation works
- Maintain proper color contrast
- Support screen readers

✅ **Performance**
- Lazy load below-fold images
- Use appropriate resource hints (preconnect, prefetch)
- Defer non-critical JavaScript
- Optimize images with srcset and modern formats
- Minimize HTML size

✅ **SEO**
- Include proper meta tags
- Use semantic markup
- Add structured data (Schema.org)
- Implement canonical URLs
- Create descriptive page titles

✅ **Forms**
- Use appropriate input types
- Provide validation feedback
- Make required fields clear
- Support autocomplete
- Group related fields with fieldset

✅ **Multimedia**
- Provide fallback content
- Include captions/subtitles for videos
- Use poster images for videos
- Optimize file sizes

✅ **Security**
- Validate all user input
- Use HTTPS
- Implement CSP headers
- Sanitize user-generated content

---

## Additional Resources

- [MDN HTML Documentation](https://developer.mozilla.org/en-US/docs/Web/HTML)
- [HTML5 Specification](https://html.spec.whatwg.org/)
- [W3C Web Accessibility Initiative (WAI)](https://www.w3.org/WAI/)
- [ARIA Authoring Practices Guide](https://www.w3.org/WAI/ARIA/apg/)
- [Schema.org](https://schema.org/)
- [Can I Use](https://caniuse.com/) - Browser compatibility

---

**Remember**: Good HTML is semantic, accessible, and performant. Always prioritize user experience, test with real users, and stay updated with web standards.
