# Evaluation Report — Multi-Modal Damage Claim Verification

> **Template:** Fill in `[TBD]` fields after running live evaluation and full test inference.
> Generated artifacts from `code/evaluation/main.py` should be pasted or summarized below.

---

## 1. System overview

| Item | Value |
|---|---|
| Model | Gemini 2.0 Flash (`gemini-2.0-flash`) |
| SDK | `google-generativeai` |
| Pipeline | 3-stage: claim extraction → per-image analysis → aggregation |
| Primary strategy | `primary_temp_0_1` (temperature 0.1) |
| Comparison strategy | `comparison_temp_0_5` (temperature 0.5) |
| Final strategy for `output.csv` | `[TBD — e.g. primary_temp_0_1]` |

### Architecture

```text
claims.csv row
    │
    ├─► Stage 1: Extract claim from transcript (text-only)
    │       • Hindi/Hinglish handling
    │       • Prompt-injection detection
    │
    ├─► Stage 2: Analyze each image separately (vision)
    │       • One Gemini call per image
    │       • Image quality / mismatch / authenticity flags
    │
    └─► Stage 3: Aggregate verdict (text-only)
            • Cross-check evidence_requirements.csv
            • Apply user_history.csv as risk context only
            • Output confidence → manual_review_required if < 0.65
```

---

## 2. Dataset sizes

| Split | Claims | Total images | Avg images/claim | Est. model calls (`2 + images`) |
|---|---:|---:|---:|---:|
| Sample (`sample_claims.csv`) | 20 | 29 | 1.45 | ~69 |
| Test (`claims.csv`) | 44 | 82 | 1.86 | ~170 |

> Model calls = 1 extraction + N image analyses + 1 aggregation per claim.

---

## 3. Strategy comparison (sample set)

Run:

```bash
venv\Scripts\python.exe code\evaluation\main.py
```

Then paste results from `code/evaluation/strategy_comparison.csv` or summarize here.

| Strategy | claim_status accuracy | issue_type | object_part | severity | Runtime (s) | Model calls | Total tokens |
|---|---:|---:|---:|---:|---:|---:|---:|
| `primary_temp_0_1` | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| `comparison_temp_0_5` | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |

### Observations

- **Primary (temp 0.1):** [TBD — e.g. more consistent enums, lower claim_status accuracy variance]
- **Comparison (temp 0.5):** [TBD — e.g. more varied justifications, slightly lower structured-field accuracy]
- **Selected for production:** [TBD — justify choice]

Full per-field metrics are in `code/evaluation/evaluation_metrics.json`.

---

## 4. Operational analysis

### 4.1 Model calls

| Phase | Sample (20 rows) | Test (44 rows) | Notes |
|---|---:|---:|---|
| Claim extraction | [TBD] / 20 | [TBD] / 44 | Text-only |
| Per-image analysis | [TBD] / 29 | [TBD] / 82 | One call per image |
| Aggregation | [TBD] / 20 | [TBD] / 44 | Text-only |
| **Total** | **[TBD] / ~69** | **[TBD] / ~170** | Sequential per claim |

### 4.2 Token usage (approximate)

Fill from CLI output after `code/main.py` and `code/evaluation/main.py`.

| Metric | Sample run | Test run (projected) | Assumption |
|---|---:|---:|---|
| Prompt (input) tokens | [TBD] | [TBD] | ~800 text / ~1,500 with image per vision call |
| Output tokens | [TBD] | [TBD] | ~200–400 JSON per call |
| **Total tokens** | **[TBD]** | **[TBD]** | Sum from `UsageStats` |

### 4.3 Images processed

| Split | Images sent to model | Missing/unreadable on disk |
|---|---:|---|
| Sample | [TBD] / 29 | [TBD] |
| Test | [TBD] / 82 | [TBD] |

### 4.4 Cost estimate (full test set)

