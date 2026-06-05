"""Default seed manifest and native seed loader for the Exec-EA ontology."""

import json
import re
from datetime import datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, Field

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.embedder.client import EmbedderClient
from graphiti_core.exec_ea.ontology import EDGE_TYPES, ENTITY_TYPES
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode
from graphiti_core.utils.bulk_utils import add_nodes_and_edges_bulk
from graphiti_core.utils.datetime_utils import utc_now

EXEC_EA_SEED_NAMESPACE = 'exec-ea'


class SeedEntity(BaseModel):
    """A deterministic native Graphiti entity seed."""

    seed_id: str
    entity_type: str
    name: str
    summary: str = ''
    attributes: dict[str, Any] = Field(default_factory=dict)


class SeedEdge(BaseModel):
    """A deterministic native Graphiti edge seed between two entity seeds."""

    seed_id: str
    source_seed_id: str
    target_seed_id: str
    edge_type: str
    fact: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class SeedManifest(BaseModel):
    """A versioned collection of native Exec-EA seed entities and edges."""

    manifest_id: str
    version: str
    name: str
    description: str
    source: str
    source_checked_at: datetime
    entities: list[SeedEntity]
    edges: list[SeedEdge] = Field(default_factory=list)


class SeedLoadResult(BaseModel):
    """Summary of a native Exec-EA seed load."""

    manifest_episode_uuid: str | None
    node_uuids: list[str]
    edge_uuids: list[str]
    episodic_edge_uuids: list[str]


def seed_uuid(group_id: str, *parts: str) -> str:
    """Return a deterministic UUID for a seed object in a graph namespace."""

    return str(uuid5(NAMESPACE_URL, ':'.join([EXEC_EA_SEED_NAMESPACE, group_id, *parts])))


def _concept_key(value: str) -> str:
    normalized = re.sub(r'[^a-z0-9]+', '-', value.lower()).strip('-')
    return normalized or 'unknown'


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
    }.get(entity_type, _concept_key(entity_type))


def _marker_values(markers: list[dict[str, Any]]) -> list[str]:
    return [str(marker['value']) for marker in markers if marker.get('value')]


def _registry_entity(record: dict[str, Any]) -> SeedEntity:
    entity_type = 'Program' if record['kind'] == 'program' else 'Project'
    registry_id = str(record['project_id'])
    status_field = 'program_status' if entity_type == 'Program' else 'project_status'
    aliases = _marker_values(record.get('markers', []))

    return SeedEntity(
        seed_id=f'project_registry:{registry_id}',
        entity_type=entity_type,
        name=record['canonical_name'],
        summary=(
            f'{entity_type} seed from project_registry record {registry_id}; '
            f'status {record["status"]}.'
        ),
        attributes={
            'canonical_label': record['canonical_name'],
            'registry_id': registry_id,
            'registry_parent_id': str(record['parent_id']) if record.get('parent_id') else None,
            'registry_kind': record['kind'],
            status_field: record['status'],
            'aliases': aliases or None,
            'concept_key': _concept_key(record['canonical_name']),
            'seed_role': record['kind'],
            'match_markers_json': json.dumps(record.get('markers', []), sort_keys=True),
            'source_updated_at': record.get('updated_at'),
            'seed_source': 'project_registry',
        },
    )


def _registry_parent_edges(records: list[dict[str, Any]]) -> list[SeedEdge]:
    by_id = {record['project_id']: record for record in records}
    edges: list[SeedEdge] = []

    for record in records:
        parent_id = record.get('parent_id')
        if parent_id is None:
            continue

        parent = by_id[parent_id]
        edge_type = (
            'PROGRAM_HAS_PROJECT' if parent['kind'] == 'program' else 'PROJECT_HAS_WORKSTREAM'
        )
        source_seed_id = f'project_registry:{parent_id}'
        target_seed_id = f'project_registry:{record["project_id"]}'
        edges.append(
            SeedEdge(
                seed_id=f'{source_seed_id}:{edge_type}:{target_seed_id}',
                source_seed_id=source_seed_id,
                target_seed_id=target_seed_id,
                edge_type=edge_type,
                fact=f'{parent["canonical_name"]} contains {record["canonical_name"]}.',
                attributes={
                    'membership_status': record['status'],
                    'seed_source': 'project_registry',
                },
            )
        )

    return edges


def seed_manifest_from_project_registry_records(
    records: list[dict[str, Any]],
    *,
    source_checked_at: datetime,
    extra_entities: list[SeedEntity] | None = None,
    extra_edges: list[SeedEdge] | None = None,
) -> SeedManifest:
    """Build a seed manifest from OpenSearch `project_registry` documents."""

    entities = [
        _registry_entity(record) for record in sorted(records, key=lambda item: item['project_id'])
    ]
    edges = _registry_parent_edges(records)

    if extra_entities:
        entities.extend(extra_entities)
    if extra_edges:
        edges.extend(extra_edges)

    return SeedManifest(
        manifest_id='exec_ea_seed_manifest_v1',
        version='1',
        name='Exec-EA seed manifest v1',
        description='Project registry seeds plus promoted benchmark seeds for the Exec-EA graph.',
        source='OpenSearch project_registry plus question-driven seed audit',
        source_checked_at=source_checked_at,
        entities=entities,
        edges=edges,
    )


def build_seed_nodes(
    manifest: SeedManifest, group_id: str, created_at: datetime | None = None
) -> dict[str, EntityNode]:
    """Build deterministic Graphiti entity nodes from a seed manifest."""

    now = created_at or utc_now()
    nodes: dict[str, EntityNode] = {}

    for entity in manifest.entities:
        if entity.entity_type not in ENTITY_TYPES:
            raise ValueError(f'Unknown Exec-EA entity type: {entity.entity_type}')
        if entity.seed_id in nodes:
            raise ValueError(f'Duplicate seed entity id: {entity.seed_id}')

        nodes[entity.seed_id] = EntityNode(
            uuid=seed_uuid(group_id, 'entity', entity.seed_id),
            name=entity.name,
            group_id=group_id,
            labels=[entity.entity_type],
            summary=entity.summary,
            attributes={
                **entity.attributes,
                'concept_key': entity.attributes.get('concept_key')
                or _concept_key(entity.attributes.get('canonical_label') or entity.name),
                'seed_role': entity.attributes.get('seed_role') or _seed_role(entity.entity_type),
                'seed_id': entity.seed_id,
                'seed_manifest_id': manifest.manifest_id,
                'seed_manifest_version': manifest.version,
            },
            created_at=now,
        )

    return nodes


