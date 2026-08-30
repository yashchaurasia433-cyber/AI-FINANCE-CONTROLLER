"""Synthetic bank + gateway sample data for the "Sample data" source option — seeded so results are reproducible, with the same categories of realistic mismatch a real settlement file exhibits."""
import random
from datetime import date, timedelta

STATUS_TYPES = ['captured', 'refunded', 'settled']


def generate_transactions(n=80, seed=42):
    rng = random.Random(seed)
    base_date = date(2026, 8, 1)
    bank_rows, gateway_rows = [], []

    for i in range(n):
        ref = 'TXN' + ''.join(rng.choice('0123456789') for _ in range(8))
        amount = round(rng.uniform(199, 45999), 2)
        txn_date = base_date + timedelta(days=rng.randint(0, 25))
        merchant = f'Merchant_{rng.randint(1, 12)}'
        status = rng.choice(STATUS_TYPES)

        gw_row = {
            'gateway_txn_id': ref,
            'order_id': 'order_' + ''.join(rng.choice('0123456789abcdef') for _ in range(10)),
            'amount': amount, 'currency': 'INR', 'status': status,
            'created_at': txn_date.isoformat(), 'merchant': merchant,
        }
        bank_row = {
            'bank_ref_id': ref, 'amount': amount, 'value_date': txn_date.isoformat(),
            'narration': f'NEFT/{ref}/{merchant}',
        }

        bucket = i % 12
        if bucket == 0:
            bank_row['amount'] = round(amount + rng.choice([0.02, -0.05, 1.0, -0.5]), 2)
        elif bucket == 1:
            bank_row['value_date'] = (txn_date + timedelta(days=rng.choice([1, 2]))).isoformat()
        elif bucket == 2:
            bank_rows.append(bank_row)
            continue
        elif bucket == 3:
            gateway_rows.append(gw_row)
            continue
        elif bucket == 4:
            gateway_rows.append(gw_row)
            gateway_rows.append({**gw_row, 'gateway_txn_id': ref + '-DUP'})
            bank_rows.append(bank_row)
            continue
        elif bucket == 5:
            last_digit = int(ref[-1])
            corrupted = ref[:-1] + str((last_digit + 1) % 10)
            bank_row['bank_ref_id'] = corrupted
            bank_row['narration'] = f'NEFT/{corrupted}/{merchant}'

        gateway_rows.append(gw_row)
        bank_rows.append(bank_row)

    return bank_rows, gateway_rows
