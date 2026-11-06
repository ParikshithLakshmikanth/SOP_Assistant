# MINI PHASE 2 — Visual and Tabular Component Extraction Report
**SOP Document Intelligence and Revision Impact Analysis Assistant**  
**Repository Working Directory:** `D:\Parikshith\SOP_Assistant`  
**Execution Date:** 2026-11-05  
**Operating Environment:** Offline-First Windows 11 (AMD64), Python 3.11.13, PyMuPDF 1.25.3, Tesseract OCR 5.4.0, Ollama Local Daemon (`gemma-2b`, `nomic-embed-text`), FAISS-CPU 1.10.0, Streamlit 1.43.2.

---

## 1. Executive Summary

In **Mini Phase 2**, the SOP Document Intelligence Assistant was upgraded with a **Multi-Source Visual and Tabular Component Extraction Engine**. Rather than relying solely on unstructured paragraph text, the system now performs deep inspection of all SOP pages to extract engineering components, technical parameters, dimensional tolerances, metrology tooling, and stage-gate hold points across six distinct document artifact types:

1. **Tables & Technical Matrices**: 5-column QA verification matrices capturing Step, Parameter, Tolerance, Metrology Gauge, and Inspection Sampling hold points.
2. **Executive Summaries & Normative Matrices**: Critical material specifications, hardness benchmarks, and preheat criteria from Page 1 controls.
3. **Stage-Gate Warnings & Callouts**: Mandatory quality hold points, hull e-Passport ledger counter-stamps, and traceability station references.
4. **Section Headings & Assemblies**: Major vehicle assembly descriptions with acronym preservation (`RHA`, `HVF`, `MBT`, etc.).
5. **Visual Diagrams, Illustrations & Figures**: Embedded schematics and raster drawings processed via PyMuPDF pixmap rendering and local Tesseract OCR with confidence profiling.
6. **Captions & Blueprints**: Explicit drawing captions with uncertainty flagging for indicative, low-resolution, or blurred graphics.

Every extracted component retains complete provenance (`document_id`, `filename`, `page_number`, `section_reference`), and components with low OCR confidence (<50%) or blurry visuals are explicitly marked as uncertain (`is_uncertain: True`) with diagnostic reasoning rather than inventing specifications.

A dedicated **Visual & Tabular Component Explorer** view was integrated into the Streamlit application (`app.py`), enabling interactive search, filtering by subsystem and source type, and side-by-side inspection of component tolerances and inspection tooling.

All **12/12** component extraction tests and all **66** regression tests (**78/78 tests total**) passed with 100% success.

---

## 2. Extraction Pipeline Architecture

```
                                  SOP Document (PDF)
                                          │
                     ┌────────────────────┴────────────────────┐
                     ▼                                         ▼
            Page Text Blocks & Tables                   Embedded Raster / Visuals
                     │                                         │
     ┌───────────────┼───────────────┐                         ▼
     ▼               ▼               ▼                  PyMuPDF Pixmap
Page 1 Exec.     Tables &       Stage-Gate                 Rendering
Summary Matrix    Matrices       Callouts                      │
     │               │               │                         ▼
     │               │               │                  Tesseract OCR
     │               │               │             (image_to_data + Conf)
     │               │               │                         │
     ▼               ▼               ▼                         ▼
  Component:      Component:      Component:              Component:
 Base Material,   Step Number,    Critical Hold,         Visual Diagram /
 Preheat Criteria Tolerance, Tool Hull e-Passport          Schematic
                     │
                     ▼
          Section Heading Assemblies
           (Acronym-Preserved Title)
                     │
                     ▼
        Component Normalizer & Dedup
          (clean_cell_value, etc.)
                     │
                     ▼
    Atomic Persistence: data/faiss_index/
           components_metadata.json
                     │
                     ▼
      Streamlit Component Explorer UI
```

---

## 3. Implementation Details

### 3.1 Document Processor (`document_processor.py`)

Five dedicated extraction functions were implemented and wired directly into the document ingestion lifecycle:

1. **`clean_cell_value(val)`**:
   - Normalizes raw PDF table cells and OCR output.
   - Converts replacement artifacts (`\ufffd`) to standard hyphens.
   - Cleans spaced decimals (`0 .62` $\to$ `0.62`) and step numbers (`11 .` $\to$ `1.1`).
   - Fixes spaced hyphens in defence standards and compound terms (`MIL -DTL -12560` $\to$ `MIL-DTL-12560`, `Ultra-High -Strength` $\to$ `Ultra-High-Strength`).

