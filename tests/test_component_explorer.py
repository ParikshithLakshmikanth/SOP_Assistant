#!/usr/bin/env python3
"""
Unit and Integration Tests for Mini Phase 4: Component Explorer UI & Logic
========================================================================
Validates:
1. Component filtering (by entity type, document, revision, subsystem, uncertainty, search).
2. Revision filtering (V1 Baseline, V2 Revised, All Revisions).
3. Component detail rendering (name, description, function, subsystem, provenance).
4. Missing descriptions and graceful fallback handling.
5. Evidence display and verbatim passage provenance.
6. Relationship validation (strictly verified source references, never co-occurrence).
7. Cross-revision comparison (added, removed, modified, unchanged categorization).
8. Uploaded-document components filtering and integration.
"""

import unittest
import os
import json
from typing import Dict, Any, List

import rag_engine as re


class TestComponentExplorer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.components = re.load_components_metadata()
        cls.assertTrue(len(cls.components) > 0, "components_metadata.json must contain records")

    # ------------------------------------------------------------------------
    # 1. Component Filtering by Entity Type
    # ------------------------------------------------------------------------
    def test_01_component_filtering_by_entity_type(self):
        """1. Verify entity type filtering defaults to physical, assemblies & subsystems."""
        # Default filtering
        default_filtered = re.filter_components(self.components)
        self.assertGreater(len(default_filtered), 0)
        for c in default_filtered:
            self.assertIn(c.get("entity_type"), ("PHYSICAL_COMPONENT", "ASSEMBLY", "SUBSYSTEM"))

        # Explicit entity type filter
        assemblies = re.filter_components(self.components, entity_type_filter="ASSEMBLY")
        self.assertGreater(len(assemblies), 0)
        self.assertTrue(all(c.get("entity_type") == "ASSEMBLY" for c in assemblies))

        params = re.filter_components(self.components, entity_type_filter="TECHNICAL_PARAMETER")
        self.assertGreater(len(params), 0)
        self.assertTrue(all(c.get("entity_type") == "TECHNICAL_PARAMETER" for c in params))

        tools = re.filter_components(self.components, entity_type_filter="TOOL_OR_INSTRUMENT")
        self.assertGreater(len(tools), 0)
        self.assertTrue(all(c.get("entity_type") == "TOOL_OR_INSTRUMENT" for c in tools))

        # Unfiltered mode
        unfiltered = re.filter_components(self.components, entity_type_filter="All Extracted Entities (Unfiltered)")
        self.assertEqual(len(unfiltered), len(self.components))

    # ------------------------------------------------------------------------
    # 2. Revision Filtering (V1, V2, All)
    # ------------------------------------------------------------------------
    def test_02_revision_filtering_v1_v2_all(self):
        """2. Verify revision filtering isolates V1, V2, and All components deterministically."""
        # V1 Only
        v1_filtered = re.filter_components(self.components, revision_filter="V1 (Baseline / Archival)", entity_type_filter="All")
        self.assertGreater(len(v1_filtered), 0)
        self.assertTrue(all(re.is_v1_component(c) for c in v1_filtered))
        self.assertFalse(any(re.is_v2_component(c) for c in v1_filtered))

        # V2 Only
        v2_filtered = re.filter_components(self.components, revision_filter="V2 (Active / Revised)", entity_type_filter="All")
        self.assertGreater(len(v2_filtered), 0)
        self.assertTrue(all(re.is_v2_component(c) for c in v2_filtered))
        self.assertFalse(any(re.is_v1_component(c) for c in v2_filtered))

        # All Revisions
        all_filtered = re.filter_components(self.components, revision_filter="All Revisions", entity_type_filter="All")
        self.assertEqual(len(all_filtered), len(self.components))
        self.assertEqual(len(v1_filtered) + len(v2_filtered), len(all_filtered))

    # ------------------------------------------------------------------------
    # 3. Component Filtering by Document and Subsystem
    # ------------------------------------------------------------------------
    def test_03_component_filtering_by_document_and_subsystem(self):
        """3. Verify filtering by specific document, subsystem, and keyword search."""
        # By Document
        doc_name = "HVF_SOP_1_Hull_Welding_v2.pdf"
        doc_filtered = re.filter_components(self.components, doc_filter=doc_name, entity_type_filter="All")
        self.assertGreater(len(doc_filtered), 0)
        for c in doc_filtered:
            c_doc = c.get("source_filename") or c.get("filename", "")
            self.assertEqual(c_doc, doc_name)

        # By Subsystem
        sub_name = "Armoured Hull Structure"
        sub_filtered = re.filter_components(self.components, subsystem_filter=sub_name, entity_type_filter="All")
        self.assertGreater(len(sub_filtered), 0)
        for c in sub_filtered:
            self.assertIn(sub_name.lower(), [str(c.get("subsystem", "")).lower(), str(c.get("parent_subsystem", "")).lower()])

        # By Search Keyword
        kw_filtered = re.filter_components(self.components, search_keyword="bearing", entity_type_filter="All")
        self.assertGreater(len(kw_filtered), 0)
        for c in kw_filtered:
            self.assertTrue(any("bearing" in str(v).lower() for v in c.values()))

    # ------------------------------------------------------------------------
    # 4. Component Detail Rendering Completeness
    # ------------------------------------------------------------------------
    def test_04_component_detail_rendering_completeness(self):
        """4. Verify format_component_detail produces complete engineering cards."""
        # Select verified physical component
        hull_plate = next((c for c in self.components if c.get("component_name") == "Lower Hull Plate"), None)
        self.assertIsNotNone(hull_plate)

        detail = re.format_component_detail(hull_plate)
        self.assertEqual(detail["component_name"], "Lower Hull Plate")
        self.assertEqual(detail["entity_type"], "PHYSICAL_COMPONENT")
        self.assertTrue(detail["has_simple_description"])
        self.assertIn("Heavy armoured base plate", detail["simple_description"])
        self.assertTrue(detail["has_primary_function"])
        self.assertIn("floor protection", detail["primary_function"])
        self.assertTrue(detail["has_associated_subsystem"])
        self.assertEqual(detail["associated_subsystem"], "Armoured Hull Structure")
        self.assertEqual(detail["evidence_status"], "DIRECTLY_STATED")
        self.assertTrue(detail["has_relationships"])
        self.assertGreater(len(detail["relationships"]), 0)
        self.assertEqual(detail["filename"], "HVF_SOP_1_Hull_Welding.pdf")
        self.assertEqual(detail["page_number"], 2)
        self.assertIn("SECTION 1.0", detail["section"])
        self.assertTrue(len(detail["supporting_passage"]) > 0)

    # ------------------------------------------------------------------------
    # 5. Missing Descriptions and Graceful Fallback Handling
    # ------------------------------------------------------------------------
    def test_05_missing_descriptions_and_fallback_handling(self):
        """5. Verify graceful fallbacks when descriptions or functions are missing."""
        mock_incomplete = {
            "component_id": "CMP_MOCK_01",
            "component_name": "Unspecified Sensor Wire",
            "entity_type": "PHYSICAL_COMPONENT",
            "simple_description": None,
            "primary_function": "",
            "parent_subsystem": None,
            "subsystem": None,
            "relationships": [],
            "source_filename": "HVF_SOP_MOCK.pdf",
            "page_number": 3,
            "section_reference": "SECTION 2.1",
            "supporting_source_passage": ""
        }

        detail = re.format_component_detail(mock_incomplete)
        self.assertFalse(detail["has_simple_description"])
        self.assertEqual(detail["simple_description"], "No simplified explanation documented in SOP source.")
        self.assertFalse(detail["has_primary_function"])
        self.assertEqual(detail["primary_function"], "No primary vehicle function explicitly documented in SOP source.")
        self.assertFalse(detail["has_associated_subsystem"])
        self.assertEqual(detail["associated_subsystem"], "No parent assembly or subsystem explicitly assigned in SOP source.")
        self.assertFalse(detail["has_relationships"])
        self.assertEqual(len(detail["relationships"]), 0)

    # ------------------------------------------------------------------------
    # 6. Evidence Display and Verbatim Provenance
    # ------------------------------------------------------------------------
    def test_06_evidence_display_and_provenance(self):
        """6. Verify all formatted components retain verifiable source provenance."""
        sample_records = self.components[:20]
        for c in sample_records:
            detail = re.format_component_detail(c)
            self.assertTrue(len(detail["filename"]) > 0, "Filename must not be empty")
            self.assertTrue(detail["page_number"] is not None, "Page number must be defined")
            self.assertTrue(len(detail["section"]) > 0, "Section reference must not be empty")
            self.assertIn(detail["evidence_status"], ("DIRECTLY_STATED", "SUPPORTED_BY_PASSAGE", "INFERRED", "UNCERTAIN"))

    # ------------------------------------------------------------------------
    # 7. Relationship Validation (Never Co-Occurrence)
    # ------------------------------------------------------------------------
    def test_07_relationship_validation_and_no_cooccurrence(self):
        """7. Verify relationships contain explicit source references and no co-occurrence inference."""
        comps_with_rels = [c for c in self.components if c.get("relationships")]
        self.assertGreater(len(comps_with_rels), 0)

        for c in comps_with_rels:
            detail = re.format_component_detail(c)
            for r in detail["relationships"]:
                self.assertEqual(r["source_component"], detail["component_name"])
                self.assertTrue(len(r["target_component"]) > 0)
                self.assertTrue(len(r["relationship_type"]) > 0)
                # Must have explicit source reference
                self.assertTrue(len(r["source_reference"]) > 0, f"Relationship missing source_reference: {r}")
                # Must cite section or explicit evidence
                self.assertTrue(
                    any(tok in r["source_reference"].lower() for tok in ["section", "fitted", "welded", "locked", "splined", "connected", "mounted", "coupled"]),
                    f"Relationship citation lacks evidence context: {r['source_reference']}"
                )

    # ------------------------------------------------------------------------
    # 8. Cross-Revision Comparison Categorization (V1 vs V2)
    # ------------------------------------------------------------------------
    def test_08_v1_v2_comparison_categorization(self):
        """8. Verify compare_component_revisions accurately segments added, removed, modified, and unchanged."""
        comp_diff = re.compare_component_revisions(self.components)
        summary = comp_diff["summary"]

        # Verify summary keys
        self.assertIn("total_compared", summary)
        self.assertIn("added_count", summary)
        self.assertIn("removed_count", summary)
        self.assertIn("modified_count", summary)
        self.assertIn("unchanged_count", summary)

        # Mathematical consistency
        self.assertEqual(
            summary["total_compared"],
            summary["added_count"] + summary["removed_count"] + summary["modified_count"] + summary["unchanged_count"]
        )

        # Added components must be in V2 and not V1
        for c in comp_diff["added"]:
            self.assertTrue(re.is_v2_component(c))

        # Removed components must be in V1 and not V2
        for c in comp_diff["removed"]:
            self.assertTrue(re.is_v1_component(c))

        # Modified components must have diffs
        for m in comp_diff["modified"]:
            self.assertGreater(len(m["diffs"]), 0)
            self.assertTrue(re.is_v1_component(m["v1"]))
            self.assertTrue(re.is_v2_component(m["v2"]))

        # Unchanged components must have matching names
        for u in comp_diff["unchanged"]:
            self.assertEqual(u["v1"]["component_name"], u["v2"]["component_name"])

        # Domain-filtered comparison (Hull Welding)
        hull_diff = re.compare_component_revisions(self.components, sop_filter="HVF_SOP_1_Hull_Welding")
        self.assertGreater(hull_diff["summary"]["total_compared"], 0)
        self.assertGreater(hull_diff["summary"]["added_count"], 0)
        self.assertGreater(hull_diff["summary"]["removed_count"], 0)

    # ------------------------------------------------------------------------
    # 9. Uploaded Document Components Integration
    # ------------------------------------------------------------------------
    def test_09_uploaded_document_components_integration(self):
        """9. Verify uploaded document component records are properly filtered and formatted."""
        uploaded_comp = {
            "component_id": "CMP_UPLOADED_TEST_01",
            "component_name": "Auxiliary Power Unit Fuel Actuator",
            "entity_type": "PHYSICAL_COMPONENT",
            "subsystem": "Auxiliary Power Subsystem",
            "parent_subsystem": "Auxiliary Power Subsystem",
            "simple_description": "Electro-hydraulic actuator controlling auxiliary fuel valve position.",
            "primary_function": "Regulates fuel metering to the auxiliary power turbine.",
            "source_filename": "HVF_SOP_UPLOADED_TEST.pdf",
            "filename": "HVF_SOP_UPLOADED_TEST.pdf",
            "document_id": "HVF/AVNL/SOP-MBT/UPLOADED-999",
            "revision": "Rev 1.0 (Uploaded)",
            "is_v1": False,
            "is_v2": True,
            "page_number": 4,
            "section_reference": "SECTION 4.2 — AUXILIARY FUEL ACTUATION",
            "evidence_status": "DIRECTLY_STATED",
            "is_uncertain": False,
            "supporting_source_passage": "SECTION 4.2: Electro-hydraulic actuator controlling auxiliary fuel valve position."
        }

        augmented_corpus = self.components + [uploaded_comp]

        # Filter by uploaded document
        filtered = re.filter_components(augmented_corpus, doc_filter="HVF_SOP_UPLOADED_TEST.pdf", entity_type_filter="All")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["component_name"], "Auxiliary Power Unit Fuel Actuator")

        # Format detail for uploaded component
        detail = re.format_component_detail(filtered[0])
        self.assertEqual(detail["filename"], "HVF_SOP_UPLOADED_TEST.pdf")
        self.assertTrue(detail["has_simple_description"])
        self.assertTrue(detail["has_primary_function"])
        self.assertEqual(detail["evidence_status"], "DIRECTLY_STATED")


if __name__ == "__main__":
    unittest.main()
