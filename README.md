# Intelligent SOP Document Intelligence & Revision Impact Analysis Agent

**Heavy Vehicles Factory (HVF), Avadi**  
**Armoured Vehicles Nigam Limited (AVNL), Ministry of Defence, Government of India**  
*Main Battle Tank (MBT) Manufacturing & Technical Operations Platform*

---

## 1. Executive Summary & Operational Context

The **Intelligent SOP Document Intelligence and Revision Impact Analysis Agent** is a defense-grade, offline-first engineering intelligence system developed for Heavy Vehicles Factory (HVF / AVNL), Avadi.

The platform provides end-to-end intelligence across standard operating procedures (SOPs) governing high-precision armored vehicle manufacturing:
1. **Armoured Hull Fabrications & High-Tensile Steel Welds** (`HVF_SOP_1_Hull_Welding`)
2. **Turret Ring Machining, Race Ring Fitting & Hull-Turret Integration** (`HVF_SOP_2_Turret_Integration`)
3. **Power Pack Integration, V12 Diesel Engine Alignment & Final Drive Coupling** (`HVF_SOP_3_Engine_Alignment`)
4. **Torsion Bar Installation, High-Stress Suspension & Track Tensioning** (`HVF_SOP_4_Torsion_Suspension`)
5. **Main Gun 125mm Smoothbore Barrel Alignment & Muzzle Reference Metrology** (`HVF_SOP_5_Gun_Calibration`)

Operating strictly on local CPU hardware without internet access or external cloud services, the platform provides semantic evidence retrieval, progressive response streaming, deterministic revision comparison, and cross-subsystem physical interface impact analysis.

---

## 2. Fixed Core Architecture

The codebase strictly adheres to a modular **5-Primary-Python-File Architecture**:

```
sop_assistant/
│
├── app.py                     # [Module 1/5] Streamlit Frontend & User Interface
├── database.py                # [Module 2/5] SQLite Persistence & History Management
├── document_processor.py      # [Module 3/5] PDF Text Extraction & OCR Chunking Engine
├── rag_engine.py              # [Module 4/5] Local Ollama AI, FAISS CPU Vector Retrieval
├── sop_analyzer.py            # [Module 5/5] Revision Comparison & Cross-Document Impact Engine
│
├── requirements.txt           # Python dependency specification
├── run_app.ps1                # PowerShell automated health-check and startup launcher
├── README.md                  # Comprehensive technical documentation & setup guide
├── FINAL_SYSTEM_VERIFICATION_REPORT.md # End-to-end acceptance test & benchmark report
│
├── docs_generator/            # Official HVF SOP document generation scripts
│   ├── generate_hvf_sops.py   # Baseline (v1) SOP generator
│   └── generate_hvf_sops_v2.py# Revised (v2) SOP generator
│
├── SOP/                       # Official Authoritative SOP Documents (10 PDFs, 80 pages)
│   ├── HVF_SOP_1_Hull_Welding.pdf / _v2.pdf
│   ├── HVF_SOP_2_Turret_Integration.pdf / _v2.pdf
│   ├── HVF_SOP_3_Engine_Alignment.pdf / _v2.pdf
│   ├── HVF_SOP_4_Torsion_Suspension.pdf / _v2.pdf
│   └── HVF_SOP_5_Gun_Calibration.pdf / _v2.pdf
│
├── models/                    # Quantized GGUF Models & Ollama Modelfiles
│   ├── gemma-4-E2B-it-Q4_K_M.gguf          # Gemma 2B text generation model
│   ├── nomic-embed-text-v1.5.Q4_K_M.gguf    # Nomic 768-dim embedding model
│   ├── ModelFile-gemma                      # Ollama registration descriptor (gemma-2b:latest)
│   └── ModelFile-embed                      # Ollama registration descriptor (nomic-embed-text:latest)
│
├── data/                      # Persistent Local Storage (100% Offline)
│   ├── faiss_index/           # FAISS IndexFlatIP (150 chunks, 768 dimensions)
│   │   ├── sop.index          # Binary FAISS vector index
│   │   ├── chunk_metadata.json# Traceable chunk metadata & section provenance
│   │   └── index_manifest.json# Document inventory & checksums
│   ├── sop_assistant.db       # SQLite Database (Conversations, Messages, Impact Reviews)
│   └── documents/             # Uploaded PDF document staging directory
│
└── tests/                     # Comprehensive Automated Verification Suites (Phases 1-9)
    ├── test_phase1.py         # Document Processor & OCR tests (9/9 pass)
    ├── test_phase2.py         # Local Ollama Inference & Embedding tests (11/11 pass)
    ├── test_phase3.py         # FAISS Vector Indexing & RAG Retrieval tests (14/14 pass)
    ├── test_phase4.py         # Streamlit Chatbot & Ingestion tests (10/10 pass)
    ├── test_phase5.py         # SQLite Persistence & Message Lifecycle tests (10/10 pass)
    ├── test_phase6.py         # Streaming & Stop Cancellation Hardening (11/11 pass)
    ├── test_phase7.py         # SOP Revision Comparison Engine tests (12/12 pass)
    ├── test_phase8.py         # Cross-Document Impact Analysis Engine tests (14/14 pass)
    └── test_phase9.py         # Final System Verification & Acceptance Suite (10/10 pass)
```

