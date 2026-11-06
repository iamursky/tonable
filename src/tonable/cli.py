"""`tonable install`, `tonable uninstall` and `tonable doctor`.

Live keeps its User Library path in Library.cfg; Live 12.4.16 loads Remote Scripts
from that configured library, which may differ from the default location.
"""

import os
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import tonable
from tonable import bridge

PREFERENCES = Path("~/Library/Preferences/Ableton").expanduser()
DEFAULT_USER_LIBRARY = Path("~/Music/Ableton/User Library").expanduser()
SCRIPT_NAME = "Tonable"
MIN_LIVE = (12, 4)


def live_preferences(root=PREFERENCES):
    """The newest `Live 12.x.y` preferences folder and its version, or (None, None)."""
    found = []
    for folder in Path(root).glob("Live *"):
        match = re.fullmatch(r"Live (\d+)\.(\d+)(?:\.(\d+))?", folder.name)
        if match and folder.is_dir():
            version = tuple(int(part or 0) for part in match.groups())
            found.append((version, folder))
    if not found:
        return None, None
    version, folder = max(found)
    return folder, version


def user_library(preferences_folder):
    """The User Library Live uses, read from Library.cfg; ~/Music/... if not set."""
    if preferences_folder is not None:
        cfg = Path(preferences_folder) / "Library.cfg"
        try:
            project = (
                ET.parse(cfg)
                .getroot()
                .find("./ContentLibrary/UserLibrary/LibraryProject")
            )
        except (OSError, ET.ParseError):
            project = None
        if project is not None:
            path = project.find("ProjectPath")
            name = project.find("ProjectName")
            if path is not None and name is not None:
                return Path(path.get("Value")) / name.get("Value")
    return DEFAULT_USER_LIBRARY


def script_source():
    """The Remote Script folder: inside the installed wheel, or the repository."""
    packaged = Path(tonable.__file__).parent / "remote_script" / SCRIPT_NAME
    if packaged.is_dir():
        return packaged
    return Path(tonable.__file__).resolve().parents[2] / "remote_script" / SCRIPT_NAME


def script_target(library):
    return Path(library) / "Remote Scripts" / SCRIPT_NAME


def installed_version(target):
    try:
        text = (Path(target) / "version.py").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'VERSION = "([^"]+)"', text)
    return match.group(1) if match else None


def install(library=None, reload_live=True):
    library = library or user_library(live_preferences()[0])
    source = script_source()
    target = script_target(library)
    if not (source / "__init__.py").is_file():
        raise SystemExit(f"Remote Script not found at {source}")
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(
        source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
    )
    print(f"Installed Tonable {installed_version(target)} to {target}")
    if reload_live and _reload_running_live():
        return target
    print(
        "Next: restart Live, then choose Tonable in Settings -> Link, Tempo & MIDI ->"
    )
    print("Control Surface (Input and Output: None).")
    return target


def _reload_running_live(session_path=None):
    """Ask a running Tonable to load the new code; True when it did."""
    link = bridge.Bridge(session_path)
    try:
        result = link.request("reload")
    except bridge.BridgeError as err:
        if err.code == "unknown_command":
            print("Live runs an older Tonable that cannot reload: restart Live once.")
        return False
    finally:
        link.close()
    print(f"Live reloaded Tonable {result['script_version']}: no restart needed.")
    return True


def uninstall(library=None):
    library = library or user_library(live_preferences()[0])
    target = script_target(library)
    if target.exists():
        shutil.rmtree(target)
        print(f"Removed {target}")
    else:
        print(f"Nothing to remove: {target} does not exist")
    print("In Live, set the Tonable Control Surface slot back to None.")


def doctor(session_path=None):
    """Print each check with OK or FAIL; return 0 when all pass."""
    failures = 0

    def report(ok, text, hint=None):
        nonlocal failures
        print(("OK    " if ok else "FAIL  ") + text)
        if not ok:
            failures += 1
            if hint:
                print("      " + hint)

    prefs, version = live_preferences()
    if prefs is None:
        report(
            False,
            "Live preferences not found",
            "Start Live once, then run doctor again.",
        )
    else:
        shown = ".".join(str(v) for v in version)
        report(
            version[:2] >= MIN_LIVE,
            f"Live {shown} (preferences in {prefs})",
            "Tonable needs Live 12.4 or newer.",
        )
    library = user_library(prefs)
    report(library.is_dir(), f"User Library: {library}")
    target = script_target(library)
    found = installed_version(target)
    report(
        found == tonable.__version__,
        f"Remote Script in {target}: version {found or 'missing'}, "
        f"server {tonable.__version__}",
        "Run `tonable install` and restart Live.",
    )

    path = Path(session_path or bridge.SESSION_PATH)
    if not path.exists():
        report(False, f"Session file {path}", bridge.NOT_RUNNING_HINT)
        return 1
    report(bridge.session_permissions_ok(path), f"Session file {path} is owner-only")
    try:
        session = bridge.read_session(path)
        os.kill(session.get("pid", 0), 0)
        alive = True
    except (bridge.BridgeError, OSError, TypeError):
        alive = False
    report(
        alive, "Live process from the session file is running", bridge.NOT_RUNNING_HINT
    )

    link = bridge.Bridge(path)
    try:
        status = link.request("status")
    except bridge.BridgeError as err:
        report(False, f"Connection to Live: {err}", err.hint)
    else:
        s = status["set"]
        report(True, f"Connection to Live {status['live_version']}")
        report(
            status["script_version"] == tonable.__version__,
            f"Remote Script running in Live: version {status['script_version']}",
            "Restart Live so it loads the installed version.",
        )
        print(
            f"      Set: {s['tempo']:g} BPM, {s['time_signature']}, "
            f"{s['tracks']} tracks, {s['return_tracks']} returns, {s['scenes']} scenes"
        )
    finally:
        link.close()
    return 1 if failures else 0
