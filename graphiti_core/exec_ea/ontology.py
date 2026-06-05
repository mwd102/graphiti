"""
Exec-EA custom ontology for Michael Dobson's Graphiti work memory graph.

These Pydantic models are intended to be passed to Graphiti's `entity_types`,
`edge_types`, and `edge_type_map` arguments during ingestion. They keep the
first-pass ontology focused on durable work context, operational observations,
and source-backed evidence needed by executive assistant queries.
"""

from datetime import datetime

from pydantic import BaseModel, Field


class ExecEAEntity(BaseModel):
    """Base model for shared Exec-EA entity attributes."""

    canonical_label: str | None = Field(
        default=None, description='Stable display label when the extracted phrase is an alias.'
    )
    aliases: list[str] | None = Field(
        default=None, description='Known aliases, abbreviations, email names, or shorthand labels.'
    )
    confidence: float | None = Field(
        default=None, description='Confidence that this entity type and attributes are correct.'
    )


class Person(ExecEAEntity):
    """A human actor with evidence across email, transcript, calendar, or registry sources."""

    display_name: str | None = Field(default=None, description='Preferred human-readable name.')
    canonical_email: str | None = Field(
        default=None, description='Primary email address when it is known.'
    )
    organization_hint: str | None = Field(
        default=None, description='Best available organization, inferred from source evidence.'
    )
    role_title: str | None = Field(default=None, description='Role or title seen in the corpus.')


class Organization(ExecEAEntity):
    """A company, health authority, ministry, vendor body, or partner organization."""

    domain: str | None = Field(default=None, description='Primary email or web domain.')
    organization_kind: str | None = Field(
        default=None,
        description='Org classification such as vendor, partner, ministry, or health authority.',
    )


class Team(ExecEAEntity):
    """An internal team, distribution list, or operating group with members or ownership."""

    organization_hint: str | None = Field(default=None, description='Parent organization if known.')
    mailbox_or_list: str | None = Field(
        default=None, description='Team mailbox or distribution list.'
    )


class WorkingGroup(ExecEAEntity):
    """A durable working group or governance forum with recurring participants or mandate."""

    mandate: str | None = Field(default=None, description='Short purpose or governance mandate.')
    cadence: str | None = Field(default=None, description='Observed meeting cadence when known.')


class Program(ExecEAEntity):
    """A durable portfolio or operating program that can contain projects or workstreams."""

    registry_id: str | None = Field(default=None, description='Project registry identifier.')
    program_status: str | None = Field(default=None, description='Current known lifecycle state.')


class Project(ExecEAEntity):
    """A scoped body of work with timeline, deliverables, stakeholders, or decisions."""

    registry_id: str | None = Field(default=None, description='Project registry identifier.')
    project_status: str | None = Field(default=None, description='Latest known state or health.')
    priority: str | None = Field(default=None, description='Relative importance or priority label.')
    target_date: datetime | None = Field(
        default=None, description='Known target date or milestone.'
    )


class Platform(ExecEAEntity):
    """A technical platform, service, or product used by projects or programs."""

    product_family: str | None = Field(
        default=None, description='Product family or platform family.'
    )
    vendor_hint: str | None = Field(default=None, description='Vendor or supplier when known.')


class VendorProduct(ExecEAEntity):
    """A vendor-supplied product that should not be collapsed into the vendor or project."""

    vendor_hint: str | None = Field(default=None, description='Supplier or vendor name.')
    product_category: str | None = Field(default=None, description='Functional product category.')


class Vendor(Organization):
    """A supplier, advisor, partner, or commercial vendor in the work corpus."""

    contract_hint: str | None = Field(
        default=None, description='Known contract or engagement context.'
    )


class Document(ExecEAEntity):
    """An attachment, workbook, report, transcript artifact, or other source-backed document."""

    document_kind: str | None = Field(
        default=None, description='Attachment, report, workbook, deck, or note.'
    )
    attachment_id: str | None = Field(
        default=None, description='Durable attachment identifier if present.'
    )
    blob_sha256: str | None = Field(default=None, description='Content hash when available.')
    source_url: str | None = Field(
        default=None, description='Stable source pointer or URL when available.'
    )
    version_label: str | None = Field(
        default=None, description='Version, revision, or as-of label.'
    )


