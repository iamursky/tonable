"""Publish tested CI artifacts without replacing an existing release asset."""

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path


def gh(*args):
    return subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True, timeout=120
    ).stdout


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    tag = os.environ["RELEASE_TAG"]
    repo = os.environ["GITHUB_REPOSITORY"]
    wheels = list(Path("dist").glob("*.whl"))
    sources = list(Path("dist").glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise SystemExit("Expected one wheel and one source archive.")
    files = wheels + sources
    checksums = Path("SHA256SUMS.txt")
    checksums.write_text("".join(f"{digest(p)}  {p.name}\n" for p in files))
    files.append(checksums)
    # List first: authentication or network errors must never mean "create".
    releases = json.loads(gh("api", f"repos/{repo}/releases", "--paginate", "--slurp"))
    release = next((r for page in releases for r in page if r["tag_name"] == tag), None)
    if release is None:
        gh(
            "release",
            "create",
            tag,
            "--repo",
            repo,
            "--verify-tag",
            "--draft",
            "--title",
            f"Tonable {tag.removeprefix('v')}",
            "--notes-file",
            ".github/release-notes.md",
            *(str(p) for p in files),
        )
    else:
        existing = {asset["name"] for asset in release["assets"]}
        with tempfile.TemporaryDirectory(prefix="tonable-release-") as directory:
            for path in files:
                if path.name in existing:
                    gh(
                        "release",
                        "download",
                        tag,
                        "--repo",
                        repo,
                        "--pattern",
                        path.name,
                        "--dir",
                        directory,
                    )
                    if digest(Path(directory) / path.name) != digest(path):
                        raise SystemExit(
                            f"Refusing to replace changed asset {path.name}."
                        )
                else:
                    gh("release", "upload", tag, str(path), "--repo", repo)
    gh("release", "edit", tag, "--repo", repo, "--draft=false", "--latest")
    print(f"https://github.com/{repo}/releases/tag/{tag}")


if __name__ == "__main__":
    main()
