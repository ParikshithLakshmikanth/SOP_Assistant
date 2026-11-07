# Heavy Vehicles Factory (HVF) / Armoured Vehicles Nigam Limited (AVNL)
## Intelligent SOP Document Intelligence & Revision Impact Analysis Assistant
### Live Demonstration & Technical Review Guide (10–15 Minute Sequence)

This guide provides a structured, 12-step presentation script for conducting live technical demonstrations before defense evaluators, manufacturing engineers, and academic review committees.

---

## Demonstration Overview

| Stage | Duration | Core Capabilities Highlighted |
| :--- | :---: | :--- |
| **Part 1: Security & Dashboard Telemetry** | 3 mins | Air-gap verification, live Ollama loopback, FAISS corpus telemetry (150 vectors, 517 components). |
| **Part 2: Technical Chatbot & Grounded RAG** | 4 mins | Natural language querying, live token streaming, traceable citations, zero-hallucination guardrails. |
| **Part 3: Visual Component Explorer** | 3 mins | Multi-level filtering, verified structural relationships, seamless component-to-chat navigation. |
| **Part 4: Revision Comparison & Impact Analysis** | 3 mins | Numerical tolerance shifts (V1 vs V2), tooling evolution, cross-subsystem interface tracking. |
| **Part 5: Transactional Ingestion & Wrap-up** | 2 mins | Deduplication, 7-stage upload lifecycle, baseline corpus invariant preservation. |

---

## Step-by-Step Demonstration Sequence

### Step 1: System Startup & Air-Gap Compliance Check
- **Presenter Action**: Open a PowerShell window and demonstrate the running processes. Show that Ollama is bound exclusively to `127.0.0.1:11434` and Streamlit is on `http://localhost:8501`.
- **Talking Points**: *"The HVF SOP Assistant operates entirely within an air-gapped security perimeter. All generation and embeddings run locally on CPU using quantized open-weights models (`gemma-2b` and `nomic-embed-text`). No proprietary defense technical specifications or manufacturing tolerances ever touch an external network or cloud endpoint."*
- **Visual**: Show the browser opening `http://localhost:8501`.

---

### Step 2: Executive Telemetry Dashboard
- **Presenter Action**: Click **"📊 Executive Dashboard & Telemetry"**.
- **Talking Points**: *"The Executive Dashboard presents live operational telemetry. Notice the four real-time health badges: Ollama Online, SQLite OK, OCR Ready, and FAISS Synced. The system immediately reports its indexed baseline: exactly 10 authoritative HVF SOP documents, 150 semantic vector chunks, and 517 structured component metadata records."*
- **Visual Callouts**: Highlight the 10 documents listed in the corpus table covering Hull Welding, Turret Integration, Engine Powerpack, Track & Suspension, and Gun Calibration.

---

### Step 3: Direct Engineering Consultation (RAG Chatbot)
- **Presenter Action**: Click **"💬 Technical Consultation Chat"** or click **"🚀 Launch Technical Chatbot"** from the dashboard.
- **Input Prompt**:
  ```
  What are the main components of the turret mount system?
  ```
- **Talking Points**: *"Notice the token-by-token streaming with the blinking defense-blue cursor. Rather than providing generic tank information, the model extracts components exclusively from the authoritative HVF Turret Integration SOP."*
- **Expected Response**: The assistant identifies the **Turret Base Ring**, **Hull Interface Ring**, **Azimuth Bearing Assembly**, **Traverse Drive Gearbox**, and **Grade 10.9 Fasteners**.

---

### Step 4: Traceable Evidence Citation Audit
- **Presenter Action**: Expand the **"Evidence Sources & Citations"** card below the generated response.
- **Talking Points**: *"Defense engineering requires strict traceability. Every claim is mapped to an authoritative source. Here we see `HVF_SOP_2_Turret_Integration.pdf`, Section 3.1, pages 1-2, with a cosine similarity score of ~0.88. Evaluators can click the source card to view the exact text passage extracted from the PDF."*

---

### Step 5: Seamless Navigation to Component Explorer
- **Presenter Action**: Scroll to the bottom of the response where related component chips are rendered. Click on the pill: **`🔍 Turret Base Ring`**.
- **Talking Points**: *"Notice the unified workflow: clicking a component pill immediately transitions us into the Component Explorer, with 'Turret Base Ring' pre-selected in the detail inspector—no manual retyping required."*

