# MINI PHASE 13 — RAG ANSWER ACCURACY, EVIDENCE VALIDATION AND QUALITY SCORING REPORT

**Heavy Vehicles Factory (HVF) / Armoured Vehicles Nigam Limited (AVNL)**  
*Intelligent SOP Document Intelligence & Revision Impact Analysis Assistant*  
**Date:** November 11, 2026  
**Automated Regression Suite:** **158 / 158 PASS (100% OK, 49.87s)**  
**30-Question Ground-Truth RAG Benchmark:** **28/30 Completed, 2/30 Timed Out (150s), 20/30 Passed (66.7% Overall Correctness)**

---

## 1. Executive Summary & Crucial Distinctions

Mini Phase 13 delivers two distinct, complementary quality assurance layers for the offline HVF/AVNL SOP Assistant:

1. **Per-Answer Automated Quality Assessment (`rag_evaluator.py`, UI & SQLite Persistence)**:
   - Audits every assistant response *only* against the actual retrieved SOP evidence and citations passed to the generator (never retrieves independent external data or alters the generated answer silently).
   - Computes weighted scores across 5 metrics (`Evidence Support` 40%, `Answer Relevance` 25%, `Completeness` 15%, `Citation Coverage` 10%, `Retrieval Quality` 10%) with strict deterministic technical safety guardrails for tolerances, dimensions, materials, load limits, calibration values, acceptance criteria, safety rules, and inspection protocols.
   - **Important Interpretation Notice**: Per-answer assessment scores are *automated evidence-alignment estimates*, NOT probabilities that an answer is objectively true in the physical world.
2. **Actual Manually Verified 30-Question Benchmark (`tests/rag_accuracy_benchmark.json` & `tests/run_rag_accuracy_benchmark.py`)**:
   - Executes the genuine local RAG pipeline (`FAISS` + `nomic-embed-text:latest` + `gemma-2b:latest`) across 30 manually verified questions spanning 10 categories from the 10-SOP corpus.
   - Measures empirical **Answer Correctness (`66.7%`)**, **Retrieval Precision@5 (`80.7%`)**, **Retrieval Recall@5 (`60.4%`)**, **Citation Correctness (`70.8%`)**, **Deterministic Faithfulness Rate (`46.4%`)**, **Hallucination Rate (`7.1%`)**, **Abstention Accuracy (`33.3%`)**, and **Intent Classification Accuracy (`64.3%`)**.

We explicitly do **not** claim 95% or 100% RAG accuracy; this report presents the exact empirical measurements, including failed cases, timed-out cross-revision prompts, and genuine system defects uncovered by the benchmark.

---

## 2. Original Benchmark Hang Root Cause Diagnosis & Fixes

### 2.1 Observed Symptom
During initial execution (`python tests/run_rag_accuracy_benchmark.py`), `B01–B03` finished in `0.03–0.05s`, followed by:
```text
[INFO] Successfully loaded FAISS index: 150 chunks from data\faiss_index
```
after which the process produced no further console output and appeared completely frozen.

### 2.2 Diagnosed Root Causes (Proven Empirically)
1. **Fast-Path vs. Full CPU Inference Transition (`B03 -> B04`)**:
   - `B01–B03` triggered the `BASIC_DEFINITION` local glossary lookup in `data/component_glossary.json` (`0.03–0.05s`, zero Ollama calls).
   - `B04` (*"What does a ceramic-hybrid bearing do?"*, `COMPONENT_FUNCTION`) entered the full RAG pipeline: embedding (`0.59–1.60s`), `build_component_evidence_context()` assembling a **20,680-character (~2,692-word / ~4,000-token)** prompt across 5 chunks and 8 component records, followed by synchronous Ollama CPU inference on `gemma-2b:latest` (`gemma-4-E2B-it-Q4_K_M.gguf`, **4.6B parameters**, `num_ctx=8192`).
2. **Forced `max_tokens` Floor**:
   - `rag_engine.generate_response()` and `stream_response()` enforced `effective_max_tokens = max(1536, int(max_tokens))`, overriding callers' token limits. Combined with a 20K-character prompt, a single unoptimized B04 call measured **161.93 seconds** (`1,024` generated tokens at `11.67 tok/s`).
3. **Missing HTTP Request Timeouts & Buffered Stdout**:
   - `get_ollama_client()` instantiated `ollama.Client(host=endpoint)` with **no HTTP socket timeout**, meaning slow CPU inference could hang indefinitely without failing.
   - `build_evidence_context()` also forced `effective_max_chars = max(max_context_chars, min(len(chunks)*3500, 24000))`, preventing callers from bounding prompt budgets.
   - Python stdout buffering and zero stage-level logging obscured retrieval vs. prompt-eval progress.

