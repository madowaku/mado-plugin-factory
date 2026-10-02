"""MADO Plugin Factory."""

from .behavior import run_behavior_canary
from .capture import normalize_host_capture
from .bundle import compile_submission_bundle
from .evals import compile_submission_evals, validate_submission_evals
from .extensions import compile_extension_capabilities
from .freshness import run_verification_freshness
from .host import run_host_replay
from .manifest import compile_manifest, validate_manifest
from .negative import run_negative_contract
from .orchestrator import run_extension_verification
from .promotion import compile_verification_promotion, run_verification_promotion
from .marketplace import (
    compile_marketplace_bridge,
    validate_marketplace_catalog,
    verify_marketplace_install,
)
from .patch import apply_extension_patch, compile_extension_patch
from .runtime import run_extension_runtime_smoke
from .scanner import scan_candidate
from .scaffold import compile_extension_scaffold

__all__ = [
    "compile_extension_capabilities",
    "normalize_host_capture",
    "run_behavior_canary",
    "run_negative_contract",
    "compile_extension_scaffold",
    "compile_extension_patch",
    "run_extension_runtime_smoke",
    "run_host_replay",
    "run_extension_verification",
    "run_verification_freshness",
    "run_verification_promotion",
    "compile_verification_promotion",
    "apply_extension_patch",
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
__version__ = "1.6.0"
