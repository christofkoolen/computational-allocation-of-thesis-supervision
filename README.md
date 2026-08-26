# Computational allocation of thesis supervision

This project allocates thesis topics, daily supervisors, and promotors in a reproducible and auditable way.

It is designed for situations where:

- students submit ranked thesis-topic preferences;
- offered topics may have limited capacity;
- researchers have different supervision capacities and language abilities;
- the researcher who proposed a topic should normally supervise it when eligible;
- otherwise, the topic should be matched to a researcher with relevant expertise;
- previous-year thesis allocations may need to carry over;
- existing assignments may need to be reassigned when someone leaves.

The recommended way to use the project is through the Google Colab notebook. A Python command-line interface is also available for local or scripted use.

## Recommended: use Google Colab

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/christofkoolen/computational-allocation-of-thesis-supervision/blob/main/notebooks/Thesis_Allocation_Colab.ipynb)

The Colab notebook runs in the browser and does not require a local Python installation or GitHub authentication.

For a normal annual allocation:

1. prepare the three current-year input files described below;
2. if any continuing student uses topic ID `9998`, also prepare the previous `final_assignments.xlsx` file;
3. open the Colab notebook;
4. choose **Complete allocation**;
5. select the desired options;
6. run the notebook and upload the required files together;
7. download the resulting ZIP file.

The notebook can also reassign one student's supervisor or all assignments held by a departing researcher.

## What the pipeline does

A complete run has three main stages:

1. **Researcher enrichment**: optionally retrieve profile and publication text for researchers.
2. **Topic allocation**: separate `9998` carry-over students, then assign current-year students to their ranked topic IDs while respecting topic capacity.
3. **Supervision allocation**: preserve valid carry-over supervision up to current capacities, then assign open daily-supervisor and promotor roles using eligibility rules, workload constraints, topic-submitter priority, and semantic similarity.

Topic allocation and supervision allocation are separate stages. A student first receives or carries forward a topic. The program then finds suitable supervisors for any open supervision roles.

## Input files

The project accepts `.xlsx`, `.csv`, and `.tsv` files. The standard workflow uses:

- `researchers.xlsx`
- `topics.xlsx`
- `student_preferences.xlsx`

When one or more students use topic ID `9998`, Complete allocation also uses the previous final assignment file, normally named:

- `previous_final_assignments.xlsx`

Canonical column names are recommended. Selected legacy aliases are still accepted.

The Colab notebook can generate blank templates, or they can be created locally with:

