"""Verify PyPI hashes and discover tools from the published package outside checkout."""

import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def discover(version, root):
    env = {
        **os.environ,
        "HOME": str(root / "home"),
        "USERPROFILE": str(root / "home"),
        "UV_CACHE_DIR": str(root / "cache"),
        "PYTHONPATH": "",
    }
    (root / "home").mkdir()
    args = [
        "--isolated",
        "--python",
        "3.11",
        "--default-index",
        "https://pypi.org/simple",
        "--from",
        f"tonable=={version}",
        "tonable",
    ]
    result = subprocess.run(
        ["uvx", *args, "--version"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )
    assert result.stdout.strip() == f"tonable {version}"
    original = Path.cwd()
    os.chdir(root)
    try:
        params = StdioServerParameters(command="uvx", args=[*args, "serve"], env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                initialized = await client.initialize()
                assert initialized.serverInfo.version == version
                tools = await client.list_tools()
                assert len(tools.tools) == 24
                response = await client.call_tool("live_status", {})
                assert not response.isError
                status = json.loads(response.content[0].text)
                assert status["connected"] is False and status["code"] == "not_running"
    finally:
        os.chdir(original)


def main():
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    url = f"https://pypi.org/pypi/tonable/{version}/json"
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                metadata = json.load(response)
            break
        except urllib.error.HTTPError as error:
            if error.code != 404 or attempt == 5:
                raise
            time.sleep(5)
    public = {item["filename"]: item["digests"]["sha256"] for item in metadata["urls"]}
    distributions = list(Path("dist").glob("*.whl")) + list(
        Path("dist").glob("*.tar.gz")
    )
    assert len(distributions) == 2
    for path in distributions:
        assert public[path.name] == hashlib.sha256(path.read_bytes()).hexdigest(), (
            path.name
        )
    with tempfile.TemporaryDirectory(prefix="tonable-registry-") as directory:
        asyncio.run(asyncio.wait_for(discover(version, Path(directory)), timeout=240))
    print(
        f"Verified PyPI tonable {version}: both file hashes, uvx entry point, 24 tools."
    )


if __name__ == "__main__":
    main()
