# PROJECT AUDIT: SOP DOCUMENT INTELLIGENCE AND REVISION IMPACT ANALYSIS AGENT

**Audit Date:** November 02, 2026  
**Project Workspace:** `D:\Parikshith\SOP_Assistant`  
**Operating System:** Microsoft Windows 11 / Windows 10 (Build 26300, 64-bit)  
**Hardware Profile:** 15.29 GB RAM Total (~16 GB physical), CPU-only inference target  

---

## 1. Existing Project Inventory

The workspace was inspected and inventoried without modifying any existing generator scripts, PDFs, GGUF files, or Modelfiles:

```
D:\Parikshith\SOP_Assistant
├── docs_generator/
│   ├── generate_hvf_sops.py          [78,632 bytes, 1,439 lines] - ReportLab SOP generator for Baseline v1 SOPs
│   └── generate_hvf_sops_v2.py       [78,342 bytes, 1,426 lines] - ReportLab SOP generator for Revision v2 SOPs
├── models/
│   ├── gemma-4-E2B-it-Q4_K_M.gguf    [3,106,738,272 bytes (~3.1 GB)] - Gemma 4.6B instruction-tuned GGUF
│   ├── nomic-embed-text-v1.5.Q4_K_M.gguf [84,106,624 bytes (~84 MB)] - Nomic BERT embedding GGUF
│   ├── ModelFile-gemma               [33 bytes: "FROM ./gemma-4-E2B-it-Q4_K_M.gguf"]
│   └── ModelFile-embed               [42 bytes: "FROM ./nomic-embed-text-v1.5.Q4_K_M.gguf"]
└── SOP/
    ├── HVF_SOP_1_Hull_Welding.pdf           [36,706 bytes, 8 pages]
    ├── HVF_SOP_1_Hull_Welding_v2.pdf        [36,406 bytes, 8 pages]
    ├── HVF_SOP_2_Turret_Integration.pdf     [36,721 bytes, 8 pages]
    ├── HVF_SOP_2_Turret_Integration_v2.pdf  [36,223 bytes, 8 pages]
    ├── HVF_SOP_3_Engine_Alignment.pdf       [36,943 bytes, 8 pages]
    ├── HVF_SOP_3_Engine_Alignment_v2.pdf    [36,334 bytes, 8 pages]
    ├── HVF_SOP_4_Torsion_Suspension.pdf     [36,913 bytes, 8 pages]
    ├── HVF_SOP_4_Torsion_Suspension_v2.pdf  [35,857 bytes, 8 pages]
    ├── HVF_SOP_5_Gun_Calibration.pdf        [37,160 bytes, 8 pages]
    └── HVF_SOP_5_Gun_Calibration_v2.pdf     [35,838 bytes, 8 pages]
```

---

## 2. Environment Findings: Python, Ollama, & OCR

### 2.1 Python Environment
- **Python Version:** `3.11.13` (64-bit, AMD64)
- **Virtual Environment / Global:** `C:\Python31113\`
- **Database Engine:** `sqlite3` built-in, SQLite version `3.45.3`

### 2.2 Ollama Runtime & Service Status
- **Ollama CLI Version:** `0.40.13`
- **Ollama Path:** `C:\Users\LParikshith\AppData\Local\Programs\Ollama\ollama.exe`
- **Daemon Status:** Active and responding on `http://127.0.0.1:11434`
- **Initial State Observation:** The Windows tray wrapper (`ollama app.exe`) had encountered a mutex conflict with an unspecified initialization error, preventing port `11434` from opening. When launched directly as a background service (`ollama serve`), the Ollama daemon initialized cleanly and established the REST API endpoint.

### 2.3 Tesseract OCR
- **Tesseract Executable:** Available at `C:\TesseractOCR\tesseract.exe`
- **Tesseract Version:** `v5.5.3.20260724` with leptonica 1.87.0
- **Supported Accelerations:** AVX512, AVX2, AVX, FMA, SSE4.1
- **Operational Verification:** Verified OCR execution on synthetic images via `pytesseract`. Correctly extracted rendered text with zero errors.

---

## 3. Model Compatibility & Inference Verification

