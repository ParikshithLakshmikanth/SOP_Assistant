import sys
import os
import unittest
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

test_files = [
    "tests.test_rag_evaluator",
    "tests.test_frontend_assessment_lifecycle",
    "tests.test_chat_timing",
    "tests.test_cancellation_and_definitions",
    "tests.test_mini_phase6_reliability",
    "tests.test_integrated_experience",
    "tests.test_component_explorer",
    "tests.test_retrieval_fixes",
    "tests.test_component_rag",
    "tests.test_component_quality",
    "tests.test_revision_preference",
    "tests.test_compact_evidence",
    "tests.test_smooth_streaming",
    "tests.test_auto_scroll",
    "tests.test_phase7_offline_operation",
    "tests.test_phase7_persistence",
    "tests.test_phase7_revision_impact",
    "tests.test_phase7_upload_lifecycle"
]

def run_regression_suite():
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    collected_by_module = {}
    total_collected = 0

    for mod_name in test_files:
        try:
            mod_suite = loader.loadTestsFromName(mod_name)
            count = mod_suite.countTestCases()
            collected_by_module[mod_name] = count
            total_collected += count
            suite.addTests(mod_suite)
        except Exception as e:
            print(f"FAILED TO LOAD {mod_name}: {e}")

    print("==================================================================")
    print("REGRESSION TEST SUITE INVENTORY:")
    print("==================================================================")
    for mod_name, count in collected_by_module.items():
        print(f"  {mod_name}: {count} tests")
    print(f"TOTAL TESTS COLLECTED: {total_collected}")
    print("==================================================================")

    runner = unittest.TextTestRunner(verbosity=2)
    t0 = time.time()
    result = runner.run(suite)
    duration = time.time() - t0

    print("\n==================================================================")
    print("REGRESSION EXECUTION SUMMARY:")
    print("==================================================================")
    print(f"Total Collected: {total_collected}")
    print(f"Total Run:       {result.testsRun}")
    print(f"Passed:          {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failed:          {len(result.failures)}")
    print(f"Errors:          {len(result.errors)}")
    print(f"Skipped:         {len(result.skipped)}")
    print(f"Duration:        {duration:.2f}s")
    print("==================================================================")

    if result.wasSuccessful():
        print("ALL TESTS PASSED SUCCESSFULLY! (100% OK)")
        return 0
    else:
        print("SOME TESTS FAILED.")
        return 1

if __name__ == "__main__":
    sys.exit(run_regression_suite())

