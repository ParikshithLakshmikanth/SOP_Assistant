# Intelligent SOP Document Intelligence & Revision Impact Analysis Assistant
## Final Technical & Engineering Project Report

**Facility**: Heavy Vehicles Factory (HVF), Avadi, Chennai, Tamil Nadu  
**Organization**: Armoured Vehicles Nigam Limited (AVNL), Ministry of Defence, Government of India  
**Project**: AI-Powered Offline Standard Operating Procedure (SOP) Document Intelligence and Revision Impact Analysis Assistant  
**Date**: November 2026  
**Status**: 100% Complete & Accepted (Mini Phases 1–8)

---

## 1. Executive Summary & Project Identification

This report presents the final engineering documentation, empirical evaluation, and architectural acceptance of the **Intelligent SOP Document Intelligence and Revision Impact Analysis Assistant**.

Engineered specifically for the defense manufacturing workflows of Heavy Vehicles Factory (HVF), an operating division of Armoured Vehicles Nigam Limited (AVNL), this application solves a fundamental operational challenge: enabling production engineers, quality inspectors, and shop-floor technicians to interactively query, audit, and compare mission-critical Standard Operating Procedures (SOPs) governing main battle tank (MBT) assembly within a **100% offline, air-gapped security perimeter**.

The system adheres strictly to a clean **5-primary-Python-module architecture** (`app.py`, `document_processor.py`, `rag_engine.py`, `sop_analyzer.py`, `database.py`), leverages local quantized open-weights models (`gemma-2b:latest` and `nomic-embed-text:latest`) executed on standard CPU hardware via Ollama, indexes an authoritative corpus of 10 defense SOP PDFs (150 semantic chunks in FAISS `IndexFlatIP`), and maintains a rigorously grounded database of **517 structured component metadata records**. Across 10 specialized automated test suites, the application achieves a **100% pass rate (108/108 tests passing in ~53 seconds)**.

---

## 2. Problem Statement & Defense Manufacturing Context

Heavy Vehicles Factory (HVF) at Avadi is the focal manufacturing center for Indian armored fighting vehicles, producing frontline platforms including the **T-90 Bhishma**, **T-72 Ajeya**, and **Arjun MBT**. In armored vehicle fabrication and assembly, standard operating procedures dictate high-consequence mechanical and metallurgical operations:
1. Multi-pass submerged arc and flux-cored welding of quenched-and-tempered high-hardness armor steel plates.
2. High-precision CNC machining and fitting of 2.5-meter diameter turret azimuth race rings.
3. Optical alignment, dynamic vibration isolation, and driveline backlash calibration of 1,000+ hp V12 multi-fuel powerpacks.
4. Pre-stressing, scragging, and splined socket installation of high-strength suspension torsion bars.
5. Collimation, trunnion bearing clearance, and optical muzzle reference calibration of 125mm smoothbore main guns.

### Operational Vulnerabilities Addressed:
- **Cloud Inadmissibility**: Defense technical data cannot leave the physical factory premises or be processed by external cloud APIs due to national security regulations.
- **Revision Drift**: Engineering changes between baseline (V1) and revised (V2) SOPs—such as tightening bearing runout tolerances from ±0.05 mm down to ±0.02 mm or switching lubricants from Molykote to Krytox—often lead to assembly errors if shop-floor personnel consult outdated documentation.
- **Cross-Subsystem Interface Blind Spots**: Tightening turret base ring tolerances directly impacts the hull welding roof plate flatness and the main gun trunnion alignment. Without cross-document interface visibility, isolated engineering modifications cause costly downstream integration failures.
- **AI Hallucination Risk**: Standard commercial generative chatbots frequently invent plausible-sounding torque numbers, bearing part numbers, and fastener grades. In tank manufacturing, ungrounded AI outputs present critical safety hazards.

---

## 3. Project Objectives & Success Criteria

The engineering objectives defined across Mini Phases 1 through 8 are summarized below:

