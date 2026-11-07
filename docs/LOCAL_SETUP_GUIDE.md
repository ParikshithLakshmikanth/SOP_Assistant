# Heavy Vehicles Factory (HVF) / Armoured Vehicles Nigam Limited (AVNL)
## Intelligent SOP Document Intelligence & Revision Impact Analysis Assistant
### Local Setup & Installation Guide for Windows

This guide provides step-by-step instructions to configure, install, and run the HVF SOP Assistant on a local, air-gapped Windows 10/11 engineering workstation.

---

## 1. Hardware & System Requirements

### Recommended Workstation Specs
- **OS**: Windows 10 / Windows 11 (64-bit)
- **CPU**: Modern x86_64 Multi-core processor (Intel Core i5/i7/i9 8th Gen+ or AMD Ryzen 5/7/9)
- **RAM**: 16 GB minimum (32 GB recommended for large concurrent vector searches)
- **Disk**: 10 GB free NVMe/SSD space (for Ollama model weights, FAISS indices, and PDF cache)
- **GPU**: Optional (all inference runs efficiently on CPU using quantized GGUF weights)

---

## 2. Prerequisites Installation

### A. Python 3.11+
1. Download Python 3.11.x from [python.org](https://www.python.org/downloads/).
2. During installation, ensure you check **"Add Python to PATH"**.
3. Verify in PowerShell:
   ```powershell
   python --version
   pip --version
   ```

### B. Ollama for Windows
1. Download the Windows installer from [ollama.com/download/windows](https://ollama.com/download/windows).
2. Run the installer and launch Ollama.
3. Start the Ollama background daemon:
   ```powershell
   ollama serve
   ```
4. In a separate PowerShell terminal, pull the two required local quantized models:
   ```powershell
   # 1. Text Generation Instruction Model (2 Billion Parameters)
   ollama pull gemma-2b:latest

   # 2. Dense Semantic Vector Embedding Model (768 Dimensions)
   ollama pull nomic-embed-text:latest
   ```
5. Verify both models are present:
   ```powershell
   ollama list
   ```
   *Expected Output includes `gemma-2b:latest` and `nomic-embed-text:latest`.*

### C. Tesseract OCR (For Scanned PDF Support)
1. Download the Windows installer from the UB-Mannheim repository:
   `https://github.com/UB-Mannheim/tesseract/wiki`
2. Install to the default directory or workstation location:
   - Primary workstation path: `C:\TesseractOCR\tesseract.EXE`
   - Standard default path: `C:\Program Files\Tesseract-OCR\tesseract.exe`
3. The application automatically probes these standard locations in `document_processor.configure_tesseract()`. If installed to a custom location, add that folder to your Windows system `PATH` or set `$env:TESSERACT_PATH`.

---

## 3. Project Installation & Environment Setup

### Step 1: Navigate to Project Directory
```powershell
cd D:\Parikshith\SOP_Assistant
```

### Step 2: Create and Activate Virtual Environment
```powershell
# Create virtual environment
python -m venv .venv

# Activate virtual environment
.\.venv\Scripts\Activate.ps1
```
*(If PowerShell restricts script execution, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`)*

### Step 3: Install Python Dependencies
```powershell
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 4. Verification & Baseline Index Inspection

Verify that the local corpus indices, component database, and SQLite database are in a healthy state:

```powershell
# Run the automated regression test suite (108 tests)
python tests/run_all_regression_tests.py
```
*Expected output: `108 / 108 tests PASS (100% OK)`.*

Verify baseline invariants directly:
```powershell
python -c "import rag_engine as re; health = re.get_comprehensive_system_health(); print(health)"
```
*Expected Output: `overall_status: 'HEALTHY'`, `faiss: {'total_vectors': 150}`, `components: {'total_records': 517}`.*

---

## 5. Starting the Streamlit Application

Launch the local interactive application:

```powershell
streamlit run app.py
```

The browser will open automatically at:
```
Local URL: http://localhost:8501
```

---

## 6. Troubleshooting Common Issues

### Issue 1: `ConnectionRefusedError: [WinError 10061] No connection could be made because the target machine actively refused it`
- **Cause**: The Ollama daemon is not running on `127.0.0.1:11434`.
- **Solution**: Open a PowerShell window and run:
  ```powershell
  ollama serve
  ```

### Issue 2: `Model 'gemma-2b:latest' not found`
- **Cause**: The model was not downloaded prior to launching the app.
- **Solution**: Run:
  ```powershell
  ollama pull gemma-2b:latest
  ollama pull nomic-embed-text:latest
  ```

### Issue 3: `TesseractNotFound: tesseract is not installed or it's not in your PATH`
- **Cause**: Tesseract OCR was installed to a non-standard directory.
- **Solution**: Verify `C:\Program Files\Tesseract-OCR\tesseract.exe` exists, or set the environment variable:
  ```powershell
  $env:TESSERACT_PATH="C:\CustomPath\tesseract.exe"
  ```

### Issue 4: `Port 8501 is already in use`
- **Cause**: A previous Streamlit instance is still running in the background.
- **Solution**: Identify and kill the process:
  ```powershell
  Get-NetTCPConnection -LocalPort 8501 | Select-Object OwningProcess
  Stop-Process -Id <PID> -Force
  ```
  Or run Streamlit on an alternative port:
  ```powershell
  streamlit run app.py --server.port 8502
  ```

### Issue 5: `FAISS Index dimension mismatch (expected 768)`
- **Cause**: An incorrect embedding model was used to query the index.
- **Solution**: Ensure `nomic-embed-text:latest` is set in `rag_engine.py` (which produces 768-dimensional embeddings).