class EmailThread(ExecEAEntity):
    """A conversation thread keyed by email conversation or thread identifiers."""

    conversation_id: str | None = Field(default=None, description='Email conversation identifier.')
    thread_id: str | None = Field(
        default=None, description='Thread identifier from the source system.'
    )
    latest_message_at: datetime | None = Field(
        default=None, description='Latest observed message time.'
    )


class MeetingSeries(ExecEAEntity):
    """A durable recurring cadence such as an executive meeting, sync, or one-on-one."""

    series_key: str | None = Field(default=None, description='Curated or normalized series key.')
    cadence: str | None = Field(default=None, description='Observed recurrence pattern.')
    owner_hint: str | None = Field(default=None, description='Organizer or owner when known.')


class MeetingOccurrence(ExecEAEntity):
    """A single meeting instance backed by a transcript, calendar event, or both."""

    transcript_id: str | None = Field(default=None, description='Transcript identifier if present.')
    calendar_event_id: str | None = Field(
        default=None, description='Calendar event identifier if present.'
    )
    occurrence_start: datetime | None = Field(
        default=None, description='Start time for this occurrence.'
    )
    occurrence_end: datetime | None = Field(
        default=None, description='End time for this occurrence.'
    )


class Workstream(ExecEAEntity):
    """A sub-area of work within a project or program that can carry blockers or actions."""

    workstream_status: str | None = Field(default=None, description='Latest known state or health.')
    owner_hint: str | None = Field(default=None, description='Named owner or accountable group.')


class Topic(ExecEAEntity):
    """A durable topic or classification promoted beyond a transient transcript tag."""

    taxonomy: str | None = Field(default=None, description='Controlled vocabulary or topic family.')


class Obligation(ExecEAEntity):
    """A commitment owed by a person, including commitments by Michael or owed to Michael."""

    obligation_text: str | None = Field(
        default=None, description='Concise action or commitment text.'
    )
    obligation_status: str | None = Field(
        default=None, description='Open, done, waiting, cancelled, or unclear.'
    )
    due_at: datetime | None = Field(
        default=None, description='Firm due date when explicitly supported.'
    )
    due_date_confidence: str | None = Field(
        default=None, description='Firm, inferred, hedged, or unknown.'
    )


class ApprovalRequest(ExecEAEntity):
    """A decision, approval, or sign-off request waiting on a named person or role."""

    request_text: str | None = Field(default=None, description='What needs approval or sign-off.')
    approval_status: str | None = Field(
        default=None, description='Waiting, approved, declined, or unclear.'
    )
    requested_at: datetime | None = Field(default=None, description='When the request was made.')
    due_at: datetime | None = Field(
        default=None, description='Requested or required approval date.'
    )


class Decision(ExecEAEntity):
    """A source-backed decision, direction, or agreed outcome with timing and scope."""

    decision_text: str | None = Field(default=None, description='Concise decision statement.')
    decided_at: datetime | None = Field(default=None, description='When the decision was made.')
    decision_status: str | None = Field(
        default=None, description='Final, tentative, reversed, or unclear.'
    )


class ActionItem(ExecEAEntity):
    """A concrete action item extracted from a meeting, email, or document."""

    action_text: str | None = Field(default=None, description='Concise action item text.')
    action_status: str | None = Field(
        default=None, description='Open, done, waiting, cancelled, or unclear.'
    )
    due_at: datetime | None = Field(
        default=None, description='Due date when supported by evidence.'
    )


class Blocker(ExecEAEntity):
    """A blocker, waiting state, or impediment affecting a project or deliverable."""

    blocker_text: str | None = Field(
        default=None, description='What is blocked or preventing progress.'
    )
    blocker_status: str | None = Field(
        default=None, description='Open, resolved, accepted, or unclear.'
    )
    blocker_owner_hint: str | None = Field(
        default=None, description='Person, group, or vendor associated with the blocker.'
    )


class ProjectStatus(ExecEAEntity):
    """A dated status observation for a project, program, platform rollout, or workstream."""

    status_text: str | None = Field(default=None, description='Concise status summary.')
    status_label: str | None = Field(
        default=None, description='Green, amber, red, on track, delayed, or similar.'
    )
    observed_at: datetime | None = Field(
        default=None, description='As-of time for the status observation.'
    )


