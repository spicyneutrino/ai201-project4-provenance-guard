# Provenance Guard

A Flask API that classifies submitted text as AI-generated or human-written, returns confidence scores and transparency labels, handles creator appeals, enforces rate limiting, and maintains a structured audit log.

## Architecture Overview

**Submission flow:** A `POST /submit` request arrives with a text body and creator ID. The system runs two independent detection signals in sequence: first the Groq LLM signal (a remote call to `llama-3.3-70b-versatile` that returns a probability float), then a local stylometric analysis (sentence length variance, type-token ratio, punctuation density). The two scores are combined using a weighted average (60% LLM, 40% stylometric) to produce a `confidence` value between 0 and 1. That score is mapped to one of three attribution labels (`likely_human`, `uncertain`, `likely_ai`) along with a human-readable `label_text`. The result is written as a JSON line to `audit_log.json` and returned to the caller.

**Appeal flow:** A `POST /appeal` request supplies a `content_id` (from a prior submission) and the creator's written reasoning. The system looks up the `content_id` in the in-memory store (404 if missing), updates its status to `under_review`, and appends a new audit log entry preserving the original classified entry unchanged. This creates an auditable chain: one entry for the original classification, one for the appeal.

## Detection Signals

| Signal | What it measures | Why chosen | What it misses |
|---|---|---|---|
| **LLM Semantic** (Groq `llama-3.3-70b-versatile`) | Semantic patterns: hedging language, structural uniformity, absence of personal voice | Captures meaning-level AI tells that statistics cannot | Polished human writing (academic, formal) mimics AI patterns and will score high |
| **Stylometric Heuristics** (pure Python) | Surface statistics: sentence length variance, lexical diversity (TTR), punctuation density | Fast, deterministic, no API dependency, catches structural uniformity | Formal academic prose naturally has low variance and low punctuation; will over-flag human writers |

## Confidence Scoring

**Formula:**
```
combined_score = (0.60 × llm_score) + (0.40 × stylometric_score)
```

**Why 60/40?** The LLM captures semantics — it can tell when a sentence *reads* like AI even if its length and word choice look normal. The stylometric signal provides a structural sanity check that is fast and deterministic. The LLM signal is weighted higher because semantic judgment is more reliable than surface statistics for distinguishing AI from polished human writing, but 40% stylometric ensures the LLM's occasional API failures (which fall back to 0.5) don't dominate.

**Example inputs (scores from live smoke test):**

| Input | Confidence | Attribution |
|---|---|---|
| "Artificial intelligence represents a transformative paradigm shift in modern society. It is important to note that while the benefits of AI are numerous, it is equally essential to consider the ethical implications. Furthermore, stakeholders across various sectors must collaborate to ensure responsible deployment." | 0.715 | likely_ai |
| "ok so i finally tried that new ramen place downtown and honestly? underwhelming. the broth was fine but they put WAY too much sodium in it and i was thirsty for like three hours after. my friend got the spicy version and said it was better. probably wont go back unless someone drags me there" | 0.3587 | uncertain |

**Threshold validation approach:** The three thresholds (< 0.35 = `likely_human`, 0.35–0.65 = `uncertain`, > 0.65 = `likely_ai`) were validated empirically: the AI text above should score > 0.65 and the human text above should score < 0.35. If either lands in `uncertain`, it signals the weights or thresholds need adjustment.

## Transparency Label Variants

| Attribution | Exact label text |
|---|---|
| `likely_human` | "This content shows strong indicators of human authorship. The writing style reflects the natural variation and personal voice consistent with human writing." |
| `uncertain` | "Our system was unable to confidently determine whether this content was written by a human or AI. This does not indicate a violation — many writing styles fall in this range. No action has been taken." |
| `likely_ai` | "This content shows strong indicators of AI generation. The writing style appears notably uniform and lacks the natural variation typical of human authors. If you wrote this yourself, you can submit an appeal below." |

## Rate Limiting

- `POST /submit`: **10 per minute**, **50 per day** (per IP)

**Reasoning:** Legitimate writers submit a few drafts per session — 10/minute is generous for that use case while blocking automated flood attacks. 50/day caps bulk programmatic use: a creator working hard all day might submit 20–30 drafts; 50 gives double that headroom. These limits are per-IP, so multiple users on the same platform share their own quotas.

## Known Limitations

**Formal academic writing is systematically misclassified.** A dissertation paragraph with uniform sentence lengths, specialized vocabulary, and minimal punctuation will score high on both signals — low variance triggers the stylometric AI score, and the LLM recognizes the formal register as AI-like. This is a false positive with no algorithmic fix at current signal design; the appeals path is the intended mitigation.

## Spec Reflection

**One way the spec helped:** The locked threshold values (0.35 / 0.65) and exact formula weights (0.60 / 0.40) eliminated design decisions that would otherwise require empirical tuning. Having them fixed meant implementation could proceed directly to coding without a calibration phase.

**One divergence and why:** The spec lists `groq==0.15.0` and `python-dotenv==1.0.1` as exact pins in `requirements.txt`, but `uv add` resolved newer compatible versions (`groq>=1.5.0`, `python-dotenv>=1.2.2`). The pinned versions in `requirements.txt` are kept as the spec requires for reproducibility documentation, but the actual installed versions in `pyproject.toml` are the resolved newer ones since the API surface used (`.chat.completions.create`) is stable across versions.

## AI Usage

1. **app.py generation:** Provided the full CLAUDE.md locked spec (Detection Signals, Confidence Combining, Thresholds, Audit Log schema, API Endpoints, factory pattern contract) as input. Requested a complete `app.py` implementation. Verified output by checking each formula coefficient against the spec line by line, confirming the Groq prompt text matched the spec verbatim, and validating the audit log entry schema field by field.

2. **planning.md generation:** Provided the complete spec sections plus the required planning.md outline (8 required topics). Requested substantive analysis — not just restatement of spec values but explanation of *why* thresholds were chosen and *how* signals fail. Revised the edge case section to add the short-text handling description after reviewing that the implementation defaults variance to 1.0 for fewer than 2 sentences, which was an implementation decision not explicit in the spec.
