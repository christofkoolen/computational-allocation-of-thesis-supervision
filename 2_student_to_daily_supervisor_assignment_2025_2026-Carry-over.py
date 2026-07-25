# -*- coding: utf-8 -*-
"""
Created on Tue Jul  1 19:29:31 2025

End-to-end script that:
- Normalizes submitted topics to a row-per-topic table
- Checks who submitted topics
- Verifies global capacity vs. students
- Assigns daily supervisors in two stages:
    (0) Preassign (carry-overs): lock any existing students_df['daily_supervisor']
        and count these against capacity.
    (1) Prefer topic submitter with fairness cap (per-researcher step-1 cap)
    (2) Semantic match for remaining students:
        (2A) Fill unmet minima first
        (2B) General load-balanced matching (respecting max)
- Exports assignment and supervision summary

NOTE: This version intentionally does NOT rely on any 'supervision_languages'
column in researchers_df.
"""

# =============================================================================
# DEPENDENCIES
# =============================================================================
import os
import pandas as pd
from collections import defaultdict
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# =============================================================================
# FILES & LOAD
# =============================================================================

# Directory where your Excel files are stored
directory = r'C:\Users\chris\My Drive (christofkoolen@gmail.com)\PostDoc\Admin\LLM Thesis Allocation\Allocation 2025-2026\Files'
# directory = r'C:\Users\u0124399\My Drive\PostDoc\Admin\LLM Thesis Allocation\Files'

# Define full paths to the Excel files
students_file = os.path.join(directory, "thesis_topics_assigned_to_students_updated.xlsx")
researchers_file = os.path.join(directory, "researcher_profiles_2025_2026_updated.xlsx")
thesis_topics_file = os.path.join(directory, "submitted_thesis_topics.xlsx")

# Load the Excel files into DataFrames
students_df = pd.read_excel(students_file)
researchers_df = pd.read_excel(researchers_file)
thesis_topics_df = pd.read_excel(thesis_topics_file)

# Optional: preview
print("Students file loaded:", students_df.shape)
print("Researchers file loaded:", researchers_df.shape)
print("Thesis topics file loaded:", thesis_topics_df.shape)

# =============================================================================
# PART 1 - CLEAN-UP: Normalize submitted topics to row-per-topic
# =============================================================================

# Build normalized topic records
records = []
for _, row in thesis_topics_df.iterrows():
    for i in range(1, 21):  # topics 1..20
        topic_col = f'Proposed thesis topic no. {i}'
        subject_col = f'Subject fields relevant to topic no. {i}'
        if topic_col in thesis_topics_df.columns:
            topic = row.get(topic_col)
            subject = row.get(subject_col)
            if pd.notna(topic) and str(topic).strip():
                records.append({
                    'first_name': row.get('First name'),
                    'family_name': row.get('Family name'),
                    'email': row.get('E-mail address'),
                    'topic_number': i,
                    'proposed_thesis_topic': topic,
                    'subject_field': subject
                })

normalized_topics_df = pd.DataFrame(records)
print("Normalized topics shape:", normalized_topics_df.shape)

# Canonicalize by email (no fuzzy matching)
def _clean_email(x):
    return str(x).strip().lower() if pd.notna(x) else None

researchers_df = researchers_df.copy()
researchers_df['email_key'] = researchers_df['email'].map(_clean_email)

email_to_canonical = researchers_df.set_index('email_key')['email'].to_dict()
email_to_fullname  = researchers_df.set_index('email_key')['full_name'].to_dict()

normalized_topics_df = normalized_topics_df.copy()
normalized_topics_df['email_key'] = normalized_topics_df['email'].map(_clean_email)
normalized_topics_df['email'] = normalized_topics_df['email_key'].map(email_to_canonical)
normalized_topics_df['full_name'] = normalized_topics_df['email_key'].map(email_to_fullname)
normalized_topics_df.drop(columns=['first_name', 'family_name', 'email_key'], inplace=True, errors='ignore')

cols = ['full_name', 'email'] + [c for c in normalized_topics_df.columns if c not in ('full_name', 'email')]
normalized_topics_df = normalized_topics_df[cols]

# Save normalized topics
normalized_topics_path = os.path.join(directory, 'normalized_topics_df.xlsx')
normalized_topics_df.to_excel(normalized_topics_path, index=False)

# =============================================================================
# PART 2 - WHO SUBMITTED TOPICS
# =============================================================================

topic_counts = (
    normalized_topics_df
    .groupby('full_name')
    .size()
    .reset_index(name='submitted_topics')
)

researchers_with_topics = researchers_df.merge(topic_counts, on='full_name', how='left')
researchers_with_topics['submitted_topics'] = researchers_with_topics['submitted_topics'].fillna(0).astype(int)
researchers_with_topics['submitted'] = researchers_with_topics['submitted_topics'].apply(lambda x: 'yes' if x > 0 else 'no')

