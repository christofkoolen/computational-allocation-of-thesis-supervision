# Student preference input

The third annual input file is `student_preferences.xlsx`. Upload it alongside
`researchers.xlsx` and `topics.xlsx`.

## Common fields

Every response requires:

| Column | Meaning |
| --- | --- |
| `full_name` | Student name used in allocation outputs |
| `Email` | Unique student identifier |
| `student_number` | Student number retained for auditing |
| `thesis_type` | Individual or dual thesis answer |
| `thesis_allocation_status` | Ranked, self-proposed, or carry-over route |

The `full_name` and `Email` fields are authoritative student identifiers. The
normalized allocation outputs continue to call this field `email`.

## Dual thesis submissions

For a dual thesis, the response also requires:

| Column | Meaning |
| --- | --- |
| `partner_full_name` | Second student's name |
| `partner_email` | Second student's unique email |
| `partner_student_number` | Second student's student number |
| `dual_thesis_confirmation` | Confirmation that both students agreed |

One partner submits the preference row for the pair. The other partner must not
submit a second row. The program rejects any student email that appears in more
than one thesis group.

A pair is one thesis for capacity purposes:

- one place from the allocated offered topic;
- one daily-supervisor slot;
- one promotor slot;
- one shared topic, language, daily supervisor, and promotor.

Both students are still represented in the preference objective. Therefore a
pair assigned its second choice contributes `2 students x rank 2 = 4` points.
The final output contains one row per student with a shared `thesis_group_id`.

## New ranked topic

The ranked branch requires three different exact topic IDs and an ordered
language list for each choice:

| Column | Meaning |
| --- | --- |
| `topic_preference_1` | First-choice topic ID |
| `topic_preference_1_languages` | Ordered language alternatives for choice 1 |
| `topic_preference_2` | Second-choice topic ID |
| `topic_preference_2_languages` | Ordered language alternatives for choice 2 |
| `topic_preference_3` | Third-choice topic ID |
| `topic_preference_3_languages` | Ordered language alternatives for choice 3 |

Enter languages separated by semicolons, for example `Dutch; English`. The
ordering matters. The topic-rank objective is optimized first across all
students. Among allocations with the same optimal topic cost, the optimizer
minimizes language rank.

A topic-language combination is available only when a daily supervisor and a
promotor can both be assigned within their eligibility, language, maximum
capacity, and distinct-role constraints. If the first language is infeasible,
the next listed language is considered. If none is feasible, the optimizer must
use another topic choice or report that a complete allocation is impossible.

## Self-proposed topic

The self-proposed branch requires:

| Column | Meaning |
| --- | --- |
| `self_proposed_thesis_title` | Proposed thesis title |
| `self_proposed_thesis_description` | Substantive text used for matching |
| `self_proposed_thesis_language` | Ordered acceptable language or languages |

The proposed topic is fixed and does not consume capacity from `topics.xlsx`.
Its description is used directly for supervisor matching. It still requires a
feasible daily supervisor and promotor in one of the submitted languages.

## Carry-over topic

The carry-over branch requires:

| Column | Meaning |
| --- | --- |
| `carry_over_thesis_topic` | Existing topic title |
| `carry_over_thesis_description` | Optional additional matching text |
| `carry_over_thesis_language` | Ordered acceptable language or languages |
| `daily_supervisor_email` | Current daily supervisor |
| `thesis_promotor_email` | Current promotor |

The topic is fixed and does not consume capacity from `topics.xlsx`. Valid
current supervisors are retained with priority, subject to current eligibility,
language, maximum capacity, and the distinct-role rule. An unavailable or
ineligible named supervisor is reopened for matching and produces a warning.

### Supervisor email recovery

Carry-over supervisor emails are matched in three steps:

1. normalize capitalization and surrounding spaces;
2. try an exact match against researcher emails;
3. when exact matching fails, accept a fuzzy match only if it is a unique,
   high-confidence one-character insertion, deletion, replacement, or adjacent
   transposition.

A fuzzy match also requires a clear margin over the second-best candidate. If a
match is weak or ambiguous, the run continues and assigns a replacement where
feasible. The administrative result identifies the affected role explicitly as
`MANUAL REVIEW NEEDED - UNKNOWN DAILY SUPERVISOR` or `MANUAL REVIEW NEEDED -
UNKNOWN THESIS PROMOTOR`.

The final assignment output records:

| Column | Purpose |
| --- | --- |
| `submitted_daily_supervisor_email` | Exact submitted daily-supervisor value |
| `resolved_daily_supervisor_email` | Exact or confidently corrected researcher email; blank when unknown |
| `daily_supervisor_email` | Ultimately assigned daily-supervisor email |
| `daily_supervisor_email_resolution` | `exact`, `fuzzy_match`, or `manual_review` |
| `daily_supervisor_email_match_score` | Similarity score used for audit |
| `daily_supervisor_review_status` | Role-specific manual-review label, otherwise blank |
| `daily_supervisor_review_reason` | Submitted value, closest candidates, and assigned replacement |
| `submitted_thesis_promotor_email` | Exact submitted promotor value |
| `resolved_thesis_promotor_email` | Exact or confidently corrected researcher email; blank when unknown |
| `thesis_promotor_email` | Internal resolved request field; blank when unknown |
| `thesis_promotor_email_resolution` | `exact`, `fuzzy_match`, or `manual_review` |
| `thesis_promotor_email_match_score` | Similarity score used for audit |
| `promotor_email` | Ultimately assigned promotor email |
| `thesis_promotor_review_status` | Role-specific manual-review label, otherwise blank |
| `thesis_promotor_review_reason` | Submitted value, closest candidates, and assigned replacement |
| `carry_over_review_status` | Combined review labels when either or both roles need review |
| `carry_over_review_reason` | Combined review details for the thesis group |

After identification, ordinary eligibility rules still apply. A confidently
identified researcher who is ineligible, language-incompatible, or beyond their
maximum capacity is reopened for assignment. If a different researcher is
assigned, the role is marked `MANUAL REVIEW NEEDED - ... REASSIGNED`.

## Optimization order

The allocation workflow uses lexicographic priorities:

1. produce a complete allocation, unless partial results were explicitly
   allowed;
2. retain feasible named carry-over supervisors;
3. minimize student-weighted topic rank cost;
4. minimize student-weighted language rank;
5. maximize assignments to eligible topic submitters;
6. meet researcher minimum workload targets where feasible;
7. maximize semantic fit with mild load balancing and deterministic tie-breaking.

All topic capacities, maximum researcher capacities, language compatibility,
role eligibility, and the distinct-role rule remain hard constraints.
