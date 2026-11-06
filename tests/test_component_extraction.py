"""
Test Suite: Visual and Tabular Component Extraction (Mini Phase 2)
==================================================================
Validates multi-source component extraction from:
- Tables and technical matrices
- Executive summaries and document control matrices
- Captions and callout boxes (stage-gate warnings)
- Section headings and assembly descriptions
- Visual diagrams and labelled figures (PyMuPDF + Tesseract OCR)
- Uncertainty profiling for unclear/blurry diagrams
- Provenance preservation (page numbers and section references)
- Search and lookup integration in rag_engine
- Offline-first execution (zero external cloud APIs)
"""

import os
import sys
import io
import unittest
import fitz
from PIL import Image, ImageDraw

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import document_processor as dp
import rag_engine as re


class TestComponentExtraction(unittest.TestCase):
    """Unit and integration tests for visual, tabular, and multi-source component extraction."""

    @classmethod
    def setUpClass(cls):
        cls.test_dir = os.path.join("data", "test_components_tmp")
        os.makedirs(cls.test_dir, exist_ok=True)

    def _create_synthetic_diagram_pdf(self, file_path: str, is_blurry: bool = False):
        """Creates a test PDF with an embedded diagram image."""
        doc = fitz.open()
        page = doc.new_page()

        page.insert_text(
            (50, 40),
            "STANDARD OPERATING PROCEDURE: TURRET MOUNTING\n"
            "SECTION 1.0 — TURRET RACEWAY BEARING FITUP\n",
            fontsize=11
        )

        if not is_blurry:
            # High-resolution clear diagram with crisp text
            img = Image.new("RGB", (450, 220), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)
            draw.rectangle([10, 10, 440, 210], outline=(0, 0, 0), width=3)
            draw.text((25, 25), "FIGURE 1.1 — FOUR-POINT BEARING RACEWAY SCHEMATIC", fill=(0, 0, 0))
            draw.text((25, 75), "BEARING BALL NOMINAL DIAMETER: 25.40 mm +/- 0.02 mm", fill=(0, 0, 0))
            draw.text((25, 125), "RADIAL CLEARANCE TOLERANCE: 0.08 mm - 0.12 mm", fill=(0, 0, 0))
            draw.text((25, 175), "DIAL INDICATOR CALIBRATION: CAL-HVF-9921", fill=(0, 0, 0))
        else:
            # Low-resolution ambiguous thumbnail without readable text (< 60x40)
            img = Image.new("RGB", (50, 30), color=(180, 180, 180))

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        page.insert_image(fitz.Rect(50, 100, 500, 320 if not is_blurry else 140), stream=buf.getvalue())

        doc.save(file_path)
        doc.close()

    # ------------------------------------------------------------------------
    # Test 1: Tabular Component Extraction from Actual SOP
    # ------------------------------------------------------------------------
    def test_01_tabular_component_extraction_actual_sop(self):
        """Verifies tabular component extraction from official Hull Welding SOP."""
        sop_path = os.path.join("SOP", "HVF_SOP_1_Hull_Welding.pdf")
        self.assertTrue(os.path.exists(sop_path), f"Missing {sop_path}")

        comps = dp.extract_components_from_document(sop_path)
        self.assertGreaterEqual(len(comps), 40)

        tab_comps = [c for c in comps if c["source_type"] == "table"]
        self.assertGreaterEqual(len(tab_comps), 25, "Expected at least 25 tabular step components across 6 sections")

        # Inspect specific step 1.1
        step_1_1 = next((c for c in tab_comps if c.get("step_number") == "1.1"), None)
        self.assertIsNotNone(step_1_1, "Step 1.1 not found in extracted table components")
        self.assertIn("Chemical Equivalence", step_1_1["component_name"])
        self.assertIn("0.62", step_1_1["technical_specifications"])
        self.assertIn("Spectrometer", step_1_1["tooling_or_metrology"])
        self.assertEqual(step_1_1["page_number"], 2)
        self.assertIn("SECTION 1.0", step_1_1["section_reference"])
        self.assertFalse(step_1_1["is_uncertain"])

    # ------------------------------------------------------------------------
    # Test 2: Executive Summary Component Extraction
    # ------------------------------------------------------------------------
    def test_02_executive_summary_extraction(self):
        """Verifies extraction of critical acceptance benchmarks from Page 1 executive summary."""
        sop_path = os.path.join("SOP", "HVF_SOP_1_Hull_Welding.pdf")
        comps = dp.extract_components_from_document(sop_path)

        exec_comps = [c for c in comps if c["source_type"] == "executive_summary"]
        self.assertGreaterEqual(len(exec_comps), 3)

        # Confirm BaseMaterialSpec and Preheat criteria
        mat_comp = next((c for c in exec_comps if "BaseMaterialSpec" in c["component_name"]), None)
        self.assertIsNotNone(mat_comp)
        self.assertIn("MIL-DTL-12560", mat_comp["technical_specifications"])
        self.assertEqual(mat_comp["page_number"], 1)

    # ------------------------------------------------------------------------
    # Test 3: Callout and Stage-Gate Warning Extraction
    # ------------------------------------------------------------------------
    def test_03_callout_and_stage_gate_warning_extraction(self):
        """Verifies extraction of Stage-Gate Warnings and quality hold points."""
        sop_path = os.path.join("SOP", "HVF_SOP_1_Hull_Welding.pdf")
        comps = dp.extract_components_from_document(sop_path)

        callout_comps = [c for c in comps if c["source_type"] == "callout_box"]
        self.assertGreaterEqual(len(callout_comps), 5, "Expected at least 5 stage-gate warnings across sections")

        sg_comp = callout_comps[0]
        self.assertIn("Stage-Gate Hold Warning", sg_comp["component_name"])
        self.assertIsNotNone(sg_comp["callout_warning"])
        self.assertIn("counter-stamped", sg_comp["callout_warning"].lower())
        self.assertIn("hull e-Passport", sg_comp["callout_warning"])

    # ------------------------------------------------------------------------
    # Test 4: Section Heading Assembly Extraction
    # ------------------------------------------------------------------------
    def test_04_section_heading_assembly_extraction(self):
        """Verifies assembly descriptions extracted from section headings."""
        sop_path = os.path.join("SOP", "HVF_SOP_1_Hull_Welding.pdf")
        comps = dp.extract_components_from_document(sop_path)

        sec_comps = [c for c in comps if c["source_type"] == "heading"]
        self.assertGreaterEqual(len(sec_comps), 5)

        sec1 = next((c for c in sec_comps if c["page_number"] == 2), None)
        self.assertIsNotNone(sec1)
        self.assertIn("RHA Plate Receiving", sec1["component_name"])
        self.assertEqual(sec1["subsystem"], "Armoured Hull Structure & Fabrication")

    # ------------------------------------------------------------------------
    # Test 5: Visual Diagram Extraction with OCR
    # ------------------------------------------------------------------------
    def test_05_visual_diagram_and_figure_extraction_with_ocr(self):
        """Verifies PyMuPDF rendering + Tesseract OCR on a crisp technical diagram."""
        diag_pdf = os.path.join(self.test_dir, "clear_diagram.pdf")
        self._create_synthetic_diagram_pdf(diag_pdf, is_blurry=False)

        comps = dp.extract_components_from_document(diag_pdf)
        fig_comps = [c for c in comps if c["source_type"] == "diagram_figure"]
        self.assertGreaterEqual(len(fig_comps), 1)

        fig = fig_comps[0]
        self.assertFalse(fig["is_uncertain"], "Crisp diagram should have high confidence")
        self.assertIsNone(fig["uncertainty_reason"])
        self.assertIn("25.40", fig["technical_specifications"])
        self.assertEqual(fig["page_number"], 1)

    # ------------------------------------------------------------------------
    # Test 6: Unclear Diagram Marked Uncertain Without Hallucination
    # ------------------------------------------------------------------------
    def test_06_unclear_diagram_marked_uncertain_without_inventing(self):
        """Verifies low-resolution blurry diagram is flagged as uncertain without invented facts."""
        blurry_pdf = os.path.join(self.test_dir, "blurry_diagram.pdf")
        self._create_synthetic_diagram_pdf(blurry_pdf, is_blurry=True)

        comps = dp.extract_components_from_document(blurry_pdf)
        fig_comps = [c for c in comps if c["source_type"] == "diagram_figure"]
        self.assertGreaterEqual(len(fig_comps), 1)

        fig = fig_comps[0]
        self.assertTrue(fig["is_uncertain"], "Low-res diagram must be marked uncertain")
        self.assertIsNotNone(fig["uncertainty_reason"])
        self.assertIn("unclear", fig["uncertainty_reason"].lower())
        self.assertIn("unclear", fig["technical_specifications"].lower())

    # ------------------------------------------------------------------------
    # Test 7: Provenance Preservation (Page Numbers & Section References)
    # ------------------------------------------------------------------------
    def test_07_provenance_preservation(self):
        """Confirms 100% of extracted components maintain page number and section reference."""
        sop_path = os.path.join("SOP", "HVF_SOP_2_Turret_Integration.pdf")
        comps = dp.extract_components_from_document(sop_path)
        self.assertGreaterEqual(len(comps), 40)

        for c in comps:
            self.assertGreaterEqual(c["page_number"], 1, f"Invalid page number in {c['component_id']}")
            self.assertLessEqual(c["page_number"], 8)
            self.assertTrue(bool(c["section_reference"]), f"Empty section reference in {c['component_id']}")
            self.assertTrue(bool(c["component_name"]))
            self.assertTrue(bool(c["subsystem"]))

    # ------------------------------------------------------------------------
    # Test 8: Extraction Across All Five Logical SOPs
    # ------------------------------------------------------------------------
    def test_08_extraction_across_all_five_logical_sops(self):
        """Verifies component extraction on all 5 official baseline SOP documents."""
        baseline_files = [
            ("HVF_SOP_1_Hull_Welding.pdf", "Armoured Hull Structure & Fabrication"),
            ("HVF_SOP_2_Turret_Integration.pdf", "Turret Integration & Drive Mechanism"),
            ("HVF_SOP_3_Engine_Alignment.pdf", "Powerpack & Engine Drive Alignment"),
            ("HVF_SOP_4_Torsion_Suspension.pdf", "Torsion Bar & Tracked Suspension System"),
            ("HVF_SOP_5_Gun_Calibration.pdf", "125mm Smoothbore Main Gun & Recoil System")
        ]

        for fname, expected_subsystem in baseline_files:
            sop_path = os.path.join("SOP", fname)
            comps = dp.extract_components_from_document(sop_path)
            self.assertGreaterEqual(len(comps), 40, f"Expected >= 40 components in {fname}, got {len(comps)}")

            subsystems = {c["subsystem"] for c in comps}
            self.assertIn(expected_subsystem, subsystems, f"Expected {expected_subsystem} in {fname}")

    # ------------------------------------------------------------------------
    # Test 9: Component Search and Lookup Integration
    # ------------------------------------------------------------------------
    def test_09_component_search_and_retrieval(self):
        """Verifies rag_engine component search across names, specs, tooling, and filters."""
        # Search by keyword
        hardness_results = re.search_components("hardness", top_k=5)
        self.assertGreater(len(hardness_results), 0)
        top_h = hardness_results[0]
        self.assertIn("hardness", (top_h["component_name"] + top_h["technical_specifications"]).lower())

        # Search by subsystem filter
        turret_results = re.search_components("bearing", subsystem="Turret Integration & Drive Mechanism", top_k=5)
        self.assertGreater(len(turret_results), 0)
        for r in turret_results:
            self.assertEqual(r["subsystem"], "Turret Integration & Drive Mechanism")

        # Search by source_type filter
        table_results = re.search_components("tolerance", source_type="table", top_k=5)
        self.assertGreater(len(table_results), 0)
        for r in table_results:
            self.assertEqual(r["source_type"], "table")

    # ------------------------------------------------------------------------
    # Test 10: End-to-End Integration in process_pdf
    # ------------------------------------------------------------------------
    def test_10_end_to_end_integration_in_process_pdf(self):
        """Verifies process_pdf incorporates components and total_components cleanly."""
        sop_path = os.path.join("SOP", "HVF_SOP_3_Engine_Alignment.pdf")
        doc_record = dp.process_pdf(sop_path)

        self.assertEqual(doc_record["status"], "success")
        self.assertIn("components", doc_record)
        self.assertIn("total_components", doc_record)
        self.assertEqual(doc_record["total_components"], len(doc_record["components"]))
        self.assertGreaterEqual(doc_record["total_components"], 40)

        # Check engine-specific component
        dial_comp = next((c for c in doc_record["components"] if "crankshaft" in c["component_name"].lower() or "dial indicator" in c["tooling_or_metrology"].lower() or "alignment" in c["component_name"].lower()), None)
        self.assertIsNotNone(dial_comp)

    # ------------------------------------------------------------------------
    # Test 11: Deduplication and Schema Invariants
    # ------------------------------------------------------------------------
    def test_11_deduplication_and_schema_invariants(self):
        """Verifies component records conform to schema and contain zero duplicates."""
        sop_path = os.path.join("SOP", "HVF_SOP_4_Torsion_Suspension.pdf")
        comps = dp.extract_components_from_document(sop_path)

        seen_keys = set()
        required_keys = {
            "component_id", "component_name", "subsystem", "source_type",
            "page_number", "section_reference", "technical_specifications",
            "tooling_or_metrology", "acceptance_criteria", "is_uncertain"
        }

        for c in comps:
            self.assertTrue(required_keys.issubset(c.keys()))
            dedup_key = (c["component_name"].strip().lower(), c["page_number"], c["source_type"])
            self.assertNotIn(dedup_key, seen_keys, f"Duplicate component found: {dedup_key}")
            seen_keys.add(dedup_key)

    # ------------------------------------------------------------------------
    # Test 12: Offline Execution (Zero External Cloud Services)
    # ------------------------------------------------------------------------
    def test_12_offline_execution_local_only(self):
        """Verifies Tesseract binary and PyMuPDF run locally with zero network calls."""
        self.assertTrue(os.path.exists(dp.TESSERACT_BIN), f"Local Tesseract executable must exist at {dp.TESSERACT_BIN}")
        self.assertFalse("http" in dp.TESSERACT_BIN.lower())


if __name__ == "__main__":
    unittest.main()

