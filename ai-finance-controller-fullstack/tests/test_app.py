"""
Run with: python3 -m unittest tests.test_app -v
(No pytest dependency required — stdlib unittest + Flask's built-in test
client, which needs no live server or network access.)
"""
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MatcherTests(unittest.TestCase):
    def setUp(self):
        from app.matcher import reconcile, compute_metrics
        self.reconcile = reconcile
        self.compute_metrics = compute_metrics

    def test_exact_match(self):
        bank = [{'bank_ref_id': 'TXN001', 'amount': 500.0, 'value_date': '2026-08-01', 'narration': ''}]
        gw = [{'gateway_txn_id': 'TXN001', 'order_id': 'o1', 'amount': 500.0, 'currency': 'INR', 'status': 'captured', 'created_at': '2026-08-01', 'merchant': 'M'}]
        results = self.reconcile(bank, gw)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['match_type'], 'exact')
        self.assertEqual(results[0]['confidence'], 1.0)

    def test_fuzzy_amount_drift(self):
        bank = [{'bank_ref_id': 'TXN002', 'amount': 500.05, 'value_date': '2026-08-01', 'narration': ''}]
        gw = [{'gateway_txn_id': 'TXN002', 'order_id': 'o2', 'amount': 500.0, 'currency': 'INR', 'status': 'captured', 'created_at': '2026-08-01', 'merchant': 'M'}]
        results = self.reconcile(bank, gw)
        self.assertEqual(results[0]['match_type'], 'fuzzy')
        self.assertGreater(results[0]['confidence'], 0.9)

    def test_date_lag_boundary(self):
        bank = [{'bank_ref_id': 'TXN003', 'amount': 1000.0, 'value_date': '2026-08-03', 'narration': ''}]
        gw = [{'gateway_txn_id': 'TXN003', 'order_id': 'o3', 'amount': 1000.0, 'currency': 'INR', 'status': 'captured', 'created_at': '2026-08-01', 'merchant': 'M'}]
        results = self.reconcile(bank, gw)
        self.assertEqual(results[0]['match_type'], 'fuzzy')

    def test_amount_too_far_off_no_free_pass_on_matching_ref(self):
        bank = [{'bank_ref_id': 'TXN005', 'amount': 500.0, 'value_date': '2026-08-01', 'narration': ''}]
        gw = [{'gateway_txn_id': 'TXN005', 'order_id': 'o5', 'amount': 5000.0, 'currency': 'INR', 'status': 'captured', 'created_at': '2026-08-01', 'merchant': 'M'}]
        results = self.reconcile(bank, gw)
        self.assertEqual(len(results), 2)
        types = sorted(r['match_type'] for r in results)
        self.assertEqual(types, ['unmatched_bank', 'unmatched_gateway'])

    def test_duplicate_gateway_charge_only_one_claims(self):
        bank = [{'bank_ref_id': 'TXN008', 'amount': 400.0, 'value_date': '2026-08-01', 'narration': ''}]
        gw = [
            {'gateway_txn_id': 'TXN008', 'order_id': 'o8', 'amount': 400.0, 'currency': 'INR', 'status': 'captured', 'created_at': '2026-08-01', 'merchant': 'M'},
            {'gateway_txn_id': 'TXN008-DUP', 'order_id': 'o8b', 'amount': 400.0, 'currency': 'INR', 'status': 'captured', 'created_at': '2026-08-01', 'merchant': 'M'},
        ]
        results = self.reconcile(bank, gw)
        matched = [r for r in results if r['match_type'] in ('exact', 'fuzzy')]
        unmatched_gw = [r for r in results if r['match_type'] == 'unmatched_gateway']
        self.assertEqual(len(matched), 1)
        self.assertEqual(len(unmatched_gw), 1)

    def test_no_data_loss(self):
        bank = [
            {'bank_ref_id': 'TXN010', 'amount': 100.0, 'value_date': '2026-08-01', 'narration': ''},
            {'bank_ref_id': 'TXN011', 'amount': 200.0, 'value_date': '2026-08-02', 'narration': ''},
        ]
        gw = [
            {'gateway_txn_id': 'TXN010', 'order_id': 'o1', 'amount': 100.0, 'currency': 'INR', 'status': 'captured', 'created_at': '2026-08-01', 'merchant': 'M'},
            {'gateway_txn_id': 'TXN099', 'order_id': 'o2', 'amount': 999.0, 'currency': 'INR', 'status': 'captured', 'created_at': '2026-08-09', 'merchant': 'M'},
        ]
        results = self.reconcile(bank, gw)
        self.assertEqual(sum(1 for r in results if r['bank_record']), len(bank))
        self.assertEqual(sum(1 for r in results if r['gateway_record']), len(gw))

    def test_scales_to_large_dataset_reasonably_fast(self):
        import time
        from app.data_gen import generate_transactions
        bank, gw = generate_transactions(n=50000, seed=1)
        t0 = time.time()
        results = self.reconcile(bank, gw)
        elapsed = time.time() - t0
        self.assertLess(elapsed, 5.0, f'Reconciliation of 50000 records took {elapsed:.1f}s — too slow for "big data" claims')
        bank_seen = sum(1 for r in results if r['bank_record'])
        gw_seen = sum(1 for r in results if r['gateway_record'])
        self.assertEqual(bank_seen, len(bank))
        self.assertEqual(gw_seen, len(gw))

    def test_duplicate_reference_id_with_different_amount_is_never_silently_dropped(self):
        """Regression test for a real bug found during development: two
        DISTINCT gateway records sharing the same reference id (a genuine
        duplicate-id scenario, or a random collision in a large batch)
        were being tracked as "claimed" by the reference-id STRING alone.
        Claiming one silently vanished the other from every downstream
        pass — never matched, never even reported as an exception. This
        must never regress: every input record must appear in the output,
        regardless of whether its reference id happens to collide with
        another record's."""
        bank = [{'bank_ref_id': 'TXN90046114', 'amount': 17574.18, 'value_date': '2026-08-06', 'narration': ''}]
        gw = [
            {'gateway_txn_id': 'TXN90046114', 'order_id': 'o1', 'amount': 17574.18, 'currency': 'INR', 'status': 'refunded', 'created_at': '2026-08-06', 'merchant': 'Merchant_3'},
            {'gateway_txn_id': 'TXN90046114', 'order_id': 'o2', 'amount': 10511.06, 'currency': 'INR', 'status': 'refunded', 'created_at': '2026-08-21', 'merchant': 'Merchant_1'},
        ]
        results = self.reconcile(bank, gw)
        gw_seen = sum(1 for r in results if r['gateway_record'])
        self.assertEqual(gw_seen, 2, 'both gateway records must appear in the output, even though they share a reference id')
        exact = [r for r in results if r['match_type'] == 'exact']
        unmatched_gw = [r for r in results if r['match_type'] == 'unmatched_gateway']
        self.assertEqual(len(exact), 1)
        self.assertEqual(len(unmatched_gw), 1)
        self.assertEqual(unmatched_gw[0]['gateway_record']['order_id'], 'o2')

    def test_fuzz_no_data_loss_across_many_random_seeds_and_sizes(self):
        """Broad regression sweep: for a range of dataset sizes and random
        seeds, every single input record must appear exactly once in the
        output — the invariant the earlier bug violated only at scale
        (it needed a large enough batch for a reference-id collision to
        actually occur by chance)."""
        from app.data_gen import generate_transactions
        for size in (50, 500, 3000):
            for seed in (1, 2, 3, 4, 5):
                bank, gw = generate_transactions(n=size, seed=seed)
                results = self.reconcile(bank, gw)
                bank_seen = sum(1 for r in results if r['bank_record'])
                gw_seen = sum(1 for r in results if r['gateway_record'])
                self.assertEqual(bank_seen, len(bank), f'size={size} seed={seed}')
                self.assertEqual(gw_seen, len(gw), f'size={size} seed={seed}')
                # every result index and gw/bank record must be genuinely distinct objects, not double-counted
                bank_ids_seen = [id(r['bank_record']) for r in results if r['bank_record']]
                gw_ids_seen = [id(r['gateway_record']) for r in results if r['gateway_record']]
                self.assertEqual(len(bank_ids_seen), len(set(bank_ids_seen)), f'size={size} seed={seed}: a bank record object appeared more than once')
                self.assertEqual(len(gw_ids_seen), len(set(gw_ids_seen)), f'size={size} seed={seed}: a gateway record object appeared more than once')


