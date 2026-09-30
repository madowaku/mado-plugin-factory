"""MADO Plugin Factory."""

from .evals import compile_submission_evals, validate_submission_evals
from .manifest import compile_manifest, validate_manifest
from .scanner import scan_candidate

__all__ = [
    "compile_manifest",
    "compile_submission_evals",
    "scan_candidate",
    "validate_manifest",
    "validate_submission_evals",
]
__version__ = "0.3.0"