class MetricSnapshot(ExecEAEntity):
    """A source-backed metric value with an as-of date, unit, and project or platform scope."""

    metric_label: str | None = Field(default=None, description='Metric name or table label.')
    metric_value: str | None = Field(
        default=None, description='Observed value as written in the source.'
    )
    metric_unit: str | None = Field(
        default=None, description='Unit, currency, count, percent, or denominator.'
    )
    observed_at: datetime | None = Field(default=None, description='As-of date for the value.')


class DeliverableStatus(ExecEAEntity):
    """A dated status observation for a report, closure package, workbook, or deliverable."""

    deliverable_text: str | None = Field(
        default=None, description='Deliverable or package being tracked.'
    )
    deliverable_status: str | None = Field(
        default=None, description='Draft, submitted, approved, late, or unclear.'
    )
    due_at: datetime | None = Field(
        default=None, description='Relevant due date or comment deadline.'
    )
    observed_at: datetime | None = Field(default=None, description='As-of date for this status.')


class MeetingCarryForward(ExecEAEntity):
    """An unresolved item that carries from one meeting occurrence to a later occurrence."""

    item_text: str | None = Field(
        default=None, description='Unresolved item being carried forward.'
    )
    carried_from: datetime | None = Field(
        default=None, description='Occurrence date it carried from.'
    )
    carried_to: datetime | None = Field(
        default=None, description='Occurrence date it carried into.'
    )
    carry_status: str | None = Field(
        default=None, description='Open, resolved, repeated, or unclear.'
    )


class Risk(ExecEAEntity):
    """A project or operational risk that may require mitigation or executive attention."""

    risk_text: str | None = Field(default=None, description='Risk statement.')
    severity: str | None = Field(default=None, description='Severity or impact label.')
    likelihood: str | None = Field(default=None, description='Likelihood label when present.')


class Issue(ExecEAEntity):
    """A concrete issue or problem distinct from a future risk or external blocker."""

    issue_text: str | None = Field(default=None, description='Issue statement.')
    issue_status: str | None = Field(
        default=None, description='Open, resolved, monitoring, or unclear.'
    )
    severity: str | None = Field(default=None, description='Severity or impact label.')


class Dependency(ExecEAEntity):
    """A dependency between work items, teams, vendors, approvals, or deliverables."""

    dependency_text: str | None = Field(default=None, description='Dependency statement.')
    dependency_status: str | None = Field(
        default=None, description='Open, met, at risk, or unclear.'
    )
    due_at: datetime | None = Field(default=None, description='Date the dependency is needed.')


class Renewal(ExecEAEntity):
    """A contract, license, platform, or service renewal that may require action or approval."""

    renewal_text: str | None = Field(default=None, description='Renewal being tracked.')
    renewal_status: str | None = Field(
        default=None, description='Upcoming, in progress, approved, expired, or unclear.'
    )
    renewal_date: datetime | None = Field(default=None, description='Renewal or expiry date.')


class BudgetItem(ExecEAEntity):
    """A budget, savings, cost, or financial planning item from a source document or discussion."""

    budget_label: str | None = Field(
        default=None, description='Budget line, savings item, or financial category.'
    )
    amount: str | None = Field(
        default=None, description='Amount as written, including currency if present.'
    )
    fiscal_period: str | None = Field(
        default=None, description='Fiscal year, quarter, month, or planning period.'
    )


class ProcurementEvent(ExecEAEntity):
    """A procurement, purchase order, contract, or sourcing event tied to a project or vendor."""

    event_text: str | None = Field(default=None, description='Procurement event summary.')
    procurement_status: str | None = Field(
        default=None, description='Requested, pending, approved, issued, or unclear.'
    )
    event_at: datetime | None = Field(default=None, description='Event date when known.')


class Assessment(ExecEAEntity):
    """A source-backed assessment, audit, review, or findings package."""

    assessment_kind: str | None = Field(
        default=None, description='Audit, security assessment, review, or findings package.'
    )
    assessment_status: str | None = Field(
        default=None, description='Draft, active, complete, accepted, or unclear.'
    )
    observed_at: datetime | None = Field(default=None, description='As-of date for the assessment.')


