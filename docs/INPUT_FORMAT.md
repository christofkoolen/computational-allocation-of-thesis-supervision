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
| `appointment` | No | Informational role or appointment label |
| `profile_url` | No | Web profile used by the enrichment stage |
| `publications_url` | No | Explicit publications page; derived from supported KU Leuven staff URLs when blank |
| `profile_description` | No | Existing profile text; retained unless `--refresh` is used |
| `publication_list` | No | Existing publication text; retained unless `--refresh` is used |
| `daily_supervisor_minimum_theses` | Yes for matching | Workload target for the daily-supervisor role |
| `daily_supervisor_maximum_theses` | Yes for matching | Hard capacity; zero makes the person ineligible for this role |
| `promotor_minimum_theses` | Yes for matching | Workload target for the promotor role |
| `promotor_maximum_theses` | Yes for matching | Hard capacity; zero makes the person ineligible for this role |

Each minimum and maximum must be a non-negative whole number, and a minimum
cannot exceed its corresponding maximum.

## Topics

One row represents one available thesis topic.

| Column | Required | Meaning |
| --- | --- | --- |
| `topic_id` | Recommended | Stable unique ID; generated from the title when the entire column is blank |
| `topic_title` | Yes | Unique official topic title |
| `topic_description` | No | Text included in semantic matching |
| `submitter_email` | No | Researcher who proposed the topic; receives absolute supervision priority when eligible and within maximum capacity |
| `capacity` | No | Number of students who may receive the topic; defaults to 1 |
| `supervision_languages` | No | Comma or semicolon separated languages allowed for the topic |

The aliases `proposed_thesis_topic`, `subject_field`, and
`researcher_email` remain supported.

## Student preferences

One row represents one student's ranked submission.

| Column | Required | Meaning |
| --- | --- | --- |
| `full_name` | Yes | Student display name |
| `email` | Yes | Unique student identifier |
| `preference_1` | Yes | Topic ID or official title |
| `preference_1_languages` | No | Acceptable languages for this choice |
| `preference_2` | No | Topic ID or official title |
| `preference_2_languages` | No | Acceptable languages for this choice |
| `preference_3` | No | Topic ID or official title |
| `preference_3_languages` | No | Acceptable languages for this choice |

The legacy names `topic_1`, `topic_2`, `topic_3`, and
`topic_1_language` through `topic_3_language` are accepted.

By default, the final row is retained when a form export contains duplicate
student emails. Use `--duplicate-policy error` or
`--duplicate-policy keep-first` to select a different policy.

## Existing assignments

The matching and reassignment commands accept the output of
`allocate-topics`. Carry-over values may already be present in:

| Column | Meaning |
| --- | --- |
| `daily_supervisor` | Existing daily-supervisor name |
| `daily_supervisor_email` | Existing daily-supervisor email |
| `promotor` | Existing promotor name |
| `promotor_email` | Existing promotor email |

Email is the canonical identifier. A name-only carry-over is accepted when it
matches exactly one researcher. Conflicting names and emails are rejected.
