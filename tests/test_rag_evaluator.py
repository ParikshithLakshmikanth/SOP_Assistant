"""
Test Suite for Mini Phase 13: RAG Answer Accuracy, Evidence Validation & Quality Scoring
======================================================================================
Validates all 20 required unit and integration scenarios:
1. Fully supported answer
2. Partially supported answer
3. Unsupported factual claim
4. Contradictory claim
5. Incorrect citation
6. Missing citation
7. Correct basic definition
8. Irrelevant SOP summary
9. Incomplete answer
10. Unsupported tolerance
11. Unsupported material specification
12. Insufficient evidence and abstention
13. General engineering context correctly labeled
14. Evaluator malformed JSON
15. Evaluator timeout
16. Evaluator unavailable
17. Historical message without assessment
18. Assessment persistence after restart
19. Sequential questions with separate assessments
20. Cancellation during answer generation (and non-destruction guarantee)
"""

import os
import json
import time
import unittest

import database as db
import rag_engine as re_engine
import rag_evaluator as eval_mod
from app import format_assessment_summary


# Sample grounded SOP evidence fixtures matching real HVF corpus facts
HULL_EVIDENCE = [
    {
        "passage_number": 1,
        "chunk_id": "HVF_AVNL_SOP_MBT_HW_101_C0001",
        "filename": "HVF_SOP_1_Hull_Welding.pdf",
        "revision": "Rev 4.2 (2026) | 30-Oct-2026",
        "section_title": "SECTION 1.0 — RHA PLATE RECEIVING",
        "page_number": "1-2",
        "score": 0.88,
        "evidence_status": "DIRECTLY_STATED",
        "chunk_text": (
            "Base Material Spec: MIL-DTL-12560 / DMR-1700 Ultra-High-Strength RHA (380-440 BHN). "
            "Preheat & Interpass: 150°C min preheat; 220°C max interpass (IR pyrometer verified). "
            "Laser Tracker Hull Envelope Tolerance ≤ ±0.80 mm across 6.8 m length."
        ),
    }
]

TURRET_V2_EVIDENCE = [
    {
        "passage_number": 1,
        "chunk_id": "HVF_AVNL_SOP_MBT_TI_204_V2_C0001",
        "filename": "HVF_SOP_2_Turret_Integration_v2.pdf",
        "revision": "Rev 4.5 [Version 2.0] | 30-Oct-2026",
        "section_title": "SECTION 1.0 — SUB-MICRON LASER TRACKER PLINTH MAPPING",
        "page_number": "1-2",
        "score": 0.91,
        "evidence_status": "DIRECTLY_STATED",
        "chunk_text": (
            "Plinth Flatness Matrix: ≤ 0.035 mm total indicator reading (TIR) across 2,240 mm pitch diameter. "
            "Dual-Pinion Backlash: 0.14 mm – 0.20 mm electronically pre-loaded dual pinion drives. "
            "Static Breakaway Torque: ≤ 380 Nm smooth breakaway across continuous 360° rotation."
        ),
    }
]


def _mock_good_llm_fn(question, answer, claims, records):
    return json.dumps({
        "evidence_support": 92,
        "answer_relevance": 94,
        "completeness": 90,
        "unsupported_claims": [],
        "contradicted_claims": [],
        "missing_evidence": [],
        "evidence_reason": "All claims match retrieved passages.",
        "relevance_reason": "Directly answers the question.",
        "completeness_reason": "Covers requested tolerances completely."
    })


def _mock_optimistic_llm_fn(question, answer, claims, records):
    """Simulates an overly optimistic small LLM that misses a critical technical error."""
    return json.dumps({
        "evidence_support": 98,
        "answer_relevance": 95,
        "completeness": 95,
        "unsupported_claims": [],
        "contradicted_claims": [],
        "missing_evidence": [],
        "evidence_reason": "Sounds plausible.",
        "relevance_reason": "Relevant.",
        "completeness_reason": "Complete."
    })


