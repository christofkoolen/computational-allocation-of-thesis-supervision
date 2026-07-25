# -*- coding: utf-8 -*-
"""
Fill missing daily supervisors and thesis promotors using two-phase semantic matching
(minima-first, then general) with load balancing and capacity limits.

Now also prints the Top-10 best candidates per student & role on every run.

Inputs (same folder by default):
  - final_assignment.xlsx
  - promotor_summary.xlsx
  - daily_supervision_summary.xlsx   ('.xlxs' typo handled automatically)
  - researcher_profiles_2025_2026_updated.xlsx

Outputs:
  - final_assignment_filled.xlsx
  - replacement_log.csv
"""

import os
import pandas as pd
import numpy as np
from collections import defaultdict
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# =========================
# Config
# =========================
DIRECTORY = r'C:\Users\chris\My Drive (christofkoolen@gmail.com)\PostDoc\Admin\LLM Thesis Allocation\Allocation 2025-2026\Files'

FINAL_ASSIGNMENT_XLSX = os.path.join(DIRECTORY, 'final_assignment - Copy.xlsx')
PROMOTOR_SUMMARY_XLSX = os.path.join(DIRECTORY, 'promotor_summary.xlsx')
DAILY_SUP_SUMMARY_XLSX = os.path.join(DIRECTORY, 'daily_supervision_summary.xlsx')  # retry .xlxs if needed
RESEARCHERS_XLSX       = os.path.join(DIRECTORY, 'researcher_profiles_2025_2026_updated.xlsx')

OUTPUT_ASSIGNMENT_XLSX = os.path.join(DIRECTORY, 'final_assignment_filled.xlsx')
OUTPUT_LOG_CSV         = os.path.join(DIRECTORY, 'replacement_log.csv')

# Embedding model & scoring knobs
EMBEDDING_MODEL_NAME = 'sentence-transformers/all-mpnet-base-v2'

# Load-balancing: similarity / (1 + current_load)**EXP
LOAD_BALANCE_EXPONENT = 1.0

# Bonus to nudge candidates who are still below their minimum (applied in general phase as light bias)
BELOW_MIN_BONUS = 0.05

# Should daily supervisor and thesis promotor be different people?
ENFORCE_DISTINCT_ROLES = True

# =========================
# Helpers
# =========================
def _nonempty(x):
    return pd.notna(x) and str(x).strip() != ''

def _clean(x):
    return str(x).strip() if pd.notna(x) else ''

def _load_daily_supervision_summary(path):
    """Load daily supervision summary, retrying .xlxs/.xlsx if the user-provided extension is off."""
    try:
        return pd.read_excel(path)
    except Exception:
        base, ext = os.path.splitext(path)
        trial = base + ('.xlsx' if ext.lower() == '.xlxs' else '.xlxs')
        return pd.read_excel(trial)

def _ensure_cols(df, cols, df_name='DataFrame'):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"{df_name} is missing required columns: {missing}")

def _coalesce_column(df, target, aliases):
    """Ensure df[target] exists by copying from the first present alias; otherwise create NaN column."""
    if target in df.columns:
        return
    for cand in aliases:
        if cand in df.columns:
            df[target] = df[cand]
            return
    df[target] = np.nan

def _build_embeddings(text_ser, model):
    texts = text_ser.fillna('').tolist()
    return model.encode(texts, show_progress_bar=False)

def _rank(query_text, embeddings, candidate_index_df, model):
    """Return candidate_index_df with a 'similarity' column, ranked descending."""
    if not _nonempty(query_text):
        out = candidate_index_df.copy()
        out['similarity'] = 0.0
        return out
    q_emb = model.encode([str(query_text)])[0]
    sims = cosine_similarity([q_emb], embeddings)[0]
    ranked = candidate_index_df.copy()
    ranked['similarity'] = sims
    return ranked.sort_values('similarity', ascending=False)

def _score(similarity, cur_load, below_min):
    # Load-balanced similarity with optional below-min bonus
    s = similarity / ((1 + cur_load) ** LOAD_BALANCE_EXPONENT)
    if below_min:
        s += BELOW_MIN_BONUS
    return s

