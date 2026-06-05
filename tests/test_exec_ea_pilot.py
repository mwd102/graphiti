from datetime import datetime, timezone
from typing import Any

from graphiti_core.exec_ea import (
    CSM_EXEC_PILOT_SLICE,
    CSM_EXEC_SERIES_KEY,
    CSMExecPilotConfig,
    build_pilot_episode_nodes,
    build_pilot_episodic_edges,
    build_seed_nodes,
    deterministic_episode_uuid,
    fetch_csm_exec_pilot_records,
)
from graphiti_core.exec_ea.seeds import DEFAULT_SEED_MANIFEST


class FakeOpenSearchClient:
    def fetch_source_records(self, index: str, body: dict[str, Any], *, size: int):
        from graphiti_core.exec_ea import normalize_hit

        hits = {
            'transcripts': [
                {
                    '_index': 'transcripts',
                    '_id': 'transcript-1',
                    '_source': {
                        'transcript_id': 'transcript-1',
                        'title': 'CSM Executive Meeting',
                        'date': '2026-05-26',
                        'participant_names': [
                            'Dobson, Michael [PHSA]',
                            'Lucas, Derek [PHSA]',
                            'Ross, Jamie',
                        ],
                        'cleaned_content': 'Michael committed to follow up on CSM actions.',
                    },
                }
            ],
            'calendar_events': [
                {
                    '_index': 'calendar_events',
                    '_id': 'event-1',
                    '_source': {
                        'outlook_event_id': 'event-1',
                        'title': 'CSM Executive Meeting',
                        'series_key': 'csm executive meeting',
                        'start_time': '2026-06-23T16:00:00Z',
                        'end_time': '2026-06-23T16:30:00Z',
                        'organizer': {
                            'name': 'Dury, Jennifer [PHSA]',
                            'email': 'jennifer.dury@phsa.ca',
                        },
                        'attendees': [
                            {
                                'name': 'Dobson, Michael [PHSA]',
                                'email': 'michael.dobson@phsa.ca',
                            },
                            {
                                'name': 'Lucas, Derek [PHSA]',
                                'email': 'derek.lucas@phsa.ca',
                            },
                        ],
                    },
                }
            ],
            'chunks': [
                {
                    '_index': 'chunks',
                    '_id': 'transcript-1-0',
                    '_source': {
                        'chunk_id': 'transcript-1-0',
                        'title': 'CSM Executive Meeting',
                        'transcript_id': 'transcript-1',
                        'transcript_date': '2026-05-26',
                        'sequence': 0,
                        'speakers': ['Dobson, Michael', 'Ross, Jamie'],
                        'content': 'The group discussed Data Governance and CSM priorities.',
                    },
                }
            ],
        }

        return [normalize_hit(hit) for hit in hits[index][:size]]


def _ids(matches: list[dict]) -> set[str]:
    return {match['seed_id'] for match in matches}


def test_fetch_csm_exec_pilot_records_attaches_seed_matches() -> None:
    records = fetch_csm_exec_pilot_records(
        FakeOpenSearchClient(),
        CSMExecPilotConfig(
            transcript_limit=1,
            calendar_limit=1,
            chunk_transcript_limit=1,
            chunk_limit=1,
        ),
    )

    assert len(records) == 3
    assert all(record.metadata['pilot_slice'] == CSM_EXEC_PILOT_SLICE for record in records)
    assert all(record.metadata['series_key'] == CSM_EXEC_SERIES_KEY for record in records)
    assert all(
        'series:csm-executive-meeting' in _ids(record.metadata['series_matches'])
        for record in records
    )
    assert 'person:michael-dobson' in _ids(records[0].metadata['person_matches'])
    assert 'project_registry:5' in _ids(records[2].metadata['project_matches'])


def test_build_pilot_episode_nodes_uses_deterministic_episode_uuids() -> None:
    records = fetch_csm_exec_pilot_records(
        FakeOpenSearchClient(),
        CSMExecPilotConfig(transcript_limit=1, calendar_limit=0, chunk_limit=0),
    )
    created_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
    episodes = build_pilot_episode_nodes(records, 'michael', created_at=created_at)

    assert len(episodes) == 1
    assert episodes[0].uuid == deterministic_episode_uuid('michael', records[0])
    assert episodes[0].episode_metadata['pilot_slice'] == CSM_EXEC_PILOT_SLICE
    assert episodes[0].episode_metadata['source_kind'] == 'transcript'
    assert episodes[0].created_at == created_at


def test_build_pilot_episodic_edges_mentions_matched_seed_nodes() -> None:
    records = fetch_csm_exec_pilot_records(
        FakeOpenSearchClient(),
        CSMExecPilotConfig(transcript_limit=1, calendar_limit=0, chunk_limit=0),
    )
    created_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
    episodes = build_pilot_episode_nodes(records, 'michael', created_at=created_at)
    seed_nodes = build_seed_nodes(DEFAULT_SEED_MANIFEST, 'michael', created_at)
    episodic_edges = build_pilot_episodic_edges(
        records, episodes, seed_nodes, 'michael', created_at=created_at
    )

    target_uuids = {edge.target_node_uuid for edge in episodic_edges}

    assert seed_nodes['series:csm-executive-meeting'].uuid in target_uuids
    assert seed_nodes['person:michael-dobson'].uuid in target_uuids
    assert seed_nodes['project_registry:5'].uuid in target_uuids
    assert all(edge.source_node_uuid == episodes[0].uuid for edge in episodic_edges)
