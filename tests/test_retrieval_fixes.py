"""
Unit and regression test suite for Mini Phase 3D retrieval and intent fixes.
Tests:
1. Intent detection for hull assemblies and subsystem breakdown.
2. Structural hull assemblies retrieval (Hull Tub Assembly, Sponson Box).
3. Structural plates vs process equipment distinction (Lower Hull Plate, Glacis Plate).
4. Procedural retrieval for engine alignment from SOP 3.
5. Exclusion of unrelated alignment chunks (suppression of SOP 4 sprockets and SOP 1 turnover jig).
6. Preservation of procedural sequence and exact technical values.
7. Strict V1/V2 revision isolation.
8. Missing evidence / empty query boundaries.
"""

import unittest
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import rag_engine as re


class TestRetrievalFixes(unittest.TestCase):
    """Test suite covering Mini Phase 3D retrieval, ranking, and intent fixes."""

    @classmethod
    def setUpClass(cls):
        cls.index, cls.metadata, cls.manifest = re.load_faiss_index()
        cls.components = re.load_components_metadata()

    def test_01_intent_detection_hull_assemblies(self):
        """Verify intent detection identifies 'main assemblies' as component intent."""
        queries = [
            "What are the main assemblies of the hull welding SOP?",
            "What does the hull welding SOP say about its main assemblies?",
            "List the main assemblies and subsystems of the armoured hull",
        ]
        for q in queries:
            intent = re.detect_component_intent(q)
            self.assertTrue(
                intent["is_component_intent"],
                f"Query '{q}' was not recognized as component intent: {intent}"
            )
            self.assertIn(
                intent["category"],
                ["ASSEMBLY_SUBSYSTEM", "COMPONENT_OVERVIEW"],
                f"Query '{q}' got wrong category: {intent['category']}"
            )

    def test_02_hull_structural_assemblies_retrieval(self):
        """Verify retrieval prioritizes structural assemblies (Hull Tub Assembly, Sponson Box)."""
        query = "What does the hull welding SOP say about its main assemblies?"
        evidence = re.retrieve_component_aware_evidence(query, top_k_chunks=5, top_k_components=8)
        
        comps = evidence.get("components", [])
        self.assertGreater(len(comps), 0, "No components retrieved for hull assemblies query")
        
        comp_names = [c["component_name"] for c in comps]
        self.assertIn("Hull Tub Assembly", comp_names, "Hull Tub Assembly missing from retrieved components")
        self.assertIn("Sponson Box", comp_names, "Sponson Box missing from retrieved components")
        
        # Verify entity types are ASSEMBLY
        for c in comps:
            if c["component_name"] in ["Hull Tub Assembly", "Sponson Box"]:
                self.assertEqual(c["entity_type"], "ASSEMBLY")

    def test_03_structural_plates_vs_process_equipment(self):
        """Verify structural plates are classified as PHYSICAL_COMPONENT, not process equipment."""
        query = "What does the hull welding SOP say about its main assemblies?"
        evidence = re.retrieve_component_aware_evidence(query, top_k_chunks=5, top_k_components=8)
        
        comps = evidence.get("components", [])
        plate_comps = [c for c in comps if c["component_name"] in ["Lower Hull Plate", "Glacis Plate"]]
        self.assertGreater(len(plate_comps), 0, "Structural plates missing from retrieved components")
        
        for p in plate_comps:
            self.assertEqual(
                p["entity_type"],
                "PHYSICAL_COMPONENT",
                f"{p['component_name']} should be PHYSICAL_COMPONENT, got {p['entity_type']}"
            )
            # Must not be process or tool
            self.assertNotIn(p["entity_type"], ["PROCESS_OR_OPERATION", "TOOL_OR_INSTRUMENT"])

    def test_04_engine_alignment_procedural_retrieval_sop3(self):
        """Verify engine alignment procedural query retrieves chunks exclusively from SOP 3."""
        query = "What are the engine alignment procedure steps?"
        chunks = re.retrieve_relevant_chunks(query, top_k=5, revision_mode="v2")
        self.assertGreater(len(chunks), 0)
        
        # Top chunks must be from HVF_SOP_3_Engine_Alignment_v2.pdf
        top_chunks = chunks[:3]
        for c in top_chunks:
            self.assertIn(
                "Engine_Alignment",
                c.get("filename", ""),
                f"Top chunk {c.get('filename')} is not from Engine Alignment SOP 3"
            )

    def test_05_exclusion_of_unrelated_alignment_chunks(self):
        """Verify suspension sprocket laser alignment and turnover jigs are excluded from top engine alignment chunks."""
        query = "What are the engine alignment procedure steps?"
        chunks = re.retrieve_relevant_chunks(query, top_k=3, revision_mode="v2")
        
        for c in chunks:
            fn = c.get("filename", "")
            sec = c.get("section_title", "")
            self.assertNotIn(
                "Torsion_Suspension",
                fn,
                f"Suspension chunk unexpectedly found in top engine alignment results: {fn} - {sec}"
            )
            self.assertNotIn(
                "Hull_Welding",
                fn,
                f"Hull turnover jig chunk unexpectedly found in top engine alignment results: {fn} - {sec}"
            )

    def test_06_procedural_sequence_and_value_preservation(self):
        """Verify retrieved Engine Alignment chunks contain correct procedure steps and exact tolerances."""
        query = "What are the engine alignment procedure steps?"
        chunks = re.retrieve_relevant_chunks(query, top_k=5, revision_mode="v2")
        
        combined_text = " ".join(c.get("chunk_text", "") for c in chunks)
        
        # Check Section 1.0 values: hydromount damping, thermal offset
        self.assertIn("+0.10 mm", combined_text, "Cold offset +0.10 mm missing from retrieved chunks")
        self.assertIn("0.035 mm", combined_text, "Running offset 0.035 mm missing from retrieved chunks")
        
        # Check Section 2.0 values: 5.5-tonne powerpack, 4-point hoist
        self.assertIn("5.5-tonne", combined_text, "5.5-tonne powerpack specification missing from retrieved chunks")
        
        # Check Section 3.0 values: dual-laser, thermal compensation
        self.assertIn("dual-laser", combined_text.lower(), "Dual-laser sensor protocol missing from retrieved chunks")
        
        # Check QA capability index: Cpk >= 1.67
        self.assertIn("1.67", combined_text, "DGQA Cpk >= 1.67 benchmark missing from retrieved chunks")

    def test_07_revision_mode_isolation(self):
        """Verify strict revision isolation is preserved in retrieval."""
        query = "What are the engine alignment procedure steps?"
        
        # V2 mode must contain only V2 chunks
        v2_chunks = re.retrieve_relevant_chunks(query, top_k=4, revision_mode="v2")
        for c in v2_chunks:
            self.assertTrue(re.is_v2_chunk(c), f"V1 chunk found in V2 retrieval: {c.get('filename')}")
            
        # V1 mode must contain only V1 chunks
        v1_chunks = re.retrieve_relevant_chunks(query, top_k=4, revision_mode="v1")
        for c in v1_chunks:
            self.assertTrue(re.is_v1_chunk(c), f"V2 chunk found in V1 retrieval: {c.get('filename')}")

    def test_08_missing_evidence_and_empty_queries(self):
        """Verify retrieval handles non-existent terms and empty queries gracefully."""
        # Empty query
        intent_empty = re.detect_component_intent("")
        self.assertFalse(intent_empty["is_component_intent"])
        self.assertEqual(intent_empty["category"], "GENERAL_PROCEDURAL")
        
        # Non-existent component
        res = re.retrieve_component_aware_evidence("quantum hyperdrive warp coil", top_k_chunks=3, top_k_components=5)
        self.assertEqual(len(res["components"]), 0, "Hallucinated components for non-existent query")


if __name__ == "__main__":
    unittest.main()