class TestRAGEvaluator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "test_rag_evaluator.db"
        )
        if os.path.exists(cls.test_db_path):
            os.remove(cls.test_db_path)
        db.init_database(cls.test_db_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    def setUp(self):
        conv = db.create_conversation("Eval Test Conv", db_path=self.test_db_path)
        self.cid = conv["conversation_id"]

    # 1. Fully supported answer
    def test_01_fully_supported_answer(self):
        q = "What is the base material and preheat requirement in Hull Welding V1?"
        a = (
            "The base material specification is MIL-DTL-12560 / DMR-1700 Ultra-High-Strength RHA (380-440 BHN) "
            "[HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1].\n"
            "The mandatory preheat is 150°C minimum with a 220°C maximum interpass temperature "
            "[HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 2]."
        )
        res = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=True, llm_eval_fn=_mock_good_llm_fn)
        self.assertTrue(res["evaluation_succeeded"])
        self.assertEqual(res["assessment_status"], "completed")
        self.assertGreaterEqual(res["overall_score"], 85.0)
        self.assertEqual(res["warning_label"], "HIGH EVIDENCE SUPPORT")
        self.assertEqual(res["unsupported_claims_count"], 0)
        self.assertEqual(res["contradicted_claims_count"], 0)
        self.assertEqual(res["claims"][0]["support_status"], "SUPPORTED")

    # 2. Partially supported answer
    def test_02_partially_supported_answer(self):
        q = "What is the hull envelope tolerance and paint thickness in V1?"
        a = (
            "The Laser Tracker Hull Envelope Tolerance is ≤ ±0.80 mm across 6.8 m length "
            "[HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1].\n"
            "Additionally, standard primer coat conditioning prepares welded hull plates prior to inspection."
        )
        res = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=False)
        self.assertTrue(res["evaluation_succeeded"])
        self.assertNotEqual(res["warning_label"], "HIGH EVIDENCE SUPPORT")
        self.assertTrue(any(c["support_status"] in {"PARTIALLY_SUPPORTED", "UNSUPPORTED"} for c in res["claims"]))

    # 3. Unsupported factual claim
    def test_03_unsupported_factual_claim(self):
        q = "What is the base material spec for Hull Welding?"
        a = (
            "The hull requires ultrasonic degassing under cryogenic vacuum chambers for 12 hours prior to fitup "
            "[HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1]."
        )
        res = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=True, llm_eval_fn=_mock_optimistic_llm_fn)
        self.assertGreater(res["unsupported_claims_count"], 0)
        self.assertNotEqual(res["warning_label"], "HIGH EVIDENCE SUPPORT")
        self.assertEqual(res["warning_label"], "UNSUPPORTED CLAIMS DETECTED")
        self.assertLess(res["overall_score"], 75.0)

    # 4. Contradictory claim
    def test_04_contradictory_claim(self):
        q = "What is the turret plinth flatness tolerance in V2?"
        a = (
            "In Version 2 (Rev 4.5), the Plinth Flatness Matrix tolerance is ≤ 0.25 mm total indicator reading (TIR) across 2,240 mm pitch diameter "
            "[HVF_SOP_2_Turret_Integration_v2.pdf, Rev 4.5, SECTION 1.0, Page 1]."
        )
        res = eval_mod.evaluate_rag_answer(q, a, TURRET_V2_EVIDENCE, use_llm=True, llm_eval_fn=_mock_optimistic_llm_fn)
        self.assertGreater(res["contradicted_claims_count"], 0)
        self.assertEqual(res["warning_label"], "CONTRADICTORY EVIDENCE")
        self.assertLessEqual(res["overall_score"], 49.0)
        self.assertNotEqual(res["warning_label"], "HIGH EVIDENCE SUPPORT")

    # 5. Incorrect citation
    def test_05_incorrect_citation(self):
        q = "What is the base material in Hull Welding?"
        a = (
            "The base material specification is MIL-DTL-12560 Ultra-High-Strength RHA "
            "[HVF_SOP_5_Gun_Calibration.pdf, Rev 9.9, SECTION 1.0, Page 99]."
        )
        res = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=False)
        self.assertLess(res["metrics"]["citation_coverage"]["score"], 50.0)
        self.assertTrue(len(res["critical_warnings"]) > 0)
        self.assertNotEqual(res["warning_label"], "HIGH EVIDENCE SUPPORT")

    # 6. Missing citation
    def test_06_missing_citation(self):
        q = "What is the turret V2 breakaway torque?"
        a = "The Static Breakaway Torque in Version 2 is ≤ 380 Nm across continuous 360° rotation."
        res = eval_mod.evaluate_rag_answer(q, a, TURRET_V2_EVIDENCE, use_llm=False)
        self.assertLess(res["metrics"]["citation_coverage"]["score"], 60.0)
        self.assertIn("omits inline", res["metrics"]["citation_coverage"]["justification"].lower())

    # 7. Correct basic definition
    def test_07_correct_basic_definition(self):
        entry = re_engine.lookup_component_glossary("What is a hull?")
        self.assertIsNotNone(entry)
        def_text, def_cits = re_engine.format_basic_definition_response(entry, "What is a hull?")
        res = eval_mod.evaluate_rag_answer(
            "What is a hull?",
            def_text,
            def_cits,
            info={"glossary_match": entry["canonical_name"]},
            use_llm=False
        )
        self.assertTrue(res["evaluation_succeeded"])
        self.assertGreaterEqual(res["metrics"]["evidence_support"]["score"], 75.0)
        self.assertEqual(res["contradicted_claims_count"], 0)

    # 8. Irrelevant SOP summary
    def test_08_irrelevant_sop_summary(self):
        q = "What is the main gun muzzle reference system compensation tolerance?"
        a = (
            "The Hull Welding SOP covers RHA plate receiving, preheat at 150°C, and 220°C max interpass "
            "[HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1]."
        )
        res = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=False)
        self.assertLessEqual(res["metrics"]["answer_relevance"]["score"], 35.0)
        self.assertLess(res["overall_score"], 75.0)

    # 9. Incomplete answer
    def test_09_incomplete_answer(self):
        q = "What are the V2 plinth flatness, dual-pinion backlash, breakaway torque, and slip-ring loss criteria?"
        a = (
            "Plinth Flatness Matrix is ≤ 0.035 mm TIR "
            "[HVF_SOP_2_Turret_Integration_v2.pdf, Rev 4.5, SECTION 1.0, Page 1]."
        )
        res = eval_mod.evaluate_rag_answer(q, a, TURRET_V2_EVIDENCE, use_llm=False)
        self.assertLessEqual(res["metrics"]["completeness"]["score"], 60.0)

    # 10. Unsupported tolerance (critical technical claim warning + cap)
    def test_10_unsupported_tolerance(self):
        q = "What is the turret plinth flatness tolerance in V2?"
        a = (
            "The Plinth Flatness Matrix tolerance is ± 0.002 mm TIR across the mounting ring "
            "[HVF_SOP_2_Turret_Integration_v2.pdf, Rev 4.5, SECTION 1.0, Page 1]."
        )
        res = eval_mod.evaluate_rag_answer(q, a, TURRET_V2_EVIDENCE, use_llm=True, llm_eval_fn=_mock_optimistic_llm_fn)
        self.assertNotEqual(res["warning_label"], "HIGH EVIDENCE SUPPORT")
        self.assertTrue(any(c["is_critical_technical_claim"] for c in res["claims"]))
        self.assertTrue(len(res["critical_warnings"]) > 0)
        self.assertTrue(res["human_verification_recommended"])

    # 11. Unsupported material specification
    def test_11_unsupported_material_specification(self):
        q = "What material is specified for Hull Welding?"
        a = (
            "The plates are fabricated from SAE 4340 Titanium-Vanadium Alloy Grade 5 steel "
            "[HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1]."
        )
        res = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=True, llm_eval_fn=_mock_optimistic_llm_fn)
        self.assertEqual(res["warning_label"], "UNSUPPORTED CLAIMS DETECTED")
        self.assertTrue(any(c["critical_category"] == "material" for c in res["claims"]))
        self.assertLess(res["overall_score"], 70.0)

    # 12. Insufficient evidence and abstention
    def test_12_insufficient_evidence_and_abstention(self):
        q = "What is the nuclear biological chemical filter cartridge flow rate in CFM?"
        a = "The provided SOP documentation does not contain sufficient evidence to answer this question."
        res = eval_mod.evaluate_rag_answer(
            q, a, [], info={"is_insufficient": True}, use_llm=False
        )
        self.assertEqual(res["warning_label"], "INSUFFICIENT EVIDENCE")
        self.assertLessEqual(res["metrics"]["retrieval_quality"]["score"], 35.0)
        self.assertLessEqual(res["metrics"]["completeness"]["score"], 45.0)
        self.assertTrue(res["human_verification_recommended"])
        self.assertTrue(len(res["missing_evidence"]) > 0)

    # 13. General engineering context correctly labeled
    def test_13_general_engineering_context_labeled(self):
        q = "What is the role of an assembly component?"
        a = (
            "GENERAL_CONTEXT: Standard engineering context indicates mechanical housings protect internal seals from debris.\n"
            "The Hull Welding preheat requirement is 150°C min [HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1]."
        )
        res = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=False)
        statuses = [c["support_status"] for c in res["claims"]]
        self.assertIn("GENERAL_CONTEXT", statuses)
        self.assertIn("SUPPORTED", statuses)
        self.assertEqual(res["contradicted_claims_count"], 0)
        self.assertEqual(res["unsupported_claims_count"], 0)

    # 14. Evaluator malformed JSON
    def test_14_evaluator_malformed_json(self):
        def _bad_json_fn(*args, **kwargs):
            return "{ evidence_support: BROKEN JSON [!!"

        q = "What is the hull preheat?"
        a = "Preheat is 150°C min [HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1]."
        res = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=True, llm_eval_fn=_bad_json_fn)
        self.assertFalse(res["evaluation_succeeded"])
        self.assertEqual(res["assessment_status"], "unavailable")
        self.assertEqual(res["warning_label"], "ASSESSMENT UNAVAILABLE")
        self.assertEqual(res["display_message"], "Answer quality assessment unavailable.")
        self.assertIsNone(res["overall_score"])
        self.assertEqual(res["metrics"]["evidence_support"]["status"], "NOT ASSESSED")

    # 15. Evaluator timeout
    def test_15_evaluator_timeout(self):
        def _timeout_fn(*args, **kwargs):
            raise TimeoutError("Ollama evaluator timed out after 15.0s.")

        q = "What is the hull preheat?"
        a = "Preheat is 150°C min."
        res = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=True, llm_eval_fn=_timeout_fn)
        self.assertFalse(res["evaluation_succeeded"])
        self.assertEqual(res["assessment_status"], "unavailable")
        self.assertEqual(res["warning_label"], "ASSESSMENT UNAVAILABLE")
        self.assertEqual(res["display_message"], "Answer quality assessment unavailable.")

    # 16. Evaluator unavailable
    def test_16_evaluator_unavailable(self):
        def _conn_err_fn(*args, **kwargs):
            raise ConnectionError("Ollama daemon unreachable.")

        q = "What is the hull preheat?"
        a = "Preheat is 150°C min."
        res = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=True, llm_eval_fn=_conn_err_fn)
        self.assertFalse(res["evaluation_succeeded"])
        self.assertEqual(res["assessment_status"], "unavailable")
        self.assertEqual(res["display_message"], "Answer quality assessment unavailable.")

    # 17. Historical message without assessment
    def test_17_historical_message_without_assessment(self):
        saved = db.save_message(
            conversation_id=self.cid,
            role="assistant",
            content="Legacy response content.",
            db_path=self.test_db_path
        )
        loaded = db.get_conversation_messages(self.cid, db_path=self.test_db_path)
        legacy_msg = next(m for m in loaded if m["message_id"] == saved["message_id"])
        summary = format_assessment_summary(legacy_msg.get("assessment_metadata"))
        self.assertEqual(summary["state"], "historical")
        self.assertEqual(summary["status_text"], "Not assessed — historical response.")

    # 18. Assessment persistence after restart
    def test_18_assessment_persistence_after_restart(self):
        q = "What is the hull preheat?"
        a = "Preheat is 150°C min [HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1]."
        assess = eval_mod.evaluate_rag_answer(q, a, HULL_EVIDENCE, use_llm=True, llm_eval_fn=_mock_good_llm_fn)

        saved = db.save_message(
            conversation_id=self.cid,
            role="assistant",
            content=a,
            citations=HULL_EVIDENCE,
            db_path=self.test_db_path
        )
        ok = db.update_message_assessment(saved["message_id"], assess, db_path=self.test_db_path)
        self.assertTrue(ok)

        # Simulate DB reopen / application restart
        db.init_database(self.test_db_path)
        msgs = db.get_conversation_messages(self.cid, db_path=self.test_db_path)
        reloaded = next(m for m in msgs if m["message_id"] == saved["message_id"])
        self.assertEqual(reloaded["content"], a)
        self.assertEqual(reloaded["assessment_metadata"]["overall_score"], assess["overall_score"])
        self.assertEqual(reloaded["assessment_metadata"]["warning_label"], assess["warning_label"])
        self.assertEqual(len(reloaded["assessment_metadata"]["claims"]), len(assess["claims"]))

    # 19. Sequential questions with separate assessments
    def test_19_sequential_questions_separate_assessments(self):
        r1 = eval_mod.evaluate_rag_answer(
            "What is hull preheat?",
            "Preheat is 150°C min [HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, SECTION 1.0, Page 1].",
            HULL_EVIDENCE,
            use_llm=True,
            llm_eval_fn=_mock_good_llm_fn,
        )
        r2 = eval_mod.evaluate_rag_answer(
            "What is turret V2 plinth flatness?",
            "Plinth Flatness Matrix tolerance is 0.99 mm [HVF_SOP_2_Turret_Integration_v2.pdf, Rev 4.5, SECTION 1.0, Page 1].",
            TURRET_V2_EVIDENCE,
            use_llm=True,
            llm_eval_fn=_mock_optimistic_llm_fn,
        )
        m1 = db.save_message(self.cid, "assistant", "Ans 1", assessment_metadata=r1, db_path=self.test_db_path)
        m2 = db.save_message(self.cid, "assistant", "Ans 2", assessment_metadata=r2, db_path=self.test_db_path)
        msgs = db.get_conversation_messages(self.cid, db_path=self.test_db_path)
        d1 = next(m for m in msgs if m["message_id"] == m1["message_id"])["assessment_metadata"]
        d2 = next(m for m in msgs if m["message_id"] == m2["message_id"])["assessment_metadata"]
        self.assertEqual(d1["warning_label"], "HIGH EVIDENCE SUPPORT")
        self.assertEqual(d2["warning_label"], "CONTRADICTORY EVIDENCE")
        self.assertNotEqual(d1["overall_score"], d2["overall_score"])

    # 20. Cancellation during answer generation & non-destruction guarantee
    def test_20_cancellation_and_non_destruction_on_failure(self):
        # 20a. Cancellation before substantive output
        res_empty_cancel = eval_mod.evaluate_rag_answer(
            "What is hull preheat?",
            "*[Generation was stopped by user]*",
            HULL_EVIDENCE,
            info={"is_cancelled": True},
            use_llm=True
        )
        self.assertTrue(res_empty_cancel["assessment_skipped"])
        self.assertEqual(res_empty_cancel["assessment_status"], "skipped")

        # 20b. Cancellation after partial output saves answer & runs quick non-blocking assessment
        partial_answer = "Preheat is 150°C min.\n*[Generation was stopped by user]*"
        saved = db.save_message(
            self.cid, "assistant", partial_answer, is_cancelled=True, db_path=self.test_db_path
        )
        res_partial_cancel = eval_mod.evaluate_rag_answer(
            "What is hull preheat?",
            partial_answer,
            HULL_EVIDENCE,
            info={"is_cancelled": True},
            use_llm=True  # skipped LLM internally because is_cancelled=True
        )
        self.assertEqual(res_partial_cancel["evaluator_model"], "deterministic-auditor")
        # Persist failed/unavailable assessment and verify original answer content is completely preserved
        bad_assess = eval_mod.evaluate_rag_answer(
            "What is hull preheat?",
            partial_answer,
            HULL_EVIDENCE,
            use_llm=True,
            llm_eval_fn=lambda *a, **k: "not-json"
        )
        db.update_message_assessment(saved["message_id"], bad_assess, db_path=self.test_db_path)
        loaded = db.get_conversation_messages(self.cid, db_path=self.test_db_path)
        rec = next(m for m in loaded if m["message_id"] == saved["message_id"])
        self.assertEqual(rec["content"], partial_answer)
        self.assertEqual(rec["assessment_metadata"]["display_message"], "Answer quality assessment unavailable.")


if __name__ == "__main__":
    unittest.main()

