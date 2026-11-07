import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import rag_engine as re
import sop_analyzer as sa

def test_revision_and_impact():
    print("==================================================================")
    print("STEP 6: REVISION AND IMPACT ANALYSIS ACCEPTANCE TEST")
    print("==================================================================")

    # 1. Revision Mode Isolation
    query = "turret mount alignment bearing laser"

    # V1 Mode
    chunks_v1 = re.retrieve_relevant_chunks(query, revision_mode="v1", top_k=5)
    print(f"V1 Retrieval: {len(chunks_v1)} chunks retrieved.")
    assert len(chunks_v1) > 0, "V1 retrieval must return chunks."
    for c in chunks_v1:
        assert re.is_v1_chunk(c), f"V1 mode returned non-V1 chunk: {c.get('filename')} ({c.get('revision')})"
        assert not re.is_v2_chunk(c), f"V1 mode returned V2 chunk: {c.get('filename')}"
    print("V1 Strict Revision Isolation: PASS")

    # V2 Mode
    chunks_v2 = re.retrieve_relevant_chunks(query, revision_mode="v2", top_k=5)
    print(f"V2 Retrieval: {len(chunks_v2)} chunks retrieved.")
    assert len(chunks_v2) > 0, "V2 retrieval must return chunks."
    for c in chunks_v2:
        assert re.is_v2_chunk(c), f"V2 mode returned non-V2 chunk: {c.get('filename')} ({c.get('revision')})"
    print("V2 Strict Revision Isolation: PASS")

    # All Revisions Mode
    chunks_all = re.retrieve_relevant_chunks(query, revision_mode="all", top_k=6)
    print(f"All Revisions Retrieval: {len(chunks_all)} chunks retrieved.")
    has_v1 = any(re.is_v1_chunk(c) for c in chunks_all)
    has_v2 = any(re.is_v2_chunk(c) for c in chunks_all)
    assert has_v1 and has_v2, "All revisions mode must include both V1 and V2 chunks."
    print("All Revisions Dual-Version Inclusion: PASS")

    # 2. Cross-Document Impact Analysis
    pairs = sa.get_available_sop_pairs()
    assert len(pairs) == 5, f"Expected 5 SOP pairs, found {len(pairs)}"
    print(f"Found {len(pairs)} logical SOP pairs for revision analysis.")

    # Run structural revision diff on Turret Integration
    turret_pair = next(p for p in pairs if p["logical_sop_id"] == "HVF_SOP_2_Turret_Integration")
    print(f"Comparing revisions for {turret_pair['logical_sop_id']}...")
    diff_report = sa.compare_sop_files(turret_pair["baseline_path"], turret_pair["revised_path"])
    print(f"Diff report generated: {diff_report.get('logical_sop_id')}, total_changes={diff_report.get('total_changes')}")
    assert diff_report.get("total_changes", 0) > 0, "Revision diff must identify changes."
    assert len(diff_report.get("changes", [])) > 0, "Changes list must be populated."

    # Run Cross-Document Impact Analysis
    impacts = sa.analyze_cross_document_impacts(diff_report)
    print(f"Cross-document impacts identified: {len(impacts.get('impacts', []))}")
    for imp in impacts.get("impacts", []):
        assert imp.get("impact_class") in sa.ALL_IMPACT_CLASSES, f"Invalid impact class: {imp.get('impact_class')}"
        assert imp.get("source_passage"), "Impact must be grounded in an explicit source passage."
    print("Cross-Document Evidence-Grounded Impact Analysis: PASS")

    print("\nALL REVISION & IMPACT CHECKS PASSED (100% OK)")

if __name__ == "__main__":
    test_revision_and_impact()
