#!/usr/bin/env python3
"""Runner for Phase 3 Integration Test Suite."""
import os
import sys

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)

from tests.test_phase3_integration import run_tests

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)

