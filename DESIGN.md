# Allege Automation — Design Document

Working prototype for Nomura OTC Allege reconciliation workflow.

---

## 1. Business Context

An **allege** is a claim raised by a counterparty that a trade exists (settled, confirmed, or in progress) which they cannot find or cannot match in their records vs. Nomura's. Each business day, analysts in Nomura's back office (example: Gopi, Settlement Analyst) receive dozens of allege emails and must:

1. Read the email and decide: is this an allege?
2. Extract trade details from the email body
3. Search internal systems (Back Office → Middle Office → Front Office) for a matching trade
4. Present findings (match, no-match, multi-match) to the analyst
5. Draft a reply email using a pre-defined template
6. Analyst reviews, edits if needed, and sends

This prototype automates steps 1-5, leaving final review and send to the human analyst.

### Who initiates the allege email?
The common pattern is **counterparty-initiated**: the counterparty has booked a trade, attempted to match via CLS / DTCC / MarkitWire / SWIFT, and cannot find Nomura's side. They email Nomura alleging that the trade is missing / unbooked / mismatched. All 9 allege sample emails in this prototype model this inbound direction.

Less commonly, Nomura chases a counterparty proactively before value date when a confirmation is missing. The counterparty's reply ("we don't have this trade") is itself then treated as an allege on the Nomura side. This outbound-chase workflow is **out of scope** for the prototype and will land once the tool is connected to Nomura's outbound mailbox (see Section 7).

---

## 2. Scope

### In scope for the demo
- Read `.eml` files from a local `inbox/` folder (no Gmail / Outlook integration)
- Classify each email as allege / non-allege using LLM (with rule-based fallback)
- Extract trade fields from email body using regex-first, LLM-fallback
- Resolve counterparty (stated, inferred from sender domain, or from signature)
- Detect broker-originated emails and handle counterparty differently
- Match against three mock CSV systems (BO, MO, FO) using exact match on key fields
- Stop at first-hit in the BO → MO → FO sequence
- Draft reply email from templated text (match, no-match, multi-match, counterparty-inferred)
- Save approved drafts to `sent/` folder (no real SMTP send)
- Full audit log of every tool action and every human action
- Admin panel: toggle LLM on/off, toggle Extended Thinking, reset demo
- Role-based UI: Gopi (Settlement Analyst) sees settlement alleges only

### Explicitly out of scope (future phases)
- Real email ingestion from shared mailbox or IMAP
- Real email sending via SMTP
- Live thread awareness: if a counterparty replies and resolves the issue while the tool is mid-processing the earlier email, the tool does not currently re-evaluate. Latest-reply logic applies only at the moment of processing.
- Fuzzy matching as fallback when exact match fails
- Arati's Confirmations workflow (separate product)
- Multi-analyst routing, queue management, SLAs
- Integration with real BO/MO/FO systems (Murex, etc.)
- ML-based counterparty disambiguation
- ML-based email classification trained on Nomura's own history

---

## 3. Architecture

### Tech stack
- **Frontend:** React 18 + TypeScript + Vite + Tailwind + shadcn/ui + React Router + TanStack Query (existing Lovable-generated app, lightly modified)
- **Backend:** Python 3.11 + FastAPI + Pydantic + SQLite + Jinja2
- **LLM:** Anthropic Claude Sonnet 4.6 via official `anthropic` SDK (model string: `claude-sonnet-4-5` — update when 4.6 GA)
- **Email parsing:** Python stdlib `email` module
- **Matching:** pandas (exact-match on product-appropriate key fields)
- **Runtime:** Both services run locally (Mac and Windows supported) — frontend `:8080`, backend `:8000`

### Architectural note: pipeline vs agent
The prototype is a **deterministic pipeline**, NOT an agent. Python code orchestrates the flow (parse → classify → extract → resolve counterparty → match → draft → persist). The LLM is called in two specific steps only:

1. **Classifier** — one JSON call returning `{is_allege, confidence, reasoning}` for the latest reply.
2. **Extractor** — one JSON call to fill in trade fields that regex did not find.

