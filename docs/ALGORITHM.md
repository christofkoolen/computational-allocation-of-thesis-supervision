# Algorithm

## 1. Researcher enrichment

The enrichment stage retrieves visible body text from each missing profile and
publications page. Existing text is reused unless refresh mode is requested.
Scripts, styles, templates, and SVG content are excluded.

A failed request does not remove a researcher. The output records a status for
each retrieval and emits a warning, allowing the input to be corrected and run
again.

## 2. Branching student-preference group allocation

The recommended Forms workflow uses one mixed-integer optimization model for
topic, language, daily-supervisor, and promotor decisions. An individual is one
thesis group. A confirmed dual pair is also one thesis group, with two student
members.

Each ranked topic and each ordered language for that topic creates a possible
group option. Self-proposed and carry-over rows instead create fixed topic
options from their dedicated form fields. Selecting an offered topic consumes
one unit of its topic capacity regardless of whether the group contains one or
two students. Selecting supervisors consumes one thesis slot per role.

The objective is lexicographic:

1. retain feasible named carry-over roles;
2. minimize topic rank multiplied by group size;
3. minimize language rank multiplied by group size;
4. maximize eligible topic-submitter assignments;
5. minimize unmet researcher workload targets;
6. minimize semantic mismatch with a mild incremental load-balancing cost.

The optimizer fixes the optimum after each stage before solving the next stage.
Consequently, a later preference can never worsen an earlier priority. Topic
capacity, researcher maximum capacity, role eligibility, language compatibility,
and distinct daily-supervisor/promotor roles are hard constraints throughout.

Because topic and supervision choices are in the same model, a topic-language
option with insufficient supervision capacity is unavailable. The next language
listed for that topic can then be selected, or another ranked topic can be used.

Before optimization, named carry-over researcher emails are normalized and
matched exactly. An unmatched value is corrected automatically only when one
researcher is a unique high-confidence match at Damerau-Levenshtein distance one,
with a sufficient score and runner-up margin. This recognizes a single inserted,
deleted, substituted, or transposed character. When a match is ambiguous or too
weak, the requested role is reopened for automatic assignment instead of stopping
the run. The final administrative output clearly marks the daily supervisor or
thesis promotor as unknown and requiring manual review. Submitted values, closest
candidates, assigned replacements, and resolution diagnostics remain available.

## 3. Legacy canonical topic allocation

Each student, offered topic, and capacity is represented in a flow network:

- the source has capacity 1 to each student;
- a student has one edge to each valid ranked preference;
- those edges cost 1, 2, or 3 according to rank;
- each offered topic has its declared capacity to the sink;
- a student's own-topic preference (`9999`) has a student-specific edge to the sink.

Topics do not have language restrictions. A successive shortest augmenting-path
solver computes maximum flow at minimum total cost, so a complete result has the
smallest possible sum of preference ranks across all students. When the selected
preference contains one or more requested supervision languages, the first
listed language is carried forward as `assigned_language` for the supervision
stage.

Preferences resolve by exact topic ID only. Topic titles are display fields and
are never used to identify a preference. There is no fuzzy or approximate title
matching. Topic ID `9999` is reserved for a student's own topic and requires a
short `own_topic_description`.

## 4. Legacy canonical supervisor matching

Researcher text combines the profile description and publication list. For an
offered topic, topic text combines the official title and description. For an
own topic (`9999`), the student's `own_topic_description` is used directly as
the topic text.

The production backend creates normalized sentence-transformer embeddings and
uses cosine similarity.

Daily supervisors and promotors are optimized as separate global flow problems.
Existing assignments are fixed and counted against capacity. Each researcher
may declare `supervision_languages`; when `assigned_language` is populated for a
student, only researchers who support that language receive an assignment edge.
A blank researcher language field is treated as unrestricted for backwards
compatibility.

Language compatibility is therefore a hard eligibility filter, not part of the
semantic score. If a student has `assigned_language = French`, an English-only
researcher receives no edge for that student even if that researcher is the
strongest semantic match. A researcher who supports French remains eligible.
Only among language-compatible candidates does the optimization consider
submitter priority, capacity, minimum workload targets, semantic similarity, and
load balancing.

The flow network then accounts for:

- researcher-level supervision-language compatibility as a hard candidate filter;
- hard maximum capacities;
- absolute priority for an eligible offered-topic submitter;
- prioritized minimum workload slots;
- semantic similarity cost;
- a mild incremental load-balancing cost;
- exclusion of the other role when distinct roles are required.

The objective is lexicographic. It first maximizes the number of assignments
given to their topic submitter among language-compatible and otherwise eligible
researchers. Minimum workload slots, semantic similarity, and load balancing are
considered only among solutions with that maximum. Submitter priority remains
subject to language compatibility, role eligibility, exclusions, the
distinct-role rule, and the researcher's maximum capacity. If one researcher
submitted more assigned topics than their available capacity, the secondary
costs determine which of those topics they supervise.

The topic-allocation stage is not rerun when the supervision stage encounters a
language bottleneck. If a student has an assigned language but no eligible
researcher with compatible language and remaining capacity, a complete
supervision assignment is infeasible. Partial mode may leave that student
unassigned instead.

Own topics have no topic submitter, so they are matched on language eligibility,
semantic fit, workload constraints, and capacity.

Existing carry-over supervisors and promotors are validated against the selected
`assigned_language` before they are kept fixed.

The output records the raw semantic match score and whether an assignment came
from a carry-over, topic-submitter priority, or general semantic matching.

## 5. Reassignment

The reassignment command clears only the selected student's role or the
assignments held by a selected departing researcher. All other assignments
remain fixed and seed the current workload. The same capacity-constrained and
language-aware matching algorithm then fills only those cleared rows.

The output includes a change log with the previous assignee, replacement,
semantic score, and assignment source.

## Determinism

Inputs and candidates are sorted by canonical email or topic ID before graph
construction. Given the same inputs, configuration, model, and dependency
versions, the optimization produces the same assignment.
