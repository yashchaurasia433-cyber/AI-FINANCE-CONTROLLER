(async function () {
  const meRes = await fetch('/api/auth/me');
  const me = await meRes.json();
  if (me.authenticated) {
    document.getElementById('account-username').textContent = me.username;
    document.getElementById('account-email').textContent = me.email;
  }

  const llmRes = await fetch('/api/llm-status');
  const llm = await llmRes.json();
  document.getElementById('llm-status-text').textContent = llm.available
    ? '✓ An Anthropic API key is configured on the server. Settlement Q&A can answer open-ended questions.'
    : 'No Anthropic API key is configured. Settlement Q&A is running in rule-based mode only (still fully functional for common questions).';

  document.getElementById('change-password-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const alertEl = document.getElementById('pw-alert');
    alertEl.innerHTML = '';

    const currentPassword = document.getElementById('current_password').value;
    const newPassword = document.getElementById('new_password').value;
    const confirmPassword = document.getElementById('confirm_new_password').value;

    if (newPassword !== confirmPassword) {
      alertEl.innerHTML = `<div class="alert alert-error">New passwords do not match.</div>`;
      return;
    }

    const res = await fetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    });
    const data = await res.json();
    if (res.ok) {
      alertEl.innerHTML = `<div class="alert alert-success">Password updated.</div>`;
      document.getElementById('change-password-form').reset();
    } else {
      alertEl.innerHTML = `<div class="alert alert-error">${(data.errors || ['Could not update password.']).join(' ')}</div>`;
    }
  });
})();
