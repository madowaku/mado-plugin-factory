"""MADO Plugin Factory."""

from .manifest import compile_manifest, validate_manifest
from .scanner import scan_candidate

__all__ = ["compile_manifest", "scan_candidate", "validate_manifest"]
__version__ = "0.2.0"
