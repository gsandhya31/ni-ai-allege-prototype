# Business Requirements Document — Allege Automation

**Version:** 0.1 (prototype)
**Owner:** Sandhya (NI-AI programme)
**Date:** 16-Apr-2026
**Status:** Prototype complete; ready for MD review before production build

---

## 1. Executive summary

Nomura's OTC Settlement Analysts receive 50-200 allege emails per business day from counterparties claiming trades that aren't matched in Nomura's books. Each allege requires the analyst to (a) classify the email, (b) locate the trade across Back Office, Middle Office, and Front Office systems, (c) draft a reply, and (d) send. This process takes 10-20 minutes per email, is error-prone, and doesn't scale.

This prototype demonstrates that 80-90% of the manual work can be automated by a deterministic Python pipeline augmented with an LLM (Claude Sonnet 4.6). The pipeline reads inbound emails, classifies them, extracts trade details, runs exact-match lookups across mock BO/MO/FO CSVs, and generates a reply using one of four templates. The analyst remains in the loop — they approve and send — and every decision is captured in an append-only audit log.

The prototype is local-only and uses folder-based email I/O, mock CSV systems, and a draft-to-folder "send." All of these have clear production counterparts (shared mailbox, real system integrations, SMTP).

---

## 2. Problem statement

### Current state
- Analysts manually read each allege email, judge whether it's a real allege, then log into three separate systems sequentially to search for the trade.
- Reply emails are hand-drafted, inconsistent in tone and completeness.
- Audit trail is fragmented across mailbox, system logs, and personal notes.
- Volume grows with business; headcount does not.
- No institutional memory — when an analyst leaves, their judgement on edge cases (brokers, entity mismatches, thread dynamics) leaves with them.

### Pain points
- **Time:** 10-20 min/email * 100 emails/day = ~20-30 analyst-hours/day burned on a mechanical process.
- **Risk:** misclassification and missed alleges lead to settlement failures, regulatory exposure, and counterparty relationship damage.
- **Compliance:** current audit trail is insufficient for detailed regulator queries ("why did you reply X on Y date?").
- **Scalability:** the workflow does not extend to other products (equity swaps, repo, securities lending).

---

## 3. Solution overview

A deterministic Python pipeline with targeted LLM use, fronted by a web UI that the analyst works inside.

### Pipeline stages (per email)
1. **Parse** — open `.eml`, extract sender, subject, body, strip quoted history to get latest reply.
2. **Classify** — LLM call on latest reply decides allege / not-allege, with confidence score and reasoning.
3. **Extract** — regex pulls trade date, value date, notional, rate, currency, counterparty ref, labelled counterparty line, etc. LLM fills any missing fields in one call, without overwriting successful regex captures (especially `counterparty_stated`).
4. **Counterparty resolution** — if counterparty is **explicitly stated** in the body (e.g. a `Counterparty:` line, including templates with extra spaces after the colon), use it and treat the source as **stated** (not inferred). Otherwise infer from sender domain where mapped; if the sender is a known inter-dealer broker and no stated counterparty was extracted, mark as **broker-unknown** and require analyst verification. Unknown domains fall back to sender display name with low confidence.
5. **Match** — exact comparison on product-appropriate key fields against BO → MO → FO CSVs. First-hit wins. Returns single-match, multi-match, or no-match.
6. **Draft** — Jinja2 template renders a reply based on outcome (match / no-match / multi-match / counterparty-inferred).
7. **Persist** — case row in SQLite, audit entries throughout.

### Analyst workflow in UI
- Dashboard lists cases assigned to the analyst (plus unassigned).
- Detail view shows side-by-side counterparty vs internal record, auto-drafted reply, and an AI-suggested action.
- Analyst can edit the draft, approve it, or override with manual action.
- On approval, draft is saved to `sent/` folder (production: sent via SMTP) and the action is audited.

### Admin controls
- Toggle LLM on/off (fall back to rules only).
- Toggle extended thinking for harder cases.
- Reset demo to a known-good state (dev/test only).

---

## 4. Business rules (prototype-level)

### Allege classification
- Decision based on **latest reply** in an email thread only. Earlier messages are ignored.
- Resolution indicators in latest reply ("we found the trade", "please ignore", "confirmed") classify the email as not-allege even if the thread started as an allege.
- Invoices, newsletters, OOO replies, KYC requests, SSI change notices, and delivery bounces are classified as not-allege.
- Low-confidence classifications (<0.6) still run the full pipeline but are flagged on the dashboard as "Low-confidence — please verify." Analyst must confirm or reject before the draft is marked ready-to-send.

