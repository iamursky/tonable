"""`tonable` serves MCP on stdio; setup commands never start the MCP server."""

import argparse
import sys
from pathlib import Path

from tonable import __version__


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="tonable",
        description="Run the local MCP server or install its Live component.",
    )
    parser.add_argument("--version", action="version", version=f"tonable {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="Run the MCP server on stdio (also the default)")
    commands.add_parser("libraries", help="List existing User Library candidates")
    for name in ("install", "uninstall", "doctor"):
        command = commands.add_parser(name)
        command.add_argument(
            "--user-library", type=Path, help="User Library root folder"
        )
        if name != "doctor":
            command.add_argument(
                "--yes", action="store_true", help="Confirm a unique path"
            )
            command.add_argument("--dry-run", action="store_true", help="Preview only")
        if name == "install":
            command.add_argument(
                "--replace", action="store_true", help="Replace Tonable"
            )
            command.add_argument(
                "--reload",
                action="store_true",
                help="Ask running Live to reload after copying",
            )
    args = parser.parse_args(argv)

    if args.command in (None, "serve"):
        from tonable.server import run

        run()
        return 0

    from tonable import cli

    try:
        if args.command == "libraries":
            candidates = cli.discover_libraries()
            for path, origin in candidates:
                print(f"{path} [{origin}]")
            if not candidates:
                print("No existing User Library found; use --user-library PATH.")
            return 0
        if args.command == "doctor":
            return cli.doctor(library=args.user_library)
        library = cli.select_library(args.user_library, yes=args.yes or args.dry_run)
        if args.command == "install":
            cli.install(
                library,
                replace=args.replace,
                dry_run=args.dry_run,
                reload_live=args.reload,
            )
        else:
            cli.uninstall(library, yes=args.yes, dry_run=args.dry_run)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    except (KeyboardInterrupt, EOFError):
        print("Cancelled.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
