# Google Colab guide

The Colab notebook provides a browser-only workflow for colleagues who do not
use Python or a terminal.

## Open the notebook

Open
[Thesis Allocation in Colab](https://colab.research.google.com/github/christofkoolen/computational-allocation-of-thesis-supervision/blob/main/notebooks/Thesis_Allocation_Colab.ipynb).

The notebook loads the allocation package from the public GitHub repository. It
does not require a GitHub account or access token.

## The three input files

Use these filenames consistently:

1. `researchers.xlsx`
2. `topics.xlsx`
3. `student_preferences.xlsx`

The notebook recognizes files by their columns, but using these names keeps the
annual workflow predictable. The first notebook section can download blank
versions of all three files.

`student_preferences.xlsx` contains the student's identity, thesis type, and
allocation route. Depending on the route, it contains ranked topic and language
preferences, a self-proposed topic, or carry-over details. A dual-thesis row also
contains the partner's identity and confirmation.

Languages are ordered alternatives. If the first listed language has
insufficient supervision capacity, the optimizer can use the next language for
that topic. If no submitted language is feasible, it considers the student's
other ranked topics.

A dual pair consumes one offered-topic place, one daily-supervisor slot, and one
promotor slot. Both students receive the same assignment and appear separately
in the final student-level output.

## Complete allocation

1. Open the notebook.
2. Choose **Complete allocation**.
3. Select the matching and validation options.
4. Run the notebook.
5. Upload the three input files together.
6. Download `thesis_allocation_results.zip`.

The ZIP contains:

- `researchers_enriched.xlsx`
- `topic_assignments.xlsx`
- `thesis_group_assignments.xlsx`
- `final_assignments.xlsx`
- `final_assignments_shareable.xlsx`
- `supervisor_summary.xlsx`
- `run_report.json`

`thesis_group_assignments.xlsx` contains one row per thesis and is the correct
file for reviewing capacity use. `final_assignments.xlsx` contains one row per
student, so each dual thesis appears twice with the same `thesis_group_id`.

## Reassign supervision

Choose **Reassign supervision** to replace one student's daily supervisor or
promotor, or to replace every assignment held by a departing researcher.

Upload:

1. the previous `final_assignments.xlsx`
2. `researchers.xlsx`
3. `topics.xlsx`

For **One student**, enter `student_email`. For **Everyone assigned to a
departing supervisor**, enter `departing_researcher_email`. Assignments outside
the selected scope remain fixed.

The notebook downloads `thesis_reassignment_results.zip`, containing the updated
assignments, workload summary, and reassignment log.

## Matching and capacity rules

- Topic IDs are matched exactly.
- Topic capacity is a hard maximum.
- Researcher maximums determine role eligibility and capacity.
- Researcher minimums are workload targets.
- Student language order is considered after topic rank.
- Daily supervisors and promotors must be different unless the corresponding
  option is enabled.
- Eligible topic submitters receive supervision priority up to capacity.
- Carry-over supervisor emails are recovered from a small typo only when one
  researcher is a uniquely strong match. Ambiguous matches stop for correction.

## Semantic matching and privacy

Production matching uses `BAAI/bge-base-en-v1.5`. The lexical option is faster
and useful for testing, but it is less effective at matching related concepts
that use different wording.

Uploaded files are processed on a temporary Google-hosted virtual machine. They
are not mounted to Google Drive or printed as notebook tables. When finished,
select **Runtime > Disconnect and delete runtime**.
