# Final Implementation Document — Company Name Matching (10k × 10k) with Optional Gemini Embeddings and Rare LLM Arbitration

## 0) What changed after reviewing the third-party plan (the “gem”)

The third-party plan largely aligns with the proposed architecture. The main improvements worth explicitly adopting:

1) **Explicit candidate-reduction target**: design blocking to reliably shrink 10k×10k to ~10k×50–150 comparisons (and cap at ~500). This keeps performance predictable and prevents “candidate explosions.”

2) **Tighter LLM gating rule set**: require *all* of:
   - ambiguous band  
   - no numeric conflict  
   - at least one side has ≥2 core tokens  
   - only top K candidates (K=1–3)  
   - margin below threshold  
   This makes “LLM rarely called” enforceable, not just aspirational.

3) **Structured `NormalizedName.meta.warnings`**: store warnings (e.g., “stripping reverted due to short core”, “collision acronym”) to drive debugging and future tuning.

Everything below integrates these improvements into a single spec.

---

## 1) Objective

Match companies across two lists:

- List A: ~10,000 names
- List B: ~10,000 names

For each `A[i]`, output:

- `MATCH` to a specific `B[j]`, or
- `NO_MATCH`, or
- `REVIEW` (optional “human/secondary signal needed” state)

Constraints:
- No all-pairs (100M) scoring
- High precision by default
- Deterministic matching is the primary engine
- Gemini embeddings are optional, used safely (candidate gen + small scoring feature)
- LLM arbitration is optional and must be called very rarely (target <0.5% of A)

---

## 2) High-Level Architecture

### Stage 0 — Offline preprocessing (A and B)
- Normalize all names into stable representations (`NormalizedName`)
- Build lexical blocking indices for B
- Optional: compute embeddings for B and build ANN index

### Stage 1 — Candidate generation (per A item)
- Use blocking keys (exact core, prefixes, acronym) to retrieve candidate IDs from B
- Optional: union in ANN neighbors from embeddings
- Deduplicate + cap candidates (hard limit)

### Stage 2 — Deterministic scoring (per candidate pair)
- Compute similarity features + penalties
- Combine into score ∈ [0,1]
- Sort candidates by score

### Stage 3 — Decision logic + margin rule
- `MATCH` if best score is high and margin over runner-up is sufficient
- `NO_MATCH` if best score is low
- otherwise `AMBIGUOUS` -> optional LLM arbiter (strict gating)

### Stage 4 — Rare LLM arbitration (only for knife-edge)
- Evaluate top K candidates only (K=1–3)
- Cache outcomes
- Enforce global and per-item call caps

---

## 3) Package Layout

```
bizmatch/
  config.py
  types.py
  normalize.py
  designators.py
  acronyms.py
  embeddings.py          # Gemini embedding provider + caching
  index.py               # lexical + ANN indices, candidate retrieval
  scoring.py             # deterministic features + score
  matcher.py             # orchestration + decision bands
  llm_arbiter.py         # rare arbitration with strict gating + caching
  io.py                  # CSV/JSONL input + output
  evaluation.py          # labeled evaluation + error analysis
data/
  designators_global.txt
  designator_aliases.json
  stopwords.txt
  acronym_collision.txt
tests/
  unit tests + labeled fixtures
```

---

## 4) Core Types (types.py)

### 4.1 `NormalizedName`
Fields:
- `original: str`
- `normalized_text: str` (NFKC + casefold)
- `raw_tokens: list[str]`
- `core_tokens: list[str]`
- `core_string: str` (`" ".join(core_tokens)`)
- `acronym: str | None`
- `numeric_tokens: list[str]`
- `keys: dict[str, str]` (blocking keys)
- `meta: dict` including:
  - `removed_designators: list[str]`
  - `warnings: list[str]`  ✅ (adopted “gem”)
  - `notes: dict` (optional)

### 4.2 `Candidate`
- `b_id: int`
- `sources: set[str]` (e.g., `{"k_core","k_prefix2","embedding"}`)

### 4.3 `ScoredCandidate`
- `b_id: int`
- `score: float`
- `features: dict[str, float|bool|str]`
- `reasons: list[str]`

### 4.4 `MatchResult`
- `a_id: int`
- `a_name: str`
- `b_id: int | None`
- `b_name: str | None`
- `decision: "MATCH" | "NO_MATCH" | "REVIEW"`
- `score: float`
- `runner_up_score: float | None`
- `margin: float | None`
- `used_llm: bool`
- `reasons: list[str]`
- `debug: dict` (optional; top candidates, warnings)

---

## 5) Normalization (normalize.py)

