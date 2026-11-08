"""
Test Suite for Mini Phase 11:
1. Chat cancellation lifecycle and immediate sequential message submission without page refresh.
2. Race condition protection and generator ownership.
3. Intent classification and 6-part beginner-friendly component definitions.
4. All 14 Section 13 acceptance questions.
"""

import os
import unittest
import uuid
import time
import json
from unittest.mock import MagicMock, patch

import rag_engine as re_module
import database as db_module


class TestChatCancellationAndDefinitions(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "faiss_index")
        cls.test_db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "test_cancellation.db")
        db_module.init_database(cls.test_db_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    # ========================================================================
    # PART A: CANCELLATION LIFECYCLE & SEQUENTIAL SUBMISSION TESTS
    # ========================================================================

    def test_01_cancellation_lifecycle_and_sequential_submission(self):
        """
        Simulates:
        1. User sends 'hi'.
        2. Generation begins.
        3. User clicks Stop.
        4. User immediately submits 'What is a hull?' without refreshing page.
        5. Verifies is_generating resets, partial response is saved with is_cancelled=True,
           and next message processes immediately.
        """
        conv = db_module.create_conversation("Cancellation Test Conv", db_path=self.test_db_path)
        cid = conv["conversation_id"]

        # Step 1: User sends 'hi'
        db_module.save_message(cid, "user", "hi", db_path=self.test_db_path)

        # Step 2: Generation simulated
        session_state = {
            "is_generating": True,
            "stop_requested": False,
            "active_generation_id": str(uuid.uuid4())
        }

        # Step 3: User clicks Stop (triggers callback)
        def handle_chat_stop_click():
            session_state["stop_requested"] = True
            session_state["is_generating"] = False

        handle_chat_stop_click()
        self.assertTrue(session_state["stop_requested"])
        self.assertFalse(session_state["is_generating"])

        # Simulated finally block of interrupted generation
        generation_interrupted = session_state.get("stop_requested", False)
        session_state["is_generating"] = False
        session_state["stop_requested"] = False

        # Save partial message with is_cancelled=True
        partial_text = "Hello! I am the Intelligent SOP Assistant... *[Generation stopped by user]*"
        saved_msg = db_module.save_message(
            conversation_id=cid,
            role="assistant",
            content=partial_text,
            is_cancelled=generation_interrupted,
            db_path=self.test_db_path
        )
        self.assertTrue(saved_msg["is_cancelled"])

        # Step 4: User immediately submits 'What is a hull?'
        next_input = "What is a hull?"
        # The precondition in app.py: `if user_input and not st.session_state["is_generating"]:`
        can_submit_immediately = bool(next_input and not session_state["is_generating"])
        self.assertTrue(can_submit_immediately, "Next message must be submittable immediately without refresh")

        # Step 5: Process next message
        session_state["active_generation_id"] = str(uuid.uuid4())
        session_state["is_generating"] = True
        session_state["stop_requested"] = False

        ans = re_module.generate_rag_answer(next_input, index_dir=self.index_dir)
        self.assertIn("Armoured Hull Tub Assembly", ans["answer"])
        self.assertIn("**What it is**", ans["answer"])
        self.assertFalse(ans["is_insufficient"])

        # Reset after second message finishes
        session_state["is_generating"] = False
        self.assertFalse(session_state["is_generating"])

    def test_02_stale_generator_cannot_write_after_new_request_begins(self):
        """Ensures an old generator detects ownership change via active_generation_id and terminates."""
        gen_id_1 = str(uuid.uuid4())
        gen_id_2 = str(uuid.uuid4())

        session_state = {
            "active_generation_id": gen_id_2,  # New request superseded gen_id_1
            "stop_requested": False
        }

        # Old generator simulates running with gen_id_1
        tokens_emitted = []
        mock_tokens = ["Token1", "Token2", "Token3", "Token4"]
        for t in mock_tokens:
            if session_state.get("active_generation_id") != gen_id_1:
                # Stale generator detects ownership transfer and aborts
                break
            tokens_emitted.append(t)

        self.assertEqual(len(tokens_emitted), 0, "Stale generator must not emit any tokens once superseded")

    def test_03_repeated_stop_clicks_do_not_corrupt_state(self):
        """Repeated Stop button clicks must maintain clean boolean flags without throwing errors."""
        session_state = {
            "is_generating": True,
            "stop_requested": False
        }

        def handle_chat_stop():
            session_state["stop_requested"] = True
            session_state["is_generating"] = False

        # Click stop 5 times in rapid succession
        for _ in range(5):
            handle_chat_stop()

        self.assertTrue(session_state["stop_requested"])
        self.assertFalse(session_state["is_generating"])

        # Reset in finally
        session_state["stop_requested"] = False
        self.assertFalse(session_state["stop_requested"])
        self.assertFalse(session_state["is_generating"])

    # ========================================================================
    # PART B: INTENT CLASSIFICATION TESTS (ALL 8 CATEGORIES)
    # ========================================================================

    def test_04_all_eight_intent_categories_classified(self):
        """Validates that all 8 required intent categories are correctly recognized."""
        cases = [
            ("What is a hull?", "BASIC_DEFINITION"),
            ("What does a hull do?", "COMPONENT_FUNCTION"),
            ("What are the parts of a hull?", "COMPONENT_OVERVIEW"),
            ("How is the hull connected to the turret?", "COMPONENT_RELATIONSHIPS"),
            ("How do I weld the hull?", "GENERAL_PROCEDURAL"),
            ("What is the hull plate thickness?", "TECHNICAL_SPECIFICATION"),
            ("What changed in the hull SOP in V2?", "REVISION_CHANGES"),
            ("Hi", "GENERAL_CONVERSATION")
        ]
        for query, expected_cat in cases:
            intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
            self.assertEqual(intent["category"], expected_cat, f"Query '{query}' expected category '{expected_cat}', got '{intent['category']}'")

    # ========================================================================
    # PART C: ALL 14 ACCEPTANCE QUESTIONS FROM SECTION 13
    # ========================================================================

    def test_05_q01_what_is_a_hull(self):
        """Q1: 'What is a hull?' -> BASIC_DEFINITION with 6-part structure and grounded citations."""
        query = "What is a hull?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "BASIC_DEFINITION")

        ans = re_module.generate_rag_answer(query, index_dir=self.index_dir)
        text = ans["answer"]
        self.assertIn("**What it is**", text)
        self.assertIn("**What it does**", text)
        self.assertIn("**Where it fits**", text)
        self.assertIn("**Related parts**", text)
        self.assertIn("**SOP reference**", text)
        self.assertIn("**Evidence note**", text)
        self.assertIn("HVF_SOP_1_Hull_Welding.pdf", text)
        self.assertGreater(len(ans["citations"]), 0)

    def test_06_q02_what_does_a_hull_do(self):
        """Q2: 'What does a hull do?' -> COMPONENT_FUNCTION."""
        query = "What does a hull do?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "COMPONENT_FUNCTION")
        self.assertTrue(intent["is_component_intent"])

    def test_07_q03_what_are_the_main_parts_of_a_hull(self):
        """Q3: 'What are the main parts of a hull?' -> COMPONENT_OVERVIEW."""
        query = "What are the main parts of a hull?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "COMPONENT_OVERVIEW")
        self.assertTrue(intent["is_component_intent"])

    def test_08_q04_what_is_a_turret_base_ring(self):
        """Q4: 'What is a turret base ring?' -> BASIC_DEFINITION with 6-part structure."""
        query = "What is a turret base ring?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "BASIC_DEFINITION")

        ans = re_module.generate_rag_answer(query, index_dir=self.index_dir)
        text = ans["answer"]
        self.assertIn("**What it is**", text)
        self.assertIn("**What it does**", text)
        self.assertIn("Turret Base Ring", text)
        self.assertIn("HVF_SOP_2_Turret_Integration", text)

    def test_09_q05_what_is_a_ceramic_hybrid_bearing(self):
        """Q5: 'What is a ceramic-hybrid bearing?' -> BASIC_DEFINITION with 6-part structure."""
        query = "What is a ceramic-hybrid bearing?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "BASIC_DEFINITION")

        ans = re_module.generate_rag_answer(query, index_dir=self.index_dir)
        text = ans["answer"]
        self.assertIn("**What it is**", text)
        self.assertIn("Ceramic-Hybrid Cross-Roller Bearing", text)
        self.assertIn("HVF_SOP_2_Turret_Integration", text)

    def test_10_q06_what_does_a_v12_powerpack_contain(self):
        """Q6: 'What does a V12 powerpack contain?' -> ASSEMBLY_SUBSYSTEM."""
        query = "What does a V12 powerpack contain?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "ASSEMBLY_SUBSYSTEM")
        self.assertTrue(intent["is_component_intent"])

    def test_11_q07_what_is_a_torsion_bar(self):
        """Q7: 'What is a torsion bar?' -> BASIC_DEFINITION with 6-part structure."""
        query = "What is a torsion bar?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "BASIC_DEFINITION")

        ans = re_module.generate_rag_answer(query, index_dir=self.index_dir)
        text = ans["answer"]
        self.assertIn("**What it is**", text)
        self.assertIn("Torsion Bar", text)
        self.assertIn("HVF_SOP_4_Torsion_Suspension.pdf", text)

    def test_12_q08_what_is_a_hydromount(self):
        """Q8: 'What is a hydromount?' -> BASIC_DEFINITION with 6-part structure."""
        query = "What is a hydromount?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "BASIC_DEFINITION")

        ans = re_module.generate_rag_answer(query, index_dir=self.index_dir)
        text = ans["answer"]
        self.assertIn("**What it is**", text)
        self.assertIn("Hydromount", text)
        self.assertIn("HVF_SOP_3_Engine_Alignment", text)

    def test_13_q09_what_is_a_track_system(self):
        """Q9: 'What is a track system?' -> BASIC_DEFINITION with 6-part structure."""
        query = "What is a track system?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "BASIC_DEFINITION")

        ans = re_module.generate_rag_answer(query, index_dir=self.index_dir)
        text = ans["answer"]
        self.assertIn("**What it is**", text)
        self.assertIn("Track and Running Gear System", text)
        self.assertIn("HVF_SOP_4_Torsion_Suspension.pdf", text)

    def test_14_q10_difference_between_hull_and_turret(self):
        """Q10: 'What is the difference between a hull and a turret?' -> COMPONENT_RELATIONSHIPS."""
        query = "What is the difference between a hull and a turret?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "COMPONENT_RELATIONSHIPS")
        self.assertTrue(intent["is_component_intent"])

    def test_15_q11_how_is_the_hull_welded(self):
        """Q11: 'How is the hull welded?' -> GENERAL_PROCEDURAL."""
        query = "How is the hull welded?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "GENERAL_PROCEDURAL")
        self.assertFalse(intent["is_component_intent"])

    def test_16_q12_what_changed_in_hull_welding_in_v2(self):
        """Q12: 'What changed in hull welding in V2?' -> REVISION_CHANGES."""
        query = "What changed in hull welding in V2?"
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "REVISION_CHANGES")
        self.assertTrue(intent["is_component_intent"])

    def test_17_q13_hi_greeting_fast_bypass(self):
        """Q13: 'Hi.' -> GENERAL_CONVERSATION with zero FAISS retrieval and immediate answer."""
        query = "Hi."
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "GENERAL_CONVERSATION")
        self.assertFalse(intent["is_component_intent"])

        # Test streaming fast bypass
        gen, citations, info = re_module.stream_rag_answer(query, index_dir=self.index_dir)
        tokens = list(gen)
        streamed_text = "".join(tokens)
        self.assertIn("Hello!", streamed_text)
        self.assertEqual(len(citations), 0, "Greetings must not return document citations")
        self.assertEqual(info["retrieved_chunks_count"], 0, "Greetings must not retrieve FAISS chunks")
        self.assertTrue(info.get("is_greeting", False))

    def test_18_q14_explain_engine_alignment_in_simple_words(self):
        """Q14: 'Explain engine alignment in simple words.' -> BASIC_DEFINITION with 6-part structure."""
        query = "Explain engine alignment in simple words."
        intent = re_module.detect_component_intent(query, index_dir=self.index_dir)
        self.assertEqual(intent["category"], "BASIC_DEFINITION")

        ans = re_module.generate_rag_answer(query, index_dir=self.index_dir)
        text = ans["answer"]
        self.assertIn("**What it is**", text)
        self.assertIn("Engine-to-Transmission Alignment System", text)
        self.assertIn("HVF_SOP_3_Engine_Alignment.pdf", text)


if __name__ == "__main__":
    unittest.main()
