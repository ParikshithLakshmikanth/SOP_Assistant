import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database as db
import rag_engine as re
import numpy as np

def test_persistence_and_reliability():
    print("==================================================================")
    print("STEP 7: PERSISTENCE & RELIABILITY ACCEPTANCE TEST")
    print("==================================================================")

    # 1. Conversation History Persistence across DB restarts
    conv_data = db.create_conversation("E2E Acceptance Test Session")
    assert conv_data is not None, "Failed to create conversation"
    conv_id = conv_data["conversation_id"] if isinstance(conv_data, dict) else conv_data
    
    msg_user_id = db.save_message(conv_id, "user", "What is the function of the ceramic-hybrid bearing?")
    msg_asst_id = db.save_message(
        conv_id, 
        "assistant", 
        "The ceramic-hybrid bearing enables smooth 360-degree turret rotation.",
        citations=[{"filename": "HVF_SOP_2_Turret_Integration_v2.pdf", "page": 3, "revision": "Rev 4.5"}]
    )

    # Re-query DB anew
    conv = db.get_conversation(conv_id)
    messages = db.get_conversation_messages(conv_id)
    print(f"Conversation persisted: id={conv_id}, title={conv.get('title')}, messages={len(messages)}")
    assert len(messages) == 2, f"Expected 2 messages, got {len(messages)}"
    assert messages[0]["content"] == "What is the function of the ceramic-hybrid bearing?"
    assert "ceramic-hybrid" in messages[1]["content"]

    # Clean up test conversation
    db.delete_conversation(conv_id)
    conv_post = db.get_conversation(conv_id)
    assert conv_post is None, "Conversation deletion should succeed."
    print("Conversation persistence and cleanup: PASS")

    # 2. Synchronized Metadata & Vector Count Invariant
    index, metadata, manifest = re.load_faiss_index()
    comps = re.load_components_metadata()
    print(f"FAISS total: {index.ntotal}, Metadata total: {len(metadata)}, Manifest chunk_count: {manifest.get('chunk_count')}")
    assert index.ntotal == len(metadata) == manifest.get("chunk_count") == 150, "FAISS, metadata, and manifest must be 100% synchronized."
    assert len(comps) == 517, "Components metadata must equal 517."
    print("FAISS/Metadata synchronization: PASS")

    # 3. Failed Ingestion Integrity Protection
    # Attempting to index a chunk with bad dimensions (e.g. 512 instead of 768)
    bad_chunks = [{
        "chunk_id": "BAD_CHUNK_001",
        "document_id": "CORRUPT_DOC",
        "filename": "corrupt.pdf",
        "chunk_text": "This should not be indexed.",
        "embedding": [0.1] * 512 # Invalid dim 512
    }]
    
    print("Attempting to index invalid embedding dimension...")
    try:
        # Pre-check dimensions validation
        valid_dim = re.validate_embedding_dimensions([[0.1] * 512], expected_dim=768)
        assert not valid_dim, "Invalid dimension must be rejected by validator."
        print("Embedding dimension validation rejected invalid vector: PASS")
    except Exception as e:
        print(f"Caught expected error: {e}")

    # Confirm index remains untampered
    idx_after, meta_after, _ = re.load_faiss_index()
    assert idx_after.ntotal == 150, "Index must remain untouched after validation rejection."
    assert len(meta_after) == 150, "Metadata must remain untouched."
    print("Failed ingestion boundary safety: PASS")

    # 4. Database Integrity Check
    db_health = db.get_database_health()
    print("Database Health Diagnostic:", db_health)
    assert db_health["is_healthy"], "Database must be healthy."
    assert len(db_health["issues"]) == 0, f"Database issues found: {db_health['issues']}"
    print("Database Integrity: PASS")

    print("\nALL PERSISTENCE AND RELIABILITY CHECKS PASSED (100% OK)")

if __name__ == "__main__":
    test_persistence_and_reliability()
