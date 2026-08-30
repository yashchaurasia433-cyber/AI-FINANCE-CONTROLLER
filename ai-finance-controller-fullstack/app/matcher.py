"""
Deterministic, explainable reconciliation engine.

Same core approach as before (exact match, then confidence-scored fuzzy
match with a hard amount/date gate) but re-architected for scale: naive
fuzzy matching compares every remaining bank record against every
remaining gateway record — O(n*m), which falls over on large files. This
version buckets remaining records by date and only compares a bank record
against gateway records whose date falls within the tolerance window,
which is how real reconciliation systems avoid a quadratic blowup — the
match RESULT is identical to brute force (nothing outside the date
tolerance can ever score above zero anyway; the hard gate says so), only
the number of comparisons performed changes.
"""
from datetime import date, timedelta
from difflib import SequenceMatcher
from collections import defaultdict

AMOUNT_TOLERANCE_ABS = 1.0
DATE_TOLERANCE_DAYS = 2
FUZZY_CONFIDENCE_THRESHOLD = 0.55


def _parse_iso_date(s: str) -> date:
    y, m, d = s.split('-')
    return date(int(y), int(m), int(d))


def _ref_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _score_pair(bank, gw):
    reasons = []
    amount_diff = abs(bank['amount'] - gw['amount'])
    amount_score = max(0.0, 1 - amount_diff / (AMOUNT_TOLERANCE_ABS + 0.01))
    if amount_diff > AMOUNT_TOLERANCE_ABS:
        return 0.0, [f'amount off by {amount_diff:.2f}']

    day_diff = abs((_parse_iso_date(bank['value_date']) - _parse_iso_date(gw['created_at'])).days)
    date_score = max(0.0, 1 - day_diff / (DATE_TOLERANCE_DAYS + 1))
    if day_diff > DATE_TOLERANCE_DAYS:
        return 0.0, [f'date offset {day_diff}d']

    # Only reached once amount AND date are both within tolerance — this is
    # the expensive check (string similarity), so it's deliberately last:
    # most candidates in a date-blocked window fail on amount alone, and
    # skipping ref-similarity for those is what keeps large batches fast.
    if amount_diff > 0:
        reasons.append(f'amount off by {amount_diff:.2f}')
    if day_diff > 0:
        reasons.append(f'date offset {day_diff}d')

    ref_sim = _ref_similarity(bank['bank_ref_id'], gw['gateway_txn_id'])
    if ref_sim < 1.0:
        reasons.append(f'ref similarity {ref_sim:.2f}')

    confidence = 0.5 * ref_sim + 0.3 * amount_score + 0.2 * date_score
    return confidence, reasons