class CsvImportTests(unittest.TestCase):
    def setUp(self):
        from app.csv_import import guess_column_mapping, parse_amount, parse_date_to_iso, parse_csv_text, normalize_rows
        self.guess_column_mapping = guess_column_mapping
        self.parse_amount = parse_amount
        self.parse_date_to_iso = parse_date_to_iso
        self.parse_csv_text = parse_csv_text
        self.normalize_rows = normalize_rows

    def test_messy_bank_header_mapping(self):
        headers = ['Txn Date', 'Cheque No./Ref No.', 'Withdrawal Amt.', 'Deposit Amt.', 'Narration']
        mapping = self.guess_column_mapping(headers, ['ref', 'amount', 'date', 'narration'])
        self.assertEqual(mapping['date'], 'Txn Date')
        self.assertEqual(mapping['ref'], 'Cheque No./Ref No.')
        self.assertEqual(mapping['narration'], 'Narration')

    def test_clean_gateway_header_mapping(self):
        headers = ['payment_id', 'order_id', 'amount', 'currency', 'status', 'created_at', 'merchant_name']
        mapping = self.guess_column_mapping(headers, ['ref', 'order_id', 'amount', 'currency', 'status', 'date', 'merchant'])
        self.assertEqual(mapping['ref'], 'payment_id')
        self.assertEqual(mapping['date'], 'created_at')
        self.assertEqual(mapping['merchant'], 'merchant_name')

    def test_amount_parsing_currency_and_commas(self):
        self.assertEqual(self.parse_amount('₹1,234.50'), 1234.5)
        self.assertEqual(self.parse_amount('1234.50'), 1234.5)
        self.assertIsNone(self.parse_amount(''))

    def test_date_parsing_unambiguous(self):
        self.assertEqual(self.parse_date_to_iso('2026-08-15'), '2026-08-15')
        self.assertEqual(self.parse_date_to_iso('15/08/2026'), '2026-08-15')

    def test_date_parsing_falls_back_to_month_first_when_day_first_impossible(self):
        self.assertEqual(self.parse_date_to_iso('08-15-2026'), '2026-08-15')

    def test_date_parsing_garbage_returns_none(self):
        self.assertIsNone(self.parse_date_to_iso('garbage'))

    def test_normalize_rows_skips_bad_rows_keeps_good_ones(self):
        rows = [
            {'txn_ref': 'TXN001', 'amt': '500.00', 'dt': '2026-08-01', 'note': 'payment'},
            {'txn_ref': '', 'amt': '500.00', 'dt': '2026-08-01', 'note': 'bad row'},
            {'txn_ref': 'TXN002', 'amt': 'notanumber', 'dt': '2026-08-01', 'note': 'bad amount'},
        ]
        mapping = {'ref': 'txn_ref', 'amount': 'amt', 'date': 'dt', 'narration': 'note'}
        records, skipped = self.normalize_rows(rows, mapping, 'bank')
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['bank_ref_id'], 'TXN001')
        self.assertEqual(len(skipped), 2)

    def test_quoted_comma_in_amount_parses_correctly(self):
        csv_text = 'Txn Date,Ref,Amount\n01/08/2026,TXN001,"1,500.00"\n'
        headers, rows = self.parse_csv_text(csv_text)
        self.assertEqual(rows[0]['Amount'], '1,500.00')
        self.assertEqual(self.parse_amount(rows[0]['Amount']), 1500.0)