| Objective | Target Metric | Achieved Result | Status |
| :--- | :--- | :--- | :---: |
| **Air-Gap Security** | Zero external network calls. Local CPU execution only. | Sockets bound strictly to loopback (`127.0.0.1`). External sockets blocked. | **MET (100%)** |
| **Corpus Baseline** | Index 10 authoritative HVF SOP PDFs covering 5 domains. | Exactly 10 PDFs indexed, producing 150 semantic vectors (768 dims). | **MET (100%)** |
| **Component Database** | Extract and ground technical components from SOPs. | 517 structured component records persisted with exact citations. | **MET (100%)** |
| **Evidence Grounding** | Every answer backed by exact filename, section, page. | Traceable citations with similarity scores on 100% of responses. | **MET (100%)** |
| **Zero False Inference** | Do not infer structural links from co-occurrence. | Relationships asserted only when explicitly stated in text. | **MET (100%)** |
| **Revision Diffing** | Identify structural, tolerance, and tooling shifts. | Deterministic diffing surfacing numerical tolerance changes. | **MET (100%)** |
| **Cross-Impact Analysis**| Trace geometric interface couplings across subsystems. | Cross-document impact maps for all 5 vehicle subsystem pairs. | **MET (100%)** |
| **Automated Testing** | Full regression test suite covering all modules. | 108 / 108 passing automated tests across 10 test suites. | **MET (100%)** |

---

## 4. System Architecture & 5-Module Modular Decomposition

The application strictly maintains a 5-module separation of concerns without code duplication or circular dependencies:

```
D:\Parikshith\SOP_Assistant\
├── app.py                  # Module 1: Streamlit Frontend & Executive Dashboard
├── document_processor.py   # Module 2: Document Ingestion, Chunker & Entity Extractor
├── rag_engine.py           # Module 3: Hybrid Retrieval, Ollama Client & Prompter
├── sop_analyzer.py         # Module 4: Structural Revision Diff & Cross-Impact Engine
└── database.py             # Module 5: Transactional SQLite Storage & Message History
```

1. **`app.py`**: Streamlit single-page application orchestrating 6 operational modes: Executive Dashboard, Consultation Chatbot, Visual Component Explorer, SOP Revision Comparison Engine, Cross-Document Impact Analysis, and Transactional Document Ingestion. Features live token streaming with custom CSS typing indicators.
2. **`document_processor.py`**: Ingestion engine combining PyMuPDF digital text extraction, Tesseract OCR for low-density scanned pages, 500-word hierarchical chunking with 50-word sliding overlap, SHA-256 deduplication, and regex taxonomy component extraction.
3. **`rag_engine.py`**: Core intelligence layer managing local Ollama loopback communication, 768-dimensional Nomic embeddings, FAISS `IndexFlatIP` cosine similarity search, conversational coreference resolution, and prompt assembly.
4. **`sop_analyzer.py`**: Analytical comparison engine performing section-by-section diffing, numerical tolerance extraction, tooling shifts, and physical interface dependency tracking across vehicle subsystems.
5. **`database.py`**: Relational persistence layer managing SQLite tables with Write-Ahead Logging (WAL) and foreign key cascades for multi-session conversation tracking.

---

## 5. Data Engineering & Semantic Ingestion Pipeline

To convert raw defense engineering PDFs into searchable semantic units, the system executes a deterministic 7-stage pipeline:
1. **Validation & Deduplication**: Computes SHA-256 hash. If duplicate hash exists in database, rejects upload immediately.
2. **Text Parsing via PyMuPDF**: High-throughput extraction of text streams, tables, and page metadata.
3. **Tesseract OCR Fallback**: Triggered automatically if a page yields fewer than 30 characters of digital text, rendering the page to a 300 DPI pixmap before invoking optical character recognition.
4. **Hierarchical Semantic Chunking**: Segments documents into 500-word blocks with 50-word overlaps. Each chunk preserves section titles, document ID, revision, start page, and end page.
5. **Dense Vector Embeddings**: Generates 768-dimensional float32 embeddings using local `nomic-embed-text:latest` and normalizes vectors using L2 norm.
6. **FAISS Index Storage**: Ingests normalized vectors into `sop.index` using `IndexFlatIP` (inner product = cosine similarity for unit vectors).
7. **Corpus Manifest Synchronization**: Updates `index_manifest.json` recording total chunks, document metadata, and chunk boundary indices.

The baseline corpus consists of 10 defense PDFs comprising **150 chunks**:
- `HVF_SOP_1_Hull_Welding.pdf` & `HVF_SOP_1_Hull_Welding_v2.pdf` (Hull Welding: 30 chunks)
- `HVF_SOP_2_Turret_Integration.pdf` & `HVF_SOP_2_Turret_Integration_v2.pdf` (Turret Integration: 30 chunks)
- `HVF_SOP_3_Engine_Alignment.pdf` & `HVF_SOP_3_Engine_Alignment_v2.pdf` (Engine Alignment: 30 chunks)
- `HVF_SOP_4_Torsion_Suspension.pdf` & `HVF_SOP_4_Torsion_Suspension_v2.pdf` (Track & Suspension: 30 chunks)
- `HVF_SOP_5_Gun_Calibration.pdf` & `HVF_SOP_5_Gun_Calibration_v2.pdf` (Gun Calibration: 30 chunks)

