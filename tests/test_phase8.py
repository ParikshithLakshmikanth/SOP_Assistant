#!/usr/bin/env python3
"""
Phase 8 Automated Verification Test Suite
==========================================
Verifies:
1. Explicit SOP document references are extracted correctly.
2. Section references are normalized without losing original text.
3. Equipment and parameter references are extracted with source traceability.
4. Direct dependencies are detected.
5. Potential dependencies are distinguished from direct dependencies.
6. Shared generic terminology alone does not create a false impact.
7. No-impact and insufficient-evidence cases are distinguished.
8. Every impact result contains valid source and affected-document evidence.
9. Safety-critical ambiguous changes require human review.
10. Accept, reject, and investigate review decisions persist correctly.
11. Reviewer notes persist across application restarts.
12. SQLite schema migration preserves all Phase 5 conversation records.
13. Report export preserves evidence and review status.
14. Integration across actual 5 SOP pairs in SOP/ directory.
"""

import os
import sys
import unittest
import uuid

# Ensure current working directory is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import document_processor as dp
import sop_analyzer as sa
import database as db


class TestPhase8CrossDocumentImpactEngine(unittest.TestCase):

    def setUp(self):
        self.sop_dir = os.path.join(BASE_DIR, "SOP")
        self.assertTrue(os.path.isdir(self.sop_dir), f"SOP directory missing: {self.sop_dir}")
        self.test_db = os.path.join(BASE_DIR, "data", f"test_phase8_{uuid.uuid4().hex[:8]}.db")

    def tearDown(self):
        if os.path.exists(self.test_db):
            try:
                os.remove(self.test_db)
            except Exception:
                pass

    # -------------------------------------------------------------------------
    # TEST 1: Explicit Document References Extraction
    # -------------------------------------------------------------------------
    def test_01_explicit_document_reference_extraction(self):
        """Verify extraction and normalization of SOP document IDs and numbers."""
        sample_text = (
            "Refer to specification HVF/AVNL/SOP-MBT/HW-101 and TI-204 for turret plinth alignment. "
            "Also consult SOP 4 and SOP-MBT/GC-518 revision guidelines."
        )
        refs = sa.extract_cross_references(sample_text)
        doc_ids = refs["document_ids"]
        self.assertIn("HVF/AVNL/SOP-MBT/HW-101", doc_ids)
        self.assertIn("TI-204", doc_ids)
        self.assertIn("SOP-4", doc_ids)
        self.assertIn("GC-518", doc_ids)

    # -------------------------------------------------------------------------
    # TEST 2: Section References Normalization
    # -------------------------------------------------------------------------
    def test_02_section_references_normalization(self):
        """Verify section numbers are recognized and normalized."""
        sample_text = (
            "Execute procedure according to SECTION 1.0 and 2.0.A before proceeding to "
            "Section 4.2. Review APPENDIX A for revision details."
        )
        refs = sa.extract_cross_references(sample_text)
        secs = refs["sections"]
        self.assertIn("SECTION 1.0", secs)
        self.assertIn("2.0.A", secs)
        self.assertIn("SECTION 4.2", secs)
        self.assertIn("APPENDIX A", secs)

    # -------------------------------------------------------------------------
    # TEST 3: Equipment and Parameter References Extraction
    # -------------------------------------------------------------------------
    def test_03_equipment_and_parameter_extraction(self):
        """Verify tooling, sensors, and numerical parameters are extracted with units."""
        sample_text = (
            "Align using Leica AT960 laser tracker with dual-laser aligner. "
            "Maintain preheat temperature at 180 °C, torque of 450 Nm, and clearance of 0.35 mm."
        )
        refs = sa.extract_cross_references(sample_text)
        self.assertTrue(any("Laser Tracker" in e for e in refs["equipment"]))
        params = " ".join(refs["parameters"]).lower()
        self.assertIn("180", params)
        self.assertIn("450", params)
        self.assertIn("0.35", params)

    # -------------------------------------------------------------------------
    # TEST 4: Direct Dependencies Detection
    # -------------------------------------------------------------------------
    def test_04_direct_dependencies_detection(self):
        """Verify direct geometric and physical interfaces are classified as Direct impact."""
        # Simulated change in Hull Welding: Turret base mounting plane flatness
        change = {
            "change_id": "CHG-HW-01",
            "primary_classification": "Changed numerical parameter, tolerance, or threshold",
            "classifications": ["Changed numerical parameter, tolerance, or threshold"],
            "baseline_section": "SECTION 5.0 — HULL FINISHING",
            "revised_section": "SECTION 5.0 — TURRET BASE MOUNTING PLANE FINISHING",
            "baseline_page": 5,
            "revised_page": 5,
            "baseline_passage": "Machine hull upper deck mounting plane flat to 0.50 mm across circumference.",
            "revised_passage": "Machine turret base mounting plane flat to 0.35 mm across 2.2 m circle.",
            "document_title": "Hull Welding",
            "baseline_document_id": "HVF/AVNL/SOP-MBT/HW-101",
            "baseline_filename": "HVF_SOP_1_Hull_Welding.pdf",
            "revised_filename": "HVF_SOP_1_Hull_Welding_v2.pdf"
        }

        # Mock Turret Integration document chunk
        turret_chunk = {
            "chunk_id": "TI-01",
            "section_title": "SECTION 1.0 — HULL PLINTH & TURRET BASE RING MAPPING",
            "chunk_text": "Verify plinth flatness and bearing spigot concentricity before race fitment.",
            "page_number": 1
        }
        mock_turret_doc = {
            "logical_sop_id": "HVF_SOP_2_Turret_Integration",
            "document_title": "Turret Integration",
            "document_id": "HVF/AVNL/SOP-MBT/TI-204",
            "filename": "HVF_SOP_2_Turret_Integration.pdf",
            "revision": "Rev 3.8",
            "chunks": [turret_chunk]
        }

        candidates = sa.identify_cross_document_impacts(
            change=change,
            corpus_docs=[mock_turret_doc],
            source_sop_id="HVF_SOP_1_Hull_Welding",
            db_path=self.test_db
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["classification"], sa.IMPACT_DIRECT)
        self.assertEqual(candidates[0]["affected_sop_id"], "HVF_SOP_2_Turret_Integration")
        self.assertIn("plinth", candidates[0]["affected_passage"].lower())

    # -------------------------------------------------------------------------
    # TEST 5: Potential vs Direct Dependencies Distinction
    # -------------------------------------------------------------------------
    def test_05_potential_dependencies_distinction(self):
        """Verify contextual attitude coupling is classified as Potential impact."""
        # Simulated change in Torsion Suspension: Static combat belly clearance
        change = {
            "change_id": "CHG-TS-01",
            "primary_classification": "Changed numerical parameter, tolerance, or threshold",
            "classifications": ["Changed numerical parameter, tolerance, or threshold"],
            "baseline_section": "SECTION 3.0 — SUSPENSION CALIBRATION",
            "revised_section": "SECTION 3.0 — AUTOMATED VERNIER CALIBRATION",
            "baseline_page": 3,
            "revised_page": 3,
            "baseline_passage": "Set belly clearance to 450 mm with port-starboard level balance within 2.0 mm.",
            "revised_passage": "Set static combat belly clearance to 455 mm ± 4 mm and port-starboard level balance within 1.0 mm.",
            "document_title": "Torsion Suspension",
            "baseline_document_id": "HVF/AVNL/SOP-MBT/TS-412",
            "baseline_filename": "HVF_SOP_4_Torsion_Suspension.pdf",
            "revised_filename": "HVF_SOP_4_Torsion_Suspension_v2.pdf"
        }

        mock_turret_doc = {
            "logical_sop_id": "HVF_SOP_2_Turret_Integration",
            "document_title": "Turret Integration",
            "document_id": "HVF/AVNL/SOP-MBT/TI-204",
            "filename": "HVF_SOP_2_Turret_Integration.pdf",
            "revision": "Rev 3.8",
            "chunks": [
                {
                    "chunk_id": "TI-06",
                    "section_title": "SECTION 6.0 — ROTATION AND STABILIZATION",
                    "chunk_text": "Subject vehicle to dynamic shake rig testing and evaluate cant-angle running torque.",
                    "page_number": 6
                }
            ]
        }

        candidates = sa.identify_cross_document_impacts(
            change=change,
            corpus_docs=[mock_turret_doc],
            source_sop_id="HVF_SOP_4_Torsion_Suspension",
            db_path=self.test_db
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["classification"], sa.IMPACT_POTENTIAL)

    # -------------------------------------------------------------------------
    # TEST 6: Generic Terminology Does Not Create False Impact
    # -------------------------------------------------------------------------
    def test_06_generic_terms_prevent_false_impact(self):
        """Verify sharing generic words like 'tank', 'vehicle', 'bolt' does not create impact."""
        generic_change = {
            "change_id": "CHG-GEN-01",
            "primary_classification": "Modified procedure or sequence",
            "classifications": ["Modified procedure or sequence"],
            "baseline_section": "SECTION 1.0 — GENERAL SHOP RULES",
            "revised_section": "SECTION 1.0 — GENERAL SHOP RULES",
            "baseline_page": 1,
            "revised_page": 1,
            "baseline_passage": "The operator must clean the vehicle tank steel surfaces with an air hose.",
            "revised_passage": "The operator must verify that the vehicle tank metal assembly area is clean.",
            "document_title": "General",
            "baseline_document_id": "HVF-GEN-001",
            "baseline_filename": "base.pdf",
            "revised_filename": "rev.pdf"
        }

        unrelated_doc = {
            "logical_sop_id": "HVF_SOP_5_Gun_Calibration",
            "document_title": "Gun Calibration",
            "document_id": "HVF/AVNL/SOP-MBT/GC-518",
            "filename": "HVF_SOP_5_Gun_Calibration.pdf",
            "revision": "Rev 4.6",
            "chunks": [
                {
                    "chunk_id": "GC-01",
                    "section_title": "SECTION 1.0 — BORE PROFILOMETRY",
                    "chunk_text": "The operator checks the vehicle tank steel breech block for cleanliness.",
                    "page_number": 1
                }
            ]
        }

        candidates = sa.identify_cross_document_impacts(
            change=generic_change,
            corpus_docs=[unrelated_doc],
            source_sop_id="HVF_SOP_1_Hull_Welding",
            db_path=self.test_db
        )
        self.assertEqual(len(candidates), 0, "Generic word overlap falsely triggered an impact candidate!")

    # -------------------------------------------------------------------------
    # TEST 7: No-Impact and Insufficient Evidence Distinction
    # -------------------------------------------------------------------------
    def test_07_no_impact_and_insufficient_evidence_distinction(self):
        """Verify distinction between no-impact and insufficient-evidence classifications."""
        change = {
            "change_id": "CHG-EA-05",
            "primary_classification": "Modified procedure or sequence",
            "classifications": ["Modified procedure or sequence"],
            "baseline_section": "SECTION 4.0 — FLUID HEADERS",
            "revised_section": "SECTION 4.0 — FLUID HEADERS",
            "baseline_page": 4,
            "revised_page": 4,
            "baseline_passage": "Bilge pump output verified at 60 L/min and cooling circuit pressure at 2.0 bar.",
            "revised_passage": "Bilge pump output verified at 80 L/min and cooling circuit pressure at 2.5 bar with scavenge blower.",
            "document_title": "Engine Alignment",
            "baseline_document_id": "HVF-EA-309",
            "baseline_filename": "base.pdf",
            "revised_filename": "rev.pdf"
        }

        mock_turret_doc = {
            "logical_sop_id": "HVF_SOP_2_Turret_Integration",
            "document_title": "Turret Integration",
            "document_id": "HVF/AVNL/SOP-MBT/TI-204",
            "filename": "HVF_SOP_2_Turret_Integration.pdf",
            "revision": "Rev 3.8",
            "chunks": [
                {
                    "chunk_id": "TI-04",
                    "section_title": "SECTION 4.0 — OVERTURN CLAMPING",
                    "chunk_text": "Verify hermetic nbc seal differential and ballistic labyrinth mud clearance.",
                    "page_number": 4
                }
            ]
        }

        candidates = sa.identify_cross_document_impacts(
            change=change,
            corpus_docs=[mock_turret_doc],
            source_sop_id="HVF_SOP_3_Engine_Alignment",
            db_path=self.test_db
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["classification"], sa.IMPACT_INSUFFICIENT)

    # -------------------------------------------------------------------------
    # TEST 8: Evidence-Backed Provenance Completeness
    # -------------------------------------------------------------------------
    def test_08_evidence_backed_provenance(self):
        """Verify impact record contains complete provenance for source and affected documents."""
        change = {
            "change_id": "CHG-GC-02",
            "primary_classification": "Changed numerical parameter, tolerance, or threshold",
            "classifications": ["Changed numerical parameter, tolerance, or threshold"],
            "baseline_section": "SECTION 2.0 — TRUNNIONS",
            "revised_section": "SECTION 2.0 — TRUNNIONS",
            "baseline_page": 2,
            "revised_page": 2,
            "baseline_passage": "Elevation trunnion alignment deviation must be within 0.04 mm.",
            "revised_passage": "Elevation trunnion alignment deviation must be within 0.02 mm across mantlet cradle.",
            "document_title": "Gun Calibration",
            "baseline_document_id": "HVF/AVNL/SOP-MBT/GC-518",
            "baseline_filename": "HVF_SOP_5_Gun_Calibration.pdf",
            "revised_filename": "HVF_SOP_5_Gun_Calibration_v2.pdf"
        }

        mock_turret_doc = {
            "logical_sop_id": "HVF_SOP_2_Turret_Integration",
            "document_title": "Turret Integration",
            "document_id": "HVF/AVNL/SOP-MBT/TI-204",
            "filename": "HVF_SOP_2_Turret_Integration.pdf",
            "revision": "Rev 3.8",
            "chunks": [
                {
                    "chunk_id": "TI-05",
                    "section_title": "SECTION 5.0 — DIGITAL SERVO TUNING",
                    "chunk_text": "Align line-of-sight stabilization and optical rotary slip-ring FORJ unit.",
                    "page_number": 5
                }
            ]
        }

        candidates = sa.identify_cross_document_impacts(
            change=change,
            corpus_docs=[mock_turret_doc],
            source_sop_id="HVF_SOP_5_Gun_Calibration",
            db_path=self.test_db
        )
        self.assertEqual(len(candidates), 1)
        cand = candidates[0]

        # Verify all required provenance fields
        self.assertEqual(cand["source_sop_id"], "HVF_SOP_5_Gun_Calibration")
        self.assertEqual(cand["source_change_id"], "CHG-GC-02")
        self.assertEqual(cand["source_section"], "SECTION 2.0 — TRUNNIONS")
        self.assertEqual(cand["source_page"], 2)
        self.assertTrue(len(cand["source_passage"]) > 10)

        self.assertEqual(cand["affected_sop_id"], "HVF_SOP_2_Turret_Integration")
        self.assertEqual(cand["affected_filename"], "HVF_SOP_2_Turret_Integration.pdf")
        self.assertEqual(cand["affected_section"], "SECTION 5.0 — DIGITAL SERVO TUNING")
        self.assertEqual(cand["affected_page"], 5)
        self.assertTrue(len(cand["affected_passage"]) > 10)

    # -------------------------------------------------------------------------
    # TEST 9: Safety-Critical Changes Require Human Review
    # -------------------------------------------------------------------------
    def test_09_safety_critical_requires_human_review(self):
        """Verify changes with primary safety hazard classifications require human review."""
        safety_change = {
            "change_id": "CHG-SAF-01",
            "primary_classification": "Changed safety warning or precaution",
            "classifications": ["Changed safety warning or precaution"],
            "baseline_section": "SECTION 2.0 — TURNOVER JIG",
            "revised_section": "SECTION 2.0 — TURNOVER JIG",
            "baseline_page": 2,
            "revised_page": 2,
            "baseline_passage": "General safety rules apply during turnover jig locking.",
            "revised_passage": "WARNING: Danger of radiation and high-voltage interlock trip during transverse bulkhead locking.",
            "document_title": "Hull Welding",
            "baseline_document_id": "HVF-HW-101",
            "baseline_filename": "HVF_SOP_1_Hull_Welding.pdf",
            "revised_filename": "HVF_SOP_1_Hull_Welding_v2.pdf"
        }

        mock_engine_doc = {
            "logical_sop_id": "HVF_SOP_3_Engine_Alignment",
            "document_title": "Engine Alignment",
            "document_id": "HVF/AVNL/SOP-MBT/EA-309",
            "filename": "HVF_SOP_3_Engine_Alignment.pdf",
            "revision": "Rev 5.1",
            "chunks": [
                {
                    "chunk_id": "EA-01",
                    "section_title": "SECTION 1.0 — REAR ENGINE BAY",
                    "chunk_text": "Verify bulkhead pitch and engine bay mount co-planarity across nodes.",
                    "page_number": 1
                }
            ]
        }

        candidates = sa.identify_cross_document_impacts(
            change=safety_change,
            corpus_docs=[mock_engine_doc],
            source_sop_id="HVF_SOP_1_Hull_Welding",
            db_path=self.test_db
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["classification"], sa.IMPACT_HUMAN_REVIEW)
        self.assertIn("Critical", candidates[0]["evidence_strength"])

    # -------------------------------------------------------------------------
    # TEST 10: Human Review Decisions Persistence
    # -------------------------------------------------------------------------
    def test_10_human_review_decisions_persistence(self):
        """Verify saving ACCEPTED, REJECTED, and INVESTIGATE decisions via database.py."""
        db.init_database(self.test_db)

        # 1. Save ACCEPTED
        r1 = db.save_impact_review(
            impact_id="IMP-TEST-01",
            source_change_id="CHG-01",
            source_sop_id="HVF_SOP_1_Hull_Welding",
            affected_sop_id="HVF_SOP_2_Turret_Integration",
            decision="ACCEPTED",
            reviewer_notes="Approved for production line integration.",
            db_path=self.test_db
        )
        self.assertEqual(r1["decision"], "ACCEPTED")

        # 2. Update to REJECTED
        r2 = db.save_impact_review(
            impact_id="IMP-TEST-01",
            source_change_id="CHG-01",
            source_sop_id="HVF_SOP_1_Hull_Welding",
            affected_sop_id="HVF_SOP_2_Turret_Integration",
            decision="REJECTED",
            reviewer_notes="Tolerance variation falls within existing buffer.",
            db_path=self.test_db
        )
        self.assertEqual(r2["decision"], "REJECTED")

        # 3. Save INVESTIGATE
        r3 = db.save_impact_review(
            impact_id="IMP-TEST-02",
            source_change_id="CHG-02",
            source_sop_id="HVF_SOP_1_Hull_Welding",
            affected_sop_id="HVF_SOP_3_Engine_Alignment",
            decision="INVESTIGATE",
            reviewer_notes="Requires physical measurement on Shop-04A coordinate table.",
            db_path=self.test_db
        )
        self.assertEqual(r3["decision"], "INVESTIGATE")

        # List reviews
        rev_list = db.list_impact_reviews(db_path=self.test_db)
        self.assertEqual(len(rev_list), 2)

    # -------------------------------------------------------------------------
    # TEST 11: Reviewer Notes Persist Across Reconnection
    # -------------------------------------------------------------------------
    def test_11_reviewer_notes_reconnection_persistence(self):
        """Verify reviewer decisions and detailed rationale persist across database reconnections."""
        db.init_database(self.test_db)
        note_text = "Verified with DGQA resident inspector on 2026-11-02. Cleared for Batch-II series."
        db.save_impact_review(
            impact_id="IMP-PERSIST-99",
            source_change_id="CHG-99",
            source_sop_id="HVF_SOP_2_Turret_Integration",
            affected_sop_id="HVF_SOP_5_Gun_Calibration",
            decision="ACCEPTED",
            reviewer_notes=note_text,
            db_path=self.test_db
        )

        # Retrieve through separate call
        retrieved = db.get_impact_review("IMP-PERSIST-99", db_path=self.test_db)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["decision"], "ACCEPTED")
        self.assertEqual(retrieved["reviewer_notes"], note_text)

    # -------------------------------------------------------------------------
    # TEST 12: SQLite Schema Migration Preserves Phase 5 Records
    # -------------------------------------------------------------------------
    def test_12_schema_migration_preserves_conversations(self):
        """Verify adding impact_reviews table preserves existing conversation and message data."""
        # 1. Initialize schema and insert conversation & messages
        db.init_database(self.test_db)
        c = db.create_conversation("Historical Consultation", db_path=self.test_db)
        cid = c["conversation_id"]

        m1 = db.save_message(cid, "user", "What is the preheat temp?", db_path=self.test_db)
        m2 = db.save_message(
            cid,
            "assistant",
            "Preheating is 180 C.",
            citations=[{"citation": "HVF_SOP_1.pdf, Page 3", "score": 0.95}],
            db_path=self.test_db
        )

        # 2. Re-run init_database (idempotent schema migration)
        db.init_database(self.test_db)

        # 3. Add an impact review
        db.save_impact_review(
            impact_id="IMP-MIGRATE-01",
            source_change_id="CHG-01",
            source_sop_id="HVF_SOP_1_Hull_Welding",
            affected_sop_id="HVF_SOP_2_Turret_Integration",
            decision="ACCEPTED",
            reviewer_notes="Post-migration validation.",
            db_path=self.test_db
        )

        # 4. Verify historical conversation data remains 100% intact
        conv = db.get_conversation_with_messages(cid, db_path=self.test_db)
        self.assertIsNotNone(conv)
        self.assertEqual(conv["title"], "Historical Consultation")
        self.assertEqual(len(conv["messages"]), 2)
        self.assertEqual(conv["messages"][0]["content"], "What is the preheat temp?")
        self.assertEqual(conv["messages"][1]["citations"][0]["citation"], "HVF_SOP_1.pdf, Page 3")

    # -------------------------------------------------------------------------
    # TEST 13: Report Export Preserves Evidence and Review Status
    # -------------------------------------------------------------------------
    def test_13_report_export_evidence_and_status(self):
        """Verify generated Markdown report includes metrics, candidate details, and review status."""
        impact_result = {
            "source_sop_id": "HVF_SOP_1_Hull_Welding",
            "source_document_title": "Armoured Hull Fabrications",
            "baseline_filename": "HVF_SOP_1_Hull_Welding.pdf",
            "revised_filename": "HVF_SOP_1_Hull_Welding_v2.pdf",
            "substantive_changes_count": 12,
            "editorial_changes_count": 3,
            "total_candidates": 1,
            "unimpacted_sop_count": 2,
            "unimpacted_sops": ["HVF_SOP_5_Gun_Calibration"],
            "counts_by_classification": {
                sa.IMPACT_DIRECT: 1,
                sa.IMPACT_POTENTIAL: 0,
                sa.IMPACT_HUMAN_REVIEW: 0,
                sa.IMPACT_INSUFFICIENT: 0,
                sa.IMPACT_NO_IDENTIFIED: 2
            },
            "counts_by_decision": {"PENDING": 0, "ACCEPTED": 1, "REJECTED": 0, "INVESTIGATE": 0},
            "candidates": [
                {
                    "impact_id": "IMP-1-2-11-01",
                    "classification": sa.IMPACT_DIRECT,
                    "affected_sop_id": "HVF_SOP_2_Turret_Integration",
                    "affected_title": "Turret Integration",
                    "affected_filename": "HVF_SOP_2_Turret_Integration.pdf",
                    "affected_section": "SECTION 1.0 — HULL PLINTH",
                    "affected_page": 1,
                    "source_change_id": "CHG-HW-11",
                    "source_section": "5.0.A SHOP-FLOOR EXECUTION",
                    "source_page": 6,
                    "dependency_type": "Direct Physical / Geometric Interface",
                    "evidence_strength": "High (Coupled Geometric Tolerance)",
                    "review_status": "ACCEPTED",
                    "reviewer_notes": "Sign-off verified.",
                    "explanation": "Welded hull upper deck plinth flatness directly dictates turret bearing seating.",
                    "source_passage": "Turret Base Mounting Plane Flatness: <= 0.35 mm across 2.2 m circle.",
                    "affected_passage": "Plinth Flatness Mapping: <= 0.035 mm TIR across 360 circle."
                }
            ]
        }

        report = sa.generate_impact_report(impact_result)
        self.assertIn("# CROSS-DOCUMENT IMPACT ANALYSIS REPORT", report)
        self.assertIn("IMP-1-2-11-01", report)
        self.assertIn("HVF_SOP_2_Turret_Integration", report)
        self.assertIn("ACCEPTED", report)
        self.assertIn("Sign-off verified.", report)
        self.assertIn("Source Changed Passage:", report)
        self.assertIn("Affected Document Evidence Passage:", report)

    # -------------------------------------------------------------------------
    # TEST 14: End-to-End Real SOP Pairs Integration
    # -------------------------------------------------------------------------
    def test_14_e2e_real_sop_pairs_integration(self):
        """Execute cross-document impact analysis across real SOP pairs in SOP/."""
        pairs = sa.get_available_sop_pairs(self.sop_dir)
        self.assertEqual(len(pairs), 5)

        # Pre-process all corpus documents once
        all_files = [f for f in sorted(os.listdir(self.sop_dir)) if f.endswith(".pdf")]
        corpus_docs = [dp.process_pdf(os.path.join(self.sop_dir, f)) for f in all_files]

        for p in pairs:
            comp = sa.compare_sop_files(p["baseline_path"], p["revised_path"])
            impact_res = sa.analyze_cross_document_impacts(
                comparison_result=comp,
                corpus_docs=corpus_docs,
                sop_dir=self.sop_dir,
                db_path=self.test_db
            )
            self.assertEqual(impact_res["status"], "success")
            self.assertGreater(impact_res["total_candidates"], 0, f"No candidates found for {p['logical_sop_id']}")
            self.assertIn(sa.IMPACT_DIRECT, impact_res["counts_by_classification"])

            # Verify report generation works cleanly
            rpt = sa.generate_impact_report(impact_res)
            self.assertTrue(len(rpt) > 500)
            self.assertIn("Executive Summary & Impact Metrics", rpt)


if __name__ == "__main__":
    print("=" * 70)
    print("PHASE 8 AUTOMATED VERIFICATION TEST SUITE: IMPACT ANALYSIS ENGINE")
    print("=" * 70)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestPhase8CrossDocumentImpactEngine)
    runner = unittest.TextTestRunner(verbosity=2)
    res = runner.run(suite)
    sys.exit(0 if res.wasSuccessful() else 1)
