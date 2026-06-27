# Damage Claim Verification System

Multimodal evidence review for insurance damage claims (cars, laptops, packages). The system reads claim conversations and images, then produces structured verdicts for each row in `dataset/claims.csv`.

Built for **HackerRank Orchestrate** (June 2026).

---

## Quick start

```bash
# From repo root (Windows)
venv\Scripts\python.exe code\main.py

# Smoke test — first 3 claims only
venv\Scripts\python.exe code\main.py --limit 3

# Evaluate on labeled sample set
venv\Scripts\python.exe code\evaluation\main.py
```

Output is written to `output.csv` at the repo root (14 columns, exact schema order).

---

## Requirements

| Dependency | Purpose |
|---|---|
| Python 3.14+ | Runtime |
| `google-generativeai` | Gemini 2.0 Flash API |
| `pandas` | CSV I/O |
| `pillow` | Image loading |
| `python-dotenv` | Load `GEMINI_API_KEY` from `.env` |

Install (if needed):

```bash
python -m venv venv
venv\Scripts\pip install google-generativeai pandas pillow python-dotenv
```

---

## Environment variables

Create `.env` at the repo root (never commit this file):

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash   # optional, this is the default
```

---

## Project layout

```text
code/
├── main.py              # CLI entry point → output.csv
├── data_loader.py       # CSV parsing, image path resolution, dataclasses
├── prompts.py           # Gemini prompt templates + JSON schemas
├── vision.py            # Gemini API wrapper (retry, JSON parsing)
├── agent.py             # Pipeline orchestration + output normalization
├── README.md            # This file
└── evaluation/
    ├── main.py          # Sample-set metrics + strategy comparison
    ├── evaluation_report.md   # Operational analysis template
    ├── evaluation_metrics.json
    └── strategy_comparison.csv
```

Dataset (provided, do not modify structure):

```text
dataset/
├── claims.csv              # Test input (44 rows)
├── sample_claims.csv       # Labeled dev set (20 rows)
├── user_history.csv
├── evidence_requirements.csv
└── images/
    ├── test/
    └── sample/
```

---

## How it works

### Three-stage pipeline

1. **Claim extraction** (text) — Parse the conversation; handle English/Hindi/Hinglish; detect prompt injection.
2. **Per-image analysis** (vision) — One Gemini call per image; assess damage, quality, risk flags, and per-image support.
3. **Aggregation** (text) — Combine per-image results with evidence requirements and user history into a final verdict.

Images are the **primary source of truth**. User history adds risk context only and cannot override clear visual evidence.

### Resilience

- Exponential backoff on 429 / transient API errors (`vision.py`)
- Fallback verdicts when extraction or aggregation fails (`agent.py`)
- Missing images and per-image failures are isolated so the batch continues

---

## Running inference

```bash
venv\Scripts\python.exe code\main.py [options]
```

| Flag | Default | Description |
|---|---|---|
| `--input` | `dataset/claims.csv` | Input claims file |
| `--output` | `output.csv` | Predictions output path |
| `--repo-root` | auto-detected | Repo root containing `dataset/` |
| `--limit` | all rows | Process only first N claims |

Example — custom paths:

```bash
venv\Scripts\python.exe code\main.py ^
  --input dataset\claims.csv ^
  --output output.csv
```

The CLI prints per-claim progress and usage stats (model calls, images sent, tokens, retries).

---

## Evaluation

Compare two strategies on `sample_claims.csv` (temperature 0.1 vs 0.5):

```bash
venv\Scripts\python.exe code\evaluation\main.py
```

Score an existing predictions file without API calls:

```bash
venv\Scripts\python.exe code\evaluation\main.py ^
  --skip-live ^
  --predictions output.csv
```

| Flag | Description |
|---|---|
| `--limit N` | Evaluate first N sample rows only |
| `--output-dir` | Where to write metrics (default: `code/evaluation/`) |
| `--predictions` | Score a CSV instead of running live strategies |
| `--skip-live` | Skip Gemini calls; requires `--predictions` |

Artifacts:

- `strategy_comparison.csv` — accuracy by field and strategy
- `evaluation_metrics.json` — full metrics
- `predictions_<strategy>.csv` — dev-set predictions per strategy

Fill in `evaluation/evaluation_report.md` after live runs with observed token usage, cost, and latency.

---

## Output schema

`output.csv` columns (in order):

```text
user_id, image_paths, user_claim, claim_object,
evidence_standard_met, evidence_standard_met_reason,
risk_flags, issue_type, object_part,
claim_status, claim_status_justification,
supporting_image_ids, valid_image, severity
```

Key enums:

- `claim_status`: `supported` | `contradicted` | `not_enough_information`
- `risk_flags`: semicolon-separated from allowed list, or `none`
- `supporting_image_ids`: semicolon-separated image IDs (e.g. `img_1`), or `none`
- Booleans: `true` / `false` as strings

---

## Module reference

| Module | Responsibility |
|---|---|
| `data_loader.py` | Load claims, sample labels, user history, evidence rules; resolve `dataset/images/` paths |
| `prompts.py` | System instruction, stage prompts, JSON response schemas |
| `vision.py` | `GeminiVisionClient` — API calls, image upload, retry, `UsageStats` |
| `agent.py` | `ClaimReviewAgent` — end-to-end review, enum normalization, fallbacks |
| `main.py` | CLI and `process_claims()` for batch inference |
| `evaluation/main.py` | Metrics, strategy comparison, artifact export |

---

## Image path note

CSV paths use `images/test/...` but files live under `dataset/images/test/...`. `data_loader.py` resolves both layouts automatically while preserving the original path string for output.

---

## Submission checklist

- [ ] `GEMINI_API_KEY` set and quota available for full test run
- [ ] `venv\Scripts\python.exe code\evaluation\main.py` — review sample accuracy
- [ ] `venv\Scripts\python.exe code\main.py` — generate `output.csv` (44 rows)
- [ ] Update `evaluation/evaluation_report.md` with live stats
- [ ] Zip `code/` (exclude `venv/`, `__pycache__/`, `.env`)
- [ ] Upload `output.csv` and chat transcript per HackerRank instructions

---

## Operational notes

- **Calls per claim:** `2 + number_of_images` (extract + N vision + aggregate)
- **Test set estimate:** 44 claims, 82 images → ~170 API calls
- **Rate limits:** Sequential processing with retry backoff; see `evaluation_report.md` for TPM/RPM discussion
- If the API quota is exhausted, the system still completes but returns fallback rows with `manual_review_required`
