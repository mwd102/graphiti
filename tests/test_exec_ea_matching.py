from graphiti_core.exec_ea import (
    match_source_record,
    normalize_hit,
    source_record_to_raw_episode,
    source_record_with_seed_matches,
)


def _ids(matches: list[dict]) -> set[str]:
    return {match['seed_id'] for match in matches}


def test_match_source_record_finds_cross_role_project_platform_vendor_seeds() -> None:
    record = normalize_hit(
        {
            '_index': 'emails',
            '_id': 'email-1',
            '_source': {
                'graph_immutable_id': 'immutable-1',
                'subject': 'CrowdStrike to Defender migration checkpoint',
                'from_email': 'jaross@deloitte.ca',
                'from_name': 'Jamie Ross',
                'received_at': '2026-06-03T15:00:00Z',
                'body': 'Can you approve the next Defender for Endpoint checkpoint?',
                'conversation_id': 'conversation-1',
            },
        }
    )

    match_metadata = match_source_record(record).metadata()

    assert 'project_registry:18' in _ids(match_metadata['project_matches'])
    assert 'project_registry:13' in _ids(match_metadata['project_matches'])
    assert 'platform:crowdstrike' in _ids(match_metadata['platform_matches'])
    assert 'vendor_product:crowdstrike-falcon' in _ids(match_metadata['platform_matches'])
    assert 'platform:defender-mde' in _ids(match_metadata['platform_matches'])
    assert 'vendor:microsoft' in _ids(match_metadata['vendor_matches'])
    assert 'vendor:crowdstrike' in _ids(match_metadata['vendor_matches'])


def test_match_source_record_finds_series_by_calendar_series_key() -> None:
    record = normalize_hit(
        {
            '_index': 'calendar_events',
            '_id': 'event-1',
            '_source': {
                'outlook_event_id': 'event-1',
                'title': 'Sync',
                'series_key': 'hardeep_michael_1_1',
                'start_time': '2026-06-22T17:00:00Z',
                'end_time': '2026-06-22T17:30:00Z',
                'attendees': [
                    {'name': 'Michael Dobson', 'email': 'michael.dobson@phsa.ca'},
                    {'name': 'Hardeep Parwana', 'email': 'hardeep@phsa.ca'},
                ],
            },
        }
    )

    match_metadata = match_source_record(record).metadata()

    assert 'series:hardeep-michael-1-1' in _ids(match_metadata['series_matches'])
    assert 'person:hardeep-parwana' in _ids(match_metadata['person_matches'])
    assert 'person:michael-dobson' in _ids(match_metadata['person_matches'])


def test_match_source_record_finds_person_and_vendor_by_email_aliases() -> None:
    record = normalize_hit(
        {
            '_index': 'emails',
            '_id': 'email-1',
            '_source': {
                'graph_immutable_id': 'immutable-1',
                'subject': 'Data Governance update',
                'from_email': 'jaross@deloitte.ca',
                'from_name': 'Jamie Ross',
                'received_at': '2026-06-03T15:00:00Z',
                'body': 'Varonis and Purview are still the key discussion points.',
            },
        }
    )

    match_metadata = match_source_record(record).metadata()

    assert 'person:jamie-ross' in _ids(match_metadata['person_matches'])
    assert 'vendor:deloitte' in _ids(match_metadata['vendor_matches'])
    assert 'project_registry:24' in _ids(match_metadata['project_matches'])
    assert 'platform:purview' in _ids(match_metadata['platform_matches'])
    assert 'platform:varonis' in _ids(match_metadata['platform_matches'])


def test_source_record_with_seed_matches_feeds_raw_episode_metadata() -> None:
    record = normalize_hit(
        {
            '_index': 'chunks',
            '_id': 'chunk-1',
            '_source': {
                'chunk_id': 'chunk-1',
                'title': 'Leadership Team Meeting',
                'transcript_date': '2026-06-03T00:00:00Z',
                'content': 'The team carried forward the unresolved Data Governance blocker.',
            },
        }
    )

    matched_record = source_record_with_seed_matches(record)
    raw_episode = source_record_to_raw_episode(matched_record)

    assert 'series_matches' in raw_episode.episode_metadata
    assert 'project_matches' in raw_episode.episode_metadata
    assert 'series:leadership-team-meeting' in _ids(raw_episode.episode_metadata['series_matches'])
    assert 'project_registry:24' in _ids(raw_episode.episode_metadata['project_matches'])