class ExecEAEdge(BaseModel):
    """Base model for shared Exec-EA edge attributes."""

    confidence: float | None = Field(
        default=None, description='Confidence that this relation is correct.'
    )
    evidence_text: str | None = Field(
        default=None, description='Short supporting phrase from the source.'
    )
    observed_at: datetime | None = Field(
        default=None, description='When the relation was observed.'
    )


class PersonWorksForOrg(ExecEAEdge):
    """A person works for, represents, or is affiliated with an organization."""

    role_title: str | None = Field(
        default=None, description='Role or title within the organization.'
    )


class PersonMemberOfTeam(ExecEAEdge):
    """A person is a member, owner, sponsor, or participant in a team or working group."""

    role: str | None = Field(
        default=None, description='Member, owner, sponsor, chair, or participant.'
    )


class PersonUsesAlias(ExecEAEdge):
    """A person is known by an email address, display name, initials, or shorthand alias."""

    alias_kind: str | None = Field(
        default=None, description='Email, display name, initials, or shorthand.'
    )


class PersonAttendedMeeting(ExecEAEdge):
    """A person attended, spoke in, or was listed as present at a meeting occurrence."""

    attendance_status: str | None = Field(
        default=None, description='Present, optional, invited, absent, or unclear.'
    )


class PersonOrganizedMeeting(ExecEAEdge):
    """A person organized, chaired, hosted, or owned a meeting occurrence."""

    organizer_role: str | None = Field(
        default=None, description='Organizer, chair, host, owner, or delegate.'
    )


class PersonSentEmail(ExecEAEdge):
    """A person sent or authored a message in an email thread."""

    message_at: datetime | None = Field(default=None, description='Message timestamp when known.')


class PersonReceivedEmail(ExecEAEdge):
    """A person received, was copied on, or was expected to respond in an email thread."""

    recipient_role: str | None = Field(
        default=None, description='To, cc, bcc, for-info, or inferred recipient role.'
    )


class ProgramHasProject(ExecEAEdge):
    """A program contains, sponsors, or governs a project."""

    membership_status: str | None = Field(
        default=None, description='Active, proposed, archived, or unclear.'
    )


class ProjectHasWorkstream(ExecEAEdge):
    """A project contains a workstream, swimlane, or delivery area."""

    workstream_role: str | None = Field(
        default=None, description='Delivery, governance, technical, reporting, or other role.'
    )


class ProjectInvolvesPlatform(ExecEAEdge):
    """A project involves, deploys, replaces, integrates, or governs a platform."""

    involvement: str | None = Field(
        default=None, description='Deploys, migrates from, migrates to, evaluates, or governs.'
    )


class VendorProvidesPlatform(ExecEAEdge):
    """A vendor provides, supports, sells, or advises on a platform or vendor product."""

    provider_role: str | None = Field(
        default=None, description='Vendor, reseller, implementer, advisor, or support partner.'
    )


class ProjectHasVendor(ExecEAEdge):
    """A project engages, depends on, evaluates, or works with a vendor."""

    vendor_role: str | None = Field(
        default=None, description='Supplier, partner, advisor, assessor, or implementer.'
    )


class ProjectHasDecision(ExecEAEdge):
    """A project has a source-backed decision, direction, or agreed outcome."""

    decision_scope: str | None = Field(
        default=None, description='Scope of the decision within the project.'
    )


class ProjectHasActionItem(ExecEAEdge):
    """A project has a concrete action item or follow-up."""

    action_status: str | None = Field(
        default=None, description='Open, done, waiting, cancelled, or unclear.'
    )


class ProjectHasRisk(ExecEAEdge):
    """A project has an identified risk or exposure."""

    risk_status: str | None = Field(
        default=None, description='Open, mitigated, accepted, or unclear.'
    )


class ProjectHasDependency(ExecEAEdge):
    """A project has a dependency on another team, vendor, approval, deliverable, or work item."""

    dependency_role: str | None = Field(
        default=None, description='Required by, blocked by, waiting for, or informs.'
    )


class ProjectHasRenewal(ExecEAEdge):
    """A project or platform context includes a contract, license, or service renewal."""

    renewal_status: str | None = Field(
        default=None, description='Upcoming, in progress, approved, expired, or unclear.'
    )


