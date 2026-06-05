"""Export each feature manifest as canonical JSON — the bytes that get signed.

Run before cosign signing (see .github/workflows/sign.yml) so each manifest's
on-disk form matches exactly what gateway.signing verifies at runtime.
"""

from __future__ import annotations

import os
import sys

from gateway.samples import build_dev_catalog_and_invoker
from gateway.signing import canonical_bytes


def main(out_dir: str = "manifests") -> None:
    catalog, _ = build_dev_catalog_and_invoker()
    os.makedirs(out_dir, exist_ok=True)
    for feature in catalog.list():
        path = os.path.join(out_dir, f"{feature.manifest.name}.json")
        with open(path, "wb") as fh:
            fh.write(canonical_bytes(feature.manifest.model_dump(mode="json")))
        print("wrote", path)


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