def reconcile(bank_records, gateway_records):
    results = []

    # ---- Pass 1: exact match (ref id + amount + date) ----
    # Tracked by INDEX into the original lists, never by the reference-id
    # string alone — two distinct records can legitimately share the same
    # reference id (a genuine duplicate transaction id, or in rare cases a
    # coincidental collision in a large batch) with different amounts or
    # dates. Claiming by string previously meant claiming one such record
    # silently vanished the other from every downstream pass — it was
    # never matched AND never reported as an exception. Indices make each
    # input record a distinct entity regardless of what its reference id
    # happens to say.
    gw_by_key = defaultdict(list)
    for gi, gw in enumerate(gateway_records):
        key = (gw['gateway_txn_id'], round(gw['amount'], 2), gw['created_at'])
        gw_by_key[key].append(gi)

    remaining_bank_idx = []
    claimed_gw_idx = set()
    for bi, bank in enumerate(bank_records):
        key = (bank['bank_ref_id'], round(bank['amount'], 2), bank['value_date'])
        candidates = [gi for gi in gw_by_key.get(key, []) if gi not in claimed_gw_idx]
        if len(candidates) == 1:
            gi = candidates[0]
            claimed_gw_idx.add(gi)
            results.append({
                'match_type': 'exact', 'bank_record': bank, 'gateway_record': gateway_records[gi],
                'confidence': 1.0, 'reasons': ['exact match: ref id, amount, and date all align'],
            })
        else:
            remaining_bank_idx.append(bi)

    remaining_gw_idx = [gi for gi in range(len(gateway_records)) if gi not in claimed_gw_idx]

    # ---- Pass 2: fuzzy match, date+amount-bucketed candidate generation, greedy highest-confidence pairing ----
    # Blocking on date alone still leaves a large candidate pool on dense
    # datasets (many transactions per day) since nothing narrows by amount.
    # Given AMOUNT_TOLERANCE_ABS, a real match's amount can only fall in the
    # same or an adjacent whole-rupee bucket — bucketing on BOTH date and
    # floor(amount) cuts the candidate pool far more than date alone,
    # without changing which pairs can possibly match (the hard gate in
    # _score_pair already rejects anything outside tolerance; this only
    # changes how many pairs get to that check).
    remaining_gw_records = [(gi, gateway_records[gi]) for gi in remaining_gw_idx]
    gw_buckets = defaultdict(list)
    for gi, g in remaining_gw_records:
        bucket_key = (g['created_at'], int(g['amount']))
        gw_buckets[bucket_key].append((gi, g))

    amount_span = int(AMOUNT_TOLERANCE_ABS) + 1  # +1 to cover floor() edge effects

    def candidates_within_window(bank_record):
        center_date = _parse_iso_date(bank_record['value_date'])
        center_amount = int(bank_record['amount'])
        seen = set()
        for d_offset in range(-DATE_TOLERANCE_DAYS, DATE_TOLERANCE_DAYS + 1):
            date_key = (center_date + timedelta(days=d_offset)).isoformat()
            for a_offset in range(-amount_span, amount_span + 1):
                bucket_key = (date_key, center_amount + a_offset)
                for gi, g in gw_buckets.get(bucket_key, []):
                    if gi not in seen:
                        seen.add(gi)
                        yield gi, g

    candidates = []
    for bi in remaining_bank_idx:
        b = bank_records[bi]
        for gi, g in candidates_within_window(b):
            score, reasons = _score_pair(b, g)
            if score >= FUZZY_CONFIDENCE_THRESHOLD:
                candidates.append((score, bi, gi, reasons))
    candidates.sort(key=lambda t: t[0], reverse=True)

    claimed_bank_idx = set()
    claimed_gw_idx2 = set()
    for score, bi, gi, reasons in candidates:
        if bi in claimed_bank_idx or gi in claimed_gw_idx2:
            continue
        claimed_bank_idx.add(bi)
        claimed_gw_idx2.add(gi)
        results.append({
            'match_type': 'fuzzy', 'bank_record': bank_records[bi], 'gateway_record': gateway_records[gi],
            'confidence': round(score, 2), 'reasons': reasons,
        })

    # ---- Leftovers are exceptions ----
    for bi in remaining_bank_idx:
        if bi not in claimed_bank_idx:
            results.append({
                'match_type': 'unmatched_bank', 'bank_record': bank_records[bi], 'gateway_record': None,
                'confidence': 0.0, 'reasons': ['no gateway record found within amount/date/ref tolerance'],
            })
    for gi in remaining_gw_idx:
        if gi not in claimed_gw_idx2:
            results.append({
                'match_type': 'unmatched_gateway', 'bank_record': None, 'gateway_record': gateway_records[gi],
                'confidence': 0.0, 'reasons': ['no bank record found within amount/date/ref tolerance'],
            })

    return results


def compute_metrics(results):
    total = len(results)
    exact = sum(1 for r in results if r['match_type'] == 'exact')
    fuzzy = sum(1 for r in results if r['match_type'] == 'fuzzy')
    unmatched_bank = [r for r in results if r['match_type'] == 'unmatched_bank']
    unmatched_gw = [r for r in results if r['match_type'] == 'unmatched_gateway']
    matched = exact + fuzzy
    match_rate = (matched / total) if total else 0.0

    unmatched_bank_value = sum(r['bank_record']['amount'] for r in unmatched_bank)
    unmatched_gw_value = sum(r['gateway_record']['amount'] for r in unmatched_gw)
    fuzzy_results = [r for r in results if r['match_type'] == 'fuzzy']
    avg_fuzzy_confidence = (sum(r['confidence'] for r in fuzzy_results) / len(fuzzy_results)) if fuzzy_results else None

    return {
        'total_records_considered': total,
        'exact_matches': exact,
        'fuzzy_matches': fuzzy,
        'unmatched_bank_only': len(unmatched_bank),
        'unmatched_gateway_only': len(unmatched_gw),
        'match_rate': round(match_rate, 4),
        'avg_fuzzy_match_confidence': round(avg_fuzzy_confidence, 3) if avg_fuzzy_confidence is not None else None,
        'unmatched_bank_value_inr': round(unmatched_bank_value, 2),
        'unmatched_gateway_value_inr': round(unmatched_gw_value, 2),
        'total_value_at_risk_inr': round(unmatched_bank_value + unmatched_gw_value, 2),
    }