---

## 6. Structured Component Extraction & Grounding Methodology

Mini Phase 2 and 2B established a structured component metadata database persisted in `data/faiss_index/components_metadata.json`, containing **517 reconciled records**:

### Entity Breakdown by Type across all 10 Distinct Categories
- **OTHER_REFERENCE**: 168 records (general references, visual callouts, standard designations).
- **TECHNICAL_PARAMETER**: 122 records (numerical tolerances, pressures, clearances).
- **PHYSICAL_COMPONENT**: 97 records (discrete machined parts: bearings, torsion bars, injector nozzles, trunnions).
- **ASSEMBLY**: 43 records (mechanical groups: turret ring assembly, powerpack package, bogie wheel arm).
- **PROCESS_OR_OPERATION**: 32 records (surface preparation, torque tightening, radiographic testing).
- **MATERIAL**: 28 records (weld wire, alloy steel, aerospace lubricants, primers).
- **TOOL_OR_INSTRUMENT**: 14 records (manufacturing and inspection instruments: dial test indicators, flaw detectors).
- **DOCUMENT_OR_CERTIFICATE**: 7 records (DGQA acceptance certificates, welding certifications).
- **SUBSYSTEM**: 5 records (major vehicle functional domains: traverse drive subsystem, hydro-gas suspension).
- **ACCEPTANCE_CRITERION**: 1 record (quality gate criteria).
- **Total Reconciled Records**: **517 records** (including **145 core hardware entities**: 97 physical components + 43 assemblies + 5 subsystems).

### Strict Evidence Gate & Relationship Grounding
A fundamental quality innovation enforced in Mini Phase 2B and 3C is the **Strict Evidence Gate**:
1. Every component record links to an exact source citation (`filename`, `revision`, `section`, `page_number`, `chunk_id`).
2. Structural relationships (`parent_assembly`, `connected_to`) are **asserted only when explicitly documented in the SOP text** (e.g., *"The Turret Base Ring mounts to the Hull Interface Ring via 48 bolts"*).
3. Components that merely co-occur in the same paragraph or section without an explicit structural connection have their relationship fields left empty. The system never infers mechanical relationships from co-occurrence.

---

## 7. Hybrid Vector Retrieval & RAG Generation Architecture

The retrieval engine (`rag_engine.py`) employs a **hybrid two-stage retrieval pipeline**:

```
User Technical Query
       │
       ▼ (Conversational Coreference Resolution)
Effective Query ("it" / "they" resolved to antecedent entity)
       │
       ├─────────────────────────────────┐
       ▼ (Dense Semantic Search)         ▼ (Structured Entity Lookup)
Ollama nomic-embed-text (768 dims)       Scan components_metadata.json
       │                                 │
FAISS IndexFlatIP Cosine Search          Exact & Normalized Entity Matches
(Top-k vectors filtered by revision)     (Components, Subsystems, Specs)
       │                                 │
       └────────────────┬────────────────┘
                        ▼ (Context Fusion & Grounding Prompt Assembly)
                 Prompt Fed to Local Ollama gemma-2b:latest
                        │
                        ▼ (Token-by-Token Streaming Response)
                 Live Markdown + Traceable Citations Rendered in UI
```

### Prompt Guardrails
The system prompt strictly commands the model:
- Base answers exclusively on the provided context passages.
- Cite the source document, revision, section, and page for every factual claim.
- If the retrieved context does not contain sufficient factual evidence, explicitly state: *"Based on the available SOP documents, there is no direct evidence to answer this question."*
- Suppress internal thinking traces (`<think>...</think>`).

---

## 8. SOP Revision Diffing & Tolerance Shift Metrology

The revision comparison engine (`sop_analyzer.py`) provides deterministic auditing between V1 baseline and V2 revised SOPs:
- **Structural Diffing**: Identifies added, deleted, and modified sections using Python `difflib`.
- **Numerical Tolerance Metrology**: Employs specialized regex patterns capturing dimensions, tolerances, and engineering units:
  - Pattern: `(\d+(?:\.\d+)?)\s*(?:±|\+\/-)\s*(\d+(?:\.\d+)?)\s*(mm|μm|deg|Nm|bar|rpm)`
  - Detects shifts: e.g., in Turret Integration, radial runout tightened from `0.05 mm` to `0.02 mm`.
- **Tooling & Equipment Upgrades**: Detects changes in specialized equipment (e.g., transition from manual micrometers to digital laser alignment systems; shift from Molykote grease to Krytox aerospace lubricant).
- **Safety Rule Changes**: Surfaces new personal protective equipment (PPE) mandates and hazardous material warnings.

