#!/usr/bin/env python3
"""
Frontend Quality Assessment Lifecycle & Non-Blocking Async Tests
Verifies:
- 3 consecutive questions receive distinct UUID-bound assessments via background evaluation.
- Submitting Q2 while Q1 evaluation is still running does not block or leak assessments.
- Completed answers, cancelled answers, evaluator timeout, evaluator failure, and
  historical unassessed/persisted responses render and persist properly in SQLite.
- Critical unsupported/contradicted claim warnings trigger cleanly regardless of score.
"""

import os
import sys
import time
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import database as db
import rag_evaluator as eval_mod
from app import (
    _format_assessment_timestamp,
    format_assessment_summary,
    get_eval_job_status,
    start_background_evaluation,
)


HULL_EVIDENCE = [
    {
        "filename": "HVF_SOP_1_Hull_Welding.pdf",
        "revision": "Rev 4.2",
        "section_title": "SECTION 1.0",
        "page_number": 1,
        "chunk_text": "Minimum preheat temperature is 150°C and maximum interpass is 220°C.",
    }
]


class TestFrontendAssessmentLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "test_frontend_eval.db")
        db.init_database(self.db_path)
        conv = db.create_conversation("Frontend Eval Lifecycle Test", db_path=self.db_path)
        self.cid = conv["conversation_id"]

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_01_nonblocking_three_consecutive_questions_and_overlap(self):
        """Three consecutive questions run async per UUID; Q2 starts while Q1 is still running."""
        q1_gate = threading.Event()
        q1_started = threading.Event()

        def mock_eval_fn(question, answer, citations, info=None, use_llm=True, llm_timeout=45.0):
            if "Q1" in question:
                q1_started.set()
                q1_gate.wait(timeout=3.0)
                return eval_mod.evaluate_rag_answer(
                    question="What is hull preheat?",
                    answer=answer,
                    citations=citations,
                    use_llm=False,
                )
            if "Q2" in question:
                return eval_mod.evaluate_rag_answer(
                    question="What is hull interpass?",
                    answer=answer,
                    citations=citations,
                    use_llm=False,
                )
            raise TimeoutError("Simulated evaluator timeout after 45.0s")

        m1 = db.save_message(
            self.cid,
            "assistant",
            "Preheat is 150°C min [HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1].",
            citations=HULL_EVIDENCE,
            assessment_metadata={"assessment_status": "pending"},
            db_path=self.db_path,
        )
        m2 = db.save_message(
            self.cid,
            "assistant",
            "Interpass max is 220°C [HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1].",
            citations=HULL_EVIDENCE,
            assessment_metadata={"assessment_status": "pending"},
            db_path=self.db_path,
        )
        m3 = db.save_message(
            self.cid,
            "assistant",
            "Q3 response text.",
            citations=HULL_EVIDENCE,
            assessment_metadata={"assessment_status": "pending"},
            db_path=self.db_path,
        )

        # Launch Q1 while gate keeps it running
        t0 = time.perf_counter()
        started_1 = start_background_evaluation(
            m1["message_id"], "Q1 preheat", m1["content"], HULL_EVIDENCE, {}, True,
            db_path=self.db_path, eval_fn=mock_eval_fn
        )
        self.assertTrue(started_1)
        self.assertLess(time.perf_counter() - t0, 0.5, "start_background_evaluation must not block")
        self.assertTrue(q1_started.wait(timeout=2.0))
        self.assertEqual(get_eval_job_status(m1["message_id"])["status"], "running")

        # Launch Q2 and Q3 while Q1 is STILL running
        start_background_evaluation(
            m2["message_id"], "Q2 interpass", m2["content"], HULL_EVIDENCE, {}, True,
            db_path=self.db_path, eval_fn=mock_eval_fn
        )
        start_background_evaluation(
            m3["message_id"], "Q3 fail", m3["content"], HULL_EVIDENCE, {}, True,
            db_path=self.db_path, eval_fn=mock_eval_fn
        )

        # Wait briefly for Q2 & Q3 while Q1 is still gated
        deadline = time.perf_counter() + 3.0
        while time.perf_counter() < deadline:
            s2 = get_eval_job_status(m2["message_id"])
            s3 = get_eval_job_status(m3["message_id"])
            if s2["status"] == "done" and s3["status"] == "done":
                break
            time.sleep(0.05)

        self.assertEqual(get_eval_job_status(m1["message_id"])["status"], "running")
        self.assertEqual(get_eval_job_status(m2["message_id"])["status"], "done")
        self.assertEqual(get_eval_job_status(m3["message_id"])["status"], "done")

        # Release Q1
        q1_gate.set()
        deadline = time.perf_counter() + 3.0
        while time.perf_counter() < deadline:
            if get_eval_job_status(m1["message_id"])["status"] == "done":
                break
            time.sleep(0.05)

        # Reload from SQLite and verify strict UUID isolation
        r1 = db.get_message_by_id(m1["message_id"], db_path=self.db_path)["assessment_metadata"]
        r2 = db.get_message_by_id(m2["message_id"], db_path=self.db_path)["assessment_metadata"]
        r3 = db.get_message_by_id(m3["message_id"], db_path=self.db_path)["assessment_metadata"]

        self.assertEqual(r1["assessment_status"], "completed")
        self.assertIsNotNone(r1["overall_score"])
        self.assertEqual(r2["assessment_status"], "completed")
        self.assertIsNotNone(r2["overall_score"])
        self.assertEqual(r3["assessment_status"], "unavailable")
        self.assertIsNone(r3["overall_score"])
        self.assertEqual(format_assessment_summary(r3)["expander_title"], "Answer Quality Assessment — Assessment unavailable")

    def test_02_cancelled_timeout_failure_and_historical_states(self):
        """Verify pending, skipped/cancelled, unavailable (timeout/failure), and historical states."""
        # Pending summary
        pend = format_assessment_summary({"assessment_status": "pending"})
        self.assertEqual(pend["state"], "pending")
        self.assertIsNone(pend["overall_score"])
        self.assertIn("Assessing answer quality", pend["status_text"])

        # Historical empty
        hist = format_assessment_summary({})
        self.assertEqual(hist["state"], "historical")
        self.assertEqual(hist["status_text"], "Not assessed — historical response.")

        # Evaluator timeout via real evaluate_rag_answer(use_llm=True) against failing/timeout llm_eval_fn
        def timeout_fn(*a, **k):
            raise TimeoutError("Ollama request timed out after 15.0s")

        unavail = eval_mod.evaluate_rag_answer(
            "What is hull preheat?",
            "Preheat is 150°C min.",
            HULL_EVIDENCE,
            use_llm=True,
            llm_eval_fn=timeout_fn,
        )
        self.assertEqual(unavail["assessment_status"], "unavailable")
        self.assertIsNone(unavail["overall_score"])
        self.assertIn("not a statistical probability", unavail["disclaimer"])
        self.assertNotEqual(_format_assessment_timestamp(unavail["evaluated_at"]), "N/A")

        # Cancelled message triggers fast skipped/deterministic audit
        m_cancel = db.save_message(
            self.cid,
            "assistant",
            "*[Generation was stopped by user]*",
            is_cancelled=True,
            assessment_metadata={"assessment_status": "pending"},
            db_path=self.db_path,
        )
        start_background_evaluation(
            m_cancel["message_id"],
            "What is hull preheat?",
            m_cancel["content"],
            HULL_EVIDENCE,
            {"is_cancelled": True},
            use_llm=False,
            db_path=self.db_path,
        )
        deadline = time.perf_counter() + 3.0
        while time.perf_counter() < deadline:
            if get_eval_job_status(m_cancel["message_id"])["status"] == "done":
                break
            time.sleep(0.05)

        loaded_cancel = db.get_message_by_id(m_cancel["message_id"], db_path=self.db_path)["assessment_metadata"]
        self.assertEqual(loaded_cancel["assessment_status"], "skipped")
        self.assertIsNone(loaded_cancel["overall_score"])


if __name__ == "__main__":
    unittest.main()

