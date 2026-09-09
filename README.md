# Computational allocation of thesis supervision

This project allocates thesis topics, daily supervisors, and promotors. It
combines ranked student preferences with topic capacity, ordered language
preferences, researcher eligibility, supervision capacity, topic-submitter
priority, and semantic expertise matching.

The recommended interface is the Google Colab notebook. A command-line interface
is available for local and scripted use.

## Use Google Colab

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/christofkoolen/computational-allocation-of-thesis-supervision/blob/main/notebooks/Thesis_Allocation_Colab.ipynb)

Colleagues need three files:

1. `researchers.xlsx`
2. `topics.xlsx`
3. `student_preferences.xlsx`

In Colab:

1. open the notebook;
2. choose **Complete allocation**;
3. configure the matching options;
4. select **Runtime > Run all**;
5. upload the three files together;
6. download `thesis_allocation_results.zip`.

The notebook can generate blank versions of all three input files. It recognizes
files from their columns, but the standard filenames make each annual run easier
to organize.

## Allocation workflow

The program:

1. validates researcher, topic, and student-preference data;
2. groups the members of each individual or dual thesis;
3. routes ranked, self-proposed, and carry-over submissions;
4. selects a topic and ordered language alternative;
5. assigns a daily supervisor and promotor;
6. expands the final result to one row per student;
7. writes group-level, student-level, workload, and diagnostic outputs.

Topic, language, and supervision choices are optimized jointly. A language is
feasible only when both supervision roles can be filled within the applicable
language, eligibility, and capacity constraints.

## Input files

The project accepts `.xlsx`, `.csv`, and `.tsv` tables. Excel is recommended for
the standard three-file workflow.

### 1. `researchers.xlsx`

One row represents one researcher.

| Column | Purpose |
| --- | --- |
| `full_name` | Researcher name |
| `email` | Unique researcher identifier |
| `appointment_type` | Descriptive appointment information |
| `appointment_percentage` | Descriptive appointment information |
| `comment` | Optional comment |
| `timestamp` | Optional source or update timestamp |
| `supervision_languages` | Languages in which the researcher can supervise |
| `profile_url` | Profile page used for optional enrichment |
| `publications_url` | Publications page used for optional enrichment |
| `profile_description` | Expertise text used for matching |
| `publication_list` | Publication text used for matching |
| `daily_supervisor_minimum_theses` | Target minimum daily-supervisor workload |
| `daily_supervisor_maximum_theses` | Hard maximum daily-supervisor workload |
| `promotor_minimum_theses` | Target minimum promotor workload |
| `promotor_maximum_theses` | Hard maximum promotor workload |

A role maximum above `0` makes the researcher eligible for that role. A maximum
of `0` makes the researcher ineligible. Minimums are workload targets and cannot
create eligibility.

Multiple supervision languages may be separated by semicolons, commas, slashes,
or pipes. A blank researcher-language field is treated as unrestricted for
backwards compatibility.

### 2. `topics.xlsx`

One row represents one offered thesis topic.

| Column | Purpose |
| --- | --- |
| `topic_id` | Stable unique numerical or textual identifier |
| `topic_title` | Official topic title |
| `topic_description` | Description used for semantic matching |
| `submitter_email` | Researcher who proposed the topic |
| `capacity` | Maximum number of theses that may receive the topic |

Students select topics using exact `topic_id` values. Titles are display text and
are not used as identifiers. Topic capacity is a hard constraint.

An eligible topic submitter has absolute supervision priority for that topic up
to the researcher's role capacity. Language compatibility, role eligibility,
maximum capacity, and the distinct-role requirement remain mandatory.

### 3. `student_preferences.xlsx`

One row represents an individual thesis or one dual-thesis pair.

Common fields:

| Column | Purpose |
| --- | --- |
| `full_name` | Primary student's name |
| `email` | Primary student's unique email |
| `student_number` | Primary student's number |
| `thesis_type` | Individual or dual thesis |
| `thesis_allocation_status` | Ranked, self-proposed, or carry-over route |

A dual thesis additionally uses:

- `partner_full_name`
- `partner_email`
- `partner_student_number`
- `dual_thesis_confirmation`

Only one partner should submit the pair. If the same student appears in multiple
thesis groups, validation stops so conflicting rankings cannot be selected
silently.

#### Ranked topic route

The ranked route uses:

- `topic_preference_1` and `topic_preference_1_languages`
- `topic_preference_2` and `topic_preference_2_languages`
- `topic_preference_3` and `topic_preference_3_languages`

