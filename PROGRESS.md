# Build Progress Tracker

## Status: ✅ Prototype complete and smoke-tested

All phases done. The prototype is ready to run on your Mac / Windows laptop. See `README.md` for setup + demo walkthrough.

## Phase 1 — Scaffolding ✅
Backend folder structure, requirements.txt, .env.example, run.sh (Mac) and run.bat (Windows), DESIGN.md, PROGRESS.md.

## Phase 2 — Mock Data ✅
BO system CSV (20 rows), MO system CSV (10 rows), FO system CSV (7 rows). 14 seed .eml files (9 allege + 5 non-allege). seed_audit.json.

## Phase 3 — Core Services ✅
config, services/audit, services/llm, services/email_parser, services/classifier, services/extractor, services/counterparty, services/matcher, services/drafter, services/cases, services/pipeline.

## Phase 4 — API ✅
app/main.py (FastAPI + CORS + lifespan), app/models.py (Pydantic), routes/alleges, routes/process, routes/actions, routes/admin, routes/audit. 16 endpoints total.

## Phase 5 — Frontend Wiring ✅
src/lib/api.ts (fetch helpers), AllegeContext loads from API with mock fallback, Admin page "LLM & Demo" tab added (toggles + reset), AllegeDetail "Auto-Drafted Reply" card added, Vite proxy /api → :8000. Gopi-only dashboard filter.

## Phase 6 — Docs & Demo ✅
README.md (setup + MD demo script), BRD.md (business requirements), DESIGN.md (updated), .gitignore (backend + frontend), run.bat for Windows.

## Smoke tests passed
- Pipeline processes all 14 emails end-to-end (rules-only mode verified; LLM mode requires API key on laptop).
- 9 alleges / 5 non-alleges split correct.
- All 4 draft templates render cleanly.
- FastAPI app imports with 16 routes registered.
- End-to-end TestClient run: health, process, list, detail, settings, send, audit — all pass.

## To run it on your laptop
1. Install Python 3.11 + Node 18+ (see README).
2. Put your Anthropic API key in backend/.env.
3. `cd github_ni-ai-fx-otc-settlements && npm install && cd ..`
4. `./run.sh` (Mac) or `run.bat` (Windows).
5. Open http://localhost:8080, log in as Gopi.
6. In the app: Admin → LLM & Demo → Process button to run the pipeline on the seeded inbox.

## Iteration — Apr 2026 (post-MD polish)

Documentation and behaviour tightened for analyst trust and demo accuracy:

- **Allege detail — mismatch highlighting:** normalise backend `mismatchFields` keys (`snake_case` ↔ camelCase) so fields such as `settlement_method` still get red row styling alongside the amber banner (`AllegeDetail.tsx`).
- **Human-in-the-loop copy:** user-facing strings use imperative **“Escalate to …”** where appropriate (vs past-tense “Escalated”) in mock UI data and audit samples.
- **Front Office escalation modal:** **To** pre-filled with `frontoffice-otc@abc.com` (`EscalateFrontOfficeModal.tsx`).
- **Extractor:** robust `Counterparty:` line capture (multiline, spaces after colon); **LLM merge** no longer overwrites a populated `counterparty_stated` with null (`extractor.py`).
- **Pipeline suggested action:** distinct no-match analyst text for **domain-inferred**, **broker-unknown**, and **sender-name-fallback** (`pipeline.py`).
- **Docs:** `DESIGN.md`, `BRD.md`, `README.md` updated to match the above.

**Note:** Cases already persisted in SQLite before an extractor/pipeline change keep their stored `aiSuggestedAction` until **Admin → Reset → Process** (or re-ingest) rebuilds payloads.
