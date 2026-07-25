"""Verify the packaged enum-generator command boundary."""

import ast
import importlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_packaged_enum_generator_is_authoritative_and_legacy_module_is_alias() -> None:
    """Verify both enum-generator import paths share one module."""
    package_module = importlib.import_module("acquire.enumsgen")
    legacy_module = importlib.import_module("enumsgen")

    assert legacy_module is package_module
    assert package_module.__file__ == str(
        REPOSITORY_ROOT / "src" / "acquire" / "enumsgen.py"
    )


def test_enum_generator_wrapper_is_minimal_and_owned_by_issue_111() -> None:
    """Verify the transitional direct-file path contains only delegation."""
    wrapper_path = REPOSITORY_ROOT / "server" / "enumsgen.py"
    source = wrapper_path.read_text()
    tree = ast.parse(source)

    assert "issue #111" in source
    assert "from acquire import enumsgen as _enumsgen" in source
    assert not any(
        isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        for node in ast.walk(tree)
    )


def test_enum_generator_does_not_mutate_sys_path() -> None:
    """Verify the installed generator has no path-injection fallback."""
    source_path = REPOSITORY_ROOT / "src" / "acquire" / "enumsgen.py"
    tree = ast.parse(source_path.read_text())

    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Attribute)
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "sys"
        and node.func.value.attr == "path"
        for node in ast.walk(tree)
    )


def test_installed_enum_command_runs_outside_repository(
    tmp_path: Path,
) -> None:
    """Verify help and development output use only explicit installed inputs."""
    command = shutil.which("acquire-generate-enums")
    assert command is not None
    client_source_root = tmp_path / "private-client-source"
    client_source_root.mkdir()
    (client_source_root / "app.js").write_text("enums.PubSub.Client_Started\n")
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)

    help_result = subprocess.run(
        [command, "--help"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    generate_result = subprocess.run(
        [
            command,
            "js",
            "development",
            "--client-source-root",
            str(client_source_root),
        ],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert help_result.returncode == 0
    assert help_result.stderr == ""
    assert "Generate or replace JavaScript enum definitions" in help_result.stdout
    assert generate_result.returncode == 0
    assert generate_result.stderr == ""
    assert generate_result.stdout.startswith("module.exports = {\n")
    assert "\tPubSub: {" in generate_result.stdout