---

## 3. Key Capabilities & Feature Inventory

### A. Document Intelligence & Text Ingestion (`document_processor.py`)
- **PyMuPDF Native Digital Text Parsing**: High-speed page-by-page extraction with structural boundary detection.
- **Tesseract OCR Fallback**: Automatically triggered when a page contains fewer than 50 characters of digital text.
- **Section-Aware Chunking**: Preserves section headings, table structures, and multi-page procedural context.
- **Traceable Chunk Schema**: Stable hash IDs, source document filename, logical category, revision, section title, and start/end page numbers.

### B. Local AI & Semantic Retrieval (`rag_engine.py`)
- **100% Offline CPU Execution**: Local Ollama server (`http://127.0.0.1:11434`).
- **Nomic Dense Embeddings**: 768-dimensional normalized embeddings with IndexFlatIP inner-product cosine retrieval.
- **Gemma 2B Generation**: Evidence-grounded response generation strictly constrained to retrieved SOP passages.
- **Evidence-Backed Citations**: Standardized citation schema `[Filename, Revision, Section, Page X]`.
- **Honest Abstention**: Explicitly states when the corpus does not contain sufficient factual evidence to answer an inquiry.
- **Thinking Trace Suppression**: Automatically strips internal model reasoning tags (`<think>...</think>`).

### C. Persistent Dialogue & Multi-Session History (`database.py`)
- **SQLite Relational Persistence**: Stored in `data/sop_assistant.db` with WAL mode and foreign key cascading.
- **Dialogue Lifecycle**: Create, switch, rename, and delete technical consultations.
- **Interruption Resilience**: Cancelled responses are saved with partial text, citations, and `is_cancelled=True`.
- **Rerun Idempotency**: UI reruns do not duplicate messages or corrupt chronological ordering.
- **FAISS Isolation**: Conversation logs and user queries are never injected into the authoritative SOP vector corpus.

### D. SOP Revision Comparison Engine (`sop_analyzer.py`)
- **Baseline vs. Revised Alignment**: Section-by-section comparison using normalized section keys.
- **Multi-Dimensional Classification**:
  - Changed numerical parameter, tolerance, or threshold.
  - Changed safety warning or precaution.
  - Changed equipment, tooling, or material.
  - Changed inspection or acceptance criterion.
  - Changed responsibility or approval requirement.
- **Verbatim Evidence**: Side-by-side Before/After source passages with exact page references.
- **Exportable Audit Reports**: One-click generation and download of comprehensive `.md` revision reports.

### E. Cross-Document Impact Analysis Engine (`sop_analyzer.py`)
- **Deterministic Interface Rules**: 8 high-precision physical/geometric interface couplings across shop-floor operations:
  - Hull Welding $\leftrightarrow$ Turret Integration (Turret Base Mounting Plane flatness & runout).
  - Hull Welding $\leftrightarrow$ Torsion Suspension (Hull datum transverse bulkhead pitch & hull floor sag).
  - Hull Welding $\leftrightarrow$ Engine Alignment (Engine compartment deck plane & bulkhead concentricity).
  - Engine Alignment $\leftrightarrow$ Torsion Suspension (Final drive input concentricity & sprocket drive heights).
  - Turret Integration $\leftrightarrow$ Gun Calibration (Elevation trunnion coaxiality & bearing play).
  - Torsion Suspension $\leftrightarrow$ Gun Calibration (Hull dynamic ride height & boresight zero reference).
  - Turret Integration $\leftrightarrow$ Hull Welding (Ball race ring mounting bolt torque & flange distortion).
  - Engine Alignment $\leftrightarrow$ Turret Integration (Engine scavenge clearance & plinth NBC sealing perimeter).
- **Classification Hierarchy**: `Direct impact`, `Potential impact`, `Human review required`, `Insufficient evidence`, and `No identified impact`.
- **Interactive Review Workflow**: Human engineering decisions (`ACCEPTED`, `REJECTED`, `INVESTIGATE`) and reviewer notes persisted in SQLite.
- **Traceable Impact Audit Report**: Detailed markdown export of all discovered candidates and review determinations.

---

## 4. Hardware & System Requirements

- **Operating System**: Windows 10 / Windows 11 (64-bit).
- **Architecture**: x86_64 CPU (AVX2 supported).
- **Memory (RAM)**: Minimum 12 GB, recommended 16 GB RAM.
- **Storage**: ~8 GB free disk space (models: ~3.2 GB; dependencies & data: ~2 GB).
- **Network**: **Zero internet connection required** during operation (100% air-gapped / offline).

---

## 5. Offline Installation & Setup Guide

