# Connect Tonable to an MCP client

Run Live, the Tonable server and the client on the same Mac, under the same user.
Complete the [installation steps](../README.md#install-from-this-repository) first.
Use a client capable of launching a local **stdio** MCP server.

## Find the executable

After `uv tool install .`, run:

```sh
uv tool dir --bin
command -v tonable
```

Use the absolute path to `tonable` in that directory. The examples below use
`/absolute/path/to/tonable` as a placeholder: replace it with your actual path.
Desktop clients may not inherit your shell's `PATH`. Do not put `~`, shell
variables or extra quote characters inside a JSON `command` value.

No environment variables, port, key or working directory are required for an
installed Tonable executable. Run it without arguments, or with `serve`.

## Codex

Register the installed command with the local Codex CLI:

```sh
codex mcp add tonable -- /absolute/path/to/tonable
codex mcp list
```

Alternatively, merge this into `~/.codex/config.toml`:

```toml
[mcp_servers.tonable]
command = "/absolute/path/to/tonable"
args = []
```

Codex CLI and its IDE extension share MCP configuration. Start a new local
session and ask it to call `live_status`, then `read_set`. A cloud worker running
on another machine cannot reach the Live process on your Mac through this setup.

The registration syntax, TOML fields and shared configuration follow the
[official OpenAI MCP documentation](https://developers.openai.com/codex/mcp/),
checked on 6 November 2026. This is not a hosted ChatGPT connector.

## Claude Code

Add Tonable for your user account:

```sh
claude mcp add --transport stdio --scope user tonable -- /absolute/path/to/tonable
claude mcp get tonable
```

Open Claude Code locally and use `/mcp` to inspect the connection. Ask for
`live_status` and `read_set` before trying any edits. The `--` separates client
options from the command that launches Tonable.

This configuration follows the
[official Claude Code MCP documentation](https://code.claude.com/docs/en/mcp),
checked on 6 November 2026. User scope keeps the machine-specific executable path
out of shared project configuration.

## Claude Desktop

Use the local server configuration, not the remote connector form. On macOS, open
**Settings → Developer → Edit Config** and merge this entry into
`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "tonable": {
      "command": "/absolute/path/to/tonable",
      "args": []
    }
  }
}
```

Preserve other server entries. Fully quit Claude Desktop and reopen it. Check
that Tonable's tools appear, then request `live_status` and `read_set`.
Organization policy may restrict local servers.

The file location, entry format and restart procedure follow the
[official MCP local-server guide](https://modelcontextprotocol.io/docs/develop/connect-local-servers),
checked on 6 November 2026. Tonable is not packaged as a Desktop extension.
[Anthropic distinguishes local Desktop servers from remote connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp):
the latter connect from its cloud. This local setup does not enable Tonable in
claude.ai, mobile apps or Cowork.

## Other local MCP clients

Map these settings to your client's documented format:

| Setting | Value |
|---|---|
| Server name | `tonable` |
| Transport | `stdio` |
| Command | Absolute path to the installed `tonable` executable |
| Arguments | Empty list, or `["serve"]` |
| Environment | Same user account as Live; no Tonable-specific variables |
| Working directory | Not required for an installed package |

A client must support MCP tool discovery and tool calls over stdio. Configuration
file names and wrapper keys vary; the Desktop JSON format is not universal.
Check your client's official documentation and verify discovery locally.
Tonable does not offer HTTP, SSE, OAuth, a remote URL or an automatic transport
fallback. Do not expose the Remote Script's loopback port through a tunnel.

## Verify and troubleshoot

1. Run `tonable --version` and `tonable doctor` from a terminal.
2. Connect the client and confirm `tools/list` exposes 24 Tonable tools.
3. Call `live_status`. With Tonable active in Live it should report
   `connected: true`; without Live it should return a readable `not_running` error.
4. Call `read_set` and compare it with the open Set. This step does not edit Live.

If no tools appear, check the absolute executable path, client permissions and
client logs. If tools appear but Live is disconnected, select Tonable as a Control
Surface and run `doctor`. After upgrading, reconnect the server or restart the
client session so it discovers the current tool list.

The setup examples were checked against official documentation, not exercised in
each client UI during publication preparation. The automated checks cover MCP
stdio initialization, tool discovery and disconnected error handling; repeat the
read-only client checks above on your own installation.
