#!/usr/bin/env python3
"""
Phase 7 Automated Verification Test Suite
==========================================
Verifies:
1. Pairing discovery across all 5 official SOP pairs.
2. Pair validation and rejection rules (mismatched logical ID, identical revision, empty chunks).
3. Section key extraction across diverse heading formats.
4. Section alignment (MATCHED, ADDED, REMOVED).
5. Unchanged text detection and counting.
6. Numerical parameter / tolerance / threshold classification.
7. Safety warning and precaution classification.
8. Equipment, tooling, and inspection / acceptance criteria classification.
9. Editorial and formatting change detection.
10. Uncertain change flagging for mandatory human review.
11. Traceability guarantees (filenames, revisions, sections, pages, verbatim passages).
12. End-to-end comparison and report generation across all 5 actual SOP PDF pairs.
"""

import os
import sys
import unittest

# Ensure current working directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import document_processor as dp
import sop_analyzer as sa


class TestPhase7SOPAnalyzer(unittest.TestCase):

    def setUp(self):
        self.sop_dir = os.path.join(BASE_DIR, "SOP")
        self.assertTrue(os.path.isdir(self.sop_dir), f"SOP directory missing: {self.sop_dir}")

    # -------------------------------------------------------------------------
    # TEST 1: Pairing Discovery
    # -------------------------------------------------------------------------
    def test_01_pairing_discovery(self):
        """Verify discovery and pairing of all 5 official baseline/revised SOP pairs."""
        pairs = sa.get_available_sop_pairs(self.sop_dir)
        self.assertEqual(len(pairs), 5, f"Expected 5 pairs, got {len(pairs)}")

        expected_ids = {
            "HVF_SOP_1_Hull_Welding",
            "HVF_SOP_2_Turret_Integration",
            "HVF_SOP_3_Engine_Alignment",
            "HVF_SOP_4_Torsion_Suspension",
            "HVF_SOP_5_Gun_Calibration"
        }
        found_ids = {p["logical_sop_id"] for p in pairs}
        self.assertEqual(expected_ids, found_ids)

        for p in pairs:
            self.assertTrue(os.path.exists(p["baseline_path"]), f"Missing {p['baseline_path']}")
            self.assertTrue(os.path.exists(p["revised_path"]), f"Missing {p['revised_path']}")
            self.assertTrue(p["is_complete"])
            self.assertIn("_v2.pdf", p["revised_filename"])

    # -------------------------------------------------------------------------
    # TEST 2: Pair Validation & Rejection Rules
    # -------------------------------------------------------------------------
    def test_02_pair_validation_rejection(self):
        """Verify validation logic accepts valid pairs and rejects mismatched/invalid pairs."""
        # 1. Valid pair
        doc_a = {
            "logical_sop_id": "HVF_SOP_1_Hull_Welding",
            "document_id": "HVF-WLD-2024-001",
            "revision": "v1.0",
            "chunks": [{"chunk_id": "c1", "section_title": "1.0", "chunk_text": "text", "page_number": 1}]
        }
        doc_b = {
            "logical_sop_id": "HVF_SOP_1_Hull_Welding",
            "document_id": "HVF-WLD-2026-002",
            "revision": "v2.0",
            "chunks": [{"chunk_id": "c2", "section_title": "1.0", "chunk_text": "new text", "page_number": 1}]
        }
        is_valid, msg = sa.validate_sop_pair(doc_a, doc_b)
        self.assertTrue(is_valid, f"Expected valid pair, got: {msg}")

        # 2. Mismatched logical_sop_id
        doc_mismatched = dict(doc_b, logical_sop_id="HVF_SOP_2_Turret_Integration")
        is_valid, msg = sa.validate_sop_pair(doc_a, doc_mismatched)
        self.assertFalse(is_valid)
        self.assertIn("Mismatched logical SOP IDs", msg)

        # 3. Identical document ID and revision
        doc_identical = dict(doc_a)
        is_valid, msg = sa.validate_sop_pair(doc_a, doc_identical)
        self.assertFalse(is_valid)
        self.assertIn("no revision delta", msg)

        # 4. Empty chunks
        doc_empty = dict(doc_a, chunks=[])
        is_valid, msg = sa.validate_sop_pair(doc_empty, doc_b)
        self.assertFalse(is_valid)
        self.assertIn("0 extracted text chunks", msg)

        # 5. None / missing records
        is_valid, msg = sa.validate_sop_pair({}, doc_b)
        self.assertFalse(is_valid)

    # -------------------------------------------------------------------------
    # TEST 3: Section Key Extraction
    # -------------------------------------------------------------------------
    def test_03_section_key_extraction(self):
        """Verify extract_section_key handles diverse section formats and prefixes."""
        cases = [
            ("SECTION 1.0 — RHA PLATE RECEIVING", "SECTION 1.0"),
            ("SECTION 2.3: Joint Beveling and Fit-up", "SECTION 2.3"),
            ("1.0.A Material Certification", "1.0.A"),
            ("0.2 Document Control History", "0.2"),
            ("APPENDIX A — Calibration Certificates", "APPENDIX A"),
            ("Section 4.1  Torsion Bar Installation", "SECTION 4.1"),
            ("General Introduction", "GENERAL INTRODUCTION"),
            ("", "GENERAL")
        ]
        for title, expected in cases:
            extracted = sa.extract_section_key(title)
            self.assertEqual(extracted, expected, f"Failed for '{title}': got '{extracted}' != '{expected}'")

    # -------------------------------------------------------------------------
    # TEST 4: Section Alignment (Added, Removed, Matched)
    # -------------------------------------------------------------------------
    def test_04_section_alignment_added_removed_matched(self):
        """Verify section alignment correctly identifies MATCHED, ADDED, and REMOVED sections."""
        base_chunks = [
            {"section_title": "SECTION 1.0 — Prep", "chunk_text": "Base prep", "page_number": 1},
            {"section_title": "SECTION 2.0 — Obsolete Step", "chunk_text": "Deprecated", "page_number": 2},
        ]
        rev_chunks = [
            {"section_title": "SECTION 1.0 — Advanced Prep", "chunk_text": "Revised prep", "page_number": 1},
            {"section_title": "SECTION 3.0 — AI Laser Scan", "chunk_text": "New laser scan", "page_number": 3},
        ]

        aligned = sa.align_document_sections(base_chunks, rev_chunks)
        status_map = {item["section_key"]: item["status"] for item in aligned}

        self.assertEqual(status_map.get("SECTION 1.0"), "MATCHED")
        self.assertEqual(status_map.get("SECTION 2.0"), "REMOVED")
        self.assertEqual(status_map.get("SECTION 3.0"), "ADDED")

    # -------------------------------------------------------------------------
    # TEST 5: Unchanged Text Detection
    # -------------------------------------------------------------------------
    def test_05_unchanged_text_detection(self):
        """Verify identical sections are detected as unchanged and excluded from diffs."""
        base_chunks = [
            {"section_title": "SECTION 1.0 — Scope", "chunk_text": "This procedure governs standard hull assembly.", "page_number": 1},
            {"section_title": "SECTION 2.0 — Preheat", "chunk_text": "Preheat plate to 120 C.", "page_number": 2}
        ]
        rev_chunks = [
            {"section_title": "SECTION 1.0 — Scope", "chunk_text": "This procedure governs standard hull assembly.", "page_number": 1},
            {"section_title": "SECTION 2.0 — Preheat", "chunk_text": "Preheat plate to 160 C.", "page_number": 2}
        ]

        doc_a = {
            "logical_sop_id": "HVF_SOP_1_Hull_Welding",
            "document_id": "HVF-WLD-001",
            "revision": "v1.0",
            "filename": "base.pdf",
            "chunks": base_chunks
        }
        doc_b = {
            "logical_sop_id": "HVF_SOP_1_Hull_Welding",
            "document_id": "HVF-WLD-002",
            "revision": "v2.0",
            "filename": "rev.pdf",
            "chunks": rev_chunks
        }

        result = sa.compare_sop_revisions(doc_a, doc_b)
        self.assertEqual(result["unchanged_sections_count"], 1)
        self.assertEqual(result["total_changes"], 1)
        self.assertEqual(result["changes"][0]["revised_section"], "SECTION 2.0 — Preheat")

    # -------------------------------------------------------------------------
    # TEST 6: Numerical Parameter Classification
    # -------------------------------------------------------------------------
    def test_06_numerical_parameter_classification(self):
        """Verify numerical parameters, tolerances, and thresholds are classified correctly."""
        base = "Preheat temperature shall be maintained at 150 C with torque of 450 Nm and clearance of 0.5 mm."
        rev = "Preheat temperature shall be maintained at 180 C with torque of 520 Nm and clearance of 0.2 mm."

        classes, primary, expl = sa.classify_passage_difference(base, rev)
        self.assertIn("Changed numerical parameter, tolerance, or threshold", classes)
        self.assertEqual(primary, "Changed numerical parameter, tolerance, or threshold")
        self.assertIn("Numerical values/tolerances updated", expl)

    # -------------------------------------------------------------------------
    # TEST 7: Safety Warning Classification
    # -------------------------------------------------------------------------
    def test_07_safety_warning_classification(self):
        """Verify safety warnings, hazards, and precautions are classified correctly."""
        base = "Standard workshop rules apply. Wear protective gloves during operations."
        rev = "WARNING: Danger of toxic fume and radiation hazard. Full PPE and emergency interlock trip required."

        classes, primary, expl = sa.classify_passage_difference(base, rev)
        self.assertIn("Changed safety warning or precaution", classes)
        self.assertIn("Safety protocols updated", expl)

    # -------------------------------------------------------------------------
    # TEST 8: Equipment & Inspection Classification
    # -------------------------------------------------------------------------
    def test_08_equipment_and_inspection_classification(self):
        """Verify equipment tooling and inspection/metrology criteria are classified correctly."""
        base = "Perform manual visual check with ruler and spirit level on fixture."
        rev = "Deploy robotic laser tracker with PAUT phased-array ultrasonic inspection metrology benchmark."

        classes, primary, expl = sa.classify_passage_difference(base, rev)
        self.assertIn("Changed equipment, tooling, or material", classes)
        self.assertIn("Changed inspection or acceptance criterion", classes)

    # -------------------------------------------------------------------------
    # TEST 9: Editorial Change Detection
    # -------------------------------------------------------------------------
    def test_09_editorial_change_detection(self):
        """Verify minor wording/formatting changes without operational shift are marked editorial."""
        base = "The operator must clean the surface thoroughly before proceeding."
        rev = "The operator must clean the surface thoroughly before proceeding. "  # whitespace / minor phrasing

        classes, primary, expl = sa.classify_passage_difference(base, rev)
        self.assertIn("Editorial or formatting-only change", classes)

        # High similarity test without triggering parameter regex
        base2 = "Ensure the area is cleared of dust and clean for operation."
        rev2 = "Ensure that the area is cleared of dust and kept clean for operation."
        classes2, primary2, expl2 = sa.classify_passage_difference(base2, rev2)
        self.assertIn("Editorial or formatting-only change", classes2)

    # -------------------------------------------------------------------------
    # TEST 10: Uncertain Change Flagging
    # -------------------------------------------------------------------------
    def test_10_uncertain_change_flagging(self):
        """Verify complete rewrites with low similarity are flagged for human review."""
        base = "Step Alpha: Initialize primary hydraulics subsystem."
        rev = "Unrelated paragraph discussing administrative billing codes and archive storage protocols."

        classes, primary, expl = sa.classify_passage_difference(base, rev)
        self.assertIn("Uncertain change requiring human review", classes)
        self.assertIn("manual engineering review", expl.lower())

    # -------------------------------------------------------------------------
    # TEST 11: Traceability Guarantees
    # -------------------------------------------------------------------------
    def test_11_traceability_guarantees(self):
        """Verify every detected change preserves complete provenance and verbatim text."""
        base_chunk = {
            "section_title": "SECTION 2.1 — Welding Torch Setup",
            "chunk_text": "Operate GMAW torch at 220 A and 28 V.",
            "page_number": 3
        }
        rev_chunk = {
            "section_title": "SECTION 2.1 — Twin-Wire Robotic Setup",
            "chunk_text": "Operate twin-wire robotic torch at 290 A and 34 V.",
            "page_number": 3
        }
        doc_a = {
            "logical_sop_id": "HVF_SOP_1_Hull_Welding",
            "document_id": "HVF-WLD-001",
            "revision": "v1.0",
            "filename": "HVF_SOP_1_Hull_Welding.pdf",
            "chunks": [base_chunk]
        }
        doc_b = {
            "logical_sop_id": "HVF_SOP_1_Hull_Welding",
            "document_id": "HVF-WLD-002",
            "revision": "v2.0",
            "filename": "HVF_SOP_1_Hull_Welding_v2.pdf",
            "chunks": [rev_chunk]
        }

        result = sa.compare_sop_revisions(doc_a, doc_b)
        self.assertEqual(len(result["changes"]), 1)
        chg = result["changes"][0]

        # Check required traceability fields
        self.assertTrue(chg["change_id"].startswith("CHG-"))
        self.assertEqual(chg["baseline_filename"], "HVF_SOP_1_Hull_Welding.pdf")
        self.assertEqual(chg["baseline_revision"], "v1.0")
        self.assertEqual(chg["baseline_page"], 3)
        self.assertEqual(chg["baseline_section"], "SECTION 2.1 — Welding Torch Setup")
        self.assertEqual(chg["baseline_passage"], "Operate GMAW torch at 220 A and 28 V.")

        self.assertEqual(chg["revised_filename"], "HVF_SOP_1_Hull_Welding_v2.pdf")
        self.assertEqual(chg["revised_revision"], "v2.0")
        self.assertEqual(chg["revised_page"], 3)
        self.assertEqual(chg["revised_section"], "SECTION 2.1 — Twin-Wire Robotic Setup")
        self.assertEqual(chg["revised_passage"], "Operate twin-wire robotic torch at 290 A and 34 V.")

    # -------------------------------------------------------------------------
    # TEST 12: End-to-End Across All 5 Real SOP Pairs
    # -------------------------------------------------------------------------
    def test_12_e2e_all_five_sop_pairs(self):
        """Execute complete extraction, pairing, comparison, and report generation on all 5 SOP pairs."""
        all_results = sa.compare_all_existing_pairs(self.sop_dir)
        self.assertEqual(len(all_results), 5, "Expected results for all 5 pairs")

        for res in all_results:
            self.assertEqual(res["status"], "success")
            self.assertGreater(res["total_changes"], 0, f"Expected changes in {res['logical_sop_id']}")
            self.assertIn("baseline", res)
            self.assertIn("revised", res)
            self.assertIn("classification_summary", res)

            # Check markdown report export
            report = sa.generate_comparison_report(res)
            self.assertTrue(len(report) > 500, f"Report too short for {res['logical_sop_id']}")
            self.assertIn(res["logical_sop_id"], report)
            self.assertIn("Executive Change Metrics", report)
            self.assertIn("Traceable Change Inventory", report)
            self.assertIn("Before (Baseline):", report)
            self.assertIn("After (Revised):", report)


if __name__ == "__main__":
    print("=" * 70)
    print("PHASE 7 AUTOMATED VERIFICATION TEST SUITE: SOP REVISION COMPARISON")
    print("=" * 70)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase7SOPAnalyzer)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    sys.exit(0 if res.wasSuccessful() else 1)

