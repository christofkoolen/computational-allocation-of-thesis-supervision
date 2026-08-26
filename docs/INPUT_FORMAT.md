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
| `topic_description` | No | Text included in semantic matching |
| `submitter_email` | No | Researcher who proposed the topic; receives absolute supervision priority when eligible and within maximum capacity |
| `capacity` | No | Number of students who may receive the topic; defaults to 1 when the column is omitted |

Topic ID `9999` is reserved for a student's own topic and must not appear in
the topics file. Topic IDs are never generated from titles.

The aliases `proposed_thesis_topic`, `subject_field`, and
`researcher_email` remain supported for the descriptive topic fields.

## Student preferences

One row represents one student's ranked submission. Students must provide all
three preference fields as topic IDs. Topic titles are not accepted as identifiers
and no fuzzy or approximate title matching is performed.

| Column | Required | Meaning |
| --- | --- | --- |
| `full_name` | Yes | Student display name |
| `email` | Yes | Unique student identifier |
| `preference_1` | Yes | First-choice topic ID |
| `preference_1_languages` | No | Acceptable supervision languages for this choice; the first listed language becomes the selected language when this occurrence is assigned |
| `preference_2` | Yes | Second-choice topic ID |
| `preference_2_languages` | No | Acceptable supervision languages for this choice; the first listed language becomes the selected language when this occurrence is assigned |
| `preference_3` | Yes | Third-choice topic ID |
| `preference_3_languages` | No | Acceptable supervision languages for this choice; the first listed language becomes the selected language when this occurrence is assigned |
| `own_topic_description` | Conditional | Short description required when any preference is topic ID `9999` |

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

When a student chooses `9999`, that choice is treated as that student's own,
unique thesis topic. It is not constrained by an offered-topic capacity. The
`own_topic_description` is carried into the assignment output and is used as the
topic text for semantic supervisor and promotor matching when `9999` is allocated.

Repeated `9999` preferences are accepted. If `9999` appears more than once, the
earliest occurrence has the lowest rank cost. Because an own topic has no shared
topic-capacity constraint, a first-choice `9999` will be selected during topic
allocation. Daily-supervisor and promotor allocation is a separate stage and
remains subject to researcher eligibility, language, and capacity constraints.

By default, the final row is retained when a form export contains duplicate
student emails. Use `--duplicate-policy error` or
`--duplicate-policy keep-first` to select a different policy.

## Existing assignments

The matching and reassignment commands accept the output of
`allocate-topics`. Carry-over values may already be present in:

| Column | Meaning |
| --- | --- |
| `assigned_topic_id` | Exact topic ID; `9999` identifies an own topic |
| `assigned_topic` | Display title generated by the allocation workflow |
| `assigned_language` | Selected supervision language; when populated, assigned researchers must support it |
| `own_topic_description` | Required when `assigned_topic_id` is `9999` |
| `daily_supervisor` | Existing daily-supervisor name |
| `daily_supervisor_email` | Existing daily-supervisor email |
| `promotor` | Existing promotor name |
| `promotor_email` | Existing promotor email |

Email is the canonical researcher identifier. A name-only supervision
carry-over is accepted when it matches exactly one researcher. Conflicting
names and emails are rejected. A fixed carry-over that does not support the
selected `assigned_language` is rejected. Topic titles are not used to recover
a missing or mistyped topic ID.