def _print_top10(role_label, phase_label, student_name, student_email, topic_text,
                 ranked_df, load_dict, min_dict, max_dict, avoid_name=None, unmet_only=None):
    """
    Build viable candidates table (respect capacity, avoid_name, unmet minima if provided),
    compute final scores, and print Top-10.
    """
    df = ranked_df.copy()

    # Annotate with current load / caps
    df['cur_load'] = df['full_name'].map(lambda n: int(load_dict.get(n, 0)))
    df['min_cap']  = df['full_name'].map(lambda n: int(min_dict.get(n, 0)))
    df['max_cap']  = df['full_name'].map(lambda n: int(max_dict.get(n, 0)))
    df['below_min'] = df['cur_load'] < df['min_cap']
    df['capacity_left'] = df['cur_load'] < df['max_cap']

    # Apply filters
    mask = df['capacity_left']
    if ENFORCE_DISTINCT_ROLES and _nonempty(avoid_name):
        mask &= df['full_name'] != avoid_name
    if unmet_only is not None:
        # keep only names present in unmet_only (set of names)
        mask &= df['full_name'].isin(unmet_only)

    df = df.loc[mask].copy()

    # Compute final score used in the algorithm
    df['final_score'] = df.apply(
        lambda r: _score(r['similarity'], r['cur_load'], bool(r['below_min'])),
        axis=1
    )

    # Order by final score (desc)
    df = df.sort_values('final_score', ascending=False)

    # Print Top-10 snapshot
    head = df[['full_name', 'email', 'similarity', 'final_score',
               'cur_load', 'min_cap', 'max_cap', 'below_min']].head(10)

    print("\n" + "="*88)
    print(f"TOP-10 CANDIDATES | Role: {role_label} | Phase: {phase_label}")
    print(f"Student: {student_name} <{student_email}>")
    print(f"Topic: {str(topic_text)[:200]}{'...' if len(str(topic_text)) > 200 else ''}")
    if ENFORCE_DISTINCT_ROLES and _nonempty(avoid_name):
        print(f"Avoid (distinct-roles): {avoid_name}")
    if unmet_only is not None:
        print(f"Restricted to candidates below minimum ({len(unmet_only)} in pool)")
    print("-"*88)
    if head.empty:
        print("No viable candidates (capacity or constraints blocked all).")
    else:
        # pretty print
        with pd.option_context('display.max_colwidth', 60, 'display.width', 160):
            print(head.to_string(index=False))
    print("="*88 + "\n")

# =========================
# Load data
# =========================
final_assignment = pd.read_excel(FINAL_ASSIGNMENT_XLSX)
promotor_summary = pd.read_excel(PROMOTOR_SUMMARY_XLSX)
daily_sup_summary = _load_daily_supervision_summary(DAILY_SUP_SUMMARY_XLSX)
researchers_df   = pd.read_excel(RESEARCHERS_XLSX)

# Normalize student sheet columns (support alternate names)
_coalesce_column(final_assignment, 'thesis_promotor',       ['thesis_promotor', 'promotor'])
_coalesce_column(final_assignment, 'thesis_promotor_email', ['thesis_promotor_email', 'promotor_email'])

# Ensure student sheet has required columns
for c in ['full_name', 'email', 'assigned_topic', 'daily_supervisor', 'daily_supervisor_email',
          'thesis_promotor', 'thesis_promotor_email']:
    if c not in final_assignment.columns:
        final_assignment[c] = np.nan

# Ensure summary sheets have required columns
_ensure_cols(daily_sup_summary,
             ['full_name', 'daily_supervisor_minimum_theses', 'daily_supervisor_maximum_theses', 'assigned_theses'],
             'daily_supervision_summary')
_ensure_cols(promotor_summary,
             ['full_name', 'promotor_minimum_theses', 'promotor_maximum_theses', 'assigned_promotor_theses'],
             'promotor_summary')

# Ensure researchers have text fields
for c in ['full_name', 'email', 'appointment', 'profile_description', 'publication_list']:
    if c not in researchers_df.columns:
        researchers_df[c] = np.nan

# Clean names/emails
researchers_df['full_name'] = researchers_df['full_name'].map(_clean)
researchers_df['email']     = researchers_df['email'].map(_clean)

