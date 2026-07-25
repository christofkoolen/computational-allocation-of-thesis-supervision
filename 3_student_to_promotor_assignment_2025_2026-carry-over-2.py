# -*- coding: utf-8 -*-
"""
End-to-end promotor assignment with carry-over handling and constraint:
- Preassign promotors from existing data (daily_supervisor_df or students_df) and count them toward capacity.
- Do NOT auto-assign a promotor who is the same as the student's daily supervisor.
- Step 1: Submitter-first with fairness cap.
- Step 2: Semantic matching (2A minima-first, 2B general) with load balancing.
- Export final assignment and promotor summary.
"""

#%% Dependencies
import os
import pandas as pd
from collections import defaultdict
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

#%% File paths
directory = r'C:\Users\chris\My Drive (christofkoolen@gmail.com)\PostDoc\Admin\LLM Thesis Allocation\Allocation 2025-2026\Files'
# directory = r'C:\Users\u0124399\My Drive\PostDoc\Admin\LLM Thesis Allocation\Files'

students_file           = os.path.join(directory, "thesis_topics_assigned_to_students_updated.xlsx")
researchers_file        = os.path.join(directory, "researcher_profiles_2025_2026_updated.xlsx")
daily_supervisor_file   = os.path.join(directory, "daily_supervisor_assignment.xlsx")
normalized_topics_file  = os.path.join(directory, "normalized_topics_df.xlsx")

# Outputs
final_assignment_xlsx   = os.path.join(directory, "final_assignment.xlsx")
promotor_summary_xlsx   = os.path.join(directory, "promotor_summary.xlsx")

#%% Load data
students_df         = pd.read_excel(students_file)
researchers_df      = pd.read_excel(researchers_file)
daily_supervisor_df = pd.read_excel(daily_supervisor_file)

print("Students file loaded:", students_df.shape)
print("Researchers file loaded:", researchers_df.shape)
print("Daily supervisor file loaded:", daily_supervisor_df.shape)

try:
    normalized_topics_df = pd.read_excel(normalized_topics_file)
    HAS_TOPICS = True
    print("Topics (submitter) file loaded:", normalized_topics_df.shape)
except Exception as e:
    print(f"Note: Could not load topics file '{normalized_topics_file}'. Submitter-first Step 1 will be skipped. ({e})")
    normalized_topics_df = None
    HAS_TOPICS = False

#%% =============================================================================
# PART 1: SANITY CHECK FOR PROMOTOR CAPACITY
# =============================================================================
included_promotor_roles = [
    'professor', 'postdoctoral researcher', 'research fellow',
    'emeritus', 'research expert', 'teaching assistant'
]

eligible_promotors = researchers_df[
    researchers_df['appointment'].astype(str).str.strip().str.lower().isin(
        [role.lower() for role in included_promotor_roles]
    )
].copy()

min_capacity = eligible_promotors['promotor_minimum_theses'].sum()
max_capacity = eligible_promotors['promotor_maximum_theses'].sum()
student_count = len(students_df)

print(f"Total students to assign promotors for: {student_count}")
print(f"Promotor minimum capacity: {min_capacity}")
print(f"Promotor maximum capacity: {max_capacity}")
print("Feasibility:",
      "Not enough promotor capacity" if max_capacity < student_count
      else f"Sufficient (max {max_capacity} ≥ students {student_count})")

#%% =============================================================================
# PART 1.5: CONFIG & HELPERS
# =============================================================================
# Policy knobs
PROMOTOR_CAP_MODE = 'min_plus'   # 'min_only' or 'min_plus'
PROMOTOR_CAP_FRACTION = 0.75     # used if 'min_plus'
PROMOTOR_LOAD_BALANCE_EXP = 1.0  # similarity / (1 + current_load)**exp

ROLE_PROMOTOR_SET = {r.lower().strip() for r in included_promotor_roles}

def cap_step1(min_theses, max_theses):
    minv = int(min_theses or 0)
    maxv = int(max_theses or 0)
    if PROMOTOR_CAP_MODE == 'min_only':
        return minv
    extra = int(round(PROMOTOR_CAP_FRACTION * max(0, maxv - minv)))
    return minv + extra

# Capacity lookup with normalized appointment
promotor_capacity_lookup = (
    researchers_df
    .assign(appointment_normalized=researchers_df['appointment'].astype(str).str.strip().str.lower())
    .set_index('full_name')[['promotor_minimum_theses','promotor_maximum_theses','appointment_normalized','email']]
    .to_dict('index')
)

