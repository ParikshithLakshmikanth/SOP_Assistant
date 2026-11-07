# Heavy Vehicles Factory (HVF) / Armoured Vehicles Nigam Limited (AVNL)
## Intelligent SOP Document Intelligence & Revision Impact Analysis Assistant
### System Architecture Specification

---

## 1. Executive Summary & Operational Context

The **SOP Document Intelligence & Revision Impact Analysis Assistant** is an offline-first, defense-grade technical intelligence platform engineered specifically for the Heavy Vehicles Factory (HVF), an operational production facility of Armoured Vehicles Nigam Limited (AVNL) located in Avadi, Chennai, Tamil Nadu, India.

HVF is the premier manufacturing complex for armored fighting vehicles (AFVs) in India, producing frontline main battle tanks (MBTs) such as the **T-90 Bhishma**, **T-72 Ajeya**, and the **Arjun MBT**, alongside heavy recovery and support vehicles. In defense manufacturing environments, Standard Operating Procedures (SOPs) govern mission-critical processes:
* Heavy armor plate welding and radiographic joint inspections
* Turret-hull ring integration and azimuth bearing runout checks
* V12 twin-turbo powerpack engine alignment and driveline backlash adjustments
* High-pressure hydraulic suspension and track-tensioning calibrations
* Main gun barrel trunnion mounting and digital fire-control zeroing

The application operates under a **strict air-gapped, CPU-only security envelope**. No engineering data, CAD references, tolerances, or procedure logs ever leave the local hardware perimeter. All intelligence is powered by local quantized open-weights models executed via Ollama, indexed using FAISS vector spaces, and tracked through a local SQLite transactional store.

---

## 2. High-Level System Architecture

The application adopts a modular, 5-tier architecture combining low-level document parsing, dense semantic vector retrieval, structured domain component graphs, cross-revision analytical diffing, and an interactive executive interface.

```mermaid
graph TD
    subgraph UI ["Tier 1: User Interface & Presentation (app.py)"]
        UI_Dash["Executive Telemetry Dashboard"]
        UI_Chat["Technical Consultation Chatbot"]
        UI_Exp["Visual Component Explorer"]
        UI_Diff["SOP Revision Comparison Engine"]
        UI_Impact["Cross-Document Impact Analysis"]
        UI_Upload["Transactional Ingestion Interface"]
    end

    subgraph Core ["Tier 2: Orchestration & Intelligence (rag_engine.py & sop_analyzer.py)"]
        Router["Intent Router & Conversational Resolver"]
        HybridRet["Hybrid Vector & Component Retriever"]
        PromptEng["Context Assembler & Grounding Prompter"]
        CompEngine["Component Extraction & Graph Engine"]
        DiffEngine["Structural & Numerical Diff Engine"]
    end

    subgraph Inference ["Tier 3: Local Offline Inference (Ollama Air-Gapped Loopback)"]
        LLM["Ollama: gemma-2b:latest (Instruction Model)"]
        Embedder["Ollama: nomic-embed-text:latest (768-dim Embeddings)"]
    end

    subgraph Parsing ["Tier 4: Document Parsing & Ingestion (document_processor.py)"]
        PyMuPDF["PyMuPDF (fitz) Text & Layout Extractor"]
        Tesseract["Tesseract OCR Engine (Scanned PDFs)"]
        Chunker["Semantic Hierarchical Chunker (500 tokens / 50 overlap)"]
        MetadataExtract["Header, Table & Metadata Normalizer"]
    end

    subgraph Storage ["Tier 5: Persistence & Indices (Data Storage Layer)"]
        FAISS["FAISS Index (sop.index - 150 Vectors)"]
        Manifest["Corpus Manifest (index_manifest.json)"]
        CompDB["Component Metadata (components_metadata.json - 517 Records)"]
        SQLite["Transactional SQLite DB (sop_assistant.db)"]
        PDFDir["Air-Gapped PDF Corpus (SOP/*.pdf)"]
    end

    UI --> Router
    Router --> HybridRet
    HybridRet --> FAISS
    HybridRet --> CompDB
    HybridRet --> Embedder
    Router --> PromptEng
    PromptEng --> LLM
    LLM --> UI_Chat

    UI_Diff --> DiffEngine
    UI_Impact --> DiffEngine
    UI_Exp --> CompEngine
    CompEngine --> CompDB

    UI_Upload --> PyMuPDF
    PyMuPDF --> Chunker
    Chunker --> Embedder
    Embedder --> FAISS
    UI_Chat --> SQLite
```

---

## 3. Five Core Modules & Responsibilities

The system maintains strict architectural modularity across five distinct Python modules:

| Module | Architectural Role | Core Responsibilities |
| :--- | :--- | :--- |
| [`app.py`](file:///d:/Parikshith/SOP_Assistant/app.py) | **Module 1: Streamlit Frontend** | Executive dashboard, telemetry, conversation tabs, live streaming LLM responses with typing indicators, interactive Component Explorer, revision comparison viewers, and 7-stage upload UI. |
| [`document_processor.py`](file:///d:/Parikshith/SOP_Assistant/document_processor.py) | **Module 2: Document Ingestion** | PDF text and table extraction via PyMuPDF, OCR fallback with Tesseract, deterministic semantic chunking (500 words, 50 word overlap), document hash deduplication, and component entity extraction. |
| [`rag_engine.py`](file:///d:/Parikshith/SOP_Assistant/rag_engine.py) | **Module 3: Hybrid Retrieval & Generation** | Hybrid retrieval fusing FAISS cosine dense vectors and structured component records, revision filtering (V1, V2, All), streaming Ollama inference, query resolution, and system health checks. |
| [`sop_analyzer.py`](file:///d:/Parikshith/SOP_Assistant/sop_analyzer.py) | **Module 4: Revision & Impact Analysis** | Section-by-section structural diffing between V1 and V2 SOPs, numerical tolerance shift extraction, tooling/safety change detection, and cross-subsystem interface impact propagation. |
| [`database.py`](file:///d:/Parikshith/SOP_Assistant/database.py) | **Module 5: Persistence & History** | SQLite database schema (`conversations`, `messages`, `uploaded_documents`, `indexing_history`), foreign keys, transactions, and conversation persistence. |

---

## 4. PDF Ingestion & Indexing Pipeline

Every technical SOP undergoes a deterministic, 7-stage transactional ingestion pipeline to guarantee reproducible indexing and avoid duplicate vector corruptions.

```mermaid
flowchart TD
    A["Raw SOP PDF Upload (e.g., HVF_SOP_2_Turret_Integration.pdf)"] --> B["Stage 1: Validation & Deduplication (SHA-256 Hash Check)"]
    B -->|Duplicate Found| B1["Reject Duplicate / Return Existing Record"]
    B -->|Unique File| C["Stage 2: Text Extraction via PyMuPDF (fitz)"]
    C -->|Low Text Density| C1["Stage 2B: Fallback to Tesseract OCR Engine"]
    C -->|Text Extracted| D["Stage 3: Metadata & Section Normalization"]
    C1 --> D
    D --> E["Stage 4: Semantic Hierarchical Chunking (500 words, 50-word overlap)"]
    E --> F["Stage 5: Regex & Context Component Extraction (Components, Subsystems, Specs)"]
    F --> G["Stage 6: Dense Embedding Generation (Ollama nomic-embed-text: 768 dims)"]
    G --> H["Stage 7: Atomic Transactional Commit"]
    H --> H1["Append Vectors to data/faiss_index/sop.index"]
    H --> H2["Persist Records in components_metadata.json"]
    H --> H3["Record Document & Ingestion Log in SQLite"]
    H --> H4["Update index_manifest.json"]
```

---

## 5. Query Processing & Hybrid RAG Retrieval Workflow

When an engineer asks a technical question, the system resolves conversational pronouns, extracts target component entities, and executes hybrid retrieval combining vector similarity with structured component facts.

```mermaid
sequenceDiagram
    autonumber
    actor Engineer as Tank Assembly Engineer
    participant UI as app.py (Streamlit)
    participant RE as rag_engine.py
    participant Ollama as Ollama Daemon (Local CPU)
    participant FAISS as FAISS Index (IndexFlatIP)
    participant Meta as Component Metadata (JSON)

    Engineer->>UI: "What are the main components of the turret mount system?"
    UI->>RE: answer_question(question, revision_filter="All")
    RE->>RE: resolve_conversational_query(question, history)
    RE->>Meta: match_components_in_text(effective_question)
    Meta-->>RE: Return 4 matched components (Turret Ring, Traverse Gearbox, Bearing...)
    RE->>Ollama: POST /api/embeddings (nomic-embed-text)
    Ollama-->>RE: 768-dimensional query vector (normalized L2)
    RE->>FAISS: index.search(query_vec, top_k=8)
    FAISS-->>RE: Top 8 FAISS chunk indices & inner product scores
    RE->>RE: Filter chunks by revision (V1, V2, or All)
    RE->>RE: Assemble Prompt (Compact Evidence Chunks + Structured Component Facts)
    RE->>Ollama: POST /api/chat (gemma-2b:latest, stream=True)
    loop Token Streaming
        Ollama-->>RE: Token chunk
        RE-->>UI: Yield token chunk
        UI-->>Engineer: Live markdown rendering with blinking cursor
    end
    RE->>UI: Append traceable citations (filename, revision, section, page)
    UI->>Engineer: Display interactive evidence cards & related component chips
```

---

## 6. Component Extraction & Relationship Validation Flow

The system extracts technical entities from SOP text into structured records, categorizing them into explicit types and strictly validating relationships only when documented in the text.

```mermaid
flowchart LR
    subgraph SOP_Text ["Raw SOP Technical Text"]
        Raw["...The Turret Base Ring mounts to the Hull Turret Ring via 48 Grade 10.9 bolts..."]
    end

    subgraph Extraction ["Component Extractor (document_processor.py)"]
        Regex["Regex Technical Patterns (Mounts, Bearings, Drives, Turbos)"]
        Taxonomy["Hierarchical Taxonomy Classifier"]
    end

    subgraph Typing ["Entity Classification"]
        PC["PHYSICAL_COMPONENT (e.g., Ceramic-Hybrid Bearing)"]
        AS["ASSEMBLY (e.g., Turret Ring Assembly)"]
        SS["SUBSYSTEM (e.g., Traverse Drive Subsystem)"]
        EQ["EQUIPMENT / TOOLING (e.g., Ultrasonic Flaw Detector)"]
    end

    subgraph EvidenceGate ["Evidence & Grounding Gate"]
        Check1{"Explicit Text Match in Chunk?"}
        Check2{"Direct Structural Relationship Documented?"}
    end

    subgraph Persistence ["Persistence Layer"]
        CompStore["components_metadata.json (517 Records)"]
    end

    Raw --> Regex
    Regex --> Taxonomy
    Taxonomy --> PC
    Taxonomy --> AS
    Taxonomy --> SS
    Taxonomy --> EQ
    PC --> Check1
    AS --> Check1
    SS --> Check1
    EQ --> Check1
    Check1 -- Yes --> Check2
    Check1 -- No --> Reject["Mark UNCERTAIN / Exclude"]
    Check2 -- "Explicit Link Found" --> Link["Set relationship: parent_assembly / connects_to"]
    Check2 -- "Only Co-occurring" --> NoLink["Leave relationships empty (Do NOT infer)"]
    Link --> CompStore
    NoLink --> CompStore
```

---

## 7. SOP Revision Comparison & Impact Analysis Flow

When comparing baseline V1 against revised V2 SOPs, the analysis engine detects section modifications, numerical tolerance tightening, tooling shifts, and cascading interface impacts.

```mermaid
flowchart TD
    subgraph Input ["Baseline & Revised Documents"]
        V1["Baseline SOP V1 (e.g., HVF-TR-2024-V1.pdf)"]
        V2["Revised SOP V2 (e.g., HVF-TR-2025-V2.pdf)"]
    end

    subgraph SOPAnalyzer ["Diff & Impact Engine (sop_analyzer.py)"]
        DocParser["Section & Paragraph Alignment"]
        TextDiff["Unified Text Diff (difflib)"]
        TolDiff["Numerical Tolerance Extractor (Regex & Units)"]
        ToolDiff["Tooling, Equipment & Safety Rule Comparator"]
        GraphImpact["Subsystem Interconnection Dependency Graph"]
    end

    subgraph Outputs ["Structured Comparison Artifacts"]
        Out1["Structural Section Changes (Added, Removed, Modified)"]
        Out2["Tolerance Shifts (e.g., ±0.05 mm tightened to ±0.02 mm)"]
        Out3["Tooling & Consumable Upgrades (e.g., Molykote -> Krytox)"]
        Out4["Cross-Subsystem Interface Impact Warnings"]
    end

    V1 --> DocParser
    V2 --> DocParser
    DocParser --> TextDiff
    DocParser --> TolDiff
    DocParser --> ToolDiff
    DocParser --> GraphImpact

    TextDiff --> Out1
    TolDiff --> Out2
    ToolDiff --> Out3
    GraphImpact --> Out4
```

---

## 8. Uploaded-Document Ingestion Lifecycle

The application supports transactional ingestion of newly uploaded user documents while preserving the baseline invariants (150 vectors and 517 baseline components).

```mermaid
stateDiagram-v2
    [*] --> Idle: Application Ready (150 Chunks, 517 Components)
    Idle --> Validating: User Uploads PDF in Ingest Interface
    Validating --> Rejected: Duplicate SHA-256 or Invalid PDF
    Rejected --> Idle: Display Warning Card

    Validating --> Processing: Valid Unique PDF
    Processing --> Chunking: Extract Text via PyMuPDF / OCR
    Chunking --> Embedding: Compute Embeddings via Local Ollama
    Embedding --> Indexing: Append to In-Memory FAISS Index
    Indexing --> Extracted: Extract Component Records
    Extracted --> Persisted: Commit to SQLite & Session Metadata
    Persisted --> Searchable: Incremental Chunks Active (150 + N)

    Searchable --> Reverted: User Clears Session / System Restarts
    Reverted --> Idle: Reloads Clean Baseline (150 Vectors, 517 Records)
```

---

## 9. Data Storage & Persistence Architecture

The persistence tier relies on three complementary formats chosen for robustness, auditability, and defense compliance:

```
SOP/
├── HVF_SOP_1_Hull_Welding.pdf          # Hull Welding V1
├── HVF_SOP_1_Hull_Welding_v2.pdf       # Hull Welding V2
├── HVF_SOP_2_Turret_Integration.pdf    # Turret Integration V1
├── HVF_SOP_2_Turret_Integration_v2.pdf # Turret Integration V2
├── HVF_SOP_3_Engine_Alignment.pdf      # Engine Alignment V1
├── HVF_SOP_3_Engine_Alignment_v2.pdf   # Engine Alignment V2
├── HVF_SOP_4_Torsion_Suspension.pdf    # Track & Suspension V1
├── HVF_SOP_4_Torsion_Suspension_v2.pdf # Track & Suspension V2
├── HVF_SOP_5_Gun_Calibration.pdf       # Gun Calibration V1
└── HVF_SOP_5_Gun_Calibration_v2.pdf    # Gun Calibration V2

data/
├── faiss_index/
│   ├── sop.index                   # FAISS IndexFlatIP (150 baseline 768-dim L2-normalized vectors)
│   ├── index_manifest.json         # Master manifest: 10 indexed PDFs, chunk ranges, hashes
│   └── components_metadata.json    # 517 structured entity records with exact citations
└── sop_assistant.db                # SQLite 3 transactional store (Conversations, Citations, History)
```

### SQLite Schema (`sop_assistant.db`)
1. **`conversations`**:
   - `conversation_id` (TEXT, PK): UUID4 identifier.
   - `title` (TEXT): Auto-generated or user-edited conversation title.
   - `created_at` (TIMESTAMP): Creation time in ISO-8601 format.
   - `updated_at` (TIMESTAMP): Last active timestamp.
2. **`messages`**:
   - `message_id` (INTEGER, PK, Auto-increment).
   - `conversation_id` (TEXT, FK -> `conversations.conversation_id`).
   - `role` (TEXT): `'user'` or `'assistant'`.
   - `content` (TEXT): Full response or prompt text.
   - `citations` (TEXT): JSON-serialized array of evidence citations.
   - `timestamp` (TIMESTAMP).
3. **`uploaded_documents`**:
   - `doc_id` (TEXT, PK): UUID4 identifier.
   - `filename` (TEXT): Original filename.
   - `file_hash` (TEXT, UNIQUE): SHA-256 checksum.
   - `file_size` (INTEGER): File size in bytes.
   - `total_pages` (INTEGER): Page count.
   - `total_chunks` (INTEGER): Vector count.
   - `ingested_at` (TIMESTAMP).
4. **`indexing_history`**:
   - `event_id` (INTEGER, PK, Auto-increment).
   - `event_type` (TEXT): `'INITIAL_INDEX'`, `'INCREMENTAL_UPLOAD'`, `'REINDEX'`.
   - `total_documents` (INTEGER).
   - `total_vectors` (INTEGER).
   - `status` (TEXT): `'SUCCESS'`, `'FAILED'`.
   - `timestamp` (TIMESTAMP).

---

## 10. Security, Air-Gap, and Operational Boundaries

The system enforces strict operational constraints to comply with defense data governance standards:

* **Strict Air-Gap Compliance**: Zero external socket connections. The socket layer binds exclusively to loopback `127.0.0.1:11434` for Ollama and `127.0.0.1:8501` for the local Streamlit dashboard. All external DNS, HTTP, HTTPS, and cloud API calls are blocked.
* **CPU Execution Compatibility**: All inference models (`gemma-2b` and `nomic-embed-text`) are quantized to run on standard multicore x86_64 CPUs without requiring dedicated CUDA/GPU hardware.
* **Deterministic Fact Grounding**: The LLM prompt engineering explicitly instructs the model to refuse answering when evidence is not contained in the retrieved context chunks. Component functions and relationships are never inferred from co-occurrence or naming conventions.