2. **`derive_subsystem_from_section(section_title)`**:
   - Classifies section titles into human-readable engineering subsystems:
     - *Armoured Hull Structure & Fabrication*
     - *Turret Integration & Drive Mechanism*
     - *Powerpack & Engine Drive Alignment*
     - *Torsion Bar & Tracked Suspension System*
     - *125mm Smoothbore Main Gun & Recoil System*
     - *Hydraulic & Braking Subsystems*
     - *Auxiliary Power & Electrical Generation*

3. **`extract_tables_from_page(page, page_number, section_title, doc_id)`**:
   - Uses `page.find_tables()` cross-referenced with block layout coordinates to extract tabular matrix rows.
   - Maps columns into Step Number, Parameter Name, Technical Tolerance, Metrology Tooling, and Quality Sampling.
   - Extracts Page 1 Executive Summary normative criteria (e.g., `MIL-DTL-12560`, preheat tolerances).

4. **`extract_callouts_from_page(page, page_number, section_title, doc_id)`**:
   - Inspects blocks for `STAGE-GATE WARNING`, `QUALITY ASSURANCE & NON-CONFORMANCE CONTROL`, and `MANDATORY DIRECTIVE`.
   - Extracts mandatory hold criteria, e-Passport ledger counter-stamp requirements, and calibration station codes (`CAL-WLD-01`, `LOT-RHA-2026-X`).

5. **`extract_diagrams_and_figures_from_page(page, pdf_path, page_number, section_title, doc_id)`**:
   - Detects embedded raster images (`page.get_images()`) and rendered drawing regions.
   - Renders 200 DPI pixmaps and executes local Tesseract OCR with word-level confidence profiling.
   - Detects drawing captions (`Figure X.Y`, `Schematic`).
   - **Zero-Hallucination Policy**: If average OCR confidence $< 50\%$ or image dimensions $< 100\times100$ px, flags `is_uncertain: True` with explicit uncertainty reasoning instead of fabricating specs.

6. **`extract_headings_and_assemblies(page, page_number, section_title, doc_id)`**:
   - Extracts vehicle assembly definitions from section headings while preserving defence acronyms (`RHA`, `HVF`, `AVNL`, `MBT`, `QA`, `NDT`, `APU`).

7. **`extract_components_from_document(pdf_path)`**:
   - Orchestrates multi-source extraction across all pages.
   - Deduplicates components by `(name, page_number, source_type)`.
   - Preserves 100% of page numbers, section references, and document IDs.

### 3.2 RAG Engine & Persistence (`rag_engine.py`)

- **Component Persistence**: Added `save_components_metadata()` and `load_components_metadata()` targeting `data/faiss_index/components_metadata.json` with atomic temporary-file replacement.
- **Component Search API**:
  - `get_document_components(doc_id_or_filename)`: Retrieves all extracted components for a specific SOP document.
  - `search_components(query, subsystem, source_type, is_uncertain, top_k)`: High-speed keyword and multi-facet filtering across extracted components.
- **Ingestion Integration**: `index_documents()` and `index_chunks()` extract and persist components alongside vector chunks during both baseline indexing and ad-hoc user uploads.
- **Corpus Coverage**: All **455 baseline components** across all 10 official SOP PDFs (51 per baseline V1 SOP, 40 per revised V2 SOP) are extracted and persisted in `data/faiss_index/components_metadata.json`.

### 3.3 Streamlit User Interface (`app.py`)

Added a fourth primary operating mode: **🧩 Visual & Tabular Component Explorer**:
- **Sidebar Facet Filters**: Filter by Document, Engineering Subsystem, Source Type (Table, Callout, Diagram, Executive Summary, Heading), and Uncertainty status.
- **Search Bar**: Real-time filtering by component name, specification, tooling, or stage-gate warning.
- **Metrics Dashboard**: Live count cards for Total Components, Tabular Matrices, Visual Diagrams, Stage-Gate Warnings, and Uncertain Items.
- **Structured Component Cards**:
  - Distinct badges for source type and subsystem.
  - Technical tolerance and acceptance criteria highlights.
  - Metrology gauges and inspection station indicators.
  - Verbatim stage-gate warnings and quality hold directives.
  - Clean provenance pills with PDF filename, revision, page number, and section title.

---

## 4. Test Accounting and Verification Results

### 4.1 Component Extraction Test Suite (`tests/test_component_extraction.py`)

