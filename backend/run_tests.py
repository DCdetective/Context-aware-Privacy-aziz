#!/usr/bin/env python3
"""
Comprehensive test runner for MedShield.
Runs all test suites and generates a report.
"""

import subprocess
import sys


def run_test_suite(name, path, markers=None):
    """Run a test suite and return success status."""
    print("\n" + "=" * 70)
    print(f"Running: {name}")
    print("=" * 70)
    
    cmd = ["pytest", path, "-v", "-s"]
    if markers:
        cmd.extend(["-m", markers])
    
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def main():
    """Run all test suites."""
    print("=" * 70)
    print("MedShield - Comprehensive Test Suite")
    print("=" * 70)
    
    # Resolve paths relative to this file, so the runner works from any CWD.
    base_dir = __file__.rsplit("/", 1)[0] if "/" in __file__ else __file__.rsplit("\\", 1)[0]
    tests_dir = f"{base_dir}/tests"

    test_suites = [
        ("Setup Tests", f"{tests_dir}/test_setup.py"),
        ("Identity Vault Tests", f"{tests_dir}/test_identity_vault.py"),
        ("Semantic Store Tests", f"{tests_dir}/test_semantic_store.py"),
        ("Gatekeeper Agent Tests", f"{tests_dir}/test_gatekeeper.py"),
        ("Coordinator Agent Tests", f"{tests_dir}/test_coordinator.py"),
        ("Worker Agent Tests", f"{tests_dir}/test_worker.py"),
        ("API Routes Tests", f"{tests_dir}/test_api_routes.py"),
        ("End-to-End Tests", f"{tests_dir}/test_e2e_workflow.py"),
        ("Privacy Compliance Tests", f"{tests_dir}/test_privacy_compliance.py"),
        ("Performance Tests", f"{tests_dir}/test_performance.py"),
    ]
    
    results = {}
    
    for name, path in test_suites:
        try:
            success = run_test_suite(name, path)
            results[name] = "✅ PASSED" if success else "❌ FAILED"
        except Exception as e:
            results[name] = f"❌ ERROR: {str(e)}"
    
    # Print summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    for name, result in results.items():
        print(f"{name:.<50} {result}")
    
    # Overall result
    failed_count = sum(1 for r in results.values() if "FAILED" in r or "ERROR" in r)
    
    print("=" * 70)
    if failed_count == 0:
        print("🎉 ALL TESTS PASSED!")
        print("=" * 70)
        return 0
    else:
        print(f"⚠️  {failed_count} TEST SUITE(S) FAILED")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
