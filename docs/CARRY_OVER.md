# Previous-year thesis carry-over

The complete annual allocation workflow supports an optional previous-year
carry-over mechanism for continuing students.

## When to use topic ID `9998`

Topic ID `9998` is reserved for a student who wants to continue the thesis
allocation from the previous academic year.

The student enters:

```text
preference_1 = 9998
```

For a `9998` submission, `preference_2` and `preference_3` may be left blank.
Topic ID `9998` may not be used as preference 2 or preference 3, and it must not
appear in `topics.xlsx`.

A repeat student who does not want to carry over the previous allocation simply
submits ordinary topic IDs. The student's presence in the previous assignment
file does not trigger carry-over by itself.

## Optional fourth input file

A normal complete allocation uses:

- `researchers.xlsx`
- `topics.xlsx`
- `student_preferences.xlsx`

When at least one student uses `9998`, also provide the previous complete
assignment file. The recommended filename is:

```text
previous_final_assignments.xlsx
```

The Colab notebook identifies the file by its assignment columns, so the exact
filename is recommended rather than mandatory.

The previous assignment is matched to the current student by normalized student
email. If a student selects `9998` but their email is absent from the previous
assignment file, the run stops with a validation error.

## What is carried forward

For a valid `9998` student, the previous record supplies:

- `assigned_topic_id`
- `assigned_topic`
- `assigned_topic_description`
- `assigned_language`
- `own_topic_description`, when applicable
- `daily_supervisor`
- `daily_supervisor_email`
- `promotor`
- `promotor_email`

New allocation runs write `assigned_topic_description` into both the topic and
final assignment outputs. This makes `final_assignments.xlsx` self-contained for
future carry-over and for semantic supervisor reassignment.

Older previous-final-assignment files that do not yet contain
`assigned_topic_description` remain usable. In that case, the previous
`assigned_topic` title is used as the semantic matching text fallback.

The carry-over student is separated before the current-year topic optimizer is
run. Their previous final-assignment row is authoritative for the thesis topic.
For a `9998` student, the supervisor-matching stage does not resolve that
student's `assigned_topic_id` against the current `topics.xlsx` file. This is
true even if the same topic ID has been reused for a different current-year
topic.

The carried topic therefore does not consume capacity from this year's offered
topics and does not need to appear in the current `topics.xlsx` file.

The preference cost reported for the annual optimizer concerns the students who
participate in the current-year ranked-topic allocation. A `9998` carry-over does
not add a rank cost.

## Previous daily supervisor and promotor

The workflow attempts to keep the previous daily supervisor and promotor fixed.
Each previous researcher is checked against the current `researchers` file.

A previous role can be kept when the researcher:

1. can still be resolved in the current researcher data;
2. has a positive current maximum capacity for that role; and
3. supports the carried `assigned_language` when a language is specified.

Kept carry-over assignments count immediately against the researcher's current-
year maximum capacity. New supervisor assignments are optimized around this
fixed workload.

For example, if a daily supervisor has a current maximum of `5` and already has
two valid `9998` carry-over students, the optimizer has three additional daily-
supervisor slots available for that researcher.

If the previous researcher is absent from the current researcher file, no
longer eligible for the role, or incompatible with the carried language, only
that role is cleared. The topic and any other still-valid role remain fixed, and
the open role is reassigned by the normal supervisor-matching algorithm.

For example:

```text
previous topic             -> carried over
previous assigned language -> carried over
previous daily supervisor  -> departed -> reassigned
previous promotor          -> still valid -> carried over
```

### When carry-over demand exceeds the current maximum

Current maximum capacities remain hard limits. Carry-over assignments do not
allow a researcher to exceed the current maximum.

If more `9998` students carry the same researcher than that researcher can
currently supervise, carry-over roles are retained up to the current maximum in
student input order. The excess role or roles are cleared and sent through the
normal matching algorithm.

For example:

```text
daily supervisor current maximum = 2

student 1 -> previous supervisor retained
student 2 -> previous supervisor retained
student 3 -> previous supervisor cleared and reassigned
```

The third student's topic and assigned language remain carried over; only the
overflowing supervision role is rematched.

## Relationship to topic ID `9999`

The reserved IDs have different meanings:

| Topic ID | Meaning |
| --- | --- |
| `9998` | Continue the previous complete thesis allocation |
| `9999` | Student-specific new own topic |
| other ID | Current-year offered topic preference |

A `9998` student uses the previous final assignment as the authoritative topic
record. A `9999` student creates a new own topic and must provide
`own_topic_description`.

## Google Colab flow

In **Complete allocation**:

1. upload `researchers`, `topics`, and `student_preferences`;
2. if any student uses `9998`, upload `previous_final_assignments` in the same
   upload window;
3. the notebook separates carry-over students first;
4. their topic information is read from `previous_final_assignments`, not from
   the current `topics.xlsx`;
5. remaining students enter the current-year topic optimizer;
6. both groups are combined;
7. valid previous supervision remains fixed up to current maximum capacities;
8. departed, ineligible, language-incompatible, or excess carry-over roles are
   reassigned normally;
9. the final results ZIP includes the combined current-year allocation.

The separate **Reassign supervision** workflow can subsequently reassign a role
for a carried student even when the carried topic is absent from this year's
`topics.xlsx` or when its old topic ID has been reused for a different topic.
