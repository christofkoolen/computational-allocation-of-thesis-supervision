# Computational allocation of thesis supervision

This project helps allocate thesis topics, daily supervisors, and promotors in a reproducible and auditable way.

It is designed for situations where:

- students submit three ranked thesis-topic preferences;
- offered topics may have limited capacity;
- researchers have different supervision capacities and language abilities;
- the researcher who proposed a topic should normally supervise it when eligible;
- otherwise, the topic should be matched to a researcher with relevant expertise;
- existing assignments may need to be reassigned when someone leaves.

The recommended way to use the project is through the Google Colab notebook. A command-line interface is also available for local or scripted use.

## Recommended: use Google Colab

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/christofkoolen/computational-allocation-of-thesis-supervision/blob/main/notebooks/Thesis_Allocation_Colab.ipynb)

The Colab notebook runs entirely in the browser and does not require a local Python installation or GitHub authentication.

For a normal annual allocation:

1. prepare the three input files described below;
2. open the Colab notebook;
3. choose **Complete allocation**;
4. select the desired options;
5. run the notebook and upload the three input files together;
6. download the resulting ZIP file.

The notebook can also reassign one student's supervisor or all assignments held by a departing researcher.

## What the pipeline does

A complete run has three main stages:

1. **Researcher enrichment**: optionally retrieve profile and publication text for researchers.
2. **Topic allocation**: assign students to their ranked topic IDs while respecting topic capacity.
3. **Supervision allocation**: assign daily supervisors and promotors using eligibility rules, workload constraints, topic-submitter priority, and semantic similarity.

Topic allocation and supervision allocation are separate stages. A student first receives a topic. The program then finds suitable supervisors for that assigned topic.

## Input files

The project accepts `.xlsx`, `.csv`, and `.tsv` files. The standard workflow uses three files:

- `researchers.xlsx`
- `topics.xlsx`
- `student_preferences.xlsx`

Canonical column names are recommended. Selected legacy aliases are still accepted.

The Colab notebook can generate blank templates, or they can be created locally with:

```bash
thesis-allocation create-templates input
```

### 1. `researchers.xlsx`

One row represents one researcher.

| Column | Purpose |
| --- | --- |
| `full_name` | Researcher name |
| `email` | Unique researcher identifier |
| `appointment_type` | Descriptive appointment information only |
| `appointment_percentage` | Descriptive appointment information only |
| `comment` | Optional descriptive comment |
| `timestamp` | Optional source or update timestamp |
| `supervision_languages` | Languages in which the researcher can supervise; blank means unrestricted |
| `profile_url` | Researcher profile page used for optional enrichment |
| `publications_url` | Publications page used for optional enrichment |
| `profile_description` | Text describing the researcher's expertise |
| `publication_list` | Publication text used for semantic matching |
| `daily_supervisor_minimum_theses` | Target minimum daily-supervisor workload |
| `daily_supervisor_maximum_theses` | Hard maximum daily-supervisor workload |
| `promotor_minimum_theses` | Target minimum promotor workload |
| `promotor_maximum_theses` | Hard maximum promotor workload |

### Researcher eligibility

The descriptive appointment fields do not determine whether someone may supervise.

Eligibility is controlled by the maximum-capacity columns:

- `daily_supervisor_maximum_theses > 0` means the researcher is eligible as a daily supervisor;
- `promotor_maximum_theses > 0` means the researcher is eligible as a promotor;
- a maximum of `0` makes the researcher ineligible for that role.

The minimum columns are workload targets. They do not make someone eligible for a role.

Minimums and maximums must be non-negative whole numbers, and a minimum cannot exceed the corresponding maximum.

### Supervision languages

`supervision_languages` may contain multiple languages separated by commas or semicolons.

If a student has an assigned supervision language, a researcher who does not support that language is excluded before semantic similarity or workload optimization is considered.

A blank researcher language field is treated as unrestricted for backwards compatibility.

### 2. `topics.xlsx`

One row represents one offered thesis topic.

| Column | Purpose |
| --- | --- |
| `topic_id` | Stable unique ID used in student preferences |
| `topic_title` | Official topic title |
| `topic_description` | Optional description used in semantic supervisor matching |
| `submitter_email` | Email of the researcher who proposed the topic |
| `capacity` | Maximum number of students who may receive this offered topic |

`topic_id` and `topic_title` must be unique.

Topic ID `9999` is reserved for student-specific own topics and must not appear in `topics.xlsx`.

### Topic capacity

Topic capacity is a hard constraint during topic allocation.

For example, if a topic has:

```text
capacity = 3
```

