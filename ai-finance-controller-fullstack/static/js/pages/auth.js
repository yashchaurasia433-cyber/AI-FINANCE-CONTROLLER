function showAlert(text, type) {
  const el = document.getElementById('form-alert');
  el.innerHTML = `<div class="alert alert-${type}">${text}</div>`;
}

function clearAlert() {
  document.getElementById('form-alert').innerHTML = '';
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

function wireRegisterForm() {
  document.getElementById('register-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAlert();
    const username = document.getElementById('username').value.trim();
    const email = document.getElementById('email').value.trim();
    const password = document.getElementById('password').value;

    const { ok, data } = await postJson('/api/auth/register', { username, email, password });
    if (ok) {
      window.location.href = '/dashboard';
    } else {
      showAlert((data.errors || ['Registration failed.']).join(' '), 'error');
    }
  });
}

function wireLoginForm(nextPath) {
  document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAlert();
    const identifier = document.getElementById('identifier').value.trim();
    const password = document.getElementById('password').value;

    const { ok, data } = await postJson('/api/auth/login', { username: identifier, password });
    if (ok) {
      window.location.href = (nextPath && nextPath.startsWith('/')) ? nextPath : '/dashboard';
    } else {
      showAlert((data.errors || ['Sign in failed.']).join(' '), 'error');
    }
  });
}

function wireForgotPasswordForm() {
  document.getElementById('forgot-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAlert();
    const email = document.getElementById('email').value.trim();

    const { ok, data } = await postJson('/api/auth/forgot-password', { email });
    if (ok) {
      showAlert(data.message, 'success');
      if (data.demo_reset_link) {
        const box = document.getElementById('reset-link-box');
        box.style.display = 'block';
        box.innerHTML = `
          <span class="box-label">Demo reset link</span>
          <a href="${data.demo_reset_link}">${window.location.origin}${data.demo_reset_link}</a>
          <div class="box-note">No email server is configured for this demo, so the link is shown here directly instead of being emailed. In production this would go to your inbox, not this page.</div>
        `;
      }
    } else {
      showAlert((data.errors || ['Something went wrong.']).join(' '), 'error');
    }
  });
}

function wireResetPasswordForm(token, uid) {
  document.getElementById('reset-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAlert();
    const newPassword = document.getElementById('new_password').value;
    const confirmPassword = document.getElementById('confirm_password').value;

    if (newPassword !== confirmPassword) {
      showAlert('Passwords do not match.', 'error');
      return;
    }

    const { ok, data } = await postJson('/api/auth/reset-password', { token, uid, password: newPassword });
    if (ok) {
      showAlert('Password reset. Redirecting to sign in…', 'success');
      setTimeout(() => { window.location.href = '/login'; }, 1500);
    } else {
      showAlert((data.errors || ['Could not reset password.']).join(' '), 'error');
    }
  });
}
