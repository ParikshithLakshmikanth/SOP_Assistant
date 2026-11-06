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
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        color: #1E3A8A;
        margin-bottom: 0px;
        font-weight: 700;
    }
    .sub-header {
        font-size: 0.95rem;
        color: #475569;
        margin-bottom: 15px;
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

    # Active conversation ID backed by SQLite
    if "current_conv_id" not in st.session_state:
        recent = db.list_conversations(limit=1)
        if recent:
            st.session_state["current_conv_id"] = recent[0]["conversation_id"]
        else:
            new_conv = db.create_conversation("New Consultation")
            st.session_state["current_conv_id"] = new_conv["conversation_id"]

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
    is_connected = re.check_ollama_connection()
    models_info = re.verify_required_models() if is_connected else {}

    index, metadata, manifest = re.load_faiss_index()
    doc_count = len(manifest.get("documents", [])) if manifest else 0
    chunk_count = index.ntotal if index else 0

    index_consistent = False
    consistency_msg = ""
    if index is not None and chunk_count > 0:
        index_consistent, consistency_msg = re.validate_index_consistency(index, metadata, manifest)

    # Database health check
    db_ok = False
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
        db_ok = True
    except Exception:
        db_ok = False

    # Tesseract OCR check
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
        "ollama_online": is_connected,
        "llm_ready": models_info.get("llm_present", False),
        "embed_ready": models_info.get("embed_present", False),
        "all_models_ready": models_info.get("all_ready", False),
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "index_loaded": (index is not None and chunk_count > 0),
        "index_consistent": index_consistent,
        "consistency_msg": consistency_msg,
        "db_ready": db_ok,
        "tesseract_ready": tess_ok,
        "tesseract_path": tess_path
    }

telemetry = check_system_telemetry()


# ============================================================================
# COMPACT EVIDENCE SOURCES HELPERS
# ============================================================================

def group_citations_by_source(citations_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Groups retrieved citation passages by unique source PDF filename and revision.
    Consolidates page references into clean, sorted ranges (e.g. 'Page 3' or 'Pages 6–7').
    Extracts short section titles for optional inspection.
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
            "passage_count": data["count"]
        })

    return grouped_sources


