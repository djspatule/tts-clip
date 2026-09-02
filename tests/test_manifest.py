"""Manifest contract tests for the Omarchy plugin."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "manifest.json"


@pytest.fixture(scope="module")
def manifest() -> dict[str, object]:
    return json.loads(MANIFEST.read_text())


REQUIRED_TOP = (
    "schemaVersion",
    "id",
    "name",
    "version",
    "author",
    "license",
    "description",
    "kinds",
    "entryPoints",
)

VALID_KINDS = {"bar", "bar-widget", "panel", "overlay", "menu", "service"}


def test_manifest_exists() -> None:
    assert MANIFEST.is_file(), f"{MANIFEST} missing"


def test_manifest_is_valid_json(manifest: dict[str, object]) -> None:
    assert isinstance(manifest, dict)


@pytest.mark.parametrize("field", REQUIRED_TOP)
def test_manifest_has_required_field(manifest: dict[str, object], field: str) -> None:
    assert field in manifest, f"missing required field: {field}"


def test_schema_version_is_one(manifest: dict[str, object]) -> None:
    assert manifest["schemaVersion"] == 1


def test_id_is_namespaced(manifest: dict[str, object]) -> None:
    """Omarchy convention: io.github.<user>.<plugin> or <user>.<plugin>."""
    pid = str(manifest["id"])
    assert "." in pid, f"id must be namespaced, got {pid!r}"
    assert not pid.startswith("omarchy."), "third-party plugins cannot use omarchy.* namespace"


def test_id_matches_repo_owner(manifest: dict[str, object]) -> None:
    assert str(manifest["id"]).startswith("io.github.djspatule.")


def test_kinds_are_recognized(manifest: dict[str, object]) -> None:
    kinds = manifest["kinds"]
    assert isinstance(kinds, list) and kinds, "kinds must be a non-empty list"
    for k in kinds:
        assert k in VALID_KINDS, f"unknown kind: {k}"


def test_entry_points_match_kinds(manifest: dict[str, object]) -> None:
    entry_points = manifest["entryPoints"]
    assert isinstance(entry_points, dict) and entry_points, "entryPoints must be a non-empty dict"
    # Omarchy convention: kind `bar-widget` maps to entry point key `barWidget`
    kind_to_key = {
        "bar": "bar",
        "bar-widget": "barWidget",
        "panel": "panel",
        "overlay": "overlay",
        "menu": "menu",
        "service": "service",
    }
    for kind in manifest["kinds"]:
        ep_key = kind_to_key[str(kind)]
        assert (
            ep_key in entry_points
        ), f"missing entry point for kind {kind} (expected key {ep_key})"
        file_name = entry_points[ep_key]
        assert (
            REPO_ROOT / str(file_name)
        ).is_file(), f"entry point file does not exist: {file_name}"


def test_manifest_validates_via_omarchy(manifest: dict[str, object]) -> None:
    """The Omarchy CLI is the source of truth for schema validation."""
    import shutil
    import subprocess

    if shutil.which("omarchy") is None:
        pytest.skip("omarchy not on PATH")
    result = subprocess.run(
        ["omarchy", "plugin", "validate", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"omarchy plugin validate failed: {result.stderr}"


def test_license_is_mit(manifest: dict[str, object]) -> None:
    assert manifest["license"] == "MIT"
    license_file = REPO_ROOT / "LICENSE"
    assert license_file.is_file()
    assert "MIT License" in license_file.read_text()


def test_no_secrets_in_manifest(manifest: dict[str, object]) -> None:
    """Defensive: the manifest shouldn't carry credentials of any kind."""
    raw = MANIFEST.read_text()
    assert "sk-cp-" not in raw, "found sk-cp- in manifest"
    assert "MiniMax_API_KEY" not in raw, "found API key name in manifest"
