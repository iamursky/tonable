"""Release guards fail before publication and never overwrite changed assets."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


def load_script(name):
    path = Path(__file__).parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load_script("check_release")
publisher = load_script("github_release")


@pytest.mark.parametrize(
    ("ref_type", "tag"), [("branch", "main"), ("tag", "v0.5.1"), ("tag", "v0.5.20")]
)
def test_invalid_release_ref_fails_before_git(tmp_path, monkeypatch, ref_type, tag):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.5.2"\n')
    monkeypatch.setenv("RELEASE_REF_TYPE", ref_type)
    monkeypatch.setenv("RELEASE_TAG", tag)
    monkeypatch.setattr(
        guard.subprocess, "run", lambda *a, **k: pytest.fail("git called")
    )
    with pytest.raises(SystemExit):
        guard.main()


def test_tag_outside_main_is_rejected(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.5.2"\n')
    monkeypatch.setenv("RELEASE_REF_TYPE", "tag")
    monkeypatch.setenv("RELEASE_TAG", "v0.5.2")

    def fail_ancestry(command, **kwargs):
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(guard.subprocess, "run", fail_ancestry)
    with pytest.raises(subprocess.CalledProcessError):
        guard.main()


@pytest.fixture
def release_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("RELEASE_TAG", "v0.5.2")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/tonable")
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "tonable-0.5.2-py3-none-any.whl").write_bytes(b"synthetic wheel")
    (dist / "tonable-0.5.2.tar.gz").write_bytes(b"synthetic source")
    return dist


def test_release_api_failure_never_creates_release(release_files, monkeypatch):
    calls = []

    def fail_api(*args):
        calls.append(args)
        raise subprocess.CalledProcessError(1, ["gh", *args])

    monkeypatch.setattr(publisher, "gh", fail_api)
    with pytest.raises(subprocess.CalledProcessError):
        publisher.main()
    assert len(calls) == 1
    assert calls[0][0] == "api"


def test_new_release_is_draft_until_assets_are_attached(release_files, monkeypatch):
    calls = []

    def capture(*args):
        calls.append(args)
        return "[[]]" if args[0] == "api" else ""

    monkeypatch.setattr(publisher, "gh", capture)
    publisher.main()
    create, publish = calls[1:]
    assert create[:2] == ("release", "create")
    assert "--draft" in create
    assert any(arg.endswith(".whl") for arg in create)
    assert any(arg.endswith(".tar.gz") for arg in create)
    assert "SHA256SUMS.txt" in create
    assert publish[:2] == ("release", "edit")
    assert "--draft=false" in publish


def test_changed_public_asset_is_never_replaced(release_files, monkeypatch):
    wheel = next(release_files.glob("*.whl"))
    calls = []

    def existing_release(*args):
        calls.append(args)
        if args[0] == "api":
            return json.dumps(
                [[{"tag_name": "v0.5.2", "assets": [{"name": wheel.name}]}]]
            )
        assert args[:2] == ("release", "download")
        destination = Path(args[args.index("--dir") + 1])
        (destination / wheel.name).write_bytes(b"different public bytes")
        return ""

    monkeypatch.setattr(publisher, "gh", existing_release)
    with pytest.raises(SystemExit, match="Refusing to replace"):
        publisher.main()
    assert not any(
        call[:2] in (("release", "edit"), ("release", "upload")) for call in calls
    )
