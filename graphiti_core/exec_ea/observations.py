"""Observation extraction for Exec-EA pilot slices.

The deterministic cue extractor in this module is retained for cheap audits and
regression probes. Production observation extraction should use the LLM-backed
structured extractor so Graphiti, not token matching, decides which operational
facts are durable enough to model.
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.exec_ea.opensearch import OpenSearchClient, SourceRecord
from graphiti_core.exec_ea.pilot import (
    CSM_EXEC_SERIES_KEY,
    CSMExecPilotConfig,
    build_pilot_episode_nodes,
    build_pilot_episodic_edges,
    deterministic_episode_uuid,
    fetch_csm_exec_pilot_records,
)
from graphiti_core.exec_ea.seeds import (
    DEFAULT_SEED_MANIFEST,
    SeedManifest,
    build_seed_nodes,
    seed_exec_ea_graph,
    seed_uuid,
)
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.nodes import EntityNode
from graphiti_core.prompts.models import Message
from graphiti_core.utils.bulk_utils import add_nodes_and_edges_bulk
from graphiti_core.utils.datetime_utils import utc_now

ObservationType = Literal[
    'ActionItem',
    'Blocker',
    'Decision',
    'MeetingCarryForward',
    'Obligation',
    'ProjectStatus',
]

LLM_OBSERVATION_EXTRACTION_METHOD = 'llm_observation_v1'
DETERMINISTIC_OBSERVATION_EXTRACTION_METHOD = 'deterministic_cue_v1'
CSM_EXEC_SERIES_SEED_ID = 'series:csm-executive-meeting'


OBSERVATION_CUE_PATTERNS: tuple[tuple[ObservationType, str, float], ...] = (
    ('MeetingCarryForward', r'\b(carry forward|carried forward|unresolved|parking lot)\b', 0.82),
    ('Obligation', r"\b(i will|i'll|i can|i need to|i committed|committed to)\b", 0.82),
    ('ActionItem', r'\b(action item|follow up|next step|need to|needs to|to do|will send)\b', 0.75),
    ('Decision', r'\b(decided|decision|agreed|confirmed|approved|we will|we are going to)\b', 0.78),
    (
        'Blocker',
        r'\b(blocked|blocker|blocking|waiting on|stuck|delay|delayed|risk|concern)\b',
        0.75,
    ),
    ('ProjectStatus', r'\b(on track|going well|status|at risk|delayed|complete|completed)\b', 0.72),
)

OWNER_SEED_PATTERNS = {
    'person:michael-dobson': re.compile(r'\b(dobson,\s*michael|michael|mike d)\b', re.I),
    'person:derek-lucas': re.compile(r'\b(lucas,\s*derek|derek)\b', re.I),
    'person:jamie-ross': re.compile(r'\b(ross,\s*jamie|jamie ross|jamie)\b', re.I),
    'person:jennifer-dury': re.compile(r'\b(dury,\s*jennifer|jennifer|jen)\b', re.I),
    'person:ali-deheshi': re.compile(r'\b(deheshi,\s*ali|ali)\b', re.I),
}


class ObservationCandidate(BaseModel):
    """A source-backed operational observation candidate."""

    observation_id: str
    observation_type: ObservationType
    text: str
    cue: str
    confidence: float
    source_index: str
    source_id: str
    source_kind: str
    reference_time: datetime
    owner_seed_id: str | None = None
    project_seed_ids: list[str] = Field(default_factory=list)
    series_seed_ids: list[str] = Field(default_factory=list)
    extraction_method: str = DETERMINISTIC_OBSERVATION_EXTRACTION_METHOD
    evidence_text: str | None = None


class LLMExtractedObservation(BaseModel):
    """Structured observation returned by the production LLM extractor."""

    observation_type: ObservationType = Field(
        ...,
        description='Operational observation class. Use the closest Exec-EA ontology type.',
    )
    text: str = Field(
        ...,
        description='Concise observation text suitable for a durable graph node.',
    )
    evidence_text: str = Field(
        ...,
        description='Short exact quote copied from the source text supporting the observation.',
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description='Confidence that this is a durable operational observation.',
    )
    owner_seed_id: str | None = Field(
        default=None,
        description='Seed id for the person who owns or is accountable for the observation.',
    )
    project_seed_ids: list[str] = Field(
        default_factory=list,
        description='Specific work-context seed ids. Prefer projects/platforms over broad programs.',
    )
    series_seed_ids: list[str] = Field(
        default_factory=list,
        description='Meeting-series seed ids explicitly scoped by the source.',
    )


class LLMObservationExtraction(BaseModel):
    """Structured response for production observation extraction."""

    observations: list[LLMExtractedObservation] = Field(default_factory=list)


class ObservationGraph(BaseModel):
    """Native Graphiti graph objects for observation candidates."""

    candidates: list[ObservationCandidate]
    nodes: list[EntityNode]
    entity_edges: list[EntityEdge]
    episodic_edges: list[EpisodicEdge]


class ObservationImportResult(BaseModel):
    """Summary of a CSM observation import run."""

    group_id: str
    source_record_count: int
    candidate_count: int
    observation_node_uuids: list[str]
    entity_edge_uuids: list[str]
    episodic_edge_uuids: list[str]


def extract_observation_candidates(
    record: SourceRecord,
    *,
    max_candidates: int = 6,
) -> list[ObservationCandidate]:
    """Extract audit-only deterministic observation candidates from a source record."""

    candidates: list[ObservationCandidate] = []
    seen: set[tuple[str, str]] = set()

    for snippet in _candidate_snippets(record.content):
        for observation_type, pattern, confidence in OBSERVATION_CUE_PATTERNS:
            match = re.search(pattern, snippet, re.I)
            if match is None:
                continue

            candidate_key = (observation_type, _normalized_text(snippet))
            if candidate_key in seen:
                continue
            seen.add(candidate_key)

            candidates.append(
                ObservationCandidate(
                    observation_id=_observation_id(record, observation_type, snippet),
                    observation_type=observation_type,
                    text=snippet,
                    cue=match.group(1),
                    confidence=confidence,
                    source_index=record.source_index,
                    source_id=record.source_id,
                    source_kind=record.source_kind,
                    reference_time=record.reference_time,
                    owner_seed_id=_owner_seed_id(snippet),
                    project_seed_ids=_matched_seed_ids(record, 'project_matches'),
                    series_seed_ids=_matched_seed_ids(record, 'series_matches'),
                    extraction_method=DETERMINISTIC_OBSERVATION_EXTRACTION_METHOD,
                )
            )

        if len(candidates) >= max_candidates:
            break

    return candidates


async def extract_observation_candidates_with_llm(
    record: SourceRecord,
    llm_client: LLMClient,
    *,
    max_observations: int = 8,
    group_id: str | None = None,
) -> list[ObservationCandidate]:
    """Extract production observation candidates with structured LLM output."""

    messages = observation_extraction_messages(record, max_observations=max_observations)
    response = await llm_client.generate_response(
        messages,
        response_model=LLMObservationExtraction,
        max_tokens=4096,
        group_id=group_id,
        prompt_name='exec_ea.extract_observations',
    )
    extraction = LLMObservationExtraction(**response)
    candidates: list[ObservationCandidate] = []
    for observation in extraction.observations[:max_observations]:
        candidate = _llm_observation_candidate(record, observation)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def observation_extraction_messages(
    record: SourceRecord,
    *,
    max_observations: int = 8,
) -> list[Message]:
    """Build the production observation extraction prompt for a source record."""

    seed_context = _seed_match_context(record)
    source_payload = {
        'source_index': record.source_index,
        'source_id': record.source_id,
        'source_kind': record.source_kind,
        'title': record.title,
        'reference_time': record.reference_time.isoformat(),
        'metadata': {
            key: value
            for key, value in record.metadata.items()
            if key
            in {
                'pilot_slice',
                'series_key',
                'series_name',
                'transcript_id',
                'calendar_event_id',
                'chunk_id',
            }
        },
        'content': _truncate_source_content(record.content),
    }

    return [
        Message(
            role='system',
            content=(
                'You are an executive-assistant knowledge graph observation extractor. '
                'Extract durable operational observations from source evidence for Graphiti. '
                'Use semantic judgment, not keyword matching.'
            ),
        ),
        Message(
            role='user',
            content=f"""