class ProjectHasProcurementEvent(ExecEAEdge):
    """A project includes a purchase order, sourcing, contract, or procurement event."""

    procurement_status: str | None = Field(
        default=None, description='Requested, pending, approved, issued, or unclear.'
    )


class DocumentAttachedToEmail(ExecEAEdge):
    """A document was attached to, forwarded in, or referenced by an email thread."""

    attachment_role: str | None = Field(
        default=None,
        description='Attachment, linked file, forwarded report, or referenced artifact.',
    )


class ChunkPartOfTranscript(ExecEAEdge):
    """A transcript chunk or document segment is part of a larger transcript document."""

    sequence_index: int | None = Field(default=None, description='Chunk order when known.')


class EmailPartOfThread(ExecEAEdge):
    """An email message or document artifact belongs to an email thread."""

    sequence_index: int | None = Field(default=None, description='Message order when known.')


class MeetingSeriesHasOccurrence(ExecEAEdge):
    """A meeting series has a specific calendar or transcript-backed occurrence."""

    occurrence_status: str | None = Field(
        default=None, description='Scheduled, completed, cancelled, or unclear.'
    )


class OccurrenceHasTranscript(ExecEAEdge):
    """A meeting occurrence is backed by a transcript document or transcript source artifact."""

    transcript_status: str | None = Field(
        default=None, description='Available, partial, missing, or unclear.'
    )


class OccurrenceHasCalendarEvent(ExecEAEdge):
    """A meeting occurrence is backed by a calendar event artifact."""

    calendar_status: str | None = Field(
        default=None, description='Scheduled, cancelled, moved, or unclear.'
    )


class PersonOwnsObligation(ExecEAEdge):
    """A person owns, committed to, or is responsible for an obligation."""

    owner_role: str | None = Field(
        default=None, description='Owner, accountable, contributor, or delegate.'
    )


class ObligationRequestedBy(ExecEAEdge):
    """An obligation was requested by, assigned by, or is owed to a person."""

    request_role: str | None = Field(
        default=None, description='Requester, assigner, owed-to person, or sponsor.'
    )


class ApprovalWaitingOnPerson(ExecEAEdge):
    """An approval or sign-off request is waiting on a person."""

    waiting_status: str | None = Field(
        default=None, description='Waiting, escalated, completed, or unclear.'
    )


class DecisionAppliesToProject(ExecEAEdge):
    """A decision applies to, constrains, or changes a project."""

    impact: str | None = Field(default=None, description='Scope or impact of the decision.')


class BlockerBlocksProject(ExecEAEdge):
    """A blocker is blocking, delaying, or putting a project at risk."""

    blocked_status: str | None = Field(
        default=None, description='Blocking, delaying, resolved, accepted, or unclear.'
    )


class MetricSnapshotForProject(ExecEAEdge):
    """A metric snapshot is scoped to a project, platform rollout, or workstream."""

    metric_scope: str | None = Field(
        default=None, description='Rollout, finance, staffing, schedule, or operational scope.'
    )


class DeliverableStatusForProject(ExecEAEdge):
    """A deliverable status is scoped to a project, program, or workstream."""

    deliverable_scope: str | None = Field(
        default=None, description='Report, closure package, workbook, deck, or approval package.'
    )


class MeetingCarriedForwardItem(ExecEAEdge):
    """A meeting occurrence carried an unresolved item or action into another occurrence."""

    carry_reason: str | None = Field(
        default=None, description='Why the item carried forward if known.'
    )


class EvidenceSupportsFact(ExecEAEdge):
    """A domain artifact explicitly supports a modeled fact, assessment, metric, or status."""

    support_kind: str | None = Field(
        default=None,
        description='Quote, table, attachment, transcript, calendar, or assessment support.',
    )