The three topic IDs must be different. Topic ranks cost 1, 2, and 3 points. The
optimizer minimizes the total student-weighted topic cost across the complete
group. For a dual pair, the chosen rank cost is multiplied by two.

Languages are ordered alternatives. For example, `Dutch; English` prefers Dutch
over English. If Dutch has insufficient feasible supervision capacity but English
is feasible, the thesis may be assigned in English. If neither is feasible, that
topic choice is unavailable and another ranked topic must be considered.

#### Self-proposed topic route

The self-proposed route uses:

- `self_proposed_thesis_title`
- `self_proposed_thesis_description`
- `self_proposed_thesis_language`

The topic is fixed and does not consume capacity from `topics.xlsx`. Its title
and description are used directly for supervisor matching. Both supervision
roles must still be feasible in one of the submitted languages.

#### Carry-over topic route

The carry-over route uses:

- `carry_over_thesis_topic`
- `carry_over_thesis_description`, optional
- `carry_over_thesis_language`
- `daily_supervisor_email`
- `thesis_promotor_email`

The existing topic is fixed. Named supervisors are retained with priority when
they remain eligible, language-compatible, and within maximum capacity.

Supervisor emails are matched exactly after capitalization and surrounding-space
normalization. A one-character typo is corrected automatically only when one
researcher is a uniquely strong match. Weak or ambiguous matches stop with the
closest candidates listed for correction. The submitted values and resolution
details remain in the outputs.

See [student preference input](docs/STUDENT_PREFERENCES.md) for the complete
column contract.

## Optimization priorities

The current workflow applies these priorities in order:

1. produce a complete allocation, unless partial results were requested;
2. retain feasible named carry-over supervisors;
3. minimize student-weighted topic rank cost;
4. minimize student-weighted language rank;
5. maximize assignments to eligible topic submitters;
6. meet researcher minimum workload targets where feasible;
7. maximize semantic fit with mild load balancing.

After each stage, its optimum is fixed before the next stage is solved. Topic
capacity, researcher maximum capacity, role eligibility, language compatibility,
and distinct supervision roles remain hard constraints.

## Dual-thesis capacity

A dual pair is one thesis allocation unit. It consumes:

- one offered-topic place;
- one daily-supervisor slot;
- one promotor slot.

Both students receive the same topic, language, daily supervisor, and promotor.
They appear as separate rows in `final_assignments.xlsx` with the same
`thesis_group_id`. Capacity reporting uses the group-level result, so the pair is
counted once.

## Output files

A complete run produces:

| File | Purpose |
| --- | --- |
| `researchers_enriched.xlsx` | Validated and optionally enriched researcher data |
| `topic_assignments.xlsx` | One row per thesis group with topic allocation details |
| `thesis_group_assignments.xlsx` | Complete group-level topic and supervision audit |
| `final_assignments.xlsx` | Complete student-level results |
| `final_assignments_shareable.xlsx` | Reduced student-facing assignment fields |
| `supervisor_summary.xlsx` | Workload, minimum, and maximum overview |
| `run_report.json` | Counts, warnings, and output paths |

The group-level workbook is authoritative for topic and supervision capacity.
The student-level workbook is appropriate for communication and student-record
workflows.

## Run locally

Install Python 3.10 or newer, then install the package:

```bash
python -m venv .venv
python -m pip install -e ".[semantic]"
```

Create blank inputs:

```bash
thesis-allocation create-templates input
```

Run the complete workflow:

```bash
thesis-allocation run \
  --researchers input/researchers.xlsx \
  --topics input/topics.xlsx \
  --preferences input/student_preferences.xlsx \
  --output-directory output \
  --skip-scrape
```

Remove `--skip-scrape` to retrieve missing researcher profile and publication
text from configured URLs. Use `--backend tfidf` for fast offline lexical
matching.

## Reassign supervision

The reassignment command replaces one student's role or every assignment held by
a departing researcher while preserving unaffected assignments.

```bash
thesis-allocation reassign \
  --assignments output/final_assignments.xlsx \
  --topics input/topics.xlsx \
  --researchers input/researchers.xlsx \
  --role daily_supervisor \
  --departing-supervisor-email researcher@example.org \
  --output output/final_assignments_reassigned.xlsx \
  --summary-output output/supervisor_summary_reassigned.xlsx \
  --log-output output/reassignment_log.csv
```

## Development

Run the tests with:

```bash
python -m unittest discover -s tests -v
```

Validate that the committed Colab notebook matches its generator:

```bash
python scripts/build_colab_notebook.py --check
```

See [algorithm details](docs/ALGORITHM.md), [Colab guide](docs/COLAB.md), and
[student preference input](docs/STUDENT_PREFERENCES.md) for more information.