# Attach email to summaries if missing
name_to_email = researchers_df.set_index('full_name')['email'].to_dict()
if 'email' not in daily_sup_summary.columns:
    daily_sup_summary['email'] = daily_sup_summary['full_name'].map(name_to_email)
if 'email' not in promotor_summary.columns:
    promotor_summary['email'] = promotor_summary['full_name'].map(name_to_email)

# =========================
# Build candidate pools (restricted to people present in summaries)
# and their profile text from researcher profiles
# =========================
prof_text = researchers_df[['full_name', 'profile_description', 'publication_list']].copy()
prof_text['combined_text'] = prof_text['profile_description'].fillna('') + ' ' + prof_text['publication_list'].fillna('')

# Daily supervisor candidates
ds_candidates = (
    daily_sup_summary[['full_name', 'email',
                       'daily_supervisor_minimum_theses',
                       'daily_supervisor_maximum_theses',
                       'assigned_theses']]
    .copy()
)
ds_candidates['full_name'] = ds_candidates['full_name'].map(_clean)
ds_candidates['email']     = ds_candidates['email'].map(_clean)
ds_candidates = ds_candidates.merge(prof_text[['full_name', 'combined_text']], on='full_name', how='left')
ds_candidates['combined_text'] = ds_candidates['combined_text'].fillna('')

# Promotor candidates
pr_candidates = (
    promotor_summary[['full_name', 'email',
                      'promotor_minimum_theses',
                      'promotor_maximum_theses',
                      'assigned_promotor_theses']]
    .copy()
)
pr_candidates['full_name'] = pr_candidates['full_name'].map(_clean)
pr_candidates['email']     = pr_candidates['email'].map(_clean)
pr_candidates = pr_candidates.merge(prof_text[['full_name', 'combined_text']], on='full_name', how='left')
pr_candidates['combined_text'] = pr_candidates['combined_text'].fillna('')

# =========================
# Embeddings (once per role)
# =========================
model = SentenceTransformer(EMBEDDING_MODEL_NAME)
ds_embeddings = _build_embeddings(ds_candidates['combined_text'], model)
pr_embeddings = _build_embeddings(pr_candidates['combined_text'], model)

# Candidate index DataFrames used for ranking (columns used later)
ds_index = ds_candidates[['full_name', 'email',
                          'daily_supervisor_minimum_theses',
                          'daily_supervisor_maximum_theses',
                          'assigned_theses']].reset_index(drop=True)

pr_index = pr_candidates[['full_name', 'email',
                          'promotor_minimum_theses',
                          'promotor_maximum_theses',
                          'assigned_promotor_theses']].reset_index(drop=True)

# =========================
# Live loads from summaries (will be updated as we assign)
# =========================
ds_load = ds_index.set_index('full_name')['assigned_theses'].fillna(0).astype(int).to_dict()
pr_load = pr_index.set_index('full_name')['assigned_promotor_theses'].fillna(0).astype(int).to_dict()

ds_min = ds_index.set_index('full_name')['daily_supervisor_minimum_theses'].fillna(0).astype(int).to_dict()
ds_max = ds_index.set_index('full_name')['daily_supervisor_maximum_theses'].fillna(0).astype(int).to_dict()

pr_min = pr_index.set_index('full_name')['promotor_minimum_theses'].fillna(0).astype(int).to_dict()
pr_max = pr_index.set_index('full_name')['promotor_maximum_theses'].fillna(0).astype(int).to_dict()

# =========================
# Minima helpers (recomputed on demand)
# =========================
def ds_unmet_minima():
    unmet = {}
    for name in ds_min.keys():
        cur = int(ds_load.get(name, 0))
        need = int(ds_min[name])
        d = need - cur
        if d > 0:
            unmet[name] = d
    return unmet

def pr_unmet_minima():
    unmet = {}
    for name in pr_min.keys():
        cur = int(pr_load.get(name, 0))
        need = int(pr_min[name])
        d = need - cur
        if d > 0:
            unmet[name] = d
    return unmet

# =========================
# Replacement log
# =========================
replacement_log = []  # (student_email, role, assigned_name, assigned_email, phase, score)

