#!/usr/bin/env python3
"""
Root entrypoint for TestRevisionPreference test suite.
Delegates to tests/test_revision_preference.py.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tests.test_revision_preference import TestRevisionPreference

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestRevisionPreference)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