submission_status_df = (
    researchers_with_topics[['full_name', 'email', 'appointment', 'submitted', 'submitted_topics']]
    .sort_values(by='full_name')
    .reset_index(drop=True)
)

submission_status_path = os.path.join(directory, 'submission_status_df.xlsx')
submission_status_df.to_excel(submission_status_path, index=False)

# =============================================================================
# PART 3 - CHECK MINIMUM POSSIBLE ASSIGNMENTS (global feasibility)
# =============================================================================

included_daily_supervisor_roles = [
    'postdoctoral researcher',
    'researcher',
    'affiliated researcher',
    'doctoral researcher',
    'research expert',
    'research fellow',
    'teaching assistant',
]

eligible_researchers = researchers_df[
    researchers_df['appointment'].astype(str).str.strip().str.lower().isin([r.lower() for r in included_daily_supervisor_roles])
]

min_capacity = eligible_researchers['daily_supervisor_minimum_theses'].sum()
max_capacity = eligible_researchers['daily_supervisor_maximum_theses'].sum()
student_count = len(students_df)

print(f"Total students to assign: {student_count}")
print(f"Available capacity from selected roles:")
print(f"  Minimum capacity: {min_capacity}")
print(f"  Maximum capacity: {max_capacity}")
print("Feasibility:",
      "Not enough capacity" if max_capacity < student_count
      else f"Sufficient (max {max_capacity} ≥ students {student_count})")

# =============================================================================
# PART 0: SETUP & HELPERS (kept naming)
# =============================================================================

# Roles considered eligible for daily supervision
ROLE_SET = {r.lower().strip() for r in included_daily_supervisor_roles}

# Policy knobs
CAP_MODE = 'min_plus'   # 'min_only' or 'min_plus'
CAP_FRACTION = 0.5      # used if CAP_MODE == 'min_plus'
LOAD_BALANCE_EXPONENT = 1.0  # similarity / (1 + current_load)**exp

def _cap_step1(min_theses, max_theses):
    if CAP_MODE == 'min_only':
        return int(min_theses or 0)
    extra = int(round(CAP_FRACTION * max(0, int(max_theses or 0) - int(min_theses or 0))))
    return int(min_theses or 0) + extra

# Build topic_lookup (no language fields needed)
merge_cols = [
    'full_name',
    'appointment',
    'daily_supervisor_minimum_theses',
    'daily_supervisor_maximum_theses',
    'email'
]

topic_lookup = normalized_topics_df.merge(
    researchers_df[merge_cols].rename(columns={'email': 'researcher_email'}),
    on='full_name', how='left'
)

topic_lookup = (
    topic_lookup.sort_values(by=['proposed_thesis_topic','full_name'])
    .drop_duplicates(subset=['proposed_thesis_topic'])
    .set_index('proposed_thesis_topic')
)

# Capacity table
capacity_lookup = (
    researchers_df
    .assign(_appointment=lambda d: d['appointment'].astype(str).str.strip().str.lower())
    .set_index('full_name')[['daily_supervisor_minimum_theses',
                             'daily_supervisor_maximum_theses',
                             '_appointment']]
    .rename(columns={'_appointment':'appointment_norm'})
    .to_dict('index')
)

def _eligible(name):
    info = capacity_lookup.get(name)
    return bool(info) and info['appointment_norm'] in ROLE_SET

# =============================================================================
# PREASSIGNMENT (carry-overs): lock existing supervisors and seed loads
# =============================================================================

# Ensure columns exist
if 'daily_supervisor' not in students_df.columns:
    students_df['daily_supervisor'] = None
if 'daily_supervisor_email' not in students_df.columns:
    students_df['daily_supervisor_email'] = None

# Map helpers
name_to_email = researchers_df.set_index('full_name')['email'].to_dict()

# 1) Flag preassigned rows
_pre_mask = students_df['daily_supervisor'].astype(str).str.strip().ne('') & students_df['daily_supervisor'].notna()
students_df['_preassigned'] = _pre_mask

# 2) Ensure emails for preassigned
students_df.loc[_pre_mask, 'daily_supervisor_email'] = (
    students_df.loc[_pre_mask, 'daily_supervisor']
    .map(name_to_email)
    .fillna(students_df.loc[_pre_mask, 'daily_supervisor_email'])
)

# 3) Seed current load with preassigned students
current_load = defaultdict(int)
for sup_name, cnt in students_df.loc[_pre_mask, 'daily_supervisor'].value_counts().items():
    current_load[sup_name] = int(cnt)

# Warn if any preassignment exceeds max
_over_max = []
for name, cnt in current_load.items():
    caps = capacity_lookup.get(name)
    if not caps:
        continue
    max_allowed = int(caps.get('daily_supervisor_maximum_theses') or 0)
    if max_allowed and cnt > max_allowed:
        _over_max.append((name, cnt, max_allowed))
