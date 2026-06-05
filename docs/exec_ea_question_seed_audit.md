# Exec-EA Question-Driven Seed Audit

Live audit date: 2026-06-05

Purpose: translate the 20 target answerability questions into concrete seed,
ontology, importer, and pilot requirements. The target is roughly 80%
material answerability in the pilot, not complete corpus coverage.

## Live Source Check

Logical OpenSearch counts from `_count`:

| Index | Count | Relevant use |
| --- | ---: | --- |
| `emails` | 3,530 | Inbox triage, approvals, obligations, project updates, person dossiers. |
| `transcripts` | 1,443 | Meeting decisions, commitments, carry-forwards, project status. |
| `chunks` | 30,715 | Fine-grained evidence with sequence, speakers, and source links. |
| `email_attachments` | 1,003 | Reports, workbooks, tables, approvals, project artifacts. |
| `calendar_events` | 1,235 | Meeting instances, future prep, absence windows, series continuity. |
| `project_registry` | 28 | Current authoritative program/project seed source. |

Key schema signals are present:

- Email has `folder_path`, `is_read`, `direct_recipient`, `importance`,
  `flag_status`, `conversation_id`, `thread_id`, `from_email`, and timestamps.
- Transcripts have `title`, `date`, participants, content, topics, and stable
  `transcript_id`.
- Chunks have `chunk_id`, `source`, `source_id`, `transcript_id`, `sequence`,
  neighbor chunk IDs, speakers, timestamps, and content.
- Attachments have `filename`, `extraction_status`, `extraction_method`,
  `table_count`, `blob_sha256`, attachment/message IDs, and extracted text.
- Calendar events have `title`, `series_key`, organizer, attendees, start/end
  time, event ID, web link, and cancellation state.

## Coverage Signals

Named benchmark concepts have enough live coverage to seed, except the budget
savings workbook, which needs a better source locator or alternate naming.

| Signal | Emails | Transcripts | Chunks | Attachments | Calendar | Readiness |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| CSM Executive Meeting | 4 | 18 | 592 | 1 | 27 | Seed series now. |
| Forecight monthly cybersecurity sync | 3 | 9 | 133 | 1 | 6 | Seed series and vendor now. |
| Hardeep | 934 | 611 | 6,773 | 52 | 33 | Seed person and aliases now. |
| Leadership Team Meeting | 9 | 65 | 1,638 | 4 | 7 | Seed series now. |
| Purview + Copilot | 39 | 76 | 225 | 20 | 1 | Seed workstream/group. |
| CrowdStrike + Defender/MDE | 101 | 141 | 587 | 33 | 24 | Seed project/platform links now. |
| Data Governance | 84 | 179 | 514 | 34 | 7 | Seed project and platforms now. |
| Oracle + OCI | 40 | 53 | 343 | 14 | 14 | Seed as Cerner/OCI work context. |
| Patient Portal closure | 4 | 1 | 4 | 2 | 0 | Pilot with artifact validation. |
| Defender endpoint counts | 11 | 65 | 73 | 25 | 0 | Needs table/value extraction. |
| Budget savings workbook | 4 | 5 | 9 | 0 | 0 | Needs source locator. |
| Jamie Ross / `jaross@deloitte.ca` | 205 | 133 | 152 | 11 | 101 | Seed person/vendor alias now. |
| Derek Lucas | 578 | 179 | 635 | 77 | 245 | Seed person now. |
| Forecight | 179 | 30 | 956 | 78 | 13 | Seed vendor/partner now. |
| Approval/sign-off language | 485 | 642 | 2,071 | 173 | 3 | Observation extraction required. |
| Blocked/waiting language | 79 | 364 | 679 | 28 | 3 | Observation extraction required. |

Recurring series date coverage is strong:

| Series | Transcripts | Transcript range | Calendar events | Calendar range |
| --- | ---: | --- | ---: | --- |
| CSM Executive Meeting | 18 | 2025-10-28 to 2026-05-26 | 27 | 2025-11-04 to 2026-06-23 |
| Leadership Team Meeting | 57 | 2025-01-08 to 2026-06-03 | 7 | 2026-05-20 to 2026-06-22 |
| Forecight/PHSA cybersecurity sync | 16 | 2025-03-06 to 2026-03-04 | 6 | 2025-12-08 to 2026-06-03 |
| Hardeep 1:1 | 18 | 2025-04-14 to 2026-03-09 | 24 | 2025-11-25 to 2026-06-22 |

Email triage is viable but needs thread-state inference:

- `Inbox`: 254 emails.
- `Inbox` unread: 154 emails.
- `Inbox` direct recipient: 204 emails.
- `Inbox` direct recipient and unread: 136 emails.
- `ForInfo` unread: 1,269 emails.
- `Daily Summary`: 364 email hits.
- `Winston`: 0 email hits by that exact token.

## Answerability Readiness

