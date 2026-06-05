"""Pilot source-slice import helpers for Exec-EA Graphiti ingestion."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.edges import EpisodicEdge
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.exec_ea.matching import source_record_with_seed_matches
from graphiti_core.exec_ea.opensearch import OpenSearchClient, SourceRecord
from graphiti_core.exec_ea.seeds import (
    DEFAULT_SEED_MANIFEST,
    SeedManifest,
    build_seed_nodes,
    seed_exec_ea_graph,
    seed_uuid,
)
from graphiti_core.nodes import EntityNode, EpisodicNode
from graphiti_core.utils.bulk_utils import add_nodes_and_edges_bulk
from graphiti_core.utils.datetime_utils import utc_now

CSM_EXEC_PILOT_SLICE = 'csm_exec_series'
CSM_EXEC_SERIES_NAME = 'CSM Executive Meeting'
CSM_EXEC_SERIES_KEY = 'csm_executive_meeting'


class CSMExecPilotConfig(BaseModel):
    """Fetch limits for the CSM Executive Meeting pilot slice."""

    transcript_limit: int = 18
    calendar_limit: int = 27
    chunk_transcript_limit: int = 3
    chunk_limit: int = 120


class PilotImportResult(BaseModel):
    """Summary of a pilot import run."""

    group_id: str
    pilot_slice: str
    source_record_count: int
    episode_uuids: list[str]
    episodic_edge_uuids: list[str]
    seed_graph_loaded: bool


def deterministic_episode_uuid(group_id: str, record: SourceRecord) -> str:
    """Return a stable episode UUID for a normalized OpenSearch record."""

    return seed_uuid(
        group_id,
        'opensearch_episode',
        record.source_index,
        record.source_kind,
        record.source_id,
    )


def csm_exec_transcripts_query() -> dict[str, Any]:
    """OpenSearch query for CSM Executive Meeting transcript records."""

    return {
        'query': {'match_phrase': {'title': CSM_EXEC_SERIES_NAME}},
        'sort': [{'date': 'asc'}, {'transcript_id': 'asc'}],
    }


def csm_exec_calendar_query() -> dict[str, Any]:
    """OpenSearch query for CSM Executive Meeting calendar records."""

    return {
        'query': {
            'bool': {
                'should': [
                    {'match_phrase': {'title': CSM_EXEC_SERIES_NAME}},
                    {'term': {'series_key': 'csm executive meeting'}},
                ],
                'minimum_should_match': 1,
            }
        },
        'sort': [{'start_time': 'asc'}, {'outlook_event_id': 'asc'}],
    }


def csm_exec_chunks_query(transcript_ids: list[str]) -> dict[str, Any]:
    """OpenSearch query for chunks attached to selected CSM Exec transcripts."""

    return {
        'query': {
            'bool': {
                'filter': [
                    {'terms': {'transcript_id': transcript_ids}},
                    {'match_phrase': {'title': CSM_EXEC_SERIES_NAME}},
                ]
            }
        },
        'sort': [{'transcript_date': 'asc'}, {'transcript_id': 'asc'}, {'sequence': 'asc'}],
    }


def fetch_csm_exec_pilot_records(
    client: OpenSearchClient,
    config: CSMExecPilotConfig | None = None,
    manifest: SeedManifest = DEFAULT_SEED_MANIFEST,
) -> list[SourceRecord]:
    """Fetch, normalize, and seed-match the CSM Executive Meeting pilot slice."""

    pilot_config = config or CSMExecPilotConfig()
    transcript_records = client.fetch_source_records(
        'transcripts', csm_exec_transcripts_query(), size=pilot_config.transcript_limit
    )
    calendar_records = client.fetch_source_records(
        'calendar_events', csm_exec_calendar_query(), size=pilot_config.calendar_limit
    )

    chunk_records: list[SourceRecord] = []
    selected_transcript_ids = [
        record.metadata.get('transcript_id')
        for record in transcript_records[-pilot_config.chunk_transcript_limit :]
    ]
    selected_transcript_ids = [
        str(transcript_id) for transcript_id in selected_transcript_ids if transcript_id
    ]

    if selected_transcript_ids and pilot_config.chunk_limit > 0:
        chunk_records = client.fetch_source_records(
            'chunks',
            csm_exec_chunks_query(selected_transcript_ids),
            size=pilot_config.chunk_limit,
        )

    records = transcript_records + calendar_records + chunk_records
    return [_prepare_csm_exec_record(record, manifest) for record in records]


def build_pilot_episode_nodes(
    records: list[SourceRecord],
    group_id: str,
    *,
    created_at: datetime | None = None,
) -> list[EpisodicNode]:
    """Build deterministic episode nodes for a pilot source-record slice."""

    now = created_at or utc_now()
    return [
        EpisodicNode(
            uuid=deterministic_episode_uuid(group_id, record),
            name=record.title,
            group_id=group_id,
            labels=[],
            source=record.episode_source,
            source_description=f'{record.source_index}:{record.source_kind}',
            content=record.content,
            entity_edges=[],
            valid_at=record.reference_time,
            created_at=now,
            episode_metadata={
                'source_index': record.source_index,
                'source_kind': record.source_kind,
                'source_system': 'opensearch',
                'source_id': record.source_id,
                'source_updated_at': (
                    record.source_updated_at.isoformat() if record.source_updated_at else None
                ),
                **record.metadata,
            },
        )
        for record in records
    ]


def build_pilot_episodic_edges(
    records: list[SourceRecord],
    episodes: list[EpisodicNode],
    seed_nodes: dict[str, EntityNode],
    group_id: str,
    *,
    created_at: datetime | None = None,
) -> list[EpisodicEdge]:
    """Build deterministic MENTIONS edges from pilot episodes to matched seed nodes."""

    now = created_at or utc_now()
    episodic_edges: list[EpisodicEdge] = []
    seen: set[str] = set()

    for record, episode in zip(records, episodes, strict=True):
        for seed_id in _matched_seed_ids(record):
            seed_node = seed_nodes.get(seed_id)
            if seed_node is None:
                continue

            edge_uuid = seed_uuid(group_id, 'pilot_mentions', episode.uuid, seed_id)
            if edge_uuid in seen:
                continue
            seen.add(edge_uuid)

            episodic_edges.append(
                EpisodicEdge(
                    uuid=edge_uuid,
                    group_id=group_id,
                    source_node_uuid=episode.uuid,
                    target_node_uuid=seed_node.uuid,
                    created_at=now,
                )
            )

    return episodic_edges


async def import_csm_exec_pilot(
    driver: GraphDriver,
    embedder: EmbedderClient,
    group_id: str,
    client: OpenSearchClient | None = None,
    config: CSMExecPilotConfig | None = None,
    manifest: SeedManifest = DEFAULT_SEED_MANIFEST,
    *,
    load_seed_graph: bool = True,
    created_at: datetime | None = None,
) -> PilotImportResult:
    """Import the CSM Executive Meeting source slice as Graphiti episodes."""

    opensearch_client = client or OpenSearchClient()
    records = fetch_csm_exec_pilot_records(opensearch_client, config, manifest)

    if load_seed_graph:
        await seed_exec_ea_graph(driver, embedder, group_id, manifest, created_at=created_at)

    seed_nodes = build_seed_nodes(manifest, group_id, created_at)
    episodes = build_pilot_episode_nodes(records, group_id, created_at=created_at)
    episodic_edges = build_pilot_episodic_edges(
        records, episodes, seed_nodes, group_id, created_at=created_at
    )

    await add_nodes_and_edges_bulk(driver, episodes, episodic_edges, [], [], embedder)

    return PilotImportResult(
        group_id=group_id,
        pilot_slice=CSM_EXEC_PILOT_SLICE,
        source_record_count=len(records),
        episode_uuids=[episode.uuid for episode in episodes],
        episodic_edge_uuids=[edge.uuid for edge in episodic_edges],
        seed_graph_loaded=load_seed_graph,
    )


def _prepare_csm_exec_record(record: SourceRecord, manifest: SeedManifest) -> SourceRecord:
    metadata = {
        **record.metadata,
        'pilot_slice': CSM_EXEC_PILOT_SLICE,
        'series_key': CSM_EXEC_SERIES_KEY,
        'series_name': CSM_EXEC_SERIES_NAME,
    }
    prepared = record.model_copy(update={'metadata': metadata})
    return source_record_with_seed_matches(prepared, manifest)


def _matched_seed_ids(record: SourceRecord) -> list[str]:
    seed_ids: list[str] = []
    for metadata_key in (
        'project_matches',
        'platform_matches',
        'vendor_matches',
        'person_matches',
        'series_matches',
        'organization_matches',
        'document_matches',
    ):
        for match in record.metadata.get(metadata_key) or []:
            seed_id = match.get('seed_id') if isinstance(match, dict) else None
            if seed_id:
                seed_ids.append(str(seed_id))

    return seed_ids
