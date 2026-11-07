# Heavy Vehicles Factory (HVF) / Armoured Vehicles Nigam Limited (AVNL)
## Intelligent SOP Document Intelligence & Revision Impact Analysis Assistant
### Module Reference Guide

This document provides a comprehensive technical reference for the five primary Python modules comprising the HVF SOP Assistant architecture.

---

## 1. Overview of Core Modules

```
D:\Parikshith\SOP_Assistant\
├── app.py                  # Module 1: Streamlit Frontend & Telemetry Dashboard
├── document_processor.py   # Module 2: PDF Parsing, Chunker & Component Extractor
├── rag_engine.py           # Module 3: Hybrid Retrieval, Ollama Client & Prompter
├── sop_analyzer.py         # Module 4: Structural Revision Diff & Cross-Impact Engine
└── database.py             # Module 5: Transactional SQLite Storage & History
```

---

## 2. Module 1: `app.py` (Streamlit Frontend & Dashboard)

`app.py` provides the user-facing web interface. Built on Streamlit, it coordinates state management, user input routing, real-time token streaming, evidence card display, and component exploration.

### Key Functions and Components

#### `init_session_state() -> None`
- **Purpose**: Initializes all required `st.session_state` keys upon app boot.
- **Keys Handled**:
  - `current_conv_id`: Active SQLite conversation identifier. Supports `?conv=<id>` URL override.
  - `app_mode_radio`: Operating mode navigation. Supports `?mode=dashboard|chat|explorer|compare|impact|upload`.
  - `is_generating`, `stop_requested`: Thread-safe execution flags for real-time inference cancellation.
  - `target_nav_component`: Pre-selected component when navigating from chat or external query (`?comp=<name>`).
  - `diff_sop_sel`: Pre-selected SOP domain when navigating to revision comparison (`?sop=<name>`).
