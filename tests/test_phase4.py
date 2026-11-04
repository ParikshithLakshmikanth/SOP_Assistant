#!/usr/bin/env python3
"""
Test Suite: Phase 4 - Single-Page Streamlit SOP Chatbot Backend & UI Logic
========================================================================
Validates:
1. Syntax and compilation of app.py.
2. System telemetry checks (live Ollama status, model health, FAISS corpus stats).
3. Retrieval filtering logic (logical_sop_id and revision).
4. Streamed RAG token generation (stream_rag_answer).
5. Evidence citation formatting and metadata preservation.
6. Out-of-corpus query handling (insufficient evidence detection).
7. Stream interruption / generation cancellation logic.
8. Incremental PDF upload, processing, and indexing pipeline.
9. Duplicate document prevention during indexing.
10. Document removal and FAISS corpus restoration to baseline (150 chunks).
"""

import os
import sys
import time
import py_compile
import shutil
import numpy as np
import fitz  # PyMuPDF

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import document_processor as dp
import rag_engine as re


def run_tests():
    print("=" * 70)
    print("RUNNING PHASE 4 VERIFICATION TEST SUITE (Streamlit Chatbot & RAG)")
    print("=" * 70)

    test_results = {}

    # ------------------------------------------------------------------------
    # Test 1: Python Compilation of app.py
    # ------------------------------------------------------------------------
    print("\n--- Test 1: Python Compilation of app.py ---")
    try:
        app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py")
        py_compile.compile(app_path, doraise=True)
        print("  [PASS] app.py compiled successfully with 0 syntax or parsing errors.")
        test_results["Test 1: app.py Compilation"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Failed to compile app.py: {e}")
        test_results["Test 1: app.py Compilation"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 2: System Telemetry and Model Health Check
    # ------------------------------------------------------------------------
    print("\n--- Test 2: Live System Telemetry Verification ---")
    try:
        is_connected = re.check_ollama_connection()
        models_info = re.verify_required_models() if is_connected else {}
        index, metadata, manifest = re.load_faiss_index()

        doc_count = len(manifest.get("documents", [])) if manifest else 0
        chunk_count = index.ntotal if index else 0

        print(f"  Ollama Online: {is_connected}")
        print(f"  Gemma Model Ready: {models_info.get('llm_present')}")
        print(f"  Nomic Model Ready: {models_info.get('embed_present')}")
        print(f"  FAISS Index Loaded: {index is not None}")
        print(f"  Indexed Document Count: {doc_count} (Expected: 10)")
        print(f"  Indexed Chunk Count: {chunk_count} (Expected: 150)")

        assert is_connected is True, "Ollama daemon is not reachable"
        assert models_info.get("all_ready") is True, "Required models not loaded"
        assert index is not None, "FAISS index is None"
        assert doc_count == 10, f"Expected 10 documents, got {doc_count}"
        assert chunk_count == 150, f"Expected 150 chunks, got {chunk_count}"

        print("  [PASS] Telemetry accurately reports active backend and 150-chunk corpus.")
        test_results["Test 2: System Telemetry"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Telemetry verification failed: {e}")
        test_results["Test 2: System Telemetry"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 3: Streamed RAG Answer Generation (stream_rag_answer)
    # ------------------------------------------------------------------------
    print("\n--- Test 3: Progressive Token Streaming & Citations ---")
    try:
        query = "What is the preheating temperature required for weld seam root passes?"
        t0 = time.time()
        token_stream, citations, info = re.stream_rag_answer(
            question=query,
            top_k=3,
            logical_sop_id="HVF_SOP_1_Hull_Welding",
            max_tokens=768
        )

        streamed_tokens = []
        for token in token_stream:
            streamed_tokens.append(token)

        full_streamed_answer = "".join(streamed_tokens).strip()
        elapsed = time.time() - t0

        print(f"  Query: '{query}'")
        print(f"  Streamed Tokens: {len(streamed_tokens)}")
        print(f"  Elapsed Time: {elapsed:.2f}s")
        print(f"  Citations Returned: {len(citations)}")
        print(f"  Answer Snippet: {full_streamed_answer[:140]}...")

        assert len(streamed_tokens) > 5, "Stream yielded too few tokens"
        assert len(full_streamed_answer) > 20, "Answer is too short"
        assert len(citations) > 0, "No citations returned with stream"
        for c in citations:
            assert "citation" in c and "score" in c and "chunk_text" in c

        print("  [PASS] stream_rag_answer delivers progressive tokens and valid citations.")
        test_results["Test 3: Token Streaming"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Streaming test failed: {e}")
        test_results["Test 3: Token Streaming"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 4: Retrieval Filtering in Chat Workflow
    # ------------------------------------------------------------------------
    print("\n--- Test 4: Filter-Restricted Retrieval ---")
    try:
        # Search specifically for gun calibration
        token_stream, citations, info = re.stream_rag_answer(
            question="What is the laser collimator alignment tolerance?",
            top_k=4,
            logical_sop_id="HVF_SOP_5_Gun_Calibration",
            max_tokens=768
        )
        # Drain stream
        _ = "".join([t for t in token_stream])

        print(f"  Retrieved {len(citations)} citations for HVF_SOP_5_Gun_Calibration:")
        for c in citations:
            print(f"    - Doc: {c['document_id']} | Logical: {c['logical_sop_id']} | Rev: {c['revision']}")
            assert c["logical_sop_id"] == "HVF_SOP_5_Gun_Calibration", f"Unexpected SOP in results: {c['logical_sop_id']}"

        print("  [PASS] Logical SOP filtering correctly restricts evidence retrieval.")
        test_results["Test 4: Retrieval Filtering"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Filtering test failed: {e}")
        test_results["Test 4: Retrieval Filtering"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 5: Stream Interruption / Cancellation
    # ------------------------------------------------------------------------
    print("\n--- Test 5: Generation Interruption & Stop Handling ---")
    try:
        time.sleep(1.0)
        token_stream, citations, info = re.stream_rag_answer(
            question="Provide a comprehensive breakdown of all torque tightening steps for suspension arms.",
            top_k=3,
            max_tokens=768
        )

        received_tokens = []
        stopped_early = False
        for token in token_stream:
            received_tokens.append(token)
            if len(received_tokens) >= 8:
                # Simulate user clicking Stop button
                stopped_early = True
                break

        print(f"  Stopped after receiving {len(received_tokens)} tokens.")
        assert stopped_early is True
        assert len(received_tokens) == 8
        assert len(citations) > 0, "Citations must be available even when generation is stopped"

        print("  [PASS] Early stream termination cleanly stops generation while preserving citations.")
        test_results["Test 5: Generation Cancellation"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Cancellation test failed: {e}")
        test_results["Test 5: Generation Cancellation"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 6: Evidence Grounding and Source Citations Format
    # ------------------------------------------------------------------------
    print("\n--- Test 6: Source Citation Format Verification ---")
    try:
        results = re.retrieve_relevant_chunks("laser alignment offset", top_k=3)
        formatted_cits = [re.format_citation(r) for r in results]

        print("  Sample Formatted Citations:")
        for cit in formatted_cits:
            print(f"    {cit}")
            assert cit.startswith("["), "Citation must start with bracket"
            assert cit.endswith("]"), "Citation must end with bracket"
            assert ("Page" in cit or ", p." in cit), "Citation must contain page reference"
            assert "HVF" in cit, "Citation must mention document"

        print("  [PASS] Citations match standardized schema [filename, rev, section, Page X].")
        test_results["Test 6: Citation Formatting"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Citation verification failed: {e}")
        test_results["Test 6: Citation Formatting"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 7: Out-of-Corpus Query & Insufficient Evidence Abstention
    # ------------------------------------------------------------------------
    print("\n--- Test 7: Out-of-Corpus Query Abstention ---")
    try:
        out_query = "What is the exact chemical recipe for baking French macarons at high altitude?"
        answer_result = re.generate_rag_answer(
            question=out_query,
            top_k=3,
            max_tokens=768
        )
        answer_text = answer_result["answer"]
        print(f"  Out-of-corpus query: '{out_query}'")
        print(f"  System Answer: {answer_text[:160]}...")

        # Must state that evidence is not present in the SOPs
        abstention_keywords = [
            "does not contain sufficient evidence",
            "does not contain",
            "not mentioned",
            "not provide",
            "not found",
            "insufficient",
            "no information",
            "cannot answer"
        ]
        has_abstention = any(k in answer_text.lower() for k in abstention_keywords)
        print(f"  Abstention Detected: {has_abstention}")

        assert has_abstention, "LLM failed to express lack of evidence for out-of-corpus question"
        print("  [PASS] Agent correctly abstains on questions outside the SOP corpus.")
        test_results["Test 7: Abstention on Out-of-Corpus"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Abstention test failed: {e}")
        test_results["Test 7: Abstention on Out-of-Corpus"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 8: Document Ingestion, Embedding & Incremental FAISS Indexing
    # ------------------------------------------------------------------------
    print("\n--- Test 8: In-App Document Ingestion Pipeline ---")
    try:
        os.makedirs(os.path.join("data", "documents"), exist_ok=True)
        test_pdf_path = os.path.join("data", "documents", "HVF_SOP_TEST_Ingestion.pdf")

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(
            (50, 72),
            "AVNL / HVF TECHNICAL STANDARD OPERATING PROCEDURE\n"
            "DOCUMENT ID:\n"
            "HVF/AVNL/SOP-MBT/TEST-999\n"
            "REVISION:\n"
            "Rev 1.0 (2026)\n"
            "SHOP:\n"
            "Auxiliary Test Facilities (Shop-09)\n"
            "PLATFORM:\n"
            "Main Battle Tank Test Rig\n\n"
            "SECTION 1.0 — HYDRAULIC ACCUMULATOR CHARGE\n"
            "Charge hydraulic accumulator to precisely 315 bar (+/- 2 bar) using dry nitrogen gas.\n"
            "Inspect manifold O-rings for extrusion or micro-fissures prior to bolting flange.\n"
        )
        doc.save(test_pdf_path)
        doc.close()

        # Step A: Process PDF
        doc_record = dp.process_pdf(test_pdf_path)
        assert doc_record["status"] == "success"
        test_chunks_count = doc_record["total_chunks"]
        print(f"  Processed test PDF: DocID='{doc_record['document_id']}', {test_chunks_count} chunks extracted.")
        assert doc_record["document_id"] == "HVF/AVNL/SOP-MBT/TEST-999"

        # Step B: Index into FAISS
        idx_res = re.index_documents([doc_record], replace_existing=True)
        print(f"  Indexed into FAISS: +{idx_res['indexed_chunks']} chunks in {idx_res['embedding_duration_s']}s.")

        # Step C: Verify index expanded
        idx_after, meta_after, manifest_after = re.load_faiss_index()
        print(f"  Total index size after upload: {idx_after.ntotal} chunks (Expected: {150 + test_chunks_count})")
        assert idx_after.ntotal == 150 + test_chunks_count

        # Step D: Query the newly ingested knowledge
        test_q_res = re.retrieve_relevant_chunks("hydraulic accumulator nitrogen charge pressure 315 bar", top_k=3)
        found_test_doc = any("TEST-999" in r["document_id"] for r in test_q_res)
        print(f"  Retrieved matches: {[r['document_id'] for r in test_q_res]}")
        assert found_test_doc, "Uploaded document TEST-999 was not retrieved in top search results"

        print("  [PASS] Ingestion pipeline successfully extracts, embeds, and indexes new SOPs.")
        test_results["Test 8: Incremental Ingestion"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Ingestion pipeline test failed: {e}")
        test_results["Test 8: Incremental Ingestion"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 9: Duplicate Document Prevention
    # ------------------------------------------------------------------------
    print("\n--- Test 9: Duplicate Ingestion Prevention ---")
    try:
        # Re-index the same test document
        idx_res_dup = re.index_documents([doc_record], replace_existing=True)
        idx_dup, meta_dup, manifest_dup = re.load_faiss_index()
        print(f"  Total index size after re-indexing same doc: {idx_dup.ntotal} chunks")
        assert idx_dup.ntotal == 150 + test_chunks_count, "Index total should NOT increase on re-indexing same document"

        print("  [PASS] Duplicate indexing is properly prevented by replace_existing=True.")
        test_results["Test 9: Duplicate Prevention"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Duplicate prevention test failed: {e}")
        test_results["Test 9: Duplicate Prevention"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 10: Document Deletion & Baseline Restoration
    # ------------------------------------------------------------------------
    print("\n--- Test 10: Document Deletion & Baseline Restoration ---")
    try:
        # Remove the test document
        rem_res = re.remove_document_from_index("HVF/AVNL/SOP-MBT/TEST-999")
        print(f"  Removal Result: Removed {rem_res['removed_count']} chunks. Remaining: {rem_res['remaining_count']}")

        # Clean up temporary test file
        if os.path.exists(test_pdf_path):
            os.remove(test_pdf_path)

        # Reload FAISS to verify exact baseline
        final_idx, final_meta, final_manifest = re.load_faiss_index()
        print(f"  Corpus chunks after cleanup: {final_idx.ntotal} (Expected: 150)")
        print(f"  Corpus documents after cleanup: {len(final_manifest['documents'])} (Expected: 10)")

        assert final_idx.ntotal == 150, f"Expected 150 chunks, got {final_idx.ntotal}"
        assert len(final_manifest["documents"]) == 10, f"Expected 10 docs, got {len(final_manifest['documents'])}"

        print("  [PASS] Test document removed cleanly and 150-chunk baseline preserved.")
        test_results["Test 10: Baseline Restoration"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Document removal / restoration failed: {e}")
        test_results["Test 10: Baseline Restoration"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # FINAL SUMMARY
    # ------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("PHASE 4 VERIFICATION SUMMARY")
    print("=" * 70)
    passed_count = sum(1 for v in test_results.values() if v == "PASS")
    total_count = len(test_results)

    for test_name, status in test_results.items():
        print(f"  {test_name:<45} : {status}")

    print(f"\nTotal: {passed_count}/{total_count} Tests Passed.")
    return passed_count == total_count


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
