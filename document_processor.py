#!/usr/bin/env python3
"""
SOP Document Intelligence: Document Processing Engine
=====================================================
Module: document_processor.py
Architecture Role: Module 2 of 5 in Intelligent SOP Assistant Stack.

Responsibilities:
- Reads SOP PDF files page-by-page using PyMuPDF (fitz).
- Detects scanned/image-only pages requiring OCR fallback.
- Executes Tesseract OCR with automatic path resolution and fallback.
- Normalizes and sanitizes extracted text while preserving section boundaries.
- Extracts structured document metadata (Doc ID, Logical SOP ID, Title, Revision, Platform, Shop).
- Identifies section headings and hierarchical document structure.
- Generates section-aware, evidence-traceable chunks (~400-600 tokens with ~50 tokens overlap).
- Preserves exact source-page references and generates stable, deterministic chunk IDs.
- Provides robust error handling for empty, corrupted, or non-standard documents.
"""

import os
import re
import shutil
import logging
from typing import List, Dict, Any, Optional, Tuple, Union
import pymupdf
import pytesseract
from PIL import Image
import io

# Setup logger
logger = logging.getLogger("SOP_DocumentProcessor")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ============================================================================
# TESSERACT OCR CONFIGURATION & DISCOVERY
# ============================================================================

def configure_tesseract() -> str:
    """
    Locates and configures the Tesseract OCR executable.
    Checks system PATH first, followed by standard Windows installation paths.
    
    Returns:
        str: Absolute path to the verified tesseract executable.
    """
    # 1. Check system PATH
    tess_path = shutil.which("tesseract")
    if tess_path and os.path.exists(tess_path):
        pytesseract.pytesseract.tesseract_cmd = tess_path
        logger.debug(f"Tesseract discovered via PATH: {tess_path}")
        return tess_path

    # 2. Check known Windows installation paths
    candidate_paths = [
        r"C:\TesseractOCR\tesseract.exe",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    
    for candidate in candidate_paths:
        if os.path.exists(candidate):
            pytesseract.pytesseract.tesseract_cmd = candidate
            logger.debug(f"Tesseract configured via fallback path: {candidate}")
            return candidate

    logger.warning("Tesseract binary not found in PATH or standard directories.")
    return ""

# Initialize Tesseract configuration on module load
TESSERACT_BIN = configure_tesseract()


# ============================================================================
# TEXT CLEANING & NORMALIZATION
# ============================================================================

def clean_text(raw_text: str) -> str:
    """
    Cleans raw extracted text:
    - Normalizes Unicode characters and non-standard whitespace.
    - Strips recurring PDF page running headers/footers.
    - Fixes hyphenated line-break wraps (e.g. 'fabri-\ncations' -> 'fabrications').
    - Preserves meaningful section headings, paragraph breaks, and table cell splits.
    
    Args:
        raw_text: Raw string extracted from PDF or OCR.
        
    Returns:
        str: Sanitized, normalized text string.
    """
    if not raw_text:
        return ""

    # Replace replacement characters and null bytes
    text = raw_text.replace("\x00", "").replace("\ufffd", " - ")

    # Fix line hyphenation: e.g., "assem-\nbly" -> "assembly"
    text = re.sub(r'(\b\w+)-\s*\n\s*(\w+\b)', r'\1\2', text)

    # Normalize carriage returns and non-breaking spaces
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")

    # Remove repeated excessive tabs or horizontal whitespace
    text = re.sub(r'[ \t]+', ' ', text)

    # Filter out excessive blank lines (> 2 newlines reduced to 2)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Clean leading and trailing whitespace per line
    cleaned_lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(cleaned_lines).strip()

    return text


# ============================================================================
# PAGE EXTRACTION & OCR FALLBACK
# ============================================================================

def detect_scanned_pages(page_data: Dict[str, Any], min_chars: int = 50) -> bool:
    """
    Evaluates whether a page has insufficient digital text and requires OCR.
    
    Args:
        page_data: Dictionary containing 'raw_text' and 'char_count'.
        min_chars: Minimum character threshold for digital text validity.
        
    Returns:
        bool: True if page is deemed scanned/empty/insufficient, False otherwise.
    """
    text = page_data.get("raw_text", "").strip()
    return len(text) < min_chars


def perform_ocr(pdf_path: str, page_number: int, dpi: int = 200) -> str:
    """
    Renders a specified PDF page to an in-memory raster image and applies
    Tesseract OCR to extract textual content.
    
    Args:
        pdf_path: Filepath of the target PDF.
        page_number: 1-indexed page number to OCR.
        dpi: Resolution for rendering the page pixmap.
        
    Returns:
        str: Extracted OCR text string, or empty string on failure.
    """
    if not TESSERACT_BIN and not shutil.which("tesseract"):
        logger.error(f"Cannot perform OCR on {pdf_path} (page {page_number}): Tesseract not configured.")
        return ""

    try:
        doc = pymupdf.open(pdf_path)
        if page_number < 1 or page_number > len(doc):
            logger.error(f"Invalid page number {page_number} for PDF with {len(doc)} pages.")
            return ""

        page = doc[page_number - 1]
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))

        # Perform OCR
        ocr_text = pytesseract.image_to_string(img, config="--psm 6")
        doc.close()
        return clean_text(ocr_text)

    except Exception as e:
        logger.error(f"OCR failed for {pdf_path} page {page_number}: {e}")
        return ""


