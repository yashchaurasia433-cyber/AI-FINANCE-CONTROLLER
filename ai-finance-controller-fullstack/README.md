# AI Finance Controller

Built for Razorpay Buildathon — **Track 04: Finance Controller**.

A real full-stack web application — Flask backend, SQLite database, real
password-hashed accounts with a working forgot/reset password flow,
per-user reconciliation history, and a 3D-visualized reconciliation
workspace that reconciles sample data, your own CSV uploads, or a CSV
fetched from a URL. This is a ground-up rebuild: a real backend and
database, not a client-only static site with an illusion of login.

## Why this is a genuine rebuild, not a reskin

The previous version of this project ran entirely in the browser: no
server, no database, a "login" that was just a flag in `sessionStorage`
anyone could flip in devtools, an API key the user had to paste into the
page, and CSV imports that could hit browser CORS restrictions when
fetching from a URL. Every one of those is architecturally different here:

| | Before | Now |
|---|---|---|
| Login | Client-side flag, fake | Real Flask session, password-hashed in SQLite |
| Forgot/reset password | Didn't exist | Full token-based flow, tested end-to-end |
| Data persistence | None — lost on tab close | SQLite database, run history per account |
| CSV/URL import | Client-side, URL fetch blocked by CORS | Server-side — CORS never applies |
| LLM API key | Pasted into the browser | Read from server environment only |
| Large files | Limited by browser memory/JS speed | Server-side pandas + optimized matcher (100k records in ~2s) |

## Pages

| Page | Route | Protected? |
|---|---|---|
| Home | `/` | No |
| Create account | `/register` | No (redirects away if already signed in) |
| Sign in | `/login` | No (redirects away if already signed in) |
| Forgot password | `/forgot-password` | No |
| Reset password | `/reset-password?token=...&uid=...` | No (token-gated) |
| Dashboard | `/dashboard` | Yes |
| Reconciliation Workspace | `/reconciliation` | Yes |
| Run History | `/history` | Yes |
| Settings | `/settings` | Yes |

Protected pages are guarded **server-side** in `app/security.py` — a
request without a valid session is redirected before any protected HTML
or JSON is ever produced. There is no client-side flag to flip.

## What it does