<SOURCE_RECORD>
{json.dumps(source_payload, default=str, indent=2)}
</SOURCE_RECORD>

<AVAILABLE_SEEDS>
{json.dumps(seed_context, default=str, indent=2)}
</AVAILABLE_SEEDS>

# TASK
Extract at most {max_observations} source-backed operational observations that should become
native graph nodes. Return no observation when the source is only agenda framing,
meeting logistics, social chatter, jokes, transcription filler, or weak status preamble.

# OBSERVATION TYPES
- Obligation: a person commits to or is accountable for doing something.
- ActionItem: a concrete follow-up or next step, assigned or assignable.
- Decision: a decision, approval, agreement, or direction that changes work.
- Blocker: a delay, dependency, risk, waiting state, or impediment affecting work.
- ProjectStatus: a dated status/health update with substance, not merely the word "status".
- MeetingCarryForward: an unresolved meeting item explicitly carried into another occurrence.

# SEED RULES
- Use only seed ids from AVAILABLE_SEEDS.
- Prefer specific Project, Platform, VendorProduct, or Workstream context over broad Program context.
- Include a Program seed only when the observation is explicitly program-level.
- For CSM Exec sources, use series:{CSM_EXEC_SERIES_SEED_ID.split(':', 1)[1]} only when
  the observation is scoped to this meeting series.
