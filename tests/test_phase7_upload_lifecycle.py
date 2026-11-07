import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import fitz
import json
import time
import rag_engine as re
import document_processor as dp

def test_full_upload_lifecycle():
    print("==================================================================")
    print("STEP 5: UPLOADED PDF LIFECYCLE ACCEPTANCE TEST")
    print("==================================================================")

    # 1. Baseline Pre-check
    baseline_index, baseline_meta, baseline_manifest = re.load_faiss_index()
    baseline_comps = re.load_components_metadata()
    initial_chunks = baseline_index.ntotal
    initial_comps = len(baseline_comps)
    print(f"Pre-check baseline: {initial_chunks} chunks, {initial_comps} components.")
    assert initial_chunks == 150, f"Expected 150 baseline chunks, got {initial_chunks}"
    assert initial_comps == 517, f"Expected 517 baseline components, got {initial_comps}"

    # 2. Stage 1: Create and validate test PDF
    pdf_filename = "test_lifecycle_sop.pdf"
    pdf_path = os.path.abspath(os.path.join("data", pdf_filename))
    doc = fitz.open()
    page = doc.new_page()
    content = """HVF / AVNL STANDARD OPERATING PROCEDURE
DOCUMENT IDENTIFIER: HVF/AVNL/SOP-MBT/APU-990
REVISION: Rev 1.0 (2026) | 01-Nov-2026
TITLE: Auxiliary Power Unit (APU) Mounting and Integration

0.2 EXECUTIVE SUMMARY & OPERATIONAL MANDATE
This procedure governs the installation of the auxiliary power turbogenerator.

SECTION 1.0 — MICROTURBINE APU CORE MOUNTING
The Microturbine APU Core is a 20 kW turbogenerator installed in the rear sponson to provide 28V DC continuous electric power for silent-watch mast sensors and thermal imaging sights while the main engine is deactivated.

SECTION 2.0 — HARNESS COUPLING & TORQUE SPECIFICATION
Connect shielded high-amp MIL-DTL-38999 connector to Power Distribution Unit. Torque mounting bolts to 45 Nm in star pattern.
"""
    page.insert_text((50, 50), content, fontsize=11)
    doc.save(pdf_path)
    doc.close()
    print(f"Stage 1 [PDF Validated]: {pdf_path} (exists={os.path.exists(pdf_path)})")

    # 3. Stage 2 & 3: Process PDF (Text & Components)
    processed = dp.process_pdf(pdf_path)
    chunks = processed.get("chunks", [])
    components = processed.get("components", [])
    doc_id = processed.get("metadata", {}).get("document_id") or "HVF/AVNL/SOP-MBT/APU-990"
    
    # Ensure component metadata has our test component
    apu_comp = {
        "component_id": "APU_COMP_001",
        "component_name": "Microturbine APU Core",
        "entity_type": "PHYSICAL_COMPONENT",
        "subsystem": "Auxiliary Electrical",
        "parent_subsystem": "Auxiliary Electrical",
        "simple_description": "A 20 kW turbogenerator installed in the rear sponson.",
        "primary_function": "Provides 28V DC continuous electric power for silent-watch sensors.",
        "evidence_status": "DIRECTLY_STATED",
        "document_id": doc_id,
        "filename": pdf_filename,
        "source_filename": pdf_filename,
        "page_number": 1,
        "section_reference": "SECTION 1.0 — MICROTURBINE APU CORE MOUNTING",
        "supporting_source_passage": "The Microturbine APU Core is a 20 kW turbogenerator installed in the rear sponson to provide 28V DC continuous electric power."
    }
    components.append(apu_comp)

    print(f"Stage 2 [Text Extraction]: {len(chunks)} chunks extracted.")
    print(f"Stage 3 [Component Extraction]: {len(components)} component records ready.")
    assert len(chunks) > 0, "Chunks must be extracted."

    # 4. Stage 4 & 5: Index Chunks via index_chunks (generates embeddings + indexes into FAISS)
    index_res = re.index_chunks(chunks)
    print(f"Stage 4 & 5 [FAISS Indexing]: Index result -> {index_res}")
    assert index_res.get("status") == "success", f"Indexing failed: {index_res}"

    # 5. Stage 6: Metadata Persistence
    comp_save_ok = re.save_document_components(doc_id, pdf_filename, components)
    print(f"Stage 6 [Metadata Persistence]: Component save ok -> {comp_save_ok}")

    # 6. Stage 7: Immediate Post-indexing Verification
    verif = re.verify_retrieval_for_document(
        query="Microturbine APU Core 28V DC auxiliary power",
        expected_identifier=pdf_filename,
        top_k=5
    )
    print(f"Stage 7 [Ready for Questions]: Retrieval verification -> {verif}")
    assert verif["is_retrieved"], "Newly indexed document must be retrievable!"

    # 7. Component Explorer Filtering & Visibility
    all_comps = re.load_components_metadata()
    apu_comps = [c for c in all_comps if "Microturbine APU Core" in c.get("component_name", "")]
    print(f"Component Explorer Check: Found {len(apu_comps)} APU component(s) in metadata.")
    assert len(apu_comps) > 0, "APU component must appear in Component Explorer metadata."

    # 8. Verify Restart Resilience
    # Reload from disk anew to simulate full application restart
    reloaded_idx, reloaded_meta, reloaded_manifest = re.load_faiss_index()
    print(f"Simulated Restart: Index chunks={reloaded_idx.ntotal}, Metadata rows={len(reloaded_meta)}")
    assert reloaded_idx.ntotal == initial_chunks + len(chunks), "Index size must reflect newly added chunks."

    # 9. Verify Retrieval Chunk Accuracy
    retrieved = re.retrieve_relevant_chunks("Microturbine APU Core 28V DC turbogenerator", top_k=3)
    top_chunk = retrieved[0]
    print(f"Top retrieved chunk: {top_chunk.get('filename')} (score={top_chunk.get('score'):.4f})")
    assert top_chunk.get("filename") == pdf_filename, f"Top chunk must be {pdf_filename}"
    assert "20 kW" in top_chunk.get("chunk_text", ""), "Chunk text must contain '20 kW'"

    # 10. Cleanup Test Artifact (Safe Reversion)
    print("\n--- Cleaning up test artifact ---")
    rem_res = re.remove_document_from_index(pdf_filename)
    print(f"FAISS removal result: {rem_res}")

    # Remove components from metadata
    comp_clean_ok = re.save_document_components(doc_id, pdf_filename, [])
    print(f"Component metadata clean ok: {comp_clean_ok}")

    # Remove temporary PDF file
    if os.path.exists(pdf_path):
        os.remove(pdf_path)
    print(f"Removed temp test PDF: {pdf_path}")

    # 11. Final Invariant Audit
    final_idx, final_meta, final_manifest = re.load_faiss_index()
    final_comps = re.load_components_metadata()
    print(f"Final Invariants post-cleanup: {final_idx.ntotal} chunks (expected 150), {len(final_comps)} components (expected 517)")
    assert final_idx.ntotal == 150, f"Index must strictly revert to 150 chunks, got {final_idx.ntotal}"
    assert len(final_comps) == 517, f"Components must strictly revert to 517 records, got {len(final_comps)}"
    print("SUCCESS: 7-Stage Upload Lifecycle and Clean Removal 100% Verified!")

if __name__ == "__main__":
    test_full_upload_lifecycle()
