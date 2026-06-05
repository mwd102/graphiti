"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from graphiti_core.nodes import (
    CommunityNode,
    EntityNode,
    EpisodeType,
    EpisodicNode,
)
from graphiti_core.utils.bulk_utils import add_nodes_and_edges_bulk
from tests.helpers_test import (
    GraphProvider,
    assert_community_node_equals,
    assert_entity_node_equals,
    assert_episodic_node_equals,
    get_node_count,
    group_id,
)

created_at = datetime.now()
deleted_at = created_at + timedelta(days=3)
valid_at = created_at + timedelta(days=1)
invalid_at = created_at + timedelta(days=2)


@pytest.fixture
def sample_entity_node():
    return EntityNode(
        uuid=str(uuid4()),
        name='Test Entity',
        group_id=group_id,
        labels=['Entity', 'Person'],
        created_at=created_at,
        name_embedding=[0.5] * 1024,
        summary='Entity Summary',
        attributes={
            'age': 30,
            'location': 'New York',
        },
    )


@pytest.fixture
def sample_episodic_node():
    return EpisodicNode(
        uuid=str(uuid4()),
        name='Episode 1',
        group_id=group_id,
        created_at=created_at,
        source=EpisodeType.text,
        source_description='Test source',
        content='Some content here',
        valid_at=valid_at,
        entity_edges=[],
    )


@pytest.fixture
def sample_community_node():
    return CommunityNode(
        uuid=str(uuid4()),
        name='Community A',
        group_id=group_id,
        created_at=created_at,
        name_embedding=[0.5] * 1024,
        summary='Community summary',
    )


