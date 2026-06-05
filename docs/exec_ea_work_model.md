# Exec EA Work Model Research

Working note for tailoring this Graphiti fork to an executive EA knowledge graph.
This is based on a first live read of the OpenSearch staging data at
`http://100.96.45.83:19200` on 2026-06-05. It should be treated as a living model:
the goal is to capture the real shape of the work before implementation hardens it.

## Source Inventory

The current staging corpus is organized around source records plus evidence units:

| Index | Count | Role |
| --- | ---: | --- |
| `emails` | 3,530 | Microsoft Graph mail records with sender, recipient, thread, folder, body, summary, and vectors. |
| `transcripts` | 1,443 | Meeting-level transcript records with participants, dates, titles, topics, summaries, and vectors. |
| `chunks` | 30,715 | Mixed evidence chunks, mostly transcript chunks but also email chunks and some records with missing `source`; preserve source linkage, sequence, speakers, timestamps, topic summary, and vectors. |
| `email_attachments` | 1,003 | Attachment records linked to source email, with extraction text/markdown when available. |
| `calendar_events` | 1,235 | Outlook calendar events with organizer, attendees, series key, timing, and agenda. |
| `project_registry` | 28 | Curated project/program registry with markers for matching source records. |

Temporal coverage:

- `transcripts` and `chunks`: 2025-01-07 through 2026-06-04.
- `emails`: 2025-11-03 through 2026-06-01.
- `email_attachments`: 2025-11-03 through 2026-06-01.
- `calendar_events`: 2025-10-27 through 2026-06-26.

Embeddings already exist in OpenSearch for several record types: dense 3072-dim KNN
vectors plus sparse rank-feature vectors. Graphiti should still treat OpenSearch as
source/provenance unless we explicitly decide to reuse compatible embeddings.

## People

The work is highly person-centric. People appear through:

- Email identity fields: `from_email`, `from_name`, `to`, `cc`, `bcc`.
- Transcript fields: `participants`, `participant_names`, chunk `speakers`.
- Calendar fields: `organizer`, `attendees`, `attendee_emails`.
- Project markers: `person` marker type in `project_registry`.

The identity surface is large and messy: roughly 1,350 unique email identities in
email headers, roughly 1,400 calendar email identities, and roughly 1,400
transcript participant/name tokens. This makes identity resolution a first-order
problem, not a cleanup detail.

Observed high-frequency internal actors:

| Person/email | Evidence |
| --- | --- |
| `michael.dobson@phsa.ca` | 1,299 transcript participant records, 1,512 sent email records, 1,225 calendar attendee records. |
| `hardeep.parwana@phsa.ca` | 302 transcript participant records, 230 calendar attendee records. |
| `ali.deheshi@phsa.ca` | 187 transcript participant records, 180 calendar attendee records, 65 sent email records. |
| `travis.gamble@phsa.ca` | 179 transcript participant records, 139 calendar attendee records. |
| `derek.lucas@phsa.ca` | 147 transcript participant records, 245 calendar attendee records. |
| `jennifer.dury@phsa.ca` | 107 transcript participant records, 132 calendar attendee records, 90 calendar organizer records. |
| `cameron.haley@phsa.ca` | 109 transcript participant records, 172 calendar attendee records. |
| `ana.joshi@phsa.ca` | 99 transcript participant records, 112 calendar attendee records. |

Additional person facts from transcript evidence:

- Hardeep Parwana appears to report directly to Michael Dobson in multiple transcript
  chunks.
- A January 7 transcript says Michael is the new Director of Governance and that
  Hardeep, Kris, Ana, and others were absorbed into Michael's team.
- Assistant/admin identities are operationally important. Jennifer Dury schedules
  on Michael's behalf; Charran Millsip appears as Executive Assistant to Derek Lucas.
  Other assistant/admin names in signatures include Ashley King, Connie Lee, Jessica
  Bennington, Jana Rockwood, and Rosy Cheng.

Observed external/vendor/advisor actors:

| Person/email or domain | Evidence |
| --- | --- |
| `mrosenblood@deloitte.ca`, `mike.rosenblood@phsa.ca` | Appears in both Deloitte and PHSA forms, suggesting alias handling is required. |
| `jaross@deloitte.ca` | 118 transcript participant records, 101 calendar attendee records. |
| `robbanderson@deloitte.ca`, `robb.anderson@phsa.ca` | Appears in both Deloitte and PHSA forms, used as a SAFS project marker. |
| `jstewart@forecight.com` | 98 sent email records, 10 calendar organizer records. |
| `lannyc@microsoft.com` | 38 transcript participant records, 50 calendar attendee records. |
| `erinkelly@microsoft.com` | 22 transcript participant records, 60 calendar attendee records. |
| `bkuhn@zscaler.com` | 18 sent email records, 6 calendar organizer records. |
| `florence.moreno@darktrace.com`, `joel.thomas@darktrace.com` | Visible Darktrace contacts in email. |