then at most three students can receive that offered topic, even if more students rank it first.

If the `capacity` column is omitted entirely, the default capacity is `1`. If the column is present, each topic must have a positive whole-number capacity.

Topic capacity is separate from supervisor capacity. Topic capacity limits how many students can receive a topic. Researcher maximums limit how many theses a researcher may supervise.

### Why `topic_description` matters

`topic_description` does not affect which ranked topic a student receives.

It is used later for semantic supervisor matching. For an offered topic, the program combines:

```text
topic_title + topic_description
```

and compares that text with researcher expertise derived from:

```text
profile_description + publication_list
```

A concise, substantive topic description therefore gives the semantic matcher more information about the expertise relevant to the thesis.

The default semantic model is:

```text
BAAI/bge-base-en-v1.5
```

The model converts the topic and researcher text into normalized embeddings and the program compares them using cosine similarity.

The current implementation does **not** chunk long researcher text. `profile_description` and `publication_list` are concatenated and sent to the embedding model as one text. Text beyond the model's effective input length can therefore be truncated. Keeping the most informative research description and publication information near the beginning of these fields is useful when the combined text is very long.

### What if the person who submitted a topic has left?

The topic remains valid.

The submitter receives special supervision priority only when that person is still an eligible researcher for the relevant role. If the submitter is absent from the eligible candidate pool, the program falls back to the normal matching process using language compatibility, capacity, workload targets, semantic similarity, and load balancing.

For a **new allocation**, a former employee should be removed from the researcher file or given a maximum capacity of `0` for roles they may no longer perform. If a former employee remains in `researchers.xlsx` with a positive maximum, the program still considers that person eligible.

For **reassignment of existing assignments**, use the reassignment workflow described below. The departing researcher is explicitly excluded from replacement candidates while unaffected assignments remain fixed.

### 3. `student_preferences.xlsx`

One row represents one student's submission.

| Column | Purpose |
| --- | --- |
| `full_name` | Student name |
| `email` | Unique student identifier |
| `preference_1` | First-choice topic ID |
| `preference_1_languages` | Acceptable supervision language or languages for the first choice |
| `preference_2` | Second-choice topic ID |
| `preference_2_languages` | Acceptable supervision language or languages for the second choice |
| `preference_3` | Third-choice topic ID |
| `preference_3_languages` | Acceptable supervision language or languages for the third choice |
| `own_topic_description` | Required when the student uses topic ID `9999` |

Students must provide three different topic IDs. Topic titles are not used as identifiers and there is no fuzzy title matching.

By default, if a form export contains multiple rows with the same student email, the final row is retained. The CLI can instead keep the first row or stop with an error.

## Own topics: topic ID `9999`

Topic ID `9999` represents a student-specific own topic.

When a student uses `9999`:

- `own_topic_description` is required;
- `9999` can appear at most once because all three preference IDs must differ;
- it does not consume capacity from any offered topic;
- it has no topic submitter;
- its description is used directly for semantic supervisor matching.

Because an own topic has no shared topic-capacity constraint, ranking `9999` first means it will be selected during topic allocation. Ranking it second or third makes it an always-available fallback when a higher-ranked offered topic cannot be assigned.

Supervisor allocation still has to satisfy researcher eligibility, language, and capacity constraints.

## How topic allocation works

The program models topic allocation as a minimum-cost flow problem.

Each student can receive at most one topic. Each offered topic can receive students only up to its declared capacity. A student's first, second, and third choices have costs of `1`, `2`, and `3` respectively.

The optimizer finds a complete feasible allocation with the smallest possible total preference cost. In practical terms, it tries to keep students as high as possible in their ranked preferences across the whole cohort rather than processing students one by one.

Preferences are resolved by exact topic ID only.

If the selected preference contains one or more supervision languages, the first listed language is carried forward as `assigned_language` for the supervision stage.

Topic allocation itself does not reject a topic because a later supervision-language match may be difficult. If the supervision stage later has insufficient language-compatible capacity, the topic allocation is not automatically rerun.

## How daily supervisors and promotors are chosen

After topics have been assigned, daily supervisors and promotors are matched separately as global optimization problems.

For each role, the program first builds the set of eligible researcher candidates. A candidate must:

1. have a positive maximum capacity for that role;
2. support the student's `assigned_language` when one is specified;
3. have available capacity;
4. satisfy any explicit exclusions;
5. be different from the student's other supervision role unless `--allow-same-person` is used.

Among feasible candidates, the optimization follows these priorities.

### 1. Eligible topic submitter

