# Heavy Vehicles Factory (HVF) / Armoured Vehicles Nigam Limited (AVNL)
## Intelligent SOP Document Intelligence & Revision Impact Analysis Assistant
### Data Flow & Serialization Specification

This document details the data contracts, JSON schemas, database DDLs, and cross-module serialization formats utilized across the system.

---

## 1. Document Chunk Schema (`index_manifest.json`)

Semantic text chunks represent the primary retrieval units stored in the FAISS index and tracked in `data/faiss_index/index_manifest.json`.

```json
{
  "chunk_id": "HVF_SOP_2_Turret_Integration_chunk_004",
  "filename": "HVF_SOP_2_Turret_Integration.pdf",
  "logical_sop_id": "HVF_SOP_2_Turret_Integration",
  "sop_domain": "Turret Integration",
  "revision": "Rev 3.8 (2026)",
  "page_number": 2,
  "section_title": "3.2 Azimuth Bearing Alignment",
  "token_count": 482,
  "embedding_dim": 768,
  "chunk_text": "3.2 Azimuth Bearing Alignment:\nThe Turret Base Ring must be placed concentrically with the Hull Interface Ring. Prior to bolting, measure the radial runout using a calibrated Dial Test Indicator. Total indicated runout must not exceed 0.05 mm across 360 degrees of rotation. Lubricate all bearing races with Molykote G-Rapid Plus prior to final bolt torquing..."
}
```

### Schema Constraints
- `chunk_id` is globally unique and formatted as `{filename}_chunk_{index:03d}`.
- `word_count` targets 500 words with a 50-word sliding overlap across adjacent chunks within the same document.
- `embedding_dim` is strictly 768 to match `nomic-embed-text:latest`.

---

## 2. Component Metadata Schema (`components_metadata.json`)

Extracted technical entities are persisted in `data/faiss_index/components_metadata.json` (517 baseline records).

```json
{
  "component_id": "COMP-TR-V1-0012",
  "component_name": "Turret Base Ring",
  "normalized_name": "turret base ring",
  "entity_type": "PHYSICAL_COMPONENT",
  "subsystem": "Turret Mount System",
  "logical_sop_id": "HVF_SOP_2_Turret_Integration",
  "revision": "Rev 3.8 (2026)",
  "filename": "HVF_SOP_2_Turret_Integration.pdf",
  "evidence_status": "EXPLICITLY_GROUNDED",
  "source_reference": {
    "filename": "HVF_SOP_2_Turret_Integration.pdf",
    "revision": "Rev 3.8 (2026)",
    "section": "3.2 Azimuth Bearing Alignment",
    "page_number": 2,
    "chunk_id": "HVF_SOP_2_Turret_Integration_chunk_004"
  },
  "specifications": {
    "material": "Forged Ni-Cr-Mo Alloy Steel",
    "runout_tolerance": "0.05 mm",
    "fasteners": "48x Grade 10.9 M24 Bolts",
    "torque_spec": "650 Nm"
  },
  "relationships": {
    "parent_assembly": "Turret Mount Assembly",
    "connected_to": [
      "Hull Interface Ring",
      "Azimuth Drive Pinion"
    ]
  },
  "is_uncertain": false
}
```

### Entity Type Taxonomy (517 Total Records across 10 Distinct Types)
The component metadata database categorizes entities into 10 explicit types, of which **145 are core hardware entities** (`PHYSICAL_COMPONENT`, `ASSEMBLY`, `SUBSYSTEM`):
1. `OTHER_REFERENCE`: 168 records (general references, visual callouts, standard designations).
2. `TECHNICAL_PARAMETER`: 122 records (numerical tolerances, pressures, clearances).
3. `PHYSICAL_COMPONENT`: 97 records (discrete machined parts: bearings, torsion bars, injector nozzles).
4. `ASSEMBLY`: 43 records (interconnected mechanical groupings: turret ring assembly, bogie wheel arm).
5. `PROCESS_OR_OPERATION`: 32 records (surface preparation, torque tightening, radiographic testing).
6. `MATERIAL`: 28 records (weld wire, alloy steel, aerospace lubricants, primers).
7. `TOOL_OR_INSTRUMENT` / `EQUIPMENT`: 14 records (dial test indicator, ultrasonic flaw detector).
8. `DOCUMENT_OR_CERTIFICATE`: 7 records (DGQA acceptance certificates, welding certifications).
9. `SUBSYSTEM`: 5 records (major functional vehicle domains: traverse drive subsystem, suspension).
10. `ACCEPTANCE_CRITERION`: 1 record (quality gate criteria).

---

## 3. Citation & Evidence Schema

Whenever the RAG chatbot answers an engineering query, it attaches structured citation metadata to every response.

```json
{
  "source_id": "SRC-001",
  "filename": "HVF_SOP_2_Turret_Integration.pdf",
  "logical_sop_id": "HVF_SOP_2_Turret_Integration",
  "revision": "V1",
  "section": "3.2 Azimuth Bearing Alignment",
  "page_number": 2,
  "chunk_id": "HVF-TR-2024-V1_chunk_004",
  "similarity_score": 0.8842,
  "snippet": "Prior to bolting, measure the radial runout using a calibrated Dial Test Indicator. Total indicated runout must not exceed 0.05 mm across 360 degrees of rotation..."
}
```

---

## 4. SQLite Relational Schema (`data/sop_assistant.db`)

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- 1. Conversation Sessions
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Message History with Traceable Citations
CREATE TABLE IF NOT EXISTS messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT CHECK(role IN ('user', 'assistant')) NOT NULL,
    content TEXT NOT NULL,
    citations TEXT, -- JSON Array of Citation Objects
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(conversation_id) ON DELETE CASCADE
);

-- 3. Ingested Upload Document Catalog
CREATE TABLE IF NOT EXISTS uploaded_documents (
    doc_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_hash TEXT NOT NULL UNIQUE,
    file_size INTEGER NOT NULL,
    total_pages INTEGER NOT NULL,
    total_chunks INTEGER NOT NULL,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Indexing Audit History
CREATE TABLE IF NOT EXISTS indexing_history (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    total_documents INTEGER NOT NULL,
    total_vectors INTEGER NOT NULL,
    status TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexing for Rapid Conversation Retrieval
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_docs_hash ON uploaded_documents(file_hash);
```

---

## 5. End-to-End Data Pipeline Flow

```
[Raw PDF Document]
       │
       ▼ (fitz / PyMuPDF Page Parsing)
[Page Dictionaries (text, tables, metadata)]
       │
       ├─────────────────────────────────┐
       ▼ (Semantic Chunker)              ▼ (Component Extractor)
[Text Chunks (500 words)]        [Extracted Entities (517 Records)]
       │                                 │
       ▼ (Ollama Embedding API)          ▼ (Strict Evidence Gate)
[768-dim Normalized Vectors]     [Grounded Component Metadata]
       │                                 │
       ▼ (FAISS IndexFlatIP)             ▼ (JSON Store)
[data/faiss_index/sop.index]     [components_metadata.json]
       │                                 │
       └────────────────┬────────────────┘
                        ▼ (Hybrid Retrieval Engine)
       [User Query -> Dense Cosine Search + Exact Entity Match]
                        │
                        ▼ (Grounded Prompt Assembly)
       [Prompt Sent to Ollama gemma-2b via Local HTTP]
                        │
                        ▼ (Streaming Token Generation)
       [Response Rendered in app.py + Citations Saved in SQLite]
```