Modeling implications:

- `Person` must have stable identifiers and aliases: email addresses, display names,
  transcript speaker names, and organization-specific aliases.
- Person identity is not just a name. Some people appear with both consultant and
  internal addresses, so email aliases should merge into a canonical person only when
  evidence is strong.
- Health authority domains should be modeled as partner/internal-health-sector
  organizations, not generic external vendors.
- EA/admin relationships should be explicit because they explain scheduling authority,
  delegated communication, and why one person can speak or schedule on behalf of
  another.
- Useful relations: `WORKS_FOR`, `USES_EMAIL_ALIAS`, `ATTENDED`, `ORGANIZED`,
  `SENT_EMAIL`, `RECEIVED_EMAIL`, `OWNS_PROJECT`, `SUPPORTS_PROJECT`,
  `REPORTS_TO`, `ASSISTANT_TO`, `EXECUTIVE_SPONSOR_OF`, `VENDOR_CONTACT_FOR`.

## Teams And Organizations

Teams are inferred from domains, meeting titles, distribution lists, and organizational
phrases. They are not currently a clean first-class index.

Strong organization/domain signals:

| Domain | Email count | Interpretation |
| --- | ---: | --- |
| `phsa.ca` | 2,801 | Main internal organization. |
| `forecight.com` | 109 | Security/risk assessment vendor/partner. |
| `microsoft.com` | 88 | Microsoft platform/vendor relationship. |
| `deloitte.ca` | 80 | CSM transformation and advisory relationship. |
| `vch.ca` | 45 | Health authority stakeholder. |
| `gov.bc.ca` | 31 | Government/ministry context. |
| `zscaler.com` | 26 | SASE/Zscaler platform vendor. |
| `darktrace.com` | 25 | Darktrace platform vendor. |
| `cyber.gc.ca` | 24 | Canadian Centre for Cyber Security context. |
| `phc.ca`, `northernhealth.ca`, `fraserhealth.ca`, `interiorhealth.ca`, `islandhealth.ca` | Various | Health authority stakeholders. |

Recurring team/cadence signals:

- `CTIS Security Weekly Meeting`
- `Leadership Team Meeting`
- `Derek's Directs`
- `CSM Executive Meeting`
- `Security Program Alignment Weekly Connect`
- `Provincial Health Security Working Group`
- `PHSA Data Governance Steering Committee`
- `Legal-Privacy-Security Weekly Meeting`
- `STRA Sprint Backlog Refinement Session`

Distribution-list signals:

- `_phsa_pdhis_ctis_informationsecurity@phsa.ca`
- `_phsa_pdhis_ctis_adminsupport@phsa.ca`
- `_phsa_pdhis_directors@phsa.ca`
- `_phsa_pdhis_staff@phsa.ca`

Modeling implications:

- Add `Organization` and `Team`/`WorkingGroup` entities.
- Treat domains and distribution lists as organization/team evidence, not necessarily
  as the canonical entity by themselves.
- Useful relations: `MEMBER_OF`, `PART_OF_ORG`, `REPRESENTS`, `PARTICIPATES_IN`,
  `GOVERNS`, `STEERS`, `ESCALATES_TO`.

## Projects, Programs, Platforms, Vendors

The curated project registry is the best current authority for project/program scope.
It has 7 programs and 21 projects. Marker types include `phrase`, `domain`, `person`,
and `subject`.

The hierarchy is shallow:

- `SASE` contains `Corrections`, `Zscaler`, and `Palo Alto Prisma Access`.
- `CSM - Cyber Security Modernization` contains `LINUS`, `OAG audit`, `Agile`,
  `Metrics/Reporting`, `SAFS`, and `OCM`.
- `Cerner`, `VMO`, `STRA`, `AI Governance`, and `Shared Services` are root programs
  with no children in the current registry.

Markers are mostly aliases or matching rules, not typed business objects:

- `phrase`: 58
- `person`: 10
- `domain`: 4
- `subject`: 3
- `candidate_markers`: empty for all current registry records

Current registry:

