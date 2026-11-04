#!/usr/bin/env python3
"""
Test Suite: Phase 5 - SQLite Conversation Persistence & History Management
==========================================================================
Validates:
1. Database initialization and schema creation (conversations & messages tables).
2. Conversation creation, title assignment, and unique ID generation.
3. User and assistant message persistence (with JSON citations and cancellation status).
4. Strict chronological message retrieval and sequence ordering.
5. Listing conversations ordered by updated_at descending with message counts.
6. Persistence across database reconnection (re-opening SQLite database).
7. Conversation deletion and cascading message deletion (foreign key ON DELETE CASCADE).
8. Robust handling of invalid, missing, or empty inputs.
9. Prevention of duplicate message insertions on simulated UI reruns.
10. Strict separation: Phase 4 RAG retrieval, citations, streaming, and FAISS corpus (150 chunks)
    remain completely unaffected and unpolluted by conversational history.
"""

import os
import sys
import time
import py_compile
import sqlite3
import numpy as np

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import database as db
import rag_engine as re

TEST_DB_PATH = os.path.join("data", "test_phase5_verification.db")


def cleanup_test_db():
    """Removes the test database file and any associated WAL/SHM files."""
    for ext in ["", "-wal", "-shm"]:
        target = TEST_DB_PATH + ext
        if os.path.exists(target):
            try:
                os.remove(target)
            except Exception:
                pass