- Do not create a carry-forward from "parking lot" unless it clearly means an agenda parking-lot item,
  not a physical location.
- Treat "need to", "to do", "I'll", "I can", "we will", and bare "status" as weak cues.
  Extract them only when the source also provides an owner, object of work, and concrete outcome.

# OUTPUT
For each observation, include concise text, exact evidence_text copied from SOURCE_RECORD content,
confidence, and seed ids.
If no durable operational observation exists, return an empty observations list.
""",
        ),
    ]


def build_observation_graph(
    records: list[SourceRecord],
    group_id: str,
    seed_nodes: dict[str, EntityNode],
    *,
    created_at: datetime | None = None,
) -> ObservationGraph:
    """Build native Graphiti observation nodes from audit-only deterministic candidates."""

    candidates = [
        candidate for record in records for candidate in extract_observation_candidates(record)
    ]
    return build_observation_graph_from_candidates(
        records,
        candidates,
        group_id,
        seed_nodes,
        created_at=created_at,
    )


def build_observation_graph_from_candidates(
    records: list[SourceRecord],
    candidates: list[ObservationCandidate],
    group_id: str,
    seed_nodes: dict[str, EntityNode],
    *,
    created_at: datetime | None = None,
) -> ObservationGraph:
    """Build native Graphiti observation nodes and typed edges from candidates."""

    now = created_at or utc_now()
    nodes = [_candidate_node(candidate, group_id, now) for candidate in candidates]
    nodes_by_observation_id = {
        candidate.observation_id: node for candidate, node in zip(candidates, nodes, strict=True)
    }

    entity_edges: list[EntityEdge] = []
    episodic_edges: list[EpisodicEdge] = []
    seen_entity_edges: set[str] = set()
    seen_episodic_edges: set[str] = set()

    records_by_source = {(record.source_index, record.source_id): record for record in records}

    for candidate in candidates:
        observation_node = nodes_by_observation_id[candidate.observation_id]
        record = records_by_source[(candidate.source_index, candidate.source_id)]
        episode_uuid = deterministic_episode_uuid(group_id, record)
        mention_uuid = seed_uuid(
            group_id, 'observation_mentions', episode_uuid, observation_node.uuid
        )
        if mention_uuid not in seen_episodic_edges:
            seen_episodic_edges.add(mention_uuid)
            episodic_edges.append(
                EpisodicEdge(
                    uuid=mention_uuid,
                    group_id=group_id,
                    source_node_uuid=episode_uuid,
                    target_node_uuid=observation_node.uuid,
                    created_at=now,
                )
            )

        for edge in _candidate_entity_edges(candidate, observation_node, seed_nodes, group_id, now):
            if edge.uuid in seen_entity_edges:
                continue
            seen_entity_edges.add(edge.uuid)
            entity_edges.append(edge)

    return ObservationGraph(
        candidates=candidates,
        nodes=nodes,
        entity_edges=entity_edges,
        episodic_edges=episodic_edges,
    )


async def import_csm_exec_observations(
    driver: GraphDriver,
    embedder: EmbedderClient,
    group_id: str,
    client: OpenSearchClient | None = None,
    config: CSMExecPilotConfig | None = None,
    manifest: SeedManifest = DEFAULT_SEED_MANIFEST,
    *,
    load_seed_graph: bool = True,
    load_source_episodes: bool = True,
    created_at: datetime | None = None,
) -> ObservationImportResult:
    """Import audit-only deterministic CSM Exec observation candidates into Graphiti."""

    return await _import_csm_exec_observation_candidates(
        driver,
        embedder,
        group_id,
        client=client,
        config=config,
        manifest=manifest,
        load_seed_graph=load_seed_graph,
        load_source_episodes=load_source_episodes,
        created_at=created_at,
        candidates=None,
    )


async def import_csm_exec_observations_with_llm(
    driver: GraphDriver,
    embedder: EmbedderClient,
    llm_client: LLMClient,
    group_id: str,
    client: OpenSearchClient | None = None,
    config: CSMExecPilotConfig | None = None,
    manifest: SeedManifest = DEFAULT_SEED_MANIFEST,
    *,
    load_seed_graph: bool = True,
    load_source_episodes: bool = True,
    allow_full_import: bool = False,
    created_at: datetime | None = None,
) -> ObservationImportResult:
    """Import production LLM-extracted CSM Exec observations into Graphiti."""

    opensearch_client = client or OpenSearchClient()
    records = fetch_csm_exec_pilot_records(opensearch_client, config, manifest)
    if len(records) > 50 and not allow_full_import:
        raise ValueError(
            'Refusing full CSM Exec observation import without allow_full_import=True. '
            'Use a bounded CSMExecPilotConfig for review runs.'
        )

    candidates: list[ObservationCandidate] = []
    for record in records:
        candidates.extend(
            await extract_observation_candidates_with_llm(record, llm_client, group_id=group_id)
        )

    return await _import_csm_exec_observation_candidates(
        driver,
        embedder,
        group_id,
        client=opensearch_client,
        config=config,
        manifest=manifest,
        load_seed_graph=load_seed_graph,
        load_source_episodes=load_source_episodes,
        created_at=created_at,
        candidates=candidates,
        records=records,
    )


async def _import_csm_exec_observation_candidates(
    driver: GraphDriver,
    embedder: EmbedderClient,
    group_id: str,
    *,
    client: OpenSearchClient | None,
    config: CSMExecPilotConfig | None,
    manifest: SeedManifest,
    load_seed_graph: bool,
    load_source_episodes: bool,
    created_at: datetime | None,
    candidates: list[ObservationCandidate] | None,
    records: list[SourceRecord] | None = None,
) -> ObservationImportResult:
    opensearch_client = client or OpenSearchClient()
    if records is None:
        records = fetch_csm_exec_pilot_records(opensearch_client, config, manifest)

    if load_seed_graph:
        await seed_exec_ea_graph(driver, embedder, group_id, manifest, created_at=created_at)

    seed_nodes = build_seed_nodes(manifest, group_id, created_at)
    source_episodes = (
        build_pilot_episode_nodes(records, group_id, created_at=created_at)
        if load_source_episodes
        else []
    )
    source_seed_mentions = (
        build_pilot_episodic_edges(
            records, source_episodes, seed_nodes, group_id, created_at=created_at
        )
        if load_source_episodes
        else []
    )
    observation_graph = build_observation_graph_from_candidates(
        records,
        candidates
        if candidates is not None
        else [
            candidate for record in records for candidate in extract_observation_candidates(record)
        ],
        group_id,
        seed_nodes,
        created_at=created_at,
    )

    await add_nodes_and_edges_bulk(
        driver,
        source_episodes,
        source_seed_mentions + observation_graph.episodic_edges,
        observation_graph.nodes,
        observation_graph.entity_edges,
        embedder,
    )

    return ObservationImportResult(
        group_id=group_id,
        source_record_count=len(records),
        candidate_count=len(observation_graph.candidates),
        observation_node_uuids=[node.uuid for node in observation_graph.nodes],
        entity_edge_uuids=[edge.uuid for edge in observation_graph.entity_edges],
        episodic_edge_uuids=[edge.uuid for edge in observation_graph.episodic_edges],
    )


def _candidate_node(
    candidate: ObservationCandidate, group_id: str, created_at: datetime
) -> EntityNode:
    return EntityNode(
        uuid=seed_uuid(group_id, 'observation', candidate.observation_id),
        name=_observation_name(candidate),
        group_id=group_id,
        labels=[candidate.observation_type],
        summary=candidate.text,
        attributes={
            'observation_id': candidate.observation_id,
            'observation_type': candidate.observation_type,
            'observation_text': candidate.text,
            'observation_status': 'candidate',
            'cue': candidate.cue,
            'confidence': candidate.confidence,
            'source_index': candidate.source_index,
            'source_id': candidate.source_id,
            'source_kind': candidate.source_kind,
            'reference_time': candidate.reference_time.isoformat(),
            'extraction_method': candidate.extraction_method,
            **({'evidence_text': candidate.evidence_text} if candidate.evidence_text else {}),
            **({'owner_seed_id': candidate.owner_seed_id} if candidate.owner_seed_id else {}),
        },
        created_at=created_at,
    )


def _candidate_entity_edges(
    candidate: ObservationCandidate,
    observation_node: EntityNode,
    seed_nodes: dict[str, EntityNode],
    group_id: str,
    created_at: datetime,
) -> list[EntityEdge]:
    edges: list[EntityEdge] = []

    if candidate.observation_type == 'Obligation' and candidate.owner_seed_id:
        person_node = seed_nodes.get(candidate.owner_seed_id)
        if person_node is not None:
            edges.append(
                _entity_edge(
                    group_id,
                    created_at,
                    person_node.uuid,
                    observation_node.uuid,
                    'PERSON_OWNS_OBLIGATION',
                    f'{person_node.name} owns obligation candidate: {candidate.text}',
                    candidate,
                )
            )

    for project_seed_id in candidate.project_seed_ids[:3]:
        project_node = seed_nodes.get(project_seed_id)
        if project_node is None:
            continue

        if candidate.observation_type == 'ActionItem':
            edges.append(
                _entity_edge(
                    group_id,
                    created_at,
                    project_node.uuid,
                    observation_node.uuid,
                    'PROJECT_HAS_ACTION_ITEM',
                    f'{project_node.name} has action item candidate: {candidate.text}',
                    candidate,
                )
            )
        elif candidate.observation_type == 'Decision':
            edges.append(
                _entity_edge(
                    group_id,
                    created_at,
                    project_node.uuid,
                    observation_node.uuid,
                    'PROJECT_HAS_DECISION',
                    f'{project_node.name} has decision candidate: {candidate.text}',
                    candidate,
                )
            )
        elif candidate.observation_type == 'Blocker':
            edges.append(
                _entity_edge(
                    group_id,
                    created_at,
                    observation_node.uuid,
                    project_node.uuid,
                    'BLOCKER_BLOCKS_PROJECT',
                    f'Blocker candidate affects {project_node.name}: {candidate.text}',
                    candidate,
                )
            )
        elif candidate.observation_type == 'ProjectStatus':
            edges.append(
                _entity_edge(
                    group_id,
                    created_at,
                    project_node.uuid,
                    observation_node.uuid,
                    'PROJECT_HAS_STATUS',
                    f'{project_node.name} has status candidate: {candidate.text}',
                    candidate,
                )
            )

    if candidate.observation_type == 'MeetingCarryForward':
        for series_seed_id in candidate.series_seed_ids[:2]:
            series_node = seed_nodes.get(series_seed_id)
            if series_node is None:
                continue
            edges.append(
                _entity_edge(
                    group_id,
                    created_at,
                    series_node.uuid,
                    observation_node.uuid,
                    'MEETING_SERIES_HAS_CARRY_FORWARD',
                    f'{series_node.name} has carry-forward candidate: {candidate.text}',
                    candidate,
                )
            )

    return edges


def _entity_edge(
    group_id: str,
    created_at: datetime,
    source_node_uuid: str,
    target_node_uuid: str,
    name: str,
    fact: str,
    candidate: ObservationCandidate,
) -> EntityEdge:
    edge_uuid = seed_uuid(
        group_id,
        'observation_edge',
        candidate.observation_id,
        source_node_uuid,
        name,
        target_node_uuid,
    )
    return EntityEdge(
        uuid=edge_uuid,
        group_id=group_id,
        source_node_uuid=source_node_uuid,
        target_node_uuid=target_node_uuid,
        created_at=created_at,
        name=name,
        fact=fact,
        valid_at=candidate.reference_time,
        reference_time=candidate.reference_time,
        attributes={
            'observation_id': candidate.observation_id,
            'confidence': candidate.confidence,
            'extraction_method': candidate.extraction_method,
        },
    )


def _llm_observation_candidate(
    record: SourceRecord,
    observation: LLMExtractedObservation,
) -> ObservationCandidate | None:
    text = _truncate_snippet(observation.text)
    evidence_text = _truncate_snippet(observation.evidence_text)
    if not evidence_text or not _source_contains_evidence(record, evidence_text):
        return None

    confidence = max(0.0, min(1.0, observation.confidence))
    return ObservationCandidate(
        observation_id=_observation_id(record, observation.observation_type, evidence_text),
        observation_type=observation.observation_type,
        text=text,
        cue='llm',
        confidence=confidence,
        source_index=record.source_index,
        source_id=record.source_id,
        source_kind=record.source_kind,
        reference_time=record.reference_time,
        owner_seed_id=_validated_owner_seed_id(record, observation.owner_seed_id),
        project_seed_ids=_validated_work_seed_ids(record, observation.project_seed_ids),
        series_seed_ids=_validated_series_seed_ids(record, observation.series_seed_ids),
        extraction_method=LLM_OBSERVATION_EXTRACTION_METHOD,
        evidence_text=evidence_text,
    )


def _candidate_snippets(content: str) -> list[str]:
    snippets: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped or stripped.endswith(':'):
            continue
        stripped = _extract_evidence_text(stripped)
        if not stripped:
            continue
        snippets.extend(
            snippet.strip()
            for snippet in re.split(r'(?<=[.!?])\s+', stripped)
            if len(snippet.strip()) >= 24
        )

    return [_truncate_snippet(snippet) for snippet in snippets]


def _truncate_source_content(content: str, max_chars: int = 8000) -> str:
    normalized = re.sub(r'\s+', ' ', content).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + '...'


def _source_contains_evidence(record: SourceRecord, evidence_text: str) -> bool:
    return _normalized_text(evidence_text) in _normalized_text(record.content)


def _seed_match_context(record: SourceRecord) -> list[dict[str, Any]]:
    context: list[dict[str, Any]] = []
    for metadata_key in (
        'person_matches',
        'project_matches',
        'platform_matches',
        'vendor_matches',
        'series_matches',
    ):
        for match in record.metadata.get(metadata_key) or []:
            if not isinstance(match, dict):
                continue
            context.append(
                {
                    'seed_id': match.get('seed_id'),
                    'entity_type': match.get('entity_type'),
                    'name': match.get('name'),
                    'seed_role': match.get('seed_role'),
                    'match_field': match.get('match_field'),
                    'confidence': match.get('confidence'),
                    'bucket': metadata_key,
                }
            )
    return context


def _seed_matches_by_id(record: SourceRecord, metadata_key: str) -> dict[str, dict[str, Any]]:
    matches: dict[str, dict[str, Any]] = {}
    for match in record.metadata.get(metadata_key) or []:
        if not isinstance(match, dict):
            continue
        seed_id = match.get('seed_id')
        if seed_id is None:
            continue
        matches[str(seed_id)] = match
    return matches


def _validated_owner_seed_id(record: SourceRecord, owner_seed_id: str | None) -> str | None:
    if owner_seed_id is None:
        return None
    owner_matches = _seed_matches_by_id(record, 'person_matches')
    return owner_seed_id if owner_seed_id in owner_matches else None


def _validated_work_seed_ids(record: SourceRecord, seed_ids: list[str]) -> list[str]:
    project_matches = _seed_matches_by_id(record, 'project_matches')
    platform_matches = _seed_matches_by_id(record, 'platform_matches')
    allowed_matches = {**project_matches, **platform_matches}
    valid_seed_ids = [seed_id for seed_id in seed_ids if seed_id in allowed_matches]

    specific_seed_ids = [
        seed_id
        for seed_id in valid_seed_ids
        if allowed_matches[seed_id].get('entity_type') != 'Program'
    ]
    if specific_seed_ids:
        return _dedupe_preserve_order(specific_seed_ids)[:3]
    return _dedupe_preserve_order(valid_seed_ids)[:2]


def _validated_series_seed_ids(record: SourceRecord, seed_ids: list[str]) -> list[str]:
    series_matches = _seed_matches_by_id(record, 'series_matches')
    if record.metadata.get('series_key') == CSM_EXEC_SERIES_KEY:
        return [CSM_EXEC_SERIES_SEED_ID] if CSM_EXEC_SERIES_SEED_ID in series_matches else []

    valid_seed_ids = [seed_id for seed_id in seed_ids if seed_id in series_matches]
    return _dedupe_preserve_order(valid_seed_ids)[:2]


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _extract_evidence_text(line: str) -> str:
    evidence_prefixes = (
        'Agenda:',
        'Body:',
        'Content:',
        'Extracted content:',
        'Transcript:',
    )
    skipped_prefixes = (
        'Attendees:',
        'Cc:',
        'Date:',
        'End:',
        'Filename:',
        'Folder:',
        'From:',
        'Location:',
        'Organizer:',
        'Participants:',
        'Received:',
        'Sequence:',
        'Source:',
        'Speakers:',
        'Start:',
        'Subject:',
        'Title:',
        'To:',
        'Topics:',
    )

    for prefix in evidence_prefixes:
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    if any(line.startswith(prefix) for prefix in skipped_prefixes):
        return ''
    return line


def _truncate_snippet(snippet: str, max_chars: int = 420) -> str:
    normalized = re.sub(r'\s+', ' ', snippet).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + '...'


def _observation_id(record: SourceRecord, observation_type: str, text: str) -> str:
    digest = hashlib.sha1(_normalized_text(text).encode('utf-8')).hexdigest()[:16]
    return ':'.join(
        [
            record.source_index,
            record.source_kind,
            record.source_id,
            observation_type,
            digest,
        ]
    )


def _observation_name(candidate: ObservationCandidate) -> str:
    prefix = candidate.observation_type
    text = candidate.text
    max_text_chars = 90 - len(prefix)
    return f'{prefix}: {text[:max_text_chars].rstrip()}'


def _owner_seed_id(text: str) -> str | None:
    for seed_id, pattern in OWNER_SEED_PATTERNS.items():
        if pattern.search(text):
            return seed_id
    return None


def _matched_seed_ids(record: SourceRecord, metadata_key: str) -> list[str]:
    seed_ids: list[str] = []
    for match in record.metadata.get(metadata_key) or []:
        if not isinstance(match, dict):
            continue
        seed_id = match.get('seed_id')
        if seed_id is not None:
            seed_ids.append(str(seed_id))
    return seed_ids


def _normalized_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip().lower()
