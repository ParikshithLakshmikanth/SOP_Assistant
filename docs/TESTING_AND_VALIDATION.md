# Heavy Vehicles Factory (HVF) / Armoured Vehicles Nigam Limited (AVNL)
## Intelligent SOP Document Intelligence & Revision Impact Analysis Assistant
### Comprehensive Testing & Validation Specification

---

## 1. Quality Assurance Overview

The HVF SOP Assistant undergoes automated regression testing across **10 dedicated test suites** comprising **108 discrete test assertions**. All tests execute locally on standard CPU hardware without external network dependencies.

### Master Test Runner
```powershell
python tests/run_all_regression_tests.py
```

### Overall Regression Status
- **Total Test Cases Executed**: 108
- **Total Passed**: 108 (100.0%)
- **Total Failed**: 0
- **Total Errors**: 0
- **Total Wall-Clock Execution Time**: ~53.1 seconds

---

## 2. Test Suite Matrix

| # | Test Suite | Module Under Test | Tests | Status | Key Verifications |
| :- | :--- | :--- | :-: | :-: | :--- |
| 1 | `tests/test_rag_pipeline.py` | `rag_engine.py` | 18 | PASS | Dense cosine FAISS retrieval, L2 normalization, revision filtering (V1 vs V2), hybrid component record matching, prompt formatting. |
| 2 | `tests/test_system_health.py` | `rag_engine.py`, `app.py` | 12 | PASS | Ollama daemon loopback detection, model existence (`gemma-2b`, `nomic-embed-text`), FAISS index vector synchronization, Tesseract configuration. |
| 3 | `tests/test_document_ingestion.py` | `document_processor.py` | 15 | PASS | PyMuPDF text/table parsing, OCR fallback, semantic 500-word chunking with 50-word overlap, SHA-256 deduplication, 517 component extractions. |
| 4 | `tests/test_persistence.py` | `database.py` | 14 | PASS | SQLite tables initialization, WAL mode, foreign key cascading, conversation CRUD, citation JSON serialization. |
| 5 | `tests/test_compact_evidence.py` | `app.py` | 8 | PASS | Citation deduplication, source grouping by document and revision, max score aggregation, page range sorting. |
| 6 | `tests/test_smooth_streaming.py` | `rag_engine.py`, `app.py` | 9 | PASS | Token generator yielding, cancellation via stop flag, partial token preservation, citation emission on stream completion. |
| 7 | `tests/test_phase7_upload_lifecycle.py` | End-to-End System | 7 | PASS | 7-stage transactional ingestion: validation -> text parsing -> chunking -> Ollama embedding -> FAISS append (150 -> 151) -> component extraction -> clean rollback back to 150 vectors. |
| 8 | `tests/test_phase7_offline_operation.py` | Network Layer | 6 | PASS | Air-gap verification: monkey-patched socket blocking all non-loopback connections. Zero external DNS or HTTP requests permitted. Loopback 127.0.0.1:11434 verified functional. |
| 9 | `tests/test_phase7_persistence.py` | `database.py` | 9 | PASS | Application restarts, database schema re-open, conversational reload, boundary protection against corrupted embedding arrays. |
| 10 | `tests/test_phase7_revision_impact.py` | `sop_analyzer.py` | 10 | PASS | V1 vs V2 section diffing, numerical tolerance shift extraction, tooling shifts, cross-subsystem interface dependency tracking. |

---

## 3. Specialized Air-Gap Validation (`test_phase7_offline_operation.py`)

To verify defense-grade compliance, network socket calls are intercepted at the Python socket library level:

```python
# Sockets are strictly restricted to 127.0.0.1 loopback
def guarded_connect(sock, address):
    host, port = address[0], address[1]
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise PermissionError(f"AIR-GAP VIOLATION: Attempted socket connection to {host}:{port}")
    return original_connect(sock, address)
```

### Verification Checks:
1. `test_airgap_blocks_external_http`: Connection to public IPs (e.g., `8.8.8.8`, `1.1.1.1`) immediately raises `PermissionError`.
2. `test_airgap_blocks_dns_resolution`: Socket `getaddrinfo()` for external domains raises `PermissionError`.
3. `test_airgap_allows_ollama_loopback`: Local HTTP requests to `http://127.0.0.1:11434/api/tags` execute successfully.
4. `test_airgap_allows_streamlit_loopback`: Local requests to `http://127.0.0.1:8501/_stcore/health` execute successfully.

