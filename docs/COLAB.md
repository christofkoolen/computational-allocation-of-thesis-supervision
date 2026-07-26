# Google Colab guide

The Colab notebook provides a browser-only workflow for colleagues who do not
use Python or a terminal.

## Open the notebook

Open
[Thesis Allocation in Colab](https://colab.research.google.com/github/christofkoolen/computational-allocation-of-thesis-supervision/blob/main/notebooks/Thesis_Allocation_Colab.ipynb).

The notebook loads the allocation package from the public GitHub repository.
It does not require a GitHub account or access token.

## Complete allocation

1. Leave **Complete allocation** selected.
2. Choose semantic matching for normal use or fast lexical matching for a
   quicker test.
3. Enable researcher-profile retrieval only when the uploaded researcher file
   contains profile URLs that should be retrieved.
4. Select **Runtime → Run all**.
5. Upload the researcher, topic, and student-preference files together when the
   upload window appears.
6. Wait for `thesis_allocation_results.zip` to download.

The notebook identifies the three inputs from their columns, so their filenames
do not need to match the template filenames.

## Reassignment

1. Select **Reassign supervision**.
2. Select the role and whether the target is one student or everyone assigned
   to a departing supervisor.
3. Enter the target email address.
4. Select **Runtime → Run all**.
5. Upload the previous final assignments, researcher file, and topic file
   together.
6. Wait for `thesis_reassignment_results.zip` to download.

Assignments outside the selected target remain fixed.

## Input templates

The final notebook cell can generate the three blank input workbooks. Set
`download_blank_templates` to `True` and run that cell.

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
