# Native Graphiti Exec-EA Ingestion Plan

## Purpose

This is the steering document for tailoring this Graphiti fork into Michael
Dobson's personal executive-EA knowledge system.

The central rule is simple: improve Graphiti so it can represent the work
natively. Do not build a second operational memory system beside it.

Use OpenSearch as the staging/source archive and Graphiti as the transformed
working memory graph. OpenSearch remains useful for source refresh, audit, and
backfill. Normal reasoning, retrieval, and agent memory should happen inside
Graphiti after ingestion.

The desired shape is:

```text
OpenSearch source record
  -> Graphiti EpisodicNode with persisted provenance
  -> native/custom EntityNode labels and attributes
  -> native/custom EntityEdge facts, names, temporal bounds, and attributes
  -> source traceability through episode metadata and edge episode IDs
```

## Current Fork Facts

These facts were checked against the fork on 2026-06-05 and should be rechecked
before editing the related code.

- `EpisodicNode` already has an `episode_metadata` field, but the current save,
  bulk save, return-query, parser, and public ingestion paths do not persist and
  return it end to end.
- `Graphiti.add_episode(...)` does not currently accept a provenance metadata
  dict.
- `RawEpisode` does not currently carry provenance metadata for bulk ingestion.
- `SearchFilters.property_filters` exists, but generic node/edge search filters
  do not apply it, and episode search only applies query/group filters.
- This fork has a native saga layer: `SagaNode`, `HAS_EPISODE`, and
  `NEXT_EPISODE`. Use it for coherent episode streams such as meeting series,
  email threads, recurring cadences, and durable workstreams.
- Upstream Graphiti docs caution that bulk ingestion is best for empty graphs or
  cases where temporal invalidation is not required. This fork's current
  `add_episode_bulk` implementation now routes through edge resolution and
  persists invalidated edges. Keep using caution with bulk ingestion, but the
  reason is batch ordering, attribution quality, reviewability, and operational
  control rather than a known absence of invalidation.

## Graphiti-Native Rules

Use these rules to evaluate every proposed change.

- Episodes are the ingestion and provenance unit. A source email, transcript,
  transcript chunk, attachment, calendar event, or seed manifest should become a
  Graphiti episode or a small set of episodes when the source record is too large.
- Extracted or seeded entities must be native Graphiti entities. Domain objects
  should be Pydantic models passed through `entity_types`, not rows in a side
  state store.
- Domain facts must be native Graphiti entity edges. Domain relationships should
  be Pydantic models passed through `edge_types`, with high-value signatures
  constrained through `edge_type_map`.
- Retrieval should prefer Graphiti search over OpenSearch lookback. Use
  `SearchFilters.node_labels` and `SearchFilters.edge_types` for typed retrieval
  over custom labels and relationships.
- Use `group_id` as the graph namespace/partition only. It is not a project ID,
  source ID, ingestion run ID, user ID, or ontology category.
- Preserve source and matching provenance on episodes first. Put durable domain
  properties on entities and relation-specific properties on edges. Do not force
  source bookkeeping into domain entity attributes.
- Keep source-specific episode kinds such as `email`, `transcript_chunk`,
  `calendar_event`, and `project_seed` in `episode_metadata.source_kind`. For
  source records, use `EpisodeType.json` or `EpisodeType.text` in v1. Do not add
  custom `EpisodeType` values unless Graphiti itself needs a new public source
  behavior.
- Use sagas where Graphiti needs ordered streams: an `EmailThread` saga, a
  recurring meeting series saga, or a workstream saga can connect episodes with
  `HAS_EPISODE` and `NEXT_EPISODE` without inventing a separate timeline store.
- Avoid a separate task/state/document database for obligations, approvals,
  decisions, metrics, or carry-forwards unless Graphiti cannot reasonably express
  the behavior. If an import checkpoint table is required, it is operational
  infrastructure, not the retrieval source of truth.

## Modeling Boundaries

Graphiti has three different jobs here. Keep them separate.

- Source provenance: stored on `EpisodicNode.episode_metadata`, plus native
  `MENTIONS` links and `EntityEdge.episodes`.
- Durable work model: represented as native/custom entity nodes such as
  `Program`, `Project`, `Platform`, `Vendor`, `Person`, `MeetingSeries`, and
  `Document`.
- Temporal facts and observations: represented as native/custom entity edges and
  observation entities such as `Obligation`, `Decision`, `Blocker`,
  `ProjectStatus`, and `MetricSnapshot`.

Do not use `EVIDENCE_SUPPORTS_FACT` as a blanket replacement for native episode
provenance. Use it only when a domain artifact entity, such as a `Document` or
`Assessment`, explicitly supports another modeled object. Ordinary source-record
lineage should remain in episode metadata and edge episode IDs.

## Target Answerability Benchmarks

