import os
import shutil
import tempfile
import unittest
from typing import Dict, Any, List

import pymupdf

import document_processor as dp
import rag_engine as re_mod


class TestComponentQuality(unittest.TestCase):
    """
    Mini Phase 2B Quality Control Test Suite:
    Validates entity classification, strict relationship predicates, source provenance,
    deduplication, V1/V2 separation, upload lifecycle decoupling, and persistence.
    """

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix="sop_comp_quality_test_")
        cls.sop_dir = "SOP"
        cls.test_pdf = os.path.join(cls.sop_dir, "HVF_SOP_4_Torsion_Suspension.pdf")
        cls.test_pdf_v2 = os.path.join(cls.sop_dir, "HVF_SOP_4_Torsion_Suspension_v2.pdf")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_physical_component_classification(self):
        """1. Verify physical components are classified as PHYSICAL_COMPONENT."""
        cases = [
            ("Torsion Bar", "High-tensile forged alloy bar running across lower hull."),
            ("Balancer Arm", "Forged suspension swing arm transferring wheel load."),
            ("2A46M 125mm Smoothbore Gun Barrel", "Autofrettaged cannon barrel."),
            ("Drive Sprocket", "Toothed drive wheel meshing with track."),
            ("Lower Hull Plate", "Rolled homogeneous armour plate at hull belly."),
            ("Labyrinth Seal", "Triple-lip journal seal preventing dirt entry.")
        ]
        for name, ctx in cases:
            etype = dp.classify_entity_record(name, ctx)
            self.assertEqual(etype, "PHYSICAL_COMPONENT", f"Failed for {name}: got {etype}")

    def test_02_assembly_classification(self):
        """2. Verify complex assemblies are classified as ASSEMBLY."""
        cases = [
            ("Needle-Bearing Housing", "Cast housing enclosing double-row needle bearings."),
            ("Turret Basket Assembly", "Structural rotating framework beneath turret ring."),
            ("Road Wheel Hub", "Dual road wheel hub with tapered bearings."),
            ("Hydraulic Rotary Damper", "Rotary shock absorber assembly."),
            ("V12 Powerpack Engine", "V-92S2 turbocharged multi-fuel powerpack engine."),
            ("Sponson Box", "Welded over-track side armour box assembly.")
        ]
        for name, ctx in cases:
            etype = dp.classify_entity_record(name, ctx)
            self.assertEqual(etype, "ASSEMBLY", f"Failed for {name}: got {etype}")

    def test_03_tool_vs_component_distinction(self):
        """3. Verify tools and metrology instruments are NOT classified as components."""
        cases = [
            ("Hydraulic Grease Gun", "Pneumatic grease dispensing tool."),
            ("Dial Indicator", "Digital plunger gauge measuring axial runout."),
            ("Torque Wrench", "Dual-drive calibrated tightening wrench."),
            ("Alignment Jig", "Rigid fixture datum jig for hull plate alignment."),
            ("Autocollimator", "Optical alignment instrument for trunnion axis.")
        ]
        for name, ctx in cases:
            etype = dp.classify_entity_record(name, ctx)
            self.assertEqual(etype, "TOOL_OR_INSTRUMENT", f"Failed for {name}: got {etype}")
            self.assertNotEqual(etype, "PHYSICAL_COMPONENT")

    def test_04_parameter_vs_component_distinction(self):
        """4. Verify technical parameters are NOT classified as physical components."""
        cases = [
            ("215 mm Spring Height", "Installed static ride height specification."),
            ("Balancer Arm Radial Play", "Permissible bearing play limit of 0.08 mm."),
            ("Peak Torquing Limit", "Maximum tightening torque of 480 Nm."),
            ("Backlash Clearance", "Permissible gear tooth gap 0.15 - 0.25 mm."),
            ("Hull Co-Planarity TIR", "Total indicator reading across plinth circle.")
        ]
        for name, ctx in cases:
            etype = dp.classify_entity_record(name, ctx)
            self.assertEqual(etype, "TECHNICAL_PARAMETER", f"Failed for {name}: got {etype}")
            self.assertNotEqual(etype, "PHYSICAL_COMPONENT")

    def test_05_material_classification(self):
        """5. Verify materials and consumables are classified as MATERIAL."""
        cases = [
            ("Ceramic-Epoxy Coating", "High-hardness protective anti-wear coating."),
            ("Synthetic Ester Hydraulic Oil", "Aeroshell Fluid 41 mineral/synthetic hydraulic oil."),
            ("Viton Elastomer", "Fluorocarbon polymer sealing compound."),
            ("Loctite 270", "High-strength anaerobic threadlocking adhesive."),
            ("Argon Shielding Gas", "Welding grade 99.998% pure argon gas.")
        ]
        for name, ctx in cases:
            etype = dp.classify_entity_record(name, ctx)
            self.assertEqual(etype, "MATERIAL", f"Failed for {name}: got {etype}")
            self.assertNotEqual(etype, "PHYSICAL_COMPONENT")

    def test_06_unsupported_relationship_rejection(self):
        """6. Verify unsupported relationships are rejected when no predicate exists."""
        # Unsupported: merely mentioned in proximity without a relational verb
        unsupported_ctx = "The technician placed the torsion bar on the bench next to the hydraulic jack."
        rel_invalid = dp.validate_relationship(
            source_component="Torsion Bar",
            target_component="Hydraulic Jack",
            relationship_type="CONNECTED_TO",
            source_reference="Section 3.1",
            context_text=unsupported_ctx
        )
        self.assertIsNone(rel_invalid, "Should reject relationship without relational predicate!")

        # Supported: contains explicit predicate "engages directly with"
        supported_ctx = "Torsion bar splines engage directly with the internal splines of the balancer arm."
        rel_valid = dp.validate_relationship(
            source_component="Torsion Bar",
            target_component="Balancer Arm",
            relationship_type="CONNECTED_TO",
            source_reference="Section 3.0",
            context_text=supported_ctx
        )
        self.assertIsNotNone(rel_valid, "Should accept relationship with explicit predicate!")
        self.assertEqual(rel_valid["relationship_type"], "CONNECTED_TO")
        self.assertEqual(rel_valid["target_component"], "Balancer Arm")

    def test_07_component_deduplication(self):
        """7. Verify components extracted within the same document are deduplicated."""
        comps = dp.extract_components_from_document(self.test_pdf)
        keys = [(c["component_name"].strip().lower(), c["page_number"], c.get("entity_type")) for c in comps]
        self.assertEqual(len(keys), len(set(keys)), "Extracted components contain duplicate entries!")

    def test_08_source_provenance(self):
        """8. Verify all extracted components include complete source provenance."""
        comps = dp.extract_components_from_document(self.test_pdf)
        self.assertGreater(len(comps), 0)
        for c in comps:
            self.assertIn("source_filename", c)
            self.assertTrue(bool(c["source_filename"]))
            self.assertIn("document_id", c)
            self.assertTrue(bool(c["document_id"]))
            self.assertIn("revision", c)
            self.assertTrue(bool(c["revision"]))
            self.assertIn("section_reference", c)
            self.assertTrue(bool(c["section_reference"]))
            self.assertIn("page_number", c)
            self.assertIsInstance(c["page_number"], int)
            self.assertGreaterEqual(c["page_number"], 1)

    def test_09_v1_v2_separation(self):
        """9. Verify V1 vs V2 separation: distinct revision flags and filenames."""
        comps_v1 = dp.extract_components_from_document(self.test_pdf)
        comps_v2 = dp.extract_components_from_document(self.test_pdf_v2)

        phy_v1 = [c for c in comps_v1 if c.get("entity_type") in ("PHYSICAL_COMPONENT", "ASSEMBLY")]
        phy_v2 = [c for c in comps_v2 if c.get("entity_type") in ("PHYSICAL_COMPONENT", "ASSEMBLY")]

        self.assertGreater(len(phy_v1), 0)
        self.assertGreater(len(phy_v2), 0)

        for c in phy_v1:
            self.assertTrue(c["is_v1"])
            self.assertFalse(c["is_v2"])
            self.assertIn("HVF_SOP_4_Torsion_Suspension.pdf", c["source_filename"])

        for c in phy_v2:
            self.assertFalse(c["is_v1"])
            self.assertTrue(c["is_v2"])
            self.assertIn("HVF_SOP_4_Torsion_Suspension_v2.pdf", c["source_filename"])

    def test_10_uploaded_pdf_component_extraction(self):
        """10. Verify dynamic component extraction on an uploaded/synthetic PDF."""
        synth_pdf_path = os.path.join(self.temp_dir, "HVF_SOP_99_Auxiliary_Hydraulics.pdf")
        doc = pymupdf.open()
        page = doc.new_page()
        page.insert_text((50, 50), "HVF/AVNL/SOP-MBT/AH-909\nSTANDARD OPERATING PROCEDURE\n", fontsize=14)
        page.insert_text((50, 100), "SECTION 1.0 — AUXILIARY HYDRAULIC VALVE BLOCK\n", fontsize=12)
        page.insert_text((50, 130), "The Hydraulic Accumulator Cylinder is connected to the Solenoid Valve Assembly.\n", fontsize=10)
        page.insert_text((50, 160), "The Swashplate Piston Pump supplies fluid at 180 bar pressure.\n", fontsize=10)
        doc.save(synth_pdf_path)
        doc.close()

        doc_record = dp.process_pdf(synth_pdf_path)
        self.assertEqual(doc_record["status"], "success")
        self.assertEqual(doc_record.get("component_extraction_status"), "success")
        self.assertGreater(doc_record["total_components"], 0)

        # Check that dynamic physical components or assemblies were extracted
        types = [c.get("entity_type") for c in doc_record["components"]]
        self.assertTrue(any(t in ("PHYSICAL_COMPONENT", "ASSEMBLY", "OTHER_REFERENCE") for t in types))

    def test_11_component_metadata_persistence_after_restart(self):
        """11. Verify atomic persistence in components_metadata.json across reload."""
        test_comps = [
            {
                "component_id": "CMP_TEST_01",
                "component_name": "Hydrostatic Test Accumulator",
                "entity_type": "PHYSICAL_COMPONENT",
                "subsystem": "Hydraulic Subsystem",
                "document_id": "DOC/TEST_101",
                "filename": "test_sop.pdf",
                "source_filename": "test_sop.pdf",
                "page_number": 2,
                "section_reference": "SECTION 2.0",
                "is_v1": True,
                "is_v2": False,
                "evidence_status": "DIRECTLY_STATED",
                "relationships": []
            }
        ]
        ok = re_mod.save_components_metadata(test_comps, index_dir=self.temp_dir)
        self.assertTrue(ok)

        # Reload from scratch
        loaded = re_mod.load_components_metadata(index_dir=self.temp_dir)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["component_name"], "Hydrostatic Test Accumulator")
        self.assertEqual(loaded[0]["entity_type"], "PHYSICAL_COMPONENT")

    def test_12_failed_component_extraction_with_successful_faiss_ingestion(self):
        """12. Verify that if component extraction fails, chunk indexing still succeeds."""
        synth_pdf_path = os.path.join(self.temp_dir, "HVF_SOP_CORRUPT_COMP.pdf")
        doc = pymupdf.open()
        p = doc.new_page()
        p.insert_text((50, 50), "HVF/AVNL/SOP-MBT/ERR-01\nValid content for chunking.\nSECTION 1.0\nText for embedding.", fontsize=11)
        doc.save(synth_pdf_path)
        doc.close()

        # Monkey-patch extract_components_from_document to simulate extraction crash
        orig_extract = dp.extract_components_from_document
        try:
            def mock_fail(pdf_path, pages=None, metadata=None):
                raise RuntimeError("Simulated visual extraction parser timeout")

            dp.extract_components_from_document = mock_fail

            doc_record = dp.process_pdf(synth_pdf_path)
            # PDF processing and chunking must succeed
            self.assertEqual(doc_record["status"], "success")
            self.assertGreater(doc_record["total_chunks"], 0)
            # Component status reflects error gracefully
            self.assertEqual(doc_record["total_components"], 0)
            self.assertIn("error: Simulated visual extraction parser timeout", doc_record["component_extraction_status"])

            # Verify FAISS indexing succeeds despite component failure
            summary = re_mod.index_chunks(doc_record["chunks"], index_dir=self.temp_dir, replace_existing=True)
            self.assertGreater(summary["indexed_chunks"], 0)
        finally:
            dp.extract_components_from_document = orig_extract

    def test_13_safe_component_extraction_retry(self):
        """13. Verify safe retry of component extraction without modifying FAISS index."""
        synth_pdf_path = os.path.join(self.temp_dir, "HVF_SOP_RETRY_TEST.pdf")
        doc = pymupdf.open()
        p = doc.new_page()
        p.insert_text((50, 50), "HVF/AVNL/SOP-MBT/RT-707\nSECTION 1.0\nTorsion Bar Assembly and Balancer Arm.\n", fontsize=11)
        doc.save(synth_pdf_path)
        doc.close()

        # Initial ingestion with empty components
        re_mod.save_document_components(
            document_id="HVF/AVNL/SOP-MBT/RT-707",
            filename="HVF_SOP_RETRY_TEST.pdf",
            components=[],
            index_dir=self.temp_dir
        )
        before_comps = re_mod.get_document_components("HVF/AVNL/SOP-MBT/RT-707", index_dir=self.temp_dir)
        self.assertEqual(len(before_comps), 0)

        # Retry extraction
        res = re_mod.retry_component_extraction(
            pdf_path=synth_pdf_path,
            document_id="HVF/AVNL/SOP-MBT/RT-707",
            filename="HVF_SOP_RETRY_TEST.pdf",
            index_dir=self.temp_dir
        )
        self.assertEqual(res["status"], "success")
        self.assertGreater(res["extracted_count"], 0)

        after_comps = re_mod.get_document_components("HVF/AVNL/SOP-MBT/RT-707", index_dir=self.temp_dir)
        self.assertEqual(len(after_comps), res["extracted_count"])

    def test_14_regression_existing_component_explorer(self):
        """14. Verify existing Component Explorer search and document filtering work."""
        # Search all physical components
        results = re_mod.search_components("Torsion", entity_type="PHYSICAL_COMPONENT")
        self.assertGreater(len(results), 0)
        self.assertTrue(all(r.get("entity_type") == "PHYSICAL_COMPONENT" for r in results))

        # Search assemblies only
        asm_results = re_mod.search_components("Housing", entity_type="ASSEMBLY")
        self.assertGreater(len(asm_results), 0)
        self.assertTrue(all(r.get("entity_type") == "ASSEMBLY" for r in asm_results))

        # Document-specific lookup
        doc_comps = re_mod.get_document_components("HVF_SOP_4_Torsion_Suspension.pdf")
        self.assertGreater(len(doc_comps), 0)


if __name__ == "__main__":
    unittest.main()