| Question | Status | What must exist in the pilot |
| --- | --- | --- |
| What are my top priorities today? | Partial | Priority/ranking logic over obligations, approvals, blockers, recent meetings, direct inbox items, and project importance. |
| What is sitting in my inbox that actually needs a response from me? | Partial | Email thread state, direct-recipient/folder/read filters, machine-summary exclusions, response-needed observation. |
| I was out Tuesday-Thursday; what did I miss? | Likely | Temporal query over email, transcripts, calendar, and project/person relevance filters. |
| What did I commit to in the last CSM Executive Meeting that I have not done yet? | Likely | CSM series seed, latest occurrence join, Michael-owned obligations, follow-through inference. |
| What have I said I would do but there is no sign I followed through? | Hard | Absence detection over later emails, meetings, approvals, and deliverable/status observations. |
| What is due from me before the end of the month? | Partial | Deadline extraction with firm-vs-hedged date confidence and Michael ownership. |
| What approvals or sign-offs are waiting on me? | Likely | ApprovalRequest entities, waiting-on person edges, document/procurement links. |
| Who owes me something right now, and what? | Partial | Bidirectional obligations with owner/requester and overdue ranking. |
| Is Forecight late on anything they committed to in the monthly cybersecurity sync? | Likely | Forecight vendor seed, monthly sync series seed, vendor-owned obligations, due/follow-through inference. |
| Do I owe Derek anything, and is he waiting on me? | Likely | Derek person seed/aliases, bidirectional obligations, waiting-on edges. |
| Get me up to speed on the CrowdStrike-to-Defender migration. | Strong | CrowdStrike, Defender/MDE, project/platform/vendor seeds, migration relation, attachment ingestion. |
| What is blocked on Data Governance, and who is the blocker? | Likely | Data Governance seed, blocker observations, person/project attribution. |
| What changed on Oracle OCI since last week? | Likely | Cerner/OCI seed, temporal delta query, project-matched episodes. |
| Where did the Patient Portal closure report land, and is it approved yet? | Partial | Patient Portal deliverable/document seed, two known attachment candidates, approval/status observations. |
| Brief me for my next 1:1 with Hardeep. | Strong | Hardeep person seed, Hardeep 1:1 series seed, open items and next calendar event. |
| What did we decide about Purview/Copilot, and when? | Likely | Purview/Copilot workstream or working-group seed, decision observations with timestamps. |
| Across the last three Leadership Team Meetings, what carried forward unresolved? | Likely | Leadership Team Meeting series seed, occurrence ordering, carry-forward observations. |
| What is our current endpoint count for the Defender rollout? | Partial | MetricSnapshot extraction from attachments/tables with as-of date and source document. |
| Pull the latest figures from the budget savings workbook. | Gap | Need exact workbook/file locator or alternate naming before this can be a pilot acceptance item. |
| Who is Jamie Ross, how do I know them, and what are we working on together? | Strong | Jamie Ross person seed, Deloitte org seed, alias handling, project and recent-interaction edges. |

Expected pilot answerability after the recommended seeds and observation types:
16 of 20 should be materially answerable. The four weakest cases are broad
absence detection, firm deadline confidence, Patient Portal approval resolution,
and the budget savings workbook locator.

## Seed Priorities

Create seed manifests in this order after provenance support exists.

1. Program/project seeds from `project_registry`.
2. Promoted platform and vendor-product seeds:
   - Defender/MDE
   - CrowdStrike
   - Purview
   - Copilot
   - Varonis
   - Oracle OCI
   - Forescout
   - Medigate
   - Imprivata/FairWarning
   - Zscaler
   - Darktrace
   - Securin
   - Prisma Access
   - BlueVoyant/MXDR
   - Abnormal AI
   - Resolver
3. Vendor/organization seeds:
   - PHSA
   - Deloitte
   - Forecight
   - Microsoft
   - Palo Alto
   - Varonis
   - Imprivata
   - Zscaler
   - Darktrace
   - Securin
   - BlueVoyant
   - Abnormal Security
   - Resolver
   - Forescout
   - Medigate

Role-aware seed rule:

- Do not collapse registry project names into platform or vendor names. Create
  separate native seeds when a term crosses roles, share a normalized
  `concept_key`, and connect the seeds with typed edges. For example, `Zscaler`,
  `CrowdStrike`, `Darktrace`, `BlueVoyant`, `Abnormal AI`, `Resolver`,
  `FairWarning`, and `Palo Alto Prisma Access` should each preserve distinct
  project/platform/vendor-product/vendor roles where evidence supports them.
4. Person seeds and aliases:
   - Michael Dobson
   - Hardeep Parwana
   - Derek Lucas
   - Jamie Ross / `jaross@deloitte.ca`
   - Jennifer Dury
   - Ali Deheshi
   - key Forecight contacts
   - key Microsoft contacts
5. Meeting series seeds:
   - CSM Executive Meeting
   - Forecight/PHSA Monthly Cybersecurity Sync
   - 1:1 w/Hardeep & Michael
   - Leadership Team Meeting
   - Microsoft Offer / Purview & Copilot Working Group
6. Document/deliverable seeds for pilot:
   - Patient Portal closure/report artifacts
   - Defender deployment and CrowdStrike migration PDFs
   - Defender endpoint-count/table-bearing source artifacts
   - budget savings workbook after locator validation

## Observation Types Needed For 80% Coverage

These should be first-pass custom entity types and edge types, not deferred
analytics:

- `Obligation`
- `ApprovalRequest`
- `Decision`
- `ActionItem`
- `Blocker`
- `ProjectStatus`
- `DeliverableStatus`
- `MeetingCarryForward`
- `MetricSnapshot`
- `Renewal`
- `BudgetItem`
- `ProcurementEvent`

Important inference rule: done/not-done, late/not-late, and no-follow-through
are query-time conclusions over later evidence. Do not create unsupported
negative facts in the graph.

## Implementation Consequence

The next code step remains provenance foundation. This audit strengthens, rather
than changes, the build order:

1. Persist episode metadata and wire metadata filters.
2. Define custom entity and edge types with the observation types above.
3. Generate seed manifests from this audit plus `project_registry`.
4. Build deterministic project/platform/person/series matching.
5. Pilot on one slice that exercises at least 16 of the 20 benchmark questions.
