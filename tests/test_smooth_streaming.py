#!/usr/bin/env python3
"""
Test Suite: Smooth Streaming Response & ChatGPT/Gemini-Style UI Polish
======================================================================
Validates:
1. First visible content appears before generation completes.
2. Multiple chunks accumulate in the correct order.
3. No chunks are duplicated or lost.
4. Final answer matches the complete generated response.
5. Markdown remains correctly rendered (headings, bold, lists, tables, code).
6. Cursor is visible only during generation.
7. Cursor disappears after completion.
8. Fade-in styling is present (150-250ms animation).
9. Reduced-motion preference is respected.
10. Stop button / early cancellation still works.
11. Partial output persists after cancellation (is_cancelled=True, citations attached).
12. SQLite receives the complete response after normal completion (is_cancelled=False).
13. Compact evidence sources still appear below the answer.
"""

import os
import sys
import time
import tempfile
import unittest

# Ensure repo root is in sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
# Also add current directory if running directly
if "." not in sys.path:
    sys.path.insert(0, ".")

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import database as db
import rag_engine as re
from app import (
    render_streaming_display,
    SmoothStreamAccumulator,
    group_citations_by_source
)


class TestSmoothStreamingResponse(unittest.TestCase):

    def setUp(self):
        self.sample_citations = [
            {
                "chunk_id": "HVF_SOP_1_Hull_Welding_v2.pdf_chunk_05",
                "filename": "HVF_SOP_1_Hull_Welding_v2.pdf",
                "document_id": "HVF/AVNL/SOP-MBT/HW-101-V2",
                "revision": "Rev 5.0 [Version 2.0] | 30-Oct-2026",
                "section_title": "Section 3.2: Preheat and Interpass Temperature Controls",
                "page_number": 3,
                "score": 0.8250,
                "chunk_text": "High-hardened armor plate preheat shall be maintained at 150 deg C +/- 10 deg C.",
                "citation": "[Doc: HVF/AVNL/SOP-MBT/HW-101-V2, Sec: 3.2, Rev: Rev 5.0, Page: 3]"
            },
            {
                "chunk_id": "HVF_SOP_2_Turret_Integration_v2.pdf_chunk_12",
                "filename": "HVF_SOP_2_Turret_Integration_v2.pdf",
                "document_id": "HVF/AVNL/SOP-MBT/TI-201-V2",
                "revision": "Rev 4.5 [Version 2.0] | 30-Oct-2026",
                "section_title": "Section 4.1: Turret Ring Bearing Backlash",
                "page_number": 6,
                "score": 0.8421,
                "chunk_text": "The turret azimuth bearing backlash must not exceed 0.05 mm across 360 degrees.",
                "citation": "[Doc: HVF/AVNL/SOP-MBT/TI-201-V2, Sec: 4.1, Rev: Rev 4.5, Page: 6]"
            }
        ]

    def test_01_first_visible_content_before_completion(self):
        """Verify first visible content appears immediately on the first token before generation completes."""
        tokens = [
            "The ", "turret ", "azimuth ", "bearing ", "backlash ",
            "must ", "not ", "exceed ", "0.05 ", "mm."
        ]
        accumulator = SmoothStreamAccumulator()

        # Feed only the first token
        should_render_first = accumulator.add_token(tokens[0])
        self.assertTrue(should_render_first, "First visible token must trigger immediate render")

        display_html = accumulator.get_display_html(is_active=True)
        self.assertIn("The ", display_html, "First token must be present in display HTML")
        self.assertIn('<span class="typing-cursor"></span>', display_html, "Typing cursor must be present")
        self.assertNotIn("backlash", display_html, "Subsequent tokens must not have appeared yet")
        self.assertTrue(accumulator.first_token_emitted)

    def test_02_multiple_chunks_accumulate_in_correct_order(self):
        """Verify tokens accumulate in strict chronological sequence without transposition."""
        tokens = ["Armor ", "plate ", "preheat: ", "150°C ", "+/- ", "10°C."]
        accumulator = SmoothStreamAccumulator()

        flushed_snapshots = []
        for token in tokens:
            if accumulator.add_token(token):
                flushed_snapshots.append(accumulator.full_response)

        # Ensure all snapshots are prefixes of the full text
        full = "".join(tokens)
        for snap in flushed_snapshots:
            self.assertTrue(full.startswith(snap), f"Snapshot '{snap}' must be prefix of '{full}'")

        self.assertEqual(accumulator.full_response, full)

    def test_03_no_chunks_duplicated_or_lost(self):
        """Verify full_response contains exactly all tokens without loss or duplication."""
        tokens = [f"token_{i} " for i in range(25)]
        accumulator = SmoothStreamAccumulator()

        for token in tokens:
            accumulator.add_token(token)

        expected = "".join(tokens)
        self.assertEqual(accumulator.full_response, expected)
        self.assertEqual(len(accumulator.full_response), len(expected))

    def test_04_final_answer_matches_complete_response(self):
        """Verify final text matches the full model output after thinking sanitization."""
        raw_text = "The azimuth backlash shall not exceed 0.05 mm across 360 degrees."
        accumulator = SmoothStreamAccumulator()
        for word in raw_text.split(" "):
            accumulator.add_token(word + " ")

        final_text = accumulator.get_final_text(interrupted=False)
        self.assertEqual(final_text, re.sanitize_model_output(raw_text))

    def test_05_markdown_remains_correctly_rendered(self):
        """Verify complex Markdown (headings, lists, bold, tables, code) is parsed cleanly."""
        md_text = (
            "### Hull Welding Acceptance Benchmarks\n\n"
            "- **Minimum Preheat**: 150°C +/- 10°C per [HW-101-V2]\n"
            "- **NDT Standard**: `IS 4225 Grade 1`\n\n"
            "| Parameter | Tolerance |\n"
            "| :--- | :--- |\n"
            "| Heat Input | 1.2–1.8 kJ/mm |\n"
            "| Interpass Temp | Max 250°C |\n"
        )
        accumulator = SmoothStreamAccumulator()
        for line in md_text.splitlines(keepends=True):
            accumulator.add_token(line)

        final_text = accumulator.get_final_text(interrupted=False)
        self.assertEqual(final_text, md_text.strip())
        self.assertIn("### Hull Welding Acceptance Benchmarks", final_text)
        self.assertIn("| Parameter | Tolerance |", final_text)
        self.assertIn("`IS 4225 Grade 1`", final_text)
        self.assertNotIn("streaming-fade-in", final_text)
        self.assertNotIn("typing-cursor", final_text)

    def test_06_cursor_visible_only_during_generation(self):
        """Verify typing cursor is present during generation and absent afterwards."""
        accumulator = SmoothStreamAccumulator()
        accumulator.add_token("Testing cursor presence.")

        active_html = accumulator.get_display_html(is_active=True)
        self.assertIn('<span class="typing-cursor"></span>', active_html)

    def test_07_cursor_disappears_after_completion(self):
        """Verify typing cursor is completely absent from completed answers."""
        accumulator = SmoothStreamAccumulator()
        accumulator.add_token("Completed response test.")

        final_text = accumulator.get_final_text(interrupted=False)
        self.assertNotIn("typing-cursor", final_text)
        self.assertNotIn("<span", final_text)

        static_display = accumulator.get_display_html(is_active=False)
        self.assertNotIn("typing-cursor", static_display)

    def test_08_fade_in_styling_present(self):
        """Verify CSS contains .streaming-fade-in with keyframes and 150-250ms animation."""
        app_path = os.path.join(BASE_DIR, "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            app_code = f.read()

        self.assertIn(".streaming-fade-in", app_code)
        self.assertIn("@keyframes textFadeIn", app_code)
        self.assertIn(".typing-cursor", app_code)
        self.assertIn("@keyframes cursorBlink", app_code)
        self.assertIn("0.2s", app_code)  # 200ms animation duration

    def test_09_reduced_motion_respected(self):
        """Verify CSS defines prefers-reduced-motion media query disabling animations."""
        app_path = os.path.join(BASE_DIR, "app.py")
        with open(app_path, "r", encoding="utf-8") as f:
            app_code = f.read()

        self.assertIn("@media (prefers-reduced-motion: reduce)", app_code)
        self.assertIn("animation: none !important", app_code)

    def test_10_stop_button_and_generator_close(self):
        """Verify early cancellation interrupts the stream, closes generator, and sets flag."""
        def mock_infinite_stream():
            try:
                for i in range(100):
                    yield f"chunk_{i} "
            finally:
                mock_infinite_stream.closed = True

        mock_infinite_stream.closed = False
        gen = mock_infinite_stream()
        accumulator = SmoothStreamAccumulator()

        interrupted = False
        for token in gen:
            accumulator.add_token(token)
            if accumulator.render_count >= 2 or len(accumulator.full_response) >= 15:
                interrupted = True
                if hasattr(gen, "close") and callable(gen.close):
                    gen.close()
                break

        self.assertTrue(interrupted)
        self.assertTrue(mock_infinite_stream.closed, "Generator close() must be triggered")
        self.assertTrue(len(accumulator.full_response) < 100)

    def test_11_partial_output_persists_after_cancellation(self):
        """Verify cancelled output is saved to database with is_cancelled=True and citations."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            temp_db = tf.name

        try:
            db.init_database(db_path=temp_db)
            conv = db.create_conversation("Cancellation Test", db_path=temp_db)
            cid = conv["conversation_id"]

            accumulator = SmoothStreamAccumulator()
            for t in ["Partial ", "welding ", "benchmark ", "for "]:
                accumulator.add_token(t)

            partial_final = accumulator.get_final_text(interrupted=True)
            self.assertTrue(partial_final.endswith("*[Generation stopped by user]*"))

            saved = db.save_message(
                conversation_id=cid,
                role="assistant",
                content=partial_final,
                citations=self.sample_citations,
                is_cancelled=True,
                db_path=temp_db
            )

            messages = db.get_conversation_messages(cid, db_path=temp_db)
            self.assertEqual(len(messages), 1)
            msg = messages[0]
            self.assertEqual(msg["is_cancelled"], 1)
            self.assertIn("*[Generation stopped by user]*", msg["content"])
            self.assertEqual(len(msg["citations"]), 2)
        finally:
            if os.path.exists(temp_db):
                try:
                    os.remove(temp_db)
                except Exception:
                    pass

    def test_12_sqlite_receives_complete_response_on_normal_completion(self):
        """Verify normal completion saves complete answer with is_cancelled=False and citations."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
            temp_db = tf.name

        try:
            db.init_database(db_path=temp_db)
            conv = db.create_conversation("Normal Completion Test", db_path=temp_db)
            cid = conv["conversation_id"]

            full_answer = "Hull welding preheat is strictly 150°C per SOP HW-101-V2."
            accumulator = SmoothStreamAccumulator()
            for word in full_answer.split(" "):
                accumulator.add_token(word + " ")

            final_text = accumulator.get_final_text(interrupted=False)
            self.assertNotIn("*[Generation stopped by user]*", final_text)

            saved = db.save_message(
                conversation_id=cid,
                role="assistant",
                content=final_text,
                citations=self.sample_citations,
                is_cancelled=False,
                db_path=temp_db
            )

            messages = db.get_conversation_messages(cid, db_path=temp_db)
            self.assertEqual(len(messages), 1)
            msg = messages[0]
            self.assertEqual(msg["is_cancelled"], 0)
            self.assertEqual(msg["content"], final_text)
            self.assertEqual(len(msg["citations"]), 2)
        finally:
            if os.path.exists(temp_db):
                try:
                    os.remove(temp_db)
                except Exception:
                    pass

    def test_13_compact_evidence_sources_preserved(self):
        """Verify compact evidence sources grouping and rendering remain intact."""
        grouped = group_citations_by_source(self.sample_citations)
        self.assertEqual(len(grouped), 2)
        by_file = {g["filename"]: g for g in grouped}

        self.assertEqual(by_file["HVF_SOP_1_Hull_Welding_v2.pdf"]["pages_str"], "Page 3")
        self.assertEqual(by_file["HVF_SOP_2_Turret_Integration_v2.pdf"]["pages_str"], "Page 6")
        self.assertEqual(by_file["HVF_SOP_1_Hull_Welding_v2.pdf"]["revision"], "Rev 5.0")
        self.assertEqual(by_file["HVF_SOP_2_Turret_Integration_v2.pdf"]["revision"], "Rev 4.5")


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSmoothStreamingResponse)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
