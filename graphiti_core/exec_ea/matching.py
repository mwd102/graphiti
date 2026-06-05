"""Deterministic seed matching for normalized Exec-EA source records."""

import json
import re
from typing import Any

from pydantic import BaseModel

from graphiti_core.exec_ea.opensearch import SourceRecord
from graphiti_core.exec_ea.seeds import (
    DEFAULT_SEED_MANIFEST,
    SeedEdge,
    SeedEntity,
    SeedManifest,
)

MATCH_METADATA_KEYS = {
    'Document': 'document_matches',
    'MeetingSeries': 'series_matches',
    'Organization': 'organization_matches',
    'Person': 'person_matches',
    'Platform': 'platform_matches',
    'Program': 'project_matches',
    'Project': 'project_matches',
    'Vendor': 'vendor_matches',
    'VendorProduct': 'platform_matches',
    'WorkingGroup': 'series_matches',
}


class SeedMatch(BaseModel):
    """A deterministic match between a source record and a seed entity."""

    seed_id: str
    entity_type: str
    name: str
    seed_role: str
    concept_key: str
    matched_value: str
    match_field: str
    confidence: float


class SeedMatchSet(BaseModel):
    """Role-bucketed seed matches for provenance metadata."""

    matches: list[SeedMatch]

    def metadata(self) -> dict[str, list[dict[str, Any]]]:
        """Return matches grouped into episode metadata keys."""

        grouped: dict[str, list[dict[str, Any]]] = {}
        for match in self.matches:
            metadata_key = MATCH_METADATA_KEYS.get(match.entity_type)
            if metadata_key is None:
                continue
            grouped.setdefault(metadata_key, []).append(match.model_dump())

        return grouped


class SeedMatchCandidate(BaseModel):
    """Searchable seed term used by the deterministic matcher."""

    seed_id: str
    entity_type: str
    name: str
    seed_role: str
    concept_key: str
    value: str
    match_field: str
    confidence: float


def match_source_record(
    record: SourceRecord,
    manifest: SeedManifest = DEFAULT_SEED_MANIFEST,
    *,
    max_matches_per_bucket: int = 8,
) -> SeedMatchSet:
    """Match a normalized source record to role-aware Exec-EA seeds."""

    text = _record_text(record)
    metadata = _normalized_metadata(record.metadata)
    candidates = _seed_match_candidates(manifest.entities)
    best_by_seed: dict[str, SeedMatch] = {}

    for candidate in candidates:
        confidence = _candidate_confidence(candidate, text, metadata)
        if confidence is None:
            continue

        current = best_by_seed.get(candidate.seed_id)
        if current is not None and current.confidence >= confidence:
            continue

        best_by_seed[candidate.seed_id] = SeedMatch(
            seed_id=candidate.seed_id,
            entity_type=candidate.entity_type,
            name=candidate.name,
            seed_role=candidate.seed_role,
            concept_key=candidate.concept_key,
            matched_value=candidate.value,
            match_field=candidate.match_field,
            confidence=confidence,
        )

    _propagate_seed_edge_matches(best_by_seed, manifest.entities, manifest.edges)

    return SeedMatchSet(
        matches=_limit_matches_by_bucket(list(best_by_seed.values()), max_matches_per_bucket)
    )


def source_record_with_seed_matches(
    record: SourceRecord,
    manifest: SeedManifest = DEFAULT_SEED_MANIFEST,
    *,
    max_matches_per_bucket: int = 8,
) -> SourceRecord:
    """Return a copy of a source record with seed-match metadata attached."""

    match_set = match_source_record(record, manifest, max_matches_per_bucket=max_matches_per_bucket)
    return record.model_copy(update={'metadata': {**record.metadata, **match_set.metadata()}})


