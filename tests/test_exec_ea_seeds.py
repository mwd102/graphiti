from datetime import datetime, timezone

from graphiti_core.edges import EntityEdge, EpisodicEdge
from graphiti_core.exec_ea import (
    DEFAULT_SEED_MANIFEST,
    PROJECT_REGISTRY_RECORDS_V1,
    build_seed_edges,
    build_seed_episodic_edges,
    build_seed_manifest_episode,
    build_seed_nodes,
    seed_manifest_from_project_registry_records,
    seed_uuid,
)
from graphiti_core.nodes import EntityNode, EpisodeType, EpisodicNode


def _is_neo4j_property_value(value: object) -> bool:
    primitive = str | int | float | bool
    return (
        value is None
        or isinstance(value, primitive)
        or (isinstance(value, list) and all(isinstance(item, primitive) for item in value))
    )


def test_default_seed_manifest_contains_live_project_registry_snapshot() -> None:
    registry_entities = [
        entity
        for entity in DEFAULT_SEED_MANIFEST.entities
        if entity.seed_id.startswith('project_registry:')
    ]
    programs = [entity for entity in registry_entities if entity.entity_type == 'Program']
    projects = [entity for entity in registry_entities if entity.entity_type == 'Project']

    assert len(PROJECT_REGISTRY_RECORDS_V1) == 28
    assert len(registry_entities) == 28
    assert len(programs) == 7
    assert len(projects) == 21


def test_default_seed_manifest_contains_benchmark_seeds() -> None:
    seed_ids = {entity.seed_id for entity in DEFAULT_SEED_MANIFEST.entities}

    assert 'platform:defender-mde' in seed_ids
    assert 'platform:palo-alto-prisma-access' in seed_ids
    assert 'platform:bluevoyant-mxdr' in seed_ids
    assert 'platform:abnormal-ai' in seed_ids
    assert 'platform:resolver' in seed_ids
    assert 'platform:oracle-oci' in seed_ids
    assert 'vendor:forecight' in seed_ids
    assert 'vendor:zscaler' in seed_ids
    assert 'vendor:darktrace' in seed_ids
    assert 'vendor:securin' in seed_ids
    assert 'vendor:forescout' in seed_ids
    assert 'vendor:medigate' in seed_ids
    assert 'vendor_product:prisma-access' in seed_ids
    assert 'vendor_product:crowdstrike-falcon' in seed_ids
    assert 'person:hardeep-parwana' in seed_ids
    assert 'person:derek-lucas' in seed_ids
    assert 'person:jamie-ross' in seed_ids
    assert 'series:csm-executive-meeting' in seed_ids
    assert 'series:leadership-team-meeting' in seed_ids
    assert 'document:patient-portal-closure-report' in seed_ids
    assert 'document:budget-savings-workbook' in seed_ids


def test_default_seed_manifest_has_unique_ids() -> None:
    entity_seed_ids = [entity.seed_id for entity in DEFAULT_SEED_MANIFEST.entities]
    edge_seed_ids = [edge.seed_id for edge in DEFAULT_SEED_MANIFEST.edges]

    assert len(entity_seed_ids) == len(set(entity_seed_ids))
    assert len(edge_seed_ids) == len(set(edge_seed_ids))


def test_project_registry_parent_edges_are_native_graphiti_relations() -> None:
    manifest = seed_manifest_from_project_registry_records(
        PROJECT_REGISTRY_RECORDS_V1,
        source_checked_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
    )

    parent_edges = {edge.seed_id: edge for edge in manifest.edges}

    assert (
        parent_edges['project_registry:1:PROGRAM_HAS_PROJECT:project_registry:2'].edge_type
        == 'PROGRAM_HAS_PROJECT'
    )
    assert (
        parent_edges['project_registry:5:PROGRAM_HAS_PROJECT:project_registry:10'].edge_type
        == 'PROGRAM_HAS_PROJECT'
    )


def test_seed_uuid_is_deterministic_and_group_scoped() -> None:
    assert seed_uuid('michael', 'entity', 'person:hardeep-parwana') == seed_uuid(
        'michael', 'entity', 'person:hardeep-parwana'
    )
    assert seed_uuid('michael', 'entity', 'person:hardeep-parwana') != seed_uuid(
        'other-group', 'entity', 'person:hardeep-parwana'
    )