- **Dependencies**: [`database.init_database()`](file:///d:/Parikshith/SOP_Assistant/database.py).

#### `check_system_telemetry() -> Dict[str, Any]`
- **Decorator**: `@st.cache_data(ttl=10)`
- **Purpose**: Queries live health of all backend subsystems (Ollama daemon, LLM model, embedding model, FAISS index, component records, Tesseract OCR, SQLite database).
- **Return Dict**:
  - `ollama_online` (bool)
  - `llm_ready` (bool)
  - `embed_ready` (bool)
  - `doc_count` (int)
  - `chunk_count` (int)
  - `components_count` (int)
  - `tesseract_ready` (bool)
  - `overall_status` (str: `"HEALTHY"`, `"DEGRADED"`, `"OFFLINE"`)

#### `group_citations_by_source(citations_list: List[Dict]) -> List[Dict]`
- **Purpose**: Deduplicates raw chunk citations by grouping multiple page hits from the same SOP filename and revision, calculating the maximum similarity score.
- **Parameters**: `citations_list` (list of citation dictionaries with `filename`, `page_number`, `score`, `section`).
- **Returns**: Compacted list of unique document sources with sorted page ranges and representative snippets.

#### `render_chat_tab() -> None`
- **Purpose**: Renders the conversation stream, user input bar, stop button, live markdown generator, and collapsible citation cards.
- **Streaming Implementation**: Consumes generator yielded by [`rag_engine.stream_answer()`](file:///d:/Parikshith/SOP_Assistant/rag_engine.py). Updates placeholder every token and renders CSS typing cursor.

#### `render_component_explorer() -> None`
- **Purpose**: Displays the visual and tabular component explorer with multi-level filters:
  - Document filter (All or specific SOP)
  - Revision filter (V1, V2, All)
  - Entity Type filter (`PHYSICAL_COMPONENT`, `ASSEMBLY`, `SUBSYSTEM`, `EQUIPMENT`)
  - Subsystem domain filter
- **Inspector View**: Shows component details, exact SOP citations, evidence status badge, verified relationship graph, and an "Ask AI about this component" action button.

#### `render_revision_diff_tab() -> None`
- **Purpose**: Interactive comparison viewer presenting structural additions/deletions, tolerance shifts (before vs after), tooling upgrades, and side-by-side text diffs.

#### `render_upload_tab() -> None`
- **Purpose**: Transactional upload drop-zone executing the 7-stage ingestion workflow with progress bars and immediate component extraction results.

---

## 3. Module 2: `document_processor.py` (Ingestion & Component Extraction)

`document_processor.py` handles parsing of raw technical PDFs, OCR fallbacks, semantic chunking, and regex-based component extraction.

### Constants
- `CHUNK_SIZE = 500`: Target word count per chunk.
- `CHUNK_OVERLAP = 50`: Overlap word count between consecutive chunks.
- `DEFAULT_SOP_DIR = "SOP"`: Path to standard authoritative SOP PDFs.
- `TESSERACT_BIN = "C:\\TesseractOCR\\tesseract.EXE"`: Primary path to Tesseract OCR binary.

### Key Functions

#### `configure_tesseract() -> Optional[str]`
- **Purpose**: Scans known Windows installation locations for `tesseract.exe` (probing `C:\TesseractOCR\tesseract.EXE`, `C:\Program Files\Tesseract-OCR\tesseract.exe`, and PATH). Configures `pytesseract.pytesseract.tesseract_cmd` automatically.

#### `process_pdf(pdf_path: str) -> Dict[str, Any]`
- **Purpose**: Full processing pipeline for an SOP PDF. Extracts text and tables page by page via `extract_pdf_pages()`, runs OCR fallback if text density is low, constructs semantic chunks via `create_document_chunks()`, and extracts component records via `extract_components_from_document()`.
- **Returns**:
  ```python
  {
      "metadata": {"document_id": "...", "title": "...", "revision": "..."},
      "pages": [{"page_number": 1, "text": "...", "tables": [...]}],
      "chunks": [{"chunk_id": "...", "chunk_text": "...", "page_number": 1, ...}],
      "components": [{"component_id": "...", "component_name": "...", ...}]
  }
  ```

#### `create_document_chunks(pages: List[Dict], ...) -> List[Dict[str, Any]]`
- **Purpose**: Implements deterministic hierarchical semantic chunking over extracted PDF pages.
- **Chunk Schema**:
  - `chunk_id` (str): e.g., `"HVF_SOP_2_Turret_Integration_chunk_001"`
  - `chunk_text` (str): 500-word block with 50-word overlap
  - `filename` (str)
  - `logical_sop_id` (str): e.g., `"HVF_SOP_2_Turret_Integration"`
  - `revision` (str): `"Rev 3.8 (2026)"` / `"Rev 4.5 [Version 2.0]"`
  - `page_number` (int), `page_numbers` (List[int])
  - `section_title` (str): Inferred section header (e.g., `"3.0 Assembly Procedure"`)
  - `token_count` (int), `char_count` (int)

#### `extract_components_from_document(doc_data: Dict[str, Any]) -> List[Dict[str, Any]]`
- **Purpose**: Extracts structured component records from SOP text.
- **Entity Classification**:
  - `PHYSICAL_COMPONENT`: Discrete parts (e.g., `"Torsion Bar"`, `"Drive Sprocket"`)
  - `ASSEMBLY`: Mechanical groupings (e.g., `"Turret Ring Assembly"`, `"Hydraulic Rotary Damper"`)
  - `SUBSYSTEM`: Major vehicle systems (e.g., `"Traverse Drive Subsystem"`)
  - `TOOL_OR_INSTRUMENT` / `EQUIPMENT`: Tooling and instruments (e.g., `"Dial Test Indicator"`)
  - Plus `MATERIAL`, `TECHNICAL_PARAMETER`, `PROCESS_OR_OPERATION`, `DOCUMENT_OR_CERTIFICATE`, `OTHER_REFERENCE`, `ACCEPTANCE_CRITERION`.
- **Relationship Rule**: Only sets explicit links (`parent_assembly`, `connected_to`) when direct structural connection is stated in the SOP text. Co-occurring entities are not assumed to be related.
- **Returns**: List of component record dictionaries.

---

## 4. Module 3: `rag_engine.py` (Hybrid Retrieval & Generation)

`rag_engine.py` orchestrates Ollama API communication, dense vector retrieval via FAISS, component record matching, prompt assembly, and response streaming.

### Key Functions

#### `get_ollama_client() -> OllamaClient`
- **Purpose**: Thread-safe HTTP loopback client communicating with `http://127.0.0.1:11434`.

#### `generate_embedding(text: str, model: str = 'nomic-embed-text:latest', endpoint: str = 'http://127.0.0.1:11434', normalize: bool = True) -> np.ndarray`
- **Model**: `nomic-embed-text:latest` (768 dimensions).
- **Processing**: Automatically strips whitespace, normalizes via L2 norm (`vec / norm`), and returns `float32` array of shape `(768,)` for inner product FAISS similarity.

#### `load_faiss_index(index_dir: str = "data/faiss_index") -> Tuple[faiss.Index, List[Dict], Dict]`
- **Purpose**: Loads pre-built `sop.index` (FAISS `IndexFlatIP`), chunk metadata from `chunk_metadata.json`, and manifest from `index_manifest.json`.
- **Invariants**: Baseline contains exactly 150 vectors representing 10 SOP PDFs.

#### `load_components_metadata(path: str = "data/faiss_index/components_metadata.json") -> List[Dict]`
- **Purpose**: Loads the 517 structured component records.
- **Invariants**: 517 total records across 10 logical SOP revisions (145 hardware entities).

#### `resolve_conversational_query(question: str, history: List[Dict]) -> Tuple[str, Optional[str]]`
- **Purpose**: Resolves conversational antecedents, pronouns ("it", "they", "these parts"), and follow-ups against prior turns.
- **Returns**: `(effective_question, antecedent_component_name)`.

#### `retrieve_component_aware_evidence(query: str, top_k_chunks: int = 5, ...) -> Dict[str, Any]`
- **Purpose**: Performs dual retrieval:
  1. Dense vector search over FAISS index using cosine similarity.
  2. Structured lookup in `components_metadata.json` for exact entity mentions.
- **Revision Filtering**: Filters out chunks and component records that do not match the selected revision (`"V1"`, `"V2"`, or `"ALL"`).

#### `generate_rag_answer(question: str, ...) -> Dict[str, Any]`
- **Purpose**: Synthesizes evidence-grounded answer to technical questions using retrieved chunks and structured component metadata.
- **Returns**: Dictionary with `answer`, `citations`, `is_insufficient`, `is_cross_revision`, `component_intent`, `tokens_per_second`.

#### `stream_rag_answer(question: str, ...) -> Generator`
- **Purpose**: Primary generator for interactive streaming in Streamlit.
- **Yields**: Successive token strings as generated by Ollama `gemma-2b:latest`.
- **Final Yield**: Citation metadata dictionary containing source chunks, page numbers, and similarity scores.

#### `get_comprehensive_system_health() -> Dict[str, Any]`
- **Purpose**: Deep diagnostic check inspecting Ollama loopback, model availability, FAISS dimension and vector count, component metadata consistency, and SQLite schema integrity.

---

## 5. Module 4: `sop_analyzer.py` (Revision & Impact Analysis)

`sop_analyzer.py` performs deterministic analytical diffing between baseline and revised SOPs.

### Key Functions

#### `compare_sop_files(v1_path: str, v2_path: str) -> Dict[str, Any]`
- **Purpose**: Compares two PDF revisions of an SOP.
- **Analysis Categories**:
  - `structural_changes`: Added, deleted, and modified sections.
  - `tolerance_changes`: Regex extraction of numerical tolerances (e.g., `±0.05 mm` -> `±0.02 mm`).
  - `tooling_changes`: Tooling and equipment shifts (e.g., torque wrenches, lubricants).
  - `safety_changes`: Safety warnings, PPE requirements, hazardous material notices.
  - `component_evolution`: Components introduced or superseded between revisions.

#### `analyze_cross_document_impacts(logical_sop_id: str) -> List[Dict[str, Any]]`
- **Purpose**: Traces interface dependencies between vehicle subsystems.
- **Dependency Map**:
  - `HVF-TR` (Turret) <-> `HVF-HW` (Hull Ring Interface)
  - `HVF-EP` (Powerpack) <-> `HVF-HW` (Engine Bay Mounts)
  - `HVF-TS` (Suspension) <-> `HVF-HW` (Hull Torsion Tube Sockets)
  - `HVF-GC` (Gun Calibration) <-> `HVF-TR` (Trunnion & Azimuth Drives)
- **Returns**: List of potential impact warnings grounded in explicit structural interfaces.

---

## 6. Module 5: `database.py` (Persistence & History)

`database.py` manages persistent storage using standard library `sqlite3` with thread-safe connection pooling and WAL mode.

### Key Functions

#### `init_database(db_path: str = "data/sop_assistant.db") -> None`
- **Purpose**: Creates SQLite tables (`conversations`, `messages`, `uploaded_documents`, `indexing_history`) and indexes if they do not exist. Enables Foreign Key constraints.

#### `create_conversation(title: str = "New Consultation") -> Dict[str, Any]`
- **Purpose**: Creates a new conversation row with a unique UUID4.
- **Returns**: `{"conversation_id": "...", "title": "...", "created_at": "..."}`.

#### `save_message(conv_id: str, role: str, content: str, citations: List[Dict] = None) -> int`
- **Purpose**: Persists a message with serialized JSON citations into `messages` table.
- **Returns**: Auto-incremented `message_id`.

#### `get_conversation_messages(conv_id: str) -> List[Dict[str, Any]]`
- **Purpose**: Retrieves chronological message history with parsed citation JSON.

#### `record_uploaded_document(filename: str, file_hash: str, file_size: int, total_pages: int, total_chunks: int) -> str`
- **Purpose**: Logs ingested document metadata. Enforces unique file hash to prevent duplicate ingestion.