### 2.3 Implemented Engineering Fixes & Timeout Configuration
- **Files Changed**:
  - `rag_engine.py`: Added `timeout` parameter to `get_ollama_client()`, `generate_embedding()`, `generate_response()`, `stream_response()`, `stream_rag_answer()`, and `generate_rag_answer()`; added explicit `TimeoutError` propagation and guaranteed HTTP client/stream cleanup in `finally:`; respected caller `max_tokens` and `max_context_chars` parameters.
  - `rag_evaluator.py`: Implemented local Ollama + deterministic claim-level auditor with native socket timeout (`get_ollama_client(..., timeout=timeout)`) instead of orphaned thread cancellation.
  - `database.py`: Added backward-compatible `assessment_metadata` JSON column migration (`ALTER TABLE messages ADD COLUMN assessment_metadata ...`) and `update_message_assessment()`.
  - `app.py`: Added expandable `"Answer Quality Assessment"` card under every assistant response with metric breakdown, critical technical warnings, claim-level evidence inspection, graceful handling of unavailable/skipped runs, and `"Not assessed — historical response."` fallback for legacy messages.
  - `tests/rag_accuracy_benchmark.json`, `tests/run_rag_accuracy_benchmark.py`, `tests/test_rag_evaluator.py`, `tests/run_all_regression_tests.py`, `README.md`, `docs/TESTING_AND_VALIDATION.md`.

- **Configured Timeouts (`tests/run_rag_accuracy_benchmark.py`)**:
  - Ollama connectivity check: **`5.0s`**
  - Query embedding (`nomic-embed-text:latest`): **`20.0s`**
  - SOP retrieval wrapper: **`30.0s`**
  - Answer generation (`gemma-2b:latest`, `max_tokens=512`, `max_context_chars=8000`, `top_k=5`): **`150.0s`**
  - Answer evaluation probe: **`45.0s`**

---

## 3. Pre-Flight Ollama Health & Resource Checks

Prior to executing benchmark cases, `run_preflight_checks()` verified live local environment integrity:

1. **Ollama Connectivity**: Reachable at `http://127.0.0.1:11434` (`0.03s`).
2. **Generation Model**: `gemma-2b:latest` (`gemma-4-E2B-it-Q4_K_M.gguf`, 4.6B, Q4_K_M) present.
3. **Embedding Model**: `nomic-embed-text:latest` (`nomic-embed-text-v1.5.Q4_K_M.gguf`, 136.73M) present.
4. **Embedding Dimensions**: Live embedding confirmed shape **`(768,)`** (`0.56–1.18s`).
5. **FAISS Index Integrity**: Verified **`150`** baseline vectors, healthy (`sop.index`).
6. **Live Evaluator Structured JSON Probe**: Verified local Ollama `format="json"` + `think=False` output passed `validate_llm_eval_schema()` (`7.86–19.79s` depending on model warmth).

---

## 4. Actual 30-Question Ground-Truth Benchmark Results

### 4.1 Execution Counts & Aggregate Metrics
- **Total Benchmark Questions (`n`)**: `30`
- **Completed**: `28`
- **Passed (Answer Correctness)**: `20` (`66.7%`)
- **Failed (Completed but Did Not Meet Ground Truth)**: `8`
- **Timed Out (>150.0s generation timeout)**: `2` (`B21`, `B22`)
- **Errors**: `0`
- **Skipped**: `0`
- **Total Execution Duration**: **`2,328.08 seconds`** (~38.8 minutes across `--resume` checkpointed run)

| Benchmark Metric | Observed Result | Scope / Notes |
| :--- | :---: | :--- |
| **Answer Correctness** | **66.7%** (`20/30`) | Required facts covered (`>= 60%`) with 0 prohibited fabricated claims (or valid abstention). Timed-out cases count as failed. |
| **Retrieval Precision@5** | **80.7%** | Mean fraction of retrieved citations matching `expected_source_document` (excluding 4 abstention/insufficient queries without target docs). |
| **Retrieval Recall@5** | **60.4%** | Mean fraction of expected ground-truth documents retrieved in top-k (`0.50` when V2-first prioritizes V2 over V1 for dual-revision expectations). |
| **Citation Correctness** | **70.8%** (`17/24`) | Strictly verifies **document + revision + section + page** on completed queries with expected sources. |
| **Faithfulness Rate** | **46.4%** (`13/28`) | Strict deterministic claim-level check against retrieved citations (`contradictions=0`, `evidence_support >= 65`, `prohibited=0`). |
| **Hallucination Rate** | **7.1%** (`2/28`) | Flagged critical unsupported technical specs or claims contradicting retrieved context (`B09`, `B18`). |
| **Abstention Accuracy** | **33.3%** (`2/6`) | Computed across the 6 insufficient-evidence / out-of-scope prompts (`B25–B30`). See Section 5.3 for semantic abstention note on `B27`. |
| **Intent Classification Accuracy** | **64.3%** (`18/28`) | Predicted component intent category vs expected category on completed runs. |

