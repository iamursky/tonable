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

    target = cli.install(library, reload_live=False)
    assert target == old
    assert not (target / "stale.py").exists()
    assert (target / "__init__.py").is_file()
    assert (target / "server.py").is_file()
    assert not list(target.rglob("__pycache__"))
    assert cli.installed_version(target) == tonable.__version__

    cli.uninstall(library)
    assert not target.exists()
    assert "Removed" in capsys.readouterr().out