if _over_max:
    print("WARNING: Some preassigned loads exceed maximum capacity:", _over_max)

# =============================================================================
# PART 1: TOPIC-SUBMITTER PREFERENCE (WITH FAIRNESS CAP)
# =============================================================================

def assign_supervisor_submitter_first(row):
    """Assign to the topic submitter when possible, respecting:
       - role eligibility
       - per-researcher step-1 cap (to prevent overload in step 1)
       - max capacity
       Skips rows preassigned by carry-over.
    """
    # Keep preassigned rows as-is
    if bool(row.get('_preassigned', False)):
        return pd.Series([row['daily_supervisor'], row['daily_supervisor_email'], None, None])

    topic = row.get('assigned_topic')
    if pd.isna(topic) or topic not in topic_lookup.index:
        return pd.Series([None, None, None, None])

    topic_info = topic_lookup.loc[topic]
    if isinstance(topic_info, pd.DataFrame):
        topic_info = topic_info.iloc[0]

    supervisor = topic_info['full_name']
    if not _eligible(supervisor):
        return pd.Series([None, None, None, None])

    sup_info = capacity_lookup[supervisor]
    min_theses = int(sup_info.get('daily_supervisor_minimum_theses') or 0)
    max_theses = int(sup_info.get('daily_supervisor_maximum_theses') or 0)
    if max_theses <= 0:
        return pd.Series([None, None, None, None])

    step1_cap = _cap_step1(min_theses, max_theses)

    # No language confirmation logic here (column intentionally unused)
    return pd.Series([supervisor, topic_info['researcher_email'], None, step1_cap])

# Apply step 1 (topic-submitter preference), but don't overwrite preassigned rows
tmp = students_df.apply(assign_supervisor_submitter_first, axis=1)
cols_assign = ['daily_supervisor', 'daily_supervisor_email', 'supervision_language_confirmed', '_step1_cap']
for c in cols_assign:
    if c not in students_df.columns:
        students_df[c] = None
students_df.loc[~students_df['_preassigned'], cols_assign] = tmp.loc[~students_df['_preassigned'], :].values

# Enforce per-researcher caps for step 1 (respect preassigned & seeded load)
def enforce_step1_caps(row):
    if bool(row.get('_preassigned', False)):
        return row

    name = row['daily_supervisor']
    if pd.isna(name):
        return row

    if not _eligible(name):
        row[['daily_supervisor','daily_supervisor_email','supervision_language_confirmed']] = [None, None, None]
        return row

    max_allowed = int(capacity_lookup[name]['daily_supervisor_maximum_theses'] or 0)
    step1_cap = int(row.get('_step1_cap') or 0) if row.get('_step1_cap') is not None else max_allowed

    used = current_load.get(name, 0)
    if used >= min(step1_cap, max_allowed):
        row[['daily_supervisor','daily_supervisor_email','supervision_language_confirmed']] = [None, None, None]
        return row

    current_load[name] = used + 1
    return row

students_df = students_df.apply(enforce_step1_caps, axis=1).drop(columns=['_step1_cap'])

# Build the stage-1 view
daily_supervisor_assignment = students_df[[
    'full_name','email','assigned_topic',
    'daily_supervisor','daily_supervisor_email',
    'assigned_language','supervision_language_confirmed',
    '_preassigned'
]].copy()

# =============================================================================
# PART 2: SEMANTIC MATCHING + MINIMUM-FIRST + LOAD BALANCING
# =============================================================================

# Prepare eligible researcher profiles
eligible_profiles = (
    researchers_df[
        researchers_df['appointment'].astype(str).str.strip().str.lower().isin(ROLE_SET)
    ]
    .copy()
)

eligible_profiles['combined'] = (
    eligible_profiles['profile_description'].fillna('') + ' ' +
    eligible_profiles['publication_list'].fillna('')
)

# Embeddings
# model = SentenceTransformer('all-MiniLM-L6-v2')
model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
profile_embeddings = model.encode(eligible_profiles['combined'].fillna('').tolist(), show_progress_bar=False)

# Quick index for row -> researcher info
eligible_index = eligible_profiles[['full_name','email','appointment']].reset_index(drop=True)

def rank_researchers_embeddings(query):
    q_emb = model.encode([query])[0]
    sims = cosine_similarity([q_emb], profile_embeddings)[0]
    ranked = eligible_index.copy()
    ranked['similarity'] = sims
    return ranked.sort_values('similarity', ascending=False)

# Current load after step 1 (includes preassignments and accepted step-1)
current_load = daily_supervisor_assignment['daily_supervisor'].value_counts().to_dict()