class AppFactoryFixture:
    """Provides a fresh app + isolated temp SQLite DB per test class."""

    @classmethod
    def setUpClass(cls):
        cls._tmpdir = tempfile.mkdtemp()
        cls._db_path = os.path.join(cls._tmpdir, 'test.db')
        import app.db as db_module
        db_module.DB_PATH = cls._db_path
        from app import create_app
        cls.app = create_app()
        cls.app.config['TESTING'] = True

    def setUp(self):
        # Fresh DB per test method to avoid cross-test interference
        import app.db as db_module
        if os.path.exists(db_module.DB_PATH):
            os.remove(db_module.DB_PATH)
        db_module.init_db()
        self.client = self.app.test_client()


class AuthFlowTests(AppFactoryFixture, unittest.TestCase):
    def test_register_login_logout_and_protected_redirect(self):
        r = self.client.post('/api/auth/register', json={'email': 'a@b.com', 'username': 'alice', 'password': 'password123'})
        self.assertEqual(r.status_code, 200)

        r = self.client.get('/dashboard')
        self.assertEqual(r.status_code, 200)

        self.client.post('/api/auth/logout')
        r = self.client.get('/dashboard', follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn('/login', r.headers['Location'])

        r = self.client.post('/api/auth/login', json={'username': 'alice', 'password': 'wrongpass'})
        self.assertEqual(r.status_code, 401)

        r = self.client.post('/api/auth/login', json={'username': 'alice', 'password': 'password123'})
        self.assertEqual(r.status_code, 200)

    def test_duplicate_registration_rejected(self):
        self.client.post('/api/auth/register', json={'email': 'a@b.com', 'username': 'alice', 'password': 'password123'})
        r = self.client.post('/api/auth/register', json={'email': 'a@b.com', 'username': 'alice2', 'password': 'password123'})
        self.assertEqual(r.status_code, 409)

    def test_weak_password_rejected(self):
        r = self.client.post('/api/auth/register', json={'email': 'x@y.com', 'username': 'xavier', 'password': 'short'})
        self.assertEqual(r.status_code, 400)

    def test_forgot_and_reset_password_full_flow(self):
        self.client.post('/api/auth/register', json={'email': 'b@c.com', 'username': 'bob', 'password': 'oldpassword1'})
        self.client.post('/api/auth/logout')

        r = self.client.post('/api/auth/forgot-password', json={'email': 'b@c.com'})
        self.assertEqual(r.status_code, 200)
        link = r.get_json()['demo_reset_link']
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(link).query)
        token, uid = q['token'][0], q['uid'][0]

        r = self.client.post('/api/auth/reset-password', json={'token': 'wrong', 'uid': uid, 'password': 'newpassword1'})
        self.assertEqual(r.status_code, 400)

        r = self.client.post('/api/auth/reset-password', json={'token': token, 'uid': uid, 'password': 'newpassword1'})
        self.assertEqual(r.status_code, 200)

        # token reuse must fail
        r = self.client.post('/api/auth/reset-password', json={'token': token, 'uid': uid, 'password': 'again12345'})
        self.assertEqual(r.status_code, 400)

        r = self.client.post('/api/auth/login', json={'username': 'bob', 'password': 'oldpassword1'})
        self.assertEqual(r.status_code, 401)
        r = self.client.post('/api/auth/login', json={'username': 'bob', 'password': 'newpassword1'})
        self.assertEqual(r.status_code, 200)

    def test_forgot_password_unknown_email_gives_generic_response_no_leak(self):
        r = self.client.post('/api/auth/forgot-password', json={'email': 'nobody@nowhere.com'})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn('demo_reset_link', r.get_json())

    def test_change_password_requires_correct_current_password(self):
        self.client.post('/api/auth/register', json={'email': 'e@f.com', 'username': 'erin', 'password': 'password123'})
        r = self.client.post('/api/auth/change-password', json={'current_password': 'wrong', 'new_password': 'newpassword1'})
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/api/auth/change-password', json={'current_password': 'password123', 'new_password': 'newpassword1'})
        self.assertEqual(r.status_code, 200)


