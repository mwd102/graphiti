"""Deterministic observation candidate extraction for Exec-EA pilot slices."""

import hashlib
import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.exec_ea.opensearch import OpenSearchClient, SourceRecord
from graphiti_core.exec_ea.pilot import (
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
from graphiti_core.nodes import EntityNode
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
    project_seed_ids: list[str] = []
    series_seed_ids: list[str] = []


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
    """Extract deterministic operational observation candidates from a source record."""

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
                )
            )

        if len(candidates) >= max_candidates:
            break

    return candidates


def build_observation_graph(
    records: list[SourceRecord],
    group_id: str,
    seed_nodes: dict[str, EntityNode],
    *,
    created_at: datetime | None = None,
) -> ObservationGraph:
    """Build native Graphiti observation nodes and typed edges for source records."""

    now = created_at or utc_now()
    candidates = [
        candidate for record in records for candidate in extract_observation_candidates(record)
    ]
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
    """Import deterministic CSM Exec observation candidates into Graphiti."""

    opensearch_client = client or OpenSearchClient()
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
    observation_graph = build_observation_graph(
        records, group_id, seed_nodes, created_at=created_at
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
            'extraction_method': 'deterministic_cue_v1',
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
            'extraction_method': 'deterministic_cue_v1',
        },
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
