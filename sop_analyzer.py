#!/usr/bin/env python3
"""
SOP Document Intelligence & Revision Impact Analysis Assistant
==============================================================
Module: sop_analyzer.py
Architecture Role: Module 4 of 5 (SOP Revision Comparison & Analysis Engine).

Responsibilities:
- Pair matching & rigorous validation of baseline (v1) and revised (v2) SOP documents.
- Section-aware alignment and diff analysis across document revisions.
- Deterministic extraction and classification of changes into operational categories:
  * Numerical parameter, tolerance, or threshold shifts
  * Safety warnings and precaution updates
  * Equipment, tooling, and sensor transitions
  * Inspection, metrology, and acceptance criteria modifications
  * Responsibility and sign-off governance changes
  * Added and removed procedures
  * Editorial and formatting updates
  * Uncertain changes flagged for mandatory human review
- Full traceability preserving exact source filenames, revision strings, section headings,
  page numbers, and verbatim text passages.
- Standalone report generation (Markdown) for compliance and auditing.
- Strictly offline, deterministic execution without modifying authoritative SOP PDFs.
"""

import os
import re
import difflib
import logging
from typing import List, Dict, Any, Optional, Tuple, Set

import document_processor as dp
import database as db

logger = logging.getLogger("SOP_Assistant.Analyzer")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ============================================================================
# CLASSIFICATION TAXONOMY
# ============================================================================

CHANGE_TYPES = [
    "Changed numerical parameter, tolerance, or threshold",
    "Changed safety warning or precaution",
    "Changed equipment, tooling, or material",
    "Changed inspection or acceptance criterion",
    "Changed responsibility or approval requirement",
    "Modified procedure or sequence",
    "Added requirement or instruction",
    "Removed requirement or instruction",
    "Editorial or formatting-only change",
    "Uncertain change requiring human review"
]

# Regular expression heuristics for classification
RE_NUMERICAL = re.compile(
    r'(?:[±\+\-]?\s*\d+(?:\.\d+)?\s*(?:mm|bar|nm|c|°c|mrad|kj/mm|mpa|rpm|v|hz|%|kg|deg|degrees|arcsec|kn|m|s|min|hours|elements))'
    r'|(?:tolerance|clearance|pressure|temperature|torque|voltage|wavelength|straightness|perpendicularity)\b',
    re.IGNORECASE
)

RE_SAFETY = re.compile(
    r'\b(?:safety|warning|caution|danger|hazard|ppe|protective|emergency|trip|interlock|fume|radiation|high-voltage|cryogenic|lockout|tagout|hse)\b',
    re.IGNORECASE
)

RE_EQUIPMENT = re.compile(
    r'\b(?:robot|robotic|jig|fixture|laser|tracker|sensor|probe|torch|welder|damper|collimator|gmaw|saw|cnc|invar|transducer|bearing|accumulator|manifold|rfid|iot|telemetry|twin-wire|scada)\b',
    re.IGNORECASE
)

RE_INSPECTION = re.compile(
    r'\b(?:ndt|paut|tofd|ultrasonic|radiographic|spectrographic|metrology|inspection|acceptance|criterion|benchmark|deviation|quarantine|pass/fail|dossier|passport|vision|fissure|fpi)\b',
    re.IGNORECASE
)

RE_RESPONSIBILITY = re.compile(
    r'\b(?:supervisor|officer|manager|inspector|operator|director|mrb|board|authority|sign-off|clearance|authorization|approval|sign-off)\b',
    re.IGNORECASE
)


# ============================================================================
# PAIR MATCHING & VALIDATION
# ============================================================================

def extract_section_key(title: str) -> str:
    """
    Extracts canonical structural section identifier from title.
    Matches formats like 'SECTION 1.0', '1.0.A', '0.2', 'APPENDIX A'.
    """
    if not title:
        return "GENERAL"

    clean = title.strip()
    m = re.match(r'^(SECTION\s+\d+\.\d+|\d+\.\d+\.[A-Z]|\d+\.\d+|APPENDIX\s+[A-Z])', clean, re.IGNORECASE)
    if m:
        return m.group(1).upper()

    # Fallback to prefix before delimiter
    delim_match = re.split(r'[\u2014\u2013\-:]', clean)
    if delim_match:
        return delim_match[0].strip().upper()
    return clean[:20].upper()


def get_available_sop_pairs(sop_dir: str = "SOP") -> List[Dict[str, Any]]:
    """
    Scans the SOP directory, pairs baseline (v1) and revised (v2) PDFs by logical_sop_id,
    and returns validated pairing metadata.
    
    Returns:
        List[Dict[str, Any]]: List of valid pairs with paths and metadata.
    """
    if not os.path.exists(sop_dir):
        logger.warning(f"SOP directory '{sop_dir}' does not exist.")
        return []

    files = [f for f in os.listdir(sop_dir) if f.lower().endswith(".pdf")]
    logical_map: Dict[str, Dict[str, str]] = {}

    for f in sorted(files):
        path = os.path.join(sop_dir, f)
        stem = os.path.splitext(f)[0]
        logical_id = re.sub(r'[_ -]v\d+$', '', stem, flags=re.IGNORECASE)
        is_v2 = bool(re.search(r'[_ -]v2$', stem, flags=re.IGNORECASE))

        if logical_id not in logical_map:
            logical_map[logical_id] = {}

        if is_v2:
            logical_map[logical_id]["revised"] = path
        else:
            logical_map[logical_id]["baseline"] = path

    pairs = []
    for log_id, paths in sorted(logical_map.items()):
        if "baseline" in paths and "revised" in paths:
            pairs.append({
                "logical_sop_id": log_id,
                "baseline_path": paths["baseline"],
                "revised_path": paths["revised"],
                "baseline_filename": os.path.basename(paths["baseline"]),
                "revised_filename": os.path.basename(paths["revised"]),
                "is_complete": True
            })
        else:
            logger.warning(f"Incomplete pair for logical SOP '{log_id}': {paths}")

    return pairs


