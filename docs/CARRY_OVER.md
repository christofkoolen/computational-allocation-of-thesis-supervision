# Previous-year thesis carry-over

The complete annual allocation workflow supports an optional previous-year
carry-over mechanism for continuing students.

## When to use topic ID `9998`

Topic ID `9998` is reserved for a student who wants to continue the thesis
allocation from the previous academic year.

A student is treated as carry-over when `9998` appears in **any** of the three
ranked topic fields:

```text
preference_1 = 9998
```

or, for example:

```text
preference_1 = current-topic-A
preference_2 = 9998
preference_3 = current-topic-B
```

The position of `9998` does not give it a rank. It is an instruction that
overrides the current-year ranked-topic choices on that row. Once `9998` appears
in any preference field, the whole student row is handled as carry-over and the
other submitted topic choices are ignored for current-year topic allocation.
The submitted preference fields themselves remain unchanged in the generated
assignment files for auditability.

If a form requires all three topic fields to contain a value, the student may
enter:

```text
preference_1 = 9998
preference_2 = 9998
preference_3 = 9998
```

This is valid and represents **one** carry-over student, not three carry-over
requests.

Topic ID `9998` must not appear in `topics.xlsx`.

A repeat student who does not want to carry over the previous allocation must
submit ordinary topic IDs without `9998` in any of the three preference fields.
The student's presence in the previous assignment file does not trigger
carry-over by itself.

## Optional fourth input file

A normal complete allocation uses:

- `researchers.xlsx`
- `topics.xlsx`
- `student_preferences.xlsx`

When at least one student uses `9998`, the preferred input is also the previous
complete assignment file. The recommended filename is:

```text
previous_final_assignments.xlsx
```

The Colab notebook identifies the file by its assignment columns, so the exact
filename is recommended rather than mandatory.

The previous assignment is matched to the current student by normalized student
email. When the previous file is supplied but a `9998` student's email is absent
from it, the run stops with a validation error because the supplied continuity
file is internally incomplete for that student.

### If no previous final-assignment file is available

The complete run no longer stops merely because a `9998` student exists without
`previous_final_assignments`.

Instead, the student remains in the generated outputs and is clearly marked for
manual follow-up. Human-readable unresolved assignment fields contain:

```text
CARRY-OVER STUDENT - MANUAL REVIEW NEEDED
```

The output keeps the student's submitted name and email, and `assigned_topic_id`
is shown as `9998`. Researcher identifier fields such as
`daily_supervisor_email` and `promotor_email` remain blank rather than inventing
invalid email values.

Automatic topic inference and automatic daily-supervisor/promotor matching are
skipped for that unresolved carry-over row. Other students continue through the
normal allocation workflow.

The corresponding assignment-source values identify the row explicitly:

```text
topic_assignment_source = carry_over_manual_review
daily_supervisor_assignment_source = manual_review
promotor_assignment_source = manual_review
```

`run_report.json` also contains `manual_review_students` and emits a warning with
the affected student email addresses.

## What is carried forward when the previous file is available

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
For a resolved `9998` student, the supervisor-matching stage does not resolve
that student's `assigned_topic_id` against the current `topics.xlsx` file. This
is true even if the same topic ID has been reused for a different current-year
topic.

The carried topic therefore does not consume capacity from this year's offered
topics and does not need to appear in the current `topics.xlsx` file.

The preference cost reported for the annual optimizer concerns the students who
participate in the current-year ranked-topic allocation. A `9998` carry-over does
not add a rank cost, regardless of which preference field contains `9998`.

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

If a row contains both `9998` and `9999`, `9998` wins: the row is treated as
carry-over and the own-topic instruction is ignored for the current annual run.

A resolved `9998` student uses the previous final assignment as the authoritative
topic record. If that file is not available, the row is retained for manual
review rather than being automatically inferred. A `9999` student creates a new
own topic and must provide `own_topic_description` only when the row does not
contain `9998`.

## Google Colab flow

In **Complete allocation**:

1. upload `researchers`, `topics`, and `student_preferences`;
2. if available, also upload `previous_final_assignments` when students use
   `9998` in any preference field;
3. the notebook separates carry-over students first;
4. when a matching previous row exists, its topic information is used directly
   rather than the current `topics.xlsx`;
5. when no previous file was uploaded, unresolved `9998` rows are retained and
   marked `CARRY-OVER STUDENT - MANUAL REVIEW NEEDED`;
6. remaining students enter the current-year topic optimizer;
7. resolved carry-over and current-year students are combined;
8. valid previous supervision remains fixed up to current maximum capacities;
9. departed, ineligible, language-incompatible, or excess resolved carry-over
   roles are reassigned normally;
10. unresolved manual-review rows are skipped by automatic supervisor matching;
11. the final results ZIP includes all rows, including those requiring manual
    review.

The separate **Reassign supervision** workflow can subsequently reassign a role
for a resolved carried student even when the carried topic is absent from this
year's `topics.xlsx` or when its old topic ID has been reused for a different
topic.
