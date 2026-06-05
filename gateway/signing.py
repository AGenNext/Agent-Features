"""Manifest signing & verification via Sigstore (cosign).

Supply-chain provenance for features. The unit that gets signed is a feature
manifest's **canonical digest** (sha256 over its sorted-key, whitespace-free
JSON), so a signature commits to the exact advertised contract.

Keyless signing happens in CI, where an OIDC identity is available: GitHub
Actions → Fulcio (short-lived cert) → Rekor (transparency log). See
``.github/workflows/sign.yml``. At runtime the gateway recomputes the digest
and, when ``cosign`` and a signature bundle are present, verifies it with
``cosign verify-blob``. Where cosign isn't installed (e.g. this dev sandbox),
verification degrades to an explicit ``unverified`` status rather than failing
closed — the digest and the exact verify command are still returned.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess  # noqa: S404 - used with a fixed argv, no shell
import tempfile
from typing import Any

# Where CI drops `<feature>.bundle` cosign bundles for the gateway to verify.
SIGNATURES_DIR = os.getenv("SIGNATURES_DIR", "signatures")
# The identity a valid signature must carry (set in the deployment env).
SIGNING_IDENTITY = os.getenv("SIGNING_IDENTITY", "")
SIGNING_OIDC_ISSUER = os.getenv("SIGNING_OIDC_ISSUER", "https://token.actions.githubusercontent.com")


def canonical_bytes(manifest: dict[str, Any]) -> bytes:
    """The exact bytes that get signed: canonical JSON of the manifest."""

    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()


def manifest_digest(manifest: dict[str, Any]) -> str:
    """Content digest of a manifest, as ``sha256:<hex>``."""

    return "sha256:" + hashlib.sha256(canonical_bytes(manifest)).hexdigest()


def cosign_available() -> bool:
    return shutil.which("cosign") is not None


def _bundle_path(feature: str) -> str:
    return os.path.join(SIGNATURES_DIR, f"{feature}.bundle")


def verify_command(feature: str) -> str:
    """The exact cosign command a user can run to verify this feature."""

    identity = SIGNING_IDENTITY or "<expected-identity>"
    return (
        "cosign verify-blob "
        f"--bundle {_bundle_path(feature)} "
        f"--certificate-identity {identity} "
        f"--certificate-oidc-issuer {SIGNING_OIDC_ISSUER} <manifest.json>"
    )


def verify(feature: str, manifest: dict[str, Any]) -> dict[str, Any]:
    """Report the signature status of a feature manifest.

    Returns plain data (never raises to the caller): the digest, whether a
    bundle exists, and a verification ``status`` of ``verified`` / ``failed`` /
    ``unverified`` (cosign or bundle absent) / ``unsigned``.
    """

    digest = manifest_digest(manifest)
    base = {
        "feature": feature,
        "digest": digest,
        "algorithm": "sha256",
        "issuer": SIGNING_OIDC_ISSUER,
        "command": verify_command(feature),
    }
    bundle = _bundle_path(feature)
    if not os.path.exists(bundle):
        return {**base, "signed": False, "status": "unsigned"}
    if not cosign_available():
        return {**base, "signed": True, "status": "unverified",
                "reason": "cosign is not available in this environment"}

    with tempfile.NamedTemporaryFile("wb", suffix=".json", delete=False) as fh:
        fh.write(canonical_bytes(manifest))
        blob = fh.name
    try:
        argv = ["cosign", "verify-blob", "--bundle", bundle, "--certificate-oidc-issuer", SIGNING_OIDC_ISSUER]
        if SIGNING_IDENTITY:
            argv += ["--certificate-identity", SIGNING_IDENTITY]
        argv.append(blob)
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)  # noqa: S603
    except (OSError, subprocess.SubprocessError):
        return {**base, "signed": True, "status": "unverified",
                "reason": "cosign verification could not run"}
    finally:
        os.unlink(blob)

    ok = proc.returncode == 0
    return {**base, "signed": True, "status": "verified" if ok else "failed"}