### Step 1: Python Environment Setup
Ensure Python 3.11 (64-bit) is installed and available in your PATH:
```powershell
# Verify Python version
python --version
# Expected: Python 3.11.x

# Create virtual environment (optional if using system Python)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install requirements from local offline packages or pip
pip install -r requirements.txt
```

### Step 2: Tesseract OCR Configuration
Tesseract OCR is pre-configured to detect `C:\TesseractOCR\tesseract.exe` automatically or locate `tesseract` in your system `PATH`.
Verify installation:
```powershell
# Check Tesseract binary
Test-Path "C:\TesseractOCR\tesseract.exe"
# Or run from PATH
tesseract --version
```

### Step 3: Local Ollama AI Setup & Model Registration
Ensure the Ollama executable is available in PATH.
Start the local Ollama server in a background or separate terminal:
```powershell
ollama serve
```

Register the local quantized GGUF models using the provided Modelfiles:
```powershell
cd D:\Parikshith\SOP_Assistant

# Register Gemma 2B text generation model
ollama create gemma-2b:latest -f models\ModelFile-gemma

# Register Nomic 768-dim embedding model
ollama create nomic-embed-text:latest -f models\ModelFile-embed

# Verify model registrations
ollama list
```
Expected output:
```
NAME                      ID              SIZE      MODIFIED
gemma-2b:latest           ...             3.1 GB    ...
nomic-embed-text:latest   ...             84 MB     ...
```

---

## 6. Launching the Application

### Option A: Automated PowerShell Launcher (Recommended)
Run the automated verification and launcher script from PowerShell:
```powershell
.\run_app.ps1
```
The script performs 6 health checks (Python, Ollama service, model registrations, Tesseract OCR, FAISS index, and SQLite database) before starting Streamlit.

### Option B: Direct Streamlit Execution
```powershell
streamlit run app.py
```
Open your browser to `http://localhost:8501`.

---

## 7. Running the Automated Test Suite

The system includes a verification suite with **101 tests across 9 phases**:

```powershell
# Run individual phase suites
python test_phase1.py   # PDF Extraction & OCR (9 tests)
python test_phase2.py   # Ollama & Embeddings (11 tests)
python test_phase3.py   # FAISS Retrieval & Grounding (14 tests)
python test_phase4.py   # Streamlit RAG Chatbot (10 tests)
python test_phase5.py   # SQLite History & Persistence (10 tests)
python test_phase6.py   # Streaming & Cancellation (11 tests)
python test_phase7.py   # Revision Comparison (12 tests)
python test_phase8.py   # Cross-Document Impact (14 tests)
python test_phase9.py   # Final System Verification & Benchmarks (10 tests)
```

**Overall Test Suite Result: 101 / 101 Tests Passing (100% Pass Rate).**

---

## 8. Data Management & Backup Guidance

All production persistent data resides under the local `data/` directory:
- `data/faiss_index/` — FAISS vector index (`sop.index`), metadata (`chunk_metadata.json`), and manifest (`index_manifest.json`).
- `data/sop_assistant.db` — SQLite database storing consultations, messages, citations, and human review decisions.
- `data/documents/` — Uploaded supplementary SOP documents.

### Recommended Backup Procedure:
```powershell
# Create a timestamped backup of the database and vector corpus
$backupDate = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item -Path "data" -Destination "data_backup_$backupDate" -Recurse
```

### Rebuilding the FAISS Corpus:
If documents in `SOP/` are added or updated, click **Rebuild FAISS Corpus** under the **Vector Database Management** sidebar in the Streamlit UI, or execute via Python:
```python
import rag_engine as re
re.rebuild_faiss_index()
```

---

## 9. Troubleshooting & Diagnostics

| Symptom | Probable Cause | Corrective Action |
|---|---|---|
| **Ollama Daemon Unreachable** | `ollama serve` is not running. | Open a terminal and run `ollama serve`. Verify with `curl http://127.0.0.1:11434/api/tags`. |
| **Missing AI Models** | GGUF models not registered in Ollama. | Execute `ollama create gemma-2b:latest -f models\ModelFile-gemma` and `ollama create nomic-embed-text:latest -f models\ModelFile-embed`. |
| **FAISS Index Missing** | First-time startup without index build. | Click **Rebuild FAISS Corpus** in the Streamlit sidebar expander. |
| **OCR Standby / Not Detected** | Tesseract not found in PATH or `C:\TesseractOCR`. | Install Tesseract OCR to `C:\TesseractOCR` or add its directory to system `PATH`. |
| **Slow Inference on CPU** | Large batch or thread contention. | Reduce `max_tokens` or lower Top-K from 5 to 3 in sidebar controls. |

---

## 10. Security & Air-Gapped Compliance

- **No Remote Telemetry**: Zero external web requests, analytics, or remote API calls.
- **Loopback Only**: All network traffic is strictly bound to `127.0.0.1` (localhost).
- **Official Secrets Act Compliance**: Technical documents, parameters, and review logs remain strictly on local authorized DPSU hardware.