A true agent would hand Claude tools (search_bo, search_mo, search_fo, draft_reply, etc.) and let it decide the order of operations autonomously. That is more flexible but also more expensive, slower, and less predictable — wrong trade-offs for a high-volume operations pipeline.

**Future enhancement:** add an agent-style reasoning layer that activates only on ambiguous cases (low-confidence classification, counterparty cannot be resolved, matching returned unexpected patterns). The agent would be given tools, examine the case, and produce a structured recommendation for the analyst. The happy-path pipeline stays deterministic.

### Flow diagram (per email)

```
.eml in inbox/
     │
     ▼
[email_parser]   ── strip quoted history, get latest reply, sender, subject
     │
     ▼
[classifier]     ── LLM or rules → is_allege? (+ reasoning)
     │
     ├── not_allege ──► [audit] ──► stop
     │
     ▼ (is_allege)
[extractor]      ── regex first; LLM for any missing fields
     │
     ▼
[counterparty]   ── stated in extract? ──► use it
                   broker domain & no stated? ──► broker-unknown (analyst verify)
                   else known CP domain? ──► domain-inferred
                   else ──► sender-name fallback
     │
     ▼
[matcher]        ── exact match: BO → MO → FO; first-hit wins
     │
     ▼
[allege_record]  ── build record matching UI's AllegeRecord schema
     │
     ▼
[drafter]        ── render Jinja template (match / no-match / multi-match / inferred-cp)
     │
     ▼
[persist]        ── SQLite case row; audit log entries throughout
     │
     ▼
UI → analyst reviews → approves → draft saved to sent/
```

---

## 4. Business Logic — Rules & Assumptions

### Classification rules
- Classification is applied to the **latest reply** in the email thread only. If an earlier message in the thread was an allege but the latest reply indicates resolution ("we found the trade," "please ignore," "confirmed on our side"), the email is classified as **not allege**.
- If LLM is OFF (admin toggle), classification falls back to keyword rules: presence of "allege", "alleged trade", "unmatched", "cannot find", "please confirm", "discrepancy", "break", "SSI missing", "not booked", "value today," etc.
- The classifier emits a confidence score. The pipeline **still runs end-to-end** regardless of the score (to save analyst clicks and surface a draft either way), but cases with confidence under 0.6 are flagged on the dashboard as **"Low-confidence classification — please verify"** and the analyst must confirm or reject the allege classification before the draft can be marked ready-to-send. Nothing is silently skipped.

### Field extraction rules
- Regex attempts to pull: trade date, value date, counterparty trade ref, notional, currency, currency pair, rate, direction (buy/sell), settlement method, BIC, product type.
- **Counterparty (stated):** a dedicated multiline regex recognises a labelled line such as `Counterparty:             Deutsche Bank AG` (extra spaces after the colon are common in bank templates). If that capture succeeds, it is treated as authoritative for counterparty resolution. A separate fallback regex still looks for “Sent on behalf of …” / “Acting on behalf of …” when the labelled line is absent.
- Any field that regex cannot find is passed to the LLM (single call per email — all missing fields at once, to minimise API cost). **Important:** the LLM merge step must **not** overwrite a non-empty regex `counterparty_stated` with `null` or a guess — stated-in-body always wins over inference.
- If LLM is OFF and regex cannot find a field, the field stays null and the allege is flagged `partial_extraction=true`.

### Counterparty resolution rules
1. **Stated in body** — explicit `Counterparty:` (or `Counter party:`) line, or “on behalf of” phrasing captured by regex / LLM → use it (`counterparty_source="stated"` in the pipeline payload). This takes priority over sender domain.
2. **Missing from body, sender domain is a known counterparty domain** → derive counterparty from domain (e.g. `@jpmorgan.com` → "JPMorgan Chase"). Flag as `counterparty_source="domain-inferred"`.
3. **Missing from body, sender domain is an inter-dealer broker** → do **not** treat sender as counterparty. If the extractor (regex or LLM) still cannot produce a stated counterparty, flag as `counterparty_source="broker-unknown"` and use counterparty-inferred / analyst-verify flows.
4. **Missing from body, unknown domain** → fallback to sender display name with low confidence (`counterparty_source="sender-name-fallback"`).
5. When `counterparty_source` is anything other than "stated", the matcher runs **two passes**: once with the inferred counterparty, once without (against all 5 non-counterparty key fields). Both result sets are shown to the analyst so they can judge.

