# Project plan: Allege prototype → production

This document outlines a phased path from the current **file-drop + CSV reference** prototype to a **production-grade** allege triage service for Nomura OTC settlements, including **Nomura mailbox integration** and **internal system interfaces**. Treat timelines as order-of-magnitude; refine with capacity planning and architecture review.

---

## 1. Goals and success criteria

| Area | Prototype today | Production target |
|------|-----------------|---------------------|
| Ingestion | `.eml` files in `data/inbox` | Continuous ingestion from **Nomura-managed mailboxes** (see §3) |
| Identity | Hash-based demo case IDs | **Stable case IDs** tied to enterprise message / thread IDs |
| Booking truth | CSVs (BO / MO / FO) | **Authoritative APIs or feeds** from BO, MO, FO, and booking systems |
| Classification / extract | Latest body + optional LLM | Same logic, **governed LLM** (data residency, logging, redaction) |
| Outbound | Write to `sent/` folder | **Approved send** via enterprise SMTP / relay with audit |
| UI | Analyst workstation (browser) | Same + **SSO**, entitlements, optional Citrix/VDI constraints |
| Ops | Local SQLite | **HA persistence**, backups, monitoring, runbooks |

**Success:** measurable reduction in time-to-first-touch, fewer mis-routed alleges, full audit trail from message receipt through resolution, and safe handling of PII/market data under Nomura policy.

---

## 2. Guiding principles

1. **Human-in-the-loop** for settlement-impacting actions until policy allows automation.
2. **Deterministic core** (classify → extract → match → draft) remains testable; **LLM as augment**, not sole source of truth for booking keys.
3. **Integration by contracts**: versioned APIs/events from mailbox and booking platforms; avoid screen-scraping except as temporary bridge.
4. **Security by design**: secrets in vault, least-privilege service accounts, encryption in transit and at rest.

---

## 3. Nomura mailbox integration (major workstream)

### 3.1 Discovery (phase 0–1)

- **Which mailboxes** (shared ops / confirmations / product-specific) are in scope for v1?
- **Platform**: Microsoft 365 (Graph), on-prem Exchange EWS, or other — drives auth and sync model.
- **Policies**: retention, journaling, DLP, allowed use of content for model training (typically **no training** on production mail).
- **Threading rules**: how `Message-ID`, `In-Reply-To`, `References`, and conversation IDs map to a **case** in your model (align with §4 in `visual-overview.html`: “latest reply” classification must be defined against real thread boundaries).

### 3.2 Ingestion architecture

| Component | Responsibility |
|-----------|----------------|
| **Connector service** | Poll or subscribe (webhook / Graph delta) to inbox changes; normalize to internal message DTO |
| **Dedup / idempotency** | Stable id per message; replays must not duplicate cases |
| **Pipeline trigger** | Queue (e.g. Kafka / SQS / internal bus) → worker invokes existing **pipeline** steps |
| **Failure handling** | Dead-letter, retry with backoff, alert on stuck messages |

### 3.3 Identity and correlation

- Map **Nomura message / thread / conversation ID** → internal `case_id` (replace demo `msg#######` generation in `pipeline.py`).
- Optional: link to **CRM / case management** if Nomura uses one for breaks.

### 3.4 Outbound

- Replace prototype “save to `sent/`” with **authenticated SMTP** or **Graph send** using a **nominated sending identity** (shared mailbox or send-as).
- Enforce **pre-send review** in UI (already aligned with product); store **final body hash** and timestamp in audit.

### 3.5 Non-functional

- Rate limits, mailbox quota, attachment size limits, **malware scanning** on attachments before extract.
- **Redaction** pipeline for logs and third-party LLM if any field leaves the bank.

---

## 4. Internal system integration (beyond mailbox)

Prioritize by **dependency for “truth”** and **volume of alleges**. Order below is a typical priority stack; Nomura’s actual names and interfaces will replace placeholders.