def build_seed_edges(
    manifest: SeedManifest,
    group_id: str,
    seed_nodes: dict[str, EntityNode],
    created_at: datetime | None = None,
) -> list[EntityEdge]:
    """Build deterministic Graphiti entity edges from a seed manifest."""

    now = created_at or utc_now()
    edges: list[EntityEdge] = []
    seen_ids: set[str] = set()

    for edge in manifest.edges:
        if edge.edge_type not in EDGE_TYPES:
            raise ValueError(f'Unknown Exec-EA edge type: {edge.edge_type}')
        if edge.seed_id in seen_ids:
            raise ValueError(f'Duplicate seed edge id: {edge.seed_id}')
        if edge.source_seed_id not in seed_nodes:
            raise ValueError(f'Unknown source seed id: {edge.source_seed_id}')
        if edge.target_seed_id not in seed_nodes:
            raise ValueError(f'Unknown target seed id: {edge.target_seed_id}')

        seen_ids.add(edge.seed_id)
        edges.append(
            EntityEdge(
                uuid=seed_uuid(group_id, 'edge', edge.seed_id),
                group_id=group_id,
                source_node_uuid=seed_nodes[edge.source_seed_id].uuid,
                target_node_uuid=seed_nodes[edge.target_seed_id].uuid,
                created_at=now,
                name=edge.edge_type,
                fact=edge.fact,
                attributes={
                    **edge.attributes,
                    'seed_id': edge.seed_id,
                    'seed_manifest_id': manifest.manifest_id,
                    'seed_manifest_version': manifest.version,
                },
                valid_at=manifest.source_checked_at,
                reference_time=manifest.source_checked_at,
            )
        )

    return edges


def build_seed_manifest_episode(
    manifest: SeedManifest,
    group_id: str,
    entity_edges: list[EntityEdge],
    created_at: datetime | None = None,
) -> EpisodicNode:
    """Build the optional seed-manifest episode that preserves seed provenance."""

    now = created_at or utc_now()
    return EpisodicNode(
        uuid=seed_uuid(group_id, 'episode', manifest.manifest_id, manifest.version),
        name=manifest.name,
        group_id=group_id,
        labels=[],
        source=EpisodeType.json,
        source_description=manifest.source,
        content=json.dumps(manifest.model_dump(mode='json'), sort_keys=True),
        entity_edges=[edge.uuid for edge in entity_edges],
        valid_at=manifest.source_checked_at,
        created_at=now,
        episode_metadata={
            'source_kind': 'seed_manifest',
            'source_system': 'exec_ea',
            'source_id': manifest.manifest_id,
            'seed_manifest_version': manifest.version,
            'source_updated_at': manifest.source_checked_at.isoformat(),
        },
    )


def build_seed_episodic_edges(
    manifest: SeedManifest,
    group_id: str,
    manifest_episode: EpisodicNode,
    seed_nodes: dict[str, EntityNode],
    created_at: datetime | None = None,
) -> list[EpisodicEdge]:
    """Build deterministic MENTIONS edges from the manifest episode to every seed node."""

    now = created_at or utc_now()
    return [
        EpisodicEdge(
            uuid=seed_uuid(group_id, 'mentions', manifest.manifest_id, entity.seed_id),
            group_id=group_id,
            source_node_uuid=manifest_episode.uuid,
            target_node_uuid=seed_nodes[entity.seed_id].uuid,
            created_at=now,
        )
        for entity in manifest.entities
    ]


async def seed_exec_ea_graph(
    driver: GraphDriver,
    embedder: EmbedderClient,
    group_id: str,
    manifest: SeedManifest | None = None,
    *,
    include_manifest_episode: bool = True,
    created_at: datetime | None = None,
) -> SeedLoadResult:
    """Persist Exec-EA seeds as native Graphiti nodes, edges, and provenance episode."""

    seed_manifest = manifest or DEFAULT_SEED_MANIFEST
    seed_nodes = build_seed_nodes(seed_manifest, group_id, created_at)
    seed_edges = build_seed_edges(seed_manifest, group_id, seed_nodes, created_at)

    episodic_nodes: list[EpisodicNode] = []
    episodic_edges: list[EpisodicEdge] = []
    manifest_episode_uuid = None

    if include_manifest_episode:
        manifest_episode = build_seed_manifest_episode(
            seed_manifest, group_id, seed_edges, created_at
        )
        episodic_nodes.append(manifest_episode)
        episodic_edges = build_seed_episodic_edges(
            seed_manifest, group_id, manifest_episode, seed_nodes, created_at
        )
        manifest_episode_uuid = manifest_episode.uuid

    await add_nodes_and_edges_bulk(
        driver,
        episodic_nodes,
        episodic_edges,
        list(seed_nodes.values()),
        seed_edges,
        embedder,
    )

    return SeedLoadResult(
        manifest_episode_uuid=manifest_episode_uuid,
        node_uuids=[node.uuid for node in seed_nodes.values()],
        edge_uuids=[edge.uuid for edge in seed_edges],
        episodic_edge_uuids=[edge.uuid for edge in episodic_edges],
    )