# =========================
# Two-phase assignment for DAILY SUPERVISOR
# =========================
# Phase 1: Minima-first
ds_missing_mask = ~final_assignment['daily_supervisor'].apply(_nonempty)
for idx, srow in final_assignment[ds_missing_mask].iterrows():
    topic = srow.get('assigned_topic')
    student_name = _clean(srow.get('full_name'))
    student_email = _clean(srow.get('email'))
    avoid_name = _clean(srow.get('thesis_promotor')) if ENFORCE_DISTINCT_ROLES else ''

    ranked = _rank(topic, ds_embeddings, ds_index, model)
    unmet = ds_unmet_minima()
    if not unmet:
        # Nothing below minimum; will be handled in Phase 2
        pass
    else:
        # Print Top-10 for this run (minima-first)
        _print_top10(
            role_label="Daily Supervisor",
            phase_label="Minima-first",
            student_name=student_name,
            student_email=student_email,
            topic_text=topic,
            ranked_df=ranked,
            load_dict=ds_load, min_dict=ds_min, max_dict=ds_max,
            avoid_name=avoid_name,
            unmet_only=set(unmet.keys())
        )

        best = None
        best_score = -1.0

        for _, cand in ranked.iterrows():
            name = cand['full_name']
            if name not in unmet:
                continue  # minima-first: only those below min
            cur = int(ds_load.get(name, 0))
            mx  = int(ds_max.get(name, 0))
            if cur >= mx:
                continue
            if avoid_name and name == avoid_name:
                continue

            score = _score(cand['similarity'], cur, below_min=True)
            if score > best_score:
                best_score = score
                best = cand

        if best is not None:
            final_assignment.at[idx, 'daily_supervisor'] = best['full_name']
            final_assignment.at[idx, 'daily_supervisor_email'] = best.get('email', np.nan)
            ds_load[best['full_name']] = ds_load.get(best['full_name'], 0) + 1
            replacement_log.append((srow.get('email'), 'daily_supervisor', best['full_name'], best.get('email', np.nan), 'minima_first', round(best_score, 6)))
            continue  # proceed to next student; already filled in phase 1

# Phase 2: General fill (respect max; light bonus if still below min)
ds_missing_mask = ~final_assignment['daily_supervisor'].apply(_nonempty)
for idx, srow in final_assignment[ds_missing_mask].iterrows():
    topic = srow.get('assigned_topic')
    student_name = _clean(srow.get('full_name'))
    student_email = _clean(srow.get('email'))
    avoid_name = _clean(srow.get('thesis_promotor')) if ENFORCE_DISTINCT_ROLES else ''

    ranked = _rank(topic, ds_embeddings, ds_index, model)

    # Print Top-10 for this run (general)
    _print_top10(
        role_label="Daily Supervisor",
        phase_label="General",
        student_name=student_name,
        student_email=student_email,
        topic_text=topic,
        ranked_df=ranked,
        load_dict=ds_load, min_dict=ds_min, max_dict=ds_max,
        avoid_name=avoid_name,
        unmet_only=None
    )

    best = None
    best_score = -1.0

    for _, cand in ranked.iterrows():
        name = cand['full_name']
        cur = int(ds_load.get(name, 0))
        mx  = int(ds_max.get(name, 0))
        if cur >= mx:
            continue
        if avoid_name and name == avoid_name:
            continue

        below_min = cur < int(ds_min.get(name, 0))
        score = _score(cand['similarity'], cur, below_min)
        if score > best_score:
            best_score = score
            best = cand

    if best is not None:
        final_assignment.at[idx, 'daily_supervisor'] = best['full_name']
        final_assignment.at[idx, 'daily_supervisor_email'] = best.get('email', np.nan)
        ds_load[best['full_name']] = ds_load.get(best['full_name'], 0) + 1
        replacement_log.append((srow.get('email'), 'daily_supervisor', best['full_name'], best.get('email', np.nan), 'general', round(best_score, 6)))