def is_promotor_eligible(name):
    info = promotor_capacity_lookup.get(name)
    return bool(info) and info['appointment_normalized'] in ROLE_PROMOTOR_SET

# Name -> email (for filling promotor_email)
name_to_email = researchers_df.set_index('full_name')['email'].to_dict()

#%% =============================================================================
# PART 1.75: PREASSIGNMENT (carry-overs) FOR PROMOTOR
# =============================================================================
# Ensure promotor columns exist in working frame
if 'promotor' not in daily_supervisor_df.columns:
    daily_supervisor_df['promotor'] = None
if 'promotor_email' not in daily_supervisor_df.columns:
    daily_supervisor_df['promotor_email'] = None

# 1) Bring in any promotor already present in students_df (match by email)
if 'promotor' in students_df.columns:
    # Left-join students_df[['email','promotor']] onto daily_supervisor_df by email
    pre_from_students = students_df[['email', 'promotor']].copy()
    pre_from_students.columns = ['email', 'promotor_from_students']
    daily_supervisor_df = daily_supervisor_df.merge(pre_from_students, on='email', how='left')

    # If daily_supervisor_df has no promotor but students_df does, take it
    take_students_mask = (
        daily_supervisor_df['promotor'].isna()
        & daily_supervisor_df['promotor_from_students'].notna()
        & (daily_supervisor_df['promotor_from_students'].astype(str).str.strip() != '')
    )
    daily_supervisor_df.loc[take_students_mask, 'promotor'] = daily_supervisor_df.loc[take_students_mask, 'promotor_from_students']

    # Drop helper col
    daily_supervisor_df.drop(columns=['promotor_from_students'], inplace=True)

# 2) Flag preassigned promotors (from either source)
pre_promotor_mask = daily_supervisor_df['promotor'].notna() & (daily_supervisor_df['promotor'].astype(str).str.strip() != '')
daily_supervisor_df['_pre_promotor'] = pre_promotor_mask

# 3) Ensure promotor_email for preassigned rows
daily_supervisor_df.loc[pre_promotor_mask, 'promotor_email'] = (
    daily_supervisor_df.loc[pre_promotor_mask, 'promotor'].map(name_to_email)
    .fillna(daily_supervisor_df.loc[pre_promotor_mask, 'promotor_email'])
)

# 4) Seed current promotor load from preassigned rows
promotor_load = defaultdict(int)
for name, cnt in daily_supervisor_df.loc[pre_promotor_mask, 'promotor'].value_counts().items():
    promotor_load[name] = int(cnt)

# 5) Warn if any preassignment exceeds max capacity
_over_max = []
for name, used in promotor_load.items():
    caps = promotor_capacity_lookup.get(name)
    if not caps:
        continue
    max_allowed = int(caps.get('promotor_maximum_theses') or 0)
    if max_allowed and used > max_allowed:
        _over_max.append((name, used, max_allowed))
if _over_max:
    print("WARNING: Some preassigned promotor loads exceed maximum capacity:", _over_max)

