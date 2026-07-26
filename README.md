# Computational allocation of thesis supervision

This repository provides one reproducible pipeline for:

1. enriching researcher records with profile and publication text;
2. assigning students to their ranked thesis topics at the lowest total preference cost;
3. semantically matching daily supervisors and promotors under workload constraints;
4. reassigning supervision after a departure or an ad hoc change.

The year-specific scripts and machine-specific paths have been replaced by an
installable Python package, a Google Colab workflow, a command-line interface,
validated input contracts, and automated tests.

## Recommended: Google Colab

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/christofkoolen/computational-allocation-of-thesis-supervision/blob/main/notebooks/Thesis_Allocation_Colab.ipynb)

The Colab notebook is intended for colleagues who do not use Python or a
terminal. It supports the complete allocation and targeted reassignment
workflows. To use it:

1. Open the notebook with the badge above.
2. Review the plain-language options.
3. Select **Runtime → Run all**.
4. Upload the three requested Excel or CSV files together.
5. Download the generated results ZIP.

No local installation or GitHub authentication is required. Colab processes
uploaded files on a Google-hosted virtual machine. Use real student data only
when this arrangement has been approved by the institution. See
[the Colab guide](docs/COLAB.md) for complete instructions and data-handling
notes.

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

The first semantic run downloads the default
`sentence-transformers/all-MiniLM-L6-v2` model. Existing profile text is reused.
Missing profile or publication text is retrieved when a corresponding URL is
available. Add `--skip-scrape` to prohibit network retrieval.

## Outputs

The complete pipeline produces:

| File | Purpose |
| --- | --- |
| `researchers_enriched.xlsx` | Researcher input plus retrieved text and per-row scrape status |
| `topic_assignments.xlsx` | Ranked-topic allocation, selected language, rank, and cost |
| `final_assignments.xlsx` | Topic, daily supervisor, promotor, match scores, and assignment source |
| `supervisor_summary.xlsx` | Minimum, maximum, actual load, and capacity flags per researcher |
| `run_report.json` | Machine-readable totals, output paths, and warnings |

The pipeline stops with an actionable message before producing misleading
downstream results when an input is invalid or a complete assignment is
impossible. Deliberate partial runs remain available.

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
[the Colab guide](docs/COLAB.md) for details.

## Development

The base test suite does not download an embedding model.

```bash
python -m pip install -e .
python -m compileall -q src tests
python -m unittest discover -s tests -v
python scripts/build_colab_notebook.py --check
```
