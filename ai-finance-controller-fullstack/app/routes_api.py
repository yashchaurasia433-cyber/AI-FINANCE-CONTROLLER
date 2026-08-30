import json
import os

import requests as http_requests
from flask import Blueprint, request, jsonify

from .db import get_db, now_iso
from .security import api_login_required, current_user_id
from .data_gen import generate_transactions
from .matcher import reconcile, compute_metrics
from .csv_import import parse_csv_text, guess_column_mapping, normalize_rows
from .forecast import build_daily_settled_series, linear_forecast
from .chat import answer_question, explain_exception
from . import upload_cache

bp = Blueprint('api', __name__, url_prefix='/api')

BANK_FIELDS = ['ref', 'amount', 'date', 'narration']
GATEWAY_FIELDS = ['ref', 'amount', 'date', 'order_id', 'currency', 'status', 'merchant']
MAX_UPLOAD_ROWS = 200_000  # sanity ceiling so a malformed file can't exhaust server memory


def _llm_available():
    return bool(os.environ.get('ANTHROPIC_API_KEY'))


def _save_run(source, bank_rows, gateway_rows):
    results = reconcile(bank_rows, gateway_rows)
    metrics = compute_metrics(results)

    db = get_db()
    cur = db.execute(
        'INSERT INTO runs (user_id, source, row_count, metrics_json, results_json, created_at) VALUES (?, ?, ?, ?, ?, ?)',
        (current_user_id(), source, len(results), json.dumps(metrics), json.dumps(results), now_iso()),
    )
    db.commit()
    run_id = cur.lastrowid
    db.close()
    return run_id, metrics, results


def _load_run(run_id):
    db = get_db()
    row = db.execute('SELECT * FROM runs WHERE id = ? AND user_id = ?', (run_id, current_user_id())).fetchone()
    db.close()
    if not row:
        return None
    return {
        'id': row['id'], 'source': row['source'], 'row_count': row['row_count'],
        'metrics': json.loads(row['metrics_json']), 'results': json.loads(row['results_json']),
        'created_at': row['created_at'],
    }


@bp.get('/llm-status')
@api_login_required
def llm_status():
    return jsonify({'available': _llm_available()})


# ===== Sample data =====
@bp.post('/reconcile/sample')
@api_login_required
def reconcile_sample():
    data = request.get_json(silent=True) or {}
    n = min(int(data.get('n', 80)), 20000)
    seed = int(data.get('seed', 42))

    bank_rows, gateway_rows = generate_transactions(n=n, seed=seed)
    run_id, metrics, results = _save_run('sample', bank_rows, gateway_rows)
    return jsonify({'run_id': run_id, 'metrics': metrics, 'results': results})


# ===== CSV preview (upload or URL) — returns guessed mapping without importing yet =====
@bp.post('/csv/preview-upload')
@api_login_required
def csv_preview_upload():
    kind = request.form.get('kind')
    if kind not in ('bank', 'gateway'):
        return jsonify({'error': 'kind must be "bank" or "gateway"'}), 400
    file = request.files.get('file')
    if not file:
        return jsonify({'error': 'No file uploaded'}), 400

    try:
        text = file.read().decode('utf-8-sig', errors='replace')
        headers, rows = parse_csv_text(text)
    except Exception as e:
        return jsonify({'error': f'Could not parse CSV: {e}'}), 400

    return _respond_preview(headers, rows, kind)


@bp.post('/csv/preview-url')
@api_login_required
def csv_preview_url():
    data = request.get_json(silent=True) or {}
    url = (data.get('url') or '').strip()
    kind = data.get('kind')
    if kind not in ('bank', 'gateway'):
        return jsonify({'error': 'kind must be "bank" or "gateway"'}), 400
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    try:
        # Fetched server-side — this is what avoids the browser CORS
        # restriction a client-only fetch would hit.
        resp = http_requests.get(url, timeout=20)
        resp.raise_for_status()
        headers, rows = parse_csv_text(resp.text)
    except http_requests.exceptions.RequestException as e:
        return jsonify({'error': f'Could not fetch URL: {e}'}), 400
    except Exception as e:
        return jsonify({'error': f'Could not parse CSV from URL: {e}'}), 400

    return _respond_preview(headers, rows, kind)


def _respond_preview(headers, rows, kind):
    if len(rows) > MAX_UPLOAD_ROWS:
        return jsonify({'error': f'File has {len(rows)} rows, over the {MAX_UPLOAD_ROWS} row limit.'}), 400
    if not headers or not rows:
        return jsonify({'error': 'No rows found in this file.'}), 400

    fields = BANK_FIELDS if kind == 'bank' else GATEWAY_FIELDS
    guessed = guess_column_mapping(headers, fields)
    upload_id = upload_cache.store(headers, rows)

    return jsonify({
        'upload_id': upload_id,
        'headers': headers,
        'row_count': len(rows),
        'guessed_mapping': guessed,
        'sample_rows': rows[:5],
        'kind': kind,
    })


