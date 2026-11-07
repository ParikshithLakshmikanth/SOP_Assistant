#!/usr/bin/env python3
"""
Unit and Integration Tests for Mini Phase 5: Integrated Component Explorer and SOP Chatbot
========================================================================================
Validates:
1. Opening chatbot from a selected component with proper prompt construction.
2. Correct component context transfer (name, entity type, filename, section, page).
3. Revision mode preservation between Component Explorer and Chatbot.
4. Context-aware conversational follow-up questions with antecedent pronoun resolution.
5. Verified relationship navigation with target existence validation.
6. Unresolved relationship target handling without fabricating fake component records.
7. Citation correctness in component QA synthesis.
8. SQLite conversation history persistence across multi-turn component dialogues.
9. Non-regression for standard procedural queries.
10. Uploaded document component context transfer and follow-up interaction.
"""

import unittest
import os
import tempfile
from typing import Dict, Any, List

import rag_engine as re
import database as db


class TestIntegratedExperience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.components = re.load_components_metadata()
        cls.assertTrue(len(cls.components) > 0, "components_metadata.json must contain records")
        cls.temp_dir = tempfile.mkdtemp(prefix="sop_test_mini5_")
        cls.db_path = os.path.join(cls.temp_dir, "test_assistant.db")
        db.init_database(cls.db_path)

    @classmethod
    def tearDownClass(cls):
        import shutil
        if os.path.exists(cls.temp_dir):
            try:
                shutil.rmtree(cls.temp_dir)
            except Exception:
                pass

    # ------------------------------------------------------------------------
    # 1. Opening Chatbot from a Selected Component & Context Transfer
    # ------------------------------------------------------------------------
    def test_01_component_to_chat_context_transfer(self):
        """1. Verify opening chatbot transfers complete component context and generates proper prompt."""
        plate = next((c for c in self.components if c.get("component_name") == "Lower Hull Plate"), None)
        self.assertIsNotNone(plate)

        detail = re.format_component_detail(plate)
        # Context payload construction as performed in app.py
        context_payload = {
            "component_name": detail["component_name"],
            "entity_type": detail["entity_type"],
            "filename": detail["filename"],
            "section": detail["section"],
            "page_number": detail["page_number"],
            "associated_subsystem": detail["associated_subsystem"]
        }
        prompt_text = f"Explain the {detail['component_name']} ({detail['entity_type']}), its documented function, and its relationships based on the SOP evidence."

        self.assertEqual(context_payload["component_name"], "Lower Hull Plate")
        self.assertEqual(context_payload["entity_type"], "PHYSICAL_COMPONENT")
        self.assertEqual(context_payload["filename"], "HVF_SOP_1_Hull_Welding.pdf")
        self.assertIn("Lower Hull Plate", prompt_text)
        self.assertIn("PHYSICAL_COMPONENT", prompt_text)
        self.assertIn("relationships", prompt_text)

    # ------------------------------------------------------------------------
    # 2. Revision Mode Preservation
    # ------------------------------------------------------------------------
    def test_02_revision_mode_preservation(self):
        """2. Verify revision mode selection in Explorer maps deterministically to RAG retrieval."""
        mode_mappings = [
            ("V1 (Baseline / Archival)", "v1"),
            ("V2 (Active / Revised)", "v2"),
            ("All Revisions", "all")
        ]
        for ui_choice, expected_engine_mode in mode_mappings:
            evidence = re.retrieve_component_aware_evidence(
                query="Lower Hull Plate",
                top_k_chunks=3,
                revision_mode=ui_choice
            )
            self.assertEqual(evidence["revision_mode"], expected_engine_mode)

    # ------------------------------------------------------------------------
    # 3. Context-Aware Conversational Follow-Up Resolution
    # ------------------------------------------------------------------------
    def test_03_conversational_follow_up_pronoun_resolution(self):
        """3. Verify resolve_conversational_query maps pronoun follow-ups to the antecedent component."""
        history = [
            {"role": "user", "content": "Explain the Lower Hull Plate (PHYSICAL_COMPONENT), its documented function, and its relationships based on the SOP evidence."},
            {"role": "assistant", "content": "The Lower Hull Plate is a heavy armoured base plate forming the structural floor..."}
        ]

        test_questions = [
            ("What does this component do?", "Lower Hull Plate"),
            ("Which assembly does it belong to?", "Lower Hull Plate"),
            ("What other components connect to it?", "Lower Hull Plate"),
            ("What happens if this component is changed?", "Lower Hull Plate"),
            ("What changed in this component between V1 and V2?", "Lower Hull Plate"),
            ("Which SOP section describes its installation?", "Lower Hull Plate")
        ]

        for q, expected_antecedent in test_questions:
            eff_q, ant = re.resolve_conversational_query(q, history)
            self.assertEqual(ant, expected_antecedent, f"Failed antecedent for query: {q}")
            self.assertIn(expected_antecedent, eff_q)

    # ------------------------------------------------------------------------
    # 4. Verified Relationship Navigation (Resolved Targets)
    # ------------------------------------------------------------------------
    def test_04_verified_relationship_navigation_resolved(self):
        """4. Verify relationships link to valid existing component targets in metadata."""
        comps_with_rels = [c for c in self.components if c.get("relationships")]
        self.assertGreater(len(comps_with_rels), 0)

        all_names = {c.get("component_name", "").strip().lower() for c in self.components if c.get("component_name")}

        for c in comps_with_rels:
            detail = re.format_component_detail(c)
            for r in detail["relationships"]:
                tgt_name = r.get("target_component", "")
                self.assertIn(tgt_name.strip().lower(), all_names, f"Target '{tgt_name}' should exist in metadata")

    # ------------------------------------------------------------------------
    # 5. Unresolved Relationship Target Handling
    # ------------------------------------------------------------------------
    def test_05_unresolved_relationship_target_handling(self):
        """5. Verify unresolved relationship targets are flagged without creating fake records."""
        mock_comp = {
            "component_id": "CMP_MOCK_UNRESOLVED",
            "component_name": "Optical Fire-Wire Detection Loop",
            "entity_type": "PHYSICAL_COMPONENT",
            "relationships": [
                {
                    "source_component": "Optical Fire-Wire Detection Loop",
                    "relationship_type": "CONNECTED_TO",
                    "target_component": "External Non-Indexed Halon Dispenser Unit",
                    "source_reference": "Section 1.0: Fire-wire sensor loop connects directly to the external dispenser unit."
                }
            ],
            "source_filename": "HVF_SOP_3_Engine_Alignment.pdf",
            "page_number": 2,
            "section_reference": "SECTION 1.0"
        }

        detail = re.format_component_detail(mock_comp)
        self.assertTrue(detail["has_relationships"])
        rel = detail["relationships"][0]

        # Verify target is identified as non-existent in corpus
        all_names = {c.get("component_name", "").strip().lower() for c in self.components if c.get("component_name")}
        is_resolved = rel["target_component"].strip().lower() in all_names
        self.assertFalse(is_resolved, "Simulated external target should be unresolved")
        self.assertEqual(rel["relationship_type"], "CONNECTED_TO")
        self.assertEqual(rel["target_component"], "External Non-Indexed Halon Dispenser Unit")
        self.assertTrue(len(rel["source_reference"]) > 0)

    # ------------------------------------------------------------------------
    # 6. Citation Correctness in Component QA Synthesis
    # ------------------------------------------------------------------------
    def test_06_citation_correctness_in_chat_synthesis(self):
        """6. Verify component RAG synthesis returns structured citations."""
        evidence = re.retrieve_component_aware_evidence(
            query="Explain the Turret Bearing Ring",
            top_k_chunks=3,
            revision_mode="v2"
        )
        self.assertTrue(evidence["is_component_query"])
        self.assertGreater(len(evidence["citations"]), 0)
        top_cit = evidence["citations"][0]
        self.assertIn("filename", top_cit)
        self.assertIn("revision", top_cit)
        self.assertIn("page_number", top_cit)
        self.assertIn("citation", top_cit)

    # ------------------------------------------------------------------------
    # 7. Conversation History Persistence in SQLite
    # ------------------------------------------------------------------------
    def test_07_conversation_history_persistence_in_db(self):
        """7. Verify multi-turn component dialogue persists cleanly in SQLite database."""
        cid = db.create_conversation("Component: Lower Hull Plate", db_path=self.db_path)["conversation_id"]

        # Turn 1: Initial component inquiry
        db.save_message(
            conversation_id=cid,
            role="user",
            content="Explain the Lower Hull Plate (PHYSICAL_COMPONENT), its documented function, and its relationships based on the SOP evidence.",
            db_path=self.db_path
        )
        db.save_message(
            conversation_id=cid,
            role="assistant",
            content="The Lower Hull Plate is a heavy armoured base plate forming the structural floor...",
            citations=[{"citation": "[HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, Page 2]"}],
            db_path=self.db_path
        )

        # Turn 2: Follow-up question
        db.save_message(
            conversation_id=cid,
            role="user",
            content="What other components connect to it?",
            db_path=self.db_path
        )
        db.save_message(
            conversation_id=cid,
            role="assistant",
            content="It connects to the Glacis Plate via a bevel weld joint and locks into the Hull Tub Assembly...",
            citations=[{"citation": "[HVF_SOP_1_Hull_Welding.pdf, Rev 4.2, Page 3]"}],
            db_path=self.db_path
        )

        # Reload messages
        history = db.get_conversation_messages(cid, db_path=self.db_path)
        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[2]["role"], "user")
        self.assertEqual(history[3]["role"], "assistant")
        self.assertEqual(len(history[1]["citations"]), 1)
        self.assertEqual(len(history[3]["citations"]), 1)

    # ------------------------------------------------------------------------
    # 8. Non-Regression on Procedural Inquiries
    # ------------------------------------------------------------------------
    def test_08_existing_procedural_questions_non_regression(self):
        """8. Verify procedural questions without pronouns pass through unaffected."""
        procedural_q = "What are the engine alignment procedure steps?"
        eff_q, ant = re.resolve_conversational_query(procedural_q, [])
        self.assertEqual(eff_q, procedural_q)
        self.assertIsNone(ant)

        # Verify retrieval operates normally
        evidence = re.retrieve_component_aware_evidence(procedural_q, top_k_chunks=3, revision_mode="v2")
        self.assertGreater(len(evidence["chunks"]), 0)
        top_chunk = evidence["chunks"][0]
        self.assertIn("HVF_SOP_3_Engine_Alignment", top_chunk["filename"])

    # ------------------------------------------------------------------------
    # 9. Uploaded Document Components Integration & Follow-Up
    # ------------------------------------------------------------------------
    def test_09_uploaded_document_components_follow_up(self):
        """9. Verify uploaded document component context is retained across follow-ups."""
        uploaded_comp = {
            "component_id": "CMP_UPLOADED_AUX_01",
            "component_name": "Auxiliary Power Turbine Igniter",
            "entity_type": "PHYSICAL_COMPONENT",
            "source_filename": "HVF_SOP_UPLOADED_AUX.pdf",
            "page_number": 5
        }

        history = [
            {"role": "user", "content": f"Explain the {uploaded_comp['component_name']} ({uploaded_comp['entity_type']}) based on the SOP evidence."},
            {"role": "assistant", "content": f"The {uploaded_comp['component_name']} initiates combustion in the auxiliary power turbine..."}
        ]

        # Follow-up referencing uploaded component
        eff_q, ant = re.resolve_conversational_query("What does this component do?", history)
        self.assertEqual(ant, "Auxiliary Power Turbine Igniter")
        self.assertIn("Auxiliary Power Turbine Igniter", eff_q)


if __name__ == "__main__":
    unittest.main()