@pytest.mark.asyncio
async def test_entity_node(sample_entity_node, graph_driver):
    uuid = sample_entity_node.uuid

    # Create node
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0
    await sample_entity_node.save(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 1

    # Get node by uuid
    retrieved = await EntityNode.get_by_uuid(graph_driver, sample_entity_node.uuid)
    await assert_entity_node_equals(graph_driver, retrieved, sample_entity_node)

    # Get node by uuids
    retrieved = await EntityNode.get_by_uuids(graph_driver, [sample_entity_node.uuid])
    await assert_entity_node_equals(graph_driver, retrieved[0], sample_entity_node)

    # Get node by group ids
    retrieved = await EntityNode.get_by_group_ids(
        graph_driver, [group_id], limit=2, with_embeddings=True
    )
    assert len(retrieved) == 1
    await assert_entity_node_equals(graph_driver, retrieved[0], sample_entity_node)

    # Delete node by uuid
    await sample_entity_node.delete(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0

    # Delete node by uuids
    await sample_entity_node.save(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 1
    await sample_entity_node.delete_by_uuids(graph_driver, [uuid])
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0

    # Delete node by group id
    await sample_entity_node.save(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 1
    await sample_entity_node.delete_by_group_id(graph_driver, group_id)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0

    await graph_driver.close()


@pytest.mark.asyncio
async def test_community_node(sample_community_node, graph_driver):
    uuid = sample_community_node.uuid

    # Create node
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0
    await sample_community_node.save(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 1

    # Get node by uuid
    retrieved = await CommunityNode.get_by_uuid(graph_driver, sample_community_node.uuid)
    await assert_community_node_equals(graph_driver, retrieved, sample_community_node)

    # Get node by uuids
    retrieved = await CommunityNode.get_by_uuids(graph_driver, [sample_community_node.uuid])
    await assert_community_node_equals(graph_driver, retrieved[0], sample_community_node)

    # Get node by group ids
    retrieved = await CommunityNode.get_by_group_ids(graph_driver, [group_id], limit=2)
    assert len(retrieved) == 1
    await assert_community_node_equals(graph_driver, retrieved[0], sample_community_node)

    # Delete node by uuid
    await sample_community_node.delete(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0

    # Delete node by uuids
    await sample_community_node.save(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 1
    await sample_community_node.delete_by_uuids(graph_driver, [uuid])
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0

    # Delete node by group id
    await sample_community_node.save(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 1
    await sample_community_node.delete_by_group_id(graph_driver, group_id)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0

    await graph_driver.close()


@pytest.mark.asyncio
async def test_episodic_node(sample_episodic_node, graph_driver):
    uuid = sample_episodic_node.uuid

    # Create node
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0
    await sample_episodic_node.save(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 1

    # Get node by uuid
    retrieved = await EpisodicNode.get_by_uuid(graph_driver, sample_episodic_node.uuid)
    await assert_episodic_node_equals(retrieved, sample_episodic_node)

    # Get node by uuids
    retrieved = await EpisodicNode.get_by_uuids(graph_driver, [sample_episodic_node.uuid])
    await assert_episodic_node_equals(retrieved[0], sample_episodic_node)

    # Get node by group ids
    retrieved = await EpisodicNode.get_by_group_ids(graph_driver, [group_id], limit=2)
    assert len(retrieved) == 1
    await assert_episodic_node_equals(retrieved[0], sample_episodic_node)

    # Delete node by uuid
    await sample_episodic_node.delete(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0

    # Delete node by uuids
    await sample_episodic_node.save(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 1
    await sample_episodic_node.delete_by_uuids(graph_driver, [uuid])
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0

    # Delete node by group id
    await sample_episodic_node.save(graph_driver)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 1
    await sample_episodic_node.delete_by_group_id(graph_driver, group_id)
    node_count = await get_node_count(graph_driver, [uuid])
    assert node_count == 0

    await graph_driver.close()


@pytest.mark.asyncio
async def test_episodic_node_episode_metadata_round_trip(graph_driver):
    if graph_driver.provider != GraphProvider.NEO4J:
        pytest.skip('Episode metadata persistence is wired for Neo4j first')

    episode = EpisodicNode(
        uuid=str(uuid4()),
        name='Episode with metadata',
        group_id=group_id,
        created_at=created_at,
        source=EpisodeType.json,
        source_description='OpenSearch email',
        content='{"subject": "metadata test"}',
        valid_at=valid_at,
        entity_edges=[],
        episode_metadata={
            'source_system': 'opensearch',
            'source_index': 'emails',
            'source_kind': 'email',
            'source_id': 'email-123',
            'ingestion_run_id': 'run-456',
            'project_matches': [{'project_id': 18, 'confidence': 0.91}],
        },
    )

    await episode.save(graph_driver)

    retrieved = await EpisodicNode.get_by_uuid(graph_driver, episode.uuid)
    await assert_episodic_node_equals(retrieved, episode)

    retrieved_by_uuids = await EpisodicNode.get_by_uuids(graph_driver, [episode.uuid])
    await assert_episodic_node_equals(retrieved_by_uuids[0], episode)

    retrieved_by_group = await EpisodicNode.get_by_group_ids(graph_driver, [group_id], limit=1)
    await assert_episodic_node_equals(retrieved_by_group[0], episode)

    await graph_driver.close()


@pytest.mark.asyncio
async def test_episodic_node_episode_metadata_bulk_round_trip(graph_driver, mock_embedder):
    if graph_driver.provider != GraphProvider.NEO4J:
        pytest.skip('Episode metadata persistence is wired for Neo4j first')

    episodes = [
        EpisodicNode(
            uuid=str(uuid4()),
            name='Bulk episode 1',
            group_id=group_id,
            created_at=created_at,
            source=EpisodeType.text,
            source_description='OpenSearch transcript chunk',
            content='Bulk content 1',
            valid_at=valid_at,
            entity_edges=[],
            episode_metadata={
                'source_system': 'opensearch',
                'source_index': 'chunks',
                'source_kind': 'transcript_chunk',
                'source_id': 'chunk-1',
            },
        ),
        EpisodicNode(
            uuid=str(uuid4()),
            name='Bulk episode 2',
            group_id=group_id,
            created_at=created_at,
            source=EpisodeType.text,
            source_description='OpenSearch transcript chunk',
            content='Bulk content 2',
            valid_at=valid_at,
            entity_edges=[],
            episode_metadata={
                'source_system': 'opensearch',
                'source_index': 'chunks',
                'source_kind': 'transcript_chunk',
                'source_id': 'chunk-2',
            },
        ),
    ]

    await add_nodes_and_edges_bulk(
        driver=graph_driver,
        episodic_nodes=episodes,
        episodic_edges=[],
        entity_nodes=[],
        entity_edges=[],
        embedder=mock_embedder,
    )

    retrieved = await EpisodicNode.get_by_uuids(
        graph_driver, [episode.uuid for episode in episodes]
    )
    retrieved_by_uuid = {episode.uuid: episode for episode in retrieved}

    for episode in episodes:
        await assert_episodic_node_equals(retrieved_by_uuid[episode.uuid], episode)

    await graph_driver.close()
