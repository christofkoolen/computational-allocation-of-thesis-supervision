# Computational allocation of thesis supervision

This repository provides one reproducible pipeline for:

1. enriching researcher records with profile and publication text;
2. assigning students to their ranked thesis topics at the lowest total preference cost;
3. semantically matching daily supervisors and promotors under workload constraints;
4. reassigning supervision after a departure or an ad hoc change.

The year-specific scripts and machine-specific paths have been replaced by a
guided browser interface, an installable Python package, a command-line
interface, validated input contracts, and automated tests.

## Recommended: browser interface for colleagues

The local Streamlit app provides file-upload forms, guided options, previews,
and ZIP downloads. It opens in the default web browser and does not require
colleagues to type commands after setup.

On Windows:

1. Download and extract the repository ZIP.
2. Install Python 3.10 or newer if it is not already installed.
3. Double-click `INSTALL_APP.bat` once.
4. Double-click `START_APP.bat` whenever the app is needed.
5. Keep the small command window open while using the browser app.

The app has three screens:

- **Run complete allocation** accepts the researcher, topic, and student files
  and returns every result as one ZIP download.
- **Reassign supervision** replaces one student's role or every assignment
  held by a departing supervisor.
- **Input templates** downloads the three blank Excel workbooks.

The local launcher binds the server to `127.0.0.1`, so uploaded student data is
processed on the same computer. Enabling researcher-profile retrieval sends
requests to the profile URLs in the uploaded researcher file. See
[the browser-app guide](docs/WEB_APP.md) for setup and deployment choices.

The first semantic run downloads the default
`sentence-transformers/all-MiniLM-L6-v2` model. Existing profile text is reused.
Missing profile or publication text can be retrieved when a corresponding URL
is available.

## Outputs

The browser interface returns a ZIP containing:

| File | Purpose |
| --- | --- |
| `researchers_enriched.xlsx` | Researcher input plus retrieved text and per-row scrape status |
| `topic_assignments.xlsx` | Ranked-topic allocation, selected language, rank, and cost |
| `final_assignments.xlsx` | Topic, daily supervisor, promotor, match scores, and assignment source |
| `supervisor_summary.xlsx` | Minimum, maximum, actual load, and capacity flags per researcher |
| `run_report.json` | Machine-readable totals, output paths, and warnings |

The app stops with an actionable message before producing misleading downstream
results when an input is invalid or a complete assignment is impossible.
Deliberate partial runs remain available in the options.

## Command-line use

Python 3.10 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[semantic]"
thesis-allocation create-templates input
```

Fill the three generated workbooks and run:

```bash
thesis-allocation run \
  --researchers input/researchers.xlsx \
  --topics input/topics.xlsx \
  --preferences input/student_preferences.xlsx \
  --output-directory output
```

Add `--skip-scrape` to prohibit network retrieval.

## Individual stages

Run only the researcher enrichment:

```bash
thesis-allocation scrape-researchers \
  --researchers input/researchers.xlsx \
  --output output/researchers_enriched.xlsx
```

Run the exact topic optimizer:

```bash
thesis-allocation allocate-topics \
  --preferences input/student_preferences.xlsx \
  --topics input/topics.xlsx \
  --output output/topic_assignments.xlsx
```

Run supervisor matching:

```bash
thesis-allocation match-supervisors \
  --assignments output/topic_assignments.xlsx \
  --topics input/topics.xlsx \
  --researchers output/researchers_enriched.xlsx \
  --output output/final_assignments.xlsx \
  --summary-output output/supervisor_summary.xlsx
```

For an offline smoke test, add `--backend tfidf`. This is a lexical fallback.
Production semantic matching uses the default sentence-transformers backend.

## Reassignment

Reassign every daily-supervisor assignment held by someone who leaves:

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

Reassign one student's promotor:

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

Existing assignments outside the selected target remain fixed. The previous
assignee is excluded from an ad hoc replacement, and a departing researcher is
excluded from every replacement generated in that run.

## Policy behavior

- Topic ranks cost exactly 1, 2, and 3.
- Topic capacities are hard constraints.
- Language compatibility is enforced while optimizing, rather than checked after allocation.
- Existing supervisor assignments are treated as fixed carry-overs.
- A researcher is eligible for a role when that role's maximum capacity is greater than zero.
- Minimum supervision targets are prioritized before optional capacity.
- Semantic similarity is optimized globally with a mild load-balancing cost.
- A topic submitter receives a configurable preference when eligible.
- Daily supervisor and promotor must be different people unless `--allow-same-person` is supplied.
- Invalid, ambiguous, and low-confidence topic references stop the run with suggestions.

See [the input contract](docs/INPUT_FORMAT.md),
[the algorithm description](docs/ALGORITHM.md), and
[the browser-app guide](docs/WEB_APP.md) for details.

## Development

The base test suite does not download an embedding model.

```bash
python -m pip install -e ".[web]"
python -m compileall -q src tests
python -m unittest discover -s tests -v
```