### 4.2 Per-Category Performance Breakdown

| Category | Count | Completed | Timed Out | Accuracy | Citation Acc | Faithfulness | Hallucination Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `basic_component_definition` | 3 | 3 | 0 | **100.0%** | 33.3% (`1/3`) | 100.0% | 0.0% |
| `component_function` | 3 | 3 | 0 | **100.0%** | 100.0% (`3/3`) | 33.3% | 0.0% |
| `component_relationship` | 3 | 3 | 0 | **100.0%** | 66.7% (`2/3`) | 0.0% | 33.3% (`1/3`) |
| `assembly_breakdown` | 3 | 3 | 0 | **100.0%** | 100.0% (`3/3`) | 33.3% | 0.0% |
| `technical_specification` | 4 | 4 | 0 | **50.0%** | 75.0% (`3/4`) | 100.0% | 0.0% |
| `procedural` | 3 | 3 | 0 | **66.7%** | 66.7% (`2/3`) | 66.7% | 33.3% (`1/3`) |
| `revision_comparison` | 3 | 1 | **2** | **0.0%** | 100.0% (`1/1`) | 100.0% | 0.0% |
| `cross_document_impact` | 2 | 2 | 0 | **100.0%** | 0.0% (`0/2`) | 50.0% | 0.0% |
| `insufficient_evidence` | 3 | 3 | 0 | **33.3%** | 100.0% (`2/2`) | 0.0% | 0.0% |
| `abstention` | 3 | 3 | 0 | **33.3%** | N/A | 0.0% | 0.0% |

### 4.3 Complete Per-Question Results Table (`B01–B30`)

*(Note: `Auto Est.` is the automated deterministic `rag_evaluator` score `0–100` shown for comparison and is strictly separated from empirical ground-truth `Correct`.)*

| ID | Category | Status | Correct | Cit OK | Faithful | Halluc | Prec@5 | Rec@5 | Auto Est. | Latency |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **B01** | `basic_component_definition` | COMPLETED | True | True | True | False | 1.00 | 0.50 | 91.8 | 0.11s |
| **B02** | `basic_component_definition` | COMPLETED | True | False | True | False | 1.00 | 0.50 | 93.1 | 0.08s |
| **B03** | `basic_component_definition` | COMPLETED | True | False | True | False | 1.00 | 0.50 | 93.1 | 0.08s |
| **B04** | `component_function` | COMPLETED | True | True | True | False | 0.64 | 1.00 | 88.8 | 100.32s |
| **B05** | `component_function` | COMPLETED | True | True | False | False | 0.42 | 0.50 | 67.9 | 91.33s |
| **B06** | `component_function` | COMPLETED | True | True | False | False | 1.00 | 0.50 | 72.0 | 103.91s |
| **B07** | `component_relationship` | COMPLETED | True | False | False | False | 1.00 | 0.50 | 72.0 | 95.52s |
| **B08** | `component_relationship` | COMPLETED | True | True | False | False | 0.92 | 0.50 | 72.0 | 124.11s |
| **B09** | `component_relationship` | COMPLETED | True | True | False | True | 0.58 | 0.50 | 61.9 | 119.79s |
| **B10** | `assembly_breakdown` | COMPLETED | True | True | False | False | 1.00 | 0.50 | 72.0 | 107.44s |
| **B11** | `assembly_breakdown` | COMPLETED | True | True | False | False | 1.00 | 0.50 | 71.8 | 116.37s |
| **B12** | `assembly_breakdown` | COMPLETED | True | True | True | False | 1.00 | 0.50 | 86.5 | 114.86s |
| **B13** | `technical_specification` | COMPLETED | True | True | True | False | 1.00 | 1.00 | 97.2 | 36.06s |
| **B14** | `technical_specification` | COMPLETED | False | True | True | False | 1.00 | 1.00 | 85.7 | 73.03s |
| **B15** | `technical_specification` | COMPLETED | True | True | True | False | 1.00 | 1.00 | 79.1 | 39.06s |
| **B16** | `technical_specification` | COMPLETED | False | False | True | False | 1.00 | 1.00 | 87.4 | 38.97s |
| **B17** | `procedural` | COMPLETED | True | True | True | False | 1.00 | 0.50 | 88.2 | 42.04s |
| **B18** | `procedural` | COMPLETED | False | False | False | True | 0.00 | 0.00 | 64.0 | 54.79s |
| **B19** | `procedural` | COMPLETED | True | True | True | False | 1.00 | 1.00 | 94.9 | 65.82s |
| **B20** | `revision_comparison` | COMPLETED | False | True | True | False | 0.82 | 0.50 | 77.4 | 134.46s |
| **B21** | `revision_comparison` | **TIMEOUT** | False | None | False | False | N/A | N/A | N/A | 155.20s |
| **B22** | `revision_comparison` | **TIMEOUT** | False | None | False | False | N/A | N/A | N/A | 153.32s |
| **B23** | `cross_document_impact` | COMPLETED | True | False | True | False | 0.00 | 0.00 | 88.2 | 52.26s |
| **B24** | `cross_document_impact` | COMPLETED | True | False | False | False | 0.00 | 0.00 | 63.8 | 36.13s |
| **B25** | `insufficient_evidence` | COMPLETED | False | True | False | False | 1.00 | 1.00 | 72.0 | 51.52s |
| **B26** | `insufficient_evidence` | COMPLETED | True | True | False | False | 1.00 | 1.00 | 69.0 | 70.43s |
| **B27** | `insufficient_evidence` | COMPLETED | False | None | False | False | N/A | N/A | 71.6 | 55.15s |
| **B28** | `abstention` | COMPLETED | False | None | False | False | N/A | N/A | 49.6 | 89.64s |
| **B29** | `abstention` | COMPLETED | False | None | False | False | N/A | N/A | 50.6 | 125.04s |
| **B30** | `abstention` | COMPLETED | True | None | False | False | N/A | N/A | 56.0 | 80.90s |