### 5.1 Input/Output
Input: raw company name `str`  
Output: `NormalizedName`

### 5.2 Rules
1. Unicode normalize: `unicodedata.normalize("NFKC", s)`
2. Casefold: `s.casefold()`
3. Symbol replacement:
   - `& -> and`
   - optionally `+ -> and`
4. Punctuation normalization:
   - convert punctuation to spaces
   - preserve digits
   - collapse whitespace
5. Tokenize by spaces
6. Token canonicalization:
   - apply alias map (e.g., `inc.` -> `inc`, `l.l.c` -> `llc`)
7. Save `raw_tokens`
8. Strip legal designators (see section 6)
9. Safety rule:
   - **never strip** if resulting tokens < 2  
   - record warning: `designator_strip_reverted_short_core`
10. Extract `numeric_tokens`:
   - include standalone digit tokens and numeric substrings (`54`, `2023`, `3m`->`3` optional)
11. Acronym generation (see section 7)
12. Generate blocking keys (see section 8)
13. Populate meta warnings:
   - collision acronym
   - single-token core
   - strip reverted, etc.

---

## 6) Legal Designator Handling (designators.py)

### 6.1 Designators
Examples:
- `inc, incorporated, corp, corporation`
- `ltd, limited, plc`
- `llc, llp, lp`
- `gmbh, ag, sa, sas, sarl, bv, nv, oy, ab, kk, pty`

### 6.2 Rules
- Token-level matching only (no substrings)
- Default stripping is suffix-only (configurable)
- Prefix stripping only if explicitly enabled
- Maintain alias map (`inc.` → `inc`, `co.` → `co`)

### 6.3 Safety
- If stripping drops tokens below 2, revert and warn

---

## 7) Acronym Handling (acronyms.py)

### 7.1 Generation
- Initialism from `core_tokens`: first letter of each token -> `ibm`
- Normalize acronym-like inputs:
  - `I.B.M.` and `I B M` → `ibm`

### 7.2 Safety
- Minimum length ≥ 3 (config)
- Maintain collision list (e.g., `abc`, `aaa`, etc.)
- **Acronym match is never sufficient alone**; it only boosts score.
- If acronym is collision:
  - add meta warning: `collision_acronym`
  - use weak acronym feature in scoring

---

## 8) Candidate Generation (Blocking + Optional ANN) (index.py)

### 8.1 Goal
Reduce 10k×10k to ~10k×50–150 comparisons, with a hard cap per A.

### 8.2 Blocking keys
Compute from `core_tokens`:
- `k_core`: exact `core_string`
- `k_prefix2`: first 2 core tokens joined
- `k_prefix3`: first 3 core tokens joined
- `k_acronym`: acronym (if present; collision-aware)
Optional:
- `k_first`: first core token (use carefully; can explode candidates)

### 8.3 Lexical index
Build inverted index for B:
- `dict[str, set[int]]` mapping key -> B IDs
Populate with all keys above.

### 8.4 Candidate retrieval per A item
Union candidates from all available keys, tracking sources.
Enforce caps:
- `max_candidates_total` (recommended 500)
- optional per-source caps:
  - `max_candidates_lexical` (e.g., 300)
  - `max_candidates_embedding` (e.g., 200)

### 8.5 Optional embeddings-based candidates
- Build embeddings for all B `core_string`
- ANN query for A embedding to get top 50–200 neighbors
- Union with lexical candidates
- Embedding candidates are for recall; they do not override deterministic logic.

---

## 9) Deterministic Scoring (scoring.py)

### 9.1 Features (per A,B candidate pair)
1. **Token overlap**
   - overlap coefficient on `core_tokens`:
     - `|A∩B| / min(|A|,|B|)`
2. **Fuzzy similarity**
   - `rapidfuzz.fuzz.WRatio(a.core_string, b.core_string) / 100`
3. **Acronym relation**
   - exact acronym match
   - acronym ↔ initialism match
   - collision acronym treated as weak
4. **Numeric consistency**
   - mismatch => strong penalty
   - one-side-only numbers => mild penalty (configurable)
5. **Short-name guardrail**
   - if min core token count == 1 => heavy penalty
   - also down-weight/disable semantic feature
6. **Semantic similarity (optional)**
   - Gemini embedding cosine similarity
   - feature only (never decisive alone)

### 9.2 Recommended weights (starting point)
| Feature             | Weight |
|--------------------|--------|
| Token overlap      | 0.35   |
| Fuzzy similarity   | 0.30   |
| Acronym signal     | 0.20   |
| Semantic similarity| 0.15   |
| Penalties          | subtract |

Constraint: `semantic` must not push a pair across `T_high` without corroborating lexical evidence.

