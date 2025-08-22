"""Test framework reporting components."""

from .coverage_matrix import CoverageMatrixGenerator
from .models import (
    CoverageMatrix,
    RequirementCoverage,
    CapabilityCoverage,
    TestSuiteCoverage,
    CoverageGap,
)

__all__ = [
    "CoverageMatrixGenerator",
    "CoverageMatrix",
    "RequirementCoverage", 
    "CapabilityCoverage",
    "TestSuiteCoverage",
    "CoverageGap",
]