class ApiFlowTests(AppFactoryFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.client.post('/api/auth/register', json={'email': 'g@h.com', 'username': 'grace', 'password': 'password123'})

    def test_sample_reconcile_and_run_persistence(self):
        r = self.client.post('/api/reconcile/sample', json={'n': 80, 'seed': 42})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data['metrics']['exact_matches'], 45)
        self.assertEqual(data['metrics']['fuzzy_matches'], 21)

        run_id = data['run_id']
        r2 = self.client.get(f'/api/runs/{run_id}')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()['metrics']['total_records_considered'], 87)

    def test_runs_are_isolated_per_user(self):
        r = self.client.post('/api/reconcile/sample', json={'n': 80, 'seed': 42})
        run_id = r.get_json()['run_id']

        self.client.post('/api/auth/logout')
        self.client.post('/api/auth/register', json={'email': 'i@j.com', 'username': 'ivan', 'password': 'password123'})
        r2 = self.client.get(f'/api/runs/{run_id}')
        self.assertEqual(r2.status_code, 404, "a user must not be able to view another user's run")

    def test_dashboard_summary_is_never_empty_and_idempotent(self):
        r1 = self.client.get('/api/dashboard/summary')
        data1 = r1.get_json()
        self.assertTrue(data1['is_fresh_sample'])

        r2 = self.client.get('/api/dashboard/summary')
        data2 = r2.get_json()
        self.assertFalse(data2['is_fresh_sample'])
        self.assertEqual(data1['run_id'], data2['run_id'])

    def test_full_upload_import_pipeline(self):
        bank_csv = ('Txn Date,Cheque No./Ref No.,Withdrawal Amt.,Narration\n'
                    '01/08/2026,TXN10000001,"1,500.00",NEFT payment\n'
                    '02/08/2026,TXN10000002,2300.50,NEFT payment 2\n'
                    '03/08/2026,TXN10000003,999.00,NEFT payment 3\n')
        gw_csv = ('payment_id,order_id,amount,currency,status,created_at,merchant_name\n'
                  'TXN10000001,o1,1500.00,INR,captured,2026-08-01,Merchant_1\n'
                  'TXN10000002,o2,2300.50,INR,captured,2026-08-02,Merchant_2\n')

        r1 = self.client.post('/api/csv/preview-upload',
                               data={'file': (io.BytesIO(bank_csv.encode()), 'bank.csv'), 'kind': 'bank'},
                               content_type='multipart/form-data')
        p1 = r1.get_json()
        r2 = self.client.post('/api/csv/preview-upload',
                               data={'file': (io.BytesIO(gw_csv.encode()), 'gw.csv'), 'kind': 'gateway'},
                               content_type='multipart/form-data')
        p2 = r2.get_json()

        r3 = self.client.post('/api/reconcile/import', json={
            'source': 'upload',
            'bank_upload_id': p1['upload_id'], 'bank_mapping': p1['guessed_mapping'],
            'gateway_upload_id': p2['upload_id'], 'gateway_mapping': p2['guessed_mapping'],
        })
        self.assertEqual(r3.status_code, 200)
        result = r3.get_json()
        self.assertEqual(result['metrics']['exact_matches'], 2)
        self.assertEqual(result['metrics']['unmatched_bank_only'], 1)

        # upload cache must be discarded after a successful import
        r4 = self.client.post('/api/reconcile/import', json={
            'source': 'upload',
            'bank_upload_id': p1['upload_id'], 'bank_mapping': p1['guessed_mapping'],
            'gateway_upload_id': p2['upload_id'], 'gateway_mapping': p2['guessed_mapping'],
        })
        self.assertEqual(r4.status_code, 400)

    def test_chat_and_explain_use_real_run_data(self):
        r = self.client.post('/api/reconcile/sample', json={'n': 80, 'seed': 42})
        run_id = r.get_json()['run_id']

        r2 = self.client.post('/api/chat', json={'run_id': run_id, 'question': 'what is the match rate?'})
        self.assertEqual(r2.status_code, 200)
        self.assertIn('75.9%', r2.get_json()['answer'])

        r3 = self.client.post('/api/explain', json={'run_id': run_id, 'index': 0})
        self.assertEqual(r3.status_code, 200)
        self.assertTrue(len(r3.get_json()['explanation']) > 0)

    def test_all_pages_require_login(self):
        self.client.post('/api/auth/logout')
        for path in ['/dashboard', '/reconciliation', '/history', '/settings']:
            r = self.client.get(path, follow_redirects=False)
            self.assertEqual(r.status_code, 302, f'{path} should redirect when not logged in')

    def test_api_routes_require_login(self):
        self.client.post('/api/auth/logout')
        r = self.client.post('/api/reconcile/sample', json={})
        self.assertEqual(r.status_code, 401)
        r = self.client.get('/api/runs')
        self.assertEqual(r.status_code, 401)


if __name__ == '__main__':
    unittest.main()