The first production-oriented target is not complete coverage of the corpus. It is
roughly 80% answerability across a representative executive-assistant question set.
Use these questions to steer seed choice, ontology scope, importer matching, and
pilot evaluation. See `docs/exec_ea_question_seed_audit.md` for the live
OpenSearch seed/readiness audit derived from this benchmark.

Daily prioritization and triage:

- What are my top priorities today?
- What is sitting in my inbox that actually needs a response from me?
- I was out Tuesday-Thursday; what did I miss?

Michael-owned obligations:

- What did I commit to in the last CSM Executive Meeting that I have not done yet?
- What have I said I would do but there is no sign I followed through?
- What is due from me before the end of the month?
- What approvals or sign-offs are waiting on me?

Obligations owed to Michael:

- Who owes me something right now, and what?
- Is Forecight late on anything they committed to in the monthly cybersecurity sync?
- Do I owe Derek anything, and is he waiting on me?

Project and workstream catch-up:

- Get me up to speed on the CrowdStrike-to-Defender migration.
- What is blocked on Data Governance, and who is the blocker?
- What changed on Oracle OCI since last week?
- Where did the Patient Portal closure report land, and is it approved yet?

Meeting prep and recall:

- Brief me for my next 1:1 with Hardeep.
- What did we decide about Purview/Copilot, and when?
- Across the last three Leadership Team Meetings, what carried forward unresolved?

Facts, numbers, and people:

- What is our current endpoint count for the Defender rollout?
- Pull the latest figures from the budget savings workbook.
- Who is Jamie Ross, how do I know them, and what are we working on together?

Seed implications from this benchmark:

- Prioritize durable seeds for the projects, platforms, vendors, people, documents,
  and meeting series directly named above before broad ontology expansion.
- Treat recurring meeting series as first-class seeds: CSM Executive Meeting,
  monthly cybersecurity sync, Hardeep 1:1, Leadership Team Meeting, and relevant
  Purview/Copilot working groups.
- Treat obligations, approvals, blockers, decisions, carry-forwards, deliverable
  statuses, metric snapshots, and document/table values as first-pass observation
  types, not later analytics polish.
- Preserve absence and follow-through as query-time inference over evidence. Do
  not create fake "done" or "not done" facts without supporting episodes.

## Native Exec-EA Ontology

Core entity types:

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

Core relation types:

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

These relation names are starting constraints, not permission to create one-off
relationship names for every phrasing. `edge_type_map` should be specific enough
to steer extraction but broad enough to remain maintainable.

## Custom Type Discipline

- Entity type names are PascalCase.
- Relation type names are SCREAMING_SNAKE_CASE.
- Attribute names are snake_case.
- Custom type attributes should be optional, atomic fields with specific Python
  types where practical.
- Avoid protected `EntityNode` attribute names in custom entity models: `uuid`,
  `name`, `group_id`, `labels`, `created_at`, `summary`, `attributes`, and
  `name_embedding`.
- Do not place source IDs such as `chunk_id`, `internet_message_id`, or
  `outlook_event_id` on every extracted domain entity by default. Put them in
  episode metadata unless the source ID is the durable identifier of that entity
  type, such as `EmailThread.conversation_id` or `MeetingOccurrence.transcript_id`.
- Keep generated transcript topics mostly as tags/classifications until a topic
  has durable ownership, governance, lifecycle, or meaningful relations.
- Split overlapping project/platform/vendor words. For example, `CrowdStrike`
  can be a vendor, platform, and project context; model those roles explicitly
  instead of collapsing them into one `Project`.
- Seed manifests must be role-aware. When a surface term crosses roles, create
  separate native seeds with the same normalized `concept_key` and different
  `seed_role` values, then connect them with typed relations. Examples:
  `Zscaler` as a SASE `Project`, `Platform`, and `Vendor`; `CrowdStrike` as a
  registry `Project`, endpoint `Platform`, vendor product, and `Vendor`; `Palo
  Alto Prisma Access` as a registry `Project`, platform, vendor product, and
  Palo Alto vendor relationship.

## Provenance Model

Persisted episode metadata is the first implementation gate.

Recommended v1 `episode_metadata` fields:

- `source_system`
- `source_index`
- `source_kind`
- `source_id`
- `external_url`
- `thread_id`
- `conversation_id`
- `conversation_index`
- `internet_message_id`
- `transcript_id`
- `chunk_id`
- `prev_chunk_id`
- `next_chunk_id`
- `attachment_id`
- `blob_sha256`
- `calendar_event_id`
- `series_key`
- `project_matches`
- `platform_matches`
- `person_matches`
- `ingestion_run_id`
- `source_created_at`
- `source_updated_at`
- `extraction_status`
- `extraction_method`
- `match_confidence`
- `ambiguity_flags`

