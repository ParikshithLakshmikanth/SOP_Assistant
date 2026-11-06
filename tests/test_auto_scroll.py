#!/usr/bin/env python3
"""
tests/test_auto_scroll.py - Verification for Phase 1: Continuous Chat Auto-Scrolling.

Verifies:
1. Auto-scroll trigger present during active streaming.
2. Auto-scroll trigger absent after normal completion.
3. Auto-scroll trigger absent after cancellation.
4. AutoScrollController pause condition on user upward scroll (threshold = 80px).
5. Typing cursor and fade-in animations remain functional alongside auto-scroll.
6. CSS definitions for auto-scroll and animations present in app.py.
7. Long response accumulates correctly without token drops or order corruption.
8. Error handling stops auto-scroll cleanly.
9. Database persistence is clean of scroll triggers and raw HTML tags.
10. Graceful degradation: zero layout impact if JS is restricted.
"""

import os
import sys
import unittest
import tempfile
from typing import List, Dict, Any

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import app
from app import (
    AutoScrollController,
    AUTOSCROLL_TRIGGER_HTML,
    SmoothStreamAccumulator,
    render_streaming_display,
)
import database as db


class TestAutoScroll(unittest.TestCase):
    """Test suite for Phase 1 Continuous Chat Auto-Scrolling."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_scroll.db")
        db.init_database(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_01_auto_scroll_trigger_present_during_active_streaming(self):
        """Verify auto-scroll trigger and anchor are emitted during active streaming."""
        acc = SmoothStreamAccumulator(enable_auto_scroll=True)
        self.assertFalse(acc.scroll_controller.is_active)

        acc.add_token("First step: ")
        acc.add_token("Inspect the hull joint.")
        display_html = acc.get_display_html(is_active=True)

        self.assertTrue(acc.scroll_controller.is_active)
        self.assertIn("sop-autoscroll-anchor", display_html)
        self.assertIn("sop-autoscroll-trigger", display_html)
        self.assertIn("sop-chat-bottom-anchor", display_html)
        self.assertIn("onload=", display_html)

    def test_02_auto_scroll_trigger_absent_after_normal_completion(self):
        """Verify auto-scroll trigger and typing cursor are absent after normal completion."""
        acc = SmoothStreamAccumulator(enable_auto_scroll=True)
        acc.add_token("Hull welding benchmark is 450 MPa.")
        _ = acc.get_display_html(is_active=True)
        self.assertTrue(acc.scroll_controller.is_active)

        final_text = acc.get_final_text(interrupted=False)
        self.assertFalse(acc.scroll_controller.is_active)
        self.assertNotIn("sop-autoscroll-anchor", final_text)
        self.assertNotIn("sop-autoscroll-trigger", final_text)
        self.assertNotIn("typing-cursor", final_text)
        self.assertNotIn("<img", final_text)
        self.assertEqual(final_text, "Hull welding benchmark is 450 MPa.")

    def test_03_auto_scroll_trigger_absent_after_cancellation(self):
        """Verify auto-scroll stops and clean text is emitted upon user cancellation."""
        acc = SmoothStreamAccumulator(enable_auto_scroll=True)
        acc.add_token("Partial generation text before stop button clicked...")
        _ = acc.get_display_html(is_active=True)

        final_text = acc.get_final_text(interrupted=True)
        self.assertFalse(acc.scroll_controller.is_active)
        self.assertNotIn("sop-autoscroll-anchor", final_text)
        self.assertNotIn("sop-autoscroll-trigger", final_text)
        self.assertNotIn("typing-cursor", final_text)
        self.assertIn("*[Generation stopped by user]*", final_text)

    def test_04_auto_scroll_controller_pause_condition(self):
        """Verify user upward scroll detection logic with 80px distance threshold."""
        controller = AutoScrollController()
        # Near bottom: dist <= 80px -> should NOT pause
        self.assertFalse(controller.should_pause(0.0))
        self.assertFalse(controller.should_pause(50.0))
        self.assertFalse(controller.should_pause(80.0))

        # Scrolled up: dist > 80px -> should pause auto-scrolling
        self.assertTrue(controller.should_pause(80.1))
        self.assertTrue(controller.should_pause(150.0))
        self.assertTrue(controller.should_pause(1000.0))

        # Custom threshold testing
        self.assertFalse(controller.should_pause(90.0, threshold=100.0))
        self.assertTrue(controller.should_pause(105.0, threshold=100.0))

    def test_05_typing_cursor_and_fade_in_remain_functional(self):
        """Verify typing cursor and fade-in animations coexist seamlessly with auto-scroll."""
        acc = SmoothStreamAccumulator(min_batch_chars=5, enable_auto_scroll=True)
        acc.add_token("Phase A ")
        acc.add_token("completed successfully.")
        display_html = acc.get_display_html(is_active=True)

        # Both typing cursor and auto-scroll trigger must be present
        self.assertIn('<span class="typing-cursor"></span>', display_html)
        self.assertIn("sop-autoscroll-trigger", display_html)
        self.assertIn("streaming-fade-in", display_html)

        # When generation ends, both are removed
        completed_html = acc.get_display_html(is_active=False)
        self.assertNotIn("typing-cursor", completed_html)
        self.assertNotIn("sop-autoscroll-trigger", completed_html)

    def test_06_css_definitions_present_in_app(self):
        """Verify app CSS contains required selectors for auto-scroll and animations."""
        app_path = os.path.join(PROJECT_ROOT, "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            app_code = f.read()

        self.assertIn(".sop-autoscroll-anchor", app_code)
        self.assertIn(".sop-autoscroll-trigger", app_code)
        self.assertIn(".typing-cursor", app_code)
        self.assertIn(".streaming-fade-in", app_code)
        self.assertIn("@media (prefers-reduced-motion: reduce)", app_code)

    def test_07_long_response_rendering_accumulates_properly(self):
        """Verify long responses accumulating over many tokens preserve all content and scroll trigger."""
        acc = SmoothStreamAccumulator(min_batch_chars=8, enable_auto_scroll=True)
        tokens = [
            "Section 4.1: Technical Specification.\n\n",
            "1. Tensile Strength: 450 MPa minimum across all joint classes.\n",
            "2. Yield Strength: 320 MPa nominal benchmark.\n",
            "3. Inspection Frequency: 100% radiographic inspection of primary hull joints.\n",
            "4. Heat Input: Controlled between 1.2 kJ/mm and 1.8 kJ/mm.\n",
            "5. Post-weld Heat Treatment: Maintain at 600°C for 2 hours per HVF_SOP_1.\n",
            "6. Non-Destructive Testing: Performed per Rev 5.0 acceptance criteria.\n"
        ]
        for tok in tokens:
            acc.add_token(tok)
            display = acc.get_display_html(is_active=True)
            self.assertIn("sop-autoscroll-trigger", display)

        final_output = acc.get_final_text(interrupted=False)
        expected_full = "".join(tokens).strip()
        self.assertEqual(final_output, expected_full)
        self.assertNotIn("sop-autoscroll", final_output)

    def test_08_error_handling_stops_auto_scroll(self):
        """Verify that when an error occurs during inference, auto-scroll is cleanly stopped."""
        acc = SmoothStreamAccumulator(enable_auto_scroll=True)
        acc.add_token("Initial partial answer before error...")
        _ = acc.get_display_html(is_active=True)
        self.assertTrue(acc.scroll_controller.is_active)

        # Simulate exception in streaming loop
        try:
            raise ConnectionResetError("Model socket unexpectedly closed")
        except Exception as e:
            acc.full_response += f"\n\n*[Error: {str(e)}]*"
            acc.scroll_controller.stop()

        self.assertFalse(acc.scroll_controller.is_active)
        final = acc.get_final_text(interrupted=True)
        self.assertNotIn("sop-autoscroll-trigger", final)
        self.assertIn("Model socket unexpectedly closed", final)

    def test_09_database_persistence_clean_of_scroll_html(self):
        """Verify persisted SQLite conversation messages contain no auto-scroll HTML or artifacts."""
        conv = db.create_conversation("Auto Scroll DB Test", db_path=self.db_path)
        cid = conv["conversation_id"] if isinstance(conv, dict) else conv
        acc = SmoothStreamAccumulator(enable_auto_scroll=True)
        acc.add_token("Persisted content without HTML tags.")
        final_clean = acc.get_final_text(interrupted=False)

        citations = [{"pdf_name": "HVF_SOP_1_Hull_Welding_v2.pdf", "page": 4, "rev": "Rev 5.0"}]
        mid = db.save_message(
            conversation_id=cid,
            role="assistant",
            content=final_clean,
            citations=citations,
            is_cancelled=False,
            db_path=self.db_path
        )

        messages = db.get_conversation_messages(cid, db_path=self.db_path)
        self.assertEqual(len(messages), 1)
        saved_msg = messages[0]
        self.assertEqual(saved_msg["content"], "Persisted content without HTML tags.")
        self.assertNotIn("sop-autoscroll", saved_msg["content"])
        self.assertNotIn("<img", saved_msg["content"])
        self.assertEqual(len(saved_msg["citations"]), 1)

    def test_10_graceful_degradation_without_js(self):
        """Verify that trigger HTML has display:none and zero dimensions, preventing visual distortion."""
        self.assertIn('style="display:none;"', AUTOSCROLL_TRIGGER_HTML)
        self.assertIn('alt=""', AUTOSCROLL_TRIGGER_HTML)
        self.assertTrue(AUTOSCROLL_TRIGGER_HTML.startswith('<span class="sop-autoscroll-anchor"'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
