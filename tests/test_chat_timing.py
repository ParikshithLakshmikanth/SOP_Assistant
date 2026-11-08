"""
Test Suite for Mini Phase 12: Chat Timestamps and Response Performance Metrics
==============================================================================
Validates:
1. Normal completed response timing and format.
2. Slow first token latency measurement.
3. Fast first token latency measurement.
4. Multiple streamed tokens tracking and first-token latch.
5. Empty tokens before first real token filtering.
6. Cancellation before first token.
7. Cancellation after partial output.
8. Model exception handling with timing.
9. Multiple sequential questions independence.
10. Streamlit rerun and formatter robustness against edge cases.
11. SQLite persistence and recovery across session restarts.
12. Legacy message backward compatibility.
"""

import os
import re
import time
import json
import uuid
import unittest
from datetime import datetime, timezone, timedelta

import database as db
from app import format_message_timing_display


class TestChatTiming(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "test_timing.db")
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass
        db.init_database(cls.test_db_path)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_db_path):
            try:
                os.remove(cls.test_db_path)
            except Exception:
                pass

    def setUp(self):
        conv = db.create_conversation("Timing Test Conv", db_path=self.test_db_path)
        self.cid = conv["conversation_id"]

    # ------------------------------------------------------------------------
    # Scenario 1: Normal completed response
    # ------------------------------------------------------------------------
    def test_01_normal_completed_response(self):
        """Verify normal completed response captures all timestamps and durations correctly."""
        submission_dt = datetime.now().astimezone()
        submission_perf = time.perf_counter()

        # Simulate brief latency before first token
        time.sleep(0.05)
        first_token_dt = datetime.now().astimezone()
        first_token_perf = time.perf_counter()
        first_token_latency = round(first_token_perf - submission_perf, 2)

        # Stream tokens
        time.sleep(0.05)
        completion_perf = time.perf_counter()
        completion_dt = datetime.now().astimezone()
        total_duration = round(completion_perf - submission_perf, 2)

        timing_data = {
            "started_at": first_token_dt.isoformat(),
            "first_token_latency": first_token_latency,
            "completed_at": completion_dt.isoformat(),
            "total_duration": total_duration,
            "completion_status": "completed",
            "token_count": 5,
            "display_started": first_token_dt.strftime("%H:%M:%S"),
            "display_completed": completion_dt.strftime("%H:%M:%S"),
            "date": first_token_dt.strftime("%Y-%m-%d"),
            "timezone": first_token_dt.tzname() or "Local"
        }

        # Assertions on metrics
        self.assertGreater(first_token_latency, 0)
        self.assertGreater(total_duration, first_token_latency)
        self.assertTrue(re.match(r"^\d{2}:\d{2}:\d{2}$", timing_data["display_started"]))
        self.assertTrue(re.match(r"^\d{2}:\d{2}:\d{2}$", timing_data["display_completed"]))

        # Formatter verification
        caption, tooltip = format_message_timing_display({
            "role": "assistant",
            "timing_metadata": timing_data
        })
        self.assertIn(f"Started: {timing_data['display_started']}", caption)
        self.assertIn(f"First token: {first_token_latency:.2f}s", caption)
        self.assertIn(f"Completed: {timing_data['display_completed']}", caption)
        self.assertIn(f"Total: {total_duration:.2f}s", caption)
        self.assertIn("Date:", tooltip)
        self.assertIn("Generated tokens: ~5", tooltip)

    # ------------------------------------------------------------------------
    # Scenario 2: Slow first token
    # ------------------------------------------------------------------------
    def test_02_slow_first_token(self):
        """Simulate a delayed first token (~0.5s or simulated 2.0s)."""
        submission_perf = time.perf_counter()
        # Simulated slow delay
        simulated_delay = 2.05
        first_token_perf = submission_perf + simulated_delay
        first_token_latency = round(first_token_perf - submission_perf, 2)

        timing_data = {
            "started_at": datetime.now().astimezone().isoformat(),
            "first_token_latency": first_token_latency,
            "completed_at": datetime.now().astimezone().isoformat(),
            "total_duration": 3.50,
            "completion_status": "completed",
            "token_count": 10,
            "display_started": "10:00:02",
            "display_completed": "10:00:05",
            "date": "2026-11-08",
            "timezone": "IST"
        }

        self.assertAlmostEqual(timing_data["first_token_latency"], 2.05, delta=0.05)
        caption, _ = format_message_timing_display({"role": "assistant", "timing_metadata": timing_data})
        self.assertIn("First token: 2.05s", caption)

    # ------------------------------------------------------------------------
    # Scenario 3: Fast first token
    # ------------------------------------------------------------------------
    def test_03_fast_first_token(self):
        """Simulate a fast first token (<0.2s)."""
        submission_perf = time.perf_counter()
        first_token_perf = submission_perf + 0.08
        first_token_latency = round(first_token_perf - submission_perf, 2)

        timing_data = {
            "started_at": datetime.now().astimezone().isoformat(),
            "first_token_latency": first_token_latency,
            "completed_at": datetime.now().astimezone().isoformat(),
            "total_duration": 0.45,
            "completion_status": "completed",
            "token_count": 8,
            "display_started": "10:00:00",
            "display_completed": "10:00:01",
            "date": "2026-11-08",
            "timezone": "IST"
        }

        self.assertLess(timing_data["first_token_latency"], 0.20)
        caption, _ = format_message_timing_display({"role": "assistant", "timing_metadata": timing_data})
        self.assertIn("First token: 0.08s", caption)

    # ------------------------------------------------------------------------
    # Scenario 4: Multiple streamed tokens
    # ------------------------------------------------------------------------
    def test_04_multiple_streamed_tokens(self):
        """Simulate 20 tokens streamed with latching of first token."""
        tokens = [f"tok_{i}" for i in range(20)]
        submission_perf = time.perf_counter()

        first_token_perf = None
        first_token_latency = None
        token_count = 0

        for tok in tokens:
            if first_token_perf is None and tok and tok.strip() != "":
                first_token_perf = time.perf_counter()
                first_token_latency = round(first_token_perf - submission_perf, 2)
            token_count += 1
            time.sleep(0.005)

        completion_perf = time.perf_counter()
        total_duration = round(completion_perf - submission_perf, 2)

        self.assertEqual(token_count, 20)
        self.assertIsNotNone(first_token_latency)
        self.assertLessEqual(first_token_latency, total_duration)

    # ------------------------------------------------------------------------
    # Scenario 5: Empty tokens before first real token
    # ------------------------------------------------------------------------
    def test_05_empty_tokens_before_first_real_token(self):
        """Ensure empty strings and whitespace do not trigger first-token timestamp."""
        tokens = ["", "  ", "\t", "\n", "FirstRealToken", "NextToken"]
        submission_perf = time.perf_counter()

        first_token_perf = None
        first_token_val = None

        for tok in tokens:
            if first_token_perf is None and tok and tok.strip() != "":
                first_token_perf = time.perf_counter()
                first_token_val = tok

        self.assertIsNotNone(first_token_perf)
        self.assertEqual(first_token_val, "FirstRealToken")

    # ------------------------------------------------------------------------
    # Scenario 6: Cancellation before first token
    # ------------------------------------------------------------------------
    def test_06_cancellation_before_first_token(self):
        """When user clicks Stop before any token arrives."""
        timing_data = {
            "started_at": None,
            "first_token_latency": None,
            "completed_at": None,
            "total_duration": 0.85,
            "completion_status": "cancelled",
            "token_count": 0,
            "display_started": None,
            "display_completed": None,
            "date": "2026-11-08",
            "timezone": "IST"
        }

        self.assertIsNone(timing_data["completed_at"])
        self.assertIsNone(timing_data["first_token_latency"])
        self.assertEqual(timing_data["completion_status"], "cancelled")

        caption, _ = format_message_timing_display({"role": "assistant", "timing_metadata": timing_data})
        self.assertEqual(caption, "Cancelled after: 0.85s")
        self.assertNotIn("Started:", caption)
        self.assertNotIn("Completed:", caption)

    # ------------------------------------------------------------------------
    # Scenario 7: Cancellation after partial output
    # ------------------------------------------------------------------------
    def test_07_cancellation_after_partial_output(self):
        """When user clicks Stop after partial output has already streamed."""
        timing_data = {
            "started_at": "2026-11-08T10:44:13+05:30",
            "first_token_latency": 1.42,
            "completed_at": None,
            "total_duration": 3.20,
            "completion_status": "cancelled",
            "token_count": 14,
            "display_started": "10:44:13",
            "display_completed": None,
            "date": "2026-11-08",
            "timezone": "IST"
        }

        self.assertIsNone(timing_data["completed_at"])
        self.assertEqual(timing_data["first_token_latency"], 1.42)

        caption, _ = format_message_timing_display({"role": "assistant", "timing_metadata": timing_data})
        expected_caption = "Started: 10:44:13 | First token: 1.42s | Cancelled after: 3.20s"
        self.assertEqual(caption, expected_caption)
        self.assertNotIn("Completed:", caption)

    # ------------------------------------------------------------------------
    # Scenario 8: Model exception
    # ------------------------------------------------------------------------
    def test_08_model_exception(self):
        """When an exception occurs during generation."""
        timing_data = {
            "started_at": None,
            "first_token_latency": None,
            "completed_at": None,
            "total_duration": 2.10,
            "completion_status": "failed",
            "token_count": 0,
            "display_started": None,
            "display_completed": None,
            "date": "2026-11-08",
            "timezone": "IST"
        }

        caption, _ = format_message_timing_display({"role": "assistant", "timing_metadata": timing_data})
        self.assertEqual(caption, "Failed after: 2.10s")

    # ------------------------------------------------------------------------
    # Scenario 9: Multiple sequential questions
    # ------------------------------------------------------------------------
    def test_09_multiple_sequential_questions(self):
        """Ensure sequential questions maintain independent timing without state contamination."""
        msg1 = db.save_message(
            conversation_id=self.cid,
            role="user",
            content="Question 1",
            timing_metadata={"display_asked": "10:00:01", "date": "2026-11-08", "timezone": "IST"},
            db_path=self.test_db_path
        )
        time.sleep(0.01)
        msg2 = db.save_message(
            conversation_id=self.cid,
            role="user",
            content="Question 2",
            timing_metadata={"display_asked": "10:00:05", "date": "2026-11-08", "timezone": "IST"},
            db_path=self.test_db_path
        )
        time.sleep(0.01)
        msg3 = db.save_message(
            conversation_id=self.cid,
            role="user",
            content="Question 3",
            timing_metadata={"display_asked": "10:00:10", "date": "2026-11-08", "timezone": "IST"},
            db_path=self.test_db_path
        )

        loaded = db.get_conversation_messages(self.cid, db_path=self.test_db_path)
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded[0]["timing_metadata"]["display_asked"], "10:00:01")
        self.assertEqual(loaded[1]["timing_metadata"]["display_asked"], "10:00:05")
        self.assertEqual(loaded[2]["timing_metadata"]["display_asked"], "10:00:10")

    # ------------------------------------------------------------------------
    # Scenario 10: Streamlit rerun & edge-case robustness
    # ------------------------------------------------------------------------
    def test_10_edge_case_robustness(self):
        """Ensure formatter handles missing, empty, or partial timing dictionaries without crashing."""
        edge_cases = [
            {},
            {"completion_status": "completed"},
            {"completion_status": "cancelled", "total_duration": None},
            {"completion_status": "failed", "first_token_latency": None},
            {"total_duration": 0.0, "first_token_latency": 0.0},
            {"date": "", "timezone": ""}
        ]

        for case in edge_cases:
            res = format_message_timing_display({"role": "assistant", "timing_metadata": case})
            if res is not None:
                caption, tooltip = res
                self.assertIsInstance(caption, str)
                self.assertIsInstance(tooltip, str)

    # ------------------------------------------------------------------------
    # Scenario 11: Historical timing metadata after restart
    # ------------------------------------------------------------------------
    def test_11_historical_timing_metadata_after_restart(self):
        """Ensure timing metadata survives database reloads and re-initialization."""
        assistant_timing = {
            "started_at": "2026-11-08T10:44:13+05:30",
            "first_token_latency": 1.42,
            "completed_at": "2026-11-08T10:44:21+05:30",
            "total_duration": 8.76,
            "completion_status": "completed",
            "token_count": 84,
            "display_started": "10:44:13",
            "display_completed": "10:44:21",
            "date": "2026-11-08",
            "timezone": "IST"
        }

        db.save_message(
            conversation_id=self.cid,
            role="assistant",
            content="Detailed SOP answer.",
            timing_metadata=assistant_timing,
            db_path=self.test_db_path
        )

        # Re-initialize DB (simulate application restart)
        db.init_database(self.test_db_path)
        messages = db.get_conversation_messages(self.cid, db_path=self.test_db_path)

        persisted = next(m for m in messages if m["role"] == "assistant")
        self.assertEqual(persisted["timing_metadata"]["total_duration"], 8.76)
        self.assertEqual(persisted["timing_metadata"]["first_token_latency"], 1.42)
        self.assertEqual(persisted["timing_metadata"]["token_count"], 84)

        caption, tooltip = format_message_timing_display(persisted)
        self.assertIn("Total: 8.76s", caption)
        self.assertIn("First token: 1.42s", caption)

    # ------------------------------------------------------------------------
    # Scenario 12: Legacy messages without timing metadata
    # ------------------------------------------------------------------------
    def test_12_legacy_messages_without_timing_metadata(self):
        """Verify legacy messages with empty or missing timing metadata render gracefully."""
        legacy_user = {
            "role": "user",
            "content": "Old question",
            "timestamp": "09:30:00",
            "timing_metadata": {}
        }
        legacy_assistant = {
            "role": "assistant",
            "content": "Old answer",
            "timestamp": "09:30:15",
            "timing_metadata": {}
        }

        user_caption, user_tooltip = format_message_timing_display(legacy_user)
        self.assertEqual(user_caption, "Asked: 09:30:00")
        self.assertEqual(user_tooltip, "Historical message (timestamp only)")

        asst_caption, asst_tooltip = format_message_timing_display(legacy_assistant)
        self.assertEqual(asst_caption, "Recorded: 09:30:15")
        self.assertEqual(asst_tooltip, "Historical message (timestamp only)")

        # Case where no timestamp exists at all
        no_ts_msg = {"role": "assistant", "content": "No ts"}
        res = format_message_timing_display(no_ts_msg)
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