### 3.1 Nomic Embed Text (`nomic-embed-text:latest`)
- **Source GGUF:** `models/nomic-embed-text-v1.5.Q4_K_M.gguf` (84.1 MB)
- **Registration Status:** Verified and registered in Ollama as `nomic-embed-text:latest`
- **Model Architecture:** `nomic-bert` (136.73M parameters, Q4_K_M)
- **Embedding Dimension:** Strictly **768** dimensions
- **Context Length:** 2,048 tokens
- **Inference Verification:**
  - REST test payload: `{"model": "nomic-embed-text:latest", "prompt": "test"}`
  - Result: Returned float array of length 768 in 46ms.
  - Compatibility Verdict: **100% Compatible & Ready**.

### 3.2 Gemma Generation Model (`gemma-2b:latest`)
- **Source GGUF:** `models/gemma-4-E2B-it-Q4_K_M.gguf` (3.11 GB)
- **Modelfile:** `models/ModelFile-gemma` (`FROM ./gemma-4-E2B-it-Q4_K_M.gguf`)
- **Registration Status:** Registered into Ollama as `gemma-2b:latest` (ID: `06a7eb0742bc`)
- **Model Architecture:** `gemma4` (4.6B parameter instruction-tuned variant, Q4_K_M quantization)
- **Context Length:** 131,072 tokens
- **Inference Verification:**
  - Cold load test: Prompt `"Answer in 5 words: What is an SOP?"` executed in 19.4s (model loading + eval), producing `"Standard procedure for routine tasks."`
  - Warm load test: Prompt `"Say hello in 3 words."` executed in 0.43s at **34.16 tokens/sec** on CPU.
  - Streaming test: Verified token-by-token streaming via `ollama.Client().chat(stream=True)` yielding 101 progressive chunks.
  - Compatibility Verdict: **100% Compatible & Ready**.

---

## 4. PDF Inspection Results (All 10 Documents)

All 10 PDF documents were inspected using `pymupdf` (fitz). Every document follows a strict 8-page format generated via ReportLab with high textual density, tabular matrices, and standard formatting:

| File Name | Size (Bytes) | Pages | Total Chars | Scanned / Images | Document ID | Revision & Date | Target Platform & Shop |
| :--- | :---: | :---: | :---: | :---: | :--- | :--- | :--- |
| **HVF_SOP_1_Hull_Welding.pdf** | 36,706 | 8 | 24,848 | 0 (Native Text) | `HVF/AVNL/SOP-MBT/HW-101` | Rev 4.2 (2026) \| 30-Oct-2026 | MBT T-90S / Arjun Mk-1A; Shop-04 |
| **HVF_SOP_1_Hull_Welding_v2.pdf** | 36,406 | 8 | 24,657 | 0 (Native Text) | `HVF/AVNL/SOP-MBT/HW-101-V2` | Rev 5.0 [v2.0] \| 30-Oct-2026 | MBT T-90S / Arjun Mk-1A (Batch-II); Shop-04A |
| **HVF_SOP_2_Turret_Integration.pdf** | 36,721 | 8 | 24,992 | 0 (Native Text) | `HVF/AVNL/SOP-MBT/TI-204` | Rev 3.8 (2026) \| 30-Oct-2026 | MBT T-90S / Arjun Mk-1A; Shop-06 |
| **HVF_SOP_2_Turret_Integration_v2.pdf** | 36,223 | 8 | 24,598 | 0 (Native Text) | `HVF/AVNL/SOP-MBT/TI-204-V2` | Rev 4.5 [v2.0] \| 30-Oct-2026 | MBT T-90S / Arjun Mk-1A (Batch-II); Shop-06B |
| **HVF_SOP_3_Engine_Alignment.pdf** | 36,943 | 8 | 25,074 | 0 (Native Text) | `HVF/AVNL/SOP-MBT/EA-309` | Rev 5.1 (2026) \| 30-Oct-2026 | V-46-6 / V-92S2 Multi-fuel V12; Shop-02 |
| **HVF_SOP_3_Engine_Alignment_v2.pdf** | 36,334 | 8 | 24,569 | 0 (Native Text) | `HVF/AVNL/SOP-MBT/EA-309-V2` | Rev 6.0 [v2.0] \| 30-Oct-2026 | V-92S2 / DATRAN V12; Shop-02C |
| **HVF_SOP_4_Torsion_Suspension.pdf** | 36,913 | 8 | 25,252 | 0 (Native Text) | `HVF/AVNL/SOP-MBT/TS-412` | Rev 4.0 (2026) \| 30-Oct-2026 | High-strain Torsion Suspension; Shop-03 |
| **HVF_SOP_4_Torsion_Suspension_v2.pdf** | 35,857 | 8 | 24,247 | 0 (Native Text) | `HVF/AVNL/SOP-MBT/TS-412-V2` | Rev 5.2 [v2.0] \| 30-Oct-2026 | High-strain Torsion Suspension; Shop-03R |
| **HVF_SOP_5_Gun_Calibration.pdf** | 37,160 | 8 | 25,493 | 0 (Native Text) | `HVF/AVNL/SOP-MBT/GC-518` | Rev 4.6 (2026) \| 30-Oct-2026 | 125mm 2A46M / 120mm Rifled Gun; Shop-08 |
| **HVF_SOP_5_Gun_Calibration_v2.pdf** | 35,838 | 8 | 24,286 | 0 (Native Text) | `HVF/AVNL/SOP-MBT/GC-518-V2` | Rev 5.4 [v2.0] \| 30-Oct-2026 | 125mm 2A46M-5 / 120mm Rifled Mk-II; Shop-08X |

