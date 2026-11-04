# ==============================================================================
# Intelligent SOP Document Intelligence & Revision Impact Analysis Agent
# Windows PowerShell Startup & Health Verification Script (run_app.ps1)
# ==============================================================================

Write-Host "==========================================================================" -ForegroundColor Cyan
Write-Host " [HVF / AVNL] SOP Intelligence & Revision Impact Analysis Assistant" -ForegroundColor Yellow
Write-Host " Heavy Vehicles Factory, Avadi | Armoured Vehicles Nigam Limited" -ForegroundColor Gray
Write-Host "==========================================================================" -ForegroundColor Cyan

# 1. Check Python
Write-Host "`n[1/6] Verifying Python Environment..." -ForegroundColor White
if (Get-Command "python" -ErrorAction SilentlyContinue) {
    $pyVer = python --version 2>&1
    Write-Host "  [+] Found Python: $pyVer" -ForegroundColor Green
} else {
    Write-Host "  [!] Python is not installed or not in PATH." -ForegroundColor Red
    exit 1
}

# 2. Check Ollama Daemon
Write-Host "`n[2/6] Verifying Local Ollama Inference Server..." -ForegroundColor White
$ollamaUrl = "http://127.0.0.1:11434/api/tags"
try {
    $resp = Invoke-RestMethod -Uri $ollamaUrl -Method Get -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  [+] Ollama daemon active at http://127.0.0.1:11434" -ForegroundColor Green
    
    # 3. Check Required Models
    Write-Host "`n[3/6] Verifying Registered Ollama Models..." -ForegroundColor White
    $models = $resp.models | ForEach-Object { $_.name }
    
    $hasLlm = $models -contains "gemma-2b:latest" -or $models -contains "gemma-2b"
    $hasEmbed = $models -contains "nomic-embed-text:latest" -or $models -contains "nomic-embed-text"
    
    if ($hasLlm) {
        Write-Host "  [+] Generation Model Registered: gemma-2b:latest" -ForegroundColor Green
    } else {
        Write-Host "  [!] Missing Model: gemma-2b:latest (Required for text generation)" -ForegroundColor Yellow
    }
    
    if ($hasEmbed) {
        Write-Host "  [+] Embedding Model Registered: nomic-embed-text:latest" -ForegroundColor Green
    } else {
        Write-Host "  [!] Missing Model: nomic-embed-text:latest (Required for vector search)" -ForegroundColor Yellow
    }
    
    if (-not ($hasLlm -and $hasEmbed)) {
        Write-Host "  Notice: Register models with 'ollama create' if not yet available." -ForegroundColor Yellow
    }
} catch {
    Write-Host "  [!] Ollama server is offline at http://127.0.0.1:11434" -ForegroundColor Yellow
    Write-Host "      (Application will start in offline standby mode. Run 'ollama serve' in another window for AI generation.)" -ForegroundColor Gray
}

# 4. Check Tesseract OCR
Write-Host "`n[4/6] Verifying Tesseract OCR Engine..." -ForegroundColor White
$tessPath = "C:\TesseractOCR\tesseract.exe"
if (Test-Path $tessPath) {
    Write-Host "  [+] Found Tesseract OCR: $tessPath" -ForegroundColor Green
} elseif (Get-Command "tesseract" -ErrorAction SilentlyContinue) {
    $tessCmd = (Get-Command "tesseract").Source
    Write-Host "  [+] Found Tesseract in PATH: $tessCmd" -ForegroundColor Green
} else {
    Write-Host "  [*] Tesseract OCR not detected. Scanned image-only PDFs will require digital text fallback." -ForegroundColor Yellow
}

# 5. Check FAISS Vector Corpus
Write-Host "`n[5/6] Verifying FAISS Knowledge Base..." -ForegroundColor White
$faissIndex = "data\faiss_index\sop.index"
$faissMeta = "data\faiss_index\chunk_metadata.json"
$faissManifest = "data\faiss_index\index_manifest.json"

if ((Test-Path $faissIndex) -and (Test-Path $faissMeta) -and (Test-Path $faissManifest)) {
    Write-Host "  [+] FAISS Index files detected in data\faiss_index" -ForegroundColor Green
} else {
    Write-Host "  [*] FAISS index files not found. Rebuild can be triggered within the Streamlit UI sidebar." -ForegroundColor Yellow
}

# 6. Check SQLite Database
Write-Host "`n[6/6] Verifying Persistent SQLite Storage..." -ForegroundColor White
$dbPath = "data\sop_assistant.db"
if (Test-Path $dbPath) {
    Write-Host "  [+] SQLite database found: $dbPath" -ForegroundColor Green
} else {
    Write-Host "  [*] SQLite database will be initialized automatically upon application launch." -ForegroundColor Cyan
}

# Launch Application
Write-Host "`n==========================================================================" -ForegroundColor Cyan
Write-Host " Starting Streamlit Application (app.py)..." -ForegroundColor Yellow
Write-Host " Press Ctrl+C in this terminal window to stop the application." -ForegroundColor Gray
Write-Host "==========================================================================" -ForegroundColor Cyan

streamlit run app.py