---

## 9. Cross-Document Subsystem Interface Impact Analysis

In armored fighting vehicle manufacturing, subsystems do not operate in isolation. The impact analysis engine maps physical interface dependencies:

| Subsystem Pair | Interface Boundary | Propagated Impact Scenario |
| :--- | :--- | :--- |
| **Turret (`HVF-TR`) <-> Hull (`HVF-HW`)** | Turret Ring Well & Azimuth Bearing Flange | Tightening turret ring flatness tolerance to 0.02 mm requires re-machining the hull roof plate after hull welding to eliminate weld heat distortion. |
| **Powerpack (`HVF-EP`) <-> Hull (`HVF-HW`)** | Engine Bay Bedplate Vibration Mounts | Raising engine alignment precision requires precision line-boring of the hull engine bay foundation sockets. |
| **Suspension (`HVF-TS`) <-> Hull (`HVF-HW`)** | Torsion Bar Hull Tube Sockets | Changes in torsion bar pre-stress angles require verify-boring of hull torsion sockets prior to bogie wheel installation. |
| **Gun (`HVF-GC`) <-> Turret (`HVF-TR`)** | Trunnion Bearing Azimuth Mount | Modifications to turret traverse bearings alter muzzle reference sensor boresight zeroes. |

---

## 10. User Experience & Engineering Dashboard Design

The Streamlit frontend (`app.py`) provides an executive defense dashboard featuring:
- **Telemetry Indicators**: Real-time badges for Ollama loopback status, generation model health, embedding model health, FAISS vector index status, SQLite database health, and OCR readiness.
- **Progressive Streaming Response**: Real-time token streaming with a blinking defense-blue cursor (`.typing-cursor`) and cancellation stop button that preserves partial text and citations.
- **Traceable Citation Cards**: Expandable evidence sources displaying filename, revision, section title, page number, and similarity score.
- **Visual Component Explorer**: Filterable multi-level grid supporting SOP domain, revision, and entity type filters, with one-click "Ask AI about this component" actions.
- **Unified Query Parameter Navigation**: Supports deep linking (`?mode=dashboard`, `?mode=chat`, `?mode=explorer`, `?comp=Turret+Base+Ring`).

---

## 11. Persistence & Transactional State Management

The persistence tier relies on SQLite 3 (`data/sop_assistant.db`):
- **WAL Mode Enabled**: `PRAGMA journal_mode = WAL` allows concurrent read access during background indexing.
- **Foreign Key Enforcement**: `PRAGMA foreign_keys = ON` ensures child messages are automatically cascade-deleted when a conversation session is removed.
- **Audit Logging**: The `indexing_history` table maintains an immutable log of every indexing event, timestamp, vector count, and status.

---

## 12. Security, Air-Gap, and Offline Verification

The application is rigorously secured for defense environments:
1. **Network Air-Gap**: All socket connections to non-loopback addresses are blocked. Sockets bind strictly to `127.0.0.1:11434` (Ollama) and `127.0.0.1:8501` (Streamlit).
2. **CPU Execution**: Operates entirely on standard CPU hardware without external cloud or GPU requirements.
3. **Model Sovereignty**: Weights are stored as local GGUF files registered directly into the local Ollama instance.

---

## 13. Comprehensive Automated Verification & Test Results

The project includes **10 specialized regression suites** comprising **108 discrete automated test assertions**:

```
Master Test Runner: python tests/run_all_regression_tests.py
```

### Detailed Test Execution Breakdown:
1. `tests/test_rag_pipeline.py` (18 tests): Dense vector retrieval, revision filtering, hybrid metadata lookups. -> **PASS**
2. `tests/test_system_health.py` (12 tests): Telemetry checks, Ollama daemon status, FAISS vector invariants. -> **PASS**
3. `tests/test_document_ingestion.py` (15 tests): Text parsing, OCR fallback, 500-word chunking, deduplication. -> **PASS**
4. `tests/test_persistence.py` (14 tests): SQLite schema, foreign keys, message history, citation serialization. -> **PASS**
5. `tests/test_compact_evidence.py` (8 tests): Citation deduplication, score aggregation, page range sorting. -> **PASS**
6. `tests/test_smooth_streaming.py` (9 tests): Token streaming, cancellation, partial answer preservation. -> **PASS**
7. `tests/test_phase7_upload_lifecycle.py` (7 tests): 7-stage upload lifecycle, temporary indexing to 151, retrieval, and clean reversion back to 150/517. -> **PASS**
8. `tests/test_phase7_offline_operation.py` (6 tests): Socket monkey-patching, air-gap enforcement, 0 external calls. -> **PASS**
9. `tests/test_phase7_persistence.py` (9 tests): SQLite restart, schema integrity, boundary safety against bad embeddings. -> **PASS**
10. `tests/test_phase7_revision_impact.py` (10 tests): Structural revision diff, numerical tolerance shifts, interface impacts. -> **PASS**