| System / domain | Role in production | Integration notes |
|-----------------|---------------------|-------------------|
| **Murex (or primary trade repository)** | Canonical trade economics, refs, status | REST/SOAP/DB export per approved pattern; match keys must align with §matcher contract |
| **BO / MO / FO** | Booking layers as today | Replace CSV with **read APIs** or **nightly certified extracts**; keep **BO → MO → FO** order if still business rule |
| **SSI / static data** | Settlement instructions, BIC, agent | API or golden-source DB; needed for mismatch reasons |
| **DTCC / MarkitWire / SWIFT** | Channel metadata where alleges originate | Often indirect (data lands in Murex / confirmations); define whether pipeline reads from hub only |
| **Entitlements / LDAP or Entra ID** | Who sees which desk / entity | Front-end SSO + API **JWT** validation |
| **Audit / immutable log** | Regulatory and internal audit | Append-only store; correlate user id, case id, message id |
| **Ticketing (optional)** | Jira / ServiceNow for escalations | Webhook or API on “Escalate” actions |

**Deliverable per system:** interface control document (ICD), non-prod environment, contract tests, fallback when downstream is unavailable (queue + degrade message).

---

## 5. LLM and intelligence in production

- **Hosting**: cloud API vs **on-prem / Hugging Face** endpoints — decision drives network zones and latency SLOs.
- **Controls**: prompt versioning, PII scrubbing, output schema validation (already JSON-oriented in classifier), **no retention** where policy requires zero data at vendor.
- **Fallback**: rules-only path (already partially present) when LLM disabled or unhealthy.

---

## 6. Phased roadmap (suggested)

### Phase A — Foundation (4–8 weeks, parallel tracks)

- Harden **config & secrets** (vault, no keys in `.env` in prod).
- **CI/CD**, env promotion (dev → UAT → prod).
- **Observability**: structured logs, metrics, tracing IDs from message → case → UI session.
- **SSO** on UI; role matrix (analyst / manager / admin) backed by directory groups.

### Phase B — Mailbox MVP (8–14 weeks)

- Complete §3 discovery; implement **connector + queue + pipeline worker** in non-prod mailbox.
- **Case ID** scheme live; backfill strategy for reprocessing.
- **Outbound** send path in UAT with security sign-off.

### Phase C — Booking & SSI truth (10–16 weeks, can overlap B)

- First **read-only** integration to **one** authoritative booking source for FX (or chosen product).
- Retire CSV for that path; parity tests vs prototype matcher behaviour.
- Expand product types per business priority.

### Phase D — Production pilot (4–6 weeks)

- Limited desk, **parallel run** (legacy process + new UI) or shadow mode.
- KPIs: precision/recall on classify (sampled), time-to-triage, analyst NPS, incident count.

### Phase E — General availability + hardening

- Scale workers, DR drills, SLOs, on-call runbooks.
- **Optional agent layer** (see `docs/visual-overview.html`) only after Phase D stable.

*(Week ranges assume a small dedicated squad + platform teams for mail and Murex; adjust for Nomura resourcing.)*

---

## 7. Workstreams and RACI (lightweight)

| Workstream | Engineering | Business / Ops | Security | Platform (mail/Murex) |
|------------|-------------|----------------|----------|------------------------|
| Mailbox connector | R/A | C | C | A |
| Pipeline / matcher | R/A | C | I | C |
| UI / workflows | R/A | C | C | I |
| LLM governance | R | I | A | I |
| SSO / IAM | C | I | A | R |

*(R = responsible, A = accountable, C = consulted, I = informed.)*

---

## 8. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Mailbox API limits / throttling | Back-pressure, batching, off-peak catch-up jobs |
| Murex field drift | Versioned extract contracts; contract tests on each release |
| LLM hallucination on extract | Schema validation + human review for low confidence; rules fallback |
| Scope creep (all products day one) | **Vertical slice**: one product + one desk + one mailbox |

---

## 9. Deliverables checklist (exit “prototype”)

- [ ] ICDs for mailbox, Murex (or primary book), and SSI source  
- [ ] Non-prod end-to-end: ingest real-shaped mail → case → analyst send (UAT relay)  
- [ ] Production SSO + RBAC  
- [ ] Audit trail exportable for compliance sample  
- [ ] DR: RPO/RTO agreed and tested for case DB + queue  
- [ ] Runbooks: connector down, Murex down, LLM down  

---

## 10. References in this repo

- `docs/visual-overview.html` — business rules and sample inventory  
- `BRD.md`, `DESIGN.md`, `README.md` — product and technical context  
- `backend/app/services/pipeline.py` — orchestration touchpoints for replacement  

---

*Document version: 1.0 — align with Nomura enterprise architecture review before committing dates or vendor-specific APIs.*