```bash
python -m thesis_allocation create-templates input
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
| `topic_description` | Optional description used in semantic supervisor matching and copied into `assigned_topic_description` |
| `submitter_email` | Email of the researcher who proposed the topic |
| `capacity` | Maximum number of students who may receive this offered topic |

`topic_id` and `topic_title` must be unique.

Topic IDs `9998` and `9999` are reserved and must not appear in `topics.xlsx`. `9998` means previous-year carry-over and `9999` means a student-specific own topic.

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

The allocated description is also written to `assigned_topic_description` so `final_assignments.xlsx` contains the topic text needed for later carry-over and reassignment.

A concise, substantive topic description gives the semantic matcher more information about the expertise relevant to the thesis.

The default semantic model is:

```text
BAAI/bge-base-en-v1.5
```

The model converts topic and researcher text into normalized embeddings and the program compares them using cosine similarity.

The current implementation does **not** chunk long researcher text. `profile_description` and `publication_list` are concatenated and sent to the embedding model as one text. Text beyond the model's effective input length can therefore be truncated. Keeping the most informative research description and publication information near the beginning of these fields is useful when the combined text is very long.

### What if the person who submitted a topic has left?

The topic remains valid.

The submitter receives special supervision priority only when that person is still an eligible researcher for the relevant role. If the submitter is absent from the eligible candidate pool, the program falls back to normal matching using language compatibility, capacity, workload targets, semantic similarity, and load balancing.

For a **new allocation**, a former employee should be removed from the researcher file or given a maximum capacity of `0` for roles they may no longer perform. If a former employee remains in `researchers.xlsx` with a positive maximum, the program still considers that person eligible.

For **reassignment of existing assignments**, use the reassignment workflow described below. The departing researcher is explicitly excluded from replacement candidates while unaffected assignments remain fixed.

### 3. `student_preferences.xlsx`

One row represents one student's submission.

| Column | Purpose |
| --- | --- |
| `full_name` | Student name |
| `email` | Unique student identifier |
| `preference_1` | First-choice topic ID, or `9998` for previous-year carry-over |
| `preference_1_languages` | Acceptable supervision language or languages for the first choice |
| `preference_2` | Second-choice topic ID; may be blank when `preference_1 = 9998` |
| `preference_2_languages` | Acceptable supervision language or languages for the second choice |
| `preference_3` | Third-choice topic ID; may be blank when `preference_1 = 9998` |
| `preference_3_languages` | Acceptable supervision language or languages for the third choice |
| `own_topic_description` | Required when the student uses topic ID `9999` |

For ordinary current-year allocation, students provide all three preference fields. The topic IDs do **not** have to be different. Repeated topic IDs are accepted.

For example:

```text
preference_1 = A
preference_2 = A
preference_3 = B
```

is valid input. If topic `A` can be assigned, its first occurrence has the lowest rank cost and is therefore the effective choice. If `A` cannot be assigned because its capacity is exhausted, the repeated `A` does not provide an additional alternative, so `B` remains a third-choice fallback.

This permissive behavior is intentional. The program does not reject a student's submission simply because the same topic was selected more than once.

Topic titles are not used as identifiers and there is no fuzzy title matching.

By default, if a form export contains multiple rows with the same student email, the final row is retained. The CLI can instead keep the first row or stop with an error.

## Previous-year carry-over: topic ID `9998`

Topic ID `9998` means: **continue my previous thesis allocation**.

A continuing student enters:

```text
preference_1 = 9998
```

For that student, preferences 2 and 3 may be blank. `9998` is allowed only as preference 1.

Complete allocation then matches the student by normalized email to `previous_final_assignments.xlsx` and carries forward:

- `assigned_topic_id`
- `assigned_topic`
- `assigned_topic_description`
- `assigned_language`
- previous daily supervisor
- previous promotor

The previous final-assignment row is authoritative for the `9998` student's topic. That student's topic is not resolved against the current `topics.xlsx`, even when the old topic ID has been reused for a different current-year topic.

Valid previous supervisors remain fixed only up to their current role maximums. If three carry-over students point to a researcher whose current maximum is two, the first two carry-over roles are retained and the third role is cleared and reassigned through normal matching. The topic and language remain carried over.

If a previous supervisor has left, is currently ineligible, or is incompatible with the carried language, only that role is cleared and reassigned.

A repeat student who wants a new topic simply submits three ordinary topic IDs. Being present in the previous assignment file does not trigger carry-over by itself.

See [`docs/CARRY_OVER.md`](docs/CARRY_OVER.md) for the detailed policy.

## Own topics: topic ID `9999`

Topic ID `9999` represents a student-specific own topic.

When a student uses `9999`:

- `own_topic_description` is required;
- it does not consume capacity from any offered topic;
- it has no topic submitter;
- its description is copied into `assigned_topic_description` and used directly for semantic supervisor matching.

Repeated `9999` preferences are accepted as well. If it occurs more than once, the earliest occurrence has the lowest rank cost. Because an own topic has no shared topic-capacity constraint, a first-choice `9999` will be selected during topic allocation.

Supervisor allocation still has to satisfy researcher eligibility, language, and capacity constraints.

## How topic allocation works

The program models topic allocation as a minimum-cost flow problem.

Each ordinary student can receive at most one topic. Each offered topic can receive students only up to its declared capacity. A student's first, second, and third preference positions have costs of `1`, `2`, and `3` respectively.

The optimizer finds a complete feasible allocation with the smallest possible total preference cost. In practical terms, it tries to keep students as high as possible in their ranked preferences across the whole cohort rather than processing students one by one.

Preferences are resolved by exact topic ID only.

Repeated IDs simply create repeated ranked routes to the same topic. The earliest occurrence has the lowest cost. Repetition does not increase a topic's capacity and does not create an extra fallback option.

`9998` students are separated before this current-year topic optimization and contribute no preference cost.

If the selected preference contains one or more supervision languages, the first listed language for the selected occurrence is carried forward as `assigned_language` for the supervision stage.

Topic allocation itself does not reject a topic because a later supervision-language match may be difficult. If the supervision stage later has insufficient language-compatible capacity, the topic allocation is not automatically rerun.

## How daily supervisors and promotors are chosen

After topics have been assigned or carried over, daily supervisors and promotors are matched separately as global optimization problems.

For each role, the program first builds the set of eligible researcher candidates. A candidate must:

1. have a positive maximum capacity for that role;
2. support the student's `assigned_language` when one is specified;
3. have available capacity;
4. satisfy any explicit exclusions;
5. be different from the student's other supervision role unless `--allow-same-person` is used.

Among feasible candidates, the optimization follows these priorities.

### 1. Eligible topic submitter

For current-year offered topics, an eligible topic submitter receives absolute assignment priority up to that person's maximum capacity.

Submitter priority still respects supervision-language compatibility, role eligibility, maximum capacity, explicit exclusions, and the distinct-role rule.

If the submitter is unavailable or ineligible, the topic is matched normally. Own topics and `9998` carry-over topics have no current-year submitter priority.

### 2. Minimum workload targets

After submitter priority, the optimizer prioritizes available slots that help researchers reach their declared minimum workload targets.

Minimums are targets rather than hard guarantees. A minimum can remain unmet when other constraints make it impossible to satisfy.

### 3. Semantic similarity

The semantic model compares the assigned topic text with researcher profile and publication text.

For current-year offered topics:

```text
topic text = assigned_topic + assigned_topic_description
```

For own topics:

```text
topic text = own_topic_description
```

For `9998` carry-over topics:

```text
topic text = previous assigned_topic + previous assigned_topic_description
```

Older previous-final-assignment files without `assigned_topic_description` fall back to the previous `assigned_topic` title.

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

Email is the canonical researcher identifier. A name-only fixed assignment is accepted only when it matches exactly one researcher.

For general fixed preassignments passed directly to supervisor matching, conflicting names/emails, unknown researcher emails, and language-incompatible fixed supervisors are rejected.

The annual `9998` workflow is more recovery-oriented: a previous supervisor who is absent, currently ineligible, language-incompatible, or beyond the current role maximum is cleared for the affected carry-over student and that open role is reassigned. Valid carry-over assignments count against current maximum capacity.

## Reassignment

The project supports targeted reassignment without rebuilding every supervision assignment.

You can replace one student's daily supervisor or promotor, or every assignment held by one departing researcher for a selected role.

The reassignment workflow clears only the selected role for the affected student or students. All other assignments remain fixed and count toward current workload.

The same language, capacity, distinct-role, minimum-workload, semantic, and load-balancing rules are then used to fill the open assignments.

The reassignment output includes a change log containing the previous assignee, replacement, semantic score, and assignment source.

### Reassign a departing daily supervisor from the CLI

```bash
python -m thesis_allocation reassign \
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
python -m thesis_allocation reassign \
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

