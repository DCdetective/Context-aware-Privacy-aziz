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
    
    test_suites = [
        ("Setup Tests", "tests/test_setup.py"),
        ("Identity Vault Tests", "tests/test_identity_vault.py"),
        ("Semantic Store Tests", "tests/test_semantic_store.py"),
        ("Gatekeeper Agent Tests", "tests/test_gatekeeper.py"),
        ("Coordinator Agent Tests", "tests/test_coordinator.py"),
        ("Worker Agent Tests", "tests/test_worker.py"),
        ("API Routes Tests", "tests/test_api_routes.py"),
        ("End-to-End Tests", "tests/test_e2e_workflow.py"),
        ("Privacy Compliance Tests", "tests/test_privacy_compliance.py"),
        ("Performance Tests", "tests/test_performance.py"),
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
