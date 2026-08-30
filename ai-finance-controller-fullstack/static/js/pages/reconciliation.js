(function () {
  const BANK_FIELDS = { required: ['ref', 'amount', 'date'], optional: ['narration'] };
  const GATEWAY_FIELDS = { required: ['ref', 'amount', 'date'], optional: ['order_id', 'currency', 'status', 'merchant'] };
  const FIELD_LABELS = { ref: 'Reference / Txn ID', amount: 'Amount', date: 'Date', narration: 'Narration', order_id: 'Order ID', currency: 'Currency', status: 'Status', merchant: 'Merchant' };

  let currentRunId = null;
  let currentResults = [];
  let currentMetrics = {};
  let sceneDispose = null;
  let forecastDispose = null;
  let llmAvailable = false;

  const pending = { upload: { bank: null, gateway: null }, url: { bank: null, gateway: null } };

  const els = {
    statusPill: document.getElementById('status-pill'),
    runSampleBtn: document.getElementById('run-sample-btn'),
    metricsGrid: document.getElementById('metrics-grid'),
    ledgerScroll: document.getElementById('ledger-scroll'),
    ledgerFilters: document.getElementById('ledger-filters'),
    chatLog: document.getElementById('chat-log'),
    chatInput: document.getElementById('chat-input'),
    chatSend: document.getElementById('chat-send'),
    llmBadge: document.getElementById('llm-badge'),
    sceneContainer: document.getElementById('scene-container'),
    forecastNote: document.getElementById('forecast-note'),
    importRunBtn: document.getElementById('import-run-btn'),
    importRunUrlBtn: document.getElementById('import-run-url-btn'),
  };

  const fmtInr = (n) => '₹' + Number(n).toLocaleString('en-IN', { maximumFractionDigits: 2 });

  async function getJson(url) {
    const res = await fetch(url);
    if (res.status === 401) { window.location.href = '/login'; throw new Error('not authenticated'); }
    return res.json();
  }
  async function postJson(url, body) {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (res.status === 401) { window.location.href = '/login'; throw new Error('not authenticated'); }
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, data };
  }

  document.querySelectorAll('.source-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.source-tab').forEach((t) => t.classList.remove('active'));
      document.querySelectorAll('.source-view').forEach((v) => v.classList.remove('active'));
      tab.classList.add('active');
      document.querySelector(`.source-view[data-view="${tab.dataset.source}"]`).classList.add('active');
    });
  });

  function renderMappingBlock(container, kind, previewData, sourceKey) {
    const fields = kind === 'bank' ? BANK_FIELDS : GATEWAY_FIELDS;
    const allFields = [...fields.required, ...fields.optional];
    const guess = previewData.guessed_mapping;
    const headers = previewData.headers;

    const existing = container.querySelector(`[data-kind="${kind}"]`);
    if (existing) existing.remove();

    const block = document.createElement('div');
    block.dataset.kind = kind;
    block.style.marginTop = '16px';
    block.innerHTML = `
      <div class="section-label" style="margin-bottom:8px;">${kind === 'bank' ? 'Bank' : 'Gateway'} column mapping (${previewData.row_count} rows)</div>
      <table class="mapping-table">
        <thead><tr><th>Field</th><th>Maps to column</th></tr></thead>
        <tbody>
          ${allFields.map((f) => `
            <tr>
              <td>${FIELD_LABELS[f]}${fields.required.includes(f) ? ' *' : ''}</td>
              <td>
                <select data-field="${f}">
                  ${fields.required.includes(f) ? '' : '<option value="">— none —</option>'}
                  ${headers.map((h) => `<option value="${h}" ${h === guess[f] ? 'selected' : ''}>${h}</option>`).join('')}
                </select>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
    container.appendChild(block);

    pending[sourceKey][kind] = { upload_id: previewData.upload_id, blockEl: block, fields };
    updateImportButtonState(sourceKey);
  }

  function readMapping(blockEl) {
    const mapping = {};
    blockEl.querySelectorAll('select').forEach((sel) => { mapping[sel.dataset.field] = sel.value || null; });
    return mapping;
  }

  function updateImportButtonState(sourceKey) {
    const btn = sourceKey === 'upload' ? els.importRunBtn : els.importRunUrlBtn;
    const ready = pending[sourceKey].bank && pending[sourceKey].gateway;
    btn.disabled = !ready;
  }

  function wireUploadSlot(kind) {
    const btn = document.getElementById(`${kind}-upload-btn`);
    const input = document.getElementById(`${kind}-upload-input`);
    const status = document.getElementById(`${kind}-file-status`);
    const slot = document.getElementById(`${kind}-upload-slot`);
    btn.addEventListener('click', () => input.click());
    input.addEventListener('change', async () => {
      const file = input.files[0];
      if (!file) return;
      status.textContent = `${file.name} — parsing…`;
      const form = new FormData();
      form.append('file', file);
      form.append('kind', kind);
      const res = await fetch('/api/csv/preview-upload', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) {
        status.textContent = `Error: ${data.error}`;
        return;
      }
      slot.classList.add('has-file');
      status.textContent = `${file.name} (${data.row_count} rows)`;
      renderMappingBlock(document.getElementById('mapping-container'), kind, data, 'upload');
    });
  }
  wireUploadSlot('bank');
  wireUploadSlot('gateway');

  els.importRunBtn.addEventListener('click', async () => {
    const bank = pending.upload.bank, gateway = pending.upload.gateway;
    const statusEl = document.getElementById('upload-import-status');
    els.importRunBtn.disabled = true;
    statusEl.textContent = 'Importing and reconciling…';
    statusEl.className = 'import-status';

    const { ok, data } = await postJson('/api/reconcile/import', {
      source: 'upload',
      bank_upload_id: bank.upload_id, bank_mapping: readMapping(bank.blockEl),
      gateway_upload_id: gateway.upload_id, gateway_mapping: readMapping(gateway.blockEl),
    });
    els.importRunBtn.disabled = false;
    if (!ok) {
      statusEl.textContent = `Error: ${data.error}`;
      statusEl.className = 'import-status error';
      return;
    }
    statusEl.textContent = `Reconciled ${data.metrics.total_records_considered} records` +
      (data.bank_skipped || data.gateway_skipped ? ` (skipped ${data.bank_skipped + data.gateway_skipped} unparseable rows)` : '');
    statusEl.className = 'import-status ok';
    applyRun(data.run_id, data.metrics, data.results);
  });

  function wireUrlFetch(kind) {
    const btn = document.getElementById(`${kind}-url-fetch`);
    const input = document.getElementById(`${kind}-url-input`);
    btn.addEventListener('click', async () => {
      const url = input.value.trim();
      if (!url) return;
      btn.disabled = true;
      btn.textContent = 'Fetching…';
      const { ok, data } = await postJson('/api/csv/preview-url', { url, kind });
      btn.disabled = false;
      btn.textContent = 'Fetch';
      const statusEl = document.getElementById('url-import-status');
      if (!ok) {
        statusEl.textContent = `Error fetching ${kind}: ${data.error}`;
        statusEl.className = 'import-status error';
        return;
      }
      renderMappingBlock(document.getElementById('url-mapping-container'), kind, data, 'url');
    });
  }
  wireUrlFetch('bank');
  wireUrlFetch('gateway');

  els.importRunUrlBtn.addEventListener('click', async () => {
    const bank = pending.url.bank, gateway = pending.url.gateway;
    const statusEl = document.getElementById('url-import-status');
    els.importRunUrlBtn.disabled = true;
    statusEl.textContent = 'Importing and reconciling…';
    statusEl.className = 'import-status';

    const { ok, data } = await postJson('/api/reconcile/import', {
      source: 'url',
      bank_upload_id: bank.upload_id, bank_mapping: readMapping(bank.blockEl),
      gateway_upload_id: gateway.upload_id, gateway_mapping: readMapping(gateway.blockEl),
    });
    els.importRunUrlBtn.disabled = false;
    if (!ok) {
      statusEl.textContent = `Error: ${data.error}`;
      statusEl.className = 'import-status error';
      return;
    }
    statusEl.textContent = `Reconciled ${data.metrics.total_records_considered} records`;
    statusEl.className = 'import-status ok';
    applyRun(data.run_id, data.metrics, data.results);
  });

  function renderMetrics(metrics) {
    const cards = [
      { label: 'Match rate', value: (metrics.match_rate * 100).toFixed(1) + '%', cls: 'gold' },
      { label: 'Exact matches', value: metrics.exact_matches, cls: 'gold' },
      { label: 'Fuzzy matches', value: metrics.fuzzy_matches, cls: 'green' },
      { label: 'Unmatched — bank', value: metrics.unmatched_bank_only, cls: 'red' },
      { label: 'Unmatched — gateway', value: metrics.unmatched_gateway_only, cls: 'red' },
      { label: 'Value at risk', value: fmtInr(metrics.total_value_at_risk_inr), cls: 'red' },
    ];
    els.metricsGrid.innerHTML = cards.map((c) => `
      <div class="metric-card"><div class="metric-label">${c.label}</div><div class="metric-value ${c.cls}">${c.value}</div></div>
    `).join('');
  }

  function rowRef(r) { return r.bank_record ? r.bank_record.bank_ref_id : r.gateway_record.gateway_txn_id; }
  function rowAmount(r) { return r.bank_record ? r.bank_record.amount : r.gateway_record.amount; }
  function statusLabel(type) { return { exact: 'Exact', fuzzy: 'Fuzzy', unmatched_bank: 'Bank-only', unmatched_gateway: 'Gateway-only' }[type]; }

  let activeFilter = 'all';
  function renderLedger() {
    const rows = currentResults
      .map((r, idx) => ({ r, idx }))
      .filter(({ r }) => activeFilter === 'all' || r.match_type === activeFilter);
    els.ledgerScroll.innerHTML = rows.slice(0, 300).map(({ r, idx }) => `
      <div class="ledger-row" data-idx="${idx}">
        <div class="row-top">
          <span class="ref">${rowRef(r)}</span>
          <span class="status-tag ${r.match_type}">${statusLabel(r.match_type)}</span>
          <span class="amt">${fmtInr(rowAmount(r))}</span>
        </div>
        <div class="explain"></div>
      </div>
    `).join('');
  }

  els.ledgerScroll.addEventListener('click', async (e) => {
    const row = e.target.closest('.ledger-row');
    if (!row) return;
    const idx = Number(row.dataset.idx);
    const explainEl = row.querySelector('.explain');
    const wasOpen = row.classList.contains('open');
    row.classList.toggle('open');
    if (!wasOpen && !explainEl.dataset.loaded) {
      explainEl.textContent = 'Explaining…';
      const { data } = await postJson('/api/explain', { run_id: currentRunId, index: idx });
      explainEl.textContent = data.explanation || data.error || 'No explanation available.';
      explainEl.dataset.loaded = '1';
    }
  });

  els.ledgerFilters.addEventListener('click', (e) => {
    const btn = e.target.closest('.filter-chip');
    if (!btn) return;
    document.querySelectorAll('.filter-chip').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    activeFilter = btn.dataset.filter;
    renderLedger();
  });

  async function renderForecast(runId) {
    const fc = await getJson(`/api/runs/${runId}/forecast`);
    const history = fc.history || [], forecast = fc.forecast || [];

    if (forecastDispose) forecastDispose();
    const container = document.getElementById('forecast-3d-container');
    if (!history.length) {
      els.forecastNote.textContent = 'Not enough matched history to project a forecast yet.';
      forecastDispose = null;
      return;
    }
    forecastDispose = initForecastScene(container, history, forecast);

    els.forecastNote.textContent = forecast.length
      ? `Linear trend over ${history.length} days of matched settlement volume, projected ${forecast.length} days forward. Auditable, not a black-box model.`
      : `${history.length} days of matched settlement volume — not enough history yet for a 7-day projection.`;
  }

  function appendMsg(role, text) {
    const div = document.createElement('div');
    div.className = `msg ${role}`;
    div.innerHTML = `<div class="role">${role === 'user' ? 'You' : 'Copilot'}</div><div class="bubble"></div>`;
    div.querySelector('.bubble').textContent = text;
    els.chatLog.appendChild(div);
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
    return div;
  }

  async function sendChat() {
    const q = els.chatInput.value.trim();
    if (!q || !currentRunId) return;
    els.chatInput.value = '';
    appendMsg('user', q);
    const thinking = appendMsg('agent', '…');
    const { data } = await postJson('/api/chat', { run_id: currentRunId, question: q });
    thinking.querySelector('.bubble').textContent = data.answer || data.error || 'No answer available.';
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
  }
  els.chatSend.addEventListener('click', sendChat);
  els.chatInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') sendChat(); });

  function applyRun(runId, metrics, results) {
    currentRunId = runId;
    currentMetrics = metrics;
    currentResults = results;
    renderMetrics(metrics);
    renderLedger();
    renderForecast(runId);
    if (sceneDispose) sceneDispose();
    sceneDispose = initFlowScene(els.sceneContainer, results);
    els.statusPill.textContent = `${metrics.total_records_considered} records · ${(metrics.match_rate * 100).toFixed(1)}% matched`;
  }

  els.runSampleBtn.addEventListener('click', async () => {
    els.runSampleBtn.disabled = true;
    els.statusPill.textContent = 'running…';
    const { ok, data } = await postJson('/api/reconcile/sample', { n: 80, seed: Math.floor(Math.random() * 100000) });
    els.runSampleBtn.disabled = false;
    if (!ok) { els.statusPill.textContent = 'error'; return; }
    applyRun(data.run_id, data.metrics, data.results);
  });

  async function init() {
    const status = await getJson('/api/llm-status');
    llmAvailable = status.available;
    els.llmBadge.textContent = llmAvailable ? 'LLM enabled' : 'Rule-based mode';
    els.llmBadge.className = `llm-badge ${llmAvailable ? 'on' : 'off'}`;

    const requestedRunId = new URLSearchParams(window.location.search).get('run_id');
    let runId = requestedRunId;
    if (!runId) {
      const summary = await getJson('/api/dashboard/summary');
      runId = summary.run_id;
    }
    const run = await getJson(`/api/runs/${runId}`);
    applyRun(run.id, run.metrics, run.results);
  }
  init();
})();