PROJECT_REGISTRY_RECORDS_V1: list[dict[str, Any]] = [
    {
        'project_id': 1,
        'canonical_name': 'SASE',
        'kind': 'program',
        'parent_id': None,
        'status': 'active',
        'markers': [{'type': 'phrase', 'value': 'SASE', 'weight': 0.85}],
        'updated_at': '2026-05-28 02:48:08.395225+00:00',
    },
    {
        'project_id': 2,
        'canonical_name': 'Corrections (BC Attorney General trial)',
        'kind': 'project',
        'parent_id': 1,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'corrections', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Correctional Centres', 'weight': 0.85},
            {'type': 'phrase', 'value': "CC's", 'weight': 0.85},
            {'type': 'phrase', 'value': 'AG', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.397593+00:00',
    },
    {
        'project_id': 3,
        'canonical_name': 'Zscaler',
        'kind': 'project',
        'parent_id': 1,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'Zscaler', 'weight': 0.85},
            {'type': 'phrase', 'value': 'App Connector', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.398416+00:00',
    },
    {
        'project_id': 4,
        'canonical_name': 'Palo Alto Prisma Access',
        'kind': 'project',
        'parent_id': 1,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'Prisma Access', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Palo Alto', 'weight': 0.85},
            {'type': 'domain', 'value': 'paloaltonetworks.com', 'weight': 0.8},
            {'type': 'person', 'value': 'Ashley Anderson', 'weight': 0.65},
        ],
        'updated_at': '2026-05-28 02:48:08.399251+00:00',
    },
    {
        'project_id': 5,
        'canonical_name': 'CSM - Cyber Security Modernization',
        'kind': 'program',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'CSM', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Cyber Security Modernization', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Cyber Security Modernisation', 'weight': 0.85},
            {'type': 'domain', 'value': 'deloitte.ca', 'weight': 0.8},
        ],
        'updated_at': '2026-05-28 02:48:08.400139+00:00',
    },
    {
        'project_id': 6,
        'canonical_name': 'LINUS',
        'kind': 'project',
        'parent_id': 5,
        'status': 'active',
        'markers': [{'type': 'phrase', 'value': 'LINUS', 'weight': 0.85}],
        'updated_at': '2026-05-28 02:48:08.400882+00:00',
    },
    {
        'project_id': 7,
        'canonical_name': 'OAG audit',
        'kind': 'project',
        'parent_id': 5,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'OAG', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Office of the Auditor General', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.401664+00:00',
    },
    {
        'project_id': 8,
        'canonical_name': 'Agile (CSM)',
        'kind': 'project',
        'parent_id': 5,
        'status': 'active',
        'markers': [
            {'type': 'person', 'value': 'jyoti.kumar@phsa.ca', 'weight': 0.65},
            {'type': 'person', 'value': 'Kushagra Tripathi', 'weight': 0.65},
            {'type': 'person', 'value': 'ana.joshi@phsa.ca', 'weight': 0.65},
            {'type': 'phrase', 'value': 'Planner', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Jira', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Azure DevOps', 'weight': 0.85},
            {'type': 'phrase', 'value': 'ADO', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 18:02:26.933037+00:00',
    },
    {
        'project_id': 9,
        'canonical_name': 'Metrics/Reporting',
        'kind': 'project',
        'parent_id': 5,
        'status': 'active',
        'markers': [{'type': 'phrase', 'value': 'Metrics/Reporting', 'weight': 0.85}],
        'updated_at': '2026-05-28 02:48:08.403055+00:00',
    },
    {
        'project_id': 10,
        'canonical_name': 'SAFS',
        'kind': 'project',
        'parent_id': 5,
        'status': 'active',
        'markers': [
            {'type': 'person', 'value': 'robbanderson@deloitte.ca', 'weight': 0.65},
            {'type': 'person', 'value': 'robb.anderson@phsa.ca', 'weight': 0.65},
            {'type': 'phrase', 'value': 'SAFS', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 21:01:00.779280+00:00',
    },
    {
        'project_id': 11,
        'canonical_name': 'OCM',
        'kind': 'project',
        'parent_id': 5,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'OCM', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Organizational Change Management', 'weight': 0.85},
            {'type': 'person', 'value': 'jeff.dennler@deloitte.ca', 'weight': 0.65},
            {'type': 'person', 'value': 'amy.akers@deloitte.ca', 'weight': 0.65},
            {'type': 'person', 'value': 'hannah.johnstone@deloitte.ca', 'weight': 0.65},
            {'type': 'subject', 'value': 'More OCM', 'weight': 0.85},
            {
                'type': 'subject',
                'value': 'OCM Introduction for Azure Migration Support',
                'weight': 0.85,
            },
            {'type': 'subject', 'value': 'Cyber Security Team Design', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.404484+00:00',
    },
    {
        'project_id': 12,
        'canonical_name': 'Cerner',
        'kind': 'program',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'Cerner', 'weight': 0.85},
            {'type': 'phrase', 'value': 'OCI', 'weight': 0.85},
            {'type': 'phrase', 'value': 'PDHIS', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.405306+00:00',
    },
    {
        'project_id': 13,
        'canonical_name': 'Defender rollout',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'Defender for Endpoint', 'weight': 0.85},
            {'type': 'phrase', 'value': 'MDE', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.406032+00:00',
    },
    {
        'project_id': 14,
        'canonical_name': 'Darktrace',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'Darktrace', 'weight': 0.85},
            {'type': 'domain', 'value': 'darktrace.com', 'weight': 0.8},
        ],
        'updated_at': '2026-05-28 02:48:08.406744+00:00',
    },
    {
        'project_id': 15,
        'canonical_name': 'Resolver',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [{'type': 'phrase', 'value': 'Resolver', 'weight': 0.85}],
        'updated_at': '2026-05-28 02:48:08.407439+00:00',
    },
    {
        'project_id': 16,
        'canonical_name': 'Abnormal AI',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [{'type': 'phrase', 'value': 'Abnormal AI', 'weight': 0.85}],
        'updated_at': '2026-05-28 02:48:08.408114+00:00',
    },
    {
        'project_id': 17,
        'canonical_name': 'BlueVoyant',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'BlueVoyant', 'weight': 0.85},
            {'type': 'phrase', 'value': 'MXDR', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.408818+00:00',
    },
    {
        'project_id': 18,
        'canonical_name': 'CrowdStrike',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'CrowdStrike', 'weight': 0.85},
            {'type': 'phrase', 'value': 'CS Renewal', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.409518+00:00',
    },
    {
        'project_id': 19,
        'canonical_name': 'RedOps pen-test',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [{'type': 'phrase', 'value': 'RedOps', 'weight': 0.85}],
        'updated_at': '2026-05-28 02:48:08.410221+00:00',
    },
    {
        'project_id': 20,
        'canonical_name': 'Securin.io POC',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'Securin', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Securin.io', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.410923+00:00',
    },
    {
        'project_id': 21,
        'canonical_name': 'VMO - Vulnerability Management Office',
        'kind': 'program',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'VMO', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Vulnerability Management Office', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.411658+00:00',
    },
    {
        'project_id': 22,
        'canonical_name': 'STRA (internal)',
        'kind': 'program',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'STRA', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Security Threat and Risk Assessment', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.412363+00:00',
    },
    {
        'project_id': 23,
        'canonical_name': 'AI Governance',
        'kind': 'program',
        'parent_id': None,
        'status': 'active',
        'markers': [{'type': 'phrase', 'value': 'AI Governance', 'weight': 0.85}],
        'updated_at': '2026-05-28 02:48:08.413071+00:00',
    },
    {
        'project_id': 24,
        'canonical_name': 'Data Governance',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'Purview', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Protiviti', 'weight': 0.85},
            {'type': 'domain', 'value': 'protiviti.com', 'weight': 0.8},
            {'type': 'phrase', 'value': 'Varonis', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Data Governance', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 21:01:00.779280+00:00',
    },
    {
        'project_id': 25,
        'canonical_name': 'Service Catalogue',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'Service Catalogue', 'weight': 0.85},
            {'type': 'phrase', 'value': 'Service Catalog', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.414623+00:00',
    },
    {
        'project_id': 26,
        'canonical_name': 'Azure Migration',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [{'type': 'phrase', 'value': 'Azure Migration', 'weight': 0.85}],
        'updated_at': '2026-05-28 02:48:08.415312+00:00',
    },
    {
        'project_id': 27,
        'canonical_name': 'FairWarning',
        'kind': 'project',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'FairWarning', 'weight': 0.85},
            {'type': 'phrase', 'value': 'P2Sentinel', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 21:01:00.779280+00:00',
    },
    {
        'project_id': 28,
        'canonical_name': 'Shared Services - BC Shared Health Services',
        'kind': 'program',
        'parent_id': None,
        'status': 'active',
        'markers': [
            {'type': 'phrase', 'value': 'BCHSHS', 'weight': 0.85},
            {'type': 'phrase', 'value': 'BC Shared Health Services', 'weight': 0.85},
            {'type': 'phrase', 'value': 'BC Health Shared Services', 'weight': 0.85},
            {'type': 'phrase', 'value': 'HA Transformation', 'weight': 0.85},
            {'type': 'person', 'value': 'Brent Kruschel', 'weight': 0.65},
            {'type': 'phrase', 'value': 'Shared Services', 'weight': 0.85},
            {'type': 'phrase', 'value': 'BCSHS', 'weight': 0.85},
        ],
        'updated_at': '2026-05-28 02:48:08.416804+00:00',
    },
]


PROMOTED_SEED_ENTITIES_V1: list[SeedEntity] = [
    SeedEntity(
        seed_id='organization:phsa',
        entity_type='Organization',
        name='PHSA',
        summary='Provincial Health Services Authority organization seed.',
        attributes={
            'canonical_label': 'PHSA',
            'aliases': ['Provincial Health Services Authority', 'phsa.ca'],
            'domain': 'phsa.ca',
            'organization_kind': 'health authority',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor:deloitte',
        entity_type='Vendor',
        name='Deloitte',
        summary='Deloitte vendor and advisory partner seed.',
        attributes={
            'canonical_label': 'Deloitte',
            'aliases': ['deloitte.ca'],
            'domain': 'deloitte.ca',
            'organization_kind': 'vendor',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor:forecight',
        entity_type='Vendor',
        name='Forecight',
        summary='Forecight STRA and cybersecurity assessment partner seed.',
        attributes={
            'canonical_label': 'Forecight',
            'organization_kind': 'vendor',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor:microsoft',
        entity_type='Vendor',
        name='Microsoft',
        summary='Microsoft platform vendor seed.',
        attributes={
            'canonical_label': 'Microsoft',
            'aliases': ['microsoft.com'],
            'domain': 'microsoft.com',
            'organization_kind': 'vendor',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor:palo-alto',
        entity_type='Vendor',
        name='Palo Alto Networks',
        summary='Palo Alto Networks vendor seed for Prisma Access context.',
        attributes={
            'canonical_label': 'Palo Alto Networks',
            'aliases': ['Palo Alto', 'paloaltonetworks.com'],
            'domain': 'paloaltonetworks.com',
            'organization_kind': 'vendor',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor:varonis',
        entity_type='Vendor',
        name='Varonis',
        summary='Varonis vendor seed for data governance context.',
        attributes={
            'canonical_label': 'Varonis',
            'organization_kind': 'vendor',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor:imprivata',
        entity_type='Vendor',
        name='Imprivata',
        summary='Imprivata vendor seed for FairWarning/P2Sentinel context.',
        attributes={
            'canonical_label': 'Imprivata',
            'organization_kind': 'vendor',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor:oracle',
        entity_type='Vendor',
        name='Oracle',
        summary='Oracle vendor seed for OCI and Cerner context.',
        attributes={
            'canonical_label': 'Oracle',
            'organization_kind': 'vendor',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor:crowdstrike',
        entity_type='Vendor',
        name='CrowdStrike',
        summary='CrowdStrike vendor seed, kept separate from project and platform contexts.',
        attributes={
            'canonical_label': 'CrowdStrike',
            'organization_kind': 'vendor',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor:protiviti',
        entity_type='Vendor',
        name='Protiviti',
        summary='Protiviti vendor seed for Data Governance context.',
        attributes={
            'canonical_label': 'Protiviti',
            'aliases': ['protiviti.com'],
            'domain': 'protiviti.com',
            'organization_kind': 'vendor',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='platform:defender-mde',
        entity_type='Platform',
        name='Microsoft Defender for Endpoint',
        summary='Defender/MDE endpoint security platform seed.',
        attributes={
            'canonical_label': 'Microsoft Defender for Endpoint',
            'aliases': ['Defender', 'MDE', 'Defender for Endpoint'],
            'vendor_hint': 'Microsoft',
            'product_family': 'endpoint security',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='platform:crowdstrike',
        entity_type='Platform',
        name='CrowdStrike Falcon',
        summary='CrowdStrike endpoint security platform seed.',
        attributes={
            'canonical_label': 'CrowdStrike Falcon',
            'aliases': ['CrowdStrike', 'CS Renewal'],
            'vendor_hint': 'CrowdStrike',
            'product_family': 'endpoint security',
            'concept_key': 'crowdstrike',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='platform:purview',
        entity_type='Platform',
        name='Microsoft Purview',
        summary='Purview data governance platform seed.',
        attributes={
            'canonical_label': 'Microsoft Purview',
            'aliases': ['Purview'],
            'vendor_hint': 'Microsoft',
            'product_family': 'data governance',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='platform:copilot',
        entity_type='Platform',
        name='Microsoft Copilot',
        summary='Copilot platform seed for AI and Purview/Copilot working group context.',
        attributes={
            'canonical_label': 'Microsoft Copilot',
            'aliases': ['Copilot', 'M365 Copilot'],
            'vendor_hint': 'Microsoft',
            'product_family': 'AI productivity',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='platform:varonis',
        entity_type='Platform',
        name='Varonis',
        summary='Varonis data security and governance platform seed.',
        attributes={
            'canonical_label': 'Varonis',
            'vendor_hint': 'Varonis',
            'product_family': 'data security',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='platform:oracle-oci',
        entity_type='Platform',
        name='Oracle OCI',
        summary='Oracle Cloud Infrastructure platform seed for Cerner context.',
        attributes={
            'canonical_label': 'Oracle OCI',
            'aliases': ['OCI', 'Oracle Cloud Infrastructure'],
            'vendor_hint': 'Oracle',
            'product_family': 'cloud infrastructure',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='platform:forescout',
        entity_type='Platform',
        name='Forescout',
        summary='Forescout platform seed, explicitly distinct from Forecight.',
        attributes={
            'canonical_label': 'Forescout',
            'vendor_hint': 'Forescout',
            'product_family': 'network access control',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='platform:medigate',
        entity_type='Platform',
        name='Medigate',
        summary='Medigate platform seed.',
        attributes={
            'canonical_label': 'Medigate',
            'product_family': 'medical device security',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='platform:fairwarning',
        entity_type='Platform',
        name='FairWarning',
        summary='FairWarning/P2Sentinel platform seed.',
        attributes={
            'canonical_label': 'FairWarning',
            'aliases': ['P2Sentinel'],
            'vendor_hint': 'Imprivata',
            'product_family': 'privacy monitoring',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='platform:zscaler',
        entity_type='Platform',
        name='Zscaler',
        summary='Zscaler platform seed.',
        attributes={
            'canonical_label': 'Zscaler',
            'aliases': ['App Connector'],
            'vendor_hint': 'Zscaler',
            'product_family': 'secure access service edge',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='platform:darktrace',
        entity_type='Platform',
        name='Darktrace',
        summary='Darktrace platform seed.',
        attributes={
            'canonical_label': 'Darktrace',
            'vendor_hint': 'Darktrace',
            'product_family': 'cybersecurity',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='platform:securin',
        entity_type='Platform',
        name='Securin.io',
        summary='Securin.io platform seed for POC context.',
        attributes={
            'canonical_label': 'Securin.io',
            'aliases': ['Securin'],
            'vendor_hint': 'Securin',
            'product_family': 'security assessment',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='person:michael-dobson',
        entity_type='Person',
        name='Michael Dobson',
        summary='Primary graph subject and executive assistant user.',
        attributes={
            'canonical_label': 'Michael Dobson',
            'aliases': ['Michael', 'mike'],
            'organization_hint': 'PHSA',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='person:hardeep-parwana',
        entity_type='Person',
        name='Hardeep Parwana',
        summary='High-coverage person seed for recurring 1:1 and workstream context.',
        attributes={
            'canonical_label': 'Hardeep Parwana',
            'aliases': ['Hardeep'],
            'organization_hint': 'PHSA',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='person:derek-lucas',
        entity_type='Person',
        name='Derek Lucas',
        summary='High-coverage person seed for bidirectional obligation checks.',
        attributes={
            'canonical_label': 'Derek Lucas',
            'aliases': ['Derek'],
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='person:jamie-ross',
        entity_type='Person',
        name='Jamie Ross',
        summary='Deloitte contact seed for person dossier and project collaboration queries.',
        attributes={
            'canonical_label': 'Jamie Ross',
            'aliases': ['Jamie Ross', 'jaross@deloitte.ca'],
            'canonical_email': 'jaross@deloitte.ca',
            'organization_hint': 'Deloitte',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='person:jennifer-dury',
        entity_type='Person',
        name='Jennifer Dury',
        summary='Person seed from benchmark seed priorities.',
        attributes={
            'canonical_label': 'Jennifer Dury',
            'aliases': ['Jennifer', 'Jen Dury'],
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='person:ali-deheshi',
        entity_type='Person',
        name='Ali Deheshi',
        summary='Person seed from benchmark seed priorities.',
        attributes={
            'canonical_label': 'Ali Deheshi',
            'aliases': ['Ali'],
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='series:csm-executive-meeting',
        entity_type='MeetingSeries',
        name='CSM Executive Meeting',
        summary='Recurring CSM Executive Meeting series seed.',
        attributes={
            'canonical_label': 'CSM Executive Meeting',
            'series_key': 'csm_executive_meeting',
            'aliases': ['CSM Exec', 'CSM Executive'],
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='series:forecight-monthly-cybersecurity-sync',
        entity_type='MeetingSeries',
        name='Forecight/PHSA Monthly Cybersecurity Sync',
        summary='Recurring Forecight and PHSA cybersecurity sync series seed.',
        attributes={
            'canonical_label': 'Forecight/PHSA Monthly Cybersecurity Sync',
            'series_key': 'forecight_phsa_monthly_cybersecurity_sync',
            'aliases': ['Forecight monthly cybersecurity sync', 'PHSA cybersecurity sync'],
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='series:hardeep-michael-1-1',
        entity_type='MeetingSeries',
        name='1:1 w/Hardeep & Michael',
        summary='Recurring one-on-one between Hardeep and Michael.',
        attributes={
            'canonical_label': '1:1 w/Hardeep & Michael',
            'series_key': 'hardeep_michael_1_1',
            'aliases': ['Hardeep 1:1', '1:1 with Hardeep'],
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='series:leadership-team-meeting',
        entity_type='MeetingSeries',
        name='Leadership Team Meeting',
        summary='Recurring Leadership Team Meeting series seed.',
        attributes={
            'canonical_label': 'Leadership Team Meeting',
            'series_key': 'leadership_team_meeting',
            'aliases': ['Leadership Team', 'LT Meeting'],
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='series:microsoft-purview-copilot-working-group',
        entity_type='MeetingSeries',
        name='Microsoft Offer / Purview & Copilot Working Group',
        summary='Purview, Copilot, and Microsoft offer working-group series seed.',
        attributes={
            'canonical_label': 'Microsoft Offer / Purview & Copilot Working Group',
            'series_key': 'microsoft_purview_copilot_working_group',
            'aliases': ['Purview/Copilot working group', 'Microsoft Offer'],
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='document:patient-portal-closure-report',
        entity_type='Document',
        name='Patient Portal closure report',
        summary='Pilot deliverable seed for Patient Portal closure report tracking.',
        attributes={
            'canonical_label': 'Patient Portal closure report',
            'document_kind': 'closure report',
            'aliases': ['Patient Portal closure', 'Patient Portal closure report'],
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='document:defender-endpoint-count-artifacts',
        entity_type='Document',
        name='Defender endpoint-count source artifacts',
        summary='Pilot document family seed for Defender endpoint-count tables.',
        attributes={
            'canonical_label': 'Defender endpoint-count source artifacts',
            'document_kind': 'document family',
            'aliases': ['endpoint count', 'Defender rollout endpoint count'],
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='document:budget-savings-workbook',
        entity_type='Document',
        name='Budget savings workbook',
        summary='Locator-pending document seed for budget savings workbook queries.',
        attributes={
            'canonical_label': 'Budget savings workbook',
            'document_kind': 'workbook',
            'version_label': 'locator pending',
            'seed_source': 'question_seed_audit',
        },
    ),
]


ROLE_DISAMBIGUATION_SEED_ENTITIES_V1: list[SeedEntity] = [
    SeedEntity(
        seed_id='vendor:zscaler',
        entity_type='Vendor',
        name='Zscaler',
        summary='Zscaler vendor seed, separate from the SASE project and platform contexts.',
        attributes={
            'canonical_label': 'Zscaler',
            'organization_kind': 'vendor',
            'concept_key': 'zscaler',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='vendor:darktrace',
        entity_type='Vendor',
        name='Darktrace',
        summary='Darktrace vendor seed, separate from the project and platform contexts.',
        attributes={
            'canonical_label': 'Darktrace',
            'aliases': ['darktrace.com'],
            'domain': 'darktrace.com',
            'organization_kind': 'vendor',
            'concept_key': 'darktrace',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='vendor:securin',
        entity_type='Vendor',
        name='Securin',
        summary='Securin vendor seed, separate from the Securin.io POC project.',
        attributes={
            'canonical_label': 'Securin',
            'aliases': ['Securin.io'],
            'organization_kind': 'vendor',
            'concept_key': 'securin',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='vendor:bluevoyant',
        entity_type='Vendor',
        name='BlueVoyant',
        summary='BlueVoyant vendor seed, separate from MXDR project/platform context.',
        attributes={
            'canonical_label': 'BlueVoyant',
            'organization_kind': 'vendor',
            'concept_key': 'bluevoyant',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='vendor:abnormal-security',
        entity_type='Vendor',
        name='Abnormal Security',
        summary='Abnormal Security vendor seed for Abnormal AI context.',
        attributes={
            'canonical_label': 'Abnormal Security',
            'aliases': ['Abnormal AI'],
            'organization_kind': 'vendor',
            'concept_key': 'abnormal-ai',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='vendor:resolver',
        entity_type='Vendor',
        name='Resolver',
        summary='Resolver vendor seed, separate from Resolver project/product context.',
        attributes={
            'canonical_label': 'Resolver',
            'organization_kind': 'vendor',
            'concept_key': 'resolver',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='vendor:forescout',
        entity_type='Vendor',
        name='Forescout',
        summary='Forescout vendor seed, explicitly distinct from Forecight.',
        attributes={
            'canonical_label': 'Forescout',
            'organization_kind': 'vendor',
            'concept_key': 'forescout',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor:medigate',
        entity_type='Vendor',
        name='Medigate',
        summary='Medigate vendor seed for medical device security platform context.',
        attributes={
            'canonical_label': 'Medigate',
            'organization_kind': 'vendor',
            'concept_key': 'medigate',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='platform:palo-alto-prisma-access',
        entity_type='Platform',
        name='Palo Alto Prisma Access',
        summary='Prisma Access platform seed, separate from the SASE project context.',
        attributes={
            'canonical_label': 'Palo Alto Prisma Access',
            'aliases': ['Prisma Access', 'Palo Alto'],
            'vendor_hint': 'Palo Alto Networks',
            'product_family': 'secure access service edge',
            'concept_key': 'palo-alto-prisma-access',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='platform:bluevoyant-mxdr',
        entity_type='Platform',
        name='BlueVoyant MXDR',
        summary='BlueVoyant MXDR platform seed, separate from the registry project.',
        attributes={
            'canonical_label': 'BlueVoyant MXDR',
            'aliases': ['BlueVoyant', 'MXDR'],
            'vendor_hint': 'BlueVoyant',
            'product_family': 'managed detection and response',
            'concept_key': 'bluevoyant',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='platform:abnormal-ai',
        entity_type='Platform',
        name='Abnormal AI',
        summary='Abnormal AI email security platform seed.',
        attributes={
            'canonical_label': 'Abnormal AI',
            'vendor_hint': 'Abnormal Security',
            'product_family': 'email security',
            'concept_key': 'abnormal-ai',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='platform:resolver',
        entity_type='Platform',
        name='Resolver',
        summary='Resolver platform seed, separate from the project and vendor contexts.',
        attributes={
            'canonical_label': 'Resolver',
            'vendor_hint': 'Resolver',
            'product_family': 'risk management',
            'concept_key': 'resolver',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='vendor_product:prisma-access',
        entity_type='VendorProduct',
        name='Prisma Access',
        summary='Prisma Access vendor product seed supplied by Palo Alto Networks.',
        attributes={
            'canonical_label': 'Prisma Access',
            'vendor_hint': 'Palo Alto Networks',
            'product_category': 'secure access service edge',
            'concept_key': 'palo-alto-prisma-access',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='vendor_product:defender-for-endpoint',
        entity_type='VendorProduct',
        name='Defender for Endpoint',
        summary='Defender for Endpoint vendor product seed supplied by Microsoft.',
        attributes={
            'canonical_label': 'Defender for Endpoint',
            'aliases': ['MDE'],
            'vendor_hint': 'Microsoft',
            'product_category': 'endpoint security',
            'concept_key': 'defender-rollout',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor_product:crowdstrike-falcon',
        entity_type='VendorProduct',
        name='CrowdStrike Falcon',
        summary='CrowdStrike Falcon vendor product seed.',
        attributes={
            'canonical_label': 'CrowdStrike Falcon',
            'aliases': ['CrowdStrike'],
            'vendor_hint': 'CrowdStrike',
            'product_category': 'endpoint security',
            'concept_key': 'crowdstrike',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEntity(
        seed_id='vendor_product:bluevoyant-mxdr',
        entity_type='VendorProduct',
        name='BlueVoyant MXDR',
        summary='BlueVoyant MXDR vendor product seed.',
        attributes={
            'canonical_label': 'BlueVoyant MXDR',
            'vendor_hint': 'BlueVoyant',
            'product_category': 'managed detection and response',
            'concept_key': 'bluevoyant',
            'seed_source': 'project_registry',
        },
    ),
    SeedEntity(
        seed_id='vendor_product:fairwarning-p2sentinel',
        entity_type='VendorProduct',
        name='FairWarning/P2Sentinel',
        summary='FairWarning/P2Sentinel vendor product seed supplied by Imprivata.',
        attributes={
            'canonical_label': 'FairWarning/P2Sentinel',
            'aliases': ['FairWarning', 'P2Sentinel'],
            'vendor_hint': 'Imprivata',
            'product_category': 'privacy monitoring',
            'concept_key': 'fairwarning',
            'seed_source': 'project_registry',
        },
    ),
]


PROMOTED_SEED_EDGES_V1: list[SeedEdge] = [
    SeedEdge(
        seed_id='vendor:microsoft:provides:platform:defender-mde',
        source_seed_id='vendor:microsoft',
        target_seed_id='platform:defender-mde',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Microsoft provides Microsoft Defender for Endpoint.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='vendor:microsoft:provides:platform:purview',
        source_seed_id='vendor:microsoft',
        target_seed_id='platform:purview',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Microsoft provides Microsoft Purview.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='vendor:microsoft:provides:platform:copilot',
        source_seed_id='vendor:microsoft',
        target_seed_id='platform:copilot',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Microsoft provides Microsoft Copilot.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='vendor:crowdstrike:provides:platform:crowdstrike',
        source_seed_id='vendor:crowdstrike',
        target_seed_id='platform:crowdstrike',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='CrowdStrike provides the CrowdStrike Falcon platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='vendor:varonis:provides:platform:varonis',
        source_seed_id='vendor:varonis',
        target_seed_id='platform:varonis',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Varonis provides the Varonis platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='vendor:oracle:provides:platform:oracle-oci',
        source_seed_id='vendor:oracle',
        target_seed_id='platform:oracle-oci',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Oracle provides Oracle OCI.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='vendor:imprivata:provides:platform:fairwarning',
        source_seed_id='vendor:imprivata',
        target_seed_id='platform:fairwarning',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Imprivata provides the FairWarning/P2Sentinel platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='project_registry:13:involves:platform:defender-mde',
        source_seed_id='project_registry:13',
        target_seed_id='platform:defender-mde',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Defender rollout project involves Microsoft Defender for Endpoint.',
        attributes={'involvement': 'deploys', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='project_registry:18:involves:platform:crowdstrike',
        source_seed_id='project_registry:18',
        target_seed_id='platform:crowdstrike',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The CrowdStrike project involves the CrowdStrike Falcon platform.',
        attributes={
            'involvement': 'renewal or migration context',
            'seed_source': 'project_registry',
        },
    ),
    SeedEdge(
        seed_id='project_registry:24:involves:platform:purview',
        source_seed_id='project_registry:24',
        target_seed_id='platform:purview',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Data Governance project involves Microsoft Purview.',
        attributes={'involvement': 'governs', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:24:involves:platform:varonis',
        source_seed_id='project_registry:24',
        target_seed_id='platform:varonis',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Data Governance project involves Varonis.',
        attributes={'involvement': 'governs', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:12:involves:platform:oracle-oci',
        source_seed_id='project_registry:12',
        target_seed_id='platform:oracle-oci',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Cerner program involves Oracle OCI.',
        attributes={'involvement': 'cloud infrastructure', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:3:involves:platform:zscaler',
        source_seed_id='project_registry:3',
        target_seed_id='platform:zscaler',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Zscaler project involves the Zscaler platform.',
        attributes={'involvement': 'deploys', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:14:involves:platform:darktrace',
        source_seed_id='project_registry:14',
        target_seed_id='platform:darktrace',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Darktrace project involves the Darktrace platform.',
        attributes={'involvement': 'platform context', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:20:involves:platform:securin',
        source_seed_id='project_registry:20',
        target_seed_id='platform:securin',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Securin.io POC project involves Securin.io.',
        attributes={'involvement': 'proof of concept', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:27:involves:platform:fairwarning',
        source_seed_id='project_registry:27',
        target_seed_id='platform:fairwarning',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The FairWarning project involves the FairWarning/P2Sentinel platform.',
        attributes={'involvement': 'platform context', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='person:jamie-ross:works-for:vendor:deloitte',
        source_seed_id='person:jamie-ross',
        target_seed_id='vendor:deloitte',
        edge_type='PERSON_WORKS_FOR_ORG',
        fact='Jamie Ross works with Deloitte.',
        attributes={'role_title': None, 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='person:michael-dobson:works-for:organization:phsa',
        source_seed_id='person:michael-dobson',
        target_seed_id='organization:phsa',
        edge_type='PERSON_WORKS_FOR_ORG',
        fact='Michael Dobson works with PHSA.',
        attributes={'role_title': None, 'seed_source': 'question_seed_audit'},
    ),
]


ROLE_DISAMBIGUATION_SEED_EDGES_V1: list[SeedEdge] = [
    SeedEdge(
        seed_id='vendor:zscaler:provides:platform:zscaler',
        source_seed_id='vendor:zscaler',
        target_seed_id='platform:zscaler',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Zscaler provides the Zscaler platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='vendor:palo-alto:provides:platform:palo-alto-prisma-access',
        source_seed_id='vendor:palo-alto',
        target_seed_id='platform:palo-alto-prisma-access',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Palo Alto Networks provides the Prisma Access platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='vendor:palo-alto:provides:vendor_product:prisma-access',
        source_seed_id='vendor:palo-alto',
        target_seed_id='vendor_product:prisma-access',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Palo Alto Networks provides the Prisma Access vendor product.',
        attributes={'provider_role': 'vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='vendor:microsoft:provides:vendor_product:defender-for-endpoint',
        source_seed_id='vendor:microsoft',
        target_seed_id='vendor_product:defender-for-endpoint',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Microsoft provides Defender for Endpoint.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='vendor:crowdstrike:provides:vendor_product:crowdstrike-falcon',
        source_seed_id='vendor:crowdstrike',
        target_seed_id='vendor_product:crowdstrike-falcon',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='CrowdStrike provides CrowdStrike Falcon.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='vendor:darktrace:provides:platform:darktrace',
        source_seed_id='vendor:darktrace',
        target_seed_id='platform:darktrace',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Darktrace provides the Darktrace platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='vendor:securin:provides:platform:securin',
        source_seed_id='vendor:securin',
        target_seed_id='platform:securin',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Securin provides the Securin.io platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='vendor:bluevoyant:provides:platform:bluevoyant-mxdr',
        source_seed_id='vendor:bluevoyant',
        target_seed_id='platform:bluevoyant-mxdr',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='BlueVoyant provides the BlueVoyant MXDR platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='vendor:bluevoyant:provides:vendor_product:bluevoyant-mxdr',
        source_seed_id='vendor:bluevoyant',
        target_seed_id='vendor_product:bluevoyant-mxdr',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='BlueVoyant provides the BlueVoyant MXDR vendor product.',
        attributes={'provider_role': 'vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='vendor:abnormal-security:provides:platform:abnormal-ai',
        source_seed_id='vendor:abnormal-security',
        target_seed_id='platform:abnormal-ai',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Abnormal Security provides the Abnormal AI platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='vendor:resolver:provides:platform:resolver',
        source_seed_id='vendor:resolver',
        target_seed_id='platform:resolver',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Resolver provides the Resolver platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='vendor:forescout:provides:platform:forescout',
        source_seed_id='vendor:forescout',
        target_seed_id='platform:forescout',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Forescout provides the Forescout platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='vendor:medigate:provides:platform:medigate',
        source_seed_id='vendor:medigate',
        target_seed_id='platform:medigate',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Medigate provides the Medigate platform.',
        attributes={'provider_role': 'vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='vendor:imprivata:provides:vendor_product:fairwarning-p2sentinel',
        source_seed_id='vendor:imprivata',
        target_seed_id='vendor_product:fairwarning-p2sentinel',
        edge_type='VENDOR_PROVIDES_PLATFORM',
        fact='Imprivata provides the FairWarning/P2Sentinel vendor product.',
        attributes={'provider_role': 'vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:3:has-vendor:vendor:zscaler',
        source_seed_id='project_registry:3',
        target_seed_id='vendor:zscaler',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The Zscaler project has Zscaler as a vendor context.',
        attributes={'vendor_role': 'platform vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:4:involves:platform:palo-alto-prisma-access',
        source_seed_id='project_registry:4',
        target_seed_id='platform:palo-alto-prisma-access',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Palo Alto Prisma Access project involves the Prisma Access platform.',
        attributes={'involvement': 'deploys', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:4:involves:vendor_product:prisma-access',
        source_seed_id='project_registry:4',
        target_seed_id='vendor_product:prisma-access',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Palo Alto Prisma Access project involves the Prisma Access vendor product.',
        attributes={'involvement': 'deploys', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:4:has-vendor:vendor:palo-alto',
        source_seed_id='project_registry:4',
        target_seed_id='vendor:palo-alto',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The Palo Alto Prisma Access project has Palo Alto Networks as a vendor context.',
        attributes={'vendor_role': 'platform vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:13:involves:vendor_product:defender-for-endpoint',
        source_seed_id='project_registry:13',
        target_seed_id='vendor_product:defender-for-endpoint',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Defender rollout project involves the Defender for Endpoint vendor product.',
        attributes={'involvement': 'deploys', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='project_registry:13:has-vendor:vendor:microsoft',
        source_seed_id='project_registry:13',
        target_seed_id='vendor:microsoft',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The Defender rollout project has Microsoft as a vendor context.',
        attributes={'vendor_role': 'platform vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='project_registry:14:has-vendor:vendor:darktrace',
        source_seed_id='project_registry:14',
        target_seed_id='vendor:darktrace',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The Darktrace project has Darktrace as a vendor context.',
        attributes={'vendor_role': 'platform vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:16:involves:platform:abnormal-ai',
        source_seed_id='project_registry:16',
        target_seed_id='platform:abnormal-ai',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The Abnormal AI project involves the Abnormal AI platform.',
        attributes={'involvement': 'platform context', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:16:has-vendor:vendor:abnormal-security',
        source_seed_id='project_registry:16',
        target_seed_id='vendor:abnormal-security',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The Abnormal AI project has Abnormal Security as a vendor context.',
        attributes={'vendor_role': 'platform vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:17:involves:platform:bluevoyant-mxdr',
        source_seed_id='project_registry:17',
        target_seed_id='platform:bluevoyant-mxdr',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The BlueVoyant project involves the BlueVoyant MXDR platform.',
        attributes={'involvement': 'platform context', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:17:involves:vendor_product:bluevoyant-mxdr',
        source_seed_id='project_registry:17',
        target_seed_id='vendor_product:bluevoyant-mxdr',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The BlueVoyant project involves the BlueVoyant MXDR vendor product.',
        attributes={'involvement': 'platform context', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:17:has-vendor:vendor:bluevoyant',
        source_seed_id='project_registry:17',
        target_seed_id='vendor:bluevoyant',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The BlueVoyant project has BlueVoyant as a vendor context.',
        attributes={'vendor_role': 'platform vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:18:involves:vendor_product:crowdstrike-falcon',
        source_seed_id='project_registry:18',
        target_seed_id='vendor_product:crowdstrike-falcon',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The CrowdStrike project involves the CrowdStrike Falcon vendor product.',
        attributes={
            'involvement': 'renewal or migration context',
            'seed_source': 'question_seed_audit',
        },
    ),
    SeedEdge(
        seed_id='project_registry:18:has-vendor:vendor:crowdstrike',
        source_seed_id='project_registry:18',
        target_seed_id='vendor:crowdstrike',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The CrowdStrike project has CrowdStrike as a vendor context.',
        attributes={'vendor_role': 'platform vendor', 'seed_source': 'question_seed_audit'},
    ),
    SeedEdge(
        seed_id='project_registry:20:has-vendor:vendor:securin',
        source_seed_id='project_registry:20',
        target_seed_id='vendor:securin',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The Securin.io POC project has Securin as a vendor context.',
        attributes={'vendor_role': 'platform vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:24:has-vendor:vendor:protiviti',
        source_seed_id='project_registry:24',
        target_seed_id='vendor:protiviti',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The Data Governance project has Protiviti as a vendor context.',
        attributes={
            'vendor_role': 'advisory or implementation vendor',
            'seed_source': 'project_registry',
        },
    ),
    SeedEdge(
        seed_id='project_registry:24:has-vendor:vendor:varonis',
        source_seed_id='project_registry:24',
        target_seed_id='vendor:varonis',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The Data Governance project has Varonis as a vendor context.',
        attributes={'vendor_role': 'platform vendor', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:27:involves:vendor_product:fairwarning-p2sentinel',
        source_seed_id='project_registry:27',
        target_seed_id='vendor_product:fairwarning-p2sentinel',
        edge_type='PROJECT_INVOLVES_PLATFORM',
        fact='The FairWarning project involves the FairWarning/P2Sentinel vendor product.',
        attributes={'involvement': 'platform context', 'seed_source': 'project_registry'},
    ),
    SeedEdge(
        seed_id='project_registry:27:has-vendor:vendor:imprivata',
        source_seed_id='project_registry:27',
        target_seed_id='vendor:imprivata',
        edge_type='PROJECT_HAS_VENDOR',
        fact='The FairWarning project has Imprivata as a vendor context.',
        attributes={'vendor_role': 'platform vendor', 'seed_source': 'question_seed_audit'},
    ),
]


DEFAULT_SEED_MANIFEST = seed_manifest_from_project_registry_records(
    PROJECT_REGISTRY_RECORDS_V1,
    source_checked_at=datetime.fromisoformat('2026-06-05T00:00:00+00:00'),
    extra_entities=PROMOTED_SEED_ENTITIES_V1 + ROLE_DISAMBIGUATION_SEED_ENTITIES_V1,
    extra_edges=PROMOTED_SEED_EDGES_V1 + ROLE_DISAMBIGUATION_SEED_EDGES_V1,
)
