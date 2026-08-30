(async function () {
  const fmtInr = (n) => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });

  function timeAgo(iso) {
    const diffMs = Date.now() - new Date(iso).getTime();
    const mins = Math.round(diffMs / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins} min ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 24) return `${hrs} hr${hrs === 1 ? '' : 's'} ago`;
    const days = Math.round(hrs / 24);
    return `${days} day${days === 1 ? '' : 's'} ago`;
  }

  const res = await fetch('/api/runs');
  if (res.status === 401) { window.location.href = '/login'; return; }
  const data = await res.json();
  const tbody = document.getElementById('history-body');

  if (!data.runs.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="muted-row">No runs yet — head to the Reconciliation Workspace to run one.</td></tr>`;
    return;
  }

  tbody.innerHTML = data.runs.map((r) => `
    <tr>
      <td>#${r.id}</td>
      <td><span class="source-tag">${r.source}</span></td>
      <td>${r.row_count}</td>
      <td>${(r.match_rate * 100).toFixed(1)}%</td>
      <td>${fmtInr(r.total_value_at_risk_inr)}</td>
      <td>${timeAgo(r.created_at)}</td>
      <td><a href="/reconciliation?run_id=${r.id}" class="btn btn-ghost btn-sm">View →</a></td>
    </tr>
  `).join('');
})();