### Text Quality Assessment
1. **Extraction Fidelity:** Direct text extraction via PyMuPDF extracts 100% of the textual content with complete fidelity. No embedded raster images exist in the current PDFs, so PyMuPDF is the high-speed primary path.
2. **OCR Fallback:** Scanned or image-only PDF pages (e.g., if a user uploads a scanned SOP document via the UI) can be detected if extracted text length is below a configurable threshold (e.g., < 50 characters per page), triggering `pytesseract` OCR rendering with `C:\TesseractOCR\tesseract.exe`.
3. **Structured Headings:** Each document has numbered sections (`0.1`, `1.0`, `2.0`, `3.0`, etc.) and structured tabular sections that will allow precise section-aware chunking.

---

## 5. Dependency Audit & Status

| Library / Tool | Required For | Status | Version |
| :--- | :--- | :--- | :--- |
| `python` | Application Runtime | Installed | 3.11.13 |
| `pymupdf` | PDF Text/Page Extraction | Installed | 2.0 |
| `streamlit` | Chatbot Frontend | Installed | 1.66.1 |
| `faiss-cpu` | Vector Similarity Search | Installed | 1.15.1 |
| `pytesseract` | OCR Interface | Installed | 0.3.13 |
| `tesseract.exe` | System OCR Engine | Installed | v5.5.3.20260724 (`C:\TesseractOCR\tesseract.exe`) |
| `ollama` (Python SDK) | Local AI Interface | Installed | 0.6.3 |
| `sqlite3` | Conversation & Metadata Storage | Installed | 3.45.3 (standard library) |
| `reportlab` | SOP Generator Verification | Installed | 5.1.0 |

---

## 6. Identified Risks & Mitigations

1. **Ollama Service Reliability on Windows:**
   - *Risk:* Windows tray `ollama app.exe` had a mutex/socket lock issue initially.
   - *Mitigation:* Ensure `document_processor.py`, `rag_engine.py`, and `app.py` check Ollama availability with graceful fallback messages and instructions if the daemon is offline.
2. **CPU Inference Latency & RAM Consumption:**
   - *Risk:* The system has 15.29 GB RAM, of which ~2.2 GB was initially free. `gemma-2b:latest` takes ~3.1 GB RAM. If available RAM is constrained, page swapping could slow down generation.
   - *Mitigation:* Our warm prompt test achieved 34.16 tokens/sec. We will limit the context window to relevant retrieved chunks (e.g., top-k 3-5 chunks, ~1500 tokens context) to keep memory footprint light and response generation fast.
3. **Chunking Boundary Quality:**
   - *Risk:* Fixed character splitting without section awareness breaks table matrices and technical specifications.
   - *Mitigation:* In Phase 1, implement section-aware and sentence-aware chunking preserving Section Heading, Page Number, Document ID, and Revision Tag.

---

## 7. Recommended Corrections & Next Steps

1. Configure `pytesseract.pytesseract.tesseract_cmd` to explicitly point to `C:\TesseractOCR\tesseract.exe` as the default fallback in `document_processor.py`.
2. Standardize Ollama model names:
   - Generation LLM: `gemma-2b:latest`
   - Embedding Model: `nomic-embed-text:latest`
3. Proceed strictly to **Phase 1: Document Processing** (`document_processor.py`) upon user approval.

