from datetime import datetime, timezone

from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.exec_ea import (
    build_observation_graph,
    build_pilot_episode_nodes,
    build_seed_nodes,
    extract_observation_candidates,
    normalize_hit,
    source_record_with_seed_matches,
)
from graphiti_core.exec_ea.seeds import DEFAULT_SEED_MANIFEST
from graphiti_core.nodes import EntityNode


def _matched_record():
    record = normalize_hit(
        {
            '_index': 'chunks',
            '_id': 'chunk-1',
            '_source': {
                'chunk_id': 'chunk-1',
                'title': 'CSM Executive Meeting',
                'transcript_id': 'transcript-1',
                'transcript_date': '2026-05-26',
                'sequence': 3,
                'speakers': ['Dobson, Michael', 'Ross, Jamie'],
                'content': (
                    'Dobson, Michael [PHSA]: I will follow up on the CSM action list. '
                    'Ross, Jamie: We agreed the Data Governance work is blocked waiting on review. '
                    'Dobson, Michael [PHSA]: The Defender rollout status is on track. '
                    'Dobson, Michael [PHSA]: Carry forward the unresolved endpoint-count item.'
                ),
            },
        }
    )
    prepared = record.model_copy(
        update={
            'metadata': {
                **record.metadata,
                'pilot_slice': 'csm_exec_series',
                'series_key': 'csm_executive_meeting',
                'series_name': 'CSM Executive Meeting',
            }
        }
    )
    return source_record_with_seed_matches(prepared)


def test_extract_observation_candidates_from_csm_record() -> None:
    record = _matched_record()
    candidates = extract_observation_candidates(record)

    candidate_types = {candidate.observation_type for candidate in candidates}

    assert 'Obligation' in candidate_types
    assert 'Decision' in candidate_types
    assert 'MeetingCarryForward' in candidate_types
    assert 'ProjectStatus' in candidate_types
    assert any(candidate.owner_seed_id == 'person:michael-dobson' for candidate in candidates)
    assert all(candidate.project_seed_ids for candidate in candidates)
    assert all(candidate.series_seed_ids for candidate in candidates)


def test_build_observation_graph_creates_native_nodes_and_mentions() -> None:
    created_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
    record = _matched_record()
    seed_nodes = build_seed_nodes(DEFAULT_SEED_MANIFEST, 'michael', created_at)
    episodes = build_pilot_episode_nodes([record], 'michael', created_at=created_at)
    graph = build_observation_graph([record], 'michael', seed_nodes, created_at=created_at)

    assert graph.candidates
    assert all(isinstance(node, EntityNode) for node in graph.nodes)
    assert all(isinstance(edge, EpisodicEdge) for edge in graph.episodic_edges)
    assert {edge.source_node_uuid for edge in graph.episodic_edges} == {episodes[0].uuid}
    assert {node.labels[0] for node in graph.nodes}.issuperset(
        {'Obligation', 'Decision', 'MeetingCarryForward'}
    )


def test_build_observation_graph_creates_supported_typed_edges() -> None:
    created_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
    record = _matched_record()
    seed_nodes = build_seed_nodes(DEFAULT_SEED_MANIFEST, 'michael', created_at)
    graph = build_observation_graph([record], 'michael', seed_nodes, created_at=created_at)

    edge_names = {edge.name for edge in graph.entity_edges}
    source_target_names = {
        (edge.source_node_uuid, edge.name, edge.target_node_uuid) for edge in graph.entity_edges
    }

    assert all(isinstance(edge, EntityEdge) for edge in graph.entity_edges)
    assert 'PERSON_OWNS_OBLIGATION' in edge_names
    assert 'PROJECT_HAS_DECISION' in edge_names
    assert 'PROJECT_HAS_STATUS' in edge_names
    assert 'BLOCKER_BLOCKS_PROJECT' in edge_names
    assert 'MEETING_SERIES_HAS_CARRY_FORWARD' in edge_names
    assert any(
        source_uuid == seed_nodes['person:michael-dobson'].uuid
        and edge_name == 'PERSON_OWNS_OBLIGATION'
        for source_uuid, edge_name, _ in source_target_names
    )
