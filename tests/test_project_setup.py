from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _package_names(path: Path) -> set[str]:
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=\[]", line, maxsplit=1)[0].strip().lower()
        names.add(name)
    return names


def test_unified_requirements_cover_backend_runtime_dependencies():
    root_packages = _package_names(ROOT / "requirements.txt")
    backend_packages = _package_names(ROOT / "backend" / "requirements.txt")

    assert backend_packages <= root_packages


def test_unix_launchers_have_valid_shell_syntax():
    bash = shutil.which("bash")
    assert bash is not None

    subprocess.run(
        [bash, "-n", str(ROOT / "run_backend.sh"), str(ROOT / "start.sh")],
        check=True,
    )


def test_launchers_preserve_required_runtime_contracts():
    launchers = [
        ROOT / "run_backend.bat",
        ROOT / "run_backend.ps1",
        ROOT / "run_backend.sh",
        ROOT / "start.bat",
        ROOT / "start.ps1",
        ROOT / "start.sh",
    ]

    for launcher in launchers:
        content = launcher.read_text(encoding="utf-8").lower()
        assert "backend.main:app" in content
        assert "rag_enabled" in content
        assert "rag_vector_enabled" in content
        assert "translation_enabled" in content
        assert "/api/health" in content


def test_windows_full_stack_launchers_do_not_require_python_launcher_alias():
    batch = (ROOT / "start.bat").read_text(encoding="utf-8").lower()
    powershell = (ROOT / "start.ps1").read_text(encoding="utf-8").lower()

    assert "where py" in batch
    assert "where python" in batch
    assert "%py_cmd% -m uvicorn" in batch
    assert "get-command py" in powershell
    assert "get-command python" in powershell
    assert "& $pycmd -m uvicorn" in powershell
