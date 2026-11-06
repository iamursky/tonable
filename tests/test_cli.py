import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import tonable
from tonable import cli

LIBRARY_CFG = """<?xml version="1.0" encoding="UTF-8"?>
<Ableton MajorVersion="5" Creator="Ableton Live 12.4.16">
  <ContentLibrary>
    <UserLibrary>
      <LibraryProject Id="1">
        <ProjectLocation />
        <ProjectName Value="User Library" />
        <ProjectPath Value="/example/Ableton" />
      </LibraryProject>
    </UserLibrary>
  </ContentLibrary>
</Ableton>
"""


def test_newest_live_preferences(tmp_path):
    for name in ("Live 12.3.5", "Live 12.4.16", "Live 12.4.2", "Live Beta", "Other"):
        (tmp_path / name).mkdir()
    folder, version = cli.live_preferences(tmp_path)
    assert folder.name == "Live 12.4.16"
    assert version == (12, 4, 16)


def test_no_live_preferences(tmp_path):
    assert cli.live_preferences(tmp_path) == (None, None)


def test_user_library_from_library_cfg(tmp_path):
    (tmp_path / "Library.cfg").write_text(LIBRARY_CFG)
    assert str(cli.user_library(tmp_path)) == "/example/Ableton/User Library"


def test_user_library_default_without_cfg(tmp_path):
    assert cli.user_library(tmp_path) == cli.DEFAULT_USER_LIBRARY
    assert cli.user_library(None) == cli.DEFAULT_USER_LIBRARY


def test_install_and_uninstall(tmp_path, capsys):
    library = tmp_path / "User Library"
    # A stale copy with leftovers is replaced, not merged.
    old = library / "Remote Scripts" / "Tonable"
    old.mkdir(parents=True)
    (old / "stale.py").write_text("")

    target = cli.install(library, replace=True)
    assert target == old
    assert not (target / "stale.py").exists()
    assert (target / "__init__.py").is_file()
    assert (target / "server.py").is_file()
    assert not list(target.rglob("__pycache__"))
    assert cli.installed_version(target) == tonable.__version__

    cli.uninstall(library, yes=True)
    assert not target.exists()
    assert "Removed" in capsys.readouterr().out


def test_platform_defaults(tmp_path):
    prefs, library = cli.platform_paths("darwin", tmp_path, {})
    assert prefs == tmp_path / "Library/Preferences/Ableton"
    assert library == tmp_path / "Music/Ableton/User Library"
    prefs, library = cli.platform_paths(
        "win32", tmp_path, {"APPDATA": str(tmp_path / "app")}
    )
    assert prefs == tmp_path / "app/Ableton"
    assert library == tmp_path / "Documents/Ableton/User Library"
    assert cli.platform_paths("linux", tmp_path, {}) == (None, None)


def write_config(preferences, library):
    preferences.mkdir(parents=True, exist_ok=True)
    root = ET.fromstring(LIBRARY_CFG)
    root.find(".//ProjectPath").set("Value", str(library.parent))
    root.find(".//ProjectName").set("Value", library.name)
    (preferences / "Library.cfg").write_bytes(ET.tostring(root))