| ID | Parent | Kind | Name | Marker examples |
| ---: | ---: | --- | --- | --- |
| 1 |  | program | SASE | `SASE` |
| 2 | 1 | project | Corrections (BC Attorney General trial) | `corrections`, `Correctional Centres`, `CC's`, `AG` |
| 3 | 1 | project | Zscaler | `Zscaler`, `App Connector` |
| 4 | 1 | project | Palo Alto Prisma Access | `Prisma Access`, `Palo Alto`, `paloaltonetworks.com`, `Ashley Anderson` |
| 5 |  | program | CSM - Cyber Security Modernization | `CSM`, `Cyber Security Modernization`, `deloitte.ca` |
| 6 | 5 | project | LINUS | `LINUS` |
| 7 | 5 | project | OAG audit | `OAG`, `Office of the Auditor General` |
| 8 | 5 | project | Agile (CSM) | `Planner`, `Jira`, `Azure DevOps`, `ADO`, named people |
| 9 | 5 | project | Metrics/Reporting | `Metrics/Reporting` |
| 10 | 5 | project | SAFS | `SAFS`, Robb Anderson markers |
| 11 | 5 | project | OCM | `OCM`, `Organizational Change Management`, subject/person markers |
| 12 |  | program | Cerner | `Cerner`, `OCI`, `PDHIS` |
| 13 |  | project | Defender rollout | `Defender for Endpoint`, `MDE` |
| 14 |  | project | Darktrace | `Darktrace`, `darktrace.com` |
| 15 |  | project | Resolver | `Resolver` |
| 16 |  | project | Abnormal AI | `Abnormal AI` |
| 17 |  | project | BlueVoyant | `BlueVoyant`, `MXDR` |
| 18 |  | project | CrowdStrike | `CrowdStrike`, `CS Renewal` |
| 19 |  | project | RedOps pen-test | `RedOps` |
| 20 |  | project | Securin.io POC | `Securin`, `Securin.io` |
| 21 |  | program | VMO - Vulnerability Management Office | `VMO`, `Vulnerability Management Office` |
| 22 |  | program | STRA (internal) | `STRA`, `Security Threat and Risk Assessment` |
| 23 |  | program | AI Governance | `AI Governance` |
| 24 |  | project | Data Governance | `Purview`, `Protiviti`, `Varonis`, `Data Governance` |
| 25 |  | project | Service Catalogue | `Service Catalogue`, `Service Catalog` |
| 26 |  | project | Azure Migration | `Azure Migration` |
| 27 |  | project | FairWarning | `FairWarning`, `P2Sentinel` |
| 28 |  | program | Shared Services - BC Shared Health Services | `BCHSHS`, `Shared Services`, `HA Transformation`, `BCSHS` |

High-volume platform/vendor terms across all source indices:

| Term | Total hits | Notes |
| --- | ---: | --- |
| Microsoft | 5,569 | Broad platform/vendor/calendar footprint. |
| Defender | 2,137 | Strong project/platform signal; related to CrowdStrike migration. |
| CrowdStrike | 1,660 | Strong project/platform signal; renewal and migration context. |
| Deloitte | 2,590 | CSM/advisory/vendor context. |
| Forecight | 1,256 | STRA/security assessment vendor context. |
| Zscaler | 803 | SASE project/platform. |
| Forescout | 637 | Strong platform signal not yet in registry. |
| Darktrace | 375 | Registry project/platform. |
| Medigate | 312 | Strong platform signal not yet in registry. |
| Varonis | 247 | Present under Data Governance registry project. |
| Imprivata | 162 | Renewal/platform signal not yet in registry. |
| Securin | 82 | Registry POC project. |

High-signal registry matches by marker mentions:

| Registry entity | Emails | Transcripts | Chunks | Attachments | Events |
| --- | ---: | ---: | ---: | ---: | ---: |
| CSM | 524 | 369 | 3,873 | 125 | 64 |
| Cerner | 953 | 403 | 3,115 | 148 | 67 |
| STRA | 214 | 353 | 1,565 | 98 | 16 |
| Data Governance | 230 | 353 | 1,472 | 63 | 25 |
| CrowdStrike | 250 | 201 | 1,194 | 92 | 42 |
| SASE | 75 | 72 | 418 | 29 | 8 |

Important cleanup examples:

- `CrowdStrike` is not only a standalone project. Evidence includes migration from
  CrowdStrike to Defender/MDE, so model `MIGRATES_FROM` and `MIGRATES_TO`.
