# cm — Company Name Matching

A company name matching system that finds the best match for a given company name against a reference list. It combines deterministic scoring (token overlap, fuzzy similarity, acronym detection) with optional semantic embeddings and LLM arbitration via Google Gemini on Vertex AI.

## How It Works

The matcher runs a 4-stage pipeline for each input name:

### Stage 1: Candidate Generation

Narrows down the full reference list to a manageable set of candidates using two strategies:

- **Lexical blocking** — groups names by shared n-gram keys and retrieves candidates that share blocking keys with the query.
- **Embedding ANN** (when Gemini is enabled) — computes vector embeddings for all names using `text-embedding-004`, then retrieves the nearest neighbors by cosine similarity. This catches semantic matches that lexical blocking would miss (e.g. abbreviations, translations).

### Stage 2: Scoring

Each candidate is scored against the query using a weighted combination of:

| Feature | Weight | Description |
|---------|--------|-------------|
| Token overlap | 0.35 | Jaccard-style overlap of core tokens |
| Fuzzy similarity | 0.30 | RapidFuzz token-sort ratio |
| Acronym signal | 0.20 | Detects when one name is an acronym of the other |
| Semantic similarity | 0.15 | Cosine similarity of embeddings (0 if disabled) |

Penalties are applied for numeric mismatches and very short names.

### Stage 3: Decision Bands

The top-scored candidate is classified into one of three decisions:

- **MATCH** — score >= 0.92 and margin over runner-up >= 0.06
- **NO_MATCH** — score <= 0.75
- **REVIEW** — everything in between (ambiguous)

### Stage 4: LLM Arbitration (optional)

When Gemini is enabled, REVIEW cases are sent to `gemini-2.0-flash` for a second opinion. The LLM receives structured evidence (original names, tokens, feature scores) and returns a JSON verdict (`SAME`, `DIFFERENT`, or `UNSURE` with a confidence score). Gating rules prevent wasteful calls:

- Both sides must have at least 2 core tokens (or the call is skipped)
- Numeric conflicts are never sent to the LLM
- A global call cap (default 50) limits total LLM usage per run

## Setup

```bash
uv sync
```

### Gemini / Vertex AI Authentication

The Gemini providers use Vertex AI with Application Default Credentials (ADC). No API key is needed — authenticate with `gcloud auth application-default login`:

```bash
# One-time: install gcloud CLI
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth application-default login

# Set your GCP project
gcloud config set project <YOUR_PROJECT_ID>
```

The project is resolved from (in order):
1. `GOOGLE_CLOUD_PROJECT` environment variable
2. `gcloud config get-value project`

The location defaults to `us-central1` (override with `GOOGLE_CLOUD_LOCATION`).

## Usage

```bash
# Full pipeline with Gemini (embeddings + LLM arbitration)
uv run cm match

# Deterministic only (no Gemini calls)
uv run cm match --no-gemini

# Group-based matching (deduplicates identical A names first)
uv run cm match --group

# Custom file paths
uv run cm match --top path/to/top.xlsx --cup path/to/cup.xlsx --output results.xlsx
```

### Input Files

- `--top` — Excel file with company names to match in column `A`
- `--cup` — Excel file with reference names in column `CUP_NAME` (and `CUP_ID` for output)

### Output

An Excel file with columns:

| Column | Description |
|--------|-------------|
| A_name | Original input name |
| matched_CUP_NAME | Best match from reference list (if MATCH) |
| matched_CUP_ID | CUP_ID of the matched reference |
| decision | MATCH, NO_MATCH, or REVIEW |
| score | Composite similarity score (0–1) |
| runner_up_score | Score of the second-best candidate |
| reasons | Scoring breakdown |

### Other Commands

```bash
# Find duplicate names in both input files
uv run cm dupes
```

## Programmatic Usage

```python
from cm import Matcher, MatchConfig, GeminiEmbeddingProvider, GeminiLLMProvider
from cm.gemini import _make_client

client = _make_client()
matcher = Matcher(
    config=MatchConfig(),
    embedding_provider=GeminiEmbeddingProvider(client),
    llm_provider=GeminiLLMProvider(client),
)

matcher.preprocess_b(["Acme Corp", "Globex Inc", ...])
result = matcher.match_one("ACME Corporation")
print(result.decision, result.score)
```