For offered topics, an eligible topic submitter receives absolute assignment priority up to that person's maximum capacity.

Submitter priority still respects:

- supervision-language compatibility;
- role eligibility;
- maximum capacity;
- explicit exclusions;
- the rule that daily supervisor and promotor are normally different people.

If the submitter is unavailable or ineligible, the topic is matched normally.

Own topics have no submitter priority.

### 2. Minimum workload targets

After submitter priority, the optimizer prioritizes available slots that help researchers reach their declared minimum workload targets.

Minimums are targets rather than hard guarantees. A minimum can remain unmet when other constraints make it impossible to satisfy.

### 3. Semantic similarity

The semantic model compares the assigned topic text with researcher profile and publication text.

For offered topics:

```text
topic text = topic_title + topic_description
```

For own topics:

```text
topic text = own_topic_description
```

For researchers:

```text
researcher text = profile_description + publication_list
```

The resulting similarity score helps the optimizer choose researchers whose expertise is more closely related to the thesis topic.

### 4. Load balancing

A mild incremental load-balancing cost discourages unnecessary concentration of assignments on the same researchers when otherwise comparable alternatives exist.

### Distinct daily supervisor and promotor

By default, one person cannot be both the daily supervisor and promotor for the same student.

The CLI option:

```text
--allow-same-person
```

removes this restriction.

## Existing and carry-over assignments

Supervisor matching can preserve existing daily-supervisor and promotor assignments.

Email is the canonical researcher identifier. A name-only carry-over is accepted only when it matches exactly one researcher.

Existing assignments are validated. The program rejects conflicting names and emails, unknown researcher emails, and fixed supervisors who are incompatible with a student's selected supervision language.

Existing assignments count against the researcher's maximum capacity.

## Reassignment

The project supports targeted reassignment without rebuilding every supervision assignment.

You can replace:

- one student's daily supervisor;
- one student's promotor;
- every assignment held by one departing daily supervisor;
- every assignment held by one departing promotor.

The reassignment workflow clears only the selected role for the affected student or students. All other assignments remain fixed and count toward current workload.

The same language, capacity, distinct-role, minimum-workload, semantic, and load-balancing rules are then used to fill the open assignments.

The reassignment output includes a change log containing the previous assignee, replacement, semantic score, and assignment source.

### Reassign a departing daily supervisor from the CLI

```bash
thesis-allocation reassign \
  --assignments output/final_assignments.xlsx \
  --topics input/topics.xlsx \
  --researchers output/researchers_enriched.xlsx \
  --role daily_supervisor \
  --departing-supervisor-email person@example.org \
  --output output/final_assignments_reassigned.xlsx \
  --summary-output output/supervisor_summary_reassigned.xlsx \
  --log-output output/reassignment_log.csv
```

### Reassign one student's promotor from the CLI

```bash
thesis-allocation reassign \
  --assignments output/final_assignments.xlsx \
  --topics input/topics.xlsx \
  --researchers output/researchers_enriched.xlsx \
  --role promotor \
  --student-email student@example.org \
  --output output/final_assignments_reassigned.xlsx \
  --summary-output output/supervisor_summary_reassigned.xlsx \
  --log-output output/reassignment_log.csv
```

## Researcher enrichment

The enrichment stage can retrieve visible text from researcher profile and publication pages when those fields are missing.

Existing `profile_description` and `publication_list` values are reused unless refresh mode is requested.

The scraper excludes page elements such as scripts, styles, templates, and SVG content.

A failed retrieval does not remove the researcher. The enriched output records retrieval status and the run emits a warning so that the input can be reviewed.

Use `--skip-scrape` in a complete CLI run when no web retrieval should occur.

## Outputs

A complete allocation produces:

| File | Contents |
| --- | --- |
| `researchers_enriched.xlsx` | Researcher input, retrieved text, and retrieval status |
| `topic_assignments.xlsx` | Assigned topic ID and title, selected language, assigned rank, and preference cost |
| `final_assignments.xlsx` | Topic, daily supervisor, promotor, semantic scores, and assignment sources |
| `supervisor_summary.xlsx` | Researcher minimums, maximums, actual workload, language information, and capacity flags |
| `run_report.json` | Machine-readable totals, warnings, and output paths |

Assignment sources make the result easier to audit. A supervision assignment can come from an existing carry-over, topic-submitter priority, or general semantic matching.

The pipeline stops with an actionable error when the input is invalid or a complete assignment is impossible. Partial results can be explicitly enabled when appropriate.

## Using Google Colab

The Colab notebook is intended for colleagues who do not normally use Python or a terminal.

