"""Install optional diagnostics; never copy factory content into the repository."""

import argparse
import shutil
from pathlib import Path

from tonable import cli


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", nargs="?", choices=["install", "uninstall"], default="install"
    )
    parser.add_argument(
        "--places-preset",
        type=Path,
        help="Optional existing .adg file for the Places check",
    )
    args = parser.parse_args(argv)
    library = cli.user_library(cli.live_preferences()[0])
    target = library / "Remote Scripts" / "TonableProbe"
    if args.command == "uninstall":
        if target.exists():
            shutil.rmtree(target)
        print(f"Removed {target}")
        print("In Live, set the TonableProbe Control Surface slot to None.")
        print("Reports and optional Places files in ~/.tonable were kept.")
        return
    preset = args.places_preset
    if preset is not None:
        preset = preset.expanduser().resolve()
        if not preset.is_file() or preset.suffix.lower() != ".adg":
            parser.error("--places-preset must be an existing .adg file")
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        Path(__file__).parent / "TonableProbe" / "__init__.py", target / "__init__.py"
    )
    shutil.rmtree(target / "__pycache__", ignore_errors=True)
    print(f"Installed {target}")
    if preset is not None:
        places = Path("~/.tonable/probe-places").expanduser()
        places.mkdir(parents=True, exist_ok=True, mode=0o700)
        shutil.copyfile(preset, places / "Tonable Probe Places.adg")
        print(f"Prepared {places}; add it to Places in Live before running the probe.")
    print("Restart Live and select TonableProbe only in a disposable empty Set.")


if __name__ == "__main__":
    main()