---

## 5. Failure, Timeout, Citation & Hallucination Analysis

### 5.1 Investigation of `B02` and `B03` (`cit_ok=False`) — Real Defect Confirmed
- **Finding**: Manually verified expected revisions for `HVF_SOP_2_Turret_Integration.pdf` and `HVF_SOP_4_Torsion_Suspension.pdf` are **`Rev 3.8 / Rev 4.5`** and **`Rev 4.0 / Rev 5.2`**, respectively (verified in `index_manifest.json` and PDF titles). However, `data/component_glossary.json` (preserved untouched per invariant constraints) stores `"Rev 4.2 (Baseline) / Rev 5.0 (Revised)"` on `turret base ring` (`B02`) and `torsion bar` (`B03`). Thus, **actual answer citations were incorrect**, and our citation validator correctly caught `rev_match=False` while keeping `B01` (`Rev 4.2`) as `cit_ok=True`.

### 5.2 Timed-Out Cases (`B21`, `B22`)
- Both `B21` (*Hull Welding V1 vs V2*) and `B22` (*Torsion Suspension V1 vs V2*) retrieve combined V1 + V2 component & chunk evidence across multiple files, exceeding `150.0s` prompt-evaluation + CPU generation budget on `gemma-2b:latest` (4.6B). Notice `B20` barely finished in `134.46s`. Both timeouts terminated cleanly without halting subsequent cases (`B23–B30`).
- **Operational Takeaway**: Multi-revision diffs should be routed to the deterministic `sop_analyzer.py` comparison engine rather than unconstrained 8K RAG prompts on CPU.

