# -*- coding: utf-8 -*-
"""
Created on Sat Jun 14 10:46:03 2025

@author: chris
"""

#%% import dependencies
import os
import re
import heapq
import pandas as pd

# Try fast fuzzy matching if available
try:
    from rapidfuzz import process, fuzz
    HAS_RAPIDFUZZ = True
except Exception:
    HAS_RAPIDFUZZ = False


#%% Load files into working environment (unchanged paths)
directory = r'C:\Users\chris\My Drive (christofkoolen@gmail.com)\PostDoc\Admin\LLM Thesis Allocation\Allocation 2025-2026\Files'

students_filename = "students_and_preferred_topics_2025_2026.xlsx"
topics_filename   = "available_thesis_topics.xlsx"

students_path = os.path.join(directory, students_filename)
topics_path   = os.path.join(directory, topics_filename)

if not os.path.isfile(students_path):
    raise FileNotFoundError(f"Could not find {students_filename} in {directory}")
if not os.path.isfile(topics_path):
    raise FileNotFoundError(f"Could not find {topics_filename} in {directory}")

students_and_preferred_topics = pd.read_excel(students_path)
available_thesis_topics = pd.read_excel(topics_path)

print(f"Loaded students_and_preferred_topics: {students_and_preferred_topics.shape}")
print(f"Loaded available_thesis_topics: {available_thesis_topics.shape}")


#%% Remove duplicate submissions (more robust: trim + lower emails)
print("Number of students before duplicate removal:", len(students_and_preferred_topics))

def _clean_email(x):
    return str(x).strip().lower() if pd.notna(x) else x

if 'email' not in students_and_preferred_topics.columns:
    raise KeyError("Expected 'email' column in students_and_preferred_topics")

students_and_preferred_topics['email_norm'] = students_and_preferred_topics['email'].map(_clean_email)
students_and_preferred_topics = (
    students_and_preferred_topics
    .sort_values(['email_norm'])            # deterministic
    .drop_duplicates(subset='email_norm', keep='first', ignore_index=True)
)

print("Number of students after duplicate removal:", len(students_and_preferred_topics))


#%% Minimum edit distance between student-listed topics and supervisor-listed topics
# Faster fuzzy matching with RapidFuzz if available; fallback to Levenshtein

# 1) Prepare list of official titles (and a normalized copy)
if 'proposed_thesis_topic' not in available_thesis_topics.columns:
    raise KeyError("Expected 'proposed_thesis_topic' in available_thesis_topics")

choices = available_thesis_topics['proposed_thesis_topic'].dropna().astype(str).tolist()
choices_norm = [c.strip().lower() for c in choices]