**AI suggested action (no-match):** the pipeline text shown in the UI distinguishes **domain-inferred**, **broker-unknown**, and **sender-name-fallback** so analysts are not told “inferred from sender domain” when the issue is actually broker-origin or ambiguous headers.

### Broker domain list
Hardcoded list, expandable from Admin panel later. Initial entries:
- `tpicap.com`, `tullettprebon.com`, `icap.com`, `bgcpartners.com`, `tradition.com`, `marexspectron.com`, `gfigroup.com`

### Matching rules
- **Exact match** on all selected key fields. No fuzzy.
- Key field set depends on product type:
  - **FX Spot / Forward / NDF:** `tradeDate, counterparty, nomuraEntity, currencyPair, notional, rate, direction, valueDate`
  - **FX Swap:** `tradeDate, counterparty, nomuraEntity, currencyPair, notional, rate, direction, valueDate` (near leg only)
  - **IRS:** `tradeDate, counterparty, nomuraEntity, notional, currency, rate (fixed leg), direction, valueDate`
  - **CDS:** `tradeDate, counterparty, nomuraEntity, notional, currency, direction, valueDate`
  - **Cross Currency Swap:** `tradeDate, counterparty, nomuraEntity, notional, currency, rate, direction, valueDate`
- **Lookup order:** Back Office → Middle Office → Front Office. **Stop at first hit.**
- If multi-match within a single system (more than one row matches), return all candidates and use multi-match email template.
- UI flags explicitly: "BO checked ✓, MO not checked, FO not checked" when first hit is in BO.

### Draft email templates
Four templates, rendered with Jinja2:
1. **match** — "Trade found in <system>, please confirm details"
2. **no_match** — "Trade not found in any system (BO, MO, FO), please provide additional details"
3. **multi_match** — "Multiple matches found in <system>, need more info to disambiguate"
4. **counterparty_inferred** — "We have assumed counterparty is <X> based on <source>. Trade <found/not found>. Please confirm counterparty and details."

### Audit rules
- Every step of the pipeline produces an audit entry: parser start/end, classifier decision + reasoning, extractor fields found/missing, counterparty resolution path, matcher system-by-system result, drafter template chosen.
- Every human action produces an audit entry: allege viewed, draft edited, draft approved/rejected, send clicked, resolve clicked, admin toggle flipped.
- Audit log is append-only. Reset button preserves seed audit entries (labeled `seed=true`) and wipes live entries only.

---

## 4a. UI rules for displaying match outcomes

The dashboard and the allege detail page must make match outcomes **visually unmistakable**. This is a key MD requirement.

### Dashboard table ("Match Status" column)
- **NOT FOUND** (red badge) — when `nomuraDetails === null`. The trade is not in BO, MO, or FO.
- **MISMATCH (n)** (amber badge) — when a match exists but one or more fields disagree. Count shown.
- **MATCH** (green badge) — clean match, all fields agree.

### Allege detail page — top banner
One of three banners is always visible above the side-by-side cards:
- **Red banner (not found):** "Trade not found in any system (BO, MO, FO)." Plus explanation.
- **Amber banner (mismatch):** "Match found, but N field(s) do not agree" followed by pill badges listing each mismatched field by name.
- **Green banner (clean match):** "Clean match — all fields agree."

### Side-by-side comparison cards
Every field that can appear in `mismatchFields` is rendered in both cards with a MISMATCH badge when it differs. Fields covered:
- From `counterpartyDetails` / `nomuraDetails`: ref, amount, rate, settlementMethod, bic, valueDate
- From the top-level allege record: productType, direction, nomuraEntity

