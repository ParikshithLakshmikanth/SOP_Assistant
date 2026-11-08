#!/usr/bin/env python3
"""
Test Suite: test_navigation_paths.py
====================================
Comprehensive verification of all dashboard and sidebar navigation flows in app.py.
Ensures zero StreamlitWidgetAlreadyInstantiatedError or duplicate widget keys.
"""

import os
import sys
import unittest
from streamlit.testing.v1 import AppTest

# Ensure repository root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

APP_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app.py"))

class TestAppNavigation(unittest.TestCase):
    """Verifies that all Streamlit navigation actions transition state safely without errors."""

    def setUp(self):
        self.at = AppTest.from_file(APP_PATH, default_timeout=30)
        self.at.run()
        self.assertEqual(len(self.at.exception), 0, f"Startup exceptions: {self.at.exception}")

    # ------------------------------------------------------------------------
    # 1. Dashboard Launch Buttons
    # ------------------------------------------------------------------------

    def test_01_dashboard_to_chat(self):
        """Path 1: Dashboard -> Technical Consultation Chat via dash_launch_chat button."""
        self.assertEqual(self.at.session_state["app_mode_radio"], "📊 Executive Dashboard & Telemetry")
        btn = self.at.button(key="dash_launch_chat")
        self.assertIsNotNone(btn, "dash_launch_chat button not found")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on dash_launch_chat: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "💬 Technical Consultation Chat")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "💬 Technical Consultation Chat")

    def test_02_dashboard_to_component_explorer(self):
        """Path 2: Dashboard -> Component Explorer via dash_launch_comp button."""
        btn = self.at.button(key="dash_launch_comp")
        self.assertIsNotNone(btn, "dash_launch_comp button not found")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on dash_launch_comp: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "🧩 Visual & Tabular Component Explorer")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "🧩 Visual & Tabular Component Explorer")

    def test_03_dashboard_to_revision_comparison(self):
        """Path 3: Dashboard -> SOP Revision Comparison via dash_launch_diff button."""
        btn = self.at.button(key="dash_launch_diff")
        self.assertIsNotNone(btn, "dash_launch_diff button not found")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on dash_launch_diff: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "⚖️ SOP Revision Comparison Engine")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "⚖️ SOP Revision Comparison Engine")

    def test_04_dashboard_to_impact_analysis(self):
        """Path 4: Dashboard -> Cross-Document Impact Analysis via dash_launch_impact button."""
        btn = self.at.button(key="dash_launch_impact")
        self.assertIsNotNone(btn, "dash_launch_impact button not found")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on dash_launch_impact: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "🔗 Cross-Document Impact Analysis")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "🔗 Cross-Document Impact Analysis")

    def test_05_dashboard_to_upload(self):
        """Path 5: Dashboard -> Upload SOP via dash_launch_upload button."""
        btn = self.at.button(key="dash_launch_upload")
        self.assertIsNotNone(btn, "dash_launch_upload button not found")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on dash_launch_upload: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "📥 Ingest & Manage SOP Documents")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "📥 Ingest & Manage SOP Documents")

    # ------------------------------------------------------------------------
    # 2. Sidebar Navigation Buttons
    # ------------------------------------------------------------------------

    def test_06_sidebar_to_dashboard(self):
        """Path 6: Sidebar -> Dashboard via nav_btn_dash button."""
        # First switch to chat
        self.at.radio(key="app_mode_radio").set_value("💬 Technical Consultation Chat").run()
        self.assertEqual(self.at.session_state["app_mode_radio"], "💬 Technical Consultation Chat")
        
        # Click sidebar dashboard button
        btn = self.at.button(key="nav_btn_dash")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on nav_btn_dash: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "📊 Executive Dashboard & Telemetry")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "📊 Executive Dashboard & Telemetry")

    def test_07_sidebar_to_chat(self):
        """Path 7: Sidebar -> Chatbot via nav_btn_chat button."""
        btn = self.at.button(key="nav_btn_chat")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on nav_btn_chat: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "💬 Technical Consultation Chat")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "💬 Technical Consultation Chat")

    def test_08_sidebar_to_component_explorer(self):
        """Path 8: Sidebar -> Component Explorer via nav_btn_comp button."""
        btn = self.at.button(key="nav_btn_comp")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on nav_btn_comp: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "🧩 Visual & Tabular Component Explorer")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "🧩 Visual & Tabular Component Explorer")

    def test_09_sidebar_to_revision_comparison(self):
        """Path 9: Sidebar -> Revision Comparison via nav_btn_diff button."""
        btn = self.at.button(key="nav_btn_diff")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on nav_btn_diff: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "⚖️ SOP Revision Comparison Engine")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "⚖️ SOP Revision Comparison Engine")

    def test_10_sidebar_to_impact_map(self):
        """Path 10: Sidebar -> Impact Map via nav_btn_impact button."""
        btn = self.at.button(key="nav_btn_impact")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on nav_btn_impact: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "🔗 Cross-Document Impact Analysis")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "🔗 Cross-Document Impact Analysis")

    def test_11_sidebar_to_upload(self):
        """Path 11: Sidebar -> Upload SOP via nav_btn_upload button."""
        btn = self.at.button(key="nav_btn_upload")
        btn.click().run()
        self.assertEqual(len(self.at.exception), 0, f"Exceptions on nav_btn_upload: {self.at.exception}")
        self.assertEqual(self.at.session_state["app_mode_radio"], "📥 Ingest & Manage SOP Documents")
        self.assertEqual(self.at.radio(key="app_mode_radio").value, "📥 Ingest & Manage SOP Documents")

    # ------------------------------------------------------------------------
    # 3. Direct Radio Selection for All 6 Operating Modes
    # ------------------------------------------------------------------------

    def test_12_radio_selection_each_operating_mode(self):
        """Path 12: Direct selection of each operating mode on st.radio."""
        modes = [
            "💬 Technical Consultation Chat",
            "🧩 Visual & Tabular Component Explorer",
            "⚖️ SOP Revision Comparison Engine",
            "🔗 Cross-Document Impact Analysis",
            "📥 Ingest & Manage SOP Documents",
            "📊 Executive Dashboard & Telemetry"
        ]
        for target_mode in modes:
            radio = self.at.radio(key="app_mode_radio")
            radio.set_value(target_mode).run()
            self.assertEqual(len(self.at.exception), 0, f"Exceptions selecting {target_mode}: {self.at.exception}")
            self.assertEqual(self.at.session_state["app_mode_radio"], target_mode)
            self.assertEqual(self.at.radio(key="app_mode_radio").value, target_mode)

    # ------------------------------------------------------------------------
    # 4. Cross-Module Component Explorer Callbacks
    # ------------------------------------------------------------------------

    def test_13_component_explorer_ask_ai_callback(self):
        """Path 13: Component Explorer -> Ask AI about component callback logic."""
        import streamlit as st
        from app import ask_ai_component_callback
        fake_detail = {
            "component_id": "test_comp_1",
            "component_name": "Turret Ring Plinth",
            "entity_type": "PHYSICAL_COMPONENT",
            "filename": "HVF_SOP_2_Turret_Integration.pdf",
            "revision": "v1.0",
            "section": "Section 3.1",
            "page_number": 2,
            "associated_subsystem": "Turret Mount System"
        }
        st.session_state["app_mode_radio"] = "🧩 Visual & Tabular Component Explorer"
        ask_ai_component_callback(fake_detail, "V1 (Baseline / Archival)")
        self.assertEqual(st.session_state["app_mode_radio"], "💬 Technical Consultation Chat")
        self.assertIn("Turret Ring Plinth", st.session_state.get("pending_chat_prompt", ""))
        self.assertEqual(st.session_state.get("revision_preference"), "V1 Only (Archival Baseline SOPs)")

    def test_14_navigate_to_mode_with_kwargs(self):
        """Path 14: navigate_to_mode callback sets mode and kwargs cleanly."""
        import streamlit as st
        from app import navigate_to_mode
        st.session_state["app_mode_radio"] = "📊 Executive Dashboard & Telemetry"
        navigate_to_mode(
            "🧩 Visual & Tabular Component Explorer",
            target_nav_component="Laser Rangefinder Unit",
            comp_doc_sel="HVF_SOP_5_Gun_Calibration.pdf"
        )
        self.assertEqual(st.session_state["app_mode_radio"], "🧩 Visual & Tabular Component Explorer")
        self.assertEqual(st.session_state["target_nav_component"], "Laser Rangefinder Unit")
        self.assertEqual(st.session_state["comp_doc_sel"], "HVF_SOP_5_Gun_Calibration.pdf")


if __name__ == "__main__":
    unittest.main()
