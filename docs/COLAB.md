# Google Colab guide

The Colab notebook provides a browser-only workflow for colleagues who do not
use Python or a terminal.

## Open the notebook

Open
[Thesis Allocation in Colab](https://colab.research.google.com/github/christofkoolen/computational-allocation-of-thesis-supervision/blob/main/notebooks/Thesis_Allocation_Colab.ipynb).

The notebook loads the allocation package from the public GitHub repository.
It does not require a GitHub account or access token.

## 1. Optional input templates

The first numbered section can generate the three blank current-year input
workbooks. Skip this section when the files are already prepared.

The student-preference template contains three preference columns for exact
thesis topic IDs. For normal current-year allocation, students provide all three.
The IDs do not have to be different. Repeated preferences are accepted and do
not stop the workflow. If the same topic appears more than once, its earliest
occurrence has the lowest preference cost. A repeated choice does not create
extra topic capacity or an additional fallback option.

Topic ID `9998` is reserved for previous-year carry-over. If `9998` appears in
**any** of the three preference fields, the whole student row is treated as
carry-over and the other topic choices on that row are ignored for current-year
topic allocation. If a form requires all three preference fields to contain a
value, `9998 / 9998 / 9998` is valid and represents one carry-over student.
When the previous `final_assignments` file is available, upload it as an optional
fourth file, normally named `previous_final_assignments.xlsx`.

If no previous final-assignment file is available, the Complete allocation run
still completes. The unresolved `9998` student stays in the outputs and is marked
`CARRY-OVER STUDENT - MANUAL REVIEW NEEDED`; automatic topic inference and
supervisor/promotor matching are skipped for that row.

Topic ID `9999` is reserved for an own topic on a row that does not contain
`9998`. When a non-carry-over student selects it, `own_topic_description` must
contain a short description of that own topic. Repeated `9999` preferences are
accepted as well; the earliest occurrence has the lowest preference cost. If a
row contains both `9998` and `9999`, `9998` takes precedence and the row is
handled as carry-over.

An own topic does not share an offered-topic capacity. Therefore, if a
non-carry-over student ranks `9999` first, it is selected during topic allocation.
Supervisor and promotor allocation happens afterwards and remains subject to
researcher eligibility, language, and capacity.

The researcher template contains `supervision_languages`, which records the
languages in which each researcher can supervise. The topic template has no
language column because topics themselves do not determine language eligibility.

In `researchers.xlsx`, `appointment_type`, `appointment_percentage`, `comment`,
and `timestamp` are descriptive only. Daily-supervisor and promotor eligibility
is controlled by the corresponding maximum-capacity columns: a maximum above
`0` makes the researcher eligible for that role, while `0` makes them ineligible.
The minimum columns are workload targets rather than role categories.

## 2. Choose a workflow

Select the workflow before running the notebook.

### 2.a Workflow 1: thesis topic and supervision allocation

Choose **Complete allocation** for the normal annual allocation. Students provide
their ranked preferences as exact topic IDs rather than typed titles. Review the
complete-allocation options before running.

For ordinary students, repeated topic IDs are accepted. For example, `A, A, B`
is valid input. If `A` can be assigned, its first occurrence is the effective
preference because it has the lowest rank cost. If `A` cannot be assigned because
its topic capacity is exhausted, the repeated `A` does not provide another
alternative and `B` remains a third-choice fallback.

For carry-over, `9998` is an instruction rather than a ranked fallback. For
example:

```text
preference_1 = A
preference_2 = 9998
preference_3 = B
```

means “continue my previous allocation,” not “try A first, then carry over.” The
student is separated before the current-year topic optimizer runs. The original
submitted preference values remain in the generated assignment files for
auditing, but the ordinary topic choices on that row are not used for allocation.

For a `9998` student with a matching previous final-assignment row, the notebook
carries forward the previous topic, topic description, assigned language, daily
supervisor, and promotor. That student's topic is not resolved against the
current `topics.xlsx`, even if the old topic ID has been reused for a different
current-year topic.

If no previous final-assignment file is uploaded, the `9998` row is retained for
manual review instead. The visible unresolved assignment fields are marked:

```text
CARRY-OVER STUDENT - MANUAL REVIEW NEEDED
```

Researcher email fields remain blank rather than containing placeholder email
values. The student is excluded from automatic supervisor/promotor matching, so
the program does not guess a new assignment from incomplete carry-over data.
Other students continue normally.

If a previous final-assignment file is uploaded but does not contain the email of
a `9998` student, the run still stops with a validation error because the supplied
continuity file is inconsistent for that student.

Previous supervision is kept only while the researcher is still listed and
eligible, supports the carried language, and remains within the current maximum
for that role. If carry-over demand exceeds a researcher's current maximum, the
excess student's role is cleared and reassigned normally. The carried topic stays
fixed.

A repeat student who wants a new topic must submit ordinary current-year topic
IDs with no `9998` in any of the three fields. Their presence in the previous
assignment file does not trigger carry-over.

Topic preferences are matched by exact topic ID only. Typed titles, approximate
titles, and fuzzy matching are not used. The selected supervision language is
carried forward as `assigned_language` and is a **hard eligibility constraint**
during daily-supervisor and promotor matching.

For example, if a student receives a topic with `assigned_language = French`, an
English-only researcher is excluded for that student even if their research
profile is an excellent semantic match. A researcher who supports French remains
eligible. Only after incompatible researchers are removed does the optimizer
consider topic-submitter priority, maximum capacities, minimum workload targets,
semantic fit, and load balancing. The topic assignment itself is not reconsidered
because the supervision stage later encounters a language constraint.

### 2.b Workflow 2: reassignment

Choose **Reassign supervision** to replace one student's daily supervisor or
promotor, or to replace assignments held by a departing researcher. Select the
role and scope first.

- For **One student**, enter the student's email in `student_email`.
- For **Everyone assigned to a departing supervisor**, enter the departing
  researcher's email in `departing_researcher_email`.

Only the email field corresponding to the selected scope is used. Assignments
outside the selected target remain fixed. Replacements remain subject to the
same hard researcher-level supervision-language compatibility rule.

For resolved carried `9998` assignments, reassignment uses the topic information
stored in the final-assignment row. New runs include `assigned_topic_description`,
so the previous final file contains the semantic topic text needed for later
replacement matching. Older files without that field fall back to the stored
`assigned_topic` title.

## 3. Run the selected workflow

Select **Runtime → Run all** after choosing and configuring the workflow.

For **Complete allocation**, upload the researcher, topic, and student-preference
files together when the upload window appears. If one or more students have
`9998` in any preference field and the previous final assignments are available,
upload that file in the same window as an optional fourth file. The notebook
separates carry-over students first, allocates current-year topics for everyone
else, then assigns any open daily-supervisor and promotor roles. If the previous
file is missing, unresolved `9998` rows are retained for manual review instead
of stopping the run. The notebook downloads `thesis_allocation_results.zip` when
the workflow completes.

`run_report.json` includes `manual_review_students` in addition to the carry-over
count, and the notebook prints the corresponding warning messages.

For **Reassign supervision**, upload the previous final assignments, researcher
file, and topic file together. The notebook downloads
`thesis_reassignment_results.zip` when finished.

## Semantic matching and GPU use

Production semantic matching uses the default `BAAI/bge-base-en-v1.5` Sentence
Transformers model. The model compares the assigned topic text with researcher
profile and publication text.

If a Colab GPU runtime is selected and CUDA is available to PyTorch, Sentence
Transformers can use the GPU automatically because the allocation code does not
force a CPU device. The embedding stage can therefore run faster on a GPU.
Spreadsheet processing, scraping, and the allocation flow algorithms remain
largely CPU work.

## Data handling

Colab executes the notebook in a Google-hosted virtual machine. Uploaded
student and researcher files therefore leave the user's computer.

The notebook:

- does not mount Google Drive;
- does not display input tables;
- removes uploaded input files after processing;
- downloads outputs as one ZIP;
- instructs the user to delete the runtime when finished.

Google documents that Colab virtual machines are private to the user's account
and are deleted after being idle, but institutional approval is still required
before processing real student data:
https://research.google.com/colaboratory/faq.html

## Maintenance

The notebook is generated from `scripts/build_colab_notebook.py`. After editing
the workflow, regenerate and verify it:

```bash
python scripts/build_colab_notebook.py
python scripts/build_colab_notebook.py --check
```

The committed notebook contains no outputs or uploaded data.