A failed retrieval does not remove the researcher. The enriched output records retrieval status and the run emits a warning so that the input can be reviewed.

Use `--skip-scrape` in a complete CLI run when no web retrieval should occur.

## Outputs

A complete allocation produces:

| File | Contents |
| --- | --- |
| `researchers_enriched.xlsx` | Researcher input, retrieved text, and retrieval status |
| `topic_assignments.xlsx` | Assigned topic ID, title, description, selected language, assigned rank, and preference cost |
| `final_assignments.xlsx` | Full allocation with topic ID/title/description, daily supervisor, promotor, semantic scores, assignment sources, and carried-forward student fields |
| `final_assignments_shareable.xlsx` | Reduced publication copy with student identity, assigned topic and language, and supervisor/promotor names and emails |
| `supervisor_summary.xlsx` | Researcher minimums, maximums, actual workload, language information, and capacity flags |
| `run_report.json` | Machine-readable totals, warnings, and output paths |

`final_assignments.xlsx` includes `assigned_topic_description`. This field is the allocated offered-topic description, the student's own-topic description for `9999`, or the carried previous description for `9998`.

`final_assignments_shareable.xlsx` contains exactly these columns:

```text
full_name
email
assigned_topic
assigned_language
daily_supervisor
daily_supervisor_email
promotor
promotor_email
```

It is a reduced-column sharing copy, not an anonymized dataset. It still contains student and researcher email addresses, so publication should follow the institution's applicable privacy rules.

Assignment sources make the full result easier to audit. A supervision assignment can come from an existing carry-over, topic-submitter priority, or general semantic matching.

The pipeline stops with an actionable error when the input is invalid or a complete assignment is impossible. Partial results can be explicitly enabled when appropriate.

## Using Google Colab

The Colab notebook is intended for colleagues who do not normally use Python or a terminal.

### Complete allocation