# Helper: compute unmet minima
def unmet_minima_dict():
    unmet = {}
    for name, caps in capacity_lookup.items():
        if caps['appointment_norm'] not in ROLE_SET:
            continue
        min_req = int(caps.get('daily_supervisor_minimum_theses') or 0)
        cur = int(current_load.get(name, 0))
        d = max(0, min_req - cur)
        if d > 0:
            unmet[name] = d
    return unmet

# Students still unassigned after step 1
unassigned_idx = daily_supervisor_assignment['daily_supervisor'].isna()
unassigned_students = daily_supervisor_assignment[unassigned_idx].copy()

# Phase 2A: Satisfy minima first
for idx, row in unassigned_students.iterrows():
    topic_query = row['assigned_topic']
    if pd.isna(topic_query) or not str(topic_query).strip():
        continue

    ranked = rank_researchers_embeddings(str(topic_query))
    unmet = unmet_minima_dict()
    if not unmet:
        break  # all mins satisfied

    best = None
    best_score = -1.0

    for _, r in ranked.iterrows():
        name = r['full_name']
        if name not in capacity_lookup:
            continue
        caps = capacity_lookup[name]
        cur = int(current_load.get(name, 0))
        max_allowed = int(caps.get('daily_supervisor_maximum_theses') or 0)
        if cur >= max_allowed:
            continue
        if name not in unmet:
            continue

        score = r['similarity'] / ((1 + cur) ** LOAD_BALANCE_EXPONENT)
        if score > best_score:
            best_score = score
            best = (name, r['email'])

    if best:
        name, email = best
        daily_supervisor_assignment.at[idx, 'daily_supervisor'] = name
        daily_supervisor_assignment.at[idx, 'daily_supervisor_email'] = email
        daily_supervisor_assignment.at[idx, 'supervision_language_confirmed'] = "Needs manual checking"
        current_load[name] = current_load.get(name, 0) + 1

# Phase 2B: General matching (respect max & load-balance)
unassigned_idx = daily_supervisor_assignment['daily_supervisor'].isna()
unassigned_students = daily_supervisor_assignment[unassigned_idx].copy()

for idx, row in unassigned_students.iterrows():
    topic_query = row['assigned_topic']
    if pd.isna(topic_query) or not str(topic_query).strip():
        continue

    ranked = rank_researchers_embeddings(str(topic_query))
    best = None
    best_score = -1.0

    for _, r in ranked.iterrows():
        name = r['full_name']
        if name not in capacity_lookup:
            continue
        caps = capacity_lookup[name]
        cur = int(current_load.get(name, 0))
        max_allowed = int(caps.get('daily_supervisor_maximum_theses') or 0)
        if cur >= max_allowed:
            continue

        score = r['similarity'] / ((1 + cur) ** LOAD_BALANCE_EXPONENT)
        if score > best_score:
            best_score = score
            best = (name, r['email'])

    if best:
        name, email = best
        daily_supervisor_assignment.at[idx, 'daily_supervisor'] = name
        daily_supervisor_assignment.at[idx, 'daily_supervisor_email'] = email
        daily_supervisor_assignment.at[idx, 'supervision_language_confirmed'] = "Needs manual checking"
        current_load[name] = current_load.get(name, 0) + 1

# =============================================================================
# EXPORT ASSIGNMENTS
# =============================================================================
print("Assignment preview:\n", daily_supervisor_assignment.head())

assignment_path = os.path.join(directory, 'daily_supervisor_assignment.xlsx')
daily_supervisor_assignment.drop(columns=['_preassigned'], errors='ignore').to_excel(assignment_path, index=False)

# =============================================================================
# PART 4: SUPERVISION OVERVIEW SUMMARY
# =============================================================================

supervision_counts = (
    daily_supervisor_assignment['daily_supervisor']
    .value_counts()
    .rename_axis('full_name')
    .reset_index(name='assigned_theses')
)

daily_supervision_summary = researchers_df.merge(
    supervision_counts,
    on='full_name',
    how='left'
)

daily_supervision_summary['assigned_theses'] = daily_supervision_summary['assigned_theses'].fillna(0).astype(int)

daily_supervision_summary = daily_supervision_summary[[
    'full_name',
    'email',
    'appointment',
    'daily_supervisor_minimum_theses',
    'daily_supervisor_maximum_theses',
    'assigned_theses'
]].sort_values(by='assigned_theses', ascending=False)

print("Supervision summary preview:\n", daily_supervision_summary.head())
total_assigned_theses = daily_supervision_summary["assigned_theses"].sum()
print("Total assigned theses:", total_assigned_theses)

summary_path = os.path.join(directory, 'daily_supervision_summary.xlsx')
daily_supervision_summary.to_excel(summary_path, index=False)

print("\nExported files:")
print(" -", normalized_topics_path)
print(" -", submission_status_path)
print(" -", assignment_path)
print(" -", summary_path)
