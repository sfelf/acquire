import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

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