- `Purview` and `Varonis` sit under Data Governance. Evidence includes comparisons
  and funded engagements involving Microsoft, Protiviti, Varonis, and possibly Cyera.
- `Forescout` and `Medigate` are strong workstream/platform signals but absent from
  the current registry.
- `Forecight` is a vendor/partner around STRA and cybersecurity sync work, not a
  product platform.
- `FairWarning` should likely be a platform/product, with Imprivata as vendor and
  renewal/onboarding as project events.

Modeling implications:

- Separate `Program`, `Project`, `Platform`, and `Vendor` instead of collapsing all
  work into `Project`.
- `project_registry` should seed `Program` and `Project` nodes, then source records
  should link to matching projects with confidence and marker evidence.
- Forescout, Medigate, Imprivata, Microsoft/Purview, Defender, CrowdStrike, Varonis,
  Zscaler, Darktrace, Resolver, Abnormal, BlueVoyant, Securin, Palo Alto/Prisma should
  be modeled as `Platform` or `VendorProduct` entities.
- Vendors and platforms are not always the same thing. Example: Microsoft is a vendor;
  Purview and Defender are platforms/products; Deloitte and Forecight are advisory or
  services vendors; CrowdStrike and Varonis are both vendor and product shorthand in
  source language.
- Split overlapping vendor/product/project names. `CrowdStrike`, `Zscaler`,
  `Darktrace`, `Resolver`, and `Securin` can refer to a vendor, a platform, and a
  project depending on context.
- Preserve registry markers as alias/evidence rules, but do not let `domain`,
  `person`, or `subject` markers stand in for typed graph relations.

Useful relations:

- `PARENT_PROGRAM_OF`
- `PROJECT_PART_OF_PROGRAM`
- `PROJECT_USES_PLATFORM`
- `PROJECT_EVALUATES_PLATFORM`
- `VENDOR_PROVIDES_PLATFORM`
- `PROJECT_HAS_VENDOR`
- `PROJECT_HAS_WORKSTREAM`
- `PROJECT_HAS_RENEWAL`
- `PROJECT_HAS_RISK`
- `PROJECT_HAS_DECISION`
- `PROJECT_HAS_ACTION_ITEM`

## Topics And Work Domains

The generated transcript topics are useful as local chunk summaries but noisy as a
global taxonomy. Many top exact labels are meeting boilerplate such as openings,
closings, greetings, and scheduling.

The real work-domain taxonomy emerges better from controlled terms in subjects,
titles, summaries, attachment text, transcript chunks, and calendar titles:

| Domain signal | Approx hits | Interpretation |
| --- | ---: | --- |
| `Security Threat and Risk Assessment` / `STRA` | Very high | STRA is a central operating workflow, not just a topic. |
| `shared services` | 11,220 | Major transformation/governance program theme. |
| `data governance` | 8,919 | Broad strategic domain involving Purview, labels, DLP, Varonis. |
| `risk` | 6,149 | Cross-cutting security/risk concept. |
| `AI Governance` | 4,438 | Program/topic signal, but count likely includes broad words. |
| `operating model` | 3,518 | Transformation/design theme. |
| `budget` | 2,584 | Executive finance/procurement work. |
| `resource` | 2,582 | Staffing/resourcing/capacity theme. |
| `audit` | 2,072 | OAG and assurance work. |
| `incident` | 1,977 | Incident response/escalation context. |
| `vulnerability` | 1,516 | VMO/vulnerability management context. |
| `renewal` | 1,401 | Contracts and platform lifecycle. |
| `procurement` | 1,208 | RFPs, quotes, purchasing, renewals. |
| `RFP` | 704 | Procurement/project lifecycle. |
| `capital` | 879 | Capital funding and budget planning. |
| `DLP`, `labels` | 626, 251 | Data governance/Purview/Varonis subdomain. |

Recommended taxonomy:

- `SecurityRiskAssurance`: STRA, privacy/security assessments, risk registers,
  OAG/audit, vulnerability, incident, controls.
- `CyberModernization`: CSM, SAFS, OCM, metrics, team design, agile delivery,
  operating model.
- `IdentityEndpointNetworkSecurity`: Defender, CrowdStrike, Zscaler, SASE,
  Palo Alto, Forescout, Medigate, Darktrace.
- `DataGovernanceAndPrivacy`: Purview, Varonis, DLP, labels, EDM, data risk,
  governance committee.
- `ProcurementCommercials`: renewals, quotes, RFP, budget, capital, licensing,
  contracts.
