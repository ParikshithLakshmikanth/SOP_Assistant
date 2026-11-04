#!/usr/bin/env python3
"""
Root entrypoint for TestSmoothStreamingResponse test suite.
Delegates to tests/test_smooth_streaming.py.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tests.test_smooth_streaming import TestSmoothStreamingResponse

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSmoothStreamingResponse)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