# Fallback Levenshtein (space-efficient)
def levenshtein(a: str, b: str) -> int:
    len_a, len_b = len(a), len(b)
    prev = list(range(len_b + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len_b
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(
                prev[j] + 1,      # deletion
                curr[j-1] + 1,    # insertion
                prev[j-1] + cost  # substitution
            )
        prev = curr
    return prev[len_b]

# 2) Best-match resolver
def best_match(s: str) -> str | None:
    if not isinstance(s, str) or not s.strip():
        return None
    s_norm = s.strip().lower()
    if HAS_RAPIDFUZZ:
        match = process.extractOne(
            s_norm,
            choices_norm,
            scorer=fuzz.ratio
        )
        if match is None:
            return None
        idx = match[2]  # index in choices_norm
        return choices[idx]
    else:
        # fallback exact min distance
        distances = [levenshtein(s_norm, c) for c in choices_norm]
        best_idx = min(range(len(distances)), key=lambda i: distances[i])
        return choices[best_idx]

# 3) Apply to each topic column (only if column exists)
for i in (1, 2, 3):
    col = f'topic_{i}'
    edit_col = f'{col}_edit'
    if col in students_and_preferred_topics.columns:
        students_and_preferred_topics[edit_col] = (
            students_and_preferred_topics[col].astype(str).apply(best_match)
        )
    else:
        students_and_preferred_topics[edit_col] = None

print("Preview after fuzzy title correction:")
print(students_and_preferred_topics.head(3)[
    ['email', 'topic_1', 'topic_1_edit', 'topic_2', 'topic_2_edit', 'topic_3', 'topic_3_edit']
    if 'topic_1' in students_and_preferred_topics.columns else students_and_preferred_topics.columns[:8]
])


#%% Optional: Save intermediate progress to pickle (skip immediate re-load)
# (Keep this if you like the checkpoint; the re-load is redundant.)
intermediate_pickle = os.path.join(directory, 'students_and_preferred_topics_2025_2026.pkl')
students_and_preferred_topics.to_pickle(intermediate_pickle)
print(f"Saved intermediate pickle to: {intermediate_pickle}")


#%% Optimization Problem: Assign Students to Preferred Topics at Minimal Cost
# Supports per-topic capacity if available_thesis_topics has a 'capacity' column; defaults to 1.

# Resolve per-topic capacity (optional column)
if 'capacity' in available_thesis_topics.columns:
    topic_capacity = (
        available_thesis_topics
        .set_index('proposed_thesis_topic')['capacity']
        .fillna(1).astype(int).to_dict()
    )
else:
    topic_capacity = {t: 1 for t in choices}

# Build preference edges (only to valid, available topics)
MAX_PER_TOPIC_DEFAULT = 1
students = students_and_preferred_topics['email_norm'].tolist()

assignments = []
for _, row in students_and_preferred_topics.iterrows():
    email = row['email_norm']
    for cost in (1, 2, 3):
        topic = row.get(f'topic_{cost}_edit')
        if pd.isna(topic) or not topic:
            continue
        if topic not in topic_capacity:
            # skip topics not in official list (shouldn’t happen after best_match)
            continue
        assignments.append((email, topic, cost))

# Topics present in at least one edge
topics = sorted({t for _, t, _ in assignments})
idx_s = {s: i for i, s in enumerate(students)}
idx_t = {t: j for j, t in enumerate(topics)}

S, T = len(students), len(topics)
SRC, SNK = 0, S + T + 1
N = SNK + 1

class MinCostFlow:
    def __init__(self, N):
        self.N = N
        self.graph = [[] for _ in range(N)]
    def add_edge(self, fr, to, cap, cost, data=None):
        fwd = {'to': to, 'cap': cap, 'cost': cost, 'rev': len(self.graph[to]), 'orig_cap': cap, 'data': data}
        rev = {'to': fr, 'cap': 0,   'cost': -cost, 'rev': len(self.graph[fr]), 'orig_cap': 0,   'data': None}
        self.graph[fr].append(fwd)
        self.graph[to].append(rev)
    def flow(self, s, t, maxf):
        INF = float('inf')
        potential = [0]*self.N
        flow = cost = 0
        while flow < maxf:
            dist = [INF]*self.N
            prevv = [-1]*self.N
            preve = [-1]*self.N
            dist[s] = 0
            pq = [(0, s)]
            while pq:
                cd, v = heapq.heappop(pq)
                if cd > dist[v]: 
                    continue
                for i, e in enumerate(self.graph[v]):
                    if e['cap'] <= 0:
                        continue
                    nd = cd + e['cost'] + potential[v] - potential[e['to']]
                    if nd < dist[e['to']]:
                        dist[e['to']] = nd
                        prevv[e['to']] = v
                        preve[e['to']] = i
                        heapq.heappush(pq, (nd, e['to']))
            if dist[t] == INF:
                break
            for v in range(self.N):
                if dist[v] < INF:
                    potential[v] += dist[v]
            d = maxf - flow
            v = t
            while v != s:
                d = min(d, self.graph[prevv[v]][preve[v]]['cap'])
                v = prevv[v]
            flow += d
            cost += d * potential[t]
            v = t
            while v != s:
                e = self.graph[prevv[v]][preve[v]]
                e['cap'] -= d
                self.graph[v][e['rev']]['cap'] += d
                v = prevv[v]
        return flow, cost

# Build network
mcmf = MinCostFlow(N)

# Source -> students (each student 1 slot)
for s in students:
    mcmf.add_edge(SRC, 1 + idx_s[s], 1, 0)

# Topics -> sink (capacity per topic if specified; otherwise default)
for t in topics:
    cap = int(topic_capacity.get(t, MAX_PER_TOPIC_DEFAULT))
    mcmf.add_edge(1 + S + idx_t[t], SNK, cap, 0)

# Student -> topic edges with cost (1,2,3)
for s, t, c in assignments:
    u = 1 + idx_s[s]
    v = 1 + S + idx_t[t]
    mcmf.add_edge(u, v, 1, c, data={'email': s, 'topic': t, 'cost': c})

# Solve
flow, total_cost = mcmf.flow(SRC, SNK, len(students))
if flow < len(students):
    # It may be normal if not enough capacity across topics; warn clearly.
    print(f"Warning: only {flow}/{len(students)} students assigned — likely insufficient topic capacity or invalid prefs.")

# Extract assignments
assigned_topic = {}
assigned_score = {}
for u in range(N):
    for e in mcmf.graph[u]:
        if e.get('orig_cap', 0) > 0 and e.get('data') and e['cap'] == 0:
            d = e['data']
            assigned_topic[d['email']] = d['topic']
            assigned_score[d['email']] = d['cost']

students_and_preferred_topics['assigned_topic'] = students_and_preferred_topics['email_norm'].map(assigned_topic)
students_and_preferred_topics['assigned_score'] = students_and_preferred_topics['email_norm'].map(assigned_score)

print(students_and_preferred_topics[['email','assigned_topic','assigned_score']].head(10))
print(f"flow returned = {flow}  (target {len(students)})")
print(f"total_cost = {total_cost}")

# Students with no feasible (student, topic) edges
feasible_students = {email for email,_,_ in assignments}
missing = set(students) - feasible_students
if missing:
    print("Students with no feasible preferences:", sorted(missing)[:10], "… (truncated)")


#%% Language Compatibility Check and Assignment
# Case-insensitive, strips whitespace; tiny normalizer to harmonize common variants.

def split_langs(s):
    if not isinstance(s, str):
        return []
    return [lang.strip() for lang in re.split(r'[;,]', s) if lang.strip()]

# Normalize a few common labels (extend as needed)
LANG_MAP = {
    'en': 'English', 'eng': 'English', 'english': 'English',
    'nl': 'Dutch',   'dut': 'Dutch',   'dutch': 'Dutch',
    'fr': 'French',  'fra': 'French',  'french': 'French',
    'de': 'German',  'ger': 'German',  'german': 'German',
}

def norm_lang_list(xs):
    out = []
    for x in xs:
        key = x.strip().lower()
        out.append(LANG_MAP.get(key, x.strip().title()))
    return out

# Build topic -> allowed supervision languages
if 'supervision_languages' not in available_thesis_topics.columns:
    raise KeyError("Expected 'supervision_languages' in available_thesis_topics")

supervision_map = {
    row['proposed_thesis_topic']: norm_lang_list(split_langs(row['supervision_languages']))
    for _, row in available_thesis_topics.iterrows()
}

def language_sanity(row) -> str:
    score = row.get('assigned_score')
    topic = row.get('assigned_topic')
    if pd.isna(score) or pd.isna(topic):
        return "NOK"
    lang_col = f"topic_{int(score)}_language"
    student_langs = norm_lang_list(split_langs(row.get(lang_col, "")))
    allowed = supervision_map.get(topic, [])
    return "OK" if any(lang in allowed for lang in student_langs) else "INVALID TOPIC-LANGUAGE COMBINATION"

def pick_language(row):
    if row['sanity_check'] != "OK":
        return None
    score = int(row['assigned_score'])
    student_langs = norm_lang_list(split_langs(row.get(f"topic_{score}_language", "")))
    allowed = supervision_map.get(row['assigned_topic'], [])
    for lang in student_langs:
        if lang in allowed:
            return lang
    return None

students_and_preferred_topics['sanity_check'] = students_and_preferred_topics.apply(language_sanity, axis=1)
students_and_preferred_topics['assigned_language'] = students_and_preferred_topics.apply(pick_language, axis=1)

print(students_and_preferred_topics[[
    'full_name','email','assigned_topic','assigned_score','sanity_check','assigned_language'
]].head(10))


#%% Final Output: Assigned Topics with Language Sanity Check
thesis_topics_assigned_to_students = students_and_preferred_topics[[
    'full_name', 'email', 'assigned_topic', 'assigned_language', 'sanity_check'
]].copy()

thesis_topics_assigned_to_students['daily_supervisor'] = ''
thesis_topics_assigned_to_students['daily_supervisor_email'] = ''
thesis_topics_assigned_to_students['promotor'] = ''
thesis_topics_assigned_to_students['promotor_email'] = ''


print(thesis_topics_assigned_to_students.head(10))


#%% Save all files in Python and Excel
save_path = os.path.join(directory, 'thesis_topics_assigned_to_students.pkl')
thesis_topics_assigned_to_students.to_pickle(save_path)
print(f"Saved pickle to: {save_path}")

excel_path = os.path.join(directory, 'thesis_topics_assigned_to_students.xlsx')
thesis_topics_assigned_to_students.to_excel(excel_path, index=False)
print(f"Saved Excel to: {excel_path}")

