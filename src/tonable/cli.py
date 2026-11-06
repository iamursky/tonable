"""`tonable install`, `tonable uninstall` and `tonable doctor`.

Live keeps its User Library path in Library.cfg; Live 12.4.16 loads Remote Scripts
from that configured library, which may differ from the default location.
"""

import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
from importlib.resources import files
from pathlib import Path

import tonable
from tonable import bridge


def platform_paths(platform=None, home=None, environ=None):
    """Known defaults for discovery; explicit paths work on any OS."""
    platform = platform or sys.platform
    home = Path(home) if home is not None else Path.home()
    environ = os.environ if environ is None else environ
    if platform == "darwin":
        return home / "Library/Preferences/Ableton", home / "Music/Ableton/User Library"
    if platform == "win32":
        appdata = Path(environ.get("APPDATA", home / "AppData/Roaming"))
        return appdata / "Ableton", home / "Documents/Ableton/User Library"
    return None, None


PREFERENCES, DEFAULT_USER_LIBRARY = platform_paths()
SCRIPT_NAME = "Tonable"
MIN_LIVE = (12, 4)


def preference_folders(root=None):
    """All versioned Live preferences, newest first."""
    root = PREFERENCES if root is None else root
    found = []
    if root is None:
        return found
    for folder in Path(root).glob("Live *"):
        match = re.fullmatch(r"Live (\d+)\.(\d+)(?:\.(\d+))?", folder.name)
        if match and folder.is_dir():
            version = tuple(int(part or 0) for part in match.groups())
            found.append((version, folder))
    return sorted(found, reverse=True)


def live_preferences(root=None):
    """The newest versioned Live preferences folder, or (None, None)."""
    found = preference_folders(root)
    if not found:
        return None, None
    version, folder = found[0]
    return folder, version


def configured_library(preferences_folder):
    """Read a valid absolute library location; never guess from partial XML."""
    if preferences_folder is None:
        return None
    try:
        project = (
            ET.parse(Path(preferences_folder) / "Library.cfg")
            .getroot()
            .find("./ContentLibrary/UserLibrary/LibraryProject")
        )
    except (OSError, ET.ParseError):
        return None
    if project is None:
        return None
    path, name = project.find("ProjectPath"), project.find("ProjectName")
    base = path.get("Value", "") if path is not None else ""
    leaf = name.get("Value", "") if name is not None else ""
    if (
        not Path(base).is_absolute()
        or not leaf
        or leaf in (".", "..")
        or "/" in leaf
        or "\\" in leaf
    ):
        return None
    return Path(base) / leaf


def user_library(preferences_folder):
    """Configured library or the OS default, for read-only library access."""
    return configured_library(preferences_folder) or DEFAULT_USER_LIBRARY


def discover_libraries(root=None, default=None):
    """Existing configured libraries, deduplicated; default only as a fallback."""
    found = {}
    configured = False
    for _, folder in preference_folders(root):
        library = configured_library(folder)
        if library is not None:
            configured = True
            if library.is_dir():
                found.setdefault(library.resolve(), f"{folder.name}/Library.cfg")
            else:
                print(f"Configured library unavailable: {library}", file=sys.stderr)
    default = DEFAULT_USER_LIBRARY if default is None else default
    if not configured and default is not None and Path(default).is_dir():
        found[Path(default).resolve()] = (
            "OS default (verify in Live Settings -> Library)"
        )
    return list(found.items())