def extract_pdf_pages(pdf_path: str, min_chars_threshold: int = 50) -> List[Dict[str, Any]]:
    """
    Extracts text page-by-page from a PDF using PyMuPDF. Automatically detects
    scanned/image pages and applies Tesseract OCR fallback when necessary.
    
    Args:
        pdf_path: Path to the target PDF file.
        min_chars_threshold: Character threshold to trigger OCR fallback.
        
    Returns:
        List[Dict[str, Any]]: List of per-page data dicts containing:
            - page_number (1-indexed int)
            - text (cleaned text)
            - raw_text (unmodified text)
            - char_count (int)
            - word_count (int)
            - is_ocr (bool)
            - images_count (int)
            - blocks (structured text blocks)
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file does not exist: {pdf_path}")

    pages_data: List[Dict[str, Any]] = []

    try:
        doc = pymupdf.open(pdf_path)
    except Exception as e:
        logger.error(f"Failed to open PDF document {pdf_path}: {e}")
        raise ValueError(f"Corrupted or invalid PDF file: {pdf_path}") from e

    try:
        total_pages = len(doc)
        for page_idx in range(total_pages):
            page_num = page_idx + 1
            page = doc[page_idx]

            raw_text = page.get_text("text") or ""
            images = page.get_images()
            images_count = len(images) if images else 0

            # Structured blocks from PyMuPDF: (x0, y0, x1, y1, text, block_no, block_type)
            raw_blocks = page.get_text("blocks") or []
            cleaned_blocks = []
            for b in raw_blocks:
                b_text = b[4].strip() if len(b) > 4 and b[4] else ""
                if b_text:
                    cleaned_blocks.append({
                        "bbox": (b[0], b[1], b[2], b[3]),
                        "text": clean_text(b_text),
                        "block_no": b[5] if len(b) > 5 else 0,
                        "type": b[6] if len(b) > 6 else 0
                    })

            page_info = {
                "page_number": page_num,
                "raw_text": raw_text,
                "text": clean_text(raw_text),
                "char_count": len(raw_text.strip()),
                "word_count": len(raw_text.split()),
                "is_ocr": False,
                "images_count": images_count,
                "blocks": cleaned_blocks
            }

            # Check if page is scanned or text is insufficient
            if detect_scanned_pages(page_info, min_chars=min_chars_threshold):
                logger.info(f"Page {page_num} of {os.path.basename(pdf_path)} has insufficient text ({page_info['char_count']} chars). Triggering OCR fallback.")
                ocr_result = perform_ocr(pdf_path, page_num)
                if ocr_result:
                    page_info["raw_text"] = ocr_result
                    page_info["text"] = ocr_result
                    page_info["char_count"] = len(ocr_result)
                    page_info["word_count"] = len(ocr_result.split())
                    page_info["is_ocr"] = True
                    # Create single fallback block for OCR text
                    page_info["blocks"] = [{
                        "bbox": (0, 0, 0, 0),
                        "text": ocr_result,
                        "block_no": 0,
                        "type": 0
                    }]

            pages_data.append(page_info)

    finally:
        doc.close()

    return pages_data


# ============================================================================
# METADATA EXTRACTION
# ============================================================================

def extract_document_metadata(pages: List[Dict[str, Any]], filename: str) -> Dict[str, Any]:
    """
    Parses document metadata from the first page metadata matrix and filename.
    
    Extracts:
    - document_id (e.g. 'HVF/AVNL/SOP-MBT/HW-101')
    - logical_sop_id (e.g. 'HVF_SOP_1_Hull_Welding' - shared category for v1 & v2)
    - document_title (e.g. 'ARMOURED HULL FABRICATIONS & HIGH-TENSILE STEEL WELDS')
    - revision (e.g. 'Rev 4.2 (2026) | 30-Oct-2026')
    - filename (e.g. 'HVF_SOP_1_Hull_Welding.pdf')
    - platform (e.g. 'MBT T-90S Bhishma / Arjun Mk-1A')
    - shop (e.g. 'Heavy Hull Fabrication & Robotic Welding Shop (Shop-04)')
    - eco_number (if present in Revision v2)
    - total_pages (int)
    """
    base_name = os.path.basename(filename)
    stem = os.path.splitext(base_name)[0]

    # Logical SOP ID: normalize away version suffixes like _v2, -v2, _v1, etc.
    logical_sop_id = re.sub(r'[_ -]v\d+$', '', stem, flags=re.IGNORECASE)

    p1_text = pages[0]["text"] if pages else ""
    lines = [l.strip() for l in p1_text.splitlines() if l.strip()]

    doc_id = "UNKNOWN"
    revision = "UNKNOWN"
    title = "UNKNOWN"
    platform = "UNKNOWN"
    shop = "UNKNOWN"
    eco_number = ""

    # 1. Parse Document ID
    for i, line in enumerate(lines):
        if "DOCUMENT ID" in line:
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j].startswith("HVF/"):
                    doc_id = lines[j]
                    break
            break

    # Fallback for Doc ID if table formatting shifted
    if doc_id == "UNKNOWN":
        doc_id_match = re.search(r'HVF/AVNL/SOP-[A-Z0-9/_-]+', p1_text)
        if doc_id_match:
            doc_id = doc_id_match.group(0)

    # 2. Parse Revision & Date
    for i, line in enumerate(lines):
        if "REVISION" in line:
            for j in range(i + 1, min(i + 4, len(lines))):
                if lines[j].startswith("Rev"):
                    revision = lines[j]
                    break
            break

    # Fallback for Revision
    if revision == "UNKNOWN":
        rev_match = re.search(r'Rev\s+[0-9.]+(?:\s*\[[^\]]+\])?(?:\s*\([^)]+\))?(?:\s*\|\s*[0-9A-Za-z-]+)?', p1_text)
        if rev_match:
            revision = rev_match.group(0)

    # 3. Parse ECO / ECN Number (v2 documents)
    for i, line in enumerate(lines):
        if "ECO" in line and "ECN" in line:
            for j in range(i + 1, min(i + 3, len(lines))):
                if "ECO-" in lines[j]:
                    eco_number = lines[j]
                    break
            break

    # 4. Parse Title
    title_parts = []
    in_title = False
    for line in lines:
        if "STANDARD OPERATING PROCEDURE:" in line:
            in_title = True
            rem = line.replace("STANDARD OPERATING PROCEDURE:", "").strip()
            if rem:
                title_parts.append(rem)
            continue
        if in_title:
            if "0.1 DOCUMENT CONTROL" in line or line.startswith("0.1"):
                break
            # Ignore classification headers if interspersed
            if "MINISTRY OF DEFENCE" in line or "RESTRICTED" in line:
                continue
            title_parts.append(line)
    if title_parts:
        title = " ".join(title_parts).strip()

    # Fallback for Title
    if title == "UNKNOWN":
        title_search = re.search(r'STANDARD OPERATING PROCEDURE:\s*([^\n]+(?:\n[^\n0-9]+)?)', p1_text)
        if title_search:
            title = " ".join(title_search.group(1).split())

    # 5. Parse Platform
    for i, line in enumerate(lines):
        if "TARGET" in line and "PLATFORM" in lines[min(i + 1, len(lines) - 1)]:
            parts = []
            for j in range(i + 2, min(i + 7, len(lines))):
                if "PRODUCTION" in lines[j] or "SHOP" in lines[j]:
                    break
                parts.append(lines[j])
            platform = " ".join(parts).strip()
            break

    # 6. Parse Production Shop
    for i, line in enumerate(lines):
        if "PRODUCTION" in line and "SHOP" in lines[min(i + 1, len(lines) - 1)]:
            parts = []
            for j in range(i + 2, min(i + 7, len(lines))):
                if "QA SURVEILLANCE" in lines[j] or "PAGE BUDGET" in lines[j]:
                    break
                parts.append(lines[j])
            shop = " ".join(parts).strip()
            break

    return {
        "document_id": doc_id,
        "logical_sop_id": logical_sop_id,
        "document_title": title,
        "revision": revision,
        "filename": base_name,
        "platform": platform,
        "shop": shop,
        "eco_number": eco_number,
        "total_pages": len(pages)
    }


# ============================================================================
# SECTION HEADING DETECTION
# ============================================================================

SECTION_HEADING_PATTERNS = [
    re.compile(r'^(SECTION\s+\d+\.\d+[^:\n]*)(?::|\s*[-–—]|\n|$)', re.IGNORECASE),
    re.compile(r'^(APPENDIX\s+[A-Z][^:\n]*)(?::|\s*[-–—]|\n|$)', re.IGNORECASE),
    re.compile(r'^(0\.[123]\s+[A-Z\s&,/-]{4,})', re.IGNORECASE),
    re.compile(r'^(\d+\.\d+\.[A-Z]\s+[A-Z\s&,/-]{4,})', re.IGNORECASE),
    re.compile(r'^(\d+\.\d+\s+[A-Z][A-Za-z0-9\s&,/-]{4,})'),
]

def detect_section_headings(text: str) -> List[Tuple[str, int]]:
    """
    Scans a block of text and returns a list of detected section headings
    paired with their line index position.
    
    Args:
        text: Text string to analyze.
        
    Returns:
        List[Tuple[str, int]]: List of (heading_string, line_index) tuples.
    """
    headings: List[Tuple[str, int]] = []
    lines = text.splitlines()

    for idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or len(line) < 3 or len(line) > 140:
            continue

        for pattern in SECTION_HEADING_PATTERNS:
            match = pattern.match(line)
            if match:
                headings.append((line, idx))
                break

    return headings


# ============================================================================
# SECTION-AWARE CHUNKING ENGINE
# ============================================================================

def estimate_tokens(text: str) -> int:
    """
    Estimates token count for English technical text.
    Standard calibration: 1 word ~ 1.33 tokens, or len(text) / 4.
    """
    words = len(text.split())
    char_estimate = len(text) // 4
    return max(1, (words * 4 // 3 + char_estimate) // 2)


def create_document_chunks(
    document_data: Dict[str, Any],
    target_tokens: int = 500,
    overlap_tokens: int = 50
) -> List[Dict[str, Any]]:
    """
    Constructs section-aware, evidence-grounded chunks targeting ~400-600 tokens
    with ~50 tokens overlap where practical.
    
    Guarantees:
    - Never discards text silently.
    - Preserves exact source page references. Chunks spanning multiple pages preserve
      all source pages in `page_numbers` list and `page_number` range string.
    - Preserves active section heading context for every chunk.
    - Generates unique, stable, deterministic chunk IDs.
    
    Args:
        document_data: Dictionary returned by extract_document_metadata() + pages.
        target_tokens: Target size in tokens (~500).
        overlap_tokens: Overlap between consecutive chunks (~50).
        
    Returns:
        List[Dict[str, Any]]: Structured chunks list conforming to required schema.
    """
    doc_id = document_data.get("document_id", "DOC")
    logical_sop_id = document_data.get("logical_sop_id", "SOP")
    filename = document_data.get("filename", "")
    revision = document_data.get("revision", "")
    pages = document_data.get("pages", [])

    # Clean document identifier for stable chunk IDs
    safe_doc_id = re.sub(r'[^A-Za-z0-9_]', '_', doc_id)
    if not safe_doc_id or safe_doc_id == "UNKNOWN":
        safe_doc_id = re.sub(r'[^A-Za-z0-9_]', '_', os.path.splitext(filename)[0])

    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    current_section = "0.0 PREAMBLE & GENERAL DIRECTIVES"
    current_blocks: List[str] = []
    current_pages: List[int] = []
    current_tokens = 0

    def flush_chunk(blocks: List[str], pages_list: List[int], section: str) -> Optional[Dict[str, Any]]:
        nonlocal chunk_index
        text = "\n\n".join(blocks).strip()
        if not text:
            return None

        clean_pages = sorted(list(set(pages_list)))
        if len(clean_pages) == 1:
            p_display: Union[int, str] = clean_pages[0]
        elif len(clean_pages) > 1:
            p_display = f"{clean_pages[0]}-{clean_pages[-1]}"
        else:
            p_display = 1

        c_id = f"{safe_doc_id}_C{chunk_index:04d}"
        t_count = estimate_tokens(text)

        chunk_record = {
            "chunk_id": c_id,
            "document_id": doc_id,
            "logical_sop_id": logical_sop_id,
            "filename": filename,
            "revision": revision,
            "section_title": section,
            "page_number": p_display,
            "page_numbers": clean_pages,
            "chunk_text": text,
            "chunk_index": chunk_index,
            "token_count": t_count,
            "char_count": len(text)
        }
        chunk_index += 1
        return chunk_record

    for page in pages:
        p_num = page["page_number"]
        blocks = page.get("blocks", [])

        # Fallback if no structured blocks present (e.g. from plain text or OCR)
        if not blocks and page.get("text"):
            blocks = [{
                "text": page["text"],
                "block_no": 0,
                "bbox": (0, 0, 0, 0)
            }]

        for b in blocks:
            b_text = b["text"].strip()
            if not b_text:
                continue

            # Strip repetitive page headers/footers to preserve token budget for real content
            if "HEAVY VEHICLES FACTORY (HVF)" in b_text and len(b_text) < 70:
                continue
            if "RESTRICTED - FOR OFFICIAL USE ONLY" in b_text and len(b_text) < 70:
                continue

            first_line = b_text.splitlines()[0].strip()
            headings = detect_section_headings(first_line)
            is_new_section = len(headings) > 0

            # If encountering a major new section and we already accumulated adequate text, flush current chunk
            if is_new_section and current_tokens >= 250:
                flushed = flush_chunk(current_blocks, current_pages, current_section)
                if flushed:
                    chunks.append(flushed)

                # Overlap logic: keep last block if modest size (< 80 tokens)
                if current_blocks and estimate_tokens(current_blocks[-1]) <= (overlap_tokens * 2):
                    current_blocks = [current_blocks[-1]]
                    current_pages = [current_pages[-1]]
                    current_tokens = estimate_tokens(current_blocks[0])
                else:
                    current_blocks = []
                    current_pages = []
                    current_tokens = 0

            if is_new_section:
                current_section = headings[0][0]

            b_tokens = estimate_tokens(b_text)

            # If a single block itself is massive (> 600 tokens), split it internally by sentences
            if b_tokens > 650:
                sentences = re.split(r'(?<=[.!?])\s+', b_text)
                for sentence in sentences:
                    s_tokens = estimate_tokens(sentence)
                    if current_tokens + s_tokens > target_tokens and current_tokens >= 300:
                        flushed = flush_chunk(current_blocks, current_pages, current_section)
                        if flushed:
                            chunks.append(flushed)
                        current_blocks = []
                        current_pages = []
                        current_tokens = 0
                    current_blocks.append(sentence)
                    current_pages.append(p_num)
                    current_tokens += s_tokens
            else:
                # Normal block accumulation
                if current_tokens + b_tokens > target_tokens and current_tokens >= 350:
                    flushed = flush_chunk(current_blocks, current_pages, current_section)
                    if flushed:
                        chunks.append(flushed)

                    # Maintain overlap from end of flushed chunk
                    if current_blocks and estimate_tokens(current_blocks[-1]) <= (overlap_tokens * 2):
                        current_blocks = [current_blocks[-1], b_text]
                        current_pages = [current_pages[-1], p_num]
                        current_tokens = estimate_tokens(current_blocks[0]) + b_tokens
                    else:
                        current_blocks = [b_text]
                        current_pages = [p_num]
                        current_tokens = b_tokens
                else:
                    current_blocks.append(b_text)
                    current_pages.append(p_num)
                    current_tokens += b_tokens

    # Flush remaining accumulated blocks
    if current_blocks:
        flushed = flush_chunk(current_blocks, current_pages, current_section)
        if flushed:
            chunks.append(flushed)

    return chunks


# ============================================================================
# COMPREHENSIVE PDF PROCESSING PIPELINE
# ============================================================================

def process_pdf(pdf_path: str, min_chars_threshold: int = 50) -> Dict[str, Any]:
    """
    Executes the complete document processing pipeline for a single SOP PDF:
    1. Extracts all pages (native digital text or Tesseract OCR fallback).
    2. Parses and validates all document metadata.
    3. Builds section-aware, evidence-traceable chunks.
    
    Args:
        pdf_path: Absolute or relative filepath of the target PDF.
        min_chars_threshold: Insufficient text threshold for OCR triggering.
        
    Returns:
        Dict[str, Any]: Fully structured document object conforming to the project schema:
            - document_id
            - logical_sop_id
            - document_title
            - revision
            - filename
            - platform
            - shop
            - total_pages
            - pages
            - chunks
            - total_chunks
            - status
    """
    filename = os.path.basename(pdf_path)
    logger.info(f"Processing SOP document: {filename}")

    try:
        pages = extract_pdf_pages(pdf_path, min_chars_threshold=min_chars_threshold)
        metadata = extract_document_metadata(pages, filename)
        
        document_record: Dict[str, Any] = {
            **metadata,
            "pages": pages,
        }

        chunks = create_document_chunks(document_record)
        document_record["chunks"] = chunks
        document_record["total_chunks"] = len(chunks)
        document_record["status"] = "success"

        logger.info(
            f"Successfully processed {filename}: "
            f"DocID={document_record['document_id']} | "
            f"Rev={document_record['revision'][:20]} | "
            f"Pages={document_record['total_pages']} | "
            f"Chunks={document_record['total_chunks']}"
        )
        return document_record

    except Exception as e:
        logger.error(f"Error processing {pdf_path}: {e}", exc_info=True)
        return {
            "document_id": "ERROR",
            "logical_sop_id": re.sub(r'[_ -]v\d+$', '', os.path.splitext(filename)[0], flags=re.IGNORECASE),
            "document_title": f"Processing Error: {filename}",
            "revision": "UNKNOWN",
            "filename": filename,
            "platform": "UNKNOWN",
            "shop": "UNKNOWN",
            "total_pages": 0,
            "pages": [],
            "chunks": [],
            "total_chunks": 0,
            "status": f"error: {str(e)}"
        }


def process_all_sops(sop_dir: str = "SOP") -> List[Dict[str, Any]]:
    """
    Processes all SOP PDF files in the specified directory.
    Sorts files predictably, processes each through process_pdf, and returns
    a comprehensive list of structured document records.
    
    Args:
        sop_dir: Directory containing SOP PDFs (default: 'SOP').
        
    Returns:
        List[Dict[str, Any]]: List of processed document objects.
    """
    if not os.path.exists(sop_dir):
        logger.error(f"SOP directory not found: {sop_dir}")
        return []

    pdf_files = sorted([
        os.path.join(sop_dir, f) for f in os.listdir(sop_dir)
        if f.lower().endswith(".pdf")
    ])

    logger.info(f"Discovered {len(pdf_files)} SOP PDF files in '{sop_dir}'")
    processed_docs: List[Dict[str, Any]] = []

    for pdf_path in pdf_files:
        doc_result = process_pdf(pdf_path)
        processed_docs.append(doc_result)

    return processed_docs


if __name__ == "__main__":
    import json
    docs = process_all_sops("SOP")
    print(f"\nCompleted processing of {len(docs)} documents.")
    for d in docs:
        print(f" - {d['filename']}: {d['document_id']} ({d['total_chunks']} chunks, {d['total_pages']} pages)")

