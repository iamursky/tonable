"""Reject branch dispatches, version mismatches and tags outside main."""

import os
import re
import subprocess
import tomllib
from pathlib import Path


def main():
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    tag = os.environ.get("RELEASE_TAG", "")
    if os.environ.get("RELEASE_REF_TYPE") != "tag":
        raise SystemExit("Run Release on a version tag, not a branch.")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or tag != f"v{version}":
        raise SystemExit(f"Release tag must be v{version}; received {tag!r}.")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", "HEAD", "origin/main"], check=True
    )
    print(f"Validated {tag}: tagged commit is on main.")


if __name__ == "__main__":
    main()
