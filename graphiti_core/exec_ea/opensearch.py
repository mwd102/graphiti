"""Read-only OpenSearch normalization helpers for Exec-EA ingestion."""

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib import request

from pydantic import BaseModel, Field

from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.bulk_utils import RawEpisode

DEFAULT_OPENSEARCH_URL = 'http://100.96.45.83:19200'

SOURCE_KIND_BY_INDEX = {
    'emails': 'email',
    'transcripts': 'transcript',
    'chunks': 'transcript_chunk',
    'email_attachments': 'attachment',
    'calendar_events': 'calendar_event',
    'project_registry': 'project_seed',
}


class SourceRecord(BaseModel):
    """A normalized source record ready to become a Graphiti episode."""

    source_index: str
    source_id: str
    source_kind: str
    title: str
    content: str
    reference_time: datetime
    episode_source: EpisodeType = EpisodeType.text
    source_updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OpenSearchClient:
    """Small read-only OpenSearch client for source fetches used by Exec-EA ingestion."""

    def __init__(self, base_url: str = DEFAULT_OPENSEARCH_URL, timeout: float = 30.0):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout

    def search(
        self, index: str, body: Mapping[str, Any], *, size: int = 10
    ) -> list[dict[str, Any]]:
        """Return raw OpenSearch hits for a read-only search request."""

        url = f'{self.base_url}/{index}/_search?size={size}'
        payload = json.dumps(body).encode('utf-8')
        req = request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with request.urlopen(req, timeout=self.timeout) as response:
            data = json.loads(response.read().decode('utf-8'))

        return data.get('hits', {}).get('hits', [])

    def fetch_source_records(
        self, index: str, body: Mapping[str, Any], *, size: int = 10
    ) -> list[SourceRecord]:
        """Search an index and normalize each hit to a SourceRecord."""

        return [normalize_hit(hit) for hit in self.search(index, body, size=size)]


def normalize_hit(hit: Mapping[str, Any]) -> SourceRecord:
    """Normalize a raw OpenSearch hit from any supported Exec-EA source index."""

    source_index = str(hit['_index'])
    source = dict(hit.get('_source') or {})
    source_id = _source_id(source_index, str(hit['_id']), source)

    match source_index:
        case 'emails':
            return _normalize_email(source_index, source_id, source)
        case 'transcripts':
            return _normalize_transcript(source_index, source_id, source)
        case 'chunks':
            return _normalize_chunk(source_index, source_id, source)
        case 'email_attachments':
            return _normalize_attachment(source_index, source_id, source)
        case 'calendar_events':
            return _normalize_calendar_event(source_index, source_id, source)
        case 'project_registry':
            return _normalize_project_seed(source_index, source_id, source)
        case _:
            raise ValueError(f'Unsupported Exec-EA OpenSearch index: {source_index}')


