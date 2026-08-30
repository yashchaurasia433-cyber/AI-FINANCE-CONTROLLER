# 💰 AI Finance Controller

### Real accounts. Real database. Real reconciliation engine — visualized in 3D.

Built for **Razorpay AI Buildathon — Track 04 (Finance Controller)** 🏆

A full-stack web app that reconciles a bank statement against a payment
gateway ledger, explains every mismatch in plain English, and never
pretends it solved something it didn't. Not a prototype — a real Flask
backend, a real SQLite database, and a matching engine stress-tested at
**100,000 transactions in ~2 seconds**.

---

## 🚀 What it does

- 🔐 **Real user accounts** — password hashing, server-side sessions, a working forgot-password/reset-password flow (not a fake login)
- ⚡ **Deterministic reconciliation** — exact match, then confidence-scored fuzzy matching for rounding drift, settlement lag, and reference-ID typos
- 🛡️ **A hard trust rule** — a coincidentally similar reference ID can *never* override a genuinely wrong amount or date
- 📂 **Bring your own data** — reconcile the sample dataset, upload your own bank + gateway CSVs, or fetch one from a URL
- 🧠 **Auto column detection** — messy real-world headers get mapped automatically, you confirm before anything imports
- 🌌 **3D visualization** — the matching process rendered as a literal sorting gate; particles pass through when matched, divert when they don't
- 📊 **Interactive 3D forecast** — hover any bar for the exact settled amount and date
- 💬 **Settlement Q&A** — ask plain-English questions, answered from the real data on screen
- 🗂️ **Persistent history** — every reconciliation run is saved to your account

---

## 🧪 Built and verified with rigor, not just polish

- ✅ **30 automated tests** — matching logic, CSV edge cases, full auth flows, per-user data isolation
- 🐛 **A real bug found and fixed during development**: two transactions sharing a reference ID could silently vanish — never matched, never even reported. Fixed with index-based tracking, locked in with a regression test + a 15-scenario fuzz sweep
- 📈 **Performance-tuned**: date + amount blocking cut fuzzy-match time on 30,000 records from 19.5s → 0.41s
- 📝 **Limitations disclosed up front**, not hidden — see the README section below

---

## 🖥️ Quick start

```bash
git clone https://github.com/your-username/ai-finance-controller.git
cd ai-finance-controller
pip install -r requirements.txt
cp .env.example .env   # optional — see comments inside
python run.py
```


---

## 🧰 Tech stack

`Python` `Flask` `SQLite` `pandas` `Three.js` `Vanilla JS`

---

## 🗺️ Pages

| Page | Route | 🔒 Protected? |
|---|---|:---:|
| 🏠 Home | `/` | No |
| 📝 Register | `/register` | No |
| 🔑 Login | `/login` | No |
| ❓ Forgot Password | `/forgot-password` | No |
| 🔄 Reset Password | `/reset-password` | Token-gated |
| 📊 Dashboard | `/dashboard` | ✅ Yes |
| ⚙️ Reconciliation Workspace | `/reconciliation` | ✅ Yes |
| 📜 Run History | `/history` | ✅ Yes |
| 🛠️ Settings | `/settings` | ✅ Yes |

---

## 🎨 Color palette — every color means something

| Color | Meaning |
|---|---|
| 🟡 Gold `#D8A857` | Money / settled / exact match |
| 🟢 Green `#4FAE7D` | Matched (fuzzy) |
| 🔴 Red `#E2665A` | Exception / value at risk |
| 🔵 Cyan `#4FA8C9` | Bank / source system |
| 🟣 Violet `#7C6FF0` | AI / copilot features |

---

## ⚠️ Known limitations (stated honestly)

- 📧 **No real email delivery** — no SMTP server is configured, so the forgot-password flow shows the reset link directly on the page instead of emailing it. Clearly labeled in the UI, not hidden.
- 💾 **Session secret regenerates on restart** unless `SECRET_KEY` is set in `.env`
- 🧵 **Upload cache is in-process memory** — fine for the single-process dev server this ships with; a production deployment would need a shared store like Redis
- 📉 **Forecast is a plain linear trend** — chosen deliberately for auditability over raw accuracy

---

## 🧪 Run the tests

```bash
python3 -m unittest tests.test_app -v
```

30 tests, no `pytest` required — stdlib `unittest` + Flask's built-in test client.

## 🌐 Live Demo

🔗 **[AI-FINANCE-CONTROLLER](https://ai-finance-controller-he6s.onrender.com))**

> ⏳ **Note:** This is hosted on Render's free tier, which spins down after 15 minutes of inactivity. The first request after a period of inactivity may take 30–60 seconds to wake up — please be patient on your first visit.

Try it out:
1. 📝 Create an account (or use it directly — no test credentials needed)
2. ⚡ Click **"Run Sample Reconciliation"** on the Reconciliation Workspace
3. 🌌 Watch the 3D sorting gate animate as transactions get matched
4. 💬 Ask the Settlement Q&A something like *"what's the match rate?"*

---

## 📄 License & credits

Built solo for the Razorpay AI Buildathon, Track 04.
