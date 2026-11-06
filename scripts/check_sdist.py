"""Run the full test suite from the source archive in a temporary environment."""

import argparse
import os
import subprocess
import tarfile
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", default="3.11")
    args = parser.parse_args()
    archives = list(Path("dist").glob("tonable-*.tar.gz"))
    if len(archives) != 1:
        parser.error("Build exactly one source archive in dist/ before this check.")
    with tempfile.TemporaryDirectory(prefix="tonable-source-") as directory:
        root = Path(directory)
        source = root / "source"
        with tarfile.open(archives[0]) as archive:
            archive.extractall(source, filter="data")
        projects = list(source.glob("*/pyproject.toml"))
        if len(projects) != 1:
            parser.error("Expected one project in the source archive.")
        home = root / "home"
        home.mkdir()
        env = {
            **os.environ,
            "HOME": str(home),
            "USERPROFILE": str(home),
            "PYTHONPATH": "",
            "UV_NO_CONFIG": "1",
        }
        for command in (
            ["uv", "sync", "--locked", "--python", args.python],
            ["uv", "run", "--locked", "--python", args.python, "pytest"],
        ):
            subprocess.run(
                command, cwd=projects[0].parent, env=env, check=True, timeout=180
            )


if __name__ == "__main__":
    main()