### Counterparty resolution
- Explicit counterparty in body (labelled line such as `Counterparty: <legal name>`, or captured “on behalf of” text) → use it; pipeline marks source as **stated**. LLM fill-in must not overwrite a successful regex capture of the stated counterparty with `null`.
- Missing; sender domain is a known counterparty domain → infer (e.g. `@jpmorgan.com` → "JPMorgan Chase"), flag on UI / suggested-action copy as **domain-inferred** (wording distinct from broker and header-fallback cases).
- Missing; sender domain is a known inter-dealer broker (TP ICAP, Tullett Prebon, ICAP, BGC Partners, Tradition, GFI, Marex Spectron) → do not assume sender is counterparty. Flag as **broker-unknown** until the analyst confirms the legal counterparty from the email body or follow-up.
- Missing; unknown domain → use sender's name as fallback with explicit **sender-name-fallback** / low-confidence handling.

### Analyst UI (resolution)
- **Escalate to Front Office** modal pre-fills the escalation **To** field with `frontoffice-otc@abc.com` (configurable placeholder for the demo). Analyst confirms or edits before logging the action.

### Matching
- Exact match only. No fuzzy logic in this prototype.
- Lookup order: **BO → MO → FO**. Stop at first system with at least one hit.
- Multi-match in one system returns all candidates; draft asks counterparty for a disambiguating field.
- Key fields are product-dependent (see DESIGN §4).

### Email templates (four)
1. **Match** — "Trade found in [BO/MO/FO], please confirm details."
2. **No match** — "Trade not found in any system (BO, MO, FO), please provide additional details."
3. **Multi match** — "Multiple matches found in [system], need your trade ref to disambiguate."
4. **Counterparty inferred** — "We have assumed counterparty is [X] based on [source]. Trade [match outcome]. Please confirm."

### Audit
- Append-only. Every tool action and every human action gets a timestamped row.
- Seed entries preserved across demo resets; live entries wiped.
- Required fields: timestamp, actor, actor type (human / tool), allege ID, action, details, AI-recommended action (when applicable), whether human followed AI recommendation.

---

## 5. Non-functional requirements

| Area | Prototype | Production target |
|---|---|---|
| Latency per email | 2-5 s (LLM on), <0.5 s (LLM off) | Same |
| Throughput | ~10 emails/min on a laptop | 1 email/s (parallelised) |
| Availability | Local only | 99.9%, HA deploy |
| Data residency | Local Mac | Nomura-approved on-prem or private cloud |
| Security | `.env` for secrets, no real data | Vault-backed secrets, encrypted at rest |
| Audit retention | SQLite file | 7-year retention in enterprise audit store |
| PII | Mock data only | Real trade data — data classification and access controls required |

---

## 6. Future enhancements (not in this prototype)

See DESIGN.md §7. Headline items:
- Real mailbox ingestion (IMAP / Outlook add-in / shared-mailbox webhook)
- Real SMTP send with bounce handling
- Outbound chase workflow (Nomura initiates)
- Fuzzy match fallback
- Agent-style reasoning layer for low-confidence or ambiguous cases only
- Arati's Confirmations workflow
- BO/MO/FO integration with Murex / DTCC / MarkitWire
- Attachment-based alleges (PDF / Excel)
- Case ID scheme aligned to Nomura mailbox conventions
- Multi-analyst queue, SLA and escalation rules
- Analyst feedback loop to improve classifier accuracy

---

## 7. Success criteria for production

1. **Accuracy:** ≥ 95% correct classification on a held-out test set of 1,000 real Nomura emails.
2. **Field extraction:** ≥ 90% recall on mandatory fields (trade date, counterparty, notional, currency).
3. **Matching:** ≥ 99% exact-match correctness when the trade exists in BO/MO/FO.
4. **Throughput:** 1 email processed per second sustained; daily peak of 500 emails with latency <10 s end-to-end.
5. **Audit completeness:** 100% of tool and human actions logged; pass internal audit review.
6. **Analyst adoption:** ≥ 80% of alleges handled through the tool within 3 months of launch.
7. **Analyst time saved:** ≥ 60% reduction in time-per-allege vs baseline.

---

## 8. Risks & mitigations

| Risk | Mitigation |
|---|---|
| LLM misclassifies an allege as non-allege | Low-confidence flag; nothing silently skipped; analyst can always see the pipeline's verdict |
| Exact match misses a match due to formatting differences | Regex normalises common variants; production adds fuzzy fallback |
| Analyst blindly approves drafts | Every approve action audited; manager review dashboard for sampling |
| LLM provider outage | Rules fallback; demo mode switch in Admin |
| API key leakage | Keys in `.env` never committed; production uses secrets manager |
| Counterparty inference wrong (broker vs CP) | Broker domain allow-list; all inferred counterparties flagged on UI |
| Data residency / regulatory | Private deployment; Anthropic offers EU and compliant endpoints |

---

## 9. Approvals required

- MD — Settlement Operations (sponsor)
- Head of Technology — NI-AI
- Head of Compliance (for audit design sign-off)
- Head of Information Security (for secrets handling, data classification)
- Vendor management (Anthropic commercial terms for production)