**Pricing assumptions** (Gemini 2.0 Flash, check current rates at [ai.google.dev/pricing](https://ai.google.dev/pricing)):

| Component | Assumed rate |
|---|---|
| Input tokens | $0.10 / 1M tokens |
| Output tokens | $0.40 / 1M tokens |
| Images | Included in input tokenization |

| Estimate | Input tokens | Output tokens | Input cost | Output cost | **Total** |
|---|---:|---:|---:|---:|---:|
| Conservative | [TBD] | [TBD] | $[TBD] | $[TBD] | **$[TBD]** |
| Observed run | [TBD] | [TBD] | $[TBD] | $[TBD] | **$[TBD]** |

Example back-of-envelope (replace with observed stats):

- ~170 calls × ~2,000 avg tokens ≈ 340K total tokens
- At Flash rates → roughly **$0.05–$0.15** for the full test set (order-of-magnitude; update after live run)

### 4.5 Latency / runtime

| Run | Claims | Elapsed | Avg sec/claim | Notes |
|---|---:|---:|---:|---|
| Sample evaluation | 20 | [TBD] | [TBD] | Includes 2 strategy passes if comparing live |
| Test inference | 44 | [TBD] | [TBD] | Single strategy |
| Single-claim smoke | 1 | ~31s (fallback) | ~31s | Observed with API quota retries |

Bottleneck: sequential per-image calls (no batching). Dominant latency = network + vision encoding + retry backoff on 429.

---

## 5. Rate limits and resilience

### TPM / RPM considerations

| Limit type | Gemini 2.0 Flash free tier (typical) | Our exposure |
|---|---|---|
| RPM (requests/min) | [check current quota] | Up to ~4 calls/claim × claim throughput |
| TPM (tokens/min) | [check current quota] | Vision calls dominate input tokens |
| Daily quota | [check current quota] | 170 calls for full test set |

### Mitigations implemented

| Strategy | Location | Purpose |
|---|---|---|
| Exponential backoff + API `retry_delay` | `code/vision.py` | Handle 429 / transient errors |
| Max 4 retries per call | `code/vision.py` | Avoid infinite loops |
| Rule-based fallback verdict | `code/agent.py` | Continue batch if extraction/aggregation fails |
| Per-image error isolation | `code/agent.py` | One bad image does not crash the claim |
| Confidence → `manual_review_required` | `code/prompts.py`, `code/agent.py` | Escalate low-confidence cases |
| Sequential (non-batched) processing | `code/main.py` | Simpler rate-limit control; easier to debug |

### Not yet implemented (optional improvements)

- [ ] Response caching keyed by `(image_hash, prompt_version)`
- [ ] Inter-claim delay / adaptive throttling when 429 rate rises
- [ ] Parallel image analysis with bounded concurrency (e.g. 2–3 workers)
- [ ] Shorter error messages in fallback rows (avoid raw API dumps in CSV)

---

## 6. Error handling summary

| Failure mode | Behavior |
|---|---|
| API quota exhausted (429) | Retry up to 4×, then fallback verdict with `manual_review_required` |
| Missing image file | Synthetic per-image result with `damage_not_visible` |
| Per-image API error | Isolated error result; other images still processed |
| Extraction failure | Skip vision; return `not_enough_information` fallback |
| Aggregation failure | Rule-based merge of per-image results |

---

## 7. Reproduction checklist

```bash
# 1. Evaluate on labeled sample set (compares two temperatures)
venv\Scripts\python.exe code\evaluation\main.py

# 2. Score an existing predictions file without API calls
venv\Scripts\python.exe code\evaluation\main.py --skip-live --predictions output.csv

# 3. Generate final test predictions
venv\Scripts\python.exe code\main.py

# 4. Update this report with [TBD] values from CLI usage stats
```

### Files to attach / reference

- `code/evaluation/strategy_comparison.csv`
- `code/evaluation/evaluation_metrics.json`
- `code/evaluation/predictions_primary_temp_0_1.csv`
- `output.csv` (final test predictions)

---

## 8. Final strategy decision

**Strategy chosen for submission:** `[TBD]`

**Rationale:**

1. [TBD — e.g. highest claim_status accuracy on sample set]
2. [TBD — e.g. more stable enum outputs at lower temperature]
3. [TBD — e.g. acceptable cost/latency for 44-row test set]

---

*Last updated: [TBD — date after live runs complete]*
