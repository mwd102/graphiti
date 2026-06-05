from datetime import datetime

from graphiti_core.exec_ea import normalize_hit, source_record_to_raw_episode
from graphiti_core.nodes import EpisodeType


def test_normalize_email_hit_preserves_thread_and_triage_metadata() -> None:
    record = normalize_hit(
        {
            '_index': 'emails',
            '_id': 'email-1',
            '_source': {
                'graph_immutable_id': 'immutable-1',
                'subject': 'CrowdStrike to Defender migration',
                'from_name': 'Jamie Ross',
                'from_email': 'jaross@deloitte.ca',
                'to': 'michael.dobson@phsa.ca',
                'received_at': '2026-06-03T15:00:00Z',
                'processed_at': '2026-06-03T15:05:00Z',
                'unique_body': 'Can you approve the next migration checkpoint?',
                'thread_id': 'thread-1',
                'conversation_id': 'conversation-1',
                'conversation_index': 'abc',
                'internet_message_id': '<message-1>',
                'folder_path': 'Inbox',
                'direct_recipient': True,
                'is_read': False,
                'importance': 'high',
                'flag_status': 'notFlagged',
            },
        }
    )

    assert record.source_id == 'immutable-1'
    assert record.source_kind == 'email'
    assert record.reference_time == datetime.fromisoformat('2026-06-03T15:00:00+00:00')
    assert 'CrowdStrike to Defender migration' in record.content
    assert record.metadata['conversation_id'] == 'conversation-1'
    assert record.metadata['direct_recipient'] is True
    assert record.metadata['is_read'] is False


def test_normalize_chunk_hit_preserves_chunk_links() -> None:
    record = normalize_hit(
        {
            '_index': 'chunks',
            '_id': 'chunk-hit-1',
            '_source': {
                'chunk_id': 'chunk-1',
                'title': 'CSM Executive Meeting',
                'source': 'transcript',
                'source_id': 'transcript-source-1',
                'transcript_id': 'transcript-1',
                'transcript_date': '2026-05-26T00:00:00Z',
                'sequence': 7,
                'prev_chunk_id': 'chunk-0',
                'next_chunk_id': 'chunk-2',
                'speakers': ['Michael Dobson', 'Hardeep Parwana'],
                'content': 'Michael committed to follow up on endpoint counts.',
            },
        }
    )

    assert record.source_id == 'chunk-1'
    assert record.source_kind == 'transcript_chunk'
    assert record.metadata['prev_chunk_id'] == 'chunk-0'
    assert record.metadata['next_chunk_id'] == 'chunk-2'
    assert 'Michael Dobson, Hardeep Parwana' in record.content


def test_normalize_calendar_event_hit_preserves_series_metadata() -> None:
    record = normalize_hit(
        {
            '_index': 'calendar_events',
            '_id': 'event-hit-1',
            '_source': {
                'outlook_event_id': 'event-1',
                'title': '1:1 w/Hardeep & Michael',
                'series_key': 'hardeep_michael_1_1',
                'start_time': '2026-06-22T17:00:00Z',
                'end_time': '2026-06-22T17:30:00Z',
                'organizer': {'name': 'Hardeep Parwana', 'email': 'hardeep@phsa.ca'},
                'attendees': [
                    {'name': 'Michael Dobson', 'email': 'michael.dobson@phsa.ca'},
                    {'name': 'Hardeep Parwana', 'email': 'hardeep@phsa.ca'},
                ],
                'web_link': 'https://outlook.office365.com/calendar/item',
                'ingested_at': '2026-06-03T00:00:00Z',
            },
        }
    )

    assert record.source_id == 'event-1'
    assert record.source_kind == 'calendar_event'
    assert record.metadata['series_key'] == 'hardeep_michael_1_1'
    assert record.metadata['external_url'] == 'https://outlook.office365.com/calendar/item'
    assert 'Michael Dobson <michael.dobson@phsa.ca>' in record.content


def test_normalize_attachment_hit_prefers_extracted_content() -> None:
    record = normalize_hit(
        {
            '_index': 'email_attachments',
            '_id': 'attachment-hit-1',
            '_source': {
                'attachment_id': 'attachment-1',
                'filename': 'Defender endpoint counts.xlsx',
                'subject': 'Latest Defender endpoint count',
                'received_at': '2026-06-01T12:00:00Z',
                'extracted_at': '2026-06-01T12:10:00Z',
                'extraction_status': 'success',
                'extraction_method': 'docling',
                'blob_sha256': 'abc123',
                'extracted_text': 'Endpoint count: 12345',
            },
        }
    )

    assert record.source_id == 'attachment-1'
    assert record.source_kind == 'attachment'
    assert 'Endpoint count: 12345' in record.content
    assert record.metadata['blob_sha256'] == 'abc123'


def test_project_registry_hit_becomes_json_project_seed() -> None:
    record = normalize_hit(
        {
            '_index': 'project_registry',
            '_id': '13',
            '_source': {
                'project_id': 13,
                'canonical_name': 'Defender rollout',
                'kind': 'project',
                'parent_id': None,
                'status': 'active',
                'markers': [{'type': 'phrase', 'value': 'MDE', 'weight': 0.85}],
                'updated_at': '2026-05-28T02:48:08+00:00',
            },
        }
    )

    assert record.source_id == '13'
    assert record.source_kind == 'project_seed'
    assert record.episode_source == EpisodeType.json
    assert record.metadata['project_name'] == 'Defender rollout'


def test_source_record_to_raw_episode_carries_provenance_metadata() -> None:
    record = normalize_hit(
        {
            '_index': 'emails',
            '_id': 'email-1',
            '_source': {
                'graph_immutable_id': 'immutable-1',
                'subject': 'Approval needed',
                'received_at': '2026-06-03T15:00:00Z',
                'processed_at': '2026-06-03T15:05:00Z',
                'body': 'Please approve the PO.',
                'conversation_id': 'conversation-1',
            },
        }
    )

    raw_episode = source_record_to_raw_episode(record)

    assert raw_episode.source == EpisodeType.text
    assert raw_episode.name == 'Approval needed'
    assert raw_episode.reference_time == record.reference_time
    assert raw_episode.episode_metadata['source_index'] == 'emails'
    assert raw_episode.episode_metadata['source_kind'] == 'email'
    assert raw_episode.episode_metadata['source_id'] == 'immutable-1'
    assert raw_episode.episode_metadata['conversation_id'] == 'conversation-1'