def test_seed_builders_create_native_graphiti_nodes_and_edges() -> None:
    created_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
    nodes = build_seed_nodes(DEFAULT_SEED_MANIFEST, 'michael', created_at)
    edges = build_seed_edges(DEFAULT_SEED_MANIFEST, 'michael', nodes, created_at)

    defender_rollout = nodes['project_registry:13']
    defender_platform = nodes['platform:defender-mde']
    defender_edges = [
        edge
        for edge in edges
        if edge.source_node_uuid == defender_rollout.uuid
        and edge.target_node_uuid == defender_platform.uuid
    ]

    assert isinstance(defender_rollout, EntityNode)
    assert defender_rollout.labels == ['Project']
    assert defender_rollout.attributes['registry_id'] == '13'
    assert defender_platform.labels == ['Platform']
    assert defender_edges
    assert isinstance(defender_edges[0], EntityEdge)
    assert defender_edges[0].name == 'PROJECT_INVOLVES_PLATFORM'


def test_seed_builders_keep_project_platform_vendor_roles_separate() -> None:
    created_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
    nodes = build_seed_nodes(DEFAULT_SEED_MANIFEST, 'michael', created_at)
    edges = build_seed_edges(DEFAULT_SEED_MANIFEST, 'michael', nodes, created_at)

    zscaler_project = nodes['project_registry:3']
    zscaler_platform = nodes['platform:zscaler']
    zscaler_vendor = nodes['vendor:zscaler']
    crowdstrike_project = nodes['project_registry:18']
    crowdstrike_platform = nodes['platform:crowdstrike']
    crowdstrike_vendor = nodes['vendor:crowdstrike']

    assert zscaler_project.labels == ['Project']
    assert zscaler_platform.labels == ['Platform']
    assert zscaler_vendor.labels == ['Vendor']
    assert zscaler_project.uuid != zscaler_platform.uuid != zscaler_vendor.uuid
    assert zscaler_project.attributes['seed_role'] == 'project'
    assert zscaler_platform.attributes['seed_role'] == 'platform'
    assert zscaler_vendor.attributes['seed_role'] == 'vendor'

    assert crowdstrike_project.labels == ['Project']
    assert crowdstrike_platform.labels == ['Platform']
    assert crowdstrike_vendor.labels == ['Vendor']
    assert crowdstrike_project.attributes['concept_key'] == 'crowdstrike'
    assert crowdstrike_platform.attributes['concept_key'] == 'crowdstrike'
    assert crowdstrike_vendor.attributes['concept_key'] == 'crowdstrike'

    edge_names = {
        (
            edge.source_node_uuid,
            edge.target_node_uuid,
            edge.name,
        )
        for edge in edges
    }
    assert (
        zscaler_project.uuid,
        zscaler_platform.uuid,
        'PROJECT_INVOLVES_PLATFORM',
    ) in edge_names
    assert (
        zscaler_project.uuid,
        zscaler_vendor.uuid,
        'PROJECT_HAS_VENDOR',
    ) in edge_names
    assert (
        crowdstrike_vendor.uuid,
        crowdstrike_platform.uuid,
        'VENDOR_PROVIDES_PLATFORM',
    ) in edge_names


def test_seed_builder_attributes_are_neo4j_property_safe() -> None:
    created_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
    nodes = build_seed_nodes(DEFAULT_SEED_MANIFEST, 'michael', created_at)
    edges = build_seed_edges(DEFAULT_SEED_MANIFEST, 'michael', nodes, created_at)

    for node in nodes.values():
        assert all(_is_neo4j_property_value(value) for value in node.attributes.values())

    for edge in edges:
        assert all(_is_neo4j_property_value(value) for value in edge.attributes.values())


def test_seed_manifest_episode_preserves_seed_provenance() -> None:
    created_at = datetime(2026, 6, 5, tzinfo=timezone.utc)
    nodes = build_seed_nodes(DEFAULT_SEED_MANIFEST, 'michael', created_at)
    edges = build_seed_edges(DEFAULT_SEED_MANIFEST, 'michael', nodes, created_at)
    episode = build_seed_manifest_episode(DEFAULT_SEED_MANIFEST, 'michael', edges, created_at)
    episodic_edges = build_seed_episodic_edges(
        DEFAULT_SEED_MANIFEST, 'michael', episode, nodes, created_at
    )

    assert isinstance(episode, EpisodicNode)
    assert episode.source == EpisodeType.json
    assert episode.episode_metadata == {
        'source_kind': 'seed_manifest',
        'source_system': 'exec_ea',
        'source_id': DEFAULT_SEED_MANIFEST.manifest_id,
        'seed_manifest_version': DEFAULT_SEED_MANIFEST.version,
        'source_updated_at': DEFAULT_SEED_MANIFEST.source_checked_at.isoformat(),
    }
    assert set(episode.entity_edges) == {edge.uuid for edge in edges}
    assert len(episodic_edges) == len(DEFAULT_SEED_MANIFEST.entities)
    assert all(isinstance(edge, EpisodicEdge) for edge in episodic_edges)
