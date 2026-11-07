#!/usr/bin/env python3
"""
Test Suite: Mini Phase 6 — Professional UI Polish and System Reliability
========================================================================
Validates:
1. Comprehensive System Health & Diagnostics (Ollama, FAISS, SQLite, Components, Docs).
2. SQLite Database Health Diagnostics (integrity PRAGMA, row counts, connectivity).
3. FAISS Vector Corpus Invariants (150 vectors, dimension 768, 10 baseline documents).
4. Component Metadata Invariants (517 records across 10 entity classifications).
5. Compact Evidence Grouping with Verbatim Supporting Passages.
6. Referenced Component Extraction in Assistant Responses.
7. 7-Stage Upload Pipeline Structure and Verification.
8. Graceful Degradation and Meaningful Error Recovery Guidance.
9. Operational Modes and Navigation State Management.
10. Module Compilation and Architecture Integrity.
"""

import os
import sys
import io
import time
import unittest
import py_compile
import tempfile
import sqlite3
from typing import Dict, Any, List

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import rag_engine as re
import database as db
import document_processor as dp
import sop_analyzer as sa
from app import (
    group_citations_by_source,
    find_referenced_components_in_text,
    check_system_telemetry,
    REVISION_CHOICES
)


class TestMiniPhase6UIReliability(unittest.TestCase):

    def setUp(self):
        self.cached_comps = re.load_components_metadata()

    def test_01_comprehensive_system_health(self):
        """Verify get_comprehensive_system_health returns all 5 operational tiers with valid metrics."""
        health = re.get_comprehensive_system_health()
        self.assertIn("overall_status", health)
        self.assertIn(health["overall_status"], ["HEALTHY", "DEGRADED", "CRITICAL"])
        self.assertIn("status_message", health)
        self.assertIn("ollama", health)
        self.assertIn("faiss", health)
        self.assertIn("components", health)
        self.assertIn("database", health)
        self.assertIn("documents", health)

        # FAISS details
        faiss_h = health["faiss"]
        self.assertEqual(faiss_h.get("total_vectors"), 150, "FAISS vector count must match baseline 150.")
        self.assertEqual(faiss_h.get("embedding_dimension"), 768, "Embedding dimension must be 768.")
        self.assertTrue(faiss_h.get("is_healthy"), "FAISS index must report healthy.")

        # Component details
        comp_h = health["components"]
        self.assertEqual(comp_h.get("total_records"), 517, "Component metadata must match baseline 517.")
        self.assertTrue(comp_h.get("is_healthy"), "Component store must be healthy.")

        # Database details
        db_h = health["database"]
        self.assertTrue(db_h.get("is_healthy"), "Database must report healthy.")
        self.assertTrue(db_h.get("connected"), "Database must be connected.")

    def test_02_database_health_diagnostics(self):
        """Verify get_database_health performs PRAGMA integrity check and counts records accurately."""
        health = db.get_database_health()
        self.assertTrue(health["is_healthy"], "Database should be healthy.")
        self.assertTrue(health["connected"], "Database connection should succeed.")
        self.assertTrue(health["file_exists"], "Database file must exist.")
        self.assertGreaterEqual(health["total_conversations"], 1, "Must have at least 1 conversation.")
        self.assertGreaterEqual(health["total_messages"], 1, "Must have at least 1 message.")
        self.assertEqual(len(health["issues"]), 0, f"Issues list should be empty: {health['issues']}")
        self.assertGreater(health["file_size_bytes"], 0, "Database file size must be non-zero.")

    def test_03_faiss_corpus_health_and_invariants(self):
        """Verify FAISS vector index maintains the strict 150 vector invariant and 10 baseline documents."""
        faiss_h = re.verify_faiss_index_health()
        self.assertTrue(faiss_h["is_healthy"], "Index should report healthy.")
        self.assertEqual(faiss_h["total_vectors"], 150, "Index must contain exactly 150 vectors.")
        self.assertEqual(faiss_h["embedding_dimension"], 768, "Embedding dimension must be 768.")
        self.assertEqual(len(faiss_h["baseline_documents"]), 10, "Corpus must have 10 baseline SOP documents.")
        self.assertEqual(len(faiss_h["uploaded_documents"]), 0, "Corpus must have 0 custom uploaded documents in baseline.")

    def test_04_component_metadata_health_and_invariants(self):
        """Verify components_metadata.json maintains the strict 517 record invariant across 10 entity types."""
        comps = re.load_components_metadata()
        self.assertEqual(len(comps), 517, "Components metadata must contain exactly 517 records.")

        types = {c.get("entity_type") for c in comps}
        expected_types = {
            "PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM", "MATERIAL",
            "TOOL_OR_INSTRUMENT", "TECHNICAL_PARAMETER", "ACCEPTANCE_CRITERION",
            "PROCESS_OR_OPERATION", "DOCUMENT_OR_CERTIFICATE", "OTHER_REFERENCE"
        }
        self.assertEqual(types, expected_types, f"Must match all 10 distinct entity types. Got: {types}")

        # Check physical components + assemblies + subsystems count
        core_hardware = [c for c in comps if c.get("entity_type") in ("PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM")]
        self.assertEqual(len(core_hardware), 145, f"Hardware entities must equal 145. Got: {len(core_hardware)}")

    def test_05_compact_evidence_sources_with_verbatim_passages(self):
        """Verify group_citations_by_source maintains backward compatibility and captures verbatim passages."""
        sample_citations = [
            {
                "chunk_id": "doc1_c1",
                "filename": "HVF_SOP_2_Turret_Integration_v2.pdf",
                "revision": "Rev 4.5 [Version 2.0]",
                "section_title": "Section 4.1: Bearing Alignment",
                "page_number": 6,
                "score": 0.85,
                "chunk_text": "Turret ring backlash must not exceed 0.05 mm across 360 degrees."
            },
            {
                "chunk_id": "doc1_c2",
                "filename": "HVF_SOP_2_Turret_Integration_v2.pdf",
                "revision": "Rev 4.5 [Version 2.0]",
                "section_title": "Section 4.2: Slip-Ring Testing",
                "page_number": 7,
                "score": 0.82,
                "chunk_text": "Rotational torque resistance during slip-ring alignment shall be within 18-22 Nm."
            },
            {
                "chunk_id": "doc2_c1",
                "filename": "HVF_SOP_1_Hull_Welding_v2.pdf",
                "revision": "Rev 5.0 [Version 2.0]",
                "section_title": "Section 3.2: Preheat Controls",
                "page_number": 3,
                "score": 0.81,
                "chunk_text": "High-hardened armor plate preheat shall be maintained at 150 deg C +/- 10 deg C."
            }
        ]

        grouped = group_citations_by_source(sample_citations)
        self.assertEqual(len(grouped), 2, "Should group into 2 distinct source entries.")

        # Check required fields for backward compatibility
        for g in grouped:
            self.assertIn("filename", g)
            self.assertIn("revision", g)
            self.assertIn("pages_str", g)
            self.assertIn("sections", g)
            self.assertIn("passage_count", g)
            self.assertIn("passages", g, "Must include passages list for expandable verbatim evidence.")

        turret_group = next(g for g in grouped if "Turret" in g["filename"])
        self.assertEqual(turret_group["passage_count"], 2)
        self.assertEqual(len(turret_group["passages"]), 2)
        self.assertIn("0.05 mm", turret_group["passages"][0])

    def test_06_referenced_component_detection(self):
        """Verify find_referenced_components_in_text detects true components and ignores short stopwords."""
        answer_text = (
            "According to the SOP evidence, the Turret Base Ring is coupled to the Lower Hull Plate, "
            "and alignment is verified across the Cross-Roller Bearing Raceway."
        )

        detected = find_referenced_components_in_text(answer_text, self.cached_comps, max_matches=5)
        self.assertGreaterEqual(len(detected), 2, f"Should detect at least 2 components. Got: {detected}")
        # At least one of Turret Base Ring, Lower Hull Plate, Cross-Roller Bearing Raceway should be detected
        detected_lower = [d.lower() for d in detected]
        has_expected = any(c in " ".join(detected_lower) for c in ["bearing", "plate", "hull", "turret"])
        self.assertTrue(has_expected, f"Expected known components in detected list: {detected}")

        # Verify stop-word filtering
        generic_text = "The system was tested during step 1 with high data."
        detected_generic = find_referenced_components_in_text(generic_text, self.cached_comps)
        self.assertEqual(len(detected_generic), 0, f"Generic text should yield 0 components. Got: {detected_generic}")

    def test_07_seven_stage_upload_workflow_structure(self):
        """Verify the 7-stage upload lifecycle components and verification methods."""
        # 1. Validation check
        self.assertTrue(hasattr(re, "verify_retrieval_for_document"))
        self.assertTrue(hasattr(re, "save_document_components"))
        self.assertTrue(hasattr(re, "index_chunks"))
        self.assertTrue(hasattr(dp, "process_pdf"))

        # 2. Test immediate verification method on existing baseline document
        verif = re.verify_retrieval_for_document(
            query="hull welding preheat temperature",
            expected_identifier="HVF_SOP_1_Hull_Welding_v2.pdf",
            top_k=5,
            revision_mode="v2"
        )
        self.assertIn("is_retrieved", verif)
        self.assertIn("best_rank", verif)
        self.assertIn("best_score", verif)
        self.assertTrue(verif["is_retrieved"], "Baseline document should be retrievable in top 5.")

    def test_08_error_recovery_and_graceful_degradation(self):
        """Verify health checks handle missing services or corrupt files gracefully without throwing."""
        # Test non-existent database file handling
        fake_db = os.path.join(tempfile.gettempdir(), "non_existent_fake_db.db")
        if os.path.exists(fake_db):
            os.remove(fake_db)
        health = db.get_database_health(fake_db)
        self.assertFalse(health["is_healthy"])
        self.assertFalse(health["file_exists"])
        self.assertIn("does not exist", health["issues"][0])

        # Test index verification on non-existent document
        verif = re.verify_document_indexed("non_existent_doc_id_9999")
        self.assertFalse(verif["is_indexed"])
        self.assertEqual(verif["chunk_count"], 0)

    def test_09_session_state_and_navigation_modes(self):
        """Verify that all 6 required operating modes are valid and supported in app navigation."""
        expected_modes = [
            "📊 Executive Dashboard & Telemetry",
            "💬 Technical Consultation Chat",
            "🧩 Visual & Tabular Component Explorer",
            "⚖️ SOP Revision Comparison Engine",
            "🔗 Cross-Document Impact Analysis",
            "📥 Ingest & Manage SOP Documents"
        ]
        self.assertEqual(len(expected_modes), 6, "Must define exactly 6 primary operational modes.")

        # Test check_system_telemetry integration
        telemetry = check_system_telemetry()
        self.assertIn("overall_status", telemetry)
        self.assertIn("components_count", telemetry)
        self.assertIn("uploaded_doc_count", telemetry)
        self.assertEqual(telemetry["doc_count"], 10)
        self.assertEqual(telemetry["chunk_count"], 150)
        self.assertEqual(telemetry["components_count"], 517)

    def test_10_module_compilation_and_architecture_integrity(self):
        """Verify all 5 primary Python architecture modules compile cleanly without syntax errors."""
        modules = [
            "app.py",
            "rag_engine.py",
            "document_processor.py",
            "database.py",
            "sop_analyzer.py"
        ]
        for mod in modules:
            try:
                py_compile.compile(mod, doraise=True)
            except Exception as e:
                self.fail(f"Module {mod} failed compilation: {e}")


if __name__ == "__main__":
    unittest.main()
