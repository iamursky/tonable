"""The optional probe installer uses configured paths and preserves runtime data."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "probe_install", Path(__file__).parents[1] / "probe" / "install.py"
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


@pytest.fixture
def library(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    library = tmp_path / "configured library"
    monkeypatch.setattr(installer.cli, "live_preferences", lambda: (None, None))
    monkeypatch.setattr(installer.cli, "user_library", lambda prefs: library)
    return library


def test_install_uses_configured_library_and_optional_places(library):
    preset = library.parent / "example.adg"
    preset.write_bytes(b"synthetic test preset")
    installer.main(["--places-preset", str(preset)])
    target = library / "Remote Scripts" / "TonableProbe" / "__init__.py"
    assert target.is_file()
    places = Path.home() / ".tonable" / "probe-places" / "Tonable Probe Places.adg"
    assert places.read_bytes() == preset.read_bytes()
    assert not (library / "Remote Scripts" / "Tonable").exists()


def test_invalid_preset_does_not_install(library):
    with pytest.raises(SystemExit) as error:
        installer.main(["--places-preset", str(library / "missing.adg")])
    assert error.value.code == 2
    assert not library.exists()


def test_uninstall_preserves_tonable_and_reports(library):
    installer.main([])
    normal = library / "Remote Scripts" / "Tonable" / "version.py"
    normal.parent.mkdir()
    normal.write_text('VERSION = "example"')
    report = Path.home() / ".tonable" / "probe-report.json"
    report.parent.mkdir()
    report.write_text('{"status": "done"}')
    installer.main(["uninstall"])
    assert not (library / "Remote Scripts" / "TonableProbe").exists()
    assert normal.exists()
    assert report.read_text() == '{"status": "done"}'