Choose **Complete allocation** and upload researcher data, topic data, and student preferences. If any student uses `9998`, also upload the previous final assignments in the same upload window. The notebook separates carry-over students first, allocates current-year topics for everyone else, fills open daily-supervisor and promotor roles, and downloads `thesis_allocation_results.zip`. The ZIP includes both the full `final_assignments.xlsx` and the reduced `final_assignments_shareable.xlsx`.

### Reassignment

Choose **Reassign supervision** and upload the previous final assignments, researcher data, and topic data. Choose the role and whether to replace one student's assignment or all assignments held by a departing researcher. The notebook downloads `thesis_reassignment_results.zip`.

### Semantic versus lexical matching

The notebook offers:

- **Semantic matching (recommended)**, using the sentence-transformer backend and the default `BAAI/bge-base-en-v1.5` model;
- **Fast lexical matching**, using TF-IDF as an offline fallback.

A GPU runtime can accelerate embedding generation when CUDA is available to PyTorch and Sentence Transformers. The code does not force a CPU device, so the semantic model can use an available CUDA device automatically. Topic optimization, spreadsheet processing, and most other stages remain CPU work.

### Data handling in Colab

Colab runs on a Google-hosted virtual machine, so uploaded student and researcher data leave the user's computer.

The notebook does not mount Google Drive, does not display uploaded input tables, removes uploaded input files after processing, downloads outputs as one ZIP archive, and instructs the user to disconnect and delete the runtime when finished.

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
python -m thesis_allocation create-templates input
```

Run the complete pipeline:

```bash
python -m thesis_allocation run \
  --researchers input/researchers.xlsx \
  --topics input/topics.xlsx \
  --preferences input/student_preferences.xlsx \
  --output-directory output
```

When `9998` is used, add:

```text
--previous-final-assignments input/previous_final_assignments.xlsx
```

The first semantic run downloads the default `BAAI/bge-base-en-v1.5` model.

Useful options include:

```text
--skip-scrape
--backend tfidf
--model MODEL_NAME
--allow-partial
--allow-same-person
```

## Running individual stages

### Enrich researchers

```bash
python -m thesis_allocation scrape-researchers \
  --researchers input/researchers.xlsx \
  --output output/researchers_enriched.xlsx
```

### Allocate topics only

```bash
python -m thesis_allocation allocate-topics \
  --preferences input/student_preferences.xlsx \
  --topics input/topics.xlsx \
  --output output/topic_assignments.xlsx
```

The standalone `allocate-topics` stage does not process `9998`; previous-year carry-over belongs to the complete annual `run` workflow because it also requires the previous final assignments and current researcher data.

### Match supervisors only

```bash
python -m thesis_allocation match-supervisors \
  --assignments output/topic_assignments.xlsx \
  --topics input/topics.xlsx \
  --researchers output/researchers_enriched.xlsx \
  --output output/final_assignments.xlsx \
  --summary-output output/supervisor_summary.xlsx
```

## Important policy summary

- Ordinary current-year students provide three ranked topic-ID fields.
- Topic ID `9998` is reserved for previous-year carry-over and is used only as preference 1.
- A `9998` student's topic information comes from the previous final assignment, not the current topics file.
- Valid carry-over supervision is preserved only up to current maximum capacities; excess roles are reassigned.
- Topic ID `9999` is reserved for a student's own topic.
- Repeated ordinary topic IDs are accepted and do not cause input validation to fail.
- When the same topic appears more than once, its earliest occurrence has the lowest rank cost.
- Topic titles are display fields and are not used to resolve ordinary preferences.
- Offered-topic capacity is a hard constraint.
- Own topics and carry-over topics do not consume shared current-year offered-topic capacity.
- `assigned_topic_description` is retained in final assignments for semantic matching and future carry-over.
- Researcher role eligibility is determined by positive maximum capacity for that role.
- `assigned_language` is a hard supervision-eligibility constraint.
- Eligible current-year topic submitters receive supervision priority up to their available capacity.
- Researcher minimums are prioritized workload targets.
- Semantic similarity is optimized globally among feasible candidates.
- Daily supervisor and promotor must normally be different people.
- Existing valid assignments remain fixed unless explicitly targeted for reassignment or released by annual carry-over validation.
- Invalid topic IDs, conflicting fixed assignments, and infeasible complete allocations produce explicit errors.

## Determinism and reproducibility

Inputs and candidates are sorted by canonical email or topic ID before optimization.

Given the same inputs, model, configuration, and dependency versions, the optimization is designed to produce the same assignment.