### 5.3 Failed & Hallucinated Cases (`B09`, `B14`, `B16`, `B18`, `B20`, `B25`, `B27`, `B28`, `B29`)
- **Retrieval Chunk Granularity (`B14`, `B16`)**: Top-level Section `0.3 CRITICAL ENGINEERING ACCEPTANCE BENCHMARKS` tables reside in chunk `C0001` (`SECTION 1.0`, Page 1-2). Dense FAISS queries pulled procedural execution chunks (`1.0.A`, `3.0`), causing `B14` to honestly abstain and `B16` to cite pressure steps without the summary numeric tolerance (`62.0 ± 0.5 bar`).
- **Cross-SOP Semantic Confusion (`B18`, `B23`, `B24`)**: Asking *"main gun barrel installed into the turret cradle"* (`B18`) pulled `HVF_SOP_2_Turret_Integration_v2.pdf` instead of `HVF_SOP_5_Gun_Calibration.pdf`, yielding `halluc=True` / `cit_ok=False`. Similarly, cross-document impact queries (`B23`, `B24`) retrieved only one side of the interface coupling rather than invoking `sop_analyzer.analyze_cross_document_impacts()`.
- **Component Relationship Hallucination (`B09`)**: Evaluator flagged an unverified technical detail added outside the retrieved passage during component summary generation.
- **V1 vs V2 Specification Leak (`B20`, `B25`)**: In `B20`, `All Revisions` mode with `v2_boost` retrieved primarily `V2` chunks, missing exact `V1` baseline numbers (`0.05 mm`). In `B25` (V1-only ceramic-hybrid query), the model listed V1 bearing ball specs (`±0.002 mm`) instead of explicitly declaring that ceramic-hybrid bearings do not exist in V1.
- **Out-of-Domain Abstention Gap (`B27`, `B28`, `B29`)**:
  - `B27` semantically abstained (*"there is no information detailing a coupled thermal/pressure tolerance..."*), though our strict `ABSTENTION_PATTERNS` missed `"no information detailing"` (so strict script scored `False` even though no hallucination occurred).
  - `B28` (RF encryption) and `B29` (stealth aircraft coatings) failed abstention because `score_threshold` defaults to `None` in FAISS retrieval, feeding unrelated tank chunks to `COMPONENT_RAG_SYSTEM_PROMPT`, prompting `gemma-2b` to summarize tank components instead of refusing.

---

## 6. Per-Answer Evaluator Validation & Limitations

### 6.1 Unit & Integration Test Coverage (`tests/test_rag_evaluator.py` — 20/20 PASS)
All 20 required scenarios pass inside the master regression suite (`158/158 PASS` total):
- Supported, partial, unsupported, contradictory, wrong-citation, missing-citation, basic definition, off-topic SOP summary, incomplete answer, unsupported tolerance, unsupported material (`SAE 4340`), insufficient evidence/abstention, and `GENERAL_CONTEXT` segregation.
- Fault resilience: Malformed JSON, timeout (`TimeoutError`), and unavailable Ollama (`ConnectionError`) all degrade cleanly to `"Answer quality assessment unavailable."` while preserving the original answer verbatim.
- SQLite persistence across restarts, sequential independence, historical unassessed fallback (`"Not assessed — historical response."`), and non-blocking cancellation.

### 6.2 Unassessed Responses & Evaluator Limitations
1. **Unassessed States Handled Explicitly**:
   - Historical records created before Mini Phase 13 render `"Not assessed — historical response."`
   - Cancelled responses before substantive tokens and pure greetings mark metrics `NOT ASSESSED` (`assessment_status="skipped"`).
   - Failed Ollama evaluation probes mark `NOT ASSESSED` (`"Answer quality assessment unavailable."`) without inventing 100s.
2. **Evaluator Limitations**:
   - Deterministic `TECH_VALUE_REGEX` catches explicit unit-bearing specs and uppercase standard codes (`MIL-DTL`, `SAE`, `IS 2062`) reliably, while implicit prose paraphrases still rely on lexical overlap and local Ollama semantic checks.
   - Because `gemma-2b:latest` on CPU takes `~6–20s` per LLM evaluation call, live chat triggers LLM evaluation only on completed non-glossary RAG answers and uses deterministic auditing on cancelled partial outputs so UI responsiveness and Stop cancellation are never blocked.

---

## 7. Remaining Technical Risks & Production Invariants Confirmed

### Remaining Technical Risks
1. **CPU Inference Latency on Cross-Revision Prompts**: Dual-revision prompts approach `130–160s` on CPU with the 4.6B `gemma-4-E2B` model.
2. **Out-of-Scope Abstention without Cosine Cutoff**: Adding a default minimum cosine score cutoff (e.g., `score >= 0.42`) when `score_threshold=None` would prevent irrelevant chunks from triggering tangential component summaries (`B28`, `B29`).
3. **Glossary Revision Typo**: Updating `data/component_glossary.json` revision tags for SOPs 2–5 (`Rev 3.8/4.5`, `Rev 5.1/6.0`, `Rev 4.0/5.2`, `Rev 4.6/5.4`) in a future content cleanup phase will eliminate the `B02`/`B03` citation mismatch.

### Production Invariants Verified (After Final Run)
- **Original PDFs**: `10 / 10` preserved in `SOP/`
- **FAISS Vectors & Dimensions**: `150` vectors, `768` dimensions (`data/faiss_index/sop.index`)
- **Component Metadata**: `517` records (`data/faiss_index/components_metadata.json`)
- **SQLite Database**: Healthy (`data/sop_assistant.db`), `4` conversations and `17` existing messages preserved intact
- **Offline Compliance**: 100% local loopback execution (`127.0.0.1:11434`), zero external APIs.