def _seed_match_candidates(entities: list[SeedEntity]) -> list[SeedMatchCandidate]:
    candidates: list[SeedMatchCandidate] = []
    seen: set[tuple[str, str, str]] = set()

    for entity in entities:
        attributes = entity.attributes
        seed_role = str(attributes.get('seed_role') or _seed_role(entity.entity_type))
        concept_key = str(attributes.get('concept_key') or _normalize_key(entity.name))

        term_specs: list[tuple[str, str, float]] = [
            (entity.name, 'name', 1.0),
        ]
        if attributes.get('canonical_label'):
            term_specs.append((str(attributes['canonical_label']), 'canonical_label', 1.0))
        for alias in attributes.get('aliases') or []:
            term_specs.append((str(alias), 'alias', 0.9))
        if attributes.get('domain'):
            term_specs.append((str(attributes['domain']), 'domain', 0.95))
        if attributes.get('series_key'):
            term_specs.append((str(attributes['series_key']), 'series_key', 1.0))

        for marker in _registry_markers(attributes):
            marker_value = marker.get('value')
            if not marker_value:
                continue
            marker_type = str(marker.get('type') or 'marker')
            marker_weight = float(marker.get('weight') or 0.75)
            term_specs.append((str(marker_value), f'registry_marker:{marker_type}', marker_weight))

        for value, match_field, confidence in term_specs:
            normalized_value = value.strip()
            if not normalized_value:
                continue

            key = (entity.seed_id, normalized_value.lower(), match_field)
            if key in seen:
                continue
            seen.add(key)

            candidates.append(
                SeedMatchCandidate(
                    seed_id=entity.seed_id,
                    entity_type=entity.entity_type,
                    name=entity.name,
                    seed_role=seed_role,
                    concept_key=concept_key,
                    value=normalized_value,
                    match_field=match_field,
                    confidence=confidence,
                )
            )

    return candidates


def _candidate_confidence(
    candidate: SeedMatchCandidate,
    text: str,
    metadata: dict[str, str],
) -> float | None:
    value = candidate.value.lower()

    if candidate.match_field == 'series_key':
        if value == metadata.get('series_key'):
            return candidate.confidence
        if value in text:
            return max(candidate.confidence - 0.1, 0.0)
        return None

    if candidate.match_field == 'domain':
        if value in metadata.get('email_domains', '') or value in text:
            return candidate.confidence
        return None

    if candidate.match_field.endswith(':domain'):
        if value in metadata.get('email_domains', '') or value in text:
            return candidate.confidence
        return None

    if _term_in_text(value, text):
        return candidate.confidence

    return None


def _propagate_seed_edge_matches(
    best_by_seed: dict[str, SeedMatch],
    entities: list[SeedEntity],
    edges: list[SeedEdge],
) -> None:
    seed_entities = {entity.seed_id: entity for entity in entities}

    for _ in range(2):
        added = False
        matched_seed_ids = set(best_by_seed)

        for edge in edges:
            if edge.edge_type == 'VENDOR_PROVIDES_PLATFORM':
                if edge.target_seed_id in matched_seed_ids:
                    added |= _add_propagated_match(
                        best_by_seed,
                        seed_entities,
                        source_match=best_by_seed[edge.target_seed_id],
                        target_seed_id=edge.source_seed_id,
                        match_field=edge.edge_type,
                        confidence_multiplier=0.8,
                    )
                if edge.source_seed_id in matched_seed_ids:
                    added |= _add_propagated_match(
                        best_by_seed,
                        seed_entities,
                        source_match=best_by_seed[edge.source_seed_id],
                        target_seed_id=edge.target_seed_id,
                        match_field=edge.edge_type,
                        confidence_multiplier=0.75,
                    )

            if edge.edge_type in {'PROJECT_INVOLVES_PLATFORM', 'PROJECT_HAS_VENDOR'}:
                if edge.source_seed_id in matched_seed_ids:
                    added |= _add_propagated_match(
                        best_by_seed,
                        seed_entities,
                        source_match=best_by_seed[edge.source_seed_id],
                        target_seed_id=edge.target_seed_id,
                        match_field=edge.edge_type,
                        confidence_multiplier=0.72,
                    )
                if edge.target_seed_id in matched_seed_ids:
                    added |= _add_propagated_match(
                        best_by_seed,
                        seed_entities,
                        source_match=best_by_seed[edge.target_seed_id],
                        target_seed_id=edge.source_seed_id,
                        match_field=edge.edge_type,
                        confidence_multiplier=0.7,
                    )

        if not added:
            return


