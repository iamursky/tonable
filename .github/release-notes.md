Tonable connects a local MCP client to Ableton Live 12.4+ through 24 tools.

This release includes a Python wheel and source archive. No repository checkout
is needed: use `uvx --python 3.11 --from <wheel-path-or-URL> tonable serve`, or
install the wheel with `uv tool install --python 3.11 <wheel-path-or-URL>`.

Use `tonable libraries` to find a User Library, then `tonable install --dry-run`
to review the destination. `--user-library PATH` selects an explicit folder;
`--replace` permits replacement. Installation does not contact Live unless you
add `--reload`.

CI checks Python 3.11 and 3.13 on Linux and macOS, builds and validates both
archives, tests the extracted source, and checks installation and discovery of
24 MCP tools outside the checkout. These are synthetic tests; they do not replace
manual checks in a disposable Live Set. The Live workflow is validated on macOS;
Windows Live support remains unverified.

See the README for installation and client configuration. Registry installation
is available only after the separate PyPI publication succeeds. MIT and upstream
notices are included in both distributions.
