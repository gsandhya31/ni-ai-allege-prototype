# Allege Automation Prototype

Working prototype for Nomura OTC Allege reconciliation. Reads `.eml` files from a local folder, classifies each as allege / not-allege, extracts trade fields, searches three mock internal systems (BO → MO → FO), drafts a reply from templates, and lets the analyst approve + send.

> This is a demo-only prototype. No real emails are sent. Drafts are saved to `backend/data/sent/` as `.eml` files for inspection.

---

## Quick start

### Prerequisites

**macOS:**
- Node.js 18+ (`brew install node`)
- Python 3.11 (`brew install python@3.11`)
- Homebrew (optional, for the above)

**Windows:**
- Node.js 18+ from [nodejs.org](https://nodejs.org) (LTS installer)
- Python 3.11 from [python.org](https://www.python.org/downloads/windows/) — tick **"Add Python to PATH"** during install
- Git (optional) from [git-scm.com](https://git-scm.com/download/win)

### One-time setup

1. Open a terminal in this folder.
2. Get an Anthropic API key (see below) and add it to `backend/.env`.
3. Install frontend deps:
   ```
   cd github_ni-ai-fx-otc-settlements
   npm install
   cd ..
   ```

### Getting an Anthropic API key

1. Go to https://console.anthropic.com (separate from your Claude chat subscription)
2. Sign in, add a payment method, set a spend cap of ~$10 for safety
3. API Keys → Create Key → name it "allege-prototype" → copy the key (starts with `sk-ant-...`)
4. Create `backend/.env` from the template:
   - **macOS/Linux:**
     ```
     cp backend/.env.example backend/.env
     open -e backend/.env
     ```
   - **Windows:**
     ```
     copy backend\.env.example backend\.env
     notepad backend\.env
     ```
5. Paste your key into the `ANTHROPIC_API_KEY=` line. Save.

> **Never commit `.env`.** It's already in `.gitignore`.

### Running the demo

**macOS/Linux:**
```
./run.sh
```

**Windows:**
```
run.bat
```

This will:
1. Create a Python virtualenv in `backend/.venv` and install backend deps (first run only, ~2 min)
2. Start the backend on http://127.0.0.1:8000
3. Start the frontend on http://localhost:8080

Open http://localhost:8080 in your browser. Log in as **Gopi** (Settlement Analyst).

---

## Architecture at a glance

```
┌─────────────────────────────────────────────┐
│  React frontend (Lovable) — localhost:8080  │
│  (Dashboard, AllegeDetail, Admin, Audit)    │
└────────────────┬────────────────────────────┘
                 │ Vite proxies /api → :8000
┌────────────────▼────────────────────────────┐
│  FastAPI backend — localhost:8000           │
│  /api/alleges, /process, /actions, /admin   │
└────────────────┬────────────────────────────┘
                 │
     ┌───────────┼────────────────┐
     ▼           ▼                ▼
 .eml files   3 mock CSVs     SQLite
 (inbox/)    (BO / MO / FO)  (audit + cases)
                 │
                 ▼
            Anthropic Claude
          (classification + field extraction)
```

Details in [`DESIGN.md`](./DESIGN.md). Business requirements in [`BRD.md`](./BRD.md). Internal build status in [`PROGRESS.md`](./PROGRESS.md).

### Behaviour notes (keep docs in sync)

When you change **extractor**, **counterparty resolution**, or **pipeline** copy, update `DESIGN.md` / `BRD.md` and bump `PROGRESS.md`. After backend logic changes, use **Admin → LLM & Demo → Reset** (then **Process**) so SQLite cases and `aiSuggestedAction` reflect the new rules — existing rows are not auto-migrated.

---

## Demo script for the MD

**Total runtime: ~5 minutes.**

### 0. Before they arrive
- Start the app (`./run.sh` / `run.bat`).
- Log in as Gopi. Go to **Admin → LLM & Demo** and click **Reset** so the demo starts clean.
- Click **Process** to run the pipeline on the 14 seeded emails.
- Go back to **Dashboard**.

### 1. Open the dashboard (30 sec)
- "Each row is an email our tool processed this morning."
- Point out mix of `Open`, risk levels, counterparties, AI confidence, aging.
- Note: 14 emails in the inbox. 9 turned into alleges, 5 were correctly filtered out as non-allege (invoice, OOO, newsletter, KYC, bounce). Show that ratio via the Audit Trail page filter if asked.

### 2. Drill into a straight-match allege (60 sec) — e.g. Goldman
- Show the side-by-side comparison.
- Show AI classification + confidence bar.
- In **AI Analysis**, review the **Counterparty reply draft** (when the backend has run) — same section as suggested action; then **Send** if appropriate.
- Click **Edit Draft**, tweak a word, click **Send**. Toast confirms; badge shows "SENT".
- Open `backend/data/sent/` in Finder/Explorer — the `.eml` is there.

### 3. Drill into a no-match allege (45 sec) — e.g. Barclays CDS
- The right-hand panel shows "No matching trade found in booking system" with the red box.
- Auto-draft uses the **no-match template** asking for more info.
- "This is what would have taken Gopi 15 minutes of searching BO/MO/FO manually."

### 4. Drill into the multi-match allege (45 sec) — e.g. Citi USD/JPY
- Shows multiple candidates.
- Auto-draft uses the **multi-match template** asking for a trade ref to disambiguate.

### 5. Thread-resolved case (60 sec) — `05_thread_resolved.eml`
- Filter audit trail to this message. Show the classifier's reasoning: "Latest reply indicates resolution — not an allege."
- "The tool reads the latest reply only, so once a counterparty retracts, we don't waste analyst time."

### 6. Broker case (60 sec) — TP ICAP email
- Show how the tool flagged the broker domain and did not auto-assume the counterparty.
- The draft explicitly asks the broker to confirm whom they're acting on behalf of.

### 7. Admin panel (60 sec)
- Show **LLM & Demo** tab: LLM toggle, extended thinking, API key status, reset button.
- Show the **Audit Trail** page — every tool action and every human action timestamped.

### Key MD-level talking points
- **Human-in-the-loop by design.** The tool drafts; the analyst sends. Nothing auto-sends.
- **Full audit trail.** Every decision traceable. Required for regulatory defence.
- **Configurable.** LLM can be turned off; system falls back to deterministic rules.
- **Scalable.** Same pattern handles Arati's Confirmations workflow and other products.
- **Cost.** ~$0.001 per email with Sonnet. 10K emails/month = ~$10/month in LLM costs. Negligible.

---

## Windows support

Windows launchers are already shipped:
- `run.bat` (top-level) — starts backend + frontend in two terminal windows
- `backend/run.bat` — starts backend only

**Whenever you change `run.sh`, update `run.bat` to match.** Same for `backend/run.sh` ↔ `backend/run.bat`. The two are kept behaviour-identical on purpose so a Windows demo runs identically to the Mac one.

---

## File map

```
Allege Prototype/
├── DESIGN.md                         ← business logic, scope, rules, future work
├── BRD.md                            ← business requirements document
├── PROGRESS.md                       ← build progress tracker (internal)
├── README.md                         ← this file
├── run.sh  / run.bat                 ← starts both services
├── backend/
│   ├── run.sh / run.bat              ← backend only
│   ├── requirements.txt, .env.example
│   ├── app/
│   │   ├── main.py                   ← FastAPI app
│   │   ├── config.py                 ← env + mutable settings
│   │   ├── models.py                 ← Pydantic request/response
│   │   ├── routes/                   ← alleges, process, actions, admin, audit
│   │   ├── services/                 ← email_parser, classifier, extractor,
│   │   │                               counterparty, matcher, drafter,
│   │   │                               cases, audit, llm, pipeline
│   │   └── db/                       ← SQLite files (generated)
│   ├── data/
│   │   ├── inbox/                    ← drop .eml files to process
│   │   ├── reference/                ← 3 mock system CSVs
│   │   └── sent/                     ← approved drafts land here
│   └── samples/
│       ├── inbox_seed/               ← 14 seed .eml files (reset target)
│       └── seed_audit.json
└── github_ni-ai-fx-otc-settlements/  ← existing Lovable React frontend
    └── src/
        ├── lib/api.ts                ← API client
        ├── contexts/AllegeContext.tsx ← loads from API (or falls back to mock)
        ├── components/allege-actions/
        │   └── EscalateFrontOfficeModal.tsx  ← FO escalation; pre-filled To: frontoffice-otc@abc.com
        └── pages/
            ├── Admin.tsx             ← added LLM & Demo tab
            └── AllegeDetail.tsx      ← AI Analysis embeds counterparty reply draft (backend); mismatch key normalisation
```

---

## Troubleshooting

- **Frontend loads but shows "Backend not reachable" banner in Admin:** backend didn't start. Check the terminal window running `backend/run.sh` for errors. Most common: missing Python 3.11, port 8000 already in use.
- **LLM off by default / rules fallback:** if `ANTHROPIC_API_KEY` is missing or the key is invalid, the pipeline silently falls back to rule-based classification. Check Admin → LLM & Demo → API Key Status indicator.
- **Port conflict on 8080 or 8000:** stop whatever else is using them, or edit `vite.config.ts` and `backend/.env`.
- **Stale cases showing after code changes:** go to Admin → LLM & Demo → **Reset**.

---

## What's NOT in this prototype (on purpose)

See [`DESIGN.md` §7 "Open points / Future Enhancements"](./DESIGN.md). High level:
- No real email ingestion (folder-drop only)
- No real email send (writes to `sent/`)
- Rules-only fallback if LLM is off (not as smart as LLM)
- Arati's Confirmations workflow is mock only
- No live thread watching — once a case is flagged, a later "please ignore" doesn't reclassify
- BO/MO/FO are CSV mocks, not real Murex/DTCC/MarkitWire feeds
