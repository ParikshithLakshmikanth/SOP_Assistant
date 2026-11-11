#!/usr/bin/env python3
"""
SOP Document Intelligence: Evidence-Based RAG Answer Evaluator
==============================================================
Module: rag_evaluator.py
Role: Mini Phase 13 — Per-Answer Quality Assessment, Claim-Level Verification,
      and Critical Technical Safety Auditing.

Design Guarantees:
1. Evaluates ONLY against the actual retrieved SOP evidence and citations passed
   from the RAG pipeline (never retrieves external documents independently).
2. Local evaluation ONLY via the existing local Ollama runtime (zero external APIs).
3. Enforces deterministic technical safety checks (tolerances, dimensions, materials,
   load limits, calibration values, acceptance criteria, safety/inspection rules) so
   optimistic LLM scores can NEVER hide a critical technical error.
4. Enforces weighted scoring formula with explicit justification per metric and
   explicit NOT ASSESSED handling when metrics cannot be evaluated.
5. Non-destructive: never alters, blocks, or destroys the original generated answer
   if evaluation fails, times out, or returns malformed JSON.
"""

import re
import json
import time
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, Callable

import rag_engine as re_engine

logger = logging.getLogger("SOP_RAGEvaluator")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ============================================================================
# CONSTANTS & EVALUATION SCHEMA CONTRACTS
# ============================================================================

ASSESSMENT_VERSION = "1.0.0"
DEFAULT_EVAL_MODEL = re_engine.DEFAULT_LLM_MODEL
DEFAULT_OLLAMA_ENDPOINT = re_engine.DEFAULT_OLLAMA_ENDPOINT

METRIC_WEIGHTS: Dict[str, float] = {
    "evidence_support": 0.40,
    "answer_relevance": 0.25,
    "completeness": 0.15,
    "citation_coverage": 0.10,
    "retrieval_quality": 0.10,
}

ALLOWED_CLAIM_STATUSES = {
    "SUPPORTED",
    "PARTIALLY_SUPPORTED",
    "UNSUPPORTED",
    "CONTRADICTED",
    "INFERRED",
    "GENERAL_CONTEXT",
}

ALLOWED_WARNING_LABELS = {
    "HIGH EVIDENCE SUPPORT",
    "PARTIAL EVIDENCE",
    "INSUFFICIENT EVIDENCE",
    "UNSUPPORTED CLAIMS DETECTED",
    "CONTRADICTORY EVIDENCE",
    "ASSESSMENT UNAVAILABLE",
}

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "are", "was",
    "were", "have", "has", "had", "not", "but", "what", "which", "who", "whom",
    "when", "where", "why", "how", "does", "did", "can", "could", "would",
    "should", "may", "might", "must", "shall", "will", "about", "across",
    "between", "under", "over", "above", "below", "through", "during", "before",
    "after", "only", "also", "such", "than", "then", "there", "these", "those",
    "its", "their", "your", "our", "all", "any", "each", "both", "more", "most",
    "other", "some", "using", "used", "use", "per", "via", "based", "sop",
    "page", "section", "rev", "revision", "version", "document", "hvf", "avnl",
}

ABSTENTION_SIGNALS = [
    "does not contain sufficient",
    "does not provide sufficient",
    "does not contain information",
    "does not contain specific",
    "does not document",
    "insufficient evidence",
    "not specify",
    "not specified",
    "not mentioned in",
    "not documented",
    "no information provided",
    "there is no information",
    "no relationship is specified",
    "cannot be determined from",
    "missing from the retrieved",
    "not covered in the retrieved",
    "no specific evidence",
    "none explicitly documented",
]

# Critical technical safety categories & detection regexes
CRITICAL_CATEGORY_PATTERNS: List[Tuple[str, str]] = [
    ("tolerance", r"(?:±|\+/-|\btir\b|total indicator|runout|backlash|clearance|concentricity|eccentricity|flatness|straightness|tolerance|coaxiality|offset|deviation|droop)"),
    ("dimension", r"(?:\b\d+(?:\.\d+)?\s*(?:mm|cm|m|inch|inches|micron|µm)\b|\bthickness\b|\bdiameter\b|\broot\s+gap\b|\bpitch\b|\bbore\b|\bspan\b)"),
    ("material", r"(?:\b(?:SAE|AISI|ASTM|IS|MIL-DTL|DMR|GOST)\s*[-]?\s*[A-Z0-9]+\b|\bRHA\b|\bHHA\b|\bBHN\b|\bHBW\b|\bHRC\b|\bgrade\s+\d+(?:\.\d+)?\b|\bceramic[-\s]hybrid\b|\btitanium\b|\bSi3N4\b|\bMolykote\b|\bKrytox\b|\bPTFE\b|\bchrome[-\s]molybdenum\b)"),
    ("load_limit", r"(?:\b\d+(?:\.\d+)?\s*(?:Nm|N·m|kN|tonne|tonnes|ton|tons|kgf|kg|MPa|GPa|bar|psi)\b|\btorque\b|\bbreakaway\b|\bpreload\b|\bpre-load\b|\bload\s+(?:limit|distribution)\b)"),
    ("calibration", r"(?:\b\d+(?:\.\d+)?\s*(?:mrad|mil|arcsec|°C|°F|Hz|RPM|kW|HP|dB|MΩ|mΩ|VDC|sec)\b|\bboresight\b|\bmuzzle\s+reference\b|\bmrs\b|\bCpk\b|\bcalibrat)"),
    ("acceptance_criteria", r"(?:\bacceptance\b|\bstage[-\s]gate\b|\bmrb\b|\bred[-\s]tag\b|\bncr\b|\bquarantine\b|\bstop[-\s]line\b|\bstrict\s+maximum\b|\bmandatory\b|\bzero\s+(?:bypass|pressure\s+decay)\b)"),
    ("safety", r"(?:\bsafety\b|\bhazard\b|\bscada\s+safety\s+trip\b|\bhydrogen[-\s]induced\b|\bblast\b|\bppe\b|\bofficial\s+secrets\b)"),
    ("inspection", r"(?:\bpaut\b|\btofd\b|\bmpi\b|\bultrasonic\b|\bspectroscopy\b|\bautocollimator\b|\blaser\s+tracker\b|\bindenter\b|\bdyno\b|\bnondestructive\b|\bnon-destructive\b|\bndT\b)"),
]

# Extraction regex for technical numbers + units
TECH_VALUE_REGEX = re.compile(
    r"(?P<prefix>[±+\-≤≥<>]?\s*)?"
    r"(?P<num>\d+(?:,\d{3})*(?:\.\d+)?)"
    r"(?:\s*(?:–|-|to)\s*(?P<num2>\d+(?:,\d{3})*(?:\.\d+)?))?"
    r"\s*(?P<unit>mm/m|mm|cm|µm|micron|mrad|mil|Nm|N·m|kN|MPa|GPa|bar|psi|°C|°F|Hz|RPM|kW|HP|MΩ|mΩ|dB|BHN|HBW|HRC|CEV|kgf|tonne|tonnes|sec|min|%)\b",
    re.IGNORECASE,
)

# Material / grade / code regex (uppercase standard prefixes to avoid matching lowercase "is 150")
TECH_CODE_REGEX = re.compile(
    r"\b(?:SAE\s*[-]?\s*\d{3,4}|AISI\s*[-]?\s*\d{3,4}|IS\s*[-]?\s*\d{3,5}|ASTM\s*[-]?\s*[A-Z]?\d+|"
    r"MIL-DTL-\d+[A-Z]?|MIL-PRF-\d+|MIL-STD-\d+|DMR-\d+[A-Z]?|"
    r"[Gg]rade\s+\d+(?:\.\d+)?|Si3N4|ER-\d+|2A46M-5|V-92S2|T-90S|AT960)\b"
)

