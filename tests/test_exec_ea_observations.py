from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.exec_ea import (
    LLM_OBSERVATION_EXTRACTION_METHOD,
    LLMObservationExtraction,
    build_observation_graph,
    build_observation_graph_from_candidates,
    build_pilot_episode_nodes,
    build_seed_nodes,
    extract_observation_candidates,
    extract_observation_candidates_with_llm,
    normalize_hit,
    observation_extraction_messages,
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


def test_observation_extraction_messages_ask_llm_for_semantic_observations() -> None:
    record = _matched_record()
    messages = observation_extraction_messages(record)

    assert messages[0].role == 'system'
    assert 'Use semantic judgment, not keyword matching' in messages[0].content
    assert 'Do not create a carry-forward from "parking lot"' in messages[1].content
    assert 'Treat "need to", "to do", "I\'ll", "I can", "we will", and bare "status"' in (
        messages[1].content
    )
    assert 'project_registry:24' in messages[1].content
    assert 'series:csm-executive-meeting' in messages[1].content


@pytest.mark.asyncio
async def test_extract_observation_candidates_with_llm_validates_seed_scope() -> None:
    record = _matched_record()
    llm_client = MagicMock()
    llm_client.generate_response = AsyncMock(
        return_value={
            'observations': [
                {
                    'observation_type': 'Obligation',
                    'text': 'Michael will follow up on the Data Governance action list.',
                    'evidence_text': (
                        'Dobson, Michael [PHSA]: I will follow up on the CSM action list.'
                    ),
                    'confidence': 0.92,
                    'owner_seed_id': 'person:michael-dobson',
                    'project_seed_ids': [
                        'project_registry:5',
                        'project_registry:24',
                        'project_registry:missing',
                    ],
                    'series_seed_ids': [
                        'series:leadership-team-meeting',
                        'series:csm-executive-meeting',
                    ],
                }
            ]
        }
    )

    candidates = await extract_observation_candidates_with_llm(
        record, llm_client, group_id='michael'
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.extraction_method == LLM_OBSERVATION_EXTRACTION_METHOD
    assert candidate.cue == 'llm'
    assert candidate.owner_seed_id == 'person:michael-dobson'
    assert candidate.project_seed_ids == ['project_registry:24']
    assert candidate.series_seed_ids == ['series:csm-executive-meeting']
    assert candidate.evidence_text
    llm_client.generate_response.assert_awaited_once()
    call_kwargs = llm_client.generate_response.await_args.kwargs
    assert call_kwargs['response_model'] is LLMObservationExtraction
    assert call_kwargs['prompt_name'] == 'exec_ea.extract_observations'


@pytest.mark.asyncio
async def test_extract_observation_candidates_with_llm_rejects_unsupported_evidence() -> None:
    record = _matched_record()
    llm_client = MagicMock()
    llm_client.generate_response = AsyncMock(
        return_value={
            'observations': [
                {
                    'observation_type': 'Decision',
                    'text': 'The team approved a fictional decision.',
                    'evidence_text': 'This sentence is not present in the source.',
                    'confidence': 0.99,
                    'owner_seed_id': None,
                    'project_seed_ids': ['project_registry:24'],
                    'series_seed_ids': ['series:csm-executive-meeting'],
                }
            ]
        }
    )

    assert await extract_observation_candidates_with_llm(record, llm_client) == []


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


@pytest.mark.asyncio
async def test_build_observation_graph_from_llm_candidates_marks_extraction_method() -> None:
    created_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
    record = _matched_record()
    llm_client = MagicMock()
    llm_client.generate_response = AsyncMock(
        return_value={
            'observations': [
                {
                    'observation_type': 'ProjectStatus',
                    'text': 'Defender rollout is on track.',
                    'evidence_text': (
                        'Dobson, Michael [PHSA]: The Defender rollout status is on track.'
                    ),
                    'confidence': 0.88,
                    'owner_seed_id': None,
                    'project_seed_ids': ['project_registry:13'],
                    'series_seed_ids': ['series:csm-executive-meeting'],
                }
            ]
        }
    )
    candidates = await extract_observation_candidates_with_llm(record, llm_client)
    seed_nodes = build_seed_nodes(DEFAULT_SEED_MANIFEST, 'michael', created_at)
    graph = build_observation_graph_from_candidates(
        [record], candidates, 'michael', seed_nodes, created_at=created_at
    )

    assert graph.nodes[0].attributes['extraction_method'] == LLM_OBSERVATION_EXTRACTION_METHOD
    assert graph.nodes[0].attributes['evidence_text'] == (
        'Dobson, Michael [PHSA]: The Defender rollout status is on track.'
    )
    assert {edge.name for edge in graph.entity_edges} == {'PROJECT_HAS_STATUS'}