ENTITY_TYPES: dict[str, type[BaseModel]] = {
    'Person': Person,
    'Organization': Organization,
    'Team': Team,
    'WorkingGroup': WorkingGroup,
    'Program': Program,
    'Project': Project,
    'Platform': Platform,
    'VendorProduct': VendorProduct,
    'Vendor': Vendor,
    'Document': Document,
    'EmailThread': EmailThread,
    'MeetingSeries': MeetingSeries,
    'MeetingOccurrence': MeetingOccurrence,
    'Workstream': Workstream,
    'Topic': Topic,
    'Obligation': Obligation,
    'ApprovalRequest': ApprovalRequest,
    'Decision': Decision,
    'ActionItem': ActionItem,
    'Blocker': Blocker,
    'ProjectStatus': ProjectStatus,
    'MetricSnapshot': MetricSnapshot,
    'DeliverableStatus': DeliverableStatus,
    'MeetingCarryForward': MeetingCarryForward,
    'Risk': Risk,
    'Issue': Issue,
    'Dependency': Dependency,
    'Renewal': Renewal,
    'BudgetItem': BudgetItem,
    'ProcurementEvent': ProcurementEvent,
    'Assessment': Assessment,
}


EDGE_TYPES: dict[str, type[BaseModel]] = {
    'PERSON_WORKS_FOR_ORG': PersonWorksForOrg,
    'PERSON_MEMBER_OF_TEAM': PersonMemberOfTeam,
    'PERSON_USES_ALIAS': PersonUsesAlias,
    'PERSON_ATTENDED_MEETING': PersonAttendedMeeting,
    'PERSON_ORGANIZED_MEETING': PersonOrganizedMeeting,
    'PERSON_SENT_EMAIL': PersonSentEmail,
    'PERSON_RECEIVED_EMAIL': PersonReceivedEmail,
    'PROGRAM_HAS_PROJECT': ProgramHasProject,
    'PROJECT_HAS_WORKSTREAM': ProjectHasWorkstream,
    'PROJECT_INVOLVES_PLATFORM': ProjectInvolvesPlatform,
    'VENDOR_PROVIDES_PLATFORM': VendorProvidesPlatform,
    'PROJECT_HAS_VENDOR': ProjectHasVendor,
    'PROJECT_HAS_DECISION': ProjectHasDecision,
    'PROJECT_HAS_ACTION_ITEM': ProjectHasActionItem,
    'PROJECT_HAS_RISK': ProjectHasRisk,
    'PROJECT_HAS_DEPENDENCY': ProjectHasDependency,
    'PROJECT_HAS_RENEWAL': ProjectHasRenewal,
    'PROJECT_HAS_PROCUREMENT_EVENT': ProjectHasProcurementEvent,
    'DOCUMENT_ATTACHED_TO_EMAIL': DocumentAttachedToEmail,
    'CHUNK_PART_OF_TRANSCRIPT': ChunkPartOfTranscript,
    'EMAIL_PART_OF_THREAD': EmailPartOfThread,
    'MEETING_SERIES_HAS_OCCURRENCE': MeetingSeriesHasOccurrence,
    'OCCURRENCE_HAS_TRANSCRIPT': OccurrenceHasTranscript,
    'OCCURRENCE_HAS_CALENDAR_EVENT': OccurrenceHasCalendarEvent,
    'PERSON_OWNS_OBLIGATION': PersonOwnsObligation,
    'OBLIGATION_REQUESTED_BY': ObligationRequestedBy,
    'APPROVAL_WAITING_ON_PERSON': ApprovalWaitingOnPerson,
    'DECISION_APPLIES_TO_PROJECT': DecisionAppliesToProject,
    'BLOCKER_BLOCKS_PROJECT': BlockerBlocksProject,
    'METRIC_SNAPSHOT_FOR_PROJECT': MetricSnapshotForProject,
    'DELIVERABLE_STATUS_FOR_PROJECT': DeliverableStatusForProject,
    'MEETING_CARRIED_FORWARD_ITEM': MeetingCarriedForwardItem,
    'EVIDENCE_SUPPORTS_FACT': EvidenceSupportsFact,
}