**Final Result**: **108 / 108 tests PASS (100% OK in 53.12 seconds)**.

---

## 14. Real-Question Evaluation & Acceptance Results

During Mini Phases 3B, 3C, and 3D, eight technical domain questions were evaluated against the real SOP corpus:

| Question | Technical Finding | Supporting SOP Citation | Verification |
| :--- | :--- | :--- | :---: |
| **Q1: Turret Mount Components** | Identifies Turret Base Ring, Hull Interface Ring, Azimuth Bearing, Traverse Drive Gearbox, Fasteners. | `HVF_SOP_2_Turret_Integration.pdf` (Sec 3.1, p. 1-2) | **100% Grounded** |
| **Q2: Ceramic-Hybrid Bearing** | High-stiffness, low-friction rotational support for azimuth assembly with reduced thermal expansion. | `HVF_SOP_2_Turret_Integration_v2.pdf` (Sec 3.2, p. 2) | **100% Grounded** |
| **Q3: V12 Powerpack Components**| V12 Diesel Block, Injection Pump, Dual Turbochargers, Fluid Coupling Transmission, Cooling Fan Drives. | `HVF_SOP_3_Engine_Alignment.pdf` (Sec 2.0, p. 1-3) | **100% Grounded** |
| **Q4: Suspension Parts** | Torsion Bars, Hydraulic Rotary Dampers, Dual Bogie Road Wheels, Track Tensioning Idler, Steel Track Links. | `HVF_SOP_4_Torsion_Suspension.pdf` (Sec 2.1, p. 1-2) | **100% Grounded** |
| **Q5: Torsion System Relations**| Splined connection between Torsion Bar and Road Wheel Swing Arm, anchored at hull socket with rotary damper linkage. | `HVF_SOP_4_Torsion_Suspension.pdf` (Sec 3.3, p. 2) | **100% Grounded** |
| **Q6: Turret SOP V1 vs V2** | Runout tightened from 0.05 mm to 0.02 mm; steel to ceramic-hybrid bearing; Molykote to Krytox grease; torque 650 Nm to 720 Nm. | `HVF_SOP_2_Turret_Integration.pdf` vs `HVF_SOP_2_Turret_Integration_v2.pdf` | **100% Grounded** |
| **Q7: Hull Welding Assemblies** | Identifies structural plates (Glacis Armor Plate, Side Hull Plates, Floor Belly Armor, Bulkhead, Roof Plate). | `HVF_SOP_1_Hull_Welding.pdf` (Sec 2.0, p. 1-2) | **100% Grounded** |
| **Q8: Engine Alignment Steps** | Bedplate cleaning; lowering block onto vibration dampers; dual dial indicator measurement; precision shimming (max 0.08 mm TIR); torque to 450 Nm. | `HVF_SOP_3_Engine_Alignment.pdf` (Sec 4.2, p. 3) | **100% Grounded** |

---

## 15. Conclusion, Operational Impact & Future Enhancements

The **HVF SOP Document Intelligence & Revision Impact Analysis Assistant** has successfully concluded all 8 development and acceptance phases. It represents a fully validated, production-grade AI platform that solves the dual imperative of modern defense engineering: **harnessing the analytical power of advanced language models while rigorously safeguarding national defense data sovereignty within an air-gapped facility**.

### Operational Impact:
- **Reduces Quality Audit Cycles**: Inspectors can audit tolerance shifts between revisions in seconds rather than days.
- **Prevents Shop-Floor Assembly Collisions**: Cross-subsystem impact analysis proactively flags interface consequences before steel is cut or torqued.
- **Accelerates Technical Training**: Junior assembly technicians can query complex tank SOPs in natural language and receive beginner-friendly, citation-backed answers.

### Future Enhancements:
1. **Multimodal Raster CAD Ingestion**: Integrating local vision models to parse 2D engineering blueprints and schematic wiring diagrams directly.
2. **Shop-Floor Handheld Deployment**: Compiling the backend for ruggedized field tablets running lightweight ARM64 CPU inference.
3. **Automated Non-Conformance Logging**: Connecting the RAG chatbot to shop-floor quality inspection logs to automatically match field defects against SOP tolerance sections.

