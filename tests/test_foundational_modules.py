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


def test_legacy_foundational_modules_are_logic_free_compatibility_wrappers() -> None:
    for module_name in FOUNDATIONAL_MODULES:
        wrapper = (REPOSITORY_ROOT / "server" / f"{module_name}.py").read_text()
        statements = ast.parse(wrapper).body

        assert "#111" in wrapper
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

        for exported_name in legacy_module.__all__:
            assert getattr(legacy_module, exported_name) is getattr(
                package_module, exported_name
            )