def _add_propagated_match(
    best_by_seed: dict[str, SeedMatch],
    seed_entities: dict[str, SeedEntity],
    *,
    source_match: SeedMatch,
    target_seed_id: str,
    match_field: str,
    confidence_multiplier: float,
) -> bool:
    if target_seed_id in best_by_seed:
        return False

    entity = seed_entities.get(target_seed_id)
    if entity is None:
        return False

    attributes = entity.attributes
    confidence = round(source_match.confidence * confidence_multiplier, 4)
    best_by_seed[target_seed_id] = SeedMatch(
        seed_id=entity.seed_id,
        entity_type=entity.entity_type,
        name=entity.name,
        seed_role=str(attributes.get('seed_role') or _seed_role(entity.entity_type)),
        concept_key=str(attributes.get('concept_key') or _normalize_key(entity.name)),
        matched_value=source_match.name,
        match_field=f'seed_edge:{match_field}',
        confidence=confidence,
    )
    return True


def _term_in_text(term: str, text: str) -> bool:
    if len(term) <= 3 or not re.search(r'[^a-z0-9]', term):
        return re.search(rf'(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])', text) is not None

    return term in text


def _limit_matches_by_bucket(
    matches: list[SeedMatch], max_matches_per_bucket: int
) -> list[SeedMatch]:
    grouped: dict[str, list[SeedMatch]] = {}
    for match in sorted(matches, key=lambda item: (-item.confidence, item.seed_role, item.name)):
        metadata_key = MATCH_METADATA_KEYS.get(match.entity_type)
        if metadata_key is None:
            continue
        bucket = grouped.setdefault(metadata_key, [])
        if len(bucket) < max_matches_per_bucket:
            bucket.append(match)

    return [match for bucket in grouped.values() for match in bucket]


def _record_text(record: SourceRecord) -> str:
    metadata_values = ' '.join(
        str(value)
        for value in record.metadata.values()
        if isinstance(value, str | int | float | bool)
    )
    return f'{record.title}\n{record.content}\n{metadata_values}'.lower()


def _normalized_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    email_values: list[str] = []
    series_key = ''

    for key, value in metadata.items():
        if key == 'series_key' and value:
            series_key = str(value).lower()
        if key.endswith('email') or key in {'from_email', 'sender_domain'}:
            email_values.append(str(value).lower())

    domains = []
    for value in email_values:
        if '@' in value:
            domains.append(value.rsplit('@', 1)[1])
        elif '.' in value:
            domains.append(value)

    return {'series_key': series_key, 'email_domains': ' '.join(domains)}


def _registry_markers(attributes: dict[str, Any]) -> list[dict[str, Any]]:
    markers_json = attributes.get('match_markers_json')
    if not isinstance(markers_json, str):
        return []
    try:
        markers = json.loads(markers_json)
    except json.JSONDecodeError:
        return []
    return markers if isinstance(markers, list) else []


def _seed_role(entity_type: str) -> str:
    return {
        'Program': 'program',
        'Project': 'project',
        'Platform': 'platform',
        'VendorProduct': 'vendor_product',
        'Vendor': 'vendor',
        'Organization': 'organization',
        'MeetingSeries': 'meeting_series',
        'Document': 'document',
        'Person': 'person',
    }.get(entity_type, _normalize_key(entity_type))


def _normalize_key(value: str) -> str:
    normalized = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return normalized or 'unknown'