1. **Real accounts.** Register with an email, username, and password
   (Werkzeug's scrypt-based hashing, not a demo stub). Forgot your
   password? Real token-based reset: a random 32-byte token is hashed and
   stored with a 30-minute expiry, single-use, and invalidated the moment
   it's used. (See the honesty note on email below.)
2. **Reconciles from three sources**, all producing the same normalized
   record shape:
   - **Sample data** — synthetic bank + gateway transactions with 7
     categories of realistic mismatch, generated fresh each run.
   - **Upload CSVs** — parsed server-side with pandas, columns
     auto-detected via synonym-scored global assignment, shown to you for
     confirmation before import. Handles messy real-world headers
     (`"Cheque No./Ref No."`, `"Withdrawal Amt."`), currency symbols and
     thousands separators (`"₹1,234.50"`), and ambiguous date formats.
   - **Fetch from URL** — the *server* makes the HTTP request, not the
     browser, so it is never blocked by CORS the way a client-side fetch
     would be.
3. **Matches deterministically**: exact match, then a confidence-scored
   fuzzy match for rounding drift, settlement lag, and reference typos,
   with a hard gate so a coincidentally similar reference id can never
   override a genuinely wrong amount or date.
4. **Visualizes** the process as a literal 3D sorting gate — every
   transaction is a particle rendered directly from the real match
   result, not a decorative animation.
5. **Answers questions** via Settlement Q&A — rule-based grounded answers
   with zero setup, or real LLM-powered answers if `ANTHROPIC_API_KEY` is
   set in the server environment (never in the browser).
6. **Forecasts** 7 days of settlement volume with a plain, auditable
   linear trend.
7. **Remembers everything.** Every reconciliation run is saved to your
   account in the database — see them all on the History page, revisit
   any of them in the workspace via `/reconciliation?run_id=N`.

## Honesty note on password reset email

There's no SMTP server configured — no mail credentials, no outbound
mail service. Rather than fake success silently, `/api/auth/forgot-password`
logs the reset link to the console **and** returns it directly in the API
response, so the flow is genuinely testable end-to-end without external
infrastructure. The forgot-password page displays this link directly with
a clear note that in production it would be emailed instead. See
`app/email_stub.py` for exactly where to plug in a real email provider.

## A real bug found and fixed during development

While stress-testing at scale (large synthetic batches), a data-loss bug
surfaced: the matcher tracked "claimed" bank/gateway records by their
**reference-id string**, not by which specific record object had actually
been consumed. Two distinct records that happen to share the same
reference id — a genuine duplicate transaction id, or (as actually
happened, at n=5000) a random collision in a large batch — meant claiming
one silently erased the *other* from every downstream pass: never
matched, never even reported as an exception. For a finance tool, a
transaction vanishing without a trace is a serious defect.

Fixed by tracking every record by its **index** into the original list
instead of by reference-id string, so two records are never conflated
just because their reference ids happen to match. Covered by a permanent
regression test (`test_duplicate_reference_id_with_different_amount_is_never_silently_dropped`)
plus a broader fuzz sweep across 15 size/seed combinations
(`test_fuzz_no_data_loss_across_many_random_seeds_and_sizes`) so this
class of bug can't silently reappear.

## Performance: what "works for big data" actually means here

The naive approach (compare every remaining bank record against every
remaining gateway record) is O(n×m) and falls over on large files. This
matcher blocks candidates by **both date and whole-rupee amount** before
scoring — since a real match can only fall within the amount tolerance,
narrowing by amount cuts the candidate pool far more than date alone,
without changing which pairs *can* match (the existing hard gate in
`_score_pair` still rejects anything outside tolerance; blocking only
changes how many pairs reach that check).

Measured on this machine:

| Records | Time |
|---|---|
| 80 | <0.01s |
| 5,000 | 0.05s |
| 30,000 | 0.41s |
| 100,000 | 2.1s |

## Setup

```bash
cd ai-finance-controller
pip install -r requirements.txt
cp .env.example .env   # optional — see comments inside for what each variable does
python run.py
```

Open `http://localhost:5000`, create an account, and go.

## Testing

```bash
python3 -m unittest tests.test_app -v
```

30 automated tests, no pytest dependency required (stdlib `unittest` +
Flask's built-in test client, which needs no live server or network):

- **Matcher** (9 tests): exact/fuzzy/exceptions/duplicates, the hard
  amount/date gate, no-data-loss, the duplicate-reference-id regression,
  a 15-combination fuzz sweep, and a scale benchmark (50,000 records
  under 5 seconds).
- **CSV import** (7 tests): messy real-world header mapping, currency and
  ambiguous-date parsing, row skip-tracking, quoted-comma-in-amount
  parsing.
- **Auth flow** (6 tests): register/login/logout, protected-route
  redirect, duplicate registration rejection, weak password rejection,
  the full forgot→reset→login-with-new-password flow including token
  reuse rejection, no-email-enumeration on forgot-password, change-password.
- **API flow** (8 tests): sample reconciliation + persistence, per-user
  run isolation (one user cannot view another's run), dashboard
  never-empty + idempotency, the full CSV upload→mapping→import pipeline
  end-to-end, chat/explain grounded in real run data, and that every
  protected page/API route actually requires login.

## Architecture

```
run.py                       — entry point (python run.py)
app/
  __init__.py                 — Flask app factory
  db.py                         — SQLite schema + connection helper (stdlib sqlite3, no ORM)
  security.py                    — password hashing, session auth, login_required decorators
  email_stub.py                    — simulated email delivery (honesty note above)
  matcher.py                        — reconciliation engine (exact + fuzzy, date+amount blocked)
  csv_import.py                      — CSV parsing, column auto-detection, normalization
  data_gen.py                          — synthetic sample-data generator (seeded)
  forecast.py                           — linear-trend 7-day forecast
  chat.py                                 — Settlement Q&A (rule-based + optional server-side LLM)
  upload_cache.py                          — in-memory bridge between CSV preview and import
  routes_pages.py                           — HTML page routes (server-side auth guards)
  routes_auth.py                             — auth API (register/login/forgot/reset/change)
  routes_api.py                               — reconciliation/runs/dashboard/chat API

templates/                    — Jinja2 templates, one per page
static/css/                    — one stylesheet per page + shared base.css
static/js/                      — scene.js (3D gate), scene-ambient.js (decorative),
                                    auth-client.js (nav), pages/*.js (per-page logic)
tests/test_app.py                — 30 automated tests
instance/app.db                   — SQLite database (created on first run, gitignored)
```

## Known limitations (stated up front)

- **No real email delivery** — see the honesty note above. Wiring up a
  real provider is a small, isolated change in `app/email_stub.py`.
- **Upload cache is in-process memory** (`app/upload_cache.py`) — fine for
  Flask's single-process dev server this project runs with; a
  multi-worker production deployment would need a shared store (Redis,
  etc.) instead.
- **Session secret regenerates on restart** unless `SECRET_KEY` is set in
  `.env` — without it, restarting the server logs everyone out.
- **Matching is still greedy, not globally optimal** for the fuzzy pass —
  a proper assignment algorithm would do marginally better on datasets
  with many near-tied candidates, at real added complexity.
- **The forecast is a straight linear trend** — no seasonality or
  day-of-week effects, chosen deliberately for auditability over raw
  accuracy.
- **This is a single-process Flask dev server** (`python run.py`) — for a
  real production deployment, run behind a proper WSGI server (gunicorn,
  waitress) rather than Flask's built-in dev server.

## Color palette (used with intent, not decoration)

| Color | Meaning |
|---|---|
| Gold `#D8A857` | Money / settled / exact match |
| Green `#4FAE7D` | Matched (fuzzy) |
| Red `#E2665A` | Exception / value at risk |
| Cyan `#4FA8C9` | Bank / source system |
| Violet `#7C6FF0` | AI / copilot features |
