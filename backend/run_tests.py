"""
Test runner for MedShield v2.
Runs all tests and generates coverage report.
"""

import sys
import pytest


def main():
    """Run all tests with coverage."""
    args = [
        "tests/",
        "-v",
        "--tb=short",
        "--cov=.",
        "--cov-report=html",
        "--cov-report=term-missing",
        "-W", "ignore::DeprecationWarning"
    ]
    
    # Add any command line arguments
    args.extend(sys.argv[1:])
    
    # Run pytest
    exit_code = pytest.main(args)
    
    if exit_code == 0:
        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED!")
        print("=" * 70)
        print("\nCoverage report generated in htmlcov/index.html")
    else:
        print("\n" + "=" * 70)
        print("❌ SOME TESTS FAILED")
        print("=" * 70)
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
