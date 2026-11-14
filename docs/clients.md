# Connect Tonable to an MCP client

Run Live, the Tonable server and the client locally under the same user. Complete
[installation](../README.md#install-without-a-checkout) first. The examples use a
versioned GitHub release wheel. They require no checkout. PyPI availability is
tracked separately; these commands do not depend on a registry publication.

## Choose a launch command

Find uvx with `command -v uvx` on macOS or `where uvx` on Windows. Replace
`/absolute/path/to/uvx` with its real absolute path. Desktop apps may have a
different `PATH` from your terminal. The versioned wheel URL is the package source;
you can also replace it with an absolute path to a downloaded wheel.

Test the launcher in a terminal:

```sh
/absolute/path/to/uvx --python 3.11 \
  --from https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl tonable --version
```

Alternatively, [install the persistent CLI](../README.md#install-without-a-checkout)
with `uv tool install --python 3.11 https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl`.
Find its executable with `uv tool dir --bin`. In each example, you can replace the
uvx command and all its arguments with the absolute `tonable` executable and
`serve`. Neither route needs a working directory or Tonable-specific environment
variables. Use the [uv tools guide](https://docs.astral.sh/uv/guides/tools/) for
installation and cache behavior. First use may need internet access for Python
and dependencies.

Do not put `~`, shell variables or extra quote characters inside JSON paths. On
Windows, escape backslashes as `\\` or use forward slashes. Windows client
syntax is documented by the clients; Tonable's Live workflow has only been
validated on macOS.

## Codex

Register the local stdio launcher:

```sh
codex mcp add tonable -- /absolute/path/to/uvx --python 3.11 \
  --from https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl tonable serve
codex mcp list
```

Or merge this into `~/.codex/config.toml`:

```toml
[mcp_servers.tonable]
command = "/absolute/path/to/uvx"
args = ["--python", "3.11", "--from", "https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl", "tonable", "serve"]
```

Codex CLI and its IDE extension share this configuration. Start a local session;
use `/mcp` to inspect the server, then request `live_status` and `read_set`. A cloud
worker on another machine cannot reach your local Live process through stdio.

The command and TOML fields follow the
[official OpenAI MCP documentation](https://developers.openai.com/codex/mcp/),
checked on 6 November 2026.

## Claude Code

Register Tonable in user scope:

```sh
claude mcp add --transport stdio --scope user tonable -- /absolute/path/to/uvx \
  --python 3.11 --from https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl tonable serve
claude mcp get tonable
```

Use `/mcp` in a local session to inspect the connection. The `--` separates Claude
options from the server command. User scope keeps the local artifact path out of
shared project settings. These fields follow the
[official Claude Code MCP guide](https://code.claude.com/docs/en/mcp), checked on
6 November 2026.

## Claude Desktop

On macOS, open **Settings → Developer → Edit Config**. Merge this entry into
`~/Library/Application Support/Claude/claude_desktop_config.json`, preserving
other servers:

```json
{
  "mcpServers": {
    "tonable": {
      "command": "/absolute/path/to/uvx",
      "args": [
        "--python", "3.11", "--from",
        "https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl",
        "tonable", "serve"
      ]
    }
  }
}
```

Fully quit and reopen Claude Desktop. Confirm that Tonable's tools appear.
Organization policy may restrict local servers. This setup follows the
[official MCP local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers),
checked on 6 November 2026. It uses local stdio; it supplies no remote connector
URL or Desktop extension bundle.

## Other local MCP clients

Use your client's official stdio configuration format:

| Setting | Value |
|---|---|
| Server name | `tonable` |
| Transport | `stdio` |
| Command | Absolute path to `uvx` |
| Arguments | `["--python", "3.11", "--from", "https://github.com/iamursky/tonable/releases/download/v0.6.0/tonable-0.6.0-py3-none-any.whl", "tonable", "serve"]` |
| Environment | Same user account as Live |
| Working directory | Not required |

For a persistent install, use the absolute `tonable` executable and `["serve"]`
instead. A client needs MCP tool discovery and tool calls. JSON wrapper keys and
file locations vary; consult its documentation rather than copying another
client's file. The [MCP local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers)
explains the transport model.

Tonable has no HTTP/SSE endpoint, OAuth flow or hosted connector. The loopback
socket inside Live is private bridge traffic, not an MCP URL. Keep it local.

## Verify and troubleshoot

1. Run `tonable --version` and `tonable doctor`, or invoke those commands with
   the same uvx launcher. Add `--user-library PATH` to `doctor` for a custom path.
2. Connect the client and confirm `tools/list` returns 31 Tonable tools.
3. Request `live_status`. With Tonable selected in Live it should report
   `connected: true`; otherwise it returns `connected: false` and `not_running`.
4. Request `read_set` and compare the result with Live before making edits.

If tools are missing, check the executable path and wheel URL or path, client permissions and
logs. If Live is disconnected, select Tonable as a Control Surface and run
`doctor`. After upgrading, update the configured artifact URL or path and restart the
MCP connection.

These examples were checked against official documentation. Automated checks
exercise the launch commands, stdio initialization, discovery and disconnected
status outside the checkout. No client UI or live Set was changed during this
preparation; repeat the read-only checks in each client you intend to support.