| Test ID | Test Name | Target Verification | Result |
|---|---|---|:---:|
| `test_01` | `test_01_tabular_matrix_component_extraction` | 5-column QA verification matrix extraction from `HVF_SOP_1_Hull_Welding.pdf` (Step, Tolerance, Metrology) | **PASS** |
| `test_02` | `test_02_executive_summary_extraction` | Page 1 critical acceptance benchmarks (`MIL-DTL-12560`, preheat tolerances) | **PASS** |
| `test_03` | `test_03_callout_and_stage_gate_warning_extraction` | $\ge 5$ Stage-Gate hold warnings and hull e-Passport ledger counter-stamps | **PASS** |
| `test_04` | `test_04_section_heading_assembly_extraction` | Major assembly extraction from headings with acronym preservation (`RHA Plate Receiving`) | **PASS** |
| `test_05` | `test_05_visual_diagram_and_figure_extraction_with_ocr` | PyMuPDF pixmap rendering + Tesseract OCR extraction on crisp diagrams | **PASS** |
| `test_06` | `test_06_unclear_diagram_marked_as_uncertain` | Low-resolution / blurry diagrams flagged as `is_uncertain: True` without hallucination | **PASS** |
| `test_07` | `test_07_page_and_section_provenance_preservation` | 100% of extracted components have valid `page_number` ($\ge 1$) and `section_reference` | **PASS** |
| `test_08` | `test_08_multi_sop_extraction_consistency` | Consistent component extraction across Hull Welding, Turret, Engine, Suspension, Gun SOPs | **PASS** |
| `test_09` | `test_09_component_search_and_subsystem_filtering` | Subsystem filtering and keyword search across component records | **PASS** |
| `test_10` | `test_10_persistence_and_loading_of_components_metadata` | JSON persistence, atomic write, and schema round-trip loading | **PASS** |
| `test_11` | `test_11_process_pdf_integrates_component_extraction` | End-to-end `process_pdf()` returns both text chunks and structured component list | **PASS** |
| `test_12` | `test_12_offline_execution_and_local_ocr_validation` | Zero external network calls; verifies local Tesseract OCR executable path | **PASS** |

**Component Suite Result:** **12/12 Passed** in 82.99s.

---

### 4.2 Full Regression Suite Summary

| Suite Name | File | Tests Run | Passed | Failed | Status |
|---|---|:---:|:---:|:---:|:---:|
| **Component Extraction Suite** | `tests/test_component_extraction.py` | 12 | 12 | 0 | **PASS** |
| **Uploaded Document Ingestion Suite** | `tests/test_uploaded_document_ingestion.py` | 15 | 15 | 0 | **PASS** |
| **Revision Preference Suite** | `tests/test_revision_preference.py` | 12 | 12 | 0 | **PASS** |
| **Continuous Auto-Scroll Suite** | `tests/test_auto_scroll.py` | 10 | 10 | 0 | **PASS** |
| **Compact Evidence Sources Suite** | `tests/test_compact_evidence.py` | 7 | 7 | 0 | **PASS** |
| **Phase 3 Integration & Acceptance Suite** | `tests/test_phase3_integration.py` | 10 | 10 | 0 | **PASS** |
| **Answer Completeness Suite** | `tests/test_answer_completeness.py` | 12 | 12 | 0 | **PASS** |
| **TOTAL** | — | **78** | **78** | **0** | **100% PASS** |

---

## 5. Corpus & FAISS Index Health Audit

Execution of `rag_engine.verify_faiss_index_health()` and metadata inspection confirms:
- **FAISS Vectors:** Exactly **150 vectors** across the 10 official SOP PDFs.
- **FAISS Health Status:** `is_healthy: True`, `issues: []`.
- **Extracted Components:** Exactly **455 structured component records** persisted in `data/faiss_index/components_metadata.json`.
  - Tabular Matrix Items: **300**
  - Section Heading Assemblies: **60**
  - Executive Summary Benchmarks: **60**
  - Stage-Gate Callout Warnings: **35**
- **Uncertain Items in Baseline:** **0** (baseline SOPs contain high-clarity vector tables and text).
- **Synthetic Low-Resolution Diagrams:** Reliably marked as `is_uncertain: True` with explicit uncertainty diagnostics.

---

## 6. Architectural Constraints & Offline Verification

1. **Architecture Preservation**: Exactly the 5 primary Python files maintained (`app.py`, `database.py`, `document_processor.py`, `rag_engine.py`, `sop_analyzer.py`). No secondary files or helper scripts introduced.
2. **Offline-First Integrity**: All operations execute locally on Windows CPU using local Tesseract OCR (`C:\TesseractOCR\tesseract.EXE`) and local Ollama daemon (`gemma-2b`, `nomic-embed-text`). Zero external or cloud vision APIs invoked.
3. **Traceability**: 100% of components retain precise `page_number`, `section_reference`, and `document_id` provenance.