EDGE_TYPE_MAP: dict[tuple[str, str], list[str]] = {
    ('Person', 'Organization'): ['PERSON_WORKS_FOR_ORG'],
    ('Person', 'Vendor'): ['PERSON_WORKS_FOR_ORG'],
    ('Person', 'Team'): ['PERSON_MEMBER_OF_TEAM'],
    ('Person', 'WorkingGroup'): ['PERSON_MEMBER_OF_TEAM'],
    ('Person', 'Person'): ['PERSON_USES_ALIAS'],
    ('Person', 'MeetingOccurrence'): ['PERSON_ATTENDED_MEETING', 'PERSON_ORGANIZED_MEETING'],
    ('Person', 'EmailThread'): ['PERSON_SENT_EMAIL', 'PERSON_RECEIVED_EMAIL'],
    ('Program', 'Project'): ['PROGRAM_HAS_PROJECT'],
    ('Program', 'Workstream'): ['PROJECT_HAS_WORKSTREAM'],
    ('Project', 'Workstream'): ['PROJECT_HAS_WORKSTREAM'],
    ('Project', 'Platform'): ['PROJECT_INVOLVES_PLATFORM'],
    ('Project', 'VendorProduct'): ['PROJECT_INVOLVES_PLATFORM'],
    ('Vendor', 'Platform'): ['VENDOR_PROVIDES_PLATFORM'],
    ('Vendor', 'VendorProduct'): ['VENDOR_PROVIDES_PLATFORM'],
    ('Organization', 'Platform'): ['VENDOR_PROVIDES_PLATFORM'],
    ('Project', 'Vendor'): ['PROJECT_HAS_VENDOR'],
    ('Project', 'Organization'): ['PROJECT_HAS_VENDOR'],
    ('Project', 'Decision'): ['PROJECT_HAS_DECISION'],
    ('Project', 'ActionItem'): ['PROJECT_HAS_ACTION_ITEM'],
    ('Project', 'Risk'): ['PROJECT_HAS_RISK'],
    ('Project', 'Dependency'): ['PROJECT_HAS_DEPENDENCY'],
    ('Project', 'Renewal'): ['PROJECT_HAS_RENEWAL'],
    ('Project', 'ProcurementEvent'): ['PROJECT_HAS_PROCUREMENT_EVENT'],
    ('Document', 'EmailThread'): ['DOCUMENT_ATTACHED_TO_EMAIL'],
    ('Document', 'Document'): ['CHUNK_PART_OF_TRANSCRIPT', 'EMAIL_PART_OF_THREAD'],
    ('EmailThread', 'Document'): ['EMAIL_PART_OF_THREAD'],
    ('MeetingSeries', 'MeetingOccurrence'): ['MEETING_SERIES_HAS_OCCURRENCE'],
    ('MeetingOccurrence', 'Document'): [
        'OCCURRENCE_HAS_TRANSCRIPT',
        'OCCURRENCE_HAS_CALENDAR_EVENT',
    ],
    ('Person', 'Obligation'): ['PERSON_OWNS_OBLIGATION'],
    ('Obligation', 'Person'): ['OBLIGATION_REQUESTED_BY'],
    ('ApprovalRequest', 'Person'): ['APPROVAL_WAITING_ON_PERSON'],
    ('Decision', 'Project'): ['DECISION_APPLIES_TO_PROJECT'],
    ('Blocker', 'Project'): ['BLOCKER_BLOCKS_PROJECT'],
    ('MetricSnapshot', 'Project'): ['METRIC_SNAPSHOT_FOR_PROJECT'],
    ('MetricSnapshot', 'Platform'): ['METRIC_SNAPSHOT_FOR_PROJECT'],
    ('DeliverableStatus', 'Project'): ['DELIVERABLE_STATUS_FOR_PROJECT'],
    ('DeliverableStatus', 'Document'): ['DELIVERABLE_STATUS_FOR_PROJECT'],
    ('MeetingOccurrence', 'MeetingCarryForward'): ['MEETING_CARRIED_FORWARD_ITEM'],
    ('MeetingCarryForward', 'ActionItem'): ['MEETING_CARRIED_FORWARD_ITEM'],
    ('Document', 'Decision'): ['EVIDENCE_SUPPORTS_FACT'],
    ('Document', 'ProjectStatus'): ['EVIDENCE_SUPPORTS_FACT'],
    ('Document', 'MetricSnapshot'): ['EVIDENCE_SUPPORTS_FACT'],
    ('Document', 'DeliverableStatus'): ['EVIDENCE_SUPPORTS_FACT'],
    ('Document', 'Assessment'): ['EVIDENCE_SUPPORTS_FACT'],
    ('Assessment', 'Risk'): ['EVIDENCE_SUPPORTS_FACT'],
    ('Assessment', 'Issue'): ['EVIDENCE_SUPPORTS_FACT'],
}
