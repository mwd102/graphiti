# CSM Exec Observation Candidate Audit

Date: 2026-06-05

This audit reviews deterministic observation candidates extracted from the live CSM Executive Meeting pilot slice. It is source-selection guidance before a broad Neo4j import, not a final quality score for the graph.

## Source Slice

- Query config: `CSMExecPilotConfig()` defaults.
- Source records: 138 total.
- Record mix: 18 transcripts, 27 calendar events, 93 transcript chunks.
- Candidate observations: 354 total.
- All candidates had a CSM Exec series match and at least one work-context seed match.

## Candidate Mix

| Type | Count | Notes |
| --- | ---: | --- |
| ActionItem | 141 | Highest volume; many are soft "need to" phrases rather than assigned tasks. |
| Obligation | 104 | Useful signal when speaker/owner is present, but "I'll" and "I can" are noisy in casual talk. |
| ProjectStatus | 62 | Useful for meeting catch-up, but generic "status" creates weak candidates. |
| Decision | 24 | Generally valuable, but "we will" can mean forecast/plan rather than decision. |
| Blocker | 21 | Mostly usable, though "risk" needs more context. |
| MeetingCarryForward | 2 | Both observed live examples were false positives from "parking lot" as a physical location. |

## Coverage

- Owned candidates: 126 / 354.
- Owner matches:
  - Michael Dobson: 66
  - Derek Lucas: 30
  - Jamie Ross: 23
  - Ali Deheshi: 5
  - Jennifer Dury: 2
- Source distribution:
  - transcripts: 109
  - calendar_events: 26
  - chunks: 219

## Seed Scope Findings

The top work-context matches were:

| Seed | Name | Count |
| --- | --- | ---: |
| `project_registry:5` | CSM - Cyber Security Modernization | 354 |
| `project_registry:7` | OAG audit | 127 |
| `project_registry:6` | LINUS | 123 |
| `project_registry:24` | Data Governance | 115 |
| `project_registry:13` | Defender rollout | 104 |
| `project_registry:25` | Service Catalogue | 41 |
| `project_registry:18` | CrowdStrike | 37 |
| `project_registry:1` | SASE | 36 |

`project_registry:5` is a program-level CSM umbrella. It should remain useful context, but it should not be emitted as the primary project edge for every observation. For project-scoped question answering, candidate edge creation should prefer specific project/workstream/platform matches and preserve the CSM program as broader context.

The CSM series match was expected for all candidates. A secondary `series:leadership-team-meeting` appeared 12 times and should be treated as a possible cross-series mention, not as a meeting-series scope unless the source record itself belongs to that series.

## Main Quality Issues

1. Soft action cues are too broad.
   - `need to` created 72 ActionItem candidates.
   - `to do` created 59 ActionItem candidates.
   - Many examples are discussion framing or general needs, not assigned tasks.

2. Casual first-person cues are too broad.
   - `I'll` created 56 Obligation candidates.
   - `I can` created 25 Obligation candidates.
   - Several samples are conversational, such as joining another meeting or going on mute.

3. Generic status cues inflate ProjectStatus.
   - `status` created 40 ProjectStatus candidates.
   - Some are agenda/setup lines rather than actual status updates.

4. `parking lot` is not safe as a carry-forward cue.
   - Both MeetingCarryForward candidates were false positives from references to a physical parking lot.

5. Project edges are currently over-attached.
   - Every candidate inherits the CSM program seed.
   - Candidate graph building currently takes the first three project matches, which can promote broad or weak matches into typed edges.

## Recommended Gate Before Full Import

For the next implementation pass:

- Remove `parking lot` from MeetingCarryForward unless it appears with agenda language such as "parking lot item", "parking lot topic", or "put it in the parking lot".
- Split cue strength into high/medium/low and only import low-strength cues when an owner, explicit action verb, or due/next-step marker is present.
- Treat `need to`, `to do`, `I'll`, `I can`, `we will`, and bare `status` as low-strength cues.
- Prefer specific project seeds over program seeds when emitting typed project edges.
- Keep program seeds in observation attributes or context edges, but avoid turning the CSM umbrella into the main project edge for every candidate.
- Add a source-series guard so `MEETING_SERIES_HAS_CARRY_FORWARD` only uses the source slice series unless a cross-series relation is explicit.
- Add a review threshold to the import path: full observation import should require either a bounded config or an explicit `allow_full_import=True` flag until quality gates are in place.

## Import Recommendation

Do not full-import the current 354 candidates yet. The bounded smoke import is useful and idempotent, but the live candidate set needs cue gating and project-edge pruning first. After that change, rerun this audit and compare:

- total candidates;
- low-strength cue count;
- candidate count by type;
- candidates with typed project edges;
- sampled precision for ActionItem, Obligation, ProjectStatus, and MeetingCarryForward.
