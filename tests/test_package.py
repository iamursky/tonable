import subprocess
import sys

import tonable


def test_version_is_set():
    assert tonable.__version__


def test_cli_prints_version():
    result = subprocess.run(
        [sys.executable, "-m", "tonable", "--version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == f"tonable {tonable.__version__}"