- `ExecutiveCadence`: 1:1s, signing meetings, leadership meetings, steering
  committees, working groups, status reviews.
- `SharedServicesTransformation`: shared services, HA transformation, provincial
  working groups, cross-health-authority alignment.
- `DeliveryOperations`: action items, decisions, blockers, dependencies, staffing,
  backlog, status, roadmap.

Modeling implications:

- Treat these domains mostly as tags/classifications on episodes and facts, not
  always as entities.
- Promote a topic to an entity when it has durable ownership, governance, lifecycle,
  or relations. Example: `STRA (internal)` is a program/workflow entity; `closing
  remarks` is only noise; `Data Governance` is a project/domain entity.
- Topic extraction should suppress meeting boilerplate and prioritize decisions,
  risks, asks, dependencies, dates, owners, and artifacts.

## Records, Evidence, And Provenance

Stable source IDs:

| Source | Stable IDs |
| --- | --- |
| Email | `graph_immutable_id`, `internet_message_id`, `thread_id`, `conversation_id`, `conversation_index` |
| Transcript | `transcript_id`, `gdrive_file_id`, `filename`, `date` |
| Chunk | `chunk_id`, `transcript_id`, `source_id`, `sequence`, `prev_chunk_id`, `next_chunk_id` |
| Attachment | `attachment_id`, `graph_immutable_id`, `internet_message_id`, `blob_sha256`, `blob_path` |
| Calendar | `outlook_event_id`, `series_key`, `start_time`, `end_time` |
| Project registry | `project_id`, `parent_id`, `canonical_name`, marker list |

Record hierarchy:

- Email threads are keyed by `conversation_id` / `thread_id`.
- Attachments link to email via `graph_immutable_id` and `internet_message_id`.
- Transcript chunks link to transcript via `transcript_id` and sequence.
- Calendar events may overlap with transcript records by title/time/participants,
  but there is no explicit join key in the sampled data.
- Project registry records are concept seeds, not evidence documents.

Attachment extraction:

- 566 completed, 431 skipped, 6 failed.
- Completed attachments average about 34,360 characters and 4.9 tables.
- Extraction methods include `docling-serve`, `llamaparse`, and `text-direct`.
- Skipped records are mostly inline images or unsupported types.

Graphiti implementation gaps checked in this fork:

- `EpisodicNode` has `episode_metadata`, but current save and return queries do not
  persist it.
- `add_episode()` does not accept a metadata/provenance dict.
- `SearchFilters.property_filters` exists but is not wired into generic node/edge
  search filters, and episode search does not apply arbitrary filters.
- The fork has native `SagaNode`, `HAS_EPISODE`, and `NEXT_EPISODE` support.
  Treat this as the preferred Graphiti-native way to model ordered email
  threads, meeting series, recurring cadences, and durable workstream episode
  streams.
- Upstream Graphiti docs caution that `add_episode_bulk` is best for empty graphs
  or cases where edge invalidation is not required. This fork's current bulk path
  now resolves and persists invalidated edges, so the remaining caution is about
  batch ordering, episode attribution, reviewability, and operational control.

Modeling implications:

- Add persisted provenance before large ingestion. The graph must be able to answer
  "where did this come from?", "what record/thread/chunk supports this?", and "what
  source process created it?"
- Recommended episode provenance fields:
  - `source_index`
  - `source_id`
  - `source_kind`
  - `source_system`
  - `external_url` or source pointer when available
  - `thread_id`
  - `conversation_id`
  - `transcript_id`
  - `chunk_id`
  - `attachment_id`
  - `calendar_event_id`
  - `project_matches`
  - `platform_matches`
  - `ingestion_run_id`
  - `source_updated_at`
  - `extraction_status`
  - `extraction_method`

## Proposed Native Graphiti Ontology

Use Graphiti's native custom entity and edge type extension points wherever
possible. Define domain objects as Pydantic models passed through
`entity_types`, define domain relationships through `edge_types`, and constrain
allowed relationships with `edge_type_map`. Operational observations should be
custom Graphiti entity types rather than a parallel task/state layer.

Use `group_id` as the graph namespace/partition, not as a project identifier.
Project, platform, source, and ingestion-run scoping should live in custom
entity attributes, edge attributes, or persisted episode provenance fields.

Core entities:

