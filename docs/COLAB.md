# Google Colab guide

The Colab notebook provides a browser-only workflow for colleagues who do not
use Python or a terminal.

## Open the notebook

Open
[Thesis Allocation in Colab](https://colab.research.google.com/github/christofkoolen/computational-allocation-of-thesis-supervision/blob/main/notebooks/Thesis_Allocation_Colab.ipynb).

The notebook loads the allocation package from the public GitHub repository.
It does not require a GitHub account or access token.

## 1. Optional input templates

The first numbered section can generate the three blank input workbooks. Skip
this section when the files are already prepared.

The student-preference template contains three required preference columns for
three different exact thesis topic IDs. Topic ID `9999` is reserved for an own
topic, so it can appear at most once. When a student selects it,
`own_topic_description` must contain a short description that belongs only to
that `9999` preference.

An own topic does not share an offered-topic capacity. Therefore, if a student
ranks `9999` first, it is selected during topic allocation. If `9999` is ranked
second or third, it acts as an always-available fallback when a higher-ranked
offered topic cannot be assigned. Supervisor and promotor allocation happens
afterwards and remains subject to researcher eligibility, language, and capacity.

The researcher template contains `supervision_languages`, which records the
languages in which each researcher can supervise. The topic template has no
language column because topics themselves do not determine language eligibility.

In `researchers.xlsx`, `appointment` is only a descriptive label. Daily-supervisor
and promotor eligibility is controlled by the corresponding maximum-capacity
columns: a maximum above `0` makes the researcher eligible for that role, while
`0` makes them ineligible. The minimum columns are workload targets rather than
role categories.

## 2. Choose a workflow

Select the workflow before running the notebook.

### 2.a Workflow 1: thesis topic and supervision allocation

Choose **Complete allocation** for the normal annual allocation. Students must
provide their top three preferences as exact topic IDs rather than typed titles.
Review the complete-allocation options before running.

Topic preferences are matched by exact topic ID only. Typed titles, approximate
titles, and fuzzy matching are not used. A selected student supervision language
is checked against researcher `supervision_languages` during daily-supervisor and
promotor matching.

### 2.b Workflow 2: reassignment

Choose **Reassign supervision** to replace one student's daily supervisor or
promotor, or to replace assignments held by a departing researcher. Select the
role and scope first.

- For **One student**, enter the student's email in `student_email`.
- For **Everyone assigned to a departing supervisor**, enter the departing
  researcher's email in `departing_researcher_email`.

Only the email field corresponding to the selected scope is used. Assignments
outside the selected target remain fixed. Replacements remain subject to
researcher-level supervision-language compatibility.

## 3. Run the selected workflow

Select **Runtime → Run all** after choosing and configuring the workflow.

For **Complete allocation**, upload the researcher, topic, and student-preference
files together when the upload window appears. The notebook allocates thesis
topics first and then assigns daily supervisors and promotors. It downloads
`thesis_allocation_results.zip` when the workflow completes.

For **Reassign supervision**, upload the previous final assignments, researcher
file, and topic file together. The notebook downloads
`thesis_reassignment_results.zip` when finished.

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