---

## 4. Real-Question Component RAG Acceptance Results

During Mini Phases 3B, 3C, and 3D, eight technical domain questions were evaluated against the real SOP corpus.

| # | Question | Grounded Technical Findings | Citations Verified | Acceptance Status |
| :-: | :--- | :--- | :--- | :---: |
| **Q1** | *What are the main components of the turret mount system?* | Identifies Turret Base Ring, Hull Interface Ring, Azimuth Bearing, Traverse Drive Gearbox, and Grade 10.9 Fasteners. | `HVF_SOP_2_Turret_Integration.pdf` (Sec 3.1, p. 1-2) | **PASSED (100% Grounded)** |
| **Q2** | *What is the function of a ceramic-hybrid bearing?* | Documents high-stiffness, low-friction rotational support for the turret azimuth bearing assembly with reduced thermal expansion. | `HVF_SOP_2_Turret_Integration_v2.pdf` (Sec 3.2, p. 2) | **PASSED (100% Grounded)** |
| **Q3** | *Explain the main components of the V12 powerpack.* | Outlines V12 Twin-Turbo Diesel Block, Common-Rail Injection Pump, Dual Turbochargers, Fluid Coupling Transmission, and Cooling Fan Drives. | `HVF_SOP_3_Engine_Alignment.pdf` (Sec 2.0, p. 1-3) | **PASSED (100% Grounded)** |
| **Q4** | *What are the basic parts of the suspension and track system?* | Documents High-Strength Torsion Bars, Hydraulic Rotary Dampers, Dual Bogie Road Wheels, Track Tensioning Idler, and Steel Track Links. | `HVF_SOP_4_Torsion_Suspension.pdf` (Sec 2.1, p. 1-2) | **PASSED (100% Grounded)** |
| **Q5** | *How are the components of the torsion suspension system related?* | Details splined connection between Torsion Bar and Road Wheel Swing Arm, anchored at the hull torsion tube socket with rotary damper linkage. | `HVF_SOP_4_Torsion_Suspension.pdf` (Sec 3.3, p. 2) | **PASSED (100% Grounded)** |
| **Q6** | *What changed between V1 and V2 of the turret integration SOP?* | Identifies tightening of bearing runout from 0.05 mm to 0.02 mm, transition from steel to ceramic-hybrid bearings, upgrade from Molykote to Krytox grease, and torque increase from 650 Nm to 720 Nm. | `HVF_SOP_2_Turret_Integration.pdf` vs `HVF_SOP_2_Turret_Integration_v2.pdf` | **PASSED (100% Grounded)** |
| **Q7** | *What does the hull welding SOP say about its main assemblies?* | Explicitly categorizes structural components and plates (Glacis Armor Plate, Side Hull Plates, Floor Belly Armor, Engine Bay Bulkhead, Turret Well Roof Plate) rather than manufacturing equipment. | `HVF_SOP_1_Hull_Welding.pdf` (Sec 2.0, p. 1-2) | **PASSED (100% Grounded)** |
| **Q8** | *What are the main steps in the engine alignment procedure?* | Lists sequential steps: 1. Clean engine bay bedplates; 2. Lower V12 block onto vibration dampers; 3. Measure flywheel-to-transmission angular misalignment with dual dial indicators; 4. Insert precision shims (max 0.08 mm TIR); 5. Torque foundation bolts in crisscross sequence to 450 Nm. | `HVF_SOP_3_Engine_Alignment.pdf` (Sec 4.2, p. 3) | **PASSED (100% Grounded)** |

---

## 5. System Invariants Verification

The regression runner continuously asserts the following baseline invariants:
1. `sop.index` file contains exactly **150 vectors** of dimension **768**.
2. `components_metadata.json` contains exactly **517 records**.
3. All 517 component records possess non-null `component_name`, `entity_type`, `logical_sop_id`, and `revision`.
4. Exactly **10 PDF files** are tracked in `index_manifest.json` with matching SHA-256 hashes.
5. `sop_assistant.db` conforms to Foreign Key integrity checks.

