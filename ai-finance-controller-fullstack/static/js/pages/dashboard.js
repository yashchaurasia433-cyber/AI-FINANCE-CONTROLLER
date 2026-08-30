(function () {
  const fmtInr = (n) => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });

  function renderMetrics(metrics) {
    const cards = [
      { label: 'Match rate', value: (metrics.match_rate * 100).toFixed(1) + '%', cls: 'gold' },
      { label: 'Exact matches', value: metrics.exact_matches, cls: 'gold' },
      { label: 'Fuzzy matches', value: metrics.fuzzy_matches, cls: 'green' },
      { label: 'Unmatched — bank', value: metrics.unmatched_bank_only, cls: 'red' },
      { label: 'Unmatched — gateway', value: metrics.unmatched_gateway_only, cls: 'red' },
      { label: 'Value at risk', value: fmtInr(metrics.total_value_at_risk_inr), cls: 'violet' },
    ];
    document.getElementById('metrics-grid').innerHTML = cards.map((c) => `
      <div class="metric-card">
        <div class="metric-label">${c.label}</div>
        <div class="metric-value ${c.cls}">${c.value}</div>
      </div>
    `).join('');
  }

  function renderActivity(topExceptions) {
    const labelFor = { fuzzy: 'Fuzzy', unmatched_bank: 'Bank-only', unmatched_gateway: 'Gateway-only' };
    const el = document.getElementById('activity-list');
    if (!topExceptions.length) {
      el.innerHTML = `<div class="activity-row"><span>No open exceptions right now.</span></div>`;
      return;
    }
    el.innerHTML = topExceptions.map((e) => `
      <div class="activity-row">
        <span>${e.ref}</span>
        <span class="tag ${e.type}">${labelFor[e.type] || e.type}</span>
        <span>${fmtInr(e.amount)}</span>
      </div>
    `).join('');
  }

  async function load() {
    try {
      const res = await fetch('/api/dashboard/summary');
      if (res.status === 401) { window.location.href = '/login'; return; }
      const data = await res.json();
      renderMetrics(data.metrics);
      renderActivity(data.top_exceptions);
      document.getElementById('run-timestamp').textContent = data.is_fresh_sample
        ? 'Showing a fresh sample run — you haven\'t reconciled anything yet.'
        : `Showing your most recent reconciliation run (#${data.run_id}).`;
    } catch (e) {
      document.getElementById('run-timestamp').textContent = 'Could not load dashboard data.';
    }
  }

  load();
  initAmbientScene(document.getElementById('mini-scene'), { density: 300 });
})();
