#!/usr/bin/env python3
"""
Test Suite: Compact Verified Evidence Sources Verification
===========================================================
Validates:
1. Grouping retrieved citation passages by unique source PDF and revision.
2. Keeping different revisions of the same SOP as distinct entries.
3. Consolidating page numbers into clean ranges (Page X vs Pages X–Y).
4. Preserving the total passage count in the expander header.
5. Omitting raw passage text and cosine similarity from default evidence display.
6. Preserving complete citation metadata for SQLite persistence and auditing.
7. Syntax and compilation integrity of app.py.
"""

import sys
import io
import os
import unittest
import py_compile
import tempfile
import sqlite3

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import database as db
from app import group_citations_by_source


class TestCompactEvidenceSources(unittest.TestCase):

    def setUp(self):
        # Sample retrieved citation passages matching real RAG output
        self.sample_citations = [
            {
                "chunk_id": "HVF_SOP_2_Turret_Integration_v2.pdf_chunk_12",
                "filename": "HVF_SOP_2_Turret_Integration_v2.pdf",
                "document_id": "HVF/SOP/TI-201-V2",
                "revision": "Rev 4.5 [Version 2.0] | 30-Oct-2026",
                "section_title": "Section 4.1: Turret Ring Bearing Backlash",
                "page_number": 6,
                "score": 0.8421,
                "chunk_text": "The turret azimuth bearing backlash must not exceed 0.05 mm across 360 degrees.",
                "citation": "[Doc: HVF/SOP/TI-201-V2, Sec: 4.1, Rev: Rev 4.5 [Version 2.0], Page: 6]"
            },
            {
                "chunk_id": "HVF_SOP_2_Turret_Integration_v2.pdf_chunk_13",
                "filename": "HVF_SOP_2_Turret_Integration_v2.pdf",
                "document_id": "HVF/SOP/TI-201-V2",
                "revision": "Rev 4.5 [Version 2.0] | 30-Oct-2026",
                "section_title": "Section 4.2: Slip-Ring Continuity Testing",
                "page_number": 7,
                "score": 0.7915,
                "chunk_text": "Rotational torque resistance during slip-ring alignment shall be within 18-22 Nm.",
                "citation": "[Doc: HVF/SOP/TI-201-V2, Sec: 4.2, Rev: Rev 4.5 [Version 2.0], Page: 7]"
            },
            {
                "chunk_id": "HVF_SOP_1_Hull_Welding_v2.pdf_chunk_05",
                "filename": "HVF_SOP_1_Hull_Welding_v2.pdf",
                "document_id": "HVF/SOP/HW-101-V2",
                "revision": "Rev 5.0 [Version 2.0] | 30-Oct-2026",
                "section_title": "Section 3.2: Preheat and Interpass Temperature Controls",
                "page_number": 3,
                "score": 0.8250,
                "chunk_text": "High-hardened armor plate preheat shall be maintained at 150 deg C +/- 10 deg C.",
                "citation": "[Doc: HVF/SOP/HW-101-V2, Sec: 3.2, Rev: Rev 5.0 [Version 2.0], Page: 3]"
            },
            {
                "chunk_id": "HVF_SOP_1_Hull_Welding.pdf_chunk_08",
                "filename": "HVF_SOP_1_Hull_Welding.pdf",
                "document_id": "HVF/SOP/HW-101",
                "revision": "Rev 4.2 (2026) | 30-Oct-2026",
                "section_title": "Section 4.0: GMAW Acceptance Criteria",
                "page_number": 4,
                "score": 0.7630,
                "chunk_text": "Root pass penetration minimum 6 mm without undercut or incomplete fusion.",
                "citation": "[Doc: HVF/SOP/HW-101, Sec: 4.0, Rev: Rev 4.2 (2026), Page: 4]"
            },
            {
                "chunk_id": "HVF_SOP_1_Hull_Welding.pdf_chunk_09",
                "filename": "HVF_SOP_1_Hull_Welding.pdf",
                "document_id": "HVF/SOP/HW-101",
                "revision": "Rev 4.2 (2026) | 30-Oct-2026",
                "section_title": "Section 4.1: Ultrasonic NDT Protocol",
                "page_number": 5,
                "score": 0.7510,
                "chunk_text": "Ultrasonic examination per IS 4225 Grade 1 standard across 100 percent of seam joints.",
                "citation": "[Doc: HVF/SOP/HW-101, Sec: 4.1, Rev: Rev 4.2 (2026), Page: 5]"
            }
        ]

    def test_grouping_by_source_and_revision(self):
        """Verify grouping of 5 passages into 3 unique (filename, revision) source entries."""
        grouped = group_citations_by_source(self.sample_citations)
        self.assertEqual(len(grouped), 3, "Expected 3 distinct grouped source entries from 5 passages.")

        # Check total passage count across grouped entries equals original
        total_passages = sum(g["passage_count"] for g in grouped)
        self.assertEqual(total_passages, len(self.sample_citations))

        # Check grouped filenames
        filenames = [g["filename"] for g in grouped]
        self.assertIn("HVF_SOP_2_Turret_Integration_v2.pdf", filenames)
        self.assertIn("HVF_SOP_1_Hull_Welding_v2.pdf", filenames)
        self.assertIn("HVF_SOP_1_Hull_Welding.pdf", filenames)

    def test_revisions_remain_distinct(self):
        """Verify baseline and revised versions of the same SOP are distinct entries."""
        grouped = group_citations_by_source(self.sample_citations)
        hull_entries = [g for g in grouped if "Hull_Welding" in g["filename"]]
        self.assertEqual(len(hull_entries), 2, "Expected 2 distinct entries for Hull Welding revisions.")

        revs = {g["revision"] for g in hull_entries}
        self.assertIn("Rev 5.0", revs)
        self.assertIn("Rev 4.2", revs)

    def test_page_range_formatting(self):
        """Verify page formatting: single page, consecutive pages (en-dash), and multiple ranges."""
        grouped = group_citations_by_source(self.sample_citations)
        by_file = {g["filename"]: g for g in grouped}

        # Consecutive pages 6 and 7 -> Pages 6–7
        self.assertEqual(by_file["HVF_SOP_2_Turret_Integration_v2.pdf"]["pages_str"], "Pages 6–7")

        # Single page 3 -> Page 3
        self.assertEqual(by_file["HVF_SOP_1_Hull_Welding_v2.pdf"]["pages_str"], "Page 3")

        # Consecutive pages 4 and 5 -> Pages 4–5
        self.assertEqual(by_file["HVF_SOP_1_Hull_Welding.pdf"]["pages_str"], "Pages 4–5")

    def test_disjoint_page_ranges(self):
        """Verify non-consecutive pages format cleanly into comma-separated ranges."""
        test_citations = [
            {"filename": "DocA.pdf", "revision": "Rev 1.0", "page_number": 2},
            {"filename": "DocA.pdf", "revision": "Rev 1.0", "page_number": 3},
            {"filename": "DocA.pdf", "revision": "Rev 1.0", "page_number": 8},
            {"filename": "DocA.pdf", "revision": "Rev 1.0", "page_number": 9},
            {"filename": "DocA.pdf", "revision": "Rev 1.0", "page_number": 10},
            {"filename": "DocA.pdf", "revision": "Rev 1.0", "page_number": 15},
        ]
        grouped = group_citations_by_source(test_citations)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["pages_str"], "Pages 2–3, 8–10, 15")

    def test_compact_display_suppresses_raw_text_and_scores(self):
        """Verify grouped output structures do not expose chunk_text or cosine scores."""
        grouped = group_citations_by_source(self.sample_citations)
        for g in grouped:
            # Grouped source dictionaries should only contain presentation fields
            self.assertNotIn("chunk_text", g)
            self.assertNotIn("score", g)
            self.assertIn("filename", g)
            self.assertIn("revision", g)
            self.assertIn("pages_str", g)
            self.assertIn("sections", g)

    def test_database_persistence_preserves_full_citations(self):
        """Verify that db.save_message retains complete raw citation metadata."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            temp_db = tf.name

        old_db_path = db.DEFAULT_DB_PATH
        try:
            db.DEFAULT_DB_PATH = temp_db
            db.init_database(db_path=temp_db)
            conv = db.create_conversation("Citation Test", db_path=temp_db)
            cid = conv["conversation_id"]

            saved = db.save_message(
                conversation_id=cid,
                role="assistant",
                content="Hull welding benchmarks require 150°C preheat.",
                citations=self.sample_citations,
                db_path=temp_db
            )

            # Retrieve from DB and verify citations integrity
            messages = db.get_conversation_messages(cid, db_path=temp_db)
            self.assertEqual(len(messages), 1)
            stored_citations = messages[0]["citations"]
            self.assertEqual(len(stored_citations), len(self.sample_citations))

            for orig, stored in zip(self.sample_citations, stored_citations):
                self.assertEqual(stored["chunk_id"], orig["chunk_id"])
                self.assertEqual(stored["filename"], orig["filename"])
                self.assertEqual(stored["score"], orig["score"])
                self.assertEqual(stored["chunk_text"], orig["chunk_text"])
                self.assertEqual(stored["citation"], orig["citation"])
        finally:
            db.DEFAULT_DB_PATH = old_db_path
            if os.path.exists(temp_db):
                try:
                    os.remove(temp_db)
                except Exception:
                    pass

    def test_app_compilation(self):
        """Verify app.py compiles without syntax or parsing errors."""
        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        py_compile.compile(app_path, doraise=True)


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestCompactEvidenceSources)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
