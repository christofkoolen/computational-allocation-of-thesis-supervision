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
exact thesis topic IDs. Topic ID `9999` is reserved for an own topic; when a
student selects it, `own_topic_description` must contain a short description.

The researcher template contains `supervision_languages`, which records the
languages in which each researcher can supervise. The topic template has no
language column because topics themselves do not determine language eligibility.

## 2. Thesis topic and supervisor allocation

Choose **Complete allocation** as the workflow, review the complete-allocation
options, and select **Runtime → Run all**.

Upload the researcher, topic, and student-preference files together when the
upload window appears. The notebook allocates thesis topics first and then
assigns daily supervisors and promotors. It downloads
`thesis_allocation_results.zip` when the workflow completes.

Topic preferences are matched by exact topic ID only. Typed titles, approximate
titles, and fuzzy matching are not used. A selected student supervision language
is checked against researcher `supervision_languages` during daily-supervisor and
promotor matching.

## 3. Reassign individual researchers

Choose **Reassign supervision** as the workflow. Select the role and whether the
target is one student or everyone assigned to a departing researcher, then
enter the target email address.

Select **Runtime → Run all** and upload the previous final assignments,
researcher file, and topic file together. The notebook downloads
`thesis_reassignment_results.zip` when finished. Assignments outside the
selected target remain fixed. Replacements remain subject to researcher-level
supervision-language compatibility.

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
