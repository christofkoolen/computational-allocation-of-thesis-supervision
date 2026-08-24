# Algorithm

## 1. Researcher enrichment

The enrichment stage retrieves visible body text from each missing profile and
publications page. Existing text is reused unless refresh mode is requested.
Scripts, styles, templates, and SVG content are excluded.

A failed request does not remove a researcher. The output records a status for
each retrieval and emits a warning, allowing the input to be corrected and run
again.

## 2. Topic allocation

Each student, offered topic, and capacity is represented in a flow network:

- the source has capacity 1 to each student;
- a student has one edge to each valid ranked preference;
- those edges cost 1, 2, or 3 according to rank;
- each offered topic has its declared capacity to the sink;
- a student's own-topic preference (`9999`) has a student-specific edge to the sink.

Language-incompatible offered-topic edges are omitted. A successive shortest
augmenting-path solver computes maximum flow at minimum total cost. Therefore a
complete result has the smallest possible sum of preference ranks across all
students.

Preferences resolve by exact topic ID only. Topic titles are display fields and
are never used to identify a preference. There is no fuzzy or approximate title
matching. Topic ID `9999` is reserved for a student's own topic and requires a
short `own_topic_description`.

## 3. Supervisor matching

Researcher text combines the profile description and publication list. For an
offered topic, topic text combines the official title and description. For an
own topic (`9999`), the student's `own_topic_description` is used directly as
the topic text.

The production backend creates normalized sentence-transformer embeddings and
uses cosine similarity.

Daily supervisors and promotors are optimized as separate global flow problems.
Existing assignments are fixed and counted against capacity. The flow network
then accounts for:

- hard maximum capacities;
- absolute priority for an eligible offered-topic submitter;
- prioritized minimum workload slots;
- semantic similarity cost;
- a mild incremental load-balancing cost;
- exclusion of the other role when distinct roles are required.

The objective is lexicographic. It first maximizes the number of assignments
given to their topic submitter. Minimum workload slots, semantic similarity,
and load balancing are considered only among solutions with that maximum.
Submitter priority remains subject to role eligibility, exclusions, the
distinct-role rule, and the researcher's maximum capacity. If one researcher
submitted more assigned topics than their available capacity, the secondary
costs determine which of those topics they supervise.

Own topics have no topic submitter, so they are matched on semantic fit,
workload constraints, and capacity.

The output records the raw semantic match score and whether an assignment came
from a carry-over, topic-submitter priority, or general semantic matching.

## 4. Reassignment

The reassignment command clears only the selected student's role or the
assignments held by a selected departing researcher. All other assignments
remain fixed and seed the current workload. The same capacity-constrained
matching algorithm then fills only those cleared rows.

The output includes a change log with the previous assignee, replacement,
semantic score, and assignment source.

## Determinism

Inputs and candidates are sorted by canonical email or topic ID before graph
construction. Given the same inputs, configuration, model, and dependency
versions, the optimization produces the same assignment.