#%% =============================================================================
# PART 2: PROMOTOR ASSIGNMENT — STEP 1 (SUBMITTER-FIRST, FAIRNESS CAP)
# =============================================================================
if HAS_TOPICS:
    promotor_merge_cols = [
        'full_name', 'appointment',
        'promotor_minimum_theses', 'promotor_maximum_theses', 'email'
    ]
    topic_lookup_promotor = (
        normalized_topics_df
        .merge(
            researchers_df[promotor_merge_cols].rename(columns={'email': 'promotor_email_submitter'}),
            on='full_name', how='left'
        )
        .sort_values(['proposed_thesis_topic','full_name'])
        .drop_duplicates(subset=['proposed_thesis_topic'])
        .set_index('proposed_thesis_topic')
    )

    def assign_promotor_submitter_first(row):
        # Skip rows with preassigned promotor
        if bool(row.get('_pre_promotor', False)):
            return pd.Series([row['promotor'], row['promotor_email'], None])

        topic = row.get('assigned_topic')
        if pd.isna(topic) or topic not in topic_lookup_promotor.index:
            return pd.Series([None, None, None])

        ti = topic_lookup_promotor.loc[topic]
        if isinstance(ti, pd.DataFrame):
            ti = ti.iloc[0]

        promotor_name = ti['full_name']

        # NEW RULE: do not auto-assign if same person is already the daily supervisor
        ds = str(row.get('daily_supervisor') or '').strip()
        if ds and str(promotor_name).strip() == ds:
            return pd.Series([None, None, None])

        if not is_promotor_eligible(promotor_name):
            return pd.Series([None, None, None])

        caps = promotor_capacity_lookup[promotor_name]
        minv = int(caps.get('promotor_minimum_theses') or 0)
        maxv = int(caps.get('promotor_maximum_theses') or 0)
        if maxv <= 0:
            return pd.Series([None, None, None])

        step1_cap_val = cap_step1(minv, maxv)
        return pd.Series([promotor_name, ti['promotor_email_submitter'], step1_cap_val])

    tmp = daily_supervisor_df.apply(assign_promotor_submitter_first, axis=1)
    cols = ['promotor','promotor_email','_promotor_step1_cap']
    for c in cols:
        if c not in daily_supervisor_df.columns:
            daily_supervisor_df[c] = None

    # Only update non-preassigned rows
    upd_mask = ~daily_supervisor_df['_pre_promotor']
    daily_supervisor_df.loc[upd_mask, cols] = tmp.loc[upd_mask, :].values

    # Enforce Step-1 cap & absolute max (respect preassigned + seeded load)
    def enforce_promotor_step1(row):
        if bool(row.get('_pre_promotor', False)):
            return row

        name = row['promotor']
        if pd.isna(name):
            return row
        if not is_promotor_eligible(name):
            row[['promotor','promotor_email']] = [None, None]
            return row

        max_allowed = int(promotor_capacity_lookup[name]['promotor_maximum_theses'] or 0)
        cap1 = int(row.get('_promotor_step1_cap') or 0) if row.get('_promotor_step1_cap') is not None else max_allowed

        used = promotor_load.get(name, 0)
        if used >= min(cap1, max_allowed):
            row[['promotor','promotor_email']] = [None, None]
            return row

        promotor_load[name] = used + 1
        return row

    daily_supervisor_df = daily_supervisor_df.apply(enforce_promotor_step1, axis=1).drop(columns=['_promotor_step1_cap'])
else:
    print("Skipping Step 1 (submitter-first) — topics file not available.")

#%% =============================================================================
# PART 2B: PROMOTOR ASSIGNMENT — STEP 2 (SEMANTIC MATCHING + MINIMA FIRST)
# =============================================================================
eligible_promotors_sem = researchers_df[
    researchers_df['appointment'].astype(str).str.strip().str.lower().isin(ROLE_PROMOTOR_SET)
].copy()

eligible_promotors_sem['combined'] = (
    eligible_promotors_sem['profile_description'].fillna('') + ' ' +
    eligible_promotors_sem['publication_list'].fillna('')
)

promotor_model = SentenceTransformer('sentence-transformers/all-mpnet-base-v2')
promotor_embeddings = promotor_model.encode(
    eligible_promotors_sem['combined'].fillna('').tolist(),
    show_progress_bar=False
)
promotor_index = eligible_promotors_sem[['full_name','email','appointment']].reset_index(drop=True)

def rank_promotors_by_similarity(query):
    q = promotor_model.encode([str(query)])[0]
    sims = cosine_similarity([q], promotor_embeddings)[0]
    ranked = promotor_index.copy()
    ranked['similarity'] = sims
    return ranked.sort_values('similarity', ascending=False)

# Current load (after preassignment + accepted step-1)
promotor_load = daily_supervisor_df['promotor'].value_counts(dropna=True).to_dict()

def unmet_minima():
    unmet = {}
    for name, caps in promotor_capacity_lookup.items():
        if caps['appointment_normalized'] not in ROLE_PROMOTOR_SET:
            continue
        m = int(caps.get('promotor_minimum_theses') or 0)
        cur = int(promotor_load.get(name, 0))
        d = m - cur
        if d > 0:
            unmet[name] = d
    return unmet

