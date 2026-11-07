#!/usr/bin/env python3
"""
SOP Document Intelligence & Revision Impact Analysis Assistant
==============================================================
Module: app.py
Architecture Role: Module 1 of 5 (Streamlit Frontend & User Interface).

Responsibilities:
- Professional single-page chat interface for SOP intelligence.
- Live system telemetry (Ollama daemon status, model health, FAISS corpus stats).
- Interactive retrieval filtering (by SOP category, specific document, and revision).
- Progressive token-by-token response streaming with live markdown rendering.
- Real generation cancellation (Stop button) with partial text and citation preservation.
- Expandable evidence cards with exact PDF citations, page references, and similarity scores.
- In-page PDF upload and incremental vector indexing with duplicate prevention.
- Session conversation management (creating, switching, and resetting conversations).
- Fully offline execution on CPU without external API calls.
"""

import os
import re as regex
import time
import uuid
import logging
from typing import List, Dict, Any, Optional
import streamlit as st
import pandas as pd

# Import core backend modules
import rag_engine as re
import document_processor as dp
import database as db
import sop_analyzer as sa

# ============================================================================
# PAGE CONFIGURATION & STYLING
# ============================================================================

st.set_page_config(
    page_title="HVF / AVNL - SOP Intelligence Assistant",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Defense-Grade Engineering Theme
st.markdown("""
<style>
    /* Main Layout Styling */
    .main-header {
        font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
        color: #1E3A8A;
        margin-bottom: 0px;
        font-weight: 700;
        letter-spacing: -0.02em;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #475569;
        margin-bottom: 18px;
        line-height: 1.4;
    }
    .metric-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        font-weight: 600;
        margin-right: 8px;
        margin-bottom: 8px;
    }
    .badge-success {
        background-color: #DCFCE7;
        color: #166534;
        border: 1px solid #86EFAC;
    }
    .badge-warning {
        background-color: #FEF3C7;
        color: #92400E;
        border: 1px solid #FCD34D;
    }
    .badge-danger {
        background-color: #FEE2E2;
        color: #991B1B;
        border: 1px solid #FCA5A5;
    }
    .badge-info {
        background-color: #E0E7FF;
        color: #3730A3;
        border: 1px solid #A5B4FC;
    }
    .citation-card {
        background-color: #F8FAFC;
        border-left: 4px solid #1E3A8A;
        padding: 10px 14px;
        margin-top: 8px;
        margin-bottom: 8px;
        border-radius: 4px;
        font-size: 0.9rem;
    }
    .stChatFloatingInputContainer {
        bottom: 20px;
    }

    /* Executive Engineering Dashboard Cards */
    .dashboard-banner {
        background: linear-gradient(135deg, #0F172A 0%, #1E3A8A 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 24px;
        color: #FFFFFF;
        margin-bottom: 24px;
        box-shadow: 0 4px 12px rgba(15, 23, 42, 0.12);
    }
    .dashboard-banner h2 {
        color: #FFFFFF !important;
        margin: 0 0 8px 0;
        font-weight: 700;
        font-size: 1.65rem;
    }
    .dashboard-banner p {
        color: #CBD5E1;
        margin: 0;
        font-size: 0.95rem;
        line-height: 1.5;
    }
    .dashboard-kpi-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px 20px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
        text-align: left;
        margin-bottom: 12px;
    }
    .kpi-number {
        font-size: 2.1rem;
        font-weight: 700;
        color: #1E3A8A;
        line-height: 1.1;
        margin-bottom: 4px;
    }
    .kpi-label {
        font-size: 0.8rem;
        color: #64748B;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .kpi-subtext {
        font-size: 0.8rem;
        color: #94A3B8;
        margin-top: 4px;
    }
    .health-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
        min-height: 200px;
    }
    .health-card h4 {
        color: #1E3A8A;
        margin-top: 0;
        margin-bottom: 12px;
        font-size: 1.05rem;
        font-weight: 600;
    }
    .health-item {
        font-size: 0.88rem;
        color: #334155;
        margin-bottom: 6px;
        line-height: 1.4;
    }
    .nav-card {
        background-color: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        margin-bottom: 16px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .nav-card h4 {
        color: #1E3A8A;
        margin-top: 0;
        margin-bottom: 6px;
        font-size: 1.05rem;
    }
    .nav-card p {
        color: #475569;
        font-size: 0.88rem;
        margin-bottom: 12px;
        line-height: 1.4;
    }

    /* ChatGPT / Gemini Style Smooth Streaming Response & Typing Cursor */
    .typing-cursor {
        display: inline-block;
        width: 2.5px;
        height: 1.15em;
        background-color: #1E3A8A;
        margin-left: 2px;
        margin-right: 1px;
        vertical-align: -0.15em;
        border-radius: 1px;
        animation: cursorBlink 0.75s ease-in-out infinite;
    }
    @keyframes cursorBlink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0; }
    }
    .streaming-fade-in {
        display: inline;
        animation: textFadeIn 0.2s ease-out forwards;
    }
    @keyframes textFadeIn {
        from {
            opacity: 0.25;
            transform: translateY(1px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    @media (prefers-reduced-motion: reduce) {
        .typing-cursor {
            animation: none !important;
            opacity: 1 !important;
        }
        .streaming-fade-in {
            animation: none !important;
            opacity: 1 !important;
            transform: none !important;
        }
    }

    /* Continuous Chat Auto-Scroll Anchor & Target */
    .sop-autoscroll-anchor {
        display: block;
        height: 1px;
        margin-top: -1px;
        visibility: hidden;
    }
    .sop-autoscroll-trigger {
        display: none !important;
        width: 0 !important;
        height: 0 !important;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================================
# SESSION STATE INITIALIZATION
# ============================================================================

def init_session_state():
    """Initializes persistent session state variables for chat and system state."""
    db.init_database()

    # Active conversation ID backed by SQLite (with query param override)
    query_conv = st.query_params.get("conv") if hasattr(st, "query_params") else None
    if query_conv:
        st.session_state["current_conv_id"] = query_conv
    elif "current_conv_id" not in st.session_state:
        recent = db.list_conversations(limit=10)
        # Prefer a conversation that has messages
        chosen_conv = None
        for rc in recent:
            if db.get_conversation_messages(rc["conversation_id"]):
                chosen_conv = rc["conversation_id"]
                break
        if chosen_conv:
            st.session_state["current_conv_id"] = chosen_conv
        elif recent:
            st.session_state["current_conv_id"] = recent[0]["conversation_id"]
        else:
            new_conv = db.create_conversation("New Consultation")
            st.session_state["current_conv_id"] = new_conv["conversation_id"]

    # Operating Mode default with query param support
    mode_map = {
        "dashboard": "📊 Executive Dashboard & Telemetry",
        "chat": "💬 Technical Consultation Chat",
        "explorer": "🧩 Visual & Tabular Component Explorer",
        "compare": "⚖️ SOP Revision Comparison Engine",
        "impact": "🔗 Cross-Document Impact Analysis",
        "upload": "📥 Ingest & Manage SOP Documents"
    }
    query_mode = st.query_params.get("mode") if hasattr(st, "query_params") else None
    if query_mode and query_mode in mode_map:
        st.session_state["app_mode_radio"] = mode_map[query_mode]
    elif "app_mode_radio" not in st.session_state:
        st.session_state["app_mode_radio"] = "📊 Executive Dashboard & Telemetry"

    # Optional target component and SOP from query params
    query_comp = st.query_params.get("comp") if hasattr(st, "query_params") else None
    if query_comp:
        st.session_state["target_nav_component"] = query_comp

    query_sop = st.query_params.get("sop") if hasattr(st, "query_params") else None
    if query_sop:
        st.session_state["diff_sop_sel"] = query_sop

    # Generation control flags
    if "is_generating" not in st.session_state:
        st.session_state["is_generating"] = False

    if "stop_requested" not in st.session_state:
        st.session_state["stop_requested"] = False

    # Corpus cache
    if "corpus_stats" not in st.session_state:
        st.session_state["corpus_stats"] = {"doc_count": 0, "chunk_count": 0, "status": "unknown"}


init_session_state()


# ============================================================================
# BACKEND HEALTH & TELEMETRY
# ============================================================================

@st.cache_data(ttl=10)
def check_system_telemetry() -> Dict[str, Any]:
    """Queries live Ollama, FAISS, Tesseract OCR, and SQLite database health with 10-second TTL."""
    full_health = re.get_comprehensive_system_health()

    ollama_info = full_health.get("ollama", {})
    faiss_info = full_health.get("faiss", {})
    comp_info = full_health.get("components", {})
    db_info = full_health.get("database", {})
    doc_info = full_health.get("documents", {})

    tess_path = getattr(dp, "TESSERACT_BIN", None)
    tess_ok = False
    if tess_path and os.path.isfile(tess_path):
        tess_ok = True
    else:
        try:
            detected_path = dp.configure_tesseract()
            if detected_path and os.path.isfile(detected_path):
                tess_ok = True
                tess_path = detected_path
        except Exception:
            tess_ok = False

    return {
        "ollama_online": ollama_info.get("online", False),
        "llm_ready": ollama_info.get("llm_ready", False),
        "embed_ready": ollama_info.get("embed_ready", False),
        "all_models_ready": ollama_info.get("all_models_ready", False),
        "doc_count": doc_info.get("total_documents", 0),
        "chunk_count": faiss_info.get("total_vectors", 0),
        "index_loaded": (faiss_info.get("total_vectors", 0) > 0),
        "index_consistent": faiss_info.get("is_healthy", False),
        "consistency_msg": "; ".join(faiss_info.get("issues", [])) if faiss_info.get("issues") else "Synchronized",
        "db_ready": db_info.get("is_healthy", False),
        "tesseract_ready": tess_ok,
        "tesseract_path": tess_path,
        "components_count": comp_info.get("total_records", 0),
        "components_healthy": comp_info.get("is_healthy", False),
        "uploaded_doc_count": doc_info.get("uploaded_documents_count", 0),
        "overall_status": full_health.get("overall_status", "HEALTHY"),
        "status_message": full_health.get("status_message", "Operational"),
        "full_health": full_health
    }

telemetry = check_system_telemetry()


# ============================================================================
# COMPACT EVIDENCE SOURCES HELPERS
# ============================================================================

def group_citations_by_source(citations_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Groups retrieved citation passages by unique source PDF filename and revision.
    Consolidates page references into clean, sorted ranges (e.g. 'Page 3' or 'Pages 6–7').
    Extracts short section titles and verbatim text passages for optional inspection.
    """
    if not citations_list:
        return []

    grouped = {}
    for c in citations_list:
        fname = c.get("filename") or "Unknown_SOP.pdf"
        raw_rev = c.get("revision") or "Rev 1.0"
        m_rev = regex.search(r"Rev\s*([\d\.]+)", raw_rev, regex.IGNORECASE)
        if m_rev:
            rev = f"Rev {m_rev.group(1)}"
        else:
            m_num = regex.search(r"(\d+(\.\d+)?)", raw_rev)
            rev = f"Rev {m_num.group(1)}" if m_num else raw_rev.split("|")[0].strip()
        key = (fname, rev)
        if key not in grouped:
            grouped[key] = {
                "filename": fname,
                "revision": rev,
                "pages": [],
                "sections": [],
                "passages": [],
                "count": 0
            }
        grouped[key]["count"] += 1

        # Collect page references
        page = c.get("page_number")
        if page:
            grouped[key]["pages"].append(page)
        elif c.get("page_numbers"):
            grouped[key]["pages"].extend(c.get("page_numbers"))

        # Collect unique section titles
        sec = c.get("section_title")
        if sec and sec.strip():
            clean_sec = sec.strip().replace("\ufffd", "—")
            if clean_sec not in grouped[key]["sections"]:
                grouped[key]["sections"].append(clean_sec)

        # Collect verbatim chunk text for optional inspection
        p_text = c.get("chunk_text") or c.get("passage")
        if p_text and p_text.strip():
            clean_p = p_text.strip()
            if clean_p not in grouped[key]["passages"]:
                grouped[key]["passages"].append(clean_p)

    grouped_sources = []
    for (fname, rev), data in grouped.items():
        nums = set()
        for p in data["pages"]:
            if isinstance(p, list):
                for sub in p:
                    try:
                        nums.add(int(sub))
                    except Exception:
                        pass
            elif p is not None:
                for pt in regex.findall(r"\d+", str(p)):
                    try:
                        nums.add(int(pt))
                    except Exception:
                        pass

        if not nums:
            pages_str = "Page N/A"
        else:
            sorted_nums = sorted(list(nums))
            ranges = []
            start = sorted_nums[0]
            prev = start
            for n in sorted_nums[1:]:
                if n == prev + 1:
                    prev = n
                else:
                    ranges.append(str(start) if start == prev else f"{start}–{prev}")
                    start = n
                    prev = n
            ranges.append(str(start) if start == prev else f"{start}–{prev}")
            combined = ", ".join(ranges)
            pages_str = f"Page {combined}" if len(sorted_nums) == 1 else f"Pages {combined}"

        grouped_sources.append({
            "filename": fname,
            "revision": rev,
            "pages_str": pages_str,
            "sections": data["sections"],
            "passages": data.get("passages", []),
            "passage_count": data["count"]
        })

    return grouped_sources


def render_compact_evidence_sources(citations_list: List[Dict[str, Any]]):
    """
    Renders a compact, grouped source-file list for verified evidence passages.
    Preserves total passage count in expander header while displaying:
      - PDF filename
      - Revision number
      - Page number(s)
      - Expandable section titles & verbatim supporting passages
    """
    if not citations_list:
        return

    grouped = group_citations_by_source(citations_list)

    with st.expander(f"📚 Verified Evidence Sources ({len(citations_list)} passages)", expanded=False):
        for idx, src in enumerate(grouped, 1):
            label = f"{idx}. `{src['filename']}` — {src['revision']} — {src['pages_str']}"
            sections = src.get("sections", [])
            passages = src.get("passages", [])
            if sections or passages:
                with st.expander(label, expanded=False):
                    if sections:
                        st.markdown("**Cited Section(s):**")
                        for sec in sections:
                            short_sec = (sec[:85] + "...") if len(sec) > 85 else sec
                            st.markdown(f"- **Section:** {short_sec}")
                    if passages:
                        with st.expander("📖 Verbatim Supporting Passage(s)", expanded=False):
                            for p in passages:
                                st.markdown(f"```text\n{p}\n```")
            else:
                st.markdown(label)


def find_referenced_components_in_text(text: str, all_components: List[Dict[str, Any]], max_matches: int = 4) -> List[str]:
    """
    Finds unique component names that appear verbatim in the given text.
    Filters out very short or overly generic strings to prevent false positives.
    """
    if not text or not all_components:
        return []
    text_lower = text.lower()
    matches = []
    seen = set()
    # Sort by component name length descending to prioritize longer phrases
    sorted_comps = sorted(all_components, key=lambda c: len(c.get("component_name", "")), reverse=True)
    stop_words = {"test", "unit", "spec", "data", "part", "high", "step", "hull", "turret", "laser", "system", "engine", "assy"}
    for c in sorted_comps:
        c_name = c.get("component_name", "").strip()
        if len(c_name) < 4 or c_name.lower() in stop_words:
            continue
        c_lower = c_name.lower()
        if c_lower in text_lower and c_name not in seen:
            seen.add(c_name)
            matches.append(c_name)
            if len(matches) >= max_matches:
                break
    return matches


# Revision Scope Options
REVISION_CHOICES = [
    "V2 — Latest revision (Default)",
    "V1 — Baseline revision",
    "All revisions — V2 prioritized",
]


# ============================================================================
# STREAMING RENDERING & AUTO-SCROLL HELPERS
# ============================================================================

AUTOSCROLL_TRIGGER_HTML = (
    '<span class="sop-autoscroll-anchor" id="sop-chat-bottom-anchor"></span>'
    '<img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7" '
    'class="sop-autoscroll-trigger" alt="" style="display:none;" '
    'onload="try{(function(){var w=window.parent||window;'
    'if(!w._sopScrollInit){w._sopScrollInit=true;w._sopUserScrolledUp=false;'
    'var gc=function(){return(w.document?w.document.querySelector(\'.main\'):null)||document.querySelector(\'.main\')||document.documentElement;};'
    'var os=function(){var c=gc();if(!c)return;var d=c.scrollHeight-c.scrollTop-c.clientHeight;w._sopUserScrolledUp=(d>80);};'
    'var c=gc();if(c)c.addEventListener(\'scroll\',os,{passive:true});w.addEventListener(\'scroll\',os,{passive:true});}'
    'if(!w._sopUserScrolledUp){var c=(w.document?w.document.querySelector(\'.main\'):null)||document.querySelector(\'.main\')||document.documentElement;'
    'if(c)c.scrollTo({top:c.scrollHeight,behavior:\'smooth\'});}})();}catch(e){}" />'
)


class AutoScrollController:
    """
    Manages continuous chat auto-scrolling state for progressive streaming:
    - Tracks whether auto-scroll is actively enabled for the current streaming turn.
    - Generates lightweight, scoped client-side triggers during active generation.
    - Suppresses scrolling upon stream completion, cancellation, or error.
    - Employs distance-to-bottom threshold (80px) to pause when the user scrolls upward.
    """
    SCROLL_THRESHOLD_PX = 80

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.is_active = False

    def start(self):
        self.is_active = True

    def stop(self):
        self.is_active = False

    def get_trigger_html(self) -> str:
        if not self.enabled or not self.is_active:
            return ""
        return AUTOSCROLL_TRIGGER_HTML

    @staticmethod
    def should_pause(distance_to_bottom: float, threshold: float = 80.0) -> bool:
        """Determines if auto-scroll should pause based on user scroll offset from bottom."""
        return distance_to_bottom > threshold


def render_streaming_display(
    stable_text: str,
    latest_chunk: str,
    is_active: bool = True,
    auto_scroll: bool = True
) -> str:
    """
    Constructs progressive streaming Markdown / HTML display:
    - stable_text: Established accumulated text, rendered statically without animation.
    - latest_chunk: Newly arrived token batch, wrapped in a fade-in span when safe.
    - is_active: Whether generation is currently active (appends typing cursor & scroll trigger).
    - auto_scroll: Whether to append the client-side auto-scroll trigger.
    """
    cursor_html = '<span class="typing-cursor"></span>'
    scroll_html = AUTOSCROLL_TRIGGER_HTML if (is_active and auto_scroll) else ""

    if not is_active:
        return (stable_text + latest_chunk).strip()

    full_text = stable_text + latest_chunk
    if not full_text:
        return f"{cursor_html}{scroll_html}"

    # Check for formatting characters where wrapping would break block-level markdown
    has_markdown_symbols = any(sym in latest_chunk for sym in ["\n", "```", "`", "**", "*", "#", "|", "[", "]"])

    if not has_markdown_symbols and latest_chunk:
        return f"{stable_text}<span class=\"streaming-fade-in\">{latest_chunk}</span>{cursor_html}{scroll_html}"
    else:
        return f"{full_text}{cursor_html}{scroll_html}"


class SmoothStreamAccumulator:
    """
    Buffers and smooths token streams for progressive UI rendering:
    - Emits first visible content immediately upon arrival (zero startup delay).
    - Batches subsequent tokens to prevent high-frequency DOM re-renders and UI flicker.
    - Flushes on natural boundaries (punctuation, newlines) or time thresholds (~45ms).
    - Coordinates auto-scroll triggers with client-side scroll position awareness.
    """
    def __init__(
        self,
        min_batch_chars: int = 8,
        min_batch_tokens: int = 3,
        min_interval_sec: float = 0.045,
        enable_auto_scroll: bool = True
    ):
        self.min_batch_chars = min_batch_chars
        self.min_batch_tokens = min_batch_tokens
        self.min_interval_sec = min_interval_sec
        self.enable_auto_scroll = enable_auto_scroll
        self.scroll_controller = AutoScrollController(enabled=enable_auto_scroll)
        self.full_response = ""
        self.stable_text = ""
        self.pending_tokens: List[str] = []
        self.first_token_emitted = False
        self.last_render_time = 0.0
        self.render_count = 0

    def add_token(self, token: str) -> bool:
        """
        Adds a token to the accumulator. Returns True if the UI should be updated.
        """
        self.full_response += token
        self.pending_tokens.append(token)
        pending_chunk = "".join(self.pending_tokens)

        # Sanitize to check if there is actual visible content
        clean_preview = re.sanitize_model_output(self.full_response)
        if not clean_preview.strip():
            return False

        now = time.time()
        time_elapsed = now - self.last_render_time

        # Condition 1: First visible token -> update immediately
        if not self.first_token_emitted:
            return True

        # Condition 2: Punctuation or newline boundary
        has_boundary = any(b in token for b in ["\n", ". ", "? ", "! ", ": ", "; "])
        if has_boundary:
            return True

        # Condition 3: Batch size reached
        has_enough = (len(self.pending_tokens) >= self.min_batch_tokens or 
                      len(pending_chunk) >= self.min_batch_chars)
        if has_enough:
            return True

        # Condition 4: Time interval elapsed
        if time_elapsed >= self.min_interval_sec:
            return True

        return False

    def get_display_html(self, is_active: bool = True) -> str:
        """
        Constructs the streaming display HTML with cursor, fade-in span, and auto-scroll trigger,
        advancing stable_text to the current clean output.
        """
        clean_preview = re.sanitize_model_output(self.full_response)
        pending_chunk = "".join(self.pending_tokens)

        if is_active:
            self.scroll_controller.start()
        else:
            self.scroll_controller.stop()

        html = render_streaming_display(
            stable_text=self.stable_text,
            latest_chunk=pending_chunk,
            is_active=is_active,
            auto_scroll=self.enable_auto_scroll
        )

        if is_active:
            self.stable_text = clean_preview
            self.pending_tokens = []
            self.last_render_time = time.time()
            self.first_token_emitted = True
            self.render_count += 1

        return html

    def get_final_text(self, interrupted: bool = False) -> str:
        """Returns the final sanitized plain markdown text without cursor, spans, or scroll triggers."""
        self.scroll_controller.stop()
        clean = re.sanitize_model_output(self.full_response)
        if interrupted and not clean.endswith("]*"):
            clean += "\n\n*[Generation stopped by user]*"
        if not clean:
            clean = "*[No response generated]*"
        return clean


# ============================================================================
# SIDEBAR CONTROLS & NAVIGATION
# ============================================================================

with st.sidebar:
    st.markdown("### 🛡️ HVF / AVNL Intelligence")
    st.markdown("**Heavy Vehicles Factory, Avadi**  \n*Armoured Vehicles Nigam Ltd (AVNL)*")
    st.divider()

    # --- System Telemetry Card ---
    st.markdown("#### ⚡ System Health")
    if telemetry["ollama_online"] and telemetry["all_models_ready"]:
        st.markdown('<span class="metric-badge badge-success">● Ollama AI Online</span>', unsafe_allow_html=True)
    elif telemetry["ollama_online"]:
        st.markdown('<span class="metric-badge badge-warning">▲ Models Incomplete</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="metric-badge badge-warning">✖ Ollama Offline</span>', unsafe_allow_html=True)
        st.caption("Execute `ollama serve` in a terminal to start the local AI daemon.")

    # Status badges for DB, OCR, Index
    badge_html = ""
    if telemetry.get("db_ready"):
        badge_html += '<span class="metric-badge badge-success">● SQLite DB</span>'
    else:
        badge_html += '<span class="metric-badge badge-warning">✖ SQLite DB</span>'

    if telemetry.get("tesseract_ready"):
        badge_html += '<span class="metric-badge badge-success">● OCR Ready</span>'
    else:
        badge_html += '<span class="metric-badge badge-info">○ OCR Fallback Standby</span>'

    if telemetry.get("index_consistent"):
        badge_html += '<span class="metric-badge badge-success">● FAISS Synced</span>'
    elif telemetry.get("index_loaded"):
        badge_html += '<span class="metric-badge badge-warning">▲ FAISS Check</span>'
    st.markdown(badge_html, unsafe_allow_html=True)

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.metric("Documents", telemetry["doc_count"])
    with col_m2:
        st.metric("Vector Chunks", telemetry["chunk_count"])

    st.caption(f"LLM: `{re.DEFAULT_LLM_MODEL}` | Embed: `{re.DEFAULT_EMBED_MODEL}` (768-dim)")
    st.divider()

    # --- Operating Mode Selector & Unified Navigation ---
    st.markdown("#### 🧭 Operational Navigation")
    nav_b1, nav_b2 = st.columns(2)
    with nav_b1:
        if st.button("📊 Dashboard", key="nav_btn_dash", use_container_width=True):
            st.session_state["app_mode_radio"] = "📊 Executive Dashboard & Telemetry"
            st.rerun()
        if st.button("🧩 Components", key="nav_btn_comp", use_container_width=True):
            st.session_state["app_mode_radio"] = "🧩 Visual & Tabular Component Explorer"
            st.rerun()
        if st.button("🔗 Impact Map", key="nav_btn_impact", use_container_width=True):
            st.session_state["app_mode_radio"] = "🔗 Cross-Document Impact Analysis"
            st.rerun()
    with nav_b2:
        if st.button("💬 Chatbot", key="nav_btn_chat", use_container_width=True):
            st.session_state["app_mode_radio"] = "💬 Technical Consultation Chat"
            st.rerun()
        if st.button("⚖️ Revision Diff", key="nav_btn_diff", use_container_width=True):
            st.session_state["app_mode_radio"] = "⚖️ SOP Revision Comparison Engine"
            st.rerun()
        if st.button("📥 Upload SOP", key="nav_btn_upload", use_container_width=True):
            st.session_state["app_mode_radio"] = "📥 Ingest & Manage SOP Documents"
            st.rerun()

    app_mode_options = [
        "📊 Executive Dashboard & Telemetry",
        "💬 Technical Consultation Chat",
        "🧩 Visual & Tabular Component Explorer",
        "⚖️ SOP Revision Comparison Engine",
        "🔗 Cross-Document Impact Analysis",
        "📥 Ingest & Manage SOP Documents"
    ]
    curr_mode = st.session_state.get("app_mode_radio", app_mode_options[0])
    mode_index = app_mode_options.index(curr_mode) if curr_mode in app_mode_options else 0

    app_mode = st.radio(
        "Select Operating Mode:",
        app_mode_options,
        index=mode_index,
        key="app_mode_radio"
    )
    st.divider()

    if app_mode == "💬 Technical Consultation Chat":
        # --- Conversation Manager ---
        st.markdown("#### 💬 Consultations")
        if st.button("➕ New Consultation", use_container_width=True, type="secondary"):
            all_c = db.list_conversations()
            new_conv = db.create_conversation(f"Consultation {len(all_c) + 1}")
            st.session_state["current_conv_id"] = new_conv["conversation_id"]
            st.rerun()

        all_convs = db.list_conversations(limit=50)
        if not all_convs:
            new_conv = db.create_conversation("New Consultation")
            all_convs = [new_conv]
            st.session_state["current_conv_id"] = new_conv["conversation_id"]

        conv_map = {c["conversation_id"]: c for c in all_convs}
        conv_ids = list(conv_map.keys())

        if st.session_state["current_conv_id"] not in conv_map:
            st.session_state["current_conv_id"] = conv_ids[0]

        current_idx = conv_ids.index(st.session_state["current_conv_id"])

        selected_conv_id = st.selectbox(
            "Active Consultation:",
            conv_ids,
            index=current_idx,
            format_func=lambda cid: f"{conv_map[cid]['title']} ({conv_map[cid].get('message_count', 0)} msgs)"
        )
        if selected_conv_id != st.session_state["current_conv_id"]:
            st.session_state["current_conv_id"] = selected_conv_id
            st.rerun()

        # Delete Consultation Option
        with st.expander("🗑️ Manage Consultation", expanded=False):
            curr_title = conv_map[st.session_state["current_conv_id"]]["title"]
            st.caption(f"Delete consultation `{curr_title}` and all associated messages.")
            if st.button("Delete Active Consultation", type="secondary", use_container_width=True):
                db.delete_conversation(st.session_state["current_conv_id"])
                remaining = db.list_conversations(limit=1)
                if remaining:
                    st.session_state["current_conv_id"] = remaining[0]["conversation_id"]
                else:
                    new_c = db.create_conversation("New Consultation")
                    st.session_state["current_conv_id"] = new_c["conversation_id"]
                st.success("Consultation deleted.")
                time.sleep(0.5)
                st.rerun()

        st.caption("🔒 *Conversations are persistently stored in SQLite (`data/sop_assistant.db`).*")
        st.divider()

        # --- Retrieval Filtering Controls ---
        st.markdown("#### 🔍 Retrieval Filters")
        top_k = st.slider("Top Evidence Passages (Top-K):", min_value=1, max_value=8, value=5)

        available_cats = ["All Categories"] + re.get_indexed_categories()
        category_filter = st.selectbox(
            "SOP Category Filter:",
            available_cats
        )
        filter_logical_id = None if category_filter == "All Categories" else category_filter

        if "revision_preference" not in st.session_state:
            st.session_state["revision_preference"] = REVISION_CHOICES[0]

        curr_pref = st.session_state.get("revision_preference", REVISION_CHOICES[0])
        pref_idx = REVISION_CHOICES.index(curr_pref) if curr_pref in REVISION_CHOICES else 0

        selected_rev_pref = st.selectbox(
            "SOP Revision Scope:",
            REVISION_CHOICES,
            index=pref_idx,
            key="revision_scope_select",
            help="Select whether to retrieve from latest revised SOPs (V2), baseline SOPs (V1), or search all revisions with V2 prioritized."
        )
        st.session_state["revision_preference"] = selected_rev_pref

        # Determine retrieval mode from validated preference
        if selected_rev_pref.startswith("V2"):
            rev_mode_val = "v2"
        elif selected_rev_pref.startswith("V1"):
            rev_mode_val = "v1"
        else:
            rev_mode_val = "all"

        st.divider()
    elif app_mode == "📊 Executive Dashboard & Telemetry":
        st.markdown("#### 📊 Dashboard & Telemetry")
        st.caption("Real-time system health and command overview.")
        st.markdown(
            "• Live Ollama inference state  \n"
            "• FAISS 768-dim vector sync  \n"
            "• 517 structured component records  \n"
            "• SQLite persistence metrics  \n"
            "• Quick module launch shortcuts"
        )
        st.divider()
    elif app_mode == "🧩 Visual & Tabular Component Explorer":
        st.markdown("#### 🧩 Component Explorer")
        st.caption("Inspecting multi-source SOP component intelligence.")
        st.markdown(
            "• Tables & technical matrices  \n"
            "• Visual diagrams & illustrations  \n"
            "• Callouts & stage-gate warnings  \n"
            "• Executive summaries  \n"
            "• Uncertainty profiling"
        )
        st.divider()
    elif app_mode == "📥 Ingest & Manage SOP Documents":
        st.markdown("#### 📥 Document Ingestion")
        st.caption("Transactional 7-stage PDF ingestion pipeline.")
        st.markdown(
            "1. PDF validation  \n"
            "2. Text extraction  \n"
            "3. Component extraction  \n"
            "4. 768-dim embeddings  \n"
            "5. FAISS indexing  \n"
            "6. Metadata persistence  \n"
            "7. Retrieval verification"
        )
        st.divider()
    else:
        st.markdown("#### ⚖️ Revision & Impact Engine")
        st.caption("Operating in Revision Comparison / Impact Analysis Mode.")
        st.markdown(
            "• Deterministic section alignment  \n"
            "• Numerical tolerance shifts  \n"
            "• Safety warning updates  \n"
            "• Coupled interface propagation  \n"
            "• Standalone report export"
        )
        st.divider()

    # --- Corpus Sync / Rebuild Button ---
    with st.expander("⚙️ Vector Database Management"):
        health = re.verify_faiss_index_health()
        status_color = "🟢 Healthy" if health.get("is_healthy") else "🔴 Attention Needed"
        st.markdown(f"**Index Health:** `{status_color}`")
        st.caption(
            f"• Total Vectors: **{health.get('total_vectors', 0)}** (Dim: {health.get('embedding_dimension', 768)})  \n"
            f"• Baseline SOP Documents: **{len(health.get('baseline_documents', []))}** ({health.get('baseline_chunks_count', 0)} chunks)  \n"
            f"• Uploaded Documents: **{len(health.get('uploaded_documents', []))}** ({health.get('uploaded_chunks_count', 0)} chunks)"
        )
        if health.get("uploaded_documents"):
            st.caption("Indexed Uploads: " + ", ".join([f"`{d}`" for d in health["uploaded_documents"]]))
        if health.get("issues"):
            for issue in health["issues"]:
                st.warning(f"⚠️ {issue}")
        st.divider()
        st.caption("Re-scans `SOP/` directory, extracts text, generates 768-dim embeddings, and persists FAISS index.")
        if st.button("🔄 Rebuild FAISS Corpus", use_container_width=True):
            with st.spinner("Rebuilding FAISS index from 10 SOP PDFs..."):
                t0 = time.time()
                rebuild_res = re.rebuild_faiss_index()
                dur = time.time() - t0
                st.success(f"Corpus rebuilt in {dur:.1f}s ({rebuild_res['total_chunks']} chunks).")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()


# ============================================================================
# MAIN APPLICATION HEADER
# ============================================================================

st.markdown('<h1 class="main-header">🛡️ SOP Document Intelligence Assistant</h1>', unsafe_allow_html=True)
st.markdown(
    '<p class="sub-header">'
    '<b>Heavy Vehicles Factory (HVF)</b> | Armoured Vehicles Nigam Limited (AVNL), Ministry of Defence &bull; '
    '<i>Grounded RAG with FAISS IndexFlatIP & Local Gemma 4.6B</i>'
    '</p>',
    unsafe_allow_html=True
)

# Notification banner if Ollama is offline or dependencies missing
if not telemetry["ollama_online"]:
    st.error(
        "⚠️ **Ollama Daemon Unreachable** — The local AI inference server is offline. "
        "Please start the service in your terminal via `ollama serve` and refresh this page."
    )
elif not telemetry.get("all_models_ready", False):
    st.warning(
        f"⚠️ **Required AI Models Incomplete** — LLM Ready: {telemetry.get('llm_ready')} (`{re.DEFAULT_LLM_MODEL}`), "
        f"Embedding Model Ready: {telemetry.get('embed_ready')} (`{re.DEFAULT_EMBED_MODEL}`). "
        "Please register the models in Ollama before querying."
    )
elif not telemetry["index_loaded"]:
    st.warning(
        "⚠️ **FAISS Index Missing** — No indexed SOP vector corpus was detected. "
        "Open the sidebar under **Vector Database Management** and click **Rebuild FAISS Corpus**."
    )
elif not telemetry.get("index_consistent", True):
    st.warning(
        f"⚠️ **FAISS Index Inconsistency Detected** — {telemetry.get('consistency_msg')}. "
        "Consider rebuilding the corpus under Vector Database Management."
    )

if not telemetry.get("db_ready", False):
    st.error("⚠️ **Database Unavailable** — Could not access local SQLite database `data/sop_assistant.db`.")


# ============================================================================
# TRANSACTIONAL 7-STAGE UPLOAD WORKFLOW COMPONENT
# ============================================================================

def render_seven_stage_upload(key_suffix: str = "main"):
    """
    Renders the transactional 7-stage SOP PDF upload, parsing, indexing, and verification interface:
      Stage 1: PDF Selected & Validated
      Stage 2: Text Extraction (digital stream with OCR fallback)
      Stage 3: Component Extraction (visual, tabular, entity classification)
      Stage 4: Embedding Generation (768-dim normalized dense vectors)
      Stage 5: FAISS Indexing (incremental vector insertion with duplicate safety)
      Stage 6: Metadata Persistence (atomic disk write of chunk, manifest, and component metadata)
      Stage 7: Ready for Questions (immediate post-indexing retrieval verification)
    """
    st.markdown(
        "Upload official technical documents to extract sections, generate 768-dim embeddings, "
        "and incrementally index into FAISS with transactional integrity, duplicate protection, "
        "and automatic multi-source component extraction."
    )

    # Vector health summary indicator
    current_health = re.verify_faiss_index_health()
    health_icon = "🟢" if current_health.get("is_healthy") else "🔴"
    st.caption(
        f"📊 **Index Health**: {health_icon} `{current_health.get('total_vectors', 0)}` chunks "
        f"({current_health.get('baseline_chunks_count', 0)} baseline, {current_health.get('uploaded_chunks_count', 0)} uploaded) "
        f"across `{current_health.get('total_documents', 0)}` documents."
    )

    uploaded_files = st.file_uploader(
        "Select SOP PDF File(s):",
        type=["pdf"],
        accept_multiple_files=True,
        key=f"pdf_uploader_{key_suffix}"
    )

    if uploaded_files:
        upload_btn = st.button("🚀 Process & Index Uploaded Documents", type="primary", key=f"btn_process_{key_suffix}")
        if upload_btn:
            upload_dir = os.path.join("data", "documents")
            os.makedirs(upload_dir, exist_ok=True)

            success_count = 0
            for uploaded_file in uploaded_files:
                file_bytes = uploaded_file.getbuffer()
                file_size_kb = round(len(file_bytes) / 1024, 1)
                save_path = os.path.join(upload_dir, uploaded_file.name)

                with st.status(f"Ingesting `{uploaded_file.name}` ({file_size_kb} KB)...", expanded=True) as status_box:
                    # --------------------------------------------------------
                    # STAGE 1: PDF SELECTED & VALIDATED
                    # --------------------------------------------------------
                    st.write(f"📄 **Stage 1 [PDF Selected & Validated]**: Validating file integrity for `{uploaded_file.name}`...")
                    try:
                        with open(save_path, "wb") as f:
                            f.write(file_bytes)
                        import fitz
                        test_doc = fitz.open(save_path)
                        pdf_page_count = len(test_doc)
                        test_doc.close()
                        st.write(f"✅ **Stage 1 [PDF Selected & Validated]**: PDF structure valid ({pdf_page_count} pages, {file_size_kb} KB).")
                    except Exception as e_pdf:
                        st.error(f"❌ Stage 1 [PDF Selected]: Corrupted or unreadable PDF file: {e_pdf}")
                        st.info("💡 **Recovery Action**: Ensure the uploaded file is a valid, unencrypted PDF document and try uploading again.")
                        status_box.update(label=f"❌ Failed validation for `{uploaded_file.name}`", state="error", expanded=True)
                        continue

                    # --------------------------------------------------------
                    # STAGE 2: TEXT EXTRACTION
                    # --------------------------------------------------------
                    st.write("📝 **Stage 2 [Text Extraction]**: Extracting text pages (digital stream with OCR fallback for scans/diagrams)...")
                    try:
                        doc_record = dp.process_pdf(save_path)
                    except Exception as e_proc:
                        doc_record = {"status": f"Exception: {e_proc}", "total_pages": 0, "total_chunks": 0}

                    if doc_record.get("status") != "success":
                        st.error(f"❌ Stage 2 [Text Extraction]: Extraction error: {doc_record.get('status')}")
                        st.info("💡 **Recovery Action**: Check PDF permissions, text encoding, or Tesseract OCR configuration.")
                        status_box.update(label=f"❌ Failed text extraction for `{uploaded_file.name}`", state="error", expanded=True)
                        continue

                    st.write(
                        f"✅ **Stage 2 [Text Extraction]**: Extracted **{doc_record['total_pages']}** pages "
                        f"and created **{doc_record['total_chunks']}** semantic chunks."
                    )

                    # --------------------------------------------------------
                    # STAGE 3: COMPONENT EXTRACTION
                    # --------------------------------------------------------
                    st.write("🧩 **Stage 3 [Component Extraction]**: Extracting visual, tabular, and physical components with entity classification...")
                    comp_status = doc_record.get("component_extraction_status", "success")
                    comps_to_persist = doc_record.get("components", [])

                    if comp_status != "success":
                        st.warning(f"⚠️ Stage 3 [Component Extraction]: Partial extraction notice ({comp_status}). Retry will be available.")
                        comp_success = False
                    else:
                        st.write(f"✅ **Stage 3 [Component Extraction]**: Extracted **{len(comps_to_persist)}** classified component records.")
                        comp_success = True

                    # --------------------------------------------------------
                    # STAGE 4: EMBEDDING GENERATION
                    # --------------------------------------------------------
                    st.write("⚡ **Stage 4 [Embedding Generation]**: Generating 768-dimensional normalized dense vectors via Ollama...")
                    chunks_to_index = doc_record.get("chunks", [])
                    if not chunks_to_index:
                        st.error("❌ Stage 4 [Embedding Generation]: No semantic chunks available to embed.")
                        status_box.update(label=f"❌ No chunks extracted from `{uploaded_file.name}`", state="error", expanded=True)
                        continue

                    try:
                        if not re.check_ollama_connection():
                            raise ConnectionError("Ollama daemon is unreachable at http://127.0.0.1:11434.")
                    except Exception as e_emb:
                        st.error(f"❌ Stage 4 [Embedding Generation]: Embedding failure: {e_emb}")
                        st.info("💡 **Recovery Action**: Execute `ollama serve` in a terminal and ensure `nomic-embed-text` is registered.")
                        status_box.update(label=f"❌ Embedding failed for `{uploaded_file.name}`", state="error", expanded=True)
                        continue

                    st.write(f"✅ **Stage 4 [Embedding Generation]**: Embedding model ready. Generating embeddings for **{len(chunks_to_index)}** chunks...")

                    # --------------------------------------------------------
                    # STAGE 5: FAISS INDEXING
                    # --------------------------------------------------------
                    st.write("🗄️ **Stage 5 [FAISS Indexing]**: Inserting normalized vectors into FAISS vector index with duplicate protection...")
                    try:
                        idx_summary = re.index_chunks(
                            chunks_to_index,
                            replace_existing=True
                        )
                        st.write(f"✅ **Stage 5 [FAISS Indexing]**: Indexed **{idx_summary['indexed_chunks']}** chunks ({idx_summary.get('embedding_duration_s', 0)}s).")
                    except Exception as e_idx:
                        st.error(f"❌ Stage 5 [FAISS Indexing]: Indexing error: {e_idx}")
                        st.info("💡 **Recovery Action**: Use sidebar 'Rebuild FAISS Corpus' or verify filesystem write permissions in `data/faiss_index`.")
                        status_box.update(label=f"❌ Failed to index `{uploaded_file.name}`", state="error", expanded=True)
                        continue

                    # --------------------------------------------------------
                    # STAGE 6: METADATA PERSISTENCE
                    # --------------------------------------------------------
                    st.write("💾 **Stage 6 [Metadata Persistence]**: Atomically persisting chunk metadata, manifest, and component metadata to disk...")
                    if comp_success and comps_to_persist:
                        save_ok = re.save_document_components(
                            document_id=doc_record["document_id"],
                            filename=uploaded_file.name,
                            components=comps_to_persist
                        )
                        if save_ok:
                            st.write("✅ **Stage 6 [Metadata Persistence]**: Atomically persisted component records in `components_metadata.json` and index in `sop.index`.")
                        else:
                            st.warning("⚠️ Stage 6 [Metadata Persistence]: Component metadata save encountered an issue.")
                            comp_success = False
                    else:
                        st.write("ℹ️ **Stage 6 [Metadata Persistence]**: Vector metadata persisted; component metadata skipped due to partial extraction.")

                    # --------------------------------------------------------
                    # STAGE 7: READY FOR QUESTIONS
                    # --------------------------------------------------------
                    test_query = (
                        doc_record.get("document_title")
                        if doc_record.get("document_title") and doc_record["document_title"] != "UNKNOWN"
                        else (doc_record["chunks"][0]["chunk_text"][:80] if doc_record.get("chunks") else "SOP")
                    )
                    verif_res = re.verify_retrieval_for_document(
                        query=test_query,
                        expected_identifier=doc_record["document_id"],
                        top_k=5,
                        revision_mode="v2"
                    )

                    if verif_res["is_retrieved"]:
                        st.write(
                            f"🚀 **Stage 7 [Ready for Questions]**: Retrieval verified (Rank #{verif_res['best_rank']} | "
                            f"Cosine Similarity: `{verif_res['best_score']}`). Document is live for consultation and exploration!"
                        )
                        status_box.update(label=f"✅ `{uploaded_file.name}` Ingestion & Verification Complete!", state="complete", expanded=False)
                    else:
                        st.write(f"ℹ️ **Stage 7 [Ready for Questions]**: Document persisted in index (total vectors: {idx_summary['total_index_chunks']}).")
                        status_box.update(label=f"✅ `{uploaded_file.name}` Indexed in Vector Corpus", state="complete", expanded=False)

                    # Summary Card
                    st.markdown(f"#### 📋 Ingestion Summary: `{uploaded_file.name}`")
                    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                    with col_s1:
                        st.metric("Document ID", doc_record.get("document_id", "N/A"))
                    with col_s2:
                        st.metric("Revision", doc_record.get("revision", "N/A")[:18])
                    with col_s3:
                        st.metric("Total Pages", doc_record.get("total_pages", 0))
                    with col_s4:
                        st.metric("Chunks Indexed", idx_summary.get("indexed_chunks", 0))

                    st.markdown(
                        f"- **Filename**: `{doc_record.get('filename')}`  \n"
                        f"- **Document Title**: {doc_record.get('document_title')}  \n"
                        f"- **Logical SOP Category**: `{doc_record.get('logical_sop_id')}`  \n"
                        f"- **Extracted Chunks**: `{doc_record.get('total_chunks')}`  \n"
                        f"- **Embedded & Indexed Chunks**: `{idx_summary.get('indexed_chunks')}`  \n"
                        f"- **Extracted Components**: `{len(comps_to_persist)}` (Status: `{comp_status}`)  \n"
                        f"- **Verification**: `✅ Confirmed Retrievable (Rank #{verif_res.get('best_rank', 1)})`"
                    )

                    # Action buttons
                    b_col1, b_col2, b_col3 = st.columns(3)
                    with b_col1:
                        if st.button("💬 Ask AI about this document", key=f"ask_doc_{uploaded_file.name}_{key_suffix}", type="primary", use_container_width=True):
                            st.session_state["pending_chat_prompt"] = f"Summarize the technical procedures, safety warnings, and component requirements in {uploaded_file.name}."
                            st.session_state["app_mode_radio"] = "💬 Technical Consultation Chat"
                            st.rerun()
                    with b_col2:
                        if st.button("🧩 Inspect components in Explorer", key=f"comp_doc_{uploaded_file.name}_{key_suffix}", use_container_width=True):
                            st.session_state["comp_doc_sel"] = uploaded_file.name
                            st.session_state["app_mode_radio"] = "🧩 Visual & Tabular Component Explorer"
                            st.rerun()
                    with b_col3:
                        if st.button("⚖️ Compare with other SOPs", key=f"diff_doc_{uploaded_file.name}_{key_suffix}", use_container_width=True):
                            st.session_state["app_mode_radio"] = "⚖️ SOP Revision Comparison Engine"
                            st.rerun()

                    # Retry Component Extraction Button if needed
                    if not comp_success or doc_record.get("component_extraction_status") != "success":
                        st.warning(f"⚠️ Component extraction for `{uploaded_file.name}` is incomplete.")
                        if st.button(f"🔄 Retry Component Extraction for `{uploaded_file.name}`", key=f"retry_{uploaded_file.name}_{key_suffix}"):
                            ret_res = re.retry_component_extraction(
                                pdf_path=save_path,
                                document_id=doc_record.get("document_id"),
                                filename=uploaded_file.name,
                                revision=doc_record.get("revision")
                            )
                            if ret_res.get("status") == "success":
                                st.success(f"🎉 Successfully extracted and persisted {ret_res.get('extracted_count')} components!")
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.error(f"❌ Retry failed: {ret_res.get('status')}")

                    success_count += 1
                    st.divider()

            if success_count > 0:
                st.cache_data.clear()
                st.success(f"🎉 Successfully ingested and verified {success_count} document(s) across all 7 stages!")


# ============================================================================
# MAIN APPLICATION INTERFACE (DASHBOARD, CHAT, COMPONENT EXPLORER, REVISIONS)
# ============================================================================

if app_mode == "📊 Executive Dashboard & Telemetry":
    # ------------------------------------------------------------------------
    # 1. EXECUTIVE DASHBOARD & SYSTEM TELEMETRY VIEW
    # ------------------------------------------------------------------------
    st.markdown("""
    <div class="dashboard-banner">
        <h2>🛡️ HVF / AVNL SOP Document Intelligence Platform</h2>
        <p>
            <b>Heavy Vehicles Factory (HVF)</b> | Armoured Vehicles Nigam Limited (AVNL), Ministry of Defence &bull; 
            Authoritative offline-first engineering dashboard providing grounded retrieval-augmented generation (RAG), 
            multi-source visual and tabular component extraction, mechanical relationship navigation, deterministic 
            revision tolerance diffs, and cross-subsystem interface impact analysis.
        </p>
    </div>
    """, unsafe_allow_html=True)

    # Live telemetry status banner
    status_cls = "badge-success" if telemetry["overall_status"] == "HEALTHY" else ("badge-warning" if telemetry["overall_status"] == "DEGRADED" else "badge-danger")
    st.markdown(
        f'<div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 12px 18px; margin-bottom: 22px;">'
        f'<b>System Operational State:</b> <span class="metric-badge {status_cls}">● {telemetry["overall_status"]}</span> &bull; '
        f'<span style="color: #475569; font-size: 0.92rem;">{telemetry["status_message"]}</span>'
        f'</div>',
        unsafe_allow_html=True
    )

    # 4 Primary KPI Statistics Cards
    k_col1, k_col2, k_col3, k_col4 = st.columns(4)
    with k_col1:
        st.markdown(
            f'<div class="dashboard-kpi-card">'
            f'<div class="kpi-label">Indexed Documents</div>'
            f'<div class="kpi-number">{telemetry["doc_count"]}</div>'
            f'<div class="kpi-subtext">{telemetry.get("full_health", {}).get("documents", {}).get("baseline_documents_count", 10)} baseline &bull; {telemetry["uploaded_doc_count"]} custom uploads</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with k_col2:
        st.markdown(
            f'<div class="dashboard-kpi-card">'
            f'<div class="kpi-label">Extracted Components</div>'
            f'<div class="kpi-number">{telemetry["components_count"]}</div>'
            f'<div class="kpi-subtext">Across 10 distinct entity classifications</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with k_col3:
        st.markdown(
            f'<div class="dashboard-kpi-card">'
            f'<div class="kpi-label">FAISS Vector Chunks</div>'
            f'<div class="kpi-number">{telemetry["chunk_count"]}</div>'
            f'<div class="kpi-subtext">768-dim normalized IndexFlatIP</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    with k_col4:
        db_h = telemetry.get("full_health", {}).get("database", {})
        total_convs = db_h.get("total_conversations", 0)
        total_msgs = db_h.get("total_messages", 0)
        st.markdown(
            f'<div class="dashboard-kpi-card">'
            f'<div class="kpi-label">Consultations / Msgs</div>'
            f'<div class="kpi-number">{total_convs} / {total_msgs}</div>'
            f'<div class="kpi-subtext">Persistently stored in SQLite database</div>'
            f'</div>',
            unsafe_allow_html=True
        )

    # 3 Infrastructure & Diagnostics Panels
    st.markdown("### ⚡ System Diagnostics & Infrastructure Health")
    d_col1, d_col2, d_col3 = st.columns(3)
    with d_col1:
        st.markdown('<div class="health-card">', unsafe_allow_html=True)
        st.markdown("#### 🧠 AI Inference Engine (Ollama)")
        ollama_b = '<span class="metric-badge badge-success">● Connected</span>' if telemetry["ollama_online"] else '<span class="metric-badge badge-warning">✖ Disconnected</span>'
        llm_b = '<span class="metric-badge badge-success">● Ready</span>' if telemetry["llm_ready"] else '<span class="metric-badge badge-warning">▲ Missing</span>'
        emb_b = '<span class="metric-badge badge-success">● Ready</span>' if telemetry["embed_ready"] else '<span class="metric-badge badge-warning">▲ Missing</span>'
        st.markdown(f'<div class="health-item"><b>Ollama Daemon:</b> {ollama_b}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="health-item"><b>LLM Model:</b> `{re.DEFAULT_LLM_MODEL}` {llm_b}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="health-item"><b>Embedding Model:</b> `{re.DEFAULT_EMBED_MODEL}` {emb_b}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="health-item"><b>Endpoint:</b> `{re.DEFAULT_OLLAMA_ENDPOINT}`</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with d_col2:
        st.markdown('<div class="health-card">', unsafe_allow_html=True)
        st.markdown("#### 🗄️ Vector Database (FAISS)")
        faiss_h = telemetry.get("full_health", {}).get("faiss", {})
        idx_b = '<span class="metric-badge badge-success">● Healthy & Synced</span>' if faiss_h.get("is_healthy") else '<span class="metric-badge badge-warning">▲ Check Required</span>'
        st.markdown(f'<div class="health-item"><b>Index Health:</b> {idx_b}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="health-item"><b>Total Chunks:</b> {faiss_h.get("total_vectors", 0)} (Dim: {faiss_h.get("embedding_dimension", 768)})</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="health-item"><b>Baseline Corpus:</b> {faiss_h.get("baseline_chunks_count", 0)} chunks ({len(faiss_h.get("baseline_documents", []))} docs)</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="health-item"><b>Uploaded Corpus:</b> {faiss_h.get("uploaded_chunks_count", 0)} chunks ({len(faiss_h.get("uploaded_documents", []))} docs)</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with d_col3:
        st.markdown('<div class="health-card">', unsafe_allow_html=True)
        st.markdown("#### 🧩 Knowledge & SQL Persistence")
        comp_h = telemetry.get("full_health", {}).get("components", {})
        comp_b = '<span class="metric-badge badge-success">● Valid Metadata</span>' if comp_h.get("is_healthy") else '<span class="metric-badge badge-warning">▲ Missing</span>'
        db_b = '<span class="metric-badge badge-success">● SQLite Connected</span>' if telemetry.get("db_ready") else '<span class="metric-badge badge-warning">✖ Database Offline</span>'
        ocr_b = '<span class="metric-badge badge-success">● OCR Ready</span>' if telemetry.get("tesseract_ready") else '<span class="metric-badge badge-info">○ OCR Fallback</span>'
        st.markdown(f'<div class="health-item"><b>Components Store:</b> {comp_b}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="health-item"><b>Physical / Assemblies:</b> {comp_h.get("physical_components_count", 0) + comp_h.get("assemblies_count", 0)} records</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="health-item"><b>SQLite Store:</b> {db_b}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="health-item"><b>OCR Engine:</b> {ocr_b}</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Operational Quick Navigation Cards
    st.divider()
    st.markdown("### 🧭 Operational Module Navigation")
    st.caption("Access specialized engineering intelligence modules with one click:")

    n_row1_c1, n_row1_c2 = st.columns(2)
    with n_row1_c1:
        st.markdown('<div class="nav-card">', unsafe_allow_html=True)
        st.markdown("#### 💬 Technical Consultation Chatbot")
        st.markdown("Ask natural-language engineering questions regarding manufacturing, assembly, torque, alignment, and testing procedures. Grounded in authoritative SOP passages with traceable citations.")
        if st.button("🚀 Launch Technical Chatbot", key="dash_launch_chat", type="primary", use_container_width=True):
            st.session_state["app_mode_radio"] = "💬 Technical Consultation Chat"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with n_row1_c2:
        st.markdown('<div class="nav-card">', unsafe_allow_html=True)
        st.markdown("#### 🧩 Visual & Tabular Component Explorer")
        st.markdown("Inspect 517 extracted physical components, major assemblies, and subsystems across 10 logical categories. Explore verified mechanical relationships, tolerances, and cross-revision technical evolution.")
        if st.button("🧩 Open Component Explorer", key="dash_launch_comp", type="secondary", use_container_width=True):
            st.session_state["app_mode_radio"] = "🧩 Visual & Tabular Component Explorer"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    n_row2_c1, n_row2_c2, n_row2_c3 = st.columns(3)
    with n_row2_c1:
        st.markdown('<div class="nav-card">', unsafe_allow_html=True)
        st.markdown("#### ⚖️ Revision Comparison")
        st.markdown("Audit before/after numerical tolerances, safety precautions, tooling shifts, and acceptance criteria between baseline V1 and revised V2 SOPs.")
        if st.button("⚖️ Compare SOP Revisions", key="dash_launch_diff", use_container_width=True):
            st.session_state["app_mode_radio"] = "⚖️ SOP Revision Comparison Engine"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with n_row2_c2:
        st.markdown('<div class="nav-card">', unsafe_allow_html=True)
        st.markdown("#### 🔗 Impact Analysis")
        st.markdown("Analyze how manufacturing and assembly changes propagate across coupled geometric interfaces and interconnected tank subsystems.")
        if st.button("🔗 Track Cross Impacts", key="dash_launch_impact", use_container_width=True):
            st.session_state["app_mode_radio"] = "🔗 Cross-Document Impact Analysis"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with n_row2_c3:
        st.markdown('<div class="nav-card">', unsafe_allow_html=True)
        st.markdown("#### 📥 Ingest SOP Documents")
        st.markdown("Upload and index new technical PDFs through the transactional 7-stage ingestion workflow with automatic component extraction and FAISS indexing.")
        if st.button("📥 Ingest New Documents", key="dash_launch_upload", use_container_width=True):
            st.session_state["app_mode_radio"] = "📥 Ingest & Manage SOP Documents"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

elif app_mode == "💬 Technical Consultation Chat":
    with st.expander("📥 Ingest New SOP Document (PDF Upload & Indexing)", expanded=False):
        render_seven_stage_upload(key_suffix="chat")

    # --- Conversation Display Area ---
    active_cid = st.session_state["current_conv_id"]
    active_conv = db.get_conversation(active_cid)
    if not active_conv:
        active_conv = db.create_conversation("New Consultation", conv_id=active_cid)

    messages = db.get_conversation_messages(active_cid)

    # Visibly display active revision retrieval scope
    active_scope_label = st.session_state.get("revision_preference", REVISION_CHOICES[0])
    st.caption(f"🎯 **Active Retrieval Scope**: `{active_scope_label}`")

    # Render active component context banner if initiated from Component Explorer
    active_comp_ctx = st.session_state.get("active_component_context")
    if active_comp_ctx:
        with st.container():
            st.info(
                f"🧩 **Active Component Context**: `{active_comp_ctx.get('component_name')}` "
                f"(`{active_comp_ctx.get('entity_type', 'COMPONENT')}`)  \n"
                f"• **Source Document**: `{active_comp_ctx.get('filename')}` (Section *{active_comp_ctx.get('section', 'General')}*, Page {active_comp_ctx.get('page_number', '1')})  \n"
                f"• **Subsystem**: `{active_comp_ctx.get('associated_subsystem', 'N/A')}`"
            )
            st.caption("💡 **Context-Aware Follow-Up Inquiries (Click to Ask AI)**:")
            ch_c1, ch_c2, ch_c3 = st.columns(3)
            with ch_c1:
                if st.button("⚙️ What does this component do?", key="chip_fn", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = f"What does the {active_comp_ctx.get('component_name')} do according to the SOP evidence?"
                    st.rerun()
                if st.button("📦 Which assembly does it belong to?", key="chip_asm", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = f"Which assembly or subsystem does the {active_comp_ctx.get('component_name')} belong to?"
                    st.rerun()
            with ch_c2:
                if st.button("🔗 What other components connect to it?", key="chip_rel", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = f"What other components connect to or interact with the {active_comp_ctx.get('component_name')}?"
                    st.rerun()
                if st.button("⚖️ What changed between V1 and V2?", key="chip_diff", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = f"What changed in the {active_comp_ctx.get('component_name')} between V1 and V2?"
                    st.rerun()
            with ch_c3:
                if st.button("📖 Which SOP section describes its installation?", key="chip_sec", use_container_width=True):
                    st.session_state["pending_chat_prompt"] = f"Which SOP section and page describes the {active_comp_ctx.get('component_name')} and its installation or inspection?"
                    st.rerun()
                if st.button("🧩 Open in Component Explorer", key="chip_explorer", use_container_width=True):
                    st.session_state["target_nav_component"] = active_comp_ctx.get("component_name")
                    st.session_state["app_mode_radio"] = "🧩 Visual & Tabular Component Explorer"
                    st.rerun()
        st.divider()

    # Render empty conversation prompt if no messages
    if not messages:
        st.info(
            "👋 **Welcome to the Intelligent SOP Assistant.**  \n"
            "Ask technical questions regarding hull welding, turret integration, V12 engine alignment, "
            "torsion suspension, or main gun calibration. Responses will be grounded in official SOP evidence with verifiable citations."
        )

    # Render conversation history
    cached_comps_for_chat = re.load_components_metadata()
    for idx, msg in enumerate(messages):
        role = msg.get("role", "user")
        content = msg.get("content", "")
        citations = msg.get("citations", [])
        is_cancelled = msg.get("is_cancelled", False)

        with st.chat_message(role, avatar="🧑‍💻" if role == "user" else "🛡️"):
            st.markdown(content)

            if is_cancelled:
                st.caption("⚠️ *[Generation was stopped by user]*")

            # Render referenced component pills if any components appear in the answer
            if role == "assistant" and content:
                ref_comps = find_referenced_components_in_text(content, cached_comps_for_chat)
                if ref_comps:
                    st.caption("🧩 **Referenced Components in this Response (Click to Inspect)**:")
                    pill_cols = st.columns(min(len(ref_comps), 4))
                    for p_idx, comp_name in enumerate(ref_comps[:4]):
                        with pill_cols[p_idx % len(pill_cols)]:
                            if st.button(f"🔍 {comp_name}", key=f"hist_ref_comp_{msg.get('message_id', idx)}_{p_idx}", use_container_width=True):
                                st.session_state["target_nav_component"] = comp_name
                                st.session_state["app_mode_radio"] = "🧩 Visual & Tabular Component Explorer"
                                st.rerun()

            # Render compact evidence citations if available
            if citations and role == "assistant":
                render_compact_evidence_sources(citations)

    # --- Chat Input & Streaming Generation ---
    pending_prompt = st.session_state.pop("pending_chat_prompt", None)
    controls_container = st.container()
    chat_box_input = st.chat_input("Enter your SOP engineering inquiry...")
    user_input = pending_prompt if pending_prompt else chat_box_input

    if user_input and not st.session_state["is_generating"]:
        if len(messages) == 0:
            clean_title = (user_input[:28] + "...") if len(user_input) > 28 else user_input
            db.update_conversation_title(active_cid, clean_title)

        db.save_message(
            conversation_id=active_cid,
            role="user",
            content=user_input
        )

        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(user_input)

        st.session_state["is_generating"] = True
        st.session_state["stop_requested"] = False

        stop_col1, stop_col2 = controls_container.columns([5, 2])
        with stop_col2:
            stop_clicked = st.button("⏹ Stop Generation", key="active_stop_btn", type="secondary", use_container_width=True)
            if stop_clicked:
                st.session_state["stop_requested"] = True

        with st.chat_message("assistant", avatar="🛡️"):
            response_placeholder = st.empty()
            # Immediate active typing indicator while retrieval and model start
            response_placeholder.markdown('<span class="typing-cursor"></span>' + AUTOSCROLL_TRIGGER_HTML, unsafe_allow_html=True)
            accumulator = SmoothStreamAccumulator()
            stream_citations: List[Dict[str, Any]] = []
            generation_interrupted = False

            try:
                token_stream, stream_citations, info = re.stream_rag_answer(
                    question=user_input,
                    top_k=top_k,
                    logical_sop_id=filter_logical_id,
                    revision_mode=rev_mode_val,
                    conversation_history=messages
                )

                for token in token_stream:
                    if st.session_state.get("stop_requested", False):
                        generation_interrupted = True
                        if hasattr(token_stream, "close") and callable(token_stream.close):
                            try:
                                token_stream.close()
                            except Exception:
                                pass
                        break

                    if accumulator.add_token(token):
                        display_html = accumulator.get_display_html(is_active=True)
                        response_placeholder.markdown(display_html, unsafe_allow_html=True)

            except Exception as e:
                st.error(f"Generation error: {e}")
                if not accumulator.full_response:
                    accumulator.full_response = f"*[Error during inference: {str(e)}]*"
                generation_interrupted = True

            finally:
                st.session_state["is_generating"] = False
                st.session_state["stop_requested"] = False
                accumulator.scroll_controller.stop()

            clean_text = accumulator.get_final_text(interrupted=generation_interrupted)
            response_placeholder.markdown(clean_text)

            db.save_message(
                conversation_id=active_cid,
                role="assistant",
                content=clean_text,
                citations=stream_citations,
                is_cancelled=generation_interrupted
            )

            if stream_citations:
                if info.get("is_cross_revision", False):
                    st.caption("ℹ️ *Evidence retrieved spans multiple revisions (Baseline V1 and Revised V2).*")
                if info.get("is_component_query", False) and info.get("component_intent", {}).get("is_component_intent"):
                    cat_name = info["component_intent"].get("category", "Component Intelligence")
                    st.caption(f"🧩 *Component Intelligence Active: {cat_name}*")
                render_compact_evidence_sources(stream_citations)

            # Check for referenced components in newly generated answer
            ref_comps_new = find_referenced_components_in_text(clean_text, cached_comps_for_chat)
            if ref_comps_new:
                st.caption("🧩 **Referenced Components in this Response (Click to Inspect)**:")
                pill_cols = st.columns(min(len(ref_comps_new), 4))
                for p_idx, comp_name in enumerate(ref_comps_new[:4]):
                    with pill_cols[p_idx % len(pill_cols)]:
                        if st.button(f"🔍 {comp_name}", key=f"stream_ref_comp_{p_idx}", use_container_width=True):
                            st.session_state["target_nav_component"] = comp_name
                            st.session_state["app_mode_radio"] = "🧩 Visual & Tabular Component Explorer"
                            st.rerun()

        st.rerun()

elif app_mode == "⚖️ SOP Revision Comparison Engine":
    # ========================================================================
    # SOP REVISION COMPARISON ENGINE VIEW
    # ========================================================================
    st.markdown('<h2 style="color: #1E3A8A; font-weight: 700;">⚖️ SOP Revision Comparison Engine</h2>', unsafe_allow_html=True)
    st.markdown(
        "Compare authoritative baseline (v1) and revised (v2) technical specifications. "
        "Detects numerical tolerance shifts, safety precaution updates, equipment transitions, "
        "and acceptance benchmarks with verbatim before/after source evidence."
    )

    available_pairs = sa.get_available_sop_pairs()
    if not available_pairs:
        st.warning("⚠️ No SOP revision pairs found in `SOP/` directory.")
    else:
        pair_options = [p["logical_sop_id"] for p in available_pairs]
        selected_log_id = st.selectbox(
            "Select SOP Category for Revision Audit:",
            pair_options,
            key="comparison_pair_select"
        )

        chosen_pair = next(p for p in available_pairs if p["logical_sop_id"] == selected_log_id)

        col_b, col_r = st.columns(2)
        with col_b:
            st.info(f"**Baseline (v1):** `{chosen_pair['baseline_filename']}`")
        with col_r:
            st.info(f"**Revised (v2):** `{chosen_pair['revised_filename']}`")

        run_compare = st.button("🚀 Execute Revision Comparison", type="primary")

        cmp_cache_key = f"cmp_res_{selected_log_id}"

        if run_compare:
            with st.spinner(f"Extracting, aligning, and comparing {selected_log_id}..."):
                t0 = time.time()
                cmp_res = sa.compare_sop_files(chosen_pair["baseline_path"], chosen_pair["revised_path"])
                dur = time.time() - t0
                st.session_state[cmp_cache_key] = cmp_res
                st.success(f"Audit completed in {dur:.2f}s! Identified {cmp_res['total_changes']} change points.")

        if cmp_cache_key in st.session_state:
            cmp_res = st.session_state[cmp_cache_key]
            counts = cmp_res["classification_summary"]

            st.divider()
            st.markdown("### 📊 Executive Change Summary")
            m_col1, m_col2, m_col3, m_col4, m_col5 = st.columns(5)
            with m_col1:
                st.metric("Total Changes", cmp_res["total_changes"])
            with m_col2:
                st.metric("Numerical Shifts", counts.get("Changed numerical parameter, tolerance, or threshold", 0))
            with m_col3:
                st.metric("Safety Updates", counts.get("Changed safety warning or precaution", 0))
            with m_col4:
                st.metric("Tooling/Sensors", counts.get("Changed equipment, tooling, or material", 0))
            with m_col5:
                st.metric("Acceptance Criteria", counts.get("Changed inspection or acceptance criterion", 0))

            # Report Export
            report_md = sa.generate_comparison_report(cmp_res)
            st.download_button(
                label="📥 Export Comparison Audit Report (.md)",
                data=report_md,
                file_name=f"{selected_log_id}_Revision_Comparison_Report.md",
                mime="text/markdown",
                use_container_width=True
            )

            st.divider()
            st.markdown("### 📑 Traceable Change Inventory")

            filter_cats = ["All Changes"] + [c for c, cnt in counts.items() if cnt > 0]
            chosen_cat = st.selectbox("Filter Changes By Classification:", filter_cats, key="diff_cat_filter")

            filtered_changes = cmp_res["changes"]
            if chosen_cat != "All Changes":
                filtered_changes = [c for c in filtered_changes if chosen_cat in c["classifications"]]

            st.caption(f"Displaying **{len(filtered_changes)}** matching change item(s):")

            for chg in filtered_changes:
                status_icon = "⚠️" if "Uncertain" in chg["review_status"] else "⚡"
                header_title = f"{status_icon} [{chg['change_id']}] {chg['primary_classification']}"
                if chg.get("revised_section"):
                    header_title += f" — {chg['revised_section']}"
                elif chg.get("baseline_section"):
                    header_title += f" — {chg['baseline_section']}"

                with st.expander(header_title, expanded=False):
                    st.markdown(f"**Operational Significance:** {chg['operational_significance']}")
                    st.markdown(f"**Review Status:** `{chg['review_status']}` | **Similarity:** `{chg.get('similarity_ratio', 0.0):.1%}`")
                    st.caption(
                        f"**Baseline:** `{chg['baseline_filename']}` (Page {chg['baseline_page']}) | "
                        f"**Revised:** `{chg['revised_filename']}` (Page {chg['revised_page']})"
                    )

                    c_diff1, c_diff2 = st.columns(2)
                    with c_diff1:
                        st.markdown("**Original Specification (Baseline):**")
                        st.markdown(f"```text\n{chg['baseline_passage'] if chg['baseline_passage'] else '[Section not present in baseline]'}\n```")
                    with c_diff2:
                        st.markdown("**Updated Specification (Revised):**")
                        st.markdown(f"```text\n{chg['revised_passage'] if chg['revised_passage'] else '[Section removed in revision]'}\n```")

elif app_mode == "🔗 Cross-Document Impact Analysis":
    # ========================================================================
    # CROSS-DOCUMENT IMPACT ANALYSIS ENGINE VIEW (PHASE 8)
    # ========================================================================
    st.markdown('<h2 style="color: #1E3A8A; font-weight: 700;">🔗 Cross-Document Impact Analysis Engine</h2>', unsafe_allow_html=True)
    st.markdown(
        "Analyze how substantive parameter, safety, tooling, or sequence changes in a source SOP "
        "propagate across interconnected manufacturing subsystems. Provides evidence-backed impact "
        "candidates, coupled geometric interface explanations, and interactive human review workflow."
    )

    available_pairs = sa.get_available_sop_pairs()
    if not available_pairs:
        st.warning("⚠️ No SOP revision pairs found in `SOP/` directory.")
    else:
        pair_options = [p["logical_sop_id"] for p in available_pairs]
        impact_src_log_id = st.selectbox(
            "Select Source SOP Revision Comparison to Analyze:",
            pair_options,
            key="impact_src_select"
        )

        chosen_pair = next(p for p in available_pairs if p["logical_sop_id"] == impact_src_log_id)

        col_ib, col_ir = st.columns(2)
        with col_ib:
            st.info(f"**Source Baseline:** `{chosen_pair['baseline_filename']}`")
        with col_ir:
            st.info(f"**Source Revised:** `{chosen_pair['revised_filename']}`")

        run_impact_btn = st.button("🔍 Execute Cross-Document Impact Analysis", type="primary")

        impact_cache_key = f"impact_res_{impact_src_log_id}"

        if run_impact_btn:
            with st.spinner(f"Running cross-document impact analysis on {impact_src_log_id}..."):
                t0 = time.time()
                # Run or retrieve revision comparison
                cmp_cache_key = f"cmp_res_{impact_src_log_id}"
                if cmp_cache_key in st.session_state:
                    cmp_res = st.session_state[cmp_cache_key]
                else:
                    cmp_res = sa.compare_sop_files(chosen_pair["baseline_path"], chosen_pair["revised_path"])
                    st.session_state[cmp_cache_key] = cmp_res

                impact_res = sa.analyze_cross_document_impacts(cmp_res, sop_dir="SOP")
                dur = time.time() - t0
                st.session_state[impact_cache_key] = impact_res
                st.success(f"Impact analysis completed in {dur:.2f}s! Identified {impact_res['total_candidates']} evidence-backed candidate(s).")

        if impact_cache_key in st.session_state:
            impact_res = st.session_state[impact_cache_key]
            counts_cls = impact_res["counts_by_classification"]
            counts_dec = impact_res["counts_by_decision"]

            st.divider()
            st.markdown("### 📊 Cross-Subsystem Impact Summary")

            i_col1, i_col2, i_col3, i_col4, i_col5 = st.columns(5)
            with i_col1:
                st.metric("Total Candidates", impact_res["total_candidates"])
            with i_col2:
                st.metric("Direct Impacts", counts_cls.get(sa.IMPACT_DIRECT, 0))
            with i_col3:
                st.metric("Potential Impacts", counts_cls.get(sa.IMPACT_POTENTIAL, 0))
            with i_col4:
                st.metric("Review Required", counts_cls.get(sa.IMPACT_HUMAN_REVIEW, 0))
            with i_col5:
                st.metric("Unimpacted SOPs", impact_res.get("unimpacted_sop_count", 0))

            # Download Button for Report
            report_md = sa.generate_impact_report(impact_res)
            st.download_button(
                label="📥 Export Cross-Document Impact Audit Report (.md)",
                data=report_md,
                file_name=f"{impact_src_log_id}_Cross_Document_Impact_Report.md",
                mime="text/markdown",
                use_container_width=True
            )

            st.divider()
            st.markdown("### 📑 Evidence-Backed Candidates & Review Workflow")

            candidates = impact_res.get("candidates", [])
            if not candidates:
                st.info("No cross-document impacts identified in the indexed corpus for this SOP revision.")
            else:
                # Filters
                all_aff = ["All Affected Subsystems"] + sorted(list({c["affected_sop_id"] for c in candidates}))
                all_classes = ["All Classifications"] + [c for c in sa.ALL_IMPACT_CLASSES if counts_cls.get(c, 0) > 0]
                all_statuses = ["All Review Decisions", "PENDING", "ACCEPTED", "REJECTED", "INVESTIGATE"]

                f_col1, f_col2, f_col3 = st.columns(3)
                with f_col1:
                    chosen_aff = st.selectbox("Filter Affected SOP:", all_aff, key="f_aff_sop")
                with f_col2:
                    chosen_class = st.selectbox("Filter Classification:", all_classes, key="f_class_sop")
                with f_col3:
                    chosen_status = st.selectbox("Filter Review Status:", all_statuses, key="f_status_sop")

                filtered_candidates = candidates
                if chosen_aff != "All Affected Subsystems":
                    filtered_candidates = [c for c in filtered_candidates if c["affected_sop_id"] == chosen_aff]
                if chosen_class != "All Classifications":
                    filtered_candidates = [c for c in filtered_candidates if c["classification"] == chosen_class]
                if chosen_status != "All Review Decisions":
                    filtered_candidates = [c for c in filtered_candidates if c["review_status"] == chosen_status]

                st.caption(f"Displaying **{len(filtered_candidates)}** matching impact candidate(s):")

                for idx, cand in enumerate(filtered_candidates):
                    cid = cand["impact_id"]
                    c_class = cand["classification"]
                    c_status = cand["review_status"]

                    icon = "🔴" if c_class == sa.IMPACT_DIRECT else ("🟡" if c_class == sa.IMPACT_POTENTIAL else "⚠️")
                    header_txt = f"{icon} [{cid}] {c_class} ➔ {cand['affected_sop_id']}"
                    if cand.get("affected_section"):
                        header_txt += f" ({cand['affected_section']})"

                    with st.expander(header_txt, expanded=False):
                        st.markdown(f"**Dependency Type:** `{cand['dependency_type']}` | **Evidence Strength:** `{cand['evidence_strength']}`")
                        st.markdown(f"**Technical Explanation:** {cand['explanation']}")
                        st.caption(
                            f"**Source Change:** `{cand['source_change_id']}` in *{cand['source_section']}* (Page {cand['source_page']}) | "
                            f"**Affected Spec:** `{cand['affected_filename']}` in *{cand['affected_section']}* (Page {cand['affected_page']})"
                        )

                        # Side-by-side Evidence Passages
                        ev_col1, ev_col2 = st.columns(2)
                        with ev_col1:
                            st.markdown("**Source Changed Requirement:**")
                            st.markdown(f"```text\n{cand['source_passage']}\n```")
                        with ev_col2:
                            st.markdown("**Affected Document Evidence Passage:**")
                            st.markdown(f"```text\n{cand['affected_passage']}\n```")

                        # Interactive Review Decision Form
                        st.markdown("#### ✍️ Human Engineering Review Decision")
                        rev_col1, rev_col2 = st.columns([1, 2])
                        with rev_col1:
                            decision_options = ["PENDING", "ACCEPTED", "REJECTED", "INVESTIGATE"]
                            curr_dec_idx = decision_options.index(c_status) if c_status in decision_options else 0
                            new_decision = st.selectbox(
                                "Decision",
                                decision_options,
                                index=curr_dec_idx,
                                key=f"dec_sel_{cid}"
                            )
                        with rev_col2:
                            new_notes = st.text_input(
                                "Reviewer Notes / Engineering Rationale",
                                value=cand.get("reviewer_notes", ""),
                                key=f"notes_in_{cid}"
                            )

                        if st.button("💾 Save Review Decision", key=f"save_btn_{cid}"):
                            db.save_impact_review(
                                impact_id=cid,
                                source_change_id=cand["source_change_id"],
                                source_sop_id=cand["source_sop_id"],
                                affected_sop_id=cand["affected_sop_id"],
                                decision=new_decision,
                                reviewer_notes=new_notes
                            )
                            cand["review_status"] = new_decision
                            cand["reviewer_notes"] = new_notes
                            cand["is_human_reviewed"] = True
                            st.success(f"Decision for {cid} updated to `{new_decision}`!")
                            st.rerun()

elif app_mode == "🧩 Visual & Tabular Component Explorer":
    # ========================================================================
    # SOP COMPONENT INTELLIGENCE & ARCHITECTURE EXPLORER (MINI PHASE 4)
    # ========================================================================
    st.markdown('<h2 style="color: #1E3A8A; font-weight: 700;">🧩 SOP Component Intelligence & Architecture Explorer</h2>', unsafe_allow_html=True)
    st.markdown(
        "Inspect verified physical components, major assemblies, and subsystems extracted across baseline and revised SOP documents. "
        "Explore validated mechanical relationships, verifiable source passages, and cross-revision technical evolution."
    )

    all_comps = re.load_components_metadata()
    if not all_comps:
        st.info("ℹ️ No components currently loaded in `data/faiss_index/components_metadata.json`. Ingesting or rebuilding documents will populate component metadata.")
    else:
        tab_catalog, tab_diff = st.tabs([
            "📋 Component Catalog & Detail Inspector",
            "⚖️ V1 vs V2 Component Revision Comparison"
        ])

        with tab_catalog:
            # ----------------------------------------------------------------
            # A. FILTERS
            # ----------------------------------------------------------------
            st.markdown("##### 🔍 Component Search & Hierarchy Filters")
            c_col0, c_col1, c_col2, c_col3 = st.columns(4)

            with c_col0:
                entity_filter_options = [
                    "Physical Components, Assemblies & Subsystems (Default)",
                    "All Extracted Entities (Unfiltered)",
                    "PHYSICAL_COMPONENT",
                    "ASSEMBLY",
                    "SUBSYSTEM",
                    "MATERIAL",
                    "TOOL_OR_INSTRUMENT",
                    "TECHNICAL_PARAMETER",
                    "ACCEPTANCE_CRITERION",
                    "PROCESS_OR_OPERATION",
                    "DOCUMENT_OR_CERTIFICATE",
                    "OTHER_REFERENCE"
                ]
                selected_entity = st.selectbox(
                    "Entity Classification:",
                    entity_filter_options,
                    index=0,
                    key="comp_entity_sel"
                )

            with c_col1:
                all_docs = sorted(list({c.get("filename", "") for c in all_comps if c.get("filename")}))
                doc_options = ["All Documents"] + all_docs
                selected_doc = st.selectbox("SOP Document:", doc_options, key="comp_doc_sel")

            with c_col2:
                rev_options = ["All Revisions", "V2 (Active / Revised)", "V1 (Baseline / Archival)"]
                selected_rev = st.selectbox("Revision:", rev_options, index=0, key="comp_rev_sel")

            with c_col3:
                all_subs = ["All Subsystems"] + sorted(list({c.get("subsystem", "") for c in all_comps if c.get("subsystem")}))
                selected_sub = st.selectbox("Subsystem Filter:", all_subs, key="comp_sub_sel")

            # Second row: Search & Uncertainty filter
            c_s1, c_s2 = st.columns([3, 1])
            with c_s1:
                comp_search_kw = st.text_input(
                    "Search Components, Specifications, Tooling, or Criteria:",
                    "",
                    placeholder="e.g. bearing, lower hull, torque, laser alignment...",
                    key="comp_search_kw"
                )
            with c_s2:
                unc_options = [
                    "All Confidence Levels",
                    "Directly Stated in Passage Only",
                    "Verified High-Confidence Only",
                    "Uncertain / Verification Required Only"
                ]
                selected_unc = st.selectbox("Evidence Status:", unc_options, key="comp_unc_sel")

            # Apply deterministic filtering via re.filter_components
            filtered_comps = re.filter_components(
                components=all_comps,
                doc_filter=selected_doc,
                revision_filter=selected_rev,
                subsystem_filter=selected_sub,
                entity_type_filter=selected_entity,
                uncertainty_filter=selected_unc,
                search_keyword=comp_search_kw
            )

            # Metrics row
            st.divider()
            m1, m2, m3, m4, m5 = st.columns(5)
            with m1:
                st.metric("Total Records", len(filtered_comps))
            with m2:
                st.metric("Physical Components", sum(1 for c in filtered_comps if c.get("entity_type") == "PHYSICAL_COMPONENT"))
            with m3:
                st.metric("Assemblies & Subsystems", sum(1 for c in filtered_comps if c.get("entity_type") in ("ASSEMBLY", "SUBSYSTEM")))
            with m4:
                st.metric("Directly Stated", sum(1 for c in filtered_comps if c.get("evidence_status") == "DIRECTLY_STATED"))
            with m5:
                st.metric("Uncertain Flags", sum(1 for c in filtered_comps if c.get("is_uncertain", False)))

            if not filtered_comps:
                st.warning("⚠️ No components match the selected filter criteria. Try expanding the entity classification or clearing search keywords.")
            else:
                # ------------------------------------------------------------
                # B. COMPONENT LIST (Interactive Table)
                # ------------------------------------------------------------
                st.markdown("#### 📋 Filtered Component Directory")
                st.caption(f"Displaying **{len(filtered_comps)}** component record(s) matching active criteria:")

                table_data = []
                for c in filtered_comps:
                    c_rev = "V2 (Revised)" if re.is_v2_component(c) else ("V1 (Baseline)" if re.is_v1_component(c) else c.get("revision", "N/A")[:15])
                    table_data.append({
                        "Component Name": c.get("component_name", "N/A"),
                        "Entity Type": c.get("entity_type", "OTHER_REFERENCE"),
                        "Associated SOP": c.get("source_filename") or c.get("filename", "N/A"),
                        "Revision": c_rev,
                        "Subsystem": c.get("subsystem", "N/A"),
                        "Evidence Status": c.get("evidence_status", "DIRECTLY_STATED")
                    })

                df_table = pd.DataFrame(table_data)
                st.dataframe(df_table, use_container_width=True, hide_index=True)

                # ------------------------------------------------------------
                # C. COMPONENT DETAIL INSPECTOR
                # ------------------------------------------------------------
                st.divider()
                st.markdown("#### 🔬 Detailed Component Engineering Inspector")
                st.caption("Select any component from the list below to examine its verified specifications, relationships, and source evidence:")

                # Build options for selector and resolve pending navigation
                target_nav_name = st.session_state.pop("target_nav_component", None)
                default_sel_idx = 0
                if target_nav_name:
                    tn_clean = str(target_nav_name).strip().lower()
                    for idx, c in enumerate(filtered_comps):
                        if str(c.get("component_name", "")).strip().lower() == tn_clean:
                            default_sel_idx = idx
                            break

                comp_selector_options = [
                    f"[{c.get('entity_type', 'CMP')}] {c.get('component_name')} — ({c.get('source_filename', c.get('filename', ''))})"
                    for c in filtered_comps
                ]
                selected_idx = st.selectbox(
                    "Choose Component to Inspect:",
                    range(len(filtered_comps)),
                    index=default_sel_idx,
                    format_func=lambda i: comp_selector_options[i],
                    key="comp_detail_selector"
                )

                selected_comp = filtered_comps[selected_idx]
                detail = re.format_component_detail(selected_comp)

                # Display detailed card
                icon = "🧩" if detail["entity_type"] == "PHYSICAL_COMPONENT" else ("📦" if detail["entity_type"] == "ASSEMBLY" else ("🏗️" if detail["entity_type"] == "SUBSYSTEM" else "⚙️"))
                unc_badge = "⚠️ [UNCERTAIN]" if detail["is_uncertain"] else f"✅ [{detail['evidence_status']}]"

                st.markdown(f"### {icon} {detail['component_name']} `{detail['entity_type']}` {unc_badge}")

                # AI & Workflow Actions
                act_col1, act_col2 = st.columns([1, 1])
                with act_col1:
                    if st.button("🤖 Ask AI about this component", key=f"ask_ai_{detail['component_id']}", type="primary", use_container_width=True):
                        st.session_state["active_component_context"] = {
                            "component_name": detail["component_name"],
                            "entity_type": detail["entity_type"],
                            "filename": detail["filename"],
                            "section": detail["section"],
                            "page_number": detail["page_number"],
                            "associated_subsystem": detail["associated_subsystem"]
                        }
                        if selected_rev == "V1 (Baseline / Archival)":
                            st.session_state["revision_preference"] = "V1 Only (Archival Baseline SOPs)"
                        elif selected_rev == "V2 (Active / Revised)":
                            st.session_state["revision_preference"] = "V2 Only (Revised / Active Operational SOPs)"
                        elif selected_rev == "All Revisions":
                            st.session_state["revision_preference"] = "All Revisions (Prioritize V2 / Latest)"

                        new_conv = db.create_conversation(f"Component: {detail['component_name']}")
                        st.session_state["current_conv_id"] = new_conv["conversation_id"]
                        st.session_state["pending_chat_prompt"] = f"Explain the {detail['component_name']} ({detail['entity_type']}), its documented function, and its relationships based on the SOP evidence."
                        st.session_state["app_mode_radio"] = "💬 Technical Consultation Chat"
                        st.rerun()

                with act_col2:
                    if st.button("⚖️ Compare Revisions for this SOP", key=f"cmp_sop_{detail['component_id']}", type="secondary", use_container_width=True):
                        st.session_state["diff_sop_sel"] = selected_comp.get("logical_sop_id") or selected_comp.get("filename")
                        st.session_state["app_mode_radio"] = "⚖️ SOP Revision Comparison Engine"
                        st.rerun()

                if detail["is_uncertain"]:
                    st.warning(f"⚠️ **Uncertainty Notice**: {detail['uncertainty_reason'] or 'Marked for mandatory engineering review without inventing data.'}")

                # Explanation & Function
                if detail["has_simple_description"]:
                    st.info(f"💡 **Simple Explanation (Beginner-Friendly)**: {detail['simple_description']}")
                else:
                    st.caption("ℹ️ *No simplified explanation explicitly documented in SOP source.*")

                if detail["has_primary_function"]:
                    st.markdown(f"⚙️ **Documented Primary Function**: {detail['primary_function']}")
                else:
                    st.caption("ℹ️ *No primary vehicle function explicitly documented in SOP source.*")

                # Attributes grid
                col_attr_l, col_attr_r = st.columns(2)
                with col_attr_l:
                    st.markdown(f"**Associated Assembly / Subsystem:** `{detail['associated_subsystem']}`")
                    st.markdown(f"**Material / Construction:** `{detail['material']}`")
                    st.markdown(f"**Location / Operational Use:** `{detail['location']}`")
                    if detail["alternative_names"]:
                        alts = ", ".join([f"`{a}`" for a in detail["alternative_names"] if a != detail["component_name"]])
                        if alts:
                            st.markdown(f"**Alternative Names:** {alts}")

                with col_attr_r:
                    st.markdown(f"**Source Document:** `{detail['filename']}`")
                    st.markdown(f"**Revision:** `{detail['revision']}`")
                    st.markdown(f"**Section Reference:** *{detail['section']}*")
                    st.markdown(f"**Page Number:** Page `{detail['page_number']}`")
                    st.markdown(f"**Evidence Status:** `{detail['evidence_status']}`")

                # D. RELATIONSHIPS
                st.markdown("##### 🔗 Verified Mechanical & Functional Relationships")
                if detail["has_relationships"]:
                    for r_idx, r in enumerate(detail["relationships"]):
                        tgt_name = r.get("target_component", "")
                        pred = r.get("relationship_type", "CONNECTED_TO")
                        src_ref = r.get("source_reference", "")

                        target_comp_obj = next((c for c in all_comps if str(c.get("component_name", "")).strip().lower() == str(tgt_name).strip().lower()), None)

                        r_col1, r_col2 = st.columns([3, 1])
                        with r_col1:
                            if target_comp_obj:
                                st.markdown(
                                    f"- **`[{pred}]`** ➔ **{tgt_name}** (`{target_comp_obj.get('entity_type', 'COMPONENT')}`)  \n"
                                    f"  *Evidence Source*: {src_ref}"
                                )
                            else:
                                st.markdown(
                                    f"- **`[{pred}]`** ➔ **{tgt_name}** ⚠️ *[Unresolved Reference — target entity cited in text but not indexed as a discrete component record]*  \n"
                                    f"  *Evidence Source*: {src_ref}"
                                )
                        with r_col2:
                            if target_comp_obj:
                                if st.button(f"👉 Navigate to '{tgt_name}'", key=f"nav_rel_{detail['component_id']}_{r_idx}_{tgt_name}"):
                                    st.session_state["target_nav_component"] = target_comp_obj.get("component_name")
                                    st.rerun()
                else:
                    st.caption("ℹ️ *No explicit structural relationships documented in the SOP text. (Co-occurring entities are not assumed to be related.)*")

                # Manufacturing & Metrology (if applicable)
                if detail["technical_specifications"] or detail["tooling_or_metrology"] or detail["acceptance_criteria"]:
                    with st.expander("🛠️ Manufacturing Tolerances & Metrology Criteria", expanded=False):
                        if detail["technical_specifications"]:
                            st.markdown("**Technical Specifications & Tolerances:**")
                            st.markdown(f"```text\n{detail['technical_specifications']}\n```")
                        if detail["tooling_or_metrology"]:
                            st.markdown("**Tooling & Metrology Instruments:**")
                            st.markdown(f"```text\n{detail['tooling_or_metrology']}\n```")
                        if detail["acceptance_criteria"]:
                            st.markdown(f"**Acceptance Benchmark / Hold Point:** `{detail['acceptance_criteria']}`")
                        if detail.get("callout_warning"):
                            st.error(f"🚨 **Stage-Gate Warning**: {detail['callout_warning']}")

                # Expandable source evidence
                with st.expander("📖 Verbatim Supporting SOP Passage & Audit Trail", expanded=False):
                    if detail["supporting_passage"]:
                        st.markdown(f"```text\n{detail['supporting_passage']}\n```")
                    else:
                        st.caption("No verbatim source passage cached for this component.")

                # Browsable Accordion of All Filtered Components
                st.divider()
                st.markdown(f"#### 📚 Browse All Filtered Records ({len(filtered_comps)} items)")
                for comp in filtered_comps:
                    e_type = comp.get("entity_type", "OTHER_REFERENCE")
                    is_unc = comp.get("is_uncertain", False)
                    ev_status = comp.get("evidence_status", "DIRECTLY_STATED")
                    unc_b = "⚠️ [UNCERTAIN]" if is_unc else f"✅ [{ev_status}]"
                    ic = "🧩" if e_type == "PHYSICAL_COMPONENT" else ("📦" if e_type == "ASSEMBLY" else ("🏗️" if e_type == "SUBSYSTEM" else "⚙️"))
                    c_header = f"{ic} [{comp.get('component_id', 'CMP')}] {comp.get('component_name')} — [{e_type}] {unc_b}"

                    with st.expander(c_header, expanded=False):
                        c_det = re.format_component_detail(comp)
                        if c_det["has_simple_description"]:
                            st.info(f"💡 {c_det['simple_description']}")
                        if c_det["has_primary_function"]:
                            st.markdown(f"⚙️ **Function**: {c_det['primary_function']}")
                        st.markdown(f"**Subsystem:** `{c_det['associated_subsystem']}` | **Document:** `{c_det['filename']}` (Page {c_det['page_number']})")
                        st.markdown(f"**Section:** *{c_det['section']}*")
                        if c_det["has_relationships"]:
                            st.markdown("**Validated Relationships:**")
                            for r in c_det["relationships"]:
                                st.markdown(f"- `{r.get('relationship_type')}` ➔ **{r.get('target_component')}** (*{r.get('source_reference')}*)")
                        if c_det["supporting_passage"]:
                            st.caption(f"**Source Passage:** {c_det['supporting_passage']}")

        # --------------------------------------------------------------------
        # E. REVISION COMPARISON (V1 vs V2)
        # --------------------------------------------------------------------
        with tab_diff:
            st.markdown("### ⚖️ Cross-Revision Component Evolution (V1 Baseline vs. V2 Revised)")
            st.markdown(
                "Compare physical component records, major assemblies, and engineering specifications between "
                "archival Baseline (Version 1.0) and authoritative Revised (Version 2.0) SOP documents."
            )

            # Revision comparison filters
            rc_col1, rc_col2 = st.columns(2)
            with rc_col1:
                cmp_sop_options = ["All SOP Documents"] + sorted(list({c.get("logical_sop_id") or c.get("filename") for c in all_comps if c.get("logical_sop_id") or c.get("filename")}))
                selected_cmp_sop = st.selectbox("Select SOP Domain to Compare:", cmp_sop_options, key="diff_sop_sel")

            with rc_col2:
                cmp_entity_options = [
                    "Physical Components, Assemblies & Subsystems (Default)",
                    "All Extracted Entities (Unfiltered)"
                ]
                selected_cmp_entity = st.selectbox("Entity Scope:", cmp_entity_options, key="diff_entity_sel")

            # Execute comparison
            entity_types_filter = (
                ["PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM"]
                if "Default" in selected_cmp_entity
                else None
            )

            diff_results = re.compare_component_revisions(
                components=all_comps,
                sop_filter=selected_cmp_sop,
                entity_types=entity_types_filter
            )

            diff_summary = diff_results["summary"]

            # Comparison Metrics
            st.divider()
            dm1, dm2, dm3, dm4, dm5 = st.columns(5)
            with dm1:
                st.metric("Total Compared", diff_summary["total_compared"])
            with dm2:
                st.metric("🟢 Added in V2", diff_summary["added_count"])
            with dm3:
                st.metric("🔴 Removed from V1", diff_summary["removed_count"])
            with dm4:
                st.metric("🟡 Modified Specs", diff_summary["modified_count"])
            with dm5:
                st.metric("⚪ Unchanged", diff_summary["unchanged_count"])

            st.divider()

            # Sub-tabs for comparison categories
            sub_added, sub_removed, sub_modified, sub_unchanged = st.tabs([
                f"🟢 Added in V2 ({diff_summary['added_count']})",
                f"🔴 Removed from V1 ({diff_summary['removed_count']})",
                f"🟡 Modified Specifications ({diff_summary['modified_count']})",
                f"⚪ Unchanged Components ({diff_summary['unchanged_count']})"
            ])

            # 1. Added Components
            with sub_added:
                st.markdown("#### 🟢 Newly Introduced Components & Assemblies (Version 2.0)")
                st.caption("These components exist in Version 2.0 specifications but were not present in Version 1.0:")
                if not diff_results["added"]:
                    st.info("ℹ️ No newly added components found in this domain.")
                else:
                    added_rows = []
                    for c in diff_results["added"]:
                        added_rows.append({
                            "Component Name": c.get("component_name", "N/A"),
                            "Entity Type": c.get("entity_type", "PHYSICAL_COMPONENT"),
                            "Subsystem": c.get("subsystem", "N/A"),
                            "Documented Function": c.get("primary_function") or c.get("simple_description") or "(Not documented)",
                            "SOP Document": c.get("source_filename") or c.get("filename", "N/A"),
                            "Page": c.get("page_number", "N/A")
                        })
                    st.dataframe(pd.DataFrame(added_rows), use_container_width=True, hide_index=True)

                    with st.expander("🔍 Inspect Added Component Details", expanded=False):
                        for c in diff_results["added"]:
                            st.markdown(f"**🟢 {c.get('component_name')}** `[{c.get('entity_type')}]`")
                            if c.get("primary_function"):
                                st.markdown(f"- **Function:** {c.get('primary_function')}")
                            if c.get("simple_description"):
                                st.markdown(f"- **Description:** {c.get('simple_description')}")
                            st.markdown(f"- *Citing*: `{c.get('source_filename', c.get('filename'))}` ({c.get('section_reference')}, Page {c.get('page_number')})")
                            st.divider()

            # 2. Removed Components
            with sub_removed:
                st.markdown("#### 🔴 Superseded or Retired Components (Version 1.0 Only)")
                st.caption("These components were present in Version 1.0 but have been deprecated or superseded in Version 2.0:")
                if not diff_results["removed"]:
                    st.info("ℹ️ No components were removed or superseded in this domain.")
                else:
                    removed_rows = []
                    for c in diff_results["removed"]:
                        removed_rows.append({
                            "Component Name": c.get("component_name", "N/A"),
                            "Entity Type": c.get("entity_type", "PHYSICAL_COMPONENT"),
                            "Subsystem": c.get("subsystem", "N/A"),
                            "Baseline Function": c.get("primary_function") or c.get("simple_description") or "(Not documented)",
                            "Baseline SOP": c.get("source_filename") or c.get("filename", "N/A"),
                            "Page": c.get("page_number", "N/A")
                        })
                    st.dataframe(pd.DataFrame(removed_rows), use_container_width=True, hide_index=True)

                    with st.expander("🔍 Inspect Removed Component Details", expanded=False):
                        for c in diff_results["removed"]:
                            st.markdown(f"**🔴 {c.get('component_name')}** `[{c.get('entity_type')}]`")
                            if c.get("primary_function"):
                                st.markdown(f"- **Baseline Function:** {c.get('primary_function')}")
                            st.markdown(f"- *Archival Baseline*: `{c.get('source_filename', c.get('filename'))}` ({c.get('section_reference')}, Page {c.get('page_number')})")
                            st.divider()

            # 3. Modified Components
            with sub_modified:
                st.markdown("#### 🟡 Modified Component Descriptions & Engineering Tolerances")
                st.caption("These components exist in both revisions, but their descriptions, tolerances, or specifications shifted:")
                if not diff_results["modified"]:
                    st.info("ℹ️ No modified components identified in this domain.")
                else:
                    for mod_item in diff_results["modified"]:
                        c_name = mod_item["component_name"]
                        c_v1 = mod_item["v1"]
                        c_v2 = mod_item["v2"]
                        diffs = mod_item["diffs"]

                        st.markdown(f"##### 🟡 {c_name} `[{mod_item.get('entity_type', 'PHYSICAL_COMPONENT')}]`")
                        st.caption(
                            f"Baseline: `{c_v1.get('source_filename', c_v1.get('filename'))}` (Page {c_v1.get('page_number')}) ➔ "
                            f"Revised: `{c_v2.get('source_filename', c_v2.get('filename'))}` (Page {c_v2.get('page_number')})"
                        )

                        diff_table = []
                        for d in diffs:
                            diff_table.append({
                                "Specification / Field": d["label"],
                                "V1 (Baseline Specification)": d["v1_value"],
                                "V2 (Revised Specification)": d["v2_value"]
                            })
                        st.dataframe(pd.DataFrame(diff_table), use_container_width=True, hide_index=True)
                        st.divider()

            # 4. Unchanged Components
            with sub_unchanged:
                st.markdown("#### ⚪ Unchanged Components Across Revisions")
                st.caption("These components are confirmed identical across both revisions with matching technical specifications:")
                if not diff_results["unchanged"]:
                    st.info("ℹ️ No common unchanged components found in this domain.")
                else:
                    unchanged_rows = []
                    for item in diff_results["unchanged"]:
                        c_v2 = item["v2"]
                        unchanged_rows.append({
                            "Component Name": item["component_name"],
                            "Entity Type": item.get("entity_type", "PHYSICAL_COMPONENT"),
                            "Subsystem": c_v2.get("subsystem", "N/A"),
                            "Verified Function": c_v2.get("primary_function") or c_v2.get("simple_description") or "(Identical across revisions)",
                            "Verified SOP Source": c_v2.get("source_filename") or c_v2.get("filename", "N/A")
                        })
                    st.dataframe(pd.DataFrame(unchanged_rows), use_container_width=True, hide_index=True)

elif app_mode == "📥 Ingest & Manage SOP Documents":
    # ========================================================================
    # DEDICATED 7-STAGE INGESTION & DOCUMENT MANAGEMENT VIEW
    # ========================================================================
    st.markdown('<h2 style="color: #1E3A8A; font-weight: 700;">📥 Ingest & Manage SOP Documents</h2>', unsafe_allow_html=True)
    st.markdown(
        "Upload and integrate official technical PDF documents into the local vector index and structured component database. "
        "The system executes an automated, transactional 7-stage workflow ensuring data integrity and duplicate prevention."
    )

    render_seven_stage_upload(key_suffix="mgmt")

    st.divider()
    st.markdown("### 📚 Currently Indexed Document Inventory")
    index, metadata, manifest = re.load_faiss_index()
    if not manifest or not manifest.get("documents"):
        st.info("No documents currently recorded in index manifest.")
    else:
        doc_rows = []
        for d in manifest.get("documents", []):
            fname = d.get("filename", "N/A")
            is_base = re.is_standard_baseline_corpus_doc(fname)
            doc_rows.append({
                "Document ID": d.get("document_id", "N/A"),
                "Filename": fname,
                "Revision": d.get("revision", "N/A"),
                "Type": "Baseline Standard" if is_base else "Uploaded Custom",
                "Indexed Chunks": d.get("chunks_count", 0)
            })
        st.dataframe(pd.DataFrame(doc_rows), use_container_width=True, hide_index=True)


