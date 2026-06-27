# Clario — AI Insurance Claim Verification

**Clario** is a multimodal AI pipeline that verifies insurance damage claims by analysing customer conversations and photographic evidence in a single Gemini API call. Built during the HackerRank Orchestrate Hackathon (June 2026).

---

## What it does

An insurer receives a claim conversation (text) and one or more photos. Clario reads both together and returns a structured verdict:

- **Supported** — images confirm the damage described
- **Contradicted** — images show no damage, or contradict the claim
- **Not Enough Information** — images are blurry, manipulated, or inconclusive

Along with the verdict, Clario outputs a fraud risk score, confidence score, severity level, detected language, and a list of specific risk flags.

---

## Key Features

- **Single-call architecture** — one Gemini 2.5 Flash call per claim handles vision + reasoning together; no chaining, no extra latency
- **Prompt injection detection** — flags and ignores instructions embedded inside claim text or image overlays
- **Multilingual** — handles English, Hindi, Hinglish, Spanish, Chinese-English natively; no translation step
- **Fraud risk scoring** — 0–100 score computed from risk flags, claim history, and image quality signals
- **Confidence scoring** — 0–100 score based on evidence quality and image validity
- **Demo mode** — four pre-verified real cases (car, laptop, package) run instantly without an API key

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Vision + Reasoning | Gemini 2.5 Flash (`google-genai`) |
| UI | Streamlit |
| Pipeline | Python — agent, vision client, prompt builder, data loader |
| Data | HackerRank Orchestrate dataset — 44 test claims |

---

## Project Structure

```
clario/
├── code/
│   ├── app.py              ← Streamlit UI (run this)
│   ├── agent.py            ← Claim review agent — orchestrates one call per claim
│   ├── vision.py           ← Gemini Vision client with retry + JSON parsing
│   ├── prompts.py          ← Prompt templates and output schema
│   ├── data_loader.py      ← Dataset loader, ClaimRecord, ImageRef
│   └── main.py             ← Batch pipeline runner
├── dataset/
│   ├── claims.csv
│   ├── evidence_requirements.csv
│   └── images/
│       ├── sample/         ← case_001 to case_020
│       └── test/           ← case_001 to case_056
├── evaluation/
│   ├── main.py
│   ├── evaluation_metrics.json
│   └── evaluation_report.md
├── add_features.py         ← Post-processing: fraud score, confidence, language
├── .gitignore
└── README.md
```

---

## Quickstart

```bash
# 1. Clone
git clone https://github.com/neerajashah/clario
cd clario

# 2. Set up environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt

# 3. Add API key
echo "GEMINI_API_KEY=your_key_here" > .env

# 4. Run
streamlit run code/app.py
```

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com).

---

## Output Schema

| Field | Values |
|-------|--------|
| `claim_status` | `supported` / `contradicted` / `not_enough_information` |
| `claim_status_justification` | Plain-language explanation |
| `evidence_standard_met` | `true` / `false` |
| `evidence_standard_met_reason` | Why evidence was or wasn't sufficient |
| `issue_type` | `dent` / `crack` / `broken_part` / `crushed_packaging` / `none` / `unknown` |
| `object_part` | Part of object claimed (e.g. `door`, `screen`, `hood`) |
| `supporting_image_ids` | Which images supported the verdict |
| `valid_image` | `true` / `false` |
| `severity` | `none` / `low` / `medium` / `high` / `unknown` |
| `risk_flags` | Semicolon-separated list (see below) |
| `fraud_risk_score` | 0–100 |
| `confidence_score` | 0–100 |
| `claim_language` | `en` / `hi` / `hi-en` / `es` / `zh-en` / etc. |

### Risk Flags

`possible_manipulation` · `non_original_image` · `text_instruction_present` · `claim_mismatch` · `user_history_risk` · `wrong_object` · `blurry_image` · `low_light_or_glare` · `damage_not_visible` · `cropped_or_obstructed` · `manual_review_required`

---

## Demo Cases

The app's Demo tab shows four real pipeline results — no API key needed:

| Case | Object | Verdict | Why it's interesting |
|------|--------|---------|----------------------|
| case_049 | Car — Rear Bumper | Contradicted | Prompt injection detected in submitted image |
| case_006 | Car — Hood | Not Enough Information | Blurry watermarked image; 5 risk flags |
| case_050 | Laptop — Screen | Contradicted | Multilingual claim (Chinese-English); no damage found |
| case_052 | Package — Corner | Supported | Clear evidence; low fraud risk |

---

## Deploying on Streamlit Cloud


1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Set main file path: `code/app.py`
4. Under **Advanced settings → Secrets**, add:
   ```
   GEMINI_API_KEY = "your_key_here"
   ```
5. Deploy

---

*Built by [Neeraja Shah](https://github.com/neerajashah) · HackerRank Orchestrate Hackathon, June 2026*