### Complete allocation

Choose **Complete allocation** and upload:

- researcher data;
- topic data;
- student preferences.

The notebook allocates topics first, then daily supervisors and promotors, and downloads `thesis_allocation_results.zip`.

### Reassignment

Choose **Reassign supervision** and upload:

- the previous final assignments;
- researcher data;
- topic data.

Choose the role and whether to replace one student's assignment or all assignments held by a departing researcher. The notebook downloads `thesis_reassignment_results.zip`.

### Semantic versus lexical matching

The notebook offers:

- **Semantic matching (recommended)**, using the sentence-transformer backend and the default `BAAI/bge-base-en-v1.5` model;
- **Fast lexical matching**, using TF-IDF as an offline fallback.

A GPU runtime can accelerate embedding generation when CUDA is available to PyTorch and Sentence Transformers. The code does not force a CPU device, so the semantic model can use an available CUDA device automatically. Topic optimization, spreadsheet processing, and most other stages remain CPU work.

### Data handling in Colab

Colab runs on a Google-hosted virtual machine, so uploaded student and researcher data leave the user's computer.

The notebook:

- does not mount Google Drive;
- does not display uploaded input tables;
- removes uploaded input files after processing;
- downloads outputs as one ZIP archive;
- instructs the user to disconnect and delete the runtime when finished.

Use real student data only when this processing arrangement has been approved by the relevant institution.

## Command-line installation

Python 3.10 or newer is required.

For semantic matching:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[semantic]"
```

Create blank input templates:

```bash
thesis-allocation create-templates input
```

Run the complete pipeline:

```bash
thesis-allocation run \
  --researchers input/researchers.xlsx \
  --topics input/topics.xlsx \
  --preferences input/student_preferences.xlsx \
  --output-directory output
```

The first semantic run downloads the default `BAAI/bge-base-en-v1.5` model.

To prohibit researcher-profile retrieval:

```text
--skip-scrape
```

For a lightweight offline semantic substitute, use:

```text
--backend tfidf
```

A different Sentence Transformers model can be supplied with:

```text
--model MODEL_NAME
```

## Running individual stages

### Enrich researchers

```bash
thesis-allocation scrape-researchers \
  --researchers input/researchers.xlsx \
  --output output/researchers_enriched.xlsx
```

### Allocate topics only

```bash
thesis-allocation allocate-topics \
  --preferences input/student_preferences.xlsx \
  --topics input/topics.xlsx \
  --output output/topic_assignments.xlsx
```

### Match supervisors only

```bash
thesis-allocation match-supervisors \
  --assignments output/topic_assignments.xlsx \
  --topics input/topics.xlsx \
  --researchers output/researchers_enriched.xlsx \
  --output output/final_assignments.xlsx \
  --summary-output output/supervisor_summary.xlsx
```

## Important policy summary

- Students provide three different exact topic IDs.
- Topic titles are display fields and are not used to resolve preferences.
- Topic ID `9999` is reserved for a student's own topic.
- Offered-topic capacity is a hard constraint.
- Own topics do not consume shared offered-topic capacity.
- Topic descriptions help semantic supervisor matching but do not affect topic allocation.
- Researcher role eligibility is determined by positive maximum capacity for that role.
- `assigned_language` is a hard supervision-eligibility constraint.
- Eligible topic submitters receive supervision priority up to their available capacity.
- Researcher minimums are prioritized workload targets.
- Semantic similarity is optimized globally among feasible candidates.
- Daily supervisor and promotor must normally be different people.
- Existing valid assignments remain fixed unless explicitly targeted for reassignment.
- Invalid topic IDs, conflicting carry-over assignments, and infeasible complete allocations produce explicit errors.

## Determinism and reproducibility

Inputs and candidates are sorted by canonical email or topic ID before optimization.

Given the same inputs, model, configuration, and dependency versions, the optimization is designed to produce the same assignment.

## Development

The base test suite does not download the embedding model.

```bash
python -m pip install -e .
python -m compileall -q src tests
python -m unittest discover -s tests -v
python scripts/build_colab_notebook.py --check
```

The committed Colab notebook is generated from `scripts/build_colab_notebook.py`. After changing the notebook workflow, regenerate and verify it with:

```bash
python scripts/build_colab_notebook.py
python scripts/build_colab_notebook.py --check
```

## Detailed documentation

The README is intended to be enough for most users. More implementation-focused documentation remains available in:

- [Input format](docs/INPUT_FORMAT.md)
- [Algorithm](docs/ALGORITHM.md)
- [Google Colab guide](docs/COLAB.md)
