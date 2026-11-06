#!/bin/sh
# Install the optional Live API probe in Live's configured User Library.
# Usage: probe/install.sh [uninstall | --places-preset /path/to/preset.adg]
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec uv run --project "$here/.." --locked python "$here/install.py" "$@"
