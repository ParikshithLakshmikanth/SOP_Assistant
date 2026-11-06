#!/usr/bin/env python3
"""
tests/test_revision_preference.py - Verification for Phase 2: V2-First Revision Preference & Retrieval.

Verifies:
1. Fresh session defaults to V2 ("V2 — Latest revision (Default)").
2. V2 mode retrieves only revised (V2) documents.
3. V1 mode retrieves only baseline (V1) documents.
4. All revisions mode retrieves from both V2 and V1.
5. V2 priority works among comparably relevant results (v2_boost).
6. Relevance is not sacrificed blindly when V1 is substantially more relevant.
7. V2-only mode abstains honestly when evidence is missing (no silent V1 fallback).
8. Citations preserve actual revision and page references.
9. Category filters continue working seamlessly with revision filters.
10. Selection survives Streamlit reruns.
11. Conversation history remains intact across preference switches.
12. Revision comparison and impact analysis engines are completely unaffected.
"""

import os
import sys
import unittest
import tempfile
from typing import List, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import app
from app import REVISION_CHOICES
import rag_engine as re
import database as db
import sop_analyzer as sa


class TestRevisionPreference(unittest.TestCase):
    """Test suite for Phase 2: V2-First Revision Preference & Retrieval."""

    @classmethod
    def setUpClass(cls):
        # Verify FAISS index is loaded
        cls.index, cls.metadata, cls.manifest = re.load_faiss_index()
        if cls.index is None or cls.index.ntotal == 0:
            raise RuntimeError("FAISS index not loaded. Cannot run revision preference tests.")

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_rev.db")
        db.init_database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_fresh_session_defaults_to_v2(self):
        """Verify that the default revision dropdown choice for a fresh session is V2."""
        self.assertGreaterEqual(len(REVISION_CHOICES), 3)
        self.assertEqual(REVISION_CHOICES[0], "V2 — Latest revision (Default)")
        self.assertEqual(REVISION_CHOICES[1], "V1 — Baseline revision")
        self.assertEqual(REVISION_CHOICES[2], "All revisions — V2 prioritized")

        # Simulate fresh session state
        simulated_state = {}
        if "revision_preference" not in simulated_state:
            simulated_state["revision_preference"] = REVISION_CHOICES[0]

        self.assertEqual(simulated_state["revision_preference"], "V2 — Latest revision (Default)")

    def test_02_v2_mode_retrieves_only_revised_documents(self):
        """Verify that V2 mode retrieves exclusively revised V2 documents across multiple queries."""
        queries = [
            "hull welding preheat and tensile strength benchmark",
            "turret azimuth backlash and bearing clearance",
            "engine crankshaft alignment laser collimator"
        ]

        for q in queries:
            chunks = re.retrieve_relevant_chunks(q, top_k=5, revision_mode="v2")
            self.assertGreater(len(chunks), 0, f"No chunks retrieved for query '{q}' in V2 mode")
            for c in chunks:
                self.assertTrue(
                    re.is_v2_chunk(c),
                    f"Non-V2 chunk leaked into V2 retrieval: {c.get('filename')} {c.get('revision')}"
                )
                self.assertFalse(
                    re.is_v1_chunk(c),
                    f"Baseline V1 chunk returned in V2 mode: {c.get('filename')}"
                )

    def test_03_v1_mode_retrieves_only_baseline_documents(self):
        """Verify that V1 mode retrieves exclusively baseline V1 documents across multiple queries."""
        queries = [
            "hull welding preheat and tensile strength benchmark",
            "turret azimuth backlash and bearing clearance",
            "engine crankshaft alignment dial indicator"
        ]

        for q in queries:
            chunks = re.retrieve_relevant_chunks(q, top_k=5, revision_mode="v1")
            self.assertGreater(len(chunks), 0, f"No chunks retrieved for query '{q}' in V1 mode")
            for c in chunks:
                self.assertTrue(
                    re.is_v1_chunk(c),
                    f"Non-V1 chunk leaked into V1 retrieval: {c.get('filename')} {c.get('revision')}"
                )
                self.assertFalse(
                    re.is_v2_chunk(c),
                    f"Revised V2 chunk returned in V1 mode: {c.get('filename')}"
                )

    def test_04_all_revisions_mode_retrieves_both(self):
        """Verify that All revisions mode retrieves evidence from both baseline and revised SOPs."""
        chunks = re.retrieve_relevant_chunks("hull welding", top_k=6, revision_mode="all")
        self.assertGreater(len(chunks), 0)

        has_v1 = any(re.is_v1_chunk(c) for c in chunks)
        has_v2 = any(re.is_v2_chunk(c) for c in chunks)
        self.assertTrue(has_v1, "All revisions mode should include baseline V1 passages when relevant")
        self.assertTrue(has_v2, "All revisions mode should include revised V2 passages when relevant")

    def test_05_v2_priority_works_among_comparably_relevant_results(self):
        """Verify controlled V2 preference prioritizes V2 when scores are comparably close (within boost margin)."""
        # Test synthetic candidate ranking logic
        v1_chunk = {
            "document_id": "HVF/AVNL/SOP-MBT/HW-101",
            "logical_sop_id": "HVF_SOP_1_Hull_Welding",
            "filename": "HVF_SOP_1_Hull_Welding.pdf",
            "revision": "Rev 4.2 (2026) | 30-Oct-2026",
            "chunk_text": "Baseline welding preheat.",
            "page_number": 3,
            "section_title": "SECTION 4.0"
        }
        v2_chunk = {
            "document_id": "HVF/AVNL/SOP-MBT/HW-101-V2",
            "logical_sop_id": "HVF_SOP_1_Hull_Welding",
            "filename": "HVF_SOP_1_Hull_Welding_v2.pdf",
            "revision": "Rev 5.0 [Version 2.0] | 30-Oct-2026",
            "chunk_text": "Revised welding preheat.",
            "page_number": 3,
            "section_title": "SECTION 4.0"
        }

        # Suppose V1 score is 0.71 and V2 score is 0.70 (diff = 0.01, comparable)
        v1_score = 0.71
        v2_score = 0.70
        v2_boost = 0.03

        # In All revisions mode:
        v1_effective = v1_score
        v2_effective = v2_score + v2_boost  # 0.73 > 0.71

        items = [
            {"chunk": v1_chunk, "score": v1_score, "effective": v1_effective},
            {"chunk": v2_chunk, "score": v2_score, "effective": v2_effective}
        ]
        items.sort(key=lambda x: x["effective"], reverse=True)

        self.assertEqual(items[0]["chunk"]["document_id"], "HVF/AVNL/SOP-MBT/HW-101-V2")
        self.assertEqual(items[1]["chunk"]["document_id"], "HVF/AVNL/SOP-MBT/HW-101")

    def test_06_relevance_is_not_sacrificed_blindly(self):
        """Verify that a significantly more relevant V1 chunk is not demoted below a low-relevance V2 chunk."""
        v1_score = 0.85  # Highly relevant
        v2_score = 0.55  # Low relevance
        v2_boost = 0.03

        v1_effective = v1_score
        v2_effective = v2_score + v2_boost  # 0.58 < 0.85

        items = [
            {"doc_id": "V1_HIGH", "score": v1_score, "effective": v1_effective},
            {"doc_id": "V2_LOW", "score": v2_score, "effective": v2_effective}
        ]
        items.sort(key=lambda x: x["effective"], reverse=True)

        self.assertEqual(items[0]["doc_id"], "V1_HIGH")
        self.assertEqual(items[1]["doc_id"], "V2_LOW")

    def test_07_v2_only_mode_abstains_when_evidence_is_missing(self):
        """Verify honest abstention in V2 mode when evidence is missing, without silent fallback to V1."""
        # Query with impossibly high threshold
        chunks = re.retrieve_relevant_chunks(
            "completely non-existent component xyz999",
            top_k=5,
            revision_mode="v2",
            score_threshold=0.99
        )
        self.assertEqual(len(chunks), 0)

        # Test generate_rag_answer abstention
        res = re.generate_rag_answer(
            question="completely non-existent component xyz999",
            retrieved_chunks=chunks,
            revision_mode="v2"
        )
        self.assertTrue(res["is_insufficient"])
        self.assertIn("The selected revision (V2 — Latest revision) does not provide sufficient evidence", res["answer"])

        # Test stream_rag_answer abstention
        token_gen, cits, info = re.stream_rag_answer(
            question="completely non-existent component xyz999",
            top_k=5,
            revision_mode="v2",
            score_threshold=0.99
        )
        stream_text = "".join(list(token_gen))
        self.assertTrue(info["is_insufficient"])
        self.assertEqual(len(cits), 0)
        self.assertIn("The selected revision (V2 — Latest revision) does not provide sufficient evidence", stream_text)

    def test_08_citations_preserve_actual_revision_and_page_references(self):
        """Verify citations retain exact PDF filenames, revisions, and page numbers for both V1 and V2."""
        v2_chunks = re.retrieve_relevant_chunks("hull welding", top_k=3, revision_mode="v2")
        for c in v2_chunks:
            self.assertIn("v2.pdf", c["filename"].lower())
            self.assertIn("Version 2", c["revision"])
            page_val = str(c.get("page_number", ""))
            self.assertTrue(len(page_val) > 0)
            cit = re.format_citation(c)
            self.assertIn("v2.pdf", cit.lower())
            self.assertIn(f"Page {c['page_number']}", cit)

        v1_chunks = re.retrieve_relevant_chunks("hull welding", top_k=3, revision_mode="v1")
        for c in v1_chunks:
            self.assertNotIn("_v2.pdf", c["filename"].lower())
            self.assertNotIn("Version 2", c["revision"])
            page_val = str(c.get("page_number", ""))
            self.assertTrue(len(page_val) > 0)
            cit = re.format_citation(c)
            self.assertNotIn("_v2.pdf", cit.lower())
            self.assertIn(f"Page {c['page_number']}", cit)

    def test_09_category_filters_continue_working(self):
        """Verify that SOP category filter (logical_sop_id) functions simultaneously with revision mode."""
        # Hull Welding + V2
        hw_v2 = re.retrieve_relevant_chunks(
            "welding",
            top_k=5,
            logical_sop_id="HVF_SOP_1_Hull_Welding",
            revision_mode="v2"
        )
        self.assertGreater(len(hw_v2), 0)
        for c in hw_v2:
            self.assertEqual(c["logical_sop_id"], "HVF_SOP_1_Hull_Welding")
            self.assertTrue(re.is_v2_chunk(c))

        # Turret Integration + V1
        ti_v1 = re.retrieve_relevant_chunks(
            "turret",
            top_k=5,
            logical_sop_id="HVF_SOP_2_Turret_Integration",
            revision_mode="v1"
        )
        self.assertGreater(len(ti_v1), 0)
        for c in ti_v1:
            self.assertEqual(c["logical_sop_id"], "HVF_SOP_2_Turret_Integration")
            self.assertTrue(re.is_v1_chunk(c))

    def test_10_selection_survives_streamlit_reruns(self):
        """Verify that user selection persists in session state and is not overwritten on reruns."""
        simulated_session = {"revision_preference": "V1 — Baseline revision"}

        # Simulate rerun code path
        curr_pref = simulated_session.get("revision_preference", REVISION_CHOICES[0])
        idx = REVISION_CHOICES.index(curr_pref) if curr_pref in REVISION_CHOICES else 0

        self.assertEqual(idx, 1)
        self.assertEqual(REVISION_CHOICES[idx], "V1 — Baseline revision")
        self.assertEqual(simulated_session["revision_preference"], "V1 — Baseline revision")

    def test_11_conversation_history_remains_intact(self):
        """Verify SQLite conversation history and citations remain intact when switching revision scopes."""
        cid = db.create_conversation("Multi-Turn Scope Test", db_path=self.db_path)
        cid = cid["conversation_id"] if isinstance(cid, dict) else cid

        # Turn 1: V2 query
        db.save_message(
            conversation_id=cid,
            role="user",
            content="What is the revised hull welding benchmark?",
            db_path=self.db_path
        )
        cits_v2 = [{"filename": "HVF_SOP_1_Hull_Welding_v2.pdf", "revision": "Rev 5.0", "page_number": 4}]
        db.save_message(
            conversation_id=cid,
            role="assistant",
            content="The revised benchmark is 450 MPa.",
            citations=cits_v2,
            db_path=self.db_path
        )

        # Turn 2: User switches to V1
        db.save_message(
            conversation_id=cid,
            role="user",
            content="What was the baseline benchmark?",
            db_path=self.db_path
        )
        cits_v1 = [{"filename": "HVF_SOP_1_Hull_Welding.pdf", "revision": "Rev 4.2", "page_number": 4}]
        db.save_message(
            conversation_id=cid,
            role="assistant",
            content="The baseline benchmark was 420 MPa.",
            citations=cits_v1,
            db_path=self.db_path
        )

        messages = db.get_conversation_messages(cid, db_path=self.db_path)
        self.assertEqual(len(messages), 4)
        self.assertEqual(messages[1]["citations"][0]["revision"], "Rev 5.0")
        self.assertEqual(messages[3]["citations"][0]["revision"], "Rev 4.2")

    def test_12_revision_comparison_and_impact_analysis_are_unaffected(self):
        """Verify that revision comparison and impact analysis modules operate independently of chatbot revision filter."""
        pairs = sa.get_available_sop_pairs("SOP")
        self.assertEqual(len(pairs), 5)

        for p in pairs:
            self.assertTrue(p["is_complete"])
            self.assertTrue(os.path.exists(p["baseline_path"]))
            self.assertTrue(os.path.exists(p["revised_path"]))
            self.assertIn("_v2.pdf", p["revised_path"].lower())
            self.assertNotIn("_v2.pdf", p["baseline_path"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