INLINE_CITATION_REGEX = re.compile(r"\[([^\[\]]{6,180})\]")


# ============================================================================
# HELPER FUNCTIONS: CATEGORIZATION & TEXT PARSING
# ============================================================================

def get_quality_category(score: Optional[float]) -> str:
    """
    Maps a 0-100 quality score to descriptive evidence support category.
    Note: These represent automated evidence-alignment quality estimates,
    NOT probabilities that an answer is objectively true.
    """
    if score is None:
        return "NOT ASSESSED"
    try:
        val = float(score)
    except (TypeError, ValueError):
        return "NOT ASSESSED"

    if val >= 90.0:
        return "Strong evidence support"
    if val >= 75.0:
        return "Good evidence support"
    if val >= 60.0:
        return "Moderate evidence support"
    if val >= 40.0:
        return "Weak evidence support"
    return "Poor evidence support"


def _tokenize_content_words(text: str) -> set:
    """Extracts normalized alphanumeric tokens excluding stopwords."""
    if not text:
        return set()
    words = re.findall(r"[a-z0-9]{3,}", text.lower())
    return {w for w in words if w not in STOPWORDS}


def classify_critical_claim(claim_text: str) -> Tuple[bool, Optional[str]]:
    """
    Determines whether a factual claim contains critical technical content
    (tolerances, dimensions, materials, load limits, calibration values,
    acceptance criteria, safety requirements, or inspection requirements).
    """
    if not claim_text:
        return False, None

    low = claim_text.lower()
    # Explicit honest abstentions should not be treated as hazardous spec inventions
    if any(sig in low for sig in ABSTENTION_SIGNALS) and not TECH_VALUE_REGEX.search(claim_text):
        return False, None

    for cat_name, pattern in CRITICAL_CATEGORY_PATTERNS:
        if re.search(pattern, claim_text, re.IGNORECASE):
            return True, cat_name
    return False, None


def extract_factual_claims(answer: str, max_claims: int = 15) -> List[str]:
    """
    Breaks an assistant response into clean atomic factual claims.
    Filters out markdown headers, empty separators, and pure UI cancellation tags.
    """
    if not answer or not answer.strip():
        return []

    cleaned = answer.strip()
    # Remove cancellation / error footer markers before segmenting claims
    cleaned = re.sub(r"\*\[Generation was stopped by user\]\*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*\[No response generated\]\*", "", cleaned, flags=re.IGNORECASE)

    raw_lines = [ln.strip() for ln in cleaned.splitlines() if ln.strip()]
    claims: List[str] = []

    for ln in raw_lines:
        # Skip markdown horizontal rules & headers without factual content
        if re.match(r"^[-=*_]{3,}$", ln):
            continue
        if re.match(r"^#{1,6}\s+.+$", ln):
            continue
        if re.match(r"^\*\*[^*]{1,40}\*\*$", ln):
            # Pure bold section label like "**What it is**"
            continue

        # Handle markdown table separator rows
        if re.match(r"^\|[\s\-:|]+\|$", ln):
            continue

        # Clean bullet/numbered prefixes and bold markers to check structural headings
        ln_clean = re.sub(r"^(?:[-*•]+|\d+[.)])\s+", "", ln).strip()
        heading_probe = re.sub(r"\*+", "", ln_clean).strip()
        heading_probe_norm = heading_probe.rstrip(":").strip().lower()
        structural_headers = {
            "overview",
            "main components / assemblies",
            "main components",
            "component functions",
            "validated relationships",
            "relevant procedures & operational context",
            "relevant procedures and operational context",
            "what the sop does not specify",
            "summary",
            "conclusion",
            "key differences",
            "technical parameters",
            "acceptance criteria",
        }
        if heading_probe_norm in structural_headers:
            continue
        if (
            heading_probe.endswith(":")
            and len(heading_probe) <= 180
            and not TECH_VALUE_REGEX.search(heading_probe)
        ):
            # Short section label or conversational lead-in ending with ':' (e.g. "Here is the breakdown...:")
            if (
                len(heading_probe.split()) <= 6
                or re.match(r"^(?:here\s+(?:is|are)|based\s+(?:strictly\s+)?on|below\s+(?:is|are)|the\s+following)\b", heading_probe_norm)
            ):
                continue

        if ln.startswith("|") and ln.endswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|") if c.strip()]
            # Skip table header row if it's purely uppercase labels
            if cells and all(re.match(r"^[A-Z\s/_-]+$", c) for c in cells):
                continue
            ln_clean = ": ".join(cells)

        if len(ln_clean) < 12:
            continue

        # Split long paragraphs into individual sentences, guarding abbreviations/decimals
        if len(ln_clean) > 180 and "|" not in ln:
            # Split at sentence boundaries while keeping bracketed citations attached
            parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9*\[])", ln_clean)
            for p in parts:
                p_s = p.strip()
                if len(p_s) >= 12:
                    claims.append(p_s)
        else:
            claims.append(ln_clean)

    # Deduplicate while preserving order and cap count
    seen = set()
    final_claims: List[str] = []
    for c in claims:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            final_claims.append(c)
        if len(final_claims) >= max_claims:
            break

    return final_claims


def extract_inline_citations(text: str) -> List[str]:
    """Extracts bracketed citation references from text (normalizing markdown-escaped underscores)."""
    if not text:
        return []
    matches = INLINE_CITATION_REGEX.findall(text)
    valid = []
    for m in matches:
        m_clean = m.strip().replace("\\_", "_")
        # Filter out markdown link patterns or UI status tags
        if ".pdf" in m_clean.lower() or "rev" in m_clean.lower() or "page" in m_clean.lower() or "section" in m_clean.lower() or "hvf_sop" in m_clean.lower():
            valid.append(m_clean)
    return valid