def source_record_to_raw_episode(record: SourceRecord) -> RawEpisode:
    """Convert a normalized source record into Graphiti's bulk RawEpisode model."""

    return RawEpisode(
        name=record.title,
        content=record.content,
        source=record.episode_source,
        source_description=f'{record.source_index}:{record.source_kind}',
        reference_time=record.reference_time,
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


def _source_id(index: str, hit_id: str, source: Mapping[str, Any]) -> str:
    id_fields = {
        'emails': ('graph_immutable_id', 'internet_message_id', 'mutable_id'),
        'transcripts': ('transcript_id', 'filename'),
        'chunks': ('chunk_id',),
        'email_attachments': ('attachment_id', 'blob_sha256'),
        'calendar_events': ('outlook_event_id',),
        'project_registry': ('project_id',),
    }

    for field in id_fields.get(index, ()):
        value = source.get(field)
        if value is not None:
            return str(value)

    return hit_id


def _normalize_email(index: str, source_id: str, source: Mapping[str, Any]) -> SourceRecord:
    subject = _clean_title(source.get('subject') or source.get('normalized_subject') or source_id)
    reference_time = _parse_datetime(source.get('received_at') or source.get('sent_at'))
    body = source.get('unique_body') or source.get('body') or source.get('summary_text') or ''

    content = '\n'.join(
        _present_lines(
            [
                ('Subject', subject),
                ('From', _format_person(source.get('from_name'), source.get('from_email'))),
                ('To', source.get('to')),
                ('Cc', source.get('cc')),
                ('Received', source.get('received_at')),
                ('Folder', source.get('folder_path')),
                ('Body', body),
            ]
        )
    )

    return SourceRecord(
        source_index=index,
        source_id=source_id,
        source_kind=SOURCE_KIND_BY_INDEX[index],
        title=subject,
        content=content,
        reference_time=reference_time,
        source_updated_at=_parse_optional_datetime(source.get('processed_at')),
        metadata={
            'thread_id': source.get('thread_id'),
            'conversation_id': source.get('conversation_id'),
            'conversation_index': source.get('conversation_index'),
            'internet_message_id': source.get('internet_message_id'),
            'folder_path': source.get('folder_path'),
            'direct_recipient': source.get('direct_recipient'),
            'is_read': source.get('is_read'),
            'importance': source.get('importance'),
            'flag_status': source.get('flag_status'),
            'source_created_at': _iso_or_none(source.get('sent_at') or source.get('received_at')),
        },
    )


def _normalize_transcript(index: str, source_id: str, source: Mapping[str, Any]) -> SourceRecord:
    title = _clean_title(source.get('title') or source.get('filename') or source_id)
    reference_time = _parse_datetime(source.get('date') or source.get('processed_at'))
    content_body = (
        source.get('cleaned_content')
        or source.get('raw_content')
        or source.get('summary_text')
        or ''
    )

    content = '\n'.join(
        _present_lines(
            [
                ('Title', title),
                ('Date', source.get('date')),
                (
                    'Participants',
                    _join(source.get('participant_names') or source.get('participants')),
                ),
                ('Topics', _join(source.get('topics'))),
                ('Transcript', content_body),
            ]
        )
    )

    return SourceRecord(
        source_index=index,
        source_id=source_id,
        source_kind=SOURCE_KIND_BY_INDEX[index],
        title=title,
        content=content,
        reference_time=reference_time,
        source_updated_at=_parse_optional_datetime(source.get('processed_at')),
        metadata={
            'transcript_id': source.get('transcript_id'),
            'source_created_at': _iso_or_none(source.get('date')),
            'extraction_status': source.get('processing_status'),
            'extraction_method': source.get('import_source'),
        },
    )


def _normalize_chunk(index: str, source_id: str, source: Mapping[str, Any]) -> SourceRecord:
    title = _clean_title(source.get('title') or source.get('source_id') or source_id)
    reference_time = _parse_datetime(source.get('transcript_date'))
    content_body = source.get('content') or source.get('topic_summary') or ''

    content = '\n'.join(
        _present_lines(
            [
                ('Title', title),
                ('Source', source.get('source')),
                ('Sequence', source.get('sequence')),
                ('Speakers', _join(source.get('speakers'))),
                ('Content', content_body),
            ]
        )
    )

    return SourceRecord(
        source_index=index,
        source_id=source_id,
        source_kind=SOURCE_KIND_BY_INDEX[index],
        title=title,
        content=content,
        reference_time=reference_time,
        source_updated_at=None,
        metadata={
            'chunk_id': source.get('chunk_id'),
            'transcript_id': source.get('transcript_id'),
            'source_id': source.get('source_id'),
            'prev_chunk_id': source.get('prev_chunk_id'),
            'next_chunk_id': source.get('next_chunk_id'),
            'source_created_at': _iso_or_none(source.get('transcript_date')),
        },
    )


def _normalize_attachment(index: str, source_id: str, source: Mapping[str, Any]) -> SourceRecord:
    title = _clean_title(source.get('filename') or source.get('subject') or source_id)
    reference_time = _parse_datetime(
        source.get('received_at') or source.get('sent_at') or source.get('extracted_at')
    )
    content_body = (
        source.get('extracted_markdown')
        or source.get('extracted_markdown_docling')
        or source.get('extracted_text')
        or source.get('extraction_error')
        or ''
    )

    content = '\n'.join(
        _present_lines(
            [
                ('Filename', title),
                ('Subject', source.get('subject')),
                ('From', _format_person(source.get('from_name'), source.get('from_email'))),
                ('Extraction status', source.get('extraction_status')),
                ('Extracted content', content_body),
            ]
        )
    )

    return SourceRecord(
        source_index=index,
        source_id=source_id,
        source_kind=SOURCE_KIND_BY_INDEX[index],
        title=title,
        content=content,
        reference_time=reference_time,
        source_updated_at=_parse_optional_datetime(source.get('extracted_at')),
        metadata={
            'attachment_id': source.get('attachment_id'),
            'blob_sha256': source.get('blob_sha256'),
            'internet_message_id': source.get('internet_message_id'),
            'extraction_status': source.get('extraction_status'),
            'extraction_method': source.get('extraction_method'),
            'source_created_at': _iso_or_none(source.get('received_at') or source.get('sent_at')),
        },
    )


def _normalize_calendar_event(
    index: str, source_id: str, source: Mapping[str, Any]
) -> SourceRecord:
    title = _clean_title(source.get('title') or source_id)
    reference_time = _parse_datetime(source.get('start_time') or source.get('ingested_at'))
    organizer = source.get('organizer') or {}
    attendees = source.get('attendees') or []

    content = '\n'.join(
        _present_lines(
            [
                ('Title', title),
                ('Start', source.get('start_time')),
                ('End', source.get('end_time')),
                ('Organizer', _format_person(organizer.get('name'), organizer.get('email'))),
                (
                    'Attendees',
                    _join(
                        _format_person(item.get('name'), item.get('email')) for item in attendees
                    ),
                ),
                ('Agenda', source.get('agenda')),
                ('Location', source.get('location')),
            ]
        )
    )

    return SourceRecord(
        source_index=index,
        source_id=source_id,
        source_kind=SOURCE_KIND_BY_INDEX[index],
        title=title,
        content=content,
        reference_time=reference_time,
        source_updated_at=_parse_optional_datetime(source.get('ingested_at')),
        metadata={
            'calendar_event_id': source.get('outlook_event_id'),
            'series_key': source.get('series_key'),
            'external_url': source.get('web_link'),
            'source_created_at': _iso_or_none(source.get('start_time')),
            'source_updated_at': _iso_or_none(source.get('ingested_at')),
        },
    )


def _normalize_project_seed(index: str, source_id: str, source: Mapping[str, Any]) -> SourceRecord:
    title = _clean_title(source.get('canonical_name') or source_id)
    updated_at = _parse_datetime(source.get('updated_at'))

    return SourceRecord(
        source_index=index,
        source_id=source_id,
        source_kind=SOURCE_KIND_BY_INDEX[index],
        title=title,
        content=json.dumps(source, sort_keys=True, default=str),
        reference_time=updated_at,
        episode_source=EpisodeType.json,
        source_updated_at=updated_at,
        metadata={
            'project_id': source.get('project_id'),
            'project_name': source.get('canonical_name'),
            'project_kind': source.get('kind'),
            'project_parent_id': source.get('parent_id'),
        },
    )


def _parse_datetime(value: Any) -> datetime:
    parsed = _parse_optional_datetime(value)
    if parsed is None:
        return datetime.fromtimestamp(0).astimezone()
    return parsed


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.endswith('Z'):
            normalized = normalized[:-1] + '+00:00'
        return datetime.fromisoformat(normalized)
    raise TypeError(f'Unsupported datetime value: {value!r}')


def _iso_or_none(value: Any) -> str | None:
    parsed = _parse_optional_datetime(value)
    return parsed.isoformat() if parsed else None


def _clean_title(value: Any) -> str:
    title = str(value or '').strip()
    return title or 'Untitled source record'


def _join(values: Any) -> str:
    if values is None:
        return ''
    if isinstance(values, str):
        return values
    return ', '.join(str(value) for value in values if value)


def _format_person(name: Any, email: Any) -> str:
    if name and email:
        return f'{name} <{email}>'
    if name:
        return str(name)
    if email:
        return str(email)
    return ''


def _present_lines(items: list[tuple[str, Any]]) -> list[str]:
    return [f'{label}: {value}' for label, value in items if value not in (None, '')]