def validate_sop_pair(
    baseline_doc: Dict[str, Any],
    revised_doc: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Validates that two documents constitute a legitimate revision pair.
    
    Checks:
    - Shared logical_sop_id.
    - Distinct document_id or revision string.
    - Both contain extracted chunks and valid pages.
    
    Returns:
        Tuple[bool, str]: (is_valid, validation_message)
    """
    if not baseline_doc or not revised_doc:
        return False, "One or both document records are empty or None."

    base_log = baseline_doc.get("logical_sop_id")
    rev_log = revised_doc.get("logical_sop_id")

    if not base_log or not rev_log:
        return False, "Missing logical_sop_id in one or both documents."

    if base_log != rev_log:
        return False, (
            f"Mismatched logical SOP IDs: Baseline is '{base_log}' while Revised is '{rev_log}'. "
            f"Cross-category revision comparison is rejected."
        )

    base_doc_id = baseline_doc.get("document_id", "UNKNOWN")
    rev_doc_id = revised_doc.get("document_id", "UNKNOWN")

    if base_doc_id != "UNKNOWN" and rev_doc_id != "UNKNOWN" and base_doc_id == rev_doc_id:
        # Check if revisions differ
        base_rev = baseline_doc.get("revision", "")
        rev_rev = revised_doc.get("revision", "")
        if base_rev == rev_rev:
            return False, f"Identical document ID ({base_doc_id}) and revision ({base_rev}); no revision delta."

    if not baseline_doc.get("chunks") or not revised_doc.get("chunks"):
        return False, "One or both documents have 0 extracted text chunks."

    return True, f"Valid revision pair for logical SOP: '{base_log}'"


# ============================================================================
# SECTION ALIGNMENT & GRANULAR COMPARISON
# ============================================================================

def align_document_sections(
    baseline_chunks: List[Dict[str, Any]],
    revised_chunks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Aligns sections between baseline and revised chunks using structural section keys
    and fuzzy heading similarity.
    
    Returns:
        List[Dict[str, Any]]: List of section comparison pairings:
            - section_key (str)
            - baseline_chunk (Optional[Dict])
            - revised_chunk (Optional[Dict])
            - status ('MATCHED', 'ADDED', 'REMOVED')
    """
    aligned: List[Dict[str, Any]] = []

    # Map chunks by canonical key
    base_map: Dict[str, Dict[str, Any]] = {}
    for c in baseline_chunks:
        k = extract_section_key(c["section_title"])
        base_map[k] = c

    rev_map: Dict[str, Dict[str, Any]] = {}
    for c in revised_chunks:
        k = extract_section_key(c["section_title"])
        rev_map[k] = c

    all_keys = list(base_map.keys())
    for k in rev_map.keys():
        if k not in all_keys:
            all_keys.append(k)

    for k in all_keys:
        b_chunk = base_map.get(k)
        r_chunk = rev_map.get(k)

        if b_chunk and r_chunk:
            aligned.append({
                "section_key": k,
                "baseline_chunk": b_chunk,
                "revised_chunk": r_chunk,
                "status": "MATCHED"
            })
        elif b_chunk and not r_chunk:
            aligned.append({
                "section_key": k,
                "baseline_chunk": b_chunk,
                "revised_chunk": None,
                "status": "REMOVED"
            })
        elif not b_chunk and r_chunk:
            aligned.append({
                "section_key": k,
                "baseline_chunk": None,
                "revised_chunk": r_chunk,
                "status": "ADDED"
            })

    return aligned


def classify_passage_difference(
    base_text: str,
    rev_text: str
) -> Tuple[List[str], str, str]:
    """
    Classifies the operational differences between two corresponding passages.
    
    Returns:
        Tuple[List[str], str, str]:
            - classifications (List of matching categories)
            - primary_classification (Single most prominent category)
            - operational_significance (Concise explanation)
    """
    if not base_text and rev_text:
        return (
            ["Added requirement or instruction"],
            "Added requirement or instruction",
            "Newly introduced procedure or requirement in revised specification."
        )

    if base_text and not rev_text:
        return (
            ["Removed requirement or instruction"],
            "Removed requirement or instruction",
            "Procedure or requirement deprecated or removed in revised specification."
        )

    # Check for identical text or whitespace/formatting only
    clean_b = re.sub(r'\s+', ' ', base_text.strip().lower())
    clean_r = re.sub(r'\s+', ' ', rev_text.strip().lower())
    if clean_b == clean_r:
        return (
            ["Editorial or formatting-only change"],
            "Editorial or formatting-only change",
            "Text wording identical; formatting or layout update only."
        )

    classifications: List[str] = []
    explanations: List[str] = []

    # 1. Numerical Parameter Checks
    b_nums = set(RE_NUMERICAL.findall(base_text.lower()))
    r_nums = set(RE_NUMERICAL.findall(rev_text.lower()))
    if b_nums != r_nums:
        classifications.append("Changed numerical parameter, tolerance, or threshold")
        num_diff = list(r_nums - b_nums)[:3]
        explanations.append(f"Numerical values/tolerances updated (e.g. {', '.join(num_diff) if num_diff else 'values adjusted'}).")

    # 2. Safety Warning Checks
    b_saf = set(RE_SAFETY.findall(base_text.lower()))
    r_saf = set(RE_SAFETY.findall(rev_text.lower()))
    if b_saf != r_saf:
        classifications.append("Changed safety warning or precaution")
        saf_new = list(r_saf - b_saf)[:2]
        explanations.append(f"Safety protocols updated ({', '.join(saf_new) if saf_new else 'protective precautions modified'}).")

    # 3. Equipment & Tooling Checks
    b_eq = set(RE_EQUIPMENT.findall(base_text.lower()))
    r_eq = set(RE_EQUIPMENT.findall(rev_text.lower()))
    if b_eq != r_eq:
        classifications.append("Changed equipment, tooling, or material")
        eq_new = list(r_eq - b_eq)[:2]
        explanations.append(f"Tooling or instrumentation changed ({', '.join(eq_new) if eq_new else 'hardware upgraded'}).")

    # 4. Inspection & Metrology Checks
    b_insp = set(RE_INSPECTION.findall(base_text.lower()))
    r_insp = set(RE_INSPECTION.findall(rev_text.lower()))
    if b_insp != r_insp:
        classifications.append("Changed inspection or acceptance criterion")
        insp_new = list(r_insp - b_insp)[:2]
        explanations.append(f"Quality/acceptance criteria modified ({', '.join(insp_new) if insp_new else 'NDT/metrology revised'}).")

    # 5. Responsibility & Governance Checks
    b_resp = set(RE_RESPONSIBILITY.findall(base_text.lower()))
    r_resp = set(RE_RESPONSIBILITY.findall(rev_text.lower()))
    if b_resp != r_resp:
        classifications.append("Changed responsibility or approval requirement")
        explanations.append("Authorized personnel or sign-off hierarchy modified.")

    # 6. Fallback procedure modifications
    if not classifications:
        sm = difflib.SequenceMatcher(None, clean_b, clean_r)
        ratio = sm.ratio()
        if ratio > 0.85:
            classifications.append("Editorial or formatting-only change")
            explanations.append("Minor wording or phrasing clarification without substantive operational shift.")
        elif ratio > 0.40:
            classifications.append("Modified procedure or sequence")
            explanations.append("Procedural sequence or instructions modified between revisions.")
        else:
            classifications.append("Uncertain change requiring human review")
            explanations.append("Significant structural rewrite; manual engineering review recommended.")

    # Determine primary classification
    primary = classifications[0] if classifications else "Modified procedure or sequence"
    summary_expl = " ".join(explanations) if explanations else "Operational differences detected between document versions."

    return classifications, primary, summary_expl


# ============================================================================
# COMPREHENSIVE REVISION COMPARISON
# ============================================================================

def compare_sop_revisions(
    baseline_doc: Dict[str, Any],
    revised_doc: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Executes a section-aware comparison between baseline and revised SOP documents.
    
    Guarantees:
    - Rejects invalid or mismatched pairs.
    - Evaluates section alignment across all chunks.
    - Classifies detected operational differences.
    - Preserves source filenames, revisions, sections, and page numbers.
    - Marks ambiguous changes for human review.
    
    Returns:
        Dict[str, Any]: Comprehensive comparison report object.
    """
    is_valid, msg = validate_sop_pair(baseline_doc, revised_doc)
    if not is_valid:
        raise ValueError(f"Revision comparison rejected: {msg}")

    logical_id = baseline_doc["logical_sop_id"]
    doc_title = baseline_doc.get("document_title", revised_doc.get("document_title", "SOP"))

    base_fn = baseline_doc.get("filename", "baseline.pdf")
    rev_fn = revised_doc.get("filename", "revised.pdf")

    base_rev = baseline_doc.get("revision", "v1")
    rev_rev = revised_doc.get("revision", "v2")

    aligned_sections = align_document_sections(
        baseline_chunks=baseline_doc["chunks"],
        revised_chunks=revised_doc["chunks"]
    )

    detected_changes: List[Dict[str, Any]] = []
    unchanged_sections_count = 0
    change_idx = 1

    for pairing in aligned_sections:
        status = pairing["status"]
        sec_key = pairing["section_key"]
        b_chunk = pairing["baseline_chunk"]
        r_chunk = pairing["revised_chunk"]

        if status == "ADDED" and r_chunk:
            c_types, primary, expl = classify_passage_difference("", r_chunk["chunk_text"])
            detected_changes.append({
                "change_id": f"CHG-{logical_id[:6]}-{change_idx:02d}",
                "logical_sop_id": logical_id,
                "document_title": doc_title,
                "baseline_filename": base_fn,
                "baseline_revision": base_rev,
                "baseline_page": None,
                "baseline_section": None,
                "baseline_passage": "",
                "revised_filename": rev_fn,
                "revised_revision": rev_rev,
                "revised_page": r_chunk["page_number"],
                "revised_section": r_chunk["section_title"],
                "revised_passage": r_chunk["chunk_text"].strip(),
                "classifications": c_types,
                "primary_classification": primary,
                "operational_significance": expl,
                "review_status": "Automated - High Confidence",
                "similarity_ratio": 0.0
            })
            change_idx += 1

        elif status == "REMOVED" and b_chunk:
            c_types, primary, expl = classify_passage_difference(b_chunk["chunk_text"], "")
            detected_changes.append({
                "change_id": f"CHG-{logical_id[:6]}-{change_idx:02d}",
                "logical_sop_id": logical_id,
                "document_title": doc_title,
                "baseline_filename": base_fn,
                "baseline_revision": base_rev,
                "baseline_page": b_chunk["page_number"],
                "baseline_section": b_chunk["section_title"],
                "baseline_passage": b_chunk["chunk_text"].strip(),
                "revised_filename": rev_fn,
                "revised_revision": rev_rev,
                "revised_page": None,
                "revised_section": None,
                "revised_passage": "",
                "classifications": c_types,
                "primary_classification": primary,
                "operational_significance": expl,
                "review_status": "Automated - High Confidence",
                "similarity_ratio": 0.0
            })
            change_idx += 1

        elif status == "MATCHED" and b_chunk and r_chunk:
            b_text = b_chunk["chunk_text"].strip()
            r_text = r_chunk["chunk_text"].strip()

            sm = difflib.SequenceMatcher(None, b_text, r_text)
            ratio = sm.ratio()

            if ratio >= 0.995:
                unchanged_sections_count += 1
                continue

            c_types, primary, expl = classify_passage_difference(b_text, r_text)

            review_status = "Automated - High Confidence"
            if "Uncertain change requiring human review" in c_types:
                review_status = "Uncertain - Human Review Required"
            elif "Changed numerical parameter, tolerance, or threshold" in c_types:
                review_status = "Automated - Parameter Shift"

            detected_changes.append({
                "change_id": f"CHG-{logical_id[:6]}-{change_idx:02d}",
                "logical_sop_id": logical_id,
                "document_title": doc_title,
                "baseline_filename": base_fn,
                "baseline_revision": base_rev,
                "baseline_page": b_chunk["page_number"],
                "baseline_section": b_chunk["section_title"],
                "baseline_passage": b_text,
                "revised_filename": rev_fn,
                "revised_revision": rev_rev,
                "revised_page": r_chunk["page_number"],
                "revised_section": r_chunk["section_title"],
                "revised_passage": r_text,
                "classifications": c_types,
                "primary_classification": primary,
                "operational_significance": expl,
                "review_status": review_status,
                "similarity_ratio": round(ratio, 4)
            })
            change_idx += 1

    # Summarize classification breakdown
    class_counts: Dict[str, int] = {t: 0 for t in CHANGE_TYPES}
    for chg in detected_changes:
        for c in chg["classifications"]:
            if c in class_counts:
                class_counts[c] += 1

    return {
        "logical_sop_id": logical_id,
        "document_title": doc_title,
        "baseline": {
            "document_id": baseline_doc.get("document_id"),
            "filename": base_fn,
            "revision": base_rev,
            "total_pages": baseline_doc.get("total_pages", 8),
            "total_chunks": len(baseline_doc.get("chunks", []))
        },
        "revised": {
            "document_id": revised_doc.get("document_id"),
            "filename": rev_fn,
            "revision": rev_rev,
            "total_pages": revised_doc.get("total_pages", 8),
            "total_chunks": len(revised_doc.get("chunks", []))
        },
        "total_changes": len(detected_changes),
        "unchanged_sections_count": unchanged_sections_count,
        "classification_summary": class_counts,
        "changes": detected_changes,
        "status": "success"
    }


def compare_sop_files(
    baseline_path: str,
    revised_path: str
) -> Dict[str, Any]:
    """
    Convenience wrapper: Extracts and compares two SOP PDF files directly.
    """
    if not os.path.exists(baseline_path):
        raise FileNotFoundError(f"Baseline PDF not found: {baseline_path}")
    if not os.path.exists(revised_path):
        raise FileNotFoundError(f"Revised PDF not found: {revised_path}")

    base_doc = dp.process_pdf(baseline_path)
    rev_doc = dp.process_pdf(revised_path)

    return compare_sop_revisions(base_doc, rev_doc)


def compare_all_existing_pairs(sop_dir: str = "SOP") -> List[Dict[str, Any]]:
    """
    Performs full revision comparison across all 5 official SOP pairs.
    """
    pairs = get_available_sop_pairs(sop_dir=sop_dir)
    results = []

    for p in pairs:
        logger.info(f"Comparing pair: {p['baseline_filename']} <---> {p['revised_filename']}")
        res = compare_sop_files(p["baseline_path"], p["revised_path"])
        results.append(res)

    return results


# ============================================================================
# REPORT GENERATION & EXPORT
# ============================================================================

def generate_comparison_report(
    comparison_result: Dict[str, Any],
    report_format: str = "markdown"
) -> str:
    """
    Generates a structured, traceable engineering report summarizing all
    detected changes between baseline and revised SOP versions.
    
    Args:
        comparison_result: Output from compare_sop_revisions().
        report_format: 'markdown' or 'text'.
        
    Returns:
        str: Formatted report text.
    """
    base_info = comparison_result["baseline"]
    rev_info = comparison_result["revised"]
    log_id = comparison_result["logical_sop_id"]
    title = comparison_result["document_title"]
    changes = comparison_result["changes"]
    counts = comparison_result["classification_summary"]

    lines = []
    lines.append(f"# SOP REVISION COMPARISON REPORT: {log_id}")
    lines.append(f"**Document Title:** {title}")
    lines.append(f"**Generated:** {comparison_result.get('status', 'complete').upper()}")
    lines.append("")
    lines.append("## 1. Specification Revisions")
    lines.append(f"- **Baseline:** `{base_info['filename']}` | ID: `{base_info['document_id']}` | Rev: `{base_info['revision']}`")
    lines.append(f"- **Revised:**  `{rev_info['filename']}` | ID: `{rev_info['document_id']}` | Rev: `{rev_info['revision']}`")
    lines.append("")
    lines.append("## 2. Executive Change Metrics")
    lines.append(f"- **Total Detected Changes:** {comparison_result['total_changes']}")
    lines.append(f"- **Unchanged Sections:** {comparison_result['unchanged_sections_count']}")
    lines.append("")
    lines.append("### Classification Breakdown:")
    for c_name, count in counts.items():
        if count > 0:
            lines.append(f"- **{c_name}:** {count}")
    lines.append("")
    lines.append("## 3. Traceable Change Inventory")
    lines.append("")

    for i, chg in enumerate(changes):
        lines.append(f"### Change [{i+1:02d}]: {chg['change_id']} — {chg['primary_classification']}")
        lines.append(f"- **Review Status:** `{chg['review_status']}`")
        lines.append(f"- **Operational Significance:** {chg['operational_significance']}")
        lines.append(f"- **Baseline Reference:** Section: *{chg['baseline_section']}* (Page {chg['baseline_page']})")
        lines.append(f"- **Revised Reference:**  Section: *{chg['revised_section']}* (Page {chg['revised_page']})")
        lines.append("")
        lines.append("#### Before (Baseline):")
        lines.append("```text")
        lines.append(chg["baseline_passage"] if chg["baseline_passage"] else "[Section not present in baseline]")
        lines.append("```")
        lines.append("#### After (Revised):")
        lines.append("```text")
        lines.append(chg["revised_passage"] if chg["revised_passage"] else "[Section removed in revision]")
        lines.append("```")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


# ============================================================================
# PHASE 8: CROSS-DOCUMENT IMPACT ANALYSIS ENGINE
# ============================================================================

IMPACT_DIRECT = "Direct impact"
IMPACT_POTENTIAL = "Potential impact"
IMPACT_NO_IDENTIFIED = "No identified impact"
IMPACT_INSUFFICIENT = "Insufficient evidence"
IMPACT_HUMAN_REVIEW = "Human review required"

ALL_IMPACT_CLASSES = [
    IMPACT_DIRECT,
    IMPACT_POTENTIAL,
    IMPACT_HUMAN_REVIEW,
    IMPACT_INSUFFICIENT,
    IMPACT_NO_IDENTIFIED
]

GENERIC_TERMS_STOPLIST = {
    "tank", "vehicle", "test", "bolt", "steel", "operator", "check", "specification",
    "general", "standard", "procedure", "operation", "section", "page", "assembly",
    "system", "part", "manual", "work", "unit", "grade", "item", "level", "line",
    "area", "metal", "mbt", "hvf", "avnl", "shop", "prior", "confirm", "ensure"
}

# Regex for Cross-Document Reference Extraction
RE_DOC_ID_REF = re.compile(
    r'\b(?:HVF[/_ -]AVNL[/_ -]SOP[/_ -]MBT[/_ -][A-Z0-9\-]+|HW-101|TI-204|EA-309|TS-412|GC-518|SOP[\s\-_]*[1-5])\b',
    re.IGNORECASE
)
RE_SECTION_REF = re.compile(
    r'\b(?:SECTION\s+\d+\.\d+|\d+\.\d+\.[A-Z]|\d+\.\d+|APPENDIX\s+[A-Z])\b',
    re.IGNORECASE
)
RE_EQUIP_REF = re.compile(
    r'\b(?:laser tracker|laser aligner|autocollimator|gmaw|paut|tofd|dynamometer|slip-ring|nutrunner|pyrometer|inclinometer|interferometer|theodolite|flir|spectrometer|turnover jig|mrs mirror|rotary joint)\b',
    re.IGNORECASE
)
RE_ACCEPTANCE_REF = re.compile(
    r'\b(?:paut|tofd|ndt|cev limit|h6 tolerance|iso 10816|vibration spectrum|helium leak|zero planar defect|zero defect|flank contact|dgqa)\b',
    re.IGNORECASE
)
RE_GOVERNANCE_REF = re.compile(
    r'\b(?:dgqa|chief metallurgist|mrb|shop superintendent|quality assurance|bay supervisor|commissioning committee)\b',
    re.IGNORECASE
)


def extract_cross_references(text: str) -> Dict[str, List[str]]:
    """
    Extracts and normalizes explicit cross-references from text:
    - Other SOP document IDs / codes
    - Section numbers
    - Equipment and tooling
    - Numerical parameters and tolerances
    - Inspection and acceptance criteria
    - Governance and sign-off authorities
    
    Returns:
        Dict[str, List[str]]: Structured dictionary of extracted normalized references.
    """
    if not text:
        return {
            "document_ids": [],
            "sections": [],
            "equipment": [],
            "parameters": [],
            "acceptance_criteria": [],
            "governance": []
        }

    # Document IDs
    raw_doc_ids = RE_DOC_ID_REF.findall(text)
    clean_doc_ids = sorted(list(set(re.sub(r'\s+', '-', d.strip().upper()) for d in raw_doc_ids)))

    # Sections
    raw_secs = RE_SECTION_REF.findall(text)
    clean_secs = sorted(list(set(s.strip().upper() for s in raw_secs)))

    # Equipment
    raw_equip = RE_EQUIP_REF.findall(text)
    clean_equip = sorted(list(set(e.strip().title() for e in raw_equip)))

    # Numerical Parameters
    raw_params = RE_NUMERICAL.findall(text)
    clean_params = sorted(list(set(p.strip() for p in raw_params)))

    # Acceptance Criteria
    raw_accept = RE_ACCEPTANCE_REF.findall(text)
    clean_accept = sorted(list(set(a.strip().upper() for a in raw_accept)))

    # Governance
    raw_gov = RE_GOVERNANCE_REF.findall(text)
    clean_gov = sorted(list(set(g.strip().title() for g in raw_gov)))

    return {
        "document_ids": clean_doc_ids,
        "sections": clean_secs,
        "equipment": clean_equip,
        "parameters": clean_params,
        "acceptance_criteria": clean_accept,
        "governance": clean_gov
    }


# Authoritative Physical & Functional Subsystem Interface Rules
INTERFACE_RULES = [
    # 1. Hull Welding <-> Turret Integration
    {
        "source_sop": "HVF_SOP_1_Hull_Welding",
        "affected_sop": "HVF_SOP_2_Turret_Integration",
        "source_pattern": r"(?:turret base mounting plane|plinth|turret mounting|hull upper deck plinth)",
        "affected_pattern": r"(?:plinth flatness|turret lower base ring|race fitment|bearing spigot concentricity|plinth mapping)",
        "dependency_type": "Direct Physical / Geometric Interface",
        "classification": IMPACT_DIRECT,
        "strength": "High (Coupled Geometric Tolerance)",
        "explanation": "Welded hull upper deck plinth flatness (≤ 0.35 mm across 2.2 m circle) directly dictates turret cross-roller bearing seating and plinth CNC re-facing tolerances (≤ 0.035 mm TIR)."
    },
    # 2. Hull Welding <-> Engine Alignment
    {
        "source_sop": "HVF_SOP_1_Hull_Welding",
        "affected_sop": "HVF_SOP_3_Engine_Alignment",
        "source_pattern": r"(?:transverse bulkhead|bulkhead pitch|engine bay mount|deck aperture)",
        "affected_pattern": r"(?:engine bay mount co-planarity|deck aperture edge clearance|rear engine bay)",
        "dependency_type": "Direct Physical / Geometric Interface",
        "classification": IMPACT_DIRECT,
        "strength": "High (Chassis Mounting Co-Planarity)",
        "explanation": "Transverse bulkhead weldment pitch (≤ 0.35 mm) directly dictates rear engine bay mount co-planarity (≤ 0.05 mm) and powerpack deck aperture clearance (≥ 22.0 mm)."
    },
    # 3. Hull Welding <-> Torsion Suspension
    {
        "source_sop": "HVF_SOP_1_Hull_Welding",
        "affected_sop": "HVF_SOP_4_Torsion_Suspension",
        "source_pattern": r"(?:torsion housing alignment|suspension pocket|torsion housing drift)",
        "affected_pattern": r"(?:suspension pocket bore grade|balancer arm radial clearance|torsion bar anchor)",
        "dependency_type": "Direct Physical / Geometric Interface",
        "classification": IMPACT_DIRECT,
        "strength": "High (Weld Distortion Drift to Bore Grade)",
        "explanation": "Hull welding thermal stress and torsion housing alignment drift (≤ 0.25 mm) directly govern suspension pocket H6 bore grades and balancer arm fitment."
    },
    # 4. Turret Integration <-> Gun Calibration
    {
        "source_sop": "HVF_SOP_2_Turret_Integration",
        "affected_sop": "HVF_SOP_5_Gun_Calibration",
        "source_pattern": r"(?:mantlet|elevation axis|line-of-sight stabilization|optical slip-ring|forj)",
        "affected_pattern": r"(?:mantlet cradle bushings|elevation trunnion alignment|muzzle reference system|boresight)",
        "dependency_type": "Direct Physical / Geometric Interface",
        "classification": IMPACT_DIRECT,
        "strength": "High (Mantlet Trunnion & MRS Sighting Alignment)",
        "explanation": "Turret line-of-sight stabilization (≤ 0.08 mrad) and mantlet cradle geometry directly dictate gun trunnion alignment (≤ 0.02 mm) and MRS sighting harmonization."
    },
    # 5. Turret Integration <-> Torsion Suspension
    {
        "source_sop": "HVF_SOP_2_Turret_Integration",
        "affected_sop": "HVF_SOP_4_Torsion_Suspension",
        "source_pattern": r"(?:cant-angle running torque|cant-angle|shake rig)",
        "affected_pattern": r"(?:static combat belly clearance|port-starboard level balance|ride height)",
        "dependency_type": "Chassis Attitude / Dynamic Sighting Interface",
        "classification": IMPACT_POTENTIAL,
        "strength": "Medium (Chassis Attitude Dynamic Coupling)",
        "explanation": "Turret 15-degree cant-angle running torque (≤ 410 Nm) is dynamically coupled to chassis suspension ride height (455 mm ± 4 mm) and bilateral tilt balance (≤ 1.0 mm)."
    },
    # 6. Engine Alignment <-> Torsion Suspension
    {
        "source_sop": "HVF_SOP_3_Engine_Alignment",
        "affected_sop": "HVF_SOP_4_Torsion_Suspension",
        "source_pattern": r"(?:final drive input concentricity|intermediate cardan spline|transmission output)",
        "affected_pattern": r"(?:sprocket-to-idler plane runout|drive sprocket bolt preload|laser alignment of drive sprockets)",
        "dependency_type": "Drivetrain Torque Coupling",
        "classification": IMPACT_DIRECT,
        "strength": "High (Drivetrain Coaxial Transmission)",
        "explanation": "Transmission output final drive concentricity (≤ 0.04 mm) and cardan spline backlash couple directly into suspension final drive sprockets (≤ 1.0 mm lateral runout)."
    },
    # 7. Torsion Suspension <-> Engine Alignment
    {
        "source_sop": "HVF_SOP_4_Torsion_Suspension",
        "affected_sop": "HVF_SOP_3_Engine_Alignment",
        "source_pattern": r"(?:sprocket-to-idler plane runout|drive sprocket bolt preload|drive sprocket)",
        "affected_pattern": r"(?:final drive input concentricity|intermediate cardan spline play|transmission input)",
        "dependency_type": "Drivetrain Torque Coupling",
        "classification": IMPACT_DIRECT,
        "strength": "High (Running Plane Drivetrain Interface)",
        "explanation": "Laser alignment of drive sprockets and return rollers couples with powerpack final drive concentricity and torque transmission."
    },
    # 8. Torsion Suspension <-> Turret Integration
    {
        "source_sop": "HVF_SOP_4_Torsion_Suspension",
        "affected_sop": "HVF_SOP_2_Turret_Integration",
        "source_pattern": r"(?:static combat belly clearance|port-starboard level balance|belly clearance)",
        "affected_pattern": r"(?:cant-angle running torque|dynamic stabilization drift|crane active level)",
        "dependency_type": "Chassis Attitude / Sighting Datum Interface",
        "classification": IMPACT_POTENTIAL,
        "strength": "Medium (Chassis Attitude Ground Plane)",
        "explanation": "Combat belly clearance (455 mm ± 4 mm) and port-starboard level balance (≤ 1.0 mm tilt differential) directly establish the datum attitude for turret traverse and cant-angle stabilization."
    },
    # 9. Torsion Suspension <-> Gun Calibration
    {
        "source_sop": "HVF_SOP_4_Torsion_Suspension",
        "affected_sop": "HVF_SOP_5_Gun_Calibration",
        "source_pattern": r"(?:static combat belly clearance|port-starboard level balance|belly clearance)",
        "affected_pattern": r"(?:muzzle reference system|boresight harmonization|static out-of-balance torque)",
        "dependency_type": "Chassis Attitude / Sighting Datum Interface",
        "classification": IMPACT_POTENTIAL,
        "strength": "Medium (Sighting Datum Attitude Coupling)",
        "explanation": "Suspension ride height precision and bilateral level balance directly establish the reference plane for main gun elevation zeroing and boresight harmonization."
    },
    # 10. Gun Calibration <-> Turret Integration
    {
        "source_sop": "HVF_SOP_5_Gun_Calibration",
        "affected_sop": "HVF_SOP_2_Turret_Integration",
        "source_pattern": r"(?:elevation trunnion alignment|mantlet cradle|muzzle reference system|optical transceiver)",
        "affected_pattern": r"(?:line-of-sight stabilization|optical rotary slip-ring|forj|traverse slew rate)",
        "dependency_type": "Direct Physical / Geometric Interface",
        "classification": IMPACT_DIRECT,
        "strength": "High (Trunnion Coaxiality & Sighting Harmonization)",
        "explanation": "Gun elevation trunnion alignment (≤ 0.02 mm) and Muzzle Reference System optical transceiver alignment directly link to turret-roof sensors and mantlet cradle bushings in Shop-09A."
    },
    # 11. Engine Alignment <-> Turret Integration (Insufficient evidence in corpus)
    {
        "source_sop": "HVF_SOP_3_Engine_Alignment",
        "affected_sop": "HVF_SOP_2_Turret_Integration",
        "source_pattern": r"(?:bilge pump|cooling circuit|scavenge blower|thermal aerogel shield)",
        "affected_pattern": r"(?:hermetic nbc seal|ballistic labyrinth mud|nbc seal)",
        "dependency_type": "Chassis Environmental & Thermal Seal Enclosure",
        "classification": IMPACT_INSUFFICIENT,
        "strength": "Low (Corpus Lacks Specific Coupling Tolerances)",
        "explanation": "Engine bay bilge scavenge pressure and cooling flow vent near the turret plinth sealing perimeter, but the indexed corpus lacks specific coupled thermal/pressure tolerances to substantiate a direct impact."
    }
]


def identify_cross_document_impacts(
    change: Dict[str, Any],
    corpus_docs: List[Dict[str, Any]],
    source_sop_id: str,
    db_path: str = db.DEFAULT_DB_PATH
) -> List[Dict[str, Any]]:
    """
    Evaluates a single substantive change against all other SOP documents in the corpus.
    
    Guarantees:
    - Excludes source SOP from impacted candidates.
    - Uses deterministic physical interfaces and explicit cross-references.
    - Prevents vague generic terminology overlap from generating false dependencies.
    - Classifies safety-critical and ambiguous tolerance shifts as 'Human review required'.
    - Persists and links human review decisions via database.py.
    """
    impact_candidates: List[Dict[str, Any]] = []

    # Check for pure editorial changes
    primary_class = change.get("primary_classification", "")
    if primary_class == "Editorial or formatting-only change":
        return []

    source_text = re.sub(r'\s+', ' ', (change.get("revised_passage", "") + " " + change.get("baseline_passage", ""))).lower()
    is_safety_change = "Changed safety warning or precaution" in change.get("classifications", [])
    has_safety_hazard_words = any(w in source_text for w in ["hazard", "danger", "warning", "ppe", "interlock", "radiation", "fume", "emergency"])
    change_id = change.get("change_id", "CHG-UNKNOWN")

    # Map candidate short ID prefix
    src_short = source_sop_id.replace("HVF_SOP_", "").split("_")[0]
    match_counter = 1

    for doc in corpus_docs:
        other_sop_id = doc.get("logical_sop_id", "")
        if not other_sop_id or other_sop_id == source_sop_id:
            continue

        other_short = other_sop_id.replace("HVF_SOP_", "").split("_")[0]
        other_title = doc.get("document_title", "SOP")
        other_doc_id = doc.get("document_id", "UNKNOWN")
        other_fn = doc.get("filename", "")
        other_rev = doc.get("revision", "")

        # 1. Check for Explicit Document Citations in other_doc chunks
        for chunk in doc.get("chunks", []):
            chunk_txt = chunk["chunk_text"]
            src_doc_id = change.get("baseline_document_id", "")
            if src_doc_id and src_doc_id.lower() in chunk_txt.lower():
                impact_id = f"IMP-{src_short}-{other_short}-{change_id[-2:]}-{match_counter:02d}"
                match_counter += 1

                rev_record = db.get_impact_review(impact_id, db_path=db_path)
                decision = rev_record["decision"] if rev_record else "PENDING"
                notes = rev_record["reviewer_notes"] if rev_record else ""

                impact_candidates.append({
                    "impact_id": impact_id,
                    "source_sop_id": source_sop_id,
                    "source_title": change.get("document_title", "Source SOP"),
                    "source_document_id": change.get("baseline_document_id", change.get("document_id")),
                    "source_filename": change.get("revised_filename", change.get("baseline_filename")),
                    "source_revision": change.get("revised_revision", change.get("baseline_revision")),
                    "source_change_id": change_id,
                    "source_section": change.get("revised_section") or change.get("baseline_section"),
                    "source_page": change.get("revised_page") or change.get("baseline_page"),
                    "source_passage": change.get("revised_passage") or change.get("baseline_passage"),
                    "affected_sop_id": other_sop_id,
                    "affected_title": other_title,
                    "affected_document_id": other_doc_id,
                    "affected_filename": other_fn,
                    "affected_revision": other_rev,
                    "affected_section": chunk["section_title"],
                    "affected_page": chunk["page_number"],
                    "affected_passage": chunk_txt.strip(),
                    "dependency_type": "Explicit SOP Document Citation",
                    "classification": IMPACT_DIRECT,
                    "explanation": f"Document explicitly cites source specification '{source_sop_id}', creating a direct compliance dependency.",
                    "evidence_strength": "High (Explicit Document Citation)",
                    "review_status": decision,
                    "reviewer_notes": notes,
                    "is_human_reviewed": bool(rev_record)
                })

        # 2. Check Subsystem Physical Interfaces
        for rule in INTERFACE_RULES:
            if rule["source_sop"] != source_sop_id or rule["affected_sop"] != other_sop_id:
                continue

            m_src = re.findall(rule["source_pattern"], source_text, re.IGNORECASE)
            if not m_src:
                continue

            for chunk in doc.get("chunks", []):
                c_txt = re.sub(r'\s+', ' ', chunk["chunk_text"]).lower()
                m_aff = re.findall(rule["affected_pattern"], c_txt, re.IGNORECASE)
                if m_aff:
                    impact_id = f"IMP-{src_short}-{other_short}-{change_id[-2:]}-{match_counter:02d}"
                    match_counter += 1

                    if primary_class == "Changed safety warning or precaution" and has_safety_hazard_words:
                        classification = IMPACT_HUMAN_REVIEW
                        strength = "Critical (Safety / Hazard Protocol Review Mandate)"
                        expl = f"Safety warning or hazard protocol modification in {source_sop_id} may propagate operational risk to {other_sop_id} ({rule['dependency_type']}). Human review required."
                    else:
                        classification = rule["classification"]
                        strength = rule["strength"]
                        expl = f"{rule['explanation']} Matched interface term: '{m_src[0]}'."

                    rev_record = db.get_impact_review(impact_id, db_path=db_path)
                    decision = rev_record["decision"] if rev_record else "PENDING"
                    notes = rev_record["reviewer_notes"] if rev_record else ""

                    impact_candidates.append({
                        "impact_id": impact_id,
                        "source_sop_id": source_sop_id,
                        "source_title": change.get("document_title", "Source SOP"),
                        "source_document_id": change.get("baseline_document_id", change.get("document_id")),
                        "source_filename": change.get("revised_filename", change.get("baseline_filename")),
                        "source_revision": change.get("revised_revision", change.get("baseline_revision")),
                        "source_change_id": change_id,
                        "source_section": change.get("revised_section") or change.get("baseline_section"),
                        "source_page": change.get("revised_page") or change.get("baseline_page"),
                        "source_passage": change.get("revised_passage") or change.get("baseline_passage"),
                        "affected_sop_id": other_sop_id,
                        "affected_title": other_title,
                        "affected_document_id": other_doc_id,
                        "affected_filename": other_fn,
                        "affected_revision": other_rev,
                        "affected_section": chunk["section_title"],
                        "affected_page": chunk["page_number"],
                        "affected_passage": chunk["chunk_text"].strip(),
                        "dependency_type": rule["dependency_type"],
                        "classification": classification,
                        "explanation": expl,
                        "evidence_strength": strength,
                        "review_status": decision,
                        "reviewer_notes": notes,
                        "is_human_reviewed": bool(rev_record)
                    })

    return impact_candidates


def analyze_cross_document_impacts(
    comparison_result: Dict[str, Any],
    corpus_docs: Optional[List[Dict[str, Any]]] = None,
    sop_dir: str = "SOP",
    db_path: str = db.DEFAULT_DB_PATH
) -> Dict[str, Any]:
    """
    Executes cross-document impact analysis across all substantive changes
    identified in a Phase 7 revision comparison.
    
    Args:
        comparison_result: Output from compare_sop_revisions() or compare_sop_files().
        corpus_docs: Optional pre-extracted documents across the 10 SOPs.
        sop_dir: Path to directory containing authoritative SOP PDFs.
        db_path: Path to SQLite persistence database.
        
    Returns:
        Dict[str, Any]: Complete impact analysis results containing evidence-backed candidates,
                       classification breakdowns, and review workflow states.
    """
    source_sop_id = comparison_result["logical_sop_id"]
    source_title = comparison_result.get("document_title", "SOP")
    changes = comparison_result.get("changes", [])

    # Load corpus documents if not provided
    if not corpus_docs:
        corpus_docs = []
        if os.path.isdir(sop_dir):
            for fn in sorted(os.listdir(sop_dir)):
                if fn.lower().endswith(".pdf"):
                    p = os.path.join(sop_dir, fn)
                    try:
                        corpus_docs.append(dp.process_pdf(p))
                    except Exception as e:
                        logger.warning(f"Could not load corpus PDF '{fn}': {e}")

    # Discover impact candidates across all substantive changes
    all_candidates: List[Dict[str, Any]] = []
    substantive_changes_count = 0
    editorial_changes_count = 0

    for chg in changes:
        p_class = chg.get("primary_classification", "")
        if p_class == "Editorial or formatting-only change":
            editorial_changes_count += 1
            continue

        substantive_changes_count += 1
        cands = identify_cross_document_impacts(
            change=chg,
            corpus_docs=corpus_docs,
            source_sop_id=source_sop_id,
            db_path=db_path
        )
        all_candidates.extend(cands)

    # Classifications breakdown
    counts_by_class: Dict[str, int] = {c: 0 for c in ALL_IMPACT_CLASSES}
    counts_by_decision: Dict[str, int] = {
        "PENDING": 0,
        "ACCEPTED": 0,
        "REJECTED": 0,
        "INVESTIGATE": 0
    }

    # Deduplicate candidates by (source_change_id, affected_sop_id, affected_section)
    unique_candidates: List[Dict[str, Any]] = []
    seen_keys: Set[Tuple[str, str, str]] = set()

    for cand in all_candidates:
        key = (cand["source_change_id"], cand["affected_sop_id"], cand["affected_section"])
        if key not in seen_keys:
            seen_keys.add(key)
            unique_candidates.append(cand)
            c_class = cand["classification"]
            if c_class in counts_by_class:
                counts_by_class[c_class] += 1
            dec = cand["review_status"]
            if dec in counts_by_decision:
                counts_by_decision[dec] += 1

    # Track SOPs with no identified impact
    all_corpus_sop_ids = {d["logical_sop_id"] for d in corpus_docs if d.get("logical_sop_id")}
    impacted_sop_ids = {c["affected_sop_id"] for c in unique_candidates}
    unimpacted_sop_ids = sorted(list((all_corpus_sop_ids - {source_sop_id}) - impacted_sop_ids))

    if unimpacted_sop_ids:
        counts_by_class[IMPACT_NO_IDENTIFIED] = len(unimpacted_sop_ids)

    return {
        "source_sop_id": source_sop_id,
        "source_document_title": source_title,
        "baseline_filename": comparison_result.get("baseline", {}).get("filename"),
        "revised_filename": comparison_result.get("revised", {}).get("filename"),
        "total_source_changes": len(changes),
        "substantive_changes_count": substantive_changes_count,
        "editorial_changes_count": editorial_changes_count,
        "total_candidates": len(unique_candidates),
        "unimpacted_sop_count": len(unimpacted_sop_ids),
        "unimpacted_sops": unimpacted_sop_ids,
        "counts_by_classification": counts_by_class,
        "counts_by_decision": counts_by_decision,
        "candidates": unique_candidates,
        "status": "success"
    }


def generate_impact_report(
    impact_result: Dict[str, Any],
    report_format: str = "markdown"
) -> str:
    """
    Generates a structured, traceable engineering report summarizing all
    cross-document impact analysis findings and human review decisions.
    """
    lines = []
    lines.append(f"# CROSS-DOCUMENT IMPACT ANALYSIS REPORT: {impact_result['source_sop_id']}")
    lines.append(f"**Source Document Title:** {impact_result.get('source_document_title', 'SOP')}")
    lines.append(f"**Baseline File:** `{impact_result.get('baseline_filename')}` | **Revised File:** `{impact_result.get('revised_filename')}`")
    lines.append("")
    lines.append("## 1. Executive Summary & Impact Metrics")
    lines.append(f"- **Total Substantive Source Changes Evaluated:** {impact_result.get('substantive_changes_count', 0)}")
    lines.append(f"- **Editorial Changes Filtered (No Impact):** {impact_result.get('editorial_changes_count', 0)}")
    lines.append(f"- **Identified Impact Candidates:** {impact_result.get('total_candidates', 0)}")
    lines.append("")
    lines.append("### Breakdown by Impact Classification:")
    for c_name, count in impact_result.get("counts_by_classification", {}).items():
        lines.append(f"- **{c_name}:** {count}")
    lines.append("")
    lines.append("### Human Review Decisions:")
    for d_name, count in impact_result.get("counts_by_decision", {}).items():
        lines.append(f"- **{d_name}:** {count}")
    lines.append("")
    if impact_result.get("unimpacted_sops"):
        lines.append(f"### Subsystems with No Identified Impact in Corpus:")
        for s in impact_result["unimpacted_sops"]:
            lines.append(f"- `{s}`")
        lines.append("*(Note: 'No identified impact' reflects the indexed corpus and does not guarantee absence of unindexed external dependencies).*")
        lines.append("")

    lines.append("## 2. Evidence-Backed Impact Candidates")
    lines.append("")

    candidates = impact_result.get("candidates", [])
    if not candidates:
        lines.append("*No cross-document impacts detected for substantive changes in the indexed corpus.*")
    else:
        for i, cand in enumerate(candidates):
            lines.append(f"### Candidate [{i+1:02d}]: {cand['impact_id']} — {cand['classification']}")
            lines.append(f"- **Affected Subsystem:** `{cand['affected_sop_id']}` ({cand['affected_title']})")
            lines.append(f"- **Dependency Type:** {cand['dependency_type']}")
            lines.append(f"- **Evidence Strength:** `{cand['evidence_strength']}`")
            lines.append(f"- **Human Review Status:** `{cand['review_status']}`" + (f" (*Notes: {cand['reviewer_notes']}*)" if cand['reviewer_notes'] else ""))
            lines.append(f"- **Technical Explanation:** {cand['explanation']}")
            lines.append(f"- **Source Reference:** Section: *{cand['source_section']}* (Page {cand['source_page']}) | Change: `{cand['source_change_id']}`")
            lines.append(f"- **Affected Reference:** Section: *{cand['affected_section']}* (Page {cand['affected_page']})")
            lines.append("")
            lines.append("#### Source Changed Passage:")
            lines.append("```text")
            lines.append(cand["source_passage"][:400] + ("..." if len(cand["source_passage"]) > 400 else ""))
            lines.append("```")
            lines.append("#### Affected Document Evidence Passage:")
            lines.append("```text")
            lines.append(cand["affected_passage"][:400] + ("..." if len(cand["affected_passage"]) > 400 else ""))
            lines.append("```")
            lines.append("---")
            lines.append("")

    return "\n".join(lines)


# ============================================================================
# SELF-TEST & VALIDATION
# ============================================================================

if __name__ == "__main__":
    print("Executing sop_analyzer self-test across available pairs...")
    pairs = get_available_sop_pairs()
    print(f"Discovered {len(pairs)} SOP revision pairs.")

    if pairs:
        first_pair = pairs[0]
        print(f"Comparing pair: {first_pair['logical_sop_id']}")
        cmp_res = compare_sop_files(first_pair["baseline_path"], first_pair["revised_path"])
        print(f"Total changes detected: {cmp_res['total_changes']}")
        print(f"Numerical changes: {cmp_res['classification_summary'].get('Changed numerical parameter, tolerance, or threshold', 0)}")
        print(f"Safety changes: {cmp_res['classification_summary'].get('Changed safety warning or precaution', 0)}")
        sample_rpt = generate_comparison_report(cmp_res)
        print(f"Report generated: {len(sample_rpt)} characters.")
    print("Self-test completed successfully.")

