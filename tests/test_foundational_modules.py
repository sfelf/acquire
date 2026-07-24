import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FOUNDATIONAL_MODULES = ("enums", "settings", "username_to_user_id", "util")


def test_foundational_modules_import_outside_repository(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    imports = "; ".join(
        f"import acquire.{module_name}" for module_name in FOUNDATIONAL_MODULES
    )

    result = subprocess.run(
        [sys.executable, "-c", f"{imports}; print('imported')"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "imported\n"


def test_legacy_server_modules_import_after_editable_project_install() -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    imports = (
        "import auth, cron, enumsgen, http_server, logs_to_games, server; "
        "print('imported')"
    )

    result = subprocess.run(
        [sys.executable, "-c", imports],
        cwd=REPOSITORY_ROOT / "server",
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "imported\n"


def test_legacy_foundational_modules_are_minimal_compatibility_wrappers() -> None:
    for module_name in FOUNDATIONAL_MODULES:
        wrapper = (REPOSITORY_ROOT / "server" / f"{module_name}.py").read_text()
        statements = ast.parse(wrapper).body

        assert "#111" in wrapper
        if module_name == "settings":
            assert "sys.modules[__name__] = _settings" in wrapper
            assert [type(statement) for statement in statements] == [
                ast.Expr,
                ast.Import,
                ast.ImportFrom,
                ast.Assign,
            ]
            continue

        assert f"from acquire.{module_name} import" in wrapper
        assert [type(statement) for statement in statements] == [
            ast.Expr,
            ast.ImportFrom,
            ast.Assign,
        ]
        assert isinstance(statements[1], ast.ImportFrom)
        assert statements[1].module == f"acquire.{module_name}"
        assert isinstance(statements[2], ast.Assign)
        assert isinstance(statements[2].targets[0], ast.Name)
        assert statements[2].targets[0].id == "__all__"


def test_legacy_foundational_module_exports_match_package() -> None:
    for module_name in FOUNDATIONAL_MODULES:
        legacy_module = importlib.import_module(module_name)
        package_module = importlib.import_module(f"acquire.{module_name}")

        if module_name == "settings":
            assert legacy_module is package_module
            continue

        for exported_name in legacy_module.__all__:
            assert getattr(legacy_module, exported_name) is getattr(
                package_module, exported_name
            )


def test_legacy_settings_rebinding_updates_package_settings() -> None:
    legacy_settings = importlib.import_module("settings")
    package_settings = importlib.import_module("acquire.settings")
    package_util = importlib.import_module("acquire.util")
    original_prefixes = package_settings.util__get_log_file_filenames__path_prefixes
    replacement_prefixes = ["/tmp/acquire-review-override-"]

    try:
        legacy_settings.util__get_log_file_filenames__path_prefixes = replacement_prefixes

        assert package_settings.util__get_log_file_filenames__path_prefixes is (
            replacement_prefixes
        )
        assert package_util.settings.util__get_log_file_filenames__path_prefixes is (
            replacement_prefixes
        )
    finally:
        package_settings.util__get_log_file_filenames__path_prefixes = original_prefixes


def test_legacy_installation_installs_project_editable_after_requirements() -> None:
    readme = (REPOSITORY_ROOT / "README.md").read_text()

    requirements_install = "pip3 install -r requirements.txt"
    project_install = "pip3 install --no-deps -e ."

    assert requirements_install in readme
    assert project_install in readme
    assert readme.index(requirements_install) < readme.index(project_install)