**Key normalisation:** the backend may emit mismatch field names in `snake_case` (e.g. `settlement_method`). The detail view normalises these to the same camelCase keys used by the side-by-side rows (`settlementMethod`, etc.) so highlighting and badges stay consistent with the amber banner.

When `nomuraDetails` is null, the right-hand card shows a large red "Not found in BO, MO, or FO" panel rather than an empty card.

**Resolution actions — Front Office escalation:** the “Escalate to Front Office” modal pre-fills the **To** address with `frontoffice-otc@abc.com` (demo placeholder); the analyst can edit before confirming. Nothing is sent automatically.

## 5. Role-Based Access (for the demo)

| User | Role | Can see |
|------|------|---------|
| Gopi | Settlement Analyst | Allege dashboard (Gopi's queue), AllegeDetail, TradeComparison, AgentLog, AuditTrail, Reports, Feedback |
| Arati | Confirmations Analyst | Confirmations pages only (mock; NOT wired to backend) |
| Harris | Manager | All read-only + Reports |
| Sandhya G | Admin | Admin panel + everything else |

The existing frontend has a `toolMatrix` controlling which role sees which tool. We preserve it. For the demo we log in as **Gopi**. If you log in as anyone else you'll see their mock UI unchanged.

Gopi's dashboard shows only alleges where `assignedTo === "Gopi"` or `assignedTo === null` (unassigned queue for Settlement). Arati-assigned alleges are hidden.

**Name normalization note:** The mock-data field `assignedTo` uses the first-name convention matching the login name (e.g. `"Gopi"`, `"Arati"`). Historical mock data used `"Arti"` by mistake — this has been fixed. Any new mock data or backend-generated payloads must use the full first name as defined in `DEMO_ACCOUNTS` (see `AuthContext.tsx`).

---

## 6. Data Shapes (matches existing frontend types)

See `/src/data/mockAlleges.ts` in the frontend. Backend Pydantic models mirror `AllegeRecord`, `CounterpartyDetails`, `NomuraDetails`, `AuditEntry` exactly so we can drop real data into the UI with zero refactor.

Key point: the UI's `aiSuggestedAction` and `aiConfidence` fields are populated by the backend (LLM). `mismatchFields` is populated by the matcher based on diffs between counterparty-provided values and matched internal record.

---

## 7. Open points / Future Enhancements

1. **Live thread updates** — if counterparty replies after the tool flagged an email, auto-reclassify. Requires a watcher on the inbox folder + delta handling on existing cases.
2. **Real mailbox ingestion** — shared mailbox / IMAP / Outlook add-in
3. **Real SMTP send** — with audit trail, read receipts, bounce handling
4. **Outbound-chase workflow** — Nomura proactively chasing counterparties before value date; treat inbound replies as potential alleges
5. **Fuzzy match as fallback** — when exact match returns zero, try fuzzy on numeric fields (qty ±1%, rate ±3bps, date ±1 day)
6. **Arati's Confirmations workflow** wired to backend
7. **Broker list management from Admin UI**
8. **ML-trained classifier on Nomura's historical emails**
9. **Multi-analyst queue and SLA management**
10. **BO/MO/FO integration with real systems (Murex, etc.) — replacing CSV mocks**
11. **Handling of attachment-based alleges (trade terms as PDF / Excel)**
12. **Case ID generation from Nomura mailbox scheme** — prototype uses `msg<7-digit hash of filename+message-id>`. Production will derive IDs from Nomura's own mail gateway / message-ID conventions
13. **Agent-style reasoning layer for hard cases** — see Section 3 "pipeline vs agent." Activate only when pipeline produces ambiguous or low-confidence results.
14. **Outbound template library management** — templates stored in code today, should be in a config table editable by ops managers
15. **Role permissions and data segregation beyond Gopi/Arati** — full RBAC matrix, asset-servicing analyst view, custom role creation

---

## 8. Sample Email Inventory

The prototype ships with 14 sample `.eml` files covering the realistic mix of inbound email Nomura would receive on any given day.

**10 allege scenarios** (all covered by the tool):
| # | File | Scenario |
|---|---|---|
| 01 | `01_straight_match_goldman.eml` | Clean match — all fields correct |
| 02 | `02_rate_mismatch_db.eml` | Rate + value-date mismatch → no match (key field differs) |
| 03 | `03_no_match_barclays.eml` | CDS not in any system |
| 04 | `04_multi_match_citi.eml` | Duplicate rows in MO → multi-match |
| 05 | `05_thread_resolved.eml` | Initial allege later resolved → classified not-allege |
| 06 | `06_counterparty_missing.eml` | CP missing, inferred from sender domain |
| 07 | `07_broker_sender_tpicap.eml` | Broker-originated; analyst must verify CP (LLM may fill stated CP from body when clearly present) |
| 08 | `09_entity_mismatch_hsbc.eml` | Entity discrepancy flagged |
| 09 | `15_match_with_mismatch_ubs.eml` | **Match found but settlement_method disagrees** — shows UI mismatch highlighting |
| 10 | (reserved for future) | — |

**5 non-allege scenarios** (tool correctly filters out):
| # | File | Scenario |
|---|---|---|
| 10 | `08_non_allege_noise.eml` | Vendor invoice |
| 11 | `10_non_allege_newsletter.eml` | Market commentary newsletter |
| 12 | `11_non_allege_ooo.eml` | Out-of-office auto-reply |
| 13 | `12_non_allege_kyc_request.eml` | KYC refresh — not a trade |
| 14 | `13_non_allege_bounce.eml` | Mail delivery failure bounce |
| 15 | `14_non_allege_ssi_update.eml` | Informational SSI change notice |

Each scenario is deterministically wired to the 3 mock reference CSVs in `backend/data/reference/` so that matching behaviour is predictable on stage.

## 8a. Maintainability notes

- **Windows launchers.** `run.bat` (top-level) and `backend/run.bat` ship alongside their `.sh` counterparts and must stay behaviour-identical. Any change to one should be mirrored in the other.
- **Broker domain list** lives in `backend/app/config.py::BROKER_DOMAINS` — expand here as Nomura's broker coverage grows.
- **Counterparty-domain map** in `backend/app/config.py::DOMAIN_TO_COUNTERPARTY` — keep in sync with KYC onboarding data.
- **Template changes** go into `backend/app/services/drafter.py`. Keep all four templates.
- **UI match-outcome display rules** are documented in §4a above and implemented in `AllegeDetail.tsx` (top banner + per-field highlighting) and `AllegeDashboard.tsx` ("Match Status" column).
- **Extractor / merge behaviour** is in `backend/app/services/extractor.py` (`regex_extract`, `llm_extract_missing`). **Counterparty resolution** is in `counterparty.py`; **no-match analyst copy** is assembled in `pipeline.py` (`_ai_suggested_action`).

## 9. Demo Safety

- API key is kept in `backend/.env` which is gitignored — never committed.
- If `ANTHROPIC_API_KEY` is missing or invalid, the LLM client falls back to rule-based / pre-canned responses so the demo never hard-fails on stage.
- The Admin panel has a "Use LLM" toggle. Default ON. Flip OFF to run the demo entirely on rules if there's any concern about API availability on the day.
- **Reset button** wipes live state, re-seeds the inbox, and **auto-processes** so the dashboard is populated immediately. Safe to press at any time.

### Key nuance: match vs match-with-mismatch vs no-match

- **Exact match on key fields is required for a match to be returned at all.** If the counterparty's stated rate, trade date, value date, notional, currency pair, direction, or counterparty name differs from any BO/MO/FO record → **no match** (no match returned, even if nearly all fields agree).
- **"Match found but N fields do not agree"** happens when the match succeeds on the key fields BUT non-key fields (e.g. settlement method, BIC, Nomura entity) differ between the email and the internal record. These cases are the most common real-world outcome.
- This distinction is demo-critical: the MD needs to see both "we looked and didn't find anything" and "we found it but flagged these discrepancies for you to confirm."
