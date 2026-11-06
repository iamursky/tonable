"""Entry point: `tonable` runs the MCP server on stdio; subcommands set it up."""

import argparse
import sys

from tonable import __version__

USAGE = """\
tonable              run the MCP server on stdio (for local MCP clients)
tonable install      copy the Remote Script into Live's User Library
tonable uninstall    remove the Remote Script
tonable doctor       check the installation and the connection to Live
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tonable", usage=USAGE)
    parser.add_argument("--version", action="version", version=f"tonable {__version__}")
    parser.add_argument(
        "command", nargs="?", choices=["serve", "install", "uninstall", "doctor"]
    )
    args = parser.parse_args(argv)

    if args.command in (None, "serve"):
        from tonable.server import run

        run()
        return 0

    from tonable import cli

    if args.command == "install":
        cli.install()
    elif args.command == "uninstall":
        cli.uninstall()
    else:
        return cli.doctor()
    return 0


if __name__ == "__main__":
    sys.exit(main())
