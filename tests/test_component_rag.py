#!/usr/bin/env python3
"""
Test Suite: Mini Phase 3 - Component-Aware RAG and Beginner-Friendly SOP Answers
================================================================================
Comprehensive verification of component-aware retrieval, intent classification,
evidence grounding, revision isolation, uploaded document support, and procedural fallback.

Verification Coverage:
1. Component overview questions (Category A).
2. Individual component function questions (Category B).
3. Assembly and subsystem questions (Category C).
4. Explicit relationship questions (Category D).
5. Unsupported relationship questions (rejection of unvalidated links).
6. Missing function description handling (abstention/explicit note).
7. Evidence status preservation (DIRECTLY_STATED vs GENERAL_CONTEXT vs INFERRED).
8. Citation metadata integrity (filename, revision, section, page).
9. V1 / V2 revision isolation (no cross-contamination).
10. All revisions behavior (both revisions included with V2 prioritization).
11. Hybrid retrieval (FAISS chunks + structured component records).
12. Uploaded document component questions (non-baseline PDF compatibility).
13. Procedural RAG passthrough (Category F questions continue existing flow).
14. Non-physical entity filtering (no OTHER_REFERENCE / TOOL as physical components).
15. Deterministic mocked end-to-end answer generation.
16. Streaming RAG answer with component intent metadata.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from typing import List, Dict, Any

# Ensure project root in sys.path
_dir = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.abspath(os.path.join(_dir, "..")) if os.path.basename(_dir) == "tests" else _dir
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import rag_engine as re
import document_processor as dp


class TestComponentAwareRAG(unittest.TestCase):
    """Unit and integration test cases for Mini Phase 3 Component-Aware RAG."""

    @classmethod
    def setUpClass(cls):
        cls.index_dir = re.DEFAULT_INDEX_DIR
        cls.all_comps = re.load_components_metadata(cls.index_dir)
        cls.has_metadata = len(cls.all_comps) > 0

    def setUp(self):
        self.assertTrue(self.has_metadata, "Component metadata must be present in data/faiss_index")

    def test_01_component_overview_intent_and_retrieval(self):
        """Category A: Overview/list question triggers COMPONENT_OVERVIEW and retrieves physical components."""
        query = "What are the main components of the turret mount system?"
        intent = re.detect_component_intent(query, index_dir=self.index_dir)
        
        self.assertTrue(intent["is_component_intent"])
        self.assertEqual(intent["category_code"], "A")
        self.assertEqual(intent["category"], "COMPONENT_OVERVIEW")

        res = re.retrieve_component_aware_evidence(query, top_k_components=6, index_dir=self.index_dir, revision_mode="v2")
        self.assertTrue(res["is_component_query"])
        self.assertGreater(len(res["components"]), 0)

        # Main components must strictly be physical components or assemblies
        for c in res["components"]:
            self.assertIn(c["entity_type"], ("PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM"))
            self.assertNotEqual(c["entity_type"], "OTHER_REFERENCE")

    def test_02_individual_component_function_intent_and_retrieval(self):
        """Category B: Function query triggers COMPONENT_FUNCTION and retrieves component function."""
        query = "What is the function of a ceramic-hybrid bearing?"
        intent = re.detect_component_intent(query, index_dir=self.index_dir)

        self.assertTrue(intent["is_component_intent"])
        self.assertEqual(intent["category_code"], "B")
        self.assertEqual(intent["category"], "COMPONENT_FUNCTION")

        res = re.retrieve_component_aware_evidence(query, top_k_components=4, index_dir=self.index_dir, revision_mode="v2")
        self.assertTrue(res["is_component_query"])
        self.assertGreater(len(res["components"]), 0)

        top_comp = res["components"][0]
        self.assertTrue(any(k in top_comp["component_name"].lower() for k in ("bearing", "raceway", "roller")))
        self.assertIn("primary_function", top_comp)
        self.assertTrue(len(top_comp["primary_function"]) > 0)

    def test_03_assembly_and_subsystem_intent_and_retrieval(self):
        """Category C: Subsystem query triggers ASSEMBLY_SUBSYSTEM and retrieves powerpack assemblies."""
        query = "Explain the main components of the V12 powerpack."
        intent = re.detect_component_intent(query, index_dir=self.index_dir)

        self.assertTrue(intent["is_component_intent"])
        self.assertEqual(intent["category_code"], "C")
        self.assertEqual(intent["category"], "ASSEMBLY_SUBSYSTEM")

        res = re.retrieve_component_aware_evidence(query, top_k_components=5, index_dir=self.index_dir, revision_mode="v2")
        self.assertTrue(res["is_component_query"])
        comp_names = [c["component_name"] for c in res["components"]]
        self.assertTrue(any("powerpack" in name.lower() or "engine" in name.lower() for name in comp_names))

    def test_04_explicit_relationship_validation(self):
        """Category D: Relationship query triggers COMPONENT_RELATIONSHIPS and returns validated connections."""
        query = "How does the torsion bar connect to the balancer arm?"
        intent = re.detect_component_intent(query, index_dir=self.index_dir)

        self.assertTrue(intent["is_component_intent"])
        self.assertEqual(intent["category_code"], "D")
        self.assertEqual(intent["category"], "COMPONENT_RELATIONSHIPS")

        res = re.retrieve_component_aware_evidence(query, top_k_components=5, index_dir=self.index_dir, revision_mode="all")
        self.assertTrue(res["is_component_query"])
        self.assertGreater(len(res["relationships"]), 0)

        # Check that relationships have allowed predicates and verbatim sources
        for rel in res["relationships"]:
            self.assertIn(rel["relationship_type"], re.ALLOWED_RELATIONSHIP_PREDICATES)
            self.assertTrue(len(rel["source_reference"]) > 0)
            self.assertTrue(len(rel["target_component"]) > 0)

    def test_05_unsupported_relationship_rejection(self):
        """Unsupported relationships between unrelated components are not fabricated."""
        query = "How does the glacis plate connect to the bore evacuator?"
        res = re.retrieve_component_aware_evidence(query, top_k_components=6, index_dir=self.index_dir, revision_mode="all")
        
        # Verify no link between Glacis Plate and Bore Evacuator exists
        for rel in res["relationships"]:
            src = rel["source_component"].lower()
            tgt = rel["target_component"].lower()
            self.assertFalse("glacis" in src and "evacuator" in tgt)
            self.assertFalse("evacuator" in src and "glacis" in tgt)

    def test_06_missing_function_description_handling(self):
        """When component function is unstated in SOP, prompt explicitly notes it rather than hallucinating."""
        mock_comp = {
            "component_name": "Test Unspecified Bracket",
            "entity_type": "PHYSICAL_COMPONENT",
            "source_filename": "HVF_SOP_Test.pdf",
            "revision": "Rev 1.0",
            "section_reference": "SECTION 1.0",
            "page_number": 3,
            "evidence_status": "GENERAL_CONTEXT",
            "simple_description": "Structural mounting bracket.",
            "primary_function": "",  # Missing function
            "relationships": []
        }
        context_str, citations = re.build_component_evidence_context(
            retrieved_components=[mock_comp],
            retrieved_chunks=[]
        )
        self.assertIn("do NOT invent a function", context_str)
        self.assertIn("Test Unspecified Bracket", context_str)

    def test_07_evidence_status_preservation(self):
        """Evidence status (DIRECTLY_STATED vs GENERAL_CONTEXT vs INFERRED) is explicitly preserved in context."""
        mock_comps = [
            {
                "component_name": "Lower Hull Plate",
                "entity_type": "PHYSICAL_COMPONENT",
                "source_filename": "HVF_SOP_1_Hull_Welding.pdf",
                "revision": "Rev 4.2",
                "section_reference": "SECTION 1.0",
                "page_number": 2,
                "evidence_status": "DIRECTLY_STATED",
                "primary_function": "Bottom ballistic mine protection.",
                "relationships": []
            },
            {
                "component_name": "Synthesized Hull Subassembly",
                "entity_type": "ASSEMBLY",
                "source_filename": "HVF_SOP_1_Hull_Welding.pdf",
                "revision": "Rev 4.2",
                "section_reference": "SECTION 1.0",
                "page_number": 1,
                "evidence_status": "GENERAL_CONTEXT",
                "primary_function": "Structural chassis.",
                "relationships": []
            }
        ]
        context_str, _ = re.build_component_evidence_context(retrieved_components=mock_comps, retrieved_chunks=[])
        self.assertIn("EVIDENCE STATUS: DIRECTLY_STATED", context_str)
        self.assertIn("EVIDENCE STATUS: GENERAL_CONTEXT", context_str)

    def test_08_citation_metadata_integrity(self):
        """Component citations contain filename, revision, section, and page number."""
        query = "What is the function of the torsion bar?"
        res = re.retrieve_component_aware_evidence(query, top_k_components=3, index_dir=self.index_dir, revision_mode="v2")
        self.assertGreater(len(res["citations"]), 0)

        for cit in res["citations"]:
            self.assertTrue(len(cit.get("filename", "")) > 0)
            self.assertTrue(len(cit.get("revision", "")) > 0)
            self.assertTrue(len(cit.get("section_title", "")) > 0)
            self.assertIsNotNone(cit.get("page_number"))
            # Must contain bracketed citation string
            cit_str = cit.get("citation", "")
            self.assertTrue(cit_str.startswith("[") and cit_str.endswith("]"))

    def test_09_v1_v2_isolation(self):
        """V2 mode excludes baseline V1 records; V1 mode excludes revised V2 records."""
        query = "What are the components of the hull welding structure?"

        # V2 Mode
        res_v2 = re.retrieve_component_aware_evidence(query, top_k_components=10, index_dir=self.index_dir, revision_mode="v2")
        for c in res_v2["components"]:
            self.assertTrue(c["is_v2"], f"Component {c['component_name']} must be V2 in V2 mode")
            self.assertFalse(re.is_v1_component(c), f"Component {c['component_name']} cannot be V1 in V2 mode")

        # V1 Mode
        res_v1 = re.retrieve_component_aware_evidence(query, top_k_components=10, index_dir=self.index_dir, revision_mode="v1")
        for c in res_v1["components"]:
            self.assertTrue(re.is_v1_component(c), f"Component {c['component_name']} must be V1 in V1 mode")
            self.assertFalse(c["is_v2"], f"Component {c['component_name']} cannot be V2 in V1 mode")

    def test_10_all_revisions_behavior(self):
        """All revisions mode returns records from both revisions with V2 prioritized."""
        query = "What changed in the components between V1 and V2?"
        res = re.retrieve_component_aware_evidence(query, top_k_components=10, index_dir=self.index_dir, revision_mode="all")

        has_v1 = any(re.is_v1_component(c) for c in res["components"])
        has_v2 = any(re.is_v2_component(c) for c in res["components"])
        self.assertTrue(has_v1 and has_v2, "All revisions mode must retrieve both V1 and V2 records")

    def test_11_hybrid_retrieval_chunks_and_components(self):
        """Component-aware retrieval returns both FAISS chunk passages and structured components."""
        query = "What are the basic parts of the suspension and track system?"
        res = re.retrieve_component_aware_evidence(query, top_k_chunks=3, top_k_components=5, index_dir=self.index_dir, revision_mode="v2")

        self.assertTrue(res["is_component_query"])
        self.assertGreater(len(res["components"]), 0)
        self.assertGreater(len(res["chunks"]), 0)
        self.assertGreater(len(res["citations"]), 0)

    def test_12_uploaded_document_component_query(self):
        """Uploaded documents are searchable and retrieved without hardcoding baseline SOPs."""
        mock_uploaded_comp = {
            "component_id": "CMP_UPLOADED_TEST_01",
            "component_name": "Auxiliary Hydraulic Reservoir",
            "entity_type": "PHYSICAL_COMPONENT",
            "subsystem": "Auxiliary Hydraulics Subsystem",
            "simple_description": "Welded stainless reservoir tank.",
            "primary_function": "Stores hydraulic fluid under nitrogen head pressure.",
            "source_filename": "HVF_SOP_Uploaded_Custom.pdf",
            "filename": "HVF_SOP_Uploaded_Custom.pdf",
            "document_id": "HVF/AVNL/UPLOADED/HYD-01",
            "revision": "Rev 1.0 (Uploaded)",
            "page_number": 1,
            "section_reference": "SECTION 1.0",
            "is_v1": False,
            "is_v2": True,
            "evidence_status": "DIRECTLY_STATED",
            "relationships": []
        }

        with patch("rag_engine.load_components_metadata", return_value=self.all_comps + [mock_uploaded_comp]):
            res = re.retrieve_component_aware_evidence(
                "What is the function of the Auxiliary Hydraulic Reservoir?",
                index_dir=self.index_dir,
                revision_mode="v2"
            )
            self.assertTrue(res["is_component_query"])
            names = [c["component_name"] for c in res["components"]]
            self.assertIn("Auxiliary Hydraulic Reservoir", names)

    def test_13_procedural_rag_passthrough(self):
        """Procedural questions (Category F) bypass component structuring and use procedural RAG."""
        procedural_queries = [
            "What is the preheating temperature required for hull welding?",
            "What is the torque sequence for plinth bolts?",
            "What are the safety precautions before high voltage calibration?"
        ]
        for q in procedural_queries:
            intent = re.detect_component_intent(q, index_dir=self.index_dir)
            self.assertFalse(intent["is_component_intent"], f"Query '{q}' must not trigger component intent")
            self.assertEqual(intent["category_code"], "F")
            self.assertEqual(intent["category"], "GENERAL_PROCEDURAL")

            res = re.retrieve_component_aware_evidence(q, index_dir=self.index_dir, revision_mode="v2")
            self.assertFalse(res["is_component_query"])
            self.assertEqual(len(res["components"]), 0)
            self.assertGreater(len(res["chunks"]), 0)

    def test_14_no_false_classification_from_other_reference(self):
        """OTHER_REFERENCE, TOOL_OR_INSTRUMENT, and DOCUMENT_OR_CERTIFICATE are never presented as physical components."""
        query = "What are the main components of the turret mount system?"
        res = re.retrieve_component_aware_evidence(query, top_k_components=10, index_dir=self.index_dir, revision_mode="all")

        for comp in res["components"]:
            self.assertIn(comp["entity_type"], ("PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM"))
            self.assertNotIn(comp["entity_type"], ("OTHER_REFERENCE", "TOOL_OR_INSTRUMENT", "DOCUMENT_OR_CERTIFICATE"))

    @patch("rag_engine.generate_response")
    def test_15_mocked_end_to_end_answer_generation(self, mock_gen):
        """End-to-end generate_rag_answer builds grounded component structure and returns citations."""
        mock_gen.return_value = {
            "response": (
                "### 1. Overview\n"
                "The torsion bar is the primary elastic element of the combat vehicle suspension.\n\n"
                "### 2. Main Components\n"
                "- Torsion Bar [PHYSICAL_COMPONENT]\n\n"
                "### 3. Component Functions\n"
                "Acts as primary elastic suspension spring element that twists to absorb ground shocks [HVF_SOP_4_Torsion_Suspension_v2.pdf, Rev 5.2, SECTION 1.0, Page 2].\n\n"
                "### 4. Validated Relationships\n"
                "Connected to Balancer Arm via splined interface [Section 3.0]."
            ),
            "tokens_per_second": 35.0,
            "eval_count": 80,
            "total_duration_ms": 2500.0
        }

        ans = re.generate_rag_answer(
            question="What is the function of the torsion bar?",
            revision_mode="v2",
            index_dir=self.index_dir
        )
        self.assertEqual(ans["status"], "success")
        self.assertFalse(ans["is_insufficient"])
        self.assertTrue(ans["is_component_query"])
        self.assertEqual(ans["component_intent"]["category_code"], "B")
        self.assertGreater(len(ans["citations"]), 0)
        self.assertIn("Torsion Bar", ans["answer"])

    @patch("rag_engine.stream_response")
    def test_16_streaming_rag_answer_with_component_intent(self, mock_stream):
        """stream_rag_answer returns token generator, citations, and component intent metadata."""
        def mock_tokens():
            yield "The "
            yield "torsion bar "
            yield "absorbs ground shocks."

        mock_stream.return_value = mock_tokens()

        token_gen, citations, info = re.stream_rag_answer(
            question="What is the function of the torsion bar?",
            revision_mode="v2",
            index_dir=self.index_dir
        )
        tokens = list(token_gen)
        self.assertEqual("".join(tokens), "The torsion bar absorbs ground shocks.")
        self.assertGreater(len(citations), 0)
        self.assertTrue(info["is_component_query"])
        self.assertEqual(info["component_intent"]["category_code"], "B")
        self.assertGreater(info["retrieved_components_count"], 0)


if __name__ == "__main__":
    unittest.main()

