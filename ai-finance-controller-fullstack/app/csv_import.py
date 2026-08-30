"""
Turns arbitrary CSV data (uploaded file, or fetched from a URL) into the
normalized record shape the matcher expects. Runs entirely server-side,
which matters for two reasons: (1) large files never touch the browser's
memory limits, and (2) fetching a CSV from a URL here means the server
makes the HTTP request, not the browser — so it is never blocked by
CORS the way a client-side fetch would be.
"""
import io
import re
import pandas as pd

FIELD_SYNONYMS = {
    'ref': ['ref', 'reference', 'refid', 'ref_id', 'id', 'txnid', 'txn_id', 'transaction',
            'transactionid', 'utr', 'cheque', 'uid', 'gateway_txn_id', 'bank_ref_id'],
    'amount': ['amount', 'amt', 'value', 'sum', 'total', 'debit', 'credit', 'net'],
    'date': ['date', 'value_date', 'valuedate', 'created_at', 'createdat', 'txn_date', 'txndate',
              'posting_date', 'postingdate', 'settlement_date', 'settlementdate'],
    'narration': ['narration', 'description', 'desc', 'remarks', 'particulars', 'memo', 'notes'],
    'status': ['status', 'state'],
    'merchant': ['merchant', 'vendor', 'payee', 'beneficiary', 'party'],
    'currency': ['currency', 'curr', 'ccy'],
    'order_id': ['order_id', 'orderid', 'order', 'invoice', 'invoice_id'],
}


def _normalize_header(h: str) -> str:
    return str(h).strip().lower().replace(' ', '_').replace('-', '_')


def _score_header_for_field(header: str, field: str) -> float:
    h = _normalize_header(header)
    synonyms = FIELD_SYNONYMS.get(field, [])
    if h in synonyms:
        return 1.0
    for s in synonyms:
        if s in h or h in s:
            return 0.7
    return 0.0


def guess_column_mapping(headers, required_fields):
    """Global greedy assignment across all header×field score pairs — see
    csv_import tests for why this matters more than resolving one field
    at a time (a header like "Txn Date" can score non-zero for "ref" via
    a loose match, but should lose to "date" once compared globally)."""
    candidates = []
    for field in required_fields:
        for header in headers:
            score = _score_header_for_field(header, field)
            if score > 0:
                candidates.append((score, field, header))
    candidates.sort(key=lambda t: t[0], reverse=True)

    mapping = {}
    used_headers = set()
    used_fields = set()
    for score, field, header in candidates:
        if field in used_fields or header in used_headers:
            continue
        mapping[field] = header
        used_fields.add(field)
        used_headers.add(header)
    for field in required_fields:
        mapping.setdefault(field, None)
    return mapping


def parse_amount(raw):
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or raw == '':
        return None
    cleaned = re.sub(r'[^\d.\-]', '', str(raw))
    if cleaned in ('', '-', '.', '-.'):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date_to_iso(raw):
    if raw is None or (isinstance(raw, float) and pd.isna(raw)) or raw == '':
        return None
    s = str(raw).strip()

    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        return f'{m.group(1)}-{m.group(2)}-{m.group(3)}'

    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$', s)
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), m.group(3)

        def valid(day, month):
            return 1 <= month <= 12 and 1 <= day <= 31
        if valid(a, b):
            return f'{year}-{b:02d}-{a:02d}'
        if valid(b, a):
            return f'{year}-{a:02d}-{b:02d}'
        return None

    try:
        ts = pd.to_datetime(s, errors='raise')
        return ts.strftime('%Y-%m-%d')
    except Exception:
        return None


def parse_csv_text(text: str):
    """Parses CSV text robustly (handles quoting, embedded commas, BOM) via pandas."""
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, engine='python', sep=None)
    headers = list(df.columns)
    rows = df.to_dict(orient='records')
    return headers, rows


def normalize_rows(rows, mapping, kind):
    """kind is 'bank' or 'gateway'. Returns (records, skipped) — rows that
    fail to parse are collected with a reason, never silently dropped."""
    records = []
    skipped = []

    for i, row in enumerate(rows):
        ref_raw = row.get(mapping.get('ref')) if mapping.get('ref') else None
        amount_raw = row.get(mapping.get('amount')) if mapping.get('amount') else None
        date_raw = row.get(mapping.get('date')) if mapping.get('date') else None

        amount = parse_amount(amount_raw)
        iso_date = parse_date_to_iso(date_raw)

        if not ref_raw or amount is None or not iso_date:
            reason = ('missing reference' if not ref_raw else
                       'unparseable amount' if amount is None else 'unparseable date')
            skipped.append({'row': i + 2, 'reason': reason})
            continue

        if kind == 'bank':
            records.append({
                'bank_ref_id': str(ref_raw).strip(),
                'amount': round(amount, 2),
                'value_date': iso_date,
                'narration': str(row.get(mapping.get('narration'), '') or '') if mapping.get('narration') else '',
            })
        else:
            records.append({
                'gateway_txn_id': str(ref_raw).strip(),
                'order_id': str(row.get(mapping.get('order_id'), '') or '') if mapping.get('order_id') else '',
                'amount': round(amount, 2),
                'currency': str(row.get(mapping.get('currency'), '') or 'INR') if mapping.get('currency') else 'INR',
                'status': str(row.get(mapping.get('status'), '') or '') if mapping.get('status') else '',
                'created_at': iso_date,
                'merchant': str(row.get(mapping.get('merchant'), '') or '') if mapping.get('merchant') else '',
            })

    return records, skipped