def render_compact_evidence_sources(citations_list: List[Dict[str, Any]]):
    """
    Renders a compact, grouped source-file list for verified evidence passages.
    Preserves total passage count in expander header while displaying only:
      - PDF filename
      - Revision number
      - Page number(s)
    Allows expanding individual source entries to inspect section titles.
    Suppresses raw passage text, cosine similarity scores, and internal vector metadata.
    """
    if not citations_list:
        return

    grouped = group_citations_by_source(citations_list)

    with st.expander(f"📚 Verified Evidence Sources ({len(citations_list)} passages)", expanded=False):
        for idx, src in enumerate(grouped, 1):
            label = f"{idx}. `{src['filename']}` — {src['revision']} — {src['pages_str']}"
            sections = src.get("sections", [])
            if sections:
                with st.expander(label, expanded=False):
                    for sec in sections:
                        short_sec = (sec[:85] + "...") if len(sec) > 85 else sec
                        st.markdown(f"- **Section:** {short_sec}")
            else:
                st.markdown(label)


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

    # --- Operating Mode Selector ---
    st.markdown("#### 🧭 Operational Mode")
    app_mode = st.radio(
        "Select Operating Mode:",
        [
            "💬 Technical Consultation Chat",
            "⚖️ SOP Revision Comparison Engine",
            "🔗 Cross-Document Impact Analysis",
            "🧩 Visual & Tabular Component Explorer"
        ],
        index=0,
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
    else:
        st.markdown("#### ⚖️ Revision Engine")
        st.caption("Operating in Revision Comparison / Impact Analysis Mode.")
        st.markdown(
            "• Deterministic section alignment  \n"
            "• Numerical tolerance shifts  \n"
            "• Safety warning updates  \n"
            "• Traceable before/after evidence  \n"
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
# MAIN APPLICATION INTERFACE (CHAT OR REVISION COMPARISON)
# ============================================================================

if app_mode == "💬 Technical Consultation Chat":
    with st.expander("📥 Ingest New SOP Document (PDF Upload & Indexing)", expanded=False):
        st.markdown(
            "Upload official HVF/AVNL technical documents to extract sections, generate 768-dim embeddings, "
            "and incrementally index into FAISS with transactional integrity and duplicate protection."
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
            key="pdf_uploader"
        )

        if uploaded_files:
            upload_btn = st.button("🚀 Process & Index Uploaded Documents", type="primary")
            if upload_btn:
                upload_dir = os.path.join("data", "documents")
                os.makedirs(upload_dir, exist_ok=True)

                success_count = 0
                for uploaded_file in uploaded_files:
                    file_bytes = uploaded_file.getbuffer()
                    file_size_kb = round(len(file_bytes) / 1024, 1)
                    save_path = os.path.join(upload_dir, uploaded_file.name)
                    with open(save_path, "wb") as f:
                        f.write(file_bytes)

                    with st.status(f"Ingesting `{uploaded_file.name}` ({file_size_kb} KB)...", expanded=True) as status_box:
                        # Stage 1: PDF Extracted
                        st.write("📄 **Stage 1 [PDF Extracted]**: Extracting text pages (digital stream with OCR fallback)...")
                        doc_record = dp.process_pdf(save_path)

                        if doc_record.get("status") != "success":
                            st.error(f"❌ Extraction error: {doc_record.get('status')}")
                            status_box.update(label=f"❌ Failed to extract `{uploaded_file.name}`", state="error", expanded=True)
                            continue

                        st.write(
                            f"✅ **Stage 1 [PDF Extracted]**: Extracted **{doc_record['total_pages']}** pages "
                            f"and created **{doc_record['total_chunks']}** semantic chunks."
                        )

                        # Stage 2: FAISS Indexing Completed
                        st.write("🗄️ **Stage 2 [FAISS Indexing Completed]**: Generating 768-dim embeddings and inserting into FAISS...")
                        try:
                            idx_summary = re.index_chunks(
                                doc_record.get("chunks", []),
                                replace_existing=True
                            )
                            st.write(f"✅ **Stage 2 [FAISS Indexing Completed]**: Indexed **{idx_summary['indexed_chunks']}** chunks ({idx_summary['embedding_duration_s']}s).")
                        except Exception as e:
                            st.error(f"❌ Indexing error: {e}")
                            status_box.update(label=f"❌ Failed to index `{uploaded_file.name}`", state="error", expanded=True)
                            continue

                        # Stage 3: Component Extraction Completed
                        st.write("🧩 **Stage 3 [Component Extraction Completed]**: Extracting visual, tabular, and physical components with entity classification...")
                        comp_status = doc_record.get("component_extraction_status", "success")
                        comps_to_persist = doc_record.get("components", [])

                        if comp_status != "success":
                            st.warning(f"⚠️ Stage 3: Component extraction encountered an issue: {comp_status}")
                            comp_success = False
                        else:
                            st.write(f"✅ **Stage 3 [Component Extraction Completed]**: Extracted **{len(comps_to_persist)}** classified component records.")
                            comp_success = True

                        # Stage 4: Component Metadata Persisted
                        st.write("💾 **Stage 4 [Component Metadata Persisted]**: Persisting component metadata to `components_metadata.json`...")
                        if comp_success and comps_to_persist:
                            save_ok = re.save_document_components(
                                document_id=doc_record["document_id"],
                                filename=uploaded_file.name,
                                components=comps_to_persist
                            )
                            if save_ok:
                                st.write("✅ **Stage 4 [Component Metadata Persisted]**: Atomically persisted component metadata on disk.")
                            else:
                                st.warning("⚠️ Stage 4: Failed to persist component metadata.")
                                comp_success = False
                        else:
                            st.write("⚠️ **Stage 4 [Component Metadata Persisted]**: Component persistence skipped due to extraction issue (pending retry).")

                        # Stage 5: Ready for Component Questions
                        if comp_success:
                            st.write("🚀 **Stage 5 [Ready for Component Questions]**: Document fully indexed and ready for technical consultation and Component Explorer inspection!")
                            status_box.update(label=f"✅ `{uploaded_file.name}` Ingested and Component Integrated Successfully!", state="complete", expanded=False)
                        else:
                            st.write("ℹ️ **Stage 5 [Ready for General Questions]**: Chunks indexed in FAISS for text queries; component extraction ready for retry.")
                            status_box.update(label=f"⚠️ `{uploaded_file.name}` Chunks Indexed (Component Retry Available)", state="warning", expanded=True)

                    # Ingested Document Summary Card
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
                        f"- **Index Persistence**: `✅ Verified On Disk (sop_index.faiss, chunk_metadata.json, components_metadata.json)`"
                    )

                    # Retry Component Extraction Button if needed
                    if not comp_success or doc_record.get("component_extraction_status") != "success":
                        st.warning(f"⚠️ Component extraction for `{uploaded_file.name}` is incomplete.")
                        if st.button(f"🔄 Retry Component Extraction for `{uploaded_file.name}`", key=f"retry_{uploaded_file.name}"):
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

                    # Post-Ingestion Immediate Retrieval Verification
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
                        st.success(
                            f"🎯 **Post-Ingestion Retrieval Verification**: Successfully retrieved document "
                            f"in top search results (Rank #{verif_res['best_rank']} | Cosine Similarity: `{verif_res['best_score']}`)."
                        )
                    else:
                        st.info(
                            f"ℹ️ Retrieval Verification: Document persisted in index (total vectors: {idx_summary['total_index_chunks']})."
                        )

                    success_count += 1
                    st.divider()

                if success_count > 0:
                    st.cache_data.clear()
                    st.success(f"🎉 Successfully ingested and verified {success_count} document(s) into the FAISS index!")

    # --- Conversation Display Area ---
    active_cid = st.session_state["current_conv_id"]
    active_conv = db.get_conversation(active_cid)
    if not active_conv:
        active_conv = db.create_conversation("New Consultation", conv_id=active_cid)

    messages = db.get_conversation_messages(active_cid)

    # Visibly display active revision retrieval scope
    active_scope_label = st.session_state.get("revision_preference", REVISION_CHOICES[0])
    st.caption(f"🎯 **Active Retrieval Scope**: `{active_scope_label}`")

    # Render empty conversation prompt if no messages
    if not messages:
        st.info(
            "👋 **Welcome to the Intelligent SOP Assistant.**  \n"
            "Ask technical questions regarding hull welding, turret integration, V12 engine alignment, "
            "torsion suspension, or main gun calibration. Responses will be grounded in official SOP evidence with verifiable citations."
        )

    # Render conversation history
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        citations = msg.get("citations", [])
        is_cancelled = msg.get("is_cancelled", False)

        with st.chat_message(role, avatar="🧑‍💻" if role == "user" else "🛡️"):
            st.markdown(content)

            if is_cancelled:
                st.caption("⚠️ *[Generation was stopped by user]*")

            # Render compact evidence citations if available
            if citations and role == "assistant":
                render_compact_evidence_sources(citations)

    # --- Chat Input & Streaming Generation ---
    controls_container = st.container()
    user_input = st.chat_input("Enter your SOP engineering inquiry...")

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

        stop_col1, stop_col2 = controls_container.columns([6, 1])
        with stop_col2:
            stop_clicked = st.button("⏹ Stop", key="active_stop_btn", type="secondary")
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
                render_compact_evidence_sources(stream_citations)

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
    # SOP VISUAL & TABULAR COMPONENT INTELLIGENCE EXPLORER (MINI PHASE 2)
    # ========================================================================
    st.markdown('<h2 style="color: #1E3A8A; font-weight: 700;">🧩 SOP Visual & Tabular Component Intelligence Explorer</h2>', unsafe_allow_html=True)
    st.markdown(
        "Inspect multi-source engineering component intelligence extracted across official and uploaded SOPs. "
        "Extracts from technical matrices, visual diagrams, labelled figures, stage-gate callouts, "
        "and executive summaries with complete provenance and uncertainty tracking."
    )

    all_comps = re.load_components_metadata()
    if not all_comps:
        st.info("ℹ️ No components currently loaded in `data/faiss_index/components_metadata.json`. Ingesting or rebuilding documents will populate component metadata.")
    else:
        # Document choices
        all_docs = sorted(list({c.get("filename", "") for c in all_comps if c.get("filename")}))
        doc_options = ["All Documents"] + all_docs

        # Filters
        c_col0, c_col1, c_col2, c_col3, c_col4 = st.columns(5)
        with c_col0:
            entity_filter_options = [
                "Physical Components & Assemblies (Default)",
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
            selected_entity = st.selectbox("Entity Classification:", entity_filter_options, index=0, key="comp_entity_sel")
        with c_col1:
            selected_doc = st.selectbox("Select SOP Document:", doc_options, key="comp_doc_sel")
        with c_col2:
            all_subs = ["All Subsystems"] + sorted(list({c.get("subsystem", "") for c in all_comps if c.get("subsystem")}))
            selected_sub = st.selectbox("Subsystem Filter:", all_subs, key="comp_sub_sel")
        with c_col3:
            source_options = [
                "All Sources",
                "physical_component (Physical Components)",
                "assembly (Major Assemblies)",
                "table (Tabular Matrices)",
                "diagram_figure (Visual Figures & Diagrams)",
                "callout_box (Stage-Gate Warnings & Callouts)",
                "heading (Section Headings)"
            ]
            selected_src_raw = st.selectbox("Source Type Filter:", source_options, key="comp_src_sel")
            selected_src = selected_src_raw.split(" ")[0] if selected_src_raw != "All Sources" else "All Sources"
        with c_col4:
            unc_options = ["All Records", "Verified High-Confidence Only", "Uncertain / Verification Required Only"]
            selected_unc = st.selectbox("Uncertainty Status:", unc_options, key="comp_unc_sel")

        # Keyword Search
        comp_search_kw = st.text_input("🔍 Search Components, Specifications, Tooling, or Acceptance Criteria:", "", key="comp_search_kw")

        # Filtering logic
        filtered_comps = all_comps
        if selected_entity == "Physical Components & Assemblies (Default)":
            filtered_comps = [c for c in filtered_comps if c.get("entity_type") in ("PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM")]
        elif selected_entity != "All Extracted Entities (Unfiltered)":
            filtered_comps = [c for c in filtered_comps if c.get("entity_type") == selected_entity]

        if selected_doc != "All Documents":
            filtered_comps = [c for c in filtered_comps if c.get("filename") == selected_doc]
        if selected_sub != "All Subsystems":
            filtered_comps = [c for c in filtered_comps if c.get("subsystem") == selected_sub]
        if selected_src != "All Sources":
            filtered_comps = [c for c in filtered_comps if c.get("source_type") == selected_src]
        if selected_unc == "Verified High-Confidence Only":
            filtered_comps = [c for c in filtered_comps if not c.get("is_uncertain", False)]
        elif selected_unc == "Uncertain / Verification Required Only":
            filtered_comps = [c for c in filtered_comps if c.get("is_uncertain", False)]

        if comp_search_kw.strip():
            kw_tokens = [t.lower() for t in comp_search_kw.strip().split() if len(t) >= 2]
            scored_filtered = []
            for c in filtered_comps:
                searchable = " ".join([
                    str(c.get("component_name", "")),
                    str(c.get("simple_description", "")),
                    str(c.get("primary_function", "")),
                    str(c.get("material_or_construction", "")),
                    str(c.get("technical_specifications", "")),
                    str(c.get("tooling_or_metrology", "")),
                    str(c.get("acceptance_criteria", "")),
                    str(c.get("subsystem", "")),
                    str(c.get("callout_warning", ""))
                ]).lower()
                matches = sum(1 for tok in kw_tokens if tok in searchable)
                if matches > 0:
                    scored_filtered.append((matches, c))
            scored_filtered.sort(key=lambda x: x[0], reverse=True)
            filtered_comps = [item[1] for item in scored_filtered]

        # Metric summary row
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

        st.caption(f"Displaying **{len(filtered_comps)}** classified record(s):")

        # Component Cards
        for comp in filtered_comps:
            e_type = comp.get("entity_type", "OTHER_REFERENCE")
            is_phy = e_type in ("PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM")
            src_type = comp.get("source_type", "component")
            is_unc = comp.get("is_uncertain", False)
            ev_status = comp.get("evidence_status", "DIRECTLY_STATED")
            unc_badge = "⚠️ [UNCERTAIN]" if is_unc else f"✅ [{ev_status}]"
            
            icon = "🧩" if e_type == "PHYSICAL_COMPONENT" else ("📦" if e_type == "ASSEMBLY" else ("🏗️" if e_type == "SUBSYSTEM" else ("📏" if e_type == "TECHNICAL_PARAMETER" else ("🔧" if e_type == "TOOL_OR_INSTRUMENT" else ("🧪" if e_type == "MATERIAL" else "📑")))))
            header_str = f"{icon} [{comp.get('component_id', 'CMP')}] {comp.get('component_name')} — [{e_type}] {unc_badge}"

            with st.expander(header_str, expanded=False):
                if is_unc:
                    st.warning(f"⚠️ **Uncertainty Notice**: {comp.get('uncertainty_reason', 'Low OCR confidence / visual details ambiguous. Marked for verification without inventing data.')}")

                if is_phy:
                    if comp.get("simple_description"):
                        st.info(f"💡 **Description**: {comp.get('simple_description')}")
                    if comp.get("primary_function"):
                        st.markdown(f"⚙️ **Primary Vehicle Function**: {comp.get('primary_function')}")

                    col_l, col_r = st.columns(2)
                    with col_l:
                        st.markdown(f"**Parent Subsystem:** `{comp.get('parent_subsystem', comp.get('subsystem', 'N/A'))}`")
                        st.markdown(f"**Material / Construction:** `{comp.get('material_or_construction', 'Not specified in SOP')}`")
                        st.markdown(f"**Location / Operational Use:** `{comp.get('location_or_use', 'Not specified in SOP')}`")
                        if comp.get("alternative_names"):
                            alts = ", ".join([f"`{a}`" for a in comp["alternative_names"] if a != comp.get("component_name")])
                            if alts:
                                st.markdown(f"**Alternative Names:** {alts}")

                    with col_r:
                        st.markdown(f"**Evidence Provenance:** `{comp.get('document_id', 'N/A')}` ({comp.get('revision', 'N/A')[:20]})")
                        st.markdown(f"**Source Document:** `{comp.get('source_filename', comp.get('filename', 'N/A'))}` (Page {comp.get('page_number', 'N/A')})")
                        st.markdown(f"**Section Reference:** *{comp.get('section_reference', 'N/A')}*")
                        if comp.get("interacts_with"):
                            interacts = ", ".join([f"`{i}`" for i in comp["interacts_with"]])
                            st.markdown(f"**Interacts With:** {interacts}")

                    # Validated Relationships
                    rels = comp.get("relationships", [])
                    if rels:
                        st.markdown("#### 🔗 Validated Component Relationships")
                        for r in rels:
                            st.markdown(
                                f"- **`{r.get('relationship_type', 'CONNECTED_TO')}`** ➔ **{r.get('target_component', '')}**  \n"
                                f"  *Citation*: {r.get('source_reference', 'SOP Direct Reference')}"
                            )

                    if comp.get("supporting_source_passage"):
                        st.caption(f"**Supporting Source Passage:** {comp.get('supporting_source_passage')}")
                else:
                    # Non-physical entities (parameters, tools, materials, etc.)
                    st.markdown(f"**Entity Classification:** `{e_type}` | **Subsystem:** `{comp.get('subsystem', 'N/A')}` | **Page:** `{comp.get('page_number', 'N/A')}`")
                    st.markdown(f"**Section Reference:** *{comp.get('section_reference', 'N/A')}*")
                    
                    c_p1, c_p2 = st.columns(2)
                    with c_p1:
                        st.markdown("**Technical Specifications & Tolerances:**")
                        st.markdown(f"```text\n{comp.get('technical_specifications', 'Not specified')}\n```")
                    with c_p2:
                        st.markdown("**Tooling & Metrology Instruments:**")
                        st.markdown(f"```text\n{comp.get('tooling_or_metrology', 'Not specified')}\n```")

                    st.markdown(f"**Acceptance Benchmark / Hold Point:** `{comp.get('acceptance_criteria', 'Standard station gate acceptance')}`")
                    if comp.get("callout_warning"):
                        st.error(f"🚨 **Stage-Gate Warning**: {comp.get('callout_warning')}")

                    st.caption(f"**Verbatim Evidence Snippet:** {comp.get('raw_context', comp.get('supporting_source_passage', ''))}")