### 9.3 Reasons
Add reason codes, e.g.:
- `core_overlap_high`, `fuzzy_high`
- `acronym_match_strong`, `acronym_match_weak`
- `numeric_mismatch`
- `short_name_guardrail`
- `semantic_boost`

---

## 10) Decision Bands + Margin Rule (matcher.py)

After scoring, sort candidates by `score desc`.

### 10.1 Thresholds (example defaults; tune on data)
- `T_high = 0.92`
- `T_low  = 0.75`
- `margin = 0.06`

### 10.2 Rules
- **MATCH**
  - best ≥ `T_high`
  - and (best − second_best) ≥ `margin`
- **NO_MATCH**
  - best ≤ `T_low`
- **AMBIGUOUS**
  - otherwise (eligible for optional LLM arbitration)

Notes:
- If no candidates are found -> `NO_MATCH` (unless policy says `REVIEW`)

---

## 11) LLM Integration (Rare, Controlled) (llm_arbiter.py)

### 11.1 Purpose
Resolve edge cases that are:
- not confidently matched
- not confidently rejected
- lexically ambiguous but semantically plausible

Target usage: **<0.5%** of A items.

### 11.2 When LLM is allowed (all must be true) ✅ (adopted “gem”)
1) Decision band is `AMBIGUOUS`  
2) **No numeric conflict**  
3) At least one side has `core_tokens ≥ 2`  
4) Only consider **top K candidates** (K = 1–3)  
5) `(best − second_best) < margin`  
6) Global and per-item call caps are not exceeded  
7) If both sides are single-token cores, LLM is forbidden (configurable)

### 11.3 LLM input schema
Send structured evidence:

```json
{
  "name_a_original": "...",
  "name_b_original": "...",
  "name_a_core": "...",
  "name_b_core": "...",
  "a_tokens": ["..."],
  "b_tokens": ["..."],
  "a_acronym": "...",
  "b_acronym": "...",
  "numeric_tokens_a": ["..."],
  "numeric_tokens_b": ["..."],
  "features": {
    "fuzzy": 0.88,
    "token_overlap": 0.67,
    "acronym_relation": "initialism|exact|none|collision",
    "embedding_cosine": 0.91,
    "deterministic_score": 0.86,
    "margin": 0.03
  }
}
```

### 11.4 LLM output schema (required)
```json
{
  "decision": "SAME|DIFFERENT|UNSURE",
  "confidence": 0.0,
  "reason": "short_label"
}
```

Mapping:
- SAME + confidence ≥ 0.75 -> `MATCH`
- DIFFERENT + confidence ≥ 0.75 -> `NO_MATCH`
- else -> `REVIEW`

### 11.5 Caching
Cache by stable key:
- `hash(a.core_string) + "::" + hash(b.core_string)`

---

## 12) Embeddings (Gemini) Specification (embeddings.py)

### 12.1 Usage
- Candidate generation: ANN neighbors for recall
- Optional scoring feature: cosine similarity (small weight)

### 12.2 Requirements
- Only embed `core_string`
- Aggressive caching keyed by `core_string`
- Batch embedding calls
- Persist embeddings for B to disk to avoid recompute (if repeated runs)

---

## 13) Inputs & Outputs (io.py)

### 13.1 Input
CSV (or JSONL) with one company name per row.
Optional `id` column; otherwise use row index.

### 13.2 Output
CSV/JSONL with:
- `a_id`, `a_name`
- `b_id`, `b_name` (nullable)
- `decision`
- `score`, `runner_up_score`, `margin`
- `used_llm`
- `reasons` (pipe-separated)
Optional debug:
- `warnings`
- `top_candidates` (JSON)

---

## 14) Evaluation & Tuning (evaluation.py)

### 14.1 Labeled evaluation set
Maintain `labeled_pairs.csv` with:
- `name_a,name_b,label` (1 match, 0 no-match)
Include tricky cases:
- Inc/Ltd stripping
- acronyms
- punctuation variants
- numeric mismatches
- short generic names

### 14.2 Metrics
- Precision / Recall / F1
- False positives grouped by reason codes
- Ambiguous rate and LLM call rate (must remain under caps)

### 14.3 Iteration loop
- Adjust designators, acronym collisions, weights, thresholds
- Add regression tests for each newly discovered failure

---

## 15) Acceptance Criteria

- Candidate generation reduces comparisons to ~50–150 per A on average
- Deterministic matching handles the vast majority of cases
- LLM usage:
  - <0.5% of A items in typical runs
  - hard-capped by config
  - fully cached
- All outputs are auditable via reasons + warnings
