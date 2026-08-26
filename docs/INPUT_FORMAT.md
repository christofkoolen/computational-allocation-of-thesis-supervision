# Input format

The CLI accepts `.xlsx`, `.csv`, and `.tsv` input files. Column matching is
case-insensitive, and selected legacy aliases are accepted. Canonical column
names are recommended because they make the data contract explicit.

## Researchers

One row represents one researcher.

| Column | Required | Meaning |
| --- | --- | --- |
| `full_name` | Yes | Display name |
| `email` | Yes | Unique researcher identifier |
| `appointment_type` | No | Informational role or appointment label |
| `appointment_percentage` | No | Informational appointment percentage |
| `comment` | No | Informational free-text comment |
| `timestamp` | No | Informational source or update timestamp |
| `supervision_languages` | No | Comma or semicolon separated languages in which this researcher can supervise; blank means no language restriction |
| `profile_url` | No | Web profile used by the enrichment stage |
| `publications_url` | No | Explicit publications page; derived from supported KU Leuven staff URLs when blank |
| `profile_description` | No | Existing profile text; retained unless `--refresh` is used |
| `publication_list` | No | Existing publication text; retained unless `--refresh` is used |
| `daily_supervisor_minimum_theses` | Yes for matching | Workload target for the daily-supervisor role |
| `daily_supervisor_maximum_theses` | Yes for matching | Hard capacity; zero makes the person ineligible for this role |
| `promotor_minimum_theses` | Yes for matching | Workload target for the promotor role |
| `promotor_maximum_theses` | Yes for matching | Hard capacity; zero makes the person ineligible for this role |

The `appointment_type`, `appointment_percentage`, `comment`, and `timestamp`
values are descriptive only and are not used by the allocation logic. In
particular, the program does not infer role eligibility from labels such as PhD
researcher, postdoc, or professor. A person is eligible as a daily supervisor
when `daily_supervisor_maximum_theses > 0`, and eligible as a promotor when
`promotor_maximum_theses > 0`. Both maximums may be positive when someone can
perform both roles; a maximum of `0` makes that person ineligible for that role.
The corresponding minimum columns are workload targets, not eligibility switches.

The aliases `languages`, `allowed_languages`, and `supervision_language` are
accepted for `supervision_languages`.

Each minimum and maximum must be a non-negative whole number, and a minimum
cannot exceed its corresponding maximum.

## Topics

One row represents one offered thesis topic. Topics do not contain a supervision
language field because language eligibility belongs to researchers.

| Column | Required | Meaning |
| --- | --- | --- |
| `topic_id` | Yes | Stable unique ID used by students when submitting preferences |
| `topic_title` | Yes | Unique official topic title |
| `topic_description` | No | Text included in semantic matching and copied into `assigned_topic_description` when allocated |
| `submitter_email` | No | Researcher who proposed the topic; receives absolute supervision priority when eligible and within maximum capacity |
| `capacity` | No | Number of students who may receive the topic; defaults to 1 when the column is omitted |

Topic IDs `9998` and `9999` are reserved and must not appear in the topics file.
`9998` means previous-year carry-over and `9999` means a student's own topic.
Topic IDs are never generated from titles.

The aliases `proposed_thesis_topic`, `subject_field`, and
`researcher_email` remain supported for the descriptive topic fields.

## Student preferences

One row represents one student's submission. For the normal current-year topic
allocation, students provide three ranked topic IDs. Topic titles are not
accepted as identifiers and no fuzzy or approximate title matching is performed.

| Column | Required | Meaning |
| --- | --- | --- |
| `full_name` | Yes | Student display name |
| `email` | Yes | Unique student identifier |
| `preference_1` | Yes | First-choice topic ID; `9998` in any preference field turns the whole row into previous-year carry-over |
| `preference_1_languages` | No | Acceptable supervision languages for this choice; the first listed language becomes the selected language when this occurrence is assigned |
| `preference_2` | Yes normally; may be blank for a carry-over row | Second-choice topic ID; `9998` here also means carry-over |
| `preference_2_languages` | No | Acceptable supervision languages for this choice; the first listed language becomes the selected language when this occurrence is assigned |
| `preference_3` | Yes normally; may be blank for a carry-over row | Third-choice topic ID; `9998` here also means carry-over |
| `preference_3_languages` | No | Acceptable supervision languages for this choice; the first listed language becomes the selected language when this occurrence is assigned |
| `own_topic_description` | Conditional | Short description required when a non-carry-over row contains topic ID `9999` |

### Previous-year carry-over: topic ID `9998`

A continuing student who wants to retain the previous thesis allocation may put
`9998` in **any** of the three preference fields. For example:

```text
preference_1 = current-topic-A
preference_2 = 9998
preference_3 = current-topic-B
```

This is treated as carry-over, not as “current-topic-A first, carry-over second.”
`9998` is an instruction rather than a ranked fallback. Once it appears anywhere
on the row, all three ranked topic choices are ignored for current-year topic
allocation and the student is handled through the carry-over workflow. The
original submitted preference values remain present in the output for auditing.

If a form requires every preference field to contain a value, this is also valid:

```text
preference_1 = 9998
preference_2 = 9998
preference_3 = 9998
```

It represents one carry-over student. Repeating `9998` does not create multiple
requests or any preference cost.

If the previous `final_assignments` file is available, provide it to Complete
allocation, normally as `previous_final_assignments.xlsx`.

