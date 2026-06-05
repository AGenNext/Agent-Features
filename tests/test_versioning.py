"""Unit tests for semver-range matching and version-aware resolution."""

from __future__ import annotations

import pytest

from gateway.catalog import match_version, resolve_feature
from gateway.models import Feature, Manifest


@pytest.mark.parametrize(
    "version,spec,expected",
    [
        # any
        ("1.2.3", "", True),
        ("9.9.9", "*", True),
        ("0.1.0", "latest", True),
        # exact
        ("1.2.3", "1.2.3", True),
        ("1.2.4", "1.2.3", False),
        # caret
        ("1.5.0", "^1.2.0", True),
        ("2.0.0", "^1.2.0", False),
        ("1.1.0", "^1.2.0", False),
        ("0.2.5", "^0.2.0", True),
        ("0.3.0", "^0.2.0", False),
        # tilde
        ("1.2.9", "~1.2.0", True),
        ("1.3.0", "~1.2.0", False),
        ("1.9.0", "~1", True),
        ("2.0.0", "~1", False),
        # comparators
        ("1.2.0", ">=1.2.0", True),
        ("1.1.0", ">=1.2.0", False),
        ("1.0.0", "<2.0.0", True),
        ("2.0.0", "<2.0.0", False),
        ("2.1.0", ">2.0.0", True),
    ],
)
def test_match_version(version, spec, expected):
    assert match_version(version, spec) is expected


def _feat(version: str) -> Feature:
    return Feature(
        manifest=Manifest(name=f"x-{version}", capability="x", vendor="v", version=version)
    )


def test_resolve_picks_newest_matching():
    feats = [_feat("1.0.0"), _feat("1.2.0"), _feat("2.0.0")]
    assert resolve_feature(feats, "x", version="^1.0.0").manifest.version == "1.2.0"
    assert resolve_feature(feats, "x", version="~1.0.0").manifest.version == "1.0.0"
    assert resolve_feature(feats, "x", version="latest").manifest.version == "2.0.0"
    assert resolve_feature(feats, "x", version=">=2.0.0").manifest.version == "2.0.0"
    assert resolve_feature(feats, "x", version="^9.0.0") is None