---

### Step 6: Component Detail Inspector & Verified Structural Graph
- **Presenter Action**: Review the details panel for **Turret Base Ring**.
- **Talking Points**: *"The Component Explorer displays 517 extracted entities across physical components, assemblies, and subsystems. For the Turret Base Ring, we see its material (`Forged Ni-Cr-Mo Alloy Steel`), fasteners (`48x Grade 10.9 M24`), and runout tolerance (`0.05 mm`). Crucially, notice the structural relationship box: it explicitly connects to the Hull Interface Ring and Azimuth Pinion. Our system adheres to a strict grounding rule: relationships are only asserted when explicitly documented in the SOP text—co-occurring parts are never assumed to be connected."*

---

### Step 7: Component-to-Chat AI Exploration
- **Presenter Action**: In the component inspector, click the primary button: **"💬 Ask AI about this component"**.
- **Talking Points**: *"The system automatically creates a targeted inquiry in the chatbot context. The RAG engine combines dense FAISS vector chunks with the structured component record to produce a beginner-friendly explanation of the part, its assembly hierarchy, and its maintenance precautions."*

---

### Step 8: Technical Deep-Dive on Specialized Upgrades
- **Presenter Action**: In the chatbot input bar, enter:
  ```
  What is the function of a ceramic-hybrid bearing?
  ```
- **Talking Points**: *"Let's test an advanced revision upgrade inquiry. In the V2 standard, HVF introduced ceramic-hybrid bearings for the turret azimuth ring."*
- **Expected Response**: The chatbot explains that silicon nitride ($Si_3N_4$) ceramic-hybrid bearings provide reduced rotational friction, higher radial stiffness, zero galvanic corrosion against alloy races, and significantly reduced thermal expansion under sustained firing loads. Exact citation: `HVF_SOP_2_Turret_Integration_v2.pdf`, Section 3.2.

---

### Step 9: Structural SOP Revision Comparison Engine
- **Presenter Action**: Switch navigation to **"⚖️ SOP Revision Comparison Engine"**. Select the **Turret Integration** domain.
- **Talking Points**: *"Manufacturing engineers frequently audit revision shifts. This module performs section-by-section diffing and regex numerical extraction. Evaluators can see:
  1. Runout tolerance was tightened from ±0.05 mm (V1) down to ±0.02 mm (V2).
  2. Bolt torque increased from 650 Nm to 720 Nm.
  3. Lubrication upgraded from Molykote G-Rapid Plus to Krytox 205 aerospace grease."*
- **Visual**: Show the before/after comparison tables and color-coded unified diff.

---

### Step 10: Cross-Document Interface Impact Analysis
- **Presenter Action**: Switch navigation to **"🔗 Cross-Document Impact Analysis"**. Select **Turret Integration (`HVF-TR`)**.
- **Talking Points**: *"A modification in one SOP frequently causes downstream assembly failures if interface couplings are overlooked. The Impact Analysis engine maps structural boundaries: tightening the Turret ring flatness impacts the Hull Welding SOP (`HVF-HW`) at the turret well roof plate, and impacts the Gun Calibration SOP (`HVF-GC`) at the trunnion alignment interface."*

---

### Step 11: Transactional Document Ingestion
- **Presenter Action**: Navigate to **"📥 Ingest & Manage SOP Documents"**. Drag and drop a test SOP PDF (or demonstrate the duplicate rejection).
- **Talking Points**: *"The upload engine executes a transactional 7-stage pipeline: SHA-256 deduplication, PyMuPDF text parsing with Tesseract OCR fallback, 500-word hierarchical chunking, local Ollama embedding, and atomic index updating. Duplicate uploads are rejected instantly to prevent vector index skew."*

---

### Step 12: Invariant Preservation & Wrap-Up
- **Presenter Action**: Navigate back to the Executive Dashboard.
- **Talking Points**: *"To conclude: throughout all operations, the system strictly preserves its baseline integrity—150 vectors and 517 component metadata records across 10 baseline documents. It runs 100% offline, achieves 108/108 passing automated regression tests, and delivers transparent, citation-grounded intelligence for frontline defense manufacturing."*

