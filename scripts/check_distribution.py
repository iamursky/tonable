"""Check newly built artifacts outside the checkout without contacting Live.

Usage: uv run python scripts/check_distribution.py --wheel dist/<wheel> \
    --sdist dist/<sdist> --python 3.11
"""

import argparse
import asyncio
import configparser
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


def run(command, cwd, env):
    return subprocess.run(
        [str(arg) for arg in command],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    ).stdout.strip()


async def probe(command, args, home):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, "HOME": str(home), "USERPROFILE": str(home)}
    params = StdioServerParameters(command=command, args=args, env=env)
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            initialized = await client.initialize()
            tools = await client.list_tools()
            assert initialized.serverInfo.name == "tonable"
            assert len(tools.tools) == 24
            assert len({tool.name for tool in tools.tools}) == 24
            result = await client.call_tool("live_status", {})
            assert not result.isError
            status = json.loads(result.content[0].text)
            assert status["connected"] is False
            assert status["code"] == "not_running"
            print(json.dumps({"version": initialized.serverInfo.version, "tools": 24}))


def inspect_archives(wheel, sdist):
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        scripts = {
            name.removeprefix("tonable/remote_script/"): archive.read(name)
            for name in names
            if name.startswith("tonable/remote_script/") and name.endswith(".py")
        }
        assert len(scripts) == 14, sorted(scripts)
        assert any(name.endswith("/licenses/LICENSE") for name in names)
        assert any(name.endswith("/licenses/THIRD_PARTY_NOTICES.md") for name in names)
        assert not any(name.startswith(("tests/", "probe/")) for name in names)
        entries = next(name for name in names if name.endswith("/entry_points.txt"))
        config = configparser.ConfigParser()
        config.read_string(archive.read(entries).decode())
        assert config["console_scripts"]["tonable"] == "tonable.__main__:main"
    with tarfile.open(sdist) as archive:
        members = archive.getmembers()
        relative = [member.name.split("/", 1)[1] for member in members]
        for required in (
            "assets/tonable-logo.svg",
            "tests/test_cli.py",
            "probe/install.py",
            "docs/clients.md",
            "scripts/check_distribution.py",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
        ):
            assert required in relative, required
        for name, data in scripts.items():
            member = next(
                m for m in members if m.name.endswith("/remote_script/" + name)
            )
            assert archive.extractfile(member).read() == data
    for name in names + relative:
        parts = Path(name).parts
        assert not {"__pycache__", ".venv", ".git", ".tonable", "local"} & set(parts)
        assert not name.endswith((".pyc", ".pyo", ".als", ".adg", ".adv", ".log"))
        assert Path(name).name not in ("session.json", ".env", ".mcp.json")
    return scripts


def check(wheel, sdist, python):
    scripts = inspect_archives(wheel, sdist)
    with tempfile.TemporaryDirectory(prefix="tonable-distribution-") as folder:
        root = Path(folder)
        home = root / "home"
        home.mkdir()
        env = {
            **os.environ,
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(home / "AppData/Roaming"),
            "UV_CACHE_DIR": str(root / "cache"),
            "UV_TOOL_DIR": str(root / "tools"),
            "UV_TOOL_BIN_DIR": str(root / "bin"),
            "PYTHONPATH": "",
        }
        uv = "uv"
        venv = root / "venv"
        run([uv, "venv", "--python", python, venv], root, env)
        binary_dir = venv / ("Scripts" if os.name == "nt" else "bin")
        interpreter = binary_dir / ("python.exe" if os.name == "nt" else "python")
        executable = binary_dir / ("tonable.exe" if os.name == "nt" else "tonable")
        run([uv, "pip", "install", "--python", interpreter, wheel], root, env)
        version = run([executable, "--version"], root, env)
        assert run([interpreter, "-m", "tonable", "--version"], root, env) == version
        location = run(
            [interpreter, "-c", "import tonable; print(tonable.__file__)"], root, env
        )
        assert Path(location).is_relative_to(venv)
        run([executable, "install", "--help"], root, env)
        library = root / "staged User Library"
        args = ["install", "--user-library", library]
        run([executable, *args, "--dry-run", "--reload"], root, env)
        assert not library.exists()
        run([executable, *args], root, env)
        for name, data in scripts.items():
            assert (library / "Remote Scripts" / name).read_bytes() == data
        run([executable, *args, "--replace"], root, env)
        script = Path(__file__).resolve()
        # Execute the harness with the installed environment's MCP dependency.
        for command, command_args in (
            (str(executable), []),
            (str(interpreter), ["-m", "tonable", "serve"]),
            (
                "uvx",
                [
                    "--isolated",
                    "--python",
                    python,
                    "--from",
                    str(wheel),
                    "tonable",
                    "serve",
                ],
            ),
        ):
            output = run(
                [
                    interpreter,
                    script,
                    "--probe",
                    command,
                    json.dumps(command_args),
                    home,
                ],
                root,
                env,
            )
            assert json.loads(output.splitlines()[-1])["tools"] == 24
        # Persistent CLI entry point, isolated from the user's uv tool installation.
        run([uv, "tool", "install", "--python", python, wheel], root, env)
        tool = root / "bin" / executable.name
        assert run([tool, "--version"], root, env) == version
        run([tool, "libraries"], root, env)
        run([tool, "uninstall", "--user-library", library, "--yes"], root, env)
        assert not (library / "Remote Scripts/Tonable").exists()
        assert not (home / ".tonable").exists()
        print(
            json.dumps(
                {
                    "version": version,
                    "python": run([interpreter, "--version"], root, env),
                    "remote_script_files": len(scripts),
                    "tools_per_launch": 24,
                    "launches": [
                        "console",
                        "python -m",
                        "uvx --isolated",
                    ],
                    "persistent_tool_install": "pass",
                    "temporary_library": "pass",
                    "sha256": {
                        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (wheel, sdist)
                    },
                },
                indent=2,
            )
        )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--probe":
        asyncio.run(
            asyncio.wait_for(
                probe(sys.argv[2], json.loads(sys.argv[3]), Path(sys.argv[4])),
                timeout=45,
            )
        )
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--sdist", type=Path, required=True)
    parser.add_argument("--python", default="3.11")
    args = parser.parse_args()
    check(args.wheel.resolve(), args.sdist.resolve(), args.python)


if __name__ == "__main__":
    main()