def _collect_evidence_records(
    citations: Optional[List[Dict[str, Any]]],
    info: Optional[Dict[str, Any]] = None,
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Normalizes retrieved citations and evidence passages into a unified list
    and builds the combined evidence corpus string ONLY from retrieved items.
    """
    records: List[Dict[str, Any]] = []
    text_parts: List[str] = []

    if citations:
        for i, c in enumerate(citations, 1):
            fname = c.get("filename") or c.get("document_id") or c.get("source_filename") or "Unknown_SOP.pdf"
            rev = str(c.get("revision") or "N/A")
            sec = str(c.get("section_title") or c.get("section") or c.get("section_reference") or "General")
            page = c.get("page_number") or c.get("page_numbers") or "N/A"
            ev_status = c.get("evidence_status") or "DIRECTLY_STATED"
            score = c.get("score")
            passage = (
                c.get("chunk_text")
                or c.get("text_excerpt")
                or c.get("passage")
                or ""
            ).strip()

            # Enrich component citation text if component metadata fields exist
            comp_name = c.get("component_name")
            if comp_name and not passage:
                comp_bits = [f"Component: {comp_name} ({c.get('entity_type', 'COMPONENT')})"]
                if c.get("citation"):
                    comp_bits.append(f"Citation: {c['citation']}")
                passage = " | ".join(comp_bits)

            records.append({
                "evidence_id": f"E{i}",
                "filename": str(fname),
                "revision": rev,
                "section": sec,
                "page": page,
                "evidence_status": ev_status,
                "score": float(score) if score is not None else None,
                "text": passage,
                "raw_citation": c.get("citation") or f"{fname}, {rev}, {sec}, Page {page}",
            })
            if passage:
                text_parts.append(f"[{fname} | {rev} | {sec} | Page {page}]\n{passage}")

    if info and info.get("evidence_context"):
        text_parts.append(str(info["evidence_context"]))

    return records, "\n\n".join(text_parts)


def _normalize_number_str(s: str) -> float:
    return float(s.replace(",", ""))


def _extract_tech_values(text: str) -> List[Dict[str, Any]]:
    """Extracts numeric values paired with engineering units from text."""
    results = []
    for m in TECH_VALUE_REGEX.finditer(text or ""):
        unit = m.group("unit").lower()
        nums = [_normalize_number_str(m.group("num"))]
        if m.group("num2"):
            nums.append(_normalize_number_str(m.group("num2")))
        # Capture local context window (5 words left/right)
        start = max(0, m.start() - 45)
        end = min(len(text), m.end() + 45)
        ctx = text[start:end]
        results.append({
            "raw": m.group(0).strip(),
            "nums": nums,
            "unit": unit,
            "ctx_tokens": _tokenize_content_words(ctx),
        })
    return results


def _check_inline_citation_validity(
    inline_cits: List[str],
    records: List[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """
    Verifies whether inline bracketed citations match the actual retrieved citations.
    Returns (all_valid, error_description).
    """
    if not inline_cits:
        return True, None
    if not records:
        return False, f"Inline citation [{inline_cits[0]}] references a document, but no SOP citations were retrieved."

    for cit_str in inline_cits:
        low_cit = cit_str.replace("\\_", "_").lower()

        # Check filename match if a .pdf is named
        pdf_match = re.search(r"([a-z0-9_\-]+\.pdf)", low_cit, re.IGNORECASE)
        candidate_records = records
        if pdf_match:
            cited_pdf = pdf_match.group(1).lower()
            matched_recs = [r for r in records if cited_pdf in r["filename"].lower()]
            if not matched_recs:
                return False, f"Cited document '{pdf_match.group(1)}' is absent from retrieved SOP evidence."
            candidate_records = matched_recs

        # Check revision match if Rev X.Y is specified
        rev_match = re.search(r"rev\.?\s*(\d+\.\d+)", low_cit, re.IGNORECASE)
        if rev_match:
            cited_rev = rev_match.group(1)
            rev_ok = any(cited_rev in r["revision"] for r in candidate_records)
            if not rev_ok:
                actual_revs = ", ".join(sorted(set(r["revision"] for r in candidate_records)))
                return False, f"Cited revision 'Rev {cited_rev}' contradicts retrieved revision(s): {actual_revs}."

        # Check page number match if Page X is specified
        pg_match = re.search(r"\bpages?\s+(\d+)\b", low_cit, re.IGNORECASE)
        if pg_match:
            cited_pg = pg_match.group(1)
            pg_ok = False
            for r in candidate_records:
                p_str = str(r.get("page", ""))
                if re.search(rf"\b{re.escape(cited_pg)}\b", p_str):
                    pg_ok = True
                    break
                # Also handle ranges like "1-2" or "4-5"
                rng = re.findall(r"(\d+)\s*[-–]\s*(\d+)", p_str)
                for a, b in rng:
                    if int(a) <= int(cited_pg) <= int(b):
                        pg_ok = True
                        break
            if not pg_ok:
                actual_pgs = ", ".join(sorted(set(str(r.get("page", "")) for r in candidate_records)))
                return False, f"Cited Page {cited_pg} is not supported by retrieved page(s): {actual_pgs}."

    return True, None


def verify_claim_against_evidence(
    claim: str,
    records: List[Dict[str, Any]],
    full_evidence_text: str,
) -> Dict[str, Any]:
    """
    Deterministically verifies a single factual claim against the retrieved
    evidence records and evidence corpus text.
    """
    low_claim = claim.lower()
    is_critical, critical_cat = classify_critical_claim(claim)
    inline_cits = extract_inline_citations(claim)
    cit_valid, cit_err = _check_inline_citation_validity(inline_cits, records)

    # 1. Explicit honest abstention statement
    if any(sig in low_claim for sig in ABSTENTION_SIGNALS) and not TECH_VALUE_REGEX.search(claim):
        return {
            "claim_text": claim,
            "support_status": "SUPPORTED",
            "supporting_evidence": "Honest acknowledgment of missing or unstated SOP evidence.",
            "source_filename": records[0]["filename"] if records else None,
            "revision": records[0]["revision"] if records else None,
            "section": records[0]["section"] if records else None,
            "page": records[0]["page"] if records else None,
            "evidence_classification": "DIRECTLY_STATED",
            "is_critical_technical_claim": False,
            "critical_category": None,
            "citation_valid": cit_valid,
            "citation_error": cit_err,
            "reason": "Explicitly identifies a documentation gap rather than fabricating details.",
        }

    # 2. Explicit GENERAL_CONTEXT or INFERRED marker in claim text
    explicit_gen_ctx = any(
        k in low_claim
        for k in ["general_context", "general engineering context", "general context", "standard engineering context", "not an exhaustive definition"]
    )
    explicit_inferred = any(
        k in low_claim
        for k in ["**inferred**", "inferred from", "derived from section title", "derived from documented functions", "visual diagram"]
    )

    if not records and not full_evidence_text.strip():
        if explicit_gen_ctx:
            return {
                "claim_text": claim,
                "support_status": "GENERAL_CONTEXT",
                "supporting_evidence": "Marked as general engineering context (no retrieved SOP passage).",
                "source_filename": None,
                "revision": None,
                "section": None,
                "page": None,
                "evidence_classification": "GENERAL_CONTEXT",
                "is_critical_technical_claim": is_critical,
                "critical_category": critical_cat,
                "citation_valid": cit_valid,
                "citation_error": cit_err,
                "reason": "Explicitly labeled as general context; requires SOP source for authoritative engineering sign-off.",
            }
        return {
            "claim_text": claim,
            "support_status": "UNSUPPORTED",
            "supporting_evidence": "No SOP evidence retrieved to verify this claim.",
            "source_filename": None,
            "revision": None,
            "section": None,
            "page": None,
            "evidence_classification": "UNVERIFIED",
            "is_critical_technical_claim": is_critical,
            "critical_category": critical_cat,
            "citation_valid": cit_valid,
            "citation_error": cit_err,
            "reason": "No retrieved SOP passages exist to substantiate this assertion.",
        }

    # 3. Find best-matching retrieved evidence passage via content-word overlap
    claim_no_cits = re.sub(r"\[[^\]]+\]", " ", claim)
    claim_tokens = _tokenize_content_words(claim_no_cits) or _tokenize_content_words(claim)
    best_rec: Optional[Dict[str, Any]] = None
    best_overlap_ratio = 0.0
    best_overlap_count = 0

    for rec in records:
        rec_tokens = _tokenize_content_words(rec.get("text", "") + " " + rec.get("section", ""))
        if not claim_tokens or not rec_tokens:
            continue
        inter = claim_tokens.intersection(rec_tokens)
        ratio = len(inter) / max(1, len(claim_tokens))
        if len(inter) > best_overlap_count or (len(inter) == best_overlap_count and ratio > best_overlap_ratio):
            best_overlap_count = len(inter)
            best_overlap_ratio = ratio
            best_rec = rec

    evidence_low = full_evidence_text.lower()
    ev_values = _extract_tech_values(full_evidence_text)

    # 4. Technical number / tolerance / unit check against retrieved evidence
    claim_values = _extract_tech_values(claim)
    unsupported_specs: List[str] = []
    contradicted_specs: List[str] = []

    for cv in claim_values:
        # Check if exact number(s) + unit appear in retrieved evidence
        matched_exact = False
        conflicting_ev = None
        for ev in ev_values:
            if ev["unit"] == cv["unit"]:
                if any(abs(cn - en) <= 1e-6 for cn in cv["nums"] for en in ev["nums"]):
                    matched_exact = True
                    break
                # Check if same parameter context is discussed with a different value
                shared_ctx = cv["ctx_tokens"].intersection(ev["ctx_tokens"])
                if len(shared_ctx) >= 1:
                    conflicting_ev = ev["raw"]

        if not matched_exact:
            # Also allow textual substring fallback (e.g. "0.05" appearing near unit)
            num_str = str(cv["nums"][0]).rstrip("0").rstrip(".") if "." in str(cv["nums"][0]) else str(cv["nums"][0])
            if num_str in evidence_low and cv["unit"] in evidence_low:
                # Double check if same numeric string actually exists in full_evidence_text
                if re.search(rf"\b{re.escape(str(cv['nums'][0]))}\b", evidence_low) or re.search(rf"\b{re.escape(num_str)}\b", evidence_low):
                    matched_exact = True

        if not matched_exact:
            if conflicting_ev:
                contradicted_specs.append(f"Claim states '{cv['raw']}' while retrieved evidence states '{conflicting_ev}'")
            else:
                unsupported_specs.append(cv["raw"])

    # 5. Material / grade / defense code check against retrieved evidence
    claim_codes = TECH_CODE_REGEX.findall(claim)
    unsupported_codes: List[str] = []
    for code in claim_codes:
        norm_code = re.sub(r"\s+", "", code.lower())
        norm_ev = re.sub(r"\s+", "", evidence_low)
        if norm_code not in norm_ev:
            unsupported_codes.append(code)

    # 6. Check citation errors pointing to contradicting revisions
    if contradicted_specs:
        return {
            "claim_text": claim,
            "support_status": "CONTRADICTED",
            "supporting_evidence": (best_rec["text"][:280] + "...") if best_rec and len(best_rec["text"]) > 280 else (best_rec["text"] if best_rec else ""),
            "source_filename": best_rec["filename"] if best_rec else None,
            "revision": best_rec["revision"] if best_rec else None,
            "section": best_rec["section"] if best_rec else None,
            "page": best_rec["page"] if best_rec else None,
            "evidence_classification": best_rec["evidence_status"] if best_rec else "UNVERIFIED",
            "is_critical_technical_claim": True,
            "critical_category": critical_cat or "tolerance",
            "citation_valid": cit_valid,
            "citation_error": cit_err,
            "reason": "; ".join(contradicted_specs),
        }

    if unsupported_specs or unsupported_codes:
        missing_items = unsupported_specs + unsupported_codes
        # If explicitly framed as general context without fake SOP requirement claims, allow GENERAL_CONTEXT unless asserting SOP spec
        if explicit_gen_ctx and not inline_cits and "per sop" not in low_claim and "mandatory" not in low_claim:
            return {
                "claim_text": claim,
                "support_status": "GENERAL_CONTEXT",
                "supporting_evidence": best_rec["text"][:220] if best_rec else "Labeled as general engineering context.",
                "source_filename": best_rec["filename"] if best_rec else None,
                "revision": best_rec["revision"] if best_rec else None,
                "section": best_rec["section"] if best_rec else None,
                "page": best_rec["page"] if best_rec else None,
                "evidence_classification": "GENERAL_CONTEXT",
                "is_critical_technical_claim": True,
                "critical_category": critical_cat or ("material" if unsupported_codes else "tolerance"),
                "citation_valid": cit_valid,
                "citation_error": cit_err,
                "reason": f"Explicitly marked as general context; unverified numeric/material parameters: {', '.join(missing_items)}.",
            }
        return {
            "claim_text": claim,
            "support_status": "UNSUPPORTED",
            "supporting_evidence": (best_rec["text"][:250] + "...") if best_rec and best_rec["text"] else "Not found in retrieved passages.",
            "source_filename": best_rec["filename"] if best_rec else None,
            "revision": best_rec["revision"] if best_rec else None,
            "section": best_rec["section"] if best_rec else None,
            "page": best_rec["page"] if best_rec else None,
            "evidence_classification": "UNVERIFIED",
            "is_critical_technical_claim": True,
            "critical_category": critical_cat or ("material" if unsupported_codes else "tolerance"),
            "citation_valid": cit_valid,
            "citation_error": cit_err,
            "reason": f"Technical specification/code not present in retrieved SOP evidence: {', '.join(missing_items)}.",
        }

    # Check if inline citation specifically contradicted retrieved revision/document
    if not cit_valid and cit_err and "contradicts" in cit_err.lower():
        return {
            "claim_text": claim,
            "support_status": "CONTRADICTED",
            "supporting_evidence": best_rec["text"][:240] if best_rec else "",
            "source_filename": best_rec["filename"] if best_rec else None,
            "revision": best_rec["revision"] if best_rec else None,
            "section": best_rec["section"] if best_rec else None,
            "page": best_rec["page"] if best_rec else None,
            "evidence_classification": best_rec["evidence_status"] if best_rec else "DIRECTLY_STATED",
            "is_critical_technical_claim": is_critical,
            "critical_category": critical_cat,
            "citation_valid": False,
            "citation_error": cit_err,
            "reason": cit_err,
        }

    # 7. Evidence classification honor (GENERAL_CONTEXT / INFERRED)
    if explicit_gen_ctx or (best_rec and best_rec.get("evidence_status") == "GENERAL_CONTEXT"):
        return {
            "claim_text": claim,
            "support_status": "GENERAL_CONTEXT",
            "supporting_evidence": best_rec["text"][:240] if best_rec else "General engineering explanation.",
            "source_filename": best_rec["filename"] if best_rec else None,
            "revision": best_rec["revision"] if best_rec else None,
            "section": best_rec["section"] if best_rec else None,
            "page": best_rec["page"] if best_rec else None,
            "evidence_classification": "GENERAL_CONTEXT",
            "is_critical_technical_claim": is_critical,
            "critical_category": critical_cat,
            "citation_valid": cit_valid,
            "citation_error": cit_err,
            "reason": "General engineering context explicitly separated from directly stated SOP requirements.",
        }

    if explicit_inferred or (best_rec and best_rec.get("evidence_status") == "INFERRED"):
        return {
            "claim_text": claim,
            "support_status": "INFERRED",
            "supporting_evidence": best_rec["text"][:240] if best_rec else "Inferred from section/context.",
            "source_filename": best_rec["filename"] if best_rec else None,
            "revision": best_rec["revision"] if best_rec else None,
            "section": best_rec["section"] if best_rec else None,
            "page": best_rec["page"] if best_rec else None,
            "evidence_classification": "INFERRED",
            "is_critical_technical_claim": is_critical,
            "critical_category": critical_cat,
            "citation_valid": cit_valid,
            "citation_error": cit_err,
            "reason": "Reasonable operational inference grounded in retrieved SOP context rather than verbatim text.",
        }

    # 8. Standard lexical overlap verification
    if best_rec and (best_overlap_ratio >= 0.42 or best_overlap_count >= 4):
        status = "SUPPORTED" if cit_valid else "PARTIALLY_SUPPORTED"
        reason = (
            f"Supported by retrieved SOP evidence ({best_rec['filename']}, {best_rec['revision']}, Page {best_rec['page']})."
            if cit_valid
            else f"Text aligns with evidence, but citation issue noted: {cit_err}"
        )
        return {
            "claim_text": claim,
            "support_status": status,
            "supporting_evidence": best_rec["text"][:280] + ("..." if len(best_rec["text"]) > 280 else ""),
            "source_filename": best_rec["filename"],
            "revision": best_rec["revision"],
            "section": best_rec["section"],
            "page": best_rec["page"],
            "evidence_classification": best_rec.get("evidence_status", "DIRECTLY_STATED"),
            "is_critical_technical_claim": is_critical,
            "critical_category": critical_cat,
            "citation_valid": cit_valid,
            "citation_error": cit_err,
            "reason": reason,
        }

    if best_rec and (best_overlap_ratio >= 0.22 or best_overlap_count >= 2):
        return {
            "claim_text": claim,
            "support_status": "PARTIALLY_SUPPORTED",
            "supporting_evidence": best_rec["text"][:280] + ("..." if len(best_rec["text"]) > 280 else ""),
            "source_filename": best_rec["filename"],
            "revision": best_rec["revision"],
            "section": best_rec["section"],
            "page": best_rec["page"],
            "evidence_classification": best_rec.get("evidence_status", "DIRECTLY_STATED"),
            "is_critical_technical_claim": is_critical,
            "critical_category": critical_cat,
            "citation_valid": cit_valid,
            "citation_error": cit_err,
            "reason": cit_err or "Partial lexical alignment with retrieved SOP passage; some details not verbatim.",
        }

    return {
        "claim_text": claim,
        "support_status": "UNSUPPORTED",
        "supporting_evidence": best_rec["text"][:180] if best_rec else "No matching evidence passage.",
        "source_filename": best_rec["filename"] if best_rec else None,
        "revision": best_rec["revision"] if best_rec else None,
        "section": best_rec["section"] if best_rec else None,
        "page": best_rec["page"] if best_rec else None,
        "evidence_classification": "UNVERIFIED",
        "is_critical_technical_claim": is_critical,
        "critical_category": critical_cat,
        "citation_valid": cit_valid,
        "citation_error": cit_err,
        "reason": "Claim lacks sufficient textual support in the retrieved SOP passages.",
    }


# ============================================================================
# LOCAL OLLAMA EVALUATOR & STRICT SCHEMA VALIDATION
# ============================================================================

def validate_llm_eval_schema(raw_output: Any) -> Dict[str, Any]:
    """
    Strictly validates and normalizes the JSON output produced by the local
    Ollama evaluator. Raises ValueError on malformed JSON or invalid schema.
    """
    data: Any = raw_output
    if isinstance(raw_output, str):
        text = raw_output.strip()
        if not text:
            raise ValueError("Evaluator returned empty output.")
        # Strip optional markdown json fences
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed evaluator JSON: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Evaluator output must be a JSON object.")

    required_keys = ["evidence_support", "answer_relevance", "completeness"]
    for rk in required_keys:
        if rk not in data:
            raise ValueError(f"Missing required metric '{rk}' in evaluator output.")

    validated: Dict[str, Any] = {}
    for rk in required_keys:
        val = data[rk]
        if val is None:
            validated[rk] = None
        else:
            try:
                num = float(val)
            except (TypeError, ValueError) as e:
                raise ValueError(f"Metric '{rk}' must be numeric or null, got: {val!r}") from e
            if num != num:  # NaN guard
                raise ValueError(f"Metric '{rk}' cannot be NaN.")
            validated[rk] = round(max(0.0, min(100.0, num)), 1)

    validated["unsupported_claims"] = [
        str(x).strip() for x in (data.get("unsupported_claims") or []) if str(x).strip()
    ]
    validated["contradicted_claims"] = [
        str(x).strip() for x in (data.get("contradicted_claims") or []) if str(x).strip()
    ]
    validated["missing_evidence"] = [
        str(x).strip() for x in (data.get("missing_evidence") or []) if str(x).strip()
    ]
    validated["relevance_reason"] = str(data.get("relevance_reason") or "").strip()
    validated["completeness_reason"] = str(data.get("completeness_reason") or "").strip()
    validated["evidence_reason"] = str(data.get("evidence_reason") or "").strip()

    # Optional per-claim status overrides
    raw_claims = data.get("claim_statuses") or data.get("claim_assessments") or []
    clean_claims = []
    if isinstance(raw_claims, list):
        for item in raw_claims:
            if isinstance(item, dict):
                st = str(item.get("status", "")).upper().strip()
                if st in ALLOWED_CLAIM_STATUSES:
                    clean_claims.append({
                        "claim_index": item.get("claim_index"),
                        "status": st,
                        "reason": str(item.get("reason") or "").strip(),
                    })
    validated["claim_assessments"] = clean_claims

    return validated


def _call_ollama_evaluator(
    question: str,
    answer: str,
    claims: List[str],
    records: List[Dict[str, Any]],
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    model: str = DEFAULT_EVAL_MODEL,
    timeout: float = 15.0,
) -> Any:
    """
    Executes local Ollama JSON evaluation within a bounded timeout.
    Zero external network dependencies.
    """
    if not re_engine.check_ollama_connection(endpoint, timeout=min(3.0, timeout)):
        raise ConnectionError(f"Local Ollama daemon unreachable at {endpoint}.")

    ev_snippets = []
    for r in records[:5]:
        ev_snippets.append(
            f"[{r['evidence_id']} | {r['filename']} | {r['revision']} | Page {r['page']}]\n"
            f"{r['text'][:550]}"
        )
    ev_block = "\n\n".join(ev_snippets) if ev_snippets else "NO SOP PASSAGES RETRIEVED."
    claims_block = "\n".join(f"{idx+1}. {c[:220]}" for idx, c in enumerate(claims[:8]))

    eval_prompt = (
        "You are a strict defence engineering QA auditor evaluating a RAG answer using ONLY the retrieved SOP evidence.\n"
        "Return STRICT JSON with keys:\n"
        '- "evidence_support": number 0-100 (are claims grounded in the evidence? Penalize hallucinations/contradictions)\n'
        '- "answer_relevance": number 0-100 (does the answer directly address the user question without unrelated SOP summaries?)\n'
        '- "completeness": number 0-100 (does it cover essential requested parts or honestly state gaps?)\n'
        '- "unsupported_claims": array of strings\n'
        '- "contradicted_claims": array of strings\n'
        '- "missing_evidence": array of strings\n'
        '- "evidence_reason": concise 1-sentence justification\n'
        '- "relevance_reason": concise 1-sentence justification\n'
        '- "completeness_reason": concise 1-sentence justification\n\n'
        f"USER QUESTION:\n{question}\n\n"
        f"RETRIEVED EVIDENCE:\n{ev_block}\n\n"
        f"CLAIMS TO AUDIT:\n{claims_block or answer[:600]}\n"
    )

    client = re_engine.get_ollama_client(endpoint, timeout=timeout)
    try:
        try:
            res = client.chat(
                model=model,
                messages=[{"role": "user", "content": eval_prompt}],
                format="json",
                think=False,
                options={"temperature": 0.0, "num_predict": 512, "num_ctx": 2560},
                stream=False,
            )
        except TypeError:
            res = client.chat(
                model=model,
                messages=[{"role": "user", "content": eval_prompt}],
                format="json",
                options={"temperature": 0.0, "num_predict": 512, "num_ctx": 2560},
                stream=False,
            )
    except Exception as exc:
        if isinstance(exc, TimeoutError) or "timed out" in str(exc).lower() or "timeout" in type(exc).__name__.lower():
            raise TimeoutError(f"Ollama evaluator timed out after {timeout:.1f}s.") from exc
        raise
    finally:
        inner = getattr(client, "_client", None)
        if inner is not None and hasattr(inner, "close"):
            try:
                inner.close()
            except Exception:
                pass

    msg = getattr(res, "message", None)
    if msg is not None:
        return getattr(msg, "content", "")
    if isinstance(res, dict) and "message" in res:
        return res["message"].get("content", "")
    return str(res)


# ============================================================================
# METRIC COMPUTATION & SCORE CALIBRATION
# ============================================================================

def _compute_retrieval_quality(
    question: str,
    records: List[Dict[str, Any]],
    is_insufficient: bool,
) -> Tuple[Optional[float], str]:
    """Calculates Retrieval Quality (0-100) from actual retrieved citations and scores."""
    if not records:
        return 15.0, "No supporting SOP passages were retrieved for this query."

    q_tokens = _tokenize_content_words(question)
    scores = [r["score"] for r in records if r.get("score") is not None]
    avg_sim = sum(scores) / len(scores) if scores else 0.5

    # Check lexical alignment between question and top retrieved passages
    combined_ev_tokens = set()
    for r in records[:5]:
        combined_ev_tokens.update(_tokenize_content_words(r.get("text", "") + " " + r.get("section", "")))

    q_coverage = (
        len(q_tokens.intersection(combined_ev_tokens)) / max(1, len(q_tokens))
        if q_tokens
        else 0.6
    )

    raw_score = (min(1.0, max(0.0, avg_sim)) * 55.0) + (min(1.0, q_coverage) * 45.0)
    if is_insufficient:
        raw_score = min(raw_score, 35.0)

    final_score = round(max(0.0, min(100.0, raw_score)), 1)
    just = (
        f"Evaluated {len(records)} retrieved passage(s); "
        f"question keyword coverage in context={q_coverage*100:.0f}%, "
        f"mean similarity={avg_sim:.2f}."
    )
    return final_score, just


def _compute_citation_coverage(
    verified_claims: List[Dict[str, Any]],
    records: List[Dict[str, Any]],
    answer: str,
) -> Tuple[Optional[float], str, List[str]]:
    """Calculates Citation Coverage (0-100) and collects any invalid citation errors."""
    if not verified_claims:
        return None, "NOT ASSESSED: No substantive factual claims to verify citations against.", []

    citation_errors: List[str] = []
    inline_cits_all = extract_inline_citations(answer)
    all_valid_global, err_global = _check_inline_citation_validity(inline_cits_all, records)
    if not all_valid_global and err_global:
        citation_errors.append(err_global)

    # Filter claims that require citations (exclude pure honest abstentions & general context disclaimers)
    citable_claims = [
        c for c in verified_claims
        if not (any(sig in c["claim_text"].lower() for sig in ABSTENTION_SIGNALS) and not TECH_VALUE_REGEX.search(c["claim_text"]))
    ]

    if not citable_claims:
        if records:
            return 85.0, "Abstention/context response backed by retrieved source references.", citation_errors
        return 60.0, "No verifiable factual assertions requiring SOP citations.", citation_errors

    claims_with_inline = 0
    claims_with_source_match = 0
    for c in citable_claims:
        if c.get("citation_error") and c["citation_error"] not in citation_errors:
            citation_errors.append(c["citation_error"])
        if extract_inline_citations(c["claim_text"]) and c.get("citation_valid", True):
            claims_with_inline += 1
        elif c.get("source_filename") and c.get("support_status") in {"SUPPORTED", "PARTIALLY_SUPPORTED", "INFERRED"}:
            claims_with_source_match += 0.65

    if not inline_cits_all and not records:
        return 0.0, "No SOP citations provided in answer or retrieval metadata.", citation_errors

    if not inline_cits_all:
        # Answer omitted inline bracketed citations even though passages existed
        base_ratio = (claims_with_source_match / len(citable_claims)) * 55.0
        return round(base_ratio, 1), "Answer omits inline bracketed SOP citations for factual assertions.", citation_errors

    coverage_ratio = (claims_with_inline + claims_with_source_match) / len(citable_claims)
    score = coverage_ratio * 100.0
    if citation_errors:
        score = min(score, 45.0)
        score = max(0.0, score - 15.0 * len(citation_errors))

    score = round(max(0.0, min(100.0, score)), 1)
    just = (
        f"{claims_with_inline}/{len(citable_claims)} claim(s) include valid inline citations"
        + (f"; {len(citation_errors)} citation mismatch(es) detected." if citation_errors else ".")
    )
    return score, just, citation_errors


def _compute_deterministic_relevance_and_completeness(
    question: str,
    answer: str,
    verified_claims: List[Dict[str, Any]],
    is_insufficient: bool,
) -> Tuple[float, str, float, str]:
    """
    Computes deterministic Answer Relevance and Completeness signals as a
    sanity guardrail against unrelated summaries or truncated/incomplete answers.
    """
    q_tokens = _tokenize_content_words(question)
    a_tokens = _tokenize_content_words(answer)

    if not q_tokens:
        return 80.0, "Question has no specific domain terms.", 80.0, "Standard response."

    overlap = len(q_tokens.intersection(a_tokens)) / len(q_tokens)
    has_abstention = any(sig in answer.lower() for sig in ABSTENTION_SIGNALS)

    # Relevance check: if user asks about Gun Calibration and answer discusses Hull Welding
    domain_terms_q = {w for w in q_tokens if w in {"hull", "turret", "engine", "powerpack", "torsion", "suspension", "gun", "barrel", "calibration", "boresight", "bearing", "slip", "welding", "track"}}
    domain_terms_a = {w for w in a_tokens if w in {"hull", "turret", "engine", "powerpack", "torsion", "suspension", "gun", "barrel", "calibration", "boresight", "bearing", "slip", "welding", "track"}}

    rel_score = 35.0 + (overlap * 65.0)
    if domain_terms_q and domain_terms_a and not domain_terms_q.intersection(domain_terms_a) and not has_abstention:
        # Topic mismatch: unrelated SOP summary!
        rel_score = min(rel_score, 25.0)
        rel_just = f"Answer fails to address requested domain terms ({', '.join(sorted(domain_terms_q))}) and appears off-topic."
    elif has_abstention and overlap >= 0.2:
        rel_score = max(rel_score, 75.0)
        rel_just = "Answer directly addresses the question by acknowledging missing SOP documentation."
    else:
        rel_just = f"Answer covers {overlap*100:.0f}% of core question terms."

    # Completeness check
    comp_score = 30.0 + (overlap * 55.0)
    if len(verified_claims) >= 2:
        comp_score += 12.0
    if is_insufficient or has_abstention:
        comp_score = min(comp_score, 45.0)
        comp_just = "Completeness limited by insufficient evidence in retrieved SOP passages."
    elif len(verified_claims) == 1 and len(q_tokens) >= 6:
        comp_score = min(comp_score, 60.0)
        comp_just = "Single brief claim may omit secondary aspects of the multi-part question."
    else:
        comp_just = f"Covers {len(verified_claims)} structured claim(s) addressing {overlap*100:.0f}% of query concepts."

    return (
        round(max(0.0, min(100.0, rel_score)), 1),
        rel_just,
        round(max(0.0, min(100.0, comp_score)), 1),
        comp_just,
    )


def _calculate_weighted_overall(metrics: Dict[str, Dict[str, Any]]) -> Tuple[Optional[float], Optional[str]]:
    """
    Computes weighted Overall Answer Quality Score without silently treating
    NOT ASSESSED metrics as 100.
    """
    ev_sup = metrics["evidence_support"]["score"]
    if ev_sup is None:
        return None, "Evidence Support metric could not be assessed."

    weighted_sum = 0.0
    active_weight = 0.0
    not_assessed_names = []

    for key, w in METRIC_WEIGHTS.items():
        val = metrics[key]["score"]
        if val is None:
            not_assessed_names.append(key)
        else:
            weighted_sum += val * w
            active_weight += w

    if active_weight <= 0.0:
        return None, "No metrics available to score."

    overall = round(max(0.0, min(100.0, weighted_sum / active_weight)), 1)
    note = (
        f"Weighted across assessed metrics (excluded NOT ASSESSED: {', '.join(not_assessed_names)})."
        if not_assessed_names
        else None
    )
    return overall, note


# ============================================================================
# MAIN PUBLIC ENTRY POINT: evaluate_rag_answer
# ============================================================================

def evaluate_rag_answer(
    question: str,
    answer: str,
    citations: Optional[List[Dict[str, Any]]] = None,
    info: Optional[Dict[str, Any]] = None,
    use_llm: bool = True,
    llm_timeout: float = 15.0,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    model: str = DEFAULT_EVAL_MODEL,
    llm_eval_fn: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """
    Assesses the evidence support, relevance, completeness, citation coverage,
    and retrieval quality of a single RAG assistant response.

    Never mutates or discards the original assistant answer on error.
    """
    t0 = time.perf_counter()
    now_dt = datetime.now().astimezone()
    info = info or {}
    citations = citations or []

    def _empty_metrics(reason: str) -> Dict[str, Dict[str, Any]]:
        return {
            k: {"score": None, "status": "NOT ASSESSED", "justification": reason}
            for k in METRIC_WEIGHTS.keys()
        }

    # 1. Handle conversational greetings cleanly
    if info.get("is_greeting"):
        dur = round(time.perf_counter() - t0, 3)
        return {
            "assessment_version": ASSESSMENT_VERSION,
            "evaluator_model": model,
            "assessment_status": "skipped",
            "evaluation_succeeded": True,
            "assessment_skipped": True,
            "skip_reason": "Conversational greeting — no SOP claims to verify.",
            "error_message": None,
            "display_message": None,
            "overall_score": None,
            "quality_category": "NOT ASSESSED",
            "warning_label": "HIGH EVIDENCE SUPPORT",
            "metrics": _empty_metrics("NOT ASSESSED: Conversational greeting contains no technical SOP claims."),
            "claims": [],
            "unsupported_claims_count": 0,
            "contradicted_claims_count": 0,
            "critical_warnings": [],
            "missing_evidence": [],
            "human_verification_recommended": False,
            "recommendation": "No technical verification needed for conversational greeting.",
            "disclaimer": "Automated evidence-based quality estimate; not a statistical probability that the answer is correct.",
            "evaluated_at": now_dt.isoformat(),
            "evaluation_duration_sec": dur,
        }

    is_cancelled = bool(info.get("is_cancelled", False))
    claims_text = extract_factual_claims(answer)

    # 2. Cancelled with zero substantive claims -> skip cleanly
    if is_cancelled and not claims_text:
        dur = round(time.perf_counter() - t0, 3)
        return {
            "assessment_version": ASSESSMENT_VERSION,
            "evaluator_model": model,
            "assessment_status": "skipped",
            "evaluation_succeeded": True,
            "assessment_skipped": True,
            "skip_reason": "Generation cancelled by user before substantive output.",
            "error_message": None,
            "display_message": None,
            "overall_score": None,
            "quality_category": "NOT ASSESSED",
            "warning_label": "INSUFFICIENT EVIDENCE",
            "metrics": _empty_metrics("NOT ASSESSED: Stream cancelled before factual output was generated."),
            "claims": [],
            "unsupported_claims_count": 0,
            "contradicted_claims_count": 0,
            "critical_warnings": ["Generation was cancelled before completion; partial response may be incomplete."],
            "missing_evidence": [],
            "human_verification_recommended": True,
            "recommendation": "Re-submit query or review SOP directly since generation was cancelled.",
            "disclaimer": "Automated evidence-based quality estimate; not a statistical probability that the answer is correct.",
            "evaluated_at": now_dt.isoformat(),
            "evaluation_duration_sec": dur,
        }

    # 3. Collect ONLY retrieved evidence records & verify every claim deterministically
    records, full_evidence_text = _collect_evidence_records(citations, info=info)
    verified_claims = [
        verify_claim_against_evidence(c, records, full_evidence_text)
        for c in claims_text
    ]

    # 4. Run optional local Ollama LLM assessment if requested (skip heavy LLM when cancelled mid-stream)
    llm_result: Optional[Dict[str, Any]] = None
    effective_use_llm = use_llm and not is_cancelled

    if effective_use_llm:
        try:
            if llm_eval_fn is not None:
                raw_llm_out = llm_eval_fn(question, answer, claims_text, records)
            else:
                raw_llm_out = _call_ollama_evaluator(
                    question=question,
                    answer=answer,
                    claims=claims_text,
                    records=records,
                    endpoint=endpoint,
                    model=model,
                    timeout=llm_timeout,
                )
            llm_result = validate_llm_eval_schema(raw_llm_out)
        except Exception as eval_err:
            logger.warning(f"Local RAG evaluation failed safely: {eval_err}")
            dur = round(time.perf_counter() - t0, 3)
            return {
                "assessment_version": ASSESSMENT_VERSION,
                "evaluator_model": model,
                "assessment_status": "unavailable",
                "evaluation_succeeded": False,
                "assessment_skipped": False,
                "skip_reason": None,
                "error_message": str(eval_err),
                "display_message": "Answer quality assessment unavailable.",
                "overall_score": None,
                "quality_category": "NOT ASSESSED",
                "warning_label": "ASSESSMENT UNAVAILABLE",
                "metrics": _empty_metrics(f"NOT ASSESSED: Evaluator unavailable ({eval_err})."),
                "claims": verified_claims,
                "unsupported_claims_count": sum(1 for c in verified_claims if c["support_status"] == "UNSUPPORTED"),
                "contradicted_claims_count": sum(1 for c in verified_claims if c["support_status"] == "CONTRADICTED"),
                "critical_warnings": ["Automated LLM evaluator unavailable; answer preserved unedited."],
                "missing_evidence": [],
                "human_verification_recommended": True,
                "recommendation": "Answer quality assessment unavailable. Verify specifications directly against cited SOPs.",
                "disclaimer": "Automated evidence-based quality estimate; not a statistical probability that the answer is correct.",
                "evaluated_at": now_dt.isoformat(),
                "evaluation_duration_sec": dur,
            }

    # 5. Merge deterministic claim audits with LLM claim-level tags (deterministic safety always wins)
    if llm_result and llm_result.get("claim_assessments"):
        for ca in llm_result["claim_assessments"]:
            idx = ca.get("claim_index")
            if isinstance(idx, int) and 1 <= idx <= len(verified_claims):
                vc = verified_claims[idx - 1]
                # Never downgrade deterministic CONTRADICTED or critical UNSUPPORTED
                if vc["support_status"] not in {"CONTRADICTED", "UNSUPPORTED"}:
                    if ca["status"] in {"CONTRADICTED", "UNSUPPORTED", "PARTIALLY_SUPPORTED"}:
                        vc["support_status"] = ca["status"]
                        if ca.get("reason"):
                            vc["reason"] = f"{vc['reason']} (Auditor note: {ca['reason']})"

    # 6. Calculate deterministic metrics & critical safety checks
    is_insufficient = bool(info.get("is_insufficient")) or (
        not records and not any(c["support_status"] == "GENERAL_CONTEXT" for c in verified_claims)
    ) or (
        any(sig in answer.lower() for sig in ABSTENTION_SIGNALS) and not records
    )

    ret_score, ret_just = _compute_retrieval_quality(question, records, is_insufficient)
    cit_score, cit_just, cit_errors = _compute_citation_coverage(verified_claims, records, answer)
    det_rel, det_rel_just, det_comp, det_comp_just = _compute_deterministic_relevance_and_completeness(
        question, answer, verified_claims, is_insufficient
    )

    # Calculate deterministic Evidence Support score
    if not verified_claims:
        det_ev_sup = 20.0 if is_insufficient else 50.0
        det_ev_just = "No extractable factual claims found to verify."
    else:
        status_points = {
            "SUPPORTED": 100.0,
            "INFERRED": 78.0,
            "GENERAL_CONTEXT": 72.0,
            "PARTIALLY_SUPPORTED": 58.0,
            "UNSUPPORTED": 12.0,
            "CONTRADICTED": 0.0,
        }
        pts = [status_points.get(c["support_status"], 50.0) for c in verified_claims]
        det_ev_sup = round(sum(pts) / len(pts), 1)

    contradicted_claims = [c for c in verified_claims if c["support_status"] == "CONTRADICTED"]
    unsupported_claims = [c for c in verified_claims if c["support_status"] == "UNSUPPORTED"]
    critical_bad = [
        c for c in (contradicted_claims + unsupported_claims)
        if c.get("is_critical_technical_claim")
    ]
    gen_context_claims = [c for c in verified_claims if c["support_status"] == "GENERAL_CONTEXT"]

    # Fuse LLM estimates (if enabled & succeeded) with deterministic safety guardrails
    if llm_result:
        llm_ev = llm_result["evidence_support"]
        ev_score = det_ev_sup if llm_ev is None else round(0.60 * det_ev_sup + 0.40 * llm_ev, 1)
        # Never let optimistic LLM elevate score above deterministic evidence reality when issues exist
        if contradicted_claims or unsupported_claims:
            ev_score = min(ev_score, det_ev_sup + 8.0)

        llm_rel = llm_result["answer_relevance"]
        rel_score = det_rel if llm_rel is None else round(0.45 * det_rel + 0.55 * llm_rel, 1)
        if det_rel <= 35.0:
            # Topic mismatch guardrail
            rel_score = min(rel_score, det_rel + 5.0)
        rel_just = f"{det_rel_just} {llm_result.get('relevance_reason', '')}".strip()

        llm_comp = llm_result["completeness"]
        comp_score = det_comp if llm_comp is None else round(0.45 * det_comp + 0.55 * llm_comp, 1)
        if is_insufficient:
            comp_score = min(comp_score, 50.0)
        comp_just = f"{det_comp_just} {llm_result.get('completeness_reason', '')}".strip()
    else:
        ev_score = det_ev_sup
        rel_score = det_rel
        rel_just = det_rel_just
        comp_score = det_comp
        comp_just = det_comp_just

    # Build critical warnings list
    critical_warnings: List[str] = []
    for cc in contradicted_claims:
        critical_warnings.append(
            f"CONTRADICTORY TECHNICAL CLAIM ({cc.get('critical_category') or 'spec'}): {cc['claim_text'][:120]} — {cc['reason']}"
        )
    for uc in unsupported_claims:
        if uc.get("is_critical_technical_claim"):
            critical_warnings.append(
                f"CRITICAL UNSUPPORTED CLAIM ({uc.get('critical_category') or 'spec'}): {uc['claim_text'][:120]} — {uc['reason']}"
            )
    for ce in cit_errors:
        critical_warnings.append(f"CITATION INTEGRITY ERROR: {ce}")

    # Enforce strict hard-caps so average scores cannot hide critical technical errors
    if contradicted_claims:
        ev_score = min(ev_score, 35.0)
    elif critical_bad:
        ev_score = min(ev_score, 48.0)
    elif unsupported_claims:
        ev_score = min(ev_score, 62.0)

    ev_just = (
        f"Audited {len(verified_claims)} claim(s): "
        f"{sum(1 for c in verified_claims if c['support_status']=='SUPPORTED')} supported, "
        f"{sum(1 for c in verified_claims if c['support_status']=='PARTIALLY_SUPPORTED')} partial, "
        f"{len(unsupported_claims)} unsupported, {len(contradicted_claims)} contradicted, "
        f"{len(gen_context_claims)} general context."
    )
    if llm_result and llm_result.get("evidence_reason"):
        ev_just = f"{ev_just} {llm_result['evidence_reason']}"

    metrics = {
        "evidence_support": {"score": round(ev_score, 1), "status": "ASSESSED", "justification": ev_just},
        "answer_relevance": {"score": round(rel_score, 1), "status": "ASSESSED", "justification": rel_just},
        "completeness": {"score": round(comp_score, 1), "status": "ASSESSED", "justification": comp_just},
        "citation_coverage": {
            "score": cit_score,
            "status": "ASSESSED" if cit_score is not None else "NOT ASSESSED",
            "justification": cit_just,
        },
        "retrieval_quality": {"score": ret_score, "status": "ASSESSED", "justification": ret_just},
    }

    overall_score, overall_note = _calculate_weighted_overall(metrics)

    # Strict overall score capping rules for critical safety errors or insufficient evidence
    if overall_score is not None:
        if contradicted_claims:
            overall_score = min(overall_score, 49.0)
        elif critical_bad:
            overall_score = min(overall_score, 64.0)
        elif unsupported_claims:
            overall_score = min(overall_score, 72.0)
        elif is_insufficient:
            overall_score = min(overall_score, 68.0)
        elif cit_errors:
            overall_score = min(overall_score, 74.0)
        overall_score = round(overall_score, 1)

    quality_category = get_quality_category(overall_score)

    # Determine warning label strictly
    if contradicted_claims:
        warning_label = "CONTRADICTORY EVIDENCE"
    elif unsupported_claims or critical_bad:
        warning_label = "UNSUPPORTED CLAIMS DETECTED"
    elif is_insufficient:
        warning_label = "INSUFFICIENT EVIDENCE"
    elif cit_errors or (overall_score is not None and overall_score < 75.0) or any(
        c["support_status"] in {"PARTIALLY_SUPPORTED", "GENERAL_CONTEXT"} for c in verified_claims
    ):
        if overall_score is not None and overall_score >= 85.0 and not cit_errors and not unsupported_claims and not contradicted_claims:
            warning_label = "HIGH EVIDENCE SUPPORT"
        else:
            warning_label = "PARTIAL EVIDENCE"
    elif overall_score is not None and overall_score >= 75.0:
        warning_label = "HIGH EVIDENCE SUPPORT"
    else:
        warning_label = "PARTIAL EVIDENCE"

    # Never display HIGH EVIDENCE SUPPORT if critical claim is unsupported/contradicted or evidence insufficient
    if (critical_bad or contradicted_claims or unsupported_claims or is_insufficient or cit_errors) and warning_label == "HIGH EVIDENCE SUPPORT":
        warning_label = "UNSUPPORTED CLAIMS DETECTED" if (unsupported_claims or critical_bad) else "PARTIAL EVIDENCE"

    missing_evidence = list(llm_result.get("missing_evidence", [])) if llm_result else []
    if is_insufficient and not missing_evidence:
        missing_evidence.append("Retrieved SOP passages lacked direct evidence for key aspects of the inquiry.")
    if is_cancelled:
        critical_warnings.append("Partial response evaluated deterministically after user Stop cancellation.")

    human_verify = bool(contradicted_claims or critical_bad or unsupported_claims or is_insufficient or cit_errors or is_cancelled)
    if human_verify:
        recommendation = (
            "Human verification against official controlled SOP PDFs is recommended before acting on flagged parameters."
        )
    else:
        recommendation = "Claims align with cited SOP evidence; always verify revision stamps during physical shop-floor sign-off."

    if overall_note:
        recommendation = f"{recommendation} ({overall_note})"

    dur = round(time.perf_counter() - t0, 3)
    return {
        "assessment_version": ASSESSMENT_VERSION,
        "evaluator_model": model if effective_use_llm else "deterministic-auditor",
        "assessment_status": "completed",
        "evaluation_succeeded": True,
        "assessment_skipped": False,
        "skip_reason": None,
        "error_message": None,
        "display_message": None,
        "overall_score": overall_score,
        "quality_category": quality_category,
        "warning_label": warning_label,
        "metrics": metrics,
        "claims": verified_claims,
        "unsupported_claims_count": len(unsupported_claims),
        "contradicted_claims_count": len(contradicted_claims),
        "critical_warnings": critical_warnings,
        "missing_evidence": missing_evidence,
        "human_verification_recommended": human_verify,
        "recommendation": recommendation,
        "disclaimer": "Automated evidence-based quality estimate; not a statistical probability that the answer is correct.",
        "evaluated_at": now_dt.isoformat(),
        "evaluation_duration_sec": dur,
    }
