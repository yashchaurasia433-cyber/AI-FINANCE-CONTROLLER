(async function () {
  try {
    const res = await fetch('/api/auth/me');
    const data = await res.json();
    if (data.authenticated) {
      document.querySelectorAll('#user-pill').forEach((el) => { el.textContent = data.username; });
      document.querySelectorAll('#footer-user').forEach((el) => { el.textContent = data.username; });
    } else {
      window.location.href = '/login';
    }
  } catch (e) {
    // If /api/auth/me itself fails, don't block the page — just leave the
    // pill showing its placeholder text rather than crashing navigation.
  }

  document.querySelectorAll('#logout-link').forEach((link) => {
    link.addEventListener('click', async (e) => {
      e.preventDefault();
      await fetch('/api/auth/logout', { method: 'POST' });
      window.location.href = '/login';
    });
  });
})();