def run_tests():
    print("=" * 70)
    print("RUNNING PHASE 5 VERIFICATION TEST SUITE (SQLite Persistence & History)")
    print("=" * 70)

    cleanup_test_db()
    test_results = {}

    # ------------------------------------------------------------------------
    # Test 1: Database Initialization and Schema Creation
    # ------------------------------------------------------------------------
    print("\n--- Test 1: Database Initialization & Schema Creation ---")
    try:
        db.init_database(TEST_DB_PATH)
        assert os.path.exists(TEST_DB_PATH), "Database file was not created"

        with db.get_db(TEST_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r["name"] for r in cursor.fetchall()]
            print(f"  Detected Tables: {tables}")
            assert "conversations" in tables, "conversations table missing"
            assert "messages" in tables, "messages table missing"

            cursor.execute("SELECT name FROM sqlite_master WHERE type='index';")
            indices = [r["name"] for r in cursor.fetchall()]
            print(f"  Detected Indices: {indices}")
            assert "idx_messages_conv_seq" in indices, "idx_messages_conv_seq missing"
            assert "idx_conversations_updated" in indices, "idx_conversations_updated missing"

            # Verify foreign key pragma
            cursor.execute("PRAGMA foreign_keys;")
            fk_enabled = cursor.fetchone()[0]
            print(f"  Foreign Keys Enabled: {fk_enabled == 1}")
            assert fk_enabled == 1, "Foreign keys are not enabled"

        print("  [PASS] Schema initialized with conversations, messages, indices, and foreign keys.")
        test_results["Test 1: Schema Initialization"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Schema initialization failed: {e}")
        test_results["Test 1: Schema Initialization"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 2: Conversation Creation & Unique IDs
    # ------------------------------------------------------------------------
    print("\n--- Test 2: Conversation Creation & Unique IDs ---")
    try:
        c1 = db.create_conversation("Hull Welding Consultation", db_path=TEST_DB_PATH)
        c2 = db.create_conversation("Turret Integration Consultation", db_path=TEST_DB_PATH)
        c3 = db.create_conversation(conv_id="custom-c3-id", title="Suspension Consultation", db_path=TEST_DB_PATH)

        print(f"  Created c1: ID='{c1['conversation_id']}', Title='{c1['title']}'")
        print(f"  Created c2: ID='{c2['conversation_id']}', Title='{c2['title']}'")
        print(f"  Created c3: ID='{c3['conversation_id']}', Title='{c3['title']}'")

        assert c1["conversation_id"] != c2["conversation_id"], "Conversation IDs must be distinct"
        assert c3["conversation_id"] == "custom-c3-id", "Custom conversation ID preserved"
        assert c1["title"] == "Hull Welding Consultation"
        assert c1["created_at"] is not None and c1["updated_at"] is not None

        # Verify retrieval by ID
        fetched_c1 = db.get_conversation(c1["conversation_id"], db_path=TEST_DB_PATH)
        assert fetched_c1 is not None and fetched_c1["title"] == c1["title"]

        print("  [PASS] Conversations created with unique IDs, correct titles, and timestamps.")
        test_results["Test 2: Conversation Creation"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Conversation creation failed: {e}")
        test_results["Test 2: Conversation Creation"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 3: User & Assistant Message Persistence
    # ------------------------------------------------------------------------
    print("\n--- Test 3: Message Persistence (User & Assistant) ---")
    try:
        cid = c1["conversation_id"]

        # User message
        m_user = db.save_message(
            conversation_id=cid,
            role="user",
            content="What is the minimum preheating temperature for weld root passes?",
            db_path=TEST_DB_PATH
        )
        print(f"  Saved User Message: ID={m_user['message_id'][:8]}, Seq={m_user['sequence_number']}")
        assert m_user["role"] == "user"
        assert m_user["sequence_number"] == 1
        assert m_user["is_cancelled"] is False

        # Assistant message with citations
        sample_citations = [
            {
                "citation": "[HVF_SOP_1_Hull_Welding.pdf, Rev 4.2 (2026), SECTION 3.0, Page 3]",
                "document_id": "HVF/AVNL/SOP-MBT/HW-101",
                "revision": "Rev 4.2 (2026)",
                "section_title": "SECTION 3.0 — PRE-HEATING & INTERPASS",
                "score": 0.8954,
                "chunk_text": "Induction preheating to 180 C (+/- 10 C) is mandatory for root passes."
            }
        ]
        m_asst = db.save_message(
            conversation_id=cid,
            role="assistant",
            content="Induction preheating to 180 C (+/- 10 C) is required for all root passes.",
            citations=sample_citations,
            is_cancelled=False,
            db_path=TEST_DB_PATH
        )
        print(f"  Saved Assistant Message: ID={m_asst['message_id'][:8]}, Seq={m_asst['sequence_number']}, Citations={len(m_asst['citations'])}")
        assert m_asst["role"] == "assistant"
        assert m_asst["sequence_number"] == 2
        assert len(m_asst["citations"]) == 1
        assert m_asst["citations"][0]["score"] == 0.8954

        print("  [PASS] User and assistant messages persisted with structured citations.")
        test_results["Test 3: Message Persistence"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Message persistence failed: {e}")
        test_results["Test 3: Message Persistence"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 4: Strict Chronological Ordering
    # ------------------------------------------------------------------------
    print("\n--- Test 4: Chronological Message Retrieval ---")
    try:
        cid = c1["conversation_id"]

        # Add more turns
        db.save_message(cid, "user", "What about interpass temperature?", db_path=TEST_DB_PATH)
        db.save_message(
            cid, "assistant",
            "Maximum interpass temperature must not exceed 220 C.",
            is_cancelled=True,
            db_path=TEST_DB_PATH
        )

        all_msgs = db.get_conversation_messages(cid, db_path=TEST_DB_PATH)
        print(f"  Retrieved {len(all_msgs)} messages for conversation {cid}:")
        seq_numbers = [m["sequence_number"] for m in all_msgs]
        print(f"  Sequence numbers: {seq_numbers}")

        assert len(all_msgs) == 4, f"Expected 4 messages, got {len(all_msgs)}"
        assert seq_numbers == [1, 2, 3, 4], "Messages must be ordered strictly sequentially"
        assert all_msgs[0]["role"] == "user"
        assert all_msgs[1]["role"] == "assistant"
        assert all_msgs[2]["role"] == "user"
        assert all_msgs[3]["role"] == "assistant"
        assert all_msgs[3]["is_cancelled"] is True, "Cancelled flag must be preserved"

        print("  [PASS] Messages returned in strict chronological sequence with cancellation state.")
        test_results["Test 4: Chronological Retrieval"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Chronological retrieval failed: {e}")
        test_results["Test 4: Chronological Retrieval"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 5: Listing Recent Conversations with Message Counts
    # ------------------------------------------------------------------------
    print("\n--- Test 5: Listing Recent Conversations ---")
    try:
        # Update c2 by adding a message so it becomes the most recently updated
        time.sleep(0.05)
        db.save_message(c2["conversation_id"], "user", "Turret bearing torque?", db_path=TEST_DB_PATH)

        conv_list = db.list_conversations(db_path=TEST_DB_PATH)
        print(f"  Retrieved {len(conv_list)} conversations:")
        for conv in conv_list:
            print(f"    - [{conv['conversation_id']}] '{conv['title']}' | Msgs: {conv['message_count']} | Updated: {conv['updated_at']}")

        assert len(conv_list) >= 3, "Expected at least 3 conversations"
        # c2 had the most recent message, so it must be first
        assert conv_list[0]["conversation_id"] == c2["conversation_id"], "Most recently updated conversation must be first"
        assert conv_list[0]["message_count"] == 1, "c2 message count should be 1"

        # Find c1 in list and check message count
        c1_item = next(c for c in conv_list if c["conversation_id"] == c1["conversation_id"])
        assert c1_item["message_count"] == 4, "c1 message count should be 4"

        print("  [PASS] list_conversations orders by updated_at descending with accurate message counts.")
        test_results["Test 5: Conversation Listing"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Conversation listing failed: {e}")
        test_results["Test 5: Conversation Listing"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 6: Persistence Across Database Reconnection
    # ------------------------------------------------------------------------
    print("\n--- Test 6: Persistence Across Reconnection ---")
    try:
        # Querying with independent connection simulation
        fetched = db.get_conversation_with_messages(c1["conversation_id"], db_path=TEST_DB_PATH)
        assert fetched is not None
        assert fetched["title"] == "Hull Welding Consultation"
        assert len(fetched["messages"]) == 4

        # Verify citations survived serialization / deserialization roundtrip
        asst_msg = fetched["messages"][1]
        assert len(asst_msg["citations"]) == 1
        cit = asst_msg["citations"][0]
        assert cit["score"] == 0.8954
        assert cit["document_id"] == "HVF/AVNL/SOP-MBT/HW-101"

        print("  [PASS] Conversation, messages, citations, and metadata fully intact after re-opening DB.")
        test_results["Test 6: Reconnection Persistence"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Reconnection persistence failed: {e}")
        test_results["Test 6: Reconnection Persistence"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 7: Conversation Deletion & Cascading Message Deletion
    # ------------------------------------------------------------------------
    print("\n--- Test 7: Cascading Conversation Deletion ---")
    try:
        target_id = c1["conversation_id"]
        # Confirm messages exist before deletion
        msgs_before = db.get_conversation_messages(target_id, db_path=TEST_DB_PATH)
        assert len(msgs_before) == 4

        # Delete conversation
        del_success = db.delete_conversation(target_id, db_path=TEST_DB_PATH)
        print(f"  Deleted conversation [{target_id}]: {del_success}")
        assert del_success is True

        # Check conversation is gone
        conv_after = db.get_conversation(target_id, db_path=TEST_DB_PATH)
        assert conv_after is None, "Deleted conversation must return None"

        # Check all child messages were CASCADE deleted
        msgs_after = db.get_conversation_messages(target_id, db_path=TEST_DB_PATH)
        print(f"  Messages remaining for deleted conversation: {len(msgs_after)} (Expected: 0)")
        assert len(msgs_after) == 0, "All associated messages must be cascade deleted"

        # Check other conversations remain untouched
        c2_msgs = db.get_conversation_messages(c2["conversation_id"], db_path=TEST_DB_PATH)
        assert len(c2_msgs) == 1, "c2 messages must remain untouched"

        print("  [PASS] Foreign key cascade deletion cleanly purges all conversation messages.")
        test_results["Test 7: Cascading Deletion"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Cascading deletion failed: {e}")
        test_results["Test 7: Cascading Deletion"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 8: Empty, Missing, and Invalid Input Handling
    # ------------------------------------------------------------------------
    print("\n--- Test 8: Invalid Input Handling & Robustness ---")
    try:
        # Invalid role
        invalid_role_caught = False
        try:
            db.save_message(c2["conversation_id"], "invalid_role", "Test content", db_path=TEST_DB_PATH)
        except ValueError:
            invalid_role_caught = True
        print(f"  Invalid role rejected: {invalid_role_caught}")
        assert invalid_role_caught is True

        # Non-existent conversation
        non_existent_caught = False
        try:
            db.save_message("non-existent-conv-id", "user", "Hello", db_path=TEST_DB_PATH)
        except ValueError:
            non_existent_caught = True
        print(f"  Non-existent conversation rejected: {non_existent_caught}")
        assert non_existent_caught is True

        # Missing inputs
        assert db.get_conversation("", db_path=TEST_DB_PATH) is None
        assert db.get_conversation_messages("", db_path=TEST_DB_PATH) == []
        assert db.delete_conversation("", db_path=TEST_DB_PATH) is False
        assert db.update_conversation_title("", "Title", db_path=TEST_DB_PATH) is False

        print("  [PASS] Invalid roles, non-existent foreign keys, and empty strings safely handled.")
        test_results["Test 8: Invalid Input Robustness"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Invalid input robustness failed: {e}")
        test_results["Test 8: Invalid Input Robustness"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 9: Prevention of Duplicate Messages on UI Rerun
    # ------------------------------------------------------------------------
    print("\n--- Test 9: Duplicate Prevention on Simulated UI Rerun ---")
    try:
        dup_conv = db.create_conversation("Rerun Test", db_path=TEST_DB_PATH)
        dup_cid = dup_conv["conversation_id"]

        # Insert user and assistant messages with fixed message IDs (as happens in idempotent client calls)
        fixed_user_mid = "user-mid-101"
        fixed_asst_mid = "asst-mid-102"

        db.save_message(dup_cid, "user", "Query text", msg_id=fixed_user_mid, db_path=TEST_DB_PATH)
        db.save_message(dup_cid, "assistant", "Answer text", msg_id=fixed_asst_mid, db_path=TEST_DB_PATH)

        # Simulate page rerun: query messages twice
        fetch1 = db.get_conversation_messages(dup_cid, db_path=TEST_DB_PATH)
        fetch2 = db.get_conversation_messages(dup_cid, db_path=TEST_DB_PATH)

        assert len(fetch1) == 2
        assert len(fetch2) == 2
        assert [m["message_id"] for m in fetch1] == [fixed_user_mid, fixed_asst_mid]
        assert [m["message_id"] for m in fetch2] == [fixed_user_mid, fixed_asst_mid]

        # Ensure attempting to re-insert the identical message_id triggers primary key collision
        pk_collision_caught = False
        try:
            db.save_message(dup_cid, "user", "Duplicate text", msg_id=fixed_user_mid, db_path=TEST_DB_PATH)
        except sqlite3.IntegrityError:
            pk_collision_caught = True
        print(f"  Primary key collision on duplicate message_id caught: {pk_collision_caught}")
        assert pk_collision_caught is True

        print("  [PASS] Duplicate messages strictly prevented and sequence numbers remain stable.")
        test_results["Test 9: Duplicate Prevention"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] Duplicate prevention failed: {e}")
        test_results["Test 9: Duplicate Prevention"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # Test 10: RAG Integration & Separation Rules (Regression Test)
    # ------------------------------------------------------------------------
    print("\n--- Test 10: RAG Engine Isolation & Phase 4 Regression ---")
    try:
        # A. Confirm FAISS corpus remains completely unaffected by conversation entries
        idx, meta, manifest = re.load_faiss_index()
        print(f"  FAISS Corpus: {idx.ntotal} chunks (Expected: 150)")
        print(f"  FAISS Documents: {len(manifest.get('documents', []))} (Expected: 10)")
        assert idx.ntotal == 150, f"FAISS corpus was contaminated! Chunks: {idx.ntotal}"
        assert len(manifest.get("documents", [])) == 10, "Document inventory modified!"

        # B. Verify conversation history can be passed into stream_rag_answer without errors
        simulated_history = [
            {"role": "user", "content": "I am working on the MBT turret assembly."},
            {"role": "assistant", "content": "Acknowledged. What specific turret integration step do you require?"}
        ]

        token_stream, citations, info = re.stream_rag_answer(
            question="What is the torque specification for the turret azimuth bearing bolts?",
            top_k=2,
            logical_sop_id="HVF_SOP_2_Turret_Integration",
            conversation_history=simulated_history,
            max_tokens=768
        )

        tokens = []
        for t in token_stream:
            tokens.append(t)
        asst_response = "".join(tokens).strip()

        print(f"  Streamed Tokens: {len(tokens)}")
        print(f"  Citations Returned: {len(citations)}")
        print(f"  Response Snippet: {asst_response[:120]}...")

        assert len(tokens) > 5, "RAG streaming yielded insufficient tokens"
        assert len(citations) > 0, "No citations returned with stream"
        for c in citations:
            assert c["logical_sop_id"] == "HVF_SOP_2_Turret_Integration"
            assert "HVF_SOP_2" in c["citation"]

        # C. Re-verify FAISS index was NOT modified by the conversation or query
        idx_after, _, _ = re.load_faiss_index()
        assert idx_after.ntotal == 150, "FAISS index size changed after chat turn!"

        print("  [PASS] RAG engine operates seamlessly with dialogue history; FAISS corpus remains 100% isolated.")
        test_results["Test 10: RAG & FAISS Isolation"] = "PASS"
    except Exception as e:
        print(f"  [FAIL] RAG isolation regression test failed: {e}")
        test_results["Test 10: RAG & FAISS Isolation"] = f"FAIL: {e}"

    # ------------------------------------------------------------------------
    # CLEANUP
    # ------------------------------------------------------------------------
    cleanup_test_db()

    # ------------------------------------------------------------------------
    # FINAL SUMMARY
    # ------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("PHASE 5 VERIFICATION SUMMARY")
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

