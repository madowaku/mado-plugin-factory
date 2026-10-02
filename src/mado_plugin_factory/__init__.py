"""MADO Plugin Factory."""

from .bundle import compile_submission_bundle
from .evals import compile_submission_evals, validate_submission_evals
from .extensions import compile_extension_capabilities
from .manifest import compile_manifest, validate_manifest
from .marketplace import (
    compile_marketplace_bridge,
    validate_marketplace_catalog,
    verify_marketplace_install,
)
from .scanner import scan_candidate

__all__ = [
    "compile_extension_capabilities",
    "compile_manifest",
    "compile_marketplace_bridge",
    "compile_submission_bundle",
    "compile_submission_evals",
    "scan_candidate",
    "validate_manifest",
    "validate_marketplace_catalog",
    "validate_submission_evals",
    "verify_marketplace_install",
]
__version__ = "0.6.0"
