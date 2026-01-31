// Curator - Login Page JavaScript

function switchMode(mode) {
  const loginMode = document.getElementById('loginMode');
  const setupMode = document.getElementById('setupMode');
  const errorMessage = document.getElementById('errorMessage');
  const successMessage = document.getElementById('successMessage');

  errorMessage.classList.remove('show');
  successMessage.classList.remove('show');

  if (mode === 'setup') {
    loginMode.classList.add('hidden');
    setupMode.classList.remove('hidden');
  } else {
    loginMode.classList.remove('hidden');
    setupMode.classList.add('hidden');
  }
}

// eslint-disable-next-line no-unused-vars -- Called from HTML onclick handlers
function togglePasswordVisibility(inputId) {
  const input = document.getElementById(inputId);
  if (input.type === 'password') {
    input.type = 'text';
  } else {
    input.type = 'password';
  }
}

function showError(message) {
  const errorDiv = document.getElementById('errorMessage');
  errorDiv.textContent = message;
  errorDiv.classList.add('show');
  document.getElementById('successMessage').classList.remove('show');
}

function showSuccess(message) {
  const successDiv = document.getElementById('successMessage');
  successDiv.textContent = message;
  successDiv.classList.add('show');
  document.getElementById('errorMessage').classList.remove('show');
}

// eslint-disable-next-line no-unused-vars -- Called from HTML form onsubmit handler
async function handleLogin(event) {
  event.preventDefault();
  const username = document.getElementById('loginUsername').value;
  const password = document.getElementById('loginPassword').value;
  const btn = document.getElementById('loginBtn');

  btn.disabled = true;
  btn.innerHTML = '<span class="loading"></span>Signing in...';

  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();

    if (response.ok) {
      showSuccess('Login successful! Redirecting...');
      localStorage.setItem('auth_token', data.token);
      setTimeout(() => {
        window.location.href = '/';
      }, 1000);
    } else {
      showError(data.detail || 'Login failed');
    }
  } catch (error) {
    showError('An error occurred: ' + error.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Sign In';
  }
}

// eslint-disable-next-line no-unused-vars -- Called from HTML form onsubmit handler
async function handleSetup(event) {
  event.preventDefault();
  const username = document.getElementById('setupUsername').value;
  const password = document.getElementById('setupPassword').value;
  const passwordConfirm = document.getElementById('setupPasswordConfirm').value;
  const btn = document.getElementById('setupBtn');

  if (password !== passwordConfirm) {
    showError('Passwords do not match');
    return;
  }

  if (password.length < 6) {
    showError('Password must be at least 6 characters');
    return;
  }

  btn.disabled = true;
  btn.innerHTML = '<span class="loading"></span>Creating credentials...';

  try {
    const response = await fetch('/api/auth/setup', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ username, password }),
    });

    const data = await response.json();

    if (response.ok) {
      showSuccess('Credentials created! Switching to login...');
      setTimeout(() => {
        switchMode('login');
        document.getElementById('loginUsername').value = username;
        document.getElementById('loginPassword').value = '';
      }, 1000);
    } else {
      showError(data.detail || 'Setup failed');
    }
  } catch (error) {
    showError('An error occurred: ' + error.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Create Credentials';
  }
}

// Get initial mode from backend on page load
async function initializeLoginPage() {
  try {
    const response = await fetch('/api/auth/login-mode');
    const data = await response.json();

    // Backend decides which mode to show
    const mode = data.mode; // 'login' or 'setup'
    switchMode(mode);
  } catch (error) {
    console.error('Error initializing login page:', error);
    // Default to login mode if there's an error
    switchMode('login');
  }
}

// Initialize on load
window.addEventListener('load', initializeLoginPage);
