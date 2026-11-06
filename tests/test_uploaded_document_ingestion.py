"""
Test Suite: Uploaded Document Ingestion, Persistence, and Retrieval Verification
Validates end-to-end ingestion pipeline, transactional FAISS indexing, duplicate handling,
index health diagnostics, and V2-mode retrieval of user-uploaded SOP documents.
"""

import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import fitz  # PyMuPDF

import document_processor as dp
import rag_engine as re


class TestUploadedDocumentIngestion(unittest.TestCase):
    """
    Comprehensive test suite covering all 15 verification requirements for
    uploaded SOP PDF document ingestion, persistence, and retrieval.
    """

    @classmethod
    def setUpClass(cls):
        # Create a shared temporary directory for isolated test indices
        cls.test_dir = tempfile.mkdtemp(prefix="sop_test_ingestion_")

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_dir):
            shutil.rmtree(cls.test_dir, ignore_errors=True)

    def _create_sample_pdf(self, file_path: str, title: str, doc_id: str, section: str, body: str):
        """Helper to create a well-formed PDF with PyMuPDF."""
        doc = fitz.open()
        page = doc.new_page()
        text_content = (
            f"HEAVY VEHICLES FACTORY (HVF)\n"
            f"STANDARD OPERATING PROCEDURE: {title}\n"
            f"DOCUMENT ID: {doc_id}\n"
            f"REVISION: Rev 1.0 (2026) | 30-Oct-2026\n"
            f"TARGET PLATFORM: MBT T-90S Bhishma\n"
            f"PRODUCTION SHOP: Electrical & Power Unit Shop\n\n"
            f"SECTION 1.0 {section}\n"
            f"{body}\n"
        )
        page.insert_text((50, 50), text_content, fontsize=10)
        doc.save(file_path)
        doc.close()

    def _create_arbitrary_pdf(self, file_path: str, title: str, body: str):
        """Helper to create an arbitrary SOP PDF without standard HVF headers."""
        doc = fitz.open()
        page = doc.new_page()
        text_content = (
            f"{title}\n\n"
            f"SECTION 1.0 OPERATIONAL BENCHMARKS\n"
            f"{body}\n"
        )
        page.insert_text((50, 50), text_content, fontsize=10)
        doc.save(file_path)
        doc.close()

    # ------------------------------------------------------------------------
    # Test 1: Upload and PDF Processing
    # ------------------------------------------------------------------------
    def test_01_upload_and_processing(self):
        """Test 1: Validates complete end-to-end processing of a test SOP PDF."""
        pdf_path = os.path.join(self.test_dir, "Auxiliary_Power_Unit.pdf")
        self._create_sample_pdf(
            pdf_path,
            title="AUXILIARY POWER UNIT (APU) INTEGRATION PROTOCOL",
            doc_id="HVF/AVNL/SOP-MBT/APU-901",
            section="TURBINE ROTOR CLEARANCE",
            body="Turbine rotor radial clearance benchmark shall be strictly maintained between 0.35 mm and 0.45 mm."
        )

        doc_record = dp.process_pdf(pdf_path)
        self.assertEqual(doc_record["status"], "success")
        self.assertEqual(doc_record["document_id"], "HVF/AVNL/SOP-MBT/APU-901")
        self.assertEqual(doc_record["filename"], "Auxiliary_Power_Unit.pdf")
        self.assertGreater(doc_record["total_pages"], 0)
        self.assertGreater(doc_record["total_chunks"], 0)

    # ------------------------------------------------------------------------
    # Test 2: Chunk Creation & Schema Integrity
    # ------------------------------------------------------------------------
    def test_02_chunk_creation_and_schema(self):
        """Test 2: Verifies chunk count, chunk schema, section titles, and token counts."""
        pdf_path = os.path.join(self.test_dir, "Auxiliary_Power_Unit.pdf")
        doc_record = dp.process_pdf(pdf_path)
        chunks = doc_record["chunks"]
        self.assertGreater(len(chunks), 0)

        required_keys = {
            "chunk_id", "document_id", "logical_sop_id", "filename",
            "revision", "section_title", "page_number", "chunk_text",
            "token_count", "char_count"
        }
        for chunk in chunks:
            self.assertTrue(required_keys.issubset(chunk.keys()))
            self.assertEqual(chunk["document_id"], "HVF/AVNL/SOP-MBT/APU-901")
            self.assertGreater(chunk["token_count"], 0)
            self.assertIn("clearance", chunk["chunk_text"].lower())

    # ------------------------------------------------------------------------
    # Test 3: Embedding Dimensions & Normalization
    # ------------------------------------------------------------------------
    def test_03_embedding_dimension_and_normalization(self):
        """Test 3: Confirms generated embeddings are 768-dim, float32, and L2-normalized."""
        test_texts = [
            "Turbine rotor radial clearance benchmark shall be maintained at 0.40 mm.",
            "Fuel flow regulator calibration pressure tolerance is 3.5 bar."
        ]
        vectors = re.generate_embeddings(test_texts, normalize=True)
        self.assertEqual(vectors.shape, (2, 768))
        self.assertEqual(vectors.dtype, np.float32)

        norms = np.linalg.norm(vectors, axis=1)
        for norm in norms:
            self.assertAlmostEqual(norm, 1.0, places=4)

    # ------------------------------------------------------------------------
    # Test 4: FAISS Insertion in Isolated Index
    # ------------------------------------------------------------------------
    def test_04_faiss_insertion_isolated(self):
        """Test 4: Confirms vectors added to FAISS index and ntotal increases correctly."""
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_4")
        os.makedirs(isolated_idx_dir, exist_ok=True)

        sample_chunk = {
            "chunk_id": "APU_TEST_C0001",
            "document_id": "DOC/APU_TEST",
            "logical_sop_id": "APU_TEST",
            "filename": "APU_Test.pdf",
            "revision": "Rev 1.0 (Uploaded)",
            "section_title": "1.0 BENCHMARKS",
            "page_number": 1,
            "chunk_text": "APU turbine alignment benchmark tolerance 0.05 mm.",
            "token_count": 25,
            "char_count": 60
        }

        summary = re.index_chunks([sample_chunk], index_dir=isolated_idx_dir, replace_existing=False)
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["indexed_chunks"], 1)
        self.assertEqual(summary["total_index_chunks"], 1)

        idx, meta, man = re.load_faiss_index(isolated_idx_dir)
        self.assertEqual(idx.ntotal, 1)

    # ------------------------------------------------------------------------
    # Test 5: Metadata Synchronization
    # ------------------------------------------------------------------------
    def test_05_metadata_synchronization(self):
        """Test 5: Confirms metadata list length matches FAISS ntotal exactly."""
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_4")
        idx, meta, man = re.load_faiss_index(isolated_idx_dir)
        self.assertEqual(len(meta), idx.ntotal)
        self.assertEqual(meta[0]["chunk_id"], "APU_TEST_C0001")

    # ------------------------------------------------------------------------
    # Test 6: Manifest Synchronization
    # ------------------------------------------------------------------------
    def test_06_manifest_synchronization(self):
        """Test 6: Confirms manifest chunk_count matches FAISS ntotal and document listed."""
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_4")
        idx, meta, man = re.load_faiss_index(isolated_idx_dir)
        self.assertEqual(man["chunk_count"], idx.ntotal)
        doc_ids = [d["document_id"] for d in man.get("documents", [])]
        self.assertIn("DOC/APU_TEST", doc_ids)

    # ------------------------------------------------------------------------
    # Test 7: Duplicate Upload Prevention
    # ------------------------------------------------------------------------
    def test_07_duplicate_upload_prevention(self):
        """Test 7: Uploading identical document content skips redundant indexing."""
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_7")
        os.makedirs(isolated_idx_dir, exist_ok=True)

        sample_chunk = {
            "chunk_id": "APU_DUP_C0001",
            "document_id": "DOC/APU_DUP",
            "logical_sop_id": "APU_DUP",
            "filename": "APU_Dup.pdf",
            "revision": "Rev 1.0 (Uploaded)",
            "section_title": "1.0 BENCHMARKS",
            "page_number": 1,
            "chunk_text": "APU electrical load test benchmark 28 VDC at 400 Amps.",
            "token_count": 30,
            "char_count": 70
        }

        # First indexing
        s1 = re.index_chunks([sample_chunk], index_dir=isolated_idx_dir)
        self.assertEqual(s1["status"], "success")
        self.assertEqual(s1["total_index_chunks"], 1)

        # Second indexing of identical content
        s2 = re.index_chunks([sample_chunk], index_dir=isolated_idx_dir)
        self.assertEqual(s2["status"], "duplicate_skipped")
        self.assertEqual(s2["indexed_chunks"], 0)
        self.assertEqual(s2["total_index_chunks"], 1)

    # ------------------------------------------------------------------------
    # Test 8: Same Filename with Different Content Replacement
    # ------------------------------------------------------------------------
    def test_08_same_filename_different_content_replacement(self):
        """Test 8: Cleanly replaces previous chunks without orphan vectors or desynchronization."""
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_8")
        os.makedirs(isolated_idx_dir, exist_ok=True)

        chunk_v1 = {
            "chunk_id": "SOP_REPL_C0001",
            "document_id": "DOC/SOP_REPL",
            "logical_sop_id": "SOP_REPL",
            "filename": "SOP_Replace.pdf",
            "revision": "Rev 1.0 (Uploaded)",
            "section_title": "1.0 BENCHMARKS",
            "page_number": 1,
            "chunk_text": "Original specification text version one.",
            "token_count": 20,
            "char_count": 50
        }
        re.index_chunks([chunk_v1], index_dir=isolated_idx_dir)

        # Replacement chunks with different content (2 chunks)
        chunk_v2_a = {
            "chunk_id": "SOP_REPL_C0001",
            "document_id": "DOC/SOP_REPL",
            "logical_sop_id": "SOP_REPL",
            "filename": "SOP_Replace.pdf",
            "revision": "Rev 2.0 (Uploaded)",
            "section_title": "1.0 UPDATED BENCHMARKS",
            "page_number": 1,
            "chunk_text": "Updated specification text part A with new tolerances.",
            "token_count": 25,
            "char_count": 60
        }
        chunk_v2_b = {
            "chunk_id": "SOP_REPL_C0002",
            "document_id": "DOC/SOP_REPL",
            "logical_sop_id": "SOP_REPL",
            "filename": "SOP_Replace.pdf",
            "revision": "Rev 2.0 (Uploaded)",
            "section_title": "2.0 ACCEPTANCE CRITERIA",
            "page_number": 2,
            "chunk_text": "Updated specification text part B with revised inspection guidelines.",
            "token_count": 25,
            "char_count": 65
        }

        s_repl = re.index_chunks([chunk_v2_a, chunk_v2_b], index_dir=isolated_idx_dir, replace_existing=True)
        self.assertEqual(s_repl["status"], "success")
        self.assertEqual(s_repl["indexed_chunks"], 2)
        self.assertEqual(s_repl["total_index_chunks"], 2)

        idx, meta, man = re.load_faiss_index(isolated_idx_dir)
        self.assertEqual(idx.ntotal, 2)
        self.assertEqual(len(meta), 2)
        self.assertEqual(man["chunk_count"], 2)
        # Verify old chunk was completely purged
        for c in meta:
            self.assertIn("Updated specification text", c["chunk_text"])

    # ------------------------------------------------------------------------
    # Test 9: Failed Embedding Handling
    # ------------------------------------------------------------------------
    def test_09_failed_embedding_preserves_state(self):
        """Test 9: Embedding failure preserves previous FAISS index uncorrupted."""
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_9")
        os.makedirs(isolated_idx_dir, exist_ok=True)

        initial_chunk = {
            "chunk_id": "INIT_C0001",
            "document_id": "DOC/INIT",
            "logical_sop_id": "INIT",
            "filename": "Initial.pdf",
            "revision": "Rev 1.0 (Uploaded)",
            "section_title": "1.0 INIT",
            "page_number": 1,
            "chunk_text": "Initial baseline content that must be preserved.",
            "token_count": 20,
            "char_count": 50
        }
        re.index_chunks([initial_chunk], index_dir=isolated_idx_dir)

        # Mock embedding failure
        bad_chunk = {
            "chunk_id": "FAIL_C0001",
            "document_id": "DOC/FAIL",
            "logical_sop_id": "FAIL",
            "filename": "Fail.pdf",
            "revision": "Rev 1.0 (Uploaded)",
            "section_title": "1.0 FAIL",
            "page_number": 1,
            "chunk_text": "This should fail during embedding.",
            "token_count": 20,
            "char_count": 50
        }

        with patch("rag_engine.generate_embeddings", side_effect=RuntimeError("Ollama connection timed out")):
            with self.assertRaises(RuntimeError):
                re.index_chunks([bad_chunk], index_dir=isolated_idx_dir)

        # Verify index on disk is intact
        idx, meta, man = re.load_faiss_index(isolated_idx_dir)
        self.assertEqual(idx.ntotal, 1)
        self.assertEqual(len(meta), 1)
        self.assertEqual(meta[0]["document_id"], "DOC/INIT")

    # ------------------------------------------------------------------------
    # Test 10: Failed Persistence Rollback
    # ------------------------------------------------------------------------
    def test_10_failed_persistence_rollback(self):
        """Test 10: Disk write failure leaves previous index intact."""
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_10")
        os.makedirs(isolated_idx_dir, exist_ok=True)

        initial_chunk = {
            "chunk_id": "INIT_C0001",
            "document_id": "DOC/INIT",
            "logical_sop_id": "INIT",
            "filename": "Initial.pdf",
            "revision": "Rev 1.0 (Uploaded)",
            "section_title": "1.0 INIT",
            "page_number": 1,
            "chunk_text": "Initial baseline content for rollback testing.",
            "token_count": 20,
            "char_count": 50
        }
        re.index_chunks([initial_chunk], index_dir=isolated_idx_dir)

        # Attempt to save to an invalid read-only location or simulate save failure
        with patch("rag_engine.save_faiss_index", side_effect=IOError("Disk write error")):
            with self.assertRaises(IOError):
                new_chunk = {
                    "chunk_id": "NEW_C0001",
                    "document_id": "DOC/NEW",
                    "logical_sop_id": "NEW",
                    "filename": "New.pdf",
                    "revision": "Rev 1.0 (Uploaded)",
                    "section_title": "1.0 NEW",
                    "page_number": 1,
                    "chunk_text": "New content that should not persist.",
                    "token_count": 20,
                    "char_count": 50
                }
                re.index_chunks([new_chunk], index_dir=isolated_idx_dir)

        idx, meta, man = re.load_faiss_index(isolated_idx_dir)
        self.assertEqual(idx.ntotal, 1)
        self.assertEqual(meta[0]["document_id"], "DOC/INIT")

    # ------------------------------------------------------------------------
    # Test 11: Application Rerun Reload
    # ------------------------------------------------------------------------
    def test_11_application_rerun_reload(self):
        """Test 11: Newly indexed document is immediately loaded and accessible on index reload."""
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_11")
        os.makedirs(isolated_idx_dir, exist_ok=True)

        test_chunk = {
            "chunk_id": "RERUN_C0001",
            "document_id": "DOC/RERUN",
            "logical_sop_id": "RERUN",
            "filename": "Rerun_Test.pdf",
            "revision": "Rev 1.0 (Uploaded)",
            "section_title": "1.0 RERUN",
            "page_number": 1,
            "chunk_text": "Hydraulic accumulator nitrogen pre-charge pressure benchmark is 110 bar.",
            "token_count": 25,
            "char_count": 75
        }
        re.index_chunks([test_chunk], index_dir=isolated_idx_dir)

        # Simulate Streamlit rerun: fresh call to load_faiss_index
        idx, meta, man = re.load_faiss_index(isolated_idx_dir)
        self.assertIsNotNone(idx)
        self.assertEqual(idx.ntotal, 1)
        self.assertEqual(meta[0]["document_id"], "DOC/RERUN")

    # ------------------------------------------------------------------------
    # Test 12: Application Restart Reload
    # ------------------------------------------------------------------------
    def test_12_application_restart_reload(self):
        """Test 12: Index reloaded from fresh process/call retains all chunks."""
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_11")
        # Read from disk directly to confirm binary and JSON durability
        index_path = os.path.join(isolated_idx_dir, re.INDEX_FILENAME)
        meta_path = os.path.join(isolated_idx_dir, re.METADATA_FILENAME)
        manifest_path = os.path.join(isolated_idx_dir, re.MANIFEST_FILENAME)

        self.assertTrue(os.path.exists(index_path))
        self.assertTrue(os.path.exists(meta_path))
        self.assertTrue(os.path.exists(manifest_path))

        idx, meta, man = re.load_faiss_index(isolated_idx_dir)
        self.assertEqual(idx.ntotal, 1)
        self.assertEqual(man["chunk_count"], 1)

    # ------------------------------------------------------------------------
    # Test 13: Retrieval of Uploaded Document in Default V2 Mode (ROOT CAUSE TEST)
    # ------------------------------------------------------------------------
    def test_13_retrieval_of_uploaded_document_in_default_v2_mode(self):
        """
        Test 13 (CRITICAL): Verifies newly uploaded SOP document is retrievable
        in the default 'V2 — Latest revision' mode and is NOT discarded.
        """
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_13")
        os.makedirs(isolated_idx_dir, exist_ok=True)

        # Add both a baseline V1 chunk and an uploaded SOP chunk
        baseline_chunk = {
            "chunk_id": "HVF_HW_C0001",
            "document_id": "HVF/AVNL/SOP-MBT/HW-101",
            "logical_sop_id": "HVF_SOP_1_Hull_Welding",
            "filename": "HVF_SOP_1_Hull_Welding.pdf",
            "revision": "Rev 4.2 (2026) | 30-Oct-2026",
            "section_title": "SECTION 1.0 PREHEAT",
            "page_number": 2,
            "chunk_text": "Baseline hull plate preheating minimum temperature is 120°C.",
            "token_count": 25,
            "char_count": 70
        }

        uploaded_apu_chunk = {
            "chunk_id": "DOC_APU_C0001",
            "document_id": "DOC/Auxiliary_Power_Unit",
            "logical_sop_id": "Auxiliary_Power_Unit",
            "filename": "Auxiliary_Power_Unit.pdf",
            "revision": "Rev 1.0 (Uploaded)",
            "section_title": "SECTION 2.0 ROTOR CLEARANCE",
            "page_number": 3,
            "chunk_text": "Auxiliary power unit turbine rotor clearance benchmark is 0.40 mm nominal.",
            "token_count": 28,
            "char_count": 78
        }

        re.index_chunks([baseline_chunk, uploaded_apu_chunk], index_dir=isolated_idx_dir)

        # 1. Verify V2 classification
        self.assertFalse(re.is_v2_chunk(baseline_chunk))
        self.assertTrue(re.is_v1_chunk(baseline_chunk))

        self.assertTrue(re.is_v2_chunk(uploaded_apu_chunk), "Uploaded document must be eligible as active latest (V2) SOP")
        self.assertFalse(re.is_v1_chunk(uploaded_apu_chunk))

        # 2. Query in default V2 mode: MUST retrieve the uploaded document!
        retrieved_v2 = re.retrieve_relevant_chunks(
            query="auxiliary power unit turbine rotor clearance",
            top_k=5,
            revision_mode="v2",
            index_dir=isolated_idx_dir
        )
        self.assertGreater(len(retrieved_v2), 0, "Uploaded document was discarded in V2 mode!")
        self.assertEqual(retrieved_v2[0]["document_id"], "DOC/Auxiliary_Power_Unit")
        self.assertIn("rotor clearance", retrieved_v2[0]["chunk_text"])

        # 3. Query in V1 mode: baseline V1 should be retrieved, uploaded doc excluded
        retrieved_v1 = re.retrieve_relevant_chunks(
            query="hull plate preheating",
            top_k=5,
            revision_mode="v1",
            index_dir=isolated_idx_dir
        )
        self.assertGreater(len(retrieved_v1), 0)
        self.assertEqual(retrieved_v1[0]["document_id"], "HVF/AVNL/SOP-MBT/HW-101")

        # 4. Query in All revisions mode: both retrievable
        retrieved_all = re.retrieve_relevant_chunks(
            query="auxiliary power unit",
            top_k=5,
            revision_mode="all",
            index_dir=isolated_idx_dir
        )
        self.assertGreater(len(retrieved_all), 0)
        self.assertEqual(retrieved_all[0]["document_id"], "DOC/Auxiliary_Power_Unit")

    # ------------------------------------------------------------------------
    # Test 14: Document-Level & Health Verification Utilities
    # ------------------------------------------------------------------------
    def test_14_document_level_and_health_verification_utilities(self):
        """Test 14: Validates verify_faiss_index_health, verify_document_indexed, and verify_retrieval_for_document."""
        isolated_idx_dir = os.path.join(self.test_dir, "idx_test_13")

        # Health check
        health = re.verify_faiss_index_health(index_dir=isolated_idx_dir)
        self.assertTrue(health["is_healthy"])
        self.assertEqual(health["total_vectors"], 2)
        self.assertEqual(health["baseline_chunks_count"], 1)
        self.assertEqual(health["uploaded_chunks_count"], 1)
        self.assertIn("Auxiliary_Power_Unit.pdf", health["uploaded_documents"])

        # Document indexed verification
        doc_verif = re.verify_document_indexed("Auxiliary_Power_Unit.pdf", index_dir=isolated_idx_dir)
        self.assertTrue(doc_verif["is_indexed"])
        self.assertEqual(doc_verif["chunk_count"], 1)
        self.assertFalse(doc_verif["is_standard"])

        # Retrieval verification
        retrieval_verif = re.verify_retrieval_for_document(
            query="auxiliary power unit turbine",
            expected_identifier="Auxiliary_Power_Unit.pdf",
            top_k=5,
            revision_mode="v2",
            index_dir=isolated_idx_dir
        )
        self.assertTrue(retrieval_verif["is_retrieved"])
        self.assertEqual(retrieval_verif["best_rank"], 1)
        self.assertIsNotNone(retrieval_verif["best_score"])

    # ------------------------------------------------------------------------
    # Test 15: Baseline Corpus Preservation (150 Chunks Across 10 SOPs)
    # ------------------------------------------------------------------------
    def test_15_baseline_corpus_preservation(self):
        """Test 15: Confirms all 10 baseline SOP PDFs and their 150 chunks remain intact and healthy."""
        prod_health = re.verify_faiss_index_health(index_dir=re.DEFAULT_INDEX_DIR)
        self.assertTrue(prod_health["is_healthy"], f"Baseline index is degraded: {prod_health['issues']}")
        self.assertEqual(prod_health["total_vectors"], 150, "Baseline 150 chunks count modified!")
        self.assertEqual(prod_health["baseline_chunks_count"], 150)
        self.assertEqual(prod_health["total_documents"], 10)
        self.assertEqual(len(prod_health["baseline_documents"]), 10)
        self.assertEqual(prod_health["uploaded_chunks_count"], 0)


if __name__ == "__main__":
    unittest.main()