# =========================
# Two-phase assignment for THESIS PROMOTOR
# =========================
# Phase 1: Minima-first
pr_missing_mask = ~final_assignment['thesis_promotor'].apply(_nonempty)
for idx, srow in final_assignment[pr_missing_mask].iterrows():
    topic = srow.get('assigned_topic')
    student_name = _clean(srow.get('full_name'))
    student_email = _clean(srow.get('email'))
    avoid_name = _clean(srow.get('daily_supervisor')) if ENFORCE_DISTINCT_ROLES else ''

    ranked = _rank(topic, pr_embeddings, pr_index, model)
    unmet = pr_unmet_minima()
    if not unmet:
        pass
    else:
        # Print Top-10 for this run (minima-first)
        _print_top10(
            role_label="Thesis Promotor",
            phase_label="Minima-first",
            student_name=student_name,
            student_email=student_email,
            topic_text=topic,
            ranked_df=ranked,
            load_dict=pr_load, min_dict=pr_min, max_dict=pr_max,
            avoid_name=avoid_name,
            unmet_only=set(unmet.keys())
        )

        best = None
        best_score = -1.0

        for _, cand in ranked.iterrows():
            name = cand['full_name']
            if name not in unmet:
                continue
            cur = int(pr_load.get(name, 0))
            mx  = int(pr_max.get(name, 0))
            if cur >= mx:
                continue
            if avoid_name and name == avoid_name:
                continue

            score = _score(cand['similarity'], cur, below_min=True)
            if score > best_score:
                best_score = score
                best = cand

        if best is not None:
            final_assignment.at[idx, 'thesis_promotor'] = best['full_name']
            if 'thesis_promotor_email' not in final_assignment.columns:
                final_assignment['thesis_promotor_email'] = np.nan
            final_assignment.at[idx, 'thesis_promotor_email'] = best.get('email', np.nan)
            pr_load[best['full_name']] = pr_load.get(best['full_name'], 0) + 1
            replacement_log.append((srow.get('email'), 'thesis_promotor', best['full_name'], best.get('email', np.nan), 'minima_first', round(best_score, 6)))
            continue

# Phase 2: General fill
pr_missing_mask = ~final_assignment['thesis_promotor'].apply(_nonempty)
for idx, srow in final_assignment[pr_missing_mask].iterrows():
    topic = srow.get('assigned_topic')
    student_name = _clean(srow.get('full_name'))
    student_email = _clean(srow.get('email'))
    avoid_name = _clean(srow.get('daily_supervisor')) if ENFORCE_DISTINCT_ROLES else ''

    ranked = _rank(topic, pr_embeddings, pr_index, model)

    # Print Top-10 for this run (general)
    _print_top10(
        role_label="Thesis Promotor",
        phase_label="General",
        student_name=student_name,
        student_email=student_email,
        topic_text=topic,
        ranked_df=ranked,
        load_dict=pr_load, min_dict=pr_min, max_dict=pr_max,
        avoid_name=avoid_name,
        unmet_only=None
    )

    best = None
    best_score = -1.0

    for _, cand in ranked.iterrows():
        name = cand['full_name']
        cur = int(pr_load.get(name, 0))
        mx  = int(pr_max.get(name, 0))
        if cur >= mx:
            continue
        if avoid_name and name == avoid_name:
            continue

        below_min = cur < int(pr_min.get(name, 0))
        score = _score(cand['similarity'], cur, below_min)
        if score > best_score:
            best_score = score
            best = cand

    if best is not None:
        final_assignment.at[idx, 'thesis_promotor'] = best['full_name']
        if 'thesis_promotor_email' not in final_assignment.columns:
            final_assignment['thesis_promotor_email'] = np.nan
        final_assignment.at[idx, 'thesis_promotor_email'] = best.get('email', np.nan)
        pr_load[best['full_name']] = pr_load.get(best['full_name'], 0) + 1
        replacement_log.append((srow.get('email'), 'thesis_promotor', best['full_name'], best.get('email', np.nan), 'general', round(best_score, 6)))

# =========================
# Save outputs
# =========================
final_assignment.to_excel(OUTPUT_ASSIGNMENT_XLSX, index=False)

log_df = pd.DataFrame(replacement_log, columns=[
    'student_email', 'role', 'assigned_name', 'assigned_email', 'phase', 'score'
])
log_df.to_csv(OUTPUT_LOG_CSV, index=False)

print(f"\nDone. Wrote:\n - {OUTPUT_ASSIGNMENT_XLSX}\n - {OUTPUT_LOG_CSV}")
