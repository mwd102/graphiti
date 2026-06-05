from pydantic import BaseModel

from graphiti_core.exec_ea import EDGE_TYPE_MAP, EDGE_TYPES, ENTITY_TYPES
from graphiti_core.nodes import EntityNode
from graphiti_core.utils.ontology_utils.entity_types_utils import validate_entity_types

EXPECTED_ENTITY_TYPES = {
    'Person',
    'Organization',
    'Team',
    'WorkingGroup',
    'Program',
    'Project',
    'Platform',
    'VendorProduct',
    'Vendor',
    'Document',
    'EmailThread',
    'MeetingSeries',
    'MeetingOccurrence',
    'Workstream',
    'Topic',
    'Obligation',
    'ApprovalRequest',
    'Decision',
    'ActionItem',
    'Blocker',
    'ProjectStatus',
    'MetricSnapshot',
    'DeliverableStatus',
    'MeetingCarryForward',
    'Risk',
    'Issue',
    'Dependency',
    'Renewal',
    'BudgetItem',
    'ProcurementEvent',
    'Assessment',
}

EXPECTED_EDGE_TYPES = {
    'PERSON_WORKS_FOR_ORG',
    'PERSON_MEMBER_OF_TEAM',
    'PERSON_USES_ALIAS',
    'PERSON_ATTENDED_MEETING',
    'PERSON_ORGANIZED_MEETING',
    'PERSON_SENT_EMAIL',
    'PERSON_RECEIVED_EMAIL',
    'PROGRAM_HAS_PROJECT',
    'PROJECT_HAS_WORKSTREAM',
    'PROJECT_INVOLVES_PLATFORM',
    'VENDOR_PROVIDES_PLATFORM',
    'PROJECT_HAS_VENDOR',
    'PROJECT_HAS_DECISION',
    'PROJECT_HAS_ACTION_ITEM',
    'PROJECT_HAS_RISK',
    'PROJECT_HAS_DEPENDENCY',
    'PROJECT_HAS_RENEWAL',
    'PROJECT_HAS_PROCUREMENT_EVENT',
    'DOCUMENT_ATTACHED_TO_EMAIL',
    'CHUNK_PART_OF_TRANSCRIPT',
    'EMAIL_PART_OF_THREAD',
    'MEETING_SERIES_HAS_OCCURRENCE',
    'OCCURRENCE_HAS_TRANSCRIPT',
    'OCCURRENCE_HAS_CALENDAR_EVENT',
    'PERSON_OWNS_OBLIGATION',
    'OBLIGATION_REQUESTED_BY',
    'APPROVAL_WAITING_ON_PERSON',
    'DECISION_APPLIES_TO_PROJECT',
    'BLOCKER_BLOCKS_PROJECT',
    'METRIC_SNAPSHOT_FOR_PROJECT',
    'DELIVERABLE_STATUS_FOR_PROJECT',
    'MEETING_CARRIED_FORWARD_ITEM',
    'EVIDENCE_SUPPORTS_FACT',
}


def test_exec_ea_entity_types_validate_with_graphiti() -> None:
    assert validate_entity_types(ENTITY_TYPES)


def test_exec_ea_ontology_exports_plan_types() -> None:
    assert set(ENTITY_TYPES) == EXPECTED_ENTITY_TYPES
    assert set(EDGE_TYPES) == EXPECTED_EDGE_TYPES


def test_exec_ea_models_are_pydantic_models() -> None:
    for model in ENTITY_TYPES.values():
        assert issubclass(model, BaseModel)

    for model in EDGE_TYPES.values():
        assert issubclass(model, BaseModel)


def test_exec_ea_entity_fields_avoid_graphiti_node_fields() -> None:
    protected_fields = set(EntityNode.model_fields)

    for entity_type_name, model in ENTITY_TYPES.items():
        collisions = protected_fields.intersection(model.model_fields)
        assert collisions == set(), f'{entity_type_name} collides with {collisions}'


def test_exec_ea_edge_type_map_references_known_types() -> None:
    known_node_types = set(ENTITY_TYPES) | {'Entity'}

    for (source_type, target_type), edge_type_names in EDGE_TYPE_MAP.items():
        assert source_type in known_node_types
        assert target_type in known_node_types

        for edge_type_name in edge_type_names:
            assert edge_type_name in EDGE_TYPES


def test_exec_ea_benchmark_relation_signatures_present() -> None:
    required_signatures = {
        ('Person', 'Obligation'): 'PERSON_OWNS_OBLIGATION',
        ('Obligation', 'Person'): 'OBLIGATION_REQUESTED_BY',
        ('ApprovalRequest', 'Person'): 'APPROVAL_WAITING_ON_PERSON',
        ('Project', 'Platform'): 'PROJECT_INVOLVES_PLATFORM',
        ('Project', 'Vendor'): 'PROJECT_HAS_VENDOR',
        ('Project', 'Decision'): 'PROJECT_HAS_DECISION',
        ('Blocker', 'Project'): 'BLOCKER_BLOCKS_PROJECT',
        ('MeetingSeries', 'MeetingOccurrence'): 'MEETING_SERIES_HAS_OCCURRENCE',
        ('Person', 'MeetingOccurrence'): 'PERSON_ATTENDED_MEETING',
        ('Document', 'MetricSnapshot'): 'EVIDENCE_SUPPORTS_FACT',
        ('MetricSnapshot', 'Project'): 'METRIC_SNAPSHOT_FOR_PROJECT',
        ('DeliverableStatus', 'Project'): 'DELIVERABLE_STATUS_FOR_PROJECT',
    }

    for signature, edge_type_name in required_signatures.items():
        assert edge_type_name in EDGE_TYPE_MAP[signature]
