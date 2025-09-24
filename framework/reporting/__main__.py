#!/usr/bin/env python3
"""CLI interface for coverage matrix generation.

Usage:
    python -m framework.reporting [options]
"""

import argparse
import logging
import sys
from pathlib import Path

from .coverage_matrix import CoverageMatrixGenerator
from .formatters import HTMLFormatter, JSONFormatter, MarkdownFormatter
from .models import TestSuite

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate unified test coverage report across all test suites"
    )
    
    # Input options
    parser.add_argument(
        "--base-path",
        type=Path,
        default=Path.cwd(),
        help="Base path for test suites (default: current directory)"
    )
    parser.add_argument(
        "--profile",
        help="Profile ID to use for capability analysis"
    )
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="Directory containing test execution evidence JSON files"
    )
    parser.add_argument(
        "--suites",
        nargs="+",
        choices=["xtest", "bdd", "tdd", "pen", "perf", "vuln"],
        default=["xtest", "bdd"],
        help="Test suites to include in the report (default: xtest bdd)"
    )
    
    # Output options
    parser.add_argument(
        "--format",
        choices=["html", "json", "markdown", "all"],
        default="html",
        help="Output format (default: html)"
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file path (default: coverage_report.<format>)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("coverage_reports"),
        help="Output directory for reports (default: coverage_reports)"
    )
    
    # Analysis options
    parser.add_argument(
        "--check-thresholds",
        action="store_true",
        help="Check coverage against thresholds and exit with error if not met"
    )
    parser.add_argument(
        "--min-requirement",
        type=float,
        default=80.0,
        help="Minimum requirement coverage percentage (default: 80)"
    )
    parser.add_argument(
        "--min-suite",
        type=float,
        default=70.0,
        help="Minimum test suite pass rate (default: 70)"
    )
    parser.add_argument(
        "--max-gaps",
        type=int,
        default=10,
        help="Maximum number of high-severity gaps allowed (default: 10)"
    )
    
    # Verbosity
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress non-error output"
    )
    
    args = parser.parse_args()
    
    # Set logging level
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Convert suite names to enums
    suite_map = {
        "xtest": TestSuite.XTEST,
        "bdd": TestSuite.BDD,
        "tdd": TestSuite.TDD,
        "pen": TestSuite.PEN,
    }
    include_suites = [suite_map[s] for s in args.suites if s in suite_map]
    
    try:
        # Generate coverage matrix
        logger.info(f"Generating coverage matrix for suites: {[s.value for s in include_suites]}")
        generator = CoverageMatrixGenerator(args.base_path)
        matrix = generator.generate(
            profile_id=args.profile,
            evidence_dir=args.evidence_dir,
            include_suites=include_suites
        )
        
        # Log summary
        logger.info(f"Discovered {matrix.total_tests} tests across {len(matrix.test_suites)} suites")
        logger.info(f"Requirements covered: {len(matrix.requirements)}")
        logger.info(f"Coverage gaps identified: {len(matrix.gaps)}")
        
        # Generate reports
        formatters = {
            "html": HTMLFormatter(),
            "json": JSONFormatter(),
            "markdown": MarkdownFormatter(),
        }
        
        # Determine which formats to generate
        if args.format == "all":
            formats_to_generate = ["html", "json", "markdown"]
        else:
            formats_to_generate = [args.format]
        
        # Generate each format
        for format_name in formats_to_generate:
            formatter = formatters[format_name]
            
            # Determine output path
            if args.output and len(formats_to_generate) == 1:
                output_path = args.output
            else:
                extension = {
                    "html": "html",
                    "json": "json",
                    "markdown": "md"
                }[format_name]
                output_path = args.output_dir / f"coverage_report.{extension}"
            
            # Save report
            formatter.save(matrix, output_path)
            logger.info(f"Saved {format_name.upper()} report to: {output_path}")
        
        # Check thresholds if requested
        if args.check_thresholds:
            exit_code = 0
            
            # Check requirement coverage
            for req_id, req in matrix.requirements.items():
                if req.coverage_percent < args.min_requirement:
                    logger.error(
                        f"Requirement {req_id} coverage ({req.coverage_percent:.1f}%) "
                        f"below threshold ({args.min_requirement}%)"
                    )
                    exit_code = 1
            
            # Check suite pass rates
            for suite, coverage in matrix.test_suites.items():
                if coverage.pass_rate < args.min_suite:
                    logger.error(
                        f"Suite {suite.value} pass rate ({coverage.pass_rate:.1f}%) "
                        f"below threshold ({args.min_suite}%)"
                    )
                    exit_code = 1
            
            # Check gap count
            high_gaps = len([g for g in matrix.gaps if g.severity == "high"])
            if high_gaps > args.max_gaps:
                logger.error(
                    f"High-severity gaps ({high_gaps}) exceed maximum ({args.max_gaps})"
                )
                exit_code = 1
            
            if exit_code == 0:
                logger.info("✅ All coverage thresholds met")
            else:
                logger.error("❌ Coverage thresholds not met")
            
            return exit_code
        
        # Print summary to console
        if not args.quiet:
            print("\n" + "=" * 60)
            print("COVERAGE SUMMARY")
            print("=" * 60)
            
            # Test suite summary
            print("\nTest Suites:")
            for suite, coverage in matrix.test_suites.items():
                print(f"  {suite.value:8} - {coverage.total_tests:4} tests, "
                      f"{coverage.pass_rate:5.1f}% pass rate")
            
            # Requirement summary
            print("\nRequirements:")
            for req_id in sorted(matrix.requirements.keys()):
                req = matrix.requirements[req_id]
                status = "✅" if req.coverage_percent >= 80 else "⚠️" if req.coverage_percent >= 50 else "❌"
                print(f"  {req_id}: {req.coverage_percent:5.1f}% coverage {status}")
            
            # Gap summary
            if matrix.gaps:
                high_gaps = len([g for g in matrix.gaps if g.severity == "high"])
                medium_gaps = len([g for g in matrix.gaps if g.severity == "medium"])
                print(f"\nCoverage Gaps: {len(matrix.gaps)} total "
                      f"({high_gaps} high, {medium_gaps} medium)")
            else:
                print("\nNo coverage gaps identified! 🎉")
            
            print("=" * 60)
        
        return 0
        
    except Exception as e:
        logger.error(f"Error generating coverage report: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())