# Phase 2A: satisfy minima first (skip preassigned)
unassigned_mask = daily_supervisor_df['promotor'].isna() & (~daily_supervisor_df['_pre_promotor'])
for idx, row in daily_supervisor_df[unassigned_mask].iterrows():
    topic = row['assigned_topic']
    if pd.isna(topic) or not str(topic).strip():
        continue

    ranked = rank_promotors_by_similarity(topic)
    unmet = unmet_minima()
    if not unmet:
        break

    best = None; best_score = -1.0
    ds = str(row.get('daily_supervisor') or '').strip()  # NEW: daily supervisor to avoid
    for _, r in ranked.iterrows():
        name = r['full_name']

        # NEW RULE: skip if candidate promotor is the already assigned daily supervisor
        if ds and str(name).strip() == ds:
            continue

        caps = promotor_capacity_lookup.get(name)
        if not caps:
            continue
        cur = int(promotor_load.get(name, 0))
        max_allowed = int(caps.get('promotor_maximum_theses') or 0)
        if cur >= max_allowed or name not in unmet:
            continue

        score = r['similarity'] / ((1 + cur) ** PROMOTOR_LOAD_BALANCE_EXP)
        if score > best_score:
            best_score = score
            best = (name, r['email'])

    if best:
        n, e = best
        daily_supervisor_df.at[idx, 'promotor'] = n
        daily_supervisor_df.at[idx, 'promotor_email'] = e
        promotor_load[n] = promotor_load.get(n, 0) + 1

# Phase 2B: general fill (respect max + load-balance, skip preassigned)
unassigned_mask = daily_supervisor_df['promotor'].isna() & (~daily_supervisor_df['_pre_promotor'])
for idx, row in daily_supervisor_df[unassigned_mask].iterrows():
    topic = row['assigned_topic']
    if pd.isna(topic) or not str(topic).strip():
        continue

    ranked = rank_promotors_by_similarity(topic)
    best = None; best_score = -1.0
    ds = str(row.get('daily_supervisor') or '').strip()  # NEW: daily supervisor to avoid

    for _, r in ranked.iterrows():
        name = r['full_name']

        # NEW RULE: skip if candidate promotor is the already assigned daily supervisor
        if ds and str(name).strip() == ds:
            continue

        caps = promotor_capacity_lookup.get(name)
        if not caps:
            continue
        cur = int(promotor_load.get(name, 0))
        max_allowed = int(caps.get('promotor_maximum_theses') or 0)
        if cur >= max_allowed:
            continue

        score = r['similarity'] / ((1 + cur) ** PROMOTOR_LOAD_BALANCE_EXP)
        if score > best_score:
            best_score = score
            best = (name, r['email'])

    if best:
        n, e = best
        daily_supervisor_df.at[idx, 'promotor'] = n
        daily_supervisor_df.at[idx, 'promotor_email'] = e
        promotor_load[n] = promotor_load.get(n, 0) + 1

#%% =============================================================================
# PART 3: COMBINE ASSIGNMENTS INTO STUDENT-FACING DOCUMENT
# =============================================================================
final_assignment = daily_supervisor_df[[
    'full_name',
    'email',
    'assigned_topic',
    'assigned_language',
    'supervision_language_confirmed',  # may be present from daily supervisor phase
    'daily_supervisor',
    'daily_supervisor_email',
    'promotor',
    'promotor_email'
]].copy()

print(final_assignment.head())
final_assignment.to_excel(final_assignment_xlsx, index=False)
print(f"Saved final assignment to: {final_assignment_xlsx}")

#%% =============================================================================
# PART 4: SUPERVISION SUMMARY FOR PROMOTORS
# =============================================================================
promotor_counts = (
    daily_supervisor_df['promotor']
    .value_counts(dropna=True)
    .rename_axis('full_name')
    .reset_index(name='assigned_promotor_theses')
)

promotor_summary = researchers_df.merge(
    promotor_counts,
    on='full_name',
    how='left'
)

promotor_summary['assigned_promotor_theses'] = promotor_summary['assigned_promotor_theses'].fillna(0).astype(int)

promotor_summary = promotor_summary[[
    'full_name', 'email', 'appointment',
    'promotor_minimum_theses', 'promotor_maximum_theses',
    'assigned_promotor_theses'
]].sort_values(by='assigned_promotor_theses', ascending=False)

print(promotor_summary.head())
print("Total promotor assignments:", promotor_summary['assigned_promotor_theses'].sum())

promotor_summary.to_excel(promotor_summary_xlsx, index=False)
print(f"Saved promotor summary to: {promotor_summary_xlsx}")