# ===== Confirm import: normalize with the (possibly user-edited) mapping and reconcile =====
@bp.post('/reconcile/import')
@api_login_required
def reconcile_import():
    data = request.get_json(silent=True) or {}
    bank_upload_id = data.get('bank_upload_id')
    gateway_upload_id = data.get('gateway_upload_id')
    bank_mapping = data.get('bank_mapping') or {}
    gateway_mapping = data.get('gateway_mapping') or {}
    source = data.get('source', 'upload')

    bank_entry = upload_cache.retrieve(bank_upload_id)
    gateway_entry = upload_cache.retrieve(gateway_upload_id)
    if not bank_entry or not gateway_entry:
        return jsonify({'error': 'Upload session expired or not found — please re-upload/re-fetch both files.'}), 400

    bank_records, bank_skipped = normalize_rows(bank_entry['rows'], bank_mapping, 'bank')
    gateway_records, gateway_skipped = normalize_rows(gateway_entry['rows'], gateway_mapping, 'gateway')

    if not bank_records or not gateway_records:
        return jsonify({'error': 'No valid rows after normalization — check the column mapping.'}), 400

    run_id, metrics, results = _save_run(source, bank_records, gateway_records)
    upload_cache.discard(bank_upload_id)
    upload_cache.discard(gateway_upload_id)

    return jsonify({
        'run_id': run_id, 'metrics': metrics, 'results': results,
        'bank_skipped': len(bank_skipped), 'gateway_skipped': len(gateway_skipped),
    })


# ===== Run history =====
@bp.get('/runs')
@api_login_required
def list_runs():
    db = get_db()
    rows = db.execute(
        'SELECT id, source, row_count, metrics_json, created_at FROM runs WHERE user_id = ? ORDER BY id DESC LIMIT 50',
        (current_user_id(),),
    ).fetchall()
    db.close()
    runs = []
    for r in rows:
        m = json.loads(r['metrics_json'])
        runs.append({
            'id': r['id'], 'source': r['source'], 'row_count': r['row_count'],
            'match_rate': m['match_rate'], 'total_value_at_risk_inr': m['total_value_at_risk_inr'],
            'created_at': r['created_at'],
        })
    return jsonify({'runs': runs})


@bp.get('/runs/<int:run_id>')
@api_login_required
def get_run(run_id):
    run = _load_run(run_id)
    if not run:
        return jsonify({'error': 'Run not found'}), 404
    return jsonify(run)


@bp.get('/dashboard/summary')
@api_login_required
def dashboard_summary():
    db = get_db()
    row = db.execute(
        'SELECT id FROM runs WHERE user_id = ? ORDER BY id DESC LIMIT 1', (current_user_id(),)
    ).fetchone()
    db.close()

    if not row:
        # No reconciliation has run yet for this user — generate one now
        # so the dashboard is never an empty page.
        bank_rows, gateway_rows = generate_transactions(n=80, seed=42)
        run_id, metrics, results = _save_run('sample', bank_rows, gateway_rows)
        is_fresh = True
    else:
        run = _load_run(row['id'])
        run_id, metrics, results = run['id'], run['metrics'], run['results']
        is_fresh = False

    top_exceptions = sorted(
        (r for r in results if r['match_type'] != 'exact'),
        key=lambda r: (r['bank_record']['amount'] if r['bank_record'] else r['gateway_record']['amount']),
        reverse=True,
    )[:6]
    top_exceptions_out = [{
        'ref': r['bank_record']['bank_ref_id'] if r['bank_record'] else r['gateway_record']['gateway_txn_id'],
        'type': r['match_type'],
        'amount': r['bank_record']['amount'] if r['bank_record'] else r['gateway_record']['amount'],
    } for r in top_exceptions]

    return jsonify({'run_id': run_id, 'metrics': metrics, 'top_exceptions': top_exceptions_out, 'is_fresh_sample': is_fresh})


@bp.get('/runs/<int:run_id>/forecast')
@api_login_required
def run_forecast(run_id):
    run = _load_run(run_id)
    if not run:
        return jsonify({'error': 'Run not found'}), 404
    series = build_daily_settled_series(run['results'])
    return jsonify(linear_forecast(series, horizon_days=7))


# ===== Chat / explanations =====
@bp.post('/chat')
@api_login_required
def chat():
    data = request.get_json(silent=True) or {}
    run_id = data.get('run_id')
    question = (data.get('question') or '').strip()
    if not question:
        return jsonify({'error': 'No question provided'}), 400

    run = _load_run(run_id)
    if not run:
        return jsonify({'error': 'Run not found'}), 404

    answer = answer_question(question, run['metrics'], run['results'], use_llm=_llm_available())
    return jsonify({'answer': answer})


@bp.post('/explain')
@api_login_required
def explain():
    data = request.get_json(silent=True) or {}
    run_id = data.get('run_id')
    index = data.get('index')

    run = _load_run(run_id)
    if not run or index is None or not (0 <= index < len(run['results'])):
        return jsonify({'error': 'Run or result index not found'}), 404

    result = run['results'][index]
    explanation = explain_exception(result, use_llm=_llm_available())
    return jsonify({'explanation': explanation})