def select_library(explicit=None, *, yes=False, interactive=None):
    """Select one library without silently choosing among Live installations."""
    if explicit is not None:
        library = Path(explicit).expanduser().resolve()
    else:
        candidates = discover_libraries()
        if not candidates:
            raise ValueError(
                "No existing User Library found. Use --user-library PATH from "
                "Live Settings -> Library (or an explicit staging folder)."
            )
        for i, (path, origin) in enumerate(candidates, 1):
            print(f"{i}. {path} [{origin}]")
        interactive = sys.stdin.isatty() if interactive is None else interactive
        if len(candidates) > 1:
            if not interactive:
                raise ValueError("Multiple libraries found; use --user-library PATH.")
            try:
                choice = int(input("Select a User Library number (Ctrl-C to cancel): "))
            except ValueError:
                raise ValueError("Enter a listed library number.") from None
            if not 1 <= choice <= len(candidates):
                raise ValueError("Enter a listed library number.")
            library = candidates[choice - 1][0]
        else:
            library = candidates[0][0]
        if not yes:
            if not interactive:
                raise ValueError("Confirm this path with --yes or --user-library PATH.")
            if input(f"Use {library}? [y/N] ").strip().lower() != "y":
                raise ValueError("Cancelled; no files changed.")
    if library == Path(library.anchor) or library.name in (
        "Remote Scripts",
        SCRIPT_NAME,
    ):
        raise ValueError("Choose the User Library folder, not a root or script folder.")
    if library.exists() and not library.is_dir():
        raise ValueError(f"User Library is not a directory: {library}")
    return library


def script_source():
    """Production resources in a wheel, or in an editable source checkout."""
    packaged = files("tonable").joinpath("remote_script", SCRIPT_NAME)
    if packaged.is_dir():
        return packaged
    return Path(tonable.__file__).resolve().parents[2] / "remote_script" / SCRIPT_NAME


def _copy_resources(source, target):
    target.mkdir()
    for entry in source.iterdir():
        if entry.name == "__pycache__" or entry.name.endswith((".pyc", ".pyo")):
            continue
        destination = target / entry.name
        if entry.is_dir():
            _copy_resources(entry, destination)
        else:
            destination.write_bytes(entry.read_bytes())


def _safe_target(library):
    library = Path(library).expanduser().resolve()
    target = script_target(library)
    for path in (target.parent, target):
        if path.is_symlink():
            raise ValueError(f"Refusing symlink: {path}")
        if path.exists() and not path.is_dir():
            raise ValueError(f"Not a directory: {path}")
    return target


def script_target(library):
    return Path(library) / "Remote Scripts" / SCRIPT_NAME


def installed_version(target):
    try:
        text = (Path(target) / "version.py").read_text(encoding="utf-8")
    except OSError:
        return None
    match = re.search(r'VERSION = "([^"]+)"', text)
    return match.group(1) if match else None


def install(library, *, replace=False, dry_run=False, reload_live=False):
    """Stage resources before replacing only the selected Tonable directory."""
    source = script_source()
    target = _safe_target(library)
    if not source.joinpath("__init__.py").is_file():
        raise ValueError(f"Remote Script resources not found at {source}")
    print(f"Target: {target}")
    if target.exists() and not replace:
        raise ValueError(
            "Tonable already exists; use --replace to replace this folder."
        )
    if dry_run:
        print("Dry run: no files changed; Live was not contacted.")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".tonable-", dir=target.parent))
    staged, previous = work / "Tonable", work / "previous"
    committed = False
    try:
        _copy_resources(source, staged)
        if target.exists():
            target.rename(previous)
        try:
            staged.rename(target)
        except OSError:
            if previous.exists():
                previous.rename(target)
            raise
        committed = True
    finally:
        if committed or not previous.exists():
            shutil.rmtree(work)
        else:
            print(f"Previous installation preserved at {previous}", file=sys.stderr)
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


def uninstall(library, *, yes=False, dry_run=False):
    target = _safe_target(library)
    print(f"Target: {target}")
    if dry_run:
        print("Dry run: no files changed.")
        return
    if not yes:
        if not sys.stdin.isatty() or input("Remove this Tonable folder? [y/N] ") != "y":
            raise ValueError("Removal needs confirmation; use --yes for this target.")
    if target.exists():
        shutil.rmtree(target)
        print(f"Removed {target}")
    else:
        print(f"Nothing to remove: {target} does not exist")
    print("In Live, set the Tonable Control Surface slot back to None.")


def doctor(session_path=None, library=None):
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
    library = (
        Path(library).expanduser().resolve()
        if library is not None
        else user_library(prefs)
    )
    if library is None:
        report(False, "No User Library known; use --user-library PATH")
        return 1
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
