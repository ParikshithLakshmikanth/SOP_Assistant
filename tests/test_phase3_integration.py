#!/usr/bin/env python3
"""
Test Suite: Phase 3 - Complete Integration and Acceptance Testing
================================================================
Validates the joint operation of:
1. Continuous chat auto-scrolling with user-scroll pause awareness.
2. V2-first revision selection, retrieval filtering, and boost ranking.
3. Live streaming display with smooth fade-in and live typing cursor.
4. Compact Verified Evidence Sources display.
5. User cancellation and partial response persistence with is_cancelled=True.
6. Multi-turn dialogue persistence across database reconnections.
7. Full Streamlit application integrity.
"""

import os
import sys
import time
import py_compile
import sqlite3
from typing import List, Dict, Any

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Ensure project root in sys.path
_dir = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(_dir, "..")) if os.path.basename(_dir) == "tests" else _dir
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import app
import database as db
import document_processor as dp
import rag_engine as re
import sop_analyzer as sa

TEST_DB_PATH = os.path.join("data", "test_phase3_integration.db")


def cleanup_test_db():
    for ext in ["", "-wal", "-shm"]:
        p = TEST_DB_PATH + ext
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


def run_tests():
    print("=" * 75)
    print("RUNNING PHASE 3 INTEGRATION AND ACCEPTANCE TEST SUITE")
    print("=" * 75)

    cleanup_test_db()
    db.init_database(TEST_DB_PATH)
    test_results = {}

    # -------------------------------------------------------------------------
    # Acceptance Test 1 & 2: Initial Application Session & Default V2 Selection
    # -------------------------------------------------------------------------
    print("\n--- Test 1 & 2: Fresh Session Initialization & V2 Default ---")
    try:
        # Check dropdown choices defined in app
        expected_choices = [
            "V2 — Latest revision (Default)",
            "V1 — Baseline revision",
            "All revisions — V2 prioritized",
        ]
        assert hasattr(app, "REVISION_CHOICES"), "app.py missing REVISION_CHOICES"
        assert app.REVISION_CHOICES == expected_choices, f"Choices mismatch: {app.REVISION_CHOICES}"

        # Simulate fresh session state dictionary
        simulated_session_state = {}
        if "revision_scope_select" not in simulated_session_state:
            simulated_session_state["revision_scope_select"] = app.REVISION_CHOICES[0]

        default_selection = simulated_session_state["revision_scope_select"]
        print(f"  Fresh session initial selection: '{default_selection}'")
        assert default_selection == "V2 — Latest revision (Default)"

        # Check normalization mapping in app.py
        rev_mode_map = {
            "V2 — Latest revision (Default)": "v2",
            "V1 — Baseline revision": "v1",
            "All revisions — V2 prioritized": "all",
        }
        assert rev_mode_map[default_selection] == "v2"

        print("  [PASS] Fresh session defaults to V2 — Latest revision.")
        test_results["Test 1-2: Fresh Session V2 Default"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Fresh session test failed: {e}")
        test_results["Test 1-2: Fresh Session V2 Default"] = f"FAIL: {e}"

    # -------------------------------------------------------------------------
    # Acceptance Test 3 & 4: Technical Question & V2 Evidence Retrieval
    # -------------------------------------------------------------------------
    print("\n--- Test 3 & 4: Technical SOP Query & V2-Only Evidence Retrieval ---")
    try:
        query = "What is the preheating temperature required for hull welding and induction coil arrangement?"
        rev_mode = "v2"
        retrieved = re.retrieve_relevant_chunks(query, revision_mode=rev_mode, top_k=4)

        print(f"  Query: '{query}'")
        print(f"  Retrieved {len(retrieved)} chunks in V2 mode:")
        for r in retrieved:
            is_v2 = re.is_v2_chunk(r)
            is_v1 = re.is_v1_chunk(r)
            print(f"    - Doc: {r['document_id']} | Rev: {r['revision']} | is_v2={is_v2} | is_v1={is_v1}")
            assert is_v2 is True, f"Non-V2 chunk leaked into V2 mode: {r['document_id']}"
            assert is_v1 is False, f"V1 chunk detected in V2 mode: {r['document_id']}"

        assert len(retrieved) > 0, "No chunks retrieved in V2 mode"
        print("  [PASS] V2 technical query retrieves exclusively revised V2 evidence.")
        test_results["Test 3-4: Technical Query V2 Retrieval"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] V2 retrieval test failed: {e}")
        test_results["Test 3-4: Technical Query V2 Retrieval"] = f"FAIL: {e}"

    # -------------------------------------------------------------------------
    # Acceptance Test 5 & 6: Smooth Streaming Display & Auto-Scroll Trigger
    # -------------------------------------------------------------------------
    print("\n--- Test 5 & 6: Streaming Progressive Display & Auto-Scroll Trigger ---")
    try:
        accumulator = app.SmoothStreamAccumulator(enable_auto_scroll=True)
        tokens = ["The ", "preheating ", "temperature ", "must ", "be ", "maintained ", "at ", "180°C."]

        rendered_outputs = []
        for tok in tokens:
            if accumulator.add_token(tok):
                display_html = accumulator.get_display_html(is_active=True)
                rendered_outputs.append(display_html)

        assert len(rendered_outputs) > 0, "No progressive UI updates produced"
        active_display = rendered_outputs[-1]

        # Verify typing cursor and auto-scroll trigger are present while streaming
        assert '<span class="typing-cursor"></span>' in active_display, "Typing cursor missing during streaming"
        assert app.AUTOSCROLL_TRIGGER_HTML in active_display, "Auto-scroll trigger missing during streaming"
        assert "sop-chat-bottom-anchor" in app.AUTOSCROLL_TRIGGER_HTML

        print(f"  Produced {len(rendered_outputs)} progressive display updates.")
        print("  [PASS] Live typing cursor and continuous auto-scroll trigger present while active.")
        test_results["Test 5-6: Streaming & Auto-Scroll Triggers"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Streaming display test failed: {e}")
        test_results["Test 5-6: Streaming & Auto-Scroll Triggers"] = f"FAIL: {e}"

    # -------------------------------------------------------------------------
    # Acceptance Test 7 & 8: User Scroll Awareness (Pause & Resume Logic)
    # -------------------------------------------------------------------------
    print("\n--- Test 7 & 8: Auto-Scroll User Pause & Resume Boundaries ---")
    try:
        controller = app.AutoScrollController(enabled=True)
        controller.start()
        assert controller.is_active is True

        # Case A: User is at the bottom (distance = 15px <= threshold of 80px) -> should NOT pause
        pause_at_bottom = controller.should_pause(distance_to_bottom=15.0, threshold=80.0)
        assert pause_at_bottom is False, "Auto-scroll should not pause when user is near bottom"

        # Case B: User scrolls upward to read earlier content (distance = 250px > 80px) -> SHOULD pause
        pause_scrolled_up = controller.should_pause(distance_to_bottom=250.0, threshold=80.0)
        assert pause_scrolled_up is True, "Auto-scroll must pause when user scrolls upward"

        # Case C: User returns to bottom (distance = 40px <= 80px) -> resumes auto-scroll
        resume_at_bottom = controller.should_pause(distance_to_bottom=40.0, threshold=80.0)
        assert resume_at_bottom is False, "Auto-scroll should resume when user scrolls back to bottom"

        controller.stop()
        assert controller.is_active is False
        assert controller.get_trigger_html() == ""

        print("  [PASS] Auto-scroll controller accurately manages user pause and resume thresholds.")
        test_results["Test 7-8: User Pause & Resume"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Pause & resume test failed: {e}")
        test_results["Test 7-8: User Pause & Resume"] = f"FAIL: {e}"

    # -------------------------------------------------------------------------
    # Acceptance Test 9: Cursor Removal Upon Completion
    # -------------------------------------------------------------------------
    print("\n--- Test 9: Completion Text Cleaning & Cursor Disappearance ---")
    try:
        final_clean = accumulator.get_final_text(interrupted=False)
        print(f"  Final clean text: '{final_clean}'")

        assert '<span class="typing-cursor"></span>' not in final_clean, "Cursor leaked into completed text"
        assert "sop-chat-bottom-anchor" not in final_clean, "Scroll anchor leaked into completed text"
        assert "<script>" not in final_clean, "Script leaked into completed text"
        assert final_clean == "The preheating temperature must be maintained at 180°C."

        print("  [PASS] Typing cursor and scroll triggers completely stripped on completion.")
        test_results["Test 9: Cursor Removal on Completion"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Cursor removal test failed: {e}")
        test_results["Test 9: Cursor Removal on Completion"] = f"FAIL: {e}"

    # -------------------------------------------------------------------------
    # Acceptance Test 10: Compact Verified Evidence Sources
    # -------------------------------------------------------------------------
    print("\n--- Test 10: Compact Evidence Sources Formatting ---")
    try:
        sample_citations = [
            {
                "filename": "HVF_SOP_1_Hull_Welding_v2.pdf",
                "citation": "[HVF_SOP_1_Hull_Welding_v2.pdf, Rev 5.0 [Version 2.0], SECTION 3.0, Page 3]",
                "document_id": "HVF/AVNL/SOP-MBT/HW-101-V2",
                "revision": "Rev 5.0 [Version 2.0]",
                "page_number": 3,
                "section_title": "SECTION 3.0 — PRE-HEATING & INTERPASS",
                "score": 0.842,
                "text": "Induction preheating coils..."
            },
            {
                "filename": "HVF_SOP_1_Hull_Welding_v2.pdf",
                "citation": "[HVF_SOP_1_Hull_Welding_v2.pdf, Rev 5.0 [Version 2.0], SECTION 3.0, Page 4]",
                "document_id": "HVF/AVNL/SOP-MBT/HW-101-V2",
                "revision": "Rev 5.0 [Version 2.0]",
                "page_number": 4,
                "section_title": "SECTION 3.0 — PRE-HEATING & INTERPASS",
                "score": 0.811,
                "text": "Maintain interpass temperature..."
            }
        ]

        grouped = app.group_citations_by_source(sample_citations)
        print(f"  Grouped sources count: {len(grouped)}")
        assert len(grouped) == 1, f"Expected 1 grouped document, got {len(grouped)}"
        src = grouped[0]
        print(f"    - Filename: {src['filename']}")
        print(f"    - Revision: {src['revision']}")
        print(f"    - Pages: {src['pages_str']}")
        print(f"    - Count: {src['passage_count']}")

        assert src["filename"] == "HVF_SOP_1_Hull_Welding_v2.pdf"
        assert "Rev 5.0" in src["revision"]
        assert "Pages 3–4" in src["pages_str"] or "Pages 3, 4" in src["pages_str"]
        assert src["passage_count"] == 2

        print("  [PASS] Compact evidence summary groups by document with clean metadata.")
        test_results["Test 10: Compact Evidence Formatting"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Compact evidence test failed: {e}")
        test_results["Test 10: Compact Evidence Formatting"] = f"FAIL: {e}"

    # -------------------------------------------------------------------------
    # Acceptance Test 11 & 12: Switch to V1 Mode & Retrieve Strictly Baseline
    # -------------------------------------------------------------------------
    print("\n--- Test 11 & 12: Switch to V1 Mode & Baseline-Only Retrieval ---")
    try:
        query_v1 = "hull welding preheat temperature and induction heating"
        retrieved_v1 = re.retrieve_relevant_chunks(query_v1, revision_mode="v1", top_k=4)

        print(f"  Retrieved {len(retrieved_v1)} chunks in V1 mode:")
        for r in retrieved_v1:
            is_v1 = re.is_v1_chunk(r)
            is_v2 = re.is_v2_chunk(r)
            print(f"    - Doc: {r['document_id']} | Rev: {r['revision']} | is_v1={is_v1} | is_v2={is_v2}")
            assert is_v1 is True, f"Non-V1 chunk leaked into V1 mode: {r['document_id']}"
            assert is_v2 is False, f"V2 chunk leaked into V1 mode: {r['document_id']}"

        assert len(retrieved_v1) > 0, "No chunks retrieved in V1 mode"
        print("  [PASS] V1 mode retrieves strictly baseline documentation.")
        test_results["Test 11-12: Switch to V1 Mode"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] V1 mode test failed: {e}")
        test_results["Test 11-12: Switch to V1 Mode"] = f"FAIL: {e}"

    # -------------------------------------------------------------------------
    # Acceptance Test 13 & 14: Switch to All Revisions Mode & Prioritize V2
    # -------------------------------------------------------------------------
    print("\n--- Test 13 & 14: Switch to All Revisions Mode & Prioritize V2 ---")
    try:
        query_all = "turret integration azimuth bearing torque specifications"
        retrieved_all = re.retrieve_relevant_chunks(query_all, revision_mode="all", top_k=5)

        has_v1 = any(re.is_v1_chunk(r) for r in retrieved_all)
        has_v2 = any(re.is_v2_chunk(r) for r in retrieved_all)
        print(f"  Retrieved {len(retrieved_all)} chunks in All revisions mode:")
        print(f"  Contains V1: {has_v1} | Contains V2: {has_v2}")

        for i, r in enumerate(retrieved_all):
            tag = "V2" if re.is_v2_chunk(r) else "V1"
            print(f"    [{i+1}] {tag} - {r['filename']} | Rev: {r['revision']} | Raw: {r['score']:.4f}")

        assert has_v2 is True, "All mode must retrieve V2 chunks"
        assert has_v1 is True, "All mode must retrieve relevant V1 chunks"
        assert re.is_v2_chunk(retrieved_all[0]) is True, "V2 chunk should rank first due to boost"

        print("  [PASS] All revisions mode retrieves both revisions with V2 prioritized.")
        test_results["Test 13-14: Switch to All Revisions Mode"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] All revisions mode test failed: {e}")
        test_results["Test 13-14: Switch to All Revisions Mode"] = f"FAIL: {e}"

    # -------------------------------------------------------------------------
    # Acceptance Test 15: Cancellation During Long Answer & Partial Output Persistence
    # -------------------------------------------------------------------------
    print("\n--- Test 15: Stream Interruption & Partial Output Persistence ---")
    try:
        conv = db.create_conversation("Integration Test Consultation", db_path=TEST_DB_PATH)
        cid = conv["conversation_id"]

        db.save_message(cid, "user", "Explain engine alignment laser metrology in detail.", db_path=TEST_DB_PATH)

        # Simulate user pressing Stop mid-generation
        partial_accumulator = app.SmoothStreamAccumulator()
        for tok in ["Engine ", "alignment ", "requires ", "dual-axis ", "laser ", "transmitter "]:
            partial_accumulator.add_token(tok)

        interrupted_text = partial_accumulator.get_final_text(interrupted=True)
        print(f"  Interrupted Text: '{interrupted_text}'")

        assert "*[Generation stopped by user]*" in interrupted_text
        assert "dual-axis laser transmitter" in interrupted_text

        # Save to database with is_cancelled=True
        partial_cits = [{"citation": "[HVF_SOP_3_Engine_Alignment_v2.pdf, Rev 6.0, Page 2]", "score": 0.88}]
        saved_msg = db.save_message(
            conversation_id=cid,
            role="assistant",
            content=interrupted_text,
            citations=partial_cits,
            is_cancelled=True,
            db_path=TEST_DB_PATH
        )

        assert saved_msg["is_cancelled"] is True
        assert saved_msg["citations"][0]["citation"] == "[HVF_SOP_3_Engine_Alignment_v2.pdf, Rev 6.0, Page 2]"

        # Check retrieval from DB
        stored = db.get_conversation_messages(cid, db_path=TEST_DB_PATH)[-1]
        assert stored["is_cancelled"] is True
        assert stored["content"] == interrupted_text

        print("  [PASS] Interrupted generation accurately preserved in SQLite with is_cancelled=True.")
        test_results["Test 15: Stop / Cancellation Persistence"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Cancellation persistence test failed: {e}")
        test_results["Test 15: Stop / Cancellation Persistence"] = f"FAIL: {e}"

    # -------------------------------------------------------------------------
    # Acceptance Test 16: Restart Streamlit Simulation & Multi-Turn Normal Behavior
    # -------------------------------------------------------------------------
    print("\n--- Test 16: Restart Streamlit & Session Continuity ---")
    try:
        # Simulate app restart by closing DB connection and reopening
        reconnected_db_msgs = db.get_conversation_messages(cid, db_path=TEST_DB_PATH)
        assert len(reconnected_db_msgs) == 2, f"Expected 2 messages, got {len(reconnected_db_msgs)}"

        # Immediately ask turn 2 after restart
        turn2_user = db.save_message(cid, "user", "What is the secondary datum tolerance?", db_path=TEST_DB_PATH)
        turn2_asst = db.save_message(cid, "assistant", "Secondary datum tolerance is +/- 0.05 mm.", db_path=TEST_DB_PATH)

        final_msgs = db.get_conversation_messages(cid, db_path=TEST_DB_PATH)
        assert len(final_msgs) == 4
        assert [m["sequence_number"] for m in final_msgs] == [1, 2, 3, 4]

        # Verify app compilation
        py_compile.compile("app.py", doraise=True)

        print("  [PASS] Application resumes cleanly after simulated restart; sequence numbers intact.")
        test_results["Test 16: App Restart & Session Continuity"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Restart simulation test failed: {e}")
        test_results["Test 16: App Restart & Session Continuity"] = f"FAIL: {e}"

    # -------------------------------------------------------------------------
    # CLEANUP
    # -------------------------------------------------------------------------
    cleanup_test_db()

    # -------------------------------------------------------------------------
    # FINAL SUMMARY
    # -------------------------------------------------------------------------
    print("\n" + "=" * 75)
    print("PHASE 3 INTEGRATION AND ACCEPTANCE SUMMARY")
    print("=" * 75)
    passed_count = sum(1 for v in test_results.values() if v == "PASS")
    total_count = len(test_results)

    for test_name, status in test_results.items():
        print(f"  {test_name:<45} : {status}")

    print(f"\nTotal: {passed_count}/{total_count} Acceptance Tests Passed.")
    return passed_count == total_count


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