def test_discovery_deduplicates_and_keeps_distinct_libraries(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    first.mkdir()
    second.mkdir()
    root = tmp_path / "preferences"
    write_config(root / "Live 12.4.16", first)
    write_config(root / "Live 12.4.2", first)
    write_config(root / "Live 12.3.5", second)
    assert cli.discover_libraries(root, tmp_path / "absent") == [
        (first, "Live 12.4.16/Library.cfg"),
        (second, "Live 12.3.5/Library.cfg"),
    ]


@pytest.mark.parametrize(
    "xml",
    [
        "<broken",
        "<Ableton/>",
        LIBRARY_CFG.replace('Value="/example/Ableton"', 'Value=""'),
        LIBRARY_CFG.replace('Value="User Library"', 'Value="../outside"'),
    ],
)
def test_invalid_library_config_does_not_invent_path(tmp_path, xml):
    (tmp_path / "Library.cfg").write_text(xml)
    assert cli.configured_library(tmp_path) is None


def test_discovery_never_creates_default(tmp_path):
    default = tmp_path / "missing"
    assert cli.discover_libraries(tmp_path, default) == []
    assert not default.exists()
    default.mkdir()
    assert cli.discover_libraries(tmp_path, default)[0][0] == default


def test_noninteractive_selection_requires_unambiguous_confirmation(
    tmp_path, monkeypatch
):
    choices = [(tmp_path / "one", "test"), (tmp_path / "two", "test")]
    monkeypatch.setattr(cli, "discover_libraries", lambda: choices)
    with pytest.raises(ValueError, match="Multiple"):
        cli.select_library(yes=True, interactive=False)
    choices.pop()
    with pytest.raises(ValueError, match="Confirm"):
        cli.select_library(interactive=False)
    assert cli.select_library(yes=True, interactive=False) == choices[0][0]
    assert cli.select_library(tmp_path / "explicit") == tmp_path / "explicit"


def test_interactive_selection_and_cancellation(tmp_path, monkeypatch):
    choices = [(tmp_path / "one", "test"), (tmp_path / "two", "test")]
    monkeypatch.setattr(cli, "discover_libraries", lambda: choices)
    answers = iter(["2", "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert cli.select_library(interactive=True) == choices[1][0]
    monkeypatch.setattr("builtins.input", lambda _: "0")
    with pytest.raises(ValueError, match="listed"):
        cli.select_library(interactive=True)
    choices.pop()
    monkeypatch.setattr("builtins.input", lambda _: "n")
    with pytest.raises(ValueError, match="Cancelled"):
        cli.select_library(interactive=True)


def test_install_refuses_overwrite_and_never_contacts_live(tmp_path, monkeypatch):
    def unexpected_reload():
        pytest.fail("Installation must not contact Live by default")

    monkeypatch.setattr(cli, "_reload_running_live", unexpected_reload)
    target = cli.install(tmp_path)
    (target / "keep.txt").write_text("custom")
    with pytest.raises(ValueError, match="--replace"):
        cli.install(tmp_path)
    assert (target / "keep.txt").read_text() == "custom"
    cli.install(tmp_path, replace=True)
    assert not (target / "keep.txt").exists()


@pytest.mark.parametrize("parent_link", [False, True])
def test_mutations_refuse_symlinks(tmp_path, parent_link):
    library, outside = tmp_path / "library", tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    library.mkdir()
    if parent_link:
        (library / "Remote Scripts").symlink_to(outside, target_is_directory=True)
    else:
        (library / "Remote Scripts").mkdir()
        (library / "Remote Scripts/Tonable").symlink_to(
            outside, target_is_directory=True
        )
    with pytest.raises(ValueError, match="symlink"):
        cli.install(library, replace=True)
    with pytest.raises(ValueError, match="symlink"):
        cli.uninstall(library, yes=True)
    assert (outside / "keep.txt").read_text() == "keep"


def test_staging_failure_preserves_existing_install(tmp_path, monkeypatch):
    target = cli.install(tmp_path)
    before = (target / "version.py").read_bytes()

    def fail(*_):
        raise OSError("synthetic copy failure")

    monkeypatch.setattr(cli, "_copy_resources", fail)
    with pytest.raises(OSError, match="synthetic"):
        cli.install(tmp_path, replace=True)
    assert (target / "version.py").read_bytes() == before
    assert not list(target.parent.glob(".tonable-*"))


def test_activation_failure_restores_existing_install(tmp_path, monkeypatch):
    target = cli.install(tmp_path)
    (target / "keep.txt").write_text("keep")
    original = Path.rename

    def fail_staged(path, destination):
        if path.name == "Tonable" and path.parent.name.startswith(".tonable-"):
            raise OSError("synthetic activation failure")
        return original(path, destination)

    monkeypatch.setattr(Path, "rename", fail_staged)
    with pytest.raises(OSError, match="synthetic"):
        cli.install(tmp_path, replace=True)
    assert (target / "keep.txt").read_text() == "keep"


def test_entrypoint_path_dry_run_install_and_remove(tmp_path):
    from tonable.__main__ import main

    library = tmp_path / "staging library"
    args = ["--user-library", str(library)]
    assert main(["install", *args, "--dry-run", "--reload"]) == 0
    assert not library.exists()
    assert main(["install", *args]) == 0
    neighbor = library / "Remote Scripts/Other/keep.py"
    neighbor.parent.mkdir()
    neighbor.write_text("keep")
    assert main(["uninstall", *args, "--dry-run"]) == 0
    assert (library / "Remote Scripts/Tonable").exists()
    assert main(["uninstall", *args, "--yes"]) == 0
    assert neighbor.read_text() == "keep"


def test_unavailable_configured_library_does_not_select_default(tmp_path):
    default = tmp_path / "default"
    default.mkdir()
    preferences = tmp_path / "preferences"
    write_config(preferences / "Live 12.4.16", tmp_path / "offline" / "library")
    assert cli.discover_libraries(preferences, default) == []


def test_failed_restore_keeps_backup_for_recovery(tmp_path, monkeypatch):
    target = cli.install(tmp_path)
    (target / "keep.txt").write_text("keep")
    original = Path.rename

    def fail_activation_and_restore(path, destination):
        if path.parent.name.startswith(".tonable-"):
            raise OSError("synthetic rename failure")
        return original(path, destination)

    monkeypatch.setattr(Path, "rename", fail_activation_and_restore)
    with pytest.raises(OSError, match="synthetic"):
        cli.install(tmp_path, replace=True)
    backups = list(target.parent.glob(".tonable-*/previous/keep.txt"))
    assert len(backups) == 1
    assert backups[0].read_text() == "keep"