For v1 filtering, favor simple top-level scalar fields. Nested structures such as
`project_matches` and `platform_matches` can be persisted as metadata, but
query-time filters should start with top-level fields like `source_kind`,
`source_index`, `source_id`, `ingestion_run_id`, `project_id`, `project_name`,
`platform_name`, and `series_key`.

## Source Mapping

Use these default mappings unless live OpenSearch schema inspection shows a
better source grain.

| Source index | Graphiti source grain | Episode type | Saga candidate | Notes |
| --- | --- | --- | --- | --- |
| `emails` | one email message or reviewed email-thread packet | `json` or `text` | `EmailThread` by conversation/thread ID | Preserve all mail IDs and participants in metadata. |
| `transcripts` | one meeting transcript or reviewed section | `text` | `MeetingSeries` or `MeetingOccurrence` | Long transcripts may need chunked episodes with saga ordering. |
| `chunks` | one source chunk | `text` | transcript/email saga if source-linked | Mixed-source index; preserve `source`, sequence, and links. |
| `email_attachments` | one extracted attachment or reviewed attachment section | `text` | parent email/thread saga when available | Preserve extraction method/status and attachment IDs. |
| `calendar_events` | one calendar event | `json` or `text` | `MeetingSeries` by series key/title | Join to transcripts only with explicit or reviewable match confidence. |
| `project_registry` | seed manifest episode plus native seeds | `json` | optional program/project saga only if useful | Registry markers are matching rules, not typed relations by themselves. |

## Project And Platform Matching

- Treat `project_registry` as the current seed authority for curated programs
  and projects.
- Treat registry markers as alias and matching evidence, not as graph relation
  types.
- Add curated platform/vendor aliases for high-signal concepts missing or
  underspecified in the registry: Defender, CrowdStrike, Forescout, Medigate,
  Purview, Varonis, Forecight, Zscaler, Darktrace, Imprivata, Deloitte,
  Microsoft, Palo Alto/Prisma, FairWarning, and Securin.
- Store match evidence on episode metadata before extraction: confidence,
  matched marker, marker type, matched field, ambiguity flags, and candidate
  entities.
- Keep ambiguous concepts split until evidence supports merging. In particular,
  do not merge Forecight with Forescout, and do not collapse vendor/product/project
  roles for CrowdStrike, Zscaler, Darktrace, Resolver, or Securin.

## Implementation Phases

### 1. Provenance Foundation

Goal: source traceability survives every native Graphiti path.

Required changes:

- Add optional `episode_metadata` to `Graphiti.add_episode(...)`.
- Add optional `episode_metadata` to `RawEpisode`.
- Persist `episode_metadata` in single and bulk `EpisodicNode` save paths.
- Return `episode_metadata` from single, bulk, group, entity-linked, retrieve,
  and search episode read paths.
- Wire the Neo4j path first because Neo4j is the v1 target. Keep provider
  fallbacks coherent where low-risk.
- Add basic episode metadata filtering for top-level scalar fields.

Acceptance:

- A single episode metadata round trip passes.
- A bulk episode metadata round trip passes.
- Episode search and retrieval return metadata.
- The pilot can answer "which OpenSearch record produced this episode?" without
  querying OpenSearch.

### 2. Native Ontology Layer

Goal: the exec-EA model is exposed through Graphiti's public extension points.

Required changes:

- Define Pydantic entity models for core durable work objects and observations.
- Define Pydantic edge models for high-value operational relations.
- Define a first-pass `edge_type_map` for project/platform/vendor,
  person/obligation, meeting/occurrence, document/metric, decision/project, and
  blocker/project relations.
- Keep the ontology in an exec-EA package/module rather than embedding domain
  classes into generic Graphiti internals.

Acceptance:

- `validate_entity_types` accepts the custom entity models.
- Typed node and edge filters retrieve the expected labels and relation names.
- Extraction can still fall back to generic `Entity`/generic facts where recall
  matters.

### 3. Seed Manifests And Native Seed Loader

Goal: curated durable objects exist as native Graphiti graph objects before
source extraction depends on them.

Required changes:

- Create seed manifests for programs, projects, promoted platforms, vendors,
  organizations/teams, important people/aliases, and meeting series.
- Seed using native `EntityNode`/`EntityEdge` or `add_triplet(...)` with
  deterministic UUIDs.
- Use optional `project_seed` or `seed_manifest` episodes to preserve source
  evidence for seeded objects.
- Keep import bookkeeping separate from retrieval truth.

Acceptance:

- Program/project hierarchy from `project_registry` is represented natively.
- Promoted platforms/vendors are separate from projects.
- Cross-over names have separate project/platform/vendor-product/vendor nodes
  with shared `concept_key` metadata and typed links such as
  `PROJECT_INVOLVES_PLATFORM`, `PROJECT_HAS_VENDOR`, and
  `VENDOR_PROVIDES_PLATFORM`.