When a matching previous row exists, the student is matched by normalized email.
That previous row supplies the carried topic, topic description, assigned
language, daily supervisor, and promotor. The current `topics.xlsx` is not used
to resolve that student's carried topic, even if the old topic ID happens to be
reused in the current academic year.

If no previous final-assignment file is supplied, the run still completes. The
`9998` student remains in `topic_assignments.xlsx` and `final_assignments.xlsx`
with unresolved human-readable assignment fields marked:

```text
CARRY-OVER STUDENT - MANUAL REVIEW NEEDED
```

`assigned_topic_id` remains `9998`, researcher email fields remain blank, and
automatic daily-supervisor/promotor matching is skipped for that row. The source
fields identify the case as `carry_over_manual_review` / `manual_review`, and
`run_report.json` reports the number of affected students in
`manual_review_students`.

If a previous final-assignment file is supplied but does not contain a matching
student email for a `9998` row, the run stops with a validation error because the
provided continuity file is inconsistent for that student.

A repeat student who wants a new topic must submit three ordinary topic IDs with
no `9998` in any preference field. Their presence in
`previous_final_assignments` does not trigger carry-over by itself.

If a row contains both `9998` and `9999`, `9998` takes precedence and the row is
handled as carry-over. `own_topic_description` is therefore not required for
that annual run.

See `docs/CARRY_OVER.md` for the complete carry-over policy.

### Normal ranked preferences

The three topic IDs do not have to be different. Repeated topic IDs are accepted
and do not cause input validation to fail. For example, `A, A, B` is valid. If
`A` is assignable, its first occurrence has the lowest rank cost. If `A` is not
assignable because its capacity is exhausted, the repeated occurrence does not
create a new fallback and `B` remains a third-choice option.

The legacy column names `topic_1`, `topic_2`, `topic_3`, and
`topic_1_language` through `topic_3_language` are accepted, but their values
must still be topic IDs.

Topic allocation itself does not reject a topic because of language. The first
listed supervision language for the selected preference occurrence is written to
`assigned_language`. That value is then a **hard eligibility constraint** during
daily-supervisor and promotor matching. A researcher whose
`supervision_languages` do not support the student's `assigned_language` is
excluded from that student's candidate set before semantic similarity, workload,
capacity, or topic-submitter priority are considered.

For example:

| Student | Assigned topic | Assigned language | Daily-supervisor candidate | Candidate languages | Eligible? |
| --- | --- | --- | --- | --- | --- |
| Student A | Competition law | French | Excellent researcher | English | **No** |
| Student A | Competition law | French | Good researcher | French, English | **Yes** |

The English-only researcher receives no assignment edge for Student A, even if
their semantic match to the topic is excellent. Among the remaining
French-compatible candidates, the optimizer then considers topic-submitter
priority, hard maximum capacities, minimum workload targets, semantic fit, and
load balancing. Topic allocation does not go back and choose another topic when
the subsequent supervision stage has too little language-compatible capacity. A
complete run therefore becomes infeasible if no compatible supervision assignment
can be made, unless partial results are explicitly allowed.

When a student chooses `9999` on a row without `9998`, that choice is treated as
that student's own, unique thesis topic. It is not constrained by an offered-
topic capacity. The `own_topic_description` is carried into
`assigned_topic_description` and is used as the topic text for semantic
supervisor and promotor matching when `9999` is allocated.

Repeated `9999` preferences are accepted. If `9999` appears more than once, the
earliest occurrence has the lowest rank cost. Because an own topic has no shared
topic-capacity constraint, a first-choice `9999` will be selected during topic
allocation. Daily-supervisor and promotor allocation is a separate stage and
remains subject to researcher eligibility, language, and capacity constraints.

By default, the final row is retained when a form export contains duplicate
student emails. Use `--duplicate-policy error` or
`--duplicate-policy keep-first` to select a different policy.

## Existing and final assignments

The matching and reassignment commands accept assignment tables with these topic
and supervision fields:

| Column | Meaning |
| --- | --- |
| `assigned_topic_id` | Exact topic ID; `9999` identifies an own topic; unresolved annual `9998` rows remain `9998` for manual review |
| `assigned_topic` | Display title generated by the allocation workflow; unresolved `9998` rows contain the manual-review marker |
| `assigned_topic_description` | Description of the allocated topic; retained so future carry-over/reassignment can use the previous final file as its topic source |
| `assigned_language` | Selected supervision language; when populated, assigned researchers must support it |
| `own_topic_description` | Required when `assigned_topic_id` is `9999` |
| `daily_supervisor` | Existing daily-supervisor name; unresolved annual `9998` rows contain the manual-review marker |
| `daily_supervisor_email` | Existing daily-supervisor email; blank for unresolved annual `9998` rows |
| `promotor` | Existing promotor name; unresolved annual `9998` rows contain the manual-review marker |
| `promotor_email` | Existing promotor email; blank for unresolved annual `9998` rows |

Email is the canonical researcher identifier. A name-only supervision carry-over
is accepted when it matches exactly one researcher. Conflicting names and emails
are rejected.

For general fixed preassignments supplied directly to supervisor matching, an
incompatible fixed researcher is rejected. In the annual resolved `9998`
workflow, a previous researcher who is absent, currently ineligible,
language-incompatible, or beyond the current maximum capacity is instead cleared
for that student and the open role is reassigned while the previous topic remains
fixed. When no previous final-assignment file is supplied at all, unresolved
`9998` rows are not sent to automatic supervisor matching and require manual
review.
