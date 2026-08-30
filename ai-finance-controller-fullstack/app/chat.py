"""
Two things live here:

1. rule_based_answer() / explain_exception_fallback() — deterministic
   answers computed directly from the real metrics/results, no network
   needed, always available.
2. call_llm() — an optional real call to the Anthropic API using a key
   read from the server's environment (ANTHROPIC_API_KEY). This is a
   deliberate security improvement over an earlier client-only version
   of this project, which asked the person to paste their API key into
   the browser: a server-side key is never visible to the page, never
   sent to the client, and never logged in browser history.
"""
import os
import re
import requests

ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'


def _row_ref(r):
    return r['bank_record']['bank_ref_id'] if r['bank_record'] else r['gateway_record']['gateway_txn_id']


def _row_amount(r):
    return r['bank_record']['amount'] if r['bank_record'] else r['gateway_record']['amount']


def explain_exception_fallback(result):
    if result['match_type'] == 'exact':
        return 'Exact match — no review needed.'
    if result['match_type'] == 'unmatched_bank':
        b = result['bank_record']
        return (f"Bank shows ₹{b['amount']:.2f} on {b['value_date']} (ref {b['bank_ref_id']}) with no "
                f"matching gateway record. Likely a gateway outage or manual entry. "
                f"Action: check gateway logs for this ref before escalating.")
    if result['match_type'] == 'unmatched_gateway':
        g = result['gateway_record']
        return (f"Gateway shows ₹{g['amount']:.2f} on {g['created_at']} (txn {g['gateway_txn_id']}, "
                f"status={g['status']}) with no matching bank entry. Likely still in settlement transit. "
                f"Action: re-check after the next settlement cycle.")
    if result['match_type'] == 'fuzzy':
        return (f"Matched at {round(result['confidence']*100)}% confidence on non-exact fields "
                f"({'; '.join(result['reasons'])}). Action: spot-check if confidence is below 80%.")
    return 'No explanation available.'


def rule_based_answer(question, metrics, results):
    q = question.lower()

    ref_match = re.search(r'txn\w*\d+', q, re.IGNORECASE) or re.search(r'[A-Z]{3}\d{5,}', question)
    if ref_match:
        ref = ref_match.group(0).upper()
        hit = next((r for r in results if
                    (r['bank_record'] and ref in r['bank_record']['bank_ref_id'].upper()) or
                    (r['gateway_record'] and ref in r['gateway_record']['gateway_txn_id'].upper())), None)
        if hit:
            return f"{ref}: {explain_exception_fallback(hit)}"
        return f'I couldn\'t find a record matching "{ref}" in the current dataset.'

    if re.search(r'match rate|% matched|percent matched|how many.{0,10}match', q):
        return (f"The current match rate is {metrics['match_rate']*100:.1f}% — "
                f"{metrics['exact_matches']} exact matches and {metrics['fuzzy_matches']} fuzzy matches "
                f"out of {metrics['total_records_considered']} total records.")

    if re.search(r'(value|money|amount).{0,15}risk|at risk', q):
        return (f"Total value at risk across unmatched records is ₹{metrics['total_value_at_risk_inr']:,.2f} — "
                f"₹{metrics['unmatched_bank_value_inr']:,.2f} bank-only, "
                f"₹{metrics['unmatched_gateway_value_inr']:,.2f} gateway-only.")

    if re.search(r'how many exception|exception count|number of exception', q):
        n = metrics['unmatched_bank_only'] + metrics['unmatched_gateway_only']
        return f"There are {n} exceptions: {metrics['unmatched_bank_only']} bank-only and {metrics['unmatched_gateway_only']} gateway-only."

    if re.search(r'(largest|biggest|highest).*(unmatched|exception)', q):
        unmatched = [r for r in results if r['match_type'].startswith('unmatched')]
        if not unmatched:
            return 'There are no unmatched records right now.'
        top = max(unmatched, key=_row_amount)
        return f"The largest unmatched record is {_row_ref(top)} at ₹{_row_amount(top):.2f} ({top['match_type'].replace('unmatched_', '')}-only)."

    if re.search(r'confidence|how sure|how confident', q):
        if metrics.get('avg_fuzzy_match_confidence'):
            return f"Average confidence across fuzzy matches is {metrics['avg_fuzzy_match_confidence']*100:.0f}%."
        return 'There are no fuzzy matches in the current run to report confidence on.'

    return ('I can answer questions about match rate, value at risk, exception counts, the largest '
            'unmatched record, or a specific transaction ref (e.g. "why wasn\'t TXN12345678 matched?").')


def call_llm(system_prompt, user_message):
    """Raises on failure — caller decides how to fall back."""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('No ANTHROPIC_API_KEY configured on the server')

    resp = requests.post(
        ANTHROPIC_API_URL,
        headers={
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01',
            'content-type': 'application/json',
        },
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 400,
            'system': system_prompt,
            'messages': [{'role': 'user', 'content': user_message}],
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return ''.join(b['text'] for b in data.get('content', []) if b.get('type') == 'text').strip()


def explain_exception(result, use_llm=True):
    if result['match_type'] == 'exact':
        return 'Exact match — no review needed.'
    if not use_llm:
        return explain_exception_fallback(result)
    try:
        system = ('You are a finance-operations assistant. Given ONE reconciliation exception, explain in '
                   '1-2 short sentences why it is an exception and suggest the single most likely next action. '
                   'Be concrete. Do not invent facts not present in the record.')
        b, g = result['bank_record'], result['gateway_record']
        parts = [f"Exception type: {result['match_type']}"]
        if b:
            parts.append(f"Bank: ref={b['bank_ref_id']}, amount={b['amount']}, date={b['value_date']}")
        if g:
            parts.append(f"Gateway: txn={g['gateway_txn_id']}, amount={g['amount']}, date={g['created_at']}, status={g['status']}")
        parts.append(f"Matcher notes: {'; '.join(result['reasons'])}")
        return call_llm(system, '\n'.join(parts))
    except Exception as e:
        return f"{explain_exception_fallback(result)} [LLM call failed, used fallback: {e}]"


def answer_question(question, metrics, results, use_llm=True):
    if not use_llm:
        return rule_based_answer(question, metrics, results)
    try:
        system = ('You are a Settlement Q&A assistant for a finance-operations team. Answer ONLY using the '
                   'reconciliation data provided below — never invent numbers. Be concise (2-4 sentences).')
        sample = results[:25]
        exc_lines = []
        for r in sample:
            if r['match_type'] == 'exact':
                continue
            exc_lines.append(f"{_row_ref(r)} | {r['match_type']} | ₹{_row_amount(r)} | {'; '.join(r['reasons'])}")
        import json as _json
        context = f"METRICS:\n{_json.dumps(metrics, indent=2)}\n\nEXCEPTIONS (sample):\n" + '\n'.join(exc_lines) + f"\n\nQUESTION: {question}"
        return call_llm(system, context)
    except Exception as e:
        return f"{rule_based_answer(question, metrics, results)}\n\n[LLM call failed, used rule-based fallback: {e}]"