- Seeded objects have deterministic IDs and provenance-backed attributes.

### 4. OpenSearch Importer

Goal: source records become Graphiti-native episodes and facts.

Required changes:

- Add read-only OpenSearch adapters.
- Re-read mappings and representative samples before implementation.
- Normalize each index into a common source-record model.
- Generate deterministic episode UUIDs from source kind and stable source IDs.
- Match projects/platforms/series before ingestion and attach match metadata.
- Import through `add_episode(...)` or reviewed `add_episode_bulk(...)` with
  custom entity and edge types, not by writing a parallel graph outside Graphiti.

Acceptance:

- Importing the same fixture twice is idempotent.
- Source IDs are traceable from Graphiti episodes.
- Project/platform queries work without querying OpenSearch.

### 5. Observation Extraction

Goal: operational state is modeled as Graphiti entities and temporal facts.

Required changes:

- Extract obligations, approvals, decisions, blockers, statuses, metrics,
  deliverable statuses, carry-forwards, risks, dependencies, renewals, and
  procurement events as custom entity nodes where they have durable identity.
- Connect observations to people, projects, meetings, documents, platforms, and
  source episodes through typed edges.
- Use Graphiti temporal edge validity for changes over time. Do not overwrite old
  facts when newer evidence supersedes them.

Acceptance:

- Queries can retrieve current and historical operational state from Graphiti.
- Later evidence invalidates or supersedes older facts instead of deleting
  history.
- Ambiguous owners, blockers, or project matches remain visible rather than being
  silently merged.

### 6. Pilot Ingestion

Goal: validate graph quality before broad backfill.

Pilot slice:

- One email thread.
- One transcript with chunks.
- One attachment set.
- Related calendar events.
- Relevant program/project/platform/vendor/person/meeting seeds.

Pilot report must include:

- Episode, entity, edge, saga, and seed counts.
- Matched and unmatched source records.
- Ambiguous matches and why they remain split.
- Provenance coverage.
- Typed retrieval examples.
- Graph quality notes and ontology adjustments.

### 7. Backfill

Goal: broader ingestion only after the pilot proves the model.

Rules:

- Do not broad-backfill until provenance, seeds, matching, and typed retrieval are
  working.
- Use single-episode ingestion when ordering and temporal invalidation are
  important.
- Use `add_episode_bulk` for empty-graph loads, reviewed batches, or source lanes
  where batch ordering and attribution are acceptable.
- Keep ingestion runs resumable and idempotent.

## Test Plan

Unit tests:

- `episode_metadata` single save/parse round trip.
- `episode_metadata` bulk save/parse round trip.
- Episode metadata return from `get_by_uuid`, `get_by_uuids`,
  `get_by_group_ids`, entity-linked retrieval, and search.
- Top-level metadata filter construction for supported scalar fields.
- Deterministic UUID generation.
- OpenSearch record normalization fixtures.
- Marker matching for phrase, domain, person, and subject markers.
- Ambiguity handling for Forecight/Forescout and CrowdStrike/Defender.
- Custom entity model validation avoids protected Graphiti fields.
- Edge type map contains high-value signatures and does not explode into
  one-off names.

Integration tests:

- Neo4j metadata persistence and retrieval.
- Neo4j metadata-filtered episode retrieval.
- Seed creation for programs/projects/platforms/vendors.
- Saga creation and ordered episode linking for an email thread or meeting
  series.
- Pilot ingestion from local fixtures.

Manual acceptance:

- Run pilot import against OpenSearch.
- Confirm Graphiti contains native people, projects, platforms, meetings,
  documents, and observations.
- Confirm source episodes trace back to OpenSearch IDs.
- Confirm typed project/platform/obligation/decision queries work without
  querying OpenSearch.
- Confirm ambiguous matches are visible, not silently merged.
- Confirm no side database is required for normal reasoning over transformed
  memory.

## Drift Checks

Before implementing any new feature, ask:

- Is this represented as an episode, entity, edge, saga, search filter, or driver
  capability inside Graphiti?
- If it is outside Graphiti, is it only operational infrastructure?
- Can the same query be answered from Graphiti without querying OpenSearch?
- Does every derived object trace back to an episode or seed with provenance?
- Are project/platform/vendor/person ambiguities preserved until evidence is
  strong enough to merge?
- Are we using custom types and `edge_type_map` to guide Graphiti, rather than
  replacing Graphiti extraction with a separate knowledge system?

## Assumptions

- OpenSearch is the only source for this phase.
- Graphiti is the system of record for transformed memory graph data.
- OpenSearch remains the source archive for re-import and audit.
- Neo4j is the primary target for v1.
- Source records use existing Graphiti episode types in v1.
- Do not broad-backfill until pilot graph quality is reviewed.
- Do not solve full person identity resolution in v1; preserve aliases and merge
  only high-confidence cases.