- `Person`
- `Organization`
- `Team`
- `WorkingGroup`
- `Program`
- `Project`
- `Platform`
- `VendorProduct`
- `Vendor`
- `Document`
- `EmailThread`
- `MeetingSeries`
- `MeetingOccurrence`
- `Workstream`
- `Topic`
- `Obligation`
- `ApprovalRequest`
- `Decision`
- `ActionItem`
- `Blocker`
- `ProjectStatus`
- `MetricSnapshot`
- `DeliverableStatus`
- `MeetingCarryForward`
- `Risk`
- `Issue`
- `Dependency`
- `Renewal`
- `BudgetItem`
- `ProcurementEvent`
- `Assessment`

Core relations:

- `PERSON_WORKS_FOR_ORG`
- `PERSON_MEMBER_OF_TEAM`
- `PERSON_USES_ALIAS`
- `PERSON_ATTENDED_MEETING`
- `PERSON_ORGANIZED_MEETING`
- `PERSON_SENT_EMAIL`
- `PERSON_RECEIVED_EMAIL`
- `PROGRAM_HAS_PROJECT`
- `PROJECT_HAS_WORKSTREAM`
- `PROJECT_INVOLVES_PLATFORM`
- `VENDOR_PROVIDES_PLATFORM`
- `PROJECT_HAS_VENDOR`
- `PROJECT_HAS_DECISION`
- `PROJECT_HAS_ACTION_ITEM`
- `PROJECT_HAS_RISK`
- `PROJECT_HAS_DEPENDENCY`
- `PROJECT_HAS_RENEWAL`
- `PROJECT_HAS_PROCUREMENT_EVENT`
- `DOCUMENT_ATTACHED_TO_EMAIL`
- `CHUNK_PART_OF_TRANSCRIPT`
- `EMAIL_PART_OF_THREAD`
- `MEETING_SERIES_HAS_OCCURRENCE`
- `OCCURRENCE_HAS_TRANSCRIPT`
- `OCCURRENCE_HAS_CALENDAR_EVENT`
- `PERSON_OWNS_OBLIGATION`
- `OBLIGATION_REQUESTED_BY`
- `APPROVAL_WAITING_ON_PERSON`
- `DECISION_APPLIES_TO_PROJECT`
- `BLOCKER_BLOCKS_PROJECT`
- `METRIC_SNAPSHOT_FOR_PROJECT`
- `DELIVERABLE_STATUS_FOR_PROJECT`
- `MEETING_CARRIED_FORWARD_ITEM`
- `EVIDENCE_SUPPORTS_FACT`

Source kinds to emulate in episode provenance:

- `email`
- `email_thread`
- `transcript`
- `transcript_chunk`
- `attachment`
- `calendar_event`
- `project_seed`

Keep upstream `EpisodeType` unchanged for now. Ingest source-specific kinds as
`text` or `json` episodes with precise `source_description` and persisted
provenance such as `source_kind=email`, `source_kind=transcript_chunk`, or
`source_kind=calendar_event`.

## Open Questions

- Which identity authority should merge people who have both consultant and internal
  addresses?
- Should Forecight be modeled as a vendor, a managed service partner, or a project
  context around STRA operations?
- Should Forescout and Medigate become top-level `Platform` nodes, registry projects,
  or both?
- What is the canonical team hierarchy for PHSA/PDHIS/CTIS/security leadership?
- How should calendar events be joined to transcripts when titles/time/participants
  match but no explicit key exists?
- Which topics should remain tags versus graph entities?

## Next Implementation Direction

Treat `docs/exec_ea_native_graphiti_plan.md` as the canonical implementation rail.
The condensed direction is:

1. Persist episode provenance and wire basic metadata filters.
2. Define native exec-EA custom `entity_types`, `edge_types`, and `edge_type_map`
   for projects, platforms, vendors, people, organizations, meeting series,
   documents, and operational observations.
3. Create curated seed manifests and load them as native Graphiti entities and
   edges with deterministic UUIDs and provenance-backed attributes.
4. Build deterministic source-to-project/platform/meeting matching using registry
   markers and curated aliases.
5. Ingest a small pilot slice through `add_episode(...)` with custom types:
   - 1 email thread,
   - 1 transcript with chunks,
   - 1 attachment set,
   - the relevant calendar events,
   - the matching project/platform seeds.
6. Inspect graph quality before broad backfill.

For broad backfill, be careful with `add_episode_bulk`: in this fork it appears
to perform edge invalidation, but batch ingestion still makes ordering,
attribution, and reviewability harder. Use single-episode ingestion when temporal
state changes matter, and reserve bulk ingestion for empty-graph loads or
reviewed batches whose ordering and attribution are well understood.
