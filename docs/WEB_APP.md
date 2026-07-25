# Browser app

The Streamlit interface is intended for colleagues who are comfortable working
with Excel but do not use Python or a terminal.

## Windows setup

Python 3.10 or newer must be installed once. During the Python installer, select
the option that adds Python to `PATH`.

After downloading and extracting this repository:

1. Double-click `INSTALL_APP.bat`.
2. Wait for the installation to finish. The semantic model dependencies can
   take several minutes to install.
3. Double-click `START_APP.bat`.
4. The app opens in the default browser.
5. Keep the command window open until work in the app is finished.

`START_APP.bat` automatically starts the installation script when the private
application environment does not exist yet.

## Complete allocation

Open **Run complete allocation** and upload:

1. `researchers.xlsx`;
2. `topics.xlsx`;
3. `student_preferences.xlsx`.

The options control profile retrieval, duplicate submissions, partial results,
distinct supervision roles, and the similarity backend. Semantic matching is
the production setting. TF-IDF is an offline lexical fallback.

After a successful run, download `thesis_allocation_results.zip`. It contains:

- `researchers_enriched.xlsx`;
- `topic_assignments.xlsx`;
- `final_assignments.xlsx`;
- `supervisor_summary.xlsx`;
- `run_report.json`.

## Reassignment

Open **Reassign supervision** and upload the previous final assignments,
researcher file, and topic file. Select a role and then select:

- one student for an ad hoc replacement; or
- one departing supervisor to replace every affected assignment.

All unrelated assignments remain fixed. The download contains updated
assignments, an updated workload summary, and an audit log.

## Data handling

The Windows launcher binds Streamlit to `127.0.0.1`. The Python server and
browser therefore run on the same computer, and uploaded files are processed in
that local process.

Two optional actions use external network access:

- the first semantic run downloads the embedding model;
- researcher enrichment retrieves the profile and publication URLs supplied in
  the researcher workbook.

The Streamlit architecture documentation explains that uploaded files are
processed by the machine hosting the Python server:
https://docs.streamlit.io/develop/concepts/architecture/architecture

## Hosted deployment

The root `streamlit_app.py` file is a standard deployment entry point. The app
can be hosted on Streamlit Community Cloud or an institutional server.

A hosted app processes uploaded student files on the host rather than the
colleague's computer. Do not deploy it externally until institutional
requirements for student data, access control, retention, and model downloads
have been reviewed. Streamlit's deployment documentation is available at:
https://docs.streamlit.io/deploy/streamlit-community-cloud

